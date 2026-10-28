"""NA-11 S7's inference notebook end to end on CPU (tiny models): the NA-08 checkpoint reloads into the
same model, re-predicts NA-08's val-A rows exactly, reads only the given files, trains nothing and pushes
nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from newsaction import io
from newsaction.train import PREDICTIONS_DIR
from newsaction.train import infer_nbbuild as nbi
from newsaction.train.import_preds import read_preds
from newsaction.train.kaggle_export import EVAL_COLUMNS
from test_train_import import tiny  # noqa: F401  (NA-08's tiny training runs: checkpoints to reload)


def _dataset(lay: Any, out: Path) -> list[str]:
    """A tiny NA-11 dataset: val-B rows of NA-08's tiny export (no label) and the check file from val-A."""
    out.mkdir(parents=True, exist_ok=True)
    vb = pd.read_parquet(lay.work / "kaggle" / "dataset" / "val_b.parquet", columns=list(EVAL_COLUMNS))
    va = pd.read_parquet(lay.work / "kaggle" / "dataset" / "val_a.parquet", columns=list(EVAL_COLUMNS))
    va = va.loc[(va["variant"] == "full") & (va["question_id"] == "react")].head(12)
    files = {"test_callB": vb.head(16), "check_val_a": va}
    manifest: dict[str, Any] = {"files": {}}
    for name, df in files.items():
        df.reset_index(drop=True).to_parquet(out / f"{name}.parquet", index=False)
        manifest["files"][f"{name}.parquet"] = {
            "sha256": io.sha256_file(out / f"{name}.parquet"),
            "rows": len(df),
        }
    (out / "na11_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return list(files)


@pytest.mark.slow
def test_inference_reloads_the_checkpoint_and_reproduces_val_a(tiny: dict[str, Any], tmp_path: Path) -> None:  # noqa: F811
    lay, cfg = tiny["lay"], tiny["cfg"]
    run = "laya-s13"
    run_dir = lay.work / PREDICTIONS_DIR / run
    cal = json.loads((run_dir / f"na08_{run}_calibration.json").read_text(encoding="utf-8"))
    temps = {q: float(h["temperature"]) for q, h in cal["heads"].items()}
    files = _dataset(lay, tmp_path / "data")
    out = tmp_path / "out"
    params = {
        "RUN_NAME": run,
        "CKPT_KERNEL": f"newsaction-na08-{run}",
        "TEMPERATURES": temps,
        "FILES": files,
        "MAX_LEN": cfg.model.max_len,
        "HEAD_MAX_LEN": cfg.model.head_max_len,
        "HPARAMS": {"eval_batch": 4, "amp": "fp16"},
        "PIP": [],
        "LOCAL": {
            "out_dir": str(out),
            "dataset_dir": str(tmp_path / "data"),
            "ckpt_dir": str(run_dir / "ckpt"),
            "device": "cpu",
        },
    }
    nbi.run_locally(nbi.build_notebook(), params, tmp_path / "work")
    rec = json.loads((out / f"na11_{run}_infer_record.json").read_text(encoding="utf-8"))
    assert rec["trained"] is False and rec["hub_push"] is False and rec["labels_read"] is False
    assert rec["checkpoint"]["temperatures"] == temps and rec["rows"] == {"test_callB": 16, "check_val_a": 12}
    check = read_preds(out / f"na11_{run}_check_val_a.arrow")
    ref = pd.read_parquet(
        lay.work / PREDICTIONS_DIR / "runs" / f"{run}.parquet", columns=["example_id", "probabilities"]
    )
    m = check.merge(ref, on="example_id", how="inner")
    assert len(m) == 12
    diff = max(
        float(np.max(np.abs(np.asarray(a) - np.asarray(b))))
        for a, b in zip(m["probs"], m["probabilities"], strict=True)
    )
    assert diff < 1e-5  # CPU, fp32: the reloaded checkpoint is the model behind NA-08's predictions
    outputs = json.loads((out / "na11_outputs.json").read_text(encoding="utf-8"))
    assert {f"na11_{run}_{f}.arrow" for f in files} <= set(outputs)


@pytest.mark.slow
def test_a_wrong_temperature_is_refused(tiny: dict[str, Any], tmp_path: Path) -> None:  # noqa: F811
    lay, cfg = tiny["lay"], tiny["cfg"]
    run = "anchor-s13"
    run_dir = lay.work / PREDICTIONS_DIR / run
    files = _dataset(lay, tmp_path / "data")
    params = {
        "RUN_NAME": run,
        "CKPT_KERNEL": f"newsaction-na08-{run}",
        "TEMPERATURES": {"react": 9.0},
        "FILES": files,
        "MAX_LEN": cfg.model.max_len,
        "HEAD_MAX_LEN": cfg.model.head_max_len,
        "HPARAMS": {"eval_batch": 4, "amp": "fp16"},
        "PIP": [],
        "LOCAL": {
            "out_dir": str(tmp_path / "out"),
            "dataset_dir": str(tmp_path / "data"),
            "ckpt_dir": str(run_dir / "ckpt"),
            "device": "cpu",
        },
    }
    with pytest.raises(RuntimeError, match="inference failed"):
        nbi.run_locally(nbi.build_notebook(), params, tmp_path / "work")


def test_the_committed_notebook_is_the_built_one() -> None:
    assert nbi.INFER_NOTEBOOK.read_text(encoding="utf-8") == nbi.notebook_text()
    nb = nbi.build_notebook()
    src = "\n".join("".join(c["source"]) for c in nb["cells"])
    for banned in ("push_to_hub", "upload_folder", "create_repo", "HfApi"):
        assert banned not in src
