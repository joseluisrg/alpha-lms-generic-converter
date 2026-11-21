from __future__ import annotations

from tests.golden.corpus import load_manifest
from tests.golden.features import SUPPORTED_FEATURES


def test_manifest_covers_every_supported_feature():
    manifest = load_manifest()
    declared: set[str] = set()
    for case in manifest["cases"]:
        declared.update(case.get("features", []))

    assert declared == set(SUPPORTED_FEATURES)


def test_manifest_case_ids_are_unique():
    manifest = load_manifest()
    ids = [case["id"] for case in manifest["cases"]]

    assert len(ids) == len(set(ids))
