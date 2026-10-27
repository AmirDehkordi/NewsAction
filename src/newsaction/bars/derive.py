"""NA-10 S5: intraday prices, abnormal returns and σ for D1 (PRD NA-10 S5; PREREG §2.5, §5.2–5.6, A1.2).

    uv run python -m newsaction.bars.derive

**Prices** of each symbol-session (``session_prices``), from the bars of usable sessions on the EOD basis
(``basis``), divided by NA-01's level factor so that they sit on ATOM's raw level, like the panel's raw open
and close. Bars are located by their slot after the open (``calendar``), never by clock time (CLAUDE.md A1):
- ``p10`` (P_10:00): close of the first regular bar (the open to 10:00), the D1 decision and entry price;
  ``v10`` is that bar's volume;
- ``p1530`` (P_15:30): close of the bar that ends 30 minutes before a full day's close (none on a half day);
- ``p_pre``: close of the bar that ends at the open (the last pre-market bar), served with ``extended=true``.

**Returns** of session t, with the official open O_t and close C_t from EOD and r_on,t from NA-01:
close(prev) → 10:00 ``r_c10`` = (1 + r_on,t)·P_10:00 / O_t − 1 (= P_10:00·f_t / AC_{t−1} − 1);
open → 10:00 ``r_o10`` = P_10:00 / O_t − 1 (the first 30 minutes); 10:00 → close ``r_10c`` =
C_t / P_10:00 − 1. The same for SPY (EOD open and close from the snapshot) and for the sector: the
leave-one-company-out mean over the other member companies' representative classes of the same GICS sector
with bars that session, at least 5 (PREREG §5.2; NA-01's pool and sector, ``panel.sector``).
AR_x = r_x − β_m·r_SPY,x − β_s·(r_sec,x − r_SPY,x) with NA-01's β of row t (through t−1).

**σ** (PREREG §5.4, through t−1): ``sigma_30`` = 1.4826·MAD of AR_o10 over the 126 sessions ending t−1
(≥ 60) and ``sigma_rest`` of AR_10c, each floored at the day's cross-sectional 10th percentile among members;
on a half day ``sigma_rest`` is then scaled by √((minutes − 30)/(390 − 30)), as σ_id is by √(minutes/390).
``logv10_med60`` / ``logv10_mad60``: median and 1.4826·MAD of log first-bar volume over the 60 sessions ending
t−1 (≥ 40), and ``z_vol10`` the session's first-bar abnormal volume ("volume vs normal for the time of day").

G_D1, G^lvl, the 10:00 rung (``panel.reactions``) and the D1 targets (``panel.targets``) come from the code
hashed at the NA-11 freeze. Output: ``work/panel/intraday_public.parquet`` (sessions ≤ val-B end) and
``work/bars30/session_qc.parquet``. ``test_intraday_panel`` is the post-freeze route for the test period:
``reactions`` and ``targets`` call it with frames they obtained from ``newsaction.lock``.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.bars import (
    BARS_PUBLIC,
    BARS_QC,
    INTRADAY_PUBLIC,
    INTRADAY_SPY_PUBLIC,
    PRODUCER,
    load_bars_config,
)
from newsaction.bars import basis as bs
from newsaction.bars.fetch import public_end, spy_symbol_id
from newsaction.panel import reactions, risk, sector, targets
from newsaction.panel.grid import session_index, to_long, wide
from newsaction.paths import Layout, resolve_layout

PANEL_COLUMNS: Final = (
    "session",
    "symbol_id",
    "company_id",
    "split",
    "member",
    "is_rep",
    "sector",
    "half_day",
    "raw_open",
    "raw_close",
    "r_on",
    "r_spy_on",
    "ar_cc",
    "beta_m",
    "beta_s",
    "sigma_on",
    "sigma_cc",
)
WINDOWS: Final = ("c10", "o10", "10c")
PRICE_COLUMNS: Final = ("first_open", "p10", "v10", "p1530", "p_pre")
BAR_READ: Final = ["symbol_id", "session", "slot", "regular", "open", "high", "low", "close", "volume"]


def session_prices(bars: pd.DataFrame, qc: pd.DataFrame) -> pd.DataFrame:
    """(symbol_id, session, first_open, p10, v10, p1530, p_pre, complete) of usable sessions, on ATOM's
    raw level."""
    eod = bs.on_eod_basis(bars, qc)
    key = ["symbol_id", "session"]
    first = eod.loc[eod["regular"] & (eod["slot"] == 0), [*key, "open", "close", "volume"]]
    first = first.rename(columns={"open": "first_open", "close": "p10", "volume": "v10"})
    n_full = risk.FULL_DAY_MINUTES // load_bars_config().vendor.bar_minutes
    late = eod.loc[eod["regular"] & (eod["slot"] == n_full - 2), [*key, "close"]].rename(
        columns={"close": "p1530"}
    )
    pre = eod.loc[eod["slot"] == -1, [*key, "close"]].rename(columns={"close": "p_pre"})
    out = qc.loc[qc["usable"], [*key, "complete", "level_factor", "n_expected"]]
    out = out.merge(first, on=key, how="left").merge(late, on=key, how="left").merge(pre, on=key, how="left")
    out.loc[out["n_expected"] != n_full, "p1530"] = np.nan  # a half day has no 15:30
    for c in ("first_open", "p10", "p1530", "p_pre"):
        out[c] = out[c] / out["level_factor"]
    return out.drop(columns=["level_factor", "n_expected"]).reset_index(drop=True)


def spy_frame(prices: pd.DataFrame, eod: pd.DataFrame, daily: pd.DataFrame, spy_id: int) -> pd.DataFrame:
    """Per session: SPY's EOD open and close, r_on (NA-01) and its intraday prices."""
    px = eod.loc[eod["symbol_id"] == spy_id, ["session", "open", "close"]]
    on = daily[["session", "r_spy_on"]].drop_duplicates("session")
    bars = prices.loc[prices["symbol_id"] == spy_id, ["session", "p10"]]
    return px.merge(on, on="session", how="left").merge(bars, on="session", how="left")


