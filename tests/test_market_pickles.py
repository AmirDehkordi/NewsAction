"""Pickle -> parquet conversion (PRD NA-00 S11, AC8).

Unit tests use synthetic dicts. The integration test compares per-series / per-ticker row counts of
the real Data/market pickles with work/market/*.parquet (skipped when either is absent).
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd
import pytest

import convert_pickles as cp
from newsaction import io
from newsaction.paths import DATA, WORK


def test_fred_daily_long_keeps_every_row() -> None:
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    out = cp.fred_daily_long(
        {"DFF": pd.Series([5.33, np.nan], index=idx), "DGS2": pd.Series([4.3], index=idx[:1])}
    )
    assert list(out.columns) == ["series_id", "date", "value"]
    assert Counter(out["series_id"]) == {"DFF": 2, "DGS2": 1}
    assert out["value"].isna().sum() == 1


def test_cpi_vintages_long_converts_nat_to_nan() -> None:
    df = pd.DataFrame(
        {
            "realtime_start": pd.to_datetime(["2024-02-13", "2024-03-12"]),
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "value": pd.Series([310.3, pd.NaT], dtype=object),
        }
    )
    out = cp.cpi_vintages_long({"CPIAUCSL": df})
    assert list(out.columns) == ["series_id", "date", "value", "realtime_start"]
    assert out["value"].iloc[0] == 310.3 and np.isnan(out["value"].iloc[1])
    with pytest.raises(ValueError, match="missing columns"):
        cp.cpi_vintages_long({"X": df.drop(columns="value")})


def test_earnings_and_shares_skip_none() -> None:
    ix = pd.DatetimeIndex(pd.to_datetime(["2024-02-27 16:00", "2024-05-29 16:00", "2024-05-29 16:00"]))
    e = cp.earnings_long({"A": ix, "B": None})
    assert e.shape == (3, 2) and list(e.columns) == ["ticker", "earnings_ts"]
    s = cp.shares_long(
        {"A": pd.Series([10, 11], index=pd.to_datetime(["2024-01-02", "2024-01-03"])), "B": None}
    )
    assert s["shares"].dtype == np.int64 and list(s.columns) == ["ticker", "date", "shares"]


def _counts(obj: dict[str, object]) -> Counter[str]:
    return Counter({k: len(v) for k, v in obj.items() if v is not None and len(v)})  # type: ignore[arg-type]


CASES = [
    ("fred_daily.pkl", "fred_daily.parquet", "series_id"),
    ("fred_releases.pkl", "cpi_vintages.parquet", "series_id"),
    ("earnings_dates.pkl", "earnings_dates.parquet", "ticker"),
    ("shares.pkl", "shares.parquet", "ticker"),
]


@pytest.mark.parametrize(("pkl", "parquet", "key"), CASES)
def test_row_counts_equal_pickles(pkl: str, parquet: str, key: str) -> None:
    src, dest = DATA / "market" / pkl, WORK / "market" / parquet
    if not (src.exists() and dest.exists()):
        pytest.skip("Data/ pickles or converted parquet not present")
    obj = pd.read_pickle(src)
    out = io.read_parquet(f"market/{parquet}")  # verifies the manifest hash
    assert Counter(out[key].tolist()) == _counts(obj)
    assert len(out) == sum(_counts(obj).values())


def test_market_prices_copy_matches_input() -> None:
    dest = WORK / "market" / "market_prices.parquet"
    if not dest.exists():
        pytest.skip("converted parquet not present")
    m = io.load_manifest()
    art = m["artifacts"]["work/market/market_prices.parquet"]
    assert art["sha256"] == m["inputs"]["Data/market/market_prices.parquet"]["sha256"]
    assert art["sha256"] == io.sha256_file(dest)
