"""NA-13b (e): tradable versions of the selected conditions, E8 and E9 (exploratory; NA-13's engine).

**Book.** On each session, the condition's inside events of the split outside the embargo: long those whose
direction is up and short those whose direction is down (the model's sign(N̂); E7's agreement: the common
sign; E7's rank average: the ensemble's sign), equal weight within each side (+1/K_long, −1/K_short, Σ|w| = 2;
a session missing a side holds cash: ``portfolios.tier_weights``), β-hedged with SPY (β_m of the entry
session). Entry at the official open of t (the D0 entry, after the 09:15 decision); exits at the close of t
(L = 1) and at C_{t+1} (L = 2, calendar time). ``strategy.portfolios`` builds the hedged legs (raw open →
close, then close → close), the daily gross return and turnover; ``strategy.costs`` charges 5 and 10 bp per
side on both legs and the hedge; capacity at 1% of ADV20 (``strategy.capacity``). Sharpe ratios are annualized
over the book's window (a day without a position earns 0), as in NA-13.

**Placebo.** 100 random sign assignments of the same events and sessions: a coin flip per event (seeds
2027–2126, ``portfolios.draws``; NA-13's MA-cross convention), the same weights, hedge and costs. Reported:
the percentile of the book's gross Sharpe among the placebo's (ties half) and the placebo's 90th percentile.

**Break-even** cost per side = the annualized gross return / 252 / the daily turnover (NA-14's t35). **Names
per side**: the mean over cohorts holding positions of the long and of the short count.

**Timing.** Every input must be available at or before the 09:15 decision (``portfolios.check_timing``): the
latest W0 article, the tier ranking session, the risk window (close of t−1), the val-A cut points (close of
val-A's last session), a frozen map (E8: the model's calibration instant) and the session-level inputs
(the D0 event and earnings counts at 09:15, VIX at the close of t−1, the macro calendar; SPY's overnight move
only at the open, which therefore cannot pass, and the vendor labels kept for selection only, which have no
instant at all). On the test the validation selection, which read val-B
outcomes, must also precede the decision; the val-B books are in-sample for the selection (reference only).

The market inputs are NA-13's ``work/strategy/market_{public,test}.parquet`` (the 2026 file came from NA-13's
one logged lock sequence; NA-13b reads it through ``io`` and makes no lock read).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.config import DateRange, SplitName, load_splits
from newsaction.paths import Layout, resolve_layout
from newsaction.selective import conditions as cd
from newsaction.selective import data as sd
from newsaction.strategy import costs as cs
from newsaction.strategy import portfolios as pf

EXITS: Final = ("close_t", "close_t+1")
BOOK_SPLITS: Final = ("val_b", "test")
COSTS_BP: Final = (5.0, 10.0)
PLACEBO_SEEDS: Final = 100
PLACEBO_Q: Final = 0.9
ALL: Final = "all"
TIERS_MONTHLY: Final = "panel/tiers_monthly.parquet"
E5_HORIZON: Final = 4  # the frozen V map reads e5 through C_{t+4} (PREREG A1.3)
FAMILY: Final = "exploratory"
# Vendor labels the PIT registry marks ``selection_only`` (configs/availability.yaml: produced
# retrospectively, CLAUDE.md A6): a book may not condition on them, so their condition has no instant.
SELECTION_ONLY: Final = ("e1_vendor_quantified", "e1_press_wire")


@dataclass(frozen=True)
class Book:
    model: str
    condition: str

    @property
    def key(self) -> str:
        return f"{FAMILY}|selective|{self.model}|{self.condition}"


def books_for(selected: Sequence[tuple[str, str]]) -> list[Book]:
    """The selected pairs plus E8 (both models) and E9 (Laya-Fin), each once."""
    want = [*selected, *[(m, "e8_cost") for m in sd.MAIN], ("laya_fin", "e9_division")]
    return [Book(m, k) for m, k in dict.fromkeys(want)]


def _span(split: str) -> DateRange:
    return load_splits().splits[cast(SplitName, split)]


def market(split: str, layout: Layout | None = None) -> pd.DataFrame:
    rel = sd.MARKET["test" if split == "test" else "public"]
    m = io.read_parquet(rel, layout=layout)
    m["session"] = pd.to_datetime(m["session"]).dt.date
    s = _span(split)
    return m.loc[[s.start <= d <= s.end for d in m["session"]]].reset_index(drop=True)


def split_sessions(split: str) -> list[date]:
    s = _span(split)
    return calendar.sessions(s.start, s.end)


def _close_of(d: date) -> pd.Timestamp:
    return calendar.close_utc(d)


def _utc_minutes(session: pd.Series, minutes: pd.Series) -> pd.Series:
    midnight = pd.to_datetime(session.astype(str)).dt.tz_localize("America/New_York")
    return (midnight + pd.to_timedelta(minutes, unit="min")).dt.tz_convert("UTC")


def calibration_utc(model: str, frozen: Mapping[str, Any]) -> pd.Timestamp:
    """The close of the last session the model's frozen V map read (e5 through C_{t+4})."""
    end = date.fromisoformat(frozen["calibration"][sd.CALIBRATION_KEY[model]]["a0"]["fit_range"][1])
    return _close_of(pf.session_after(end, E5_HORIZON))


