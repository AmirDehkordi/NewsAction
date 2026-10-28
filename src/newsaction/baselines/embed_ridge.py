"""Embedding + ridge baseline (PREREG §10.2; PRD NA-09 S3), in the style of Chen–Kelly–Xiu.

- **Features.** The mean of the bge-small vectors (NA-02, title_clean + snippet_clean, 384-d) of the
  articles of the event's Call A state, and the W0 attention block (log1p of articles, stories, duplicates,
  the attention ratio and the 60-session mean). Missing attention values take the train median; every
  feature is standardized with the train mean and sd.
- **Targets.** e5 (→ N_hat) and |z_cc| (→ mag_hat), one ridge each, fit on train.
- **λ** from ``embed_ridge.lambdas`` (a log grid), chosen on val-A outside the embargo: the highest mean
  daily IC with e5 for N_hat, the highest R² of |z_cc| (against the train mean) for mag_hat. Every λ is
  logged as a trial (CLAUDE.md B10).
- **P_up / P_down**: the val-A isotonic maps of N_hat (``fitting.prob_maps``).

Predictions: every Call A D0 state, test included (the inputs are the state's articles and t−1 counts).
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd
import sklearn
from sklearn.linear_model import Ridge

from newsaction.baselines import BaselinesConfig, log_trial
from newsaction.baselines.data import ATTENTION, event_embeddings
from newsaction.baselines.fitting import fit_rows, ic, prob_maps, r2, save_model, tune_rows
from newsaction.baselines.schema import FitRecord, grid_rows, row_range
from newsaction.paths import Layout

MODEL: Final = "embed_ridge"
DIM: Final = 384


def design(
    frame: pd.DataFrame, emb: npt.NDArray[np.float32], train: npt.NDArray[np.bool_]
) -> tuple[npt.NDArray[np.float64], dict[str, Any]]:
    """Standardized [embedding mean, log1p attention] with the train statistics, and those statistics."""
    att = np.log1p(frame[list(ATTENTION)].to_numpy(dtype=float).clip(min=0))
    fill = np.nanmedian(att[train], axis=0)
    att = np.where(np.isnan(att), fill, att)
    x = np.column_stack([emb.astype(np.float64), att])
    mean, sd = x[train].mean(axis=0), x[train].std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    return (x - mean) / sd, {"fill": fill.tolist(), "mean": mean.tolist(), "sd": sd.tolist()}


def fit_predict(frame: pd.DataFrame, cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    emb = event_embeddings(frame, layout)
    in_fit = (frame["split"] == cfg.fit_split).to_numpy()
    x, stats = design(frame, emb, in_fit)
    features = (*[f"bge_{i}" for i in range(DIM)], *[f"log1p_{c}" for c in ATTENTION])
    out: dict[str, npt.NDArray[np.float64]] = {}
    fits: dict[str, dict[str, Any]] = {}
    for target, metric in (("e5", "ic_e5"), ("abs_z_cc", "r2_abs_z_cc")):
        tr, tu = fit_rows(frame, cfg, target), tune_rows(frame, cfg, target)
        itr, itu = frame.index.get_indexer(tr.index), frame.index.get_indexer(tu.index)
        y = tr[target].to_numpy(dtype=float)
        grid = []
        for lam in cfg.embed_ridge.lambdas:
            p = Ridge(alpha=lam).fit(x[itr], y).predict(x[itu])
            val = ic(tu, p, target, cfg)[0] if metric == "ic_e5" else r2(p, tu[target], float(y.mean()))
            grid.append({"lambda": lam, metric: val})
            params = {"lambda": lam, "target": target, "features": "bge384_mean+attention5_log1p_std"}
            log_trial("baseline_grid", f"{MODEL}:{target}", params, "val_a", metric, val, layout=layout)
        best = max(grid, key=lambda g: (np.nan_to_num(g[metric], nan=-np.inf), -g["lambda"]))
        m = Ridge(alpha=best["lambda"]).fit(x[itr], y)
        out[target] = m.predict(x)
        fits[target] = {"tr": tr, "tu": tu, "grid": grid, "best": best, "metric": metric, "m": m}
    maps, cal, up, down = prob_maps(frame, out["e5"], cfg)
    for target, f in fits.items():
        m, best, metric = f["m"], f["best"], f["metric"]
        payload: dict[str, Any] = {"lambda": best["lambda"], "intercept": float(m.intercept_)}
        payload |= {"coef": m.coef_.tolist(), **stats}
        save_model(
            FitRecord(
                model=MODEL, target=target, point="D0", features=features,
                fit=row_range(f["tr"], cfg.fit_split), tune=row_range(f["tu"], cfg.tune_split),
                calibration=cal if target == "e5" else None,
                selected={"lambda": best["lambda"], metric: best[metric]}, grid=grid_rows(f["grid"]),
                seed=cfg.seed, library={"sklearn": sklearn.__version__},
            ),
            {"ridge": payload},
            layout,
            prob_maps=maps.payload() if target == "e5" else None,
        )  # fmt: skip
    return pd.DataFrame(
        {
            "event_id": frame["event_id"].to_numpy(),
            "model": MODEL,
            "call": "A",
            "split": frame["split"].to_numpy(),
            "session": frame["session"].to_numpy(),
            "company_id": frame["company_id"].to_numpy(),
            "N_hat": out["e5"],
            "P_up": up,
            "P_down": down,
            "mag_hat": np.maximum(out["abs_z_cc"], 0.0),
            "extra": "{}",
        }
    )
