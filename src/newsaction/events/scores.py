"""Article scores and ticker-day scores of F0–F6 for every kept article (PRD NA-03 S2).

``work/events/article_scores.parquet``: one row per kept article (all periods). It holds f0–f4 (rules,
novelty), f5 (frozen logistic regression), and f6_w0 / f6_w2 (frozen LightGBM with the W0 / W2
attention ratio of the article's ticker-day; NaN when the article is not in that window).

``work/events/ticker_days.parquet``: per window (W0, W2), company and session, the max of each score
over the window's kept articles, the article counts (kept, F1, F2, F3) and the seeded tie-breaker
``tie_u`` (``filters.tie_u``). It is computed from articles and the frozen models only, so the test
period is included; no return is read.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction import io
from newsaction.config import load_splits
from newsaction.events import (
    ARTICLE_SCORES,
    COUNTS,
    PRODUCER,
    TICKER_DAYS,
    filters,
    learned,
    load_events_config,
)
from newsaction.paths import Layout

SCORE_COLUMNS: Final = ("f0", "f1", "f2", "f3", "f4", "f5", "f6_w0", "f6_w2")


def split_name(sessions: pd.Series) -> pd.Series:
    """Split of each session; sessions before the first split are ``warmup``."""
    cfg = load_splits()
    uniq = {d: cfg.split_of(d) or "warmup" for d in set(sessions)}
    return sessions.map(uniq)


def run_scores(layout: Layout | None = None) -> pd.DataFrame:
    """Score every kept article with F0–F6 and aggregate to ticker-days; write both files."""
    cfg = load_events_config()
    arts = learned.load_kept_articles(layout)
    learned.check_embedding_alignment(arts, layout)
    f5 = learned.load_f5(layout)
    booster, prep = learned.load_f6(layout)

    def f5_and_pcs(x: npt.NDArray[np.float16]) -> npt.NDArray[np.float64]:
        return np.column_stack([f5.predict(x), prep.pca.transform(x).astype(np.float64)])

    out = learned.map_embeddings(arts["pos"].to_numpy(), f5_and_pcs, layout=layout)
    counts = io.read_parquet(COUNTS, layout=layout)
    scores = arts[["id", "company_id", "t_avail", "session_w0", "session_w2"]].copy()
    scores = pd.concat([scores, filters.rule_scores(arts, cfg.filters)], axis=1)
    scores["f5"] = out[:, 0]
    pcs = out[:, 1:]
    for w in ("W0", "W2"):
        col = f"f6_{w.lower()}"
        rows = arts[f"session_{w.lower()}"].notna().to_numpy()
        vals = np.full(len(arts), np.nan)
        sub = arts.loc[rows].reset_index(drop=True)
        frame = learned.f6_frame(sub, pcs[rows], learned.attention_for(sub, counts, w), prep)
        vals[rows] = np.asarray(booster.predict(frame), dtype=np.float64)
        scores[col] = vals
    io.write_parquet(
        scores,
        ARTICLE_SCORES,
        producer=PRODUCER,
        description="NA-03 S2: F0-F6 article scores of every kept article (f6 per window; frozen F5/F6)",
        layout=layout,
    )
    seed = cfg.learned.seed
    parts = []
    for w in ("W0", "W2"):
        td = filters.ticker_days(scores, f"session_{w.lower()}", f"f6_{w.lower()}")
        td.insert(0, "window", w)
        td["split"] = split_name(td["session"])
        td["tie_u"] = filters.tie_u(td["company_id"], td["session"], seed)
        parts.append(td)
    tds = pd.concat(parts, ignore_index=True)
    io.write_parquet(
        tds,
        TICKER_DAYS,
        producer=PRODUCER,
        description="NA-03 S2: ticker-day max scores of F0-F6 and article counts per window (W0, W2), "
        "with the seeded tie-breaker; articles and frozen models only",
        layout=layout,
    )
    return tds
