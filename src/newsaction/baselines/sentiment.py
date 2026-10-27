"""Vendor sentiment baseline (PREREG §10.1; PRD NA-09 S2).

- **Signal.** The mean vendor sentiment (−2 … +2, ``configs/baselines.yaml`` ``sentiment.scale``) over the
  articles of the event's Call A state (``data.state_articles``).
- **N_hat** = an isotonic (increasing) map of e5 on the mean sentiment, fit on train; out of range values are
  clipped to the end points.
- **mag_hat** = least squares of |z_cc| on [1, share of non-neutral articles, share with intensity
  Immediate or Short-Term], fit on train.
- **P_up / P_down**: the val-A isotonic maps of N_hat (``fitting.prob_maps``).

Nothing is tuned (no hyper-parameter); the fit records carry the train range and the val-A calibration
range. Predictions: every Call A D0 state, test included (vendor sentiment is known at the article's
t_avail).
"""

from __future__ import annotations

import json
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from newsaction.baselines import BaselinesConfig
from newsaction.baselines.fitting import fit_rows, prob_maps, save_model
from newsaction.baselines.schema import FitRecord, row_range
from newsaction.paths import Layout

MODEL: Final = "sentiment"
SIGNAL: Final = "sent_mean"
MAG_FEATURES: Final = ("share_nonneutral", "share_timely")


def fit_predict(frame: pd.DataFrame, cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    """Fit on train, save the models, and predict every row of ``frame`` (``data.d0_frame``)."""
    tr = fit_rows(frame, cfg, "e5")
    iso = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(tr[SIGNAL], tr["e5"])
    n_hat = iso.predict(frame[SIGNAL].to_numpy(dtype=float))

    trm = fit_rows(frame, cfg, "abs_z_cc")
    x = np.column_stack([np.ones(len(trm)), trm[list(MAG_FEATURES)].to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(x, trm["abs_z_cc"].to_numpy(dtype=float), rcond=None)
    xa = np.column_stack([np.ones(len(frame)), frame[list(MAG_FEATURES)].to_numpy(dtype=float)])
    mag = np.maximum(xa @ coef, 0.0)

    maps, cal, up, down = prob_maps(frame, n_hat, cfg)
    iso_payload = {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()}
    save_model(
        FitRecord(
            model=MODEL, target="e5", point="D0", features=(SIGNAL,), fit=row_range(tr, cfg.fit_split),
            tune=None, calibration=cal, selected={"map": "isotonic increasing, clipped"}, seed=cfg.seed,
        ),
        {"isotonic": iso_payload},
        layout,
        prob_maps=maps.payload(),
    )  # fmt: skip
    save_model(
        FitRecord(
            model=MODEL, target="abs_z_cc", point="D0", features=MAG_FEATURES,
            fit=row_range(trm, cfg.fit_split), tune=None,
            selected={"ols": dict(zip(("const", *MAG_FEATURES), coef.tolist(), strict=True))}, seed=cfg.seed,
        ),
        {"ols": {"coef": coef.tolist(), "features": list(MAG_FEATURES)}},
        layout,
    )  # fmt: skip
    extra: list[dict[str, Any]] = [
        {"sent_mean": float(s), "share_nonneutral": float(a), "share_timely": float(b)}
        for s, a, b in frame[[SIGNAL, *MAG_FEATURES]].to_numpy(dtype=float)
    ]
    return pd.DataFrame(
        {
            "event_id": frame["event_id"].to_numpy(),
            "model": MODEL,
            "call": "A",
            "split": frame["split"].to_numpy(),
            "session": frame["session"].to_numpy(),
            "company_id": frame["company_id"].to_numpy(),
            "N_hat": n_hat,
            "P_up": up,
            "P_down": down,
            "mag_hat": mag,
            "extra": [json.dumps(e, sort_keys=True) for e in extra],
        }
    )
