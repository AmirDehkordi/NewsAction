"""NA-03: material label, importance filters, the val-A comparison and events (PREREG §6.6–6.9, A1.2).

Modules, in pipeline order:
- ``labels``: material / delayed-reaction ticker-day labels from the public panel (train, val-A, val-B);
- ``attention``: per company-session article counts in W0 and W2 and the 60-session attention ratio;
- ``filters``: article-level scores of F0–F6 and their ticker-day aggregation (max, counts);
- ``learned``: F5 (logistic regression on embeddings) and F6 (LightGBM), fit, tuned, frozen and stored;
- ``select``: the val-A comparison at the 30% budget, the frontier and the mechanical PREREG §6.8 rule;
- ``tokens``: the ModernBERT-large tokenizer, the news block and the 600-token cap;
- ``clean_window``: A1.2 clean-window flags from D2 events only;
- ``aggregate``: D0 / D2 events for every period with the frozen filter (no outcome is read);
- ``projection``: call and cost projection for NA-11;
- ``build``: the CLI that runs them one stage per process.

Only ``labels`` and ``select`` read returns, and only for public sessions. No module here imports
``newsaction.panel.targets`` or ``newsaction.lock`` (tests/test_events_no_test_outcomes.py).
Configuration: ``configs/events.yaml``.
"""

from __future__ import annotations

import functools
from datetime import date
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS

PRODUCER: Final = "newsaction.events.build (NA-03)"
CHUNK: Final = "NA-03"
EVENTS_DIR: Final = "events"
LABELS: Final = f"{EVENTS_DIR}/labels_public.parquet"
COUNTS: Final = f"{EVENTS_DIR}/window_counts.parquet"
ARTICLE_SCORES: Final = f"{EVENTS_DIR}/article_scores.parquet"
TICKER_DAYS: Final = f"{EVENTS_DIR}/ticker_days.parquet"
EVENTS_D0: Final = f"{EVENTS_DIR}/events_d0.parquet"
EVENTS_D2: Final = f"{EVENTS_DIR}/events_d2.parquet"
MODELS_DIR: Final = f"{EVENTS_DIR}/models"

FilterId = Literal["F0", "F1", "F2", "F3", "F4", "F5", "F6"]
FILTER_IDS: Final[tuple[FilterId, ...]] = ("F0", "F1", "F2", "F3", "F4", "F5", "F6")
RULE_FILTERS: Final[frozenset[str]] = frozenset({"F0", "F1", "F2", "F3"})  # 0/1 article scores
Window = Literal["W0", "W2"]
WINDOWS: Final[tuple[Window, ...]] = ("W0", "W2")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DateWindow(_Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateWindow:
        if self.start > self.end:
            raise ValueError(f"window start {self.start} after end {self.end}")
        return self


class LabelConfig(_Strict):
    material_on_z: float = Field(gt=0)
    material_car_days: int = Field(gt=0)
    material_car_z: float = Field(gt=0)
    material_vol_z: float = Field(gt=0)
    delayed_on_max: float = Field(gt=0)
    delayed_car_days: int = Field(gt=0)
    delayed_car_z: float = Field(gt=0)


class FilterConfig(_Strict):
    material_tags: tuple[str, ...]
    hard_tags: tuple[str, ...]
    neutral_sentiment: str
    timely_intensity: tuple[str, ...]
    quality_sources: tuple[str, ...]
    pca_components: int = Field(gt=0)
    attention_lookback: int = Field(gt=0)
    attention_min_member_sessions: int = Field(gt=0)

    @model_validator(mode="after")
    def _hard_in_material(self) -> FilterConfig:
        if not set(self.hard_tags) <= set(self.material_tags):
            raise ValueError("HARD tags must be a subset of MATERIAL tags (PREREG §6.6)")
        return self


class F5Config(_Strict):
    max_iter: int = Field(gt=0)
    grid: dict[str, tuple[float, ...]]


class F6Config(_Strict):
    fixed: dict[str, float | int]
    grid: dict[str, tuple[int, ...]]


class LearnedConfig(_Strict):
    fit: DateWindow
    tune: DateWindow
    label_horizon: int = Field(gt=0)
    seed: int
    f5: F5Config
    f6: F6Config

    @model_validator(mode="after")
    def _fit_before_tune(self) -> LearnedConfig:
        if self.fit.end >= self.tune.start:
            raise ValueError("the fit window must end before the tune window starts")
        return self


class CompareConfig(_Strict):
    budget_share: float = Field(gt=0, lt=1)
    tie_pp: float = Field(ge=0)
    tie_order: tuple[str, ...]
    frontier_shares: tuple[float, ...]
    rule_version: str


class EventsConfig(_Strict):
    max_articles: int = Field(gt=0)
    max_news_tokens: int = Field(gt=0)
    tokenizer: str
    tokenizer_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    clean_horizons: tuple[int, ...]


class ProjectionConfig(_Strict):
    context_tokens: int = Field(ge=0)
    core_question_tokens: int = Field(ge=0)
    extended_question_tokens: int = Field(ge=0)
    usd_per_m: tuple[float, ...]
    flag_usd_per_m: float = Field(gt=0)
    chunk: str
    final_selection_models: int = Field(ge=0)
    ablation_events: int = Field(ge=0)
    ablation_calls_per_event: int = Field(ge=0)
    llm_baseline_usd: float = Field(ge=0)
    market_calls: int = Field(ge=0)


class NA03Config(_Strict):
    label: LabelConfig
    filters: FilterConfig
    learned: LearnedConfig
    compare: CompareConfig
    events: EventsConfig
    projection: ProjectionConfig


@functools.cache
def load_events_config(path: Path = CONFIGS / "events.yaml") -> NA03Config:
    return NA03Config.model_validate(load_yaml(path))
