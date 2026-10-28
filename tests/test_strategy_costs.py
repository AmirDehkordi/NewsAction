"""NA-13 AC2: costs on both legs and the SPY hedge; a toy book reproduces the expected net return by hand."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.strategy import capacity as cp
from newsaction.strategy import costs as cs
from newsaction.strategy import portfolios as pf

SESSIONS = calendar.sessions(date(2025, 10, 1), date(2025, 10, 31))
T = SESSIONS[3]


def toy() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two longs (A, B) and two shorts (C, D) on one session; betas 1.2, 0.8, 1.0, 1.5; SPY +1% open→close."""
    r = {1: 0.03, 2: 0.01, 3: -0.02, 4: 0.005}
    beta = {1: 1.2, 2: 0.8, 3: 1.0, 4: 1.5}
    rows = []
    for d in SESSIONS:
        for s in r:
            rows.append(
                {
                    "session": d,
                    "symbol_id": s,
                    "raw_open": 50.0,
                    "raw_close": 50.0,
                    "p10": 50.0,
                    "r_cc": 0.0,
                    "r_id": r[s] if d == T else 0.0,
                    "r_10c": 0.0,
                    "r_spy_cc": 0.0,
                    "r_spy_id": 0.01 if d == T else 0.0,
                    "r_spy_10c": 0.0,
                    "beta_m": beta[s],
                    "adv20": 2e7 * s,
                }
            )
    ev = pd.DataFrame(
        {
            "event_id": [f"E{s}" for s in r],
            "session": T,
            "symbol_id": list(r),
            "company_id": list(r),
            "tier": "rest",
        }
    )
    return ev, pd.DataFrame(rows)


def test_toy_book_net_return_by_hand() -> None:
    ev, mkt = toy()
    u = pf.build_universe(ev, mkt, "D0", "close_t", SESSIONS)
    w = np.array([0.5, 0.5, -0.5, -0.5])  # ±1/K, K = 2
    d = pf.evaluate(u, w)
    # gross: 0.5(0.03 − 1.2·0.01) + 0.5(0.01 − 0.8·0.01) − 0.5(−0.02 − 1.0·0.01) − 0.5(0.005 − 1.5·0.01)
    gross = 0.5 * 0.018 + 0.5 * 0.002 + 0.5 * 0.03 + 0.5 * 0.01
    # traded per side: Σ|w| = 2 plus the hedge |Σ w·β| = |0.6 + 0.4 − 0.5 − 0.75| = 0.25; two sides at 10 bp
    expected = gross - 2 * (2.0 + 0.25) * 10 / 1e4
    assert gross == pytest.approx(0.030)
    assert expected == pytest.approx(0.0255)
    net = cs.net(d.gross, d.turnover, 10.0)
    assert u.sessions == [T]
    assert net[0, 0] == pytest.approx(expected, abs=1e-15)
    assert cs.toy_net_return(
        [0.03, 0.01, -0.02, 0.005], w, [1.2, 0.8, 1.0, 1.5], 0.01, 10.0
    ) == pytest.approx(expected)
    assert d.turnover[0, 0] == pytest.approx(2 * 2.25)


def test_hedge_cost_counts() -> None:
    ev, mkt = toy()
    u = pf.build_universe(ev, mkt, "D0", "close_t", SESSIONS)
    w = np.array([0.5, 0.5, -0.5, -0.5])
    no_hedge = cs.cohort_notional(w, np.zeros(4), np.zeros(4, dtype=np.int64), 1)
    hedged = cs.cohort_notional(w, u.events["beta"].to_numpy(), np.zeros(4, dtype=np.int64), 1)
    assert no_hedge[0, 0] == pytest.approx(2.0)
    assert hedged[0, 0] == pytest.approx(2.25)


def test_calendar_time_turnover_and_capital() -> None:
    # one cohort a day for 3 days, held L = 2: entries on days 0..2, exits on days 1..3
    notional = np.array([[2.0, 2.0, 2.0]])
    turn = cs.turnover(notional, np.array([0, 1, 2]), np.array([1, 2, 3]), 2, 4)
    np.testing.assert_allclose(turn[0], [1.0, 2.0, 2.0, 1.0])


def test_capacity_one_percent_of_adv() -> None:
    w = np.array([0.5, 0.5, -0.5, -0.5])
    adv = np.array([2e7, 4e7, 6e7, 8e7])
    cap = cp.summarize(w, adv, np.zeros(4, dtype=np.int64), 1, holding=1)
    # the binding name: 0.01 · 2e7 · 1 / 0.5 = 4e5 dollars of capital
    assert cap.median_usd == pytest.approx(4e5)
    cap5 = cp.summarize(w, adv, np.zeros(4, dtype=np.int64), 1, holding=5)
    assert cap5.median_usd == pytest.approx(2e6)


def test_cost_levels_are_frozen() -> None:
    from newsaction.strategy import run

    st = run.frozen_strategy()
    assert tuple(float(x) for x in st["costs_bp_per_side"]) == cs.LEVELS_BP
    assert float(st["capacity_adv_share"]) == cp.ADV_SHARE
    assert float(st["quantile"]) == pf.QUANTILE
    assert int(st["pool_if_side_below"]) == pf.MIN_SIDE
    assert int(st["seed"]) == pf.SEED
