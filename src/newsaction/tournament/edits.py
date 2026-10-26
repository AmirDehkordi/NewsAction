"""Counterfactual edits of probe c (PREREG §8.3; PRD NA-06 S4c): flip the factual outcome of a state's news by
rule and change nothing else.

**Outcome phrases.** The PRD's four families (PREREG §8.3's "raise↔cut" included), every inflection, case kept
("Beats" → "Misses"):

| family | positive | negative |
|---|---|---|
| ``beat`` | beat (→ missed; a noun or after "to" → miss), beats, beating | missed, misses, missing, miss |
| ``guidance`` | raises, raised, raising (→ lower…) | lowers, lowered, lowering, cuts, cut, cutting |
| ``rating`` | upgrade, upgrades, upgraded, upgrading | downgrade, downgrades, downgraded, downgrading |
| ``expectations`` | above + expectations / estimates / consensus / forecast(s) / views | below + … |

A family word is an outcome phrase only in its context: ``beat`` needs an earnings or expectations word within
6 words (estimates, expectations, consensus, forecast, views, Street, EPS, earnings, revenue, sales, profit,
results, quarter, …), ``guidance`` a guidance noun (guidance, outlook, forecast, view, projection) within 5
words after the verb (4 after "cut") or within 3 words before a participle ("Guidance Raised"), ``rating`` a
rating or analyst word in the sentence. "On the beat", "don't miss", "upgrade to the newest version" are not
outcomes.

**Companions**, flipped with the phrases so that an edited item stays coherent (never enough on their own):
- a rating ladder in a rating sentence, "from <R1> to <R2>" or "to <R1> from <R2>", has its ratings swapped,
  with "a" / "an" fixed: "Downgrades the company to Neutral From Buy" → "Upgrades the company to Buy From
  Neutral";
- NA-04's price-target rewrite "raised by about N%" ↔ "lowered by about N%" (``states.mask``).

**A state is editable** when every check holds (``EditResult.reason`` names the first that fails):
1. ``other_subject``: the outcome is the company's: "the company" (NA-04's mask of the company's own names) is
   in the phrase's sentence, before a beat / guidance / expectations phrase (its subject: not "T-Mobile dials
   up a big earnings beat as it bests the company") and anywhere for a rating phrase except as the broker
   ("analysts at the company", "by the company");
2. ``forward_looking``: no outcome phrase is in a question or a forward-looking sentence ("Will the company
   Beat Estimates Again?", "expected to beat", "could", "ahead of", "preview", …);
3. ``uncovered_cue``: no item that mentions the company holds an outcome cue these rules do not flip
   ("topped", "surpassing", "exceeded", "fell short", "lags", "disappointing", "better-than-expected", "in
   line", "beat and raise"; a rating "raised to" / "cut to" a level, a rating ladder outside a rating
   sentence, a "from <rating>" outside a full ladder; guidance "cut", "hiked", "boosted"; a price target or
   objective "increased", "boosted" or "higher" outside NA-04's template; a stock move left by masking,
   "Shares Rise"), which would contradict the edit;
4. ``bare_rating``: a rating sentence names no target rating outside a full ladder ("Upgraded to Hold": the
   flipped item could not say which rating it came from), nor a moat, outlook or credit-rating target ("to
   wide", "to positive", "to BBB+");
5. ``numbers``: an edited sentence, and any sentence of the item with an expectations word, holds at most
   one number besides "by <amount>" magnitudes ("EPS $1.20 vs $1.10 estimate" cannot be flipped by words);
6. ``mixed``: every phrase and companion points the same way;
7. ``no_phrase``: at least one phrase of the four families.

Only the replaced words of the ``news`` headlines and snippets differ between the original and the edited
state (tests/test_tournament_edits.py).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

COMPANY: Final = re.compile(r"\bthe company\b", re.IGNORECASE)
FIELDS: Final = ("headline", "snippet")
_TOKEN: Final = re.compile(r"[A-Za-z][A-Za-z'’-]*|\d[\d,.]*")
_SENTENCE_END: Final = re.compile(r"(?<=[.!?…])\s+(?=[A-Z\"“'‘(\[])|\s+\|\s+")

EXPECT_WORDS: Final = frozenset(
    {
        "estimate", "estimates", "expectation", "expectations", "consensus", "forecast", "forecasts", "views",
        "street", "est", "eps", "earnings", "revenue", "revenues", "sales", "profit", "profits", "results",
        "quarter", "quarterly", "top-line", "bottom-line", "guidance", "outlook", "targets",
    }
)  # fmt: skip
GUIDANCE_NOUNS: Final = frozenset(
    {"guidance", "outlook", "forecast", "forecasts", "view", "projection", "projections"}
)
RATING_LEVELS: Final = (
    "strong buy",
    "strong-buy",
    "strong sell",
    "strong-sell",
    "market outperform",
    "sector outperform",
    "market perform",
    "sector perform",
    "peer perform",
    "equal weight",
    "equal-weight",
    "equalweight",
    "in-line",
    "in line",
    "outperform",
    "underperform",
    "overweight",
    "underweight",
    "neutral",
    "hold",
    "sell",
    "buy",
)
RATING_CONTEXT: Final = frozenset(
    {
        "rating", "ratings", "rated", "analyst", "analysts", "estimate", "estimates", "forecast", "forecasts",
        "target", "targets", "outlook",
    }
)  # fmt: skip
_RATING: Final = "|".join(re.escape(r).replace(r"\ ", r"[ -]") for r in RATING_LEVELS)
_Q_OPEN: Final = "[\"“'‘]?"
_Q_CLOSE: Final = "[\"”'’]?"
_ART: Final = r"(?:(?P<{0}>an?|the)\s+)?"

BEAT_FORMS: Final = {
    "beat": ("missed", +1),
    "beats": ("misses", +1),
    "beating": ("missing", +1),
    "missed": ("beat", -1),
    "misses": ("beats", -1),
    "missing": ("beating", -1),
    "miss": ("beat", -1),
}
GUIDANCE_FORMS: Final = {
    "raises": ("lowers", +1),
    "raised": ("lowered", +1),
    "raising": ("lowering", +1),
    "lowers": ("raises", -1),
    "lowered": ("raised", -1),
    "lowering": ("raising", -1),
    "cuts": ("raises", -1),
    "cut": ("raised", -1),
    "cutting": ("raising", -1),
}
GUIDANCE_PARTICIPLES: Final = frozenset({"raised", "lowered", "cut"})
RATING_FORMS: Final = {
    "upgrade": ("downgrade", +1),
    "upgrades": ("downgrades", +1),
    "upgraded": ("downgraded", +1),
    "upgrading": ("downgrading", +1),
    "downgrade": ("upgrade", -1),
    "downgrades": ("upgrades", -1),
    "downgraded": ("upgraded", -1),
    "downgrading": ("upgrading", -1),
}
NOUN_BEFORE: Final = frozenset(
    {
        "a", "an", "the", "its", "their", "his", "her", "our", "earnings", "eps", "revenue", "sales",
        "profit", "double", "triple", "solid", "big", "huge", "strong", "slight", "narrow", "quarter",
        "quarterly", "modest", "major",
    }
)  # fmt: skip

BEAT_RE: Final = re.compile(r"\b(beat|beats|beating|missed|misses|missing|miss)\b", re.IGNORECASE)
BEAT_EXCLUDE: Final = re.compile(
    r"\b(?:don'?t|do not|never|can'?t|cannot|won'?t)\s+miss\b|\bmiss(?:ed|es|ing)?\s+out\b|\bpowerbeats\b|"
    r"\bbeats\s+(?:by|headphones|earbuds|pill|studio|solo|flex|fit|pro)\b|\bheart\s*beats?\b|\bon the beat\b",
    re.IGNORECASE,
)
GUIDANCE_RE: Final = re.compile(
    r"\b(raises|raised|raising|lowers|lowered|lowering|cuts|cut|cutting)\b", re.IGNORECASE
)
RATING_RE: Final = re.compile(
    r"\b(upgrade|upgrades|upgraded|upgrading|downgrade|downgrades|downgraded|downgrading)\b", re.IGNORECASE
)
EXPECTATIONS_RE: Final = re.compile(
    r"\b(above|below)(?=\s+(?:the\s+)?"
    r"(?:(?:analysts?['’]?|wall street(?:['’]s)?|street|consensus|market)\s+)?"
    r"(?:expectations?|estimates?|consensus|forecasts?|views)\b)",
    re.IGNORECASE,
)
PRICE_TARGET_RE: Final = re.compile(r"\b(raised|lowered)(?=\s+by\s+about\s+\d+(?:\.\d+)?%)", re.IGNORECASE)
LADDER_RE: Final = re.compile(
    rf"\b(?P<w1>from|to)\s+{_ART.format('a1')}(?P<q1>{_Q_OPEN})(?P<r1>{_RATING})(?P<c1>{_Q_CLOSE})"
    rf"(?P<rw1>\s+rating)?\s+(?P<w2>to|from)\s+{_ART.format('a2')}(?P<q2>{_Q_OPEN})(?P<r2>{_RATING})"
    rf"(?P<c2>{_Q_CLOSE})\b",
    re.IGNORECASE,
)
TO_RATING_RE: Final = re.compile(
    rf"\b(?:to|from|at|as)\s+(?:(?P<art>an?|the)\s+)?(?P<q>{_Q_OPEN})(?P<r>{_RATING}){_Q_CLOSE}(?![\w-])"
    r"(?P<rw>\s+rating)?",
    re.IGNORECASE,
)
FROM_RATING_RE: Final = re.compile(
    rf"\bfrom\s+(?:(?P<art>an?|the)\s+)?(?P<q>{_Q_OPEN})(?P<r>{_RATING}){_Q_CLOSE}(?![\w-])(?P<rw>\s+rating)?",
    re.IGNORECASE,
)
OTHER_TARGET_RE: Final = re.compile(
    r"\bto\s+[\"“'‘]?(?:wide|narrow|positive|negative|stable|developing|investment[- ]grade|junk|"
    r"(?:AAA|AA|A|BBB|BB|B|CCC|CC|Aaa|Aa|Baa|Ba|Caa)[123+-]?)(?![\w-])"
)
FORWARD_RE: Final = re.compile(
    r"\?\s*$|\b(?:will|would|could|can|may|might|should|expected|expects?|expecting|likely|poised|set to|"
    r"aims?|seeks?|hopes?|on track|potential|preview|previews|ahead of|upcoming|next|again|if|whether|"
    r"to beat|to miss|to raise|to lower|to upgrade|to downgrade)\b",
    re.IGNORECASE,
)
UNCOVERED_NEAR_EXPECT: Final = re.compile(
    r"\b(?:top|tops|topped|topping|surpass\w*|exceed\w*|outpac\w*|fell short|falls short|fall short|"
    r"falling short|short of|lag|lags|lagged|lagging|trail|trails|trailed|disappoint\w*|"
    r"better[- ]than[- ]expected|worse[- ]than[- ]expected|stronger[- ]than[- ]expected|"
    r"weaker[- ]than[- ]expected|softer[- ]than[- ]expected|in[- ]line|matched|matches|meets|crush\w*|"
    r"smash\w*|blew past|blowout|ahead of)\b",
    re.IGNORECASE,
)
STOCK_MOVE: Final = re.compile(
    r"\b(?:shares|stock)\s+(?:rise|rises|rose|rising|jump\w*|surg\w*|soar\w*|climb\w*|gain\w*|rall\w*|"
    r"fall|falls|fell|falling|drop\w*|slid\w*|slump\w*|plung\w*|sink\w*|sank|tumbl\w*|dip\w*|"
    r"declin\w*|slip\w*|sli[dp]e?s?)\b|\bholds?\s+gains\b",
    re.IGNORECASE,
)
BEAT_AND_RAISE: Final = re.compile(r"\b(?:beat|miss)[- ]and[- ](?:raise|cut|lower)\b", re.IGNORECASE)
UNCOVERED_RATING: Final = re.compile(
    rf"\b(?:rais\w*|lower\w*|cut\w*|lift\w*|boost\w*|mov\w*|ups|upped|hik\w*|trim\w*|reduc\w*|slash\w*|"
    rf"bump\w*|elevat\w*|initiat\w*|start\w*|resum\w*|assign\w*)\b(?:\W+\w+){{0,4}}?\W+to\s+"
    rf"(?:(?:an?|the)\s+)?{_Q_OPEN}(?:{_RATING}){_Q_CLOSE}(?![\w-])",
    re.IGNORECASE,
)
UNCOVERED_GUIDANCE: Final = re.compile(
    r"\b(?:slash\w*|hike\w*|boost\w*|lift\w*|trim\w*|reduc\w*|increas\w*|ups|upped|bump\w*|"
    r"withdr\w*|pull\w*|suspend\w*|improv\w*|weaken\w*|strengthen\w*)\b(?:\W+\w+){0,4}?\W+"
    r"(?:guidance|outlook|forecasts?)\b|\b(?:guidance|outlook|forecasts?)\b(?:\W+\w+){0,2}?\W+(?:slashed|"
    r"hiked|boosted|lifted|trimmed|reduced|increased|withdrawn|pulled|suspended|improved|weakened)\b",
    re.IGNORECASE,
)
UNCOVERED_PRICE_TARGET: Final = re.compile(
    r"\b(?:increas\w*|rais\w*|lift\w*|boost\w*|hik\w*|cut\w*|lower\w*|reduc\w*|trim\w*|slash\w*|bump\w*|"
    r"higher|lower)\b(?:\W+\w+){0,3}?\W+(?:price[- ]targets?|price ta\w*|price objectives?|target prices?|"
    r"pts?)\b",
    re.IGNORECASE,
)
ACTOR_BEFORE: Final = re.compile(r"\b(?:at|by)\s+$", re.IGNORECASE)
_BY_AMOUNT: Final = re.compile(
    r"\bby\s+(?:about\s+|approximately\s+|roughly\s+|nearly\s+|almost\s+|some\s+)?$", re.IGNORECASE
)
_NUMBER: Final = re.compile(r"(?<![\w.])[$€£¥]?\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Phrase:
    item: int
    field: str
    start: int
    end: int
    text: str
    replacement: str
    family: str  # beat | guidance | rating | expectations | ladder | price_target
    polarity: int  # +1 positive outcome, −1 negative, 0 for a ladder (it follows its rating phrase)


@dataclass(frozen=True)
class EditResult:
    ok: bool
    reason: str | None
    phrases: tuple[Phrase, ...]
    polarity: int  # the original outcome's direction (+1 / −1), 0 when not editable
    state: dict[str, Any] | None  # the edited state, None when not editable

    @property
    def families(self) -> list[str]:
        return sorted({p.family for p in self.phrases})


def match_case(src: str, dst: str) -> str:
    """``dst`` written in the case pattern of ``src`` (UPPER, Title, lower)."""
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) spans of the sentences of a headline or snippet."""
    out, last = [], 0
    for m in _SENTENCE_END.finditer(text):
        out.append((last, m.start()))
        last = m.end()
    out.append((last, len(text)))
    return [(a, b) for a, b in out if b > a]


