"""The Kaggle notebook (PRD NA-08 S3, AC2, AC6): no Hub push, the INIT switch, val-A fitting, helpers.

The notebook is an artifact built by ``newsaction.train.nbbuild``; its ``%%writefile`` cell is
``notebook/train_ddp.py`` verbatim. The program's pure helpers are imported from that file.
"""

from __future__ import annotations

import importlib.util
import json
import re
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest

from newsaction.train import NOTEBOOK, load_training_config
from newsaction.train.kaggle_export import run_parameters
from newsaction.train.nbbuild import PROGRAM, notebook_text, parameters_of, program_of

NB_TEXT = NOTEBOOK.read_text(encoding="utf-8")
NB = json.loads(NB_TEXT)
CODE = "\n".join("".join(c["source"]) for c in NB["cells"] if c["cell_type"] == "code")
SRC = PROGRAM.read_text(encoding="utf-8")
HUB_CALLS = (
    r"push_to_hub",
    r"upload_folder",
    r"upload_file",
    r"create_repo",
    r"HfApi",
    r"HF_TOKEN",
    r"kaggle_secrets",
    r"UserSecretsClient",
    r"\.push\(",
    r"Repository\(",
    r"create_commit",
    r"hf_hub_upload",
    r"\bupload\(",
    r"kaggle (datasets|kernels) (create|push|version)",
)


@pytest.fixture(scope="module")
def prog() -> ModuleType:
    pytest.importorskip("torch")
    pytest.importorskip("laya")
    spec = importlib.util.spec_from_file_location("na08_train_ddp", PROGRAM)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_notebook_is_the_build() -> None:
    assert notebook_text() == NB_TEXT  # rebuild with: python -m newsaction.train.build --stage notebook
    assert program_of(NB) == SRC


def test_no_hub_push_or_upload_anywhere() -> None:
    for pat in HUB_CALLS:
        assert not re.search(pat, CODE), pat
        assert not re.search(pat, SRC), pat
    assert '"hub_push": False' in SRC
    assert 'rec["hub_push"] is not False' in CODE  # the summary cell re-checks every run record


def test_init_switch_and_identical_heads() -> None:
    assert re.search(r'if init == "laya":', SRC)
    assert "model.load_state_dict(load_file(str(weights)), strict=True)" in SRC  # Laya: its own weights
    assert "pretrained=True" in SRC and "encoder_dir=None" in SRC  # anchor: Hub encoder, fresh head
    assert '"head_fresh": init != "laya"' in SRC
    assert (
        "torch.manual_seed(seed)" in SRC.split("def build(")[1].split("def save_ckpt")[0]
    )  # seeded head init
    assert 'if digest != spec["weights_sha256"]' in SRC  # both inits are checked against the pin
    params = parameters_of(NB)
    assert params["LAYA"]["subfolder"] == "typed-decisions" and params["ANCHOR"]["subfolder"] is None
    assert params["HEAD"] == {"head_layers": 2, "act_costs": {"escalate": 0.5}}


def test_fitting_uses_val_a_only_and_never_reads_eval_labels() -> None:
    assert 'LABELLED = ("train", "val_a")' in SRC
    assert '(["label_index"] if split in LABELLED else [])' in SRC
    assert SRC.count("calibrate(") == 2  # the definition and one call
    assert re.search(r'calibrate\(\s*frames\["val_a"\]', SRC)
    assert 'val_loss(frames["val_a"], val_logits)' in SRC
    assert '"labels_read": {"train": True, "val_a": True, "val_b": False, "test": False}' in SRC
    assert "fit_mask" in SRC and "embargo" in SRC.split("def fit_mask")[1].split("def val_loss")[0]
    for name in ("val_b.parquet", "test_callA.parquet"):
        assert name in CODE  # the dataset cell asserts they have no label column


def test_notebook_parameters_are_the_pilot_and_every_kernel_differs_only_there() -> None:
    cfg = load_training_config()
    assert parameters_of(NB) == run_parameters(cfg.kaggle.runs[0], cfg)
    assert parameters_of(NB)["MAX_LEN"] == 1036 and parameters_of(NB)["HEAD_MAX_LEN"] == 143


