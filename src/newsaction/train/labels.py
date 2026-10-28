"""H-react, H-mag and H-cont labels of the trained decision models (PREREG §9.1; PRD NA-08 S1).

One row per event key (company, session) of the D0 and D2 events in train, val-A and val-B, read from the
representative-class row of ``panel_public`` (NA-01's frozen, purged target code):

- **H-react:** level = 4 + sign(e5)·b(|e5|), where e5 = AR(C_{t−1}→C_{t+4}) / (σ_cc·√5) and b(·) bins at
  the edges 0.5, 1, 2, 3, closed on the left: [0.5, 1) is "small" and |z| ≥ 3 "very large", as in the
  codebook's move words (PREREG §6.11). The nine levels are Q1's, from "very large fall" to "very large rise".
- **H-mag:** b(|z_cc,t|), levels 0..4.
- **H-cont** (asked of Call B D2 states only): for |G| ≥ 0.5, where G = z_cc,t (``g_d2``), x = sign(G)·y2 with
  y2 = z(O_{t+1}→C_{t+5}). The label is reverse if x ≤ −0.5, continue if x ≥ 0.5 and stall otherwise; its
  index follows Q6's option order (reverse, stall, continue).

**Purge** (PREREG §4.1). The panel's e5 and y2 are NaN when their horizon passes the last session of the
split of t, and ``build_labels`` asserts that every label's horizon ends inside its split, so train labels
end by 2025-06-30. A missing input gives a missing label (nullable Int8), never a "no move" level.

**Public sessions only.** The panel ends at the end of val-B and ``assert_public`` refuses anything later.
Val-B rows are kept for NA-11; NA-08 computes no statistic on them. This module never imports
``newsaction.panel.targets`` or ``newsaction.lock``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.events import EVENTS_D0, EVENTS_D2
from newsaction.events.labels import assert_public, split_last_session
from newsaction.paths import Layout
from newsaction.train import (
    LABELS,
    PRODUCER,
    LabelsConfig,
    load_training_config,
    option_keys,
    training_questions,
)

PANEL = "panel/panel_public.parquet"
PANEL_COLUMNS = ("session", "symbol_id", "split", "e5", "z_cc", "g_d2", "y2")
EVENT_COLUMNS = ("company_id", "symbol_id", "session", "split", "embargo")
CONT_OPTIONS = ("reverse", "stall", "continue")
COLUMNS = (
    "company_id",
    "session",
    "symbol_id",
    "split",
    "embargo",
    "in_d0",
    "in_d2",
    "e5",
    "z_cc",
    "g_d2",
    "y2",
    "cont_x",
    "react_label",
    "mag_label",
    "cont_label",
    "react_horizon_end",
    "cont_horizon_end",
)


class TrainLabelError(ValueError):
    """A label would use a session outside the public period or a horizon outside its split."""


def magnitude_bin(abs_z: pd.Series, edges: Sequence[float]) -> pd.Series:
    """b(|z|) in 0..len(edges), closed on the left; NaN stays NaN (float)."""
    v = abs_z.to_numpy(dtype="float64")
    out = np.searchsorted(np.asarray(edges, dtype="float64"), v, side="right").astype("float64")
    out[~np.isfinite(v)] = np.nan
    return pd.Series(out, index=abs_z.index)


def react_levels(e5: pd.Series, edges: Sequence[float]) -> pd.Series:
    """Q1's nine levels from e5: 4 + sign(e5)·b(|e5|) (Int8, NA where e5 is missing)."""
    b = magnitude_bin(e5.abs(), edges)
    level = len(edges) + np.sign(e5.to_numpy(dtype="float64")) * b.to_numpy()
    return pd.Series(level, index=e5.index).astype("Int8")


def mag_levels(z_cc: pd.Series, edges: Sequence[float]) -> pd.Series:
    return magnitude_bin(z_cc.abs(), edges).astype("Int8")


def cont_labels(
    g: pd.Series, y2: pd.Series, *, min_abs_g: float, band: float, order: Sequence[str]
) -> tuple[pd.Series, pd.Series]:
    """(x = sign(G)·y2, H-cont index in ``order``); NA when |G| < min_abs_g or an input is missing."""
    if tuple(order) != CONT_OPTIONS:
        raise TrainLabelError(f"Q6 options must be {CONT_OPTIONS} in this order, got {tuple(order)}")
    gv, yv = g.to_numpy(dtype="float64"), y2.to_numpy(dtype="float64")
    x = np.sign(gv) * yv
    ok = np.isfinite(x) & (np.abs(gv) >= min_abs_g)
    idx = np.where(x <= -band, 0.0, np.where(x >= band, 2.0, 1.0))
    idx[~ok] = np.nan
    return (
        pd.Series(np.where(np.isfinite(gv) & np.isfinite(yv), x, np.nan), index=g.index),
        pd.Series(idx, index=g.index).astype("Int8"),
    )


