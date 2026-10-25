"""Masking of news text (PREREG §6.3; PRD NA-04 S3).

In this order, on each title and snippet (already scrubbed by NA-02):
1. **Datelines and identifiers.** A leading press-release dateline ("JACKSONVILLE, Fla., Oct. 16, 2025
   /PRNewswire/ --", "NEW YORK (Reuters) -") and ISIN codes are removed: they carry dates and
   headquarters cities.
2. **Company.** The company's names and aliases (``configs/aliases.yaml``; ``CompanyAliases``) become
   "the company", with an optional legal suffix ("Apple Inc." → "the company"). Ticker forms become "the
   company": $T, EXCH:T with any upper-case exchange code (BOATS:NEE), T.O, T/PR, T's, bare T outside the
   stoplist; a parenthesized ticker ("(NASDAQ: AAPL)", "(COST 0.53%)") is removed.
3. **Dates.** Full dates, weekdays and months, in English and in French, German, Italian, Spanish,
   Portuguese, Dutch and Polish → "recently"; years → "the year"; fiscal years → "the fiscal year";
   quarter labels in any case ("Q3 FY2025", "Second Quarter", "SECOND-QUARTER", "3Q25", "3. Quartal") →
   "the quarter" / "quarterly"; half-year labels ("first half", "1H25") → "the half-year".
4. **People.** spaCy ``en_core_web_sm`` PERSON entities (not matching any S&P 500 company alias), and every
   capitalized occurrence of a corpus surname (the last word of a multi-word name seen at least
   ``SURNAME_MIN_COUNT`` times; "Trump", "Powell" alone): a name right after a role noun ("CEO Tim Cook",
   "analyst Dan Ives") is dropped; otherwise it becomes "an executive" when an executive title is within six
   words, else "a person".
5. **Price talk and price levels.** ``news.detect`` scrub again (after-the-fact and price-path sentences,
   share-price levels); then sentences with a stock / share price move in percent and ticker quotes
   ("MPC-1.32%") are dropped; price-target amounts become a relative change ("raises its price target to $622
   from $600" → "raises its price target up by about 4%") or are dropped, and per-share deal prices become
   "a per-share price". Fundamental figures (EPS, revenue, dividends, guidance) are kept.

A replacement at the start of a sentence is capitalized.
"""

from __future__ import annotations

import functools
import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from newsaction.config import load_yaml
from newsaction.news.detect import load_detector, split_sentences
from newsaction.states import ALIASES_PATH

COMPANY: Final = "the company"
EXECUTIVE: Final = "an executive"
PERSON: Final = "a person"
RECENTLY: Final = "recently"
YEAR: Final = "the year"
FISCAL_YEAR: Final = "the fiscal year"
QUARTER: Final = "the quarter"
HALF_YEAR: Final = "the half-year"
SURNAME_MIN_COUNT: Final = 3
SPACY_MODEL: Final = "en_core_web_sm"
SPACY_EXCLUDE: Final = ("parser", "lemmatizer", "attribute_ruler", "tagger", "senter", "morphologizer")

