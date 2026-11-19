from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from core.config import reset_settings
from core.errors import SchemaVersionError
from persistence import repositories
from persistence.repositories import SCHEMA_VERSION, get_job, init_db, list_jobs


def _use_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "database" / "jobs.db"
    monkeypatch.setenv("LMS_CONVERTER_DB_PATH", str(db_path))
    reset_settings()
    return db_path


def _database_version(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


@contextmanager
def _traced_connection(db_path: Path, statements: list[str]):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.set_trace_callback(statements.append)
    try:
        yield conn
    finally:
        conn.close()


def test_legacy_jobs_table_is_upgraded_without_data_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = _use_database(monkeypatch, tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT '',
                course_json TEXT,
                report_json TEXT,
                extracted_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO jobs
                (job_id, source_type, target_type, course_json, report_json,
                 extracted_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-job",
                "openedx",
                "moodle",
                '{"title": "Legacy course"}',
                "[]",
                "/tmp/legacy",
            ),
        )
        conn.commit()

    init_db()

    job = get_job("legacy-job")
    assert job is not None
    assert job["course_json"] == '{"title": "Legacy course"}'
    assert job["target_type"] == "moodle"
    assert job["status"] == "inspected"
    assert job["owner"] == "local"
    assert job["output_path"] is None
    assert job["error"] is None
    assert job["updated_at"] is None
    assert _database_version(db_path) == SCHEMA_VERSION

    assert [row["job_id"] for row in list_jobs()] == ["legacy-job"]


def test_init_db_records_schema_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_database(monkeypatch, tmp_path)

    init_db()

    assert _database_version(db_path) == SCHEMA_VERSION
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    assert {"job_id", "status", "owner", "output_path", "error", "updated_at"} <= columns


def test_init_db_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_database(monkeypatch, tmp_path)

    init_db()
    init_db()

    assert _database_version(db_path) == SCHEMA_VERSION
    assert list_jobs() == []


def test_init_db_rejects_newer_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_database(monkeypatch, tmp_path)
    init_db()

    with sqlite3.connect(db_path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        conn.commit()

    with pytest.raises(SchemaVersionError, match="newer"):
        init_db()


def test_init_db_rejects_incomplete_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_database(monkeypatch, tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()

    with pytest.raises(SchemaVersionError, match="missing required columns"):
        init_db()


def test_init_db_does_not_run_ddl_when_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_database(monkeypatch, tmp_path)
    init_db()
    statements: list[str] = []
    monkeypatch.setattr(
        repositories,
        "_connect",
        lambda: _traced_connection(db_path, statements),
    )

    init_db()

    ddl = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))
    ]
    assert ddl == []


def test_reads_do_not_run_ddl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_database(monkeypatch, tmp_path)
    init_db()
    statements: list[str] = []
    monkeypatch.setattr(
        repositories,
        "_connect",
        lambda: _traced_connection(db_path, statements),
    )

    assert repositories.get_job("missing") is None
    assert repositories.list_jobs() == []

    ddl = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))
    ]
    assert ddl == []
