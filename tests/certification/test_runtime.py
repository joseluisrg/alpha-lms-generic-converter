from __future__ import annotations

import sys
from pathlib import Path

from tests.certification.redaction import redact
from tests.certification.runtime import CommandError, SubprocessRunner


def test_subprocess_runner_captures_output_and_writes_log(tmp_path: Path):
    runner = SubprocessRunner()
    log = tmp_path / "command.log"

    result = runner.run(
        [sys.executable, "-c", "print('hello')"],
        log_path=log,
    )

    assert result.ok
    assert result.stdout.strip() == "hello"
    assert result.exit_code == 0
    assert result.log_file == "command.log"
    assert "hello" in log.read_text(encoding="utf-8")


def test_subprocess_runner_redacts_secrets_in_log(tmp_path: Path):
    runner = SubprocessRunner()
    log = tmp_path / "command.log"

    runner.run(
        [sys.executable, "-c", "print('token=abc123')"],
        log_path=log,
    )

    payload = log.read_text(encoding="utf-8")
    assert "abc123" not in payload
    assert "<redacted>" in payload


def test_subprocess_runner_reports_unknown_command():
    result = SubprocessRunner().run(["definitely-not-a-real-command"])

    assert not result.ok
    assert result.exit_code == 127


def test_subprocess_runner_require_raises_on_failure():
    runner = SubprocessRunner()

    try:
        runner.require([sys.executable, "-c", "raise SystemExit(3)"])
    except CommandError as exc:
        assert exc.result.exit_code == 3
    else:
        raise AssertionError("expected CommandError")


def test_redaction_covers_password_flags():
    assert redact("--adminpass=Certification1! --dbpass=database") == (
        "--adminpass=<redacted> --dbpass=<redacted>"
    )
