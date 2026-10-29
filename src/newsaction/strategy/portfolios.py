"""NA-13 portfolios (PREREG §2.5, §12, A1.6; configs/frozen.yaml ``strategy``).

**Timing (§2.5).** Each decision point has one decision instant and one entry:

| Point | Decision | Entry (``ENTRY_OF_POINT``) | First holding leg |
|---|---|---|---|
| D0 | 09:15 ET of t (``calendar.d0_cutoff_utc``) | official open of t | raw open → raw close (``r_id``) |
| D1 | 10:00 ET of t (``calendar.d1_utc``) | the 10:00 bar close of t | 10:00 bar close → close (``r_10c``) |
| D2 | close(t) (``calendar.close_utc``) | official open of next(t) | raw open → raw close of t+1 |

Later holding days earn the adjusted close → close return (``r_cc``) up to the exit close ``close_t+j``. The
10:00 bar's closing price is the D1 entry price (§2.5); the fill is stamped ``FILL_LAG`` after the decision,
since an order can only follow it. Every position is checked: entry instant > decision instant, every input
instant (``available``) ≤ the decision (``TimingError`` otherwise).

**Books (§12).** On each decision session, the events with a finite score are ranked; long the top 20%, short
the bottom 20% within each tier. A tier whose side would hold fewer than 10 events (k = ⌊0.2·n⌋) joins the
session's pool of such tiers; if the pool's side is still below 10 and some tier stands alone, the whole
session is ranked as one group. Ties in the score break on ``tiebreak`` (S-D0: N̂, of which Ñ is a monotone
map) and then on a seeded uniform draw (``SEED``). Equal weights: +1/K for each long, −1/K for each short
(K names per side over the session's groups), so Σ|w| = 2 per dollar of capital. The book is β-hedged (SPY):
each holding day earns Σ w·(r − β_m·r_SPY), with β_m of the entry session (252 sessions ending the session
before; 1.0 when missing). A name that stops trading earns 0 after its last price (§5.8).

**Calendar time (§12, A1.6).** With holding length L sessions, the cohort formed at each decision holds 1/L of
the capital; the daily return is (1/L)·Σ over active cohorts. Single-session books (L = 1) are a special case.
Costs and turnover are in ``costs``; capacity in ``capacity``.

**Sample.** The event's split outside the embargo (§4.2); the exit session must lie in the same split (§4.1).
The book's window runs from the first entry to the last exit session of its universe; days in it without a
position earn 0.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import sparse  # type: ignore[import-untyped, unused-ignore]

from newsaction import calendar
from newsaction.strategy import capacity as cp
from newsaction.strategy import costs as cs

Point = Literal["D0", "D1", "D2"]
Price = Literal["open", "bar10", "close"]
FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

QUANTILE: Final = 0.2  # configs/frozen.yaml strategy.quantile
MIN_SIDE: Final = 10  # strategy.pool_if_side_below
SEED: Final = 2026  # strategy.seed
BETA_FALLBACK: Final = 1.0
FILL_LAG: Final = pd.Timedelta(seconds=1)
ANNUAL: Final = 252
POOL: Final = "pool"
ALL: Final = "all"


class TimingError(AssertionError):
    """An entry at or before its decision, or an input available after it."""


@dataclass(frozen=True)
class Entry:
    price: Price
    offset: int  # sessions after the event session t


ENTRIES: Final[Mapping[str, Entry]] = {
    "open_t": Entry("open", 0),
    "bar10_t": Entry("bar10", 0),
    "open_t+1": Entry("open", 1),
}
ENTRY_OF_POINT: Final[Mapping[Point, str]] = {"D0": "open_t", "D1": "bar10_t", "D2": "open_t+1"}
FIRST_LEG: Final[Mapping[Price, str]] = {"open": "id", "bar10": "10c"}
LEGS: Final = ("cc", "id", "10c")
_EXIT: Final = re.compile(r"^close_t(?:\+(\d+))?$")


def exit_offset(exit_rule: str) -> int:
    m = _EXIT.fullmatch(exit_rule)
    if m is None:
        raise ValueError(f"unknown exit {exit_rule!r}; expected close_t or close_t+<k>")
    return int(m.group(1) or 0)


def holding_legs(entry: Entry, exit_off: int) -> list[tuple[int, str]]:
    """(session offset from t, return leg) of every holding day, entry to exit."""
    first = entry.offset + 1
    legs = [] if entry.price == "close" else [(entry.offset, FIRST_LEG[entry.price])]
    legs += [(o, "cc") for o in range(first, exit_off + 1)]
    if not legs:
        raise TimingError(f"exit close_t+{exit_off} is not after the entry {entry}")
    return legs


def session_after(t: date, offset: int) -> date:
    d = t
    for _ in range(abs(offset)):
        d = calendar.next_session(d) if offset > 0 else calendar.prev_session(d)
    return d


def decision_utc(point: Point, t: date) -> pd.Timestamp:
    if point == "D0":
        return calendar.d0_cutoff_utc(t)
    if point == "D1":
        return calendar.d1_utc(t)
    return calendar.close_utc(t)


def entry_utc(entry: Entry, t: date) -> pd.Timestamp:
    s = session_after(t, entry.offset)
    if entry.price == "open":
        return calendar.open_utc(s)
    if entry.price == "bar10":
        return calendar.d1_utc(s) + FILL_LAG
    return calendar.close_utc(s)


def entry_of(point: Point) -> Entry:
    return ENTRIES[ENTRY_OF_POINT[point]]


@dataclass(frozen=True)
class Rule:
    """One book: a family, a signal at a decision point, an exit, optionally a model and the gate."""

    family: str
    point: Point
    signal: str
    exit: str
    model: str | None = None
    gated: bool = False

    @property
    def key(self) -> str:
        gate = "gated" if self.gated else "all"
        return f"{self.family}|{self.model or '-'}|{self.point}|{self.signal}|{self.exit}|{gate}"


# --- the universe of one (split, point, exit, event set) ----------------------------------------------------


@dataclass
class Universe:
    point: Point
    exit: str
    holding: int
    events: (
        pd.DataFrame
    )  # one row per tradeable event (positional index 0..n-1), with cohort and timing columns
    sessions: list[date]  # the book's window
    x: sparse.csr_matrix  # (n, len(sessions)) hedged daily returns over each event's holding days
    cohort_entry: IntArray  # window position of each cohort's entry session
    cohort_exit: IntArray
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def n_cohorts(self) -> int:
        return len(self.cohort_entry)


def _wide(market: pd.DataFrame, col: str, sidx: Mapping[date, int], syms: Mapping[int, int]) -> FloatArray:
    out = np.full((len(sidx), len(syms)), np.nan)
    m = market.loc[market["session"].isin(sidx.keys()) & market[col].notna()]
    r = m["session"].map(sidx).to_numpy(dtype=np.int64)
    c = m["symbol_id"].map(syms).to_numpy(dtype=np.int64)
    out[r, c] = m[col].to_numpy(dtype=float)
    return out


def _spy(market: pd.DataFrame, col: str, sidx: Mapping[date, int]) -> FloatArray:
    s = market.loc[market["session"].isin(sidx.keys())].groupby("session")[col].first()
    out = np.full(len(sidx), np.nan)
    keep = s.notna()
    out[s.index[keep].map(sidx).to_numpy(dtype=np.int64)] = s[keep].to_numpy(dtype=float)
    return out


def check_timing(events: pd.DataFrame, available: Sequence[str]) -> None:
    """Entry strictly after the decision; every input instant at or before it."""
    late = events["entry_utc"] <= events["decision_utc"]
    if bool(late.any()):
        bad = events.loc[late, ["event_id", "decision_utc", "entry_utc"]].head(3).to_dict("records")
        raise TimingError(f"{int(late.sum())} entries not after their decision, e.g. {bad}")
    for col in available:
        missing = events[col].isna()
        if bool(missing.any()):
            raise TimingError(f"input {col}: {int(missing.sum())} positions without an availability instant")
        after = events[col] > events["decision_utc"]
        if bool(after.any()):
            bad = events.loc[after, ["event_id", col, "decision_utc"]].head(3).to_dict("records")
            raise TimingError(f"input {col}: {int(after.sum())} available after the decision, e.g. {bad}")


def build_universe(
    events: pd.DataFrame,
    market: pd.DataFrame,
    point: Point,
    exit_rule: str,
    split_sessions: Sequence[date],
    available: Sequence[str] = (),
) -> Universe:
    """``events``: event_id, session, symbol_id, tier (+ score columns and ``available`` instants, UTC);
    ``market``: ``strategy.market``'s columns for the split's sessions; ``split_sessions``: the split's
    sessions."""
    entry = entry_of(point)
    exit_off = exit_offset(exit_rule)
    legs = holding_legs(entry, exit_off)
    sessions = list(split_sessions)
    sidx = {d: i for i, d in enumerate(sessions)}
    ev = events.loc[events["session"].isin(sidx.keys())].sort_values(["session", "event_id"]).copy()
    t_idx = ev["session"].map(sidx).to_numpy(dtype=np.int64)
    first_leg = legs[0][0]
    ev["entry_idx"] = t_idx + entry.offset
    ev["exit_idx"] = t_idx + exit_off
    counts = {"events_in": len(ev)}
    keep = (t_idx + first_leg >= 0) & (ev["exit_idx"].to_numpy() <= len(sessions) - 1)
    counts["purged"] = int((~keep).sum())
    ev, t_idx = ev.loc[keep].copy(), t_idx[keep]

    syms = {int(s): i for i, s in enumerate(sorted(set(market["symbol_id"])))}
    if not set(ev["symbol_id"]).issubset(syms.keys()):
        missing = sorted(set(ev["symbol_id"]) - syms.keys())[:5]
        raise KeyError(f"events on symbols without market rows, e.g. {missing}")
    col = ev["symbol_id"].map(syms).to_numpy(dtype=np.int64)
    e_idx = ev["entry_idx"].to_numpy(dtype=np.int64)
    price_col = {"open": "raw_open", "bar10": "p10", "close": "raw_close"}[entry.price]
    fill = _wide(market, price_col, sidx, syms)[np.clip(e_idx, 0, None), col]
    has_fill = np.isfinite(fill) & (e_idx >= 0)
    counts["no_entry_price"] = int((~has_fill).sum())
    ev, t_idx, col, e_idx = ev.loc[has_fill].copy(), t_idx[has_fill], col[has_fill], e_idx[has_fill]
    if len(ev) == 0:
        counts["events"] = 0
        empty = ev.assign(cohort=pd.Series(dtype="int64"), beta=pd.Series(dtype=float)).reset_index(drop=True)
        z = np.zeros(0, np.int64)
        return Universe(point, exit_rule, len(legs), empty, [], sparse.csr_matrix((0, 0)), z, z, counts)

    beta = _wide(market, "beta_m", sidx, syms)[e_idx, col]
    counts["beta_fallback"] = int((~np.isfinite(beta)).sum())
    ev["beta"] = np.where(np.isfinite(beta), beta, BETA_FALLBACK)
    ev["adv20"] = _wide(market, "adv20", sidx, syms)[e_idx, col]

    days = sorted(set(ev["session"]))
    dec = {d: decision_utc(point, d) for d in days}
    ent = {d: entry_utc(entry, d) for d in days}
    ext = {d: calendar.close_utc(session_after(d, exit_off)) for d in days}
    ev["decision_utc"] = ev["session"].map(dec)
    ev["entry_utc"] = ev["session"].map(ent)
    ev["exit_utc"] = ev["session"].map(ext)
    check_timing(ev, available)

    stock = {leg: _wide(market, f"r_{leg}", sidx, syms) for leg in LEGS}
    spy = {leg: _spy(market, f"r_spy_{leg}", sidx) for leg in LEGS}
    rows, cols, vals = [], [], []
    nan_days = 0
    n = len(ev)
    b = ev["beta"].to_numpy(dtype=float)
    for off, leg in legs:
        s = t_idx + off
        x = stock[leg][s, col] - b * spy[leg][s]
        bad = ~np.isfinite(x)
        nan_days += int(bad.sum())
        rows.append(np.arange(n))
        cols.append(s)
        vals.append(np.where(bad, 0.0, x))
    counts["zero_return_days"] = nan_days
    lo = int(min(c.min() for c in cols))
    hi = int(max(c.max() for c in cols))
    x = sparse.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols) - lo)), shape=(n, hi - lo + 1)
    )
    cohort_days = sorted(set(t_idx.tolist()))
    cidx = {d: i for i, d in enumerate(cohort_days)}
    ev["cohort"] = [cidx[int(d)] for d in t_idx]
    c_entry = np.asarray([d + first_leg - lo for d in cohort_days], dtype=np.int64)
    c_exit = np.asarray([d + exit_off - lo for d in cohort_days], dtype=np.int64)
    ev["window_start"] = sessions[lo]
    counts["events"] = n
    counts["cohorts"] = len(cohort_days)
    return Universe(
        point,
        exit_rule,
        len(legs),
        ev.reset_index(drop=True),
        sessions[lo : hi + 1],
        x,
        c_entry,
        c_exit,
        counts,
    )


# --- sides -------------------------------------------------------------------------------------------------


def side_size(n: npt.ArrayLike, q: float = QUANTILE) -> IntArray:
    return np.floor(np.asarray(n, dtype=float) * q + 1e-9).astype(np.int64)


def groups(
    cohort: IntArray, tier: npt.ArrayLike, q: float = QUANTILE, min_side: int = MIN_SIDE
) -> npt.NDArray[np.object_]:
    """The ranking group of each event: its tier, the session's pool of small tiers, or the whole session."""
    df = pd.DataFrame({"cohort": cohort, "tier": np.asarray(tier, dtype=object)})
    n_ct = df.groupby(["cohort", "tier"])["tier"].transform("size").to_numpy()
    small = side_size(n_ct, q) < min_side
    g = np.where(small, POOL, df["tier"].to_numpy(dtype=object)).astype(object)
    pool_n = pd.Series(small.astype(int)).groupby(df["cohort"]).transform("sum").to_numpy()
    any_alone = pd.Series((~small).astype(int)).groupby(df["cohort"]).transform("sum").to_numpy() > 0
    whole = (side_size(pool_n, q) < min_side) & (pool_n > 0) & any_alone
    g[whole] = ALL
    return g


