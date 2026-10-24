"""NYSE sessions and the decision windows of PREREG §2.

Conventions:
- session dates are exchange-local ``datetime.date``;
- every instant is a tz-aware UTC ``pd.Timestamp`` (inputs may be in any timezone, never naive);
- regular and early open/close instants come from ``exchange_calendars`` (pinned in pyproject); the
  09:15 cutoff and the 10:00 D1 time come from ``configs/project.yaml`` and are converted with the
  America/New_York zone rules, so no UTC offset is ever hard-coded.

Windows are half-open on the left: W0(s) = (close(prev(s)), 09:15 ET of s] and
W2(s) = (close(prev(s)), close(s)] (PREREG §2.4).
"""

from __future__ import annotations

import bisect
import functools
import warnings
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final, NamedTuple
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.config import load_project

# Unscheduled full-day closures enforced whatever the exchange_calendars release says. They are
# already closed in exchange_calendars 4.13.2; the list protects the golden cases from version drift.
#   2025-01-09: National Day of Mourning for President Carter (NYSE closed).
FORCED_CLOSURES: Final[tuple[date, ...]] = (date(2025, 1, 9),)

_NAT: Final = np.iinfo(np.int64).min


class CalendarError(ValueError):
    """Bad calendar input: not a session, outside the table, or a naive timestamp."""


class Window(NamedTuple):
    """A (start, end] interval of UTC instants."""

    start: pd.Timestamp
    end: pd.Timestamp

    def contains(self, ts: datetime) -> bool:
        t = _to_utc(ts)
        return bool(self.start < t <= self.end)


@dataclass(frozen=True)
class _Table:
    tz: ZoneInfo
    sessions: tuple[date, ...]
    index: dict[date, int]
    opens: npt.NDArray[np.int64]  # UTC ns
    closes: npt.NDArray[np.int64]  # UTC ns
    early_closes: frozenset[date]


def _ns(values: pd.Series) -> npt.NDArray[np.int64]:
    """UTC nanoseconds of a tz-aware datetime Series (NaT -> int64 min)."""
    utc = values.dt.tz_convert("UTC").dt.as_unit("ns").dt.tz_localize(None)
    return np.asarray(utc.to_numpy(dtype="datetime64[ns]").view(np.int64), dtype=np.int64)


@functools.cache
def _table() -> _Table:
    cfg = load_project()
    with warnings.catch_warnings():
        # exchange_calendars 4.13.2 calls Series.values on tz-aware data, deprecated in pandas 3.1.
        warnings.filterwarnings("ignore", message="Series.values returning an ndarray that drops timezone")
        cal = xcals.get_calendar(
            cfg.exchange, start=cfg.calendar.start.isoformat(), end=cfg.calendar.end.isoformat()
        )
    sched = cal.schedule
    keep = ~sched.index.isin(pd.DatetimeIndex([pd.Timestamp(d) for d in FORCED_CLOSURES]))
    sched = sched[keep]
    sessions = tuple(ts.date() for ts in sched.index)
    early = frozenset(ts.date() for ts in cal.early_closes) & frozenset(sessions)
    return _Table(
        tz=ZoneInfo(cfg.timezone),
        sessions=sessions,
        index={d: i for i, d in enumerate(sessions)},
        opens=_ns(sched["open"]),
        closes=_ns(sched["close"]),
        early_closes=early,
    )


def _to_utc(ts: datetime) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        raise CalendarError(f"naive timestamp {ts!r}: instants must be tz-aware")
    return t.tz_convert("UTC")


def _utc(ns: int) -> pd.Timestamp:
    return pd.Timestamp(ns, unit="ns", tz="UTC")


def _idx(d: date) -> int:
    tab = _table()
    try:
        return tab.index[d]
    except KeyError:
        raise CalendarError(f"{d} is not an {load_project().exchange} session") from None


def _check_range(d: date) -> None:
    tab = _table()
    if not tab.sessions[0] <= d <= tab.sessions[-1]:
        raise CalendarError(f"{d} is outside the calendar table {tab.sessions[0]}..{tab.sessions[-1]}")


def _local_instant(d: date, t: time) -> pd.Timestamp:
    """The instant ``t`` (America/New_York wall time) on date ``d``, in UTC."""
    return pd.Timestamp(datetime.combine(d, t, tzinfo=_table().tz)).tz_convert("UTC")


# --- sessions -------------------------------------------------------------------------------------


def sessions(start: date, end: date) -> list[date]:
    """Sessions with start <= session <= end."""
    tab = _table()
    lo = bisect.bisect_left(tab.sessions, start)
    hi = bisect.bisect_right(tab.sessions, end)
    return list(tab.sessions[lo:hi])


def is_session(d: date) -> bool:
    _check_range(d)
    return d in _table().index


def prev_session(d: date) -> date:
    """The last session strictly before ``d`` (``d`` need not be a session)."""
    _check_range(d)
    tab = _table()
    i = bisect.bisect_left(tab.sessions, d)
    if i == 0:
        raise CalendarError(f"no session before {d} in the calendar table")
    return tab.sessions[i - 1]


