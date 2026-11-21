"""Target-environment contract for certification imports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tests.certification.artifacts import BuiltArtifact
from tests.certification.models import EnvironmentInfo, FeatureOutcome, ImportResult


@dataclass(frozen=True)
class FeatureCheck:
    outcome: FeatureOutcome
    details: str | None = None


class CertificationUnavailable(RuntimeError):
    """Raised when a real LMS environment has not been provisioned yet."""


class CertificationTarget(Protocol):
    name: str

    def environment(self) -> EnvironmentInfo:
        """Return the concrete environment used for the import."""
        ...

    def import_artifact(self, artifact: BuiltArtifact, work_dir: Path) -> ImportResult:
        """Import the generated artifact and return the import outcome."""
        ...

    def verify_feature(self, feature: Mapping[str, Any], work_dir: Path) -> FeatureCheck:
        """Verify one native or transformed matrix feature after import."""
        ...

    def close(self) -> None:
        """Release any resources held by the target environment."""
        ...


TargetFactory = Callable[[str], CertificationTarget]


def unavailable_target(name: str) -> CertificationTarget:
    raise CertificationUnavailable(
        f"{name} certification environment is not available; use --dry-run until PR-08b"
    )
