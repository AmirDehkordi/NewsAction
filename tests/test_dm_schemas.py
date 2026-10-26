"""Request and response schemas (PRD NA-05 S1): strict parsing records problems and never repairs."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from dm_fakes import MODEL, QUESTIONS, STATE, ok_response
from newsaction.dm.schemas import (
    PROB_TOL,
    RENORM_TOL,
    DecisionRequest,
    QuestionSpec,
    SchemaError,
    parse_response,
    questions_from,
)
from newsaction.states.questions import load_battery


def body() -> dict[str, Any]:
    return DecisionRequest(model=MODEL, state=STATE, questions=QUESTIONS).body({})


def good() -> dict[str, Any]:
    return ok_response(body())


def test_question_types_and_shapes() -> None:
    with pytest.raises(ValidationError):
        QuestionSpec(type="noul", instructions="x", criteria={"true": "a", "false": "b"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        QuestionSpec(type="choice", instructions="x", criteria={"only": "one"})
    with pytest.raises(ValidationError):
        QuestionSpec(type="score", instructions="x", criteria=["one"])
    with pytest.raises(ValidationError):
        QuestionSpec(type="score", instructions="x", criteria=[str(i) for i in range(11)])
    with pytest.raises(ValidationError):
        QuestionSpec(type="choice", instructions="", criteria={"a": "1", "b": "2"})
    assert QuestionSpec(type="score", instructions="x", criteria=["a", "b"]).options() == ["0", "1"]


def test_battery_questions_are_valid_specs() -> None:
    b = load_battery()
    for call, groups in (("A", ["core", "extended"]), ("B", ["core", "explain"])):
        qs = questions_from(b.request(call, groups))
        assert list(qs) == b.keys(call, groups)
    with pytest.raises(SchemaError):
        questions_from({"x": {"type": "noul", "instructions": "x"}})


def test_body_keeps_question_and_option_order_and_sorts_the_state() -> None:
    state = {"news": [], "company": {"z": 1, "a": 2}}
    req = DecisionRequest(model=MODEL, state=state, questions=QUESTIONS)
    b = req.body({"seed": 3})
    assert list(b["state"]) == ["company", "news"] and list(b["state"]["company"]) == ["a", "z"]
    assert list(b["questions"]) == list(QUESTIONS)
    assert list(b["questions"]["materiality"]["criteria"]) == ["new_information", "no_new_information"]
    assert b["provider"] == {"data_collection": "deny"} and b["seed"] == 3
    with pytest.raises(SchemaError):
        req.body({"provider": {"data_collection": "allow"}})
    assert req.state_text() == json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_a_well_formed_response_is_valid() -> None:
    p = parse_response(good(), QUESTIONS)
    assert p.valid and p.response is not None
    assert p.answers["materiality"].probs == (0.5, 0.5)
    assert p.answers["justified_move"].probs == pytest.approx((0.2,) * 5)
    assert p.response.usage.cost == 0.0001


def test_missing_type_is_invalid() -> None:
    raw = good()
    del raw["answers"]["materiality"]["type"]
    p = parse_response(raw, QUESTIONS)
    assert not p.valid
    assert p.answers["materiality"].problems == ("missing type",)
    assert p.answers["materiality"].probs is None
    assert p.answers["justified_move"].valid


def _with_sum_off(delta: float) -> dict[str, Any]:
    raw = good()
    raw["answers"]["materiality"]["probabilities"] = {
        "new_information": 0.5 + delta,
        "no_new_information": 0.5,
    }
    return raw


@pytest.mark.parametrize("delta", [0.0104, -0.0104, 0.01, -2e-6, 1e-5])
def test_sums_within_one_rounding_step_are_renormalized_and_flagged(delta: float) -> None:
    """Operator decision 2026-10-26 (PRD S1 changed): 1e-6 < |Σp − 1| ≤ 0.0105 → p / Σp, renormalized."""
    raw = _with_sum_off(delta)
    a = parse_response(raw, QUESTIONS).answers["materiality"]
    assert a.valid and a.renormalized
    assert a.raw_sum == pytest.approx(1.0 + delta)
    assert a.probs is not None and sum(a.probs) == pytest.approx(1.0, abs=1e-12)
    assert a.probs == pytest.approx(((0.5 + delta) / (1.0 + delta), 0.5 / (1.0 + delta)))
    assert a.answer is not None and a.answer.probabilities == {  # the returned answer is not altered
        "new_information": 0.5 + delta,
        "no_new_information": 0.5,
    }


@pytest.mark.parametrize("delta", [0.0106, -0.0106, 0.02, -0.5])
def test_sums_beyond_one_rounding_step_stay_invalid(delta: float) -> None:
    a = parse_response(_with_sum_off(delta), QUESTIONS).answers["materiality"]
    assert not a.valid and a.probs is None and not a.renormalized
    assert any("sum to" in x for x in a.problems)
    assert a.raw_sum == pytest.approx(1.0 + delta)


def test_the_bound_is_the_constant() -> None:
    assert RENORM_TOL == 0.0105 and PROB_TOL == 1e-6


def test_sum_within_tolerance_is_valid_and_not_flagged() -> None:
    a = parse_response(_with_sum_off(4e-7), QUESTIONS).answers["materiality"]
    assert a.valid and not a.renormalized and a.probs == (0.5 + 4e-7, 0.5)


def test_a_probability_outside_0_1_is_never_renormalized() -> None:
    raw = good()
    raw["answers"]["materiality"]["probabilities"] = {"new_information": 1.004, "no_new_information": -0.001}
    a = parse_response(raw, QUESTIONS).answers["materiality"]
    assert not a.valid and not a.renormalized and "outside [0, 1]" in a.problems[0]


def test_jev_style_score_on_a_grid_is_renormalized() -> None:
    raw = good()
    probs = {"0": 0.2, "1": 0.2, "2": 0.2, "3": 0.2, "4": 0.19}  # sums to 0.99 (a 0.01 grid)
    raw["answers"]["justified_move"]["probabilities"] = probs
    a = parse_response(raw, QUESTIONS).answers["justified_move"]
    assert a.valid and a.renormalized and a.probs is not None
    assert a.probs[4] == pytest.approx(0.19 / 0.99)


def test_missing_or_mismatched_probabilities_are_invalid() -> None:
    raw = good()
    del raw["answers"]["materiality"]["probabilities"]
    assert parse_response(raw, QUESTIONS).answers["materiality"].problems == ("missing probabilities",)
    raw = good()
    raw["answers"]["justified_move"]["probabilities"] = {str(i): 0.25 for i in range(4)}
    assert "differ from the options" in parse_response(raw, QUESTIONS).answers["justified_move"].problems[0]
    raw = good()
    raw["answers"]["materiality"]["probabilities"] = {"new_information": 1.2, "no_new_information": -0.2}
    assert not parse_response(raw, QUESTIONS).answers["materiality"].valid


def test_score_legend_and_position() -> None:
    raw = good()
    raw["answers"]["justified_move"]["legend"] = {
        "0": "big rise",
        "1": "fall",
        "2": "flat",
        "3": "rise",
        "4": "big fall",
    }
    assert "legend" in parse_response(raw, QUESTIONS).answers["justified_move"].problems[0]
    raw = good()
    del raw["answers"]["justified_move"]["legend"]
    a = parse_response(raw, QUESTIONS).answers["justified_move"]
    assert a.valid and a.notes == ("no legend",)
    raw = good()
    raw["answers"]["justified_move"]["score"] = 3.5
    a = parse_response(raw, QUESTIONS).answers["justified_move"]
    assert a.valid and a.notes == ("the score is not the probability-weighted position",)


def test_choice_must_be_an_option_and_argmax_is_noted() -> None:
    raw = good()
    raw["answers"]["materiality"]["choice"] = "maybe"
    assert not parse_response(raw, QUESTIONS).answers["materiality"].valid
    raw = good()
    raw["answers"]["materiality"]["probabilities"] = {"new_information": 0.2, "no_new_information": 0.8}
    a = parse_response(raw, QUESTIONS).answers["materiality"]
    assert a.valid and "most probable" in a.notes[0]


def test_type_mismatch_and_non_object_answers() -> None:
    raw = good()
    raw["answers"]["materiality"] = copy.deepcopy(raw["answers"]["justified_move"])
    assert "asked 'choice'" in parse_response(raw, QUESTIONS).answers["materiality"].problems[0]
    raw = good()
    raw["answers"]["materiality"] = "new_information"
    assert not parse_response(raw, QUESTIONS).answers["materiality"].valid


def test_envelope_problems() -> None:
    raw = good()
    del raw["usage"]
    p = parse_response(raw, QUESTIONS)
    assert not p.valid and p.response is None and "usage" in p.problems[0]
    raw = good()
    del raw["answers"]["materiality"]
    raw["answers"]["extra"] = {"type": "choice"}
    p = parse_response(raw, QUESTIONS)
    assert set(p.problems) == {"no answer for materiality", "unexpected answer extra"}
    assert not parse_response("not json", QUESTIONS).valid
    assert not parse_response(None, QUESTIONS).valid


def test_extra_fields_are_kept() -> None:
    raw = good()
    raw["answers"]["materiality"]["answer_confidence"] = 0.7
    raw["usage"]["truncated"] = False
    p = parse_response(raw, QUESTIONS)
    assert p.valid
    assert p.response is not None and p.response.usage.model_extra == {"truncated": False}