def test_kernel_notebooks_carry_their_run(tmp_path: Any) -> None:
    from newsaction.paths import Layout
    from newsaction.train.kaggle_export import write_kernels

    lay = Layout(tmp_path)
    out = write_kernels(lay)
    cfg = load_training_config()
    for spec in cfg.kaggle.runs:
        nb = json.loads((tmp_path / "work" / "kaggle" / "kernels" / spec.name / NOTEBOOK.name).read_text())
        assert parameters_of(nb) == run_parameters(spec, cfg)
        assert program_of(nb) == SRC
        assert out[spec.name]["kernel"].endswith(f"/newsaction-na08-{spec.name}")


# --- the program's helpers ------------------------------------------------------------------------


def test_fit_temperature_recovers_a_planted_temperature(prog: ModuleType) -> None:
    rng = np.random.default_rng(0)
    z = rng.normal(size=(4000, 5)) * 2.0
    labels = np.array([rng.choice(5, p=prog.softmax(row, 1.7)) for row in z])
    t = prog.fit_temperature(list(z), labels)
    assert t == pytest.approx(1.7, rel=0.08)
    assert prog.nll(list(z), labels, t) <= prog.nll(list(z), labels, 1.0)


def test_ece_known_values(prog: ModuleType) -> None:
    conf = np.array([0.9, 0.9, 0.6, 0.6])
    correct = np.array([1, 0, 1, 1])
    # bins: 0.9 → acc 0.5 (gap 0.4, weight 0.5); 0.6 → acc 1 (gap 0.4, weight 0.5)
    assert prog.ece(conf, correct, 15) == pytest.approx(0.4)
    assert prog.ece(np.array([1.0, 0.0]), np.array([1, 0]), 15) == pytest.approx(0.0)


def test_bucket_batches_cover_every_row_once_and_shards_match(prog: ModuleType) -> None:
    lengths = np.random.default_rng(1).integers(100, 1000, size=1003)
    b = prog.bucket_batches(lengths, 8, np.random.default_rng([13, 0]))
    flat = np.concatenate(b)
    assert sorted(flat) == list(range(1003))
    assert all(len(x) <= 8 for x in b)
    s0, s1 = prog.shard(b, 0, 2), prog.shard(b, 1, 2)
    assert len(s0) == len(s1) == len(b) // 2
    again = prog.bucket_batches(lengths, 8, np.random.default_rng([13, 0]))
    assert all((x == y).all() for x, y in zip(b, again, strict=True))  # seeded


def test_permute_labels_keeps_marginals_and_unlabelled_rows(prog: ModuleType) -> None:
    df = pd.DataFrame(
        {
            "question_id": ["react"] * 500 + ["cont"] * 300,
            "label": [i % 9 for i in range(500)] + [i % 3 if i % 4 else -1 for i in range(300)],
        }
    )
    out = prog.permute_labels(df, 2026)
    for q in ("react", "cont"):
        a, b = df[df.question_id == q]["label"], out[out.question_id == q]["label"]
        assert sorted(a) == sorted(b) and (a != b).mean() > 0.5
    assert ((df["label"] < 0) == (out["label"] < 0)).all()


def test_lr_factor_warms_up_then_decays_to_the_floor(prog: ModuleType) -> None:
    assert prog.lr_factor(0, 1000, 30, 0.01) == pytest.approx(1 / 30)
    assert prog.lr_factor(29, 1000, 30, 0.01) == pytest.approx(1.0)
    assert prog.lr_factor(30, 1000, 30, 0.01) == pytest.approx(1.0)
    assert prog.lr_factor(1000, 1000, 30, 0.01) == pytest.approx(0.01)


def test_session_of_event_id(prog: ModuleType) -> None:
    assert prog.session_of("W0:1001:2025-04-10") == "2025-04-10"


def test_read_split_never_asks_eval_files_for_labels(prog: ModuleType, tmp_path: Any) -> None:
    cols = {
        "example_id": ["x"],
        "event_id": ["W0:1:2025-11-03"],
        "call": ["A"],
        "window": ["W0"],
        "variant": ["full"],
        "question_id": ["react"],
        "question_json": ["{}"],
        "state_json": ["{}"],
        "n_tokens_state": [3],
    }
    pd.DataFrame(cols).to_parquet(tmp_path / "val_b.parquet")
    cfg = {
        "DATASET_DIR": str(tmp_path),
        "QUESTIONS_BY_SOURCE": {"A_W0": ["react"]},
        "TRAIN_VARIANTS": ["full"],
    }
    df = prog.read_split(cfg, "val_b")
    assert (df["label"] == -1).all() and len(df) == 1
