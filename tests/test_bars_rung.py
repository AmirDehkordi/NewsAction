"""NA-10 AC6 (PREREG A1.2): the 10:00 rung of the convergence ladder and G^lvl at D1, recomputed by hand.

For 10 public D0 events (seed 2026) the test rebuilds, without ``bars.derive``: P_10:00 of the stock, of SPY
and of every same-sector peer from the raw bars (close of the first regular bar × the session's basis factor
÷ NA-01's level factor), close(prev) → 10:00 returns from the EOD open and r_on, the leave-one-company-out
sector mean (member representative classes, ≥ 5), AR with the panel's β of row t (through t−1), and
CAR^lvl_10 = G^lvl_D1 = AR / σ_cc,t. Both equal the stored columns to 1e-9; no 2026 value exists yet.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pyarrow.parquet as pq
import pytest

from newsaction import io
from newsaction.bars import BARS_PUBLIC, BARS_QC, INTRADAY_PUBLIC
from newsaction.config import load_splits
from newsaction.paths import ROOT

TOL = 1e-9


def _need(*rels: str) -> None:
    for rel in rels:
        if not (ROOT / "work" / rel).is_file():
            pytest.skip(f"work/{rel} is absent (run newsaction.bars.fetch and derive)")


def test_ten_events_recomputed_from_bars() -> None:
    _need(BARS_PUBLIC, BARS_QC, INTRADAY_PUBLIC)
    intra = io.read_parquet(INTRADAY_PUBLIC, columns=["session", "symbol_id", "car_lvl_10", "g_d1_lvl"])
    assert max(intra["session"]) < load_splits().splits["test"].start
    ev = io.read_parquet("events/events_d0.parquet", columns=["session", "symbol_id", "split"])
    ev = ev.loc[ev["split"].isin(["train", "val_a", "val_b"])].merge(intra, on=["session", "symbol_id"])
    ev = ev.loc[ev["car_lvl_10"].notna()].sample(10, random_state=2026)
    days = sorted(set(ev["session"]))
    cols = [
        "session",
        "symbol_id",
        "company_id",
        "member",
        "is_rep",
        "sector",
        "raw_open",
        "r_on",
        "r_spy_on",
    ]
    pan = io.read_parquet("panel/panel_public.parquet", columns=[*cols, "beta_m", "beta_s", "sigma_cc"])
    pan = pan.loc[pan["session"].isin(days)]
    bars = pq.read_table(
        ROOT / "work" / BARS_PUBLIC,
        columns=["symbol_id", "session", "slot", "close"],
        filters=[("slot", "==", 0), ("session", "in", days)],
    ).to_pandas()
    qc = io.read_parquet(BARS_QC, columns=["symbol_id", "session", "factor", "usable", "level_factor"])
    p10 = bars.merge(qc.loc[qc["usable"]], on=["symbol_id", "session"])
    p10 = p10.assign(p10=p10["close"] * p10["factor"] / p10["level_factor"]).set_index(
        ["symbol_id", "session"]
    )["p10"]
    raw = io.read_parquet(
        "snapshot/prices_raw.parquet", columns=["symbol_id", "trade_date", "open"]
    ).set_index(["symbol_id", "trade_date"])["open"]
    sym = io.read_parquet("snapshot/symbols.parquet", columns=["symbol_id", "ticker"])
    spy = int(sym.loc[sym["ticker"] == "SPY", "symbol_id"].iloc[0])
    for rec in ev.to_dict("records"):
        t: date = rec["session"]
        day = pan.loc[pan["session"] == t].set_index("symbol_id")
        me = day.loc[rec["symbol_id"]]

        def r_c10(sid: int, r_on: float, t: date = t) -> float:
            return float((1.0 + r_on) * p10[(sid, t)] / raw[(sid, t)] - 1.0)

        r = r_c10(rec["symbol_id"], me["r_on"])
        r_m = (1.0 + me["r_spy_on"]) * p10[(spy, t)] / raw[(spy, t)] - 1.0
        peers = day.loc[
            day["member"]
            & day["is_rep"]
            & (day["sector"] == me["sector"])
            & (day["company_id"] != me["company_id"])
        ]
        vals = [
            r_c10(int(s), float(p["r_on"]))
            for s, p in peers.iterrows()
            if (int(s), t) in p10.index and np.isfinite(p["r_on"])
        ]
        assert len(vals) >= 5
        r_s = float(np.mean(vals))
        ar = r - me["beta_m"] * r_m - me["beta_s"] * (r_s - r_m)
        lvl = ar / me["sigma_cc"]
        assert abs(lvl - rec["car_lvl_10"]) <= TOL, (rec, lvl)
        assert abs(lvl - rec["g_d1_lvl"]) <= TOL
