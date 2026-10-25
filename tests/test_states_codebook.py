"""PRD NA-04 S1 / AC4: codebook v1 equals PREREG §6.11; every scale at every bin edge; encoders E0–E4."""

from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd
import pytest
import yaml

from newsaction import calendar
from newsaction.paths import ROOT
from newsaction.states import CODEBOOK_PATH
from newsaction.states.codebook import CodebookError, Move, Scale, load_codebook, parse, percent_below

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
CB = load_codebook()

# PREREG §6.11 (hard-coded here and checked against the PREREG text below)
MOVE = [
    (0.5, "negligible", "small"),
    (1.0, "small", "moderate"),
    (2.0, "moderate", "large"),
    (3.0, "large", "very large"),
    (5.0, "very large", "extreme"),
]
PERCENTILE = [
    (10, "very low", "low"),
    (30, "low", "normal"),
    (70, "normal", "high"),
    (90, "high", "very high"),
]
BETA = [
    (0.7, "defensive", "market-like"),
    (1.2, "market-like", "aggressive"),
    (1.6, "aggressive", "very aggressive"),
]
ATTENTION = [
    (0.5, "unusually quiet", "normal"),
    (1.5, "normal", "busy"),
    (3.0, "busy", "very heavy"),
    (6.0, "very heavy", "extreme"),
]
TIERS = {
    "top100": "one of the 100 largest US companies",
    "mid": "a large US company (size rank 101–250)",
    "rest": "an S&P 500 company (size rank 251–500)",
}
TIMING = [
    "after yesterday's close",
    "overnight",
    "early this morning (before 08:00)",
    "shortly before the open",
]
EPS = 1e-9


def test_prereg_table_matches_constants() -> None:
    for edge_row in (
        "| < 0.5 | negligible |",
        "| [0.5, 1) | small |",
        "| [1, 2) | moderate |",
        "| [2, 3) | large |",
        "| [3, 5) | very large |",
        "| ≥ 5 | extreme |",
    ):
        assert edge_row in PREREG
    assert "< 10 very low; 10–30 low; 30–70 normal; 70–90 high; ≥ 90 very high" in PREREG
    assert "< 0.7 defensive; 0.7–1.2 market-like; 1.2–1.6 aggressive; ≥ 1.6 very aggressive" in PREREG
    assert "< 0.5 unusually quiet; 0.5–1.5 normal; 1.5–3 busy; 3–6 very heavy; ≥ 6 extreme" in PREREG
    for words in TIERS.values():
        assert words.replace("–", "–") in PREREG
    for w in TIMING:
        assert f'"{w}"' in PREREG
    assert "The default before NA-07 is **E3**." in PREREG


@pytest.mark.parametrize(
    ("scale", "table"),
    [(CB.move, MOVE), (CB.percentile, PERCENTILE), (CB.beta, BETA), (CB.attention, ATTENTION)],
    ids=["move", "percentile", "beta", "attention"],
)
def test_bin_edges(scale: Scale, table: list[tuple[float, str, str]]) -> None:
    assert scale.edges == tuple(float(e) for e, _, _ in table)
    for edge, below, at in table:
        assert scale.word(edge - EPS) == below
        assert scale.word(edge) == at  # half-open: the edge takes the higher bin
        assert scale.word(edge + EPS) == at


def test_move_words_and_sign() -> None:
    for edge, below, at in MOVE:
        assert CB.move_words(edge) == f"{at} rise"
        assert CB.move_words(-edge) == f"{at} fall"
        assert CB.move_words(-(edge - EPS)) == f"{below} fall"
    assert CB.move_words(0.0) == "no change"
    assert CB.move_words(math.nan) == "not available"
    assert CB.relative_to == "the market and its sector"


def test_encoders_prereg_examples() -> None:
    m = Move(z=2.34, raw=0.034, benchmark=0.006, pct=97.6)
    assert CB.encode_move(m, "E0") == "+3.4% (S&P 500 +0.6%)"
    assert CB.encode_move(m, "E1") == "+2.3σ"
    assert CB.encode_move(m, "E2") == "large rise"
    assert CB.encode_move(m, "E3") == "large rise (≈2.3× a typical day's move)"
    assert CB.encode_move(m, "E4") == "a rise larger than 97% of its daily moves in the past year"


def test_e3_multiple_never_contradicts_word() -> None:
    for edge, below, at in MOVE:
        assert CB.encode_move(Move(z=edge - 0.001), "E3").startswith(f"{below} rise (≈{edge - 0.1:.1f}×")
        assert CB.encode_move(Move(z=edge), "E3").startswith(f"{at} rise (≈{edge:.1f}×")
    assert CB.encode_move(Move(z=-0.7, horizon="month"), "E3") == "small fall (≈0.7× a typical month's move)"


