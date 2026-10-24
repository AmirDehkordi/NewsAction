"""PRD NA-02 S11: member-month coverage (PREREG §3.4) and the leaver check."""

from __future__ import annotations

from datetime import date

import pandas as pd

from newsaction.news import coverage


def test_member_month_counts() -> None:
    pairs = pd.DataFrame(
        {
            "session": [date(2023, 6, 30), date(2023, 7, 3), date(2023, 7, 5), date(2023, 7, 3)],
            "company_id": [1, 1, 1, 2],
        }
    )
    arts = pd.DataFrame(
        {
            "id": ["a", "b", "c"],
            "company_id": [1, 1, 1],
            "session_w0": [date(2023, 7, 3), None, None],
            "session_w2": [date(2023, 7, 3), date(2023, 7, 5), date(2023, 7, 5)],
            "keep": [True, False, True],
            "passes_clean": [True, True, True],
        }
    )
    cov = coverage.member_month_counts(arts, pairs)
    assert cov["month"].tolist() == ["2023-07", "2023-07"]  # June 2023 is before the news load range
    one = cov.set_index("company_id")
    assert one.loc[1, "member_sessions"] == 2
    assert (one.loc[1, "n_mapped"], one.loc[1, "n_clean"], one.loc[1, "n_keep"], one.loc[1, "n_keep_w0"]) == (
        3,
        3,
        2,
        1,
    )
    assert one["covered"].to_dict() == {1: True, 2: False}


def test_leaver_rate_uses_the_last_member_sessions() -> None:
    sessions = pd.bdate_range("2025-01-01", periods=80).date
    rows = [(s, c) for s in sessions for c in (1, 2, 3)] + [(s, 9) for s in sessions[:70]]
    pairs = pd.DataFrame(rows, columns=["session", "company_id"])
    arts = pd.DataFrame(
        {
            "id": [f"x{i}" for i in range(4)],
            "company_id": [9, 9, 1, 2],
            "session_w2": [sessions[60], sessions[65], sessions[60], sessions[60]],
            "keep": [True, True, True, False],
        }
    )
    tiers = pd.DataFrame({"month": ["2025-04"] * 4, "company_id": [1, 2, 3, 9], "tier": ["Mid"] * 4})
    sectors = pd.Series({1: "Energy", 2: "Energy", 3: "Utilities", 9: "Energy"})
    out = coverage.leaver_check(arts, pairs, tiers, sectors)
    row = out.set_index("company_id").loc[9]
    assert row["window_sessions"] == 60 and row["n_stayers"] == 2  # same tier and sector: 1 and 2
    assert row["leaver_rate"] == 2 / 60
    assert row["stayer_rate_mean"] == (1 / 60 + 0) / 2
