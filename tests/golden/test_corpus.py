from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.parse import ParseService
from core.transform import TransformService
from domain.entities import Course
from tests.golden.corpus import (
    GOLDEN_ROOT,
    expected_path,
    load_manifest,
    run_case,
    run_export,
    run_roundtrip,
    source_dir,
    tree_digest,
    valid_cases,
)
from tests.golden.snapshots import (
    assert_json_snapshot,
    snapshot_course,
    snapshot_export_tree,
    snapshot_report,
)

MANIFEST = load_manifest()
VALID_CASES = valid_cases(MANIFEST)
BINARY_CONTRACTS = MANIFEST.get("binary_contracts", [])


def _case_id(case: dict) -> str:
    return case["id"]


def _assert_roundtrip_matches(original: Course, roundtrip: Course) -> None:
    assert roundtrip.title == original.title
    assert len(roundtrip.content_nodes) == len(original.content_nodes)
    assert len(roundtrip.assessments) == len(original.assessments)
    assert len(roundtrip.questions) == len(original.questions)


@pytest.mark.parametrize("case", VALID_CASES, ids=[_case_id(case) for case in VALID_CASES])
def test_golden_case(case: dict, tmp_path: Path):
    assert tree_digest(source_dir(case)) == case["source_sha256"]

    result = run_case(case, tmp_path)
    assert result["course"].integrity_errors() == []

    assert_json_snapshot(
        snapshot_course(result["course"], case),
        expected_path(case, "course"),
    )
    assert_json_snapshot(
        snapshot_report(
            result["course"],
            result["report"],
            case,
            result["report_target"],
        ),
        expected_path(case, "report"),
    )

    for target in case.get("targets", []):
        export = run_export(
            result["course"],
            target,
            result["parsed"].get("extracted_path"),
            case["id"],
            tmp_path,
        )
        assert_json_snapshot(
            snapshot_export_tree(export["extract_dir"], case["id"], target),
            expected_path(case, "exports", target),
        )

        if case.get("roundtrip"):
            roundtrip = run_roundtrip(export["archive"], target, tmp_path)
            assert roundtrip.integrity_errors() == []
            _assert_roundtrip_matches(result["course"], roundtrip)


@pytest.mark.parametrize(
    "contract",
    BINARY_CONTRACTS,
    ids=[contract["id"] for contract in BINARY_CONTRACTS],
)
def test_binary_contract_parses(contract: dict, tmp_path: Path):
    path = GOLDEN_ROOT / contract["path"]
    assert path.stat().st_size == contract["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == contract["sha256"]

    parsed = ParseService().parse(
        str(path),
        contract["source"],
        str(tmp_path / "binary-extracted"),
    )
    course = TransformService().transform(parsed, contract["source"], "golden-binary")
    assert course.title
    assert course.integrity_errors() == []
