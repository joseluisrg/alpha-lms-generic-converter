from __future__ import annotations

import pytest

from tests.certification.factory import build_target
from tests.certification.moodle import MoodleTarget
from tests.certification.openedx import OpenEdxTarget


def test_factory_returns_pinned_targets():
    moodle = build_target("moodle", run_id="test")
    openedx = build_target("openedx", run_id="test")

    assert isinstance(moodle, MoodleTarget)
    assert isinstance(openedx, OpenEdxTarget)
    assert moodle.environment().patch == "5.3.1"
    assert openedx.environment().patch == "Verawood.2"


def test_factory_rejects_unknown_target():
    with pytest.raises(ValueError, match="Unknown certification target"):
        build_target("canvas")
