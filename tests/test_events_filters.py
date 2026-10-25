"""Candidate filters, ticker-day aggregation and the attention ratio (PREREG §6.6; PRD NA-03 S2–S3)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.events import load_events_config
from newsaction.events.attention import window_counts
from newsaction.events.filters import eligible, rule_scores, ticker_days, tie_u

CFG = load_events_config().filters


def _arts(**over: list[object]) -> pd.DataFrame:
    n = len(next(iter(over.values())))
    base: dict[str, list[object]] = {
        "tag_type": ["earnings_results"] * n,
        "sentiment_direction": ["Positive"] * n,
        "sentiment_intensity": ["Immediate"] * n,
        "event_age_days": [0] * n,
        "source_class": ["other"] * n,
        "novelty": [0.3] * n,
    }
    base.update(over)
    return pd.DataFrame(base)


def test_rule_scores() -> None:
    a = _arts(
        tag_type=[
            "earnings_results",
            "product_launch",
            "macro_sector",
            "earnings_results",
            "earnings_results",
            "ma_deal",
        ],
        sentiment_direction=["Positive", "Negative", "Positive", "Neutral", "Strongly Negative", "Positive"],
        sentiment_intensity=["Immediate", "Immediate", "Immediate", "Immediate", "Medium-Term", None],
        event_age_days=[0, 0, 0, 0, 0, 3],
        source_class=[
            "press_wire_primary",
            "major_outlet",
            "aggregator",
            "other",
            "retail_analysis",
            "other",
        ],
    )
    s = rule_scores(a, CFG)
    assert s["f0"].tolist() == [1.0] * 6
    assert s["f1"].tolist() == [1, 1, 0, 0, 1, 0]  # MATERIAL tag, non-neutral, fresh story
    assert s["f2"].tolist() == [1, 0, 0, 0, 0, 0]  # + HARD tag + timely intensity
    assert s["f3"].tolist() == [1, 1, 0, 0, 0, 0]
    assert s["f4"].tolist() == [0.3] * 6
    assert (s["f2"] <= s["f1"]).all()


def test_ticker_days_max_and_counts_and_eligibility() -> None:
    sc = pd.DataFrame(
        {
            "company_id": [1, 1, 1, 2],
            "session_w0": [date(2025, 7, 7)] * 3 + [None],
            "f0": 1.0,
            "f1": [0.0, 1.0, 1.0, 1.0],
            "f2": [0.0, 0.0, 1.0, 1.0],
            "f3": [0.0, 0.0, 0.0, 1.0],
            "f4": [0.1, 0.5, 0.2, 0.9],
            "f5": [0.2, 0.1, 0.3, 0.9],
            "f6_w0": [0.4, 0.6, 0.5, np.nan],
        }
    )
    td = ticker_days(sc, "session_w0", "f6_w0")
    assert len(td) == 1  # the W2-only article of company 2 is not a W0 ticker-day
    r = td.iloc[0]
    assert (r["n_kept"], r["n_f1"], r["n_f2"], r["n_f3"]) == (3, 2, 1, 0)
    assert (r["f4"], r["f5"], r["f6"]) == (0.5, 0.3, 0.6)
    assert eligible(td, "F1").tolist() == [True] and eligible(td, "F3").tolist() == [False]
    assert eligible(td, "F6").tolist() == [True]


def test_tie_u_is_deterministic_and_uniform() -> None:
    days = calendar.sessions(date(2025, 1, 2), date(2025, 12, 31))
    comp = list(range(40))
    c = [x for x in comp for _ in days]
    d = [x for _ in comp for x in days]
    u = tie_u(c, d, 2026)
    assert np.array_equal(u, tie_u(c, d, 2026))
    assert not np.array_equal(u, tie_u(c, d, 2027))
    assert u.min() >= 0 and u.max() < 1 and abs(u.mean() - 0.5) < 0.01


def test_attention_ratio_uses_previous_member_sessions_only() -> None:
    sess = calendar.sessions(date(2025, 1, 2), date(2025, 6, 30))
    members = pd.DataFrame({"session": sess, "company_id": 1})
    t = sess[80]
    rows = [
        {"company_id": 1, "session_w0": s, "session_w2": s, "usable": True, "keep": True} for s in sess[:80]
    ]
    arts = pd.DataFrame(rows)
    base = window_counts(arts, members, CFG).set_index("session")
    # plant 50 articles on day t (W0) -> t's mean is unchanged, its count and ratio change
    planted = pd.concat(
        [
            arts,
            pd.DataFrame(
                [
                    {"company_id": 1, "session_w0": t, "session_w2": t, "usable": True, "keep": i == 0}
                    for i in range(50)
                ]
            ),
        ]
    )
    after = window_counts(planted, members, CFG).set_index("session")
    assert after.loc[t, "attention_mean_w0"] == base.loc[t, "attention_mean_w0"] == pytest.approx(1.0)
    assert (
        after.loc[t, "n_articles_w0"] == 50
        and after.loc[t, "n_stories_w0"] == 1
        and after.loc[t, "n_dup_w0"] == 49
    )
    assert after.loc[t, "attention_ratio_w0"] == pytest.approx(50.0)
    assert after.loc[sess[81], "attention_mean_w0"] > base.loc[sess[81], "attention_mean_w0"]
    # fewer than 20 previous member sessions -> no mean
    assert np.isnan(base.loc[sess[10], "attention_mean_w0"])


def test_attention_mean_ignores_non_member_sessions() -> None:
    sess = calendar.sessions(date(2025, 1, 2), date(2025, 6, 30))
    members = pd.DataFrame({"session": sess[60:], "company_id": 1})  # joins at sess[60]
    arts = pd.DataFrame(
        [{"company_id": 1, "session_w0": s, "session_w2": s, "usable": True, "keep": True} for s in sess[60:]]
    )
    out = window_counts(arts, members, CFG).set_index("session")
    assert np.isnan(out.loc[sess[70], "attention_mean_w0"])  # 10 member sessions so far
    assert out.loc[sess[90], "attention_mean_w0"] == pytest.approx(1.0)
