"""NA-08 training and inference program (PRD NA-08 S3–S5), embedded in newsaction_laya_fin.ipynb.

The notebook writes this file next to itself and launches it with
``torchrun --standalone --nproc_per_node=2 train_ddp.py run_config.json`` on Kaggle's 2×T4 (one process per
GPU, DistributedDataParallel), or with ``python train_ddp.py run_config.json`` on one device.

What it does, adapted from Laya's official 2×T4 notebook (``laya.common`` / ``laya.train`` primitives):

- **Model.** ``INIT = laya``: Laya's typed-decisions checkpoint (encoder + decision head). ``INIT =
  modernbert``: the ModernBERT-large encoder and the same decision-head architecture, freshly initialised
  (seeded). Both weight files are checked against their sha256 before loading. The act head is frozen and
  never used (Laya's model card: no usable signal).
- **Data.** The private dataset's train and val-A files carry labels; the val-B and test files have no label
  column, and this program never looks for one. Sequences are Laya's ``[CLS] question [SEP] options [SEP]
  state [SEP]``; every tokenized state must have the token count the dataset recorded, and every state that
  ``max_len`` would cut is counted and reported.
- **Training.** AdamW (backbone / head learning rates), linear warm-up then cosine decay, fp16 autocast with
  gradient scaling, gradient checkpointing, gradient accumulation, the official RLCD objective
  (``laya.train.rlcd_loss``: a proper-scoring policy-gradient term plus soft cross-entropy). After each epoch
  the val-A loss (mean cross-entropy over labelled examples outside the first 5 sessions) decides early
  stopping; the best epoch's weights are kept. A time budget stops training early if the session limit is
  near, so a run always ends with outputs.
- **Calibration.** One temperature per (question type, option count), i.e. per head, fit on val-A by
  minimising the NLL; ECE (15 bins) on val-A before and after. Nothing is computed on val-B or test.
- **Outputs** (``OUT_DIR``): per split, logits and probabilities per example (Arrow IPC); the calibration
  record; the run record; the best checkpoint in fp32. Nothing is pushed to the Hugging Face Hub.

``MODE = pilot`` trains a 5% subsample for a fixed number of steps, measures throughput and rehearses the
whole output path on small val-A / val-B / test subsets.
"""

from __future__ import annotations

import os

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import contextlib
import hashlib
import itertools
import json
import math
import platform
import random
import sys
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as pq
import torch
import torch.distributed as dist

FILES = {
    "train": "train.parquet",
    "val_a": "val_a.parquet",
    "val_b": "val_b.parquet",
    "test": "test_callA.parquet",
}
LABELLED = ("train", "val_a")
READ_COLUMNS = (
    "example_id",
    "event_id",
    "call",
    "window",
    "variant",
    "question_id",
    "question_json",
    "state_json",
    "n_tokens_state",
)
QTYPE = {"choice": 0, "score": 1}
SPECIAL = 4  # [CLS], [SEP] after the instruction, [SEP] after the options, [SEP] after the state
TEMP_BOUNDS = (0.05, 20.0)
PREFIX = "na08_"


# --- small pure helpers (unit-tested locally) ---------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def softmax(z: np.ndarray, t: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64) / t
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def nll(logits: Sequence[np.ndarray], labels: np.ndarray, t: float = 1.0) -> float:
    """Mean negative log-likelihood of the labels under softmax(logits / t)."""
    if not len(labels):
        return float("nan")
    out = 0.0
    for z, y in zip(logits, labels, strict=True):
        zz = np.asarray(z, dtype=np.float64) / t
        m = zz.max()
        out += -(zz[int(y)] - m - math.log(np.exp(zz - m).sum()))
    return out / len(labels)


def fit_temperature(logits: Sequence[np.ndarray], labels: np.ndarray) -> float:
    """argmin_T NLL(softmax(z / T)) on [0.05, 20]: a log-grid, then golden-section refinement."""
    lo, hi = math.log(TEMP_BOUNDS[0]), math.log(TEMP_BOUNDS[1])
    grid = np.linspace(lo, hi, 61)
    vals = [nll(logits, labels, math.exp(g)) for g in grid]
    i = int(np.argmin(vals))
    a, b = grid[max(0, i - 1)], grid[min(len(grid) - 1, i + 1)]
    phi = (math.sqrt(5) - 1) / 2
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = nll(logits, labels, math.exp(c)), nll(logits, labels, math.exp(d))
    for _ in range(40):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = nll(logits, labels, math.exp(c))
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = nll(logits, labels, math.exp(d))
    return float(math.exp((a + b) / 2))


