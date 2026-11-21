"""Format-matrix loading and validation constants."""

from __future__ import annotations

import json
from typing import Any

from tests.golden.corpus import GOLDEN_ROOT

MATRIX_PATH = GOLDEN_ROOT / "format-matrix.json"
MATRIX_SCHEMA_VERSION = 1
MATRIX_VERSION = 1
FEATURE_STATUSES = frozenset({"native", "transformed", "placeholder", "unsupported", "control"})
FEATURE_CATEGORIES = frozenset({"migration", "target", "validation", "security", "roundtrip"})
FEATURE_SOURCES = frozenset({"openedx", "moodle", "control"})
FEATURE_TARGETS = frozenset({"openedx", "moodle"})
IMPORT_CHECKS = frozenset({"moodle:restore", "openedx:import", "roundtrip"})


def load_matrix() -> dict[str, Any]:
    """Load and validate the format-matrix envelope."""
    try:
        data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid format matrix: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Format matrix must be a JSON object")
    if data.get("schema_version") != MATRIX_SCHEMA_VERSION:
        raise ValueError(f"Unsupported format-matrix schema: {data.get('schema_version')!r}")
    if data.get("matrix_version") != MATRIX_VERSION:
        raise ValueError(f"Unsupported format-matrix version: {data.get('matrix_version')!r}")
    return data