EXCHANGES: Final = (
    r"NYSE\s?Arca|NYSE\s?American|NYSE\s?MKT|NYSEARCA|NYSEAMERICAN|NYSEMKT|NYSE|NASDAQGS|NASDAQGM|NASDAQCM|"
    r"NasdaqGS|NasdaqGM|NasdaqCM|NASDAQ|Nasdaq|AMEX|BATS|CBOE|Cboe|OTC|OTCMKTS"
)
# any exchange-like code before a colon: NYSE:, BOATS:, OTC:, XETRA:, LSE: (NA-04 verification)
EXCH_PREFIX: Final = rf"(?:(?<![A-Za-z])(?:{EXCHANGES}|[A-Z][A-Za-z]{{1,11}})\s*:\s*)"
# share-class / venue suffixes: AAPL.O, NEE/PR, NEE/PT, BRK.B (the class is part of the ticker)
TICKER_SUFFIX: Final = r"(?:[./](?:[A-Z]{1,2}|PR[A-Z]?)(?![A-Za-z]))?"
# a quote of any ticker with a signed percent change: "MPC-1.32%", "(AAPL +0.87%)", "MSFT -1.19 %"
_NOT_TICKERS: Final = (
    r"(?!(?:EPS|FCF|GDP|CPI|PPI|PCE|ROE|ROI|ROA|YOY|QOQ|EBIT|ARR|NII|NIM|ARPU|AUM|RPO|FY|Q[1-4])\b)"
)
QUOTE: Final = re.compile(
    rf"\s*\(\s*{_NOT_TICKERS}[A-Z]{{1,5}}(?:[.\-][A-Z])?\s*[+\-−–]?\s?\d+(?:\.\d+)?\s?%\s*\)"
    rf"|(?<![A-Za-z0-9]){_NOT_TICKERS}[A-Z]{{1,5}}(?:\.[A-Z])?\s?[+\-−–]\s?\d+(?:\.\d+)?\s?%"
)
_MOVE_VERB: Final = (
    r"(?:rise[sn]?|rose|rising|fall(?:s|en|ing)?|fell|jump(?:s|ed|ing)?|drop(?:s|ped|ping)?|gain(?:s|ed|ing)?|"
    r"slides?|slid|slip(?:s|ped)?|climb(?:s|ed|ing)?|surg(?:e|es|ed|ing)|plung(?:e|es|ed|ing)|soar(?:s|ed|ing)?|"
    r"tumbl(?:e|es|ed|ing)|sinks?|sinking|sank|rall(?:y|ies|ied)|declin(?:e|es|ed|ing)|advanc(?:e|es|ed|ing)|"
    r"edg(?:e|es|ed)\s+(?:up|down|higher|lower)|trad(?:e|es|ed|ing)\s+(?:up|down|higher|lower)|"
    r"(?:are|is|was|were)\s+(?:up|down)|higher|lower|up|down)"
)
# a stock / share price move in percent (PREREG §6.4), unless a fundamental noun is its subject
_SUBJECT: Final = (
    r"(?:shares?|stocks?|the\s+company(?:['’]s)?|premarket|pre-market|after-hours|extended\s+trading)"
)
_MOVE_SUBJECT: Final = re.compile(rf"(?i)\b{_SUBJECT}\b")
PRICE_MOVE: Final = re.compile(
    rf"(?i)\b{_SUBJECT}\b(?P<mid>[^.!?%]{{0,50}}?)\b{_MOVE_VERB}\b[^.!?]{{0,25}}?\d+(?:[.,]\d+)?\s?%"
)
PRICE_MOVE_AFTER: Final = re.compile(
    r"(?i)\b\d+(?:[.,]\d+)?\s?%\s+(?:in\s+)?(?:premarket|pre-market|before\s+the\s+bell|after\s+hours|after-hours)"
)
_FUNDAMENTAL_SUBJECT: Final = re.compile(
    r"(?i)\b(?:revenues?|sales|earnings|eps|income|profits?|margins?|volumes?|orders|shipments|deliveries|guidance|"
    r"dividends?|bookings|subscribers|users|traffic|backlog|cash\s+flow|demand|output|production|compensation|"
    r"buybacks?|repurchases?|outstanding|count|targets?|ratings?|estimates?|forecasts?|outlook|sales|costs?|"
    r"expenses?|spending|capex|debt|assets|deposits|loans|premiums|rates?|unemployment|inflation|gdp|index|"
    r"prices?\s+of\s+(?!the\s+company))\b"
)
_PT: Final = r"(?:price\s+targets?|target\s+prices?|price\s+objectives?|price\s+goals?|PTs?|targets?)"
_AMT: Final = (
    r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?!\d|\.\d|\s*(?:million|billion|trillion|bn|mn|[mbk]\b|%))"
)
PT_FROM_TO: Final = re.compile(
    rf"(?i)\b(?P<label>{_PT})\b(?P<mid>[^$.;!?]{{0,60}}?)\bfrom\s+{_AMT}\s+to\s+{_AMT}"
)
PT_TO_FROM: Final = re.compile(
    rf"(?i)\b(?P<label>{_PT})\b(?P<mid>[^$.;!?]{{0,60}}?)(?:\b(?:to|at)\s+)?{_AMT}\s*,?\s*"
    rf"(?:from|vs\.?|versus|up\s+from|down\s+from)\s+{_AMT}"
)
PT_AMOUNT: Final = re.compile(
    rf"(?i)\b(?P<label>{_PT})\b(?P<mid>[^$.;!?]{{0,80}}?)"
    rf"(?:\b(?:to|at|of|from|is)\s+)?(?:(?:the|a)\s+previous\s+)?{_AMT}"
)
AMOUNT_PT: Final = re.compile(rf"(?i){_AMT}\s+(?P<label>{_PT})\b")
PER_SHARE: Final = re.compile(r"(?i)\$\s?\d[\d,]*(?:\.\d+)?\s+(?:a|per)\s+share\b")
_DEAL: Final = re.compile(
    r"(?i)\b(?:acquir\w*|acquisition|buy(?:out|s|ing)?|bought|offer\w*|deal|merger|merge|takeover|tender|bid|"
    r"valu\w+|purchas\w*|sale|sell\w*|sold|pric(?:ed|ing)|consideration|premium)\b"
)
_FUND_LEFT: Final = re.compile(
    r"(?i)\b(?:earnings|eps|dividends?|income|loss(?:es)?|profits?|revenues?|sales|ffo|affo|book\s+value|"
    r"cash\s+flow|distributions?|payout|nav|net\s+asset|guidance|estimates?|consensus)\b"
)
_MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH: Final = "(?:" + "|".join([*_MONTHS, *(m.upper() for m in _MONTHS)]) + ")"
MON: Final = (
    r"(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\."
)
MONTH_ANY: Final = (
    rf"(?:{MONTH}|{MON}|(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|"
    rf"OCT|NOV|DEC)(?=\s+\d))"
)
WEEKDAY: Final = "(?:" + "|".join([*_WEEKDAYS, *(d.upper() for d in _WEEKDAYS)]) + ")"
YEAR_RE: Final = r"(?:19\d\d|20\d\d)"
# French, German, Italian, Spanish, Portuguese, Dutch and Polish month and weekday names (NA-04 verification)
F_MONTH: Final = (
    r"(?:janvier|f[ée]vrier|avril|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre|januar|j[äa]nner|"
    r"februar|m[äa]rz|maerz|juni|juli|oktober|dezember|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
    r"settembre|ottobre|dicembre|enero|febrero|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|"
    r"noviembre|diciembre|janeiro|fevereiro|mar[çc]o|junho|julho|setembro|outubro|novembro|dezembro|januari|"
    r"februari|maart|augustus|stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|wrze[śs]nia|"
    r"pa[źz]dziernika|listopada|grudnia)"
)
F_MONTH_DAY_ONLY: Final = r"(?:mars|mai|mei|maio)"  # also ordinary words: only next to a day number or year
F_WEEKDAY: Final = (
    r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|lundi|mardi|mercredi|jeudi|vendredi|samedi|"
    r"dimanche|luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica|lunes|martes|"
    r"mi[ée]rcoles|jueves|viernes|s[áa]bado|segunda-feira|ter[çc]a-feira|quarta-feira|quinta-feira|sexta-feira|"
    r"maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)"
)
F_PREP: Final = (
    r"(?:(?:am|vom|bis|zum|seit|ab|le|du|au|des|el|del|dal|il|op|de|em|no|na|w|z|ce|cette|diesen|letzten|"
    r"vergangenen|n[äa]chsten|este|ese|questo|scorso)\s+)"
)
DAY: Final = r"(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?"
PREP: Final = (
    r"(?i:(?:as\s+of|earlier\s+in|later\s+in|in|on|at|during|from|since|until|through|by|before|after|around|"
    r"ahead\s+of|starting|beginning|effective|dated)\s+)"
)
ROLE_NOUNS: Final = (
    r"CEO|CFO|COO|CTO|CIO|CMO|President|president|Chairman|chairman|Chairwoman|chairwoman|Chair|chair|"
    r"Founder|founder|co-founder|Co-founder|Co-Founder|Director|director|Executive|executive|Officer|officer|"
    r"Chief|chief|boss|head|Head|analyst|Analyst|analysts|economist|strategist|Strategist|spokesperson|"
    r"spokesman|spokeswoman|investor|Investor|Senator|Sen\.|Rep\.|Representative|Secretary|Governor|Gov\.|"
    r"Judge|judge|Justice|Commissioner|commissioner|Minister|minister|Mayor|lawyer|attorney|partner|Partner"
)
EXEC_TITLES: Final = re.compile(
    r"\b(?:CEO|CFO|COO|CTO|CIO|CMO|[Pp]resident|[Cc]hair(?:man|woman)?|[Ff]ounder|co-founder|[Dd]irector|"
    r"[Ee]xecutive|[Oo]fficer|[Cc]hief|boss|[Hh]ead|EVP|SVP|VP)\b"
)
_ROLE_BEFORE: Final = re.compile(rf"(?:\b(?:{ROLE_NOUNS}))\s*,?\s*$")
_NON_PERSON_LABELS: Final = frozenset({"ORG", "PRODUCT", "GPE", "LOC", "FAC", "NORP", "WORK_OF_ART", "EVENT"})
_NOT_PEOPLE: Final = frozenset({"recently", "the year", "a holiday", "the quarter", "the fiscal year"})
_SPEECH_AFTER: Final = re.compile(
    r"^\s*,?\s*(?:said|says|told|wrote|writes|added|adds|noted|notes|stated|explained|commented|argued|warned|"
    r"predicted|expects|believes|thinks)\b"
)
_ROLE_AFTER: Final = re.compile(r"\s+(?:CEO|CFO|COO|CTO|Chairman|chief|Chief|President|executives?|boss)\b")
_SENT_START: Final = re.compile(r"(?:^|[.!?:]\s+|\n\s*|^[\"“‘(\[]\s*)$")
_DOUBLE_DET: Final = re.compile(r"\b(its|their|our|his|her|the|this|that|a|an|The|Its|Their|Our)\s+the\s+")
_WS: Final = re.compile(r"[ \t]{2,}")
_SPACE_PUNCT: Final = re.compile(r"\s+([,.;:!?)\]])")
_OPEN_SPACE: Final = re.compile(r"([(\[])\s+")
_EMPTY_PARENS: Final = re.compile(r"\(\s*[,;]?\s*\)")
_CAP_WORD: Final = re.compile(r"(?<![A-Za-z])(?P<w>[A-Z][A-Za-z]+)(?:['’]s)?(?![A-Za-z])")
_SEP_RUN: Final = re.compile(r"\s*([;|•])(?:\s*[;|•])+\s*")