def _sentence_of(spans: Sequence[tuple[int, int]], pos: int) -> tuple[int, int]:
    for a, b in spans:
        if a <= pos < b:
            return a, b
    return spans[-1]


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).lower().strip("'’"), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def _near(text: str, start: int, end: int, words: frozenset[str], before: int, after: int) -> bool:
    toks = _tokens(text)
    here = [i for i, (_, a, b) in enumerate(toks) if a < end and b > start]
    if not here:
        return False
    lo, hi = max(0, here[0] - before), min(len(toks), here[-1] + after + 1)
    return any(t in words for t, _, _ in toks[lo : here[0]] + toks[here[-1] + 1 : hi])


def _article(rating: str, original: str) -> str:
    """ "a" / "an" for the rating that now follows (``the`` is kept)."""
    if original.lower() == "the":
        return original
    return match_case(original, "an" if rating[:1].lower() in "aeiou" else "a")


def _ladder_text(m: re.Match[str]) -> str:
    """The ladder with its two ratings swapped; only the rating words and their articles change."""
    text, base = m.group(0), m.start()
    subs = [(m.start("r1"), m.end("r1"), m.group("r2")), (m.start("r2"), m.end("r2"), m.group("r1"))]
    if m.group("a1"):
        subs.append((m.start("a1"), m.end("a1"), _article(m.group("r2"), m.group("a1"))))
    if m.group("a2"):
        subs.append((m.start("a2"), m.end("a2"), _article(m.group("r1"), m.group("a2"))))
    for a, b, rep in sorted(subs, reverse=True):
        text = text[: a - base] + rep + text[b - base :]
    return text


