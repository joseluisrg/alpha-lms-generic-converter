"""Open edX Verawood certification target backed by Tutor."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.xml_utils import parse_xml_file
from tests.certification.artifacts import BuiltArtifact
from tests.certification.evidence import Evidence, load_evidence, sha256_file
from tests.certification.models import (
    EnvironmentInfo,
    ImportResult,
    ImportStatus,
    ReimportInfo,
)
from tests.certification.runtime import CommandError, CommandResult, CommandRunner, SubprocessRunner
from tests.certification.targets import CertificationUnavailable, FeatureCheck
from tests.certification.verifiers import verify_feature
from tests.golden.corpus import deterministic_tar_gz, extract_tar

OPENEDX_RELEASE = "Verawood"
OPENEDX_PATCH = "Verawood.2"
TUTOR_VERSION = "22.0.4"
OPENEDX_COMPONENTS = {
    "tutor": TUTOR_VERSION,
    "release": OPENEDX_PATCH,
}
REMOTE_IMPORT_DIR = "/tmp/certification-import"
REMOTE_EXPORT_DIR = "/tmp/certification-reimport"
CMS_COMMAND = ["local", "exec", "cms", "./manage.py", "cms"]


class OpenEdxTarget:
    """Import a generated OLX archive into a disposable Tutor instance."""

    name = "openedx"

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        run_id: str = "local",
        tutor: str | None = None,
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self.tutor = tutor or "tutor"
        self.run_id = run_id
        self._started = False
        self._artifact: BuiltArtifact | None = None
        self._reimport_path: Path | None = None
        self._reimport_info: ReimportInfo | None = None
        self._original_evidence: Evidence | None = None
        self._reimport_evidence: Evidence | None = None
        self._logs: list[tuple[str, Path]] = []
        self._last_command: list[str] = []
        self._import_command: list[str] = []
        self._import_exit_code: int | None = None
        self._cms_container: str | None = None

    def environment(self) -> EnvironmentInfo:
        return EnvironmentInfo(
            target=self.name,
            release=OPENEDX_RELEASE,
            patch=OPENEDX_PATCH,
            components=dict(OPENEDX_COMPONENTS),
        )

    def import_artifact(self, artifact: BuiltArtifact, work_dir: Path) -> ImportResult:
        self._artifact = artifact
        self._reimport_path = None
        self._reimport_info = None
        work_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()

        try:
            self._ensure_started(work_dir)
            self._cms_container = self._container_id(work_dir)
            source_dir = self._prepare_source(artifact, work_dir)
            course_key = self._course_key(source_dir)
            self._copy_to_cms(source_dir, work_dir)
            self._run_tutor(
                [*CMS_COMMAND, "xlint", REMOTE_IMPORT_DIR, "course"],
                work_dir,
                "xlint.log",
                timeout=900,
            )
            import_result = self._run_tutor(
                [*CMS_COMMAND, "import", REMOTE_IMPORT_DIR, "course"],
                work_dir,
                "import.log",
                timeout=1800,
            )
            self._import_command = list(import_result.command)
            self._import_exit_code = import_result.exit_code
            self._export_reimport(course_key, work_dir)
        except CertificationUnavailable:
            raise
        except CommandError as exc:
            return self._failure(exc, work_dir, started)
        except Exception as exc:
            return ImportResult(
                status=ImportStatus.ERROR,
                message=f"{type(exc).__name__}: {exc}",
                log_file=self._combined_log(work_dir),
            )

        elapsed = round(time.monotonic() - started, 3)
        return ImportResult(
            status=ImportStatus.PASSED,
            command=self._import_command,
            exit_code=self._import_exit_code,
            duration_seconds=elapsed,
            log_file=self._combined_log(work_dir),
            message=f"Open edX {OPENEDX_PATCH} imported and re-exported {course_key}.",
            reimport=self._reimport_info,
        )

    def verify_feature(self, feature: Mapping[str, Any], work_dir: Path) -> FeatureCheck:
        if self._artifact is None or self._reimport_path is None:
            raise CertificationUnavailable("Open edX import evidence is not available")
        if self._original_evidence is None:
            self._original_evidence = load_evidence(
                self._artifact.path,
                "openedx",
                work_dir / "verify-original",
            )
        if self._reimport_evidence is None:
            self._reimport_evidence = load_evidence(
                self._reimport_path,
                "openedx",
                work_dir / "verify-reimport",
            )
        return verify_feature(
            str(feature["id"]),
            self._original_evidence,
            self._reimport_evidence,
        )

    def close(self) -> None:
        if not self._started:
            return
        self._started = False
        result = self.runner.run(
            [self.tutor, "local", "down", "--volumes"],
            timeout=300,
        )
        if result.exit_code != 0:
            return

    def _ensure_started(self, work_dir: Path) -> None:
        if self._started:
            return
        if shutil.which(self.tutor) is None and self.tutor == "tutor":
            raise CertificationUnavailable(
                "Open edX certification environment is not available: tutor is not installed"
            )

        docker = self.runner.run(
            ["docker", "info"],
            timeout=30,
            log_path=work_dir / "logs" / "docker-info.log",
        )
        if not docker.ok:
            raise CertificationUnavailable(
                "Open edX certification environment is not available: Docker is unavailable"
            )

        self._run_tutor(
            ["plugins", "enable", "forum"],
            work_dir,
            "forum-plugin.log",
            timeout=300,
            required=False,
        )
        self._run_tutor(
            ["config", "save", "--set", "RUN_SMTP=false"],
            work_dir,
            "config.log",
            timeout=120,
        )
        self._started = True
        self._run_tutor(
            ["local", "launch", "--non-interactive", "--pullimages"],
            work_dir,
            "launch.log",
            timeout=3600,
        )

    def _container_id(self, work_dir: Path) -> str:
        result = self._run_tutor(
            ["local", "dc", "ps", "-q", "cms"],
            work_dir,
            "cms-container.log",
            timeout=120,
        )
        container = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if not container:
            raise RuntimeError("Tutor did not expose a CMS container")
        return container

    def _prepare_source(self, artifact: BuiltArtifact, work_dir: Path) -> Path:
        root = work_dir / "import-root"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        extract_tar(artifact.path, root / "course")
        return root

    def _course_key(self, source_dir: Path) -> str:
        root = parse_xml_file(source_dir / "course" / "course.xml")
        org = root.attrib.get("org")
        course = root.attrib.get("course")
        url_name = root.attrib.get("url_name")
        if not org or not course or not url_name:
            raise RuntimeError("Generated Open edX course.xml is missing org/course/url_name")
        return f"course-v1:{org}+{course}+{url_name}"

    def _copy_to_cms(self, source_dir: Path, work_dir: Path) -> None:
        if self._cms_container is None:
            raise RuntimeError("CMS container is not available")
        self._run(
            ["docker", "exec", self._cms_container, "rm", "-rf", REMOTE_IMPORT_DIR],
            work_dir,
            "cleanup-import.log",
            required=False,
        )
        self._run(
            ["docker", "exec", self._cms_container, "mkdir", "-p", REMOTE_IMPORT_DIR],
            work_dir,
            "prepare-import.log",
            timeout=60,
        )
        self._run(
            [
                "docker",
                "cp",
                f"{source_dir}/.",
                f"{self._cms_container}:{REMOTE_IMPORT_DIR}",
            ],
            work_dir,
            "copy-import.log",
            timeout=300,
        )

    def _export_reimport(self, course_key: str, work_dir: Path) -> None:
        if self._cms_container is None:
            raise RuntimeError("CMS container is not available")
        self._run(
            ["docker", "exec", self._cms_container, "rm", "-rf", REMOTE_EXPORT_DIR],
            work_dir,
            "cleanup-reimport.log",
            required=False,
        )
        self._run(
            ["docker", "exec", self._cms_container, "mkdir", "-p", REMOTE_EXPORT_DIR],
            work_dir,
            "prepare-reimport.log",
            timeout=60,
        )
        export_result = self._run_tutor(
            [*CMS_COMMAND, "export", course_key, REMOTE_EXPORT_DIR],
            work_dir,
            "export.log",
            timeout=1800,
        )
        host_dir = work_dir / "reimport"
        if host_dir.exists():
            shutil.rmtree(host_dir)
        host_dir.mkdir(parents=True)
        self._run(
            [
                "docker",
                "cp",
                f"{self._cms_container}:{REMOTE_EXPORT_DIR}/.",
                str(host_dir),
            ],
            work_dir,
            "copy-reimport.log",
            timeout=300,
        )
        destination = work_dir / "reimport.tar.gz"
        deterministic_tar_gz(host_dir, destination)
        self._reimport_path = destination
        self._reimport_info = ReimportInfo(
            status=ImportStatus.PASSED,
            command=list(export_result.command),
            exit_code=export_result.exit_code,
            duration_seconds=export_result.duration_seconds,
            file_name=destination.name,
            sha256=sha256_file(destination),
            size_bytes=destination.stat().st_size,
            log_file=export_result.log_file,
        )

    def _run_tutor(
        self,
        arguments: list[str],
        work_dir: Path,
        log_name: str,
        *,
        timeout: float = 600,
        required: bool = True,
    ) -> CommandResult:
        return self._run(
            [self.tutor, *arguments],
            work_dir,
            log_name,
            timeout=timeout,
            required=required,
        )

    def _run(
        self,
        command: list[str],
        work_dir: Path,
        log_name: str,
        *,
        timeout: float = 600,
        required: bool = True,
    ) -> CommandResult:
        log_path = work_dir / "logs" / log_name
        result = self.runner.run(
            command,
            env=os.environ.copy(),
            timeout=timeout,
            log_path=log_path,
        )
        self._last_command = list(result.command)
        self._logs.append((log_name, log_path))
        if required and not result.ok:
            raise CommandError(result, result.stderr.strip() or result.stdout.strip())
        return result

    def _combined_log(self, work_dir: Path) -> str | None:
        if not self._logs:
            return None
        target = work_dir / "import.log"
        sections: list[str] = []
        for name, path in self._logs:
            if not path.is_file():
                continue
            sections.append(f"===== {name} =====")
            sections.append(path.read_text(encoding="utf-8", errors="replace").rstrip())
        if not sections:
            return None
        target.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
        return target.name

    def _failure(self, exc: CommandError, work_dir: Path, started: float) -> ImportResult:
        result = exc.result
        message = result.output or str(exc)
        return ImportResult(
            status=ImportStatus.FAILED,
            command=list(result.command),
            exit_code=result.exit_code,
            duration_seconds=round(time.monotonic() - started, 3),
            log_file=self._combined_log(work_dir),
            message=message[-4000:] if message else str(exc),
        )
