from pathlib import Path

from core.accessibility import check_images
from core.parse import ParseService
from core.transform import TransformService


def test_images_without_good_alt_text_are_reported(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")

    notes = check_images(course)

    assert len(notes) == 2
    assert all(note.code == "ALT_ATTRIBUTE_MISSING" for note in notes)
    messages = " ".join(note.message for note in notes)
    assert "cpu.png" in messages
    assert "chart.png" in messages
    assert "diagram.png" not in messages


def test_images_without_good_alt_text_are_reported_in_moodle(a11y_moodle_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_moodle_archive), "moodle", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "moodle", "job-a11y-moodle")

    notes = check_images(course)

    assert len(notes) == 2
    assert all(note.code == "ALT_ATTRIBUTE_MISSING" for note in notes)
    messages = " ".join(note.message for note in notes)
    assert "cpu.png" in messages
    assert "chart.png" in messages
    assert "diagram.png" not in messages