"""Metrics, the day bootstrap and multiple-testing rules of the pre-registered analyses (PREREG §11.1–11.4,
§1.1–1.2). Hash-locked at the NA-11 freeze with ``spec.py`` (PREREG §15, NA-11 row).

Self-contained on purpose: ``daily_ic`` (``tournament.metrics``), ``nw_t`` (``news.audit``) and
``stationary_indices`` (``tournament.mcs``) are copied here verbatim, so the freeze hash covers every line a
pre-registered number depends on; ``tests/test_analysis_metrics.py`` asserts the copies equal the originals.

- **Daily IC** (§11.1). Per session, the Spearman correlation (Pearson on average ranks) of a signal and a
  target over the rows with both, on sessions with at least ``min_names`` such rows. A session on which either
  side is constant has IC 0 (NA-06's rule). The summary is the mean with its Newey–West t (5 lags).
- **Stationary block bootstrap over days** (§11.4: block 5, 10,000 reps, seed 2026). Indices are drawn on the
  split's session grid (calendar order); a session a series lacks counts as missing in that draw's mean. Ratio
  statistics (R², RMSE) are bootstrapped from per-session sums, weighted by how often a draw holds a session.
- **Bootstrap p-values** of a one-sided H0 θ <= 0 (or >= 0): the centred bootstrap distribution approximates
  the null, p = (1 + #{θ*_b − θ̂ >= θ̂}) / (B + 1) for H1: θ > 0, and the mirror image for θ < 0.
- **OOS R²** (§11.1): 1 − Σ(y − ŷ)² / Σ(y − m)², with m = 0 (zero forecast) unless a reference mean is given.
- **Quintile spread** (§11.1): within each session (>= ``min_names`` rows), the mean target of the top signal
  quintile minus that of the bottom one (quintiles of the signal's average ranks); mean over sessions, NW t.
- **Probability metrics** (§11.2): Q1's nine levels collapse to fall (levels 0–3) / no move (4) / rise (5–8);
  the realized class splits the target at ±``class_band``. Log-loss and Brier score, and their skill against
  climatology (class shares of a reference sample): 1 − score / score_climatology. ECE: top-label, equal-width
  bins. AUC for |z| >= 1: the Mann–Whitney probability that a large move ranks above a small one.
- **Isotonic maps** stored in ``configs/frozen.yaml`` (breakpoints ``x`` ascending, values ``y``) are applied
  by linear interpolation with flat extrapolation beyond the fitted range (``apply_map``).
- **Holm** (§1.1) and **Benjamini–Hochberg** (§1.2) adjusted p-values.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

Q1_LEVELS: Final = 9
Q1_FALL_LEVELS: Final = (0, 1, 2, 3)
Q1_FLAT_LEVEL: Final = 4
Q1_RISE_LEVELS: Final = (5, 6, 7, 8)
FALL: Final = 0
FLAT: Final = 1
RISE: Final = 2
Alternative = Literal["greater", "less"]


# --- copied verbatim (see the module docstring) ----------------------------------------------------------


def nw_t(x: pd.Series | np.ndarray, lags: int) -> tuple[float, float, int]:
    """(mean, Newey–West t, n) of a series (NaN dropped)."""
    v = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(v)
    if n < 3:
        return (float(v.mean()) if n else np.nan, np.nan, n)
    e = v - v.mean()
    s = float(e @ e) / n
    for k in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / n
    se = np.sqrt(s / n) if s > 0 else np.nan
    return float(v.mean()), float(v.mean() / se) if se and se > 0 else np.nan, n


def daily_ic(
    frame: pd.DataFrame, signal: str, target: str, min_names: int, *, session: str = "session"
) -> pd.Series:
    """Per session: Spearman(signal, target) over the rows with both values (>= ``min_names`` rows), 0 when
    either side is constant that day. Index: the sessions kept, sorted."""
    d = frame[[session, signal, target]].dropna()
    out: dict[object, float] = {}
    for s, g in d.groupby(session, sort=True):
        if len(g) < min_names:
            continue
        a = g[signal].rank().to_numpy(dtype=float)
        b = g[target].rank().to_numpy(dtype=float)
        if np.ptp(a) == 0 or np.ptp(b) == 0:
            out[s] = 0.0
            continue
        out[s] = float(np.corrcoef(a, b)[0, 1])
    return pd.Series(out, dtype=float, name=f"ic_{signal}_{target}")


def stationary_indices(t: int, reps: int, block: float, rng: np.random.Generator) -> IntArray:
    """(reps, t) day indices of a circular stationary bootstrap with mean block length ``block``."""
    if t < 2:
        raise ValueError("the stationary bootstrap needs at least two days")
    starts = rng.integers(0, t, size=(reps, t))
    new_block = rng.random((reps, t)) < 1.0 / block
    idx = np.empty((reps, t), dtype=np.int64)
    idx[:, 0] = starts[:, 0]
    for j in range(1, t):
        idx[:, j] = np.where(new_block[:, j], starts[:, j], (idx[:, j - 1] + 1) % t)
    return idx


# --- the day bootstrap -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bootstrap:
    """Stationary-bootstrap draws on a session grid (§11.4). ``idx[b, j]`` is the grid position of day j
    of draw b; ``counts[b, i]`` how often draw b holds grid session i."""

    grid: tuple[object, ...]
    idx: IntArray
    counts: FloatArray

    @classmethod
    def draw(cls, grid: Sequence[object], reps: int, block: float, seed: int) -> Bootstrap:
        g = tuple(sorted(set(grid)))  # type: ignore[type-var]
        idx = stationary_indices(len(g), reps, block, np.random.default_rng(seed))
        counts = np.zeros((reps, len(g)))
        rows = np.repeat(np.arange(reps), len(g))
        np.add.at(counts, (rows, idx.ravel()), 1.0)
        return cls(g, idx, counts)

    def on_grid(self, daily: pd.Series) -> FloatArray:
        """A daily series reindexed onto the grid (NaN = no value that session)."""
        return daily.reindex(list(self.grid)).to_numpy(dtype=float)

    def means(self, daily: pd.Series) -> FloatArray:
        """Bootstrap means of a daily series; a session without a value is skipped in each draw."""
        v = self.on_grid(daily)
        draws = v[self.idx]
        with np.errstate(invalid="ignore"):
            n = np.isfinite(draws).sum(axis=1)
            s = np.nansum(draws, axis=1)
        out = np.full(len(draws), np.nan)
        out[n > 0] = s[n > 0] / n[n > 0]
        return out

    def sums(self, per_day: pd.Series) -> FloatArray:
        """Bootstrap totals of a per-session sum (missing sessions contribute 0)."""
        v = np.nan_to_num(self.on_grid(per_day), nan=0.0)
        return np.asarray(self.counts @ v, dtype=float)


def boot_p(boot: npt.ArrayLike, estimate: float, alternative: Alternative) -> float:
    """Centred bootstrap p-value of H1: θ > 0 (``greater``) or θ < 0 (``less``)."""
    b = np.asarray(boot, dtype=float)
    b = b[np.isfinite(b)]
    if not len(b) or not math.isfinite(estimate):
        return math.nan
    d = b - estimate
    hits = (d >= estimate).sum() if alternative == "greater" else (d <= estimate).sum()
    return float((1 + hits) / (len(b) + 1))


def boot_p_two(boot: npt.ArrayLike, estimate: float) -> float:
    """Two-sided centred bootstrap p-value of H0: θ = 0."""
    b = np.asarray(boot, dtype=float)
    b = b[np.isfinite(b)]
    if not len(b) or not math.isfinite(estimate):
        return math.nan
    hits = (np.abs(b - estimate) >= abs(estimate)).sum()
    return float((1 + hits) / (len(b) + 1))


def percentile_ci(boot: npt.ArrayLike, level: float) -> tuple[float, float]:
    b = np.asarray(boot, dtype=float)
    b = b[np.isfinite(b)]
    if not len(b):
        return math.nan, math.nan
    lo, hi = np.quantile(b, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


@dataclass(frozen=True)
class Estimate:
    """A statistic with its Newey–West t (daily means only), bootstrap SE, CI and one-sided p."""

    value: float
    nw_t: float
    boot_se: float
    ci_low: float
    ci_high: float
    p: float
    alternative: str
    n_days: int
    n_obs: int

    def as_dict(self, prefix: str = "") -> dict[str, Any]:
        return {f"{prefix}{k}": v for k, v in asdict(self).items()}


def daily_mean_estimate(
    daily: pd.Series, boot: Bootstrap, lags: int, level: float, alternative: Alternative, n_obs: int = 0
) -> Estimate:
    """Mean of a daily series with NW t, bootstrap SE / CI and the centred one-sided p."""
    mean, t, n = nw_t(daily, lags)
    bm = boot.means(daily) if n >= 2 else np.full(1, np.nan)
    lo, hi = percentile_ci(bm, level)
    fin = bm[np.isfinite(bm)]
    se = float(np.std(fin, ddof=1)) if len(fin) > 1 else math.nan
    return Estimate(
        float(mean), float(t), se, lo, hi, boot_p(bm, float(mean), alternative), alternative, n, n_obs
    )


def ratio_estimate(
    num: pd.Series,
    den: pd.Series,
    boot: Bootstrap,
    level: float,
    alternative: Alternative,
    n_obs: int = 0,
    *,
    offset: float = 0.0,
) -> Estimate:
    """θ = offset + Σ num / Σ den over sessions (e.g. ΔR² = Σ(SSE_bench − SSE_full) / Σ SST), bootstrapped
    from the per-session sums."""
    value = offset + float(np.nansum(num.to_numpy(dtype=float)) / np.nansum(den.to_numpy(dtype=float)))
    with np.errstate(invalid="ignore", divide="ignore"):
        bs = offset + boot.sums(num) / boot.sums(den)
    lo, hi = percentile_ci(bs, level)
    fin = bs[np.isfinite(bs)]
    se = float(np.std(fin, ddof=1)) if len(fin) > 1 else math.nan
    n_days = int(pd.concat([num, den], axis=1).dropna().shape[0])
    return Estimate(value, math.nan, se, lo, hi, boot_p(bs, value, alternative), alternative, n_days, n_obs)


# --- point metrics -----------------------------------------------------------------------------------------


def oos_r2(y: npt.ArrayLike, yhat: npt.ArrayLike, mean: float = 0.0) -> float:
    """1 − Σ(y − ŷ)² / Σ(y − mean)² over the rows with both (mean 0: the zero forecast, §11.1)."""
    a, b = np.asarray(y, dtype=float), np.asarray(yhat, dtype=float)
    keep = np.isfinite(a) & np.isfinite(b)
    den = float(((a[keep] - mean) ** 2).sum())
    return 1.0 - float(((a[keep] - b[keep]) ** 2).sum()) / den if den > 0 else math.nan


def quintile_spread(
    frame: pd.DataFrame, signal: str, target: str, min_names: int, q: int = 5, *, session: str = "session"
) -> pd.Series:
    """Per session: mean target of the top signal quantile minus the bottom one (rank-based quantiles)."""
    d = frame[[session, signal, target]].dropna()
    out: dict[object, float] = {}
    for s, g in d.groupby(session, sort=True):
        if len(g) < max(min_names, q):
            continue
        r = g[signal].rank(method="first").to_numpy(dtype=float)
        bucket = np.ceil(r * q / len(g)).astype(int)
        top, bot = g[target].to_numpy()[bucket == q], g[target].to_numpy()[bucket == 1]
        out[s] = float(top.mean() - bot.mean())
    return pd.Series(out, dtype=float, name=f"qspread_{signal}_{target}")


def spearman(x: npt.ArrayLike, y: npt.ArrayLike) -> float:
    """Pooled Spearman correlation over the rows with both values (NaN with fewer than 3 or a constant)."""
    a = pd.Series(np.asarray(x, dtype=float))
    b = pd.Series(np.asarray(y, dtype=float))
    keep = a.notna() & b.notna()
    ra, rb = a[keep].rank().to_numpy(), b[keep].rank().to_numpy()
    if len(ra) < 3 or np.ptp(ra) == 0 or np.ptp(rb) == 0:
        return math.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def three_class(q1: npt.ArrayLike) -> FloatArray:
    """(n, 9) probabilities of Q1's levels → (n, 3) probabilities of fall / no move / rise."""
    p = np.asarray(q1, dtype=float)
    if p.ndim != 2 or p.shape[1] != Q1_LEVELS:
        raise ValueError(f"expected (n, {Q1_LEVELS}) Q1 probabilities, got {p.shape}")
    return np.column_stack(
        [p[:, list(Q1_FALL_LEVELS)].sum(1), p[:, Q1_FLAT_LEVEL], p[:, list(Q1_RISE_LEVELS)].sum(1)]
    )


