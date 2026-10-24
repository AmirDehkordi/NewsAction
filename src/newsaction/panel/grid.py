"""Session x symbol grid shared by the panel modules.

Wide frames have a ``DatetimeIndex`` of XNYS session dates (tz-naive midnight, one row per session
from ``newsaction.calendar``) and integer ``symbol_id`` columns. A missing price is NaN, never a
dropped row, so ``shift(k)`` always moves by k sessions.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction import calendar

FloatArray = npt.NDArray[np.float64]


def session_index(start: date, end: date) -> pd.DatetimeIndex:
    """All XNYS sessions in [start, end] as a tz-naive DatetimeIndex named ``session``."""
    return pd.DatetimeIndex([pd.Timestamp(d) for d in calendar.sessions(start, end)], name="session")


def to_dates(index: Iterable[pd.Timestamp]) -> list[date]:
    return [pd.Timestamp(t).date() for t in index]


def wide(
    long: pd.DataFrame,
    value: str,
    sessions: pd.DatetimeIndex,
    symbols: Sequence[int] | Sequence[str],
    *,
    session_col: str = "session",
    symbol_col: str = "symbol_id",
) -> pd.DataFrame:
    """Pivot a long (session, symbol, value) frame onto the grid; rows off the calendar are dropped."""
    df = long[[session_col, symbol_col, value]].copy()
    df[session_col] = pd.to_datetime(df[session_col]).dt.normalize()
    piv = df.pivot_table(index=session_col, columns=symbol_col, values=value, aggfunc="first")
    out = piv.reindex(index=sessions, columns=list(symbols)).astype("float64")
    out.index.name, out.columns.name = "session", "symbol_id"
    return out


def lag(frame: pd.DataFrame, k: int = 1) -> pd.DataFrame:
    """Value of the statistic computed through row t-k, placed on row t (k sessions back)."""
    return frame.shift(k)


def empty_like(frame: pd.DataFrame, fill: float = np.nan) -> pd.DataFrame:
    return pd.DataFrame(fill, index=frame.index, columns=frame.columns, dtype="float64")


def to_long(frames: dict[str, pd.DataFrame], mask: pd.DataFrame | None = None) -> pd.DataFrame:
    """Stack same-shaped wide frames into a long frame (session, symbol_id, <names>).

    ``mask`` (bool, same shape) selects the rows kept; by default every grid cell is kept.
    """
    first = next(iter(frames.values()))
    n_s, n_c = first.shape
    sess = np.repeat(first.index.to_numpy(), n_c)
    sym = np.tile(first.columns.to_numpy(dtype="int64"), n_s)
    keep = np.ones(n_s * n_c, dtype=bool) if mask is None else mask.to_numpy(dtype=bool).ravel()
    data: dict[str, object] = {"session": sess[keep], "symbol_id": sym[keep]}
    for name, frame in frames.items():
        if frame.shape != first.shape:
            raise ValueError(f"{name}: shape {frame.shape} differs from {first.shape}")
        data[name] = frame.to_numpy().ravel()[keep]
    return pd.DataFrame(data)
