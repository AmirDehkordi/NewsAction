"""NA-07: the encoding ("numbers as words") and anchoring study (PREREG §8.4; PRD NA-07).

Modules:
- ``study``: the encoding search on val-A and its confirmation on val-B: per (model, encoding) daily ICs, the
  stationary block bootstrap, the PREREG §8.4 encoding rule (pooled by mean rank, ties to E3) and the val-B
  check (keep the best unless it is worse than E3 by more than 1 bootstrap SE);
- ``numeracy``: the outcome-free numeracy probe (synthetic Call B reaction blocks on real masked val-A news)
  and its monotonicity score;
- ``anchoring``: Call A (news only) vs Call B (news + reaction) on the same D2 news: the slope of N̂_B on G
  with N̂_A as control, corr(N̂_A, N̂_B), and the PREREG §8.4 anchoring rule;
- ``run``: the stages (``python -m newsaction.encoding.run --stage …``), the report and the hand-off.

Configuration: ``configs/encoding.yaml`` (``EncodingConfig``). Selections go to ``configs/frozen.yaml``
``encoding`` and ``anchoring``. The three models fail NA-06's screens (PREREG §15, the operator's decision
after NA-06): every NA-07 result is model-specific.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsaction.config import SplitName, load_yaml
from newsaction.paths import CONFIGS, Layout, resolve_layout
from newsaction.tournament import log_trial as _log_trial

CHUNK: Final = "NA-07"
PRODUCER: Final = "newsaction.encoding (NA-07)"
CONFIG_PATH: Final = CONFIGS / "encoding.yaml"
ARTIFACTS: Final = "artifacts/NA-07"
WORK_DIR: Final = "dm/encoding"  # under work/
SAMPLES: Final = f"{WORK_DIR}/samples.parquet"
SEARCH: Final = f"{WORK_DIR}/search.parquet"
CONFIRM: Final = f"{WORK_DIR}/confirm.parquet"
NUMERACY: Final = f"{WORK_DIR}/numeracy.parquet"
ANCHORING: Final = f"{WORK_DIR}/anchoring.parquet"


class EncodingError(Exception):
    """The study cannot proceed (missing input, broken invariant, STOP condition)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelsConfig(_Strict):
    n: int = Field(ge=1)
    expected: tuple[str, ...]

    @model_validator(mode="after")
    def _size(self) -> ModelsConfig:
        if len(self.expected) != self.n:
            raise ValueError("models.expected must list models.n models")
        return self


class StateFiles(_Strict):
    sample: str  # "{encoding}" placeholder
    call_a_d2: str
    call_b_d2: str

    def sample_file(self, encoding: str) -> str:
        return self.sample.format(encoding=encoding)


class SampleConfig(_Strict):
    val_a: int = Field(gt=0)
    val_b: int = Field(gt=0)
    strata: tuple[str, ...]


class MetricConfig(_Strict):
    target: str
    min_names_per_day: int = Field(ge=3)
    nw_lags: int = Field(ge=0)


class BootstrapConfig(_Strict):
    block: float = Field(ge=1)
    reps: int = Field(ge=100)
    ci: float = Field(gt=0, lt=1)


class RuleConfig(_Strict):
    confirm_se: float = Field(gt=0)
    tie_decimals: int = Field(ge=1)


class NumeracyConfig(_Strict):
    n_news: int = Field(gt=0)
    magnitudes: tuple[float, ...] = Field(min_length=2)
    market_z: float
    volume_multiple: float = Field(gt=0)
    e0_stock_sigma: float = Field(gt=0)
    e0_market_sigma: float = Field(gt=0)
    target_share: float = Field(gt=0, le=1)
    tol: float = Field(ge=0)

    @model_validator(mode="after")
    def _increasing(self) -> NumeracyConfig:
        m = list(self.magnitudes)
        if m != sorted(set(m)) or m[0] <= 0:
            raise ValueError("numeracy.magnitudes must be positive and strictly increasing")
        return self


class AnchoringConfig(_Strict):
    slope_min: float
    corr_max: float
    combine: Literal["any"]


class EncodingConfig(_Strict):
    version: int
    seed: int
    groups: tuple[str, ...]
    encodings: tuple[str, ...]
    default_encoding: str
    models: ModelsConfig
    state_files: StateFiles
    samples: SampleConfig
    metric: MetricConfig
    bootstrap: BootstrapConfig
    rule: RuleConfig
    numeracy: NumeracyConfig
    anchoring: AnchoringConfig
    concurrency: int = Field(ge=1)

    @model_validator(mode="after")
    def _default_listed(self) -> EncodingConfig:
        if self.default_encoding not in self.encodings:
            raise ValueError("default_encoding must be one of encodings")
        return self


def load_encoding_config(path: Path = CONFIG_PATH) -> EncodingConfig:
    return EncodingConfig.model_validate(load_yaml(path))


def encoding_config(layout: Layout | None = None) -> EncodingConfig:
    return load_encoding_config(resolve_layout(layout).configs / "encoding.yaml")


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
    """An NA-07 ``ledgers/trials.jsonl`` record, never twice (``tournament.log_trial``)."""
    return _log_trial(kind, name, params, split, metric, value, chunk=CHUNK, layout=layout)
