"""configs/training.yaml equals PREREG §7, §9, §11 and PRD NA-08 (each value is also found in the text)."""

from __future__ import annotations

import re

import pytest

from newsaction.events import load_events_config
from newsaction.paths import ROOT
from newsaction.states.questions import load_battery
from newsaction.train import load_training_config, option_keys, training_questions

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
PRD = (ROOT / "NewsAction PRD.md").read_text(encoding="utf-8")
PRD_NA08 = re.sub(r"\s+", " ", PRD[PRD.index("## NA-08 —") : PRD.index("## NA-09 —")])  # unwrapped


def test_training_recipe_equals_prereg_9_1() -> None:
    m = load_training_config().model
    assert "learning rate 2e-5 (backbone) / 1e-4 (heads), max length 1024, ≤ 3 epochs" in PREREG
    assert (m.lr_backbone, m.lr_head, m.max_len, m.max_epochs) == (2e-5, 1e-4, 1024, 3)
    assert "seeds {13, 17, 23}; the reported model is the 3-seed ensemble" in PREREG
    assert m.seeds == (13, 17, 23)
    assert "LR_BACKBONE 2e-5, LR_HEAD 1e-4, EPOCHS ≤ 3" in PRD_NA08
    assert "MAX_LEN = 1024" in PRD_NA08


def test_block_dropout_equals_prereg() -> None:
    ex = load_training_config().export
    assert "**Block dropout:** reaction block 0.3, context block 0.1." in PREREG
    assert "(p = 0.3 sampling at export, seeded)" in PRD_NA08
    assert (ex.reaction_dropout, ex.context_dropout) == (0.3, 0.1)
    assert set(ex.context_blocks) == {"attention", "company", "market"}  # every block but news and reaction


def test_label_definitions_equal_prd_s1() -> None:
    lab = load_training_config().labels
    assert "Q1 bin edges (z: ±0.5, ±1, ±2, ±3 → levels 0..8)" in PRD_NA08
    assert "H-mag = 5-level bin of |z_cc,t| at {0.5, 1, 2, 3}" in PRD_NA08
    assert (
        "events with |G| ≥ 0.5) = reverse / stall / continue from sign(G)·z(O_{t+1}→C_{t+5}) with" in PRD_NA08
    )
    assert "±0.5 bands" in PRD_NA08
    assert lab.edges == (0.5, 1.0, 2.0, 3.0)
    assert (lab.cont_min_abs_g, lab.cont_band) == (0.5, 0.5)
    assert (lab.react_horizon, lab.mag_horizon, lab.cont_horizon) == (4, 0, 5)
    assert "e5 = AR(C_{t−1}→C_{t+4}) / (σ_cc·√5)" in PREREG  # horizon t+4
    assert lab.splits == ("train", "val_a", "val_b")


def test_questions_use_the_frozen_battery_and_the_prd_mag_wording() -> None:
    cfg = load_training_config()
    q = training_questions(cfg)
    battery = load_battery()
    assert q["react"] == battery.questions["justified_move"].request()  # Q1 wording
    assert q["cont"] == battery.questions["continuation"].request()  # Q6 wording
    assert option_keys(q["cont"]) == ["reverse", "stall", "continue"]
    wording = "How large will the stock's move relative to the market and its sector be today?"
    assert f'(score 5: "{wording}"' in PRD_NA08
    assert q["mag"]["instructions"] == wording and q["mag"]["type"] == "score"
    assert len(q["mag"]["criteria"]) == 5
    assert dict(cfg.questions.by_source) == {
        "A_W0": ("react", "mag"),
        "A_W2": ("react", "mag"),
        "B_W2": ("react", "cont"),
    }


def test_derived_and_evaluation_constants() -> None:
    cfg = load_training_config()
    assert "m = (−3.5, −2.5, −1.5, −0.75, 0, 0.75, 1.5, 2.5, 3.5)" in PREREG
    assert cfg.derived.react_midpoints == (-3.5, -2.5, -1.5, -0.75, 0.0, 0.75, 1.5, 2.5, 3.5)
    ev = cfg.evaluation
    assert "ECE (15 bins)" in PREREG and ev.ece_bins == 15
    assert "Newey–West with 5 lags" in PREREG and ev.nw_lags == 5
    assert "block 5, 10,000 reps, seed 2026" in PREREG
    assert (ev.bootstrap_block, ev.bootstrap_reps, ev.bootstrap_seed) == (5, 10_000, 2026)


def test_controls_equal_prereg_9_3_and_prd_s5() -> None:
    c = load_training_config().controls
    assert "not significantly different from 0 (|t| < 2, Newey–West)" in PREREG
    assert "reproduce the IC within ±0.003" in PREREG
    assert (c.shuffle_t_max, c.repro_ic_tol) == (2.0, 0.003)
    runs = load_training_config().kaggle
    assert runs.run(c.shuffle_run).shuffle_labels and runs.run(c.shuffle_run).epochs == 1
    assert runs.run(c.shuffle_run).init == "laya" and runs.run(c.shuffle_run).seed == 13
    a, b = (runs.run(r) for r in c.repro_runs)
    assert (a.init, a.seed) == (b.init, b.seed) == ("laya", 13)


def test_run_plan_order_and_pilot() -> None:
    k = load_training_config().kaggle
    assert "throughput pilot → shuffled-label → Laya-Fin seeds → anchor seeds → repro" in PRD_NA08
    kinds = [("pilot" if r.mode == "pilot" else r.name.split("-")[0]) for r in k.runs]
    assert kinds == ["pilot", "shuffle", "laya", "laya", "laya", "anchor", "anchor", "anchor", "repro"]
    assert "5% of train for 200 steps per INIT" in PRD_NA08
    assert (k.pilot.train_fraction, k.pilot.steps) == (0.05, 200)
    assert {x.init for x in k.pilot.launches} == {"laya", "modernbert"}
    assert "≤ 12 h per session, ~30 GPU-h/week" in PRD_NA08
    assert (k.session_hours, k.weekly_gpu_hours) == (12, 30)
    assert load_training_config().model.time_budget_hours < k.session_hours


def test_pins_agree_with_laya_and_na03() -> None:
    m = load_training_config().model
    laya_revisions = pytest.importorskip("laya.revisions")
    assert m.laya.repo == "convaiinnovations/laya" and m.laya.subfolder == "typed-decisions"
    assert m.laya.revision == laya_revisions.PINNED_REVISIONS["convaiinnovations/laya"]  # reviewed pin
    assert m.anchor.repo == "answerdotai/ModernBERT-large" and m.anchor.subfolder is None
    assert m.anchor.revision == load_events_config().events.tokenizer_revision  # NA-03 / NA-04 tokenizer
    assert (
        re.fullmatch(r"[0-9a-f]{64}", m.laya.weights_sha256)
        and m.laya.weights_sha256 != m.anchor.weights_sha256
    )


def test_no_val_b_or_test_inputs_to_fitting() -> None:
    from newsaction.train import EXPORT_FILES

    assert {n: labelled for n, (_, labelled) in EXPORT_FILES.items()} == {
        "train": True,
        "val_a": True,
        "val_b": False,
        "test_callA": False,
    }
    assert "labels ONLY for train and val-A" in PRD_NA08
