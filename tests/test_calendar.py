"""Calendar golden cases (PRD NA-00 AC2) plus DST, half days, the 2025-01-09 closure and window algebra.

Expected instants are hard-coded UTC values, never derived from the module under test.
"""

from __future__ import annotations

import itertools
import re
import warnings
from datetime import UTC, date, datetime, time, timedelta

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from newsaction import calendar as cal
from newsaction.paths import ROOT


def utc(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


# --- AC2 golden cases ------------------------------------------------------------------------------


def test_w0_across_spring_dst_change() -> None:
    # Fri 2024-03-08 closes in EST (21:00Z); Mon 2024-03-11 is EDT (09:15 ET = 13:15Z).
    assert cal.window_w0(date(2024, 3, 11)) == (utc("2024-03-08 21:00"), utc("2024-03-11 13:15"))


def test_w0_across_fall_dst_change() -> None:
    # Fri 2024-11-01 closes in EDT (20:00Z); Mon 2024-11-04 is EST (09:15 ET = 14:15Z).
    w = cal.window_w0(date(2024, 11, 4))
    assert w.start == utc("2024-11-01 20:00")
    assert w.end == utc("2024-11-04 14:15")


def test_half_day_close_and_next_w0() -> None:
    assert cal.close_utc(date(2024, 11, 29)) == utc("2024-11-29 18:00")
    assert cal.window_w0(date(2024, 12, 2)).start == utc("2024-11-29 18:00")


def test_mlk_monday_closed() -> None:
    assert not cal.is_session(date(2024, 1, 15))
    assert cal.window_w0(date(2024, 1, 16)).start == utc("2024-01-12 21:00")


def test_2025_01_09_national_day_of_mourning() -> None:
    assert not cal.is_session(date(2025, 1, 9))
    assert cal.prev_session(date(2025, 1, 10)) == date(2025, 1, 8)
    assert cal.next_session(date(2025, 1, 8)) == date(2025, 1, 10)
    assert cal.window_w0(date(2025, 1, 10)).start == utc("2025-01-08 21:00")
    assert date(2025, 1, 9) in cal.FORCED_CLOSURES


def test_half_day_close_in_summer_time() -> None:
    assert cal.close_utc(date(2025, 7, 3)) == utc("2025-07-03 17:00")
    assert cal.window_w0(date(2025, 7, 7)) == (utc("2025-07-03 17:00"), utc("2025-07-07 13:15"))


# --- DST, half days, holidays ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("d", "open_z", "close_z", "cutoff_z", "d1_z"),
    [
        (date(2024, 3, 8), "14:30", "21:00", "14:15", "15:00"),  # EST
        (date(2024, 3, 11), "13:30", "20:00", "13:15", "14:00"),  # EDT
        (date(2024, 11, 1), "13:30", "20:00", "13:15", "14:00"),  # EDT
        (date(2024, 11, 4), "14:30", "21:00", "14:15", "15:00"),  # EST
        (date(2025, 3, 7), "14:30", "21:00", "14:15", "15:00"),
        (date(2025, 3, 10), "13:30", "20:00", "13:15", "14:00"),
        (date(2025, 10, 31), "13:30", "20:00", "13:15", "14:00"),
        (date(2025, 11, 3), "14:30", "21:00", "14:15", "15:00"),
    ],
)
def test_session_instants_follow_dst(d: date, open_z: str, close_z: str, cutoff_z: str, d1_z: str) -> None:
    day = d.isoformat()
    assert cal.open_utc(d) == utc(f"{day} {open_z}")
    assert cal.close_utc(d) == utc(f"{day} {close_z}")
    assert cal.d0_cutoff_utc(d) == utc(f"{day} {cutoff_z}")
    assert cal.d1_utc(d) == utc(f"{day} {d1_z}")


HALF_DAYS = [
    date(2024, 7, 3),
    date(2024, 11, 29),
    date(2024, 12, 24),
    date(2025, 7, 3),
    date(2025, 11, 28),
    date(2025, 12, 24),
]


