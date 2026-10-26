"""Import the Kaggle runs: verify, map back to events, ensemble (PRD NA-08 S7, AC1, AC4, AC6).

A run's outputs are downloaded into ``work/kaggle/predictions/<run>/`` (runbook:
``kaggle kernels output <kernel> -p work/kaggle/predictions/<run> --file-pattern na08_``). ``verify_run``
checks, before anything is read:

- every ``na08_*`` file against the notebook's own ``na08_outputs.json`` and the run record's sha256s;
- the run record: this run (name, init, seed, shuffle flag), the pinned revision and weights sha256, the
  program sha256 equal to the committed ``notebook/train_ddp.py``, the dataset files' sha256 equal to the
  local ``sha256_manifest.json`` (the uploaded dataset is the local one, AC1), early stopping and
  temperatures on val-A, no label read from val-B or test, no Hub push (AC6), the head and sequence lengths,
  the states cut equal to the export's count;
- each prediction file: exactly the expected example ids, one row each; k equal to the question's option
  count; probabilities that sum to 1 and equal softmax(logits / T) with the run's val-A temperature.

``run`` writes one registered file per training run (``predictions/runs/<run>.parquet``: every split, logits
and calibrated probabilities) and, per model, the 3-seed ensemble (the mean of the seeds' calibrated
probabilities, PREREG §9.1) in the **common prediction schema**: one row per (event, call, question) with
``event_id``, ``company_id``, ``session``, ``split``, ``window``, ``decision_point``, ``call``, ``question``,
``model``, ``n_seeds``, ``runs``, ``k``, ``probabilities`` (options in Laya's order: score levels low to high,
Q6 reverse / stall / continue) and the derived columns (``derive``). Val-B and test predictions are stored,
never evaluated (NA-11 does).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.paths import Layout, resolve_layout
from newsaction.train import (
    DATASET_DIR,
    MODEL_NAMES,
    PREDICTIONS_DIR,
    PRODUCER,
    RUNS_DIR,
    RunSpec,
    TrainingConfig,
    load_training_config,
)
from newsaction.train.kaggle_export import INFO_FILE, MANIFEST_FILE
from newsaction.train.nbbuild import PROGRAM

PREFIX: Final = "na08_"
SPLIT_FILES: Final = {"val_a": "val_a", "val_b": "val_b", "test": "test_callA"}
PRED_SPLITS: Final = ("val_a", "val_b", "test")
ENSEMBLE_FILES: Final = {"val_a": "val_a", "val_b": "val_b", "test": "test_callA"}
PROB_TOL: Final = 1e-4
TEMP_TOL: Final = 2e-4
DERIVED: Final = (
    "n_hat",
    "e_abs_n",
    "mag_mean",
    "p_mag_ge1",
    "p_reverse",
    "p_stall",
    "p_continue",
    "c_cont",
    "j_cont",
    "w_cont",
    "confidence",
)


class RunImportError(ValueError):
    """A downloaded run fails verification (its files, its record or its predictions)."""


# --- verification -----------------------------------------------------------------------------------


def read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RunImportError(f"{path.name} is not a JSON object")
    return obj


def check_outputs(run_dir: Path, tag: str) -> dict[str, str]:
    """sha256 of every listed output equals its file (na08_outputs.json and the run record)."""
    listed = read_json(run_dir / f"{PREFIX}outputs.json")
    rec = read_json(run_dir / f"{PREFIX}{tag}_run_record.json")
    for name, sha in {**listed, **rec["outputs"]}.items():
        p = run_dir / name
        if not p.is_file():
            raise RunImportError(f"{tag}: {name} was not downloaded")
        if io.sha256_file(p) != sha:
            raise RunImportError(f"{tag}: {name} sha256 differs from the notebook's record")
    return {str(k): str(v) for k, v in listed.items()}


def expected_model(rec: Mapping[str, Any], cfg: TrainingConfig) -> None:
    m = rec["model"]
    spec = cfg.model.init_spec(m["init"])
    for key in ("repo", "revision", "weights_sha256"):
        if m.get(key) != getattr(spec, key):
            raise RunImportError(f"{rec['tag']}: {key} {m.get(key)!r} != pinned {getattr(spec, key)!r}")
    if not m.get("weights_verified"):
        raise RunImportError(f"{rec['tag']}: weights were not verified")
    if m["head_fresh"] != (m["init"] == "modernbert"):
        raise RunImportError(f"{rec['tag']}: the anchor's head must be fresh, Laya's must not")


def verify_record(
    rec: Mapping[str, Any], spec: RunSpec, cfg: TrainingConfig, layout: Layout | None = None
) -> None:
    """The run record describes this planned run, on this dataset and program, with val-A-only fitting."""
    lay = resolve_layout(layout)
    tag = rec["tag"]
    if rec.get("chunk") != "NA-08" or rec.get("run_name") != spec.name or rec.get("mode") != spec.mode:
        raise RunImportError(f"{tag}: the record is not of planned run {spec.name} ({spec.mode})")
    if rec.get("hub_push") is not False:
        raise RunImportError(f"{tag}: hub_push is not false")
    if rec["labels_read"] != {"train": True, "val_a": True, "val_b": False, "test": False}:
        raise RunImportError(f"{tag}: labels read {rec['labels_read']}")
    if rec["early_stopping"]["split"] != "val_a":
        raise RunImportError(f"{tag}: early stopping not on val-A")
    if rec.get("temperature_fit") is not None and rec["temperature_fit"]["split"] != "val_a":
        raise RunImportError(f"{tag}: temperatures not fit on val-A")
    if spec.mode == "train":
        if rec["model"]["init"] != spec.init or rec["seed"] != spec.seed:
            raise RunImportError(f"{tag}: init/seed {rec['model']['init']}/{rec['seed']} != planned")
        if bool(rec["shuffle_labels"]) != spec.shuffle_labels:
            raise RunImportError(f"{tag}: shuffle_labels {rec['shuffle_labels']} != planned")
    expected_model(rec, cfg)
    if rec.get("program_sha256") != io.sha256_file(PROGRAM):
        raise RunImportError(f"{tag}: the program run is not the committed notebook/train_ddp.py")
    ds_dir = lay.work / DATASET_DIR
    manifest = read_json(ds_dir / MANIFEST_FILE)
    local = {n: e["sha256"] for n, e in manifest["files"].items()}
    if rec["dataset"]["files"] != local:
        raise RunImportError(f"{tag}: the dataset run on Kaggle differs from the local export (AC1)")
    if rec["dataset"]["manifest_sha256"] != io.sha256_file(ds_dir / MANIFEST_FILE):
        raise RunImportError(f"{tag}: the dataset manifest differs from the local one")
    if rec["dataset"]["label_columns"] != {"val_b": False, "test": False}:
        raise RunImportError(f"{tag}: a val-B or test file had a label column")
    info = read_json(ds_dir / INFO_FILE)
    if rec["max_len"] != cfg.model.max_len or rec["head_max_len"] != cfg.model.head_max_len:
        raise RunImportError(f"{tag}: max_len / head_max_len differ from configs/training.yaml")
    heads = {q: v["head_tokens"] for q, v in info["questions"].items() if q in rec["head_tokens"]}
    if rec["head_tokens"] != heads:
        raise RunImportError(f"{tag}: head lengths {rec['head_tokens']} != the export's {heads}")
    cut_local = set(info["truncation"]["cut_example_ids"])
    cut_run = {e for ids in rec["states_cut"].values() for e in ids}
    if not cut_run <= cut_local:
        raise RunImportError(
            f"{tag}: the run cut states the export did not count: {sorted(cut_run - cut_local)}"
        )


def expected_ids(split: str, rec: Mapping[str, Any], layout: Layout | None = None) -> pd.DataFrame:
    """The dataset rows the run must have predicted for ``split`` (its sources, questions; ``full``)."""
    lay = resolve_layout(layout)
    cols = ["example_id", "event_id", "call", "window", "variant", "question_id"]
    df = io.read_parquet(f"{DATASET_DIR}/{SPLIT_FILES[split]}.parquet", columns=cols, layout=lay)
    allowed = rec["questions_by_source"]
    src = df["call"] + "_" + df["window"]
    keep = [q in allowed.get(s, []) for s, q in zip(src, df["question_id"], strict=True)]
    return df[np.asarray(keep, dtype=bool) & (df["variant"] == "full").to_numpy()].reset_index(drop=True)


def read_preds(path: Path) -> pd.DataFrame:
    import pyarrow.feather as feather

    t = feather.read_table(str(path))
    df: pd.DataFrame = t.to_pandas()
    for col in ("logits", "probs", "probs_raw"):
        df[col] = pd.Series([np.asarray(v, dtype=np.float64) for v in df[col]], index=df.index, dtype=object)
    return df


def softmax(z: np.ndarray, t: float) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64) / t
    e = np.exp(z - z.max())
    return np.asarray(e / e.sum())


def check_preds(
    df: pd.DataFrame, expected: pd.DataFrame, temps: Mapping[str, float], k_of: Mapping[str, int], tag: str
) -> None:
    if not df["example_id"].is_unique:
        raise RunImportError(f"{tag}: duplicate example ids")
    got, want = set(df["example_id"]), set(expected["example_id"])
    if got != want:
        raise RunImportError(f"{tag}: {len(want - got)} expected rows missing, {len(got - want)} unexpected")
    q = df["example_id"].map(dict(zip(expected["example_id"], expected["question_id"], strict=True)))
    if bool((q != df["question_id"]).any()):
        raise RunImportError(f"{tag}: question ids differ from the dataset's")
    k = df["question_id"].map(k_of)
    lens = df["probs"].map(len)
    if bool((df["k"] != k).any()) or bool((lens != k).any()) or bool((df["logits"].map(len) != k).any()):
        raise RunImportError(f"{tag}: option counts differ from the questions'")
    sums = df["probs"].map(np.sum)
    if bool(((sums - 1.0).abs() > PROB_TOL).any()):
        raise RunImportError(f"{tag}: probabilities do not sum to 1")
    redo = [softmax(z, temps[qq]) for z, qq in zip(df["logits"], df["question_id"], strict=True)]
    worst = max(float(np.abs(a - b).max()) for a, b in zip(redo, df["probs"], strict=True))
    if worst > TEMP_TOL:
        raise RunImportError(f"{tag}: probabilities differ from softmax(logits / T) by {worst:.2e}")


def verify_run(
    run_dir: Path,
    spec: RunSpec,
    tag: str,
    cfg: TrainingConfig,
    layout: Layout | None = None,
    subset: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, pd.DataFrame]]:
    """(run record, calibration, predictions per split) of a verified downloaded run.

    ``subset``: the pilot's rehearsal predicts a sample of each split, so its ids need only be in the dataset.
    """
    check_outputs(run_dir, tag)
    rec = read_json(run_dir / f"{PREFIX}{tag}_run_record.json")
    if rec["tag"] != tag:
        raise RunImportError(f"{run_dir.name}: record tag {rec['tag']!r} != {tag!r}")
    verify_record(rec, spec, cfg, layout)
    cal = read_json(run_dir / f"{PREFIX}{tag}_calibration.json")
    if cal["split"] != "val_a":
        raise RunImportError(f"{tag}: calibration not on val-A")
    temps = {q: float(h["temperature"]) for q, h in cal["heads"].items()}
    info = read_json(resolve_layout(layout).work / DATASET_DIR / INFO_FILE)
    k_of = {q: int(v["k"]) for q, v in info["questions"].items()}
    preds: dict[str, pd.DataFrame] = {}
    for split in PRED_SPLITS:
        df = read_preds(run_dir / f"{PREFIX}{tag}_pred_{split}.arrow")
        exp = expected_ids(split, rec, layout)
        if subset:
            exp = exp[exp["example_id"].isin(set(df["example_id"]))]
        check_preds(df, exp, temps, k_of, f"{tag}/{split}")
        meta = exp.set_index("example_id")[["event_id", "call", "window"]]
        df = df.join(meta, on="example_id")
        df["split"] = split
        preds[split] = df
    return rec, cal, preds


# --- derived columns and the common schema ------------------------------------------------------------


def derive(question: str, probs: Sequence[np.ndarray], cfg: TrainingConfig | None = None) -> pd.DataFrame:
    """Derived columns of one question's probability rows (NaN where a column does not apply)."""
    c = (load_training_config() if cfg is None else cfg).derived
    p = np.stack(probs) if len(probs) else np.zeros((0, 1))
    out = pd.DataFrame({k: np.full(len(p), np.nan) for k in DERIVED})
    if len(p):
        out["confidence"] = p.max(axis=1)
    if question == "react" and len(p):
        m = np.asarray(c.react_midpoints)
        out["n_hat"] = p @ m  # PREREG §7: N̂ = Σ p_k m_k
        out["e_abs_n"] = p @ np.abs(m)  # E|N̂| = Σ p_k |m_k|
    elif question == "mag" and len(p):
        out["mag_mean"] = p @ np.asarray(c.mag_midpoints)
        out["p_mag_ge1"] = p[:, 2:].sum(axis=1)  # P(|z_cc,t| >= 1)
    elif question == "cont" and len(p):
        out["p_reverse"], out["p_stall"], out["p_continue"] = p[:, 0], p[:, 1], p[:, 2]
        out["c_cont"] = p[:, 2] - p[:, 0]  # PREREG §7: C = P(continue) − P(reverse)
        out["j_cont"] = out["c_cont"]  # J analogue: continuation = an under-reaction
        out["w_cont"] = p[:, 0]  # W analogue: the move reverses
    return out


