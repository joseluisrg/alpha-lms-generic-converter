from __future__ import annotations

import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.config import get_settings
from core.retention import cleanup_expired_data
from domain.entities import Course
from domain.enums import SourceSystem
from persistence import repositories


def _save_job(
    job_id: str,
    *,
    extracted_path: str | None = None,
    output_path: str | None = None,
    age_days: int = 0,
) -> None:
    course = Course(course_id=job_id, title="Retention", source_system=SourceSystem.OPENEDX)
    repositories.save_job(job_id, "openedx", "moodle", course, [], extracted_path)
    if output_path is not None:
        repositories.save_migration_job(
            job_id,
            "openedx",
            "moodle",
            course,
            [],
            extracted_path,
            output_path,
        )

    timestamp = (datetime.now(UTC) - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(get_settings().db_path) as conn:
        conn.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ? WHERE job_id = ?",
            (timestamp, timestamp, job_id),
        )
        conn.commit()


def _make_file(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _make_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "course.xml").write_text("<course />", encoding="utf-8")
    return path


def test_cleanup_dry_run_then_apply(tmp_path: Path):
    settings = get_settings()
    settings.ensure_directories()

    expired_extract = _make_dir(settings.work_dir / "expired" / "course")
    expired_output = _make_file(settings.output_dir / "expired.mbz")
    fresh_extract = _make_dir(settings.work_dir / "fresh" / "course")
    fresh_output = _make_file(settings.output_dir / "fresh.mbz")
    old_upload = settings.upload_dir / "old"
    old_upload.mkdir()
    old_time = time.time() - 3 * 24 * 60 * 60
    os.utime(old_upload, (old_time, old_time))
    fresh_upload = settings.upload_dir / "fresh"
    fresh_upload.mkdir()

    _save_job(
        "expired",
        extracted_path=str(expired_extract),
        output_path=str(expired_output),
        age_days=60,
    )
    _save_job(
        "fresh",
        extracted_path=str(fresh_extract),
        output_path=str(fresh_output),
        age_days=0,
    )

    dry_run = cleanup_expired_data(
        settings=settings,
        retention_days=30,
        now=datetime.now(UTC),
        dry_run=True,
    )

    assert dry_run.jobs == 1
    assert dry_run.extracted_paths == 1
    assert dry_run.output_paths == 1
    assert dry_run.upload_sessions == 1
    assert repositories.get_job("expired") is not None
    assert expired_extract.exists()
    assert expired_output.exists()
    assert old_upload.exists()

    result = cleanup_expired_data(
        settings=settings,
        retention_days=30,
        now=datetime.now(UTC),
        dry_run=False,
    )

    assert result.jobs == 1
    assert result.extracted_paths == 1
    assert result.output_paths == 1
    assert result.upload_sessions == 1
    assert repositories.get_job("expired") is None
    assert repositories.get_job("fresh") is not None
    assert not expired_extract.exists()
    assert not expired_output.exists()
    assert not old_upload.exists()
    assert fresh_extract.exists()
    assert fresh_output.exists()
    assert fresh_upload.exists()


def test_cleanup_leaves_paths_outside_managed_roots(tmp_path: Path):
    settings = get_settings()
    settings.ensure_directories()
    external = _make_file(tmp_path / "external.mbz", b"external")

    _save_job("external", output_path=str(external), age_days=60)

    result = cleanup_expired_data(
        settings=settings,
        retention_days=30,
        now=datetime.now(UTC),
        dry_run=False,
    )

    assert result.jobs == 1
    assert result.skipped_paths == 1
    assert external.exists()
    assert repositories.get_job("external") is None


def test_cleanup_deletes_jobs_with_missing_artifacts():
    settings = get_settings()
    settings.ensure_directories()
    missing = settings.work_dir / "missing" / "course"
    _save_job("missing", extracted_path=str(missing), age_days=60)

    result = cleanup_expired_data(
        settings=settings,
        retention_days=30,
        now=datetime.now(UTC),
        dry_run=False,
    )

    assert result.jobs == 1
    assert result.extracted_paths == 0
    assert result.failed_paths == 0
    assert repositories.get_job("missing") is None


def test_cleanup_processes_multiple_batches():
    settings = get_settings()
    settings.ensure_directories()
    _save_job("expired-one", age_days=60)
    _save_job("expired-two", age_days=60)

    result = cleanup_expired_data(
        settings=settings,
        retention_days=30,
        now=datetime.now(UTC),
        dry_run=False,
        batch_size=1,
    )

    assert result.jobs == 2
    assert repositories.get_job("expired-one") is None
    assert repositories.get_job("expired-two") is None


def test_cleanup_skips_symlinked_artifacts(tmp_path: Path):
    settings = get_settings()
    settings.ensure_directories()
    outside = _make_dir(tmp_path / "outside")
    link = settings.work_dir / "linked"
    link.symlink_to(outside, target_is_directory=True)

    _save_job("linked", extracted_path=str(link), age_days=60)

    result = cleanup_expired_data(
        settings=settings,
        retention_days=30,
        now=datetime.now(UTC),
        dry_run=False,
    )

    assert result.jobs == 1
    assert result.skipped_paths == 1
    assert outside.exists()
    assert repositories.get_job("linked") is None


def test_cleanup_rejects_non_positive_retention():
    with pytest.raises(ValueError, match="positive"):
        cleanup_expired_data(retention_days=0, dry_run=True)