def _named_rating(m: re.Match[str]) -> bool:
    """A rating written as one: quoted, capitalized, after an article or before "rating" ("to Neutral",
    'a "hold" rating', "to a strong-buy rating"); not the verb in "plans to sell"."""
    return bool(m.group("q") or m.group("art") or m.group("rw")) or m.group("r")[:1].isupper()


def _beat_replacement(text: str, m: re.Match[str]) -> tuple[str, int]:
    word = m.group(1)
    low = word.lower()
    dst, pol = BEAT_FORMS[low]
    if low == "beat":
        prev = _tokens(text[: m.start()])
        noun = bool(prev) and (prev[-1][0] in NOUN_BEFORE or prev[-1][0] == "to")
        if noun or re.search(r"['’]s\s*$", text[: m.start()]):
            dst = "miss"
    return match_case(word, dst), pol


MAIN_FAMILIES: Final = frozenset({"beat", "guidance", "rating", "expectations"})


def _find(
    field_text: str, item: int, field: str, loose: frozenset[str] = frozenset()
) -> tuple[list[Phrase], list[str]]:
    """Outcome phrases and companions of one field, and the rule violations found in it. A span is edited
    once: a later match that overlaps an earlier phrase is skipped (families in the module table's order).
    For a family in ``loose`` (the item already has a phrase of it) every word of the family is a phrase,
    context or not, so that "The upgrade is a positive" flips with "upgrades the company's rating"."""
    out: list[Phrase] = []
    bad: list[str] = []
    spans = sentences(field_text)
    consistency: set[int] = set()  # starts of loose phrases (exempt from the subject check)

    def add(
        m: re.Match[str], replacement: str, family: str, polarity: int, *, contextual: bool = True
    ) -> None:
        a, b = m.start(1), m.end(1)
        if any(p.start < b and a < p.end for p in out):
            return
        out.append(Phrase(item, field, a, b, m.group(1), replacement, family, polarity))
        if not contextual:
            consistency.add(a)

    excluded = [(m.start(), m.end()) for m in BEAT_EXCLUDE.finditer(field_text)]
    for m in BEAT_RE.finditer(field_text):
        if any(a <= m.start() < b for a, b in excluded):
            continue
        contextual = _near(field_text, m.start(), m.end(), EXPECT_WORDS, 6, 6)
        if contextual or "beat" in loose:
            rep, pol = _beat_replacement(field_text, m)
            add(m, rep, "beat", pol, contextual=contextual)
    for m in GUIDANCE_RE.finditer(field_text):
        low = m.group(1).lower()
        window = (
            4 if low.startswith("cut") else 5
        )  # "cut 500 jobs, lowered its outlook": "cut" is not guidance
        after = _near(field_text, m.start(), m.end(), GUIDANCE_NOUNS, 0, window)
        before = low in GUIDANCE_PARTICIPLES and _near(field_text, m.start(), m.end(), GUIDANCE_NOUNS, 3, 0)
        if after or before:
            dst, pol = GUIDANCE_FORMS[low]
            add(m, match_case(m.group(1), dst), "guidance", pol)
    for m in RATING_RE.finditer(field_text):
        a, b = _sentence_of(spans, m.start())
        s = field_text[a:b]
        context = {t for t, _, _ in _tokens(s)} & RATING_CONTEXT
        contextual = bool(
            context or LADDER_RE.search(s) or any(_named_rating(t) for t in TO_RATING_RE.finditer(s))
        )
        if contextual or "rating" in loose:
            dst, pol = RATING_FORMS[m.group(1).lower()]
            add(m, match_case(m.group(1), dst), "rating", pol, contextual=contextual)
    for m in EXPECTATIONS_RE.finditer(field_text):
        pol = +1 if m.group(1).lower() == "above" else -1
        add(m, match_case(m.group(1), "below" if pol > 0 else "above"), "expectations", pol)
    for m in PRICE_TARGET_RE.finditer(field_text):
        pol = +1 if m.group(1).lower() == "raised" else -1
        add(m, match_case(m.group(1), "lowered" if pol > 0 else "raised"), "price_target", pol)
    # rating sentences: swap full ladders; a named target rating outside a ladder cannot be flipped
    for a, b in sorted({_sentence_of(spans, p.start) for p in out if p.family == "rating"}):
        s = field_text[a:b]
        ladders = list(LADDER_RE.finditer(s))
        for lm in ladders:
            out.append(
                Phrase(item, field, a + lm.start(), a + lm.end(), lm.group(0), _ladder_text(lm), "ladder", 0)
            )
        inside = [(lm.start(), lm.end()) for lm in ladders]
        for tm in TO_RATING_RE.finditer(s):
            if _named_rating(tm) and not any(x <= tm.start() < y for x, y in inside):
                bad.append("bare_rating")
        if OTHER_TARGET_RE.search(s):
            bad.append("bare_rating")
    for p in out:
        if p.family not in MAIN_FAMILIES:
            continue
        a, b = _sentence_of(spans, p.start)
        # the company is the subject (or, for a rating, the object) of the outcome
        if p.family == "rating":  # the company is rated, not the broker ("analysts at the company")
            s = field_text[a:b]
            named = any(not ACTOR_BEFORE.search(s[: c.start()]) for c in COMPANY.finditer(s))
        else:
            named = bool(COMPANY.search(field_text[a : p.start]))
        if p.start not in consistency and not named:
            bad.append("other_subject")
        # questions and forward-looking sentences are about expectations, not outcomes
        if FORWARD_RE.search(field_text[a:b]):
            bad.append("forward_looking")
    return out, bad


