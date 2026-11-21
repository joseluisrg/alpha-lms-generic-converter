from __future__ import annotations

from pathlib import Path

from tests.certification.cli import main
from tests.certification.targets import unavailable_target


def test_dry_run_prints_the_full_plan(capsys):
    assert main(["--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "2 imports, 57 features, matrix v1" in output
    assert "openedx/core -> moodle" in output
    assert "moodle/core -> openedx" in output


def test_dry_run_filters_to_one_target(capsys):
    assert main(["--dry-run", "--target", "moodle"]) == 0

    output = capsys.readouterr().out
    assert "1 import, 23 features" in output
    assert "openedx/core -> moodle" in output
    assert "moodle/core -> openedx" not in output


def test_dry_run_rejects_unknown_case(capsys):
    assert main(["--dry-run", "--case", "missing/case"]) == 2

    assert "Unknown case id" in capsys.readouterr().err


def test_non_dry_run_reports_unavailable_target(tmp_path: Path, capsys):
    output = tmp_path / "report.json"

    assert (
        main(
            ["--workspace", str(tmp_path / "work"), "--output", str(output)],
            target_factory=unavailable_target,
        )
        == 2
    )

    assert "not available" in capsys.readouterr().err
    assert not output.exists()
