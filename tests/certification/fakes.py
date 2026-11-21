"""Test doubles for the certification harness."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.certification.artifacts import BuiltArtifact, safe_name
from tests.certification.models import (
    EnvironmentInfo,
    FeatureOutcome,
    ImportResult,
    ImportStatus,
    ReimportInfo,
)
from tests.certification.targets import FeatureCheck


def fake_artifact(
    case: Mapping[str, Any],
    target: str,
    workspace: Path,
) -> BuiltArtifact:
    case_id = str(case["id"])
    path = workspace / "fake-artifacts" / f"{safe_name(case_id)}-{target}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"{case_id}:{target}".encode())
    payload = path.read_bytes()
    return BuiltArtifact(
        case_id=case_id,
        target=target,
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _passed_reimport() -> ReimportInfo:
    return ReimportInfo(
        status=ImportStatus.PASSED,
        command=["fake-export"],
        exit_code=0,
        file_name="reimport.tar.gz",
        sha256="b" * 64,
        size_bytes=8,
    )


@dataclass
class FakeTarget:
    environment_info: EnvironmentInfo
    import_status: ImportStatus = ImportStatus.PASSED
    import_message: str | None = None
    import_command: list[str] = field(default_factory=lambda: ["fake-import"])
    reimport: ReimportInfo | None = field(default_factory=_passed_reimport)
    feature_outcomes: dict[str, FeatureCheck] = field(default_factory=dict)
    missing_verifiers: set[str] = field(default_factory=set)
    verified: list[str] = field(default_factory=list)
    imported: list[BuiltArtifact] = field(default_factory=list)
    closed: bool = False

    name = "fake"

    def environment(self) -> EnvironmentInfo:
        return self.environment_info

    def import_artifact(self, artifact: BuiltArtifact, work_dir: Path) -> ImportResult:
        self.imported.append(artifact)
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "import.log").write_text("fake import\n", encoding="utf-8")
        return ImportResult(
            status=self.import_status,
            command=self.import_command,
            exit_code=0 if self.import_status == ImportStatus.PASSED else 1,
            duration_seconds=0.01,
            log_file="import.log",
            message=self.import_message,
            reimport=self.reimport,
        )

    def verify_feature(
        self,
        feature: Mapping[str, Any],
        work_dir: Path,
    ) -> FeatureCheck:
        feature_id = str(feature["id"])
        if feature_id in self.missing_verifiers:
            raise NotImplementedError(feature_id)
        self.verified.append(feature_id)
        return self.feature_outcomes.get(
            feature_id,
            FeatureCheck(FeatureOutcome.VERIFIED),
        )

    def close(self) -> None:
        self.closed = True


def target_factory_for(
    environments: Mapping[str, EnvironmentInfo],
    **kwargs: Any,
):
    targets: list[FakeTarget] = []

    def factory(name: str) -> FakeTarget:
        target = FakeTarget(environment_info=environments[name], **kwargs)
        targets.append(target)
        return target

    return factory, targets
