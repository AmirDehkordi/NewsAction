"""NA-12 S2 / AC3: ``run_all`` calls the frozen spec with PREREG's inference parameters (PRD NA-12).

- The test run's configuration is ``spec.load_config()`` itself and holds PREREG §11.3–§11.4's numbers (day
  × tier FE; two-way clustering by session and firm; Driscoll–Kraay with 5 lags; stationary block bootstrap
  with block 5, 10,000 reps, seed 2026; Holm at 0.05 over H1, H1b, H2, H3, H4; BH at q 0.10). The rehearsal
  moves only the ridge protocol's splits and A3.5's fit splits.
- On synthetic frames, every OLS, bootstrap and Holm call that ``primary`` makes receives those values
  (spies on ``inference.ols_fe``, ``metrics.Bootstrap.draw`` and ``metrics.holm``), and §1.3 pairs the
  primary's Holm-adjusted p with the anchor's own p.
- The secondary families are the §15 NA-12 row's; the model roles are the frozen ones; a test run before
  the unblinding refuses, and a rehearsal never writes into the repository.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from newsaction.analysis import inference as inf
from newsaction.analysis import metrics as mx
from newsaction.analysis import run_all, spec
from newsaction.paths import ROOT, Layout
from spec_fakes import panel

PREREG_BOOT = {"block": 5.0, "reps": 10_000, "seed": 2026, "ci": 0.95}
PREREG_INFERENCE = {"fe": ("session", "tier"), "cluster": ("session", "company_id"), "dk_lags": 5}


def test_the_test_run_uses_the_frozen_configuration_with_prereg_numbers() -> None:
    cfg = run_all.config_for(rehearsal=False)
    assert cfg == spec.load_config()
    assert cfg.bootstrap.model_dump() == PREREG_BOOT
    assert cfg.inference.model_dump() == PREREG_INFERENCE
    fam = cfg.multiple_testing
    assert (fam.primary.method, fam.primary.alpha, fam.primary.tests) == (
        "holm",
        0.05,
        ("H1", "H1b", "H2", "H3", "H4"),
    )
    assert (fam.secondary.method, fam.secondary.q) == ("bh", 0.10)
    assert (fam.heterogeneity.method, fam.heterogeneity.q) == ("bh", 0.10)
    assert (cfg.ridge.fit_split, cfg.ridge.lambda_split, cfg.ridge.eval_split) == ("val_b", "val_a", "test")
    assert cfg.sample.embargo and cfg.metrics.nw_lags == 5


def test_the_rehearsal_moves_only_the_fitting_splits() -> None:
    frozen, reh = spec.load_config(), run_all.config_for(rehearsal=True)
    assert (reh.ridge.fit_split, reh.ridge.lambda_split, reh.ridge.eval_split) == ("val_a", "val_a", "val_b")
    assert reh.market.eval_split == "val_b" and reh.market.fit_splits == ("val_a",)
    same = {k: v for k, v in reh.model_dump().items() if k not in ("ridge", "market")}
    assert same == {k: v for k, v in frozen.model_dump().items() if k not in ("ridge", "market")}
    assert reh.ridge.lambdas == frozen.ridge.lambdas and reh.ridge.standardize == frozen.ridge.standardize


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(primary, anchor) frames: the primary's N̂ moves z_on, y2 and z_id; the anchor's only z_id."""
    rng = np.random.default_rng(2026)
    df = panel(n_firms=40)
    n = len(df)
    df["symbol_id"] = df["company_id"]
    prim, anch = rng.normal(0, 1, n), rng.normal(0, 1, n)
    df["z_on"] = 0.6 * prim + rng.normal(0, 1, n)
    df["z_id"] = 0.3 * prim + 0.3 * anch + rng.normal(0, 1, n)
    df["z_cc"] = df["z_on"] + df["z_id"]
    df["g_d2"] = df["z_cc"]
    df["g_d1"] = 0.5 * df["z_on"] + rng.normal(0, 1, n)
    df["y1"] = rng.normal(0, 1, n)
    for c in ("z_m5", "z_m20", "z_m60", "z_vol", "har_d", "har_w", "har_m", "earnings"):
        df[c] = rng.normal(0, 1, n)
    out = []
    for sig in (prim, anch):
        f = df.copy()
        f["a0_n_hat"] = f["a2_n_hat"] = sig
        f["y2"] = 0.3 * sig - 0.1 * f["g_d2"] + f["day_tier"] + rng.normal(0, 1, n)
        f["a0_abs_n_hat"], f["a0_mag_mean"] = np.abs(sig), rng.normal(0, 1, n)
        f["b2_c"], f["b2_w"] = rng.normal(0, 1, n), rng.normal(0, 1, n)
        out.append(f)
    return out[0], out[1]


