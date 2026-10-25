"""Residual-leak scanner for masked states (PREREG §6.3 target < 0.5%; PRD NA-04 S3, S7, AC2).

The scanner is **independent of the masker**: it imports nothing from ``states.mask`` and does not read
``configs/aliases.yaml`` (tests/test_states_mask.py checks the imports). Its references are:
- **names**: the company's ATOM names (every share class; legal suffixes and class designations removed by
  its own rule), their distinctive words, and the names **harvested** from the unmasked event texts, i.e. the
  words right before the company's own "(TICKER)" / "(EXCH: TICKER)" (``harvest_names``, seen ≥ 3 times);
- **tickers**: the company's tickers in any form: $T, any upper-case code + ":" + T (NYSE:, BOATS:), "(T",
  T's, T.O, T/PR, and bare T unless T is an English word (``ENGLISH_TICKERS``);
- **dates**: English, French, German, Italian, Spanish, Portuguese, Dutch and Polish month and weekday names,
  numeric dates, and period labels in any case (Q3, 3Q25, H1 25, FY25, fiscal 2025, "second quarter",
  "first half", "3. Quartal"); **years**: 1900–2099 as a standalone number ("Russell 2000" excepted).

AC2 counts names + tickers and years + dates. The scanner also counts, for the REPORT, price-move sentences,
ticker quotes ("MPC-1.32%"), dollar price levels (price targets, "shares at $X") and a sentinel list of
public figures. It reads the ``news`` items of a state (the only free text).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Final

import pandas as pd

# words that never make a company name on their own (the scanner's own list)
GENERIC: Final = frozenset(
    """the of and for in on by to at as with from a an inc incorporated corp corporation co company companies
    ltd limited plc llc lp group holdings holding international global american america national united
    general first capital financial services service bank bancorp trust partners technologies technology
    systems solutions industries resources energy power electric health healthcare medical pharmaceuticals
    sciences scientific laboratories labs networks communications media entertainment software data digital
    realty properties residential brands foods products materials chemicals motors motor auto automotive
    parts insurance life markets exchange management new york north south east west southern western
    northern pacific texas royal universal stock stocks shares share news report reports update analyst
    rating price target class earnings flash unusually large options volume sees""".split()  # noqa: SIM905
)
ENGLISH_TICKERS: Final = frozenset(
    """A C D F J K L O T V X Q ON IT SO DE ES EL ED IP IR PM MA MS HD PG BR CI CE GL FE NI CF ALL NOW KEY KEYS
    LOW COST CAT ARE DASH COIN HOOD APP POOL WELL BALL PEAK DAY FAST HAS TECH DOW USB MAR TAP RE AI WAT CPU
    EXE DOC BRO HUM MET HAL GEN AMP TEL FOX NWS GD""".split()  # noqa: SIM905
)
SENTINEL_PEOPLE: Final = re.compile(
    r"\b(?:Trump|Powell|Biden|Bessent|Lutnick|Yellen|Lagarde|Musk|Buffett|Zuckerberg|Bezos|Dimon|Altman|Nadella|"
    r"Pichai|Jassy|Huang|Putin|Zelensky|Harris|Vance|Xi)\b"
)
_SUFFIX: Final = re.compile(
    r"(?:,?\s+(?:&\s*Co\.?|&\s*Company|Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?|Company|Companies|Ltd\.?|"
    r"Limited|plc|PLC|N\.V\.|S\.A\.|SE|AG|LLC|L\.P\.|LP))+\s*$"
)
_CLASS: Final = re.compile(r"\s*\((?:Class|Series)\s+[A-Z0-9]+\)\s*$|\s+(?:Class|Series)\s+[A-Z0-9]+$")
_PAREN: Final = re.compile(r"^(?P<base>.+?)\s*\((?P<head>[A-Z][a-z]+)\)\s*$")

_YEAR: Final = re.compile(r"(?<!\d[.,])(?<![\w$])(?<!Russell\s)(?:19\d\d|20\d\d)(?![\d%]|\.\d)")
_EN_MONTHS: Final = "January|February|March|April|June|July|August|September|October|November|December"
_F_MONTHS: Final = (
    "janvier|février|fevrier|avril|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|januar|"
    "jänner|februar|märz|maerz|juni|juli|oktober|dezember|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
    "settembre|ottobre|dicembre|enero|febrero|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|"
    "diciembre|janeiro|fevereiro|março|marco|junho|julho|setembro|outubro|novembro|dezembro|januari|februari|"
    "maart|augustus|stycznia|lutego|marca|kwietnia|czerwca|lipca|sierpnia|września|wrzesnia|października|"
    "listopada|grudnia"
)
_F_WEEKDAYS: Final = (
    "montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|lundi|mardi|mercredi|jeudi|vendredi|samedi|"
    "dimanche|lunedì|lunedi|martedì|martedi|mercoledì|mercoledi|giovedì|giovedi|venerdì|venerdi|lunes|martes|"
    "miércoles|miercoles|jueves|viernes|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag"
)
_DATE: Final = re.compile(
    rf"\b(?:{_EN_MONTHS}|{_EN_MONTHS.upper()})\b|\b(?:May|MAY)\s+\d"
    r"|\b(?i:(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2})\b"
    r"|\b(?i:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?)\b"
    rf"|\b(?i:{_F_MONTHS}|{_F_WEEKDAYS})\b|\b\d{{1,2}}\.?\s+(?i:mai|mars|mei)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"
    r"|(?<![\d/.$,])\b(?:1[0-2]|0?[1-9])/(?:1[3-9]|2\d|3[01])\b(?![\d/%])"
    r"|\b(?i:Q[1-4]|[1-4]Q\d{2}|FY\s?'?\d{2,4}|fiscal\s+(?:year\s+)?\d{4}|[1-4]\.\s*Quartal)\b"
    r"|\b(?i:(?:first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter|(?:first|second|1st|2nd)[\s-]+half)\b"
    r"|\b[Hh][12]\s?'?\d{2,4}\b|\b[12]H\s?'?\d{2}\b"
)
_PRICE_MOVE: Final = re.compile(
    r"(?i)\b(?:shares?|stock|premarket|pre-market|after-hours|extended trading)\b[^.!?]{0,50}?"
    r"\b(?:rise[sn]?|rose|rising|fall(?:s|en|ing)?|fell|jump(?:s|ed|ing)?|drop(?:s|ped|ping)?|gain(?:s|ed|ing)?|"
    r"slides?|slid|slip(?:s|ped)?|climb(?:s|ed|ing)?|surg(?:e|es|ed|ing)|plung(?:e|es|ed|ing)|soar(?:s|ed|ing)?|"
    r"tumbl(?:e|es|ed|ing)|sinks?|sank|rall(?:y|ies|ied)|declin(?:e|es|ed|ing)|advanc(?:e|es|ed|ing)|up|down|"
    r"higher|lower)\b[^.!?]{0,25}?\d+(?:[.,]\d+)?\s?%"
    r"|\b\d+(?:[.,]\d+)?\s?%\s+(?:premarket|pre-market|in premarket|before the bell|after hours)"
)
_QUOTE: Final = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,5}\s?[+\-−–]\s?\d+(?:\.\d+)?\s?%")
_PRICE_LEVEL: Final = re.compile(
    r"(?i)(?:price\s+target|target\s+price|price\s+objective|\bPT\b)[^.!?]{0,60}?\$\s?\d"
    r"|\$\s?\d[\d,]*(?:\.\d+)?\s+(?:price\s+target|PT)\b"
    r"|(?<!per\s)\b(?:shares?|stock)\s+(?:at|to|closed\s+at|trading\s+at)\s+\$\s?\d"
)


@dataclass(frozen=True)
class LeakCounts:
    names: int
    tickers: int
    years: int
    dates: int
    price_moves: int = 0
    quotes: int = 0
    price_levels: int = 0
    people: int = 0

    @property
    def name_or_ticker(self) -> bool:
        return self.names + self.tickers > 0

    @property
    def year_or_date(self) -> bool:
        return self.years + self.dates > 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def core_name(name: str) -> list[str]:
    """Name phrases of an ATOM name: class and legal suffixes removed; "X (The)" gives "The X" and "X"."""
    base = _CLASS.sub("", name.strip()).strip()
    m = _PAREN.match(base)
    stems = [f"{m['head']} {m['base']}", m["base"]] if m else [base]
    out = []
    for stem in stems:
        core = _SUFFIX.sub("", stem).strip().rstrip(",")
        out.append(core)
        if core.lower().startswith("the "):
            out.append(core[4:])
    return [o for o in dict.fromkeys(out) if len(o) >= 3]


_LOWER: Final = re.compile(r"(?<![A-Za-z])[a-z]{2,}(?![A-Za-z])")


def ordinary_words(texts: Iterable[str], min_count: int = 20) -> frozenset[str]:
    """Words written in lower case at least ``min_count`` times in ``texts``: the scanner's vocabulary."""
    counts: Counter[str] = Counter()
    for t in texts:
        counts.update(_LOWER.findall(t))
    return frozenset(w for w, n in counts.items() if n >= min_count)


