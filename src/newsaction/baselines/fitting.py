"""Shared fitting helpers of the fitted baselines (PRD NA-09 S2–S5, AC1).

- ``fit_rows`` / ``tune_rows``: the rows a baseline may fit on (``fit_split``, train) and tune on
  (``tune_split``, val-A, outside the embargo), with a non-missing target. Every fitted baseline takes its
  rows from here and records their ranges (``schema.row_range``); ``schema.check_fit_record`` refuses a
  record whose ranges leave train or val-A before anything is written.
- ``ic`` (mean daily Spearman IC, Newey–West t; ``tournament.metrics``) and ``r2`` (1 − SSE / SSE of a
  reference forecast) are the selection metrics: the daily IC with the fitted target for N̂ and y2, the R²
  of |z_cc| against the train mean for mag_hat.
- ``prob_maps``: P_up = P(e5 ≥ +band) and P_down = P(e5 ≤ −band) as isotonic maps of a baseline's N̂,
  fit on val-A outside the embargo (PREREG §7: calibration maps are fit on val-A, the range stored); the
  two are scaled down together where they would sum above 1.
- ``save_model``: one JSON per fitted target under ``work/baselines/models/``: the fit record, the model
  (coefficients, isotonic thresholds or LightGBM's model text) and the probability maps; registered.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from newsaction import io
from newsaction.baselines import PRODUCER, BaselinesConfig
from newsaction.baselines.schema import FitRecord, Range, check_fit_record, row_range
from newsaction.paths import Layout, resolve_layout
from newsaction.tournament.metrics import daily_ic, ic_stats

MODELS_DIR: Final = "baselines/models"


def fit_rows(frame: pd.DataFrame, cfg: BaselinesConfig, target: str) -> pd.DataFrame:
    """Rows of the fit split (train) with a target."""
    return frame.loc[(frame["split"] == cfg.fit_split) & frame[target].notna()]


def tune_rows(frame: pd.DataFrame, cfg: BaselinesConfig, target: str) -> pd.DataFrame:
    """Rows of the tuning split (val-A) with a target, outside the embargo (PREREG §4.2)."""
    keep = (frame["split"] == cfg.tune_split) & frame[target].notna()
    if cfg.metric.exclude_embargo:
        keep &= ~frame["embargo"].astype(bool)
    return frame.loc[keep]


def ic(rows: pd.DataFrame, signal: npt.ArrayLike, target: str, cfg: BaselinesConfig) -> tuple[float, float]:
    """(mean daily Spearman IC of ``signal`` with ``target``, its Newey–West t) over ``rows``' sessions."""
    d = pd.DataFrame({"session": rows["session"].to_numpy(), "s": np.asarray(signal), "y": rows[target]})
    st = ic_stats(daily_ic(d, "s", "y", cfg.metric.min_names_per_day), cfg.metric.nw_lags)
    return st.mean, st.t


def r2(pred: npt.ArrayLike, y: npt.ArrayLike, reference: float) -> float:
    """1 − Σ(y − pred)² / Σ(y − reference)² (out of sample when ``pred`` was fit elsewhere)."""
    p, t = np.asarray(pred, dtype=float), np.asarray(y, dtype=float)
    keep = np.isfinite(p) & np.isfinite(t)
    den = float(np.sum((t[keep] - reference) ** 2))
    return math.nan if den == 0 else 1.0 - float(np.sum((t[keep] - p[keep]) ** 2)) / den


class ProbMaps:
    """Isotonic P_up / P_down maps of N̂ (module docstring)."""

    def __init__(self, n_hat: npt.ArrayLike, e5: npt.ArrayLike, band: float) -> None:
        x, y = np.asarray(n_hat, dtype=float), np.asarray(e5, dtype=float)
        keep = np.isfinite(x) & np.isfinite(y)
        x, y = x[keep], y[keep]
        self.band = band
        self.up = IsotonicRegression(increasing=True, out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.down = IsotonicRegression(increasing=False, out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.up.fit(x, (y >= band).astype(float))
        self.down.fit(x, (y <= -band).astype(float))

    def predict(self, n_hat: npt.ArrayLike) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        x = np.asarray(n_hat, dtype=float)
        ok = np.isfinite(x)
        up = np.full(len(x), np.nan)
        down = np.full(len(x), np.nan)
        up[ok] = self.up.predict(x[ok])
        down[ok] = self.down.predict(x[ok])
        total = up + down
        scale = np.where(total > 1.0, 1.0 / np.where(total > 0, total, 1.0), 1.0)
        return up * scale, down * scale

    def payload(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "up": {"x": self.up.X_thresholds_.tolist(), "y": self.up.y_thresholds_.tolist()},
            "down": {"x": self.down.X_thresholds_.tolist(), "y": self.down.y_thresholds_.tolist()},
        }


def prob_maps(
    frame: pd.DataFrame, n_hat: npt.ArrayLike, cfg: BaselinesConfig
) -> tuple[ProbMaps, Range, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Fit the maps on val-A (outside the embargo, e5 present) and apply them to every row of ``frame``."""
    n = np.asarray(n_hat, dtype=float)
    rows = tune_rows(frame, cfg, "e5")
    pos = frame.index.get_indexer(rows.index)
    maps = ProbMaps(n[pos], rows["e5"].to_numpy(), cfg.metric.class_band)
    up, down = maps.predict(n)
    return maps, row_range(rows, cfg.tune_split), up, down


def save_model(
    record: FitRecord, model: Any, layout: Layout | None = None, *, prob_maps: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Check ``record`` (AC1), then write ``work/baselines/models/<model>_<target>.json`` = {record, model,
    prob_maps} (the fit and tuning ranges, the fitted model, the val-A probability maps) and register it."""
    lay = resolve_layout(layout)
    check_fit_record(record, lay)
    rel = f"{MODELS_DIR}/{record.model}_{record.target}.json"
    doc = {"record": record.model_dump(mode="json"), "model": model, "prob_maps": prob_maps}
    io.atomic_write_bytes(lay.work / rel, (json.dumps(doc, indent=1) + "\n").encode("utf-8"))
    return io.register_file(
        rel,
        producer=PRODUCER,
        description=f"NA-09 {record.model} → {record.target}: fit record (ranges, grid) and model",
        inspect_parquet=False,
        layout=lay,
    )


def load_record(model: str, target: str, layout: Layout | None = None) -> FitRecord:
    path = resolve_layout(layout).work / f"{MODELS_DIR}/{model}_{target}.json"
    return FitRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))["record"])
