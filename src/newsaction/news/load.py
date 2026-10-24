"""PRD NA-02 S1 + S3 (assignment): read the NewsWitch corpus and time every article.

- Only the columns in ``LOAD_COLUMNS`` are read, with pyarrow. ``body`` is never read (size, and it may
  carry post-publication edits); ``read_year`` refuses it. ``summary`` is reduced to ``summary_present``
  as soon as it is read: the LLM summary is not a text field of this pipeline (PREREG §6.4).
- Memory: ``load_year_light`` reads everything but the text; ``read_text`` then streams title, snippet and
  summary for the selected rows only (member articles), batch by batch.
- Timing (PREREG §2.2–2.4): ``precision`` and ``t_avail`` from ``timeutil``; ``session_w0`` /
  ``session_w2`` from ``calendar`` (vectorized). ``naive_sessions`` gives the assignment that treats the
  raw stamp as exact, used only by the timing audit.
- Articles are kept when t_avail falls in [t_avail_start 00:00:00, t_avail_end 23:59:59] UTC
  (``configs/news.yaml``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from newsaction import calendar, io, timeutil
from newsaction.news import load_news_config
from newsaction.paths import Layout, resolve_layout

FORBIDDEN_COLUMNS: Final = frozenset({"body"})
VENDOR_FLAGS: Final = (
    "tag_scheduled",
    "tag_forward_looking",
    "tag_primary_source",
    "tag_quantified",
    "tag_rumor",
)
TEXT_COLUMNS: Final = ("title", "snippet", "summary")
LIGHT_COLUMNS: Final = (
    "id",
    "ticker",
    "date",
    "domain",
    "non_news",
    "parsing_allowed",
    "sentiment_direction",
    "sentiment_intensity",
    "tag_type",
    "tag_type2",
    *VENDOR_FLAGS,
    "tag_source",
    "event_id",
    "event_age_days",
)
LOAD_COLUMNS: Final = (*LIGHT_COLUMNS[:3], *TEXT_COLUMNS, *LIGHT_COLUMNS[3:])  # PRD NA-02 S1
_BATCH_ROWS: Final = 200_000
_ABSENT_SUMMARY: Final = ("", "nan", "none", "null")


class NewsLoadError(ValueError):
    """A forbidden column was requested or a news file is malformed."""


def news_file(year: int) -> str:
    return f"news_{year}.parquet"


def read_year(year: int, columns: Sequence[str], *, layout: Layout | None = None) -> pa.Table:
    """Columns of ``Data/news_<year>.parquet`` (fingerprinted in the manifest); never ``body``."""
    bad = FORBIDDEN_COLUMNS.intersection(columns)
    if bad:
        raise NewsLoadError(f"refusing to read {sorted(bad)} from the news corpus (PRD NA-02 constraints)")
    lay = resolve_layout(layout)
    io.record_input(news_file(year), layout=lay)
    return pq.read_table(lay.data / news_file(year), columns=list(columns))


def summary_present(summary: pa.ChunkedArray | pa.Array) -> pa.ChunkedArray | pa.Array:
    """True where the vendor summary is a non-empty string (null, "", "nan" count as absent)."""
    stripped = pc.utf8_lower(pc.utf8_trim_whitespace(summary))
    absent = pc.is_in(stripped, value_set=pa.array(_ABSENT_SUMMARY, type=pa.large_string()))
    return pc.and_(pc.is_valid(summary), pc.invert(pc.fill_null(absent, True)))


def add_timing(df: pd.DataFrame) -> pd.DataFrame:
    """Add ts_pub_utc, precision, t_avail, session_w0, session_w2 from the unix ``date`` column."""
    out = df.copy()
    seconds = out["date"]
    out["ts_pub_utc"] = pd.to_datetime(seconds, unit="s", utc=True)
    out["precision"] = timeutil.precision_class(seconds)
    out["t_avail"] = timeutil.availability(seconds)
    out["session_w0"] = calendar.session_of_w0_series(out["t_avail"])
    out["session_w2"] = calendar.session_of_w2_series(out["t_avail"])
    return out


def naive_sessions(ts_pub_utc: pd.Series) -> pd.DataFrame:
    """W0/W2 sessions if the raw stamp were exact (no §2.3 rule): the timing audit's comparison."""
    return pd.DataFrame(
        {
            "session_w0_naive": calendar.session_of_w0_series(ts_pub_utc),
            "session_w2_naive": calendar.session_of_w2_series(ts_pub_utc),
        },
        index=ts_pub_utc.index,
    )


def in_load_range(t_avail: pd.Series) -> pd.Series:
    """t_avail within [t_avail_start 00:00:00, t_avail_end 23:59:59] UTC (configs/news.yaml)."""
    cfg = load_news_config().load
    lo = pd.Timestamp(cfg.t_avail_start, tz="UTC")
    hi = pd.Timestamp(cfg.t_avail_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return (t_avail >= lo) & (t_avail <= hi)


def load_year_light(year: int, *, layout: Layout | None = None) -> pd.DataFrame:
    """One year without the text columns, timed, in the load range; ``row`` = row number in the file."""
    table = read_year(year, LIGHT_COLUMNS, layout=layout)
    df = add_timing(table.to_pandas())
    df["row"] = np.arange(len(df), dtype=np.int64)
    df["file_year"] = year
    return df.loc[in_load_range(df["t_avail"])].reset_index(drop=True)


def read_text(year: int, rows: npt.NDArray[np.int64], *, layout: Layout | None = None) -> pd.DataFrame:
    """title, snippet and summary_present of the given file rows (ascending), streamed in batches."""
    if len(rows) and np.any(np.diff(rows) <= 0):
        raise NewsLoadError("rows must be strictly ascending")
    lay = resolve_layout(layout)
    io.record_input(news_file(year), layout=lay)
    pf = pq.ParquetFile(lay.data / news_file(year))
    parts: list[pd.DataFrame] = []
    offset = 0
    for batch in pf.iter_batches(batch_size=_BATCH_ROWS, columns=list(TEXT_COLUMNS)):
        lo, hi = np.searchsorted(rows, [offset, offset + batch.num_rows])
        if hi > lo:
            sub = batch.take(pa.array(rows[lo:hi] - offset))
            parts.append(
                pd.DataFrame(
                    {
                        "title": sub.column("title").to_pandas(),
                        "snippet": sub.column("snippet").to_pandas(),
                        "summary_present": summary_present(sub.column("summary")).to_pandas(),
                    }
                )
            )
        offset += batch.num_rows
    if not parts:
        return pd.DataFrame(
            {
                "title": pd.Series(dtype="str"),
                "snippet": pd.Series(dtype="str"),
                "summary_present": pd.Series(dtype=bool),
            }
        )
    out = pd.concat(parts, ignore_index=True)
    if len(out) != len(rows):
        raise NewsLoadError(f"news_{year}: asked for {len(rows)} rows, read {len(out)}")
    return out
