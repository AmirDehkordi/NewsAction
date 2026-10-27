"""Observed reactions G at the decision points (PREREG §5.5, Amendment A1.2; PRD NA-01 S6, NA-10 S6).

Hashed at the NA-11 freeze (PREREG §4.4).

- D2 (after close(t)): ``g_d2`` = z_cc,t (clipped at +-10, as z_cc); ``g_d2_lvl`` = AR_cc,t / sigma_cc,t
  (A1.2 level units, unclipped); context for Call B's ``reaction_so_far``: the stock's and SPY's
  close-to-close move and z_vol,t.
- D1 (10:00 ET, the close of the first 30-minute bar; NA-10): ``g_d1`` = AR(close(prev) -> 10:00) /
  (sigma_on^2 + sigma_30^2)^(1/2), clipped at +-10 (PREREG §5.5); ``g_d1_lvl`` = the same AR / sigma_cc,t
  (A1.2 G^lvl, unclipped) and ``car_lvl_10``, the 10:00 rung of the convergence ladder, which A1.2 defines
  as the same ratio (Sum AR from close(t-1) to 10:00 / sigma_cc,t); context: the stock's and SPY's
  close(prev) -> 10:00 move and the first bar's abnormal volume. The inputs (``bars.derive``) are the AR of
  the close(prev) -> 10:00 window and the sigmas of row t (data through t-1).

For the test period the panels are rebuilt from the blinded prices (and, for D1, the blinded 30-minute bars,
asked for first), obtained ONLY through ``lock.read_sealed(..., "reactions")``, which raises ``LockError``
(and logs the attempt) before the NA-11 freeze.
"""

from __future__ import annotations

from typing import Final, cast

import numpy as np
import pandas as pd

from newsaction import calendar, lock
from newsaction.config import SPLIT_ORDER, SplitName, load_splits
from newsaction.lock import LockError
from newsaction.paths import Layout

POINTS: Final = ("D1", "D2")
Z_CLIP: Final = 10.0
D2_COLUMNS: Final = ("g_d2", "g_d2_lvl", "react_r_cc", "react_r_spy_cc", "react_z_vol")
INPUT_COLUMNS: Final = ("session", "symbol_id", "ar_cc", "sigma_cc", "r_cc", "r_spy_cc", "z_vol")
D1_COLUMNS: Final = ("g_d1", "g_d1_lvl", "car_lvl_10", "react_d1_r", "react_d1_r_spy", "react_d1_z_vol")
D1_INPUT_COLUMNS: Final = (
    "session",
    "symbol_id",
    "ar_c10",
    "sigma_on",
    "sigma_30",
    "sigma_cc",
    "r_c10",
    "r_spy_c10",
    "z_vol10",
)


def _d2(panel: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in INPUT_COLUMNS if c not in panel.columns]
    if missing:
        raise ValueError(f"panel lacks columns {missing}")
    out = panel[["session", "symbol_id"]].copy()
    lvl = panel["ar_cc"] / panel["sigma_cc"]
    out["g_d2"] = np.clip(lvl, -Z_CLIP, Z_CLIP)
    out["g_d2_lvl"] = lvl
    out["react_r_cc"] = panel["r_cc"]
    out["react_r_spy_cc"] = panel["r_spy_cc"]
    out["react_z_vol"] = panel["z_vol"]
    return out.reset_index(drop=True)


def _d1(intraday: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in D1_INPUT_COLUMNS if c not in intraday.columns]
    if missing:
        raise ValueError(f"intraday panel lacks columns {missing}")
    out = intraday[["session", "symbol_id"]].copy()
    ar = intraday["ar_c10"]
    scale = (intraday["sigma_on"] ** 2 + intraday["sigma_30"] ** 2).pow(0.5)
    out["g_d1"] = (ar / scale).clip(-Z_CLIP, Z_CLIP)
    lvl = ar / intraday["sigma_cc"]
    out["g_d1_lvl"] = lvl
    out["car_lvl_10"] = lvl
    out["react_d1_r"] = intraday["r_c10"]
    out["react_d1_r_spy"] = intraday["r_spy_c10"]
    out["react_d1_z_vol"] = intraday["z_vol10"]
    return out.reset_index(drop=True)


def build_reactions(
    panel: pd.DataFrame, period: str, point: str, *, layout: Layout | None = None
) -> pd.DataFrame:
    """Observed reaction G (and Call B context) at ``point`` for the rows of ``period``.

    ``panel``: the daily panel for D2, the intraday panel (``bars.derive``) for D1."""
    if point not in POINTS:
        raise ValueError(f"unknown decision point {point!r}; expected one of {POINTS}")
    splits = load_splits().splits
    if period == "test":
        from newsaction.panel.targets import blinded_bars_file, blinded_price_files

        bars = lock.read_sealed(blinded_bars_file(), "reactions", layout=layout) if point == "D1" else None
        prices, total = (lock.read_sealed(n, "reactions", layout=layout) for n in blinded_price_files())
        days = {pd.Timestamp(d) for d in calendar.sessions(splits["test"].start, splits["test"].end)}
        if bars is not None:
            from newsaction.bars import derive  # derive imports this module

            test_intraday = derive.test_intraday_panel(bars, prices, total, layout=layout)
            return _d1(test_intraday[pd.to_datetime(test_intraday["session"]).isin(days)])
        from newsaction.panel import build  # build imports this module

        test_panel = build.test_returns_panel(prices, total, layout=layout)
        return _d2(test_panel[pd.to_datetime(test_panel["session"]).isin(days)])
    names = set(SPLIT_ORDER) - {"test"}
    if period not in names | {"public"}:
        raise ValueError(f"unknown period {period!r}")
    sess = pd.to_datetime(panel["session"])
    if bool((sess >= pd.Timestamp(splits["test"].start)).any()):
        raise LockError(
            "public reactions refuse test-period rows: use period='test' (through newsaction.lock)"
        )
    if period != "public":
        rng = splits[cast(SplitName, period)]
        panel = panel[(sess >= pd.Timestamp(rng.start)) & (sess <= pd.Timestamp(rng.end))]
    return _d1(panel) if point == "D1" else _d2(panel)
