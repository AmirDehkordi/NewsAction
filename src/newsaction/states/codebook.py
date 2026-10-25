"""Numbers as words: codebook v1 (PREREG §6.11; PRD NA-04 S1).

Every number in a state goes through one of these scales (CLAUDE.md A4). Scales are loaded from
``configs/codebook_v1.yaml`` and applied by pure functions; bins are half-open [lo, hi), so a value on an
edge takes the higher bin.

**Moves** are the only values whose form depends on the encoding (PREREG §8.4). A ``Move`` carries the
value in typical-move units (``z``, signed), its horizon, and what E0 and E4 need:

| Encoding | Form | Example |
|---|---|---|
| E0 | raw change | "+3.4% (S&P 500 +0.6%)", "+5 bp", "+1.3 points" |
| E1 | σ-number, 1 decimal | "+2.3σ" |
| E2 | words | "large rise" |
| E3 | words + multiple | "large rise (≈2.3× a typical day's move)" |
| E4 | percentile words | "a rise larger than 97% of its daily moves in the past year" |

The E3 multiple is truncated to one decimal, so it never contradicts its word: every move edge lies on the
0.1 grid (1.97 is "moderate rise (≈1.9× …)"). Every other scale (percentile, β, attention, revision, counts,
tier, timing, source type) is words only, in every encoding.
"""

from __future__ import annotations

import bisect
import functools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo

import pandas as pd

from newsaction import calendar
from newsaction.config import load_project, load_yaml
from newsaction.states import CODEBOOK_PATH, ENCODINGS, Encoding

Horizon = Literal["day", "week", "month", "three_months"]
Unit = Literal["pct", "bp", "points"]
DecisionLabel = Literal["D1", "D2"]
HORIZONS: Final[tuple[Horizon, ...]] = ("day", "week", "month", "three_months")


class CodebookError(ValueError):
    """The codebook file is malformed, or a value cannot be encoded."""


def _isnan(x: float | None) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


@dataclass(frozen=True)
class Scale:
    """Words for half-open bins: ``words[i]`` covers [edges[i-1], edges[i])."""

    edges: tuple[float, ...]
    words: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.words) != len(self.edges) + 1:
            raise CodebookError(f"{len(self.edges)} edges need {len(self.edges) + 1} words, got {self.words}")
        if list(self.edges) != sorted(set(self.edges)):
            raise CodebookError(f"edges must be strictly increasing: {self.edges}")

    def word(self, x: float) -> str:
        if _isnan(x):
            raise CodebookError("cannot place a missing value in a scale")
        return self.words[bisect.bisect_right(self.edges, x)]


@dataclass(frozen=True)
class Move:
    """A move to encode. ``z``: typical-move units (signed). ``raw``: the raw change as a decimal (E0).
    ``benchmark``: the S&P 500's raw change over the same period (E0 of stock moves). ``pct``: percent of
    the series' own past-year moves (same horizon) with a smaller absolute size (E4)."""

    z: float
    horizon: Horizon = "day"
    raw: float = math.nan
    unit: Unit = "pct"
    benchmark: float = math.nan
    pct: float = math.nan


@dataclass(frozen=True)
class E0Unit:
    format: str
    scale: float


