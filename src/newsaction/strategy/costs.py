"""NA-13 costs (PREREG §12; PRD NA-13 S2): a flat charge per side on each traded dollar, both legs, the hedge.

A cohort is the book formed at one decision: equal weights w (longs +1/K, shorts −1/K, so Σ|w| = 2) and a SPY
hedge h = −Σ w·β_m. In a calendar-time portfolio with holding length L each cohort holds 1/L of the capital,
so it trades ``(Σ|w| + |h|) / L`` dollars per dollar of capital when it enters and the same when it exits
(ATOM's ``LinearCostModel`` charges its bps on traded notional the same way; there is no impact term). Netting
between an exiting and an entering cohort is ignored (conservative). Borrow costs on the short leg are not
modelled (a stated limitation: S&P 500 names are general collateral).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
import numpy.typing as npt

BPS: Final = 1e4
LEVELS_BP: Final = (5.0, 10.0, 20.0)  # configs/frozen.yaml strategy.costs_bp_per_side

FloatArray = npt.NDArray[np.float64]


def cohort_notional(
    weights: FloatArray, beta: FloatArray, cohort: npt.NDArray[np.int64], n_cohorts: int
) -> FloatArray:
    """Traded dollars per side of each cohort before the 1/L scaling: Σ|w| + |Σ w·β| (stocks + the hedge).

    ``weights``: (S, n) for S books over n positions; ``cohort``: the cohort index of each position.
    Returns (S, n_cohorts).
    """
    w = np.atleast_2d(np.asarray(weights, dtype=float))
    stock = np.zeros((w.shape[0], n_cohorts))
    hedge = np.zeros((w.shape[0], n_cohorts))
    for s in range(w.shape[0]):
        stock[s] = np.bincount(cohort, weights=np.abs(w[s]), minlength=n_cohorts)
        hedge[s] = np.bincount(cohort, weights=w[s] * beta, minlength=n_cohorts)
    return np.asarray(stock + np.abs(hedge), dtype=float)


def turnover(
    notional: FloatArray,
    entry_idx: npt.NDArray[np.int64],
    exit_idx: npt.NDArray[np.int64],
    holding: int,
    n_sessions: int,
) -> FloatArray:
    """Daily traded dollars per dollar of capital: each cohort's notional / L on its entry and exit sessions.

    ``notional``: (S, n_cohorts); ``entry_idx`` / ``exit_idx``: session positions of each cohort. Returns
    (S, n_sessions).
    """
    nt = np.atleast_2d(np.asarray(notional, dtype=float)) / float(holding)
    out = np.zeros((nt.shape[0], n_sessions))
    for s in range(nt.shape[0]):
        out[s] = np.bincount(entry_idx, weights=nt[s], minlength=n_sessions)
        out[s] += np.bincount(exit_idx, weights=nt[s], minlength=n_sessions)
    return out


def cost(turnover_daily: FloatArray, bp_per_side: float) -> FloatArray:
    """The daily cost: ``bp_per_side`` on every traded dollar."""
    return np.asarray(turnover_daily, dtype=float) * (float(bp_per_side) / BPS)


def net(gross: FloatArray, turnover_daily: FloatArray, bp_per_side: float) -> FloatArray:
    return np.asarray(gross, dtype=float) - cost(turnover_daily, bp_per_side)


def toy_net_return(
    returns: Sequence[float], weights: Sequence[float], beta: Sequence[float], spy: float, bp_per_side: float
) -> float:
    """A one-session book entered and exited the same day (L = 1), written out by hand for the AC2 test:
    Σ w·(r − β·r_SPY) − 2 sides × bp × (Σ|w| + |Σ w·β|)."""
    w, r, b = (np.asarray(x, dtype=float) for x in (weights, returns, beta))
    gross = float(np.sum(w * (r - b * spy)))
    traded = float(np.sum(np.abs(w)) + abs(np.sum(w * b)))
    return gross - 2.0 * traded * bp_per_side / BPS
