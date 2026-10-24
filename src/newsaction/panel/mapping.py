"""ATOM symbol_id -> Data/prices symbol (PRD NA-01 S2).

Candidates are the normalized current ATOM ticker (``.`` -> ``-``) and every ``ref.symbol_ticker``
alias whose validity range overlaps the candidate's price history. A candidate is accepted only if
the daily close-to-close returns of ATOM's raw close and Data/prices' adjusted close agree over
non-event days (no ATOM corporate action on the day): Spearman correlation >= ``MIN_CORR`` on at
least ``MIN_OVERLAP`` days. Spearman is used for the decision because a single bad raw print (e.g.
GNRC 2023-02-08 in ATOM) can pull a Pearson correlation of a correct mapping below 0.99; Pearson is
reported alongside. Each Data/prices symbol is used at most once (the better-correlated id wins).

Validation uses public-period data only; the caller passes frames that end at the public end.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

MIN_CORR: Final = 0.99
MIN_OVERLAP: Final = 120

MAPPED: Final = "mapped"
NO_CANDIDATE: Final = "no_candidate"
FAILED_CORR: Final = "failed_corr"
CONFLICT: Final = "conflict"


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def candidates(
    symbols: pd.DataFrame,
    symbol_tickers: pd.DataFrame,
    price_ranges: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
) -> pd.DataFrame:
    """(symbol_id, candidate, source) for every ATOM id.

    ``price_ranges`` maps a Data/prices symbol to its (first, last) price session. Aliases count only
    if their [valid_from, valid_to) window overlaps that symbol's price history.
    """
    rows: list[tuple[int, str, str]] = []
    for sid, ticker in zip(symbols["symbol_id"], symbols["ticker"], strict=True):
        cand = normalize_ticker(str(ticker))
        if cand in price_ranges:
            rows.append((int(sid), cand, "current"))
    for rec in symbol_tickers.to_dict("records"):
        cand = normalize_ticker(str(rec["ticker"]))
        if cand not in price_ranges:
            continue
        lo = _naive(rec["valid_from"], pd.Timestamp.min)
        hi = _naive(rec["valid_to"], pd.Timestamp.max)
        first, last = price_ranges[cand]
        if lo <= last and hi > first:
            rows.append((int(rec["symbol_id"]), cand, "alias"))
    out = pd.DataFrame(rows, columns=["symbol_id", "candidate", "source"])
    return out.drop_duplicates(["symbol_id", "candidate"]).reset_index(drop=True)


def _naive(value: object, default: pd.Timestamp) -> pd.Timestamp:
    """A tz-aware instant as naive UTC (``default`` when missing)."""
    if value is None or pd.isna(value):  # type: ignore[call-overload]
        return default
    return pd.Timestamp(value).tz_convert(None)  # type: ignore[arg-type]


def _returns(series: pd.Series) -> pd.Series:
    return series / series.shift(1) - 1.0


def score(
    raw_close: pd.Series, adj_close: pd.Series, event_days: pd.DatetimeIndex
) -> tuple[int, float, float]:
    """(n, pearson, spearman) of raw-close vs adjusted-close daily returns on non-event days."""
    ra, rr = _returns(adj_close), _returns(raw_close)
    ok = ra.notna() & rr.notna() & ~ra.index.isin(event_days)
    n = int(ok.sum())
    if n < 3:
        return n, float("nan"), float("nan")
    a, r = ra[ok].to_numpy(), rr[ok].to_numpy()
    pearson = float(np.corrcoef(a, r)[0, 1])
    spearman = float(np.corrcoef(pd.Series(a).rank().to_numpy(), pd.Series(r).rank().to_numpy())[0, 1])
    return n, pearson, spearman


def map_symbols(
    symbols: pd.DataFrame,
    symbol_tickers: pd.DataFrame,
    raw_close: pd.DataFrame,
    adj_close: pd.DataFrame,
    event_days: dict[int, pd.DatetimeIndex],
) -> pd.DataFrame:
    """One row per ATOM symbol_id: chosen Data/prices symbol (or None), scores and status.

    ``raw_close`` is the ATOM raw close on the grid (columns symbol_id); ``adj_close`` the
    Data/prices adjusted close on the same sessions (columns = Data/prices symbol).
    """
    ranges: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for col in adj_close.columns:
        valid = adj_close.index[adj_close[col].notna().to_numpy()]
        if len(valid):
            ranges[str(col)] = (pd.Timestamp(valid[0]), pd.Timestamp(valid[-1]))
    cands = candidates(symbols, symbol_tickers, ranges)
    scored: list[dict[str, object]] = []
    for rec in cands.to_dict("records"):
        sid = int(rec["symbol_id"])
        if sid not in raw_close.columns:
            continue
        n, pearson, spearman = score(
            raw_close[sid], adj_close[rec["candidate"]], event_days.get(sid, pd.DatetimeIndex([]))
        )
        scored.append(
            {
                "symbol_id": sid,
                "price_symbol": rec["candidate"],
                "candidate_source": rec["source"],
                "n_obs": n,
                "corr_pearson": pearson,
                "corr_spearman": spearman,
            }
        )
    sc = pd.DataFrame(
        scored,
        columns=["symbol_id", "price_symbol", "candidate_source", "n_obs", "corr_pearson", "corr_spearman"],
    )
    ok = sc[(sc["corr_spearman"] >= MIN_CORR) & (sc["n_obs"] >= MIN_OVERLAP)]
    best = ok.sort_values(["symbol_id", "corr_spearman"], ascending=[True, False]).drop_duplicates(
        "symbol_id"
    )
    # one Data/prices symbol per id: the better-correlated id keeps it
    best = best.sort_values(["price_symbol", "corr_spearman"], ascending=[True, False])
    conflicted = best[best.duplicated("price_symbol", keep="first")]["symbol_id"]
    best = best.drop_duplicates("price_symbol", keep="first")

    out = symbols[["symbol_id", "ticker"]].rename(columns={"ticker": "atom_ticker"}).copy()
    out = out.merge(best, on="symbol_id", how="left")
    top = sc.sort_values(["symbol_id", "corr_spearman"], ascending=[True, False]).drop_duplicates("symbol_id")
    fill = top.set_index("symbol_id")
    for col in ("n_obs", "corr_pearson", "corr_spearman", "candidate_source"):
        missing = out[col].isna()
        out.loc[missing, col] = out.loc[missing, "symbol_id"].map(fill[col])
    has_cand = out["symbol_id"].isin(sc["symbol_id"])
    out["status"] = np.where(
        out["price_symbol"].notna(),
        MAPPED,
        np.where(out["symbol_id"].isin(conflicted), CONFLICT, np.where(has_cand, FAILED_CORR, NO_CANDIDATE)),
    )
    out["n_obs"] = out["n_obs"].astype("Int64")
    return out.sort_values("symbol_id").reset_index(drop=True)
