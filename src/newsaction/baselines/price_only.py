"""Price-only baseline (PREREG §10.4; PRD NA-09 S5): LightGBM on price and volume information only.

- **D0** (call A events): momentum z_m5 / z_m20 / z_m60 (t−1), z_vol of the previous session, the σ regime
  (σ_cc percentile vs its own 252 sessions, t−1), tier and sector → e5 (N_hat) and |z_cc| (mag_hat); P_up
  / P_down from the val-A isotonic maps of N_hat.
- **D2** (call B events): the same, plus the day's reaction known after the close: G = z_cc,t (``g_d2``),
  z_on,t (``react_z_on``) and z_vol,t (``react_z_vol``), PREREG §11.5's R = {G, z_on, momentum, z_vol,
  tier} → y2, the subsequent drift AR(O_{t+1}→C_{t+5}) (``y_hat``).

Both are fit on train, the grid (``price_only.grid``) chosen on val-A, every configuration a trial.

**No test predictions here.** D0 needs z_vol of the previous session, a 2026 volume, and D2 needs the 2026
reactions; neither is read before the freeze (CLAUDE.md B8; PRD S5). NA-11 predicts the test events with the
saved models (``work/baselines/models/price_only_*.lgb.txt``) after the freeze.
"""

from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from typing import Final

import numpy as np
import pandas as pd

from newsaction.baselines import BaselinesConfig
from newsaction.baselines.fitting import prob_maps
from newsaction.baselines.gbm import fit_select, save
from newsaction.paths import Layout

MODEL: Final = "price_only"
D0_FEATURES: Final = ("z_m5", "z_m20", "z_m60", "z_vol_lag1", "ctx_sigma_cc_pct", "tier", "sector")
D2_FEATURES: Final = (*D0_FEATURES, "g_d2", "react_z_on", "react_z_vol")


def _no_test(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame["split"] != "test"]


def fit_predict_d0(frame: pd.DataFrame, cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    frame = _no_test(frame)
    fit = partial(
        fit_select, frame, cfg, cfg.price_only, model=MODEL, features=D0_FEATURES, point="D0", layout=layout
    )
    n = fit(target="e5", metric="ic_e5")
    mag = fit(target="abs_z_cc", metric="r2_abs_z_cc")
    maps, cal, up, down = prob_maps(frame, n.predict_all, cfg)
    save(
        replace(n, record=n.record.model_copy(update={"calibration": cal})),
        layout,
        prob_maps=maps.payload(),
    )
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


def fit_predict_d2(frame: pd.DataFrame, cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    frame = _no_test(frame)
    y = fit_select(
        frame, cfg, cfg.price_only, model=MODEL, target="y2", metric="ic_y2", features=D2_FEATURES,
        point="D2", layout=layout,
    )  # fmt: skip
    save(y, layout)
    return pd.DataFrame(
        {
            "event_id": frame["event_id"].to_numpy(),
            "model": MODEL,
            "call": "B",
            "split": frame["split"].to_numpy(),
            "session": frame["session"].to_numpy(),
            "company_id": frame["company_id"].to_numpy(),
            "y_hat": y.predict_all,
            "extra": json.dumps({}),
        }
    )
