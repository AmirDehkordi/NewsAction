"""NA-11 S7: inference only with a frozen NA-08 checkpoint (Kaggle GPU T4 ×2; PRD NA-11 S7; CLAUDE.md D16).

Runs as ``torchrun --nproc_per_node=2 infer_ddp.py <config.json>`` next to NA-08's ``train_ddp.py`` (written
unchanged by the notebook), whose helpers it imports: ``Dist``, ``Questions``, ``infer`` and ``write_preds``.

- **Inputs.** The NA-11 dataset (masked, third-party-OK states; one row per (state, question); no label
  column) and the training kernel's ``ckpt/`` (``model.safetensors`` in fp32, ``encoder/`` config,
  ``tokenizer/``, ``rl_agent_config.json`` with ``na08_temperatures``, the val-A temperatures of that run).
- **Checks.** The checkpoint's temperatures equal the ones the config pins (NA-08's verified run); no state is
  cut at ``MAX_LEN``; and the ``check`` file (500 val-A examples NA-08 already predicted) is re-predicted, so
  the importer can compare it with NA-08's stored predictions.
- **Outputs** (``OUT_DIR``): ``na11_<run>_<file>.arrow`` per dataset file (logits, calibrated and raw
  probabilities, as NA-08's ``write_preds``) and ``na11_<run>_infer_record.json``. Nothing is trained, and
  nothing is pushed anywhere.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import torch
import train_ddp as td

PREFIX = "na11_"
READ_COLUMNS = (*td.READ_COLUMNS, "split")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_from_ckpt(ckpt: Path) -> tuple[torch.nn.Module, Any, dict[str, float]]:
    """The fine-tuned model from its checkpoint: architecture from the saved encoder config, every weight
    from ``model.safetensors`` (strict), the tokenizer it trained with, and its val-A temperatures."""
    from laya.common import build_model
    from safetensors.torch import load_file
    from transformers import AutoTokenizer

    lcfg = json.loads((ckpt / "rl_agent_config.json").read_text(encoding="utf-8"))
    temps = {str(k): float(v) for k, v in lcfg["na08_temperatures"].items()}
    tok = AutoTokenizer.from_pretrained(str(ckpt / "tokenizer"))
    model = build_model(lcfg, encoder_dir=str(ckpt / "encoder"))
    model.load_state_dict(load_file(str(ckpt / "model.safetensors")), strict=True)
    return model.float(), tok, temps


def read_file(path: Path) -> pd.DataFrame:
    names = pq.read_schema(path).names
    if any("label" in c.lower() for c in names):
        raise ValueError(f"{path.name} has a label column")
    df = pq.read_table(path, columns=list(READ_COLUMNS)).to_pandas()
    df["label"] = -1
    return df


def run(cfg: dict[str, Any]) -> None:
    d = td.Dist(cfg.get("DEVICE", "auto"))
    t0 = time.time()
    ckpt = Path(cfg["CKPT_DIR"])
    model, tok, temps = build_from_ckpt(ckpt)
    model.to(d.device)
    want = {str(k): float(v) for k, v in cfg["TEMPERATURES"].items()}
    if set(temps) != set(want) or any(abs(temps[k] - want[k]) > 1e-9 for k in want):
        raise RuntimeError(f"checkpoint temperatures {temps} differ from NA-08's verified run {want}")
    out = Path(cfg["OUT_DIR"])
    data = Path(cfg["DATASET_DIR"])
    frames = {name: read_file(data / f"{name}.parquet") for name in cfg["FILES"]}
    qs = td.Questions(list(frames.values()), tok, cfg["HEAD_MAX_LEN"])
    cut = {name: td.truncation(df, qs, cfg["MAX_LEN"]) for name, df in frames.items()}
    if any(cut.values()):
        raise RuntimeError(f"MAX_LEN {cfg['MAX_LEN']} would cut {sum(map(len, cut.values()))} examples")
    td.log(
        d,
        f"{cfg['RUN_NAME']}: {ckpt} on {d.device} (world {d.world}); rows "
        f"{ {k: len(v) for k, v in frames.items()} }",
    )
    rows: dict[str, int] = {}
    seconds: dict[str, float] = {}
    for name, df in frames.items():
        s = time.time()
        logits = td.infer(model, df, qs, tok, cfg, d)
        seconds[name] = round(time.time() - s, 1)
        rows[name] = len(df)
        if d.main:
            td.write_preds(out / f"{PREFIX}{cfg['RUN_NAME']}_{name}.arrow", df, logits, temps)
        td.log(d, f"{name}: {len(df)} rows in {seconds[name]} s")
    d.barrier()
    if d.main:
        record = {
            "chunk": "NA-11",
            "run_name": cfg["RUN_NAME"],
            "mode": "inference",
            "checkpoint": {
                "dir": str(ckpt),
                "weights_sha256": sha256_file(ckpt / "model.safetensors"),
                "temperatures": temps,
            },
            "dataset": cfg["DATASET_CHECK"],
            "program_sha256": {
                "infer_ddp.py": sha256_file(Path(__file__)),
                "train_ddp.py": sha256_file(Path(td.__file__)),
            },
            "rows": rows,
            "seconds": seconds,
            "seconds_total": round(time.time() - t0, 1),
            "world_size": d.world,
            "max_len": cfg["MAX_LEN"],
            "head_max_len": cfg["HEAD_MAX_LEN"],
            "states_cut": {k: v for k, v in cut.items() if v},
            "labels_read": False,
            "trained": False,
            "hub_push": False,
        }
        (out / f"{PREFIX}{cfg['RUN_NAME']}_infer_record.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8"
        )
    d.close()


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
