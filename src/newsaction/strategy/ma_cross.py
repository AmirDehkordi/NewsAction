"""Exploratory: news and a moving-average cross (operator request after unblinding, NA-13 preamble item 9;
PREREG §15 NA-13 row (xiii)). Run after the pre-registered strategies; no hypothesis, no claim; every variant
is a "strategy" row of ``ledgers/trials.jsonl`` and counts in the DSR.

    uv run python -m newsaction.strategy.ma_cross

Design (fixed by the operator before any test result; the operator's assistant ran it on validation only):

- **Crosses.** MA20 and MA50 of the adjusted close over each symbol's rows of the long panel (members and the
  post-exit rows, ``panel_public`` then ``strategy/market_test``); direction +1 when MA20 crosses above MA50
  at the close of t (MA20_{t−1} ≤ MA50_{t−1}, MA20_t > MA50_t), −1 when it crosses below; members at t.
- **Outcome.** direction × Σ ar_cc over the symbol's next 5 and next 20 rows (t+1..t+k; complete windows
  inside the period).
- **Groups.** The symbol's latest D0 event in sessions t−2..t: "agree" if sign(N̂_W0) = direction, else
  "disagree" (Laya-Fin and d1-ultra separately); "none" if it has no D0 event there; "all".
- **Statistic.** The mean over cross days of each day's mean signed return per group (bp), with the
  Newey–West t at k − 1 lags (``analysis.metrics.nw_t``).
- **Periods.** Validation 2025-07-01 … 2025-12-31 (val-A and val-B; it reproduces the operator's numbers)
  and the test period, once, with the identical code.
- **Tradable version.** Fade the no-news crosses: on each cross day, short the up-crosses and buy the
  down-crosses with weights −direction/N (N crosses that day), β-hedged with SPY; decision at close(t), entry
  at the next open, exit at C_{t+5} (``portfolios``' D2 timing); 10 bp per side (5 and 20 reported). Placebo:
  100 random directions per cross (seeds 2027–2126), the same weights, hedge and costs.

Writes ``artifacts/NA-13/results/ma_cross.json`` and ``work/strategy/ma_cross_books.parquet``.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.analysis import metrics as mx
from newsaction.config import load_splits
from newsaction.paths import Layout, resolve_layout
from newsaction.strategy import costs as cs
from newsaction.strategy import market as mk
from newsaction.strategy import portfolios as pf
from newsaction.strategy import run

RESULT: Final = "ma_cross.json"
OUT_BOOKS: Final = "strategy/ma_cross_books.parquet"
PERIODS: Final[dict[str, tuple[str, ...]]] = {"validation": ("val_a", "val_b"), "test": ("test",)}
TRIAL_SPLIT: Final = {"validation": "val_b", "test": "test"}  # the ledger takes one split name
HORIZONS: Final = (5, 20)
MODELS: Final = ("laya_fin", "d1_ultra")
LOOKBACK: Final = 2  # D0 events in sessions t−2..t
SHORT, LONG = mk.MA_SHORT, mk.MA_LONG
BOOK_EXIT: Final = "close_t+5"
BOOK_BP: Final = 10.0
GROUPS: Final = ("all", "none", *[f"{g}_{m}" for m in MODELS for g in ("agree", "disagree")])


def _span(period: str) -> tuple[date, date]:
    sp = load_splits().splits
    names = PERIODS[period]
    return sp[names[0]].start, sp[names[-1]].end  # type: ignore[index]


def long_rows(period: str, layout: Layout | None = None) -> pd.DataFrame:
    """The long panel's rows up to the period's end (``panel_public``; for the test, then ``market_test``)."""
    cols = ["session", "symbol_id", "company_id", "member", "adj_close", "ar_cc"]
    p = io.read_parquet(mk.PUBLIC_PANEL, columns=cols, layout=layout)
    if period == "test":
        t = io.read_parquet(mk.TEST_OUT, columns=cols, layout=layout)
        p = pd.concat([p, t], ignore_index=True)
    p["session"] = pd.to_datetime(p["session"]).dt.date
    return p.sort_values(["symbol_id", "session"]).reset_index(drop=True)


def crosses(rows: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Member crosses in [start, end] with the signed outcomes ``y5``, ``y20`` (bp of Σ ar_cc)."""
    p = rows.copy()
    g = p.groupby("symbol_id")["adj_close"]
    p["ma20"] = g.transform(lambda s: s.rolling(SHORT, min_periods=SHORT).mean())
    p["ma50"] = g.transform(lambda s: s.rolling(LONG, min_periods=LONG).mean())
    p["ma20_prev"] = p.groupby("symbol_id")["ma20"].shift(1)
    p["ma50_prev"] = p.groupby("symbol_id")["ma50"].shift(1)
    for k in HORIZONS:
        p[f"sum{k}"] = p.groupby("symbol_id")["ar_cc"].transform(
            lambda s, k=k: s.shift(-1).rolling(k, min_periods=k).sum().shift(-(k - 1))
        )
    inside = (p["session"] >= start) & (p["session"] <= end)
    up = (p["ma20_prev"] <= p["ma50_prev"]) & (p["ma20"] > p["ma50"])
    dn = (p["ma20_prev"] >= p["ma50_prev"]) & (p["ma20"] < p["ma50"])
    c = p.loc[inside & p["member"].astype(bool) & (up | dn)].copy()
    c["direction"] = np.where(up[c.index], 1, -1)
    for k in HORIZONS:
        c[f"y{k}"] = c["direction"] * c[f"sum{k}"] * 1e4
    return c.reset_index(drop=True)


