"""Accessibility and content quality checks on the canonical course."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Iterable, List

from core.identity import stable_id
from domain.entities import ContentNode, Course, MappingNote
from domain.enums import NodeType, Severity

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".jfif")

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


def check_images(course: Course) -> List[MappingNote]:
    """Report images without a meaningful alt text."""
    notes: List[MappingNote] = []
    for node in _iterate_nodes(course.content_nodes):
        if node.node_type != NodeType.HTML:
            continue
        collector = _ImageCollector()
        collector.feed(node.metadata.get("content_html", ""))
        for image in collector.images:
            problem = _alt_problem(image)
            if problem:
                src = image.get("src", "unknown")
                notes.append(MappingNote(
                    note_id=stable_id("note", course.course_id, "ALT_ATTRIBUTE_MISSING", node.node_id, src),
                    severity=Severity.WARNING,
                    code="ALT_ATTRIBUTE_MISSING",
                    message=f'Image "{src}" {problem} (page: {node.title})',
                ))
    return notes