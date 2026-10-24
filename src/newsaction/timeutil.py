"""Publication-timestamp precision and availability time, PREREG §2.2–2.3.

``date`` in the news files is unix seconds (UTC). Coarse stamps are moved to the end of the period
they may stand for, so an article is never used before it could have been read:

  class      condition (s = unix seconds)             t_avail
  date_only  s mod 86400 == 0                         23:59:59 UTC of that date
  hour       s mod 3600 == 0, not date_only           s + 3599
  minute     s mod 60 == 0, not hour                  s + 59
  exact      otherwise                                s

Both functions accept a scalar or a pandas Series / numpy array; one code path serves both.
"""

from __future__ import annotations

from typing import Final, Literal, overload

import numpy as np
import numpy.typing as npt
import pandas as pd

PrecisionClass = Literal["date_only", "hour", "minute", "exact"]
PRECISION_CLASSES: Final[tuple[PrecisionClass, ...]] = ("date_only", "hour", "minute", "exact")

DAY: Final = 86_400
HOUR: Final = 3_600
MINUTE: Final = 60

_DATE_ONLY, _HOUR, _MINUTE, _EXACT = 0, 1, 2, 3
_MISSING: Final = -1

Scalar = int | np.integer
ArrayLike = pd.Series | npt.NDArray[np.integer] | npt.NDArray[np.floating]


def _as_int_seconds(values: ArrayLike) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.bool_]]:
    """int64 seconds and a missing mask; rejects non-integral values."""
    arr = np.asarray(values)
    if arr.dtype.kind in "iu":
        return arr.astype(np.int64), np.zeros(arr.shape, dtype=bool)
    if arr.dtype.kind == "f":
        missing = np.isnan(arr)
        filled = np.where(missing, 0.0, arr)
        if not np.all(filled == np.floor(filled)):
            raise ValueError("unix seconds must be integral")
        return filled.astype(np.int64), missing
    raise TypeError(f"unix seconds must be integers, got dtype {arr.dtype}")


def _class_codes(s: npt.NDArray[np.int64]) -> npt.NDArray[np.int8]:
    codes = np.full(s.shape, _EXACT, dtype=np.int8)
    codes[s % MINUTE == 0] = _MINUTE
    codes[s % HOUR == 0] = _HOUR
    codes[s % DAY == 0] = _DATE_ONLY
    return codes


def _availability_seconds(s: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    codes = _class_codes(s)
    out = s.copy()
    out = np.where(codes == _DATE_ONLY, s - s % DAY + DAY - 1, out)  # 23:59:59 UTC of that date
    out = np.where(codes == _HOUR, s + HOUR - 1, out)  # end of that hour
    out = np.where(codes == _MINUTE, s + MINUTE - 1, out)  # end of that minute
    return out


def _check_scalar(unix_seconds: object) -> int:
    if isinstance(unix_seconds, bool) or not isinstance(unix_seconds, int | np.integer):
        raise TypeError(f"unix seconds must be an integer, got {type(unix_seconds).__name__}")
    return int(unix_seconds)


@overload
def precision_class(unix_seconds: Scalar) -> PrecisionClass: ...
@overload
def precision_class(unix_seconds: ArrayLike) -> pd.Series: ...
def precision_class(unix_seconds: Scalar | ArrayLike) -> PrecisionClass | pd.Series:
    """Precision class of a publication timestamp (PREREG §2.2); NaN maps to None in a Series."""
    if not isinstance(unix_seconds, pd.Series | np.ndarray):
        s = np.array([_check_scalar(unix_seconds)], dtype=np.int64)
        return PRECISION_CLASSES[int(_class_codes(s)[0])]
    s, missing = _as_int_seconds(unix_seconds)
    codes = np.where(missing, _MISSING, _class_codes(s))
    labels = np.array([*PRECISION_CLASSES, None], dtype=object)
    index = unix_seconds.index if isinstance(unix_seconds, pd.Series) else None
    return pd.Series(labels[codes], index=index, dtype=object, name="precision_class")


@overload
def availability(unix_seconds: Scalar) -> pd.Timestamp: ...
@overload
def availability(unix_seconds: ArrayLike) -> pd.Series: ...
def availability(unix_seconds: Scalar | ArrayLike) -> pd.Timestamp | pd.Series:
    """Availability instant t_avail (tz-aware UTC) of a publication timestamp (PREREG §2.3)."""
    if not isinstance(unix_seconds, pd.Series | np.ndarray):
        s = np.array([_check_scalar(unix_seconds)], dtype=np.int64)
        return pd.Timestamp(int(_availability_seconds(s)[0]), unit="s", tz="UTC")
    s, missing = _as_int_seconds(unix_seconds)
    values = _availability_seconds(s).astype("datetime64[s]").astype("datetime64[ns]")
    values[missing] = np.datetime64("NaT", "ns")
    utc = pd.DatetimeIndex(values).tz_localize("UTC")
    index = unix_seconds.index if isinstance(unix_seconds, pd.Series) else None
    return pd.Series(utc.array, index=index, name="t_avail")
