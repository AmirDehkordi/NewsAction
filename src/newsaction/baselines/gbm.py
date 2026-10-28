"""LightGBM fitting shared by the tags and price-only baselines (PRD NA-09 S4–S5).

``fit_select`` fits one regressor per configuration of the small grid (``GbmConfig.grid``) on train, scores
each on val-A outside the embargo (mean daily IC with the target, or the R² of |z_cc| against the train mean),
logs every configuration as a trial, refits nothing (the selected configuration's train fit is the model)
and returns it with its fit record. Determinism: fixed seed, ``deterministic`` and ``force_col_wise``, a
fixed thread count; LightGBM's model text is saved in the record's JSON.

**One OpenMP runtime per process.** LightGBM's library loads Homebrew's ``libomp`` (its rpath) and torch
loads its own copy; on this machine a process holding both segfaults (LightGBM imported before a torch model
loads, or torch imported before a LightGBM fit; NA-09 decisions). ``lightgbm`` is therefore imported only
inside the functions that fit, as ``events.learned`` does, so importing ``newsaction.baselines`` never loads
it; the ``fit`` stage never loads torch, and the tests run their LightGBM fits in a spawned process.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.baselines import BaselinesConfig, GbmConfig, log_trial
from newsaction.baselines.fitting import fit_rows, ic, r2, save_model, tune_rows
from newsaction.baselines.schema import FitRecord, Range, grid_rows, row_range
from newsaction.paths import Layout

if TYPE_CHECKING:
    import lightgbm as lgb

THREADS: Final = 4
CATEGORICAL: Final = ("tier", "sector")


@dataclass(frozen=True)
class Fitted:
    model: lgb.LGBMRegressor
    record: FitRecord
    predict_all: npt.NDArray[np.float64]


def matrix(frame: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    """The feature frame: numeric columns as float64, ``CATEGORICAL`` as pandas categories with a fixed,
    sorted category list (so train and prediction rows share codes)."""
    x = pd.DataFrame(index=frame.index)
    for c in features:
        if c in CATEGORICAL:
            cats = sorted(str(v) for v in frame[c].dropna().unique())
            x[c] = pd.Categorical(frame[c].astype("string"), categories=cats)
        else:
            x[c] = frame[c].astype("float64")
    return x


def configs(gc: GbmConfig) -> list[dict[str, Any]]:
    g = gc.grid
    return [
        {"num_leaves": a, "min_child_samples": b, "n_estimators": c}
        for a, b, c in itertools.product(g.num_leaves, g.min_child_samples, g.n_estimators)
    ]


def regressor(gc: GbmConfig, params: dict[str, Any], seed: int) -> lgb.LGBMRegressor:
    import lightgbm as lgb

    return lgb.LGBMRegressor(
        learning_rate=gc.learning_rate,
        subsample=gc.subsample,
        subsample_freq=gc.subsample_freq,
        colsample_bytree=gc.colsample_bytree,
        random_state=seed,
        deterministic=True,
        force_col_wise=True,
        n_jobs=THREADS,
        verbose=-1,
        **params,
    )


def fit_select(
    frame: pd.DataFrame,
    cfg: BaselinesConfig,
    gc: GbmConfig,
    *,
    model: str,
    target: str,
    metric: str,
    features: Sequence[str],
    point: str,
    calibration: Range | None = None,
    layout: Layout | None = None,
) -> Fitted:
    """Grid on val-A, the best configuration's train fit, its predictions for every row of ``frame``."""
    import lightgbm as lgb

    tr, tu = fit_rows(frame, cfg, target), tune_rows(frame, cfg, target)
    x = matrix(frame, features)
    xtr, xtu = x.loc[tr.index], x.loc[tu.index]
    y = tr[target].to_numpy(dtype=float)
    grid: list[dict[str, Any]] = []
    fitted: list[lgb.LGBMRegressor] = []
    for params in configs(gc):
        m = regressor(gc, params, cfg.seed).fit(
            xtr, y, categorical_feature=[c for c in features if c in CATEGORICAL]
        )
        p = m.predict(xtu)
        val = ic(tu, p, target, cfg)[0] if metric.startswith("ic_") else r2(p, tu[target], float(y.mean()))
        grid.append({**params, metric: val})
        fitted.append(m)
        log_trial(
            "baseline_grid", f"{model}:{target}", {**params, "target": target, "features": list(features)},
            "val_a", metric, val, layout=layout,
        )  # fmt: skip
    scores = [g[metric] if math.isfinite(g[metric]) else -math.inf for g in grid]
    best = int(np.argmax(scores))  # ties: the first (smaller) configuration in grid order
    m = fitted[best]
    record = FitRecord(
        model=model,
        target=target,
        point=point,
        features=tuple(features),
        fit=row_range(tr, cfg.fit_split),
        tune=row_range(tu, cfg.tune_split),
        calibration=calibration,
        selected=grid[best],
        grid=grid_rows(grid),
        seed=cfg.seed,
        library={"lightgbm": lgb.__version__},
    )
    return Fitted(m, record, np.asarray(m.predict(x), dtype=float))


def save(fitted: Fitted, layout: Layout | None = None, *, prob_maps: dict[str, Any] | None = None) -> None:
    save_model(
        fitted.record, {"lightgbm": fitted.model.booster_.model_to_string()}, layout, prob_maps=prob_maps
    )
