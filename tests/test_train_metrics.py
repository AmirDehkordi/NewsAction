"""Val-A metrics of the trained models (PREREG §11; PRD NA-08 S5, S8, AC5): the val-A guard, ECE, T, IC."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from newsaction.train.metrics import (
    SplitError,
    bootstrap_ci,
    calibration,
    ece,
    fit_temperature,
    ic_summary,
    nll,
    require_val_a,
    softmax,
)


def _panel(n_days: int = 60, n: int = 40, beta: float = 0.3, split: str = "val_a") -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for d in range(n_days):
        s = rng.normal(size=n)
        rows.append(
            pd.DataFrame(
                {
                    "session": date(2025, 7, 1) + timedelta(days=d),
                    "split": split,
                    "signal": s,
                    "target": beta * s + rng.normal(size=n),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


@pytest.mark.parametrize("split", ["val_b", "test", "train"])
def test_metrics_refuse_any_split_but_val_a(split: str) -> None:
    with pytest.raises(SplitError):
        require_val_a(pd.Series(["val_a", split]))
    with pytest.raises(SplitError):
        ic_summary(_panel(split=split), "signal", "target", ci=False)
    f = pd.DataFrame({"split": [split], "label": [0], "probabilities": [[0.6, 0.4]]})
    with pytest.raises(SplitError):
        calibration(f)


def test_ic_summary_finds_a_planted_signal_and_not_noise() -> None:
    out = ic_summary(_panel(beta=0.3), "signal", "target")
    assert out["ic"] > 0.2 and out["nw_t"] > 5 and out["days"] == 60
    lo, hi = out["ci95"]
    assert lo < out["ic"] < hi
    null = ic_summary(_panel(beta=0.0), "signal", "target", ci=False)
    assert abs(null["nw_t"]) < 3


def test_bootstrap_is_seeded() -> None:
    s = pd.Series(np.random.default_rng(3).normal(0.05, 0.1, size=80))
    assert bootstrap_ci(s) == bootstrap_ci(s)


def test_ece_and_nll() -> None:
    p = np.array([[0.9, 0.1], [0.9, 0.1], [0.4, 0.6], [0.4, 0.6]])
    y = np.array([0, 1, 1, 1])
    assert ece(p, y, 15) == pytest.approx(0.5 * abs(0.9 - 0.5) + 0.5 * abs(0.6 - 1.0))
    z = np.log(p)
    assert nll(z, y) == pytest.approx(float(np.mean(-np.log(p[np.arange(4), y]))))


def test_fit_temperature_recovers_a_planted_one() -> None:
    rng = np.random.default_rng(1)
    z = rng.normal(size=(5000, 9)) * 1.5
    y = np.array([rng.choice(9, p=softmax(r, 0.6)) for r in z])
    t = fit_temperature(z, y)
    assert t == pytest.approx(0.6, rel=0.08)
    assert nll(z, y, t) < nll(z, y, 1.0)


def test_calibration_uses_labelled_rows_only() -> None:
    f = pd.DataFrame(
        {"split": "val_a", "label": [0, 1, None], "probabilities": [[0.8, 0.2], [0.3, 0.7], [0.5, 0.5]]}
    )
    out = calibration(f)
    assert out["n"] == 2 and out["accuracy"] == 1.0
