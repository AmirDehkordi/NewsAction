"""Build the NA-11 S7 inference notebook (``notebook/newsaction_infer.ipynb``) from its parts (CLAUDE.md G25).

Cells, in order: an introduction; the ``parameters`` cell (one set per run, written by
``production.kaggle_infer``); the environment check (the attached NA-11 dataset, found by its manifest, and
the checkpoint of the attached NA-08 training kernel, found by its ``rl_agent_config.json``); NA-08's pinned
install; the dataset check (every file's sha256 against the manifest; no label column); ``%%writefile
train_ddp.py`` holding NA-08's program verbatim (its helpers; the import verifies its sha256 as before);
``%%writefile infer_ddp.py``; the launch (``torchrun`` on 2 GPUs); the output summary. Nothing is uploaded
anywhere. ``build_notebook()`` is deterministic and the committed notebook must equal it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from newsaction.train import NOTEBOOK
from newsaction.train.nbbuild import INSTALL, PROGRAM, _code, _md

INFER_PROGRAM: Final = NOTEBOOK.parent / "infer_ddp.py"
INFER_NOTEBOOK: Final = NOTEBOOK.parent / "newsaction_infer.ipynb"
PARAMS_TAG: Final = "parameters"

INTRO: Final = """\
# NewsAction NA-11: inference with the frozen NA-08 checkpoints (Kaggle GPU T4 ×2)

Predicts the NA-11 states (the test period's Call B states, built after the pre-registration freeze, and a few
validation files) with one **frozen** NA-08 checkpoint: Laya-Fin `laya-s13` or the anchor `anchor-s13`, read
from the attached training kernel's output. Nothing is trained.

**Governance.** The attached dataset is private and holds masked states only, with no label column. Nothing is
pushed to the Hugging Face Hub or anywhere else.
"""

PARAMS_DEFAULT: Final = """\
RUN_NAME = "laya-s13"
CKPT_KERNEL = "newsaction-na08-laya-s13"
TEMPERATURES = {"react": 1.0, "mag": 1.0, "cont": 1.0}
FILES = ["check_val_a"]
MAX_LEN = 1036
HEAD_MAX_LEN = 143
HPARAMS = {"eval_batch": 32, "amp": "fp16"}
PIP = ["laya==0.4.14", "transformers==5.20.2"]
LOCAL = None
"""

ENV: Final = """\
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import torch

NOTEBOOK_START = time.time()
ON_KAGGLE = Path("/kaggle/input").is_dir() and LOCAL is None
if LOCAL is None and not ON_KAGGLE:
    raise RuntimeError("not on Kaggle: set LOCAL for a local run")
OUT_DIR = Path("/kaggle/working") if ON_KAGGLE else Path(LOCAL["out_dir"])
OUT_DIR.mkdir(parents=True, exist_ok=True)
if ON_KAGGLE:
    found = sorted(p.parent for p in Path("/kaggle/input").rglob("na11_manifest.json"))
    if len(found) != 1:
        raise RuntimeError(f"attach the NA-11 dataset; found {len(found)} candidate directories")
    DATA = found[0]
    ckpts = sorted(p.parent for p in Path("/kaggle/input").rglob("rl_agent_config.json")
                   if CKPT_KERNEL in str(p) and p.parent.name == "ckpt")
    if len(ckpts) != 1:
        raise RuntimeError(f"attach the kernel {CKPT_KERNEL}; found {len(ckpts)} checkpoints")
    CKPT = ckpts[0]
    subprocess.run(["nvidia-smi"], check=False)
else:
    DATA, CKPT = Path(LOCAL["dataset_dir"]), Path(LOCAL["ckpt_dir"])
print("dataset:", DATA, "| checkpoint:", CKPT)
N_GPU = torch.cuda.device_count()
if ON_KAGGLE and N_GPU < 2:
    raise RuntimeError("Accelerator must be 'GPU T4 x2' (Notebook options -> Accelerator)")
DEVICE = "cuda" if N_GPU else (LOCAL or {}).get("device", "cpu")
print(f"run {RUN_NAME}, files {FILES}, device {DEVICE}, GPUs {N_GPU}")
"""

DATASET: Final = """\
import pyarrow.parquet as pq


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


manifest = json.loads((DATA / "na11_manifest.json").read_text(encoding="utf-8"))
files = {}
for name, entry in manifest["files"].items():
    got = sha256(DATA / name)
    if got != entry["sha256"]:
        raise RuntimeError(f"{name}: sha256 {got} differs from the dataset manifest")
    if name.endswith(".parquet") and any("label" in c.lower() for c in pq.read_schema(DATA / name).names):
        raise RuntimeError(f"{name} has a label column")
    files[name] = got