def _cap(word: str, before: str) -> str:
    return word[:1].upper() + word[1:] if _SENT_START.search(before) else word


def _tidy(text: str) -> str:
    out = _DOUBLE_DET.sub(r"\1 ", text)
    out = _EMPTY_PARENS.sub("", out)
    out = _SPACE_PUNCT.sub(r"\1", out)
    out = _OPEN_SPACE.sub(r"\1", out)
    out = _WS.sub(" ", out)
    return out.strip(" ,;-–—")


@dataclass(frozen=True)
class AliasConfig:
    legal_suffixes: tuple[str, ...]
    common_words: frozenset[str]
    bare_ticker_stoplist: frozenset[str]
    companies: Mapping[str, Mapping[str, tuple[str, ...]]]
    person_names: frozenset[str] = frozenset()


@functools.cache
def _load_alias_config(path: Path, mtime_ns: int) -> AliasConfig:
    raw = load_yaml(path)
    comps: dict[str, dict[str, tuple[str, ...]]] = {}
    for ticker, spec in (raw.get("companies") or {}).items():
        spec = spec or {}
        comps[str(ticker)] = {
            "names": tuple(str(n) for n in spec.get("names", [])),
            "tickers": tuple(str(t) for t in spec.get("tickers", [])),
        }
    return AliasConfig(
        legal_suffixes=tuple(str(s) for s in raw["legal_suffixes"]),
        common_words=frozenset(str(w) for w in raw["common_words"]),
        bare_ticker_stoplist=frozenset(str(t) for t in raw["bare_ticker_stoplist"]),
        companies=comps,
        person_names=frozenset(str(n) for n in raw.get("person_names", [])),
    )


def load_alias_config(path: Path = ALIASES_PATH) -> AliasConfig:
    return _load_alias_config(path, path.stat().st_mtime_ns)


def normalize_ticker(t: str) -> str:
    return t.strip().upper().replace(".", "-").replace("/", "-")


_CLASS: Final = re.compile(r"\s*\((?:Class|Series)\s+[A-Z0-9]+\)\s*$|\s+(?:Class|Series)\s+[A-Z0-9]+$")
_PAREN_TAIL: Final = re.compile(r"^(?P<base>.+?)\s*\((?P<head>The|Eli|[A-Z][a-z]+)\)\s*$")


def name_variants(name: str, cfg: AliasConfig) -> list[str]:
    """Alias phrases derived from an ATOM name (``configs/aliases.yaml`` header, item 1)."""
    base = _CLASS.sub("", name.strip()).strip()
    out: list[str] = []
    m = _PAREN_TAIL.match(base)
    stems = [f"{m.group('head')} {m.group('base')}", m.group("base")] if m else [base]
    suffix = re.compile(
        r"(?:,?\s+(?:"
        + "|".join(re.escape(s).rstrip(r"\.") + r"\.?" for s in cfg.legal_suffixes)
        + r"))+\s*$"
    )
    for stem in stems:
        core = suffix.sub("", stem).strip().rstrip(",")
        if core.startswith("The ") and len(core.split()) > 1:
            out += [core, core[4:]]
        else:
            out.append(core)
    words = out[-1].split()
    for n in range(len(words) - 1, 1, -1):
        out.append(" ".join(words[:n]))
    first = words[0] if words else ""
    if len(words) > 1 and len(re.sub(r"[^A-Za-z]", "", first)) >= 4 and first not in cfg.common_words:
        out.append(first)
    return [o for o in dict.fromkeys(out) if o]


@dataclass(frozen=True)
class CompanyAliases:
    company_id: int
    names: tuple[str, ...]  # longest first
    tickers: tuple[str, ...]  # normalized (class separator "-")