def tier_instants(sessions: pd.Series, layout: Layout | None = None) -> pd.Series:
    """The close of each session's tier ranking session (the prior month-end, ``panel/tiers_monthly``)."""
    tm = io.read_parquet(TIERS_MONTHLY, columns=["month", "ranking_session"], layout=layout).drop_duplicates()
    rank = {str(m): pd.to_datetime(r).date() for m, r in zip(tm["month"], tm["ranking_session"], strict=True)}
    close = {m: _close_of(r) for m, r in rank.items()}
    return sessions.map(lambda d: close[f"{d.year:04d}-{d.month:02d}"])


def condition_utc(rows: pd.DataFrame, book: Book, frozen: Mapping[str, Any]) -> pd.Series:
    """When the condition's own inputs became known (the latest of them), per event; no instant (refused by
    the timing guard) for an input the PIT registry keeps for selection only."""
    cond = cd.BY_KEY[book.condition]
    if book.condition in SELECTION_ONLY:
        return pd.Series(pd.NaT, index=rows.index, dtype="datetime64[ns, UTC]")
    parts = [pd.Series(_close_of(load_splits().splits["val_a"].end), index=rows.index)]
    days = rows["session"]
    if cond.level == "day":
        if book.condition == "e4_spy_gap":
            parts.append(days.map(calendar.open_utc))
        elif book.condition in ("e4_busy_day", "e4_earnings_season"):
            parts.append(days.map(calendar.d0_cutoff_utc))
        else:  # VIX at t−1, the weekday and the published macro calendar: known by the close of t−1
            parts.append(days.map(lambda d: _close_of(calendar.prev_session(d))))
    if book.condition == "e8_cost":
        parts.append(pd.Series(calibration_utc(book.model, frozen), index=rows.index))
    return pd.concat(parts, axis=1).max(axis=1)


def direction(rows: pd.DataFrame, book: Book, c: Mapping[str, Any]) -> pd.Series:
    if book.condition == "e7_rank_avg":
        return pd.Series(np.sign(cd.ensemble(rows, c).to_numpy()), index=rows.index)
    return pd.Series(np.sign(rows[f"n_{book.model}"].to_numpy(dtype=float)), index=rows.index)


def book_events(
    study: pd.DataFrame, book: Book, split: str, c: Mapping[str, Any], frozen: Mapping[str, Any],
    layout: Layout | None = None,
) -> pd.DataFrame:  # fmt: skip
    """The book's events with their side and input instants."""
    cond = cd.BY_KEY[book.condition]
    inside = cd.event_inside(study, book.model, cond, c)
    rows = sd.eval_rows(study, split)
    rows = rows.loc[inside.reindex(rows.index) == 1].copy()
    rows["side"] = direction(rows, book, c)
    rows = rows.loc[rows["side"].isin([-1.0, 1.0])].reset_index(drop=True)
    rows["news_utc"] = _utc_minutes(rows["session"], rows["latest_et"])
    rows["tier_utc"] = tier_instants(rows["session"], layout)
    rows["condition_utc"] = condition_utc(rows, book, frozen)
    rows["selection_utc"] = _close_of(load_splits().splits["val_b"].end)
    rows["tier"] = rows["tier"].astype(object)
    return rows


def names_per_side(w: np.ndarray, cohort: np.ndarray, n_cohorts: int) -> tuple[float, float]:
    lg = np.bincount(cohort, weights=(w > 0).astype(float), minlength=n_cohorts)
    sh = np.bincount(cohort, weights=(w < 0).astype(float), minlength=n_cohorts)
    traded = (lg > 0) & (sh > 0)
    if not traded.any():
        return math.nan, math.nan
    return float(lg[traded].mean()), float(sh[traded].mean())


def percentile(value: float, null: np.ndarray) -> float:
    """Share of the placebo below ``value`` (ties count half), in percent (NA-13's rule)."""
    n = np.asarray(null, dtype=float)
    if len(n) == 0 or not np.isfinite(value):
        return math.nan
    return float(100.0 * (np.sum(n < value) + 0.5 * np.sum(n == value)) / len(n))