def horizon_end(sessions: pd.Series, k: int) -> pd.Series:
    """The k-th session after each session (the session itself for k = 0)."""
    if sessions.empty:
        return sessions.copy()
    lo, hi = min(sessions), max(sessions)
    days = calendar.sessions(lo, hi)
    tail = days[-1]
    for _ in range(k):
        tail = calendar.next_session(tail)
        days.append(tail)
    pos = {d: i for i, d in enumerate(days)}
    return sessions.map(lambda d: days[pos[d] + k])


def event_keys(events_d0: pd.DataFrame, events_d2: pd.DataFrame, splits: Sequence[str]) -> pd.DataFrame:
    """(company_id, session) keys of the D0 and D2 events in ``splits``, with their symbol and flags."""
    parts = []
    for ev, flag in ((events_d0, "in_d0"), (events_d2, "in_d2")):
        e = ev.loc[ev["split"].isin(list(splits)), list(EVENT_COLUMNS)].copy()
        e[flag] = True
        parts.append(e)
    keys = parts[0].merge(parts[1], on=["company_id", "session"], how="outer", suffixes=("", "_d2"))
    for col in ("symbol_id", "split", "embargo"):
        other = keys.pop(f"{col}_d2")
        both = keys[col].notna() & other.notna()
        if bool((keys.loc[both, col] != other[both]).any()):
            raise TrainLabelError(f"D0 and D2 events of one company-session disagree on {col}")
        keys[col] = keys[col].where(keys[col].notna(), other)
    for flag in ("in_d0", "in_d2"):
        keys[flag] = keys[flag].astype("boolean").fillna(False).astype(bool)
    keys["symbol_id"] = keys["symbol_id"].astype("int64")
    keys["embargo"] = keys["embargo"].astype(bool)
    return keys


def build_labels(
    panel: pd.DataFrame, events_d0: pd.DataFrame, events_d2: pd.DataFrame, cfg: LabelsConfig | None = None
) -> pd.DataFrame:
    """The label table (one row per event key, sorted by session and company)."""
    tc = load_training_config()
    cfg = tc.labels if cfg is None else cfg
    assert_public(panel["session"], "panel")
    keys = event_keys(events_d0, events_d2, cfg.splits)
    assert_public(keys["session"], "events")
    p = panel[list(PANEL_COLUMNS)].rename(columns={"split": "panel_split"})
    out = keys.merge(p, on=["session", "symbol_id"], how="left", validate="one_to_one")
    known = out["panel_split"].notna()
    if bool((out.loc[known, "panel_split"] != out.loc[known, "split"]).any()):
        raise TrainLabelError("an event's split differs from the panel's split of its session")
    out = out.drop(columns="panel_split")
    out["react_label"] = react_levels(out["e5"], cfg.edges)
    out["mag_label"] = mag_levels(out["z_cc"], cfg.edges)
    order = option_keys(training_questions(tc)["cont"])
    out["cont_x"], out["cont_label"] = cont_labels(
        out["g_d2"], out["y2"], min_abs_g=cfg.cont_min_abs_g, band=cfg.cont_band, order=order
    )
    out["react_horizon_end"] = horizon_end(out["session"], cfg.react_horizon)
    out["cont_horizon_end"] = horizon_end(out["session"], cfg.cont_horizon)
    check_purge(out)
    cols = list(COLUMNS)
    return out[cols].sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def check_purge(labels: pd.DataFrame) -> None:
    """Every label's horizon ends inside the split of its session (PREREG §4.1)."""
    ends: dict[str, date] = {s: split_last_session(s) for s in labels["split"].unique()}
    last = labels["split"].map(ends)
    for label, horizon in (
        ("react_label", "react_horizon_end"),
        ("mag_label", "session"),
        ("cont_label", "cont_horizon_end"),
    ):
        has = labels[label].notna()
        late = has & (labels[horizon] > last)
        if bool(late.any()):
            first = labels.loc[late].iloc[0]
            raise TrainLabelError(
                f"{label} of {first['session']} ({first['split']}) has its horizon after the split end"
            )


def run(layout: Layout | None = None) -> pd.DataFrame:
    """Build and write work/kaggle/labels.parquet."""
    panel = io.read_parquet(PANEL, columns=list(PANEL_COLUMNS), layout=layout)
    ev0 = io.read_parquet(EVENTS_D0, columns=list(EVENT_COLUMNS), layout=layout)
    ev2 = io.read_parquet(EVENTS_D2, columns=list(EVENT_COLUMNS), layout=layout)
    out = build_labels(panel, ev0, ev2)
    io.write_parquet(
        out,
        LABELS,
        producer=PRODUCER,
        description="NA-08 S1: H-react / H-mag / H-cont labels (PREREG §9.1) of the D0 and D2 event keys of "
        "train, val-A and val-B; purged at split ends (§4.1); post (never a model input); local only",
        layout=layout,
    )
    return out