def spy_returns(spy: pd.DataFrame) -> pd.DataFrame:
    """SPY's three intraday returns per session (the market factor of every window)."""
    out = spy.rename(columns={"r_spy_on": "r_on"}).copy()
    out["r_c10"] = (1.0 + out["r_on"]) * out["p10"] / out["open"] - 1.0
    out["r_o10"] = out["p10"] / out["open"] - 1.0
    out["r_10c"] = out["close"] / out["p10"] - 1.0
    return out.sort_values("session").reset_index(drop=True)


def _object_grid(
    rows: pd.DataFrame, col: str, sessions: pd.DatetimeIndex, symbols: list[int]
) -> pd.DataFrame:
    g = rows.assign(session=pd.to_datetime(rows["session"])).pivot(
        index="session", columns="symbol_id", values=col
    )
    return g.reindex(index=sessions, columns=symbols)


def compute(daily: pd.DataFrame, prices: pd.DataFrame, spy: pd.DataFrame, symbols: list[int]) -> pd.DataFrame:
    """Intraday returns, AR, σ and the volume baseline for the ``daily`` rows of ``symbols`` (pure)."""
    rows = daily.loc[daily["symbol_id"].isin(symbols)].merge(prices, on=["symbol_id", "session"], how="left")
    sess = sorted(set(rows["session"]))
    sessions = session_index(sess[0], sess[-1])

    def g(col: str) -> pd.DataFrame:
        return wide(rows, col, sessions, symbols)

    ro, rc, r_on, p10 = g("raw_open"), g("raw_close"), g("r_on"), g("p10")
    r = {"c10": (1.0 + r_on) * p10 / ro - 1.0, "o10": p10 / ro - 1.0, "10c": rc / p10 - 1.0}
    sr = spy_returns(spy)
    s = sr.assign(session=pd.to_datetime(sr["session"])).set_index("session").reindex(sessions)
    r_m = {x: s[f"r_{x}"] for x in WINDOWS}
    member = _object_grid(rows, "member", sessions, symbols).astype("float64").fillna(0.0).astype(bool)
    pool = member & _object_grid(rows, "is_rep", sessions, symbols).astype("float64").fillna(0.0).astype(bool)
    sec = _object_grid(rows, "sector", sessions, symbols)
    company = rows.drop_duplicates("symbol_id").set_index("symbol_id")["company_id"]
    beta_m, beta_s = g("beta_m"), g("beta_s")
    frames: dict[str, pd.DataFrame] = {"p_open": ro, "p_close": rc}
    for x in WINDOWS:
        r_sec, n_sec = sector.loo_sector_return(r[x], sec, pool, company)
        rm = pd.DataFrame(np.broadcast_to(r_m[x].to_numpy()[:, None], r[x].shape), sessions, symbols)
        frames[f"r_{x}"], frames[f"r_spy_{x}"], frames[f"r_sec_{x}"] = r[x], rm, r_sec
        frames[f"ar_{x}"] = risk.abnormal(r[x], r_m[x], r_sec, beta_m, beta_s)
        if x == "c10":
            frames["r_sec_n10"] = n_sec
    frames["sigma_30"] = risk.floor_sigma(risk.robust_sigma(frames["ar_o10"]), member)
    rest = pd.Series({ts: float(calendar.session_minutes(ts.date())) for ts in sessions}) - 30.0
    scale = np.sqrt(rest / (risk.FULL_DAY_MINUTES - 30.0))
    frames["sigma_rest"] = risk.floor_sigma(risk.robust_sigma(frames["ar_10c"]), member).mul(scale, axis=0)
    v10 = g("v10")
    med, mad = risk.volume_baseline(v10)
    frames.update(logv10_med60=med, logv10_mad60=mad, z_vol10=risk.z_volume(v10, med, mad))
    for c in PRICE_COLUMNS:
        frames[c] = g(c)
    present = wide(rows.assign(one=1.0), "one", sessions, symbols).notna()
    long = to_long(frames, present)
    long["session"] = pd.to_datetime(long["session"]).dt.date
    keep = [
        "session",
        "symbol_id",
        "company_id",
        "split",
        "member",
        "is_rep",
        "half_day",
        "complete",
        "sigma_on",
        "sigma_cc",
    ]
    out = rows[keep].merge(long, on=["session", "symbol_id"], how="left")
    out = out.rename(columns={"complete": "bars_complete"})
    out["bars_complete"] = out["bars_complete"].fillna(False).astype(bool)
    out["bars_d1"] = out["p10"].notna()
    return out.sort_values(["session", "symbol_id"]).reset_index(drop=True)