def realized_class(target: npt.ArrayLike, band: float) -> IntArray:
    """0 fall (<= −band), 2 rise (>= band), 1 no move (|z| < band); −1 where the target is missing."""
    z = np.asarray(target, dtype=float)
    out = np.where(z <= -band, FALL, np.where(z >= band, RISE, FLAT)).astype(np.int64)
    out[~np.isfinite(z)] = -1
    return out


def log_loss(probs: npt.ArrayLike, y: npt.ArrayLike, eps: float = 1e-12) -> float:
    p = np.asarray(probs, dtype=float)
    lab = np.asarray(y, dtype=np.int64)
    keep = lab >= 0
    if not keep.any():
        return math.nan
    return float(-np.log(np.clip(p[keep, lab[keep]], eps, 1.0)).mean())


def brier(probs: npt.ArrayLike, y: npt.ArrayLike) -> float:
    p = np.asarray(probs, dtype=float)
    lab = np.asarray(y, dtype=np.int64)
    keep = lab >= 0
    if not keep.any():
        return math.nan
    onehot = np.eye(p.shape[1])[lab[keep]]
    return float(((p[keep] - onehot) ** 2).sum(axis=1).mean())


def climatology(y_ref: npt.ArrayLike, k: int = 3) -> FloatArray:
    """Class shares of a reference sample (the climatology forecast)."""
    lab = np.asarray(y_ref, dtype=np.int64)
    lab = lab[lab >= 0]
    return np.bincount(lab, minlength=k).astype(float) / max(len(lab), 1)