def sides(
    cohort: IntArray,
    group: npt.NDArray[np.object_],
    score: FloatArray,
    tiebreak: FloatArray | None,
    draw: FloatArray,
    q: float = QUANTILE,
) -> npt.NDArray[np.int8]:
    """+1 (long, top ⌊q·n⌋), −1 (short, bottom ⌊q·n⌋) or 0 per (cohort, group); NaN scores never trade."""
    n = len(score)
    out = np.zeros(n, dtype=np.int8)
    ok = np.isfinite(score)
    if not ok.any():
        return out
    idx = np.flatnonzero(ok)
    tb = np.zeros(n) if tiebreak is None else np.nan_to_num(np.asarray(tiebreak, dtype=float))
    g_codes = pd.factorize(pd.Series(group[idx]).astype(str) + "#" + pd.Series(cohort[idx]).astype(str))[0]
    order = np.lexsort((draw[idx], tb[idx], score[idx], g_codes))
    gs = g_codes[order]
    start = np.r_[0, np.flatnonzero(np.diff(gs)) + 1]
    size = np.diff(np.r_[start, len(gs)])
    rank = np.arange(len(gs)) - np.repeat(start, size)
    k = np.repeat(side_size(size, q), size)
    nn = np.repeat(size, size)
    s = np.zeros(len(gs), dtype=np.int8)
    s[rank < k] = -1
    s[rank >= nn - k] = 1
    s[k == 0] = 0
    out[idx[order]] = s
    return out


