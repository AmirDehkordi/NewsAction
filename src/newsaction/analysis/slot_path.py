"""NA-12 figure data: the day-t 30-minute path of CAR^lvl (PRD NA-12 S2, Figure 1; PREREG A1.2 level units).

For the rows of session t, point k of the path is AR(close(t−1) → close of the (k+1)-th regular 30-minute bar)
/ σ_cc,t: NA-10's D1 return, abnormal return and level unit with the 10:00 price replaced by that bar's
close. ``bars.derive.compute`` runs once per point on prices whose ``p10`` is the bar's close, so the market
and leave-one-out sector terms, the betas and the price basis are NA-10's. Point 0 (the open → 10:00 bar)
is therefore the frozen 10:00 rung ``car_lvl_10``; points 0 … 11 run from 10:00 to 15:30, and the official
close is the C_t rung. A half day stops at its last bar but one.

Descriptive (figure data), not a pre-registered test. ``check_public`` reproduces ``intraday_public``'s
``car_lvl_10`` at point 0 on public sessions before the routine reads any test-period bar.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.bars import BARS_PUBLIC, derive, load_bars_config
from newsaction.bars import basis as bs
from newsaction.bars.fetch import spy_symbol_id
from newsaction.panel import risk
from newsaction.paths import Layout, resolve_layout

N_POINTS: Final = risk.FULL_DAY_MINUTES // 30 - 1  # bars end 10:00 … 15:30 (bars.yaml fixes 30 minutes)
POINT_COLUMNS: Final = tuple(f"car_lvl_b{k}" for k in range(N_POINTS))
CHECK_TOL: Final = 1e-12


class SlotPathError(ValueError):
    """The path does not reproduce the frozen 10:00 rung."""


def slot_prices(bars: pd.DataFrame, qc: pd.DataFrame, k: int) -> pd.DataFrame:
    """NA-10's ``session_prices`` with ``p10`` = the close of regular bar ``k`` (on ATOM's raw level); NaN
    where the session has no bar ``k`` or ``k`` is its last bar (the close)."""
    eod = bs.on_eod_basis(bars, qc)
    key = ["symbol_id", "session"]
    bar = eod.loc[eod["regular"] & (eod["slot"] == k), [*key, "close", "volume"]]
    bar = bar.rename(columns={"close": "p10", "volume": "v10"})
    out = qc.loc[qc["usable"], [*key, "complete", "level_factor", "n_expected"]]
    out = out.merge(bar, on=key, how="left")
    out.loc[out["n_expected"] - 1 <= k, "p10"] = np.nan
    out["p10"] = out["p10"] / out["level_factor"]
    for c in ("first_open", "p1530", "p_pre"):
        out[c] = np.nan
    return out.drop(columns=["level_factor", "n_expected"]).reset_index(drop=True)


def path(daily: pd.DataFrame, bars: pd.DataFrame, ref: pd.DataFrame, spy_id: int) -> pd.DataFrame:
    """(session, symbol_id, car_lvl_b0 … b11) for the ``daily`` rows (``bars.derive.PANEL_COLUMNS``) from
    ``bars`` (``bars.derive.BAR_READ``) and the EOD reference ``ref`` (``bars.basis.reference_prices``)."""
    qc = bs.session_qc(bars, ref)
    eod = ref.rename(columns={"eod_open": "open", "eod_close": "close"})
    first = slot_prices(bars, qc, 0)
    symbols = sorted(int(x) for x in set(first["symbol_id"]) - {spy_id})
    out: pd.DataFrame | None = None
    for k in range(N_POINTS):
        px = first if k == 0 else slot_prices(bars, qc, k)
        res = derive.compute(daily, px, derive.spy_frame(px, eod, daily, spy_id), symbols)
        col = pd.DataFrame(
            {
                "session": res["session"],
                "symbol_id": res["symbol_id"],
                POINT_COLUMNS[k]: res["ar_c10"] / res["sigma_cc"],
            }
        )
        out = col if out is None else out.merge(col, on=["session", "symbol_id"], how="outer")
    assert out is not None
    return out.sort_values(["session", "symbol_id"]).reset_index(drop=True)


def public_inputs(
    sessions: Sequence[date], layout: Layout | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, int]:
    """(daily rows of ``sessions``, public bars, EOD reference, SPY's id), read as NA-10's public route
    reads them."""
    lay = resolve_layout(layout)
    full = io.read_parquet("panel/panel_public.parquet", columns=list(derive.PANEL_COLUMNS), layout=lay)
    want = set(sessions)
    daily = full.loc[[d in want for d in full["session"]]].reset_index(drop=True)
    bars = io.read_parquet(BARS_PUBLIC, columns=list(derive.BAR_READ), layout=lay)
    return daily, bars, bs.reference_prices(lay), spy_symbol_id(lay)


def check_public(sessions: Sequence[date], layout: Layout | None = None) -> dict[str, Any]:
    """Point 0 on public ``sessions`` must equal ``intraday_public``'s frozen ``car_lvl_10``."""
    lay = resolve_layout(layout)
    daily, bars, ref, spy_id = public_inputs(sessions, lay)
    got = path(daily, bars, ref, spy_id)
    ref10 = io.read_parquet(
        "panel/intraday_public.parquet", columns=["session", "symbol_id", "car_lvl_10"], layout=lay
    )
    m = got.merge(ref10, on=["session", "symbol_id"], how="inner", validate="one_to_one")
    both = m.dropna(subset=["car_lvl_b0", "car_lvl_10"])
    diff = float((both["car_lvl_b0"] - both["car_lvl_10"]).abs().max()) if len(both) else float("nan")
    one_sided = int(m["car_lvl_b0"].isna().ne(m["car_lvl_10"].isna()).sum())
    if not len(both) or not diff <= CHECK_TOL or one_sided:
        raise SlotPathError(f"point 0 differs from car_lvl_10: max {diff}, {one_sided} rows NaN on one side")
    filled = {c: int(got[c].notna().sum()) for c in POINT_COLUMNS}
    return {
        "sessions": len(set(sessions)),
        "rows": len(m),
        "rows_compared": len(both),
        "max_abs_diff_point0": diff,
        "non_missing": filled,
        "bar_minutes": load_bars_config().vendor.bar_minutes,
    }
