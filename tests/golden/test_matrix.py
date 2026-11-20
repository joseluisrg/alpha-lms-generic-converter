from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.golden.corpus import GOLDEN_ROOT, load_manifest
from tests.golden.features import SUPPORTED_FEATURES
from tests.golden.matrix import (
    FEATURE_CATEGORIES,
    FEATURE_SOURCES,
    FEATURE_STATUSES,
    FEATURE_TARGETS,
    IMPORT_CHECKS,
    load_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_DOC = REPO_ROOT / "docs" / "FORMAT_MATRIX.md"
MATRIX = load_matrix()
FEATURES: list[dict[str, Any]] = MATRIX["features"]
CASES = {case["id"]: case for case in load_manifest()["cases"]}
EVIDENCE = MATRIX["evidence"]


def test_matrix_covers_every_supported_feature():
    feature_ids = [feature["id"] for feature in FEATURES]

    assert len(feature_ids) == len(set(feature_ids))
    assert set(feature_ids) == set(SUPPORTED_FEATURES)


def test_matrix_targets_are_pinned():
    targets = MATRIX["certification_targets"]

    assert targets["moodle"]["release"] == "5.3 LTS"
    assert targets["moodle"]["patch"] == "5.3.1"
    assert targets["openedx"]["release"] == "Verawood"
    assert targets["openedx"]["patch"] == "Verawood.2"
    assert targets["openedx"]["tutor"] == "22.0.4"


@pytest.mark.parametrize("feature", FEATURES, ids=[feature["id"] for feature in FEATURES])
def test_matrix_feature_is_well_formed(feature: dict[str, Any]):
    assert feature["description"]
    assert feature["category"] in FEATURE_CATEGORIES
    assert feature["source"] in FEATURE_SOURCES
    assert feature["target"] is None or feature["target"] in FEATURE_TARGETS
    assert feature["status"] in FEATURE_STATUSES
    assert feature["evidence"] in CASES
    assert feature["import_check"] is None or feature["import_check"] in IMPORT_CHECKS


@pytest.mark.parametrize("feature", FEATURES, ids=[feature["id"] for feature in FEATURES])
def test_matrix_evidence_paths_exist(feature: dict[str, Any]):
    evidence_set = EVIDENCE.get(feature["evidence"])
    if evidence_set is None:
        return

    for key in ("fixture", "report"):
        if key in evidence_set:
            assert (GOLDEN_ROOT / evidence_set[key]).exists()

    for path in evidence_set.get("export", {}).values():
        assert (GOLDEN_ROOT / path).exists()


def test_migration_features_have_import_checks():
    for feature in FEATURES:
        if feature["category"] not in {"migration", "target"}:
            continue
        if feature["status"] == "unsupported":
            assert feature["import_check"] is None
            continue
        assert feature["import_check"] in {"moodle:restore", "openedx:import"}


def test_control_features_do_not_claim_lms_imports():
    for feature in FEATURES:
        if feature["category"] == "roundtrip":
            assert feature["status"] == "control"
            assert feature["import_check"] == "roundtrip"
        elif feature["category"] in {"validation", "security"}:
            assert feature["status"] == "control"
            assert feature["target"] is None
            assert feature["import_check"] is None


def test_placeholder_and_unsupported_features_have_evidence_and_notes():
    for feature in FEATURES:
        if feature["status"] not in {"placeholder", "unsupported"}:
            continue
        assert feature["notes"]
        assert EVIDENCE.get(feature["evidence"], {}).get("report")


def test_format_matrix_doc_mentions_every_feature():
    text = MATRIX_DOC.read_text(encoding="utf-8")

    missing = [feature["id"] for feature in FEATURES if feature["id"] not in text]
    assert not missing


def test_format_matrix_doc_statuses_match_json():
    rows: dict[str, list[str]] = {}
    for line in MATRIX_DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        rows[cells[0].strip("`")] = cells

    for feature in FEATURES:
        cells = rows[feature["id"]]
        assert cells[2] == feature["status"]
        assert cells[3] == (feature["import_check"] or "-")
