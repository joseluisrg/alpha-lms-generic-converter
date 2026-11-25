from pathlib import Path

from core.parse import ParseService
from core.quality import check_alt_text
from core.transform import TransformService


def _all_nodes(nodes):
    for node in nodes:
        yield node
        yield from _all_nodes(node.children)


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