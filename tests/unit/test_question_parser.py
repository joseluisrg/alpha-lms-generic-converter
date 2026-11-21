from __future__ import annotations

from pathlib import Path

from adapters.moodle.question_parser import parse_questions


def _write_questions(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<question_categories>
  <question id="7">
    <qtype>multichoice</qtype>
    <name><text>Question 7</text></name>
    <questiontext><text>Pick one</text></questiontext>
    <defaultmark>2</defaultmark>
    <plugin_qtype_multichoice_question>
      <multichoice><single>1</single></multichoice>
      <answer><answertext>A</answertext><fraction>1</fraction></answer>
      <answer><answertext>B</answertext><fraction>0</fraction></answer>
    </plugin_qtype_multichoice_question>
  </question>
</question_categories>
""",
        encoding="utf-8",
    )


def test_moodle_question_ids_are_stable(tmp_path: Path):
    questions_path = tmp_path / "questions.xml"
    _write_questions(questions_path)

    first = parse_questions(str(questions_path))
    second = parse_questions(str(questions_path))

    assert first == second
    assert first[0]["assessment_id"]
    assert first[0]["questions"][0]["question_id"]