def next_session(d: date) -> date:
    """The first session strictly after ``d`` (``d`` need not be a session)."""
    _check_range(d)
    tab = _table()
    i = bisect.bisect_right(tab.sessions, d)
    if i == len(tab.sessions):
        raise CalendarError(f"no session after {d} in the calendar table")
    return tab.sessions[i]


def open_utc(d: date) -> pd.Timestamp:
    return _utc(int(_table().opens[_idx(d)]))


def close_utc(d: date) -> pd.Timestamp:
    """Official close (13:00 ET on half days)."""
    return _utc(int(_table().closes[_idx(d)]))


def is_half_day(d: date) -> bool:
    _idx(d)
    return d in _table().early_closes


def session_minutes(d: date) -> int:
    """Length of the regular session in minutes (390 on a full day, 210 on a half day)."""
    tab = _table()
    i = _idx(d)
    return int((tab.closes[i] - tab.opens[i]) // 60_000_000_000)


def d0_cutoff_utc(d: date, cutoff: time | None = None) -> pd.Timestamp:
    """D0 decision instant: 09:15 ET of session ``d`` (``cutoff`` overrides it for PREREG §11.6)."""
    _idx(d)
    return _local_instant(d, load_project().d0_cutoff if cutoff is None else cutoff)


def d1_utc(d: date) -> pd.Timestamp:
    """D1 decision instant: 10:00 ET of session ``d``."""
    _idx(d)
    return _local_instant(d, load_project().d1_time)


# --- windows --------------------------------------------------------------------------------------


def window_w0(d: date, cutoff: time | None = None) -> Window:
    """W0(d) = (close(prev(d)), 09:15 ET of d]: the news window of D0 (PREREG §2.4)."""
    return Window(close_utc(prev_session(d)), d0_cutoff_utc(d, cutoff))


def window_w2(d: date) -> Window:
    """W2(d) = (close(prev(d)), close(d)]: the news window of D2 (PREREG §2.4)."""
    _idx(d)
    return Window(close_utc(prev_session(d)), close_utc(d))


def _cutoffs_ns(cutoff: time | None) -> npt.NDArray[np.int64]:
    t = load_project().d0_cutoff if cutoff is None else cutoff
    return _cutoffs_ns_cached(t)


@functools.cache
def _cutoffs_ns_cached(t: time) -> npt.NDArray[np.int64]:
    tab = _table()
    return np.array([_local_instant(d, t).value for d in tab.sessions], dtype=np.int64)


def _locate(ns: npt.NDArray[np.int64], cutoff: time | None, w0: bool) -> npt.NDArray[np.int64]:
    """Index of the session whose W2 (or W0) contains each instant; -1 if none."""
    tab = _table()
    idx = np.searchsorted(tab.closes, ns, side="left").astype(np.int64)
    valid = (ns != _NAT) & (idx > 0) & (idx < len(tab.sessions))
    if w0:
        cut = _cutoffs_ns(cutoff)
        safe = np.where(valid, idx, 0)
        valid &= ns <= cut[safe]
    return np.where(valid, idx, -1)


def session_of_w2(ts: datetime) -> date | None:
    """The session s with ts in W2(s); None outside the calendar table."""
    i = int(_locate(np.array([_to_utc(ts).value], dtype=np.int64), None, w0=False)[0])
    return None if i < 0 else _table().sessions[i]


def session_of_w0(ts: datetime, cutoff: time | None = None) -> date | None:
    """The session s with ts in W0(s); None if ts falls after the cutoff and up to the close."""
    i = int(_locate(np.array([_to_utc(ts).value], dtype=np.int64), cutoff, w0=True)[0])
    return None if i < 0 else _table().sessions[i]


def _series_ns(ts: pd.Series) -> npt.NDArray[np.int64]:
    if not isinstance(ts.dtype, pd.DatetimeTZDtype):
        raise CalendarError(f"expected a tz-aware datetime Series, got dtype {ts.dtype}")
    return _ns(ts)


def _dates_from_idx(idx: npt.NDArray[np.int64], index: pd.Index) -> pd.Series:
    table = np.array((*_table().sessions, None), dtype=object)
    return pd.Series(table[idx], index=index, dtype=object)  # idx == -1 picks the trailing None


def session_of_w2_series(ts: pd.Series) -> pd.Series:
    """Vectorized ``session_of_w2``: object Series of ``date`` or None, aligned with ``ts``."""
    return _dates_from_idx(_locate(_series_ns(ts), None, w0=False), ts.index)


def session_of_w0_series(ts: pd.Series, cutoff: time | None = None) -> pd.Series:
    """Vectorized ``session_of_w0``: object Series of ``date`` or None, aligned with ``ts``."""
    return _dates_from_idx(_locate(_series_ns(ts), cutoff, w0=True), ts.index)
