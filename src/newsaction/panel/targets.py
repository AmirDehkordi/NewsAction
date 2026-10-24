"""Targets, purge and the placebo helper (PREREG §4.1, §5.4-5.8, Amendment A1.2; PRD NA-01 S6).

Hashed at the NA-11 freeze (PREREG §4.4). The target arithmetic lives in this file only (numpy and
pandas, plus the calendar and the lock), so nothing outside the hash can change it.

``build_targets(panel, period)``:
- public periods (a split name, ``"warmup"`` or ``"public"``): computed from the panel, which must not
  contain test-period sessions;
- ``"test"``: the test panel is rebuilt from the blinded prices, obtained ONLY through
  ``lock.read_sealed(..., "targets")``, which raises ``LockError`` (and logs the attempt) unless the
  freeze record matches and ``NA_UNBLIND=1``.

Units. AR_x are abnormal returns (PREREG §5.4). A z target divides by the sigmas known at the
decision: for a window made of one intraday piece and k close-to-close days the scale is
sqrt(sigma_id^2 + k * sigma_cc^2) (PREREG §15 clarification); D0 targets use the sigmas of row t,
D2 forward targets those of row t+1 (data through t). Same-day z_x are clipped at +-10 in the panel;
multi-day z targets are not clipped. Level units (A1.2) divide by sigma_cc,t with no sqrt(h).

Purge (§4.1): a target whose horizon ends after the last session of the split containing t is NaN.
Sessions before the first split belong to ``"warmup"``, which ends the session before it.
Delistings (§5.8): after a symbol's last traded session, AR_cc counts as 0 (the last price is
held); ``delist_within_c20`` flags rows whose t+20 horizon passes that session.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Final, cast

import numpy as np
import pandas as pd

from newsaction import calendar, lock
from newsaction.config import SPLIT_ORDER, SplitName, load_splits
from newsaction.lock import LockError
from newsaction.paths import Layout

WARMUP: Final = "warmup"
PUBLIC: Final = "public"
TEST: Final = "test"
LADDER_DAYS: Final = (0, 1, 2, 5, 10, 20, 60)  # C_{t+k} rungs; the O_t rung is separate; t+60 exploratory
D2_HORIZONS: Final = (1, 5, 20)
D0_HORIZONS: Final = (1, 5)
PLACEBO_LOOKBACK: Final = 5

INPUT_COLUMNS: Final = (
    "session",
    "symbol_id",
    "ar_cc",
    "ar_on",
    "ar_id",
    "sigma_cc",
    "sigma_on",
    "sigma_id",
    "z_id",
)


def blinded_price_files() -> tuple[str, str]:
    """Names of the blinded test-period price files, as the lock knows them."""
    year = load_splits().splits[TEST].start.year
    return f"prices_raw_{year}", f"total_return_check_{year}"


def split_of_session(d: date) -> str:
    """Split name of a session; sessions before the first split are ``warmup``."""
    cfg = load_splits()
    name = cfg.split_of(d)
    if name is not None:
        return name
    if d < cfg.splits[SPLIT_ORDER[0]].start:
        return WARMUP
    raise ValueError(f"session {d} lies in no split")


def split_end(name: str) -> date:
    cfg = load_splits()
    if name == WARMUP:
        return calendar.prev_session(cfg.splits[SPLIT_ORDER[0]].start)
    end = cfg.splits[cast(SplitName, name)].end
    return calendar.prev_session(calendar.next_session(end))  # last session <= end


def _fwd(frame: pd.DataFrame, k: int) -> pd.DataFrame:
    return frame.shift(-k)


def _fwd_sum(frame: pd.DataFrame, a: int, b: int) -> pd.DataFrame:
    """sum_{j=a..b} frame[t+j]; NaN if any term is missing or beyond the grid."""
    vals = frame.fillna(0.0).cumsum()
    bad = frame.isna().astype("float64").cumsum()
    hi_v, hi_b = vals.shift(-b), bad.shift(-b)
    if a == 0:
        lo_v, lo_b = vals.shift(1).fillna(0.0), bad.shift(1).fillna(0.0)
    else:
        lo_v, lo_b = vals.shift(-(a - 1)), bad.shift(-(a - 1))
    return (hi_v - lo_v).where((hi_b - lo_b == 0) & hi_v.notna())


def _held_after_last_trade(ar_cc: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """AR_cc with 0 after each symbol's last traded row (if before the grid end); the last rows."""
    pos = np.arange(len(ar_cc))[:, None]
    finite = ar_cc.notna().to_numpy()
    last = np.where(finite.any(axis=0), len(ar_cc) - 1 - np.argmax(finite[::-1], axis=0), -1)
    stopped = last < len(ar_cc) - 1
    fill = (pos > last[None, :]) & stopped[None, :] & (last[None, :] >= 0)
    held = ar_cc.mask(pd.DataFrame(fill, index=ar_cc.index, columns=ar_cc.columns), 0.0)
    return held, pd.Series(last, index=ar_cc.columns)


