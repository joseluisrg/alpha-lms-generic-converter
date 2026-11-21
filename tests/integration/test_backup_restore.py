import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from core.config import get_settings
from persistence.repositories import SCHEMA_VERSION, get_job, init_db

runner = CliRunner()


def _job_id(output: str) -> str:
    match = re.search(r"Job ID:\s*([0-9a-f-]{36})", output)
    assert match, output
    return match.group(1)


def test_backup_restore_drill_preserves_jobs_and_artifacts(openedx_archive: Path, tmp_path: Path):
    settings = get_settings()
    settings.ensure_directories()
    output_path = settings.output_dir / "restored.mbz"
    report_path = settings.report_dir / "restored.html"

    inspect_result = runner.invoke(
        app,
        ["inspect", str(openedx_archive), "--source", "openedx"],
    )
    assert inspect_result.exit_code == 0, inspect_result.output
    inspect_job_id = _job_id(inspect_result.output)

    migrate_result = runner.invoke(
        app,
        [
            "migrate",
            str(openedx_archive),
            "--source",
            "openedx",
            "--target",
            "moodle",
            "--output",
            str(output_path),
        ],
    )
    assert migrate_result.exit_code == 0, migrate_result.output
    migration_job_id = _job_id(migrate_result.output)

    report_result = runner.invoke(
        app,
        ["report", migration_job_id, "--format", "html", "--output", str(report_path)],
    )
    assert report_result.exit_code == 0, report_result.output

    before = get_job(migration_job_id)
    assert before is not None
    assert before["status"] == "migrated"
    assert output_path.is_file()
    assert report_path.is_file()

    with closing(sqlite3.connect(settings.db_path)) as conn:
        conn.execute("PRAGMA wal_checkpoint(FULL)")

    backup_dir = tmp_path / "backup"
    shutil.copytree(settings.data_dir, backup_dir)
    shutil.rmtree(settings.data_dir)
    assert not settings.db_path.exists()

    shutil.copytree(backup_dir, settings.data_dir)
    init_db()

    assert get_job(inspect_job_id) is not None
    after = get_job(migration_job_id)
    assert after is not None
    for field in (
        "status",
        "owner",
        "source_type",
        "target_type",
        "course_json",
        "report_json",
        "extracted_path",
        "output_path",
    ):
        assert after[field] == before[field]

    assert output_path.is_file()
    assert report_path.is_file()

    with closing(sqlite3.connect(settings.db_path)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    cleanup_result = runner.invoke(app, ["cleanup"])
    assert cleanup_result.exit_code == 0, cleanup_result.output