def run_book(
    ev: pd.DataFrame, mkt: pd.DataFrame, sessions: Sequence[date], exit_rule: str, split: str,
    seeds: int = PLACEBO_SEEDS,
) -> dict[str, Any]:  # fmt: skip
    """One book on one split and exit: summary, placebo and the daily series."""
    cols = ["event_id", "session", "symbol_id", "company_id", "tier"]
    u = pf.build_universe(ev[cols], mkt, "D0", exit_rule, sessions)
    rec: dict[str, Any] = {"split": split, "exit": exit_rule, "holding": u.holding, **u.counts}
    if u.x.shape[0] == 0:
        return {"summary": rec | {"n_positions": 0}, "daily": pd.DataFrame()}
    ue = u.events.copy()
    for col in ("news_utc", "tier_utc", "condition_utc", "selection_utc"):
        ue[col] = pf.aligned(u, ev, col)
    win = list(u.sessions)
    ue["risk_utc"] = [_close_of(calendar.prev_session(d)) for d in ue["session"]]
    need = ["news_utc", "tier_utc", "condition_utc", "risk_utc"] + (
        ["selection_utc"] if split == "test" else []
    )
    pf.check_timing(ue, need)
    side = pf.aligned(u, ev, "side").to_numpy(dtype=float).astype(np.int8)
    cohort = ue["cohort"].to_numpy(dtype=np.int64)
    one = np.full(len(ue), ALL, dtype=object)
    w = pf.tier_weights(side, cohort, one, ALL, u.n_cohorts)
    d = pf.evaluate(u, w)
    s = pf.summary(d.gross[0], d.turnover[0], d.active[0])
    cap = pf.capacity_of(u, w)
    k_long, k_short = names_per_side(w, cohort, u.n_cohorts)
    ids = ue["event_id"].tolist()
    wp = np.zeros((seeds, len(ids)))
    for i in range(seeds):
        flip = np.where(pf.draws(ids, pf.SEED + 1 + i) > 0.5, 1, -1).astype(np.int8)
        wp[i] = pf.tier_weights(flip, cohort, one, ALL, u.n_cohorts)
    dp = pf.evaluate(u, wp)
    null_gross = pf.sharpe_rows(dp.gross)
    turnover = float(s["turnover_daily"])
    rec |= {k: v for k, v in s.items()}
    rec |= {
        "n_positions": len(ids),
        "n_traded_positions": int((w != 0).sum()),
        "cohorts_traded": int(np.unique(cohort[w != 0]).size),
        "names_long": k_long,
        "names_short": k_short,
        "break_even_bp": (s["ann_return_gross"] / 252.0 / turnover * 1e4) if turnover > 0 else math.nan,
        "placebo_pct_gross": percentile(s["sharpe_gross"], null_gross),
        "placebo_q90_gross": float(np.quantile(null_gross, PLACEBO_Q)),
        "placebo_median_gross": float(np.median(null_gross)),
        **{f"capacity_{k}": v for k, v in asdict(cap).items()},
    }
    for bp in COSTS_BP:
        null = pf.sharpe_rows(cs.net(dp.gross, dp.turnover, bp))
        rec[f"placebo_pct_net_{int(bp)}"] = percentile(s[f"sharpe_net_{int(bp)}"], null)
    daily = pd.DataFrame(
        {
            "session": win,
            "gross": d.gross[0],
            "turnover": d.turnover[0],
            "active": d.active[0],
            **{f"net_{int(bp)}": cs.net(d.gross[0], d.turnover[0], bp) for bp in COSTS_BP},
        }
    )
    return {"summary": rec, "daily": daily}


def run_books(
    study: pd.DataFrame, books: Sequence[Book], c: Mapping[str, Any], frozen: Mapping[str, Any],
    splits: Sequence[str] = BOOK_SPLITS, layout: Layout | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:  # fmt: skip
    """Every book on every split and exit: (summaries, daily series)."""
    lay = resolve_layout(layout)
    rows, daily = [], []
    for split in splits:
        mkt = market(split, lay)
        sess = split_sessions(split)
        for b in books:
            ev = book_events(study, b, split, c, frozen, lay)
            for ex in EXITS:
                r = run_book(ev, mkt, sess, ex, split)
                base = {
                    "key": f"{b.key}|{ex}|{split}",
                    "book": b.key,
                    "model": b.model,
                    "condition": b.condition,
                }
                rows.append(base | r["summary"])
                if not r["daily"].empty:
                    tags = {
                        "book": b.key,
                        "model": b.model,
                        "condition": b.condition,
                        "split": split,
                        "exit": ex,
                    }
                    daily.append(r["daily"].assign(**tags))
    return pd.DataFrame(rows), (pd.concat(daily, ignore_index=True) if daily else pd.DataFrame())