def ece(conf: np.ndarray, correct: np.ndarray, bins: int) -> float:
    """Top-label expected calibration error over ``bins`` equal-width bins (laya.common.ece_score's edges)."""
    conf, correct = np.asarray(conf, dtype=np.float64), np.asarray(correct, dtype=np.float64)
    if not len(conf):
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = 0.0
    for i, (lo, hi) in enumerate(itertools.pairwise(edges)):
        sel = ((conf >= lo) if i == 0 else (conf > lo)) & (conf <= hi)
        if sel.any():
            out += sel.mean() * abs(conf[sel].mean() - correct[sel].mean())
    return float(out)


def bucket_batches(
    lengths: np.ndarray, batch: int, rng: np.random.Generator, chunk: int = 64
) -> list[np.ndarray]:
    """Random micro-batches of similar length: shuffle, sort within chunks of ``chunk`` batches, shuffle."""
    idx = rng.permutation(len(lengths))
    out: list[np.ndarray] = []
    for start in range(0, len(idx), batch * chunk):
        block = idx[start : start + batch * chunk]
        block = block[np.argsort(lengths[block], kind="stable")]
        out += [block[i : i + batch] for i in range(0, len(block), batch)]
    return [out[i] for i in rng.permutation(len(out))]


def shard(batches: list[np.ndarray], rank: int, world: int) -> list[np.ndarray]:
    """Rank ``rank``'s share; every rank gets the same number of batches (DDP needs matched all-reduces)."""
    n = len(batches) // world * world
    return batches[rank:n:world]


