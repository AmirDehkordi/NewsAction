"""PRD NA-02 S4: cleaning flags (PREREG §6.1–6.2).

Per article:
- ``non_news``: the vendor flag (missing counts as False);
- ``junk_tag``: vendor ``tag_type`` in ``junk_tags`` (price_commentary, promotional_content);
- ``is_13f``: institutional-holdings (13F) auto-article, by title regex (``configs/patterns.yaml``
  ``holdings_13f``: an include pattern matches and no exclude pattern does; Form-4 insider and STOCK-Act
  congressional trades are excluded);
- ``is_form4``: insider-transaction auto-article (Form 4 / Form 144), kept as metadata, not as text;
- ``third_party_ok``: ``parsing_allowed is True`` (None and False are both not OK, PREREG §6.1).

``passes_clean`` is §6.2 before deduplication; ``keep`` in the output also requires the article to be its
near-duplicate group's representative (``dedupe``).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from newsaction.config import load_yaml
from newsaction.news import load_news_config
from newsaction.news.detect import PATTERNS_PATH

CLEAN_FLAGS = ("non_news", "junk_tag", "is_13f", "is_form4")


@dataclass(frozen=True)
class TitlePatterns:
    holdings_include: re.Pattern[str]
    holdings_exclude: re.Pattern[str]
    form4_include: re.Pattern[str]

    def is_13f(self, title: str) -> bool:
        return bool(self.holdings_include.search(title)) and not self.holdings_exclude.search(title)

    def is_form4(self, title: str) -> bool:
        return bool(self.form4_include.search(title))


def _any(patterns: Iterable[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


@functools.cache
def _load(path: Path, mtime_ns: int) -> TitlePatterns:
    raw = load_yaml(path)
    return TitlePatterns(
        holdings_include=_any(raw["holdings_13f"]["include"]),
        holdings_exclude=_any(raw["holdings_13f"]["exclude"]),
        form4_include=_any(raw["form4"]["include"]),
    )


def load_title_patterns(path: Path = PATTERNS_PATH) -> TitlePatterns:
    return _load(path, path.stat().st_mtime_ns)


def _titles(titles: pd.Series) -> list[str]:
    return ["" if pd.isna(t) else str(t) for t in titles.tolist()]


def is_13f(titles: pd.Series) -> pd.Series:
    pat = load_title_patterns()
    return pd.Series([pat.is_13f(t) for t in _titles(titles)], index=titles.index, dtype=bool)


def is_form4(titles: pd.Series) -> pd.Series:
    pat = load_title_patterns()
    return pd.Series([pat.is_form4(t) for t in _titles(titles)], index=titles.index, dtype=bool)


def _bool(s: pd.Series) -> pd.Series:
    """Nullable vendor booleans: True only where the value is True."""
    return s.astype("boolean").fillna(False).astype(bool)


def third_party_ok(parsing_allowed: pd.Series) -> pd.Series:
    """PREREG §6.1 / CLAUDE.md D15: only ``parsing_allowed is True`` may ever leave this machine."""
    return _bool(parsing_allowed)


def clean_flags(df: pd.DataFrame) -> pd.DataFrame:
    """non_news, junk_tag, is_13f, is_form4 and third_party_ok for ``df`` (title, tag_type, ...)."""
    junk = set(load_news_config().junk_tags)
    return pd.DataFrame(
        {
            "non_news": _bool(df["non_news"]),
            "junk_tag": df["tag_type"].isin(junk).fillna(False).astype(bool),
            "is_13f": is_13f(df["title"]),
            "is_form4": is_form4(df["title"]),
            "third_party_ok": third_party_ok(df["parsing_allowed"]),
        },
        index=df.index,
    )


def passes_clean(flags: pd.DataFrame) -> pd.Series:
    """PREREG §6.2 before near-duplicate collapse: none of the cleaning flags is set."""
    return ~flags[list(CLEAN_FLAGS)].any(axis=1)
