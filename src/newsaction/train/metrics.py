"""Val-A metrics of the trained models (PREREG §11.1–11.4; PRD NA-08 S5, S8).

- **Daily IC:** per session, the cross-sectional Spearman correlation of a signal with a target over the
  events of that day (at least ``min_names_per_day``); the mean, with a Newey–West t (``nw_lags`` lags), as
  NA-02's audit computes it (``news.audit.daily_ic`` / ``nw_t``).
- **Bootstrap CI:** a stationary block bootstrap over days of the daily IC series (expected block 5, 10,000
  draws, seed 2026, ``arch``), percentile interval.
- **ECE:** top-label expected calibration error over 15 equal-width bins, with laya's bin edges (the
  notebook's ``ece``).
- **Temperature:** argmin over T of the mean NLL of softmax(z / T), to re-check the notebook's fit locally.

**Val-A only.** NA-08 computes no metric on val-B or test (CLAUDE.md C13; PRD NA-08 AC5): every public entry
point here takes the frame's split and calls ``require_val_a``, which refuses anything else.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from newsaction.news.audit import daily_ic, nw_t
from newsaction.train import EvaluationConfig, load_training_config

TEMP_BOUNDS = (0.05, 20.0)


class SplitError(ValueError):
    """A metric was asked for rows outside val-A."""


def require_val_a(splits: pd.Series | Sequence[str]) -> None:
    """Refuse any row that is not val-A (NA-08 never evaluates val-B or test)."""
    bad = sorted(set(pd.Series(list(splits)).astype(str)) - {"val_a"})
    if bad:
        raise SplitError(f"NA-08 computes metrics on val-A only; got rows of {bad}")


def _cfg(cfg: EvaluationConfig | None) -> EvaluationConfig:
    return load_training_config().evaluation if cfg is None else cfg


def ic_series(df: pd.DataFrame, signal: str, target: str, cfg: EvaluationConfig | None = None) -> pd.Series:
    """Daily Spearman IC of ``signal`` with ``target`` over val-A sessions (column ``session``)."""
    require_val_a(df["split"])
    return daily_ic(df, signal, target, _cfg(cfg).min_names_per_day)


def bootstrap_ci(
    series: pd.Series, cfg: EvaluationConfig | None = None, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile CI of the mean from a stationary block bootstrap over days."""
    from arch.bootstrap import StationaryBootstrap

    c = _cfg(cfg)
    x = np.asarray(series.dropna(), dtype=float)
    if len(x) < 3:
        return (float("nan"), float("nan"))
    bs = StationaryBootstrap(c.bootstrap_block, x, seed=c.bootstrap_seed)
    means = bs.apply(lambda v: np.array([v.mean()]), c.bootstrap_reps)[:, 0]
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def ic_summary(
    df: pd.DataFrame, signal: str, target: str, cfg: EvaluationConfig | None = None, ci: bool = True
) -> dict[str, Any]:
    """Mean daily IC, Newey–West t, days, events and (optionally) the block-bootstrap 95% CI."""
    c = _cfg(cfg)
    s = ic_series(df, signal, target, c)
    mean, t, n = nw_t(s, c.nw_lags)
    out: dict[str, Any] = {
        "signal": signal,
        "target": target,
        "ic": mean,
        "nw_t": t,
        "days": n,
        "events": int(df[[signal, target]].dropna().shape[0]),
    }
    if ci:
        out["ci95"] = list(bootstrap_ci(s, c))
    return out


def softmax(z: np.ndarray, t: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64) / t
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return np.asarray(e / e.sum(axis=-1, keepdims=True))


def nll(logits: np.ndarray, labels: np.ndarray, t: float = 1.0) -> float:
    """Mean negative log-likelihood of integer ``labels`` under softmax(logits / t); logits [n, k]."""
    z = np.asarray(logits, dtype=np.float64) / t
    m = z.max(axis=1, keepdims=True)
    lse = (m + np.log(np.exp(z - m).sum(axis=1, keepdims=True)))[:, 0]
    return float(np.mean(lse - z[np.arange(len(labels)), labels.astype(int)]))


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """argmin_T NLL on [0.05, 20] (log grid, then golden-section), as the notebook fits it."""
    lo, hi = math.log(TEMP_BOUNDS[0]), math.log(TEMP_BOUNDS[1])
    grid = np.linspace(lo, hi, 61)
    vals = [nll(logits, labels, math.exp(g)) for g in grid]
    i = int(np.argmin(vals))
    a, b = grid[max(0, i - 1)], grid[min(len(grid) - 1, i + 1)]
    phi = (math.sqrt(5) - 1) / 2
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = nll(logits, labels, math.exp(c)), nll(logits, labels, math.exp(d))
    for _ in range(40):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = nll(logits, labels, math.exp(c))
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = nll(logits, labels, math.exp(d))
    return float(math.exp((a + b) / 2))


def ece(probs: np.ndarray, labels: np.ndarray, bins: int = 15) -> float:
    """Top-label ECE: bins of max probability, |mean confidence − accuracy| weighted by bin share."""
    p = np.asarray(probs, dtype=np.float64)
    conf, correct = p.max(axis=1), (p.argmax(axis=1) == labels).astype(float)
    if not len(conf):
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        sel = ((conf >= lo) if i == 0 else (conf > lo)) & (conf <= hi)
        if sel.any():
            out += sel.mean() * abs(conf[sel].mean() - correct[sel].mean())
    return float(out)


def calibration(
    frame: pd.DataFrame, cfg: EvaluationConfig | None = None, prob_col: str = "probabilities"
) -> dict[str, Any]:
    """ECE, NLL and accuracy of one question's probabilities against ``label`` (val-A rows with a label)."""
    require_val_a(frame["split"])
    c = _cfg(cfg)
    f = frame[frame["label"].notna()]
    p = np.stack([np.asarray(v, dtype=np.float64) for v in f[prob_col]])
    y = f["label"].to_numpy(dtype=int)
    return {
        "n": len(f),
        "ece": ece(p, y, c.ece_bins),
        "nll": float(np.mean(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1.0)))),
        "accuracy": float((p.argmax(axis=1) == y).mean()),
    }
