"""NA-10 S4: price basis of the 30-minute bars (PRD NA-10 S4, AC2 "the four split windows pass").

Synthetic: a session's factor is 1 as traded; a level shift is rescaled from its second session on and
ends when the open agrees with 1 again; a misprinted first bar makes the session inconsistent; the factor
of session t uses no price after 10:00 of t (PIT guard: change the close of t and only later sessions
move). Mutation: drop the ``shift(1)`` of the trailing level in ``basis.session_qc`` and the PIT test fails.

Real data (skipped until the fetch and derive ran): around the NVDA (10:1, 2024-06-10), AVGO (10:1,
2024-07-15), WMT (3:1, 2024-02-26) and CMG (50:1, 2024-06-26) splits the sessions before and on the
ex-date are as traded, their first-bar opens are within 1% of ATOM's raw open, and the 10:00 price moves
across the split like any other day once both are put on one basis with NA-01's adjustment factor.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar, io
from newsaction.bars import BARS_QC, INTRADAY_PUBLIC, basis
from newsaction.bars.basis import on_eod_basis, session_qc
from newsaction.paths import ROOT

SPLITS = (
    ("NVDA", date(2024, 6, 10), 10.0),
    ("AVGO", date(2024, 7, 15), 10.0),
    ("WMT", date(2024, 2, 26), 3.0),
    ("CMG", date(2024, 6, 26), 50.0),
)


def _bars(
    levels: list[float], open_print: dict[int, float] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bars of one symbol over len(levels) sessions: true price 100 at the open, 101 at the close (13 bars),
    served × levels[i]; the EOD reference is the true price. ``open_print``: a misprinted first-bar open."""
    days = calendar.sessions(date(2025, 3, 3), date(2025, 6, 30))[: len(levels)]
    rows, ref = [], []
    for i, (d, k) in enumerate(zip(days, levels, strict=True)):
        for slot in range(13):
            o = 100.0 + slot / 13
            c = 100.0 + (slot + 1) / 13
            rows.append(
                {
                    "symbol_id": 1,
                    "session": d,
                    "slot": slot,
                    "regular": True,
                    "open": o * k,
                    "high": max(o, c) * k,
                    "low": min(o, c) * k,
                    "close": c * k,
                    "volume": 1e4,
                }
            )
        if open_print and i in open_print:
            rows[-13]["open"] = open_print[i]
        ref.append(
            {
                "symbol_id": 1,
                "session": d,
                "eod_open": 100.0,
                "eod_high": 101.0,
                "eod_low": 100.0,
                "eod_close": 101.0,
                "level_factor": 1.0,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(ref)


def test_as_traded_sessions_keep_their_prices() -> None:
    bars, ref = _bars([1.0] * 6)
    qc = session_qc(bars, ref)
    assert (qc["basis"] == "as_traded").all() and (qc["factor"] == 1.0).all() and qc["complete"].all()
    assert qc["open_ok"].all()
    assert on_eod_basis(bars, qc)["close"].equals(bars["close"])


def test_a_level_shift_is_rescaled_from_its_second_session_and_ends() -> None:
    bars, ref = _bars([1.25] * 6 + [1.0] * 3)
    qc = session_qc(bars, ref)
    assert list(qc["basis"]) == ["inconsistent"] + ["rescaled"] * 5 + ["as_traded"] * 3
    assert np.allclose(qc.loc[1:5, "factor"], 1 / 1.25)
    fixed = on_eod_basis(bars, qc)
    first = fixed.loc[fixed["slot"] == 0].set_index("session")["open"]
    assert np.allclose(first.to_numpy(), 100.0)  # every usable session on the EOD level


def test_a_misprinted_first_bar_is_not_used() -> None:
    bars, ref = _bars([1.0] * 5, open_print={3: 82.0})
    qc = session_qc(bars, ref)
    assert qc.loc[3, "basis"] == "inconsistent" and not qc.loc[3, "usable"]
    assert qc.drop(index=3)["usable"].all()


def test_the_factor_of_a_session_uses_nothing_after_its_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """PIT guard: with a one-session trailing level, a different close of session 2 (EOD and bars) changes no
    factor up to session 2, and does change session 3's (the guard is not vacuous)."""
    cfg = basis.load_bars_config()
    one = cfg.model_copy(update={"reconcile": cfg.reconcile.model_copy(update={"trailing_sessions": 1})})
    monkeypatch.setattr(basis, "load_bars_config", lambda: one)
    bars, ref = _bars([1.25] * 6)
    base = session_qc(bars, ref)
    late = bars["session"].eq(bars["session"].unique()[2]) & bars["slot"].eq(12)
    moved = bars.copy()
    moved.loc[late, ["close", "high"]] *= 1.3
    moved_ref = ref.copy()
    moved_ref.loc[2, "eod_close"] *= 1.05
    after = session_qc(moved, moved_ref)
    assert after.loc[:2, "factor"].equals(base.loc[:2, "factor"])
    assert after.loc[3, "basis"] != base.loc[3, "basis"]


def _need(rel: str) -> None:
    if not (ROOT / "work" / rel).is_file():
        pytest.skip(f"work/{rel} is absent (run newsaction.bars.fetch and derive)")


@pytest.mark.parametrize(("ticker", "ex", "ratio"), SPLITS)
def test_split_windows_are_on_one_basis(ticker: str, ex: date, ratio: float) -> None:
    _need(BARS_QC)
    _need(INTRADAY_PUBLIC)
    sym = io.read_parquet("snapshot/symbols.parquet", columns=["symbol_id", "ticker"])
    sid = int(sym.loc[sym["ticker"] == ticker, "symbol_id"].iloc[0])
    prev = calendar.prev_session(ex)
    qc = io.read_parquet(BARS_QC).set_index(["symbol_id", "session"])
    for d in (prev, ex):
        row = qc.loc[(sid, d)]
        assert row["basis"] == "as_traded" and abs(row["phi_open"] - 1.0) <= 0.01, (
            ticker,
            d,
            row["phi_open"],
        )
    raw = io.read_parquet("snapshot/prices_raw.parquet", columns=["symbol_id", "trade_date", "open"])
    eod = raw.loc[raw["symbol_id"] == sid].set_index("trade_date")["open"]
    assert eod[prev] / eod[ex] == pytest.approx(ratio, rel=0.15)  # the raw levels do split
    pan = io.read_parquet("panel/panel_public.parquet", columns=["session", "symbol_id", "adj_factor"])
    f = pan.loc[pan["symbol_id"] == sid].set_index("session")["adj_factor"]
    intra = io.read_parquet(INTRADAY_PUBLIC, columns=["session", "symbol_id", "p10"])
    p10 = intra.loc[intra["symbol_id"] == sid].set_index("session")["p10"]
    move = (p10[ex] * f[ex]) / (p10[prev] * f[prev]) - 1.0
    assert abs(move) < 0.10, (ticker, move)  # no split-sized jump on one basis