def _uncovered(text: str, ladders_flipped: int) -> bool:
    """An outcome cue the rules do not flip (check 3) in a company item's text. ``ladders_flipped`` counts the
    item's rating ladders inside rating sentences; any other ladder is a rating change that would stay."""
    for m in UNCOVERED_NEAR_EXPECT.finditer(text):
        if _near(text, m.start(), m.end(), EXPECT_WORDS, 6, 6):
            return True
    if (
        len(LADDER_RE.findall(text)) > ladders_flipped
        or BEAT_AND_RAISE.search(text)
        or STOCK_MOVE.search(text)
    ):
        return True
    inside = [(m.start(), m.end()) for m in LADDER_RE.finditer(text)]
    for m in FROM_RATING_RE.finditer(text):
        if _named_rating(m) and not any(a <= m.start() < b for a, b in inside):
            return True
    return bool(
        UNCOVERED_RATING.search(text)
        or UNCOVERED_GUIDANCE.search(text)
        or UNCOVERED_PRICE_TARGET.search(text)
    )


def _numbers_ok(text: str, spans: Sequence[tuple[int, int]], starts: Iterable[int]) -> bool:
    """Check 5 on the edited sentences and on every sentence with an expectations word (a stated actual and
    estimate, "Reported EPS is $1.11, expectations were $1.05", contradicts a flipped verb anywhere in the
    item)."""
    check = {_sentence_of(spans, pos) for pos in starts}
    check |= {(a, b) for a, b in spans if {t for t, _, _ in _tokens(text[a:b])} & EXPECT_WORDS}
    for a, b in check:
        n = sum(1 for m in _NUMBER.finditer(text, a, b) if not _BY_AMOUNT.search(text[a : m.start()]))
        if n >= 2:
            return False
    return True