def with_news(c: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    """Each cross's latest D0 event of its symbol in t−2..t and whether sign(N̂) agrees with the direction."""
    out = c.copy()
    if out.empty:
        raise ValueError("no crosses")
    sessions = calendar.sessions(min(out["session"]), max(out["session"]))
    first = calendar.sessions(pf.session_after(sessions[0], -LOOKBACK), sessions[0])
    window = sorted({*first, *sessions})
    pos = {d: i for i, d in enumerate(window)}
    for m in MODELS:
        f = io.read_parquet(
            run.FRAME.format(point="d0", model=m), columns=["symbol_id", "session", "a0_n_hat"], layout=layout
        )
        f["session"] = pd.to_datetime(f["session"]).dt.date
        f = f.loc[f["session"].isin(pos.keys())].sort_values("session")
        latest: dict[tuple[int, date], float] = {}
        for sym, d, n in zip(f["symbol_id"], f["session"], f["a0_n_hat"], strict=True):
            i = pos[d]
            for j in range(LOOKBACK + 1):
                if i + j < len(window):
                    latest[(int(sym), window[i + j])] = float(n)  # later events overwrite earlier ones
        n_hat = [
            latest.get((int(s), d), np.nan) for s, d in zip(out["symbol_id"], out["session"], strict=True)
        ]
        out[f"n_hat_{m}"] = n_hat
        has = [((int(s), d) in latest) for s, d in zip(out["symbol_id"], out["session"], strict=True)]
        out[f"news_{m}"] = has
        out[f"agree_{m}"] = np.sign(out[f"n_hat_{m}"]) == out["direction"]
    if not (out[f"news_{MODELS[0]}"] == out[f"news_{MODELS[1]}"]).all():
        raise ValueError("the two models' D0 event sets differ")
    out["news"] = out[f"news_{MODELS[0]}"]
    return out


def group_masks(c: pd.DataFrame) -> dict[str, pd.Series]:
    masks = {"all": pd.Series(True, index=c.index), "none": ~c["news"]}
    for m in MODELS:
        masks[f"agree_{m}"] = c["news"] & c[f"agree_{m}"]
        masks[f"disagree_{m}"] = c["news"] & ~c[f"agree_{m}"]
    return masks


def statistics(c: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for g, mask in group_masks(c).items():
        for k in HORIZONS:
            x = c.loc[mask].dropna(subset=[f"y{k}"])
            day = x.groupby("session")[f"y{k}"].mean()
            mu, t, n = mx.nw_t(day, k - 1)
            out[f"{g}|{k}"] = {
                "group": g,
                "horizon": k,
                "mean_bp": mu,
                "nw_t": t,
                "n_days": n,
                "n_crosses": len(x),
            }
    return out


def fade_book(
    c: pd.DataFrame, period: str, layout: Layout | None = None, seeds: int = run.PLACEBO_SEEDS
) -> dict[str, Any]:
    """The tradable no-news fade (module docstring) with its placebo."""
    start, end = _span(period)
    sessions = calendar.sessions(start, end)
    rel = mk.TEST_OUT if period == "test" else mk.PUBLIC_OUT
    mkt = io.read_parquet(rel, layout=layout)
    mkt["session"] = pd.to_datetime(mkt["session"]).dt.date
    mkt = mkt.loc[[start <= d <= end for d in mkt["session"]]].reset_index(drop=True)
    ev = c.loc[~c["news"], ["session", "symbol_id", "company_id", "direction"]].copy()
    ev["event_id"] = [f"MA:{s}:{d}" for s, d in zip(ev["symbol_id"], ev["session"], strict=True)]
    ev["tier"] = "all"
    u = pf.build_universe(
        ev[["event_id", "session", "symbol_id", "company_id", "tier"]], mkt, "D2", BOOK_EXIT, sessions
    )
    pf.check_timing(u.events.assign(cross_utc=u.events["session"].map(calendar.close_utc)), ["cross_utc"])
    cohort = u.events["cohort"].to_numpy(dtype=np.int64)
    direction = ev.set_index("event_id")["direction"].reindex(u.events["event_id"]).to_numpy(dtype=float)
    n_c = np.bincount(cohort, minlength=u.n_cohorts).astype(float)[cohort]
    w = -direction / n_c
    d = pf.evaluate(u, w)
    s = pf.summary(d.gross[0], d.turnover[0], d.active[0])
    capy = pf.capacity_of(u, w)
    ids = u.events["event_id"].tolist()
    wp = np.zeros((seeds, len(ids)))
    for i in range(seeds):
        sign = np.where(pf.draws(ids, pf.SEED + 1 + i) > 0.5, 1.0, -1.0)
        wp[i] = -sign / n_c
    dp = pf.evaluate(u, wp)
    pl = {f"{int(bp)}": pf.sharpe_rows(cs.net(dp.gross, dp.turnover, bp)) for bp in cs.LEVELS_BP}
    rec: dict[str, Any] = {"period": period, "exit": BOOK_EXIT, **u.counts, **s}
    rec.update({f"capacity_{k}": v for k, v in asdict(capy).items()})
    rec["placebo_pct_gross"] = run.percentile(s["sharpe_gross"], pf.sharpe_rows(dp.gross))
    for tag, null in pl.items():
        rec[f"placebo_pct_net_{tag}"] = run.percentile(s[f"sharpe_net_{tag}"], null)
        rec[f"placebo_median_net_{tag}"] = float(np.median(null))
    rec["n_positions"] = len(ids)
    daily = pd.DataFrame(
        {
            "period": period,
            "session": u.sessions,
            "gross": d.gross[0],
            "turnover": d.turnover[0],
            "active": d.active[0],
            **{f"net_{int(bp)}": cs.net(d.gross[0], d.turnover[0], bp) for bp in cs.LEVELS_BP},
        }
    )
    return {"summary": rec, "daily": daily}


def build(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    t0 = time.time()
    out: dict[str, Any] = {"design": "PREREG §15 NA-13 row (xiii); module docstring", "periods": {}}
    books = []
    for period in PERIODS:
        start, end = _span(period)
        c = with_news(crosses(long_rows(period, lay), start, end), lay)
        book = fade_book(c, period, lay)
        books.append(book["daily"])
        out["periods"][period] = {
            "span": [str(start), str(end)],
            "n_crosses": len(c),
            "n_up": int((c["direction"] > 0).sum()),
            "n_no_news": int((~c["news"]).sum()),
            "statistics": statistics(c),
            "fade_no_news": book["summary"],
        }
    io.write_parquet(
        pd.concat(books, ignore_index=True),
        OUT_BOOKS,
        producer=run.CHUNK,
        description="NA-13 exploratory (operator item 9): the no-news MA20/MA50 cross fade, daily gross, "
        "turnover and net returns at 5/10/20 bp, validation and test",
        layout=lay,
    )
    out["seconds"] = round(time.time() - t0, 1)
    run.write_json(lay, RESULT, out)
    return out


def trial_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Every evaluated variant of the add-on: the group statistics and the tradable book, per period."""
    rows = []
    for period, r in result["periods"].items():
        split = TRIAL_SPLIT[period]
        span = "val_a+val_b" if period == "validation" else period
        for key, s in r["statistics"].items():
            rows.append(
                {
                    "name": f"exploratory|ma_cross|{key}|{span}",
                    "split": split,
                    "metric": "mean_signed_ar_cc_bp",
                    "value": s["mean_bp"],
                    "params": {"group": s["group"], "horizon": s["horizon"], "period": span},
                }
            )
        b = r["fade_no_news"]
        rows.append(
            {
                "name": f"exploratory|ma_cross|fade_no_news|{BOOK_EXIT}|{span}",
                "split": split,
                "metric": "sharpe_net_10",
                "value": b["sharpe_net_10"],
                "params": {"book": "fade_no_news", "exit": BOOK_EXIT, "period": span, "bp": BOOK_BP},
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    _ = list(sys.argv[1:] if argv is None else argv)
    out = build()
    for period, r in out["periods"].items():
        print(
            period,
            r["n_crosses"],
            {k: (round(v["mean_bp"], 1), round(v["nw_t"], 2)) for k, v in r["statistics"].items()},
        )
        b = r["fade_no_news"]
        print(
            "  fade",
            {k: b[k] for k in ("sharpe_gross", "sharpe_net_10", "placebo_pct_net_10", "n_positions")},
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
