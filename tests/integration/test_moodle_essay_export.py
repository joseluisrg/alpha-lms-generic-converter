import json
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adapters.openedx.target_adapter import OpenEdxTargetAdapter
from cli.main import app
from core.parse import ParseService
from core.transform import TransformService
from core.validate import ValidationService
from persistence.repositories import get_job_events


@pytest.fixture
def moodle_essay_archive(
    moodle_archive: Path, tmp_path: Path, request: pytest.FixtureRequest
) -> Path:
    course_dir = tmp_path / "src"
    with tarfile.open(moodle_archive, "r:gz") as archive:
        archive.extractall(course_dir, filter="data")

    quiz_path = course_dir / "activities" / "quiz_3" / "quiz.xml"
    quiz = ET.parse(quiz_path)
    instances = quiz.find("question_instances")
    assert instances is not None
    instances.clear()
    for question_id in ("101", "105"):
        instance = ET.SubElement(instances, "question_instance")
        ET.SubElement(instance, "questionid").text = question_id
    quiz.write(quiz_path, encoding="utf-8")

    bank_path = course_dir / "questions.xml"
    bank = ET.parse(bank_path)
    questions = bank.find(".//questions")
    assert questions is not None
    multichoice = questions.find("question[@id='101']")
    assert multichoice is not None
    essay = ET.fromstring(
        """<question id="105">
            <name>Essay</name>
            <questiontext>Explain your answer.</questiontext>
            <defaultmark>1</defaultmark>
            <qtype>essay</qtype>
        </question>"""
    )
    questions[:] = [multichoice, essay]
    bank.write(bank_path, encoding="utf-8")

    package = tmp_path / "essay.mbz"
    omitted_file = None
    if getattr(request, "param", None) == "missing-pdf":
        omitted_file = course_dir / "files" / "aa" / ("a" * 40)
        assert omitted_file.is_file()
        package = tmp_path / "preflight-demo.mbz"

    with tarfile.open(package, "w:gz") as archive:
        for path in sorted(course_dir.rglob("*")):
            if path.is_file() and path != omitted_file:
                archive.add(path, arcname=path.relative_to(course_dir).as_posix())
    return package


def test_essay_export(moodle_essay_archive: Path, tmp_path: Path) -> None:
    parsed = ParseService().parse(
        str(moodle_essay_archive), "moodle", str(tmp_path / "extract")
    )
    course = TransformService().transform(parsed, "moodle", "job-essay")
    assert [question.question_type for question in course.questions] == [
        "multichoice",
        "essay",
    ]

    notes = ValidationService().validate(course, target="openedx")
    assert sum(note.code == "ESSAY_QUESTION" for note in notes) == 1

    output = OpenEdxTargetAdapter(work_dir=tmp_path / "build").generate_export(
        course, str(tmp_path / "out.tar.gz"), parsed["extracted_path"]
    )
    export_dir = tmp_path / "olx"
    with tarfile.open(output, "r:gz") as archive:
        archive.extractall(export_dir, filter="data")

    problem_paths = list((export_dir / "problem").glob("*.xml"))
    assert len(problem_paths) == 1
    problem = ET.parse(problem_paths[0]).getroot()
    multichoice, essay = problem.findall("multiplechoiceresponse")

    correct_choices = multichoice.findall("choicegroup/choice[@correct='true']")
    assert [choice.text for choice in correct_choices] == ["A"]
    assert essay.findtext("label", "").startswith("essay:")
    review_choices = essay.findall("choicegroup/choice")
    assert [(choice.text, choice.get("correct")) for choice in review_choices] == [
        ("Review required", "false"),
    ]

def test_essay_preflight(moodle_essay_archive: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    args = ["inspect", str(moodle_essay_archive), "--validate-for", "openedx"]

    standard_path = tmp_path / "inspect.json"
    standard_run = runner.invoke(app, [*args, "--output", str(standard_path)])
    assert standard_run.exit_code == 0, standard_run.output
    standard = json.loads(standard_path.read_text(encoding="utf-8"))
    assert "parsed" in standard
    assert "findings" not in standard
    assert any(note["code"] == "ESSAY_QUESTION" for note in standard["report"])
    essay = next(
        question
        for question in standard["course"]["questions"]
        if question["question_type"] == "essay"
    )

    report_path = tmp_path / "preflight.json"
    preflight_args = [*args, "--preflight", "--output", str(report_path)]
    run = runner.invoke(app, preflight_args)
    assert run.exit_code == 0, run.output
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert set(report) == {
        "schema_version", "source", "target", "job_id",
        "validation_error_codes", "findings",
    }
    assert report["schema_version"] == 1
    assert report["source"] == "moodle"
    assert report["target"] == "openedx"
    assert report["validation_error_codes"] == []
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["finding_id"]
    assert finding == {
        "finding_id": finding["finding_id"],
        "code": "OPENEDX_ESSAY_PLACEHOLDER",
        "severity": "warning",
        "question_id": essay["question_id"],
        "status": "placeholder",
        "recommendation": "Recreate the essay question in Open edX and verify its grading.",
    }

    events = get_job_events(report["job_id"])
    assert [event["event"] for event in events] == ["inspected"]

    repeat = runner.invoke(app, preflight_args)
    assert repeat.exit_code == 0, repeat.output
    repeated_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert repeated_report["job_id"] != report["job_id"]
    assert repeated_report["findings"] == report["findings"]


@pytest.mark.parametrize("moodle_essay_archive", ["missing-pdf"], indirect=True)
def test_preflight_demo(moodle_essay_archive: Path, tmp_path: Path) -> None:
    report_path = tmp_path / "demo-test-report.json"
    args = [
        "inspect", str(moodle_essay_archive),
        "--source", "moodle", "--validate-for", "openedx",
        "--preflight", "--output", str(report_path),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["schema_version"] == 1
    assert report["source"] == "moodle"
    assert report["target"] == "openedx"
    assert report["validation_error_codes"] == []
    findings = report["findings"]
    assert len(findings) == 2
    assert {finding["code"] for finding in findings} == {
        "OPENEDX_ESSAY_PLACEHOLDER",
        "MOODLE_PACKAGE_FILE_MISSING",
    }
