"""NA-13 capacity (PREREG §12; PRD NA-13 S2): the capital at which a trade reaches 1% of the 20-session ADV.

With capital C, a cohort trades C·|w|/L dollars of each name (calendar time: 1/L of the capital per cohort).
Each trade must stay ≤ ``share`` × ADV20 (``market.adv``: dollar volume over the 20 sessions ending t−1), so a
cohort supports C_c = min over its names of share·ADV20·L/|w|. The strategy's capacity is the median of C_c
over its non-empty cohorts (half of the decisions could deploy more), reported with the 10th percentile. The
SPY hedge is left out: SPY's ADV is orders of magnitude above any single name's. Names without an ADV (fewer
than 15 of the 20 sessions) do not bind and are counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

ADV_SHARE: Final = 0.01  # configs/frozen.yaml strategy.capacity_adv_share


@dataclass(frozen=True)
class Capacity:
    median_usd: float
    p10_usd: float
    n_cohorts: int
    n_without_adv: int


def cohort_capacity(
    weights: npt.NDArray[np.float64],
    adv_usd: npt.NDArray[np.float64],
    cohort: npt.NDArray[np.int64],
    n_cohorts: int,
    holding: int,
    share: float = ADV_SHARE,
) -> npt.NDArray[np.float64]:
    """C_c per cohort (NaN for a cohort with no position or no name with an ADV)."""
    w = np.abs(np.asarray(weights, dtype=float))
    on = (w > 0) & np.isfinite(adv_usd) & (adv_usd > 0)
    cap = np.full(n_cohorts, np.inf)
    np.minimum.at(cap, cohort[on], share * adv_usd[on] * float(holding) / w[on])
    cap[~np.isfinite(cap)] = np.nan
    return cap


def summarize(
    weights: npt.NDArray[np.float64],
    adv_usd: npt.NDArray[np.float64],
    cohort: npt.NDArray[np.int64],
    n_cohorts: int,
    holding: int,
    share: float = ADV_SHARE,
) -> Capacity:
    cap = cohort_capacity(weights, adv_usd, cohort, n_cohorts, holding, share)
    ok = cap[np.isfinite(cap)]
    traded = np.abs(np.asarray(weights, dtype=float)) > 0
    missing = int((traded & ~(np.isfinite(adv_usd) & (adv_usd > 0))).sum())
    if len(ok) == 0:
        return Capacity(float("nan"), float("nan"), 0, missing)
    return Capacity(float(np.median(ok)), float(np.quantile(ok, 0.1)), len(ok), missing)