@pytest.mark.parametrize("d", HALF_DAYS)
def test_half_days_close_at_13_et(d: date) -> None:
    assert cal.is_half_day(d)
    local = cal.close_utc(d).tz_convert("America/New_York")
    assert (local.hour, local.minute) == (13, 0)
    assert cal.session_minutes(d) == 210


def test_half_day_set_2024_2025_is_exact() -> None:
    found = [d for d in cal.sessions(date(2024, 1, 1), date(2025, 12, 31)) if cal.is_half_day(d)]
    assert found == HALF_DAYS


def test_regular_days_are_not_half_days() -> None:
    for d in (date(2024, 7, 2), date(2024, 11, 27), date(2025, 12, 23)):
        assert not cal.is_half_day(d)
        assert cal.session_minutes(d) == 390


@pytest.mark.parametrize(
    "d",
    [date(2024, 1, 1), date(2024, 3, 29), date(2024, 7, 4), date(2024, 12, 25), date(2025, 4, 18),
     date(2025, 6, 19), date(2025, 11, 27), date(2024, 3, 9), date(2024, 3, 10)],
)  # fmt: skip
def test_closed_days(d: date) -> None:
    assert not cal.is_session(d)
    with pytest.raises(cal.CalendarError):
        cal.close_utc(d)
    with pytest.raises(cal.CalendarError):
        cal.window_w0(d)


def test_session_counts_per_year() -> None:
    assert len(cal.sessions(date(2024, 1, 1), date(2024, 12, 31))) == 252
    assert len(cal.sessions(date(2025, 1, 1), date(2025, 12, 31))) == 250  # 2025-01-09 closed


