from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from tests.certification.artifacts import BuiltArtifact
from tests.certification.models import ImportStatus
from tests.certification.moodle import MoodleTarget
from tests.certification.openedx import OpenEdxTarget
from tests.certification.runtime import CommandResult


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 600,
        log_path: Path | None = None,
    ) -> CommandResult:
        argv = [str(argument) for argument in command]
        self.calls.append(argv)
        joined = " ".join(argv)
        stdout = ""
        if "get_records_sql" in joined:
            stdout = "2\n"
        elif "glob(" in joined:
            stdout = "/tmp/certification-reimport/backup.mbz\n"
        if Path(argv[-1]).name == "reimport.mbz":
            Path(argv[-1]).write_bytes(b"reimport")
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(f"$ {joined}\nexit_code=0\n", encoding="utf-8")
        return CommandResult(
            command=tuple(argv),
            exit_code=0,
            stdout=stdout,
            stderr="",
            duration_seconds=0.01,
            log_file=log_path.name if log_path else None,
        )


def _artifact(tmp_path: Path) -> BuiltArtifact:
    path = tmp_path / "course.mbz"
    path.write_bytes(b"artifact")
    return BuiltArtifact(
        case_id="openedx/core",
        target="moodle",
        path=path,
        sha256="a" * 64,
        size_bytes=path.stat().st_size,
    )


def test_moodle_import_records_restore_and_reimport_commands(tmp_path: Path):
    runner = RecordingRunner()
    target = MoodleTarget(runner=runner, run_id="test", root=tmp_path)

    result = target.import_artifact(_artifact(tmp_path), tmp_path / "work")

    assert result.status == ImportStatus.PASSED
    assert any("restore_backup.php" in argument for argument in result.command)
    assert result.reimport is not None
    assert any("backup.php" in argument for argument in result.reimport.command)
    assert result.reimport.log_file == "rebackup.log"
    assert result.reimport.size_bytes == len(b"reimport")


def test_openedx_reimport_records_export_command(tmp_path: Path):
    runner = RecordingRunner()
    target = OpenEdxTarget(runner=runner, run_id="test")
    target._cms_container = "cms"

    target._export_reimport("course-v1:Org+Course+Run", tmp_path / "work")

    assert target._reimport_info is not None
    assert target._reimport_info.command[:7] == [
        "tutor",
        "local",
        "exec",
        "cms",
        "./manage.py",
        "cms",
        "export",
    ]
    assert target._reimport_info.command[7:] == [
        "course-v1:Org+Course+Run",
        "/tmp/certification-reimport",
    ]
    assert target._reimport_info.log_file == "export.log"
    assert target._reimport_info.duration_seconds == 0.01


def test_openedx_import_records_management_commands(tmp_path: Path, monkeypatch):
    runner = RecordingRunner()
    target = OpenEdxTarget(runner=runner, run_id="test")
    course_key = "course-v1:Org+Course+Run"

    monkeypatch.setattr(target, "_ensure_started", lambda work_dir: None)
    monkeypatch.setattr(target, "_container_id", lambda work_dir: "cms")
    monkeypatch.setattr(target, "_prepare_source", lambda artifact, work_dir: work_dir)
    monkeypatch.setattr(target, "_course_key", lambda source_dir: course_key)
    monkeypatch.setattr(target, "_copy_to_cms", lambda source_dir, work_dir: None)
    monkeypatch.setattr(target, "_export_reimport", lambda key, work_dir: None)

    result = target.import_artifact(_artifact(tmp_path), tmp_path / "work")

    assert result.status == ImportStatus.PASSED
    assert result.command[:7] == [
        "tutor",
        "local",
        "exec",
        "cms",
        "./manage.py",
        "cms",
        "import",
    ]
    assert result.command[7:] == ["/tmp/certification-import", "course"]
