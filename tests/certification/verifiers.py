"""Feature-level checks over original and re-imported LMS artifacts."""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Callable
from pathlib import Path

from domain.enums import NodeType
from tests.certification.evidence import Evidence
from tests.certification.models import FeatureOutcome
from tests.certification.targets import FeatureCheck

Verifier = Callable[[Evidence, Evidence], FeatureCheck | None]


class VerificationError(AssertionError):
    """Raised when a feature check fails."""


def verify_feature(feature_id: str, original: Evidence, reimport: Evidence) -> FeatureCheck:
    """Run the verifier registered for a feature, failing closed when absent."""
    verifier = VERIFIERS.get(feature_id)
    if verifier is None:
        raise NotImplementedError(f"No certification verifier for {feature_id}")
    result = verifier(original, reimport)
    return result or FeatureCheck(FeatureOutcome.VERIFIED)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _count_at_least(original: Evidence, reimport: Evidence, node_type: NodeType) -> None:
    expected = original.node_counts[node_type.value]
    actual = reimport.node_counts[node_type.value]
    _require(
        expected > 0 and actual >= expected,
        f"expected at least {expected} {node_type.value} node(s), found {actual}",
    )


def _questions_at_least(original: Evidence, reimport: Evidence, question_type: str) -> None:
    expected = original.question_counts[question_type]
    actual = reimport.question_counts[question_type]
    _require(
        expected > 0 and actual >= expected,
        f"expected at least {expected} {question_type} question(s), found {actual}",
    )


def _all_questions_at_least(original: Evidence, reimport: Evidence) -> None:
    expected = sum(original.question_counts.values())
    actual = sum(reimport.question_counts.values())
    _require(
        expected > 0 and actual >= expected,
        f"expected at least {expected} question(s), found {actual}",
    )


def _same_bytes(name: str, original: Evidence, reimport: Evidence) -> None:
    expected = original.moodle_file_bytes(name)
    actual = reimport.moodle_file_bytes(name)
    _require(expected is not None, f"original Moodle backup is missing file {name!r}")
    _require(actual is not None, f"re-imported Moodle backup is missing file {name!r}")
    _require(expected == actual, f"re-imported Moodle file {name!r} differs from the original")