def compute_targets(panel: pd.DataFrame, sessions: Sequence[date]) -> pd.DataFrame:
    """Targets for the rows of ``panel`` whose session is in ``sessions`` (all splits purged)."""
    missing = [c for c in INPUT_COLUMNS if c not in panel.columns]
    if missing:
        raise ValueError(f"panel lacks columns {missing}")
    p = panel[list(INPUT_COLUMNS)].copy()
    p["session"] = pd.to_datetime(p["session"]).dt.normalize()
    lo, hi = p["session"].min().date(), p["session"].max().date()
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in calendar.sessions(lo, hi)], name="session")
    symbols = sorted(p["symbol_id"].unique().tolist())

    def grid(col: str) -> pd.DataFrame:
        g = p.pivot_table(index="session", columns="symbol_id", values=col, aggfunc="first")
        return g.reindex(index=index, columns=symbols).astype("float64")

    ar_cc_raw, ar_on, ar_id = grid("ar_cc"), grid("ar_on"), grid("ar_id")
    s_cc, s_on, s_id = grid("sigma_cc"), grid("sigma_on"), grid("sigma_id")
    ar_cc, last = _held_after_last_trade(ar_cc_raw)

    t: dict[str, tuple[pd.DataFrame, int]] = {}  # name -> (values, horizon in sessions)
    t["y0"] = (grid("z_id"), 0)
    for k in D0_HORIZONS:
        ar = ar_id + _fwd_sum(ar_cc, 1, k)
        t[f"ar_o0_c{k}"] = (ar, k)
        t[f"z_o0_c{k}"] = (ar / (s_id**2 + k * s_cc**2).pow(0.5), k)
    s_on1, s_id1, s_cc1 = _fwd(s_on, 1), _fwd(s_id, 1), _fwd(s_cc, 1)
    t["ar_c0_o1"] = (_fwd(ar_on, 1), 1)
    t["z_c0_o1"] = (_fwd(ar_on, 1) / s_on1, 1)
    for k in D2_HORIZONS:
        ar = _fwd(ar_id, 1) + (_fwd_sum(ar_cc, 2, k) if k >= 2 else 0.0)
        t[f"ar_o1_c{k}"] = (ar, k)
        t[f"z_o1_c{k}"] = (ar / (s_id1**2 + (k - 1) * s_cc1**2).pow(0.5), k)
        t[f"fwd_lvl_o1_c{k}"] = (ar / s_cc, k)
    t["y2"] = (t["z_o1_c5"][0], 5)
    t["e5"] = (_fwd_sum(ar_cc, 0, 4) / (s_cc * np.sqrt(5.0)), 4)
    t["car6_z"] = (_fwd_sum(ar_cc, 0, 5) / (s_cc * np.sqrt(6.0)), 5)
    t["car_lvl_o0"] = (ar_on / s_cc, 0)
    for k in LADDER_DAYS:
        t[f"car_lvl_c{k}"] = (_fwd_sum(ar_cc, 0, k) / s_cc, k)
    t["e5_lvl"] = (_fwd_sum(ar_cc, 0, 4) / s_cc, 4)

    wanted = {pd.Timestamp(d) for d in sessions}
    rows = p[p["session"].isin(wanted)][["session", "symbol_id"]].drop_duplicates()
    r_pos = index.get_indexer(pd.Index(rows["session"]))
    c_pos = pd.Index(symbols).get_indexer(pd.Index(rows["symbol_id"]))
    split_names = [split_of_session(d.date()) for d in rows["session"]]
    ends = {n: index.searchsorted(pd.Timestamp(split_end(n)), side="right") - 1 for n in set(split_names)}
    end_pos = np.array([ends[n] for n in split_names])
    out = rows.reset_index(drop=True).copy()
    out["split"] = split_names
    for name, (values, horizon) in t.items():
        v = values.to_numpy(dtype="float64")[r_pos, c_pos]
        out[name] = np.where(r_pos + horizon <= end_pos, v, np.nan)
    last_pos = last.to_numpy()[c_pos]
    out["delist_within_c20"] = (last_pos < len(index) - 1) & (r_pos <= last_pos) & (r_pos + 20 > last_pos)
    out["session"] = out["session"].dt.date
    return out


