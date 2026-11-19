import json
import re
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app
from core.config import get_settings, reset_settings
from core.errors import SchemaVersionError
from domain.entities import Course
from domain.enums import SourceSystem
from persistence import repositories

runner = CliRunner()


def _job_id(output: str) -> str:
    match = re.search(r"Job ID:\s*([0-9a-f-]{36})", output)
    assert match, output
    return match.group(1)


def test_inspect_auto_detects_moodle_and_saves_json(moodle_archive: Path, tmp_path: Path):
    report_path = tmp_path / "inspection.json"

    result = runner.invoke(
        app,
        ["inspect", str(moodle_archive), "--output", str(report_path)],
    )

    assert result.exit_code == 0, result.output
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["job_id"]
    assert payload["schema_version"]
    assert payload["course"]["source_system"] == "moodle"


def test_inspect_explicit_openedx_source(openedx_archive: Path):
    result = runner.invoke(
        app,
        ["inspect", str(openedx_archive), "--source", "openedx"],
    )

    assert result.exit_code == 0, result.output
    assert _job_id(result.output)


@pytest.mark.parametrize(
    ("fixture_name", "source", "target", "suffix"),
    [
        ("openedx_archive", "openedx", "moodle", ".mbz"),
        ("moodle_archive", "moodle", "openedx", ".tar.gz"),
    ],
)
def test_migrate_end_to_end(
    fixture_name: str,
    source: str,
    target: str,
    suffix: str,
    request: pytest.FixtureRequest,
    tmp_path: Path,
):
    archive = request.getfixturevalue(fixture_name)
    output = tmp_path / f"converted{suffix}"

    result = runner.invoke(
        app,
        [
            "migrate",
            str(archive),
            "--source",
            source,
            "--target",
            target,
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert _job_id(result.output)


def test_report_command_renders_json_and_html(openedx_archive: Path, tmp_path: Path):
    inspect_result = runner.invoke(
        app,
        ["inspect", str(openedx_archive), "--source", "openedx"],
    )
    assert inspect_result.exit_code == 0, inspect_result.output
    job_id = _job_id(inspect_result.output)

    json_result = runner.invoke(app, ["report", job_id, "--format", "json"])
    assert json_result.exit_code == 0, json_result.output
    assert job_id in json_result.output

    html_path = tmp_path / "report.html"
    html_result = runner.invoke(
        app,
        ["report", job_id, "--format", "html", "--output", str(html_path)],
    )
    assert html_result.exit_code == 0, html_result.output
    assert html_path.is_file()
    assert "<html" in html_path.read_text(encoding="utf-8").lower()


def test_inspect_missing_file_fails(tmp_path: Path):
    result = runner.invoke(
        app,
        ["inspect", str(tmp_path / "missing.mbz"), "--source", "moodle"],
    )

    assert result.exit_code == 1


def test_inspect_unknown_extension_fails(tmp_path: Path):
    unknown = tmp_path / "course.bin"
    unknown.write_bytes(b"not a course archive")

    result = runner.invoke(app, ["inspect", str(unknown)])

    assert result.exit_code == 1


def test_migrate_unsupported_target_fails(openedx_archive: Path, tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "migrate",
            str(openedx_archive),
            "--source",
            "openedx",
            "--target",
            "canvas",
            "--output",
            str(tmp_path / "converted.out"),
        ],
    )

    assert result.exit_code == 1


def test_report_missing_job_fails():
    result = runner.invoke(app, ["report", "00000000-0000-0000-0000-000000000000"])

    assert result.exit_code == 1


def test_version_flag():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip()


def test_version_does_not_create_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "unused" / "jobs.db"
    monkeypatch.setenv("LMS_CONVERTER_DB_PATH", str(db_path))
    reset_settings()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert not db_path.exists()


def test_cli_rejects_newer_database_schema(monkeypatch: pytest.MonkeyPatch):
    def fail_schema_check() -> None:
        raise SchemaVersionError("Database schema version 99 is newer than supported version 1")

    monkeypatch.setattr("cli.main.init_db", fail_schema_check)

    result = runner.invoke(app, ["report", "missing"])

    assert result.exit_code == 1
    assert "Database schema version 99" in result.output


def test_cleanup_command_dry_run_then_apply():
    settings = get_settings()
    settings.ensure_directories()
    course = Course(course_id="cleanup", title="Cleanup", source_system=SourceSystem.OPENEDX)
    repositories.save_job("cleanup-job", "openedx", "moodle", course, [])
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ? WHERE job_id = ?",
            ("2020-01-01 00:00:00", "2020-01-01 00:00:00", "cleanup-job"),
        )
        conn.commit()

    dry_run = runner.invoke(app, ["cleanup"])

    assert dry_run.exit_code == 0
    assert "Would remove 1 jobs" in dry_run.output
    assert repositories.get_job("cleanup-job") is not None

    applied = runner.invoke(app, ["cleanup", "--apply"])

    assert applied.exit_code == 0
    assert "Removed 1 jobs" in applied.output
    assert repositories.get_job("cleanup-job") is None