def _openedx_asset_bytes(name: str, original: Evidence, reimport: Evidence) -> None:
    expected_path = original.openedx_static_file(name)
    actual_path = reimport.openedx_static_file(name)
    _require(expected_path is not None, f"original Open edX export is missing static/{name}")
    _require(actual_path is not None, f"re-imported Open edX export is missing static/{name}")
    if expected_path is None or actual_path is None:
        raise VerificationError(f"Open edX static/{name} is missing")
    _require(
        _sha256(expected_path) == _sha256(actual_path),
        f"re-imported Open edX asset static/{name} differs from the original",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preserve_module_counts(original: Evidence, reimport: Evidence) -> None:
    expected_sections = (
        len(original.moodle_manifest.get("sections", [])) if original.moodle_manifest else 0
    )
    actual_sections = (
        len(reimport.moodle_manifest.get("sections", [])) if reimport.moodle_manifest else 0
    )
    _require(
        expected_sections > 0 and actual_sections >= expected_sections,
        f"expected at least {expected_sections} Moodle section(s), found {actual_sections}",
    )

    expected_activities = (
        len(original.moodle_manifest.get("activities", {})) if original.moodle_manifest else 0
    )
    actual_activities = (
        len(reimport.moodle_manifest.get("activities", {})) if reimport.moodle_manifest else 0
    )
    _require(
        expected_activities > 0 and actual_activities >= expected_activities,
        f"expected at least {expected_activities} Moodle activit(ies), found {actual_activities}",
    )

    for module, expected in original.moodle_activity_modules.items():
        if not expected:
            continue
        actual = reimport.moodle_activity_modules[module]
        _require(
            actual >= expected,
            f"expected at least {expected} {module!r} module(s), found {actual}",
        )


def _moodle_assets(original: Evidence, reimport: Evidence) -> None:
    names = set(original.moodle_files_by_name)
    _require(bool(names), "original Moodle backup contains no assets")
    missing = sorted(name for name in names if name not in reimport.moodle_files_by_name)
    _require(not missing, f"re-imported Moodle backup is missing assets: {', '.join(missing)}")
    for name in sorted(names):
        _same_bytes(name, original, reimport)


def _moodle_questions(original: Evidence, reimport: Evidence) -> None:
    _all_questions_at_least(original, reimport)
    for question_type, expected in original.question_counts.items():
        if not expected:
            continue
        actual = reimport.question_counts[question_type]
        _require(
            actual >= expected,
            f"expected at least {expected} {question_type} question(s), found {actual}",
        )


def _moodle_html(original: Evidence, reimport: Evidence) -> None:
    _count_at_least(original, reimport, NodeType.HTML)
    expected_titles = original.node_titles(NodeType.HTML)
    actual_titles = reimport.node_titles(NodeType.HTML)
    missing = sorted(expected_titles - actual_titles)
    _require(not missing, f"re-imported Moodle backup lost HTML title(s): {', '.join(missing)}")


def _moodle_video(original: Evidence, reimport: Evidence) -> None:
    _count_at_least(original, reimport, NodeType.VIDEO)
    expected_names = {name for name in original.asset_names if _is_video_name(name)}
    _require(bool(expected_names), "original Moodle backup contains no video assets")
    for name in sorted(expected_names):
        _same_bytes(name, original, reimport)


def _is_video_name(name: str) -> bool:
    return Path(name).suffix.lower() in {".mp4", ".webm", ".ogg", ".mov", ".avi"}


def _moodle_scorm(original: Evidence, reimport: Evidence) -> None:
    _count_at_least(original, reimport, NodeType.SCORM)
    _require(
        "package.zip" in original.moodle_files_by_name,
        "original Moodle backup has no package.zip",
    )
    _require(
        "package.zip" in reimport.moodle_files_by_name,
        "re-imported Moodle backup has no package.zip",
    )
    _same_bytes("package.zip", original, reimport)


def _openedx_components(original: Evidence, reimport: Evidence) -> None:
    for node_type in (
        NodeType.CHAPTER,
        NodeType.SEQUENTIAL,
        NodeType.VERTICAL,
        NodeType.HTML,
        NodeType.VIDEO,
        NodeType.PROBLEM,
    ):
        _count_at_least(original, reimport, node_type)


def _openedx_assets(original: Evidence, reimport: Evidence) -> None:
    expected = set(original.openedx_static or {})
    actual = set(reimport.openedx_static or {})
    _require(bool(expected), "original Open edX export contains no static assets")
    missing = sorted(expected - actual)
    _require(not missing, f"re-imported Open edX export is missing assets: {', '.join(missing)}")
    for name in sorted(expected):
        _openedx_asset_bytes(name, original, reimport)


def _openedx_questions(original: Evidence, reimport: Evidence) -> None:
    _all_questions_at_least(original, reimport)
    for question_type, expected in original.question_counts.items():
        if not expected:
            continue
        actual = reimport.question_counts[question_type]
        _require(
            actual >= expected,
            f"expected at least {expected} {question_type} question(s), found {actual}",
        )


def _openedx_video(original: Evidence, reimport: Evidence) -> None:
    _count_at_least(original, reimport, NodeType.VIDEO)
    expected = {name for name in original.asset_names if _is_video_name(name)}
    _require(bool(expected), "original Open edX export contains no video assets")
    for name in sorted(expected):
        _openedx_asset_bytes(name, original, reimport)


def _openedx_hierarchy(original: Evidence, reimport: Evidence) -> None:
    for node_type in (NodeType.CHAPTER, NodeType.SEQUENTIAL, NodeType.VERTICAL):
        _count_at_least(original, reimport, node_type)


def _openedx_package_asset(original: Evidence, reimport: Evidence) -> None:
    _require(bool(original.openedx_scorm), "original Open edX export has no scorm/package.zip")
    _require(bool(reimport.openedx_scorm), "re-imported Open edX export has no scorm/package.zip")
    expected_path = original.openedx_package_file()
    actual_path = reimport.openedx_package_file()
    _require(expected_path is not None, "original Open edX export has no package.zip")
    _require(actual_path is not None, "re-imported Open edX export has no package.zip")
    if expected_path is None or actual_path is None:
        raise VerificationError("Open edX SCORM package is missing")
    expected = _zip_contents(expected_path)
    actual = _zip_contents(actual_path)
    _require(
        set(expected) == set(actual),
        "re-imported Open edX SCORM package manifest differs from the original",
    )
    for name in sorted(expected):
        _require(
            expected[name] == actual[name],
            f"re-imported Open edX SCORM package member {name!r} differs from the original",
        )


def _zip_contents(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {
            info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()
        }


def _openedx_tolerance(original: Evidence, reimport: Evidence) -> None:
    values = {
        str(question.metadata["tolerance"])
        for question in original.course.questions
        if question.question_type == "numerical" and question.metadata.get("tolerance") is not None
    }
    _require(bool(values), "original Open edX export contains no numerical tolerance")
    for value in values:
        _require(
            reimport.has_numerical_tolerance(value),
            f"re-imported Open edX export lost numerical tolerance {value}",
        )


VERIFIERS: dict[str, Verifier] = {
    "openedx.assets.nested": lambda original, reimport: _nested_asset(original, reimport),
    "openedx.discussion": lambda original, reimport: _count_at_least(
        original, reimport, NodeType.FORUM
    ),
    "openedx.hierarchy": _openedx_hierarchy,
    "openedx.html": _moodle_html,
    "openedx.problem.legacy_numericalinput": lambda original, reimport: _questions_at_least(
        original, reimport, "numerical"
    ),
    "openedx.problem.legacy_textinput": lambda original, reimport: _questions_at_least(
        original, reimport, "shortanswer"
    ),
    "openedx.problem.multichoice": lambda original, reimport: _questions_at_least(
        original, reimport, "multichoice"
    ),
    "openedx.problem.multiselect": lambda original, reimport: _questions_at_least(
        original, reimport, "multiselect"
    ),
    "openedx.problem.numerical": lambda original, reimport: _questions_at_least(
        original, reimport, "numerical"
    ),
    "openedx.problem.shortanswer": lambda original, reimport: _questions_at_least(
        original, reimport, "shortanswer"
    ),
    "openedx.problem.truefalse": lambda original, reimport: _questions_at_least(
        original, reimport, "truefalse"
    ),
    "openedx.scorm": _moodle_scorm,
    "openedx.video.asset": _moodle_video,
    "openedx.video.youtube": lambda original, reimport: _count_at_least(
        original, reimport, NodeType.VIDEO
    ),
    "moodle.book": lambda original, reimport: _count_at_least(original, reimport, NodeType.HTML),
    "moodle.forum": lambda original, reimport: _count_at_least(original, reimport, NodeType.FORUM),
    "moodle.hierarchy": _openedx_hierarchy,
    "moodle.label.html": _moodle_html,
    "moodle.label.youtube": lambda original, reimport: _count_at_least(
        original, reimport, NodeType.VIDEO
    ),
    "moodle.page": _moodle_html,
    "moodle.question.multichoice_multi": lambda original, reimport: _questions_at_least(
        original, reimport, "multiselect"
    ),
    "moodle.question.multichoice_single": lambda original, reimport: _questions_at_least(
        original, reimport, "multichoice"
    ),
    "moodle.question.numerical_tolerance": _openedx_tolerance,
    "moodle.question.shortanswer": lambda original, reimport: _questions_at_least(
        original, reimport, "shortanswer"
    ),
    "moodle.question.truefalse": lambda original, reimport: _questions_at_least(
        original, reimport, "truefalse"
    ),
    "moodle.question_bank_link": _openedx_questions,
    "moodle.quiz": lambda original, reimport: _count_at_least(original, reimport, NodeType.PROBLEM),
    "moodle.resource.file": lambda original, reimport: _openedx_asset_bytes(
        "handout.pdf", original, reimport
    ),
    "moodle.resource.video": _openedx_video,
    "moodle.scorm": lambda original, reimport: _openedx_scorm(original, reimport),
    "moodle.url.external": lambda original, reimport: _require_text(
        original, reimport, "https://example.org/resource"
    ),
    "moodle.url.youtube": lambda original, reimport: _count_at_least(
        original, reimport, NodeType.VIDEO
    ),
    "moodle.video": _openedx_video,
    "target.moodle.assets": _moodle_assets,
    "target.moodle.modules": _preserve_module_counts,
    "target.moodle.questions": _moodle_questions,
    "target.openedx.assets": _openedx_assets,
    "target.openedx.components": _openedx_components,
    "target.openedx.questions": _openedx_questions,
}


def _nested_asset(original: Evidence, reimport: Evidence) -> None:
    _require(
        "diagram.png" in original.moodle_files_by_name,
        "original Moodle backup has no diagram.png",
    )
    _require(
        "diagram.png" in reimport.moodle_files_by_name,
        "re-imported Moodle backup has no diagram.png",
    )
    _same_bytes("diagram.png", original, reimport)


def _openedx_scorm(original: Evidence, reimport: Evidence) -> None:
    _count_at_least(original, reimport, NodeType.SCORM)
    _openedx_package_asset(original, reimport)


def _require_text(original: Evidence, reimport: Evidence, text: str) -> None:
    _require(original.has_html(text), f"original artifact does not contain {text!r}")
    _require(reimport.has_html(text), f"re-imported artifact does not contain {text!r}")