def skill(score: float, score_climatology: float) -> float:
    return 1.0 - score / score_climatology if score_climatology > 0 else math.nan


def ece(probs: npt.ArrayLike, y: npt.ArrayLike, bins: int) -> float:
    """Top-label ECE over ``bins`` equal-width confidence bins (rows with y = −1 are skipped)."""
    p = np.asarray(probs, dtype=float)
    lab = np.asarray(y, dtype=np.int64)
    keep = lab >= 0
    p, lab = p[keep], lab[keep]
    if len(lab) == 0:
        return math.nan
    conf = p.max(1)
    hit = (p.argmax(1) == lab).astype(float)
    idx = np.minimum((conf * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.sum() / len(lab) * abs(hit[m].mean() - conf[m].mean())
    return float(total)


def auc(score: npt.ArrayLike, label: npt.ArrayLike) -> float:
    """P(score of a positive > score of a negative), ties counted half (Mann–Whitney)."""
    s = np.asarray(score, dtype=float)
    lab = np.asarray(label, dtype=float)
    keep = np.isfinite(s) & np.isfinite(lab)
    s, lab = s[keep], lab[keep].astype(bool)
    n1, n0 = int(lab.sum()), int((~lab).sum())
    if n1 == 0 or n0 == 0:
        return math.nan
    r = pd.Series(s).rank().to_numpy()
    return float((r[lab].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def apply_map(x: npt.ArrayLike, mapping: Mapping[str, Sequence[float]]) -> FloatArray:
    """A stored monotone map {x: breakpoints ascending, y: values} at ``x`` (flat beyond the fitted range)."""
    bx = np.asarray(mapping["x"], dtype=float)
    by = np.asarray(mapping["y"], dtype=float)
    if bx.ndim != 1 or len(bx) != len(by) or len(bx) < 1 or bool((np.diff(bx) < 0).any()):
        raise ValueError("a stored map needs ascending breakpoints x and as many values y")
    v = np.asarray(x, dtype=float)
    out: FloatArray = np.asarray(np.interp(v, bx, by), dtype=float)
    out[~np.isfinite(v)] = np.nan
    return out


def entropy_confidence(probs: npt.ArrayLike) -> FloatArray:
    """1 − H(p)/log k per row (1 = one option certain, 0 = uniform)."""
    p = np.asarray(probs, dtype=float)
    k = p.shape[1]
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -np.where(p > 0, p * np.log(p), 0.0).sum(axis=1)
    return np.asarray(1.0 - h / math.log(k), dtype=float) if k > 1 else np.ones(len(p))


# --- multiple testing -----------------------------------------------------------------------------------


def holm(p: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (missing p stay NaN and do not count toward the family size)."""
    items = sorted(((v, k) for k, v in p.items() if math.isfinite(v)), key=lambda t: (t[0], t[1]))
    m = len(items)
    out = {k: math.nan for k in p}
    running = 0.0
    for i, (v, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * v))
        out[k] = running
    return out


def bh(p: Mapping[str, float]) -> dict[str, float]:
    """Benjamini–Hochberg q-values (step-up; missing p stay NaN and do not count)."""
    items = sorted(((v, k) for k, v in p.items() if math.isfinite(v)), key=lambda t: (t[0], t[1]))
    m = len(items)
    out = {k: math.nan for k in p}
    running = 1.0
    for i in range(m - 1, -1, -1):
        v, k = items[i]
        running = min(running, v * m / (i + 1))
        out[k] = min(1.0, running)
    return out
