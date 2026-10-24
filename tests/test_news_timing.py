"""PRD NA-02 AC1: timestamp rules through the news pipeline (PREREG §2.2–2.4).

Mutations the verifier applies to ``timeutil._availability_seconds``:
- remove the date_only branch  -> test_date_only_fixture RED;
- remove the hour branch       -> test_hour_fixture RED.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from newsaction.news import load


def _timed(stamp: str) -> pd.Series:
    seconds = int(pd.Timestamp(stamp).timestamp())
    return load.add_timing(pd.DataFrame({"date": [seconds]})).iloc[0]


def test_date_only_fixture() -> None:
    """(a) 2025-03-10 00:00:00Z: available 23:59:59Z -> W0 and W2 of 2025-03-11, never 2025-03-10."""
    row = _timed("2025-03-10T00:00:00Z")
    assert row["precision"] == "date_only"
    assert row["t_avail"] == pd.Timestamp("2025-03-10T23:59:59Z")
    assert row["session_w0"] == date(2025, 3, 11)
    assert row["session_w2"] == date(2025, 3, 11)


def test_hour_fixture() -> None:
    """(b) 13:00:00Z (09:00 EDT): available 13:59:59Z, after the 13:15Z cutoff, before the 20:00Z close."""
    row = _timed("2025-03-10T13:00:00Z")
    assert row["precision"] == "hour"
    assert row["t_avail"] == pd.Timestamp("2025-03-10T13:59:59Z")
    assert row["session_w0"] is None
    assert row["session_w2"] == date(2025, 3, 10)


@pytest.mark.parametrize(
    ("stamp", "precision", "avail"),
    [
        # the AC's "exact" 12:30:00Z is minute-precision under §2.2 (mm:ss = 30:00, ss = 00)
        ("2025-03-10T12:30:00Z", "minute", "2025-03-10T12:30:59Z"),
        ("2025-03-10T12:30:17Z", "exact", "2025-03-10T12:30:17Z"),
    ],
)
def test_pre_cutoff_fixture(stamp: str, precision: str, avail: str) -> None:
    """(c) before 09:15 EDT: W0 and W2 of the same session."""
    row = _timed(stamp)
    assert row["precision"] == precision
    assert row["t_avail"] == pd.Timestamp(avail)
    assert row["session_w0"] == row["session_w2"] == date(2025, 3, 10)


def test_naive_assignment_differs_only_for_coarse_stamps() -> None:
    stamps = ["2025-03-10T00:00:00Z", "2025-03-10T13:00:00Z", "2025-03-10T12:30:17Z"]
    df = load.add_timing(pd.DataFrame({"date": [int(pd.Timestamp(s).timestamp()) for s in stamps]}))
    naive = load.naive_sessions(df["ts_pub_utc"])
    # date-only: naively a D0 article of 2025-03-10 (20:00 EDT on 03-09); hour: naively before the cutoff
    assert naive["session_w0_naive"].tolist() == [date(2025, 3, 10), date(2025, 3, 10), date(2025, 3, 10)]
    assert df["session_w0"].tolist() == [date(2025, 3, 11), None, date(2025, 3, 10)]


def test_weekend_date_only_goes_to_monday() -> None:
    row = _timed("2025-03-08T00:00:00Z")  # Saturday
    assert row["session_w0"] == row["session_w2"] == date(2025, 3, 10)


def test_load_range_bounds() -> None:
    ts = pd.Series(
        pd.to_datetime(
            ["2023-06-30T23:59:59Z", "2023-07-01T00:00:00Z", "2026-07-31T23:59:59Z", "2026-08-01T00:00:00Z"],
            utc=True,
        )
    )
    assert load.in_load_range(ts).tolist() == [False, True, True, False]


def test_body_is_never_read() -> None:
    assert "body" not in load.LOAD_COLUMNS
    with pytest.raises(load.NewsLoadError, match="body"):
        load.read_year(2025, ["id", "body"])
