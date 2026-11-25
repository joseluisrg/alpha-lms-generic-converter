"""Accessibility and content quality checks with their own finding format.

Every finding points to the affected course component (source_object), so
course teams, Preflight and the Ledger can refer to the same item.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel

from core.accessibility import _alt_problem, _ImageCollector, _iterate_nodes
from domain.entities import Course
from domain.enums import NodeType, Severity


class Finding(BaseModel):
    """One accessibility or content quality finding."""

    code: str
    severity: Severity
    message: str
    source_object: Dict[str, str]
    recommendation: str


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