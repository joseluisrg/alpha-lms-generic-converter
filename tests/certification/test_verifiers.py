from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from domain.entities import Course
from domain.enums import SourceSystem
from tests.certification.evidence import Evidence, load_evidence
from tests.certification.models import FeatureOutcome
from tests.certification.verifiers import (
    VERIFIERS,
    _openedx_package_asset,
    verify_feature,
)
from tests.golden.corpus import load_manifest, run_case, run_export
from tests.golden.matrix import load_matrix

CASES = (("openedx/core", "moodle"), ("moodle/core", "openedx"))


def test_every_non_placeholder_feature_has_a_verifier(tmp_path: Path):
    matrix = load_matrix()
    manifest = load_manifest()

    for case_id, target in CASES:
        case = next(case for case in manifest["cases"] if case["id"] == case_id)
        result = run_case(case, tmp_path / case_id.replace("/", "-"))
        export = run_export(
            result["course"],
            target,
            result["parsed"].get("extracted_path"),
            case_id,
            tmp_path / f"{case_id.replace('/', '-')}-export",
        )
        evidence = load_evidence(
            export["archive"],
            target,
            tmp_path / f"{case_id.replace('/', '-')}-evidence",
        )
        import_check = f"{target}:{'restore' if target == 'moodle' else 'import'}"

        for feature in matrix["features"]:
            if feature.get("import_check") != import_check or feature["status"] == "placeholder":
                continue
            assert feature["id"] in VERIFIERS
            check = verify_feature(feature["id"], evidence, evidence)
            assert check.outcome == FeatureOutcome.VERIFIED, feature["id"]


def test_openedx_package_check_accepts_rezipped_scorm_contents(tmp_path: Path):
    source = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "golden"
        / "moodle"
        / "core"
        / "source"
        / "activities"
        / "scorm_10"
        / "package.zip"
    )
    rezipped = tmp_path / "package.zip"
    with (
        zipfile.ZipFile(source) as original_zip,
        zipfile.ZipFile(rezipped, "w", compression=zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for info in original_zip.infolist():
            output_zip.writestr(info.filename, original_zip.read(info))

    assert (
        hashlib.sha256(source.read_bytes()).digest()
        != hashlib.sha256(rezipped.read_bytes()).digest()
    )

    course = Course(course_id="course", title="Course", source_system=SourceSystem.OPENEDX)
    original = Evidence(
        archive=source,
        target="openedx",
        course=course,
        extracted=source.parent,
        openedx_scorm={"scorm/unit/package.zip": source},
    )
    reimport = Evidence(
        archive=rezipped,
        target="openedx",
        course=course,
        extracted=tmp_path,
        openedx_scorm={"scorm/unit/package.zip": rezipped},
    )

    _openedx_package_asset(original, reimport)
