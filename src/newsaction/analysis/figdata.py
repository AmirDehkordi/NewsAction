"""NA-12 figure data (PRD NA-12 S2; descriptive, outside every family; PREREG §15 NA-12 row, pre-unblinding).

- **Event paths** (``event_paths``): CAR^lvl in A1.2 level units (ΣAR_cc / σ_cc,t, no √h) from the close of
  t−5 to the close of t+20, anchored at close(t−1) = 0. The post-event points are ``spec.plateau_rungs``
  (the frozen helper, equal to ``targets.py``'s rungs) over k = 0 … 20, purged like every rung; a pre-event
  point is −ΣAR_cc from t−k+1 to t−1 over σ_cc,t (the price relative to close(t−1)).
- **Figure 1** (``group_paths``): mean path per V decile (D0 events, V from W0 news) and per RG class (D2
  events, PREREG §7 RG from Call A's W2 N̂ and G = z_cc,t), each with its mean V, plus the open, 10:00 and
  day-t 30-minute points (``slot_path``) for the deciles.
- **Figure 2** (``drift_by_g``): mean sign(G)·y2 by |G| bin within terciles of news strength |V_W2|.
- **Reliability bins** (``reliability``): ``metrics.ece``'s 15 equal-width bins of the top three-class
  probability: count, mean confidence, hit rate.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.analysis import metrics as mx
from newsaction.analysis import slot_path, spec

PRE: Final = 5
POST: Final = 20
G_BINS: Final = (0.5, 1.0, 2.0, 3.0)
PATH_COLUMNS: Final = (
    *[f"car_pre{k}" for k in range(PRE, 0, -1)],
    *[f"car_post{k}" for k in range(POST + 1)],
)


def _grid(daily: pd.DataFrame, col: str) -> pd.DataFrame:
    d = daily[["session", "symbol_id", col]].copy()
    d["session"] = pd.to_datetime(d["session"])
    return d.pivot_table(index="session", columns="symbol_id", values=col, aggfunc="first").sort_index()


def event_paths(
    daily: pd.DataFrame, rows: pd.DataFrame, split_end: Mapping[str, date], cfg: spec.AnalysisConfig
) -> pd.DataFrame:
    """``rows`` (event_id, session, symbol_id, split) with ``PATH_COLUMNS`` (module docstring)."""
    wide = cfg.convergence.model_copy(update={"plateau": (0, POST)})
    post = spec.plateau_rungs(daily, rows, split_end, cfg.model_copy(update={"convergence": wide}))
    out = rows[["event_id", "session", "symbol_id", "split"]].reset_index(drop=True).copy()
    for k in range(POST + 1):
        out[f"car_post{k}"] = post[f"car_lvl_c{k}"].to_numpy()
    ar, sig = _grid(daily, "ar_cc"), _grid(daily, "sigma_cc")
    idx = ar.index
    r_pos = idx.get_indexer(pd.Index(pd.to_datetime(out["session"])))
    c_pos = ar.columns.get_indexer(pd.Index(out["symbol_id"]))
    ok = (r_pos >= 0) & (c_pos >= 0)
    a = ar.to_numpy()
    s = sig.reindex(index=idx, columns=ar.columns).to_numpy()
    sigma = np.where(ok, s[np.where(ok, r_pos, 0), np.where(ok, c_pos, 0)], np.nan)
    total = np.zeros(len(out))
    out["car_pre1"] = np.where(ok, 0.0, np.nan)
    for k in range(2, PRE + 1):
        j = r_pos - (k - 1)  # AR of session t−k+1 moves the close of t−k to the close of t−k+1
        good = ok & (j >= 0)
        v = np.where(good, a[np.where(good, j, 0), np.where(ok, c_pos, 0)], np.nan)
        total = total + v
        out[f"car_pre{k}"] = -total / sigma
    return out[["event_id", "session", "symbol_id", "split", *PATH_COLUMNS]]


def _mean_se(x: pd.Series) -> tuple[float, float, int]:
    v = x.dropna().to_numpy(dtype=float)
    n = len(v)
    if n == 0:
        return float("nan"), float("nan"), 0
    return float(v.mean()), float(v.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan"), n


def group_paths(
    frame: pd.DataFrame, group: str, value: str, columns: Sequence[str], label: str
) -> list[dict[str, Any]]:
    """Long rows (figure, group, point, mean, se, n) of the mean of each path column by ``group``, with the
    group's mean ``value`` (V) and size."""
    rows: list[dict[str, Any]] = []
    for g, sub in frame.groupby(group, observed=True, sort=True):
        mv, _, nv = _mean_se(sub[value])
        for c in columns:
            if c not in sub.columns:
                continue
            m, se, n = _mean_se(sub[c])
            rows.append(
                {"figure": label, "group": str(g), "point": c, "mean": m, "se": se, "n": n, "mean_v": mv,
                 "n_group": nv}
            )  # fmt: skip
    return rows


def deciles(x: pd.Series, q: int = 10) -> pd.Series:
    """Decile labels 1…q of ``x`` (ties at bin edges dropped, so a near-constant V gives fewer groups)."""
    codes = pd.qcut(x.rank(method="first"), q, labels=False, duplicates="drop")
    return (codes + 1).astype("Int64")


def drift_by_g(frame: pd.DataFrame, g: str, y: str, strength: str, label: str) -> list[dict[str, Any]]:
    """Mean sign(G)·y by |G| bin (``G_BINS``) within terciles of |strength| (Figure 2)."""
    d = frame.dropna(subset=[g, y, strength]).copy()
    d["signed_y"] = np.sign(d[g].to_numpy(dtype=float)) * d[y].to_numpy(dtype=float)
    edges = [0.0, *G_BINS, np.inf]
    d["g_bin"] = pd.cut(
        d[g].abs(), edges, right=False, labels=[f"[{a:g}, {b:g})" for a, b in itertools.pairwise(edges)]
    )
    d["tercile"] = pd.qcut(d[strength].abs().rank(method="first"), 3, labels=["weak", "medium", "strong"])
    rows: list[dict[str, Any]] = []
    for (t, b), sub in d.groupby(["tercile", "g_bin"], observed=True, sort=True):
        m, se, n = _mean_se(sub["signed_y"])
        rows.append({"figure": label, "tercile": str(t), "g_bin": str(b), "mean": m, "se": se, "n": n,
                     "mean_abs_strength": float(sub[strength].abs().mean())})  # fmt: skip
    return rows


def reliability(
    probs: npt.ArrayLike, target: npt.ArrayLike, cfg: spec.AnalysisConfig
) -> list[dict[str, Any]]:
    """Per bin of the top three-class probability (``metrics.ece``'s bins): n, mean confidence, hit rate."""
    p3 = mx.three_class(probs)
    y = mx.realized_class(target, cfg.metrics.class_band)
    keep = y >= 0
    p3, y = p3[keep], y[keep]
    bins = cfg.metrics.ece_bins
    conf = p3.max(1)
    hit = (p3.argmax(1) == y).astype(float)
    idx = np.minimum((conf * bins).astype(int), bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        out.append(
            {"bin": b, "lo": b / bins, "hi": (b + 1) / bins, "n": int(m.sum()),
             "confidence": float(conf[m].mean()) if m.any() else float("nan"),
             "hit_rate": float(hit[m].mean()) if m.any() else float("nan")}
        )  # fmt: skip
    return out


SLOT_POINTS: Final = ("car_lvl_o0", "car_lvl_10", *slot_path.POINT_COLUMNS, "car_lvl_c0")
