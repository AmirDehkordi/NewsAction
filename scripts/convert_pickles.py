"""NA-00 S11: convert the Data/market pickles (they need pandas >= 3) to long-format parquet in work/market/.

    uv run python scripts/convert_pickles.py

Outputs (registered in work/MANIFEST.json through newsaction.io; inputs fingerprinted):
    fred_daily.parquet      series_id, date, value                  <- fred_daily.pkl
    cpi_vintages.parquet    series_id, date, value, realtime_start  <- fred_releases.pkl
    earnings_dates.parquet  ticker, earnings_ts                     <- earnings_dates.pkl
    shares.parquet          ticker, date, shares                    <- shares.pkl
    market_prices.parquet   byte-for-byte copy of Data/market/market_prices.parquet

Every source row is kept (NaN values and duplicate stamps included), so row counts equal the
pickles' per series / ticker. Values are not transformed.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from newsaction import io

PRODUCER = "scripts/convert_pickles.py (NA-00 S11)"


def fred_daily_long(obj: Mapping[str, pd.Series]) -> pd.DataFrame:
    parts = [
        pd.DataFrame(
            {"series_id": sid, "date": pd.DatetimeIndex(s.index), "value": s.to_numpy(dtype="float64")}
        )
        for sid, s in obj.items()
    ]
    return pd.concat(parts, ignore_index=True)


def _float_or_nan(v: object) -> float:
    return np.nan if v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)) else float(v)  # type: ignore[arg-type]


def cpi_vintages_long(obj: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for sid, df in obj.items():
        missing = {"realtime_start", "date", "value"} - set(df.columns)
        if missing:
            raise ValueError(f"{sid}: missing columns {sorted(missing)}")
        parts.append(
            pd.DataFrame(
                {
                    "series_id": sid,
                    "date": pd.DatetimeIndex(df["date"]),
                    "value": np.array([_float_or_nan(v) for v in df["value"]], dtype="float64"),
                    "realtime_start": pd.DatetimeIndex(df["realtime_start"]),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def earnings_long(obj: Mapping[str, pd.DatetimeIndex | None]) -> pd.DataFrame:
    parts = [
        pd.DataFrame({"ticker": t, "earnings_ts": pd.DatetimeIndex(ix)})
        for t, ix in obj.items()
        if ix is not None and len(ix)
    ]
    return pd.concat(parts, ignore_index=True)


def shares_long(obj: Mapping[str, pd.Series | None]) -> pd.DataFrame:
    parts = [
        pd.DataFrame({"ticker": t, "date": pd.DatetimeIndex(s.index), "shares": s.to_numpy(dtype="int64")})
        for t, s in obj.items()
        if s is not None and len(s)
    ]
    return pd.concat(parts, ignore_index=True)


CONVERSIONS = (
    (
        "market/fred_daily.pkl",
        "market/fred_daily.parquet",
        fred_daily_long,
        "FRED daily series (DFF, DGS10, DGS2, BAMLH0A0HYM2), long format: series_id, observation date, value "
        "(NaN kept). Source Data/market/fred_daily.pkl.",
    ),
    (
        "market/fred_releases.pkl",
        "market/cpi_vintages.parquet",
        cpi_vintages_long,
        "ALFRED CPI vintages (CPIAUCSL, CPILFESL): series_id, observation month, value, realtime_start "
        "(vintage date). Source Data/market/fred_releases.pkl.",
    ),
    (
        "market/earnings_dates.pkl",
        "market/earnings_dates.parquet",
        earnings_long,
        "Earnings report timestamps per ticker (naive, as in the source): ticker, earnings_ts. "
        "Source Data/market/earnings_dates.pkl.",
    ),
    (
        "market/shares.pkl",
        "market/shares.parquet",
        shares_long,
        "Shares outstanding per ticker and date: ticker, date, shares. Source Data/market/shares.pkl.",
    ),
)


def main() -> int:
    for src, dest, convert, description in CONVERSIONS:
        obj = io.read_data_pickle(src)
        df = convert(obj)
        entry = io.write_parquet(df, dest, producer=PRODUCER, description=description)
        print(f"{dest}: {entry['rows']} rows, sha256 {entry['sha256']}")
    entry = io.copy_data_file(
        "market/market_prices.parquet",
        "market/market_prices.parquet",
        producer=PRODUCER,
        description="Byte-for-byte copy of Data/market/market_prices.parquet (symbol, date, close, volume).",
    )
    print(f"market/market_prices.parquet: {entry['rows']} rows, sha256 {entry['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
