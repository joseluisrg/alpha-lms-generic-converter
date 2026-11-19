"""Validate the CycloneDX SBOM produced for release artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_BOM_FORMAT = "CycloneDX"
EXPECTED_SPEC_VERSION = "1.6"
EXPECTED_ROOT_COMPONENT = "lms-converter"


def validate_sbom(payload: object) -> int:
    """Return the component count after validating the core SBOM fields."""
    if not isinstance(payload, dict):
        raise ValueError("SBOM root must be a JSON object")

    if payload.get("bomFormat") != EXPECTED_BOM_FORMAT:
        raise ValueError(f"Expected bomFormat={EXPECTED_BOM_FORMAT!r}")

    if payload.get("specVersion") != EXPECTED_SPEC_VERSION:
        raise ValueError(f"Expected specVersion={EXPECTED_SPEC_VERSION!r}")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Missing metadata object")

    component = metadata.get("component")
    if not isinstance(component, dict) or component.get("name") != EXPECTED_ROOT_COMPONENT:
        raise ValueError(f"Missing root component {EXPECTED_ROOT_COMPONENT!r}")

    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("Missing non-empty components list")

    return len(components)


def load_sbom(path: Path) -> int:
    """Load an SBOM file and return its validated component count."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    return validate_sbom(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to the CycloneDX SBOM JSON file")
    args = parser.parse_args()

    try:
        count = load_sbom(args.path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Invalid SBOM: {exc}") from exc

    print(f"Validated SBOM: {args.path} ({count} components)")


if __name__ == "__main__":
    main()
