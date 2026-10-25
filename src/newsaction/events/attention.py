"""Article counts per company-session window and the attention ratio (PRD NA-03 S3, S5; PREREG §6.10).

For each member company-session and window W ∈ {W0, W2} (``session_w0`` / ``session_w2`` of the article):
- ``n_articles_w``: usable articles (pass PREREG §6.2 and keep text; near-duplicates included);
- ``n_stories_w``: distinct stories = near-duplicate representatives (``keep``);
- ``n_dup_w``: n_articles − n_stories (repeats of a story, including stories first seen earlier);
- ``attention_mean_w``: mean ``n_articles_w`` over the company's member sessions among the
  ``attention_lookback`` sessions ending at t−1 (missing with fewer than ``attention_min_member_sessions``);
- ``attention_ratio_w``: n_articles_w / max(attention_mean_w, 1 / lookback).

Only member sessions enter the mean because the corpus holds a company's articles only while it is a
member (NA-02 maps at ``session_w2``); a joiner would otherwise look extremely busy. Everything here is
a function of article timestamps: no price or return is read.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.events import COUNTS, PRODUCER, FilterConfig, load_events_config
from newsaction.news import ARTICLES
from newsaction.paths import Layout

ARTICLE_COLUMNS: Final = ("company_id", "session_w0", "session_w2", "keep", "novelty")
WINDOW_COLUMNS: Final = {"W0": "session_w0", "W2": "session_w2"}


def member_company_sessions(layout: Layout | None = None) -> pd.DataFrame:
    """(session, company_id) for every company with a member class at open(session)."""
    mem = io.read_parquet(
        "snapshot/members_by_session.parquet", columns=["session", "symbol_id"], layout=layout
    )
    comp = io.read_parquet("panel/companies.parquet", columns=["symbol_id", "company_id"], layout=layout)
    out = mem.merge(comp, on="symbol_id", how="inner")[["session", "company_id"]].drop_duplicates()
    return out.sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def window_counts(arts: pd.DataFrame, members: pd.DataFrame, cfg: FilterConfig) -> pd.DataFrame:
    """Counts and attention ratios for every member company-session in ``members`` (pure; no I/O).

    ``arts``: company_id, session_w0, session_w2 (dates or None), ``usable`` and ``keep`` (bool).
    """
    lo, hi = min(members["session"]), max(members["session"])
    index = pd.Index(calendar.sessions(lo, hi), name="session")
    companies = pd.Index(sorted(members["company_id"].unique()), name="company_id")
    member = (
        members.assign(m=1.0)
        .pivot_table(index="session", columns="company_id", values="m", aggfunc="max")
        .reindex(index=index, columns=companies)
        .fillna(0.0)
    )
    n_lb, min_m = cfg.attention_lookback, cfg.attention_min_member_sessions
    member_prev = member.rolling(n_lb, min_periods=1).sum().shift(1)
    out = members[["session", "company_id"]].copy()
    rows = index.get_indexer(pd.Index(out["session"]))
    cols = companies.get_indexer(pd.Index(out["company_id"]))
    for w, col in WINDOW_COLUMNS.items():
        a = arts.loc[arts[col].notna() & arts["usable"].astype(bool)]
        sfx = w.lower()
        grids = {}
        for name, mask in (
            ("n_articles", np.ones(len(a), dtype=bool)),
            ("n_stories", a["keep"].to_numpy(bool)),
        ):
            g = (
                a.loc[mask]
                .groupby([col, "company_id"])
                .size()
                .unstack("company_id")
                .reindex(index=index, columns=companies)
                .fillna(0.0)
            )
            grids[name] = g
            out[f"{name}_{sfx}"] = g.to_numpy()[rows, cols].astype("int64")
        out[f"n_dup_{sfx}"] = out[f"n_articles_{sfx}"] - out[f"n_stories_{sfx}"]
        num = (grids["n_articles"] * member).rolling(n_lb, min_periods=1).sum().shift(1)
        mean = (num / member_prev).where(member_prev >= min_m)
        m = mean.to_numpy()[rows, cols]
        out[f"attention_mean_{sfx}"] = m
        out[f"attention_ratio_{sfx}"] = out[f"n_articles_{sfx}"] / np.maximum(m, 1.0 / n_lb)
    return out.reset_index(drop=True)


def load_count_inputs(layout: Layout | None = None) -> pd.DataFrame:
    arts = io.read_parquet(ARTICLES, columns=list(ARTICLE_COLUMNS), layout=layout)
    arts["usable"] = arts["novelty"].notna()
    if bool((arts["keep"] & ~arts["usable"]).any()):
        raise ValueError("a kept article is outside the usable set")
    return arts.drop(columns=["novelty"])


def run(layout: Layout | None = None) -> pd.DataFrame:
    """Build and write work/events/window_counts.parquet."""
    out = window_counts(
        load_count_inputs(layout), member_company_sessions(layout), load_events_config().filters
    )
    io.write_parquet(
        out,
        COUNTS,
        producer=PRODUCER,
        description="NA-03: usable / distinct-story / duplicate article counts per member company-session "
        "in W0 and W2 and the attention ratio vs the previous 60 member sessions (t-1); articles only",
        layout=layout,
    )
    return out
