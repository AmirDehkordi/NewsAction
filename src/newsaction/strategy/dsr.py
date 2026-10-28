"""NA-13 deflated Sharpe ratio (PREREG §12; PRD NA-13 S3): Bailey and López de Prado (2014) with the Mertens
(2002) standard error of the Sharpe ratio under non-normal returns.

A re-implementation of ATOM's ``atom_signals.stats.deflated_sharpe_ratio`` (read-only reference), checked
against numbers ATOM's own function produced once on fixed synthetic returns (``tests/golden/dsr_atom.json``,
``scripts/na13_dsr_golden.py``; agreement within 1e-6). On T per-period returns x:

- SR = mean(x)/sd(x) (per period, ddof 1, not annualized); γ3, γ4 = the standardized third and fourth moments
  (population; γ4 non-excess);
- V = ``trials_sr_var`` (the variance of the trial Sharpes) or, when not given, the analytic
  (1 + SR²/2)/(T − 1);
- SR0 = ``benchmark_sr`` + √V·((1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))), γ Euler–Mascheroni; SR0 = the
  benchmark when N < 2 or V ≤ 0;
- DSR statistic = (SR − SR0)·√(T − 1)/√(1 − γ3·SR + (γ4 − 1)/4·SR²); the deflated probability Φ(statistic).

Degenerate inputs (T < 2, no dispersion, a non-positive denominator) return a statistic and probability of 0,
as ATOM does.

``n_trials`` (``trial_count``): the rows of ``ledgers/trials.jsonl``, i.e. the rows of kind "strategy" (NA-13)
plus every model, encoding and filter selection trial logged by NA-03…NA-11 (PRD NA-13 S3; PREREG §12's
"N = trials in ledgers/trials.jsonl"); ``trial_parts`` lists the count by kind.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
from scipy.stats import norm  # type: ignore[import-untyped, unused-ignore]

from newsaction.ledger import TrialLedger

EULER_MASCHERONI: Final = 0.5772156649015329
STRATEGY_KIND: Final = "strategy"


@dataclass(frozen=True)
class DSR:
    sharpe: float
    sr0: float
    deflated_stat: float
    prob: float
    skew: float
    kurt: float
    n_obs: int
    n_trials: int
    trials_sr_var: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def expected_max_sharpe(n_trials: int, trials_sr_var: float) -> float:
    """E[max SR] over ``n_trials`` independent null trials with Sharpe variance ``trials_sr_var``."""
    if n_trials < 2 or trials_sr_var <= 0.0:
        return 0.0
    z1 = float(norm.ppf(1.0 - 1.0 / n_trials))
    z2 = float(norm.ppf(1.0 - 1.0 / (n_trials * math.e)))
    return math.sqrt(trials_sr_var) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def deflated_sharpe(
    returns: Sequence[float] | npt.NDArray[np.float64],
    *,
    n_trials: int,
    trials_sr_var: float | None = None,
    benchmark_sr: float = 0.0,
) -> DSR:
    x = np.asarray(returns, dtype=float)
    t = int(x.size)
    if t < 2:
        return DSR(0.0, 0.0, 0.0, 0.0, 0.0, 3.0, t, n_trials, 0.0)
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    if sd <= 0.0:
        return DSR(0.0, 0.0, 0.0, 0.0, 0.0, 3.0, t, n_trials, 0.0)
    sr = mean / sd
    z = (x - mean) / sd
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    var = (1.0 + 0.5 * sr**2) / (t - 1) if trials_sr_var is None else float(trials_sr_var)
    sr0 = benchmark_sr + expected_max_sharpe(n_trials, var)
    denom = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr**2
    if denom <= 0.0:
        return DSR(sr, sr0, 0.0, 0.0, skew, kurt, t, n_trials, var)
    stat = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(denom)
    return DSR(sr, sr0, stat, float(norm.cdf(stat)), skew, kurt, t, n_trials, var)


def trial_parts(path: Path | None = None) -> dict[str, int]:
    """Rows of the trials ledger by kind."""
    return dict(sorted(Counter(r["kind"] for r in TrialLedger(path).records()).items()))


def trial_count(path: Path | None = None) -> int:
    """n_trials for the DSR: every row of the ledger (strategy rows plus the selection trials)."""
    return sum(trial_parts(path).values())
