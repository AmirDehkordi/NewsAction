"""NA-13b (b): the distribution of the decision models' outputs, N̂ and the stated confidence, per model and
split (events outside the embargo; span-02's and drex-v2.0's val-A are NA-06's stage-2 sample).

Histograms share their bins across splits: BINS equal-width bins between the val-A 0.5th and 99.5th
percentiles of the measure; values beyond them fall in the end bins (``clipped`` counts them). Each bin holds
the count and the share of the split's events. The summary rows give the mean, SD, the 5/25/50/75/95th
percentiles and the share of N̂ above zero. The reliability diagrams and ECE they sit next to are NA-12's
(test split; ``artifacts/NA-12/figure_data/appendix_reliability.csv`` and table t15), not recomputed here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction.selective import data as sd

BINS: Final = 40
RANGE_Q: Final = (0.005, 0.995)
MEASURES: Final = {"n_hat": "N̂", "conf": "stated confidence"}
QUANTILES: Final = (0.05, 0.25, 0.5, 0.75, 0.95)


def edges(frame: pd.DataFrame, measure: str) -> np.ndarray:
    va = sd.eval_rows(frame, "val_a")[measure].dropna()
    lo, hi = (float(v) for v in va.quantile(list(RANGE_Q)))
    if not hi > lo:
        hi = lo + 1e-9
    return np.linspace(lo, hi, BINS + 1)


def histogram(values: pd.Series, e: np.ndarray) -> pd.DataFrame:
    v = values.dropna().to_numpy(dtype=float)
    idx = np.clip(np.searchsorted(e, v, side="right") - 1, 0, len(e) - 2)
    n = np.bincount(idx, minlength=len(e) - 1).astype(float)
    return pd.DataFrame(
        {"bin": np.arange(len(e) - 1), "lo": e[:-1], "hi": e[1:], "mid": (e[:-1] + e[1:]) / 2,
         "n": n, "share": n / max(len(v), 1)}
    )  # fmt: skip


def run(
    frames_by_model: Mapping[str, pd.DataFrame], splits: Sequence[str] = sd.SPLITS
) -> dict[str, pd.DataFrame]:
    """(histograms, summaries) as long frames."""
    hist, summ = [], []
    for model, f in frames_by_model.items():
        for measure in MEASURES:
            e = edges(f, measure)
            for split in splits:
                x = sd.eval_rows(f, split)
                if x.empty:
                    continue
                v = x[measure].dropna()
                h = histogram(v, e).assign(model=model, measure=measure, split=split)
                hist.append(h)
                row: dict[str, Any] = {
                    "model": model, "measure": measure, "split": split, "sample": str(x["sample"].iloc[0]),
                    "n": len(v), "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
                    "clipped_low": int((v < e[0]).sum()), "clipped_high": int((v > e[-1]).sum()),
                }  # fmt: skip
                row |= {f"q{int(q * 100):02d}": float(v.quantile(q)) for q in QUANTILES}
                if measure == "n_hat":
                    row["share_positive"] = float((v > 0).mean())
                summ.append(row)
    return {
        "histograms": pd.concat(hist, ignore_index=True),
        "summaries": pd.DataFrame(summ),
    }
