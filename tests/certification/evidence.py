"""Parse original and re-imported artifacts into comparable evidence."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET  # nosec B405
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.moodle.backup_reader import MoodleBackupReader
from core.xml_utils import parse_xml_file
from domain.entities import Asset, ContentNode, Course
from domain.enums import NodeType
from tests.golden.corpus import extract_tar, run_roundtrip

MOODLE_BACKUP = "moodle_backup.xml"


@dataclass(frozen=True)
class Evidence:
    """Stable view of one generated or re-imported target archive."""

    archive: Path
    target: str
    course: Course
    extracted: Path
    moodle_manifest: dict[str, Any] | None = None
    openedx_root_course: ET.Element | None = None
    openedx_static: dict[str, Path] | None = None
    openedx_scorm: dict[str, Path] | None = None

    @property
    def nodes(self) -> list[ContentNode]:
        return list(_walk_nodes(self.course.content_nodes))

    @property
    def node_counts(self) -> Counter[str]:
        return Counter(node.node_type.value for node in self.nodes)

    @property
    def question_counts(self) -> Counter[str]:
        return Counter(question.question_type for question in self.course.questions)

    @property
    def asset_names(self) -> set[str]:
        return {_asset_name(asset) for asset in self.course.assets if _asset_name(asset)}

    @property
    def moodle_file_records(self) -> dict[str, dict[str, Any]]:
        if self.moodle_manifest is None:
            return {}
        return dict(self.moodle_manifest.get("file_records", {}))

    @property
    def moodle_files_by_name(self) -> dict[str, list[dict[str, Any]]]:
        files: dict[str, list[dict[str, Any]]] = {}
        for record in self.moodle_file_records.values():
            name = str(record.get("filename", ""))
            if not name or name == ".":
                continue
            files.setdefault(name, []).append(record)
        return files

    @property
    def moodle_activity_modules(self) -> Counter[str]:
        if self.moodle_manifest is None:
            return Counter()
        return Counter(
            str(activity.get("module_name", ""))
            for activity in self.moodle_manifest.get("activities", {}).values()
        )

    @property
    def openedx_course_key(self) -> str | None:
        root = self.openedx_root_course
        if root is None:
            return None
        org = root.attrib.get("org")
        course = root.attrib.get("course")
        url_name = root.attrib.get("url_name")
        if not org or not course or not url_name:
            return None
        return f"course-v1:{org}+{course}+{url_name}"

    def html_text(self) -> str:
        return "\n".join(
            str(node.metadata.get("content_html", ""))
            for node in self.nodes
            if node.node_type in {NodeType.HTML, NodeType.PAGE}
        )

    def has_html(self, needle: str) -> bool:
        return needle in self.html_text()

    def node_titles(self, node_type: NodeType) -> set[str]:
        return {
            str(node.title) for node in self.nodes if node.node_type == node_type and node.title
        }

    def asset(self, name: str) -> Asset | None:
        for asset in self.course.assets:
            if _asset_name(asset) == name:
                return asset
        return None

    def moodle_file_record(self, name: str) -> dict[str, Any] | None:
        records = self.moodle_files_by_name.get(name)
        return records[0] if records else None

    def moodle_file_bytes(self, name: str) -> bytes | None:
        record = self.moodle_file_record(name)
        if record is None:
            return None
        contenthash = str(record.get("contenthash", ""))
        if not contenthash:
            return None
        path = self.extracted / "files" / contenthash[:2] / contenthash
        if not path.is_file():
            return None
        return path.read_bytes()

    def openedx_static_file(self, name: str) -> Path | None:
        if self.openedx_static is None:
            return None
        return self.openedx_static.get(name)

    def openedx_package_file(self, name: str = "package.zip") -> Path | None:
        for relative_path, path in sorted((self.openedx_scorm or {}).items()):
            if Path(relative_path).name == name:
                return path
        return self.openedx_static_file(name)

    def has_numerical_tolerance(self, tolerance: str | None = None) -> bool:
        for question in self.course.questions:
            if question.question_type != "numerical":
                continue
            value = question.metadata.get("tolerance")
            if value is None:
                continue
            if tolerance is None or str(value) == tolerance:
                return True
        return False


def load_evidence(archive: Path, target: str, work_dir: Path) -> Evidence:
    """Parse a target artifact and collect manifest/static evidence."""
    archive = Path(archive)
    work_dir.mkdir(parents=True, exist_ok=True)
    course = run_roundtrip(archive, target, work_dir / "roundtrip")

    if target == "moodle":
        reader = MoodleBackupReader()
        extracted = reader.extract_archive(str(archive), str(work_dir / "extract"))
        manifest = reader.read_manifest(extracted)
        return Evidence(
            archive=archive,
            target=target,
            course=course,
            extracted=extracted,
            moodle_manifest=manifest,
        )

    if target == "openedx":
        extracted = extract_tar(archive, work_dir / "extract")
        root_path = _find_root_course_xml(extracted)
        root = parse_xml_file(root_path) if root_path is not None else None
        static = {
            path.relative_to(extracted / "static").as_posix(): path
            for path in (extracted / "static").rglob("*")
            if path.is_file()
        }
        scorm = {
            path.relative_to(extracted).as_posix(): path
            for path in (extracted / "scorm").rglob("package.zip")
            if path.is_file()
        }
        return Evidence(
            archive=archive,
            target=target,
            course=course,
            extracted=extracted,
            openedx_root_course=root,
            openedx_static=static,
            openedx_scorm=scorm,
        )

    raise ValueError(f"Unsupported evidence target: {target!r}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_nodes(nodes: list[ContentNode]):
    for node in nodes:
        yield node
        yield from _walk_nodes(node.children)


def _asset_name(asset: Asset) -> str:
    original = asset.metadata.get("original_filename")
    if original:
        return str(original)
    return Path(asset.path).name


def _find_root_course_xml(extracted: Path) -> Path | None:
    direct = extracted / "course.xml"
    if direct.is_file():
        return direct
    candidates = sorted(extracted.rglob("course.xml"))
    return candidates[0] if candidates else None
