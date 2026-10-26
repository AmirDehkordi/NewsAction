"""The throughput pilot and the Kaggle quota plan (PRD NA-08 S4) → ``artifacts/NA-08/throughput.json``.

The pilot kernel (``kaggle.runs`` ``pilot``) runs one ``torchrun`` per launch of ``kaggle.pilot.launches``:
each trains a 5% subsample of train for a fixed number of micro-batches per GPU and measures the steady
training rate (sequences per second over both GPUs, after 10 warm-up micro-batches), the inference rate and
the peak GPU memory; the rehearsing launches also run the whole output path on small val-A / val-B / test
subsets, which ``import_preds.verify_run`` checks like a real run. An optional launch that fails (for
example out of memory) leaves ``na08_<tag>_failed.json``.

From the measured rates and the full row counts the plan projects, per training run: the setup (notebook
and process), each epoch (train + val-A evaluation + checkpoint) and the final inference (val-B, test).
The number of epochs is the largest ≤ ``model.max_epochs`` that fits ``model.time_budget_hours``. Options
follow the PRD's reduction order (anchor seeds → 1; MAX_LEN 768; epochs 2). MAX_LEN 768 is not available:
it would cut 27% of Call B and 4% of Call A D0 states, which the operator ruled out (NA-04 owner decision
2). An option is ``fits_week`` if its GPU-hours fit one week's quota.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Final

from newsaction.paths import Layout, resolve_layout
from newsaction.train import ARTIFACTS_SUBDIR, PREDICTIONS_DIR, TrainingConfig, load_training_config
from newsaction.train.import_preds import PREFIX, RunImportError, read_json, verify_record, verify_run

THROUGHPUT_FILE: Final = "throughput.json"
CKPT_SAVE_S: Final = 60.0  # writing the fp32 checkpoint after an improving epoch (not measured by the pilot)
OUTPUT_S: Final = 120.0  # temperature fit, prediction files, run record


def pilot_spec(cfg: TrainingConfig) -> Any:
    specs = [r for r in cfg.kaggle.runs if r.mode == "pilot"]
    if len(specs) != 1:
        raise RunImportError("exactly one pilot run must be planned")
    return specs[0]


def read_pilot(run_dir: Path, cfg: TrainingConfig, layout: Layout | None = None) -> dict[str, Any]:
    """Per launch: its status and the measured rates (verified run records)."""
    spec = pilot_spec(cfg)
    out: dict[str, Any] = {}
    for launch in cfg.kaggle.pilot.launches:
        tag = f"{spec.name}-{launch.name}"
        failed = run_dir / f"{PREFIX}{tag}_failed.json"
        if failed.is_file():
            if launch.required:
                raise RunImportError(f"required pilot launch {tag} failed")
            out[launch.name] = {"status": "failed", **read_json(failed)}
            continue
        if launch.rehearse:
            rec, _cal, preds = verify_run(run_dir, spec, tag, cfg, layout, subset=True)
            rehearsal = {s: len(p) for s, p in preds.items()}
        else:
            rec = read_json(run_dir / f"{PREFIX}{tag}_run_record.json")
            verify_record(rec, spec, cfg, layout)
            rehearsal = {}
        if rec["model"]["init"] != launch.init:
            raise RunImportError(f"{tag}: init {rec['model']['init']} != {launch.init}")
        tp = rec["throughput"]
        out[launch.name] = {
            "status": "ok",
            "init": launch.init,
            "hparams": {k: rec["hparams"][k] for k in ("micro_batch", "grad_accum", "grad_checkpointing")},
            "train_seq_per_s": tp["train_seq_per_s_steady"],
            "micro_batch_s_median": tp["micro_batch_s_median"],
            "eval_seq_per_s": tp.get("eval_seq_per_s", tp["eval_seq_per_s_probe"]),
            "notebook_to_process_s": tp["notebook_to_process_s"],
            "process_to_training_s": tp["process_to_training_s"],
            "peak_gpu_gb": rec["peak_gpu_gb"],
            "probe_peak_gpu_gb": rec["probe_peak_gpu_gb"],
            "gpu": rec["gpu"],
            "versions": rec["versions"],
            "rows_full": rec["rows_full"],
            "rehearsal_rows": rehearsal,
            "states_cut": {s: len(v) for s, v in rec["states_cut"].items()},
        }
    return out


def run_hours(rates: dict[str, Any], rows: dict[str, int], epochs: int) -> float:
    """Projected session hours of one training run with ``epochs`` epochs."""
    train_rate, eval_rate = rates["train_seq_per_s"], rates["eval_seq_per_s"]
    setup = rates["notebook_to_process_s"] + rates["process_to_training_s"]
    epoch = rows["train"] / train_rate + rows["val_a"] / eval_rate + CKPT_SAVE_S
    final = (rows["val_b"] + rows["test"]) / eval_rate + OUTPUT_S
    return float((setup + epochs * epoch + final) / 3600.0)


def max_epochs(rates: dict[str, Any], rows: dict[str, int], cfg: TrainingConfig, cap: int) -> int:
    fits = [e for e in range(1, cap + 1) if run_hours(rates, rows, e) <= cfg.model.time_budget_hours]
    return max(fits) if fits else 0


def options(
    rates: dict[str, Any], rows: dict[str, int], cfg: TrainingConfig, pilot_hours: float
) -> list[Any]:
    """The plan and its PRD reductions, with GPU-hours and weeks of quota."""
    seeds = list(cfg.model.seeds)
    week = cfg.kaggle.weekly_gpu_hours
    steps: list[tuple[str, int, int]] = [  # (name, anchor seeds, epoch cap)
        ("full", len(seeds), cfg.model.max_epochs),
        ("anchor seeds -> 1", 1, cfg.model.max_epochs),
        ("anchor seeds -> 1, epochs 2", 1, 2),
    ]
    out: list[Any] = []
    for name, n_anchor, cap in steps:
        e = max_epochs(rates, rows, cfg, cap)
        h_run = run_hours(rates, rows, e)
        h_shuffle = run_hours(rates, rows, 1)
        runs = (
            [("shuffle-s13", 1, h_shuffle)]
            + [(f"laya-s{s}", e, h_run) for s in seeds]
            + [(f"anchor-s{s}", e, h_run) for s in seeds[:n_anchor]]
            + [("repro-s13", e, h_run)]
        )
        total = pilot_hours + sum(h for _, _, h in runs)
        out.append(
            {
                "option": name,
                "epochs": e,
                "run_hours": round(h_run, 2),
                "runs": [{"run": r, "epochs": ep, "hours": round(h, 2)} for r, ep, h in runs],
                "gpu_hours": round(total, 1),
                "weeks": math.ceil(total / week),
                "fits_week": total <= week,
                "sessions_fit": e >= 1 and h_run <= cfg.kaggle.session_hours,
            }
        )
    out.insert(
        2,
        {
            "option": "MAX_LEN 768",
            "available": False,
            "reason": "would cut states (27% of Call B, 4% of Call A D0); the operator's decision on NA-04 "
            "owner decision 2: no state is cut",
        },
    )
    return out


def run(layout: Layout | None = None, cfg: TrainingConfig | None = None) -> dict[str, Any]:
    """Verify the downloaded pilot and write artifacts/NA-08/throughput.json."""
    lay = resolve_layout(layout)
    cfg = load_training_config() if cfg is None else cfg
    spec = pilot_spec(cfg)
    pilot = read_pilot(lay.work / PREDICTIONS_DIR / spec.name, cfg, lay)
    ok = {n: p for n, p in pilot.items() if p["status"] == "ok"}
    main = ok[next(x.name for x in cfg.kaggle.pilot.launches if x.required and x.init == "laya")]
    fastest = max((p for p in ok.values() if p["init"] == "laya"), key=lambda p: p["train_seq_per_s"])
    rows = main["rows_full"]
    pilot_hours = max(p["notebook_to_process_s"] for p in ok.values()) / 3600.0 + 0.5
    result = {
        "chunk": "NA-08",
        "pilot": pilot,
        "rows": rows,
        "chosen_hparams": fastest["hparams"],
        "projection": {
            "train_seq_per_s": fastest["train_seq_per_s"],
            "eval_seq_per_s": fastest["eval_seq_per_s"],
            "epoch_hours": round(rows["train"] / fastest["train_seq_per_s"] / 3600.0, 2),
            "val_a_eval_hours": round(rows["val_a"] / fastest["eval_seq_per_s"] / 3600.0, 2),
            "final_inference_hours": round(
                (rows["val_b"] + rows["test"]) / fastest["eval_seq_per_s"] / 3600.0, 2
            ),
        },
        "options": options(fastest, rows, cfg, pilot_hours),
        "quota": {
            "session_hours": cfg.kaggle.session_hours,
            "weekly_gpu_hours": cfg.kaggle.weekly_gpu_hours,
            "time_budget_hours": cfg.model.time_budget_hours,
        },
        "assumption": "a GPU T4 x2 session consumes weekly quota at the session's wall-clock rate",
    }
    path = lay.artifacts / ARTIFACTS_SUBDIR / THROUGHPUT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
