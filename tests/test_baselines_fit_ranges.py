"""Every fitted baseline is fit on train only and tuned and calibrated on val-A only (PRD NA-09 AC1;
CLAUDE.md B9; PREREG §4).

The fits run on a synthetic frame (``baselines_fakes``) in a throwaway repository: a baseline that took a
val-A (or later) row into its fit, or tuned outside val-A, records that range and ``check_fit_record``
refuses to save it, so these tests go red. The stored records of the real run are checked too.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from baselines_fakes import fit_all, frame, isolated, scrambled_val_a, small_config
from newsaction.baselines import BaselineError, baselines_config, sentiment
from newsaction.baselines.fitting import MODELS_DIR, fit_rows, load_record, tune_rows
from newsaction.baselines.schema import FitRecord, Range, check_fit_record
from newsaction.config import load_splits
from newsaction.paths import ROOT, Layout

SPLITS = load_splits().splits
FITTED = {
    "sentiment": ("e5", "abs_z_cc"),
    "embed_ridge": ("e5", "abs_z_cc"),
    "tags_gbm": ("e5", "abs_z_cc"),
    "price_only": ("e5", "abs_z_cc", "y2"),
}


def inside(r: Range, split: str) -> bool:
    rng = SPLITS[split]  # type: ignore[index]
    return r.split == split and rng.start <= r.start <= r.end <= rng.end


def test_every_fit_is_train_only_and_every_tuning_val_a_only(tmp_layout: Layout) -> None:
    isolated(fit_all, str(tmp_layout.root))
    cfg = small_config(baselines_config(tmp_layout))
    f = frame()
    for model, targets in FITTED.items():
        for target in targets:
            rec = load_record(model, target, tmp_layout)
            assert inside(rec.fit, "train"), (model, target, rec.fit)
            # the recorded range is that of the rows used: every train row with a target, nothing else
            want = fit_rows(f, cfg, target)
            assert rec.fit.n_rows == len(want) and rec.fit.end == max(want["session"])
            if rec.tune is not None:
                assert inside(rec.tune, "val_a"), (model, target, rec.tune)
                tu = tune_rows(f, cfg, target)
                assert rec.tune.n_rows == len(tu) and not bool(tu["embargo"].any())
            if rec.calibration is not None:
                assert inside(rec.calibration, "val_a"), (model, target, rec.calibration)
            check_fit_record(rec, tmp_layout)
    # the models that have hyper-parameters were tuned on val-A
    for model in ("embed_ridge", "tags_gbm", "price_only"):
        for target in FITTED[model]:
            assert load_record(model, target, tmp_layout).tune is not None


def test_fit_rows_are_the_train_split_only() -> None:
    cfg = baselines_config()
    f = frame()
    for target in ("e5", "abs_z_cc", "y2"):
        assert set(fit_rows(f, cfg, target)["split"]) == {"train"}
        tu = tune_rows(f, cfg, target)
        assert set(tu["split"]) == {"val_a"} and not bool(tu["embargo"].any())


def test_predictions_do_not_change_when_val_a_targets_change(tmp_layout: Layout) -> None:
    """The fit sees no val-A target: scrambling them moves no train-fitted N_hat or mag_hat (only the val-A
    choices of λ and of the grid, and the val-A probability maps, may move; one-point grids fix them)."""
    for name, dn, dm in isolated(scrambled_val_a, str(tmp_layout.root)):
        assert np.abs(dn).max() == pytest.approx(0.0, abs=1e-9), name
        assert np.abs(dm).max() == pytest.approx(0.0, abs=1e-9), name


def test_check_fit_record_refuses_ranges_outside_their_split(tmp_layout: Layout) -> None:
    ok_fit = Range(split="train", start=date(2024, 7, 1), end=date(2025, 6, 30), n_rows=10, n_sessions=5)
    ok_tune = Range(split="val_a", start=date(2025, 7, 9), end=date(2025, 9, 30), n_rows=10, n_sessions=5)
    base = FitRecord(
        model="m", target="e5", point="D0", features=("x",), fit=ok_fit, tune=ok_tune, selected={}, seed=1
    )
    check_fit_record(base, tmp_layout)
    bad = [
        {"fit": ok_fit.model_copy(update={"end": date(2025, 7, 1)})},  # a val-A row in the fit
        {"fit": ok_fit.model_copy(update={"start": date(2024, 6, 28)})},  # a robustness row in the fit
        {"fit": ok_fit.model_copy(update={"split": "val_a"})},
        {"tune": ok_tune.model_copy(update={"end": date(2025, 10, 1)})},  # tuned on val-B
        {"tune": ok_tune.model_copy(update={"start": date(2025, 6, 30)})},
        {"calibration": ok_tune.model_copy(update={"split": "val_b"})},
        {"calibration": ok_tune.model_copy(update={"end": date(2026, 1, 2)})},
    ]
    for upd in bad:
        with pytest.raises(BaselineError):
            check_fit_record(base.model_copy(update=upd), tmp_layout)


def test_a_fit_on_train_plus_val_a_is_refused(tmp_layout: Layout) -> None:
    """The guard on the save path: copies of the val-A rows labelled train (so the fit takes them) leave the
    train dates, and nothing is written."""
    cfg = small_config(baselines_config(tmp_layout))
    f = frame()
    leak = f.loc[f["split"] == "val_a"].assign(split="train")
    leak["event_id"] = leak["event_id"] + ":leak"
    f = pd.concat([f, leak], ignore_index=True)
    with pytest.raises(BaselineError):
        sentiment.fit_predict(f, cfg, tmp_layout)
    assert not (tmp_layout.work / MODELS_DIR / "sentiment_e5.json").exists()


def stored_records() -> list[str]:
    d = ROOT / "work" / MODELS_DIR
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.glob("*.json"))


@pytest.mark.parametrize("name", stored_records() or ["(none)"])
def test_stored_fit_records(name: str) -> None:
    if name == "(none)":
        pytest.skip("work/baselines/models is absent (run the NA-09 fit stage)")
    doc = json.loads((ROOT / "work" / MODELS_DIR / name).read_text(encoding="utf-8"))
    rec = FitRecord.model_validate(doc["record"])
    assert doc["model"]
    check_fit_record(rec)
    assert inside(rec.fit, "train")
    for r in (rec.tune, rec.calibration):
        if r is not None:
            assert inside(r, "val_a")


def test_every_fitted_model_has_its_records() -> None:
    names = set(stored_records())
    if not names:
        pytest.skip("work/baselines/models is absent (run the NA-09 fit stage)")
    assert names == {f"{m}_{t}.json" for m, ts in FITTED.items() for t in ts}