def weights(side: npt.NDArray[np.int8], cohort: IntArray, n_cohorts: int) -> FloatArray:
    """Equal weights: ±1/K with K the cohort's longs (= its shorts)."""
    longs = np.bincount(cohort, weights=(side > 0).astype(float), minlength=n_cohorts)
    k = longs[cohort]
    return np.where(side != 0, side / np.where(k > 0, k, 1.0), 0.0).astype(float)


def tier_weights(
    side: npt.NDArray[np.int8], cohort: IntArray, tier: npt.ArrayLike, which: str, n_cohorts: int
) -> FloatArray:
    """One tier's positions, each side renormalized within the tier (cash where the tier lacks a side)."""
    on = np.asarray(tier, dtype=object) == which
    lg = np.bincount(cohort, weights=((side > 0) & on).astype(float), minlength=n_cohorts)
    sh = np.bincount(cohort, weights=((side < 0) & on).astype(float), minlength=n_cohorts)
    both = (lg > 0) & (sh > 0)
    w = np.zeros(len(side))
    pos, neg = (side > 0) & on & both[cohort], (side < 0) & on & both[cohort]
    w[pos] = 1.0 / lg[cohort[pos]]
    w[neg] = -1.0 / sh[cohort[neg]]
    return w


def draws(event_ids: Sequence[str], seed: int) -> FloatArray:
    """Seeded uniform draws in event-id order (independent of row order)."""
    ids = np.asarray(event_ids, dtype=object)
    order = np.argsort(ids, kind="stable")
    u = np.random.default_rng(seed).random(len(ids))
    out = np.empty(len(ids))
    out[order] = u
    return out


