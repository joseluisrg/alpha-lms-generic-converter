"""Accessibility and content quality checks with their own finding format.

Every finding points to the affected course component (source_object), so
course teams, Preflight and the Ledger can refer to the same item.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import ssl
from html.parser import HTMLParser
from typing import Callable, Dict, Iterable, List, Optional
from xml.etree.ElementTree import ParseError

from pydantic import BaseModel

from core.errors import XmlSecurityError
from core.xml_utils import parse_xml_text
from domain.entities import ContentNode, Course
from domain.enums import NodeType, Severity

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".jfif")
CAPTION_KINDS = ("captions", "subtitles")


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


class _VideoCollector(HTMLParser):
    """Collect all <video> tags of an HTML text and whether they have captions."""

    def __init__(self) -> None:
        super().__init__()
        self.videos: List[dict] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "video":
            self.videos.append({"src": attrs.get("src", "unknown"), "has_captions": False})
        elif tag == "track" and self.videos:
            if (attrs.get("kind") or "").lower() in CAPTION_KINDS:
                self.videos[-1]["has_captions"] = True


def _openedx_video_has_captions(raw_xml: str) -> bool | None:
    """True/False for an Open edX <video> component, None if not verifiable."""
    try:
        root = parse_xml_text(raw_xml)
    except (ParseError, XmlSecurityError):
        return None
    if root.tag != "video":
        return None
    if root.attrib.get("sub") or root.attrib.get("transcripts"):
        return True
    return root.find("transcript") is not None


def check_video_captions(course: Course) -> List[Finding]:
    """Report videos without captions or a transcript, where this can be verified."""
    findings: List[Finding] = []
    fragments = {f.fragment_id: f.raw_text or "" for f in course.raw_fragments}
    for node in _iterate_nodes(course.content_nodes):
        if node.node_type == NodeType.VIDEO:
            for fragment_id in node.raw_fragment_ids:
                if _openedx_video_has_captions(fragments.get(fragment_id, "")) is False:
                    findings.append(Finding(
                        code="VIDEO_CAPTIONS_MISSING",
                        severity=Severity.WARNING,
                        message=f'Video "{node.title}" has no captions or transcript',
                        source_object={"kind": "content_node", "id": node.node_id},
                        recommendation="Add captions or a transcript for the video.",
                    ))
        elif node.node_type == NodeType.HTML:
            collector = _VideoCollector()
            collector.feed(node.metadata.get("content_html", ""))
            for video in collector.videos:
                if not video["has_captions"]:
                    findings.append(Finding(
                        code="VIDEO_CAPTIONS_MISSING",
                        severity=Severity.WARNING,
                        message=f'Video "{video["src"]}" has no captions or transcript (page: {node.title})',
                        source_object={"kind": "content_node", "id": node.node_id},
                        recommendation="Add captions or a transcript for the video.",
                    ))
    return findings


class _LinkCollector(HTMLParser):
    """Collect all external links (http/https) of an HTML text."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = (dict(attrs).get("href") or "").strip()
            if href.lower().startswith(("http://", "https://")) and href not in self.links:
                self.links.append(href)


def _ssl_context() -> ssl.SSLContext:
    """Trusted certificates for https: certifi's list if installed, else the system default."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _http_status(url: str, timeout: float = 5.0) -> Optional[int]:
    """Ask the internet for a URL; return the HTTP status, or None if there is no answer."""
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": "lms-converter-accessibility-check"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                return response.status
        except urllib.error.HTTPError as error:
            if error.code == 405 and method == "HEAD":
                continue
            return error.code
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None
    return None


def check_external_links(
    course: Course, fetch_status: Callable[[str], Optional[int]] = _http_status
) -> List[Finding]:
    """Report external links that answer with an error or not at all (goes online: on request only)."""
    findings: List[Finding] = []
    for node in _iterate_nodes(course.content_nodes):
        collector = _LinkCollector()
        collector.feed(node.metadata.get("content_html", "") or "")
        for url in collector.links:
            status = fetch_status(url)
            if status is None or status >= 400:
                answer = f"HTTP {status}" if status else "no answer"
                findings.append(Finding(
                    code="EXTERNAL_LINK_UNREACHABLE",
                    severity=Severity.WARNING,
                    message=f'Link "{url}" is not reachable ({answer}) (page: {node.title})',
                    source_object={"kind": "content_node", "id": node.node_id},
                    recommendation="Fix the link or remove it if the page no longer exists.",
                ))
    return findings


def run_quality_checks(
    course: Course,
    check_links: bool = False,
    fetch_status: Optional[Callable[[str], Optional[int]]] = None,
) -> List[Finding]:
    """Run all accessibility and content quality checks; external links only on request."""
    findings = check_alt_text(course) + check_video_captions(course)
    if check_links:
        findings += check_external_links(course, fetch_status or _http_status)
    return findings


def summarize(findings: List[Finding]) -> Dict[str, Dict[str, int]]:
    """Count findings per severity, e.g. {"info": 0, "warning": 2, "error": 0}."""
    by_severity = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        by_severity[finding.severity.value] += 1
    return {"by_severity": by_severity}