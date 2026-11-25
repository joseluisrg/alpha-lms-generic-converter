"""Check Moodle SCORM package lookup and the resulting Open edX export."""

import hashlib
import tarfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from adapters.openedx.target_adapter import OpenEdxTargetAdapter
from core.parse import ParseService
from core.transform import TransformService
from domain.entities import ContentNode, Course, ScormAsset
from domain.enums import NodeType


ACTIVITY = "activities/scorm_5"
DIRECT_PACKAGE = f"{ACTIVITY}/package.zip"
FILE_STORE_FILENAME = "lesson.zip"


def _scorm_zip(manifest_id: str = "synthetic-scorm") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as package:
        package.writestr(
            ZipInfo("imsmanifest.xml"),
            f'<manifest identifier="{manifest_id}" />',
        )
        package.writestr(ZipInfo("index.html"), "<p>Synthetic SCORM content</p>")
    return buffer.getvalue()


def _write_backup(fixture: Path, backup: Path, payload: bytes, layout: str) -> None:
    with (
        tarfile.open(fixture, "r:gz") as original,
        tarfile.open(backup, "w:gz") as edited,
    ):
        if layout == "activity_directory":
            replacements = {DIRECT_PACKAGE: payload}
        else:
            file_table = original.extractfile("files.xml")
            assert file_table is not None
            with file_table:
                files = ET.parse(file_table).getroot()
            inforef = ET.Element("inforef")
            fileref = ET.SubElement(inforef, "fileref")
            packages = [
                ("12", "package", FILE_STORE_FILENAME, payload),
                ("13", "content", "content.zip", _scorm_zip("other-content")),
            ]
            if layout == "ambiguous_packages":
                packages.append(
                    ("14", "package", "second.zip", _scorm_zip("second-package"))
                )

            replacements = {}
            for file_id, area, filename, data in packages:
                assert files.find(f"./file[@id='{file_id}']") is None
                content_hash = hashlib.sha1(data, usedforsecurity=False).hexdigest()
                record = ET.SubElement(files, "file", id=file_id)
                for tag, value in {
                    "contenthash": content_hash,
                    "component": "mod_scorm",
                    "filearea": area,
                    "filepath": "/",
                    "filename": filename,
                    "mimetype": "application/zip",
                }.items():
                    ET.SubElement(record, tag).text = value
                ET.SubElement(ET.SubElement(fileref, "file"), "id").text = file_id
                if not (layout == "missing_package" and file_id == "12"):
                    replacements[f"files/{content_hash[:2]}/{content_hash}"] = data

            replacements["files.xml"] = ET.tostring(files, encoding="utf-8")
            replacements[f"{ACTIVITY}/inforef.xml"] = ET.tostring(inforef, encoding="utf-8")

        for member in original.getmembers():
            if member.name == DIRECT_PACKAGE or member.name in replacements:
                continue
            data = original.extractfile(member)
            assert data is not None
            with data:
                edited.addfile(member, data)

        for name, data in replacements.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            edited.addfile(member, BytesIO(data))


def _scorm_activity(course: Course) -> ContentNode:
    (activity,) = (
        child
        for node in course._all_nodes()
        if node.metadata.get("moodle_cmid") == "5"
        for child in node.children
    )
    return activity


@pytest.mark.parametrize(
    ("layout", "export_name"),
    [("activity_directory", "package.zip"), ("file_store", FILE_STORE_FILENAME)],
)
def test_moodle_scorm_zip_is_linked_and_exported(
    moodle_archive: Path, tmp_path: Path, layout: str, export_name: str
) -> None:
    backup = tmp_path / "scorm.mbz"
    payload = _scorm_zip()
    _write_backup(moodle_archive, backup, payload, layout)
    parsed = ParseService().parse(str(backup), "moodle", str(tmp_path / "extracted"))
    course = TransformService().transform(parsed, "moodle", "job-scorm")
    extracted = Path(parsed["extracted_path"])

    activity = _scorm_activity(course)
    assert activity.node_type == NodeType.SCORM
    (asset,) = [asset for asset in course.assets if isinstance(asset, ScormAsset)]
    assert activity.metadata["asset_id"] == asset.asset_id
    assert (extracted / asset.original_zip_path).read_bytes() == payload

    export = OpenEdxTargetAdapter().generate_export(
        course, str(tmp_path / "scorm-export.tar.gz"), str(extracted)
    )
    with tarfile.open(export, "r:gz") as archive:
        members = {
            member.name.removeprefix("./"): member for member in archive.getmembers()
        }
        (block,) = [
            member
            for name, member in members.items()
            if name.startswith("scormxblock/") and name.endswith(".xml")
        ]
        block_file = archive.extractfile(block)
        assert block_file is not None
        with block_file:
            scorm_file = ET.parse(block_file).getroot().attrib["scorm_file"]
        assert scorm_file == f"/static/{export_name}"
        zip_file = archive.extractfile(members[scorm_file.lstrip("/")])
        assert zip_file is not None
        with zip_file:
            assert zip_file.read() == payload


@pytest.mark.parametrize("layout", ["missing_package", "ambiguous_packages"])
def test_moodle_scorm_unresolved_package_uses_html_fallback(
    moodle_archive: Path, tmp_path: Path, layout: str
) -> None:
    backup = tmp_path / "scorm.mbz"
    _write_backup(moodle_archive, backup, _scorm_zip(), layout)
    parsed = ParseService().parse(str(backup), "moodle", str(tmp_path / "extracted"))
    course = TransformService().transform(parsed, "moodle", "job-scorm")

    activity = _scorm_activity(course)
    assert activity.node_type == NodeType.HTML
    assert (
        activity.metadata["content_html"]
        == "<p>Missing SCORM package for activity: SCORM</p>"
    )
    assert not any(isinstance(asset, ScormAsset) for asset in course.assets)
