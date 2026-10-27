"""NA-09 guards (PRD NA-09; CLAUDE.md A3–A6, B8, B9): inputs checked with the availability registry, the
vendor exception limited to the pre-registered signals, metrics on val-A only, no test-period Laya request,
the LLM's selection rule, prompt and answer schema, and the Laya prediction mapping."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from newsaction import io, pit
from newsaction.baselines import BaselineError, baselines_config, laya_zeroshot, llm_baseline, metrics
from newsaction.baselines.data import VENDOR_SIGNALS, check_inputs
from newsaction.baselines.run import write_frozen_chat_models
from newsaction.dm.parse import Q1_MIDPOINTS
from newsaction.paths import ROOT, Layout

# --- inputs --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("col", ["e5", "z_cc", "z_on", "z_vol", "y2", "ar_cc", "dup_count"])
@pytest.mark.parametrize("point", ["D0", "D2"])
def test_outcomes_are_never_inputs(col: str, point: str) -> None:
    with pytest.raises(pit.PITError):
        check_inputs([col], point, vendor=True)  # type: ignore[arg-type]


def test_vendor_fields_need_the_vendor_flag() -> None:
    for col in sorted(VENDOR_SIGNALS):
        with pytest.raises(pit.PITError):
            check_inputs([col], "D0")
        check_inputs([col], "D0", vendor=True)
    # other selection_only columns stay refused even with the flag
    for col in ("source_class", "keep", "f5", "filter_score_w0", "event_age_days"):
        with pytest.raises(pit.PITError):
            check_inputs([col], "D0", vendor=True)


def test_reaction_inputs_only_at_d2() -> None:
    for col in ("g_d2", "react_z_on", "react_z_vol"):
        with pytest.raises(pit.PITError):
            check_inputs([col], "D0")
        check_inputs([col], "D2")
    check_inputs(["z_vol_lag1", "z_m5", "ctx_sigma_cc_pct", "embedding", "tier", "sector"], "D0")


# --- metrics on val-A only -------------------------------------------------------------------------------


def test_metrics_refuse_any_split_but_val_a() -> None:
    cfg = baselines_config()
    pred = pd.DataFrame({"split": ["val_a", "val_b", "test"]})
    assert list(metrics.evaluation_rows(pred, cfg)["split"]) == ["val_a"]
    for split in ("val_b", "test", "train", "robustness"):
        with pytest.raises(BaselineError):
            metrics.evaluation_rows(pred, cfg, split)  # type: ignore[arg-type]


def test_val_b_rows_do_not_change_the_metrics() -> None:
    cfg = baselines_config()
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2025-07-14", "2025-09-26")
    rows = []
    for split, d0 in (("val_a", days), ("val_b", pd.bdate_range("2025-10-14", "2025-12-26"))):
        for d in d0:
            for i in range(8):
                rows.append({"split": split, "session": d.date(), "symbol_id": i, "company_id": i})
    p = pd.DataFrame(rows)
    p["event_id"] = [f"W0:{r.symbol_id}:{r.session}" for r in p.itertuples()]
    p["model"], p["call"], p["extra"] = "sentiment", "A", "{}"
    p["N_hat"], p["mag_hat"], p["y_hat"] = rng.normal(size=len(p)), rng.random(len(p)), np.nan
    p["tier"], p["embargo"] = "mid", False
    tg = p[["session", "symbol_id", "split"]].copy()
    tg["e5"], tg["z_cc"], tg["z_on"], tg["z_id"], tg["y2"] = rng.normal(size=(5, len(p)))
    tg["abs_z_cc"] = tg["z_cc"].abs()
    a = pd.DataFrame(metrics.model_metrics(p, tg, cfg, 1.0))
    tg2 = tg.copy()
    tg2.loc[tg2["split"] == "val_b", ["e5", "z_cc", "z_on", "z_id", "abs_z_cc"]] = (
        99.0  # garbage val-B targets
    )
    b = pd.DataFrame(metrics.model_metrics(p, tg2, cfg, 1.0))
    pd.testing.assert_frame_equal(a, b)
    assert int(a["n_events"].max()) == int((p["split"] == "val_a").sum())


def test_metrics_file_has_val_a_rows_only() -> None:
    path = ROOT / "artifacts" / "NA-09" / "baseline_val_metrics.csv"
    if not path.is_file():
        pytest.skip("artifacts/NA-09/baseline_val_metrics.csv is absent (run the metrics stage)")
    t = pd.read_csv(path)
    assert "llm" not in set(t["model"])  # its 2,000 events are val-B: no metric
    for model, g in t.groupby("model"):
        pred = io.read_parquet(f"baselines/{model}.parquet", columns=["split", "event_id"])
        assert int(g["n_events"].max()) <= int((pred["split"] == "val_a").sum())


# --- Laya --------------------------------------------------------------------------------------------------


def test_laya_refuses_the_test_split() -> None:
    cfg = baselines_config()
    with pytest.raises(BaselineError):
        laya_zeroshot.specs_for(cfg, "test", "A")
    assert all(split != "test" for split, _ in cfg.laya_zeroshot.order)


def test_laya_prediction_file() -> None:
    if not (ROOT / "work" / "baselines" / "laya_zeroshot.parquet").is_file():
        pytest.skip("work/baselines/laya_zeroshot.parquet is absent (run the laya_predictions stage)")
    p = io.read_parquet("baselines/laya_zeroshot.parquet")
    assert "test" not in set(p["split"])
    assert set(p.loc[p["call"] == "B", "split"]) <= {"train", "val_a", "val_b"}
    for r in p.sample(200, random_state=0).itertuples():
        q = json.loads(r.extra)["q1_probs"]
        assert r.N_hat == pytest.approx(sum(a * b for a, b in zip(q, Q1_MIDPOINTS, strict=True)))
        assert r.P_up == pytest.approx(sum(q[5:])) and r.P_down == pytest.approx(sum(q[:4]))
        assert r.mag_hat == pytest.approx(sum(a * abs(b) for a, b in zip(q, Q1_MIDPOINTS, strict=True)))


# --- the LLM ---------------------------------------------------------------------------------------------


def test_q1_answer_keys_and_schema() -> None:
    _, levels, keys = llm_baseline.q1_levels()
    assert keys == [
        "very_large_fall", "large_fall", "moderate_fall", "small_fall", "no_meaningful_move", "small_rise",
        "moderate_rise", "large_rise", "very_large_rise",
    ]  # fmt: skip
    s = llm_baseline.schema()
    assert s["required"] == keys and s["additionalProperties"] is False
    assert [s["properties"][k]["description"] for k in keys] == levels


def test_prompt_carries_the_state_verbatim() -> None:
    state = json.dumps({"news": [{"headline": "The company beats"}]}, sort_keys=True)
    msgs = llm_baseline.messages(state)
    assert [m["role"] for m in msgs] == ["system", "user"]
    instructions, _, keys = llm_baseline.q1_levels()
    assert state in msgs[1]["content"] and instructions in msgs[1]["content"]
    assert all(k in msgs[1]["content"] for k in keys)


def catalog_entry(mid: str, prompt: float, completion: float, **kw: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": mid,
        "name": mid,
        "created": 1,
        "context_length": 32000,
        "knowledge_cutoff": "2024-01-31",
        "reasoning": None,
        "pricing": {"prompt": str(prompt * 1e-6), "completion": str(completion * 1e-6)},
        "supported_parameters": ["response_format", "structured_outputs", "seed", "temperature"],
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    }
    entry.update(kw)
    return entry


def test_selection_rule() -> None:
    cfg = baselines_config()
    models = [
        catalog_entry("mistralai/a", 0.03, 0.03),
        catalog_entry("meta-llama/b", 0.05, 0.08, created=5),
        catalog_entry("meta-llama/c", 0.05, 0.08, created=9),
        catalog_entry("mistralai/late-cutoff", 0.03, 0.03, knowledge_cutoff="2024-07-01"),
        catalog_entry("mistralai/no-cutoff", 0.03, 0.03, knowledge_cutoff=None),
        catalog_entry("mistralai/dear", 0.31, 0.03),
        catalog_entry("mistralai/free:free", 0.03, 0.03),
        catalog_entry("mistralai/x:batch", 0.03, 0.03),
        catalog_entry("someone/finetune", 0.03, 0.03),
        catalog_entry("meta-llama/llama-guard", 0.03, 0.03),
        catalog_entry("openai/thinker", 0.03, 0.03, reasoning={"mandatory": True}),
        catalog_entry("openai/no-seed", 0.03, 0.03, supported_parameters=["response_format", "temperature"]),
        catalog_entry("google/image-out", 0.03, 0.03, architecture={"input_modalities": ["text"],
                                                                     "output_modalities": ["image"]}),
    ]  # fmt: skip
    cands = llm_baseline.candidates(models, cfg, 4000.0)
    assert sorted(c["id"] for c in cands) == ["meta-llama/b", "meta-llama/c", "mistralai/a"]
    # projected cost per 1,000: input bytes / 4 tokens at the prompt price + 120 output tokens
    a = next(c for c in cands if c["id"] == "mistralai/a")
    assert a["projected_usd_per_1000"] == pytest.approx((0.03e-6 * 1000 + 0.03e-6 * 120) * 1000)
    order = llm_baseline.choose(cands, 0.052)
    assert order[:2] == ["meta-llama/c", "meta-llama/b"]  # equally close: the later release first
    assert llm_baseline.choose(cands, 0.03)[0] == "mistralai/a"


def test_frozen_chat_models_round_trip(tmp_layout: Layout) -> None:
    snap = {
        "chosen": "mistralai/a",
        "reference_usd_per_1000": 0.04,
        "raw_sha256": "f" * 64,
        "models": [
            {"id": "mistralai/a", "pricing": {"prompt": "3e-08", "completion": "3e-08"},
             "projected_usd_per_1000": 0.03, "knowledge_cutoff": "2024-01-31"},
        ],
    }  # fmt: skip
    before = yaml.safe_load((tmp_layout.configs / "frozen.yaml").read_text(encoding="utf-8"))
    write_frozen_chat_models(snap, tmp_layout)
    write_frozen_chat_models(snap, tmp_layout)  # replaces, never duplicates
    after = yaml.safe_load((tmp_layout.configs / "frozen.yaml").read_text(encoding="utf-8"))
    assert [r["id"] for r in after["chat_models"]] == ["mistralai/a"]
    assert {k: v for k, v in after.items() if k != "chat_models"} == {
        k: v for k, v in before.items() if k != "chat_models"
    }
    assert llm_baseline.chosen_model(tmp_layout) == "mistralai/a"


def test_llm_sample() -> None:
    if not (ROOT / "work" / "baselines" / "llm_sample.parquet").is_file():
        pytest.skip("work/baselines/llm_sample.parquet is absent (run the llm_sample stage)")
    cfg = baselines_config()
    s = io.read_parquet(llm_baseline.SAMPLE)
    assert len(s) == cfg.llm.sample and s["event_id"].is_unique
    assert set(s["split"]) == {"val_b"} and bool(s["third_party_ok_all"].all()) and bool(s["masked"].all())
    ev = io.read_parquet("events/events_d0.parquet", columns=["event_id", "embargo"])
    assert not bool(s.merge(ev, on="event_id")["embargo"].any())
    assert s["session"].min() > date(2025, 10, 1)
