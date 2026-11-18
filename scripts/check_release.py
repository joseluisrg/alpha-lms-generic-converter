"""Validate release metadata and extract changelog notes."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

_HEADING = re.compile(r"^##\s+\[?([0-9][^\]\s]*)\]?(?:\s+-\s+(\d{4}-\d{2}-\d{2}))?\s*$")


def project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def changelog_section(changelog: Path, version: str) -> str | None:
    lines = changelog.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(1) == version:
            start = index + 1
            break
    if start is None:
        return None

    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip()


def has_unreleased(changelog: Path) -> bool:
    return any(
        line.strip().lower() == "## unreleased"
        for line in changelog.read_text(encoding="utf-8").splitlines()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Release tag, for example v0.1.0")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Directory containing pyproject.toml and CHANGELOG.md",
    )
    parser.add_argument("--notes-out", type=Path, help="Write release notes to this file")
    args = parser.parse_args(argv)

    root: Path = args.project_root
    version = project_version(root)
    changelog = root / "CHANGELOG.md"

    if args.tag:
        tag_version = args.tag.removeprefix("v")
        if tag_version != version:
            print(
                f"error: tag {args.tag!r} does not match project version {version!r}",
                file=sys.stderr,
            )
            return 1

    if not has_unreleased(changelog):
        print("error: CHANGELOG.md must contain an '## Unreleased' section", file=sys.stderr)
        return 1

    section = changelog_section(changelog, version)
    if section is None:
        print(f"error: CHANGELOG.md has no section for version {version!r}", file=sys.stderr)
        return 1
    if not section:
        print(f"error: CHANGELOG.md section for {version!r} is empty", file=sys.stderr)
        return 1

    if args.notes_out:
        args.notes_out.write_text(section + "\n", encoding="utf-8")

    print(f"release metadata OK: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
