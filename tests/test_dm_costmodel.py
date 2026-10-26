"""Cost model (PRD NA-05 S3 dry_run, S8 calibration; PREREG §13)."""

from __future__ import annotations

import pytest

from dm_fakes import COST_CONFIG, LOCAL, MODEL, PRICE, QUESTIONS, STATE
from newsaction.dm import CostCalibration, CostConfig, DMError
from newsaction.dm.costmodel import (
    CostModel,
    Observation,
    Price,
    basis_from_copies,
    billed_bytes,
    billed_parts,
    calibrate,
    fit_tokens,
    state_copies,
)
from newsaction.dm.schemas import DecisionRequest


def req(state: object = None) -> DecisionRequest:
    return DecisionRequest(model=MODEL, state=STATE if state is None else state, questions=QUESTIONS)  # type: ignore[arg-type]


def test_billed_bytes_once_and_per_question() -> None:
    r = req()
    state = len(r.state_text().encode())
    once, per_q = billed_bytes(r, "once"), billed_bytes(r, "per_question")
    assert per_q - once == state * (len(QUESTIONS) - 1)


def test_state_copies_once_and_per_question() -> None:
    once = state_copies([1, 2, 4], short=[600, 650, 750], long=[1000, 1050, 1150])
    assert once == {1: 1.0, 2: 1.0, 4: 1.0} and basis_from_copies(once) == "once"
    per_q = state_copies([1, 2, 4], short=[600, 1200, 2400], long=[1000, 2000, 4000])
    assert per_q == {1: 1.0, 2: 2.0, 4: 4.0} and basis_from_copies(per_q) == "per_question"
    with pytest.raises(DMError):
        state_copies([2, 4], short=[1, 2], long=[3, 4])


def test_one_anomalous_usage_report_does_not_decide_the_basis() -> None:
    # NA-05 pilot: one 13-question response of inception/mercury-decide reported 161 input tokens
    copies = state_copies([1, 2, 4, 13], short=[622, 731, 968, 161], long=[975, 1060, 1326, 2357])
    assert copies[13] > 6
    assert basis_from_copies(copies) == "once"


def test_fit_tokens_recovers_two_rates_and_trims_outliers() -> None:
    state = [800.0, 1600.0, 2400.0, 800.0, 1600.0, 2400.0, 3000.0, 1200.0]
    questions = [300.0, 300.0, 300.0, 1200.0, 1200.0, 1200.0, 3000.0, 600.0]
    tokens = [100 + s / 4 + q / 2 for s, q in zip(state, questions, strict=True)]
    tokens[2] = 161.0  # a call billed far below its size (prompt cache)
    overhead, per_state, per_question, kept = fit_tokens(state, questions, tokens)
    assert per_state == pytest.approx(0.25, rel=1e-6) and per_question == pytest.approx(0.5, rel=1e-6)
    assert overhead == pytest.approx(100.0, abs=1e-6) and kept == 7


def test_calibrate_recovers_bytes_per_token_and_ratio() -> None:
    price = Price(prompt=2e-8, request=0.0, discount=0.0)
    obs = []
    for n in range(1, 7):
        questions = dict(list(QUESTIONS.items())[: 1 + n % 2])
        r = DecisionRequest(model=MODEL, state={"news": "x" * (500 * n)}, questions=questions)
        sb, qb = billed_parts(r, "once")
        tokens = round(50 + sb / 4 + qb / 3)
        obs.append(Observation(r, tokens, price.usd(tokens)))
    cal = calibrate(MODEL, obs, "once", price)
    assert cal.bytes_per_token == pytest.approx(4.0, rel=2e-2)
    assert cal.question_bytes_per_token == pytest.approx(3.0, rel=5e-2)
    assert cal.overhead_tokens == pytest.approx(50, abs=3)
    assert cal.cost_ratio == pytest.approx(1.0)


def test_estimates_use_the_calibration_and_are_zero_for_local_models() -> None:
    r = req()
    default = CostModel(COST_CONFIG, {MODEL: PRICE})
    cal = CostCalibration(
        billing_basis="once",
        bytes_per_token=4.0,
        question_bytes_per_token=4.0,
        overhead_tokens=0.0,
        safety=1.0,
        cost_ratio=1.0,
        n_calls=8,
    )
    calibrated = CostModel(CostConfig(default=COST_CONFIG.default, models={MODEL: cal}), {MODEL: PRICE})
    assert calibrated.estimate(MODEL, r).tokens == pytest.approx(billed_bytes(r, "once") / 4.0)
    assert default.estimate(MODEL, r).usd > calibrated.estimate(MODEL, r).usd  # the default over-projects
    assert default.estimate(LOCAL, r).usd == 0.0
    with pytest.raises(DMError, match="no catalog price"):
        default.estimate("test/unknown", r)


def test_price_from_catalog_strings() -> None:
    p = Price.from_catalog({"prompt": "0.000000042", "completion": "0", "request": None})
    assert p.prompt == pytest.approx(4.2e-8) and p.request == 0.0
    assert p.usd(1_000_000) == pytest.approx(0.042)
    with pytest.raises(DMError):
        Price.from_catalog({"prompt": "-1"})