def test_e0_units_and_e1_zero() -> None:
    assert CB.encode_move(Move(z=1.0, raw=0.0005, unit="bp"), "E0") == "+5 bp"
    assert CB.encode_move(Move(z=1.0, raw=-1.34, unit="points"), "E0") == "-1.3 points"
    assert CB.encode_move(Move(z=-0.04), "E1") == "0.0σ"
    assert CB.encode_move(Move(z=-1.25), "E1") == "-1.2σ"


def test_e4_horizons_and_missing() -> None:
    assert CB.encode_move(Move(z=-1.0, horizon="week", pct=80.2), "E4") == (
        "a fall larger than 80% of its weekly moves in the past year"
    )
    assert CB.encode_move(Move(z=1.0, pct=math.nan), "E4") == "not available"
    assert CB.encode_move(Move(z=math.nan), "E3") == "not available"


def test_e2_and_e3_digit_rules() -> None:
    """AC4: E2 words carry no digit; E3 carries digits only inside "≈k.k×"."""
    for z in (-12.3, -5.0, -2.0, -0.3, 0.0, 0.49, 1.5, 3.2, 7.7):
        for h in ("day", "week", "month", "three_months"):
            m = Move(z=z, horizon=h)  # type: ignore[arg-type]
            assert not re.search(r"\d", CB.encode_move(m, "E2"))
            assert not re.search(r"\d", re.sub(r"≈\d+\.\d×", "", CB.encode_move(m, "E3")))


def test_other_scales_are_words_only() -> None:
    for word in (
        CB.percentile_word(55),
        CB.beta_word(1.0),
        CB.attention_word(2.0),
        CB.revision_word(0.02),
        CB.count_word(3),
        CB.earnings_word(True),
        CB.time_label_word("D1"),
        CB.time_label_word("D2"),
    ):
        assert not re.search(r"\d", word)
    assert CB.tier_word("top100") == TIERS["top100"]
    assert CB.tier_word("mid") == TIERS["mid"] and CB.tier_word("rest") == TIERS["rest"]
    assert CB.tier_word(None) == "not available"


def test_revision_edges() -> None:
    table = [
        (-0.05, "cut sharply", "cut"),
        (-0.01, "cut", "little changed"),
        (0.01, "little changed", "raised"),
        (0.05, "raised", "raised sharply"),
    ]
    for edge, below, at in table:
        assert CB.revision_word(edge - EPS) == below
        assert CB.revision_word(edge) == at
    assert CB.revision_value(2.10, 2.00) == pytest.approx(0.05)
    assert CB.revision_value(0.06, 0.01) == pytest.approx(0.5)  # |before| floored at 0.10
    assert math.isnan(CB.revision_value(1.0, math.nan))


def test_count_words() -> None:
    assert [CB.count_word(i) for i in range(4)] == ["none", "one", "two", "three"]
    assert CB.count_word(10) == "ten" and CB.count_word(11) == "more than ten"
    with pytest.raises(CodebookError):
        CB.count_word(1.5)


def _utc(d: date, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp(f"{d.isoformat()} {hh:02d}:{mm:02d}", tz="America/New_York").tz_convert("UTC")


def test_timing_words() -> None:
    s = date(2025, 9, 15)  # a Monday: the previous session is Friday 2025-09-12
    prev = calendar.prev_session(s)
    assert CB.timing_word(_utc(prev, 16, 30), s) == "after yesterday's close"
    assert CB.timing_word(_utc(prev, 23, 59), s) == "after yesterday's close"
    assert CB.timing_word(_utc(date(2025, 9, 13), 12, 0), s) == "overnight"
    assert CB.timing_word(_utc(s, 3, 59), s) == "overnight"
    assert CB.timing_word(_utc(s, 4, 0), s) == "early this morning (before 08:00)"
    assert CB.timing_word(_utc(s, 7, 59), s) == "early this morning (before 08:00)"
    assert CB.timing_word(_utc(s, 8, 0), s) == "shortly before the open"
    assert CB.timing_word(_utc(s, 9, 15), s) == "shortly before the open"
    assert CB.timing_word(calendar.open_utc(s), s) == "during today's trading session"
    with pytest.raises(CodebookError):
        CB.timing_word(calendar.close_utc(prev), s)  # the close itself is not in W0 / W2


def test_percent_below() -> None:
    assert percent_below([1.0, 2.0, 3.0, math.nan], 2.5) == pytest.approx(200 / 3)
    assert math.isnan(percent_below([], 1.0))


def test_config_is_validated(tmp_path: object) -> None:
    raw = yaml.safe_load(CODEBOOK_PATH.read_text(encoding="utf-8"))
    raw["move"]["words"] = raw["move"]["words"][:-1]
    with pytest.raises(CodebookError):
        parse(raw)