def test_primary_passes_prereg_parameters_and_pairs_holm_with_the_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ols_calls: list[dict[str, Any]] = []
    boot_calls: list[tuple[int, float, int]] = []
    holm_calls: list[list[str]] = []
    ols_fe, draw, holm = inf.ols_fe, mx.Bootstrap.draw.__func__, mx.holm  # type: ignore[attr-defined]

    def spy_ols(*args: Any, **kw: Any) -> Any:
        ols_calls.append(kw)
        return ols_fe(*args, **kw)

    def spy_draw(cls: Any, grid: Any, reps: int, block: float, seed: int) -> Any:
        boot_calls.append((reps, block, seed))
        return draw(cls, grid, reps, block, seed)

    def spy_holm(p: Any) -> Any:
        holm_calls.append(sorted(p))
        return holm(p)

    monkeypatch.setattr(inf, "ols_fe", spy_ols)
    monkeypatch.setattr(mx.Bootstrap, "draw", classmethod(spy_draw))
    monkeypatch.setattr(mx, "holm", spy_holm)
    trained = [m for m in run_all.MODELS if m.key in (run_all.PRIMARY, run_all.ANCHOR)]
    monkeypatch.setattr(run_all, "MODELS", tuple(trained))
    prim, anch = _frames()
    frames = {run_all.PRIMARY: prim, run_all.ANCHOR: anch}
    cfg = run_all.config_for(rehearsal=False)
    ctx = run_all.Ctx(
        Layout(ROOT), cfg, False, frames, frames, {}, pd.DataFrame(), pd.DataFrame(), [], None, tmp_path
    )
    out = run_all.primary(ctx)
    assert ols_calls and all(
        (tuple(k["fe"]), tuple(k["cluster"]), k["dk_lags"], k["time"])
        == (PREREG_INFERENCE["fe"], PREREG_INFERENCE["cluster"], 5, "session")
        for k in ols_calls
    )
    assert boot_calls and set(boot_calls) == {(10_000, 5.0, 2026)}
    assert ["H1", "H1b", "H2", "H3", "H4"] in holm_calls
    # §1.3 recomputed from the reported numbers: the primary's Holm p with the anchor's own one-sided p
    for t in ("H1", "H1b", "H2", "H3", "H4"):
        p, a = out["directional"]["primary"][t], out["directional"]["anchor"][t]
        ok_p = out["holm"][t] < 0.05 and p["estimate"] > 0
        ok_a = a["p"] < 0.05 and a["estimate"] > 0
        expect = "general" if ok_p and ok_a else "model-specific" if ok_p else "not supported"
        assert out["headline"][t] == expect
    assert out["headline"]["H1"] == "model-specific" and out["headline"]["H1b"] == "general"
    assert out["holm"]["H1"] >= out["directional"]["primary"]["H1"]["p"]


def test_the_secondary_families_are_the_recorded_ones() -> None:
    h2c = set(spec.h2c_tests({}, {"rungs": {}}, {"rungs": {}}, spec.load_config()))
    assert run_all.SECONDARY[run_all.PRIMARY] == (
        "H5",
        "H7",
        *sorted(h2c, key=list(run_all.SECONDARY[run_all.PRIMARY]).index),
    )
    assert h2c <= set(run_all.SECONDARY[run_all.ANCHOR]) and h2c <= set(run_all.SECONDARY[run_all.API])
    assert {"H6", "A3.4"} <= set(run_all.SECONDARY[run_all.API])
    assert not {"H6", "A3.4"} & set(run_all.SECONDARY[run_all.PRIMARY])
    assert run_all.POOLED_FROM_API == ("H6", "A3.4")


