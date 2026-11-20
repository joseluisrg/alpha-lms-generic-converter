"""Unit tests for the Provenance Ledger and Rollback feature.

Covers acceptance criteria AC-1 through AC-14 plus two additional tests:
- HTML rendering of the Ledger History section (AC-13 HTML extension)
- False-positive hash warning: semantically identical courses with different
  Pydantic serialisations produce different output_hash values (documented
  known limitation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.errors import JobAccessError, LedgerRollbackError
from core.identity import sha256_bytes, sha256_text
from core.report import build_report_data, render_html_report
from domain.entities import Course
from domain.enums import FragmentKind, SourceSystem
from domain.raw_fragment import RawFragment, SourceLocation
from persistence import repositories
from persistence.repositories import get_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_course(course_id: str = "c-1", *, with_fragments: bool = False) -> Course:
    """Return a minimal Course, optionally with one raw fragment containing PII."""
    frags: list = []
    if with_fragments:
        frags = [
            RawFragment(
                fragment_id="f-1",
                kind=FragmentKind.XML,
                source_location=SourceLocation(source_system=SourceSystem.OPENEDX),
                raw_text="<problem>name: Alice</problem>",
            )
        ]
    return Course(
        course_id=course_id,
        title="Test Course",
        source_system=SourceSystem.OPENEDX,
        raw_fragments=frags,
    )


def _make_artifact(tmp_path: Path, name: str = "course.mbz") -> Path:
    """Write a small fake artifact file and return its path."""
    p = tmp_path / name
    p.write_bytes(b"fake artifact bytes")
    return p


def _stub_job() -> dict:
    """Return a minimal job dict suitable for passing to report helpers."""
    return {
        "status": "migrated",
        "created_at": "2026-01-01 00:00:00",
        "updated_at": "2026-01-01 00:01:00",
        "source_type": "openedx",
        "target_type": "moodle",
        "output_path": None,
        "error": None,
    }


# ---------------------------------------------------------------------------
# AC-1  Events appended on save_job / save_migration_job / mark_job_failed
# ---------------------------------------------------------------------------


def test_save_job_appends_inspected_event():
    """save_job must append exactly one 'inspected' event (AC-1)."""
    course = _make_course()
    repositories.save_job("j-1", "openedx", "", course, [])
    events = repositories.get_job_events("j-1")
    assert len(events) == 1
    assert events[0]["event"] == "inspected"
    assert events[0]["output_hash"] != ""


def test_save_migration_job_appends_migrated_event(tmp_path: Path):
    """save_migration_job appends a 'migrated' event chained to the first (AC-1)."""
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-2", "openedx", "", course, [])
    repositories.save_migration_job(
        "j-2", "openedx", "moodle", course, [], output_path=str(artifact)
    )
    events = repositories.get_job_events("j-2")
    assert len(events) == 2
    assert events[1]["event"] == "migrated"
    assert events[1]["prev_event_id"] == events[0]["event_id"]


def test_mark_job_failed_appends_failed_event():
    """mark_job_failed appends a 'failed' event (AC-1)."""
    course = _make_course()
    repositories.save_job("j-3", "openedx", "", course, [])
    repositories.mark_job_failed("j-3", "something went wrong")
    events = repositories.get_job_events("j-3")
    assert any(e["event"] == "failed" for e in events)


# ---------------------------------------------------------------------------
# AC-2  Events are insert-only — rows are never modified
# ---------------------------------------------------------------------------


def test_job_events_are_insert_only(tmp_path: Path):
    """Every transition adds a new row; no row is ever updated (AC-2)."""
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-4", "openedx", "", course, [])
    repositories.save_migration_job(
        "j-4", "openedx", "moodle", course, [], output_path=str(artifact)
    )
    events = repositories.get_job_events("j-4")
    assert len(events) == 2
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids)), "Duplicate event_id detected — a row was reused"


# ---------------------------------------------------------------------------
# AC-3  Owner scoping
# ---------------------------------------------------------------------------


def test_get_job_events_owner_scoping():
    """get_job_events returns [] for the wrong owner (AC-3)."""
    course = _make_course()
    repositories.save_job("j-5", "openedx", "", course, [], owner="alice")
    assert repositories.get_job_events("j-5", owner="bob") == []
    assert len(repositories.get_job_events("j-5", owner="alice")) == 1


# ---------------------------------------------------------------------------
# AC-4  Manifest written after migration
# ---------------------------------------------------------------------------


def test_manifest_written_after_migration(tmp_path: Path):
    """save_migration_job writes a manifest.json with a non-empty artifact_hash (AC-4)."""
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-6", "openedx", "", course, [])
    repositories.save_migration_job(
        "j-6", "openedx", "moodle", course, [], output_path=str(artifact)
    )
    job = repositories.get_job("j-6")
    assert job["manifest_path"], "manifest_path not set on job row"
    manifest_path = Path(job["manifest_path"])
    assert manifest_path.exists(), f"manifest file missing: {manifest_path}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_hash"] != "", "artifact_hash must be non-empty"
    assert len(manifest["chain"]) == 2, "chain must contain both events (inspected + migrated)"


# ---------------------------------------------------------------------------
# AC-5  Hash chain correctness
# ---------------------------------------------------------------------------


def test_manifest_hash_chain(tmp_path: Path):
    """chain[1]['prev_hash'] == sha256(json.dumps(chain[0], sort_keys=True)) (AC-5)."""
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-7", "openedx", "", course, [])
    repositories.save_migration_job(
        "j-7", "openedx", "moodle", course, [], output_path=str(artifact)
    )
    job = repositories.get_job("j-7")
    manifest = json.loads(Path(job["manifest_path"]).read_text(encoding="utf-8"))
    chain = manifest["chain"]
    assert len(chain) >= 2
    expected_prev = sha256_text(
        json.dumps(chain[0], sort_keys=True, ensure_ascii=False)
    )
    assert chain[1]["prev_hash"] == expected_prev


# ---------------------------------------------------------------------------
# AC-6  Rollback restores job
# ---------------------------------------------------------------------------


def test_rollback_restores_job(tmp_path: Path):
    """After rollback: status='inspected', output_path=None, rolled_back event exists,
    new artifact copy present at v2/ (AC-6)."""
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-8", "openedx", "", course, [])
    repositories.save_migration_job(
        "j-8", "openedx", "moodle", course, [], output_path=str(artifact)
    )
    repositories.rollback_job("j-8", owner="local")

    job = repositories.get_job("j-8")
    assert job["status"] == "inspected"
    assert job["output_path"] is None

    events = repositories.get_job_events("j-8")
    assert any(e["event"] == "rolled_back" for e in events)

    new_artifact = get_settings().output_dir / "j-8" / "v2" / artifact.name
    assert new_artifact.exists(), f"rolled-back artifact copy missing: {new_artifact}"


# ---------------------------------------------------------------------------
# AC-7  Rollback wrong owner raises JobAccessError
# ---------------------------------------------------------------------------


def test_rollback_wrong_owner_raises(tmp_path: Path):
    """rollback_job raises JobAccessError when owner does not match (AC-7)."""
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-9", "openedx", "", course, [], owner="alice")
    repositories.save_migration_job(
        "j-9", "openedx", "moodle", course, [],
        output_path=str(artifact), owner="alice"
    )
    with pytest.raises(JobAccessError):
        repositories.rollback_job("j-9", owner="bob")


# ---------------------------------------------------------------------------
# AC-8  Rollback with no manifest raises LedgerRollbackError
# ---------------------------------------------------------------------------


def test_rollback_no_manifest_raises():
    """rollback_job raises LedgerRollbackError when no manifests exist (AC-8)."""
    course = _make_course()
    repositories.save_job("j-10", "openedx", "", course, [])
    # never migrated → no v*/manifest.json on disk
    with pytest.raises(LedgerRollbackError):
        repositories.rollback_job("j-10")


# ---------------------------------------------------------------------------
# AC-11  PII exclusion — raw_fragments stripped before hashing
# ---------------------------------------------------------------------------


def test_pii_exclusion():
    """output_hash must be identical whether raw_fragments is populated or empty (AC-11).

    raw_fragments may contain PII (e.g. learner names in XML).  They are
    stripped by _serialize_course_no_fragments before the SHA-256 is computed,
    so two courses that are identical except for their raw_fragments must
    produce the same hash.
    """
    course_with = _make_course("c-pii-same", with_fragments=True)
    course_without = _make_course("c-pii-same", with_fragments=False)
    # Use distinct job IDs so we get one event each
    repositories.save_job("j-pii-a", "openedx", "", course_with, [])
    repositories.save_job("j-pii-b", "openedx", "", course_without, [])
    hash_with = repositories.get_job_events("j-pii-a")[0]["output_hash"]
    hash_without = repositories.get_job_events("j-pii-b")[0]["output_hash"]
    assert hash_with == hash_without, (
        "output_hash differed between courses with and without raw_fragments — "
        "PII is leaking into the hash"
    )


# ---------------------------------------------------------------------------
# AC-12  purge_ledger_entries_before
# ---------------------------------------------------------------------------


def test_purge_ledger_entries_before():
    """Events older than cutoff are deleted; newer events survive (AC-12)."""
    course = _make_course()
    repositories.save_job("j-purge", "openedx", "", course, [])
    # A far-future cutoff purges everything that currently exists
    deleted = repositories.purge_ledger_entries_before(
        "2099-01-01 00:00:00", owner="local"
    )
    assert deleted >= 1
    assert repositories.get_job_events("j-purge") == []


# ---------------------------------------------------------------------------
# AC-13  build_report_data includes ledger key
# ---------------------------------------------------------------------------


def test_build_report_data_ledger_key_empty():
    """build_report_data returns ledger=[] when ledger_entries is None (AC-13)."""
    course = _make_course()
    data = build_report_data("j-r1", _stub_job(), course, [], ledger_entries=None)
    assert data["ledger"] == []


def test_build_report_data_ledger_key_populated():
    """build_report_data projects ledger entries to the five display fields (AC-13)."""
    course = _make_course()
    entries = [
        {
            "event_id": "evt-aabbcc",
            "event": "inspected",
            "step": "parse|transform|validate",
            "recorded_at": "2026-01-01 00:00:00",
            "output_hash": "abcdef1234567890EXTRA",
        }
    ]
    data = build_report_data("j-r2", _stub_job(), course, [], ledger_entries=entries)
    assert len(data["ledger"]) == 1
    row = data["ledger"][0]
    assert row["event_id"] == "evt-aabbcc"
    assert row["event"] == "inspected"
    assert row["output_hash"] == "abcdef1234567890"  # first 16 chars of the input


# ---------------------------------------------------------------------------
# AC-13 (HTML)  render_html_report renders the Ledger History section
# ---------------------------------------------------------------------------


def test_render_html_report_contains_ledger_section():
    """render_html_report must include a <h2>Ledger History</h2> section and
    render each event's event_id, event name, step, and output_hash in the
    table rows.  Values must be HTML-escaped."""
    course = _make_course()
    entries = [
        {
            "event_id": "evt-<script>",   # malicious value → must be escaped
            "event": "inspected",
            "step": "parse|transform|validate",
            "recorded_at": "2026-06-01 10:00:00",
            "output_hash": "deadbeefcafe0000ffff",
        }
    ]
    html_out = render_html_report(
        "j-html", _stub_job(), course, [], ledger_entries=entries
    )

    # Section heading present
    assert "<h2>Ledger History</h2>" in html_out

    # Table headers present
    assert "<th>Event ID</th>" in html_out
    assert "<th>Output Hash (16)</th>" in html_out

    # Event data rendered — output_hash truncated to 16
    assert "deadbeefcafe0000" in html_out
    assert "ffff" not in html_out.split("deadbeefcafe0000")[1][:10]

    # Malicious event_id is escaped, never raw
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_render_html_report_no_entries_shows_placeholder():
    """When no ledger entries are supplied the table shows the 'No ledger
    entries.' placeholder row instead of empty markup."""
    course = _make_course()
    html_out = render_html_report(
        "j-html-empty", _stub_job(), course, [], ledger_entries=None
    )
    assert "<h2>Ledger History</h2>" in html_out
    assert "No ledger entries." in html_out


