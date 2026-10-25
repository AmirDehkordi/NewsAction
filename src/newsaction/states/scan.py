"""Residual-leak scanner for masked states (PREREG §6.3 target < 0.5%; PRD NA-04 S3, S7, AC2).

``residual_leaks(state, company_id)`` counts what masking should have removed from a state string:
- **names**: the company's alias phrases and their distinctive words (4+ letters, not a common word or a
  legal suffix: "Grumman" from "Northrop Grumman"), in any case, with spaces and hyphens interchangeable; a
  one-word name that is a common word ("Target", "Visa") only as written or in capitals
  (``mask.split_names``: the definition the masker applies, so a hit is a name the masker failed to remove);
- **tickers**: $TICKER, EXCH:TICKER, "(TICKER" and bare upper-case tickers of 2+ characters outside the
  stoplist;
- **years**: 1900–2099 as a standalone number ("Russell 2000" excepted);
- **dates**: month names (capitalized or in capitals; "May" and abbreviations only before a day number),
  weekdays, numeric dates, quarter / half-year / fiscal-year labels (Q3, 3Q25, H1 25, FY25, fiscal 2025).

Person names are not counted (NER is the masker; NA-06 measures identifiability).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Final

from newsaction.states.mask import (
    EXCHANGES,
    AliasConfig,
    CompanyAliases,
    load_alias_config,
    phrase_regex,
    split_names,
    ticker_regex,
)

_Patterns = tuple[re.Pattern[str] | None, re.Pattern[str] | None, re.Pattern[str] | None]
_YEAR: Final = re.compile(r"(?<!\d[.,])(?<![\w$])(?<!Russell\s)(?:19\d\d|20\d\d)(?![\d%]|\.\d)")
_MONTHS: Final = "January|February|March|April|June|July|August|September|October|November|December"
_DATE: Final = re.compile(
    rf"\b(?:{_MONTHS}|{_MONTHS.upper()})\b|\b(?:May|MAY)\s+\d"
    r"|\b(?i:(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2})\b"
    r"|\b(?i:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"
    r"|\b(?i:Q[1-4]|[1-4]Q\d{2}|FY\s?'?\d{2,4}|fiscal\s+(?:year\s+)?\d{4})\b|\b[Hh][12]\s?'?\d{2,4}\b"
)


@dataclass(frozen=True)
class LeakCounts:
    names: int
    tickers: int
    years: int
    dates: int

    @property
    def name_or_ticker(self) -> bool:
        return self.names + self.tickers > 0

    @property
    def year_or_date(self) -> bool:
        return self.years + self.dates > 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class LeakScanner:
    def __init__(self, aliases: Mapping[int, CompanyAliases], cfg: AliasConfig | None = None) -> None:
        self.cfg = load_alias_config() if cfg is None else cfg
        self.aliases = aliases
        self._cache: dict[int, _Patterns] = {}

    def patterns(self, company_id: int) -> _Patterns:
        hit = self._cache.get(company_id)
        if hit is not None:
            return hit
        a = self.aliases.get(company_id)
        if a is None:
            self._cache[company_id] = (None, None, None)
            return self._cache[company_id]
        loose, strict = split_names(a, self.cfg)
        parts = []
        if loose:
            alt = "|".join(phrase_regex(p) for p in loose)
            parts.append(rf"(?i:(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9]))")
        if strict:
            alt = "|".join(phrase_regex(p) for p in strict)
            parts.append(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])")
        names = re.compile("|".join(parts)) if parts else None
        tick = "|".join(ticker_regex(t) for t in a.tickers)
        bare = [t for t in a.tickers if len(t) >= 2 and t not in self.cfg.bare_ticker_stoplist]
        tickers = (
            re.compile(rf"(?:(?<![A-Za-z])(?:{EXCHANGES})\s*:\s*\$?|\$|\(\s*)(?:{tick})(?![A-Za-z0-9\-])")
            if tick
            else None
        )
        bare_re = (
            re.compile(
                rf"(?<![A-Za-z0-9$&.\-/])(?:{'|'.join(ticker_regex(t) for t in bare)})(?![A-Za-z0-9&\-/])"
            )
            if bare
            else None
        )
        self._cache[company_id] = (names, tickers, bare_re)
        return self._cache[company_id]

    def residual_leaks(self, state: str, company_id: int | None) -> LeakCounts:
        names = tickers = 0
        if company_id is not None:
            n_re, t_re, b_re = self.patterns(company_id)
            names = len(n_re.findall(state)) if n_re is not None else 0
            spans = [m.span() for m in t_re.finditer(state)] if t_re is not None else []
            tickers = len(spans)
            if b_re is not None:
                tickers += sum(
                    1 for m in b_re.finditer(state) if not any(s <= m.start() < e for s, e in spans)
                )
        return LeakCounts(names, tickers, len(_YEAR.findall(state)), len(_DATE.findall(state)))


def residual_leaks(
    state: str, company_id: int | None, aliases: Mapping[int, CompanyAliases], cfg: AliasConfig | None = None
) -> LeakCounts:
    """Module-level form of ``LeakScanner.residual_leaks``."""
    return LeakScanner(aliases, cfg).residual_leaks(state, company_id)