def permute_labels(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Labels permuted within each question among labelled rows (the shuffled-label control, PREREG §9.3)."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    for qid in sorted(out["question_id"].unique()):
        m = (out["question_id"] == qid).to_numpy() & (out["label"] >= 0).to_numpy()
        out.loc[m, "label"] = rng.permutation(out.loc[m, "label"].to_numpy())
    return out


def lr_factor(step: int, total: int, warmup: int, floor: float) -> float:
    """Linear warm-up to 1, then cosine decay to ``floor`` (a fraction of the base learning rate)."""
    if warmup and step < warmup:
        return (step + 1) / warmup
    span = max(1, total - warmup)
    progress = min(1.0, (step - warmup) / span)
    return floor + (1.0 - floor) * 0.5 * (1.0 + math.cos(math.pi * progress))


def session_of(event_id: str) -> str:
    """The session date in an event id ``W0:{company}:{session}``."""
    return event_id.rsplit(":", 1)[1]


# --- distributed --------------------------------------------------------------------------------------


class Dist:
    """One process per GPU under torchrun (NCCL), or a single process."""

    def __init__(self, device_pref: str) -> None:
        self.world = int(os.environ.get("WORLD_SIZE", "1"))
        self.rank = int(os.environ.get("RANK", "0"))
        self.local_rank = int(os.environ.get("LOCAL_RANK", "0"))
        if self.world > 1:
            dist.init_process_group("nccl")
            torch.cuda.set_device(self.local_rank)
            self.device = torch.device("cuda", self.local_rank)
        elif device_pref == "cuda" or (device_pref == "auto" and torch.cuda.is_available()):
            self.device = torch.device("cuda", 0)
        elif device_pref == "mps" or (device_pref == "auto" and torch.backends.mps.is_available()):
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        self.main = self.rank == 0

    def barrier(self) -> None:
        if self.world > 1:
            dist.barrier()

    def gather(self, obj: Any) -> list[Any]:
        if self.world == 1:
            return [obj]
        out: list[Any] = [None] * self.world
        dist.all_gather_object(out, obj)
        return out

    def close(self) -> None:
        if self.world > 1:
            dist.destroy_process_group()


def log(d: Dist, msg: str) -> None:
    if d.main:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --- data ---------------------------------------------------------------------------------------------


def read_split(cfg: dict[str, Any], split: str) -> pd.DataFrame:
    """One dataset file, restricted to the run's sources, questions and variants; ``label`` −1 = none."""
    path = Path(cfg["DATASET_DIR"]) / FILES[split]
    names = pq.read_schema(path).names
    cols = list(READ_COLUMNS) + (["label_index"] if split in LABELLED else [])
    cols += ["embargo"] if split == "val_a" else []
    missing = [c for c in cols if c not in names]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    df = pq.read_table(path, columns=cols).to_pandas()
    src = df["call"] + "_" + df["window"]
    allowed = cfg["QUESTIONS_BY_SOURCE"]
    keep = np.array(
        [q in allowed.get(s, []) for s, q in zip(src, df["question_id"], strict=True)], dtype=bool
    )
    variants = cfg["TRAIN_VARIANTS"] if split == "train" else ["full"]
    keep &= df["variant"].isin(variants).to_numpy()
    df = df[keep].reset_index(drop=True)
    if split in LABELLED:
        df["label"] = df.pop("label_index").astype("float64").fillna(-1).astype(np.int64)
    else:
        df["label"] = -1
    df["embargo"] = df["embargo"].astype(bool) if "embargo" in df else False
    limit = (cfg.get("LIMITS") or {}).get(split)
    if limit is not None and len(df) > limit:
        df = df.sample(n=int(limit), random_state=0).sort_index().reset_index(drop=True)
    return df


class Questions:
    """The run's questions in Laya's internal form, with their head lengths (no cut allowed)."""

    def __init__(self, frames: Sequence[pd.DataFrame], tok: Any, head_max_len: int) -> None:
        from laya.common import build_head
        from laya.train import to_internal

        self.q: dict[str, dict[str, Any]] = {}
        self.k: dict[str, int] = {}
        self.head: dict[str, int] = {}
        for df in frames:
            for qid, qj in df.groupby("question_id")["question_json"].agg(lambda s: sorted(set(s))).items():
                if len(qj) != 1:
                    raise ValueError(f"question {qid} has {len(qj)} wordings")
                q = to_internal(qid, json.loads(qj[0]))
                if qid in self.q and self.q[qid] != q:
                    raise ValueError(f"question {qid} differs between files")
                ids, markers, stats = build_head(tok, q, head_max_len)
                full, _, _ = build_head(tok, q, 100_000)
                if ids != full or stats["options_distinct"] != stats["options"]:
                    raise ValueError(f"HEAD_MAX_LEN {head_max_len} cuts question {qid} ({len(full)} tokens)")
                self.q[qid], self.k[qid], self.head[qid] = q, len(markers), len(ids)

    def qtype(self, qid: str) -> int:
        return QTYPE[self.q[qid]["t"]]


def seq_lengths(df: pd.DataFrame, qs: Questions) -> np.ndarray:
    return (df["n_tokens_state"].to_numpy() + df["question_id"].map(qs.head).to_numpy() + 1).astype(np.int64)


def truncation(df: pd.DataFrame, qs: Questions, max_len: int) -> list[str]:
    """Example ids whose state ``max_len`` would cut."""
    room = df["question_id"].map(lambda q: max_len - qs.head[q] - 1)
    return df.loc[df["n_tokens_state"].to_numpy() > room.to_numpy(), "example_id"].tolist()


def encode_batch(
    df: pd.DataFrame, rows: np.ndarray, qs: Questions, tok: Any, cfg: dict[str, Any]
) -> dict[str, Any]:
    from laya.common import collate_items
    from laya.train import encode_item

    sub = df.iloc[rows]
    ids = tok(sub["state_json"].tolist(), add_special_tokens=False)["input_ids"]
    items = []
    for state_ids, (_, r) in zip(ids, sub.iterrows(), strict=True):
        if len(state_ids) != int(r["n_tokens_state"]):
            raise ValueError(
                f"{r['example_id']}: {len(state_ids)} tokens, dataset says {r['n_tokens_state']}"
            )
        k = qs.k[r["question_id"]]
        target = np.full(k, 1.0 / k) if r["label"] < 0 else np.eye(k)[int(r["label"])]
        item = {
            "q": qs.q[r["question_id"]],
            "state_ids": list(state_ids),
            "target": target.tolist(),
            "qtype": qs.qtype(r["question_id"]),
            "k": k,
        }
        items.append(encode_item(tok, item, cfg["MAX_LEN"], cfg["HEAD_MAX_LEN"]))
    return collate_items([items], tok.pad_token_id)


# --- model --------------------------------------------------------------------------------------------


def build(cfg: dict[str, Any], init: str, seed: int) -> tuple[torch.nn.Module, Any, dict[str, Any]]:
    """(model, tokenizer, provenance) for ``init``; weights checked against their sha256 first."""
    from laya.agent import _fix_tokenizer_config
    from laya.common import build_model
    from safetensors.torch import load_file
    from transformers import AutoTokenizer

    paths = cfg["MODEL_PATHS"][init]
    spec = cfg["LAYA"] if init == "laya" else cfg["ANCHOR"]
    weights = Path(paths["weights"])
    digest = sha256_file(weights)
    if digest != spec["weights_sha256"]:
        raise ValueError(f"{init}: weights sha256 {digest} != pinned {spec['weights_sha256']}")
    head_cfg = {"head_layers": cfg["HEAD"]["head_layers"], "act_costs": cfg["HEAD"]["act_costs"]}
    torch.manual_seed(seed)
    if init == "laya":
        model_dir = Path(paths["model_dir"])
        _fix_tokenizer_config(str(model_dir))
        lcfg = json.loads((model_dir / "rl_agent_config.json").read_text(encoding="utf-8"))
        for k, v in head_cfg.items():
            if lcfg.get(k) != v:
                raise ValueError(f"laya config {k}={lcfg.get(k)!r}, expected {v!r}")
        tok = AutoTokenizer.from_pretrained(str(model_dir / "tokenizer"))
        model = build_model(lcfg, encoder_dir=str(model_dir / "encoder"))
        model.load_state_dict(load_file(str(weights)), strict=True)
        model_cfg = {**lcfg}
    else:
        enc_dir = Path(paths["model_dir"])
        tok = AutoTokenizer.from_pretrained(str(enc_dir))
        model_cfg = {"encoder": spec["repo"], **head_cfg}
        model = build_model({**model_cfg, "encoder": str(enc_dir)}, encoder_dir=None, pretrained=True)
    model = model.float()
    for p in model.act_head.parameters():
        p.requires_grad_(False)
    prov = {
        "init": init,
        "repo": spec["repo"],
        "subfolder": spec.get("subfolder"),
        "revision": spec["revision"],
        "weights_sha256": digest,
        "weights_verified": True,
        "tokenizer_sha256": sha256_file(Path(paths["tokenizer_json"])),
        "head_fresh": init != "laya",
    }
    return model, tok, {"provenance": prov, "model_cfg": model_cfg}


def save_ckpt(
    model: torch.nn.Module, tok: Any, model_cfg: dict[str, Any], path: Path, extra: dict[str, Any]
) -> None:
    """Laya's checkpoint layout, weights in fp32 (the exact weights behind the predictions)."""
    from safetensors.torch import save_file

    path.mkdir(parents=True, exist_ok=True)
    # Laya's own temperatures do not apply to these heads: neutral here, the val-A ones in na08_temperatures.
    vendor = ("temperature", "temperature_by_options", "lang_temperatures", "binning_map", "training")
    model_cfg = {k: v for k, v in model_cfg.items() if k not in vendor}
    model_cfg = {**model_cfg, "temperature": [1.0, 1.0, 1.0], "model_name": "newsaction-na08"}
    tmp = path / "model.safetensors.tmp"
    save_file({k: v.detach().float().cpu().contiguous() for k, v in model.state_dict().items()}, str(tmp))
    tmp.replace(path / "model.safetensors")
    model.encoder.config.save_pretrained(str(path / "encoder"))
    tok.save_pretrained(str(path / "tokenizer"))
    (path / "rl_agent_config.json").write_text(json.dumps({**model_cfg, **extra}, indent=2), encoding="utf-8")


# --- training and inference ---------------------------------------------------------------------------


def autocast(d: Dist, cfg: dict[str, Any]) -> contextlib.AbstractContextManager[Any]:
    if d.device.type == "cuda" and cfg["HPARAMS"]["amp"] == "fp16":
        return torch.autocast("cuda", dtype=torch.float16)
    return contextlib.nullcontext()


def forward(model: torch.nn.Module, batch: dict[str, Any], d: Dist, cfg: dict[str, Any]) -> torch.Tensor:
    dev = d.device
    with autocast(d, cfg):
        logits, _act = model(
            batch["input_ids"].to(dev),
            batch["attention_mask"].to(dev),
            batch["marker_pos"].to(dev),
            batch["marker_mask"].to(dev),
            batch["qtype"].to(dev),
        )
    return logits.float()


@torch.no_grad()
def infer(
    model: torch.nn.Module, df: pd.DataFrame, qs: Questions, tok: Any, cfg: dict[str, Any], d: Dist
) -> list[np.ndarray]:
    """Logits (each row's own options) for every row of ``df``, sharded over ranks and gathered."""
    model.eval()
    lengths = seq_lengths(df, qs)
    order = np.argsort(-lengths, kind="stable")
    mine = order[d.rank :: d.world]
    bs = cfg["HPARAMS"]["eval_batch"]
    got: dict[int, np.ndarray] = {}
    for start in range(0, len(mine), bs):
        rows = mine[start : start + bs]
        out = forward(model, encode_batch(df, rows, qs, tok, cfg), d, cfg).cpu().numpy()
        for r, z in zip(rows, out, strict=True):
            got[int(r)] = z[: qs.k[df["question_id"].iat[int(r)]]].astype(np.float32)
    merged: dict[int, np.ndarray] = {}
    for part in d.gather(got):
        merged.update(part)
    if len(merged) != len(df):
        raise RuntimeError(f"inference returned {len(merged)} of {len(df)} rows")
    return [merged[i] for i in range(len(df))]


def fit_mask(df: pd.DataFrame) -> np.ndarray:
    """Val-A rows used to fit (early stopping, temperatures): labelled and outside the embargo."""
    return (df["label"].to_numpy() >= 0) & ~df["embargo"].to_numpy(dtype=bool)


def val_loss(df: pd.DataFrame, logits: list[np.ndarray]) -> float:
    m = fit_mask(df)
    return nll([z for z, k in zip(logits, m, strict=True) if k], df.loc[m, "label"].to_numpy())


class Trainer:
    def __init__(self, model: torch.nn.Module, cfg: dict[str, Any], d: Dist, n_updates: int) -> None:
        from torch.nn.parallel import DistributedDataParallel

        hp = cfg["HPARAMS"]
        self.cfg, self.d, self.model = cfg, d, model
        if d.device.type == "cuda" and hp["grad_checkpointing"]:
            model.encoder.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
            model.head_checkpointing = True
        model.to(d.device)
        self.net = (
            DistributedDataParallel(
                model, device_ids=[d.local_rank], find_unused_parameters=False, gradient_as_bucket_view=True
            )
            if d.world > 1
            else model
        )
        enc = [p for n, p in model.named_parameters() if n.startswith("encoder.") and p.requires_grad]
        head = [p for n, p in model.named_parameters() if not n.startswith("encoder.") and p.requires_grad]
        self.params = enc + head
        self.opt = torch.optim.AdamW(
            [{"params": enc, "lr": hp["lr_backbone"]}, {"params": head, "lr": hp["lr_head"]}],
            weight_decay=hp["weight_decay"],
        )
        warm = round(hp["warmup_frac"] * n_updates)
        floors = [hp["min_lr"] / hp["lr_backbone"], hp["min_lr"] / hp["lr_head"]]
        self.sched = torch.optim.lr_scheduler.LambdaLR(
            self.opt, [lambda s, f=f: lr_factor(s, n_updates, warm, f) for f in floors]
        )
        self.scaler = torch.amp.GradScaler("cuda", enabled=d.device.type == "cuda" and hp["amp"] == "fp16")
        self.updates = 0

    def step_batches(
        self, df: pd.DataFrame, batches: list[np.ndarray], qs: Questions, tok: Any, sigma: float, stop: Any
    ) -> Iterator[float]:
        """Train on ``batches`` (this rank's share); yields each micro-batch's loss; ``stop()`` ends early."""
        from laya.train import rlcd_loss, soft_ce_loss

        hp, d = self.cfg["HPARAMS"], self.d
        accum = hp["grad_accum"]
        self.net.train()
        self.opt.zero_grad(set_to_none=True)
        n = len(batches)
        for i, rows in enumerate(batches):
            window_start = (i // accum) * accum
            window = min(accum, n - window_start)
            sync = (i + 1) % accum == 0 or i == n - 1
            ctx = self.net.no_sync() if (d.world > 1 and not sync) else contextlib.nullcontext()
            with ctx:
                batch = encode_batch(df, rows, qs, tok, self.cfg)
                logits = forward(self.net, batch, d, self.cfg)
                mask, target = batch["marker_mask"].to(d.device), batch["target"].to(d.device)
                qtype = batch["qtype"].to(d.device)
                if hp["loss"] == "rlcd":
                    loss = rlcd_loss(
                        logits,
                        target,
                        mask,
                        qtype,
                        sigma,
                        samples=hp["rl_samples"],
                        w_sph=hp["w_sph"],
                        w_rps=hp["w_rps"],
                    )
                else:
                    loss = soft_ce_loss(logits, target, mask)
                self.scaler.scale(loss / window).backward()
            if sync:
                self.scaler.unscale_(self.opt)
                torch.nn.utils.clip_grad_norm_(self.params, hp["grad_clip"])
                self.scaler.step(self.opt)
                self.scaler.update()
                self.sched.step()
                self.opt.zero_grad(set_to_none=True)
                self.updates += 1
                if stop():
                    yield float(loss.item())
                    return
            yield float(loss.item())


def write_preds(path: Path, df: pd.DataFrame, logits: list[np.ndarray], temps: dict[str, float]) -> None:
    probs = [softmax(z, temps[q]).astype(np.float32) for z, q in zip(logits, df["question_id"], strict=True)]
    raw = [softmax(z).astype(np.float32) for z in logits]
    table = pa.table(
        {
            "example_id": pa.array(df["example_id"].tolist(), pa.string()),
            "question_id": pa.array(df["question_id"].tolist(), pa.string()),
            "k": pa.array([len(z) for z in logits], pa.int8()),
            "logits": pa.array([z.tolist() for z in logits], pa.list_(pa.float32())),
            "probs": pa.array([p.tolist() for p in probs], pa.list_(pa.float32())),
            "probs_raw": pa.array([p.tolist() for p in raw], pa.list_(pa.float32())),
        }
    )
    tmp = path.with_suffix(".tmp")
    feather.write_feather(table, str(tmp), compression="zstd")
    tmp.replace(path)


def calibrate(
    df: pd.DataFrame, logits: list[np.ndarray], bins: int, qtypes: dict[str, str]
) -> dict[str, Any]:
    """One temperature per head (question type, option count) on val-A; ECE before / after (val-A)."""
    m = fit_mask(df)
    out: dict[str, Any] = {"split": "val_a", "rows": "labelled, outside the embargo", "heads": {}}
    sessions = df.loc[m, "event_id"].map(session_of)
    out["fit_sessions"] = [min(sessions), max(sessions)] if len(sessions) else None
    for qid in sorted(df["question_id"].unique()):
        sel = m & (df["question_id"] == qid).to_numpy()
        z = [lz for lz, s in zip(logits, sel, strict=True) if s]
        y = df.loc[sel, "label"].to_numpy()
        if len(y) < 10:
            raise ValueError(f"only {len(y)} val-A rows to fit the {qid} temperature")
        t = fit_temperature(z, y)
        p1, pt = softmax(np.stack(z)), softmax(np.stack(z), t)
        out["heads"][qid] = {
            "type_options": f"{qtypes[qid]}:{len(z[0])}",
            "n": len(y),
            "temperature": t,
            "nll_before": nll(z, y),
            "nll_after": nll(z, y, t),
            "ece_before": ece(p1.max(1), p1.argmax(1) == y, bins),
            "ece_after": ece(pt.max(1), pt.argmax(1) == y, bins),
            "accuracy": float((p1.argmax(1) == y).mean()),
        }
    return out


def versions() -> dict[str, Any]:
    import laya
    import transformers

    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "laya": laya.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyarrow": pa.__version__,
    }


def gpus() -> dict[str, Any]:
    if not torch.cuda.is_available():
        return {"count": 0, "names": []}
    names = [torch.cuda.get_device_properties(i).name for i in range(torch.cuda.device_count())]
    mem = [round(torch.cuda.get_device_properties(i).total_memory / 1e9, 2) for i in range(len(names))]
    return {"count": len(names), "names": names, "memory_gb": mem}


def peak_gb(d: Dist) -> float | None:
    if d.device.type != "cuda":
        return None
    return round(torch.cuda.max_memory_allocated(d.device) / 1e9, 3)


# --- main ---------------------------------------------------------------------------------------------


def run(cfg: dict[str, Any]) -> None:
    from laya.train import sigma_at

    init, seed, tag = cfg["INIT"], int(cfg["SEED"]), cfg["TAG"]
    out = Path(cfg["OUT_DIR"])
    pilot = cfg["MODE"] == "pilot"
    rehearse = bool(cfg.get("REHEARSE", True))
    d = Dist(cfg.get("DEVICE", "auto"))
    t_start = time.time()
    deadline = float(cfg["NOTEBOOK_START"]) + 3600.0 * float(cfg["TIME_BUDGET_HOURS"])
    random.seed(seed)
    np.random.seed(seed)
    if d.device.type == "cuda":
        torch.use_deterministic_algorithms(True, warn_only=True)
    model, tok, meta = build(cfg, init, seed)
    torch.manual_seed(seed + 1000 * d.rank)  # per-rank stream: RLCD noise, dropout
    log(d, f"{tag}: built {init} on {d.device} (world {d.world})")

    frames = {s: read_split(cfg, s) for s in FILES}
    if cfg["SHUFFLE_LABELS"]:
        for s in LABELLED:
            frames[s] = permute_labels(frames[s], int(cfg["SHUFFLE_SEED"]) + LABELLED.index(s))
    qs = Questions(list(frames.values()), tok, cfg["HEAD_MAX_LEN"])
    cut = {s: truncation(df, qs, cfg["MAX_LEN"]) for s, df in frames.items()}
    rows_full = {s: len(f) for s, f in frames.items()}
    log(d, f"{tag}: rows {rows_full}; cut by MAX_LEN: {sum(map(len, cut.values()))}")

    train = frames["train"]
    hp = cfg["HPARAMS"]
    if pilot:
        pc = cfg["PILOT"]
        train = train.sample(n=max(1, round(pc["train_fraction"] * len(train))), random_state=seed)
        train = train.reset_index(drop=True)
        for s, n in pc["rehearsal"].items():
            f = frames[s]
            frames[s] = f.sample(n=min(n, len(f)), random_state=seed).sort_index().reset_index(drop=True)
    lengths = seq_lengths(train, qs)
    epochs = 1 if pilot else int(cfg["EPOCHS"])
    per_rank = len(bucket_batches(lengths, hp["micro_batch"], np.random.default_rng(0))) // d.world
    if pilot:
        per_rank = min(per_rank, int(cfg["PILOT"]["steps"]))
    n_updates = epochs * math.ceil(per_rank / hp["grad_accum"])
    trainer = Trainer(model, cfg, d, n_updates)

    # Memory probe: the longest micro-batch, forward and backward, no update.
    probe = np.argsort(-lengths, kind="stable")[: hp["micro_batch"]]
    trainer.net.train()
    loss = forward(trainer.net, encode_batch(train, probe, qs, tok, cfg), d, cfg).logsumexp(-1).mean()
    trainer.scaler.scale(loss).backward()
    trainer.opt.zero_grad(set_to_none=True)
    torch.manual_seed(seed + 1000 * d.rank)
    probe_gb = peak_gb(d)
    log(d, f"{tag}: memory probe at {int(lengths[probe].max())} tokens OK, peak {probe_gb} GB")

    va = frames["val_a"]
    t0 = time.time()
    n_probe = min(len(va), 64 * d.world)
    infer(model, va.iloc[:n_probe].reset_index(drop=True), qs, tok, cfg, d)
    eval_rate = n_probe / max(1e-6, time.time() - t0)
    n_tail = len(frames["val_a"]) + len(frames["val_b"]) + len(frames["test"])
    inferred, infer_time = 0, 0.0

    setup = {
        "notebook_to_process_s": round(t_start - float(cfg["NOTEBOOK_START"]), 1),
        "process_to_training_s": round(time.time() - t_start, 1),
    }
    history: list[dict[str, Any]] = []
    best: dict[str, Any] = {"loss": float("inf"), "epoch": None}
    train_seq, train_time = 0, 0.0
    steps: list[tuple[int, float]] = []  # (sequences on this rank, seconds) per micro-batch
    stopped_by_time = False
    for epoch in range(epochs):
        batches = bucket_batches(lengths, hp["micro_batch"], np.random.default_rng([seed, epoch]))
        batches = shard(batches, d.rank, d.world)[:per_rank]
        sigma = sigma_at(epoch, epochs, hp["sigma_start"], hp["sigma_end"])
        t_ep, seen, losses = time.time(), 0, []
        state: dict[str, float] = {"i": 0, "eval_rate": eval_rate}

        def stop(epoch_start: float = t_ep, nb: int = len(batches), st: dict[str, float] = state) -> bool:
            done = max(1.0, st["i"])
            left = (nb - done) * (time.time() - epoch_start) / done
            late = time.time() + left + n_tail / max(st["eval_rate"], 1e-6) + 600.0 > deadline
            flag = torch.tensor([1.0 if late else 0.0], device=d.device)
            if d.world > 1:
                dist.all_reduce(flag, op=dist.ReduceOp.MAX)
            return bool(flag.item() > 0)

        t_step = time.time()
        for i, lv in enumerate(trainer.step_batches(train, batches, qs, tok, sigma, stop)):
            now = time.time()
            steps.append((len(batches[i]), now - t_step))
            t_step = now
            state["i"] = i + 1
            losses.append(lv)
            seen += len(batches[i])
            if d.main and (i + 1) % 100 == 0:
                rate = seen * d.world / (now - t_ep)
                log(
                    d,
                    f"{tag}: epoch {epoch + 1} step {i + 1}/{len(batches)} "
                    f"loss {np.mean(losses[-100:]):.4f} {rate:.1f} seq/s",
                )
        stopped_by_time = int(state["i"]) < len(batches)
        ep_time = time.time() - t_ep
        train_seq += seen * d.world
        train_time += ep_time
        entry = {
            "epoch": epoch + 1,
            "train_loss": float(np.mean(losses)) if losses else None,
            "micro_batches": int(state["i"]),
            "of": len(batches),
            "train_s": round(ep_time, 1),
        }
        history.append(entry)
        if pilot and not rehearse:
            break
        t_ev = time.time()
        val_logits = infer(model, frames["val_a"], qs, tok, cfg, d)
        ev_time = time.time() - t_ev
        eval_rate = len(frames["val_a"]) / max(ev_time, 1e-6)
        inferred, infer_time = inferred + len(frames["val_a"]), infer_time + ev_time
        vl = val_loss(frames["val_a"], val_logits)
        entry.update({"val_a_loss": vl, "val_a_eval_s": round(ev_time, 1)})
        log(d, f"{tag}: epoch {epoch + 1} val-A loss {vl:.5f} ({ep_time / 60:.1f} min of training)")
        if vl < best["loss"]:
            best = {
                "loss": vl,
                "epoch": epoch + 1,
                "logits": val_logits,
                "state": {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()},
            }
            if d.main and not pilot:
                extra = {"max_len": cfg["MAX_LEN"], "head_max_len": cfg["HEAD_MAX_LEN"], "fine_tuned": True}
                save_ckpt(model, tok, meta["model_cfg"], out / "ckpt", extra)
            d.barrier()
        elif not pilot:
            break  # early stopping on the val-A loss (patience 0)
        if stopped_by_time:
            break

    warm = 10 if len(steps) > 20 else 0
    steady = steps[warm:]
    throughput = {
        "train_seq_per_s": train_seq / max(train_time, 1e-6),
        "train_seq_per_s_steady": d.world * sum(n for n, _ in steady) / max(sum(t for _, t in steady), 1e-6),
        "micro_batch_s_median": float(np.median([t for _, t in steady])) if steady else None,
        "eval_seq_per_s_probe": eval_rate,
        "train_s": round(train_time, 1),
        **setup,
    }
    files: dict[str, str] = {}
    cal: dict[str, Any] | None = None
    if rehearse:
        if best["epoch"] != history[-1]["epoch"]:
            model.load_state_dict(best["state"])
        preds = {"val_a": best["logits"]}
        t_inf = time.time()
        for s in ("val_b", "test"):
            preds[s] = infer(model, frames[s], qs, tok, cfg, d)
        inf_time = time.time() - t_inf
        inferred, infer_time = inferred + len(frames["val_b"]) + len(frames["test"]), infer_time + inf_time
        throughput.update(
            {"eval_seq_per_s": inferred / max(infer_time, 1e-6), "inference_s": round(inf_time, 1)}
        )
        if d.main:
            cal = calibrate(
                frames["val_a"], preds["val_a"], int(cfg["ECE_BINS"]), {q: v["t"] for q, v in qs.q.items()}
            )
            temps = {q: h["temperature"] for q, h in cal["heads"].items()}
            for s, z in preds.items():
                path = out / f"{PREFIX}{tag}_pred_{s}.arrow"
                write_preds(path, frames[s], z, temps)
                files[path.name] = sha256_file(path)
            if not pilot:
                ck_path = out / "ckpt" / "rl_agent_config.json"
                ck = json.loads(ck_path.read_text(encoding="utf-8"))
                ck.update(
                    {
                        "na08_temperatures": temps,
                        "na08_run": tag,
                        "na08_note": "apply na08_temperatures per question_id; laya's temperature is neutral",
                    }
                )
                ck_path.write_text(json.dumps(ck, indent=2), encoding="utf-8")
            cal_path = out / f"{PREFIX}{tag}_calibration.json"
            cal_path.write_text(json.dumps(cal, indent=2), encoding="utf-8")
            files[cal_path.name] = sha256_file(cal_path)
    throughput["wall_s"] = round(time.time() - t_start, 1)
    if d.main:
        rec = {
            "chunk": "NA-08",
            "run_name": cfg["RUN_NAME"],
            "tag": tag,
            "mode": cfg["MODE"],
            "rehearse": rehearse,
            "model": meta["provenance"],
            "seed": seed,
            "shuffle_labels": bool(cfg["SHUFFLE_LABELS"]),
            "shuffle_seed": int(cfg["SHUFFLE_SEED"]) if cfg["SHUFFLE_LABELS"] else None,
            "epochs_max": epochs,
            "epochs_run": len(history),
            "best_epoch": best["epoch"],
            "history": history,
            "stopped_by_time_budget": stopped_by_time,
            "early_stopping": {
                "split": "val_a",
                "metric": "mean cross-entropy",
                "rows": "labelled, outside the embargo",
            },
            "temperature_fit": None
            if cal is None
            else {
                "split": "val_a",
                "per": "head (question type, option count)",
                "fit_sessions": cal["fit_sessions"],
            },
            "labels_read": {"train": True, "val_a": True, "val_b": False, "test": False},
            "max_len": cfg["MAX_LEN"],
            "head_max_len": cfg["HEAD_MAX_LEN"],
            "head_tokens": {q: h - 3 for q, h in qs.head.items()},
            "states_cut": cut,
            "rows_full": rows_full,
            "rows_used": {"train": len(train), **{s: len(frames[s]) for s in ("val_a", "val_b", "test")}},
            "questions_by_source": cfg["QUESTIONS_BY_SOURCE"],
            "train_variants": cfg["TRAIN_VARIANTS"],
            "hparams": hp,
            "optimizer_updates": trainer.updates,
            "throughput": throughput,
            "peak_gpu_gb": peak_gb(d),
            "probe_peak_gpu_gb": probe_gb,
            "gpu": gpus(),
            "world_size": d.world,
            "device": str(d.device),
            "versions": versions(),
            "dataset": cfg["DATASET_CHECK"],
            "program_sha256": cfg.get("PROGRAM_SHA256"),
            "hub_push": False,
            "outputs": files,
        }
        path = out / f"{PREFIX}{tag}_run_record.json"
        path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        log(d, f"{tag}: done; best epoch {best['epoch']}; {throughput}")
    d.barrier()
    d.close()


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