def build_targets(panel: pd.DataFrame, period: str, *, layout: Layout | None = None) -> pd.DataFrame:
    """PREREG §5.6 / A1.2 targets for ``period`` (see the module docstring)."""
    test_start = load_splits().splits[TEST].start
    if period == TEST:
        prices, total = (lock.read_sealed(n, "targets", layout=layout) for n in blinded_price_files())
        from newsaction.panel import build  # build imports this module

        test_panel = build.test_returns_panel(prices, total, layout=layout)
        test_sessions = calendar.sessions(test_start, load_splits().splits[TEST].end)
        return compute_targets(test_panel, test_sessions)
    names = {*SPLIT_ORDER, WARMUP, PUBLIC} - {TEST}
    if period not in names:
        raise ValueError(f"unknown period {period!r}; expected one of {sorted(names | {TEST})}")
    sess = pd.to_datetime(panel["session"])
    if bool((sess >= pd.Timestamp(test_start)).any()):
        raise LockError("public targets refuse test-period rows: use period='test' (through newsaction.lock)")
    days = sorted({d.date() for d in sess})
    if period != PUBLIC:
        days = [d for d in days if split_of_session(d) == period]
    return compute_targets(panel, days)


# --- placebo (PREREG §5.7) -------------------------------------------------------------------------


def _require_public(df: pd.DataFrame) -> None:
    test_start = pd.Timestamp(load_splits().splits[TEST].start)
    if bool((pd.to_datetime(df["session"]) >= test_start).any()):
        raise LockError("the placebo helper operates on the public panel only")


def no_event_window(events: pd.DataFrame, lookback: int = PLACEBO_LOOKBACK) -> pd.DataFrame:
    """True where a company had no selected event on t or the previous ``lookback`` sessions.

    ``events``: bool frame, rows = consecutive sessions, columns = company_id (event in W2 of t).
    """
    hit = events.astype("float64").rolling(lookback + 1, min_periods=1).max()
    return hit.eq(0.0)


def placebo_means(
    df: pd.DataFrame, targets: Sequence[str], eligible: pd.Series, by: Sequence[str] = ("session", "tier")
) -> pd.DataFrame:
    """Mean of each target over eligible rows per (day, tier).

    ``eligible`` (bool, aligned with ``df``): covered member-days without a selected event in W2 of
    the same or the previous 5 sessions (built by the caller from coverage and events).
    """
    _require_public(df)
    sub = df.loc[eligible.reindex(df.index).fillna(False).astype(bool), [*by, *targets]]
    return sub.groupby(list(by), dropna=False)[list(targets)].mean().add_suffix("_placebo").reset_index()


def placebo_adjust(
    df: pd.DataFrame, targets: Sequence[str], means: pd.DataFrame, by: Sequence[str] = ("session", "tier")
) -> pd.DataFrame:
    """``df`` with ``<target>_adj`` = target - its (day, tier) placebo mean (raw columns are kept)."""
    _require_public(df)
    out = df.merge(means, on=list(by), how="left")
    for col in targets:
        out[f"{col}_adj"] = out[col] - out[f"{col}_placebo"]
    return out
