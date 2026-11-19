"""Retention and cleanup for persisted jobs and generated artifacts."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from core.config import Settings, get_settings
from core.uploads import cleanup_expired_uploads
from persistence.repositories import delete_jobs, list_expired_jobs

_DEFAULT_BATCH_SIZE = 500
ArtifactStatus = Literal["removed", "missing", "skipped", "failed"]


@dataclass(frozen=True)
class CleanupResult:
    """Summary of a retention cleanup run."""

    dry_run: bool
    cutoff: str
    jobs: int = 0
    extracted_paths: int = 0
    output_paths: int = 0
    upload_sessions: int = 0
    skipped_paths: int = 0
    failed_paths: int = 0


def _utc_cutoff(now: datetime | None, retention_days: int) -> tuple[datetime, str]:
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    cutoff = current - timedelta(days=retention_days)
    return current, cutoff.strftime("%Y-%m-%d %H:%M:%S")


def _remove_artifact(
    path_value: str | None,
    roots: tuple[Path, ...],
    *,
    dry_run: bool,
) -> ArtifactStatus:
    if not path_value:
        return "missing"
    path = Path(path_value)
    try:
        if path.is_symlink():
            return "skipped"
        resolved = path.resolve(strict=False)
    except OSError:
        return "failed"
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        return "skipped"
    try:
        if not resolved.exists():
            return "missing"
        if not dry_run:
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
    except OSError:
        return "failed"
    return "removed"


def _process_artifacts(
    job: dict[str, Any],
    roots: tuple[Path, ...],
    *,
    dry_run: bool,
) -> tuple[int, int, int, int, bool]:
    extracted = _remove_artifact(job.get("extracted_path"), roots, dry_run=dry_run)
    output = _remove_artifact(job.get("output_path"), roots, dry_run=dry_run)
    statuses = (extracted, output)
    extracted_removed = 1 if extracted == "removed" else 0
    output_removed = 1 if output == "removed" else 0
    skipped = sum(1 for status in statuses if status == "skipped")
    failed = sum(1 for status in statuses if status == "failed")
    return extracted_removed, output_removed, skipped, failed, "failed" in statuses


def cleanup_expired_data(
    *,
    settings: Settings | None = None,
    retention_days: int | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> CleanupResult:
    """Remove expired job rows, extracted paths, outputs, and upload sessions.

    Only artifacts under the configured work and output roots are removed.
    Paths outside those roots, including user-selected CLI outputs, are left in
    place.  With ``dry_run`` enabled, counts are reported without deleting.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    cfg = settings or get_settings()
    days = cfg.retention_days if retention_days is None else retention_days
    current, cutoff = _utc_cutoff(now, days)
    roots = (cfg.work_dir.resolve(), cfg.output_dir.resolve())

    upload_sessions = cleanup_expired_uploads(
        cfg,
        max_age_seconds=min(cfg.upload_ttl_seconds, days * 24 * 60 * 60),
        now=current.timestamp(),
        dry_run=dry_run,
    )

    jobs = 0
    extracted_paths = 0
    output_paths = 0
    skipped_paths = 0
    failed_paths = 0

    if dry_run:
        for job in list_expired_jobs(cutoff, limit=None):
            extracted, output, skipped, failed, _ = _process_artifacts(job, roots, dry_run=True)
            jobs += 1
            extracted_paths += extracted
            output_paths += output
            skipped_paths += skipped
            failed_paths += failed
    else:
        while True:
            expired = list_expired_jobs(cutoff, limit=batch_size)
            if not expired:
                break
            batch_failed = False
            for job in expired:
                extracted, output, skipped, failed, failed_job = _process_artifacts(
                    job, roots, dry_run=False
                )
                extracted_paths += extracted
                output_paths += output
                skipped_paths += skipped
                failed_paths += failed
                if failed_job:
                    batch_failed = True
                    continue
                jobs += delete_jobs([job["job_id"]])
            if batch_failed or len(expired) < batch_size:
                break

    return CleanupResult(
        dry_run=dry_run,
        cutoff=cutoff,
        jobs=jobs,
        extracted_paths=extracted_paths,
        output_paths=output_paths,
        upload_sessions=upload_sessions,
        skipped_paths=skipped_paths,
        failed_paths=failed_paths,
    )