def common_schema(
    preds: pd.DataFrame,
    model: str,
    runs: Sequence[str],
    keys: pd.DataFrame,
    cfg: TrainingConfig | None = None,
) -> pd.DataFrame:
    """Event-level rows (one per event, call, question) with derived columns; ``keys`` maps events."""
    parts = []
    for q, g in preds.groupby("question_id", sort=True):
        g = g.reset_index(drop=True)
        d = derive(str(q), list(g["probabilities"]), cfg)
        parts.append(pd.concat([g, d], axis=1))
    df = pd.concat(parts, ignore_index=True).rename(columns={"question_id": "question"})
    df = df.merge(keys, on="event_id", how="left", validate="many_to_one")
    if bool(df["session"].isna().any()):
        raise RunImportError(f"{model}: predictions for events that are not in the state files")
    df["decision_point"] = df["window"].map({"W0": "D0", "W2": "D2"})
    df["model"] = model
    df["runs"] = ",".join(runs)
    df["n_seeds"] = len(runs)
    df["probabilities"] = [np.asarray(p, dtype=np.float64).tolist() for p in df["probabilities"]]
    cols = [
        "event_id",
        "company_id",
        "session",
        "split",
        "window",
        "decision_point",
        "call",
        "question",
        "model",
        "n_seeds",
        "runs",
        "k",
        "probabilities",
        *DERIVED,
    ]
    df["k"] = df["k"].astype("int8")
    return (
        df[cols]
        .sort_values(["session", "event_id", "call", "question"], kind="mergesort")
        .reset_index(drop=True)
    )