def build_aliases(
    companies: pd.DataFrame,
    extra_tickers: Iterable[tuple[int, str]] = (),
    cfg: AliasConfig | None = None,
) -> dict[int, CompanyAliases]:
    """Alias sets per company_id. ``companies``: symbol_id, company_id, ticker, name (NA-01).
    ``extra_tickers``: (company_id, ticker) from ATOM ref.symbol_ticker and the NA-02 vendor aliases."""
    cfg = load_alias_config() if cfg is None else cfg
    names: dict[int, list[str]] = {}
    tickers: dict[int, list[str]] = {}
    by_ticker = {
        normalize_ticker(str(t)): int(c)
        for t, c in zip(companies["ticker"], companies["company_id"], strict=True)
    }
    for cid, name, ticker in zip(
        companies["company_id"], companies["name"], companies["ticker"], strict=True
    ):
        names.setdefault(int(cid), []).extend(name_variants(str(name), cfg))
        tickers.setdefault(int(cid), []).append(normalize_ticker(str(ticker)))
    for cid, t in extra_tickers:
        tickers.setdefault(int(cid), []).append(normalize_ticker(t))
    for key, spec in cfg.companies.items():
        cid = by_ticker.get(normalize_ticker(key))
        if cid is None:
            continue  # a curated company outside this universe
        names.setdefault(cid, []).extend(spec["names"])
        tickers.setdefault(cid, []).extend(normalize_ticker(t) for t in spec["tickers"])
    out = {}
    for cid in sorted(names):
        ns = sorted(dict.fromkeys(n for n in names[cid] if n), key=lambda s: (-len(s), s))
        ts = sorted(dict.fromkeys(tickers.get(cid, [])), key=lambda s: (-len(s), s))
        out[cid] = CompanyAliases(cid, tuple(ns), tuple(ts))
    return out


def phrase_regex(phrase: str) -> str:
    """Words of ``phrase`` separated by any run of spaces or hyphens ("Coca-Cola" ~ "Coca Cola"); a period may
    be followed by a space ("J.M. Smucker" ~ "J. M. Smucker")."""
    parts = [p for p in re.split(r"[\s\-–]+", phrase.strip()) if p]
    out = ""
    for i, p in enumerate(parts):
        if i:
            out += r"[\s\-–]*" if parts[i - 1].endswith(".") else r"[\s\-–]+"
        if p in ("&", "and"):
            out += r"(?:&|and)"  # "Church & Dwight" ~ "Church and Dwight"
            continue
        out += re.escape(p).replace(r"\.", r"\.\s*") if p.endswith(".") and len(p) > 1 else re.escape(p)
    return re.sub("['’]", "['’]", out.replace(r"\.\s*\.", r"\."))


_LOWER: Final = re.compile(r"(?<![A-Za-z])[a-z]{2,}(?![A-Za-z])")


def lowercase_vocabulary(texts: Iterable[str], min_count: int) -> frozenset[str]:
    """Words written in lower case at least ``min_count`` times in ``texts``: ordinary English words."""
    counts: dict[str, int] = {}
    for t in texts:
        for w in _LOWER.findall(t):
            counts[w] = counts.get(w, 0) + 1
    return frozenset(w for w, n in counts.items() if n >= min_count)


_WORD: Final = re.compile(r"[A-Za-z][A-Za-z&]*(?:['’][A-Za-z]+)?")


def distinctive_words(phrases: Iterable[str], cfg: AliasConfig) -> set[str]:
    """Words of 4+ letters of alias phrases that are neither common words nor legal suffixes ("Grumman")."""
    skip = cfg.common_words | {s.rstrip(".") for s in cfg.legal_suffixes}
    out = set()
    for phrase in phrases:
        for w in _WORD.findall(phrase):
            core = re.sub(r"['’]s$", "", w)
            if (
                len(re.sub(r"[^A-Za-z]", "", core)) >= 4
                and core not in skip
                and core.capitalize() not in skip
            ):
                out.add(core)
    return out


def split_names(a: CompanyAliases, cfg: AliasConfig) -> tuple[list[str], list[str]]:
    """(case-insensitive patterns, case-sensitive patterns) of a company: phrases and distinctive words match
    in any case; a one-word name that is a common word ("Target", "Visa") only as written or in capitals."""
    loose, strict = set(distinctive_words(a.names, cfg)), set()
    for n in a.names:
        if len(re.split(r"[\s\-–]+", n.strip())) == 1 and (n in cfg.common_words or len(n) < 4):
            strict.update({n, n.upper(), n.capitalize()})
        else:
            loose.add(n)
    order = lambda v: (-len(v), v)  # noqa: E731
    return sorted(loose, key=order), sorted(strict, key=order)


def ticker_regex(t: str) -> str:
    """A normalized ticker with any class separator: BRK-B matches BRK.B, BRK/B, BRK-B, BRKB is not."""
    return r"[.\-/]".join(re.escape(p) for p in t.split("-"))


@dataclass
class CompanyPatterns:
    names: re.Pattern[str] | None
    names_strict: re.Pattern[str] | None
    stock_ticker: re.Pattern[str] | None
    paren_ticker: re.Pattern[str] | None
    prefixed_ticker: re.Pattern[str] | None
    bare_ticker: re.Pattern[str] | None


Candidate = tuple[int, int, list[str]]  # a PERSON entity: start, end, its words without a possessive


@dataclass
class MaskCounts:
    names: int = 0
    tickers: int = 0
    dates: int = 0
    persons: int = 0

    def add(self, other: MaskCounts) -> None:
        self.names += other.names
        self.tickers += other.tickers
        self.dates += other.dates
        self.persons += other.persons


