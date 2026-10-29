"""NA-13b (d): watching the open. Does the 10:00 reading (D1) add anything over the pre-open reading (D0)?

The outcome is y1 = AR(10:00 → C_t)/σ_rest (PREREG §5.6; §15 NA-10 row). For Laya-Fin and d1-ultra, on val-A,
val-B and the test (events outside the embargo), exactly these statistics and no others:

- the daily IC with y1 of the pre-open reading N̂_D0 (``a0_n_hat``), of the 10:00 reading N̂_D1 (Call B at D1,
  ``b1_n_hat``), of the revision z(N̂_D1) − z(N̂_D0) (each reading z-scored over the split's events) and of the
  first-bar move G_D1 (``g_d1``): the frozen daily IC (>= 5 names a session; a split needs >= 10 sessions),
  mean and Newey–West t (5 lags), with a 95% interval mean ± 1.96·SE, SE = |mean / t|;
- the mean of sign(N̂_D0)·y1 over the events whose first bar moved against the pre-open view
  (sign(G_D1) ≠ sign(N̂_D0)) and over those whose first bar moved with it: the mean of daily means with a
  day-clustered t (mean / (SD/√days)).

These are the operator's assistant's definitions, line for line (the numbers in the operator's prompt
reproduce exactly). An event without a first bar has no y1 either, so it never enters a mean.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction.analysis import metrics as mx
from newsaction.analysis import spec
from newsaction.selective import data as sd

COLUMNS: Final = ("event_id", "session", "split", "embargo", "a0_n_hat", "b1_n_hat", "g_d1", "y1")
IC_STATS: Final = {
    "ic_pre_open": "a0_n_hat",
    "ic_ten": "b1_n_hat",
    "ic_revision": "revision",
    "ic_first_bar": "g_d1",
}
MEAN_STATS: Final = ("mean_against", "mean_with")
STATS: Final = (*IC_STATS, *MEAN_STATS)
MIN_DAYS: Final = 10
Z95: Final = 1.959963984540054


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Events outside the embargo with the within-split z-scores, the revision and sign(N̂_D0)·y1."""
    f = frame.loc[~frame["embargo"].fillna(False).astype(bool)].copy()
    for c in ("a0_n_hat", "b1_n_hat"):
        f[c + "_z"] = f.groupby("split")[c].transform(lambda s: (s - s.mean()) / s.std())
    f["revision"] = f["b1_n_hat_z"] - f["a0_n_hat_z"]
    f["s_a0_y1"] = np.sign(f["a0_n_hat"]) * f["y1"]
    return f


def ic(d: pd.DataFrame, x: str, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    s = d.dropna(subset=[x, "y1"])
    daily = spec.daily(s, x, "y1", cfg)
    if len(daily) < MIN_DAYS:
        return {"value": math.nan, "t": math.nan, "ci_low": math.nan, "ci_high": math.nan,
                "n_days": len(daily), "n_obs": len(s)}  # fmt: skip
    mean, t, n = mx.nw_t(daily, cfg.metrics.nw_lags)
    se = abs(mean / t) if math.isfinite(t) and t != 0 else math.nan
    return {"value": mean, "t": t, "ci_low": mean - Z95 * se, "ci_high": mean + Z95 * se,
            "n_days": n, "n_obs": len(s)}  # fmt: skip


def day_mean(d: pd.DataFrame, col: str) -> dict[str, Any]:
    """Mean of daily means and its day-clustered t."""
    x = d.dropna(subset=[col])
    m = x.groupby("session")[col].mean()
    n = len(m)
    mean = float(m.mean()) if n else math.nan
    sd_ = float(m.std(ddof=1)) if n > 1 else math.nan
    se = sd_ / math.sqrt(n) if n > 1 else math.nan
    t = mean / se if se and math.isfinite(se) and se > 0 else math.nan
    return {"value": mean, "t": t, "ci_low": mean - Z95 * se, "ci_high": mean + Z95 * se,
            "n_days": n, "n_obs": len(x)}  # fmt: skip


def statistics(
    frame: pd.DataFrame, cfg: spec.AnalysisConfig, splits: Sequence[str] = sd.SPLITS
) -> pd.DataFrame:
    """The six statistics per split (rows: split × statistic)."""
    f = prepare(frame)
    rows: list[dict[str, Any]] = []
    for split in splits:
        d = f.loc[f["split"] == split]
        for name, col in IC_STATS.items():
            rows.append({"split": split, "statistic": name, "kind": "ic", **ic(d, col, cfg)})
        sa, sg = np.sign(d["a0_n_hat"]), np.sign(d["g_d1"])
        groups = {"mean_against": d.loc[sa != sg], "mean_with": d.loc[sa == sg]}
        for name, g in groups.items():
            rows.append({"split": split, "statistic": name, "kind": "mean", **day_mean(g, "s_a0_y1")})
    return pd.DataFrame(rows)


def run(cfg: spec.AnalysisConfig, layout: Any = None) -> pd.DataFrame:
    parts = []
    for model in sd.MAIN:
        f = sd.frame(model, COLUMNS, layout)
        parts.append(statistics(f, cfg).assign(model=model))
    out = pd.concat(parts, ignore_index=True)
    return out[["model", *[c for c in out.columns if c != "model"]]]
