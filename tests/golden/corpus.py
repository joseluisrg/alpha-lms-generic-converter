"""Golden-corpus manifest, deterministic packaging, and pipeline helpers."""

from __future__ import annotations

import gzip
import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

from adapters.moodle.target_adapter import MoodleTargetAdapter
from adapters.openedx.target_adapter import OpenEdxTargetAdapter
from core.parse import ParseService
from core.transform import TransformService
from core.validate import ValidationService
from tests.golden.snapshots import (
    SNAPSHOT_VERSION,
    load_json,
    snapshot_course,
    snapshot_export_tree,
    snapshot_report,
)

GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
MANIFEST_PATH = GOLDEN_ROOT / "manifest.json"
MANIFEST_SCHEMA_VERSION = 1
CORPUS_VERSION = 1


def load_manifest() -> dict[str, Any]:
    data = load_json(MANIFEST_PATH)
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported golden manifest schema: {data.get('schema_version')!r}")
    if data.get("corpus_version") != CORPUS_VERSION:
        raise ValueError(f"Unsupported golden corpus version: {data.get('corpus_version')!r}")
    if data.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError(f"Unsupported golden snapshot version: {data.get('snapshot_version')!r}")
    return data


def valid_cases(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = manifest or load_manifest()
    return [case for case in data["cases"] if case["kind"] == "valid"]


def invalid_cases(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = manifest or load_manifest()
    return [case for case in data["cases"] if case["kind"] == "invalid"]


def source_dir(case: dict[str, Any]) -> Path:
    return GOLDEN_ROOT / case["source_dir"]


def binary_path(case: dict[str, Any]) -> Path:
    return GOLDEN_ROOT / case["binary"]


def expected_path(case: dict[str, Any], key: str, target: str | None = None) -> Path:
    if key == "exports":
        if target is None:
            raise ValueError("target is required for export snapshots")
        return GOLDEN_ROOT / case["expected"]["exports"][target]
    return GOLDEN_ROOT / case["expected"][key]


def declared_snapshot_paths(manifest: dict[str, Any]) -> set[Path]:
    """Return every snapshot path declared by valid manifest cases."""
    paths: set[Path] = set()
    for case in valid_cases(manifest):
        paths.add(expected_path(case, "course"))
        paths.add(expected_path(case, "report"))
        for target in case.get("targets", []):
            paths.add(expected_path(case, "exports", target))
    return paths


def tree_digest(root: Path) -> str:
    """Return a stable digest over sorted relative paths and file contents."""
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def deterministic_tar_gz(source: Path, output: Path) -> Path:
    """Build a tar.gz with fixed metadata so repeated runs are byte-stable."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gzipped,
        tarfile.open(fileobj=gzipped, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for path in sorted(candidate for candidate in source.rglob("*") if candidate.is_file()):
            arcname = path.relative_to(source).as_posix()
            info = archive.gettarinfo(str(path), arcname=arcname)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return output


def extract_tar(archive_path: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as archive:
        archive.extractall(target_dir, filter="data")
    return target_dir


def run_case(case: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """Package, parse, transform, and validate one valid corpus case."""
    source = case["source"]
    suffix = ".mbz" if source == "moodle" else ".tar.gz"
    archive_path = tmp_path / f"{case['id'].replace('/', '-')}{suffix}"
    deterministic_tar_gz(source_dir(case), archive_path)

    parsed = ParseService().parse(
        str(archive_path),
        source,
        str(tmp_path / "source-extracted"),
    )
    course = TransformService().transform(parsed, source, "golden")

    target = case.get("report_target")
    if target is None and case.get("targets"):
        target = case["targets"][0]
    report = ValidationService().validate(course, target=target)

    return {
        "archive": archive_path,
        "parsed": parsed,
        "course": course,
        "report": report,
        "report_target": target,
    }


def run_export(
    course: Any,
    target: str,
    source_extracted_path: str | None,
    case_id: str,
    tmp_path: Path,
) -> dict[str, Any]:
    """Generate and extract one target export."""
    if target == "moodle":
        output_path = tmp_path / f"{case_id.replace('/', '-')}-moodle.mbz"
        moodle_adapter = MoodleTargetAdapter(work_dir=tmp_path / "work-moodle")
        archive = Path(
            moodle_adapter.generate_backup(course, str(output_path), source_extracted_path)
        )
    elif target == "openedx":
        output_path = tmp_path / f"{case_id.replace('/', '-')}-openedx.tar.gz"
        openedx_adapter = OpenEdxTargetAdapter(work_dir=tmp_path / "work-openedx")
        archive = Path(
            openedx_adapter.generate_export(course, str(output_path), source_extracted_path)
        )
    else:
        raise ValueError(f"Unsupported golden target: {target}")

    extract_dir = tmp_path / f"export-{target}-extracted"
    extract_tar(archive, extract_dir)
    return {"archive": archive, "extract_dir": extract_dir}


def run_roundtrip(archive_path: Path, target: str, tmp_path: Path) -> Any:
    """Parse and transform a generated export to verify it remains importable."""
    parsed = ParseService().parse(
        str(archive_path),
        target,
        str(tmp_path / f"roundtrip-{target}"),
    )
    return TransformService().transform(parsed, target, "golden-roundtrip")


def build_case_snapshots(
    case: dict[str, Any],
    tmp_path: Path,
) -> tuple[dict[Path, Any], dict[str, Any]]:
    """Build all snapshots for one case, returning paths and pipeline output."""
    result = run_case(case, tmp_path)
    snapshots: dict[Path, Any] = {
        expected_path(case, "course"): snapshot_course(result["course"], case),
        expected_path(case, "report"): snapshot_report(
            result["course"],
            result["report"],
            case,
            result["report_target"],
        ),
    }

    for target in case.get("targets", []):
        export = run_export(
            result["course"],
            target,
            result["parsed"].get("extracted_path"),
            case["id"],
            tmp_path,
        )
        snapshots[expected_path(case, "exports", target)] = snapshot_export_tree(
            export["extract_dir"],
            case["id"],
            target,
        )

    return snapshots, result


def manifest_with_updated_digests(
    manifest: dict[str, Any],
    *,
    allow_binary_change: bool = False,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return a manifest with current source/binary digests."""
    for case in manifest["cases"]:
        if case_ids is not None and case["id"] not in case_ids:
            continue
        if "source_dir" in case:
            case["source_sha256"] = tree_digest(source_dir(case))
        elif "binary" in case and allow_binary_change:
            path = binary_path(case)
            case["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            case["size"] = path.stat().st_size

    if allow_binary_change:
        for contract in manifest.get("binary_contracts", []):
            if case_ids is not None and contract["id"] not in case_ids:
                continue
            path = GOLDEN_ROOT / contract["path"]
            contract["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            contract["size"] = path.stat().st_size
    return manifest


def write_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
