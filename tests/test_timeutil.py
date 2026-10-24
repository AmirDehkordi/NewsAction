"""Timestamp precision and availability (PREREG §2.2–2.3; PRD NA-00 AC3)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from newsaction.timeutil import availability, precision_class

DAY, HOUR, MINUTE = 86_400, 3_600, 60
MAX_S = 4_102_444_800  # 2100-01-01


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


@pytest.mark.parametrize(
    ("unix", "cls", "expected"),
    [
        (1735689600, "date_only", "2025-01-01 23:59:59"),  # 2025-01-01 00:00:00Z
        (1735693200, "hour", "2025-01-01 01:59:59"),  # 01:00:00Z
        (1735693260, "minute", "2025-01-01 01:01:59"),  # 01:01:00Z
        (1735693261, "exact", "2025-01-01 01:01:01"),  # 01:01:01Z
        (1709856000, "date_only", "2024-03-08 23:59:59"),  # date-only stamp on a session day
        (1709942399, "exact", "2024-03-08 23:59:59"),  # last second of a day is exact
    ],
)
def test_golden_cases(unix: int, cls: str, expected: str) -> None:
    assert precision_class(unix) == cls
    assert availability(unix) == ts(expected)
    assert availability(unix).tzinfo is not None


def test_date_only_maps_to_end_of_same_utc_date() -> None:
    a = availability(1735689600)
    assert a.date() == datetime(2025, 1, 1, tzinfo=UTC).date()
    assert (a.hour, a.minute, a.second) == (23, 59, 59)


def test_vectorized_series_keeps_index_and_nan() -> None:
    s = pd.Series([1735689600, 1735693200, np.nan, 1735693261.0], index=[7, 8, 9, 10])
    out = availability(s)
    assert list(out.index) == [7, 8, 9, 10]
    assert str(out.dtype) == "datetime64[ns, UTC]"
    assert out[7] == ts("2025-01-01 23:59:59")
    assert out[8] == ts("2025-01-01 01:59:59")
    assert pd.isna(out[9])
    assert out[10] == ts("2025-01-01 01:01:01")
    assert precision_class(s).tolist() == ["date_only", "hour", None, "exact"]


def test_numpy_array_input() -> None:
    out = availability(np.array([1735689600, 1735693260], dtype=np.int64))
    assert out.tolist() == [ts("2025-01-01 23:59:59"), ts("2025-01-01 01:01:59")]


@pytest.mark.parametrize("bad", [1.5, "1735689600", True, None])
def test_scalar_rejects_non_integers(bad: object) -> None:
    with pytest.raises(TypeError):
        availability(bad)  # type: ignore[call-overload]


def test_series_rejects_fractional_seconds() -> None:
    with pytest.raises(ValueError, match="integral"):
        availability(pd.Series([1735689600.5]))


# --- properties ------------------------------------------------------------------------------------

date_only = st.integers(0, MAX_S // DAY).map(lambda d: d * DAY)
hour = st.integers(0, MAX_S // HOUR).filter(lambda h: (h * HOUR) % DAY).map(lambda h: h * HOUR)
minute = st.integers(0, MAX_S // MINUTE).filter(lambda m: (m * MINUTE) % HOUR).map(lambda m: m * MINUTE)
exact = st.integers(0, MAX_S).filter(lambda s: s % MINUTE)


@given(date_only)
def test_property_date_only(s: int) -> None:
    assert precision_class(s) == "date_only"
    a = availability(s)
    published = pd.Timestamp(s, unit="s", tz="UTC")
    assert a.date() == published.date()
    assert (a.hour, a.minute, a.second) == (23, 59, 59)
    assert a - published == pd.Timedelta(seconds=DAY - 1)


@given(hour)
def test_property_hour(s: int) -> None:
    assert precision_class(s) == "hour"
    assert availability(s) == pd.Timestamp(s + 3599, unit="s", tz="UTC")


@given(minute)
def test_property_minute(s: int) -> None:
    assert precision_class(s) == "minute"
    assert availability(s) == pd.Timestamp(s + 59, unit="s", tz="UTC")


@given(exact)
def test_property_exact(s: int) -> None:
    assert precision_class(s) == "exact"
    assert availability(s) == pd.Timestamp(s, unit="s", tz="UTC")


@given(st.integers(0, MAX_S))
def test_property_never_before_publication_and_within_a_day(s: int) -> None:
    published = pd.Timestamp(s, unit="s", tz="UTC")
    a = availability(s)
    assert a >= published
    assert a - published < pd.Timedelta(days=1)
    assert a.date() == published.date()  # never pushed into the next UTC day


@settings(max_examples=200)
@given(st.lists(st.one_of(date_only, hour, minute, exact), min_size=1, max_size=50))
def test_property_vectorized_equals_scalar(values: list[int]) -> None:
    vec = availability(pd.Series(values, dtype="int64"))
    cls = precision_class(pd.Series(values, dtype="int64"))
    assert vec.tolist() == [availability(v) for v in values]
    assert cls.tolist() == [precision_class(v) for v in values]
