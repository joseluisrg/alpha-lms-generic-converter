from __future__ import annotations

import io
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree.ElementTree import ParseError  # nosec B405 - expected-error type only

import pytest

from core.archive_utils import safe_extract_tar, safe_extract_zip
from core.config import get_settings
from core.errors import (
    ArchiveSecurityError,
    UnsafePathError,
    UploadSecurityError,
    XmlSecurityError,
)
from core.parse import ParseService
from core.uploads import save_upload
from core.xml_utils import parse_xml_file, parse_xml_text
from tests.golden.corpus import (
    GOLDEN_ROOT,
    binary_path,
    deterministic_tar_gz,
    invalid_cases,
    load_manifest,
    source_dir,
)

MANIFEST = load_manifest()
INVALID_CASES = invalid_cases(MANIFEST)
ERROR_TYPES = {
    "ArchiveSecurityError": ArchiveSecurityError,
    "ParseError": ParseError,
    "UnsafePathError": UnsafePathError,
    "UploadSecurityError": UploadSecurityError,
    "XmlSecurityError": XmlSecurityError,
}


def _case_id(case: dict) -> str:
    return case["id"]


def _expected_error(case: dict) -> type[Exception]:
    return ERROR_TYPES[case["expected_error"]]


def _write_tar(path: Path, entries: list[tuple[str, bytes | None, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data, entry_type in entries:
            info = tarfile.TarInfo(name)
            info.type = entry_type
            info.mtime = 0
            if data is not None:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            else:
                archive.addfile(info)


def _build_recipe(recipe: str, path: Path) -> Path:
    if recipe == "tar_duplicate":
        _write_tar(
            path,
            [
                ("course.xml", b"<course />", tarfile.REGTYPE),
                ("course.xml", b"<course />", tarfile.REGTYPE),
            ],
        )
    elif recipe == "tar_device":
        _write_tar(path, [("device", None, tarfile.CHRTYPE)])
    elif recipe == "zip_bomb":
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("zeros.bin", b"\x00" * (6 * 1024 * 1024))
    else:  # pragma: no cover - manifest-controlled
        raise AssertionError(f"Unknown archive recipe: {recipe}")
    return path


@pytest.mark.parametrize("case", INVALID_CASES, ids=[_case_id(case) for case in INVALID_CASES])
def test_invalid_case(case: dict, tmp_path: Path):
    error = _expected_error(case)
    check = case["check"]

    if check == "xml_file":
        with pytest.raises(error):
            parse_xml_file(GOLDEN_ROOT / case["source_file"])

    elif check == "xml_text_limits":
        with pytest.raises(error):
            parse_xml_text(
                case["payload"],
                max_bytes=case.get("max_bytes"),
                max_depth=case.get("max_depth"),
            )

    elif check == "package_parse":
        suffix = ".mbz" if case["source"] == "moodle" else ".tar.gz"
        archive = tmp_path / f"invalid{suffix}"
        deterministic_tar_gz(source_dir(case), archive)
        with pytest.raises(error):
            ParseService().parse(
                str(archive),
                case["source"],
                str(tmp_path / "extracted"),
            )
        assert not list(tmp_path.rglob("escape*"))

    elif check == "extract_tar":
        with pytest.raises(error):
            safe_extract_tar(binary_path(case), tmp_path / "out")

    elif check == "extract_zip":
        with pytest.raises(error):
            safe_extract_zip(binary_path(case), tmp_path / "out")

    elif check == "archive_recipe":
        suffix = ".zip" if case["recipe"] == "zip_bomb" else ".tar.gz"
        archive = _build_recipe(case["recipe"], tmp_path / f"recipe{suffix}")
        extractor = safe_extract_zip if suffix == ".zip" else safe_extract_tar
        with pytest.raises(error):
            extractor(archive, tmp_path / "out")

    elif check == "upload_boundaries":
        settings = replace(get_settings(), max_upload_bytes=4)
        with pytest.raises(error):
            save_upload(
                io.BytesIO(b"12345"),
                "course.mbz",
                session_id="golden",
                settings=settings,
            )
        with pytest.raises(error):
            save_upload(
                io.BytesIO(b""),
                "course.mbz",
                session_id="golden",
                settings=settings,
            )
        with pytest.raises(error):
            save_upload(
                io.BytesIO(b"123"),
                "course.zip",
                session_id="golden",
                settings=settings,
            )
        with pytest.raises(error):
            save_upload(
                io.BytesIO(b"123"),
                "course.mbz",
                session_id="",
                settings=settings,
            )

    else:  # pragma: no cover - manifest-controlled
        raise AssertionError(f"Unknown invalid case check: {check}")