def test_matches_exchange_calendars_directly() -> None:
    """Independent check: every 2023-2025 session instant equals the library schedule."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Series.values returning an ndarray that drops timezone")
        lib = xcals.get_calendar("XNYS", start="2023-01-01", end="2025-12-31").schedule
    lib_sessions = [ts.date() for ts in lib.index]
    ours = cal.sessions(date(2023, 1, 1), date(2025, 12, 31))
    assert ours == [d for d in lib_sessions if d not in cal.FORCED_CLOSURES]
    for d in ours[::7]:
        row = lib.loc[pd.Timestamp(d)]
        assert cal.open_utc(d) == row["open"]
        assert cal.close_utc(d) == row["close"]


# --- windows ---------------------------------------------------------------------------------------


def test_w0_boundaries_are_open_left_closed_right() -> None:
    d = date(2024, 3, 11)
    w = cal.window_w0(d)
    eps = timedelta(microseconds=1)
    assert cal.session_of_w0(w.start) is None  # close(prev) belongs to W2(prev), not W0(d)
    assert cal.session_of_w0(w.start + eps) == d
    assert cal.session_of_w0(w.end) == d
    assert cal.session_of_w0(w.end + eps) is None
    assert not w.contains(w.start)
    assert w.contains(w.end)


def test_w2_boundaries() -> None:
    d = date(2024, 11, 29)
    w = cal.window_w2(d)
    assert w == (utc("2024-11-27 21:00"), utc("2024-11-29 18:00"))
    eps = timedelta(microseconds=1)
    assert cal.session_of_w2(w.end) == d
    assert cal.session_of_w2(w.end + eps) == date(2024, 12, 2)
    assert cal.session_of_w2(w.start) == date(2024, 11, 27)


def test_weekend_news_maps_to_monday() -> None:
    sat = pd.Timestamp("2024-03-09 12:00", tz="America/New_York")
    assert cal.session_of_w0(sat) == date(2024, 3, 11)
    assert cal.session_of_w2(sat) == date(2024, 3, 11)


def test_intraday_after_cutoff_is_not_w0() -> None:
    t = pd.Timestamp("2024-03-11 10:30", tz="America/New_York")
    assert cal.session_of_w0(t) is None
    assert cal.session_of_w2(t) == date(2024, 3, 11)


def test_cutoff_override_for_robustness() -> None:
    d = date(2024, 3, 11)
    assert cal.window_w0(d, cutoff=time(8, 0)).end == utc("2024-03-11 12:00")
    assert cal.window_w0(d, cutoff=time(9, 30)).end == utc("2024-03-11 13:30")
    t = pd.Timestamp("2024-03-11 09:20", tz="America/New_York")
    assert cal.session_of_w0(t) is None
    assert cal.session_of_w0(t, cutoff=time(9, 30)) == d


def test_windows_tile_time() -> None:
    days = cal.sessions(date(2024, 1, 2), date(2025, 12, 31))
    for prev, d in itertools.pairwise(days):
        assert cal.window_w2(d).start == cal.window_w2(prev).end
        assert cal.window_w0(d).start == cal.close_utc(prev)
        assert cal.window_w0(d).start < cal.window_w0(d).end < cal.open_utc(d) < cal.close_utc(d)


def test_naive_timestamps_rejected() -> None:
    with pytest.raises(cal.CalendarError):
        cal.session_of_w0(datetime(2024, 3, 11, 13, 0))
    with pytest.raises(cal.CalendarError):
        cal.session_of_w2_series(pd.Series(pd.to_datetime(["2024-03-11 13:00"])))


def test_out_of_range_dates_raise() -> None:
    with pytest.raises(cal.CalendarError):
        cal.prev_session(date(2005, 1, 3))
    with pytest.raises(cal.CalendarError):
        cal.next_session(date(2030, 1, 3))


def test_vectorized_matches_scalar_with_nat_and_index() -> None:
    ts = pd.Series(
        pd.to_datetime(
            ["2024-03-08 21:00:00", "2024-03-08 21:00:01", "2024-03-11 13:15:00", "2024-03-11 13:15:01",
             "2024-03-11 20:00:00", None, "2025-01-09 15:00:00", "2024-11-29 18:00:01"],
            utc=True,
        ),
        index=list("abcdefgh"),
    )  # fmt: skip
    w0 = cal.session_of_w0_series(ts)
    w2 = cal.session_of_w2_series(ts)
    assert list(w0.index) == list("abcdefgh")
    assert w0.tolist() == [None, date(2024, 3, 11), date(2024, 3, 11), None, None, None,
                           date(2025, 1, 10), date(2024, 12, 2)]  # fmt: skip
    assert w2.tolist() == [date(2024, 3, 8), date(2024, 3, 11), date(2024, 3, 11), date(2024, 3, 11),
                           date(2024, 3, 11), None, date(2025, 1, 10), date(2024, 12, 2)]  # fmt: skip


def test_vectorized_accepts_other_timezones_and_units() -> None:
    ts = pd.Series(pd.to_datetime(["2024-03-11 09:15:00"]).tz_localize("America/New_York")).dt.as_unit("s")
    assert cal.session_of_w0_series(ts).tolist() == [date(2024, 3, 11)]


_LO = int(datetime(2019, 1, 2, tzinfo=UTC).timestamp())
_HI = int(datetime(2026, 12, 30, tzinfo=UTC).timestamp())


@settings(max_examples=300, deadline=None)
@given(st.lists(st.integers(min_value=_LO, max_value=_HI), min_size=1, max_size=40))
def test_property_windows_contain_their_instants(seconds: list[int]) -> None:
    ts = pd.Series(pd.to_datetime(np.array(seconds, dtype=np.int64), unit="s", utc=True))
    v0 = cal.session_of_w0_series(ts)
    v2 = cal.session_of_w2_series(ts)
    for t, s0, s2 in zip(ts, v0, v2, strict=True):
        assert cal.session_of_w0(t) == s0
        assert cal.session_of_w2(t) == s2
        assert s2 is not None and cal.window_w2(s2).contains(t)
        if s0 is not None:
            assert s0 == s2 and cal.window_w0(s0).contains(t)
        else:
            assert cal.d0_cutoff_utc(s2) < t <= cal.close_utc(s2)


def test_no_session_time_literals_outside_calendar() -> None:
    """CLAUDE.md A1: no literal "16:00" / "09:30" offsets anywhere in src/ except calendar.py."""
    pattern = re.compile(r"\b(16:00|09:30|9:30)\b")
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src").rglob("*.py")
        if p.name != "calendar.py" and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
