"""Construct real LMS certification targets."""

from __future__ import annotations

from tests.certification.moodle import MoodleTarget
from tests.certification.openedx import OpenEdxTarget
from tests.certification.targets import CertificationTarget


def build_target(name: str, *, run_id: str = "local") -> CertificationTarget:
    """Return the real target for a requested LMS."""
    if name == "moodle":
        return MoodleTarget(run_id=run_id)
    if name == "openedx":
        return OpenEdxTarget(run_id=run_id)
    raise ValueError(f"Unknown certification target: {name!r}")
