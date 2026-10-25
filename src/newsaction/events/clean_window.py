"""Convergence clean-window flags (PREREG A1.2; PRD NA-03 S5, AC7).

clean_h is True when the same company has no other D2 event in sessions (t, t+h], for
h ∈ {1, 2, 5, 10, 20}. Sessions are counted on the exchange calendar. The flag uses the D2 event table
only: no price, return or target. It is therefore defined for the test period too.

Values:
- **False** as soon as a D2 event falls inside (t, t+h];
- **True** when none does and t+h is on or before ``last_session`` (the last session the events cover);
- **NA** otherwise (the window runs past the data).

The flags look forward, so they are sample-selection flags for the analysis (A1.5 robustness: clean
windows only) and never a model input (registry kind ``post``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from newsaction import calendar


def flag_columns(horizons: Sequence[int]) -> list[str]:
    return [f"clean_{h}" for h in horizons]


def clean_flags(
    events: pd.DataFrame, d2_events: pd.DataFrame, horizons: Sequence[int], last_session: date
) -> pd.DataFrame:
    """clean_h for each row of ``events`` (company_id, session) given the D2 events (company_id, session).

    Returns a frame aligned with ``events`` holding one nullable-boolean column per horizon.
    """
    lo = min([*events["session"], *d2_events["session"]])
    grid = calendar.sessions(lo, last_session)
    pos = {d: i for i, d in enumerate(grid)}
    last = len(grid) - 1
    nxt = np.full(len(events), np.iinfo(np.int64).max, dtype=np.int64)
    ev_pos = events["session"].map(pos)
    if bool(ev_pos.isna().any()):
        raise ValueError("an event session is not an exchange session on or before last_session")
    ev_i = ev_pos.to_numpy(dtype=np.int64)
    d2_by_company = {
        c: np.sort(g["session"].map(pos).dropna().to_numpy(dtype=np.int64))
        for c, g in d2_events.groupby("company_id", sort=False)
    }
    comp = events["company_id"].to_numpy()
    for c in np.unique(comp):
        rows = np.flatnonzero(comp == c)
        d2 = d2_by_company.get(c)
        if d2 is None or len(d2) == 0:
            continue
        j = np.searchsorted(d2, ev_i[rows], side="right")
        has = j < len(d2)
        nxt[rows[has]] = d2[j[has]]
    gap = nxt - ev_i  # sessions to the company's next D2 event strictly after t
    out = pd.DataFrame(index=events.index)
    for h, col in zip(horizons, flag_columns(horizons), strict=True):
        hit = gap <= h
        observed = ev_i + h <= last
        vals = pd.array(np.where(hit, False, True), dtype="boolean")
        vals[~hit & ~observed] = pd.NA
        out[col] = vals
    return out
