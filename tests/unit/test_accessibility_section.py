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
    assert section["summary"]["by_severity"] == {"info": 0, "warning": 3, "error": 0}
    codes = sorted(f["code"] for f in section["findings"])
    assert codes == ["ALT_ATTRIBUTE_MISSING", "ALT_ATTRIBUTE_MISSING", "VIDEO_CAPTIONS_MISSING"]
    assert all(f["source_object"]["kind"] == "content_node" for f in section["findings"])


def test_html_report_shows_accessibility_section(a11y_openedx_archive: Path, tmp_path: Path):
    course = _course(a11y_openedx_archive, "openedx", tmp_path)

    page = render_html_report("job-a11y", {"status": "completed"}, course, [])

    assert "Accessibility &amp; Content Quality" in page
    assert "3 warnings" in page
    assert "cpu.png" in page


def _fake_status(url):
    return {"https://example.org/working": 200, "https://example.org/broken": 404}.get(url)


def test_report_includes_links_only_when_switched_on(a11y_openedx_archive: Path, tmp_path: Path):
    course = _course(a11y_openedx_archive, "openedx", tmp_path)

    data = build_report_data(
        "job-a11y", {"status": "completed"}, course, [],
        check_links=True, fetch_status=_fake_status,
    )

    codes = [f["code"] for f in data["accessibility"]["findings"]]
    assert "EXTERNAL_LINK_UNREACHABLE" in codes
    assert data["accessibility"]["summary"]["by_severity"]["warning"] == 4


def test_html_report_shows_broken_link_when_switched_on(a11y_openedx_archive: Path, tmp_path: Path):
    course = _course(a11y_openedx_archive, "openedx", tmp_path)

    page = render_html_report(
        "job-a11y", {"status": "completed"}, course, [],
        check_links=True, fetch_status=_fake_status,
    )

    assert "https://example.org/broken" in page
    assert "4 warnings" in page