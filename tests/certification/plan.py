"""Matrix-driven planning for LMS certification imports."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from tests.certification.models import EnvironmentInfo
from tests.golden.corpus import load_manifest, valid_cases
from tests.golden.matrix import load_matrix

IMPORT_TARGETS = {
    "moodle:restore": "moodle",
    "openedx:import": "openedx",
}
CERTIFICATION_IMPORT_CHECKS = frozenset(IMPORT_TARGETS)
CERTIFIABLE_FEATURE_STATUSES = frozenset({"native", "transformed", "placeholder"})


class PlanError(ValueError):
    """Raised when the matrix and golden corpus cannot produce a valid plan."""


@dataclass(frozen=True)
class PlannedImport:
    case: dict[str, Any]
    target: str
    environment: EnvironmentInfo
    features: tuple[dict[str, Any], ...]

    @property
    def case_id(self) -> str:
        return str(self.case["id"])

    @property
    def source(self) -> str:
        return str(self.case["source"])

    @property
    def feature_count(self) -> int:
        return len(self.features)


@dataclass(frozen=True)
class CertificationPlan:
    matrix_version: int
    imports: tuple[PlannedImport, ...]

    @property
    def feature_count(self) -> int:
        return sum(planned.feature_count for planned in self.imports)

    @property
    def case_ids(self) -> frozenset[str]:
        return frozenset(planned.case_id for planned in self.imports)

    @property
    def targets(self) -> frozenset[str]:
        return frozenset(planned.target for planned in self.imports)

    def select(
        self,
        *,
        targets: Collection[str] | None = None,
        case_ids: Collection[str] | None = None,
    ) -> CertificationPlan:
        selected = tuple(
            planned
            for planned in self.imports
            if (targets is None or planned.target in targets)
            and (case_ids is None or planned.case_id in case_ids)
        )
        if not selected:
            raise PlanError("No certification imports match the requested filters")
        return CertificationPlan(matrix_version=self.matrix_version, imports=selected)


def _environment(matrix: dict[str, Any], target: str) -> EnvironmentInfo:
    try:
        raw = matrix["certification_targets"][target]
    except KeyError as exc:
        raise PlanError(f"Missing certification target metadata for {target!r}") from exc

    components = {
        str(key): str(value) for key, value in raw.items() if key not in {"release", "patch"}
    }
    return EnvironmentInfo(
        target=target,
        release=str(raw["release"]),
        patch=str(raw["patch"]),
        components=components,
    )


def build_plan(
    matrix: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> CertificationPlan:
    """Map every import-checked feature to the artifact that proves it."""
    matrix_data = matrix or load_matrix()
    manifest_data = manifest or load_manifest()
    cases = {str(case["id"]): case for case in valid_cases(manifest_data)}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for feature in matrix_data["features"]:
        import_check = feature.get("import_check")
        target = IMPORT_TARGETS.get(str(import_check))
        if target is None:
            continue

        status = str(feature["status"])
        if status not in CERTIFIABLE_FEATURE_STATUSES:
            raise PlanError(f"Feature {feature['id']!r} has non-certifiable status {status!r}")

        case_id = str(feature["evidence"])
        case = cases.get(case_id)
        if case is None:
            raise PlanError(f"Feature {feature['id']!r} references unknown valid case {case_id!r}")
        if target not in case.get("targets", []):
            raise PlanError(
                f"Case {case_id!r} does not generate the {target!r} target "
                f"required by feature {feature['id']!r}"
            )

        grouped.setdefault((case_id, target), []).append(feature)

    if not grouped:
        raise PlanError("The format matrix has no LMS import features")

    environments = {target: _environment(matrix_data, target) for _, target in grouped}
    imports = tuple(
        PlannedImport(
            case=cases[case_id],
            target=target,
            environment=environments[target],
            features=tuple(sorted(features, key=lambda feature: str(feature["id"]))),
        )
        for (case_id, target), features in sorted(grouped.items())
    )
    return CertificationPlan(
        matrix_version=int(matrix_data["matrix_version"]),
        imports=imports,
    )
