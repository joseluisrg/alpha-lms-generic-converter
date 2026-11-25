"""Accessibility and content quality checks with their own finding format.

Every finding points to the affected course component (source_object), so
course teams, Preflight and the Ledger can refer to the same item.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, Iterable, List

from pydantic import BaseModel

from domain.entities import ContentNode, Course
from domain.enums import NodeType, Severity

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".jfif")


class Finding(BaseModel):
    """One accessibility or content quality finding."""

    code: str
    severity: Severity
    message: str
    source_object: Dict[str, str]
    recommendation: str


class _ImageCollector(HTMLParser):
    """Collect all <img> tags of an HTML text with their attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.images: List[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))


def _iterate_nodes(nodes: Iterable[ContentNode]):
    for node in nodes:
        yield node
        yield from _iterate_nodes(node.children)


def _alt_problem(image: dict) -> str | None:
    if "alt" not in image:
        return "has no alt text"
    alt = (image["alt"] or "").strip()
    if alt.lower().endswith(IMAGE_EXTENSIONS):
        return "has only a file name as alt text"
    return None


def check_alt_text(course: Course) -> List[Finding]:
    """Report images without a meaningful alt text, with the page they are on."""
    findings: List[Finding] = []
    for node in _iterate_nodes(course.content_nodes):
        if node.node_type != NodeType.HTML:
            continue
        collector = _ImageCollector()
        collector.feed(node.metadata.get("content_html", ""))
        for image in collector.images:
            problem = _alt_problem(image)
            if problem:
                src = image.get("src", "unknown")
                findings.append(Finding(
                    code="ALT_ATTRIBUTE_MISSING",
                    severity=Severity.WARNING,
                    message=f'Image "{src}" {problem} (page: {node.title})',
                    source_object={"kind": "content_node", "id": node.node_id},
                    recommendation="Add a short description of what the image shows.",
                ))
    return findings


def run_quality_checks(course: Course) -> List[Finding]:
    """Run all accessibility and content quality checks."""
    return check_alt_text(course)


def summarize(findings: List[Finding]) -> Dict[str, Dict[str, int]]:
    """Count findings per severity, e.g. {"info": 0, "warning": 2, "error": 0}."""
    by_severity = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        by_severity[finding.severity.value] += 1
    return {"by_severity": by_severity}