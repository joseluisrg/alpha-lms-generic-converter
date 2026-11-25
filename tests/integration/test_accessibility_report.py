from pathlib import Path

from core.parse import ParseService
from core.report import build_report_data
from core.transform import TransformService
from core.validate import ValidationService


def test_alt_text_findings_appear_only_in_accessibility_section(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")

    notes = ValidationService().validate(course, target="moodle")
    data = build_report_data("job-a11y", {"status": "completed"}, course, notes)

    validation_codes = [note["code"] for note in data["validation"]]
    assert "ALT_ATTRIBUTE_MISSING" not in validation_codes
    assert len(data["accessibility"]["findings"]) == 2