def build_public(
    layout: Layout | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """(intraday_public, session_qc, intraday_spy_public, notes): the public route (no test-period row is
    read or written). SPY's series starts with the panel (its r_on), which gives its D1 history."""
    lay = resolve_layout(layout)
    bars = io.read_parquet(BARS_PUBLIC, columns=BAR_READ, layout=lay)
    ref = bs.reference_prices(lay)
    qc = bs.session_qc(bars, ref)
    prices = session_prices(bars, qc)
    del bars
    spy_id = spy_symbol_id(lay)
    full = io.read_parquet("panel/panel_public.parquet", columns=list(PANEL_COLUMNS), layout=lay)
    lo = load_bars_config().fetch.stock_start
    daily = full.loc[[lo <= d <= public_end() for d in full["session"]]].reset_index(drop=True)
    eod = ref.rename(columns={"eod_open": "open", "eod_close": "close"})
    spy = spy_frame(prices, eod, full, spy_id)
    spy_out = spy_returns(spy)
    in_public = spy_out["r_on"].notna() & (spy_out["session"] <= public_end())
    spy_out = spy_out.loc[in_public].reset_index(drop=True)
    spy_out = spy_out.rename(columns={c: f"spy_{c}" for c in ("open", "close", "p10")})
    spy_out = spy_out.rename(columns={c: f"r_spy_{c[2:]}" for c in ("r_on", "r_c10", "r_o10", "r_10c")})
    symbols = sorted(int(x) for x in set(prices["symbol_id"]) - {spy_id})
    out = compute(daily, prices, spy, symbols)
    rx = reactions.build_reactions(out, "public", "D1", layout=lay)
    tg = targets.build_d1_targets(daily, out, "public", layout=lay)
    out = out.merge(rx, on=["session", "symbol_id"], how="left").merge(
        tg.drop(columns=["split"]), on=["session", "symbol_id"], how="left"
    )
    notes = {
        "basis": qc["basis"].value_counts().to_dict(),
        "symbols": len(symbols),
        "rows": len(out),
        "rows_with_bars": int(out["bars_d1"].sum()),
        "spy_sessions": len(spy_out),
    }
    return out, qc, spy_out, notes


def test_intraday_panel(
    bars: pd.DataFrame, prices: pd.DataFrame, total: pd.DataFrame, *, layout: Layout | None = None
) -> pd.DataFrame:
    """Intraday panel over public + test sessions with the blinded bars and prices added.

    Only ``reactions.build_reactions(..., "test", "D1")`` and ``targets.build_d1_targets(..., "test")`` call
    this, with frames they obtained from ``newsaction.lock`` (after the freeze / unblinding)."""
    from newsaction.panel import build

    lay = resolve_layout(layout)
    daily = build.test_returns_panel(prices, total, layout=lay)
    ref = bs.reference_prices(lay, extra=prices)
    allbars = pd.concat(
        [io.read_parquet(BARS_PUBLIC, columns=BAR_READ, layout=lay), bars[BAR_READ]], ignore_index=True
    )
    qc = bs.session_qc(allbars, ref)
    px = session_prices(allbars, qc)
    spy_id = spy_symbol_id(lay)
    spy = spy_frame(px, ref.rename(columns={"eod_open": "open", "eod_close": "close"}), daily, spy_id)
    lo = load_bars_config().fetch.stock_start
    daily = daily.loc[[d >= lo for d in daily["session"]]].reset_index(drop=True)
    return compute(daily, px, spy, sorted(int(x) for x in set(px["symbol_id"]) - {spy_id}))


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    out, qc, spy, notes = build_public(lay)
    if max([*out["session"], *qc["session"], *spy["session"]]) > public_end():
        raise ValueError("an NA-10 public file would contain a test-period session")
    for df, rel, desc in (
        (
            spy,
            INTRADAY_SPY_PUBLIC,
            "NA-10 S5: SPY's EOD open and close, P_10:00 and its intraday returns (public)",
        ),
        (
            qc,
            BARS_QC,
            "NA-10 S4: per symbol-session bar counts and first-bar open vs the EOD raw open (public)",
        ),
        (
            out,
            INTRADAY_PUBLIC,
            "NA-10 S5: D1 intraday prices, AR, sigma_30/sigma_rest, G_D1, G^lvl, 10:00 rung, y1",
        ),
    ):
        entry = io.write_parquet(
            df.reset_index(drop=True), rel, producer=PRODUCER, description=desc, layout=lay
        )
        notes[rel] = {"rows": entry["rows"], "sha256": entry["sha256"]}
    return notes


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="newsaction.bars.derive", description=__doc__).parse_args(argv)
    t0 = time.time()
    notes = run()
    rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS
    print(json.dumps(notes, indent=1, default=str))
    print(f"derive: {time.time() - t0:,.0f}s, peak RSS {rss_gb:.1f} GB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
