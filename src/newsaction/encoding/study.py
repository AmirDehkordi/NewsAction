"""The encoding search (val-A) and its confirmation (val-B) (PREREG §8.4; PRD NA-07 S1–S2).

**Models.** ``top_models``: the ``n`` stage-2 models of NA-06's leaderboard with the highest stage-2 Call A IC
(``ic2_a_z_cc``); ICs equal to ``tie_decimals`` decimals go to the cheaper (``cost_per_1000_a2``), then the
model id. NA-07 asserts that this gives the operator's three (``configs/encoding.yaml`` ``models.expected``).

**Metric.** Per (model, encoding, split): NA-06's daily Spearman IC of N̂ with z_cc,t (``tournament.metrics``)
and its mean, with the Newey–West t and a stationary block bootstrap over sessions (PREREG §11.4). One set of
bootstrap indices per split serves every series of that split (``boot_indices``), so the series are resampled
on the same sessions; a session a series lacks counts as missing in its bootstrap mean (``boot_means``).
The bootstrap SE is the standard deviation of the bootstrap means; the CI is their percentile interval.

**Encoding rule** (``choose_encoding``; PREREG §8.4 with PRD S1's pooling). Within each model the encodings
are ranked by IC (1 = highest; ICs equal to ``tie_decimals`` decimals share the average rank; a missing IC
ranks last). The best encoding has the lowest mean rank over the models. A tie in mean rank that includes the
default (E3) goes to the default; any other tie goes to the higher mean IC, then to the lower encoding index.

**Val-B check** (``val_b_delta``, ``confirm``; PRD S2). Only when the best is not the default: Δ_t = the mean
over models of daily IC(best) − daily IC(default) on the sessions where every one of those daily ICs exists;
Δ = mean_t Δ_t with its bootstrap SE. The best is kept iff Δ ≥ −``confirm_se``·SE; otherwise the default.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.encoding import EncodingError
from newsaction.tournament import metrics as mx
from newsaction.tournament.mcs import stationary_indices

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]


# --- models ----------------------------------------------------------------------------------------------


def top_models(leaderboard: pd.DataFrame, n: int, decimals: int = 12) -> list[str]:
    """The ``n`` stage-2 models with the highest stage-2 Call A IC; ties to the cheaper, then the id."""
    t = leaderboard.loc[leaderboard["stage2"].astype(bool)].copy()
    if len(t) < n:
        raise EncodingError(f"the leaderboard has {len(t)} stage-2 models, fewer than {n}")
    t["_ic"] = t["ic2_a_z_cc"].astype(float).round(decimals)
    t = t.sort_values(["_ic", "cost_per_1000_a2", "model"], ascending=[False, True, True], kind="mergesort")
    return t["model"].head(n).astype(str).tolist()


# --- bootstrap -------------------------------------------------------------------------------------------


def boot_indices(n_days: int, reps: int, block: float, seed: int) -> IntArray:
    """(reps, n_days) session indices of the stationary bootstrap (``tournament.mcs``), seeded."""
    return stationary_indices(n_days, reps, block, np.random.default_rng(seed))


def boot_means(values: npt.ArrayLike, idx: IntArray) -> FloatArray:
    """Bootstrap means of a daily series on the split's session grid (NaN = no IC that session)."""
    v = np.asarray(values, dtype=float)
    draws = v[idx]
    with np.errstate(invalid="ignore"):
        counts = np.isfinite(draws).sum(axis=1)
        sums = np.nansum(draws, axis=1)
    out = np.full(len(draws), np.nan)
    ok = counts > 0
    out[ok] = sums[ok] / counts[ok]
    return out


