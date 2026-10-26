"""Tournament metrics (PREREG §11.1–11.2; PRD NA-06 S2–S3).

- **Daily IC.** For each session, the Spearman correlation (Pearson on average ranks) between a signal and a
  target over the events that have both, on days with at least ``min_names_per_day`` such events. A day on
  which the signal (or the target) is constant has IC 0: the model ranks nothing that day, and dropping the
  day would keep only the days on which it discriminates.
- **Summary.** The mean daily IC with its Newey–West t (``nw_lags`` lags, PREREG §11.1; ``news.audit.nw_t``),
  se = mean / t, and the number of days.
- **Paired difference** of two daily IC series on their common days, with its Newey–West t (probe d).
- **Calibration** (PREREG §11.2). Q1's nine levels collapse to three classes: fall (levels 0–3, below
  −0.5 typical daily moves), no meaningful move (level 4, |move| < 0.5) and rise (levels 5–8). A target's
  realized class is fall at or below −``class_band``, rise at or above ``class_band``, else no move. ECE is
  the top-label expected calibration error over ``ece_bins`` equal-width bins of the largest class
  probability: Σ_b (n_b / N) |accuracy_b − confidence_b|.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.news.audit import nw_t

FALL: Final = 0
FLAT: Final = 1
RISE: Final = 2
Q1_LEVELS: Final = 9
Q1_FALL_LEVELS: Final = (0, 1, 2, 3)
Q1_FLAT_LEVEL: Final = 4
Q1_RISE_LEVELS: Final = (5, 6, 7, 8)


@dataclass(frozen=True)
class ICStats:
    mean: float
    t: float
    se: float
    n_days: int

    def as_dict(self, prefix: str) -> dict[str, float | int]:
        return {
            f"{prefix}": self.mean,
            f"{prefix}_t": self.t,
            f"{prefix}_se": self.se,
            f"{prefix}_days": self.n_days,
        }


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


def ic_stats(series: pd.Series, lags: int) -> ICStats:
    """Mean of a daily series with its Newey–West t and se (NaN with fewer than 3 days)."""
    mean, t, n = nw_t(series, lags)
    se = abs(mean / t) if t and math.isfinite(t) and t != 0 else math.nan
    return ICStats(mean=float(mean), t=float(t), se=float(se), n_days=int(n))


def paired(a: pd.Series, b: pd.Series, lags: int) -> ICStats:
    """``a − b`` on the common days (e.g. unmasked − masked daily IC), with its Newey–West t."""
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    return ic_stats(both["a"] - both["b"], lags)


def three_class(q1: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """(n, 9) probabilities of Q1's levels → (n, 3) probabilities of fall / no move / rise."""
    p = np.asarray(q1, dtype=float)
    if p.ndim != 2 or p.shape[1] != Q1_LEVELS:
        raise ValueError(f"expected (n, {Q1_LEVELS}) Q1 probabilities, got {p.shape}")
    return np.column_stack(
        [p[:, list(Q1_FALL_LEVELS)].sum(1), p[:, Q1_FLAT_LEVEL], p[:, list(Q1_RISE_LEVELS)].sum(1)]
    )


def realized_class(target: npt.ArrayLike, band: float) -> npt.NDArray[np.int64]:
    """0 fall (<= −band), 2 rise (>= band), 1 no move (|z| < band); −1 where the target is missing."""
    z = np.asarray(target, dtype=float)
    out = np.where(z <= -band, FALL, np.where(z >= band, RISE, FLAT)).astype(np.int64)
    out[~np.isfinite(z)] = -1
    return out


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


def spearman(x: npt.ArrayLike, y: npt.ArrayLike) -> tuple[float, float, int]:
    """(rho, two-sided p, n) of the Spearman correlation; p is exact (all permutations) for n <= 8 and from
    the t approximation above."""
    a = pd.Series(np.asarray(x, dtype=float))
    b = pd.Series(np.asarray(y, dtype=float))
    keep = a.notna() & b.notna()
    ra, rb = a[keep].rank().to_numpy(), b[keep].rank().to_numpy()
    n = len(ra)
    if n < 3 or np.ptp(ra) == 0 or np.ptp(rb) == 0:
        return math.nan, math.nan, n
    rho = float(np.corrcoef(ra, rb)[0, 1])
    if n <= 8:
        perms = np.array(list(itertools.permutations(rb)))
        sims = np.array([np.corrcoef(ra, p)[0, 1] for p in perms])
        return rho, float(np.mean(np.abs(sims) >= abs(rho) - 1e-12)), n
    t = rho * math.sqrt((n - 2) / max(1e-12, 1 - rho**2))
    return rho, float(math.erfc(abs(t) / math.sqrt(2))), n


def quantiles(values: Sequence[float] | pd.Series, qs: Sequence[float] = (0.5, 0.95)) -> list[float]:
    v = pd.Series(values, dtype=float).dropna()
    return [float(v.quantile(q)) if len(v) else math.nan for q in qs]