def _ticker_alt(t: str) -> str:
    return r"[.\-/]".join(re.escape(p) for p in re.split(r"[.\-/]", t.upper()))


def harvest_names(
    articles: pd.DataFrame, tickers: Mapping[int, Sequence[str]], min_count: int = 3
) -> dict[int, list[str]]:
    """Per company: phrases of up to four capitalized words written right before its own "(TICKER)" or
    "(EXCH: TICKER)" in the unmasked texts (``articles``: company_id, title, snippet), seen ≥ ``min_count``
    times, legal suffix and leading generic words removed, with at least one non-generic word."""
    counts: dict[int, Counter[str]] = {}
    patterns: dict[int, re.Pattern[str]] = {}
    for cid, ts in tickers.items():
        alt = "|".join(_ticker_alt(t) for t in ts)
        patterns[int(cid)] = re.compile(
            rf"((?:[A-Z][\w&.'’\-]*\s+){{0,3}}[A-Z][\w&.'’\-]*)\s*\(\s*(?:[A-Z][A-Za-z]{{1,11}}\s?:\s?)?"
            rf"(?:{alt})\s*\)"
        )
    for cid, title, snippet in zip(
        articles["company_id"], articles["title"], articles["snippet"], strict=True
    ):
        rx = patterns.get(int(cid))
        if rx is None:
            continue
        for m in rx.finditer(f"{title} {snippet}"):
            words = _SUFFIX.sub("", re.split(r"[.:!?|]\s+", m.group(1).strip())[-1]).split()
            while words and words[0].lower().strip(".,'’") in GENERIC:
                words = words[1:]
            phrase = re.sub(r"['’]s$", "", " ".join(words).strip(" ,.'’"))
            if len(phrase) >= 3 and any(w.lower().strip(".,'’") not in GENERIC for w in phrase.split()):
                counts.setdefault(int(cid), Counter())[phrase] += 1
    return {cid: sorted(p for p, n in c.items() if n >= min_count) for cid, c in counts.items()}


