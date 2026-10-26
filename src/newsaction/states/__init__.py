"""NA-04: model inputs: codebook, context, masking, questions, states (PREREG §6.3, §6.9–§7, A2, A3.1, A3.5).

Modules, in pipeline order:
- ``codebook``: numbers as words (``configs/codebook_v1.yaml``); pure functions, one per scale;
- ``macro``: scheduled CPI releases and FOMC statements (``configs/macro_calendar.yaml``);
- ``context``: the numeric company / market context through t−1 and the D2 reaction, and their rendering
  into state blocks in an encoding;
- ``mask``: company names and tickers, person names, dates and price talk out of the news text;
- ``scan``: the residual-leak scanner;
- ``questions``: the frozen battery (``configs/questions_v1.yaml``) in the decision-model request shape;
- ``build``: canonical JSON states, availability checks, token counts, samples, and the CLI.

Every input column a state consumes is registered in ``configs/availability.yaml``; ``build`` calls
``pit.check_inputs`` for every block before rendering. Constants: ``configs/states.yaml``.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from newsaction.config import SplitName, load_yaml
from newsaction.paths import CONFIGS

PRODUCER: Final = "newsaction.states.build (NA-04)"
CHUNK: Final = "NA-04"
STATES_DIR: Final = "states"
CONTEXT_COMPANY: Final = f"{STATES_DIR}/context_company.parquet"
CONTEXT_MARKET: Final = f"{STATES_DIR}/context_market.parquet"
ARTICLES_MASKED: Final = f"{STATES_DIR}/articles_masked.parquet"
SAMPLES_DIR: Final = f"{STATES_DIR}/samples"

Encoding = Literal["E0", "E1", "E2", "E3", "E4"]
ENCODINGS: Final[tuple[Encoding, ...]] = ("E0", "E1", "E2", "E3", "E4")
Call = Literal["A", "B", "M"]  # M: the optional A3.5 market state
StateWindow = Literal["W0", "W2"]

CODEBOOK_PATH: Final = CONFIGS / "codebook_v1.yaml"
QUESTIONS_PATH: Final = CONFIGS / "questions_v1.yaml"
ALIASES_PATH: Final = CONFIGS / "aliases.yaml"
MACRO_PATH: Final = CONFIGS / "macro_calendar.yaml"
STATES_CONFIG_PATH: Final = CONFIGS / "states.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextConfig(_Strict):
    history_sessions: int = Field(gt=0)
    history_min: int = Field(gt=0)
    perf_windows: dict[str, int]
    revision_days: int = Field(gt=0)


class SeriesConfig(_Strict):
    source: Literal["market_prices", "fred"]
    symbol: str
    change: Literal["return", "diff"]
    value_scale: float = Field(gt=0)
    e0_unit: Literal["pct", "bp", "points"]
    extra_lag: int = Field(ge=0)


class MarketConfig(_Strict):
    series: dict[str, SeriesConfig]
    level_percentile: tuple[str, ...]


class TokensConfig(_Strict):
    state_p95_max: int = Field(gt=0)
    total_max: int = Field(gt=0)
    laya_state_budget: int = Field(gt=0)
    special_tokens: int = Field(ge=0)


class SamplesConfig(_Strict):
    seed: int
    encodings_val_a: int = Field(gt=0)
    encodings_val_b: int = Field(gt=0)
    unmasked_val_a: int = Field(gt=0)
    strata: tuple[str, ...]
    exclude_embargo: bool


class MarketStatesConfig(_Strict):
    window: StateWindow
    max_articles: int = Field(gt=0)
    max_news_tokens: int = Field(gt=0)
    splits: tuple[SplitName, ...]


class NewsExclusionConfig(_Strict):
    """Articles left out of every state: regexes searched in NA-02's raw title / snippet and in the domain."""

    title: str = Field(min_length=1)
    snippet: str = Field(min_length=1)
    domain: str = Field(min_length=1)

    @field_validator("title", "snippet", "domain")
    @classmethod
    def _compiles(cls, v: str) -> str:
        re.compile(v)
        return v


class StatesConfig(_Strict):
    context: ContextConfig
    market: MarketConfig
    tokens: TokensConfig
    samples: SamplesConfig
    market_states: MarketStatesConfig
    news_exclusion: NewsExclusionConfig


@functools.cache
def _load(path: Path, mtime_ns: int) -> StatesConfig:
    return StatesConfig.model_validate(load_yaml(path))


def load_states_config(path: Path = STATES_CONFIG_PATH) -> StatesConfig:
    return _load(path, path.stat().st_mtime_ns)
