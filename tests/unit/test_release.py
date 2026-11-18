import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _load_release_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_release", ROOT / "scripts" / "check_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _load_release_module()


def _write_project(root: Path, version: str = "0.1.0") -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "lms-converter"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## Unreleased\n\n"
        "### Added\n\n"
        "- Next change.\n\n"
        f"## [{version}] - 2026-11-18\n\n"
        "### Added\n\n"
        "- Released change.\n",
        encoding="utf-8",
    )


def test_project_version_reads_pyproject(tmp_path: Path):
    _write_project(tmp_path, version="1.2.3")

    assert release.project_version(tmp_path) == "1.2.3"


def test_changelog_section_stops_at_next_heading(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.0.0] - 2026-01-01\n\n- Included.\n\n## [0.9.0] - 2025-12-01\n\n- Excluded.\n",
        encoding="utf-8",
    )

    section = release.changelog_section(changelog, "1.0.0")

    assert section == "- Included."
    assert "Excluded" not in section


def test_changelog_section_missing_returns_none(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## Unreleased\n\n- Pending.\n", encoding="utf-8")

    assert release.changelog_section(changelog, "1.0.0") is None


def test_has_unreleased(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## Unreleased\n", encoding="utf-8")
    assert release.has_unreleased(changelog) is True

    changelog.write_text("## [1.0.0] - 2026-01-01\n", encoding="utf-8")
    assert release.has_unreleased(changelog) is False


def test_main_accepts_matching_tag_and_writes_notes(tmp_path: Path, capsys):
    _write_project(tmp_path)
    notes = tmp_path / "notes.md"

    code = release.main(
        [
            "--project-root",
            str(tmp_path),
            "--tag",
            "v0.1.0",
            "--notes-out",
            str(notes),
        ]
    )

    assert code == 0
    assert "Released change." in notes.read_text(encoding="utf-8")
    assert "release metadata OK: 0.1.0" in capsys.readouterr().out


def test_main_rejects_mismatched_tag(tmp_path: Path, capsys):
    _write_project(tmp_path)

    code = release.main(["--project-root", str(tmp_path), "--tag", "v0.2.0"])

    assert code == 1
    assert "does not match" in capsys.readouterr().err


def test_main_requires_unreleased_section(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "lms-converter"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.0] - 2026-11-18\n\n- Released change.\n", encoding="utf-8"
    )

    code = release.main(["--project-root", str(tmp_path), "--tag", "v0.1.0"])

    assert code == 1
    assert "Unreleased" in capsys.readouterr().err
