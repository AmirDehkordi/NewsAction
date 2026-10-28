"""The common prediction schema and fit records (PRD NA-09 S1, AC1–AC3).

**Predictions** (``work/baselines/<model>.parquet``), one row per (event_id, model, call):

| column | meaning |
|---|---|
| ``event_id`` | the state's event (W0:… for call A, W2:… for call B) |
| ``model`` | the baseline (``MODELS``) |
| ``call`` | "A": a D0 event with a Call A state; "B": a D2 event with a Call B state |
| ``split`` | the event's split |
| ``session``, ``company_id`` | the event's keys (as in the state file) |
| ``N_hat`` | the news-implied eventual move in σ units (e5 scale, PREREG §5.6) |
| ``P_up``, ``P_down`` | P(e5 ≥ +0.5), P(e5 ≤ −0.5) (PREREG §11.2 classes); null for a model without them |
| ``mag_hat`` | expected \\|move\\| (\\|z_cc\\| scale for fitted models, E\\|N̂\\| for Laya and the LLM) |
| ``y_hat`` | price-only D2 only: the predicted subsequent drift y2 (PREREG §5.6) |
| ``extra`` | JSON object: model-specific fields (raw scores, Q1 probabilities, flags) |

Validators (``validate``): exact columns and types; finite numbers where present; P in [0, 1] with
P_up + P_down ≤ 1; mag_hat ≥ 0; ``extra`` a JSON object; no duplicate (event_id, model, call); every row's
event, split, session and company equal a state row of its call; **no call B row in the test period** and
test rows only for ``TEST_MODELS`` (AC3).

**Fit records** (``work/baselines/models/<model>_<target>.json``): the fit range (train only) and the tuning
range (val-A only), computed from the rows actually used and checked by ``check_fit_record`` before any
model or prediction is written (AC1).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from newsaction.baselines import BaselineError
from newsaction.config import SplitName, load_splits
from newsaction.paths import Layout, resolve_layout

PREDICTION_COLUMNS: Final = (
    "event_id",
    "model",
    "call",
    "split",
    "session",
    "company_id",
    "N_hat",
    "P_up",
    "P_down",
    "mag_hat",
    "y_hat",
    "extra",
)
FLOAT_COLUMNS: Final = ("N_hat", "P_up", "P_down", "mag_hat", "y_hat")
MODELS: Final = ("sentiment", "embed_ridge", "tags_gbm", "price_only", "laya_zeroshot", "llm")
TEST_MODELS: Final = frozenset({"sentiment", "embed_ridge", "tags_gbm"})  # inputs known before the open only
SPLITS: Final = ("robustness", "train", "val_a", "val_b", "test")
P_TOL: Final = 1e-9


class SchemaError(BaselineError):
    """Predictions that break the common schema."""


def frame(rows: pd.DataFrame) -> pd.DataFrame:
    """``rows`` in schema order and dtypes (missing optional columns are null)."""
    out = rows.copy()
    for c in FLOAT_COLUMNS:
        if c not in out.columns:
            out[c] = np.nan
    if "extra" not in out.columns:
        out["extra"] = "{}"
    out = out[list(PREDICTION_COLUMNS)].copy()
    out = out.astype(
        {"event_id": "str", "model": "str", "call": "str", "split": "str", "company_id": "int64"}
    )
    for c in FLOAT_COLUMNS:
        out[c] = pd.to_numeric(out[c], errors="raise").astype("float64")
    out["session"] = pd.to_datetime(out["session"]).dt.date
    return out.sort_values(["call", "session", "company_id", "event_id"], kind="mergesort").reset_index(
        drop=True
    )


def validate(pred: pd.DataFrame, states: Mapping[str, pd.DataFrame]) -> None:
    """Raise ``SchemaError`` unless ``pred`` satisfies the schema (module docstring). ``states`` maps a call
    ("A", "B") to its state rows (event_id, split, session, company_id)."""
    if tuple(pred.columns) != PREDICTION_COLUMNS:
        raise SchemaError(f"columns {list(pred.columns)} != {list(PREDICTION_COLUMNS)}")
    if len(pred) == 0:
        raise SchemaError("no predictions")
    if bool(pred[["event_id", "model", "call", "split", "session", "company_id"]].isna().any().any()):
        raise SchemaError("a key column is null")
    bad_model = set(pred["model"]) - set(MODELS)
    if bad_model:
        raise SchemaError(f"unknown models {sorted(bad_model)}")
    if not set(pred["call"]) <= {"A", "B"} or not set(pred["split"]) <= set(SPLITS):
        raise SchemaError("call must be A or B and split a split name")
    dup = pred.duplicated(["event_id", "model", "call"])
    if bool(dup.any()):
        raise SchemaError(f"{int(dup.sum())} duplicate (event_id, model, call) rows")
    test = pred["split"] == "test"
    if bool((test & (pred["call"] == "B")).any()):
        raise SchemaError("a D2 (call B) prediction in the test period (AC3)")
    if bool((test & ~pred["model"].isin(TEST_MODELS)).any()):
        raise SchemaError(f"test predictions are allowed only for {sorted(TEST_MODELS)} (AC3)")
    for c in FLOAT_COLUMNS:
        v = pred[c].to_numpy(dtype=float)
        if not np.isfinite(v[~np.isnan(v)]).all():
            raise SchemaError(f"{c} has an infinite value")
    if bool((pred["N_hat"].isna() & pred["y_hat"].isna()).any()):
        raise SchemaError("a row has neither N_hat nor y_hat")
    for c in ("P_up", "P_down"):
        p = pred[c].dropna()
        if bool(((p < -P_TOL) | (p > 1 + P_TOL)).any()):
            raise SchemaError(f"{c} outside [0, 1]")
    if bool((pred["P_up"].fillna(0) + pred["P_down"].fillna(0) > 1 + P_TOL).any()):
        raise SchemaError("P_up + P_down > 1")
    if bool((pred["mag_hat"].dropna() < 0).any()):
        raise SchemaError("mag_hat < 0")
    for x in pred["extra"]:
        if not isinstance(json.loads(x), dict):
            raise SchemaError("extra must be a JSON object")
    keys = ["event_id", "split", "session", "company_id"]
    for call, g in pred.groupby("call"):
        st = states[str(call)][keys].copy()
        st["session"] = pd.to_datetime(st["session"]).dt.date
        m = g[keys].merge(st, on=keys, how="left", indicator=True)
        missing = int((m["_merge"] != "both").sum())
        if missing:
            raise SchemaError(
                f"{missing} call {call} rows do not match a state (event, split, session, company)"
            )


# --- fit records ----------------------------------------------------------------------------------------


class Range(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    split: SplitName
    start: date
    end: date
    n_rows: int = Field(ge=1)
    n_sessions: int = Field(ge=1)


class FitRecord(BaseModel):
    """What a fitted baseline was fit and tuned on (AC1). ``fit`` and ``tune`` are computed from the rows
    used (``row_range``); ``calibration`` is the val-A range of the P_up / P_down maps, if any."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    target: str
    point: str
    features: tuple[str, ...]
    fit: Range
    tune: Range | None
    calibration: Range | None = None
    selected: dict[str, Any]
    grid: tuple[dict[str, Any], ...] = ()
    seed: int
    library: dict[str, str] = Field(default_factory=dict)


