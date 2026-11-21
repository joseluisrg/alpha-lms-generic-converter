from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.certification.fakes import fake_artifact, target_factory_for
from tests.certification.models import (
    CertificationReport,
    FeatureOutcome,
    ImportStatus,
    ReportStatus,
)
from tests.certification.plan import build_plan
from tests.certification.runner import report_json, run_certification
from tests.certification.targets import FeatureCheck

GENERATED_AT = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def _run(plan, tmp_path: Path, **target_kwargs):
    environments = {planned.target: planned.environment for planned in plan.imports}
    factory, targets = target_factory_for(environments, **target_kwargs)
    report = run_certification(
        plan,
        tmp_path,
        factory,
        artifact_builder=fake_artifact,
        run_id="test-run",
        generated_at=GENERATED_AT,
    )
    return report, targets


def test_runner_passes_with_verified_and_placeholder_features(tmp_path: Path):
    report, targets = _run(build_plan(), tmp_path)

    assert report.status == ReportStatus.PASSED
    assert report.run_id == "test-run"
    assert report.summary.cases_total == 2
    assert report.summary.cases_passed == 2
    assert report.summary.features_total == 57
    assert report.summary.features_verified == 39
    assert report.summary.features_expected_gap == 18
    assert report.summary.features_not_verified == 0
    assert report.summary.features_failed == 0
    assert len(targets) == 2
    assert all(target.closed for target in targets)
    assert sum(len(target.verified) for target in targets) == 39

    for case in report.cases:
        assert case.status.value == "passed"
        assert len(case.artifact.sha256) == 64
        assert case.import_result.log_file == "import.log"
        assert all(feature.outcome != FeatureOutcome.NOT_VERIFIED for feature in case.features)


def test_runner_fails_when_verifier_is_missing(tmp_path: Path):
    plan = build_plan()
    feature = next(
        feature
        for planned in plan.imports
        for feature in planned.features
        if feature["status"] == "native"
    )
    report, _ = _run(plan, tmp_path, missing_verifiers={feature["id"]})

    assert report.status == ReportStatus.FAILED
    assert report.summary.cases_failed == 1
    assert report.summary.features_not_verified == 1
    assert any(feature["id"] in error for case in report.cases for error in case.errors)


def test_runner_marks_all_features_not_verified_when_import_fails(tmp_path: Path):
    report, targets = _run(
        build_plan(),
        tmp_path,
        import_status=ImportStatus.FAILED,
        import_message="restore failed",
    )

    assert report.status == ReportStatus.FAILED
    assert report.summary.cases_failed == 2
    assert report.summary.features_verified == 0
    assert report.summary.features_not_verified == 57
    assert all(not target.verified for target in targets)
    assert all(case.import_result.status == ImportStatus.FAILED for case in report.cases)


def test_runner_records_verifier_reported_gap_as_failure(tmp_path: Path):
    plan = build_plan()
    feature = next(
        feature
        for planned in plan.imports
        for feature in planned.features
        if feature["status"] == "transformed"
    )
    report, _ = _run(
        plan,
        tmp_path,
        feature_outcomes={
            feature["id"]: FeatureCheck(
                FeatureOutcome.EXPECTED_GAP,
                "component was dropped",
            )
        },
    )

    assert report.status == ReportStatus.FAILED
    assert report.summary.features_failed == 1
    assert any(feature["id"] in error for case in report.cases for error in case.errors)


def test_runner_redacts_credentials_from_report(tmp_path: Path):
    report, _ = _run(
        build_plan(),
        tmp_path,
        import_status=ImportStatus.FAILED,
        import_message="password=hunter2 https://user:secret@example.test",
        import_command=["fake-import", "--token=abc123"],
    )

    payload = report_json(report)
    assert "hunter2" not in payload
    assert "secret" not in payload
    assert "abc123" not in payload
    assert "<redacted>" in payload


def test_runner_report_roundtrips_as_json(tmp_path: Path):
    report, _ = _run(build_plan(), tmp_path)
    payload = report_json(report)

    parsed = CertificationReport.model_validate(json.loads(payload))

    assert parsed == report
    assert payload == report_json(parsed)


def test_runner_is_deterministic_for_fixed_inputs(tmp_path: Path):
    first, _ = _run(build_plan(), tmp_path / "first")
    second, _ = _run(build_plan(), tmp_path / "second")

    assert report_json(first) == report_json(second)