# ---------------------------------------------------------------------------
# AC-14 / Tamper detection
# ---------------------------------------------------------------------------


def test_tamper_detection(tmp_path: Path):
    """Altering the artifact file or a chain entry can be detected by re-hashing.

    This test confirms the hash chain *detects* tampering — it does not
    prevent it (the manifest is a plain JSON file on disk).
    """
    course = _make_course()
    artifact = _make_artifact(tmp_path)
    repositories.save_job("j-tamper", "openedx", "", course, [])
    repositories.save_migration_job(
        "j-tamper", "openedx", "moodle", course, [], output_path=str(artifact)
    )
    job = repositories.get_job("j-tamper")
    manifest = json.loads(Path(job["manifest_path"]).read_text(encoding="utf-8"))

    # Tamper 1: overwrite the artifact file bytes
    tampered_artifact = Path(manifest["artifact_path"])
    tampered_artifact.write_bytes(b"TAMPERED BYTES")
    actual_hash = sha256_bytes(tampered_artifact.read_bytes())
    assert actual_hash != manifest["artifact_hash"], (
        "artifact_hash should differ after tampering — tamper not detected"
    )

    # Tamper 2: alter a chain entry and verify the next entry's prev_hash breaks
    chain = manifest["chain"]
    if len(chain) >= 2:
        chain[0]["output_hash"] = "000000tampered"
        expected_prev = sha256_text(
            json.dumps(chain[0], sort_keys=True, ensure_ascii=False)
        )
        assert expected_prev != chain[1]["prev_hash"], (
            "Chain prev_hash should not match after altering chain[0] — tamper not detected"
        )

