"""Point-in-time GICS sector and leave-one-out sector returns (PREREG §5.2; PRD NA-01 S3).

The sector factor of symbol i on session t, for return type x, is the equal-weighted mean of r_x over
the *other* companies of i's GICS sector that are index members on t (one representative share class
per company, so Alphabet is not counted twice and never sits in its own factor). It is NaN when fewer
than ``MIN_OTHERS`` other companies have a return that session.

ATOM's ``ref.symbol_sector`` holds one open-ended level-1 classification per symbol (no history), so
the point-in-time sector is that classification on every session (NA-01 REPORT).
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

MIN_OTHERS: Final = 5


def sector_of(gics: pd.DataFrame, sessions: pd.DatetimeIndex, symbols: list[int]) -> pd.DataFrame:
    """Level-1 GICS sector name per (session, symbol) from the validity ranges (object frame)."""
    out = pd.DataFrame(None, index=sessions, columns=symbols, dtype=object)
    for rec in gics.to_dict("records"):
        if rec["symbol_id"] not in out.columns:
            continue
        lo = (
            pd.Timestamp(rec["valid_from"]).tz_convert(None)
            if pd.notna(rec["valid_from"])
            else pd.Timestamp.min
        )
        hi = pd.Timestamp(rec["valid_to"]).tz_convert(None) if pd.notna(rec["valid_to"]) else pd.Timestamp.max
        rows = (out.index >= lo.normalize()) & (out.index < hi)
        out.loc[rows, rec["symbol_id"]] = rec["level1_name"]
    return out


def loo_sector_return(
    r: pd.DataFrame, sector: pd.DataFrame, pool: pd.DataFrame, company: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(leave-one-company-out sector mean, number of other companies) on the grid.

    ``pool`` (bool) marks the representative class of each member company on each session;
    ``company`` maps symbol_id -> company_id.
    """
    symbols = list(r.columns)
    values = r.to_numpy(dtype="float64")
    in_pool = pool.reindex(index=r.index, columns=symbols).fillna(False).to_numpy(dtype=bool) & np.isfinite(
        values
    )
    contrib = np.where(in_pool, values, 0.0)
    sec_frame = sector.reindex(index=r.index, columns=symbols)
    sec = sec_frame.to_numpy(dtype=object)
    has_sector = sec_frame.notna().to_numpy(dtype=bool)
    names = sorted({s for s in sec.ravel() if isinstance(s, str)})
    sums = np.zeros_like(values)
    counts = np.zeros_like(values)
    for name in names:
        member = sec == name
        s = np.where(member, contrib, 0.0).sum(axis=1, keepdims=True)
        n = np.where(member, in_pool, False).sum(axis=1, keepdims=True)
        sums = np.where(member, s, sums)
        counts = np.where(member, n, counts)
    comp = company.reindex(symbols).to_numpy()
    own_r = np.zeros_like(values)
    own_n = np.zeros_like(values)
    for cid in pd.unique(comp):
        cols = comp == cid
        own_r[:, cols] = contrib[:, cols].sum(axis=1, keepdims=True)
        own_n[:, cols] = in_pool[:, cols].sum(axis=1, keepdims=True)
    others = counts - own_n
    with np.errstate(invalid="ignore", divide="ignore"):
        loo = np.where(others >= MIN_OTHERS, (sums - own_r) / others, np.nan)
    loo = np.where(has_sector, loo, np.nan)
    return (
        pd.DataFrame(loo, index=r.index, columns=symbols),
        pd.DataFrame(others, index=r.index, columns=symbols),
    )
