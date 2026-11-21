"""Credential redaction for certification commands and reports."""

from __future__ import annotations

import re

_SECRET_PATTERN = re.compile(
    r"(?i)\b([\w-]*(?:password|passwd|pass|pwd|token|secret|api[_-]?key))\b"
    r"(\s*[=:]\s*)([^\s,;]+)"
)
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")


def redact(value: str) -> str:
    """Remove common credential forms from report text."""
    redacted = _SECRET_PATTERN.sub(r"\1\2<redacted>", value)
    return _URL_CREDENTIALS.sub(r"\g<scheme><redacted>@", redacted)
