"""Build ``notebook/newsaction_laya_fin.ipynb`` from its parts (PRD NA-08 S3; CLAUDE.md G25).

The notebook is an artifact: it runs on Kaggle and is never imported. Its cells are, in order: an
introduction; the ``parameters`` cell (one value set per run, written by ``kaggle_export.write_kernels``);
the environment and GPU check; the pinned install; the dataset check (every file's sha256 against the
dataset's own manifest, no label column in the val-B and test files); the model download and its sha256
check; ``%%writefile train_ddp.py`` holding ``notebook/train_ddp.py`` verbatim; the launch (``torchrun`` on
2 GPUs, one process per init); the output summary.

It is adapted from Laya's official 2×T4 notebook, whose last cells evaluate on the vendor's benchmark and
push the model to the Hugging Face Hub. Neither is here: nothing is uploaded anywhere
(``tests/test_train_notebook.py`` greps for Hub calls). ``build_notebook()`` is deterministic, and the
committed notebook must equal it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from newsaction.train import NOTEBOOK, load_training_config

PROGRAM: Final = NOTEBOOK.parent / "train_ddp.py"
WRITEFILE: Final = "%%writefile train_ddp.py\n"

INTRO: Final = """\
# NewsAction NA-08: Laya-Fin and the ModernBERT-large anchor (Kaggle GPU T4 ×2)

Fine-tunes **Laya** (`convaiinnovations/laya`, subfolder `typed-decisions`) on the NewsAction finance
questions (`INIT = "laya"`, *Laya-Fin*), or trains the same decision head freshly initialised on
**ModernBERT-large** (`answerdotai/ModernBERT-large`, `INIT = "modernbert"`, the clean anchor), with both T4
GPUs (`torchrun --nproc_per_node=2`). Adapted from Laya's official notebook
`laya_finetune_typed_decisions_2xT4_kaggle.ipynb`.

**Governance.** The attached dataset is private. It holds masked states, and labels for train and val-A
only; the val-B and test files have no label column. Nothing is pushed to the Hugging Face Hub or anywhere
else: the checkpoint stays in `/kaggle/working`.

**Settings.** Accelerator *GPU T4 x2*, Internet *on* (the pinned model revisions are downloaded from the Hub
and checked against their sha256). Outputs: `/kaggle/working/na08_*` (predictions, calibration, run record)
and `/kaggle/working/ckpt/` (the best checkpoint, fp32).

One parameter set per run is written into the next cell by `python -m newsaction.train.build --stage
kernels`; `MODE = "pilot"` measures throughput and rehearses the output path.
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
ON_KAGGLE = LOCAL is None and Path("/kaggle/working").is_dir()
if LOCAL is None and not ON_KAGGLE:
    raise RuntimeError("not on Kaggle: set LOCAL for a local run")
OUT_DIR = Path("/kaggle/working") if ON_KAGGLE else Path(LOCAL["out_dir"])
OUT_DIR.mkdir(parents=True, exist_ok=True)
DATA = Path(DATASET_DIR) if ON_KAGGLE else Path(LOCAL["dataset_dir"])
if ON_KAGGLE and not (DATA / "sha256_manifest.json").is_file():  # another mount layout: find the dataset
    found = sorted(p.parent for p in Path("/kaggle/input").rglob("sha256_manifest.json"))
    if len(found) != 1:
        raise RuntimeError(f"attach the NA-08 dataset; found {len(found)} candidate directories")
    DATA = found[0]
print("dataset:", DATA)
if ON_KAGGLE:
    subprocess.run(["nvidia-smi"], check=False)
N_GPU = torch.cuda.device_count()
for i in range(N_GPU):
    p = torch.cuda.get_device_properties(i)
    print(f"GPU {i}: {p.name} ({p.total_memory / 1e9:.1f} GB)")
if ON_KAGGLE and N_GPU < 2:
    raise RuntimeError("Accelerator must be 'GPU T4 x2' (Notebook options -> Accelerator)")
DEVICE = "cuda" if N_GPU else (LOCAL or {}).get("device", "cpu")
print(f"run {RUN_NAME}, mode {MODE}, inits {INITS}, seed {SEED}, device {DEVICE}, GPUs {N_GPU}")
"""

INSTALL: Final = """\
if ON_KAGGLE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *PIP], check=True)
import laya
import transformers

print("laya", laya.__version__, "| transformers", transformers.__version__, "| torch", torch.__version__)
"""

DATASET: Final = """\
import pyarrow.parquet as pq


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


manifest = json.loads((DATA / "sha256_manifest.json").read_text(encoding="utf-8"))
files = {}
for name, entry in manifest["files"].items():
    got = sha256(DATA / name)
    if got != entry["sha256"]:
        raise RuntimeError(f"{name}: sha256 {got} differs from the dataset manifest")
    files[name] = got