class LeakScanner:
    """Residual leaks of one company's state (module docstring)."""

    def __init__(
        self,
        companies: pd.DataFrame,
        extra_tickers: Iterable[tuple[int, str]] = (),
        harvested: Mapping[int, Sequence[str]] | None = None,
        ordinary: frozenset[str] = frozenset(),
    ) -> None:
        """``companies``: company_id, ticker, name (NA-01 ``companies.parquet``); ``extra_tickers``:
        (company_id, ticker) of former / vendor tickers; ``harvested``: ``harvest_names`` output;
        ``ordinary``: ``ordinary_words`` of the unmasked texts. A one-word name counts as written or in
        capitals: a whole ATOM name always ("Target"), a word of a longer name or a harvested word only if
        it is not an ordinary word ("Grumman" counts, "Research" does not)."""
        self.ordinary = ordinary
        self.atom: dict[int, set[str]] = {}
        self.names: dict[int, set[str]] = {}
        self.tickers: dict[int, set[str]] = {}
        rows = zip(companies["company_id"], companies["ticker"], companies["name"], strict=True)
        for cid, ticker, name in rows:
            self.names.setdefault(int(cid), set()).update(core_name(str(name)))
            self.atom.setdefault(int(cid), set()).update(core_name(str(name)))
            self.tickers.setdefault(int(cid), set()).add(str(ticker).upper())
        for cid, t in extra_tickers:
            self.tickers.setdefault(int(cid), set()).add(t.upper())
        for cid, phrases in (harvested or {}).items():
            self.names.setdefault(int(cid), set()).update(phrases)
        self._cache: dict[int, tuple[re.Pattern[str] | None, re.Pattern[str] | None]] = {}

    def _patterns(self, cid: int) -> tuple[re.Pattern[str] | None, re.Pattern[str] | None]:
        hit = self._cache.get(cid)
        if hit is not None:
            return hit
        phrases = self.names.get(cid, set())
        atom = self.atom.get(cid, set())

        def distinctive(w: str) -> bool:
            return w.lower() not in GENERIC and w.lower() not in self.ordinary

        multi = {p for p in phrases if len(p.split()) > 1}
        single = {
            p for p in phrases if len(p.split()) == 1 and ((p in atom and len(p) >= 3) or distinctive(p))
        }
        for p in (
            q for q in atom if len(q.split()) > 1
        ):  # words of a longer ATOM name ("Grumman"), 5+ letters
            single.update(
                w for w in re.findall(r"[A-Za-z][A-Za-z'’\-]*", p) if len(w) >= 5 and distinctive(w)
            )
        parts = []
        if multi:
            alt = "|".join(r"[\s\-–]+".join(map(re.escape, re.split(r"[\s\-–]+", p))) for p in sorted(multi))
            parts.append(rf"(?i:(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9]))")
        if single:
            words = sorted(single | {w.upper() for w in single})
            parts.append(rf"(?<![A-Za-z0-9])(?:{'|'.join(map(re.escape, words))})(?![A-Za-z0-9])")
        names = re.compile("|".join(parts)) if parts else None
        ts = sorted(self.tickers.get(cid, set()))
        tickers = None
        if ts:
            alt = "|".join(_ticker_alt(t) for t in ts)
            bare = [t for t in ts if len(t) >= 2 and t not in ENGLISH_TICKERS]
            forms = [
                rf"(?:\$|(?<![A-Za-z])[A-Z][A-Za-z]{{1,11}}\s?:\s?|\(\s*)(?:{alt})(?![A-Za-z0-9])",
                rf"(?<![A-Za-z0-9$&.\-/:(])(?:{alt})(?=['’]s\b)",
            ]
            if bare:
                forms.append(
                    rf"(?<![A-Za-z0-9$&.\-/:(])(?:{'|'.join(_ticker_alt(t) for t in bare)})(?![A-Za-z0-9&'’])"
                )
            tickers = re.compile("|".join(forms))
        self._cache[cid] = (names, tickers)
        return self._cache[cid]

    def scan_text(self, text: str, company_id: int | None) -> LeakCounts:
        names = tickers = 0
        if company_id is not None and company_id >= 0:
            n_re, t_re = self._patterns(company_id)
            names = len(n_re.findall(text)) if n_re is not None else 0
            tickers = len(t_re.findall(text)) if t_re is not None else 0
        return LeakCounts(
            names=names,
            tickers=tickers,
            years=len(_YEAR.findall(text)),
            dates=len(_DATE.findall(text)),
            price_moves=sum(1 for m in _PRICE_MOVE.finditer(text) if "volume" not in m.group(0).lower()),
            quotes=len(_QUOTE.findall(text)),
            price_levels=len(_PRICE_LEVEL.findall(text)),
            people=len(SENTINEL_PEOPLE.findall(text)),
        )

    def residual_leaks(self, state_json: str, company_id: int | None) -> LeakCounts:
        """Leaks in the ``news`` items of a state (headline and snippet)."""
        items = json.loads(state_json).get("news", [])
        text = "\n".join(f"{n['headline']} || {n['snippet']}" for n in items)
        return self.scan_text(text, company_id)
