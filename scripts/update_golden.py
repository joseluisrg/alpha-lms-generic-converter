#!/usr/bin/env python3
"""Update or check golden-corpus snapshots and source digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.golden.corpus import (  # noqa: E402
    MANIFEST_PATH,
    binary_path,
    build_case_snapshots,
    declared_snapshot_paths,
    invalid_cases,
    load_manifest,
    manifest_with_updated_digests,
    valid_cases,
    write_manifest,
)
from tests.golden.snapshots import load_json, write_json  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Write snapshots and manifest changes.")
    mode.add_argument("--check", action="store_true", help="Check without writing (default).")
    parser.add_argument("--case", action="append", dest="case_ids", help="Limit to one case id.")
    parser.add_argument(
        "--allow-binary-change",
        action="store_true",
        help="Allow updating hashes for committed binary fixtures.",
    )
    return parser.parse_args()


def _binary_changes(manifest: dict[str, Any], case_ids: set[str] | None) -> list[str]:
    problems: list[str] = []
    entries: list[tuple[str, Path, str | None, int | None]] = [
        (case["id"], binary_path(case), case.get("sha256"), case.get("size"))
        for case in invalid_cases(manifest)
        if "binary" in case
    ]
    entries.extend(
        (
            contract["id"],
            MANIFEST_PATH.parent / contract["path"],
            contract.get("sha256"),
            contract.get("size"),
        )
        for contract in manifest.get("binary_contracts", [])
    )

    for case_id, path, expected_hash, expected_size in entries:
        if case_ids is not None and case_id not in case_ids:
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        actual_size = path.stat().st_size
        if actual_hash != expected_hash or actual_size != expected_size:
            problems.append(
                f"{case_id}: binary changed "
                f"(expected {expected_hash}/{expected_size}, "
                f"found {actual_hash}/{actual_size})"
            )
    return problems


def _orphan_snapshots(manifest: dict[str, Any]) -> list[Path]:
    declared = declared_snapshot_paths(manifest)
    actual = {
        path for path in MANIFEST_PATH.parent.rglob("*.json") if path.parent.name == "expected"
    }
    return sorted(actual - declared)


def main() -> int:
    args = _parse_args()
    write = args.write
    case_ids = set(args.case_ids) if args.case_ids else None
    try:
        manifest = load_manifest()
    except ValueError as exc:
        print(f"Invalid golden manifest: {exc}", file=sys.stderr)
        return 2

    if case_ids is not None:
        known = {case["id"] for case in manifest["cases"]}
        missing = case_ids - known
        if missing:
            print(f"Unknown case id(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    binary_problems = _binary_changes(manifest, case_ids)
    if binary_problems and not args.allow_binary_change:
        for problem in binary_problems:
            print(problem, file=sys.stderr)
        print("Refusing binary changes without --allow-binary-change.", file=sys.stderr)
        return 2

    changed: list[Path] = []
    orphans = _orphan_snapshots(manifest) if case_ids is None else []
    changed.extend(orphans)
    if write:
        for path in orphans:
            path.unlink()

    selected_valid = [
        case for case in valid_cases(manifest) if case_ids is None or case["id"] in case_ids
    ]
    for case in selected_valid:
        with tempfile.TemporaryDirectory() as temporary:
            snapshots, _ = build_case_snapshots(case, Path(temporary))
        for path, snapshot in snapshots.items():
            if path.is_file() and load_json(path) == snapshot:
                continue
            changed.append(path)
            if write:
                write_json(path, snapshot)

    updated_manifest = manifest_with_updated_digests(
        manifest,
        allow_binary_change=args.allow_binary_change,
        case_ids=case_ids,
    )
    updated_text = json.dumps(updated_manifest, indent=2, ensure_ascii=False) + "\n"
    current_text = MANIFEST_PATH.read_text(encoding="utf-8")
    if updated_text != current_text:
        changed.append(MANIFEST_PATH)
        if write:
            write_manifest(updated_manifest)

    if changed:
        action = "Updated" if write else "Out of date"
        for path in changed:
            print(f"{action}: {path.relative_to(REPO_ROOT)}")
        if not write:
            return 1
    else:
        print("Golden corpus is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
