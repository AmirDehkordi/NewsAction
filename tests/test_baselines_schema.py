"""The common prediction schema (PRD NA-09 S1, AC2, AC3): every output validates, its events match the
states, there is no duplicate (event_id, model, call), no D2 (call B) test prediction and no test prediction
of a baseline that needs a 2026 price or answer before the freeze."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

from newsaction import io
from newsaction.baselines import baselines_config
from newsaction.baselines.schema import MODELS, PREDICTION_COLUMNS, TEST_MODELS, SchemaError, frame, validate
from newsaction.paths import ROOT


def states() -> dict[str, pd.DataFrame]:
    a = pd.DataFrame(
        {
            "event_id": ["W0:1:2025-08-01", "W0:2:2025-08-01", "W0:1:2026-03-02"],
            "split": ["val_a", "val_a", "test"],
            "session": [date(2025, 8, 1), date(2025, 8, 1), date(2026, 3, 2)],
            "company_id": [1, 2, 1],
        }
    )
    b = pd.DataFrame(
        {
            "event_id": ["W2:1:2025-08-01"],
            "split": ["val_a"],
            "session": [date(2025, 8, 1)],
            "company_id": [1],
        }
    )
    return {"A": a, "B": b}


def good(**kw: Any) -> pd.DataFrame:
    rows = pd.DataFrame(
        {
            "event_id": ["W0:1:2025-08-01", "W0:2:2025-08-01", "W0:1:2026-03-02"],
            "model": ["sentiment"] * 3,
            "call": ["A"] * 3,
            "split": ["val_a", "val_a", "test"],
            "session": [date(2025, 8, 1), date(2025, 8, 1), date(2026, 3, 2)],
            "company_id": [1, 2, 1],
            "N_hat": [0.1, -0.2, 0.0],
            "P_up": [0.3, 0.2, 0.25],
            "P_down": [0.2, 0.4, 0.25],
            "mag_hat": [1.0, 0.5, 0.7],
            "extra": ['{"a": 1}', "{}", "{}"],
        }
    )
    for k, v in kw.items():
        rows[k] = v
    return frame(rows)


def test_a_good_frame_validates() -> None:
    f = good()
    assert tuple(f.columns) == PREDICTION_COLUMNS
    validate(f, states())


@pytest.mark.parametrize(
    "change",
    [
        {"model": ["sentiment", "sentiment", "nope"]},
        {"call": ["A", "C", "A"]},
        {"event_id": ["W0:1:2025-08-01", "W0:1:2025-08-01", "W0:1:2026-03-02"]},  # duplicate
        {"event_id": ["W0:1:2025-08-01", "W0:9:2025-08-01", "W0:1:2026-03-02"]},  # not a state
        {"company_id": [1, 3, 1]},  # wrong company for the event
        {"split": ["val_a", "val_b", "test"]},  # wrong split for the event
        {"P_up": [1.2, 0.2, 0.25]},
        {"P_down": [-0.1, 0.2, 0.25]},
        {"P_up": [0.7, 0.2, 0.25], "P_down": [0.4, 0.2, 0.25]},  # sum > 1
        {"mag_hat": [-1.0, 0.5, 0.7]},
        {"N_hat": [np.inf, 0.0, 0.0]},
        {"N_hat": [np.nan, 0.0, 0.0]},  # neither N_hat nor y_hat
        {"extra": ["[1]", "{}", "{}"]},
        {
            "model": ["sentiment", "sentiment", "price_only"]
        },  # a test row of a baseline that needs 2026 prices
        {"model": ["laya_zeroshot"] * 3},
        {"model": ["llm"] * 3},
    ],
)
def test_bad_frames_are_refused(change: dict[str, Any]) -> None:
    with pytest.raises((SchemaError, ValueError, json.JSONDecodeError)):
        validate(good(**change), states())


def test_missing_column_is_refused() -> None:
    with pytest.raises(SchemaError):
        validate(good().drop(columns=["P_up"]), states())


def test_no_call_b_test_row() -> None:
    st = states()
    st["B"] = pd.concat(
        [st["B"], pd.DataFrame({"event_id": ["W2:1:2026-03-02"], "split": ["test"],
                                "session": [date(2026, 3, 2)], "company_id": [1]})]
    )  # fmt: skip
    rows = frame(
        pd.DataFrame(
            {
                "event_id": ["W2:1:2026-03-02"],
                "model": ["price_only"],
                "call": ["B"],
                "split": ["test"],
                "session": [date(2026, 3, 2)],
                "company_id": [1],
                "y_hat": [0.1],
            }
        )
    )
    with pytest.raises(SchemaError, match="test period"):
        validate(rows, st)


# --- the real outputs -----------------------------------------------------------------------------------


def outputs() -> list[str]:
    d = ROOT / "work" / "baselines"
    return sorted(m for m in MODELS if (d / f"{m}.parquet").is_file())


@pytest.fixture(scope="module")
def real_states() -> dict[str, pd.DataFrame]:
    cfg = baselines_config()
    cols = ["event_id", "split", "session", "company_id"]
    return {
        "A": io.read_parquet(cfg.state_files.call_a, columns=cols),
        "B": io.read_parquet(cfg.state_files.call_b, columns=cols),
    }


@pytest.mark.parametrize("model", outputs() or ["(none)"])
def test_real_outputs_validate(model: str, real_states: dict[str, pd.DataFrame]) -> None:
    if model == "(none)":
        pytest.skip("no work/baselines predictions yet")
    pred = io.read_parquet(f"baselines/{model}.parquet")
    validate(pred, real_states)
    assert set(pred["model"]) == {model}
    assert not bool(((pred["split"] == "test") & (pred["call"] == "B")).any())
    if model not in TEST_MODELS:
        assert "test" not in set(pred["split"])


@pytest.mark.parametrize("model", ["sentiment", "embed_ridge", "tags_gbm"])
def test_news_baselines_cover_every_call_a_state(model: str, real_states: dict[str, pd.DataFrame]) -> None:
    if model not in outputs():
        pytest.skip(f"work/baselines/{model}.parquet is absent")
    pred = io.read_parquet(f"baselines/{model}.parquet")
    assert set(pred["event_id"]) == set(real_states["A"]["event_id"])


def test_price_only_covers_every_non_test_state(real_states: dict[str, pd.DataFrame]) -> None:
    if "price_only" not in outputs():
        pytest.skip("work/baselines/price_only.parquet is absent")
    pred = io.read_parquet("baselines/price_only.parquet")
    a = real_states["A"]
    assert set(pred.loc[pred["call"] == "A", "event_id"]) == set(a.loc[a["split"] != "test", "event_id"])
    assert set(pred.loc[pred["call"] == "B", "event_id"]) == set(real_states["B"]["event_id"])
    assert (
        pred.loc[pred["call"] == "B", "N_hat"].isna().all()
        and pred.loc[pred["call"] == "B", "y_hat"].notna().all()
    )


def test_a_true_duplicate_is_refused() -> None:
    f = good()
    with pytest.raises(SchemaError, match="duplicate"):
        validate(pd.concat([f, f.iloc[[0]]], ignore_index=True), states())