def test_model_roles_are_the_frozen_ones(tmp_layout: Layout) -> None:
    run_all.check_models()
    frozen = tmp_layout.configs / "frozen.yaml"
    text = frozen.read_text()
    frozen.write_text(
        text.replace("\n  anchor: anchor\n", "\n  anchor: laya_fin\n")
    )  # load_plan does not check it
    with pytest.raises(run_all.RunAllError, match="anchor"):
        run_all.check_models(tmp_layout)
    frozen.write_text(
        text.replace("comparators: [liquid/d1-ultra, respan/span-02", "comparators: [respan/span-02")
    )
    with pytest.raises(run_all.RunAllError, match="comparators"):
        run_all.check_models(tmp_layout)


def test_a_test_run_waits_for_the_unblinding_and_a_rehearsal_stays_outside(tmp_layout: Layout) -> None:
    with pytest.raises(run_all.RunAllError, match="unblinding"):
        run_all.run(layout=tmp_layout)
    with pytest.raises(run_all.RunAllError, match="outside the repository"):
        run_all.run(rehearsal=True, out_root=ROOT / "artifacts" / "x")


def test_explanation_features_interact_x_and_each_reason_with_n_hat() -> None:
    r = pd.DataFrame(
        {
            "event_id": ["a", "b", "c"],
            "b2_x": [1.0, 0.5, np.nan],
            "a2_n_hat": [2.0, -1.0, 0.5],
            "b2_label_move_reason": ["earnings_results", "no_identifiable_news", None],
        }
    )
    out = run_all.explanation_features(r)
    assert out["b2_x_n_hat"].tolist()[:2] == [2.0, -0.5] and math.isnan(out["b2_x_n_hat"].iloc[2])
    cols = run_all.reason_columns(out)
    assert cols == ["reason__earnings_results__n_hat", "reason__no_identifiable_news__n_hat"]
    assert out[cols[0]].tolist()[:2] == [2.0, 0.0] and out[cols[1]].tolist()[:2] == [0.0, -1.0]
    assert out[cols].iloc[2].isna().all()


def test_answers_needs_values_on_every_split() -> None:
    f = pd.DataFrame({"split": ["val_a", "val_b", "test"], "x": [1.0, np.nan, 2.0]})
    assert run_all.answers(f, ["x"], ["val_a", "test"])
    assert not run_all.answers(f, ["x"], ["val_a", "val_b"])
    assert not run_all.answers(f, ["y"], ["val_a"])


def test_test_targets_refuse_member_rows_missing_from_the_test_inputs(tmp_layout: Layout) -> None:
    """A member row of targets_test without its t−1 row in panel_test_inputs is a join failure; a member
    whose tier is missing (a spin-off joiner, as in the public panel) is kept."""
    from newsaction import io
    from newsaction.analysis import frames

    keys = pd.DataFrame({"session": [date(2030, 1, 2)] * 3, "symbol_id": [1, 2, 3]})
    tt = keys.assign(split="test", member=True, is_rep=True, company_id=[11, 12, 13])
    for c in {*frames.PANEL_COLUMNS, *frames.INTRADAY_COLUMNS} - {
        *tt.columns,
        "dv_tier",
        "z_m5",
        "z_m20",
        "z_m60",
    }:
        tt[c] = 0.0
    t1 = keys.assign(tier=["top100", None, "rest"], dv_tier="mid", z_m5=0.0, z_m20=0.0, z_m60=0.0)
    io.write_parquet(tt, frames.TARGETS_TEST, producer="test", description="synthetic", layout=tmp_layout)
    io.write_parquet(t1, frames.TEST_INPUTS, producer="test", description="synthetic", layout=tmp_layout)
    panel, intraday, members = frames.test_targets(tmp_layout)
    assert len(intraday) == 3
    assert len(panel) == 3 and members["tier"].isna().sum() == 1
    io.write_parquet(
        t1.iloc[:2], frames.TEST_INPUTS, producer="test", description="synthetic", layout=tmp_layout
    )
    with pytest.raises(frames.FrameError, match="missing from panel_test_inputs"):
        frames.test_targets(tmp_layout)
