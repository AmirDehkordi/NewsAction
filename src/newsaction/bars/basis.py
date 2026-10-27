"""NA-10 S4: the price basis of the bars and their reconciliation with EOD prices (PRD NA-10 S4, AC2).

**What the vendor serves.** With ``nonadjusted=true`` FMP's 30-minute levels are not split-adjusted (probe 3:
NVDA's first-bar opens equal ATOM's raw EOD opens on both sides of the 2024-06-10 split; the fetch's
pre-flight repeats it with both switches). They are not always on the EOD level, though: some histories carry
a constant factor up to a corporate action (spin-offs, on the vendor's side or on ATOM's: HON before the
vendor-dated Solstice spin-off, FTV before Ralliant, CMCSA after the vendor-dated Versant spin-off, the whole
public history of FDX and CTVA). The levels of one session share one factor.

**Reference.** ATOM's raw EOD open, high, low and close × NA-01's level factor (``panel/mapping.parquet``
``level_factor``: 2.0 for HON, whose ATOM raw prices are half the traded level; 1 elsewhere): the traded
level.

**Session basis** (``session_qc``; one row per symbol-session with regular bars), decided with what is
known at 10:00 of the session (CLAUDE.md A1). phi_x = reference x / bar x for x = open (first regular bar),
high (max), low (min) and close (last regular bar). The level of session t is the median of phi_close over
the symbol's previous ``reconcile.trailing_sessions`` sessions with bars (all known by close(t−1); the
official close and the last bar's close differ by a few bp), and 1 when it is within
``reconcile.basis_tolerance`` of 1 or there is no earlier session. The open of t confirms it: phi_open,t (the
official open and the first bar's open, known at the open) must agree within ``reconcile.agree_tolerance``
with that level or with 1, and the closer of the two is used: 1 (``as_traded``; also when a shift has just
ended) or the level (``rescaled``: every bar price × the level, S4's per-session factor). Otherwise (a
misprinted first bar, or a level that has just changed) the session is ``inconsistent`` and not used.
After that every usable bar is on the EOD basis; ``derive`` divides by the level factor to reach ATOM's raw
level. phi_high and phi_low are kept for the report.

**AC2 metrics.** ``open_dev_bp``: the served first-bar open vs the reference open, before any factor (the
vendor's first trade vs the official opening auction); ``open_ok`` within ``reconcile.open_tolerance_bp``.
``complete``: the regular bar count equals the calendar's (13 on a full day, 7 on a half day).
"""

from __future__ import annotations

from typing import Final, Literal

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.bars import load_bars_config
from newsaction.paths import Layout

SessionBasis = Literal["as_traded", "rescaled", "inconsistent", "no_eod"]
QC_COLUMNS: Final = (
    "symbol_id",
    "session",
    "n_regular",
    "n_expected",
    "complete",
    "first_open",
    "bar_high",
    "bar_low",
    "last_close",
    "eod_open",
    "eod_high",
    "eod_low",
    "eod_close",
    "level_factor",
    "phi_open",
    "phi_high",
    "phi_low",
    "phi_close",
    "level_prev",
    "open_dev_bp",
    "open_ok",
    "basis",
    "factor",
    "usable",
)


def reference_prices(layout: Layout | None = None, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """(symbol_id, session, eod_open/high/low/close, level_factor) of the public snapshot, plus ``extra`` rows
    in the snapshot's schema (the post-freeze route adds the blinded prices it obtained from the lock)."""
    px = io.read_parquet("snapshot/prices_raw.parquet", layout=layout)
    if extra is not None:
        px = pd.concat([px, extra], ignore_index=True)
    mp = io.read_parquet("panel/mapping.parquet", columns=["symbol_id", "level_factor"], layout=layout)
    names = {
        "trade_date": "session",
        "open": "eod_open",
        "high": "eod_high",
        "low": "eod_low",
        "close": "eod_close",
    }
    out = px.rename(columns=names)[["symbol_id", "session", "eod_open", "eod_high", "eod_low", "eod_close"]]
    out = out.merge(mp, on="symbol_id", how="left")
    out["level_factor"] = out["level_factor"].fillna(1.0).astype("float64")
    return out


def expected_bars(sessions: pd.Series) -> pd.Series:
    """Regular 30-minute bars of each session: 13 on a full day, 7 on a half day (from the calendar)."""
    minutes = load_bars_config().vendor.bar_minutes
    per = {d: calendar.session_minutes(d) // minutes for d in pd.unique(sessions)}
    return sessions.map(per).astype("int64")


def session_qc(bars: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """One row per (symbol_id, session) with regular bars (module docstring)."""
    cfg = load_bars_config().reconcile
    cols = ["symbol_id", "session", "slot", "open", "high", "low", "close"]
    reg = bars.loc[bars["regular"].to_numpy(dtype=bool), cols].sort_values(
        ["symbol_id", "session", "slot"], kind="mergesort"
    )
    g = reg.groupby(["symbol_id", "session"], sort=True)
    qc = pd.DataFrame(
        {
            "n_regular": g.size(),
            "bar_high": g["high"].max(),
            "bar_low": g["low"].min(),
            "last_close": g["close"].last(),
        }
    ).reset_index()
    first = reg.loc[reg["slot"] == 0, ["symbol_id", "session", "open"]].rename(columns={"open": "first_open"})
    key = ["symbol_id", "session"]
    qc = qc.merge(first, on=key, how="left").merge(ref, on=key, how="left")
    qc["n_expected"] = expected_bars(qc["session"])
    qc["complete"] = qc["n_regular"] == qc["n_expected"]
    lvl = qc["level_factor"].fillna(1.0)
    for x, bar in (("open", "first_open"), ("high", "bar_high"), ("low", "bar_low"), ("close", "last_close")):
        qc[f"phi_{x}"] = qc[f"eod_{x}"] * lvl / qc[bar]
    qc["open_dev_bp"] = 1e4 * (1.0 / qc["phi_open"] - 1.0)
    qc["open_ok"] = qc["open_dev_bp"].abs() <= cfg.open_tolerance_bp
    prev = qc.groupby("symbol_id", sort=False)["phi_close"].transform(
        lambda x: x.rolling(cfg.trailing_sessions, min_periods=1).median().shift(1)
    )
    level = prev.where(prev.notna() & ((prev - 1.0).abs() > cfg.basis_tolerance), 1.0)
    qc["level_prev"] = level
    d_level = (qc["phi_open"] / level - 1.0).abs()
    d_one = (qc["phi_open"] - 1.0).abs()
    factor = np.where(
        np.minimum(d_level, d_one) > cfg.agree_tolerance, np.nan, np.where(d_level < d_one, level, 1.0)
    )
    basis = np.where(
        qc["eod_open"].isna() | qc["first_open"].isna(),
        "no_eod",
        np.where(np.isnan(factor), "inconsistent", np.where(factor == 1.0, "as_traded", "rescaled")),
    )
    qc["basis"] = basis
    qc["factor"] = factor
    qc["usable"] = np.isin(basis, ["as_traded", "rescaled"])
    return qc[list(QC_COLUMNS)]


def on_eod_basis(bars: pd.DataFrame, qc: pd.DataFrame) -> pd.DataFrame:
    """The bars of usable sessions on the EOD basis (traded level): prices × the session factor (1 as traded).
    Volume is left as served."""
    keep = qc.loc[qc["usable"], ["symbol_id", "session", "factor"]]
    out = bars.merge(keep, on=["symbol_id", "session"], how="inner")
    for c in ("open", "high", "low", "close"):
        if c in out.columns:
            out[c] = out[c] * out["factor"]
    return out.drop(columns="factor")
