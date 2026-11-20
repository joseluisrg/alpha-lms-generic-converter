"""SQLite persistence for inspection and migration jobs.

The store is deliberately small but production-oriented: WAL mode, bounded
connection timeouts, transactional writes, forward-compatible schema upgrades,
and explicit lifecycle fields so operators can distinguish inspected,
migrated, and failed jobs.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from core.config import get_settings
from core.errors import JobAccessError, LedgerRollbackError
from core.identity import sha256_text, tool_version
from domain.entities import Course

DEFAULT_OWNER = "local"

_REQUIRED_COLUMNS = {
    "status": "TEXT NOT NULL DEFAULT 'inspected'",
    "output_path": "TEXT",
    "error": "TEXT",
    "updated_at": "TIMESTAMP",
    "owner": "TEXT NOT NULL DEFAULT 'local'",
    # ST-4: path to versioned manifest.json written after each migration
    "manifest_path": "TEXT",
}


def _database_path() -> Path:
    """Resolve the database path at call time so configuration is never stale."""
    return get_settings().db_path


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a configured connection and always close it."""
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            target_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'inspected',
            owner TEXT NOT NULL DEFAULT 'local',
            course_json TEXT,
            report_json TEXT,
            extracted_path TEXT,
            output_path TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
    }
    for name, definition in _REQUIRED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")

    # PR-05 coordination: assign the next schema version number here
    # once the PRAGMA user_version migration system lands in PR-05.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_events (
            event_id      TEXT PRIMARY KEY,
            job_id        TEXT NOT NULL,
            owner         TEXT NOT NULL DEFAULT 'local',
            event         TEXT NOT NULL,
            step          TEXT NOT NULL DEFAULT '',
            input_hash    TEXT NOT NULL DEFAULT '',
            output_hash   TEXT NOT NULL DEFAULT '',
            tool_version  TEXT NOT NULL DEFAULT '',
            actor         TEXT NOT NULL DEFAULT 'local',
            prev_event_id TEXT,
            recorded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
        """
    )
    conn.commit()


def init_db() -> None:
    """Create or upgrade the jobs table."""
    with _connect() as conn:
        _ensure_schema(conn)


def _serialize_course(course: Any) -> str:
    if hasattr(course, "model_dump_json"):
        return course.model_dump_json()
    if hasattr(course, "dict"):
        return json.dumps(course.dict())
    return json.dumps(course)


def _serialize_report(report: list) -> str:
    items = []
    for item in report:
        if hasattr(item, "model_dump"):
            items.append(item.model_dump(mode="json"))
        else:
            items.append(item)
    return json.dumps(items)


def save_job(
    job_id: str,
    source_type: str,
    target_type: str,
    course: Any,
    report: list,
    extracted_path: Optional[str] = None,
    *,
    status: str = "inspected",
    owner: str = DEFAULT_OWNER,
) -> None:
    """Save a newly inspected job and its canonical course snapshot."""
    init_db()
    with _connect() as conn:
        # Fetch the previous canonical Course snapshot (if any) so we can
        # record it as course_before in the ledger event.
        existing = conn.execute(
            "SELECT owner, course_json FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if existing and existing["owner"] != owner:
            raise JobAccessError(f"Job {job_id} belongs to another owner")
        conn.execute(
            """
            INSERT INTO jobs
                (job_id, source_type, target_type, status, owner, course_json,
                 report_json, extracted_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                source_type = excluded.source_type,
                target_type = excluded.target_type,
                status = excluded.status,
                owner = excluded.owner,
                course_json = excluded.course_json,
                report_json = excluded.report_json,
                extracted_path = excluded.extracted_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                job_id,
                source_type,
                target_type or "",
                status,
                owner,
                _serialize_course(course),
                _serialize_report(report),
                extracted_path,
            ),
        )
        conn.commit()

    # Append ledger event after the jobs row is committed.
    # course_before = whatever Course was stored before this call (None on
    # first insert).  course_after = the new Course being saved now.
    course_before: Any = None
    if existing and existing["course_json"]:
        try:
            course_before = Course.model_validate_json(existing["course_json"])
        except Exception:
            pass  # graceful fallback; input_hash will be hash of empty string
    append_job_event(
        job_id=job_id,
        event=status,
        step="parse|transform|validate",
        course_before=course_before,
        course_after=course,
        owner=owner,
        actor=owner,
    )