_DATELINE: Final = re.compile(
    rf"^\s*[A-Z][A-Za-z .'\-]{{1,40}}(?:,\s*[A-Z][A-Za-z.]{{1,15}}(?:\s+[A-Z][A-Za-z.]{{1,15}})?)?\s*,?\s*"
    rf"(?:{WEEKDAY},?\s+)?{MONTH_ANY}\s+{DAY},?\s+{YEAR_RE}\s*(?:/\s*[A-Za-z\- ]{{2,40}}\s*/)?\s*[-–—]+\s*"
)
_WIRE_DATELINE: Final = re.compile(
    r"^\s*[A-Z][A-Z .'\-]{2,40}(?:,\s*[A-Z][A-Za-z.]{1,15})?\s*\((?:Reuters|AP|Bloomberg|Dow Jones|AFP|"
    r"Business Wire|BUSINESS WIRE|PRNewswire|GLOBE NEWSWIRE)\)\s*[-–—]+\s*"
)
_NBSP: Final = re.compile(r"[\u00a0\u2007\u202f]")
_EMAIL_URL: Final = re.compile(r"\S+@\S+\.[A-Za-z]{2,}|\bhttps?://\S+|\bwww\.\S+")  # domains name companies
_ISIN: Final = re.compile(r"\s*\(?\bISIN\b:?\s*[A-Z]{2}[A-Z0-9]{9}\d\)?|\b[A-Z]{2}[A-Z0-9]{9}\d\b")

_I: Final = "(?i)"
_DATE_RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(p[len(_I) :], re.IGNORECASE) if p.startswith(_I) else re.compile(p), r)
    for p, r in (
        (r"\b(?:Black|Cyber|Good)\s+(?:Friday|Monday)\b", "a holiday"),
        (
            rf"{_I}{F_PREP}?\b\d{{1,2}}\.?\s+(?:de\s+)?(?:{F_MONTH}|{F_MONTH_DAY_ONLY})\b(?:\s+(?:de\s+)?{YEAR_RE})?",
            RECENTLY,
        ),
        (rf"{_I}{F_PREP}?\b(?:{F_MONTH}|{F_MONTH_DAY_ONLY})\s+(?:de\s+)?{YEAR_RE}", RECENTLY),
        (rf"{_I}{F_PREP}?\b{F_MONTH}\b", RECENTLY),
        (rf"{_I}{F_PREP}?\b{F_WEEKDAY}\b", RECENTLY),
        (r"\bam\s+\d{1,2}\.(?=[\s,;]|$)", RECENTLY),
        (
            rf"{_I}\b(?:im\s+)?(?:[1-4]\.\s*Quartal|[1-4](?:er|e|º|°)?\s+trimestre|T[1-4]\s*'?(?:{YEAR_RE}|\d{{2}}))\b",
            QUARTER,
        ),
        (rf"{PREP}?\b\d{{4}}-\d{{2}}-\d{{2}}\b", RECENTLY),
        (rf"{PREP}?\b\d{{1,2}}/\d{{1,2}}/(?:\d{{4}}|\d{{2}})\b", RECENTLY),
        (rf"{PREP}?\b\d{{1,2}}\.\d{{1,2}}\.(?:\d{{4}}|\d{{2}})\b", RECENTLY),
        (r"(?<![\d/.$,])\b(?:1[0-2]|0?[1-9])/(?:1[3-9]|2\d|3[01])\b(?![\d/%])", RECENTLY),
        (r"(?<![\d/.$,])\b(?:0[1-9]/(?:[0-2]\d|3[01])|1[0-2]/0[1-9])\b(?![\d/%])", RECENTLY),  # zero padding
        (rf"{PREP}\b(?:1[0-2]|0?[1-9])/(?:[12]?\d|3[01])\b(?![\d/%])", RECENTLY),
        (rf"{PREP}?\b(?:{WEEKDAY},?\s+)?{MONTH_ANY}\s+{DAY}(?!\d)(?:,?\s*{YEAR_RE}\b)?", RECENTLY),
        (
            rf"{PREP}?\b(?:{WEEKDAY},?\s+)?(?:the\s+)?{DAY}\s+(?:of\s+)?{MONTH_ANY}(?:,?\s*{YEAR_RE}\b)?",
            RECENTLY,
        ),
        (
            rf"{_I}\b(?:the\s+)?(?:first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+(?:fiscal\s+)?quarter\s+(?:of\s+)?(?:fiscal\s+(?:year\s+)?)?(?:FY\s?)?'?(?:{YEAR_RE}|\d{{2}})\b",
            QUARTER,
        ),
        (
            rf"{_I}\b(?:the\s+)?(?:first|second|1st|2nd)[\s-]+half\s+(?:of\s+)?(?:the\s+)?(?:fiscal\s+)?(?:year\s+)?'?(?:{YEAR_RE}|\d{{2}})\b",
            HALF_YEAR,
        ),
        (rf"{_I}\b[12]H\s*'?(?:{YEAR_RE}|\d{{2}})\b", HALF_YEAR),
        (
            rf"{_I}\b(?:fiscal\s+)?Q[1-4]\s*(?:of\s+)?(?:fiscal\s+(?:year\s+)?)?(?:FY\s?|F)?'?(?:{YEAR_RE}|\d{{2}})\b",
            QUARTER,
        ),
        (rf"{_I}\b(?:fiscal\s+)?[1-4]Q\s*(?:FY)?'?(?:{YEAR_RE}|\d{{2}})\b", QUARTER),
        (rf"\b(?:fiscal\s+)?[Hh][12]\s*(?:FY)?'?(?:{YEAR_RE}|\d{{2}})\b", HALF_YEAR),
        (rf"{_I}\b(?:fiscal\s+)?(?:Q[1-4]|[1-4]Q)\b", QUARTER),
        (rf"{_I}\b(?:first|second|third|fourth|1st|2nd|3rd|4th)-quarter\b", "quarterly"),
        (
            rf"{_I}\b(?:the\s+)?(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+(?:fiscal\s+)?quarter\b",
            QUARTER,
        ),
        (rf"{_I}\b(?:first|second|1st|2nd)-half\b", "half-year"),
        (
            rf"{_I}\b(?:the\s+)?(?:first|second|1st|2nd)\s+half\s+of\s+(?:the\s+)?(?:fiscal\s+)?year\b",
            HALF_YEAR,
        ),
        (rf"{_I}\b(?:the\s+)?(?:first|second|1st|2nd)\s+(?:fiscal\s+)?half\b", HALF_YEAR),
        (rf"\b(?:the\s+)?fiscal\s+(?:year\s+)?'?(?:{YEAR_RE}|\d{{2}})\b", FISCAL_YEAR),
        (rf"{_I}\bFY\s?'?(?:{YEAR_RE}|\d{{2}})\b", FISCAL_YEAR),
        (rf"\b{YEAR_RE}\s*[-–/]\s*(?:{YEAR_RE}|\d{{2}})\b", "the period"),
        (rf"{PREP}?\b(?:early|mid|late)[\s-]+{MONTH_ANY}(?:\s+(?:of\s+)?{YEAR_RE}\b)?", RECENTLY),
        (rf"{PREP}?\b{MONTH_ANY}\s+(?:of\s+)?{YEAR_RE}", RECENTLY),
        (rf"{_I}\bfull[\s-]year\s+{YEAR_RE}\b", "full-year"),
        (rf"\b(?:early|mid|late)[\s-]+{YEAR_RE}\b", YEAR),
        (rf"\bsince\s+{YEAR_RE}\b", "for years"),
        (rf"(?<!\d[.,])(?<![\w$€£¥])(?<!Russell\s){YEAR_RE}(?!\d|[%,.]\d|\s?%)", YEAR),
        (rf"{PREP}?\b(?:early|mid|late)[\s-]+{MONTH}\b", RECENTLY),
        (rf"(?:{PREP}|\b(?:last|this|next|early|late)\s+){MONTH}\b", RECENTLY),
        (
            r"\b(?:January|February|March|April|June|July|August|September|October|November|December|JANUARY|"
            r"FEBRUARY|MARCH|APRIL|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b",
            "recent",
        ),
        (rf"{_I}(?:{PREP})?\b{WEEKDAY}\s+(?:night|morning|afternoon|evening)\b", RECENTLY),
        (rf"{_I}(?:\bon\s+)?\b{WEEKDAY}(?:'s|’s)", "the recent"),
        (rf"{_I}(?:{PREP}|\b(?:last|this|next|early|late)\s+){WEEKDAY}s?\b", RECENTLY),
        (rf"{_I}\b{WEEKDAY}s?\b", RECENTLY),
    )
)


