"""Tournament metrics (``tournament.metrics``; PREREG §11.1–11.2): daily Spearman IC, Newey–West summaries,
the 3-class collapse of Q1, ECE and the Spearman helper."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from newsaction.tournament import load_tournament_config
from newsaction.tournament.metrics import (
    FALL,
    FLAT,
    RISE,
    daily_ic,
    ece,
    ic_stats,
    paired,
    realized_class,
    spearman,
    three_class,
)


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for d in range(40):
        x = rng.normal(size=12)
        for i in range(12):
            rows.append({"session": f"2025-08-{d:02d}", "sig": x[i], "y": 0.3 * x[i] + rng.normal()})
    return pd.DataFrame(rows)


def test_daily_ic_is_spearman_per_day() -> None:
    f = frame()
    ic = daily_ic(f, "sig", "y", 5)
    assert len(ic) == 40
    g = f.loc[f["session"] == "2025-08-03"]
    assert ic["2025-08-03"] == pytest.approx(g["sig"].corr(g["y"], method="spearman"))


def test_min_names_and_constant_days() -> None:
    f = frame()
    f.loc[f["session"] == "2025-08-01", "sig"] = 1.0  # a constant signal: IC 0
    f = f.loc[~((f["session"] == "2025-08-02") & (f.index % 12 >= 4))]  # 4 names that day
    ic = daily_ic(f, "sig", "y", 5)
    assert ic["2025-08-01"] == 0.0
    assert "2025-08-02" not in ic.index


def test_ic_stats_and_paired() -> None:
    s = pd.Series([0.1, 0.2, 0.0, 0.1, 0.3, 0.1])
    st = ic_stats(s, 5)
    assert st.mean == pytest.approx(0.8 / 6) and st.n_days == 6
    assert st.se == pytest.approx(abs(st.mean / st.t))
    d = paired(s + 0.05, s, 5)
    assert d.mean == pytest.approx(0.05) and d.n_days == 6


def test_three_class_and_realized_class() -> None:
    p = np.zeros((2, 9))
    p[0, [0, 1, 2, 3]] = 0.25
    p[1, 4], p[1, 8] = 0.5, 0.5
    assert three_class(p).tolist() == [[1.0, 0.0, 0.0], [0.0, 0.5, 0.5]]
    band = load_tournament_config().metric.class_band
    assert band == 0.5
    assert realized_class([-0.5, -0.49, 0.49, 0.5, math.nan], band).tolist() == [FALL, FLAT, FLAT, RISE, -1]


def test_ece() -> None:
    # perfectly calibrated: confidence 0.6, accuracy 0.6 in its bin
    probs = np.tile([0.6, 0.2, 0.2], (10, 1))
    y = np.array([0] * 6 + [1] * 4)
    assert ece(probs, y, 15) == pytest.approx(0.0)
    # always certain and always wrong
    assert ece(np.tile([1.0, 0.0, 0.0], (5, 1)), np.full(5, 2), 15) == pytest.approx(1.0)
    assert math.isnan(ece(probs, np.full(10, -1), 15))


def test_spearman_exact_for_small_n() -> None:
    rho, p, n = spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
    assert n == 5 and rho == pytest.approx(0.8)
    assert p == pytest.approx(0.1333333, abs=1e-6)  # 16 of 120 permutations have |rho| >= 0.8
    assert math.isnan(spearman([1, 2], [2, 1])[0])