for name in ("val_b.parquet", "test_callA.parquet"):
    cols = pq.read_schema(DATA / name).names
    if any("label" in c.lower() for c in cols):
        raise RuntimeError(f"{name} has a label column")
INFO = json.loads((DATA / "dataset_info.json").read_text(encoding="utf-8"))
longest = max(q["head_tokens"] for q in INFO["questions"].values())
if longest > HEAD_MAX_LEN:
    raise RuntimeError(f"HEAD_MAX_LEN {HEAD_MAX_LEN} would cut a question of {longest} tokens")
DATASET_CHECK = {
    "dir": str(DATA),
    "files": files,
    "manifest_sha256": sha256(DATA / "sha256_manifest.json"),
    "label_columns": {"val_b": False, "test": False},
    "export_truncation": INFO["truncation"]["examples_cut"],
}
print(json.dumps(DATASET_CHECK, indent=1))
"""

MODELS: Final = """\
from huggingface_hub import snapshot_download

ROOT_FILES = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
              "special_tokens_map.json"]
MODEL_PATHS = {}
for init in INITS:
    spec = LAYA if init == "laya" else ANCHOR
    if LOCAL is not None and init in LOCAL.get("model_dirs", {}):
        root = Path(LOCAL["model_dirs"][init])
    else:
        sub = spec.get("subfolder")
        root = Path(snapshot_download(spec["repo"], revision=spec["revision"],
                                      allow_patterns=[f"{sub}/*"] if sub else ROOT_FILES))
    model_dir = root / spec["subfolder"] if spec.get("subfolder") else root
    weights = model_dir / "model.safetensors"
    got = sha256(weights)
    if got != spec["weights_sha256"]:
        raise RuntimeError(f"{init}: weights sha256 {got} != pinned {spec['weights_sha256']}")
    tok_json = model_dir / "tokenizer" / "tokenizer.json" if init == "laya" else model_dir / "tokenizer.json"
    MODEL_PATHS[init] = {"model_dir": str(model_dir), "weights": str(weights),
                         "tokenizer_json": str(tok_json)}
    print(init, spec["repo"], spec.get("subfolder"), spec["revision"], "weights sha256 OK")
"""

LAUNCH: Final = """\
PROGRAM_SHA256 = sha256("train_ddp.py")
if MODE == "pilot":
    launches = PILOT["launches"]
else:
    launches = [{"name": None, "init": INITS[0], "rehearse": True, "required": True, "hparams": {}}]
for launch in launches:
    tag = RUN_NAME if launch["name"] is None else f"{RUN_NAME}-{launch['name']}"
    run_cfg = {
        "RUN_NAME": RUN_NAME, "MODE": MODE, "INIT": launch["init"], "TAG": tag, "SEED": SEED,
        "EPOCHS": EPOCHS, "SHUFFLE_LABELS": SHUFFLE_LABELS, "SHUFFLE_SEED": SHUFFLE_SEED,
        "DATASET_DIR": str(DATA), "OUT_DIR": str(OUT_DIR), "MAX_LEN": MAX_LEN, "HEAD_MAX_LEN": HEAD_MAX_LEN,
        "QUESTIONS_BY_SOURCE": QUESTIONS_BY_SOURCE, "TRAIN_VARIANTS": TRAIN_VARIANTS, "LAYA": LAYA,
        "ANCHOR": ANCHOR, "HEAD": HEAD, "HPARAMS": {**HPARAMS, **launch.get("hparams", {})},
        "REHEARSE": launch["rehearse"], "TIME_BUDGET_HOURS": TIME_BUDGET_HOURS, "PILOT": PILOT,
        "ECE_BINS": ECE_BINS, "MODEL_PATHS": MODEL_PATHS, "DATASET_CHECK": DATASET_CHECK,
        "NOTEBOOK_START": NOTEBOOK_START, "DEVICE": DEVICE, "PROGRAM_SHA256": PROGRAM_SHA256,
        "LIMITS": (LOCAL or {}).get("limits"),
    }
    cfg_path = OUT_DIR / f"na08_{tag}_run_config.json"
    cfg_path.write_text(json.dumps(run_cfg, indent=1), encoding="utf-8")
    if N_GPU > 1:
        cmd = [sys.executable, "-m", "torch.distributed.run", "--standalone", f"--nproc_per_node={N_GPU}",
               "train_ddp.py", str(cfg_path)]
    else:
        cmd = [sys.executable, "train_ddp.py", str(cfg_path)]
    print("launch:", " ".join(cmd), flush=True)
    done = subprocess.run(cmd, check=False)
    if done.returncode != 0:
        if launch["required"]:
            raise RuntimeError(f"{tag} failed (exit code {done.returncode})")
        failure = {"tag": tag, "returncode": done.returncode, "hparams": run_cfg["HPARAMS"]}
        (OUT_DIR / f"na08_{tag}_failed.json").write_text(json.dumps(failure, indent=1), encoding="utf-8")
        print(f"optional launch {tag} failed (exit code {done.returncode}); recorded", flush=True)