def event_keys(cfg: TrainingConfig, layout: Layout | None = None) -> pd.DataFrame:
    parts = [
        io.read_parquet(p, columns=["event_id", "company_id", "session"], layout=layout)
        for p in cfg.states.values()
    ]
    return pd.concat(parts, ignore_index=True).drop_duplicates("event_id").reset_index(drop=True)


def run_frame(rec: Mapping[str, Any], preds: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """One run's predictions, every split, as a registered long frame."""
    df = pd.concat(list(preds.values()), ignore_index=True)
    df["run"] = rec["run_name"]
    df["init"] = rec["model"]["init"]
    df["seed"] = int(rec["seed"])
    df["logits"] = [z.tolist() for z in df["logits"]]
    df["probabilities"] = [p.tolist() for p in df["probs"]]
    cols = [
        "run",
        "init",
        "seed",
        "split",
        "example_id",
        "event_id",
        "call",
        "window",
        "question_id",
        "k",
        "logits",
        "probabilities",
    ]
    return df[cols].reset_index(drop=True)


def ensemble(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Mean of the runs' calibrated probabilities per (split, event, call, question); every run must agree."""
    key = ["split", "event_id", "call", "window", "question_id"]
    base = frames[0][[*key, "k"]].sort_values(key).reset_index(drop=True)
    stacks = []
    for f in frames:
        g = f.sort_values(key).reset_index(drop=True)
        if not g[key].equals(base[key]):
            raise RunImportError("the seeds' runs cover different examples")
        stacks.append([np.asarray(p, dtype=np.float64) for p in g["probabilities"]])
    mean = [np.mean([s[i] for s in stacks], axis=0) for i in range(len(base))]
    out = base.copy()
    out["probabilities"] = pd.Series(mean, index=out.index, dtype=object)
    return out


def ensemble_runs(cfg: TrainingConfig) -> dict[str, list[RunSpec]]:
    """The seed runs of each reported model (the controls are not part of an ensemble)."""
    controls = {cfg.controls.shuffle_run, cfg.controls.repro_runs[1]}
    out: dict[str, list[RunSpec]] = {name: [] for name in MODEL_NAMES.values()}
    for r in cfg.kaggle.runs:
        if r.mode == "train" and r.name not in controls and not r.shuffle_labels and r.init is not None:
            out[MODEL_NAMES[r.init]].append(r)
    return out


def run(layout: Layout | None = None, cfg: TrainingConfig | None = None) -> dict[str, Any]:
    """Verify every downloaded training run, register it, and write the per-model ensembles."""
    lay = resolve_layout(layout)
    cfg = load_training_config() if cfg is None else cfg
    base = lay.work / PREDICTIONS_DIR
    summary: dict[str, Any] = {"runs": {}, "models": {}}
    frames: dict[str, pd.DataFrame] = {}
    for spec in cfg.kaggle.runs:
        if spec.mode != "train" or not (base / spec.name).is_dir():
            continue
        rec, cal, preds = verify_run(base / spec.name, spec, spec.name, cfg, lay)
        frame = run_frame(rec, preds)
        io.write_parquet(
            frame,
            f"{RUNS_DIR}/{spec.name}.parquet",
            producer=PRODUCER,
            description=f"NA-08 S7: run {spec.name} ({rec['model']['init']}, seed {rec['seed']}): logits and "
            "val-A-calibrated probabilities per example (val-A, val-B, test); verified run record",
            layout=lay,
        )
        frames[spec.name] = frame
        summary["runs"][spec.name] = {
            "best_epoch": rec["best_epoch"],
            "epochs_run": rec["epochs_run"],
            "temperatures": {q: h["temperature"] for q, h in cal["heads"].items()},
        }
    keys = event_keys(cfg, lay)
    for model, specs in ensemble_runs(cfg).items():
        have = [s.name for s in specs if s.name in frames]
        if not have:
            continue
        mean = ensemble([frames[n] for n in have])
        for split, fname in ENSEMBLE_FILES.items():
            part = common_schema(mean[mean["split"] == split], model, have, keys, cfg)
            io.write_parquet(
                part,
                f"{PREDICTIONS_DIR}/{model}_{fname}.parquet",
                producer=PRODUCER,
                description=f"NA-08 S7: {model} {len(have)}-seed ensemble ({', '.join(have)}) on {split}, "
                "common prediction schema (mean of calibrated probabilities; derived N̂, E|N̂|, H-mag, C/J/W)",
                layout=lay,
            )
        summary["models"][model] = {"runs": have}
    return summary
