"""Vendor tags + LightGBM baseline (PREREG §10.3; PRD NA-09 S4).

- **Features** (one row per Call A D0 state, from its articles; ``data.article_features``): counts of each
  vendor tag type, the shares of the five vendor flags, sentiment (mean, min, max, share non-neutral, share
  timely), the intensity shares, counts by source class (domain), novelty (max, mean), the W0 duplicate
  count, the number of state articles, the W0 attention block, tier and sector.
- **Targets** e5 (→ N_hat) and |z_cc| (→ mag_hat), fit on train; the configuration of the small grid
  (``tags_gbm.grid``) chosen on val-A (``gbm.fit_select``), every configuration a trial.
- **P_up / P_down**: the val-A isotonic maps of N_hat.

Predictions: every Call A D0 state, test included (every input is known at the article's t_avail).
"""

from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from typing import Final

import numpy as np
import pandas as pd

from newsaction.baselines import BaselinesConfig
from newsaction.baselines.data import ATTENTION, FLAGS, INTENSITIES, SOURCE_CLASSES, TAG_TYPES
from newsaction.baselines.fitting import prob_maps
from newsaction.baselines.gbm import fit_select, save
from newsaction.paths import Layout

MODEL: Final = "tags_gbm"
FEATURES: Final = (
    *[f"n_tag_{t}" for t in TAG_TYPES],
    *[f"share_{f}" for f in FLAGS],
    "sent_mean",
    "sent_min",
    "sent_max",
    "share_nonneutral",
    "share_timely",
    *[f"share_int_{n}" for n in INTENSITIES],
    "share_int_missing",
    *[f"n_src_{s}" for s in SOURCE_CLASSES],
    "novelty_max",
    "novelty_mean",
    "dup_w0_sum",
    "n_state_articles",
    *ATTENTION,
    "tier",
    "sector",
)


def fit_predict(frame: pd.DataFrame, cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    fit = partial(
        fit_select, frame, cfg, cfg.tags_gbm, model=MODEL, features=FEATURES, point="D0", layout=layout
    )
    n = fit(target="e5", metric="ic_e5")
    mag = fit(target="abs_z_cc", metric="r2_abs_z_cc")
    maps, cal, up, down = prob_maps(frame, n.predict_all, cfg)
    n = replace(n, record=n.record.model_copy(update={"calibration": cal}))
    save(n, layout, prob_maps=maps.payload())
    save(mag, layout)
    return pd.DataFrame(
        {
            "event_id": frame["event_id"].to_numpy(),
            "model": MODEL,
            "call": "A",
            "split": frame["split"].to_numpy(),
            "session": frame["session"].to_numpy(),
            "company_id": frame["company_id"].to_numpy(),
            "N_hat": n.predict_all,
            "P_up": up,
            "P_down": down,
            "mag_hat": np.maximum(mag.predict_all, 0.0),
            "extra": json.dumps({}),
        }
    )