"""

SUMMARY: Final = """\
outputs = {p.name: sha256(p) for p in sorted(OUT_DIR.glob("na08_*"))
           if p.is_file() and p.name != "na08_outputs.json"}
(OUT_DIR / "na08_outputs.json").write_text(json.dumps(outputs, indent=1), encoding="utf-8")
for p in sorted(OUT_DIR.glob("na08_*_run_record.json")):
    rec = json.loads(p.read_text(encoding="utf-8"))
    if rec["hub_push"] is not False:
        raise RuntimeError("a run record does not say hub_push: false")
    tp = rec["throughput"]
    print(p.name, "| best epoch", rec["best_epoch"], "| epochs", rec["epochs_run"],
          "| train seq/s", round(tp["train_seq_per_s"], 2),
          "| eval seq/s", round(tp.get("eval_seq_per_s", tp["eval_seq_per_s_probe"]), 2),
          "| peak GB", rec["peak_gpu_gb"])
print(len(outputs), "output files; nothing was pushed to the Hugging Face Hub")
"""


def _md(text: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _code(text: str, tags: list[str] | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"tags": tags} if tags else {}
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": meta,
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def build_notebook() -> dict[str, Any]:
    from newsaction.train.kaggle_export import PARAMS_TAG, params_cell_source, run_parameters

    cfg = load_training_config()
    params = run_parameters(cfg.kaggle.runs[0], cfg)
    program = PROGRAM.read_text(encoding="utf-8")
    cells = [
        _md(INTRO),
        _code(params_cell_source(params), tags=[PARAMS_TAG]),
        _md("## 1. Environment and GPUs\n"),
        _code(ENV),
        _md("## 2. Pinned packages\n"),
        _code(INSTALL),
        _md("## 3. Dataset check: sha256 of every file, no label column in val-B and test\n"),
        _code(DATASET),
        _md("## 4. Model weights at the pinned revisions, sha256-checked\n"),
        _code(MODELS),
        _md("## 5. The training and inference program (`train_ddp.py`)\n"),
        _code(WRITEFILE + program),
        _md("## 6. Launch: one `torchrun` per init, one process per GPU\n"),
        _code(LAUNCH),
        _md("## 7. Outputs (nothing is pushed to the Hub)\n"),
        _code(SUMMARY),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kaggle": {"accelerator": "nvidiaTeslaT4", "isGpuEnabled": True, "isInternetEnabled": True},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_text(nb: dict[str, Any] | None = None) -> str:
    return json.dumps(build_notebook() if nb is None else nb, indent=1, ensure_ascii=False) + "\n"


def write_notebook(path: Path = NOTEBOOK) -> Path:
    path.write_text(notebook_text(), encoding="utf-8")
    return path


def program_of(nb: dict[str, Any]) -> str:
    """The ``train_ddp.py`` text held by a notebook's ``%%writefile`` cell."""
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    found = [c for c in cells if c.startswith(WRITEFILE)]
    if len(found) != 1:
        raise ValueError(f"expected one {WRITEFILE.strip()} cell, found {len(found)}")
    return found[0][len(WRITEFILE) :]


def parameters_of(nb: dict[str, Any]) -> dict[str, Any]:
    """The values of a notebook's ``parameters`` cell."""
    from newsaction.train.kaggle_export import PARAMS_TAG

    cells = [c for c in nb["cells"] if PARAMS_TAG in c.get("metadata", {}).get("tags", [])]
    if len(cells) != 1:
        raise ValueError(f"expected one parameters cell, found {len(cells)}")
    ns: dict[str, Any] = {}
    exec(compile("".join(cells[0]["source"]), "<parameters>", "exec"), ns)
    return {k: v for k, v in ns.items() if k.isupper()}


def run_locally(nb: dict[str, Any], overrides: dict[str, Any], workdir: Path) -> dict[str, Any]:
    """Execute the notebook's code cells in order, in one namespace, from ``workdir`` (smoke tests).

    ``overrides`` replaces parameters; ``LOCAL`` must be set (out_dir, dataset_dir, model_dirs, device,
    limits). The ``%%writefile`` cell writes ``train_ddp.py`` into ``workdir``; the launch cell runs it with
    this interpreter. Returns the namespace.
    """
    import os

    from newsaction.train.kaggle_export import PARAMS_TAG, params_cell_source

    if not overrides.get("LOCAL"):
        raise ValueError("a local run needs LOCAL")
    params = {**parameters_of(nb), **overrides}
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
                src = params_cell_source(params)
            if src.startswith(WRITEFILE):
                (workdir / "train_ddp.py").write_text(src[len(WRITEFILE) :], encoding="utf-8")
                continue
            exec(compile(src, f"<notebook cell {i}>", "exec"), ns)
    finally:
        os.chdir(cwd)
    return ns
