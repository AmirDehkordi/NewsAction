"""PRD NA-02 S5: after-the-fact / price-path and pre-market price-talk detectors; ``scrub`` (PREREG §6.3–6.4).

Detectors work on sentences of title + snippet (the title is split like the snippet). A sentence is
- ``after_fact`` if it describes a price move or level of a stock or the market: a stock subject with a
  move verb, a move with a same-session time phrase ("in early trading", "at last check"), closed /
  opened up or down, "as of 10:30", "trading higher", gaps, moving-average crosses, new 52-week highs,
  "<word> jumps 5%" when none of the six preceding words is a fundamental noun ("revenue jumps 5%" is not
  price talk) and no comparison period follows ("a 5% drop from the previous year");
- ``premarket`` if it has a pre-market / after-hours / extended-trading phrase **and** price content in
  the same sentence (a move, up/down, a percent, a dollar amount, "movers", "futures"). "Reports before
  the bell on Thursday" is scheduling, not price talk.

``scrub(text)`` drops every flagged sentence (``keep_premarket=True`` keeps pre-market talk for Call B's
reaction context) and removes share-price levels from the rest ("$123.45 a share", "trading at $45").
Price targets and per-share fundamentals (EPS, dividends, deal prices) are kept.

Patterns live in ``configs/patterns.yaml``; ``{NAME}`` placeholders are expanded from ``fragments``.
"""

from __future__ import annotations

import functools
import multiprocessing as mp
import os
import re
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

import pandas as pd

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS

PATTERNS_PATH: Final = CONFIGS / "patterns.yaml"
_FLAGS: Final = re.IGNORECASE
_PLACEHOLDER: Final = re.compile(r"\{([A-Z_]+)\}")
_LEFT_WORDS: Final = 6
_RIGHT_WORDS: Final = 4
_PARALLEL_MIN: Final = 20_000

# sentence boundaries: end punctuation (+ closing quotes) then space, or explicit separators
# a final token like "Inc." or "U.S." or "W." does not end a sentence
_ABBREV: Final = re.compile(
    r"\b(?:inc|corp|co|cos|ltd|llc|plc|lp|mr|mrs|ms|dr|st|jr|sr|no|nos|vs|etc|approx|est|dept|govt|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"ft|mt|gen|gov|sen|rep|rev|prof|fig|vol|[a-z])\.$",
    re.IGNORECASE,
)
# end punctuation (+ closing quotes) then whitespace before a capital, digit or "$"; or ; | • ** separators
_BOUNDARY: Final = re.compile(
    r"(?<=[.!?…])(?P<close>[\"'”’)\]]*)\s+(?=[\"'“‘(\[]?[A-Z0-9$])|(?P<sep>\s*(?:;|\s\|\s|•|\*\*)\s*)"
)


class Flags(NamedTuple):
    after_fact: bool
    premarket: bool


def _pieces(text: str) -> list[tuple[str, str]]:
    """(sentence, separator that follows it) in order; separators keep the original text."""
    out: list[tuple[str, str]] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        if m.group("sep") is None:
            end = m.start() + len(m.group("close"))
            words = text[start:end].split()
            if words and _ABBREV.search(words[-1].rstrip("\"'”’)]")):
                continue
        else:
            end = m.start()
        piece = text[start:end].strip()
        if piece:
            out.append((piece, text[end : m.end()]))
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append((tail, ""))
    return out


def split_sentences(text: str) -> list[str]:
    """Sentences of ``text``; abbreviations (Inc., U.S., Jan.) and decimals do not end a sentence."""
    return [s for s, _ in _pieces(text)]


def _expand(rule: str, fragments: dict[str, str], depth: int = 0) -> str:
    if depth > 5:
        raise ValueError("fragment expansion is nested too deeply")

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in fragments:
            raise ValueError(f"unknown fragment {{{name}}}")
        return f"(?:{_expand(fragments[name], fragments, depth + 1)})"

    return _PLACEHOLDER.sub(sub, rule)


