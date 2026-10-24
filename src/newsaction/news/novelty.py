"""PRD NA-02 S8: point-in-time novelty (PREREG §6.5).

novelty_i = 1 − max cosine(v_i, v_r) over the same company's near-duplicate **representatives** r with
t_avail_r in [t_avail_i − 7 days, t_avail_i), i.e. **strictly earlier**; 1.0 if there is none.

The scan is per company in time order and only looks backwards, so deleting every article after τ
leaves the novelty of every article at or before τ unchanged (tests/test_news_novelty.py). The strict
inequality matters: with ``<=`` a representative would see itself (novelty 0) and articles stamped at
the same instant would see each other. Rows outside ``mask`` get NaN.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.news.dedupe import company_order, times_ns


def scan(
    times: npt.NDArray[np.int64],
    vecs: npt.NDArray[np.float32],
    is_rep: npt.NDArray[np.bool_],
    window_ns: int,
) -> npt.NDArray[np.float64]:
    """Novelty of time-sorted rows of one company."""
    rep_idx = np.flatnonzero(is_rep)
    rep_times = times[rep_idx]
    rep_vecs = vecs[rep_idx]
    lo = np.searchsorted(rep_times, times - window_ns, side="left")
    hi = np.searchsorted(rep_times, times, side="left")  # strictly earlier: rep_time < t
    out = np.ones(len(times), dtype=np.float64)
    for i in np.flatnonzero(hi > lo):
        sims = rep_vecs[lo[i] : hi[i]] @ vecs[i]
        out[i] = 1.0 - float(np.max(sims))
    return out


def pit_novelty(
    df: pd.DataFrame,
    vecs: npt.NDArray[np.floating[Any]],
    *,
    mask: npt.NDArray[np.bool_],
    window: pd.Timedelta,
) -> pd.Series:
    """Novelty aligned with ``df`` (needs id, company_id, t_avail, is_representative)."""
    out = np.full(len(df), np.nan)
    times = times_ns(df)
    is_rep = df["is_representative"].astype("boolean").fillna(False).to_numpy(dtype=bool)
    for pos in company_order(df, mask).values():
        out[pos] = scan(times[pos], np.asarray(vecs[pos], dtype=np.float32), is_rep[pos], int(window.value))
    return pd.Series(out, index=df.index, name="novelty")
