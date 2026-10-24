"""PRD NA-02 S7: near-duplicate groups within a company (PREREG §6.2).

Greedy, time-ordered, per company (articles sorted by (t_avail, id)):
- an article joins the group of the most similar **representative** whose t_avail lies in
  [t_avail − 72 h, t_avail], if that cosine is ≥ 0.93;
- otherwise it starts a new group and is its representative.

So the representative is the group's earliest article, every member is within 72 h and ≥ 0.93 of it, and
groups never chain beyond 72 h. An article's group and representative status depend only on articles
at or before its own t_avail: deleting later articles changes neither (point-in-time; the property the
novelty scan relies on).

Columns: ``dup_group`` (id of the representative), ``is_representative``, ``dup_count`` (group size,
including later members: descriptive only, kind ``post``), ``dup_count_w0`` / ``dup_count_w2`` (members
in the representative's own W0 / W2 window, known at that window's end).
Rows outside ``mask`` (articles that fail cleaning) get no group.
"""

from __future__ import annotations

import bisect
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

GROUP_COLUMNS = ("dup_group", "is_representative", "dup_count", "dup_count_w0", "dup_count_w2")


def company_order(df: pd.DataFrame, mask: npt.NDArray[np.bool_]) -> dict[int, npt.NDArray[np.int64]]:
    """Row positions of masked articles per company, sorted by (t_avail, id)."""
    pos = np.flatnonzero(mask).astype(np.int64)
    cid = df["company_id"].to_numpy()[pos].astype(np.int64)
    t = times_ns(df)[pos]
    ids = df["id"].astype("str").to_numpy()[pos].astype(str)
    order = np.lexsort((ids, t, cid))
    pos, cid = pos[order], cid[order]
    cuts = np.flatnonzero(np.diff(cid)) + 1
    return {int(c[0]): p for c, p in zip(np.split(cid, cuts), np.split(pos, cuts), strict=True) if len(p)}


def times_ns(df: pd.DataFrame) -> npt.NDArray[np.int64]:
    t = df["t_avail"].dt.tz_convert("UTC").dt.as_unit("ns").dt.tz_localize(None)
    return np.asarray(t.to_numpy(dtype="datetime64[ns]").view(np.int64), dtype=np.int64)


def assign_groups(
    times: npt.NDArray[np.int64], vecs: npt.NDArray[np.float32], cosine: float, window_ns: int
) -> npt.NDArray[np.int64]:
    """For time-sorted rows: index (within the input) of each row's representative."""
    n = len(times)
    rep_of = np.empty(n, dtype=np.int64)
    rep_rows: list[int] = []
    rep_times: list[int] = []
    rep_vecs = np.empty((n, vecs.shape[1]), dtype=np.float32)
    for i in range(n):
        lo = bisect.bisect_left(rep_times, int(times[i]) - window_ns)
        if lo < len(rep_rows):
            sims = rep_vecs[lo : len(rep_rows)] @ vecs[i]
            j = int(np.argmax(sims))
            if sims[j] >= cosine:
                rep_of[i] = rep_rows[lo + j]
                continue
        rep_of[i] = i
        rep_vecs[len(rep_rows)] = vecs[i]
        rep_rows.append(i)
        rep_times.append(int(times[i]))
    return rep_of


def near_duplicate_groups(
    df: pd.DataFrame,
    vecs: npt.NDArray[np.floating[Any]],
    *,
    mask: npt.NDArray[np.bool_],
    cosine: float,
    window: pd.Timedelta,
) -> pd.DataFrame:
    """GROUP_COLUMNS aligned with ``df`` (needs id, company_id, t_avail, session_w0, session_w2)."""
    n = len(df)
    rep_pos = np.full(n, -1, dtype=np.int64)
    times = times_ns(df)
    for pos in company_order(df, mask).values():
        local = assign_groups(times[pos], np.asarray(vecs[pos], dtype=np.float32), cosine, int(window.value))
        rep_pos[pos] = pos[local]
    grouped = rep_pos >= 0
    ids = df["id"].astype("str").to_numpy()
    out = pd.DataFrame(index=df.index)
    out["dup_group"] = pd.Series(ids[np.maximum(rep_pos, 0)], index=df.index, dtype="str").where(grouped)
    out["is_representative"] = grouped & (rep_pos == np.arange(n))
    frame = pd.DataFrame(
        {"rep": rep_pos, "w0": df["session_w0"].to_numpy(), "w2": df["session_w2"].to_numpy()}
    )
    frame = frame[grouped]
    rep_w0 = pd.Series(df["session_w0"].to_numpy(), index=np.arange(n))
    rep_w2 = pd.Series(df["session_w2"].to_numpy(), index=np.arange(n))
    frame["same_w0"] = frame["w0"].notna().to_numpy() & (
        frame["w0"].to_numpy() == rep_w0.reindex(frame["rep"]).to_numpy()
    )
    frame["same_w2"] = frame["w2"].notna().to_numpy() & (
        frame["w2"].to_numpy() == rep_w2.reindex(frame["rep"]).to_numpy()
    )
    agg = frame.groupby("rep").agg(n=("rep", "size"), n_w0=("same_w0", "sum"), n_w2=("same_w2", "sum"))
    rep_has_w0 = rep_w0.reindex(agg.index).notna().to_numpy()
    agg["n_w0"] = agg["n_w0"].where(rep_has_w0)
    look = agg.reindex(rep_pos)
    out["dup_count"] = pd.array(np.where(grouped, look["n"].to_numpy(), np.nan), dtype="Int64")
    out["dup_count_w0"] = pd.array(
        np.where(grouped, look["n_w0"].to_numpy(dtype=float), np.nan), dtype="Int64"
    )
    out["dup_count_w2"] = pd.array(
        np.where(grouped, look["n_w2"].to_numpy(dtype=float), np.nan), dtype="Int64"
    )
    return out