DATASET_CHECK = {"dir": str(DATA), "files": files, "manifest_sha256": sha256(DATA / "na11_manifest.json")}
print(json.dumps(DATASET_CHECK, indent=1))
"""

LAUNCH: Final = """\
run_cfg = {
    "RUN_NAME": RUN_NAME, "CKPT_DIR": str(CKPT), "TEMPERATURES": TEMPERATURES, "FILES": FILES,
    "DATASET_DIR": str(DATA), "OUT_DIR": str(OUT_DIR), "MAX_LEN": MAX_LEN, "HEAD_MAX_LEN": HEAD_MAX_LEN,
    "HPARAMS": HPARAMS, "DATASET_CHECK": DATASET_CHECK, "DEVICE": DEVICE,
}
cfg_path = OUT_DIR / f"na11_{RUN_NAME}_infer_config.json"
cfg_path.write_text(json.dumps(run_cfg, indent=1), encoding="utf-8")
if N_GPU > 1:
    cmd = [sys.executable, "-m", "torch.distributed.run", "--standalone", f"--nproc_per_node={N_GPU}",
           "infer_ddp.py", str(cfg_path)]
else:
    cmd = [sys.executable, "infer_ddp.py", str(cfg_path)]
print("launch:", " ".join(cmd), flush=True)
done = subprocess.run(cmd, check=False)
if done.returncode != 0:
    raise RuntimeError(f"inference failed (exit code {done.returncode})")
"""

SUMMARY: Final = """\
outputs = {p.name: sha256(p) for p in sorted(OUT_DIR.glob("na11_*"))
           if p.is_file() and p.name != "na11_outputs.json"}
(OUT_DIR / "na11_outputs.json").write_text(json.dumps(outputs, indent=1), encoding="utf-8")
rec = json.loads((OUT_DIR / f"na11_{RUN_NAME}_infer_record.json").read_text(encoding="utf-8"))
if rec["hub_push"] is not False or rec["trained"] is not False:
    raise RuntimeError("the record does not say hub_push: false and trained: false")
print(json.dumps({"rows": rec["rows"], "seconds": rec["seconds"], "total_s": rec["seconds_total"]}, indent=1))
print(len(outputs), "output files; nothing was pushed to the Hugging Face Hub")
"""


def build_notebook() -> dict[str, Any]:
    program = PROGRAM.read_text(encoding="utf-8")
    infer = INFER_PROGRAM.read_text(encoding="utf-8")
    cells = [
        _md(INTRO),
        _code(PARAMS_DEFAULT, [PARAMS_TAG]),
        _md("## 1. Environment, dataset and checkpoint\n"),
        _code(ENV),
        _code(INSTALL),
        _code(DATASET),
        _md("## 2. Programs: NA-08's `train_ddp.py` (verbatim, for its helpers) and `infer_ddp.py`\n"),
        _code("%%writefile train_ddp.py\n" + program),
        _code("%%writefile infer_ddp.py\n" + infer),
        _md("## 3. Launch and outputs\n"),
        _code(LAUNCH),
        _code(SUMMARY),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_text(nb: dict[str, Any] | None = None) -> str:
    return json.dumps(build_notebook() if nb is None else nb, indent=1, ensure_ascii=False) + "\n"


def write_notebook(path: Path = INFER_NOTEBOOK) -> Path:
    path.write_text(notebook_text(), encoding="utf-8")
    return path


def with_params(nb: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """The notebook with its parameters cell set to ``params`` (repr per value)."""
    src = "".join(f"{k} = {v!r}\n" for k, v in params.items())
    out: dict[str, Any] = json.loads(json.dumps(nb))
    for cell in out["cells"]:
        if PARAMS_TAG in cell.get("metadata", {}).get("tags", []):
            cell["source"] = src.splitlines(keepends=True)
    return out


if __name__ == "__main__":
    print(write_notebook())


def run_locally(nb: dict[str, Any], params: dict[str, Any], workdir: Path) -> dict[str, Any]:
    """Execute the notebook's code cells in order from ``workdir`` (smoke tests): the parameters cell is
    replaced by ``params`` (``LOCAL`` must be set) and each ``%%writefile <name>`` cell writes its file."""
    import os

    if not params.get("LOCAL"):
        raise ValueError("a local run needs LOCAL")
    ns: dict[str, Any] = {}
    workdir.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    os.chdir(workdir)
    try:
        for i, cell in enumerate(nb["cells"]):
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            if PARAMS_TAG in cell.get("metadata", {}).get("tags", []):
                src = "".join(f"{k} = {v!r}\n" for k, v in params.items())
            if src.startswith("%%writefile "):
                head, body = src.split("\n", 1)
                (workdir / head.split()[1]).write_text(body, encoding="utf-8")
                continue
            exec(compile(src, f"<notebook cell {i}>", "exec"), ns)
    finally:
        os.chdir(cwd)
    return ns
