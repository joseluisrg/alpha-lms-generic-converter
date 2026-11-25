import json
import tarfile
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from persistence.repositories import get_job


def test_missing_package_file(moodle_archive: Path, tmp_path: Path) -> None:
    missing_payload = f"files/aa/{'a' * 40}"
    package = tmp_path / "missing.mbz"
    with (
        tarfile.open(moodle_archive, "r:gz") as original,
        tarfile.open(package, "w:gz") as edited,
    ):
        assert original.getmember(missing_payload).isfile()
        for entry in original.getmembers():
            if entry.name == missing_payload:
                continue
            data = original.extractfile(entry)
            assert data is not None
            with data:
                edited.addfile(entry, data)

    report_path = tmp_path / "missing-file-preflight.json"
    args = [
        "inspect", str(package), "--validate-for", "openedx",
        "--preflight", "--output", str(report_path),
    ]
    run = CliRunner().invoke(app, args)
    assert run.exit_code == 0, run.output
    report = json.loads(report_path.read_text(encoding="utf-8"))

    job = get_job(report["job_id"])
    assert job is not None
    assets = json.loads(job["course_json"])["assets"]
    asset = next(asset for asset in assets if asset["path"] == missing_payload)

    assert report["schema_version"] == 1
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["finding_id"]
    assert finding["code"] == "MOODLE_PACKAGE_FILE_MISSING"
    assert finding["severity"] == "warning"
    assert finding["asset_id"] == asset["asset_id"]
    assert finding["status"] == "missing"
    assert finding["recommendation"] == (
        "Check the file in Moodle and create a new backup that includes it."
    )
