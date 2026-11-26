"""Job report rendering shared by the CLI and the Streamlit interface.

All untrusted values are HTML-escaped.  Keeping this logic in one module avoids
the previous duplication between the CLI and the Streamlit app, where a fix in
one renderer could silently leave the other vulnerable.
"""

from __future__ import annotations

import html
import json
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.quality import run_quality_checks, summarize
from domain.entities import ContentNode, Course


def count_node_type(nodes: Iterable[ContentNode], target_type: str) -> int:
    """Recursively count nodes of a given type."""
    count = 0
    for node in nodes:
        if node.node_type.value == target_type:
            count += 1
        count += count_node_type(node.children, target_type)
    return count


def _report_items(report_items: Iterable[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in report_items:
        if hasattr(item, "model_dump"):
            items.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            items.append(item)
        else:
            items.append({"message": str(item)})
    return items


def _unsupported_features(report_items: List[Dict[str, Any]]) -> List[str]:
    unsupported: set[str] = set()
    for note in report_items:
        code = note.get("code")
        if code == "UNSUPPORTED_NODES":
            unsupported.add(str(note.get("message", "")))
        elif code == "UNSUPPORTED_QUESTION_TYPE":
            unsupported.add("question_type")
        elif code == "TARGET_UNSUPPORTED_NODES":
            unsupported.add("target_node_mapping")
    return sorted(unsupported)


def build_report_data(
    job_id: str,
    job: Dict[str, Any],
    course: Course,
    report_items: Iterable[Any],
    ledger_entries: Optional[List[Dict[str, Any]]] = None,
    check_links: bool = False,
    fetch_status: Optional[Callable[[str], Optional[int]]] = None,
) -> Dict[str, Any]:
    """Return a stable, JSON-serializable report document.

    *ledger_entries* is optional.  When supplied each entry is projected to the
    five display fields and ``output_hash`` is truncated to 16 chars.
    Existing callers that omit *ledger_entries* receive an empty ``"ledger"``
    list and are not affected.
    """
    items = _report_items(report_items)
    ledger_display: List[Dict[str, Any]] = [
        {
            "event_id": entry["event_id"],
            "event": entry["event"],
            "step": entry["step"],
            "recorded_at": entry["recorded_at"],
            "output_hash": entry.get("output_hash", "")[:16],
        }
        for entry in (ledger_entries or [])
    ]
    quality_findings = run_quality_checks(course, check_links=check_links, fetch_status=fetch_status)
    return {
        "schema_version": 2,
        "job_id": job_id,
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "source_type": job.get("source_type"),
        "target_type": job.get("target_type") or None,
        "output_path": job.get("output_path"),
        "error": job.get("error"),
        "course_id": course.course_id,
        "course_title": course.title,
        "content_nodes": count_node_type(course.content_nodes, "chapter"),
        "total_nodes": _count_all_nodes(course.content_nodes),
        "assessments": len(course.assessments),
        "questions": len(course.questions),
        "answer_options": len(course.answer_options),
        "assets": [{"id": a.asset_id, "path": a.path, "checksum": a.checksum}
                   for a in course.assets],
        "components": {
            "chapters": count_node_type(course.content_nodes, "chapter"),
            "sequentials": count_node_type(course.content_nodes, "sequential"),
            "verticals": count_node_type(course.content_nodes, "vertical"),
            "html": count_node_type(course.content_nodes, "html"),
            "problems": count_node_type(course.content_nodes, "problem"),
            "videos": count_node_type(course.content_nodes, "video"),
        },
        "unsupported_features": _unsupported_features(items),
        "validation": items,
        "integrity_errors": course.integrity_errors(),
        "ledger": ledger_display,
        "accessibility": {
            "summary": summarize(quality_findings),
            "findings": [f.model_dump(mode="json") for f in quality_findings],
        },
    }


def render_json_report(
    job_id: str,
    job: Dict[str, Any],
    course: Course,
    report_items: Iterable[Any],
    ledger_entries: Optional[List[Dict[str, Any]]] = None,
    check_links: bool = False,
    fetch_status: Optional[Callable[[str], Optional[int]]] = None,
) -> str:
    """Render the report as deterministic, human-readable JSON."""
    return json.dumps(
        build_report_data(job_id, job, course, report_items, ledger_entries, check_links, fetch_status),
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def render_html_report(
    job_id: str,
    job: Dict[str, Any],
    course: Course,
    report_items: Iterable[Any],
    ledger_entries: Optional[List[Dict[str, Any]]] = None,
    check_links: bool = False,
    fetch_status: Optional[Callable[[str], Optional[int]]] = None,
) -> str:
    """Render a self-contained HTML report with all untrusted text escaped."""
    data = build_report_data(job_id, job, course, report_items, ledger_entries, check_links, fetch_status)
    e = lambda value: html.escape(str(value if value is not None else ""), quote=True)
    components = data["components"]

    rows = [
        ("Job ID", data["job_id"]),
        ("Status", data["status"]),
        ("Created", data["created_at"]),
        ("Updated", data["updated_at"]),
        ("Source LMS", data["source_type"]),
        ("Target LMS", data["target_type"] or "N/A"),
        ("Course ID", data["course_id"]),
        ("Course Title", data["course_title"]),
        ("Content Nodes", data["total_nodes"]),
        ("Chapters", components["chapters"]),
        ("Sequentials", components["sequentials"]),
        ("Verticals", components["verticals"]),
        ("HTML Components", components["html"]),
        ("Problem Components", components["problems"]),
        ("Video Components", components["videos"]),
        ("Assessments", data["assessments"]),
        ("Questions", data["questions"]),
        ("Answer Options", data["answer_options"]),
        ("Assets", len(data["assets"])),
        ("Output", data["output_path"] or "N/A"),
        ("Error", data["error"] or "None"),
    ]
    summary_rows = "\n".join(
        f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>" for label, value in rows
    )

    asset_rows = "\n".join(
        f"<tr><td>{e(asset['id'])}</td><td>{e(asset['path'])}</td>"
        f"<td>{e(asset.get('checksum') or '')}</td></tr>"
        for asset in data["assets"][:200]
    )
    if len(data["assets"]) > 200:
        asset_rows += (
            f"<tr><td colspan=\"3\">... and {len(data['assets']) - 200} more</td></tr>"
        )

    unsupported_rows = "\n".join(
        f"<li>{e(item)}</li>" for item in data["unsupported_features"]
    ) or "<li>None detected</li>"

    note_rows = []
    for note in data["validation"]:
        severity = str(note.get("severity", "info")).lower()
        css_class = {"warning": "warning", "error": "error", "info": "info"}.get(
            severity, ""
        )
        note_rows.append(
            f"<tr class=\"{css_class}\"><td>{e(severity)}</td>"
            f"<td>{e(note.get('code', ''))}</td>"
            f"<td>{e(note.get('message', ''))}</td></tr>"
        )
    if not note_rows:
        note_rows.append('<tr><td colspan="3">No validation notes.</td></tr>')

    integrity_rows = "\n".join(
        f"<li>{e(message)}</li>" for message in data["integrity_errors"]
    ) or "<li>No integrity errors.</li>"

    # Build the Ledger History table rows — each value is HTML-escaped
    ledger_rows = "\n".join(
        f"<tr>"
        f"<td><code>{e(entry['event_id'])}</code></td>"
        f"<td>{e(entry['event'])}</td>"
        f"<td>{e(entry['step'])}</td>"
        f"<td>{e(entry['recorded_at'])}</td>"
        f"<td><code>{e(entry['output_hash'])}</code></td>"
        f"</tr>"
        for entry in data["ledger"]
    ) or '<tr><td colspan="5">No ledger entries.</td></tr>'

  # Build the Accessibility & Content Quality section — each value is HTML-escaped
    a11y = data["accessibility"]
    counts = a11y["summary"]["by_severity"]
    a11y_summary = f"{counts['warning']} warnings, {counts['error']} errors, {counts['info']} info"
    a11y_rows = "\n".join(
        f"<tr class=\"{e(finding['severity'])}\"><td>{e(finding['severity'])}</td>"
        f"<td>{e(finding['code'])}</td>"
        f"<td>{e(finding['message'])}</td>"
        f"<td><code>{e(finding['source_object']['kind'])}: {e(finding['source_object']['id'])}</code></td>"
        f"<td>{e(finding['recommendation'])}</td></tr>"
        for finding in a11y["findings"]
    ) or '<tr><td colspan="5">No accessibility findings.</td></tr>'


    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>LMS Converter Report - {e(job_id)}</title>
    <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 2rem; color: #1f2937; }}
        h1, h2 {{ color: #111827; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
        th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; vertical-align: top; }}
        th {{ background-color: #f3f4f6; }}
        .warning {{ background-color: #fff7ed; }}
        .error {{ background-color: #fef2f2; }}
        .info {{ background-color: #eff6ff; }}
        .summary th {{ width: 22%; }}
        code {{ white-space: pre-wrap; }}
    </style>
</head>
<body>
    <h1>LMS Converter Report</h1>
    <p>Generated from a validated canonical course snapshot.</p>
    <h2>Summary</h2>
    <table class="summary">
{summary_rows}
    </table>
    <h2>Assets</h2>
    <table>
        <tr><th>Asset ID</th><th>Path</th><th>Checksum</th></tr>
{asset_rows or '<tr><td colspan="3">No assets.</td></tr>'}
    </table>
    <h2>Unsupported Features</h2>
    <ul>
{unsupported_rows}
    </ul>
    <h2>Validation Warnings &amp; Errors</h2>
    <table>
        <tr><th>Severity</th><th>Code</th><th>Message</th></tr>
{chr(10).join(note_rows)}
    </table>
     <h2>Accessibility &amp; Content Quality</h2>
    <p>{e(a11y_summary)}</p>
    <table>
        <tr><th>Severity</th><th>Code</th><th>Message</th><th>Location (ID)</th><th>Recommendation</th></tr>
{a11y_rows}
    </table>
    <h2>Integrity Checks</h2>
    <ul>
{integrity_rows}
    </ul>
    <h2>Ledger History</h2>
    <table>
        <tr>
            <th>Event ID</th>
            <th>Event</th>
            <th>Step</th>
            <th>Recorded</th>
            <th>Output Hash (16)</th>
        </tr>
{ledger_rows}
    </table>
</body>
</html>"""


def _count_all_nodes(nodes: Iterable[ContentNode]) -> int:
    return sum(1 + _count_all_nodes(node.children) for node in nodes)
