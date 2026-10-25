"""Candidate importance filters F0–F6 (PREREG §6.6; PRD NA-03 S2).

Every candidate scores kept (near-duplicate representative) articles; a ticker-day's score in window W
is the max over its kept articles with ``session_w == s``. Each filter also has an **eligibility set**,
the ticker-days it can select at all:

| ID | Article score | Eligible ticker-day |
|---|---|---|
| F0 | 1 (clean, §6.2) | ≥ 1 kept article |
| F1 | 1 if tag ∈ MATERIAL ∧ sentiment ≠ Neutral ∧ event_age_days = 0 | ≥ 1 F1 article |
| F2 | 1 if F1 ∧ tag ∈ HARD ∧ intensity ∈ {Immediate, Short-Term} | ≥ 1 F2 article |
| F3 | 1 if source class ∈ {press wire / primary source, major outlet} | ≥ 1 F3 article |
| F4 | novelty | ≥ 1 kept article |
| F5 | logistic regression on the bge embedding (``learned``) | ≥ 1 kept article |
| F6 | LightGBM on vendor fields, novelty, 16 PCs, attention (``learned``) | ≥ 1 kept article |

**Budget selection** (``budget_select``): a filter selects min(k, |eligible|) ticker-days, ranked by
score and then by a seeded hash of (company, session) that breaks ties. Rule filters (F0–F3) have a
constant score, so above their natural rate the hash thins them at random. That is neutral: it adds no
information, and their recall at the budget is their natural precision spread over fewer days. A
selection is reproduced elsewhere by ``(threshold, tie_u_max)``: eligible ∧ (score > threshold ∨
(score = threshold ∧ u ≤ tie_u_max)).

Vendor fields (tags, sentiment, intensity, ``event_age_days``, ``source_class``) select news only
(CLAUDE.md A6).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date
from typing import Final, NamedTuple

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.events import RULE_FILTERS, FilterConfig, FilterId

SCORE_COLUMN: Final[dict[str, str]] = {
    "F0": "f0",
    "F1": "f1",
    "F2": "f2",
    "F3": "f3",
    "F4": "f4",
    "F5": "f5",
    "F6": "f6",
}
VENDOR_COLUMNS: Final = (
    "tag_type",
    "sentiment_direction",
    "sentiment_intensity",
    "event_age_days",
    "source_class",
    "tag_scheduled",
    "tag_forward_looking",
    "tag_primary_source",
    "tag_quantified",
    "tag_rumor",
)


def rule_scores(arts: pd.DataFrame, cfg: FilterConfig) -> pd.DataFrame:
    """Article scores f0–f4 (float64) for kept articles (pure)."""
    tag = arts["tag_type"]
    f1 = (
        tag.isin(cfg.material_tags)
        & arts["sentiment_direction"].notna()
        & (arts["sentiment_direction"] != cfg.neutral_sentiment)
        & (arts["event_age_days"] == 0)
    )
    f2 = f1 & tag.isin(cfg.hard_tags) & arts["sentiment_intensity"].isin(cfg.timely_intensity)
    f3 = arts["source_class"].isin(cfg.quality_sources)
    out = pd.DataFrame(index=arts.index)
    out["f0"] = 1.0
    out["f1"] = f1.fillna(False).astype("float64")
    out["f2"] = f2.fillna(False).astype("float64")
    out["f3"] = f3.fillna(False).astype("float64")
    out["f4"] = arts["novelty"].astype("float64")
    return out


def eligible(td: pd.DataFrame, fid: FilterId) -> npt.NDArray[np.bool_]:
    """Ticker-days the filter can select (see the module table)."""
    s = td[SCORE_COLUMN[fid]].to_numpy(dtype="float64")
    if fid in RULE_FILTERS:
        return np.asarray(s >= 1.0)
    return np.asarray(np.isfinite(s))


def tie_u(
    company_id: Sequence[int] | pd.Series, session: Sequence[date] | pd.Series, seed: int
) -> npt.NDArray[np.float64]:
    """Uniform [0, 1) tie-breaker: the first 8 bytes of sha256(f"{seed}:{company_id}:{session}")."""
    out = np.empty(len(company_id), dtype=np.float64)
    for i, (c, s) in enumerate(zip(company_id, session, strict=True)):
        h = hashlib.sha256(f"{seed}:{int(c)}:{s.isoformat()}".encode()).digest()
        out[i] = int.from_bytes(h[:8], "big") / 2.0**64
    return out


class Selection(NamedTuple):
    mask: npt.NDArray[np.bool_]
    threshold: float
    tie_u_max: float


def budget_select(
    score: npt.NDArray[np.float64], ok: npt.NDArray[np.bool_], u: npt.NDArray[np.float64], k: int
) -> Selection:
    """Select min(k, |ok|) rows with ``ok``, by score (high first) and then ``u`` (low first)."""
    idx = np.flatnonzero(ok)
    mask = np.zeros(len(score), dtype=bool)
    if len(idx) == 0 or k <= 0:
        return Selection(mask, float("inf"), 0.0)
    order = idx[np.lexsort((u[idx], -score[idx]))]
    chosen = order[: min(k, len(order))]
    mask[chosen] = True
    thr = float(score[chosen[-1]])
    at_thr = ok & (score == thr)
    tie_max = 1.0 if bool(mask[at_thr].all()) else float(u[chosen[score[chosen] == thr]].max())
    return Selection(mask, thr, tie_max)


def apply_threshold(
    score: npt.NDArray[np.float64],
    ok: npt.NDArray[np.bool_],
    u: npt.NDArray[np.float64],
    threshold: float,
    tie_u_max: float,
) -> npt.NDArray[np.bool_]:
    """The frozen selection rule: ok ∧ (score > threshold ∨ (score = threshold ∧ u ≤ tie_u_max))."""
    return np.asarray(ok & ((score > threshold) | ((score == threshold) & (u <= tie_u_max))))


def ticker_days(scores: pd.DataFrame, window_col: str, f6_col: str) -> pd.DataFrame:
    """Ticker-day max scores and counts over articles with ``window_col`` set (pure).

    ``scores``: one row per kept article with company_id, ``window_col``, f0–f5, ``f6_col``.
    """
    a = scores.loc[scores[window_col].notna()]
    g = a.groupby(["company_id", window_col], sort=True)
    out = g.agg(
        n_kept=("f0", "size"),
        f0=("f0", "max"),
        f1=("f1", "max"),
        f2=("f2", "max"),
        f3=("f3", "max"),
        f4=("f4", "max"),
        f5=("f5", "max"),
        f6=(f6_col, "max"),
        n_f1=("f1", "sum"),
        n_f2=("f2", "sum"),
        n_f3=("f3", "sum"),
    ).reset_index()
    out = out.rename(columns={window_col: "session"})
    for c in ("n_f1", "n_f2", "n_f3"):
        out[c] = out[c].astype("int64")
    return out
