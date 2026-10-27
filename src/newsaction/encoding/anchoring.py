"""Anchoring: does a model that sees the reaction read the news differently? (PREREG §8.4; PRD NA-07 S4)

On the same D2 events, Call A (``callA_d2_E3``: W2 news, no reaction) and Call B (``callB_d2_E3``: the same
state plus ``reaction_so_far``) give N̂_A and N̂_B. G = z_cc,t, the reaction Call B is shown (PREREG §5.5).

Per model (``stats``):
- **slope**: b in the pooled OLS N̂_B = a + b·G + c·N̂_A + e, with HC1 and session-clustered (CR1) standard
  errors; c and R² are reported beside it;
- **corr**: the Pearson correlation of N̂_A and N̂_B (Spearman reported beside it).

**Rule** (``present``): a model anchors iff slope >= ``slope_min`` (0.30) or corr < ``corr_max`` (0.70).
Across models (``combine``, PREREG §15 NA-07 row): anchoring is present iff any model anchors; the recorded
slope is the largest and the recorded corr the smallest over the models, so the rule applied to the recorded
pair gives the same verdict. calls_per_event = 2 if present (N̂ from Call A), else 1.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class OLS:
    coef: FloatArray
    se_hc1: FloatArray
    se_cluster: FloatArray
    r2: float
    n: int
    n_clusters: int


def ols(y: npt.ArrayLike, x: npt.ArrayLike, clusters: Sequence[object]) -> OLS:
    """OLS of ``y`` on [1, x] with HC1 and cluster-robust (CR1: G/(G−1)·(n−1)/(n−k)) standard errors."""
    yy = np.asarray(y, dtype=float)
    xx = np.column_stack([np.ones(len(yy)), np.asarray(x, dtype=float)])
    n, k = xx.shape
    if n <= k:
        raise ValueError(f"OLS needs more than {k} rows, got {n}")
    xtx_inv = np.linalg.inv(xx.T @ xx)
    beta = xtx_inv @ xx.T @ yy
    resid = yy - xx @ beta
    meat = (xx * resid[:, None] ** 2).T @ xx
    v_hc1 = xtx_inv @ meat @ xtx_inv * n / (n - k)
    codes, uniq = pd.factorize(pd.Series(list(clusters)), sort=True)
    g = len(uniq)
    scores = np.zeros((g, k))
    np.add.at(scores, codes, xx * resid[:, None])
    v_cl = xtx_inv @ (scores.T @ scores) @ xtx_inv
    v_cl *= (g / (g - 1)) * ((n - 1) / (n - k)) if g > 1 else math.nan
    tss = float(((yy - yy.mean()) ** 2).sum())
    return OLS(
        coef=beta,
        se_hc1=np.sqrt(np.diag(v_hc1)),
        se_cluster=np.sqrt(np.diag(v_cl)),
        r2=1.0 - float((resid**2).sum()) / tss if tss > 0 else math.nan,
        n=n,
        n_clusters=g,
    )


@dataclass(frozen=True)
class Stats:
    n: int
    n_sessions: int
    slope: float
    slope_se_hc1: float
    slope_se_cluster: float
    coef_n_hat_a: float
    intercept: float
    r2: float
    corr: float
    spearman: float
    slope_without_control: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stats(frame: pd.DataFrame) -> Stats:
    """``frame``: one row per event with ``n_hat_a``, ``n_hat_b``, ``g`` and ``session``; rows missing any
    of them are dropped."""
    d = frame[["n_hat_a", "n_hat_b", "g", "session"]].dropna()
    fit = ols(d["n_hat_b"], d[["g", "n_hat_a"]].to_numpy(), d["session"].tolist())
    simple = ols(d["n_hat_b"], d[["g"]].to_numpy(), d["session"].tolist())
    return Stats(
        n=fit.n,
        n_sessions=fit.n_clusters,
        slope=float(fit.coef[1]),
        slope_se_hc1=float(fit.se_hc1[1]),
        slope_se_cluster=float(fit.se_cluster[1]),
        coef_n_hat_a=float(fit.coef[2]),
        intercept=float(fit.coef[0]),
        r2=fit.r2,
        corr=float(np.corrcoef(d["n_hat_a"], d["n_hat_b"])[0, 1]),
        spearman=float(d["n_hat_a"].rank().corr(d["n_hat_b"].rank())),
        slope_without_control=float(simple.coef[1]),
    )


def present(slope: float, corr: float, slope_min: float, corr_max: float) -> bool:
    """PREREG §8.4: anchoring is present if the slope is >= ``slope_min`` or corr(N̂_A, N̂_B) < ``corr_max``."""
    return bool(slope >= slope_min or corr < corr_max)


@dataclass(frozen=True)
class Verdict:
    present: bool
    slope: float  # the largest slope over the models
    corr: float  # the smallest correlation over the models
    calls_per_event: int
    by_model: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def combine(per_model: Mapping[str, tuple[float, float]], slope_min: float, corr_max: float) -> Verdict:
    """``per_model``: model → (slope, corr). Present iff any model anchors (module docstring)."""
    if not per_model:
        raise ValueError("no model to combine")
    by_model = {m: present(s, c, slope_min, corr_max) for m, (s, c) in per_model.items()}
    slope = max(s for s, _ in per_model.values())
    corr = min(c for _, c in per_model.values())
    yes = any(by_model.values())
    if yes != present(slope, corr, slope_min, corr_max):  # pragma: no cover - identity of max/min and any
        raise AssertionError("the combined verdict disagrees with the rule on the recorded slope and corr")
    return Verdict(present=yes, slope=slope, corr=corr, calls_per_event=2 if yes else 1, by_model=by_model)
