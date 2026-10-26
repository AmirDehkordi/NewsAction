"""Import of the Kaggle runs and the model cards (PRD NA-08 S7, S8, AC1, AC4–AC6).

Unit tests cover the derived columns, the ensemble and the verification rules. ``tiny`` runs the whole
chain end to end on a tiny model: synthetic NA-04-style states → the export → the committed notebook (every
code cell, both INIT paths, on CPU) → ``import_preds`` → ``cards``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from conftest import make_layout
from newsaction import io
from newsaction.paths import Layout
from newsaction.states.questions import canonical_json
from newsaction.train import (
    LABELS,
    NOTEBOOK,
    SOURCES,
    TrainingConfig,
    load_training_config,
    training_questions,
)
from newsaction.train.import_preds import (
    RunImportError,
    check_preds,
    derive,
    ensemble,
    softmax,
    verify_record,
    verify_run,
)
from newsaction.train.labels import cont_labels, mag_levels, react_levels

CFG = load_training_config()


def test_derive_uses_the_prereg_midpoints() -> None:
    p = np.zeros((2, 9))
    p[0, 8] = 1.0  # very large rise
    p[1, [0, 4]] = 0.5
    d = derive("react", list(p), CFG)
    assert d["n_hat"].tolist() == [3.5, -1.75] and d["e_abs_n"].tolist() == [3.5, 1.75]
    assert d["mag_mean"].isna().all() and d["c_cont"].isna().all()
    m = derive("mag", [np.array([0.0, 0.0, 0.5, 0.5, 0.0])], CFG)
    assert m["mag_mean"].iloc[0] == pytest.approx(2.0) and m["p_mag_ge1"].iloc[0] == pytest.approx(1.0)
    c = derive("cont", [np.array([0.2, 0.3, 0.5])], CFG)
    assert c["c_cont"].iloc[0] == pytest.approx(0.3) and c["j_cont"].iloc[0] == pytest.approx(0.3)
    assert c["w_cont"].iloc[0] == pytest.approx(0.2) and c["confidence"].iloc[0] == pytest.approx(0.5)


def test_ensemble_is_the_mean_of_calibrated_probabilities() -> None:
    base = pd.DataFrame(
        {
            "split": "val_a",
            "event_id": ["e1", "e2"],
            "call": "A",
            "window": "W0",
            "question_id": "cont",
            "k": 3,
        }
    )
    a = base.assign(probabilities=[[0.2, 0.3, 0.5], [0.6, 0.2, 0.2]])
    b = base.assign(probabilities=[[0.4, 0.3, 0.3], [0.2, 0.2, 0.6]])
    out = ensemble([a, b.iloc[::-1].reset_index(drop=True)])
    got = {e: np.round(p, 6).tolist() for e, p in zip(out["event_id"], out["probabilities"], strict=True)}
    assert got == {"e1": [0.3, 0.3, 0.4], "e2": [0.4, 0.2, 0.4]}
    with pytest.raises(RunImportError):
        ensemble([a, b.iloc[:1]])


def _preds() -> tuple[pd.DataFrame, pd.DataFrame]:
    z = [np.array([0.1, 0.5, -0.2]), np.array([1.0, 0.0, 0.0])]
    df = pd.DataFrame(
        {
            "example_id": ["x", "y"],
            "question_id": "cont",
            "k": 3,
            "logits": z,
            "probs": [softmax(v, 2.0) for v in z],
        }
    )
    return df, pd.DataFrame({"example_id": ["x", "y"], "question_id": "cont"})


def test_check_preds_accepts_a_consistent_file() -> None:
    df, exp = _preds()
    check_preds(df, exp, {"cont": 2.0}, {"cont": 3}, "t")


@pytest.mark.parametrize("breakage", ["missing", "extra", "sum", "temperature", "k", "question"])
def test_check_preds_refuses_broken_files(breakage: str) -> None:
    df, exp = _preds()
    temps = {"cont": 2.0}
    if breakage == "missing":
        df = df.iloc[:1]
    elif breakage == "extra":
        exp = exp.iloc[:1]
    elif breakage == "sum":
        df.at[0, "probs"] = df.at[0, "probs"] * 0.9
    elif breakage == "temperature":
        temps = {"cont": 1.0}
    elif breakage == "k":
        df["k"] = 4
    else:
        exp["question_id"] = "react"
    with pytest.raises(RunImportError):
        check_preds(df, exp, temps, {"cont": 3, "react": 9}, "t")


# --- end to end on a tiny model ----------------------------------------------------------------------

WORDS = [
    "the",
    "company",
    "stock",
    "news",
    "headline",
    "snippet",
    "sector",
    "energy",
    "market",
    "small",
    "large",
    "rise",
    "fall",
    "normal",
    "busy",
    "one",
    "two",
    "quarter",
    "results",
    "raised",
    "guidance",
    "earnings",
    "price",
    "target",
    "analyst",
    "upgrade",
    "downgrade",
    "move",
    "continues",
    "reverses",
]
DAYS = {
    "train": [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5), date(2025, 3, 6)],
    "val_a": [date(2025, 7, 2), date(2025, 7, 9), date(2025, 7, 10), date(2025, 7, 11)],  # 07-02: embargo
    "val_b": [date(2025, 10, 15), date(2025, 10, 16)],
    "test": [date(2026, 2, 3), date(2026, 2, 4)],
}
N_COMPANIES = 12


def _tokenizer(path: Path) -> Any:
    from tokenizers import Tokenizer, models, pre_tokenizers
    from transformers import PreTrainedTokenizerFast

    vocab = {t: i for i, t in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *WORDS])}
    tk = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tk.pre_tokenizer = pre_tokenizers.Whitespace()
    tok = PreTrainedTokenizerFast(
        tokenizer_object=tk,
        unk_token="[UNK]",
        pad_token="[PAD]",
        cls_token="[CLS]",
        sep_token="[SEP]",
        mask_token="[MASK]",
    )
    tok.save_pretrained(str(path))
    return tok


def _states(tok: Any) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(0)
    out = {}
    for source in SOURCES:
        call, window = source.split("_")
        rows = []
        for split, days in DAYS.items():
            if call == "B" and split == "test":
                continue
            for day in days:
                for c in range(N_COMPANIES if day != date(2025, 7, 2) else 4):
                    words = " ".join(rng.choice(WORDS, size=int(rng.integers(5, 20))))
                    s: dict[str, Any] = {
                        "attention": {"articles": "busy"},
                        "company": {"sector": "energy"},
                        "market": {"market": "small rise"},
                        "news": [{"headline": words, "snippet": "the company"}],
                    }
                    if call == "B":
                        s["reaction_so_far"] = {"move": "large fall"}
                    sj = canonical_json(s)
                    rows.append(
                        {
                            "event_id": f"{window}:{c}:{day}",
                            "company_id": c,
                            "session": day,
                            "split": split,
                            "window": window,
                            "call": call,
                            "encoding": "E3",
                            "masked": True,
                            "state_json": sj,
                            "n_tokens_state": len(tok(sj, add_special_tokens=False)["input_ids"]),
                            "third_party_ok_all": True,
                        }
                    )
        out[source] = pd.DataFrame(rows)
    return out


def _labels(states: dict[str, pd.DataFrame]) -> pd.DataFrame:
    from newsaction.train.labels import horizon_end

    keys = pd.concat([s[["company_id", "session", "split"]] for s in states.values()]).drop_duplicates()
    keys = keys[keys["split"] != "test"].reset_index(drop=True)
    rng = np.random.default_rng(1)
    n = len(keys)
    lab = keys.assign(
        symbol_id=keys["company_id"],
        embargo=keys["session"] == date(2025, 7, 2),
        in_d0=True,
        in_d2=True,
        e5=rng.normal(size=n) * 1.5,
        z_cc=rng.normal(size=n),
        y2=rng.normal(size=n),
    )
    lab["g_d2"] = lab["z_cc"]
    lab["react_label"] = react_levels(lab["e5"], CFG.labels.edges)
    lab["mag_label"] = mag_levels(lab["z_cc"], CFG.labels.edges)
    lab["cont_x"], lab["cont_label"] = cont_labels(
        lab["g_d2"], lab["y2"], min_abs_g=0.5, band=0.5, order=["reverse", "stall", "continue"]
    )
    lab["react_horizon_end"] = horizon_end(lab["session"], 4)
    lab["cont_horizon_end"] = horizon_end(lab["session"], 5)
    return lab


def _model_dirs(root: Path, tok: Any) -> tuple[Path, Path]:
    import torch
    from laya.common import DecisionModel
    from laya.train import save_checkpoint
    from transformers import ModernBertConfig, ModernBertModel

    ecfg = ModernBertConfig(
        vocab_size=len(tok),
        hidden_size=64,
        intermediate_size=96,
        num_hidden_layers=2,
        num_attention_heads=2,
        max_position_embeddings=512,
        pad_token_id=0,
        bos_token_id=2,
        eos_token_id=3,
        cls_token_id=2,
        sep_token_id=3,
        global_attn_every_n_layers=1,
        local_attention=32,
    )
    torch.manual_seed(0)
    anchor = root / "anchor"
    ModernBertModel(ecfg).save_pretrained(str(anchor))
    tok.save_pretrained(str(anchor))
    torch.manual_seed(1)
    laya_root = root / "laya"
    dm = DecisionModel(ModernBertModel(ecfg), head_layers=2, n_act=2)
    save_checkpoint(
        dm,
        tok,
        {"encoder": "tiny", "head_layers": 2, "act_costs": {"escalate": 0.5}},
        str(laya_root / "typed-decisions"),
    )
    return laya_root, anchor


def _cfg(head_max_len: int, laya_sha: str, anchor_sha: str) -> TrainingConfig:
    m = CFG.model.model_copy(
        update={
            "max_len": 256,
            "head_max_len": head_max_len,
            "micro_batch": 4,
            "grad_accum": 2,
            "eval_batch": 8,
            "laya": CFG.model.laya.model_copy(update={"weights_sha256": laya_sha}),
            "anchor": CFG.model.anchor.model_copy(update={"weights_sha256": anchor_sha}),
        }
    )
    return CFG.model_copy(update={"model": m})


@pytest.fixture(scope="module")
def tiny(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    pytest.importorskip("torch")
    pytest.importorskip("laya")
    pytest.importorskip("tokenizers")
    from newsaction.train import cards, import_preds, kaggle_export, nbbuild

    root = tmp_path_factory.mktemp("na08")
    lay = make_layout(root / "repo")
    tok = _tokenizer(root / "tok")
    states = _states(tok)
    for source, df in states.items():
        io.write_parquet(df, CFG.states[source], producer="test", description="synthetic states", layout=lay)
    io.write_parquet(_labels(states), LABELS, producer="test", description="synthetic labels", layout=lay)
    laya_root, anchor = _model_dirs(root, tok)
    heads = kaggle_export.head_lengths(tok, training_questions(CFG), 10_000)
    cfg = _cfg(
        max(heads.values()),
        io.sha256_file(laya_root / "typed-decisions" / "model.safetensors"),
        io.sha256_file(anchor / "model.safetensors"),
    )
    info = kaggle_export.run(lay, tok=tok, n_tokens=kaggle_export.hf_lengths(tok), cfg=cfg)
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for name in ("laya-s13", "anchor-s13", "shuffle-s13"):
        params = kaggle_export.run_parameters(cfg.kaggle.run(name), cfg)
        params.update(
            EPOCHS=1 if name == "shuffle-s13" else 2,
            TIME_BUDGET_HOURS=1.0,
            LOCAL={
                "out_dir": str(lay.work / "kaggle" / "predictions" / name),
                "dataset_dir": str(lay.work / "kaggle" / "dataset"),
                "model_dirs": {"laya": str(laya_root), "modernbert": str(anchor)},
                "device": "cpu",
            },
        )
        nbbuild.run_locally(nb, params, root / f"run-{name}")
    summary = import_preds.run(lay, cfg)
    card_summary = cards.run(lay, cfg)
    return {
        "lay": lay,
        "cfg": cfg,
        "info": info,
        "summary": summary,
        "cards": card_summary,
        "states": states,
        "nb": nb,
        "root": root,
        "model_dirs": {"laya": str(laya_root), "modernbert": str(anchor)},
    }


def test_tiny_runs_are_imported_and_ensembled(tiny: dict[str, Any]) -> None:
    lay: Layout = tiny["lay"]
    assert set(tiny["summary"]["runs"]) == {"laya-s13", "anchor-s13", "shuffle-s13"}
    assert tiny["summary"]["models"] == {
        "laya_fin": {"runs": ["laya-s13"]},
        "anchor": {"runs": ["anchor-s13"]},
    }
    for model in ("laya_fin", "anchor"):
        for split in ("val_a", "val_b", "test_callA"):
            df = io.read_parquet(f"kaggle/predictions/{model}_{split}.parquet", layout=lay)
            assert len(df) and (df["model"] == model).all()
            assert np.allclose([np.sum(p) for p in df["probabilities"]], 1.0, atol=1e-5)
            ids = set().union(*(set(s["event_id"]) for s in tiny["states"].values()))
            assert set(df["event_id"]) <= ids
            r = df[df["question"] == "react"]
            mids = np.array(CFG.derived.react_midpoints)
            assert np.allclose(r["n_hat"], [np.asarray(p) @ mids for p in r["probabilities"]])
        test = io.read_parquet(f"kaggle/predictions/{model}_test_callA.parquet", layout=lay)
        assert set(test["call"]) == {"A"} and set(test["question"]) == {"react", "mag"}


def test_tiny_every_eval_state_gets_its_questions(tiny: dict[str, Any]) -> None:
    lay: Layout = tiny["lay"]
    va = io.read_parquet("kaggle/predictions/laya_fin_val_a.parquet", layout=lay)
    for source, df in tiny["states"].items():
        call, window = source.split("_")
        want = set(df.loc[df["split"] == "val_a", "event_id"])
        for q in CFG.questions.by_source[source]:
            got = set(
                va.loc[(va["call"] == call) & (va["window"] == window) & (va["question"] == q), "event_id"]
            )
            assert got == want, (source, q)


def test_tiny_cards_and_controls(tiny: dict[str, Any]) -> None:
    art = tiny["lay"].artifacts / "NA-08"
    for model in ("laya_fin", "anchor"):
        text = (art / f"model_card_{model}.md").read_text()
        assert "## Val-A results (embargo excluded)" in text and "ECE before" in text
        assert "hub_push: false" in text
        tables = text.split("## Val-A results")[1].split("## Controls")[0]
        assert "val-B" not in tables and "val_b" not in tables and "test" not in tables.lower()
    ctl = json.loads((art / "controls.json").read_text())
    sh = ctl["shuffled_label"]
    assert sh["run"] == "shuffle-s13" and isinstance(sh["pass"], bool) and sh["ic_e5"]["days"] == 3
    assert "deferral" in ctl["reproducibility"]["status"]
    trials = [json.loads(x) for x in (tiny["lay"].ledgers / "trials.jsonl").read_text().splitlines()]
    assert {t["name"] for t in trials} >= {"laya_fin/ensemble", "laya_fin/laya-s13", "anchor/anchor-s13"}
    assert all(t["split"] == "val_a" and t["chunk"] == "NA-08" for t in trials)


def test_tiny_rerun_logs_no_new_trial(tiny: dict[str, Any]) -> None:
    from newsaction.train import cards

    n = len((tiny["lay"].ledgers / "trials.jsonl").read_text().splitlines())
    cards.run(tiny["lay"], tiny["cfg"])
    assert len((tiny["lay"].ledgers / "trials.jsonl").read_text().splitlines()) == n


def test_tiny_run_records_say_what_ran(tiny: dict[str, Any]) -> None:
    run_dir = tiny["lay"].work / "kaggle" / "predictions" / "anchor-s13"
    rec = json.loads((run_dir / "na08_anchor-s13_run_record.json").read_text())
    assert (
        rec["hub_push"] is False and rec["model"]["head_fresh"] is True and rec["model"]["weights_verified"]
    )
    assert rec["labels_read"] == {"train": True, "val_a": True, "val_b": False, "test": False}
    assert rec["temperature_fit"]["split"] == "val_a" and rec["early_stopping"]["split"] == "val_a"
    assert rec["dataset"]["label_columns"] == {"val_b": False, "test": False}
    ck = json.loads((run_dir / "ckpt" / "rl_agent_config.json").read_text())
    assert ck["temperature"] == [1.0, 1.0, 1.0] and set(ck["na08_temperatures"]) == {"react", "mag", "cont"}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("hub_push", True),
        ("labels_read", {"train": True, "val_a": True, "val_b": True, "test": False}),
        ("program_sha256", "0" * 64),
        ("max_len", 512),
        ("seed", 17),
    ],
)
def test_verify_record_refuses_a_wrong_record(tiny: dict[str, Any], key: str, value: Any) -> None:
    run_dir = tiny["lay"].work / "kaggle" / "predictions" / "laya-s13"
    rec = json.loads((run_dir / "na08_laya-s13_run_record.json").read_text())
    rec[key] = value
    with pytest.raises(RunImportError):
        verify_record(rec, tiny["cfg"].kaggle.run("laya-s13"), tiny["cfg"], tiny["lay"])


def test_verify_record_refuses_another_dataset(tiny: dict[str, Any]) -> None:
    run_dir = tiny["lay"].work / "kaggle" / "predictions" / "laya-s13"
    rec = json.loads((run_dir / "na08_laya-s13_run_record.json").read_text())
    rec["dataset"]["files"]["train.parquet"] = "f" * 64
    with pytest.raises(RunImportError, match="AC1"):
        verify_record(rec, tiny["cfg"].kaggle.run("laya-s13"), tiny["cfg"], tiny["lay"])


def test_verify_run_refuses_a_tampered_prediction_file(tiny: dict[str, Any], tmp_path: Path) -> None:
    import shutil

    src = tiny["lay"].work / "kaggle" / "predictions" / "laya-s13"
    dst = tmp_path / "laya-s13"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("ckpt"))
    p = dst / "na08_laya-s13_pred_val_b.arrow"
    p.write_bytes(p.read_bytes()[:-8] + b"\0" * 8)
    with pytest.raises(RunImportError, match="sha256"):
        verify_run(dst, tiny["cfg"].kaggle.run("laya-s13"), "laya-s13", tiny["cfg"], tiny["lay"])


def test_tiny_pilot_is_verified_and_planned(tiny: dict[str, Any]) -> None:
    """The pilot kernel (three launches) through every notebook cell, then plan.run → throughput.json."""
    from newsaction.train import kaggle_export, nbbuild, plan

    lay, cfg = tiny["lay"], tiny["cfg"]
    params = kaggle_export.run_parameters(cfg.kaggle.run("pilot"), cfg)
    params.update(
        TIME_BUDGET_HOURS=1.0,
        LOCAL={
            "out_dir": str(lay.work / "kaggle" / "predictions" / "pilot"),
            "dataset_dir": str(lay.work / "kaggle" / "dataset"),
            "model_dirs": tiny["model_dirs"],
            "device": "cpu",
        },
    )
    nbbuild.run_locally(tiny["nb"], params, tiny["root"] / "run-pilot")
    out = plan.run(lay, cfg)
    assert {k: v["status"] for k, v in out["pilot"].items()} == {
        "laya": "ok",
        "laya-nockpt": "ok",
        "modernbert": "ok",
    }
    assert (
        out["pilot"]["laya"]["rehearsal_rows"]["val_a"] > 0
        and out["pilot"]["laya-nockpt"]["rehearsal_rows"] == {}
    )
    assert out["rows"]["train"] == tiny["info"]["counts"]["train"]["examples"]
    names = [o["option"] for o in out["options"]]
    assert names == ["full", "anchor seeds -> 1", "MAX_LEN 768", "anchor seeds -> 1, epochs 2"]
    assert out["options"][2]["available"] is False
    full = out["options"][0]
    assert [r["run"] for r in full["runs"]][:2] == ["shuffle-s13", "laya-s13"] and full["gpu_hours"] > 0
    assert (lay.artifacts / "NA-08" / "throughput.json").is_file()


def test_tiny_control_predicts_val_a_only(tiny: dict[str, Any]) -> None:
    run = io.read_parquet("kaggle/predictions/runs/shuffle-s13.parquet", layout=tiny["lay"])
    assert set(run["split"]) == {"val_a"}
    run_dir = tiny["lay"].work / "kaggle" / "predictions" / "shuffle-s13"
    rec = json.loads((run_dir / "na08_shuffle-s13_run_record.json").read_text())
    assert rec["shuffle_labels"] is True and rec["rows_used"]["val_b"] == rec["rows_used"]["test"] == 0
    assert "shuffle-s13" not in tiny["summary"]["models"]["laya_fin"]["runs"]  # a control is no ensemble seed
