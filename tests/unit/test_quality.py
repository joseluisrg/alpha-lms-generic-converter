from pathlib import Path

from core.parse import ParseService
from core.quality import check_alt_text, check_external_links, check_video_captions, run_quality_checks
from core.transform import TransformService


def _all_nodes(nodes):
    for node in nodes:
        yield node
        yield from _all_nodes(node.children)


def _fake_status(url):
    """Pretend to ask the internet: fixed answers instead of real requests."""
    return {"https://example.org/working": 200, "https://example.org/broken": 404}.get(url)


def test_each_alt_text_finding_points_to_its_page(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")
    page = next(n for n in _all_nodes(course.content_nodes) if n.title == "Intro HTML")

    findings = check_alt_text(course)

    assert len(findings) == 2
    for finding in findings:
        assert finding.code == "ALT_ATTRIBUTE_MISSING"
        assert finding.severity == "warning"
        assert finding.source_object == {"kind": "content_node", "id": page.node_id}
        assert finding.recommendation


def test_each_alt_text_finding_points_to_its_page_in_moodle(a11y_moodle_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_moodle_archive), "moodle", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "moodle", "job-a11y-moodle")
    page = next(n for n in _all_nodes(course.content_nodes) if n.title == "Images Page" and n.node_type.value == "html")
    findings = check_alt_text(course)

    assert len(findings) == 2
    for finding in findings:
        assert finding.code == "ALT_ATTRIBUTE_MISSING"
        assert finding.severity == "warning"
        assert finding.source_object == {"kind": "content_node", "id": page.node_id}
        assert finding.recommendation


def test_video_without_captions_is_reported(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")
    video = next(n for n in _all_nodes(course.content_nodes) if n.title == "Lecture Video" and n.node_type.value == "video")

    findings = check_video_captions(course)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "VIDEO_CAPTIONS_MISSING"
    assert finding.severity == "warning"
    assert finding.source_object == {"kind": "content_node", "id": video.node_id}
    assert "Lecture Video" in finding.message
    assert finding.recommendation


def test_video_without_captions_is_reported_in_moodle(a11y_moodle_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_moodle_archive), "moodle", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "moodle", "job-a11y-moodle")
    page = next(n for n in _all_nodes(course.content_nodes) if n.title == "Images Page" and n.node_type.value == "html")

    findings = check_video_captions(course)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "VIDEO_CAPTIONS_MISSING"
    assert finding.source_object == {"kind": "content_node", "id": page.node_id}
    assert "lecture.mp4" in finding.message
    assert "intro.mp4" not in finding.message


def test_broken_external_link_is_reported(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")
    page = next(n for n in _all_nodes(course.content_nodes) if n.title == "Intro HTML" and n.node_type.value == "html")

    findings = check_external_links(course, fetch_status=_fake_status)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "EXTERNAL_LINK_UNREACHABLE"
    assert finding.severity == "warning"
    assert finding.source_object == {"kind": "content_node", "id": page.node_id}
    assert "https://example.org/broken" in finding.message
    assert finding.recommendation


def test_broken_external_link_is_reported_in_moodle(a11y_moodle_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_moodle_archive), "moodle", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "moodle", "job-a11y-moodle")
    page = next(n for n in _all_nodes(course.content_nodes) if n.title == "Images Page" and n.node_type.value == "html")

    findings = check_external_links(course, fetch_status=_fake_status)

    assert len(findings) == 1
    assert findings[0].code == "EXTERNAL_LINK_UNREACHABLE"
    assert findings[0].source_object == {"kind": "content_node", "id": page.node_id}
    assert "https://example.org/broken" in findings[0].message


def test_external_links_are_only_checked_on_request(a11y_openedx_archive: Path, tmp_path: Path):
    parsed = ParseService().parse(str(a11y_openedx_archive), "openedx", str(tmp_path / "extract"))
    course = TransformService().transform(parsed, "openedx", "job-a11y")

    default_codes = [f.code for f in run_quality_checks(course)]
    on_request_codes = [f.code for f in run_quality_checks(course, check_links=True, fetch_status=_fake_status)]

    assert "EXTERNAL_LINK_UNREACHABLE" not in default_codes
    assert "EXTERNAL_LINK_UNREACHABLE" in on_request_codes