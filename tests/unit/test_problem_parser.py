from __future__ import annotations

from adapters.openedx.problem_parser import parse_problem

PROBLEM_XML = """\
<problem display_name="Synthetic Problem">
  <multiplechoiceresponse>
    <label>Pick one</label>
    <choicegroup type="MultipleChoice">
      <choice correct="true">A</choice>
      <choice correct="false">B</choice>
    </choicegroup>
  </multiplechoiceresponse>
  <stringresponse answer="42" type="ci">
    <label>Short answer</label>
    <textline size="20" />
  </stringresponse>
  <numericalresponse answer="3.14">
    <label>Numerical answer</label>
    <responseparam type="tolerance" default="0.01" />
    <formulaequationinput />
  </numericalresponse>
</problem>
"""


def test_source_question_ids_are_stable_across_parses():
    first = parse_problem(PROBLEM_XML, "problem-1")
    second = parse_problem(PROBLEM_XML, "problem-1")

    assert [question["question_id"] for question in first["questions"]] == [
        question["question_id"] for question in second["questions"]
    ]


def test_source_question_ids_include_problem_identity_and_position():
    first = parse_problem(PROBLEM_XML, "problem-1")
    second = parse_problem(PROBLEM_XML, "problem-2")

    first_ids = [question["question_id"] for question in first["questions"]]
    second_ids = [question["question_id"] for question in second["questions"]]

    assert len(first_ids) == len(set(first_ids))
    assert set(first_ids).isdisjoint(second_ids)
    assert [question["type"] for question in first["questions"]] == [
        "multichoice",
        "shortanswer",
        "numerical",
    ]


def test_parse_numerical_tolerance():
    questions = parse_problem(PROBLEM_XML, "problem-tolerance")["questions"]
    numerical = next(question for question in questions if question["type"] == "numerical")

    assert numerical["tolerance"] == "0.01"
