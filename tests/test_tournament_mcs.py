"""PRD NA-06 AC2: the Model Confidence Set (``tournament.mcs``).

Synthetic losses with a known best model, and agreement with ``arch.bootstrap.MCS`` given the same bootstrap
indices."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from arch.bootstrap import MCS

from newsaction.paths import ROOT
from newsaction.tournament import load_tournament_config
from newsaction.tournament.mcs import DAILY_IC_FILE, MCS_FILE, loss_matrix, mcs, stationary_indices


def synthetic(t: int = 60, k: int = 8, gap: float = 0.5, seed: int = 1) -> pd.DataFrame:
    """Daily losses: model m0 is the best by ``gap`` standard deviations, the others are equal."""
    rng = np.random.default_rng(seed)
    common = rng.normal(size=(t, 1))
    noise = rng.normal(scale=0.5, size=(t, k))
    means = np.full(k, gap)
    means[0] = 0.0
    return pd.DataFrame(common + noise + means, columns=[f"m{i}" for i in range(k)])


def test_known_best_model_is_the_only_survivor() -> None:
    res = mcs(synthetic(gap=1.5), alpha=0.10, reps=2000, block=5, seed=2026, statistic="R")
    assert res.included == ["m0"]
    assert res.pvalues["m0"] == 1.0
    assert all(res.pvalues[m] < 0.10 for m in res.models if m != "m0")


def test_known_best_model_with_the_max_statistic() -> None:
    res = mcs(synthetic(gap=1.5), alpha=0.10, reps=2000, block=5, seed=2026, statistic="max")
    assert res.included == ["m0"]


def test_equal_models_all_survive() -> None:
    res = mcs(synthetic(gap=0.0, seed=3), alpha=0.10, reps=2000, block=5, seed=2026)
    assert len(res.included) >= 7  # at most a marginal exclusion at the 10% level


def test_the_best_model_is_always_in_the_set() -> None:
    for seed in range(5):
        df = synthetic(gap=0.15, seed=seed)
        res = mcs(df, alpha=0.10, reps=1000, block=5, seed=seed)
        assert df.mean().idxmin() in res.included


def test_mcs_pvalues_are_monotone_in_the_elimination_order() -> None:
    res = mcs(synthetic(gap=0.4, seed=7), alpha=0.10, reps=1000, block=5, seed=1)
    seq = [s["mcs_pvalue"] for s in res.steps]
    assert seq == sorted(seq)
    assert len(res.steps) == len(res.models)


def test_identical_models_are_indistinguishable() -> None:
    df = synthetic(gap=1.0)
    df["m0_copy"] = df["m0"]
    res = mcs(df, alpha=0.10, reps=1000, block=5, seed=2026)
    assert {"m0", "m0_copy"} <= set(res.included)


@pytest.mark.parametrize("method", ["R", "max"])
def test_same_pvalues_as_arch_with_the_same_bootstrap(method: str) -> None:
    df = synthetic(t=40, k=6, gap=0.3, seed=11)
    ref = MCS(df, size=0.10, reps=500, block_size=5, method=method, bootstrap="stationary", seed=5)  # type: ignore[arg-type]
    ref.compute()
    indices = np.asarray(ref._bootstrap_indices)
    mine = mcs(df, alpha=0.10, reps=500, block=5, seed=None, statistic=method, indices=indices)  # type: ignore[arg-type]
    theirs = ref.pvalues["Pvalue"].to_dict()
    for m in df.columns:
        assert mine.pvalues[m] == pytest.approx(theirs[m], abs=1e-12)


def test_stationary_bootstrap_blocks() -> None:
    idx = stationary_indices(50, 4000, 5.0, np.random.default_rng(0))
    assert idx.shape == (4000, 50) and idx.min() >= 0 and idx.max() < 50
    cont = (idx[:, 1:] == (idx[:, :-1] + 1) % 50).mean()
    assert cont == pytest.approx(1 - 1 / 5, abs=0.01)  # a new block starts with probability 1/block


def test_losses_must_be_complete() -> None:
    df = synthetic()
    df.iloc[3, 2] = np.nan
    with pytest.raises(ValueError, match="finite"):
        mcs(df, alpha=0.1, reps=100, block=5, seed=1)


def test_loss_matrix_keeps_common_days_and_negates_ic() -> None:
    long = pd.DataFrame(
        {
            "model": ["a", "a", "b", "b", "a"],
            "session": ["d1", "d2", "d1", "d3", "d3"],
            "ic": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )
    lm = loss_matrix(long)
    assert list(lm.index) == ["d1", "d3"]
    assert lm.loc["d1", "a"] == -0.1 and lm.loc["d3", "b"] == -0.4


def test_config_matches_prereg() -> None:
    c = load_tournament_config().mcs
    assert (c.alpha, c.block, c.reps, c.loss) == (0.10, 5, 10000, "neg_daily_ic")


def test_recorded_mcs_reproduces_from_the_daily_ic_file() -> None:
    """The committed stage-1 MCS is what mcs.py gives on the committed daily ICs (same seed)."""
    if not (ROOT / MCS_FILE).is_file() or not (ROOT / DAILY_IC_FILE).is_file():
        pytest.skip("the select stage has not run")
    rec = json.loads((ROOT / MCS_FILE).read_text(encoding="utf-8"))["stage1"]
    cfg = load_tournament_config()
    losses = loss_matrix(pd.read_csv(ROOT / DAILY_IC_FILE))
    res = mcs(
        losses,
        alpha=rec["alpha"],
        reps=rec["reps"],
        block=rec["block"],
        seed=cfg.seed,
        statistic=rec["statistic"],
    )
    assert res.included == rec["included"]
    assert res.pvalues == pytest.approx(rec["pvalues"])
