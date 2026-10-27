"""A synthetic event frame with every column the NA-09 fitted baselines read (tests/test_baselines_*.py).

Sessions every third business day of train, val-A, val-B and the test period; ``n`` events a session; the
first five val-A sessions are the embargo. Targets carry a little signal from ``sent_mean`` and
``share_timely`` and are NaN in the test period, as in panel_public.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from newsaction.baselines import BaselinesConfig, GbmConfig, GbmGrid
from newsaction.baselines.data import ATTENTION, FLAGS, INTENSITIES, SOURCE_CLASSES, TAG_TYPES

RANGES = {
    "train": (date(2024, 7, 1), date(2025, 6, 30)),
    "val_a": (date(2025, 7, 1), date(2025, 9, 30)),
    "val_b": (date(2025, 10, 1), date(2025, 12, 31)),
    "test": (date(2026, 1, 2), date(2026, 7, 31)),
}
TIERS = ("top100", "mid", "rest")
SECTORS = ("Energy", "Financials", "Health Care", "Information Technology")


def frame(
    n: int = 8, seed: int = 0, splits: tuple[str, ...] = ("train", "val_a", "val_b", "test")
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for split in splits:
        start, end = RANGES[split]
        days = pd.bdate_range(start, end)[::3]
        for k, d in enumerate(days):
            for i in range(n):
                cid = 1000 + i
                rows.append(
                    {
                        "event_id": f"W0:{cid}:{d.date()}",
                        "company_id": cid,
                        "symbol_id": cid,
                        "session": d.date(),
                        "split": split,
                        "tier": TIERS[i % 3],
                        "sector": SECTORS[i % 4],
                        "month": f"{d.year}-{d.month:02d}",
                        "embargo": split in ("val_a", "val_b", "test") and k < 2,
                    }
                )
    f = pd.DataFrame(rows)
    m = len(f)
    f["sent_mean"] = rng.integers(-2, 3, m) / rng.integers(1, 3, m)
    f["sent_min"] = f["sent_mean"] - rng.random(m)
    f["sent_max"] = f["sent_mean"] + rng.random(m)
    f["share_nonneutral"] = rng.random(m)
    f["share_timely"] = rng.random(m)
    for c in (*[f"share_int_{x}" for x in INTENSITIES], "share_int_missing", *[f"share_{x}" for x in FLAGS]):
        f[c] = rng.random(m)
    for c in (*[f"n_tag_{t}" for t in TAG_TYPES], *[f"n_src_{s}" for s in SOURCE_CLASSES]):
        f[c] = rng.integers(0, 3, m).astype(float)
    f["novelty_max"] = rng.random(m)
    f["novelty_mean"] = f["novelty_max"] / 2
    f["dup_w0_sum"] = rng.integers(1, 5, m).astype(float)
    f["n_state_articles"] = rng.integers(1, 7, m).astype(float)
    for c in ATTENTION:
        f[c] = rng.random(m) * 3
    for c in ("z_m5", "z_m20", "z_m60", "z_vol_lag1", "g_d2", "react_z_on", "react_z_vol"):
        f[c] = rng.normal(size=m)
    f["ctx_sigma_cc_pct"] = rng.random(m) * 100
    noise = rng.normal(size=m)
    f["e5"] = 0.5 * f["sent_mean"] + noise
    f["z_cc"] = 0.3 * f["sent_mean"] + rng.normal(size=m)
    f["abs_z_cc"] = f["z_cc"].abs() + f["share_timely"]
    f["y2"] = 0.2 * f["g_d2"] + rng.normal(size=m)
    test = f["split"] == "test"
    f.loc[test, ["e5", "z_cc", "abs_z_cc", "y2", "g_d2", "react_z_on", "react_z_vol", "z_vol_lag1"]] = np.nan
    return f


def small_config(cfg: BaselinesConfig) -> BaselinesConfig:
    """The repository configuration with a two-point grid (fast)."""
    gc = GbmConfig(
        learning_rate=0.1,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        grid=GbmGrid(num_leaves=(3, 7), min_child_samples=(10,), n_estimators=(20,)),
    )
    ridge = cfg.embed_ridge.model_copy(update={"lambdas": (1.0, 100.0)})
    return cfg.model_copy(update={"tags_gbm": gc, "price_only": gc, "embed_ridge": ridge})
