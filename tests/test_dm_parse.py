"""Derived quantities (PRD NA-05 S6; PREREG §7, A2.4) on hand-made probability vectors."""

from __future__ import annotations

import math
import re

import pytest

from newsaction.dm import parse
from newsaction.dm.schemas import parse_response, questions_from
from newsaction.paths import ROOT
from newsaction.states.questions import load_battery


def one_hot(n: int, k: int) -> list[float]:
    return [1.0 if i == k else 0.0 for i in range(n)]


def test_q1_midpoints_are_prereg_s7() -> None:
    text = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
    m = re.search(r"m = \(([^)]*)\)", text)
    assert m is not None
    prereg = tuple(float(x.replace("−", "-")) for x in m.group(1).split(","))
    assert prereg == parse.Q1_MIDPOINTS


@pytest.mark.parametrize("k", range(9))
def test_n_hat_of_a_certain_level_is_its_midpoint(k: int) -> None:
    assert parse.n_hat(one_hot(9, k)) == parse.Q1_MIDPOINTS[k]
    assert parse.abs_n_hat(one_hot(9, k)) == abs(parse.Q1_MIDPOINTS[k])


def test_n_hat_of_mixtures() -> None:
    assert parse.n_hat([1 / 9] * 9) == pytest.approx(0.0)
    assert parse.abs_n_hat([1 / 9] * 9) == pytest.approx(16.5 / 9)
    p = [0, 0, 0, 0, 0.5, 0.25, 0.25, 0, 0]
    assert parse.n_hat(p) == pytest.approx(0.25 * 0.75 + 0.25 * 1.5)
    with pytest.raises(parse.ParseError):
        parse.n_hat([0.5, 0.5])
    with pytest.raises(parse.ParseError):
        parse.n_hat([0.2] * 9)


def test_materiality_and_adequacy_and_continuation() -> None:
    assert parse.materiality({"new_information": 0.7, "no_new_information": 0.3}) == 0.7
    adq = {
        "wrong_direction": 0.1,
        "much_too_small": 0.2,
        "too_small": 0.3,
        "about_right": 0.15,
        "too_large": 0.15,
        "much_too_large": 0.1,
    }
    assert parse.adequacy_j(adq) == pytest.approx(0.2 + 0.3 - 0.15 - 0.1)
    assert parse.adequacy_w(adq) == 0.1
    assert parse.continuation_c({"reverse": 0.6, "stall": 0.3, "continue": 0.1}) == pytest.approx(-0.5)
    with pytest.raises(parse.ParseError):
        parse.continuation_c({"reverse": 0.6, "continue": 0.4})


@pytest.mark.parametrize(
    ("n", "g", "label"),
    [
        (2.0, 1.0, "Under"),
        (2.0, 1.6, "Fair"),
        (2.0, 3.0, "Over"),
        (-2.0, -0.5, "Under"),
        (-2.0, -3.0, "Over"),
    ],
)
def test_rg_labels(n: float, g: float, label: str) -> None:
    value, lab = parse.rg(n, g)
    assert lab == label and value == pytest.approx((n - g) * math.copysign(1, n))


def test_rg_is_undefined_below_half() -> None:
    assert parse.rg(0.4, 3.0) == (None, None)
    assert parse.rg(-0.49, -3.0) == (None, None)
    assert parse.rg(0.5, 0.0)[1] is not None


def test_horizon_renormalizes_without_no_material_effect() -> None:
    p = {
        "today": 0.2,
        "within_days": 0.2,
        "within_weeks": 0.0,
        "months_or_longer": 0.1,
        "no_material_effect": 0.5,
    }
    h, none = parse.horizon(p)
    assert none == 0.5
    assert h == pytest.approx((0.2 * 1 + 0.2 * 3 + 0.1 * 60) / 0.5)
    assert parse.horizon({**{k: 0.0 for k in parse.HORIZON_SESSIONS}, "no_material_effect": 1.0}) == (
        None,
        1.0,
    )


def test_explanation_x_and_labels_and_confidence() -> None:
    x = {"fully_explains": 0.4, "partly_explains": 0.4, "unrelated": 0.1, "contradicts": 0.1}
    assert parse.explanation_x(x) == pytest.approx(0.4 + 0.2 - 0.1)
    assert parse.argmax_label({"a": 0.2, "b": 0.5, "c": 0.3}) == ("b", 0.5)
    assert parse.expected_level([0, 0, 1, 0, 0]) == 2.0
    assert parse.entropy_confidence([1, 0, 0]) == pytest.approx(1.0)
    assert parse.entropy_confidence([0.25] * 4) == pytest.approx(0.0)


def _answer(qtype: str, options: list[str], p: list[float]) -> dict[str, object]:
    if qtype == "choice":
        return {
            "type": "choice",
            "choice": options[p.index(max(p))],
            "probabilities": dict(zip(options, p, strict=True)),
        }
    probs = {str(i): v for i, v in enumerate(p)}
    return {"type": "score", "score": sum(i * v for i, v in enumerate(p)), "probabilities": probs}


def test_derive_on_the_full_call_a_and_call_b_batteries() -> None:
    b = load_battery()
    for call, groups in (("A", ["core", "extended"]), ("B", ["core", "explain"])):
        qs = questions_from(b.request(call, groups))
        answers = {}
        for qid, q in qs.items():
            n = len(q.options())
            answers[qid] = _answer(q.type, q.options(), one_hot(n, n - 1))
        raw = {"model": "m", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 0}}
        parsed = parse_response(raw, qs)
        assert parsed.valid, parsed.problem_list()
        d = parse.derive(parsed.answers, qs)
        assert d["n_hat"] == 3.5 and d["abs_n_hat"] == 3.5
        if call == "A":
            assert d["m"] == 0.0 and d["surprise"] == 4.0 and d["tone"] == 4.0
            assert d["p_no_material_effect"] == 1.0 and "h" not in d
            assert d["label_event_type"] == "other" and d["p_mixed"] == 1.0 and d["u_unc"] == 4.0
        else:
            assert d["j"] == -1.0 and d["w"] == 0.0 and d["c"] == 1.0
            assert d["x"] == -1.0 and d["label_move_reason"] == "no_identifiable_news"
        assert all(d[f"pmax_{q}"] == 1.0 for q in qs)


def test_derive_skips_invalid_answers() -> None:
    b = load_battery()
    qs = questions_from(b.request("A", ["core"]))
    answers = {qid: _answer(q.type, q.options(), one_hot(len(q.options()), 0)) for qid, q in qs.items()}
    answers["justified_move"]["probabilities"] = {str(i): 0.1 for i in range(9)}  # sums to 0.9
    raw = {"model": "m", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 0}}
    d = parse.derive(parse_response(raw, qs).answers, qs)
    assert "n_hat" not in d and d["m"] == 1.0
