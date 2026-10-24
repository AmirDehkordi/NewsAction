"""newsaction.calendar equals ATOM's calendar (PRD NA-01 AC4): sessions and open/close instants."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from newsaction import calendar

START, END = date(2022, 1, 3), date(2026, 10, 23)


def test_ac4_sessions_and_instants_equal_calendar_atom(snapshot: Callable[[str], pd.DataFrame]) -> None:
    atom = snapshot("calendar_atom")
    ours = calendar.sessions(START, END)
    assert [pd.Timestamp(d).date() for d in atom["session"]] == ours
    opens = [calendar.open_utc(d) for d in ours]
    closes = [calendar.close_utc(d) for d in ours]
    assert list(pd.to_datetime(atom["open_utc"], utc=True)) == opens
    assert list(pd.to_datetime(atom["close_utc"], utc=True)) == closes


def test_ac4_golden_days(snapshot: Callable[[str], pd.DataFrame]) -> None:
    atom = snapshot("calendar_atom").assign(session=lambda d: [pd.Timestamp(x).date() for x in d["session"]])
    days = set(atom["session"])
    assert date(2025, 1, 9) not in days and not calendar.is_session(date(2025, 1, 9))
    half = atom[
        (pd.to_datetime(atom["close_utc"], utc=True) - pd.to_datetime(atom["open_utc"], utc=True))
        < pd.Timedelta(hours=6)
    ]
    ours_half = [d for d in calendar.sessions(START, END) if calendar.is_half_day(d)]
    assert sorted(half["session"]) == ours_half
    assert date(2024, 11, 29) in ours_half and date(2025, 7, 3) in ours_half
