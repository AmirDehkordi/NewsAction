"""The Model Confidence Set (Hansen, Lunde and Nason 2011, Econometrica 79(2)) for the stage-1 survivors of
PREREG §8.2.

**Input.** A T × k loss matrix: rows are days, columns are models; NA-06's loss is −(daily IC). Every model
needs a loss on every day (the caller keeps the days common to all models).

**Bootstrap.** Politis and Romano's stationary bootstrap of day indices (circular, geometric block lengths
with mean ``block``). One set of B index draws serves every elimination step and every pair of models.

**Statistics** (HLN §3.1.2), with d̄_ij = mean(L_i − L_j) and its bootstrap mean d̄*_ij:
- ``R``: var̂_ij = mean_b (d̄*_ij − d̄_ij)², t_ij = d̄_ij / √var̂_ij, T_R = max over i, j in the set of t_ij; the
  bootstrap statistic replaces d̄_ij by d̄*_ij − d̄_ij. The model eliminated is the i of the pair that attains
  T_R, the worse one. Two models with identical losses on every day have t_ij = 0;
- ``max``: t_i = (L̄_i − mean_j L̄_j) / √var̂_i, the deviations re-centred on the models still in the set,
  T_max = max_i t_i; the models attaining it are eliminated.

**p-values.** Each step's p-value is the bootstrap share with T* >= T. A model's MCS p-value is the largest
step p-value up to its elimination, and the models never eliminated have 1. The set at level α keeps the
models with MCS p-value >= α (HLN's definition). Given the same bootstrap indices this reproduces
``arch.bootstrap.MCS``, which counts T* > T and keeps p > α (tests/test_tournament_mcs.py).

**CLI** (verification): ``python -m newsaction.tournament.mcs --seed 7`` reruns the stage-1 MCS from
``artifacts/NA-06/stage1_daily_ic.csv`` with another seed and compares the set with ``mcs.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.paths import resolve_layout
from newsaction.tournament import ARTIFACTS, tournament_config

DAILY_IC_FILE: Final = f"{ARTIFACTS}/stage1_daily_ic.csv"
MCS_FILE: Final = f"{ARTIFACTS}/mcs.json"
_CHUNK_REPS: Final = 2000

Statistic = Literal["R", "max"]


@dataclass(frozen=True)
class MCSResult:
    models: list[str]
    pvalues: dict[str, float]  # MCS p-value per model
    steps: list[dict[str, Any]]  # elimination order: model, step p-value, statistic value
    included: list[str]  # MCS p-value >= alpha, in the input column order
    statistic: str
    alpha: float
    reps: int
    block: float
    seed: int | None
    n_days: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stationary_indices(t: int, reps: int, block: float, rng: np.random.Generator) -> npt.NDArray[np.int64]:
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


def _boot_means(losses: npt.NDArray[np.float64], idx: npt.NDArray[np.int64]) -> npt.NDArray[np.float64]:
    out = np.empty((idx.shape[0], losses.shape[1]))
    for a in range(0, idx.shape[0], _CHUNK_REPS):
        out[a : a + _CHUNK_REPS] = losses[idx[a : a + _CHUNK_REPS]].mean(axis=1)
    return out


def _steps_r(
    mean: npt.NDArray[np.float64], boot: npt.NDArray[np.float64]
) -> list[tuple[list[int], float, float]]:
    k = len(mean)
    d = mean[:, None] - mean[None, :]
    ds = boot[:, :, None] - boot[:, None, :] - d
    var = (ds**2).mean(axis=0)
    same = var <= 0.0
    std_d = np.where(same, 0.0, d / np.sqrt(np.where(same, 1.0, var)))
    std_ds = np.where(same, 0.0, ds / np.sqrt(np.where(same, 1.0, var)))
    included = np.ones(k, dtype=bool)
    steps: list[tuple[list[int], float, float]] = []
    while included.sum() > 1:
        ind = np.flatnonzero(included)
        sub = std_d[np.ix_(ind, ind)]
        stat = float(sub.max())
        sim = std_ds[:, ind][:, :, ind].max(axis=(1, 2))
        p = float((sim >= stat).mean())
        i = int(np.argwhere(sub == stat)[0][0])
        steps.append(([int(ind[i])], p, stat))
        included[ind[i]] = False
    return steps


def _steps_max(
    mean: npt.NDArray[np.float64], boot: npt.NDArray[np.float64]
) -> list[tuple[list[int], float, float]]:
    k = len(mean)
    dev = boot - mean[None, :]
    included = np.ones(k, dtype=bool)
    steps: list[tuple[list[int], float, float]] = []
    while included.sum() > 1:
        ind = np.flatnonzero(included)
        dv = dev[:, ind] - dev[:, ind].mean(axis=1, keepdims=True)
        sd = np.sqrt((dv**2).mean(axis=0))
        sd = np.where(sd > 0, sd, np.inf)
        t_i = (mean[ind] - mean[ind].mean()) / sd
        stat = float(t_i.max())
        sim = (dv / sd).max(axis=1)
        p = float((sim >= stat).mean())
        worst = [int(ind[j]) for j in np.flatnonzero(t_i == stat)]
        steps.append((worst, p, stat))
        included[worst] = False
    return steps


def mcs(
    losses: pd.DataFrame,
    *,
    alpha: float,
    reps: int,
    block: float,
    seed: int | None,
    statistic: Statistic = "R",
    indices: npt.ArrayLike | None = None,
) -> MCSResult:
    """The MCS of the columns of ``losses`` (module docstring). ``indices`` (reps × T) replaces the bootstrap
    draws, e.g. arch's, to compare implementations."""
    loss = losses.to_numpy(dtype=float)
    if loss.ndim != 2 or loss.shape[1] < 2:
        raise ValueError("losses must be a T × k matrix with k >= 2")
    if not np.isfinite(loss).all():
        raise ValueError("losses must be finite on every day for every model (keep the common days)")
    t, _ = loss.shape
    if indices is None:
        idx = stationary_indices(t, reps, block, np.random.default_rng(seed))
    else:
        idx = np.asarray(indices, dtype=np.int64)
        if idx.ndim != 2 or idx.shape[1] != t:
            raise ValueError(f"indices must be (reps, {t})")
    boot = _boot_means(loss, idx)
    mean = loss.mean(axis=0)
    raw = _steps_r(mean, boot) if statistic == "R" else _steps_max(mean, boot)
    models = [str(c) for c in losses.columns]
    pvalues: dict[str, float] = {}
    steps: list[dict[str, Any]] = []
    running = 0.0
    for worst, p, stat in raw:
        running = max(running, p)
        for w in worst:
            pvalues[models[w]] = running
            steps.append({"model": models[w], "step_pvalue": p, "mcs_pvalue": running, "statistic": stat})
    for m in models:
        if m not in pvalues:
            pvalues[m] = 1.0
            steps.append({"model": m, "step_pvalue": 1.0, "mcs_pvalue": 1.0, "statistic": None})
    return MCSResult(
        models=models,
        pvalues=pvalues,
        steps=steps,
        included=[m for m in models if pvalues[m] >= alpha],
        statistic=statistic,
        alpha=alpha,
        reps=int(idx.shape[0]),
        block=block,
        seed=seed,
        n_days=t,
    )


