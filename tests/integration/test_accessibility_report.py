from pathlib import Path

from core.parse import ParseService
from core.transform import TransformService
from core.validate import ValidationService


def test_alt_text_findings_appear_in_validation_report(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")

    notes = ValidationService().validate(course, target="moodle")

    codes = [note.code for note in notes]
    assert codes.count("ALT_ATTRIBUTE_MISSING") == 2
    summary = next(note for note in notes if note.code == "MIGRATION_SUMMARY")
    assert "Warnings: 2" in summary.message