def _apply(text: str, phrases: Sequence[Phrase]) -> str:
    out = text
    for p in sorted(phrases, key=lambda x: x.start, reverse=True):
        out = out[: p.start] + p.replacement + out[p.end :]
    return out


def edit_state(state: Mapping[str, Any]) -> EditResult:
    """Flip every outcome phrase of ``state['news']`` if the state is editable (module docstring)."""
    news = state.get("news") or []
    phrases: list[Phrase] = []
    for i, it in enumerate(news):
        about = any(COMPANY.search(str(it.get(f) or "")) for f in FIELDS)
        item_phrases: list[Phrase] = []
        problems: list[str] = []
        texts = {f: str(it.get(f) or "") for f in FIELDS}
        first = [p.family for f in FIELDS for p in _find(texts[f], i, f)[0]]
        loose = frozenset(fam for fam in ("beat", "rating") if fam in first) if about else frozenset()
        for f in FIELDS:
            text = texts[f]
            found, bad = _find(text, i, f, loose)
            item_phrases += found
            problems += bad
            edited_at = [p.start for p in found if p.family != "ladder"]
            if about and edited_at and not _numbers_ok(text, sentences(text), edited_at):
                problems.append("numbers")
        main = [p for p in item_phrases if p.family in MAIN_FAMILIES]
        if main and not about:
            return EditResult(False, "other_subject", (), 0, None)
        if not about:
            continue
        if main and problems:
            return EditResult(False, problems[0], (), 0, None)
        n_ladders = sum(p.family == "ladder" for p in item_phrases)
        if _uncovered(" ".join(str(it.get(f) or "") for f in FIELDS), n_ladders):
            return EditResult(False, "uncovered_cue", (), 0, None)
        phrases += item_phrases
    signs = {p.polarity for p in phrases if p.polarity != 0}
    if not any(p.family in MAIN_FAMILIES for p in phrases):
        return EditResult(False, "no_phrase", (), 0, None)
    if len(signs) != 1:
        return EditResult(False, "mixed", (), 0, None)
    edited = copy.deepcopy(dict(state))
    for i, it in enumerate(edited["news"]):
        for f in FIELDS:
            mine = [p for p in phrases if p.item == i and p.field == f]
            if mine:
                it[f] = _apply(str(it[f]), mine)
    return EditResult(True, None, tuple(phrases), signs.pop(), edited)


