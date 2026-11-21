"""Subprocess execution helpers for real LMS certification targets."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tests.certification.redaction import redact


@dataclass(frozen=True)
class CommandResult:
    """Captured result of one external command."""

    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    log_file: str | None = None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part).strip()


class CommandError(RuntimeError):
    """Raised when a required command fails."""

    def __init__(self, result: CommandResult, message: str | None = None) -> None:
        super().__init__(message or f"Command failed with exit code {result.exit_code}")
        self.result = result


class CommandRunner(Protocol):
    """Executable abstraction used by target environments and tests."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 600,
        log_path: Path | None = None,
    ) -> CommandResult:
        """Run a command and capture its output."""
        ...


class SubprocessRunner:
    """Run commands without a shell, with timeout and log capture."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 600,
        log_path: Path | None = None,
    ) -> CommandResult:
        argv = tuple(str(argument) for argument in command)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cwd) if cwd else None,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = 124
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr) + f"\nCommand timed out after {timeout:g}s."
        except OSError as exc:
            exit_code = 127
            stdout = ""
            stderr = f"{type(exc).__name__}: {exc}"

        duration = round(time.monotonic() - started, 3)
        log_name: str | None = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                _log_text(argv, exit_code, stdout, stderr),
                encoding="utf-8",
            )
            log_name = log_path.name

        return CommandResult(
            command=argv,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            log_file=log_name,
            timed_out=timed_out,
        )

    def require(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 600,
        log_path: Path | None = None,
        message: str | None = None,
    ) -> CommandResult:
        result = self.run(
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            log_path=log_path,
        )
        if not result.ok:
            raise CommandError(result, message)
        return result


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _log_text(
    command: Sequence[str],
    exit_code: int,
    stdout: str,
    stderr: str,
) -> str:
    rendered = " ".join(redact(argument) for argument in command)
    sections = [f"$ {rendered}", f"exit_code={exit_code}"]
    if stdout:
        sections.extend(("", "stdout:", redact(stdout)))
    if stderr:
        sections.extend(("", "stderr:", redact(stderr)))
    return "\n".join(sections) + "\n"
