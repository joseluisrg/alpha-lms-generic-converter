from __future__ import annotations

import copy

import pytest

from tests.certification.plan import PlanError, build_plan
from tests.golden.corpus import load_manifest
from tests.golden.matrix import load_matrix


def test_plan_maps_every_import_feature_to_its_case():
    plan = build_plan()
    by_target = {planned.target: planned for planned in plan.imports}

    assert plan.matrix_version == 1
    assert plan.feature_count == 57
    assert plan.targets == frozenset({"moodle", "openedx"})
    assert set(by_target) == {"moodle", "openedx"}
    assert by_target["moodle"].case_id == "openedx/core"
    assert by_target["openedx"].case_id == "moodle/core"

    for planned in plan.imports:
        expected_check = "moodle:restore" if planned.target == "moodle" else "openedx:import"
        assert planned.feature_count > 0
        assert all(feature["import_check"] == expected_check for feature in planned.features)
        assert planned.environment.target == planned.target


def test_plan_uses_pinned_environment_metadata():
    plan = build_plan()
    by_target = {planned.target: planned for planned in plan.imports}

    moodle = by_target["moodle"].environment
    assert moodle.release == "5.3 LTS"
    assert moodle.patch == "5.3.1"
    assert moodle.components == {"php": "8.4", "database": "MariaDB 11.4"}

    openedx = by_target["openedx"].environment
    assert openedx.release == "Verawood"
    assert openedx.patch == "Verawood.2"
    assert openedx.components == {"tutor": "22.0.4"}


def test_plan_selection_filters_targets_and_cases():
    plan = build_plan()

    assert plan.select(targets={"moodle"}).feature_count == 23
    assert plan.select(targets={"openedx"}).feature_count == 34
    assert plan.select(case_ids={"openedx/core"}).targets == frozenset({"moodle"})

    with pytest.raises(PlanError, match="No certification imports"):
        plan.select(targets={"unknown"})


def test_plan_rejects_unknown_feature_evidence():
    matrix = copy.deepcopy(load_matrix())
    matrix["features"][0]["evidence"] = "missing/case"

    with pytest.raises(PlanError, match="unknown valid case"):
        build_plan(matrix=matrix)


def test_plan_rejects_case_without_target_artifact():
    manifest = copy.deepcopy(load_manifest())
    case = next(item for item in manifest["cases"] if item["id"] == "openedx/core")
    case["targets"] = []

    with pytest.raises(PlanError, match="does not generate"):
        build_plan(manifest=manifest)


def test_plan_rejects_missing_target_metadata():
    matrix = copy.deepcopy(load_matrix())
    del matrix["certification_targets"]["moodle"]

    with pytest.raises(PlanError, match="Missing certification target metadata"):
        build_plan(matrix=matrix)
