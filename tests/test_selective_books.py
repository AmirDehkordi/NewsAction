"""NA-13b tradable versions: the sign book's weights, its two exits and its timing guards, on a toy market."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.selective import books as bk
from newsaction.strategy import portfolios as pf

SESSIONS = calendar.sessions(date(2025, 10, 1), date(2025, 10, 31))
T0, T1 = SESSIONS[3], SESSIONS[4]
R_ID = {1: 0.03, 2: 0.01, 3: 0.0, 4: -0.02}
R_CC_NEXT = {1: 0.02, 2: -0.01, 3: 0.0, 4: 0.01}
BETA = {1: 1.2, 2: 0.8, 3: 1.0, 4: 1.5}


def market() -> pd.DataFrame:
    rows = []
    for d in SESSIONS:
        for s in R_ID:
            rows.append(
                {"session": d, "symbol_id": s, "raw_open": 50.0, "raw_close": 50.0, "p10": 50.0,
                 "r_cc": R_CC_NEXT[s] if d == T1 else 0.0, "r_id": R_ID[s] if d == T0 else 0.0,
                 "r_10c": 0.0, "r_spy_cc": 0.005 if d == T1 else 0.0, "r_spy_id": 0.01 if d == T0 else 0.0,
                 "r_spy_10c": 0.0, "beta_m": BETA[s], "adv20": 2e7 * s}
            )  # fmt: skip
    return pd.DataFrame(rows)


def events(days: dict[date, dict[int, int]]) -> pd.DataFrame:
    """``days``: session → {symbol: side}; every input known the evening before."""
    rows = []
    for d, sides in days.items():
        before = calendar.close_utc(calendar.prev_session(d))
        for s, side in sides.items():
            rows.append({"event_id": f"W0:{s}:{d}", "session": d, "symbol_id": s, "company_id": s,
                         "tier": "rest", "side": float(side), "news_utc": before, "tier_utc": before,
                         "condition_utc": before, "selection_utc": before})  # fmt: skip
    return pd.DataFrame(rows)


def test_each_side_is_equally_weighted_and_a_one_sided_day_holds_cash() -> None:
    ev = events({T0: {1: 1, 2: 1, 3: 1, 4: -1}, T1: {1: 1, 2: 1}})
    r = bk.run_book(ev, market(), SESSIONS, "close_t", "val_b", seeds=3)
    daily = r["daily"].set_index("session")
    # T0: three longs at +1/3, one short at −1, each against β·SPY (SPY +1% open → close)
    gross_t0 = (0.03 - 1.2 * 0.01 + 0.01 - 0.8 * 0.01 + 0.0 - 1.0 * 0.01) / 3 - (-0.02 - 1.5 * 0.01)
    assert daily.at[T0, "gross"] == pytest.approx(gross_t0)
    assert daily.at[T1, "gross"] == 0.0 and not daily.at[T1, "active"]  # no short on T1: cash
    s = r["summary"]
    assert (s["names_long"], s["names_short"]) == (3.0, 1.0)
    assert s["n_traded_positions"] == 4


def test_the_next_close_exit_holds_two_legs_at_half_capital() -> None:
    ev = events({T0: {1: 1, 2: 1, 3: 1, 4: -1}})
    r = bk.run_book(ev, market(), SESSIONS, "close_t+1", "val_b", seeds=3)
    daily = r["daily"].set_index("session")
    w = {1: 1 / 3, 2: 1 / 3, 3: 1 / 3, 4: -1.0}
    leg0 = sum(w[s] * (R_ID[s] - BETA[s] * 0.01) for s in w)  # raw open → close of t, β of t
    leg1 = sum(w[s] * (R_CC_NEXT[s] - BETA[s] * 0.005) for s in w)  # close → close of t+1, the same β
    assert daily.at[T0, "gross"] == pytest.approx(leg0 / 2)
    assert daily.at[T1, "gross"] == pytest.approx(leg1 / 2)
    assert r["summary"]["holding"] == 2


def test_an_input_known_only_at_the_open_is_refused() -> None:
    ev = events({T0: {1: 1, 4: -1}})
    ev["condition_utc"] = calendar.open_utc(T0)  # e.g. SPY's overnight move: printed at the open
    with pytest.raises(pf.TimingError):
        bk.run_book(ev, market(), SESSIONS, "close_t", "val_b", seeds=3)


def test_a_test_book_needs_the_selection_before_its_decision() -> None:
    ev = events({T0: {1: 1, 4: -1}})
    ev["selection_utc"] = calendar.close_utc(T0)
    bk.run_book(ev, market(), SESSIONS, "close_t", "val_b", seeds=3)  # val-B: in-sample, not checked
    with pytest.raises(pf.TimingError):
        bk.run_book(ev, market(), SESSIONS, "close_t", "test", seeds=3)


def test_the_placebo_flips_coins_with_seeds_after_the_strategy_seed() -> None:
    ev = events({T0: {1: 1, 2: 1, 3: 1, 4: -1}, T1: {1: 1, 2: -1}})
    a = bk.run_book(ev, market(), SESSIONS, "close_t", "val_b", seeds=20)["summary"]
    b = bk.run_book(ev, market(), SESSIONS, "close_t", "val_b", seeds=20)["summary"]
    assert a["placebo_pct_gross"] == b["placebo_pct_gross"]  # deterministic
    assert 0.0 <= a["placebo_pct_gross"] <= 100.0 and np.isfinite(a["placebo_q90_gross"])


def _instant(book: bk.Book, d: date, frozen: dict[str, object] | None = None) -> pd.Timestamp:
    rows = pd.DataFrame({"session": [d]})
    return pd.Timestamp(bk.condition_utc(rows, book, frozen or {}).iloc[0])


def test_each_condition_is_dated_when_its_input_is_known() -> None:
    d = date(2025, 10, 6)  # a val-B session, after the val-A cut points
    before = calendar.close_utc(calendar.prev_session(d))
    assert _instant(bk.Book("laya_fin", "e4_spy_gap"), d) == calendar.open_utc(d)
    for k in ("e4_busy_day", "e4_earnings_season"):
        assert _instant(bk.Book("laya_fin", k), d) == calendar.d0_cutoff_utc(d)
    for k in ("e4_vix", "e4_friday", "e4_macro"):
        assert _instant(bk.Book("laya_fin", k), d) == before
    val_a_end = calendar.close_utc(bk.load_splits().splits["val_a"].end)
    for k in ("e2_numbers", "e4_spy_gap", "e4_vix", "e9_division"):  # on val-A, the cut points bind
        assert _instant(bk.Book("laya_fin", k), date(2025, 7, 10)) == val_a_end
    for k in bk.SELECTION_ONLY:
        assert pd.isna(_instant(bk.Book("laya_fin", k), d))


def test_the_cost_rule_waits_for_the_frozen_map() -> None:
    frozen = {"calibration": {"laya_fin": {"a0": {"fit_range": ["2025-07-09", "2025-10-03"]}}}}
    got = _instant(bk.Book("laya_fin", "e8_cost"), date(2025, 10, 6), frozen)
    assert got == calendar.close_utc(
        pf.session_after(date(2025, 10, 3), bk.E5_HORIZON)
    )  # the map read e5 to t+4


def test_books_on_the_spy_gap_or_a_vendor_label_are_refused() -> None:
    for k in ("e4_spy_gap", *bk.SELECTION_ONLY):
        ev = events({T0: {1: 1, 4: -1}})
        ev["condition_utc"] = bk.condition_utc(ev, bk.Book("laya_fin", k), {})
        with pytest.raises(pf.TimingError):
            bk.run_book(ev, market(), SESSIONS, "close_t", "val_b", seeds=3)