def aligned(u: Universe, frame: pd.DataFrame, col: str) -> pd.Series:
    """``frame[col]`` in the universe's row order (by ``event_id``)."""
    return frame.set_index("event_id")[col].reindex(u.events["event_id"]).reset_index(drop=True)


def select(
    u: Universe, score: FloatArray, tiebreak: FloatArray | None = None, seed: int = SEED
) -> npt.NDArray[np.int8]:
    """The sides of one rule's ``score`` (in the universe's row order)."""
    ev = u.events
    cohort = ev["cohort"].to_numpy(dtype=np.int64)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s)
    g = np.empty(len(ev), dtype=object)
    g[ok] = groups(cohort[ok], ev["tier"].to_numpy(dtype=object)[ok])
    return sides(cohort, g, s, tiebreak, draws(ev["event_id"].tolist(), seed))


# --- evaluation ---------------------------------------------------------------------------------------------


@dataclass
class Daily:
    gross: FloatArray  # (S, T)
    turnover: FloatArray  # (S, T)
    active: npt.NDArray[np.bool_]  # (S, T): a position is held that day


def evaluate(u: Universe, w: FloatArray) -> Daily:
    """Daily gross return and turnover of the book(s) with weights ``w`` ((n,) or (S, n))."""
    w2 = np.atleast_2d(np.asarray(w, dtype=float))
    if u.x.shape[0] == 0:
        z = np.zeros((w2.shape[0], 0))
        return Daily(z, z, z.astype(bool))
    gross = np.asarray(u.x.T.dot(w2.T), dtype=float).T / u.holding
    cohort = u.events["cohort"].to_numpy(dtype=np.int64)
    beta = u.events["beta"].to_numpy(dtype=float)
    notional = cs.cohort_notional(w2, beta, cohort, u.n_cohorts)
    t = len(u.sessions)
    turn = cs.turnover(notional, u.cohort_entry, u.cohort_exit, u.holding, t)
    held = notional > 0  # (S, n_cohorts)
    active = np.zeros((w2.shape[0], t), dtype=bool)
    for j in range(u.n_cohorts):
        a, b = int(u.cohort_entry[j]), int(u.cohort_exit[j])
        active[:, a : b + 1] |= held[:, [j]]
    return Daily(gross, turn, active)


