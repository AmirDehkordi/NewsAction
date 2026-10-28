"""NA-09: the pre-registered baselines (PREREG §10; PRD NA-09) in one prediction schema.

Modules:
- ``schema``: the common prediction columns and their validators; fit records (fit and tuning ranges);
- ``data``: event frames shared by the fitted baselines (state events, their articles, targets, features);
- ``sentiment``: vendor sentiment → N̂ by an isotonic map fit on train (PREREG §10.1);
- ``embed_ridge``: mean-pooled bge-small embeddings + attention → ridge, λ on val-A (§10.2);
- ``tags_gbm``: vendor tags, flags, sentiment, sources, novelty, attention, tier, sector → LightGBM (§10.3);
- ``price_only``: momentum, volume, σ regime, tier, sector (+ G, z_on at D2) → LightGBM (§10.4);
- ``laya_zeroshot``: local Laya typed-decisions on the Call A and Call B states (§10.5);
- ``llm_baseline``: a generative LLM through ``DecisionClient.chat_json`` on a val-B subsample (§10.7);
- ``metrics``: the val-A metrics table (PRD S8); no val-B or test metric is computed in NA-09;
- ``run``: the stages (``python -m newsaction.baselines.run --stage …``).

Configuration: ``configs/baselines.yaml`` (``BaselinesConfig``). Outputs: ``work/baselines/*.parquet``
(registered), ``artifacts/NA-09/``. Test-period predictions exist only for baselines whose inputs are all
known before the decision and need no 2026 price (the news baselines at D0); price-only test predictions and
Laya's and the LLM's test predictions are made in NA-11 after the freeze.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from newsaction.config import SplitName, load_yaml
from newsaction.ledger import TRIALS, TrialLedger, TrialRecord, params_hash
from newsaction.paths import CONFIGS, Layout, resolve_layout

CHUNK: Final = "NA-09"
PRODUCER: Final = "newsaction.baselines (NA-09)"
CONFIG_PATH: Final = CONFIGS / "baselines.yaml"
ARTIFACTS: Final = "artifacts/NA-09"
WORK_DIR: Final = "baselines"  # under work/


class BaselineError(Exception):
    """A baseline cannot be fit or predicted (missing input, broken invariant, STOP condition)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StateFiles(_Strict):
    call_a: str
    call_b: str


class MetricConfig(_Strict):
    min_names_per_day: int = Field(ge=2)
    nw_lags: int = Field(ge=0)
    exclude_embargo: bool
    class_band: float = Field(gt=0)
    tiers: tuple[str, ...]


class SentimentConfig(_Strict):
    scale: dict[str, int]
    timely: tuple[str, ...]


class RidgeConfig(_Strict):
    lambdas: tuple[float, ...] = Field(min_length=1)
    standardize: bool


class GbmGrid(_Strict):
    num_leaves: tuple[int, ...] = Field(min_length=1)
    min_child_samples: tuple[int, ...] = Field(min_length=1)
    n_estimators: tuple[int, ...] = Field(min_length=1)


class GbmConfig(_Strict):
    learning_rate: float = Field(gt=0)
    subsample: float = Field(gt=0, le=1)
    subsample_freq: int = Field(ge=0)
    colsample_bytree: float = Field(gt=0, le=1)
    grid: GbmGrid


class LayaZeroShotConfig(_Strict):
    model: str
    groups: tuple[str, ...]
    chunk_size: int = Field(gt=0)
    order: tuple[tuple[SplitName, str], ...]


class LlmSelection(_Strict):
    max_prompt_usd_per_m: float = Field(gt=0)
    developers: tuple[str, ...]
    exclude_id_words: tuple[str, ...]
    required_parameters: tuple[str, ...]
    reasoning: bool
    cutoff_before: date
    reference: str
    bytes_per_token: float = Field(gt=0)
    output_tokens: int = Field(gt=0)


class LlmConfig(_Strict):
    sample: int = Field(gt=0)
    strata: tuple[str, ...]
    temperature: float = Field(ge=0)
    seed: int
    max_tokens: int = Field(gt=0)
    sum_tol: float = Field(gt=0, lt=0.5)
    concurrency: int = Field(ge=1)
    selection: LlmSelection


class BaselinesConfig(_Strict):
    version: int
    seed: int
    state_files: StateFiles
    fit_split: SplitName
    tune_split: SplitName
    metric: MetricConfig
    sentiment: SentimentConfig
    embed_ridge: RidgeConfig
    tags_gbm: GbmConfig
    price_only: GbmConfig
    laya_zeroshot: LayaZeroShotConfig
    llm: LlmConfig


def load_baselines_config(path: Path = CONFIG_PATH) -> BaselinesConfig:
    return BaselinesConfig.model_validate(load_yaml(path))


def baselines_config(layout: Layout | None = None) -> BaselinesConfig:
    return load_baselines_config(resolve_layout(layout).configs / "baselines.yaml")


def log_trial(
    kind: str,
    name: str,
    params: Mapping[str, Any],
    split: SplitName,
    metric: str,
    value: float | None,
    *,
    layout: Layout | None = None,
) -> bool:
    """Append one ``ledgers/trials.jsonl`` record (CLAUDE.md B10) unless an identical one exists; True when
    appended, so a deterministic rerun does not inflate the trial count. A value that is not finite is
    logged as null."""
    v = None if value is None or not math.isfinite(float(value)) else float(value)
    rec = TrialRecord(
        chunk=CHUNK,
        kind=kind,
        name=name,
        params_hash=params_hash(dict(params)),
        split=split,
        metric=metric,
        value=v,
    )
    ledger = TrialLedger(resolve_layout(layout).ledgers / TRIALS)
    fields = rec.model_dump()
    for r in ledger.records():
        if all(r.get(k) == v for k, v in fields.items()):
            return False
    ledger.log(rec)
    return True