@dataclass(frozen=True)
class Codebook:
    version: int
    move: Scale
    sign_up: str
    sign_down: str
    sign_zero: str
    relative_to: str
    encodings: tuple[str, ...]
    default_encoding: str
    e1_decimals: int
    e3_decimals: int
    typical: Mapping[str, str]
    e4_period: Mapping[str, str]
    e4_article: Mapping[str, str]
    e0_units: Mapping[str, E0Unit]
    e0_benchmark: str
    percentile: Scale
    beta: Scale
    attention: Scale
    tier: Mapping[str, str]
    timing: Mapping[str, str]
    time_label: Mapping[str, str]
    revision: Scale
    revision_floor: float
    count_words: tuple[str, ...]
    count_more: str
    earnings_in: str
    earnings_out: str
    source_type: Mapping[str, str]
    missing: str

    # --- moves ------------------------------------------------------------------------------------

    def move_magnitude(self, z: float) -> str:
        """PREREG §6.11 move word of |z|."""
        return self.move.word(abs(z))

    def move_words(self, z: float) -> str:
        """E2 words: "<magnitude> <rise|fall>"; exactly 0 is "no change"."""
        if _isnan(z):
            return self.missing
        if z == 0:
            return self.sign_zero
        return f"{self.move_magnitude(z)} {self.sign_up if z > 0 else self.sign_down}"

    def _e0(self, move: Move) -> str:
        unit = self.e0_units[move.unit]
        if _isnan(move.raw):
            return self.missing
        text = unit.format.format(move.raw * unit.scale)
        if not _isnan(move.benchmark):
            bench = self.e0_units["pct"]
            text += f" ({self.e0_benchmark} {bench.format.format(move.benchmark * bench.scale)})"
        return text

    def _e1(self, z: float) -> str:
        if _isnan(z):
            return self.missing
        r = round(z, self.e1_decimals)
        return f"{0.0:.{self.e1_decimals}f}σ" if r == 0 else f"{r:+.{self.e1_decimals}f}σ"

    def multiple(self, x: float) -> str:
        """|x| truncated to ``e3_decimals`` ("2.3")."""
        q = 10**self.e3_decimals
        return f"{math.floor(abs(x) * q + 1e-9) / q:.{self.e3_decimals}f}"

    def _e3(self, move: Move) -> str:
        if _isnan(move.z):
            return self.missing
        return f"{self.move_words(move.z)} (≈{self.multiple(move.z)}× {self.typical[move.horizon]})"

    def _e4(self, move: Move) -> str:
        if _isnan(move.z) or _isnan(move.pct):
            return self.missing
        if move.z == 0:
            return self.sign_zero
        article = self.e4_article["up" if move.z > 0 else "down"]
        pct = min(100, max(0, math.floor(move.pct + 1e-9)))
        return f"{article} larger than {pct}% of its {self.e4_period[move.horizon]} moves in the past year"

    def encode_move(self, move: Move, encoding: Encoding) -> str:
        if encoding == "E0":
            return self._e0(move)
        if encoding == "E1":
            return self._e1(move.z)
        if encoding == "E2":
            return self.move_words(move.z)
        if encoding == "E3":
            return self._e3(move)
        if encoding == "E4":
            return self._e4(move)
        raise CodebookError(f"unknown encoding {encoding!r}")

    # --- other scales (words only, every encoding) --------------------------------------------------

    def percentile_word(self, pct: float) -> str:
        return self.missing if _isnan(pct) else self.percentile.word(pct)

    def beta_word(self, beta: float) -> str:
        return self.missing if _isnan(beta) else self.beta.word(beta)

    def attention_word(self, multiple: float) -> str:
        return self.missing if _isnan(multiple) else self.attention.word(multiple)

    def revision_word(self, revision: float) -> str:
        return self.missing if _isnan(revision) else self.revision.word(revision)

    def revision_value(self, now: float, before: float) -> float:
        """(now − before) / max(|before|, floor): the input of ``revision_word``."""
        if _isnan(now) or _isnan(before):
            return math.nan
        return (now - before) / max(abs(before), self.revision_floor)

    def count_word(self, n: float) -> str:
        if _isnan(n):
            return self.missing
        k = int(n)
        if k != n or k < 0:
            raise CodebookError(f"a count must be a non-negative integer, got {n}")
        return self.count_words[k] if k < len(self.count_words) else self.count_more

    def tier_word(self, tier: object) -> str:
        if not isinstance(tier, str) or tier not in self.tier:
            return self.missing
        return self.tier[tier]

    def earnings_word(self, in_window: bool) -> str:
        return self.earnings_in if in_window else self.earnings_out

    def source_type_word(self, source_class: object) -> str:
        if isinstance(source_class, str) and source_class in self.source_type:
            return self.source_type[source_class]
        return self.source_type["other"]

    def time_label_word(self, point: DecisionLabel) -> str:
        return self.time_label[point]

    def timing_word(self, t_avail: pd.Timestamp | datetime, session: date) -> str:
        """PREREG §6.11 timing words for an article available at ``t_avail`` in a window of ``session``.

        Boundaries (America/New_York): after the previous session's close and within its calendar day →
        "after yesterday's close"; then until ``early_from`` on the session → "overnight" (weekends and
        holidays included); until ``before_open_from`` → "early this morning"; until the open → "shortly
        before the open"; from the open to the close → "during today's trading session".
        """
        ts = pd.Timestamp(t_avail)
        if ts.tzinfo is None:
            raise CodebookError("t_avail must be tz-aware")
        prev_close = calendar.close_utc(calendar.prev_session(session))
        open_s, close_s = calendar.open_utc(session), calendar.close_utc(session)
        if not prev_close < ts <= close_s:
            raise CodebookError(f"t_avail {ts} is outside W2({session})")
        tz = _tz()
        local = ts.tz_convert(tz)
        if local.date() == prev_close.tz_convert(tz).date():
            return self.timing["after_close"]
        if ts >= open_s:
            return self.timing["during_session"]
        start = pd.Timestamp(datetime.combine(session, _hhmm(self.timing["early_from"])), tz=tz)
        before = pd.Timestamp(datetime.combine(session, _hhmm(self.timing["before_open_from"])), tz=tz)
        if local < start:
            return self.timing["overnight"]
        if local < before:
            return self.timing["early_morning"]
        return self.timing["before_open"]