def capacity_of(u: Universe, w: FloatArray) -> cp.Capacity:
    cohort = u.events["cohort"].to_numpy(dtype=np.int64)
    return cp.summarize(w, u.events["adv20"].to_numpy(dtype=float), cohort, u.n_cohorts, u.holding)


# --- metrics ------------------------------------------------------------------------------------------------


def sharpe(r: FloatArray, annual: int = ANNUAL) -> float:
    """Annualized Sharpe mean/sd·√annual of a daily series (0 for fewer than 2 days or no dispersion)."""
    x = np.asarray(r, dtype=float)
    if len(x) < 2:
        return 0.0
    sd = float(x.std(ddof=1))
    return float(x.mean() / sd * math.sqrt(annual)) if sd > 0 else 0.0


def sharpe_rows(r: FloatArray, annual: int = ANNUAL) -> FloatArray:
    x = np.atleast_2d(np.asarray(r, dtype=float))
    if x.shape[1] < 2:
        return np.zeros(x.shape[0])
    sd = x.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(sd > 0, x.mean(axis=1) / sd * math.sqrt(annual), 0.0)
    return np.asarray(out, dtype=float)


def max_drawdown(r: FloatArray) -> float:
    wealth = np.cumprod(1.0 + np.asarray(r, dtype=float))
    if len(wealth) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.r_[1.0, wealth])[1:]
    return float(np.max(1.0 - wealth / peak))


def summary(gross: FloatArray, turnover: FloatArray, active: npt.NDArray[np.bool_]) -> dict[str, float]:
    """The table's columns at each cost level (``costs.LEVELS_BP``) from one book's daily series."""
    out: dict[str, float] = {
        "n_days": float(len(gross)),
        "n_active_days": float(active.sum()),
        "sharpe_gross": sharpe(gross),
        "ann_return_gross": float(np.mean(gross) * ANNUAL) if len(gross) else float("nan"),
        "vol": float(np.std(gross, ddof=1) * math.sqrt(ANNUAL)) if len(gross) > 1 else float("nan"),
        "turnover_daily": float(np.mean(turnover)) if len(turnover) else float("nan"),
    }
    for bp in cs.LEVELS_BP:
        r = cs.net(gross, turnover, bp)
        tag = f"{int(bp)}"
        out[f"sharpe_net_{tag}"] = sharpe(r)
        out[f"ann_return_net_{tag}"] = float(np.mean(r) * ANNUAL) if len(r) else float("nan")
        out[f"max_dd_net_{tag}"] = max_drawdown(r)
        out[f"hit_rate_net_{tag}"] = float(np.mean(r[active] > 0)) if active.any() else float("nan")
    return out