@dataclass(frozen=True)
class Detector:
    after_fact: tuple[tuple[re.Pattern[str], ...], ...]  # each rule: all of its patterns must match
    pct_move: re.Pattern[str]
    pct_noun: re.Pattern[str]
    fundamental: re.Pattern[str]
    fundamental_right: re.Pattern[str]
    premarket_ctx: re.Pattern[str]
    premarket_price: re.Pattern[str]
    price_level: tuple[re.Pattern[str], ...]
    price_level_keep: re.Pattern[str]
    non_english_script: re.Pattern[str]
    non_english_words: re.Pattern[str]
    non_english_min_words: int

    # --- sentence level ---------------------------------------------------------------------------

    def _pct_move(self, sentence: str) -> bool:
        for m in self.pct_move.finditer(sentence):
            left = " ".join(sentence[: m.start()].split()[-_LEFT_WORDS:])
            right = " ".join(sentence[m.end() :].split()[: _RIGHT_WORDS + 4])
            if not self.fundamental.search(left) and not self.fundamental_right.search(right):
                return True
        for m in self.pct_noun.finditer(sentence):
            left = " ".join(sentence[: m.start()].split()[-_LEFT_WORDS:])
            right = " ".join(sentence[m.end() :].split()[: _RIGHT_WORDS + 4])
            if not self.fundamental.search(left) and not (
                self.fundamental.search(" ".join(right.split()[:_RIGHT_WORDS]))
                or self.fundamental_right.search(right)
            ):
                return True
        return False

    def is_after_fact(self, sentence: str) -> bool:
        return any(all(p.search(sentence) for p in rule) for rule in self.after_fact) or self._pct_move(
            sentence
        )

    def is_premarket(self, sentence: str) -> bool:
        return bool(self.premarket_ctx.search(sentence) and self.premarket_price.search(sentence))

    def non_english(self, text: str) -> bool:
        """Heuristic: a non-Latin script character or >= min_words non-English function words."""
        if self.non_english_script.search(text):
            return True
        return len(self.non_english_words.findall(text)) >= self.non_english_min_words

    def flags(self, sentence: str) -> Flags:
        return Flags(self.is_after_fact(sentence), self.is_premarket(sentence))

    # --- text level -------------------------------------------------------------------------------

    def detect(self, text: str) -> Flags:
        """Article-level flags: any sentence after-the-fact / any sentence pre-market price talk."""
        af = pm = False
        for s in split_sentences(text):
            f = self.flags(s)
            af, pm = af or f.after_fact, pm or f.premarket
            if af and pm:
                break
        return Flags(af, pm)

    def remove_price_levels(self, sentence: str) -> str:
        """Drop share-price levels from one sentence; per-share fundamentals and price targets stay."""

        def drop_amount(m: re.Match[str]) -> str:
            left = sentence[max(0, m.start() - 60) : m.start()] + m.group(0)
            if self.price_level_keep.search(left):
                return m.group(0)
            amount = re.search(r"\$\d[\d,]*(?:\.\d+)?", m.group(0))
            if amount is None:
                return m.group(0)
            head = m.group(0)[: amount.start()]
            return re.sub(r"\s+(?:at|near|around|about|of)\s*$", "", head, flags=_FLAGS).rstrip()

        out = sentence
        for p in self.price_level:
            out = p.sub(drop_amount, out)
        return re.sub(r"\s{2,}", " ", out).strip()

    def analyze(self, text: str, *, keep_premarket: bool = False) -> tuple[Flags, str]:
        """Article-level flags of ``text`` and its scrubbed version, in one pass over the sentences."""
        af = pm = False
        kept: list[tuple[str, str]] = []
        for sentence, sep in _pieces(text):
            f = self.flags(sentence)
            af, pm = af or f.after_fact, pm or f.premarket
            if f.after_fact or (f.premarket and not keep_premarket):
                continue
            kept.append((self.remove_price_levels(sentence), sep))
        if not kept:
            return Flags(af, pm), ""
        body = "".join(s + (sep if sep.strip() else " ") for s, sep in kept[:-1]) + kept[-1][0]
        return Flags(af, pm), re.sub(r"\s{2,}", " ", body).strip()

    def scrub(self, text: str, *, keep_premarket: bool = False) -> str:
        """``text`` without after-the-fact sentences, pre-market talk (unless kept) and price levels."""
        return self.analyze(text, keep_premarket=keep_premarket)[1]


