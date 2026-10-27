"""NA-06: the zero-shot decision-model tournament on val-A and its contamination probes (PREREG §8.2–8.3; PRD
NA-06).

Modules:
- ``sample``: the stage-1 / stage-2 / probe samples of val-A D0 events (seed 2026, tier × month);
- ``metrics``: daily Spearman IC, Newey–West t, the 3-class calibration (ECE), cost and latency summaries;
- ``mcs``: the Model Confidence Set (Hansen, Lunde and Nason 2011) with a stationary bootstrap over days;
- ``edits``: the counterfactual edit rules of probe c;
- ``probes``: probe requests (company and month identification, edits, unmasked twins, shuffled news, reading
  validity), their scores and the PREREG §8.3 screens;
- ``run``: the stages (``python -m newsaction.tournament.run --stage …``), the leaderboard and the hand-off.

Configuration: ``configs/tournament.yaml`` (``TournamentConfig``). Selections go to ``configs/frozen.yaml``
``tournament`` and ``allow_val_b``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsaction.config import SplitName, load_yaml
from newsaction.ledger import TRIALS, TrialLedger, TrialRecord, params_hash
from newsaction.paths import CONFIGS, Layout, resolve_layout

CHUNK: Final = "NA-06"
PRODUCER: Final = "newsaction.tournament (NA-06)"
CONFIG_PATH: Final = CONFIGS / "tournament.yaml"
ARTIFACTS: Final = "artifacts/NA-06"
WORK_DIR: Final = "dm/tournament"  # under work/
SAMPLES: Final = f"{WORK_DIR}/samples.parquet"
STAGE1: Final = f"{WORK_DIR}/stage1.parquet"
STAGE2: Final = f"{WORK_DIR}/stage2.parquet"
PROBES: Final = f"{WORK_DIR}/probes.parquet"


class TournamentError(Exception):
    """The tournament cannot proceed (missing input, broken invariant, STOP condition)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StateFiles(_Strict):
    call_a: str
    call_b: str
    unmasked: str


class SampleConfig(_Strict):
    split: SplitName
    strata: tuple[str, ...]
    exclude_embargo: bool
    stage1: int = Field(gt=0)
    stage2: int = Field(gt=0)
    identification: int = Field(gt=0)
    counterfactual: int = Field(gt=0)
    shuffled: int = Field(gt=0)
    reading_validity: int = Field(gt=0)

    @model_validator(mode="after")
    def _nested(self) -> SampleConfig:
        subs = (self.stage1, self.identification, self.shuffled, self.reading_validity)
        if any(n > self.stage2 for n in subs):
            raise ValueError("every probe sample must fit inside the stage-2 sample")
        return self


class MetricConfig(_Strict):
    primary_target: str
    secondary_target: str
    min_names_per_day: int = Field(ge=3)
    nw_lags: int = Field(ge=0)
    ece_bins: int = Field(ge=2)
    class_band: float = Field(gt=0)


class McsConfig(_Strict):
    alpha: float = Field(gt=0, lt=1)
    block: float = Field(ge=1)
    reps: int = Field(ge=100)
    statistic: Literal["R", "max"]
    loss: Literal["neg_daily_ic"]


class Stage1Config(_Strict):
    max_projected_usd: float = Field(gt=0)


class Stage2Config(_Strict):
    max_models: int = Field(ge=1)


class ScreenConfig(_Strict):
    """PREREG §8.3. Pass conditions: company-ID accuracy <= ``company_id_max``; flip rate >=
    ``flip_rate_min`` (pairs with |N̂_orig| >= ``flip_min_abs_n_hat``); unmasked − masked IC <=
    ``unmasked_minus_masked_max`` or paired |t| < ``unmasked_paired_t``; shuffled-news |t| <
    ``shuffled_t``."""

    company_id_max: float
    flip_rate_min: float
    flip_min_abs_n_hat: float
    unmasked_minus_masked_max: float
    unmasked_paired_t: float
    shuffled_t: float


class CompanyProbe(_Strict):
    qid: str
    instructions: str


class MonthProbe(_Strict):
    qid: str
    instructions: str
    first: str = Field(pattern=r"^\d{4}-\d{2}$")
    last: str = Field(pattern=r"^\d{4}-\d{2}$")


class ProbeTags(_Strict):
    company: str
    month: str
    counterfactual: str
    unmasked: str
    shuffled: str
    reading_validity: str


class ProbeConfig(_Strict):
    option_keys: tuple[str, ...] = Field(min_length=2)
    company: CompanyProbe
    month: MonthProbe
    tags: ProbeTags


class ReadingValidityConfig(_Strict):
    groups: tuple[str, ...]
    event_type_map: dict[str, str]


class TournamentConfig(_Strict):
    version: int
    seed: int
    encoding: str
    groups: tuple[str, ...]
    state_files: StateFiles
    samples: SampleConfig
    metric: MetricConfig
    mcs: McsConfig
    stage1: Stage1Config
    stage2: Stage2Config
    concurrency: int = Field(ge=1)
    screens: ScreenConfig
    probes: ProbeConfig
    reading_validity: ReadingValidityConfig


def load_tournament_config(path: Path = CONFIG_PATH) -> TournamentConfig:
    return TournamentConfig.model_validate(load_yaml(path))


def tournament_config(layout: Layout | None = None) -> TournamentConfig:
    return load_tournament_config(resolve_layout(layout).configs / "tournament.yaml")


def log_trial(
    kind: str,
    name: str,
    params: Mapping[str, Any],
    split: SplitName,
    metric: str,
    value: float | None,
    *,
    chunk: str = CHUNK,
    layout: Layout | None = None,
) -> bool:
    """Append one ``ledgers/trials.jsonl`` record (CLAUDE.md B10) unless an identical one exists; True when
    appended. A deterministic rerun of the report therefore does not inflate the trial count. A value that is
    not finite (no valid answer) is logged as null. NA-07 logs through here with its own ``chunk``."""
    v = None if value is None or not math.isfinite(float(value)) else float(value)
    rec = TrialRecord(
        chunk=chunk,
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