def save_migration_job(
    job_id: str,
    source_type: str,
    target_type: str,
    course: Any,
    report: list,
    extracted_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    owner: str = DEFAULT_OWNER,
) -> None:
    """Mark an existing job as migrated, preserving its report when omitted."""
    init_db()
    with _connect() as conn:
        # Also fetch course_json so we can compute course_before for the ledger.
        existing = conn.execute(
            "SELECT report_json, extracted_path, owner, course_json FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        if existing and existing["owner"] != owner:
            raise JobAccessError(f"Job {job_id} belongs to another owner")
        effective_owner = owner

        report_json = _serialize_report(report) if report else None
        if report_json is None and existing:
            report_json = existing["report_json"] or "[]"
        if not extracted_path and existing:
            extracted_path = existing["extracted_path"]

        conn.execute(
            """
            INSERT INTO jobs
                (job_id, source_type, target_type, status, owner, course_json,
                 report_json, extracted_path, output_path, error, updated_at)
            VALUES (?, ?, ?, 'migrated', ?, ?, ?, ?, ?, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                source_type = excluded.source_type,
                target_type = excluded.target_type,
                status = excluded.status,
                owner = excluded.owner,
                course_json = excluded.course_json,
                report_json = excluded.report_json,
                extracted_path = excluded.extracted_path,
                output_path = excluded.output_path,
                error = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                job_id,
                source_type,
                target_type,
                effective_owner,
                _serialize_course(course),
                report_json or "[]",
                extracted_path,
                output_path,
            ),
        )
        conn.commit()

    # Append ledger event after committing the job row.
    course_before: Any = None
    if existing and existing["course_json"]:
        try:
            course_before = Course.model_validate_json(existing["course_json"])
        except Exception:
            pass
    append_job_event(
        job_id=job_id,
        event="migrated",
        step="export",
        course_before=course_before,
        course_after=course,
        owner=effective_owner,
        actor=effective_owner,
    )


def mark_job_failed(
    job_id: str, error: str, *, owner: Optional[str] = None
) -> None:
    """Record a terminal failure without discarding the stored course snapshot."""
    init_db()
    with _connect() as conn:
        if owner is None:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
                """,
                (error, job_id),
            )
        else:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND owner = ?
                """,
                (error, job_id, owner),
            )
        conn.commit()

    # Append failed event; no course snapshot available at failure time so
    # both input_hash and output_hash will be empty strings.
    append_job_event(
        job_id=job_id,
        event="failed",
        step="",
        course_before=None,
        course_after=None,
        owner=owner or DEFAULT_OWNER,
        actor=owner or DEFAULT_OWNER,
    )


def get_job(job_id: str, *, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a job by ID, optionally constrained to its owner."""
    init_db()
    with _connect() as conn:
        if owner is None:
            row = conn.execute(
                """
                SELECT job_id, source_type, target_type, status, owner,
                       course_json, report_json, extracted_path, output_path,
                       error, created_at, updated_at
                FROM jobs WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT job_id, source_type, target_type, status, owner,
                       course_json, report_json, extracted_path, output_path,
                       error, created_at, updated_at
                FROM jobs WHERE job_id = ? AND owner = ?
                """,
                (job_id, owner),
            ).fetchone()
    return dict(row) if row else None


def list_jobs(
    limit: int = 100, *, owner: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return recent jobs without loading the potentially large course JSON."""
    init_db()
    with _connect() as conn:
        if owner is None:
            rows = conn.execute(
                """
                SELECT job_id, source_type, target_type, status, owner,
                       extracted_path, output_path, error, created_at, updated_at
                FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(0, int(limit)),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT job_id, source_type, target_type, status, owner,
                       extracted_path, output_path, error, created_at, updated_at
                FROM jobs
                WHERE owner = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (owner, max(0, int(limit))),
            ).fetchall()
    return [dict(row) for row in rows]


def delete_job(job_id: str, *, owner: Optional[str] = None) -> bool:
    """Delete a job and its ledger events. Returns whether a row was removed.

    ``job_events`` rows reference ``jobs`` via a foreign key so they are removed
    first within the same transaction.  When *owner* is supplied, ledger rows are
    only deleted if the job belongs to that owner; a mismatched owner returns
    False without touching anything.

    See the plan (Part F) for the known limitation: this administrative path
    removes ledger rows without leaving a trace.  A future ``admin_events``
    table is proposed to record such destructive operations.
    """
    init_db()
    with _connect() as conn:
        if owner is None:
            # Delete ledger rows first to satisfy the foreign-key constraint.
            conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
            cursor = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        else:
            # Only cascade into ledger rows when the job actually belongs to
            # this owner; otherwise the jobs DELETE will simply find zero rows.
            existing = conn.execute(
                "SELECT owner FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if existing and existing["owner"] == owner:
                conn.execute(
                    "DELETE FROM job_events WHERE job_id = ?", (job_id,)
                )
            cursor = conn.execute(
                "DELETE FROM jobs WHERE job_id = ? AND owner = ?", (job_id, owner)
            )
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------


def _serialize_course_no_fragments(course: Any) -> str:
    """Serialize a Course with raw_fragments cleared (PII guard).

    ``input_hash`` and ``output_hash`` in job_events are computed from this
    representation so raw XML source text is never stored in hashes or manifests.

    Known limitation: the hash is a byte-level digest of the Pydantic JSON
    serialisation.  Semantically equivalent values that differ in format
    (e.g. ``1.0`` vs ``1``, ``null`` vs omitted key) will produce different
    hashes even though the course content is unchanged.  The hash is intended
    as a quick change-detector, not a semantic equivalence checker.
    """
    if course is None:
        return ""
    if hasattr(course, "model_copy"):
        # Pydantic v2: in-memory copy with raw_fragments stripped
        stripped = course.model_copy(update={"raw_fragments": []})
        return stripped.model_dump_json()
    if hasattr(course, "dict"):
        d = course.dict()
        d["raw_fragments"] = []
        return json.dumps(d)
    return json.dumps({})


def append_job_event(
    job_id: str,
    event: str,
    step: str,
    course_before: Any,
    course_after: Any,
    owner: str,
    actor: str,
) -> None:
    """Append an immutable event row to job_events.

    This is the only write path for job_events — rows are never updated or
    deleted during normal operation (see purge_ledger_entries_before for the
    maintenance-only delete path used by PR-06 retention).
    """
    init_db()
    event_id = str(uuid.uuid4())
    input_hash = sha256_text(_serialize_course_no_fragments(course_before))
    output_hash = sha256_text(_serialize_course_no_fragments(course_after))
    ver = tool_version()

    with _connect() as conn:
        prev_row = conn.execute(
            """
            SELECT event_id FROM job_events
            WHERE job_id = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        prev_event_id = prev_row["event_id"] if prev_row else None

        conn.execute(
            """
            INSERT INTO job_events
                (event_id, job_id, owner, event, step,
                 input_hash, output_hash, tool_version, actor, prev_event_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, job_id, owner, event, step,
                input_hash, output_hash, ver, actor, prev_event_id,
            ),
        )
        conn.commit()


def get_job_events(
    job_id: str, *, owner: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return all ledger events for a job, ordered oldest first.

    When *owner* is provided only events whose ``owner`` column matches are
    returned — identical scoping to :func:`get_job`.
    """
    init_db()
    with _connect() as conn:
        if owner is None:
            rows = conn.execute(
                """
                SELECT event_id, job_id, owner, event, step,
                       input_hash, output_hash, tool_version, actor,
                       prev_event_id, recorded_at
                FROM job_events
                WHERE job_id = ?
                ORDER BY recorded_at ASC
                """,
                (job_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT event_id, job_id, owner, event, step,
                       input_hash, output_hash, tool_version, actor,
                       prev_event_id, recorded_at
                FROM job_events
                WHERE job_id = ? AND owner = ?
                ORDER BY recorded_at ASC
                """,
                (job_id, owner),
            ).fetchall()
    return [dict(row) for row in rows]


def purge_ledger_entries_before(
    cutoff_ts: str, *, owner: Optional[str] = None
) -> int:
    """Delete job_events rows recorded before *cutoff_ts*.

    This is a maintenance-only operation intended to be called by the PR-06
    retention scheduler.  It is never wired into any automatic write path.

    Returns the number of rows deleted.
    """
    init_db()
    with _connect() as conn:
        if owner is None:
            cursor = conn.execute(
                "DELETE FROM job_events WHERE recorded_at < ?",
                (cutoff_ts,),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM job_events WHERE recorded_at < ? AND owner = ?",
                (cutoff_ts, owner),
            )
        conn.commit()
        return cursor.rowcount
