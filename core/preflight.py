"""Report actionable findings for a Moodle course bound for Open edX."""

from core.archive_utils import resolve_under
from core.errors import UnsafePathError
from core.identity import stable_id
from domain.entities import Course, MappingNote
from domain.enums import Severity

_ESSAY_PLACEHOLDER = "OPENEDX_ESSAY_PLACEHOLDER"
_MISSING_PACKAGE_FILE = "MOODLE_PACKAGE_FILE_MISSING"


def build_moodle_openedx_report(
    course: Course,
    job_id: str,
    validation_notes: list[MappingNote],
    *,
    extracted_path: str,
) -> dict[str, object]:
    """Build a report from the existing inspection without persisting a job."""
    findings = [
        {
            "finding_id": stable_id(
                "preflight", _ESSAY_PLACEHOLDER, question.question_id
            ),
            "code": _ESSAY_PLACEHOLDER,
            "severity": Severity.WARNING.value,
            "question_id": question.question_id,
            "status": "placeholder",
            "recommendation": (
                "Recreate the essay question in Open edX and verify its grading."
            ),
        }
        for question in course.questions
        if question.question_type == "essay"
    ]
    findings.extend(_missing_package_file_findings(course, extracted_path))
    return {
        "schema_version": 1,
        "job_id": job_id,
        "source": "moodle",
        "target": "openedx",
        "validation_error_codes": [
            note.code
            for note in validation_notes
            if note.severity == Severity.ERROR
        ],
        "findings": findings,
    }


def _missing_package_file_findings(
    course: Course, extracted_path: str
) -> list[dict[str, str]]:
    findings = []
    assets_by_id = {asset.asset_id: asset for asset in course.assets}
    for asset in assets_by_id.values():
        try:
            package_file = resolve_under(extracted_path, asset.path)
        except UnsafePathError:
            # Like the exporter, inspect only paths inside the package.
            continue
        if package_file.is_file():
            continue
        findings.append({
            "finding_id": stable_id("preflight", _MISSING_PACKAGE_FILE, asset.asset_id),
            "code": _MISSING_PACKAGE_FILE,
            "severity": Severity.WARNING.value,
            "asset_id": asset.asset_id,
            "status": "missing",
            "recommendation": "Check the file in Moodle and create a new backup that includes it.",
        })
    return findings