def _hhmm(text: str) -> time:
    h, m = text.split(":")
    return time(int(h), int(m))


@functools.cache
def _tz() -> ZoneInfo:
    return ZoneInfo(load_project().timezone)


def _scale(raw: Mapping[str, Any]) -> Scale:
    return Scale(tuple(float(e) for e in raw["edges"]), tuple(str(w) for w in raw["words"]))


def _strs(raw: Mapping[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in raw.items()}


def parse(raw: Mapping[str, Any]) -> Codebook:
    enc = raw["encodings"]
    if tuple(enc["ids"]) != ENCODINGS:
        raise CodebookError(f"encodings must be {ENCODINGS}")
    typical, period = _strs(enc["typical"]), _strs(enc["e4_period"])
    for name, table in (("typical", typical), ("e4_period", period)):
        if set(table) != set(HORIZONS):
            raise CodebookError(f"encodings.{name} must cover {HORIZONS}")
    timing = raw["timing"]
    return Codebook(
        version=int(raw["version"]),
        move=_scale(raw["move"]),
        sign_up=str(raw["sign"]["up"]),
        sign_down=str(raw["sign"]["down"]),
        sign_zero=str(raw["sign"]["zero"]),
        relative_to=str(raw["sign"]["relative_to"]),
        encodings=tuple(enc["ids"]),
        default_encoding=str(enc["default"]),
        e1_decimals=int(enc["e1_decimals"]),
        e3_decimals=int(enc["e3_decimals"]),
        typical=typical,
        e4_period=period,
        e4_article=_strs(enc["e4_article"]),
        e0_units={k: E0Unit(str(v["format"]), float(v["scale"])) for k, v in enc["e0_units"].items()},
        e0_benchmark=str(enc["e0_benchmark"]),
        percentile=_scale(raw["percentile"]),
        beta=_scale(raw["beta"]),
        attention=_scale(raw["attention"]),
        tier=_strs(raw["tier"]),
        timing=_strs(timing),
        time_label=_strs(raw["time_label"]),
        revision=_scale(raw["revision"]),
        revision_floor=float(raw["revision"]["floor"]),
        count_words=tuple(str(w) for w in raw["count"]["words"]),
        count_more=str(raw["count"]["more"]),
        earnings_in=str(raw["earnings"]["in_window"]),
        earnings_out=str(raw["earnings"]["not_in_window"]),
        source_type=_strs(raw["source_type"]),
        missing=str(raw["missing"]),
    )


@functools.cache
def _load(path: Path, mtime_ns: int) -> Codebook:
    return parse(load_yaml(path))


def load_codebook(path: Path = CODEBOOK_PATH) -> Codebook:
    """The codebook of ``configs/codebook_v1.yaml`` (reloaded when the file changes)."""
    return _load(path, path.stat().st_mtime_ns)


def percent_below(history: Sequence[float], value: float) -> float:
    """100 × share of ``history`` (NaNs dropped) strictly below ``value``; NaN if history is empty."""
    vals = [h for h in history if not _isnan(h)]
    if not vals or _isnan(value):
        return math.nan
    return 100.0 * sum(h < value for h in vals) / len(vals)
