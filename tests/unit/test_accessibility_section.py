from pathlib import Path

from core.parse import ParseService
from core.report import build_report_data, render_html_report
from core.transform import TransformService


def _course(archive, source, tmp_path):
    parsed = ParseService().parse(str(archive), source, str(tmp_path / "extract"))
    return TransformService().transform(parsed, source, "job-a11y")


def test_report_has_own_accessibility_section(a11y_openedx_archive: Path, tmp_path: Path):
    course = _course(a11y_openedx_archive, "openedx", tmp_path)

    data = build_report_data("job-a11y", {"status": "completed"}, course, [])

    section = data["accessibility"]
    assert section["summary"]["by_severity"] == {"info": 0, "warning": 2, "error": 0}
    assert len(section["findings"]) == 2
    assert all(f["code"] == "ALT_ATTRIBUTE_MISSING" for f in section["findings"])
    assert all(f["source_object"]["kind"] == "content_node" for f in section["findings"])


def test_html_report_shows_accessibility_section(a11y_openedx_archive: Path, tmp_path: Path):
    course = _course(a11y_openedx_archive, "openedx", tmp_path)

    page = render_html_report("job-a11y", {"status": "completed"}, course, [])

    assert "Accessibility &amp; Content Quality" in page
    assert "2 warnings" in page
    assert "cpu.png" in page