def row_range(rows: pd.DataFrame, split: SplitName) -> Range:
    """The range of the ``session`` column of ``rows``, labelled with the split it must lie in."""
    if len(rows) == 0:
        raise BaselineError(f"no {split} rows")
    s = pd.to_datetime(rows["session"]).dt.date
    return Range(split=split, start=s.min(), end=s.max(), n_rows=len(rows), n_sessions=int(s.nunique()))


def check_fit_record(rec: FitRecord, layout: Layout | None = None) -> None:
    """Raise unless the fit range lies in train and the tuning and calibration ranges in val-A (PREREG §4,
    CLAUDE.md B9; ``configs/splits.yaml``)."""
    splits = load_splits(resolve_layout(layout).configs / "splits.yaml").splits

    def inside(r: Range, name: SplitName, what: str) -> None:
        rng = splits[name]
        if r.split != name or not (rng.start <= r.start <= r.end <= rng.end):
            raise BaselineError(
                f"{rec.model} {rec.target}: {what} range {r.start}..{r.end} ({r.split}) is not inside "
                f"{name} {rng.start}..{rng.end}"
            )

    inside(rec.fit, "train", "fit")
    if rec.tune is not None:
        inside(rec.tune, "val_a", "tuning")
    if rec.calibration is not None:
        inside(rec.calibration, "val_a", "calibration")


def finite(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else float(x)


def grid_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple({k: (finite(v) if isinstance(v, float) else v) for k, v in r.items()} for r in rows)
