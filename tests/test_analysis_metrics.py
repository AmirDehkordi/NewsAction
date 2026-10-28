"""analysis.metrics: the copied helpers equal the originals; bootstrap, p-values, R², AUC, maps, Holm, BH."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from newsaction.analysis import metrics as mx
from newsaction.news import audit
from newsaction.tournament import mcs
from newsaction.tournament import metrics as tmx


def frame(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 600
    df = pd.DataFrame({"session": rng.integers(0, 40, n), "s": rng.normal(size=n), "t": rng.normal(size=n)})
    df.loc[df["session"] == 3, "s"] = 1.0  # a constant day
    df.loc[rng.random(n) < 0.05, "t"] = np.nan
    return df


def test_copies_equal_the_originals() -> None:
    df = frame()
    pd.testing.assert_series_equal(mx.daily_ic(df, "s", "t", 5), tmx.daily_ic(df, "s", "t", 5))
    x = pd.Series(np.random.default_rng(1).normal(size=50))
    assert mx.nw_t(x, 5) == audit.nw_t(x, 5)
    a = mx.stationary_indices(30, 50, 5.0, np.random.default_rng(2))
    b = mcs.stationary_indices(30, 50, 5.0, np.random.default_rng(2))
    assert np.array_equal(a, b)
    p = np.random.default_rng(3).dirichlet(np.ones(9), size=20)
    assert np.allclose(mx.three_class(p), tmx.three_class(p))
    y = mx.realized_class(np.random.default_rng(4).normal(size=20), 0.5)
    assert mx.ece(mx.three_class(p), y, 15) == tmx.ece(tmx.three_class(p), y, 15)


def test_bootstrap_counts_match_indices_and_means() -> None:
    grid = [f"d{i:02d}" for i in range(25)]
    boot = mx.Bootstrap.draw(grid, 200, 5.0, 2026)
    assert boot.counts.sum(axis=1).tolist() == [25.0] * 200
    series = pd.Series(np.arange(25, dtype=float), index=grid)
    assert np.allclose(boot.means(series), boot.idx.mean(axis=1))
    assert np.allclose(boot.sums(series), boot.idx.sum(axis=1))
    # a missing day counts as missing in the mean, as zero in a sum
    gap = series.drop("d00")
    assert np.all(np.isfinite(boot.means(gap)))


def test_centred_bootstrap_p() -> None:
    boot = np.random.default_rng(5).normal(0.3, 0.1, 9999)
    assert mx.boot_p(boot, 0.3, "greater") < 0.01
    assert mx.boot_p(boot, 0.3, "less") > 0.99
    assert mx.boot_p(boot - 0.3, 0.0, "greater") == pytest.approx(0.5, abs=0.02)
    assert mx.boot_p_two(boot, 0.3) < 0.01


def test_daily_mean_estimate_and_ratio() -> None:
    grid = list(range(60))
    boot = mx.Bootstrap.draw(grid, 2000, 5.0, 2026)
    rng = np.random.default_rng(6)
    daily = pd.Series(rng.normal(0.05, 0.1, 60), index=grid)
    est = mx.daily_mean_estimate(daily, boot, 5, 0.95, "greater")
    assert est.value == pytest.approx(daily.mean()) and est.ci_low < est.value < est.ci_high
    num, den = pd.Series(rng.random(60), index=grid), pd.Series(1 + rng.random(60), index=grid)
    r = mx.ratio_estimate(num, den, boot, 0.95, "greater")
    assert r.value == pytest.approx(num.sum() / den.sum())


def test_oos_r2_quintiles_auc_and_maps() -> None:
    y = np.array([1.0, -1.0, 2.0, -2.0])
    assert mx.oos_r2(y, y) == 1.0 and mx.oos_r2(y, np.zeros(4)) == 0.0
    assert mx.oos_r2(y, np.zeros(4), mean=1.0) == pytest.approx(1 - 10 / 14)
    df = pd.DataFrame({"session": [0] * 10, "s": np.arange(10.0), "t": np.arange(10.0)})
    assert mx.quintile_spread(df, "s", "t", 5).iloc[0] == pytest.approx(8.0)
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(7)
    s, lab = rng.normal(size=300), rng.random(300) < 0.3
    assert mx.auc(s, lab.astype(float)) == pytest.approx(roc_auc_score(lab, s))
    m = {"x": [-1.0, 0.0, 2.0], "y": [-0.5, 0.0, 1.0]}
    assert mx.apply_map([-5, -1, 1, 2, 9, np.nan], m)[:5].tolist() == [-0.5, -0.5, 0.5, 1.0, 1.0]
    with pytest.raises(ValueError):
        mx.apply_map([0.0], {"x": [1.0, 0.0], "y": [0.0, 1.0]})


def test_probability_scores_and_skill() -> None:
    p = np.array([[0.7, 0.2, 0.1], [0.1, 0.1, 0.8]])
    y = np.array([0, 2])
    assert mx.log_loss(p, y) == pytest.approx(-(math.log(0.7) + math.log(0.8)) / 2)
    assert mx.brier(p, y) == pytest.approx(((0.3**2 + 0.2**2 + 0.1**2) + (0.1**2 + 0.1**2 + 0.2**2)) / 2)
    assert mx.climatology(np.array([0, 0, 1, 2, -1])).tolist() == [0.5, 0.25, 0.25]
    assert mx.skill(0.5, 1.0) == 0.5
    assert mx.entropy_confidence(np.array([[1.0, 0.0], [0.5, 0.5]])).tolist() == [1.0, 0.0]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_holm_and_bh_equal_statsmodels(seed: int) -> None:
    p = np.random.default_rng(seed).random(8) ** 2
    keys = [f"t{i}" for i in range(8)]
    ours_h = mx.holm(dict(zip(keys, p, strict=True)))
    ours_b = mx.bh(dict(zip(keys, p, strict=True)))
    assert [ours_h[k] for k in keys] == pytest.approx(multipletests(p, method="holm")[1].tolist())
    assert [ours_b[k] for k in keys] == pytest.approx(multipletests(p, method="fdr_bh")[1].tolist())
    with_nan = mx.holm({"a": 0.01, "b": math.nan})
    assert with_nan["a"] == 0.01 and math.isnan(with_nan["b"])