@dataclass(frozen=True)
class Summary:
    ic: float
    t: float
    nw_se: float
    boot_se: float
    ci_low: float
    ci_high: float
    n_days: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize(daily: pd.Series, grid: Sequence[object], idx: IntArray, lags: int, ci: float) -> Summary:
    """Mean daily IC, Newey–West t and se, bootstrap se and percentile CI. ``grid`` is the split's session
    list that ``idx`` indexes; ``daily`` is reindexed onto it."""
    st = mx.ic_stats(daily, lags)
    values = daily.reindex(list(grid)).to_numpy(dtype=float)
    if not np.isfinite(values).any():
        return Summary(math.nan, math.nan, math.nan, math.nan, math.nan, math.nan, 0)
    bm = boot_means(values, idx)
    bm = bm[np.isfinite(bm)]
    lo, hi = np.quantile(bm, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    return Summary(
        ic=st.mean,
        t=st.t,
        nw_se=st.se,
        boot_se=float(np.std(bm, ddof=1)),
        ci_low=float(lo),
        ci_high=float(hi),
        n_days=st.n_days,
    )


# --- the encoding rule -----------------------------------------------------------------------------------


def ranks(table: pd.DataFrame, decimals: int = 12) -> pd.Series:
    """Rank of each row's encoding within its model by ``ic`` (1 = highest; equal ICs share the average
    rank; a missing IC ranks last). Index: the table's."""
    ic = table["ic"].astype(float).round(decimals)
    return ic.groupby(table["model"]).rank(ascending=False, method="average", na_option="bottom")


@dataclass(frozen=True)
class Choice:
    best: str
    reason: str
    tied: list[str]
    mean_rank: dict[str, float]
    mean_ic: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def choose_encoding(
    table: pd.DataFrame, encodings: Sequence[str], default: str, decimals: int = 12
) -> Choice:
    """PREREG §8.4 search on val-A: ``table`` has one row per (model, encoding) with ``ic``."""
    t = table.loc[table["encoding"].isin(list(encodings)), ["model", "encoding", "ic"]].copy()
    models = sorted(set(t["model"]))
    if not models:
        raise EncodingError("no encoding rows")
    if t.duplicated(["model", "encoding"]).any():
        raise EncodingError("a (model, encoding) appears twice")
    for m in models:
        missing = set(encodings) - set(t.loc[t["model"] == m, "encoding"])
        if missing:
            raise EncodingError(f"{m} has no row for {sorted(missing)}")
    t["rank"] = ranks(t, decimals)
    agg = t.groupby("encoding").agg(mean_rank=("rank", "mean"), mean_ic=("ic", "mean"))
    pooled = agg.reindex(pd.Index(list(encodings)))
    mr = pooled["mean_rank"].round(decimals)
    tied = [e for e in encodings if mr[e] == mr.min()]
    if len(tied) == 1:
        best, reason = tied[0], "lowest mean rank"
    elif default in tied:
        best, reason = default, f"tie in mean rank among {tied}: the default {default}"
    else:
        mic = pooled.loc[tied, "mean_ic"].round(decimals)
        top = [e for e in tied if mic[e] == mic.max()]
        best = top[0]
        reason = f"tie in mean rank among {tied}: the higher mean IC" + (
            f", then the lower index among {top}" if len(top) > 1 else ""
        )
    return Choice(
        best=best,
        reason=reason,
        tied=tied,
        mean_rank={e: float(pooled["mean_rank"][e]) for e in encodings},
        mean_ic={e: float(pooled["mean_ic"][e]) for e in encodings},
    )


# --- the val-B check -------------------------------------------------------------------------------------


def val_b_delta(daily: pd.DataFrame, models: Sequence[str], best: str, default: str) -> pd.Series:
    """Δ_t = mean over ``models`` of daily IC(best) − daily IC(default), on the sessions where all of them
    exist. ``daily`` is long: model, encoding, session, ic."""
    wide = daily.pivot_table(index="session", columns=["model", "encoding"], values="ic", aggfunc="first")
    cols = [(m, e) for m in models for e in (best, default)]
    missing = [c for c in cols if c not in wide.columns]
    if missing:
        raise EncodingError(f"no val-B daily IC for {missing}")
    w = wide[cols].dropna()
    diffs = pd.concat([w[(m, best)] - w[(m, default)] for m in models], axis=1)
    return diffs.mean(axis=1).rename("delta").sort_index()


@dataclass(frozen=True)
class Check:
    needed: bool
    best: str
    default: str
    chosen: str
    delta: float | None
    se: float | None
    threshold: float | None  # −confirm_se·SE
    n_days: int
    kept_best: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def confirm(
    best: str, default: str, delta: float | None, se: float | None, k: float, n_days: int = 0
) -> Check:
    """PRD S2: keep ``best`` unless Δ < −k·SE (it is worse than the default by more than k SE)."""
    if best == default:
        return Check(False, best, default, default, None, None, None, 0, True)
    if delta is None or se is None or not (math.isfinite(delta) and math.isfinite(se)):
        raise EncodingError("the val-B check needs a finite Δ and SE")
    keep = delta >= -k * se
    return Check(True, best, default, best if keep else default, delta, se, -k * se, n_days, keep)
