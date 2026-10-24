"""Point-in-time universe (PREREG §3.1-3.2; PRD NA-01 AC6)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest

from newsaction import calendar
from newsaction.panel import PANEL_START


@pytest.fixture(scope="module")
def members(snapshot: Callable[[str], pd.DataFrame], companies: pd.DataFrame) -> pd.DataFrame:
    m = snapshot("members_by_session")
    m = m.assign(session=[pd.Timestamp(d).date() for d in m["session"]])
    return m.merge(companies[["symbol_id", "company_id"]], on="symbol_id", how="left")


def _present(members: pd.DataFrame, ticker: str) -> set[date]:
    return set(members.loc[members["ticker"] == ticker, "session"])


def test_ac6_companies_per_session_495_to_505(members: pd.DataFrame) -> None:
    assert members["company_id"].notna().all()
    per = members.groupby("session")["company_id"].nunique()
    assert per.min() >= 495 and per.max() <= 505, (per.min(), per.max())
    assert len(per) == len(calendar.sessions(min(per.index), max(per.index)))  # every session present


def test_ac6_wba_leaves_on_2025_08_27(members: pd.DataFrame) -> None:
    on = _present(members, "WBA")
    assert calendar.prev_session(date(2025, 8, 27)) in on
    assert max(on) == calendar.prev_session(date(2025, 8, 27))


def test_ac6_coin_joins_on_2025_05_19(members: pd.DataFrame) -> None:
    on = _present(members, "COIN")
    assert min(on) == date(2025, 5, 19)
    assert all(d in on for d in calendar.sessions(date(2025, 5, 19), date(2025, 12, 31)))


@pytest.mark.parametrize("ticker", ["HOOD", "APP"])
def test_ac6_hood_app_join_on_2025_09_22(members: pd.DataFrame, ticker: str) -> None:
    on = _present(members, ticker)
    assert min(on) == date(2025, 9, 22) and date(2025, 9, 19) not in on


def test_leavers_have_panel_rows_after_exit_for_their_horizons(panel_public: pd.DataFrame) -> None:
    """Leavers keep priced rows for up to 60 sessions after their last member session."""
    p = panel_public[panel_public["session"] >= PANEL_START]
    wba = p[p["ticker"] == "WBA"]
    assert wba["member"].any()
    assert (~wba["member"]).sum() <= 60
