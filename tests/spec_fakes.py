"""Synthetic analysis frames for the spec tests (NA-11): events on business days of val-A, val-B and test, the
first 5 sessions of each embargoed, three tiers, and a day × tier shock."""

from __future__ import annotations

import numpy as np
import pandas as pd

from newsaction.analysis import spec

SPLITS = (("val_a", 60), ("val_b", 60), ("test", 80))
TIERS = ("top100", "mid", "rest")


def fast(reps: int = 1000) -> spec.AnalysisConfig:
    cfg = spec.load_config()
    return cfg.model_copy(update={"bootstrap": cfg.bootstrap.model_copy(update={"reps": reps})})


def panel(n_firms: int = 60, seed: int = 1) -> pd.DataFrame:
    """Events on business days of three splits; each session holds ~half of the firms; day × tier shocks."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2011-01-03", periods=sum(n for _, n in SPLITS))
    split = np.concatenate([[s] * n for s, n in SPLITS])
    first = np.concatenate([np.arange(n) < 5 for _, n in SPLITS])
    tier_of = {f: TIERS[f % 3] for f in range(n_firms)}
    rows = []
    for d, sp, emb in zip(days, split, first, strict=True):
        for f in rng.choice(n_firms, size=n_firms // 2, replace=False):
            rows.append(
                {
                    "session": d.date(),
                    "split": sp,
                    "embargo": bool(emb),
                    "company_id": int(f),
                    "tier": tier_of[int(f)],
                    "event_id": f"E:{f}:{d.date()}",
                }
            )
    df = pd.DataFrame(rows)
    shock = {(s, t): rng.normal(0, 0.5) for s in df["session"].unique() for t in TIERS}
    df["day_tier"] = [shock[(s, t)] for s, t in zip(df["session"], df["tier"], strict=True)]
    return df
