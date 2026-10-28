"""NA-13 S3: golden deflated-Sharpe numbers from ATOM's own function, computed ONCE (PRD NA-13 S3, AC3).

Run under ATOM's venv, read-only (no bytecode written into ATOM's tree):

    PYTHONDONTWRITEBYTECODE=1 /Users/amir/GitHub/Atom/.venv/bin/python scripts/na13_dsr_golden.py

The synthetic returns are generated here with a fixed seed and stored in the JSON next to ATOM's results, so
``tests/test_strategy_dsr_golden.py`` needs neither ATOM nor the generator. Writes only
``tests/golden/dsr_atom.json`` in this repository.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from atom_signals.stats import deflated_sharpe_ratio  # ATOM, read-only reference

OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "dsr_atom.json"
SEED = 2026


def cases() -> list[dict[str, object]]:
    rng = np.random.default_rng(SEED)
    normal = rng.normal(0.0005, 0.01, 252)
    skewed = np.exp(rng.normal(0.0, 0.5, 140)) * 0.01 - 0.0113
    fat = rng.standard_t(3, 500) * 0.008 + 0.0006
    negative = rng.normal(-0.001, 0.012, 60)
    crash = np.r_[np.full(99, 0.01), -0.6]  # a strong negative skew and a large kurtosis
    small = rng.normal(0.002, 0.01, 12)
    return [
        {"name": "normal_n1", "returns": normal, "n_trials": 1},
        {"name": "normal_n345", "returns": normal, "n_trials": 345},
        {"name": "normal_n600_var", "returns": normal, "n_trials": 600, "trials_sr_var": 0.004},
        {"name": "skewed_n100", "returns": skewed, "n_trials": 100},
        {"name": "fat_n563_bench", "returns": fat, "n_trials": 563, "benchmark_sr": 0.01},
        {"name": "negative_n10", "returns": negative, "n_trials": 10},
        {"name": "two_trials", "returns": small, "n_trials": 2},
        {"name": "crash_negative_skew", "returns": crash, "n_trials": 50},
        {"name": "one_obs", "returns": np.array([0.01]), "n_trials": 20},
        {"name": "zero_dispersion", "returns": np.zeros(30), "n_trials": 20},
        {"name": "zero_var_given", "returns": normal, "n_trials": 345, "trials_sr_var": 0.0},
    ]


def main() -> int:
    out = []
    for c in cases():
        kw = {k: c[k] for k in ("n_trials", "trials_sr_var", "benchmark_sr") if k in c}
        res = deflated_sharpe_ratio(c["returns"], **kw)  # type: ignore[arg-type]
        out.append(
            {
                "name": c["name"],
                "returns": [float(v) for v in np.asarray(c["returns"], dtype=float)],
                "kwargs": kw,
                "atom": asdict(res),
            }
        )
    doc = {
        "source": "atom_signals.stats.deflated_sharpe_ratio (/Users/amir/GitHub/Atom, read-only)",
        "python": sys.executable,
        "numpy": np.__version__,
        "seed": SEED,
        "cases": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(out)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