def loss_matrix(daily_ic: pd.DataFrame) -> pd.DataFrame:
    """Long daily IC (model, session, ic) → days × models losses (−IC) on the days every model has."""
    wide = daily_ic.pivot(index="session", columns="model", values="ic").sort_index()
    return -wide.dropna(axis=0, how="any")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--statistic", choices=["R", "max"], default=None)
    args = ap.parse_args(argv)
    lay = resolve_layout(None)
    cfg = tournament_config(lay).mcs
    losses = loss_matrix(pd.read_csv(lay.root / DAILY_IC_FILE))
    res = mcs(
        losses,
        alpha=cfg.alpha,
        reps=args.reps or cfg.reps,
        block=cfg.block,
        seed=args.seed,
        statistic=args.statistic or cfg.statistic,
    )
    recorded = json.loads((lay.root / MCS_FILE).read_text(encoding="utf-8"))["stage1"]["included"]
    print(f"days {res.n_days}, models {len(res.models)}, statistic {res.statistic}, seed {res.seed}")
    for s in res.steps:
        print(f"  {s['model']:45s} step p {s['step_pvalue']:.4f}  MCS p {s['mcs_pvalue']:.4f}")
    print(f"included (this run): {res.included}")
    print(f"included (mcs.json): {recorded}")
    print(f"same set: {sorted(res.included) == sorted(recorded)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
