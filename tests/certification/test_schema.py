from __future__ import annotations

import json
from pathlib import Path

from tests.certification.models import CertificationReport

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "certification" / "result-schema.json"
)


def test_result_schema_matches_committed_fixture():
    expected = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert CertificationReport.model_json_schema() == expected