def edit_u(event_id: str, seed: int) -> int:
    """The selection order of probe c: u = sha256("{seed}:counterfactual:{event_id}")."""
    return int(hashlib.sha256(f"{seed}:counterfactual:{event_id}".encode()).hexdigest()[:15], 16)


def select(
    states: pd.DataFrame, n: int, seed: int, *, preferred: Iterable[str]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """The ``n`` editable states (event_id, state_json) with the smallest u, taking the ``preferred`` events
    (the stage-2 sample, whose originals are answered anyway) first. Returns the selection with the edited
    state, its edits and polarity, and the count of states by rejection reason."""
    pref = set(preferred)
    rows: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for rec in states.to_dict("records"):
        res = edit_state(json.loads(rec["state_json"]))
        key = "editable" if res.ok else str(res.reason)
        reasons[key] = reasons.get(key, 0) + 1
        if not res.ok or res.state is None:
            continue
        rows.append(
            {
                "event_id": rec["event_id"],
                "preferred": rec["event_id"] in pref,
                "u": edit_u(str(rec["event_id"]), seed),
                "polarity": res.polarity,
                "families": ",".join(res.families),
                "n_edits": len(res.phrases),
                "edits_json": json.dumps(
                    [
                        {
                            "item": p.item,
                            "field": p.field,
                            "from": p.text,
                            "to": p.replacement,
                            "family": p.family,
                        }
                        for p in res.phrases
                    ],
                    ensure_ascii=False,
                ),
                "edited_state": res.state,
            }
        )
    df = pd.DataFrame(rows)
    if len(df) < n:
        raise ValueError(f"only {len(df)} editable states for {n} counterfactual pairs")
    df = df.sort_values(["preferred", "u"], ascending=[False, True], kind="mergesort").head(n)
    return df.reset_index(drop=True), reasons
