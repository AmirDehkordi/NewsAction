"""Observed reactions G at the decision points (PREREG §5.5, Amendment A1.2; PRD NA-01 S6).

Hashed at the NA-11 freeze (PREREG §4.4).

- D2 (after close(t)): ``g_d2`` = z_cc,t (clipped at +-10, as z_cc); ``g_d2_lvl`` = AR_cc,t / sigma_cc,t
  (A1.2 level units, unclipped); context for Call B's ``reaction_so_far``: the stock's and SPY's
  close-to-close move and z_vol,t.
- D1 (10:00 ET) needs 30-min bars: NotImplementedError until NA-10 adds them.

For the test period the panel is rebuilt from the blinded prices, obtained ONLY through
``lock.read_sealed(..., "reactions")``, which raises ``LockError`` (and logs the attempt) before the
NA-11 freeze.
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


def build_reactions(
    panel: pd.DataFrame, period: str, point: str, *, layout: Layout | None = None
) -> pd.DataFrame:
    """Observed reaction G (and Call B context) at ``point`` for the rows of ``period``."""
    if point not in POINTS:
        raise ValueError(f"unknown decision point {point!r}; expected one of {POINTS}")
    splits = load_splits().splits
    if period == "test":
        from newsaction.panel.targets import blinded_price_files

        prices, total = (lock.read_sealed(n, "reactions", layout=layout) for n in blinded_price_files())
        if point == "D1":
            raise NotImplementedError("D1 reactions need the NA-10 30-min bars")
        from newsaction.panel import build  # build imports this module

        test_panel = build.test_returns_panel(prices, total, layout=layout)
        days = {pd.Timestamp(d) for d in calendar.sessions(splits["test"].start, splits["test"].end)}
        return _d2(test_panel[pd.to_datetime(test_panel["session"]).isin(days)])
    if point == "D1":
        raise NotImplementedError("D1 reactions need the NA-10 30-min bars")
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
    return _d2(panel)
