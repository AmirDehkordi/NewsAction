"""NA-02: cleaned, correctly-timed, member-mapped news (PRD NA-02; PREREG §2, §3.4, §6.1–6.5).

Modules, in pipeline order:
- ``load``: read ``Data/news_YYYY.parquet`` (never ``body``), precision class, t_avail, W0/W2 sessions;
- ``mapping``: EXCH:SYM -> ATOM symbol (validity ranges at t_avail) -> company -> member at session_w2;
- ``detect``: after-the-fact / price-path and pre-market price-talk detectors, ``scrub``;
- ``clean``: non-news, junk tags, 13F and Form-4 auto-articles, third-party flag;
- ``sources``: domain -> source class;
- ``embed``: bge-small on title_clean + ". " + snippet_clean (MPS);
- ``dedupe`` and ``novelty``: per-company time-ordered scans that look only backwards;
- ``coverage``: member-month coverage (§3.4) and the leaver check;
- ``audit``: timing audit, leakage audit (§6.4), re-derived §14 diagnostics; sessions <= end of val-B;
- ``build``: the CLI that runs them and writes ``work/news/*.parquet``.

Configuration: ``configs/news.yaml`` (constants), ``configs/patterns.yaml`` (regexes),
``configs/sources.yaml`` (domain classes).
"""

from __future__ import annotations

import functools
from datetime import date
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS

NEWS_DIR: Final = "news"
STAGE1: Final = f"{NEWS_DIR}/articles_stage1.parquet"
ARTICLES: Final = f"{NEWS_DIR}/articles_clean.parquet"
EMBEDDINGS: Final = f"{NEWS_DIR}/embeddings_ts.parquet"
COVERAGE: Final = f"{NEWS_DIR}/coverage_member_month.parquet"
MARKET_ARTICLES: Final = f"{NEWS_DIR}/market_articles.parquet"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LoadConfig(_Strict):
    years: tuple[int, ...]
    t_avail_start: date
    t_avail_end: date


class Alias(_Strict):
    ticker: str
    symbol_id: int
    valid_from: date | None
    valid_to: date | None
    kind: Literal["rename", "class", "restrict"]
    note: str


class MappingConfig(_Strict):
    us_exchanges: tuple[str, ...]
    non_equity_prefixes: tuple[str, ...]
    aliases: tuple[Alias, ...]


class DedupeConfig(_Strict):
    cosine: float = Field(gt=0, le=1)
    window_hours: int = Field(gt=0)


class NoveltyConfig(_Strict):
    window_days: int = Field(gt=0)


class EmbedConfig(_Strict):
    model: str
    revision: str
    device: str
    compute_dtype: Literal["float16", "float32"]
    batch_size: int = Field(gt=0)
    dim: int = Field(gt=0)


class AuditConfig(_Strict):
    min_names_per_day: int = Field(gt=1)
    nw_lags: int = Field(ge=0)
    leak_t: float = Field(gt=0)


class NewsConfig(_Strict):
    load: LoadConfig
    mapping: MappingConfig
    sentiment_scale: dict[str, int]
    junk_tags: tuple[str, ...]
    dedupe: DedupeConfig
    novelty: NoveltyConfig
    embed: EmbedConfig
    market_tickers: tuple[str, ...]
    audit: AuditConfig


@functools.cache
def load_news_config(path: Path = CONFIGS / "news.yaml") -> NewsConfig:
    return NewsConfig.model_validate(load_yaml(path))
