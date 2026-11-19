from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tests.golden.corpus import (
    GOLDEN_ROOT,
    binary_path,
    deterministic_tar_gz,
    load_manifest,
    source_dir,
    tree_digest,
    valid_cases,
)

MANIFEST = load_manifest()
BINARY_BUDGET = 64 * 1024
TOTAL_BINARY_BUDGET = 256 * 1024
TEXT_SUFFIXES = frozenset(
    {
        ".csv",
        ".html",
        ".json",
        ".log",
        ".md",
        ".py",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])")
EMAIL_ALLOWLIST = ("asset+block@",)
PRIVATE_PATH_PATTERNS = (
    re.compile(r"/home/[A-Za-z0-9._-]+"),
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
)
SECRET_PATTERNS = (
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}"),
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
)


def _text_files() -> list[Path]:
    return [
        path
        for path in sorted(GOLDEN_ROOT.rglob("*"))
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
    ]


def test_fixture_text_has_no_private_data_or_secrets():
    for path in _text_files():
        text = path.read_text(encoding="utf-8")
        emails = [
            match.group(0)
            for match in EMAIL_PATTERN.finditer(text)
            if not match.group(0).startswith(EMAIL_ALLOWLIST)
        ]
        assert not emails, f"email address in {path}: {emails}"
        for pattern in PRIVATE_PATH_PATTERNS:
            assert not pattern.search(text), f"private path in {path}"
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(text), f"possible secret in {path}"


def test_manifest_source_and_binary_digests_match():
    for case in MANIFEST["cases"]:
        if "source_dir" in case:
            assert tree_digest(source_dir(case)) == case["source_sha256"], case["id"]
        if "binary" in case:
            path = binary_path(case)
            assert path.stat().st_size == case["size"], case["id"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == case["sha256"], case["id"]

    for contract in MANIFEST.get("binary_contracts", []):
        path = GOLDEN_ROOT / contract["path"]
        assert path.stat().st_size == contract["size"], contract["id"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == contract["sha256"], contract["id"]


def test_deterministic_packer_is_byte_stable(tmp_path: Path):
    case = valid_cases()[0]
    first = deterministic_tar_gz(source_dir(case), tmp_path / "first.tar.gz")
    second = deterministic_tar_gz(source_dir(case), tmp_path / "second.tar.gz")

    assert first.read_bytes() == second.read_bytes()


def test_committed_binaries_stay_within_budget():
    binaries = GOLDEN_ROOT / "binaries"
    files = [path for path in binaries.rglob("*") if path.is_file()]
    sizes = {path: path.stat().st_size for path in files}

    oversized = {path: size for path, size in sizes.items() if size > BINARY_BUDGET}
    assert not oversized, f"binary fixtures exceed {BINARY_BUDGET} bytes: {oversized}"
    assert sum(sizes.values()) <= TOTAL_BINARY_BUDGET