class Masker:
    """Masks title / snippet text of one company's articles (module docstring)."""

    def __init__(
        self,
        aliases: Mapping[int, CompanyAliases],
        cfg: AliasConfig | None = None,
        nlp: Any = None,
        vocabulary: frozenset[str] = frozenset(),
        surnames: frozenset[str] | None = None,
    ) -> None:
        """``vocabulary``: ordinary lower-case words (``lowercase_vocabulary``); a PERSON entity made only of
        such words ("Balance Sheet", "Soar") is not a name unless a role noun or a speech verb frames it.
        ``surnames``: corpus surnames masked wherever they appear; None derives them in ``mask_texts``."""
        self.cfg = load_alias_config() if cfg is None else cfg
        self.vocabulary = vocabulary
        self._derive_surnames = surnames is None
        self.surnames: frozenset[str] = frozenset() if surnames is None else surnames
        self.aliases = aliases
        self._nlp = nlp
        self._patterns: dict[int, CompanyPatterns] = {}
        every = {n.lower() for a in aliases.values() for n in a.names} | {
            t.lower() for a in aliases.values() for t in a.tickers
        }
        self._all_names = frozenset(every)
        self._alias_words = frozenset(
            w.lower() for a in aliases.values() for n in a.names for w in re.findall(r"[A-Za-z]+", n)
        )
        self._detector = load_detector()

    # --- company -----------------------------------------------------------------------------------

    def patterns(self, company_id: int) -> CompanyPatterns:
        pat = self._patterns.get(company_id)
        if pat is not None:
            return pat
        a = self.aliases.get(company_id)
        if a is None:
            pat = CompanyPatterns(None, None, None, None, None, None)
        else:
            loose, strict = split_names(a, self.cfg)
            suffix = "|".join(re.escape(s).rstrip(r"\.") + r"\.?" for s in self.cfg.legal_suffixes)

            def names_re(words: list[str], flags: int) -> re.Pattern[str] | None:
                if not words:
                    return None
                alt = "|".join(phrase_regex(v) for v in words)
                return re.compile(
                    rf"(?<![A-Za-z0-9&])(?:[Tt]he\s+)?(?:{alt})(?:,?\s+(?:{suffix}))*(?![A-Za-z0-9&])", flags
                )

            tick = "|".join(ticker_regex(t) for t in a.tickers)
            bare = [t for t in a.tickers if len(t) >= 2 and t not in self.cfg.bare_ticker_stoplist]
            stop = [t for t in a.tickers if t in self.cfg.bare_ticker_stoplist or len(t) < 2]
            exch = rf"(?:{EXCH_PREFIX})?\$?"
            bare_alts = []  # bare tickers; a stoplisted (English-word) ticker only as a possessive ("NOW's")
            if bare:
                bare_alts.append(
                    rf"(?<![A-Za-z0-9$&.\-/])(?:{'|'.join(map(ticker_regex, bare))}){TICKER_SUFFIX}"
                    rf"(?![A-Za-z0-9&]|/[A-Z]{{1,2}}\b|-[A-Z]\b|-\d)"
                )
            if stop:
                bare_alts.append(rf"(?<![A-Za-z0-9$&.\-/])(?:{'|'.join(map(ticker_regex, stop))})(?=['’]s\b)")
            pat = CompanyPatterns(
                names=names_re(loose, re.IGNORECASE),
                names_strict=names_re(strict, 0),
                stock_ticker=re.compile(
                    rf"(?<![A-Za-z0-9$&.\-/])(?:{tick})(?=\s+(?:[Ss]tock|[Ss]hares|[Oo]ptions)\b(?!\s+[Mm]arket))"
                )
                if tick
                else None,
                paren_ticker=re.compile(
                    rf"\s*\(\s*{exch}(?:{tick})(?:\.[A-Z]{{1,2}})?(?!-\d)(?=[\s,;:)–—.\-+/]|$)[^()]{{0,40}}(?:\)|$)"
                )
                if tick
                else None,
                prefixed_ticker=re.compile(
                    rf"(?:{EXCH_PREFIX}\$?|\$)(?:{tick}){TICKER_SUFFIX}(?![A-Za-z0-9])"
                )
                if tick
                else None,
                bare_ticker=re.compile("|".join(bare_alts)) if bare_alts else None,
            )
        self._patterns[company_id] = pat
        return pat

    def _replace(self, pattern: re.Pattern[str] | None, text: str, word: str) -> tuple[str, int]:
        if pattern is None:
            return text, 0

        def repl(m: re.Match[str]) -> str:
            return _cap(word, text[: m.start()])

        return pattern.subn(repl, text)

    def mask_company(self, text: str, company_id: int) -> tuple[str, MaskCounts]:
        c = MaskCounts()
        pat = self.patterns(company_id)
        if pat.paren_ticker is not None:
            text, n = pat.paren_ticker.subn("", text)
            c.tickers += n
        for p in (pat.prefixed_ticker, pat.stock_ticker):
            text, n = self._replace(p, text, COMPANY)
            c.tickers += n
        for p in (pat.names, pat.names_strict):
            text, n = self._replace(p, text, COMPANY)
            c.names += n
        text, n = self._replace(pat.bare_ticker, text, COMPANY)
        c.tickers += n
        return text, c

    # --- dates -------------------------------------------------------------------------------------

    def mask_lead(self, text: str) -> tuple[str, int]:
        """Step 1: HTML entities decoded ("Microsoft&nbsp;" → "Microsoft "), then datelines and ISIN codes."""
        text = _NBSP.sub(" ", html.unescape(text))
        total = 0
        for p in (_DATELINE, _WIRE_DATELINE, _ISIN, _EMAIL_URL):
            text, n = p.subn("", text)
            total += n
        return text, total

    def mask_dates(self, text: str) -> tuple[str, int]:
        """Step 3: dates, weekdays, months, years, fiscal periods."""
        total = 0
        for pattern, word in _DATE_RULES:
            text, n = self._replace(pattern, text, word)
            total += n
        return text, total

    # --- people ------------------------------------------------------------------------------------

    @property
    def nlp(self) -> Any:
        if self._nlp is None:
            self._nlp = load_spacy()
        return self._nlp

    def _persons(self, doc: Any) -> list[Candidate]:
        """PERSON entities that are not a company alias: (start, end, words without a possessive)."""
        out: list[Candidate] = []
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            t = ent.text.strip()
            low = t.lower()
            if not t or low in self._all_names or COMPANY in low or re.search(r"\d", t) or low in _NOT_PEOPLE:
                continue
            words = [w.text for w in ent if w.text not in ("'s", "’s")]
            if not words:
                continue
            after = doc.text[ent.end_char : ent.end_char + 20]
            if len(words) == 1 and _ROLE_AFTER.match(after):
                continue  # "Masimo CEO": an organization before a title, not a person
            out.append((ent.start_char, ent.end_char, words))
        return out

    def _namelike(self, words: Sequence[str]) -> bool:
        return any(w.lower() not in self.vocabulary for w in words)

    def corpus_surnames(
        self,
        candidates: Iterable[Sequence[Candidate]],
        foreign: Sequence[bool] | None = None,
        other_entities: Mapping[str, int] | None = None,
    ) -> frozenset[str]:
        """Last words of multi-word names in English texts seen at least ``SURNAME_MIN_COUNT`` times:
        capitalized, 3+ ASCII letters, not an ordinary lower-case word, not a word of any company alias, and
        tagged inside an organization / product / place entity less than half as often as it ends a name
        ("Powell" from "Jerome Powell"; not "Oppenheimer", a broker spaCy sometimes tags as a person)."""
        counts: dict[str, int] = {}
        for k, cands in enumerate(candidates):
            if foreign is not None and foreign[k]:
                continue
            for _, _, words in cands:
                if len(words) >= 2 and self._namelike(words):
                    last = words[-1]
                    counts[last] = counts.get(last, 0) + 1
        other = other_entities or {}
        return frozenset(
            w
            for w, n in counts.items()
            if n >= SURNAME_MIN_COUNT
            and len(w) >= 3
            and w[:1].isupper()
            and w.isascii()
            and w.isalpha()
            and w.lower() not in self.vocabulary
            and w.lower() not in self._alias_words
            and other.get(w, 0) * 2 < n
        )

    def _person_spans(
        self,
        text: str,
        candidates: Sequence[Candidate],
        surnames: frozenset[str] = frozenset(),
        *,
        foreign: bool = False,
    ) -> list[tuple[int, int]]:
        """Names of two or more words; a one-word name only if it is a known surname (of a longer name in the
        same article, or ``self.surnames`` from the corpus), follows a role noun, or precedes a speech verb
        (title-case headline words such as "Buy" or "Soar" are often tagged PERSON). In a text that looks
        non-English (``foreign``) only names of two or more capitalized words count: the English model tags
        many foreign words as PERSON. Every capitalized occurrence of a known surname is a name too."""
        known = surnames | self.surnames | self.cfg.person_names
        spans: list[tuple[int, int]] = []
        for start, end, words in candidates:
            if foreign:
                if len(words) >= 2 and all(w[:1].isupper() for w in words):
                    spans.append((start, end))
                continue
            framed = bool(_ROLE_BEFORE.search(text[:start]) or _SPEECH_AFTER.match(text[end : end + 30]))
            if framed or (self._namelike(words) and (len(words) >= 2 or words[0] in known)):
                spans.append((start, end))
        for m in _CAP_WORD.finditer(text):  # a surname NER missed: "Elon Musk ... Musk added", "Trump" alone
            name = m.group("w")
            usable = name in self.cfg.person_names or (len(name) >= 3 and name.lower() not in self.vocabulary)
            if name in known and usable and not any(s < m.end() and m.start() < e for s, e in spans):
                spans.append(m.span())
        return sorted(spans)

    def mask_persons(
        self, text: str, candidates: Sequence[Candidate], surnames: frozenset[str] = frozenset()
    ) -> tuple[str, int]:
        spans = self._person_spans(text, candidates, surnames, foreign=self._detector.non_english(text))
        out, pos, n = [], 0, 0
        for start, end in spans:
            if start < pos:
                continue
            before = text[:start]
            if _ROLE_BEFORE.search(before):
                out.append(text[pos:start].rstrip(" ,"))
                out.append("")
            else:
                window = " ".join(
                    [*text[max(0, start - 80) : start].split()[-6:], *text[end : end + 80].split()[:6]]
                )
                word = EXECUTIVE if EXEC_TITLES.search(window) else PERSON
                out.append(text[pos:start])
                out.append(_cap(word, before))
            if text[start:end].endswith(("'s", "’s")) and not _ROLE_BEFORE.search(before):
                out.append(text[end - 2 : end])
            pos = end
            n += 1
        out.append(text[pos:])
        return "".join(out), n

    # --- price talk and price levels ---------------------------------------------------------------

    @staticmethod
    def _relative(label: str, mid: str, old: str, new: str) -> str:
        a, b = float(old.replace(",", "")), float(new.replace(",", ""))
        if a <= 0 or b == a:
            change = "unchanged" if b == a else ""
        else:
            pct = (b / a - 1.0) * 100.0
            change = (
                ("raised slightly" if pct > 0 else "lowered slightly")
                if abs(pct) < 1
                else f"{'raised' if pct > 0 else 'lowered'} by about {round(abs(pct))}%"
            )
        return f"{label}{mid.rstrip()} {change}".rstrip()

    @staticmethod
    def is_price_move(sentence: str) -> bool:
        """A stock / share price move in percent: any subject occurrence whose stretch to the move verb holds
        no fundamental noun ("Earnings Disappoint, Shares Fall 8.3%" is a move; "revenue rose 5%" is not)."""
        if PRICE_MOVE_AFTER.search(sentence):
            return True
        for sm in _MOVE_SUBJECT.finditer(sentence):
            m = PRICE_MOVE.match(sentence, sm.start())
            if m and not _FUNDAMENTAL_SUBJECT.search(m.group("mid") or ""):
                return True
        return False

    def mask_prices(self, text: str) -> tuple[str, int]:
        """Step 5b: drop ticker quotes and price-move sentences; remove price-target and deal-price levels."""
        n = 0
        text, k = QUOTE.subn("", text)
        n += k
        for sentence in split_sentences(text):
            if self.is_price_move(sentence):
                text = text.replace(sentence, "", 1)
                n += 1
        text = _SEP_RUN.sub(lambda m: m.group(1) + " ", text).strip(" ;|")
        text, k = PT_FROM_TO.subn(
            lambda m: self._relative(m["label"], m["mid"], m.group(3), m.group(4)), text
        )
        n += k
        text, k = PT_TO_FROM.subn(
            lambda m: self._relative(m["label"], m["mid"], m.group(4), m.group(3)), text
        )
        n += k
        for _ in range(3):
            text, k = PT_AMOUNT.subn(lambda m: f"{m['label']}{m['mid'].rstrip()}", text)
            n += k
            if not k:
                break
        text, k = AMOUNT_PT.subn(lambda m: m["label"], text)
        n += k

        def deal(m: re.Match[str]) -> str:
            left = text[max(0, m.start() - 80) : m.start()]
            return "a per-share price" if _DEAL.search(left) and not _FUND_LEFT.search(left) else m.group(0)

        text, k = PER_SHARE.subn(deal, text)
        return text, n

    # --- one text ----------------------------------------------------------------------------------

    def pre_ner(self, text: str, company_id: int | None, *, is_title: bool) -> tuple[str, MaskCounts]:
        """Steps 1–3 (no spaCy)."""
        c = MaskCounts()
        text, n = self.mask_lead(text)
        c.dates += n
        if company_id is not None:
            text, cc = self.mask_company(text, company_id)
            c.add(cc)
        text, n = self.mask_dates(text)
        c.dates += n
        return text, c

    def post_ner(
        self, text: str, candidates: Sequence[Candidate], surnames: frozenset[str] = frozenset()
    ) -> tuple[str, int]:
        """Steps 4–5."""
        text, n = self.mask_persons(text, candidates, surnames)
        text = self._detector.scrub(_tidy(text))
        text, _ = self.mask_prices(text)
        return _tidy(text), n

    def mask_texts(
        self,
        items: Sequence[tuple[str, int | None, bool]],
        *,
        groups: Sequence[object] | None = None,
        n_process: int = 1,
        batch_size: int = 256,
    ) -> list[tuple[str, MaskCounts]]:
        """Mask many (text, company_id, is_title) items; spaCy runs once over all pre-masked texts.

        ``groups`` (one label per item; items of a group are consecutive, e.g. an article's title and snippet)
        lets a surname alone count as a person when the full name appears elsewhere in the group. Without
        ``surnames`` at construction, the corpus surnames are derived from these items (``corpus_surnames``)
        and kept in ``self.surnames``.
        """
        pre = [self.pre_ner(t, cid, is_title=title) for t, cid, title in items]
        labels = list(range(len(items))) if groups is None else list(groups)
        docs = self.nlp.pipe([p[0] for p in pre], batch_size=batch_size, n_process=n_process)
        cands: list[list[Candidate]] = []
        other: dict[str, int] = {}
        for d in docs:
            cands.append(self._persons(d))
            for ent in d.ents:
                if ent.label_ in _NON_PERSON_LABELS:
                    for w in ent:
                        other[w.text] = other.get(w.text, 0) + 1
        if self._derive_surnames:
            foreign = [self._detector.non_english(p[0]) for p in pre]
            self.surnames = self.corpus_surnames(cands, foreign, other)
        out: list[tuple[str, MaskCounts]] = []
        i = 0
        while i < len(pre):
            j = i + 1
            while j < len(pre) and labels[j] == labels[i]:
                j += 1
            local = frozenset(w[-1] for c in cands[i:j] for _, _, w in c if len(w) >= 2 and self._namelike(w))
            for (text, counts), c in zip(pre[i:j], cands[i:j], strict=True):
                masked, n = self.post_ner(text, c, local)
                counts.persons += n
                out.append((masked, counts))
            i = j
        return out

    def mask(self, text: str, company_id: int | None, *, is_title: bool = False) -> str:
        return self.mask_texts([(text, company_id, is_title)])[0][0]


@functools.cache
def load_spacy() -> Any:
    """``en_core_web_sm`` with only the NER pipe (pinned in pyproject.toml)."""
    import spacy

    return spacy.load(SPACY_MODEL, exclude=list(SPACY_EXCLUDE))