def _compile(rule: str, fragments: dict[str, str]) -> re.Pattern[str]:
    return re.compile(_expand(rule, fragments), _FLAGS)


@functools.cache
def _load(path: Path, mtime_ns: int) -> Detector:
    raw = load_yaml(path)
    frag = {str(k): str(v) for k, v in raw["fragments"].items()}
    return Detector(
        after_fact=tuple(
            tuple(_compile(p, frag) for p in (rule if isinstance(rule, list) else [rule]))
            for rule in raw["after_fact"]
        ),
        pct_move=_compile(raw["pct_move"], frag),
        pct_noun=_compile(raw["pct_noun"], frag),
        fundamental=_compile("{FUNDAMENTAL}", frag),
        fundamental_right=_compile("{FUND_RIGHT}", frag),
        premarket_ctx=_compile("{PREMARKET}", frag),
        premarket_price=_compile("{PM_PRICE}", frag),
        price_level=tuple(_compile(r, frag) for r in raw["price_level"]),
        price_level_keep=_compile(raw["price_level_keep"], frag),
        non_english_script=re.compile(raw["non_english"]["script"]),
        non_english_words=re.compile(raw["non_english"]["words"], _FLAGS),
        non_english_min_words=int(raw["non_english"]["min_words"]),
    )


def load_detector(path: Path = PATTERNS_PATH) -> Detector:
    """The detector compiled from ``configs/patterns.yaml`` (reloaded when the file changes)."""
    return _load(path, path.stat().st_mtime_ns)


def detect(text: str) -> Flags:
    return load_detector().detect(text)


def scrub(text: str, *, keep_premarket: bool = False) -> str:
    return load_detector().scrub(text, keep_premarket=keep_premarket)


def _str(x: object) -> str:
    return "" if x is None or (isinstance(x, float) and x != x) or x is pd.NA else str(x)


def non_english_hint(titles: Iterable[object], snippets: Iterable[object]) -> pd.Series:
    """Per article: title + snippet look non-English (the detectors and NA-04 masking are English-only)."""
    det = load_detector()
    return pd.Series(
        [det.non_english(f"{_str(t)} {_str(s)}") for t, s in zip(titles, snippets, strict=True)], dtype=bool
    )


def _analyze_pairs(pairs: list[tuple[str, str]]) -> list[tuple[bool, bool, str, str]]:
    det = load_detector()
    out = []
    for title, snippet in pairs:
        ft, tc = det.analyze(title)
        fs, sc = det.analyze(snippet)
        out.append((ft.after_fact or fs.after_fact, ft.premarket or fs.premarket, tc, sc))
    return out


def detect_articles(
    titles: Iterable[object], snippets: Iterable[object], *, processes: int | None = None
) -> pd.DataFrame:
    """Per article: after_fact, premarket_talk (title or snippet), title_clean, snippet_clean.

    Inputs above ``_PARALLEL_MIN`` rows are split over a process pool (deterministic: order is kept).
    The pool uses ``spawn``: a calling script must guard its entry point with ``if __name__ == "__main__"``,
    or every worker re-runs it.
    """
    pairs = [(_str(t), _str(s)) for t, s in zip(titles, snippets, strict=True)]
    workers = processes if processes is not None else min(6, max(1, (os.cpu_count() or 2) // 2))
    if len(pairs) < _PARALLEL_MIN or workers <= 1:
        rows = _analyze_pairs(pairs)
    else:
        size = -(-len(pairs) // (workers * 8))
        chunks = [pairs[i : i + size] for i in range(0, len(pairs), size)]
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
            rows = [r for part in pool.map(_analyze_pairs, chunks) for r in part]
    return pd.DataFrame(rows, columns=["after_fact", "premarket_talk", "title_clean", "snippet_clean"])
