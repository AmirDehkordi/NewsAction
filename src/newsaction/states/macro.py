"""Scheduled macro releases for the market block (PREREG §6.10; PRD NA-04 S2).

- **CPI.** A release date is a vintage date (``realtime_start``) of the configured ALFRED series that adds a
  new reference month (``work/market/cpi_vintages.parquet``). Seasonal-factor re-vintages, which add no
  month, are not releases.
- **FOMC.** Policy statement dates from ``configs/macro_calendar.yaml`` (the Federal Reserve's published
  calendar, URL cited there).

Both schedules are announced in advance, so a session's flags are ``static`` inputs (registered as
``macro_cpi_today`` / ``macro_fomc_today``). The state says only that a release is scheduled that day.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from newsaction.config import load_yaml
from newsaction.states import MACRO_PATH


@dataclass(frozen=True)
class MacroCalendar:
    cpi_series: str
    cpi_words: str
    fomc_words: str
    none_words: str
    fomc_dates: frozenset[date]

    def words(self, cpi_today: bool, fomc_today: bool) -> str:
        parts = [w for flag, w in ((cpi_today, self.cpi_words), (fomc_today, self.fomc_words)) if flag]
        return "; ".join(parts) if parts else self.none_words


@functools.cache
def _load(path: Path, mtime_ns: int) -> MacroCalendar:
    raw = load_yaml(path)
    dates = [d if isinstance(d, date) else date.fromisoformat(str(d)) for d in raw["fomc"]["statement_dates"]]
    if dates != sorted(set(dates)):
        raise ValueError("fomc.statement_dates must be sorted and unique")
    return MacroCalendar(
        cpi_series=str(raw["cpi"]["series_id"]),
        cpi_words=str(raw["cpi"]["words"]),
        fomc_words=str(raw["fomc"]["words"]),
        none_words=str(raw["none_words"]),
        fomc_dates=frozenset(dates),
    )


def load_macro(path: Path = MACRO_PATH) -> MacroCalendar:
    return _load(path, path.stat().st_mtime_ns)


def cpi_release_dates(vintages: pd.DataFrame, series_id: str) -> frozenset[date]:
    """Vintage dates of ``series_id`` whose vintage adds a reference month not in any earlier vintage."""
    v = vintages.loc[vintages["series_id"] == series_id, ["date", "realtime_start"]].dropna()
    latest = v.groupby("realtime_start")["date"].max().sort_index()
    new_month = latest > latest.cummax().shift(1)
    new_month.iloc[:1] = True
    return frozenset(pd.Timestamp(d).date() for d in latest.index[new_month.to_numpy()])


def session_flags(sessions: Iterable[date], cpi_dates: frozenset[date], cal: MacroCalendar) -> pd.DataFrame:
    """``session``, ``macro_cpi_today``, ``macro_fomc_today`` for each session."""
    days = list(sessions)
    return pd.DataFrame(
        {
            "session": days,
            "macro_cpi_today": [d in cpi_dates for d in days],
            "macro_fomc_today": [d in cal.fomc_dates for d in days],
        }
    )
