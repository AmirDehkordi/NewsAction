"""Controls (PRD NA-08 S5) and model cards (S8): ``artifacts/NA-08/{controls.json, model_card_*.md}``.

Every number here is computed on **val-A**, outside the first 5 sessions (PREREG §4.2), from the imported
predictions and the local labels (``metrics.require_val_a`` refuses anything else). Val-B and test
predictions are stored by ``import_preds`` and never evaluated in NA-08 (NA-11 does).

- **Signals and targets** (daily Spearman IC, Newey–West t, block-bootstrap 95% CI):
  Call A on D0, N̂ vs z_cc,t (the selection metric, PREREG §8.5) and vs e5 (the training target);
  Call A on D2 and Call B, N̂ vs e5; H-mag on D0, E[|z| level] vs |z_cc,t|; H-cont on Call B (|G| ≥ 0.5),
  C vs sign(G)·y2.
- **Calibration**: per head, ECE (15 bins) and NLL before (T = 1) and after the val-A temperature.
- **Controls** (PREREG §9.3): the shuffled-label run's D0 N̂ vs e5 must have |t| < 2; the rerun of Laya-Fin
  seed 13 must reproduce the D0 IC (vs z_cc,t and vs e5) within ±0.003.
- **Trials**: every evaluated variant (each run and each ensemble, on its primary metric) is logged in
  ``ledgers/trials.jsonl`` once (CLAUDE.md B10).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.config import load_splits
from newsaction.ledger import TRIALS, TrialLedger, TrialRecord, params_hash
from newsaction.paths import Layout, resolve_layout
from newsaction.train import (
    ARTIFACTS_SUBDIR,
    CHUNK,
    DATASET_DIR,
    LABELS,
    MODEL_NAMES,
    PREDICTIONS_DIR,
    RUNS_DIR,
    TrainingConfig,
    load_training_config,
    training_questions,
)
from newsaction.train.import_preds import PREFIX, common_schema, ensemble_runs, event_keys, read_json
from newsaction.train.kaggle_export import INFO_FILE, MANIFEST_FILE
from newsaction.train.metrics import calibration, ic_summary, require_val_a, softmax

CONTROLS_FILE: Final = "controls.json"
LABEL_COLUMNS: Final = (
    "company_id",
    "session",
    "embargo",
    "e5",
    "z_cc",
    "cont_x",
    "react_label",
    "mag_label",
    "cont_label",
)
LABEL_OF: Final = {"react": "react_label", "mag": "mag_label", "cont": "cont_label"}
# (name, source window/call, question, signal, target): the val-A ICs of a card
IC_SPECS: Final = (
    ("D0 Call A: N̂ vs z_cc,t", "W0", "A", "react", "n_hat", "z_cc"),
    ("D0 Call A: N̂ vs e5", "W0", "A", "react", "n_hat", "e5"),
    ("D2 Call A: N̂ vs e5", "W2", "A", "react", "n_hat", "e5"),
    ("D2 Call B: N̂ vs e5", "W2", "B", "react", "n_hat", "e5"),
    ("D0 Call A: H-mag E[level] vs |z_cc,t|", "W0", "A", "mag", "mag_mean", "abs_z_cc"),
    ("D2 Call B: C vs sign(G)·y2 (|G| ≥ 0.5)", "W2", "B", "cont", "c_cont", "cont_x"),
)
PRIMARY: Final = IC_SPECS[0]


# --- evaluation frames ------------------------------------------------------------------------------


def with_targets(pred: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Val-A rows outside the embargo, with their targets and labels (common prediction schema)."""
    v = pred[pred["split"] == "val_a"]
    lab = labels[list(LABEL_COLUMNS)]
    out = v.merge(lab, on=["company_id", "session"], how="left", validate="many_to_one")
    out = out[~out["embargo"].astype("boolean").fillna(True).astype(bool)].copy()
    out["abs_z_cc"] = out["z_cc"].abs()
    out["label"] = [r[LABEL_OF[q]] for q, r in zip(out["question"], out.to_dict("records"), strict=True)]
    require_val_a(out["split"])
    return out.reset_index(drop=True)


def ics(ev: pd.DataFrame, cfg: TrainingConfig, ci: bool = True) -> list[dict[str, Any]]:
    out = []
    for name, window, call, q, signal, target in IC_SPECS:
        sub = ev[(ev["window"] == window) & (ev["call"] == call) & (ev["question"] == q)]
        if q == "cont":
            sub = sub[sub["cont_label"].notna()]
        if sub.empty:
            continue
        out.append({"name": name, **ic_summary(sub, signal, target, cfg.evaluation, ci=ci)})
    return out


def run_eval(
    run: str, keys: pd.DataFrame, labels: pd.DataFrame, cfg: TrainingConfig, layout: Layout | None
) -> pd.DataFrame:
    """One run's val-A predictions in the common schema, with targets; also T = 1 probabilities."""
    f = io.read_parquet(f"{RUNS_DIR}/{run}.parquet", layout=layout)
    f = f[f["split"] == "val_a"].reset_index(drop=True)
    raw = {e: softmax(np.asarray(z)) for e, z in zip(f["example_id"], f["logits"], strict=True)}
    pred = common_schema(f.rename(columns={}), run, [run], keys, cfg)
    pred["probabilities_raw"] = [
        raw[e].tolist()
        for e in (
            f.set_index(["event_id", "call", "question_id"])["example_id"].reindex(
                list(zip(pred["event_id"], pred["call"], pred["question"], strict=True))
            )
        )
    ]
    return with_targets(pred, labels)


def head_calibration(ev: pd.DataFrame, cfg: TrainingConfig, raw: bool) -> dict[str, Any]:
    out = {}
    for q in sorted(ev["question"].unique()):
        sub = ev[(ev["question"] == q) & ev["label"].notna()]
        after = calibration(sub, cfg.evaluation)
        entry = {
            "n": after["n"],
            "ece_after": after["ece"],
            "nll_after": after["nll"],
            "accuracy": after["accuracy"],
        }
        if raw:
            before = calibration(sub, cfg.evaluation, prob_col="probabilities_raw")
            entry.update({"ece_before": before["ece"], "nll_before": before["nll"]})
        out[str(q)] = entry
    return out


# --- trials -----------------------------------------------------------------------------------------


def log_trial(
    name: str, params: Mapping[str, Any], metric: str, value: float | None, layout: Layout | None
) -> bool:
    """Append one val-A trial unless an identical record exists (deterministic reruns add nothing)."""
    rec = TrialRecord(
        chunk=CHUNK,
        kind="trained_model",
        name=name,
        params_hash=params_hash(dict(params)),
        split="val_a",
        metric=metric,
        value=None if value is None else float(value),
    )
    ledger = TrialLedger(resolve_layout(layout).ledgers / TRIALS)
    fields = rec.model_dump()
    if any(all(r.get(k) == v for k, v in fields.items()) for r in ledger.records()):
        return False
    ledger.log(rec)
    return True


# --- controls ---------------------------------------------------------------------------------------


def controls(
    cfg: TrainingConfig, keys: pd.DataFrame, labels: pd.DataFrame, layout: Layout | None
) -> dict[str, Any]:
    lay = resolve_layout(layout)
    c = cfg.controls

    def have(run: str) -> bool:
        return (lay.work / RUNS_DIR / f"{run}.parquet").is_file()

    out: dict[str, Any] = {"chunk": CHUNK, "split": "val_a", "embargo_excluded": True}
    if have(c.shuffle_run):
        ev = run_eval(c.shuffle_run, keys, labels, cfg, lay)
        d0 = ev[(ev["window"] == "W0") & (ev["call"] == "A") & (ev["question"] == "react")]
        e5 = ic_summary(d0, "n_hat", "e5", cfg.evaluation)
        zc = ic_summary(d0, "n_hat", "z_cc", cfg.evaluation)
        out["shuffled_label"] = {
            "run": c.shuffle_run,
            "rule": f"|NW t| of the val-A mean daily IC of N̂ vs e5 (D0) < {c.shuffle_t_max}",
            "ic_e5": e5,
            "ic_z_cc": zc,
            "pass": bool(abs(e5["nw_t"]) < c.shuffle_t_max),
            "all_heads": ics(ev, cfg, ci=False),  # reported, not part of the rule
        }
    else:
        out["shuffled_label"] = {"run": c.shuffle_run, "status": "not run"}
    a, b = c.repro_runs
    if have(a) and have(b):
        res = {}
        for r in (a, b):
            ev = run_eval(r, keys, labels, cfg, lay)
            d0 = ev[(ev["window"] == "W0") & (ev["call"] == "A") & (ev["question"] == "react")]
            res[r] = {t: ic_summary(d0, "n_hat", t, cfg.evaluation, ci=False)["ic"] for t in ("z_cc", "e5")}
        diff = {t: res[b][t] - res[a][t] for t in ("z_cc", "e5")}
        out["reproducibility"] = {
            "runs": [a, b],
            "rule": f"|Δ val-A D0 IC| ≤ {c.repro_ic_tol} for N̂ vs z_cc,t and vs e5",
            "ic": res,
            "diff": diff,
            "pass": bool(all(abs(v) <= c.repro_ic_tol for v in diff.values())),
        }
    else:
        out["reproducibility"] = {
            "runs": [a, b],
            "status": "not run (an operator-approved deferral is needed)",
        }
    return out


# --- cards ------------------------------------------------------------------------------------------


def _fmt(x: Any, nd: int = 4) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def card_text(model: str, ctx: Mapping[str, Any]) -> str:
    """The model card's markdown (``ctx`` from ``card_context``)."""
    cfg: TrainingConfig = ctx["cfg"]
    init = "laya" if model == "laya_fin" else "modernbert"
    spec = cfg.model.init_spec(init)  # type: ignore[arg-type]
    title = "Laya-Fin" if model == "laya_fin" else "ModernBERT-large anchor"
    q = training_questions(cfg)
    splits = load_splits().splits
    info = ctx["info"]
    lines = [f"# Model card: {title} (NewsAction NA-08)", ""]
    what = (
        "Laya's typed-decisions checkpoint (encoder and decision head) fine-tuned on the NewsAction "
        "finance questions; the primary trained decision model (PREREG §9.1)."
        if init == "laya"
        else "ModernBERT-large (Dec-2024 weights) with Laya's decision-head architecture, freshly "
        "initialised and trained with the identical recipe; the clean anchor of the headline-claim rule "
        "(PREREG §1.3, §9.2). No distillation from any vendor model; Laya's undisclosed training data "
        "plays no part."
    )
    rev = f"`{spec.repo}`" + (f", subfolder `{spec.subfolder}`" if spec.subfolder else "")
    tr, dates = info["truncation"], info["dates"]
    lines += [
        "| | |",
        "|---|---|",
        f"| Model | {what} |",
        f"| Init | {rev}, revision `{spec.revision}`, weights sha256 `{spec.weights_sha256}` "
        "(checked before loading) |",
        "| Architecture | ModernBERT-large encoder (fully fine-tuned) + decision head: 2 transformer "
        "layers and an option-marker scorer (Laya `DecisionModel`); the act head is frozen and unused |",
        f"| Reported model | the {ctx['n_seeds']}-seed ensemble (mean of calibrated probabilities) of "
        f"runs {', '.join(ctx['runs'])} |",
        "| Inputs | the NA-04 masked E3 states (PREREG §6.10–6.11), identical to the API models' states |",
        "| Outputs | probabilities per head; common prediction schema `work/kaggle/predictions/"
        f"{model}_{{val_a,val_b,test_callA}}.parquet` |",
        "",
        "## Heads",
        "",
        f'- **H-react** (score, 9 levels; Q1): "{q["react"]["instructions"]}" Label: Q1\'s level of '
        "e5 = AR(C_{t−1}→C_{t+4})/(σ_cc·√5): 4 + sign(e5)·bin(|e5|), bins [0, 0.5) [0.5, 1) [1, 2) "
        "[2, 3) [3, ∞). Derived N̂ = Σ p_k m_k with m = (−3.5, −2.5, −1.5, −0.75, 0, 0.75, 1.5, 2.5, "
        "3.5); E|N̂| = Σ p_k |m_k|.",
        "- **H-mag** (score, 5 levels; an internal training question, never sent to an API model): "
        f'"{q["mag"]["instructions"]}" Levels: {"; ".join(q["mag"]["criteria"])}. Label: '
        "bin(|z_cc,t|). Derived E[level midpoint] with midpoints (0.25, 0.75, 1.5, 2.5, 3.5) and "
        "P(|z| ≥ 1).",
        f'- **H-cont** (choice, 3; Q6, Call B only): "{q["cont"]["instructions"]}" Options reverse / '
        "stall / continue. Label (|G| ≥ 0.5, G = z_cc,t): x = sign(G)·y2, y2 = z(O_{t+1}→C_{t+5}); "
        "reverse x ≤ −0.5, continue x ≥ 0.5, else stall. Derived C = P(continue) − P(reverse); "
        "J analogue = C; W analogue = P(reverse).",
        "",
        "Questions asked: Call A D0 and D2: H-react, H-mag; Call B D2: H-react, H-cont.",
        "",
        "## Data",
        "",
        f"- Private Kaggle dataset `{cfg.export.dataset_id}`; files by sha256 in "
        f"`work/kaggle/dataset/{MANIFEST_FILE}` (manifest sha256 `{ctx['manifest_sha256']}`), equal to "
        "the files every run checked on Kaggle.",
        f"- Train: sessions {dates['train_first_session']} … {dates['train_last_session']}, last label "
        f"horizon {dates['train_last_label_horizon']} (purge, PREREG §4.1); "
        f"{info['counts']['train']['examples']:,} examples ({info['counts']['train']['states']:,} "
        "distinct states), including the block-dropout copies (PREREG §9.1: Call B without "
        f"`reaction_so_far`, p = {cfg.export.reaction_dropout}; any state without the context blocks, "
        f"p = {cfg.export.context_dropout}).",
        f"- Val-A: {splits['val_a'].start} … {splits['val_a'].end}: early stopping, temperatures and "
        "every number below, without the first 5 sessions (PREREG §4.2).",
        "- Val-B and test (Call A only): states without any label column; predictions are stored and "
        "not evaluated in NA-08. No test label left this machine.",
        "- Sequence: Laya's `[CLS] question [SEP] options [SEP] state [SEP]`, max length "
        f"{cfg.model.max_len}, head length {cfg.model.head_max_len} (the longest trained question, react, "
        "in Laya's rendering; operator decision on NA-04 owner decision 2). States longer than the room: "
        f"{tr['examples_cut']} examples ({tr['cut_by_split_question']}), cut by ≤ "
        f"{tr['max_excess_tokens']} tokens.",
    ]
    hp = ctx["hparams"]
    lines += [
        "",
        "## Training",
        "",
        f"AdamW, learning rates {cfg.model.lr_backbone:g} (encoder) / {cfg.model.lr_head:g} (head), "
        f"weight decay {cfg.model.weight_decay:g}, linear warm-up over {cfg.model.warmup_frac:.0%} of the "
        f"updates then cosine decay to {cfg.model.min_lr:g}, gradient clip {cfg.model.grad_clip:g}, "
        f"effective batch {hp['micro_batch']} × {ctx['world_size']} GPUs × {hp['grad_accum']}, fp16 "
        f"autocast, gradient checkpointing {'on' if hp['grad_checkpointing'] else 'off'}. Loss: Laya's "
        "official RLCD objective (`laya.train.rlcd_loss`: a proper-scoring policy-gradient term over "
        "noisy logits plus soft cross-entropy). ≤ 3 epochs, early stopping on the val-A cross-entropy "
        "(patience 0).",
        "",
        "| Run | Seed | Epochs run | Best epoch | Val-A loss by epoch | Stopped by time | GPU | Hours |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in ctx["records"]:
        losses = ", ".join(_fmt(h.get("val_a_loss")) for h in r["history"])
        hours = (r["throughput"]["wall_s"] + r["throughput"]["notebook_to_process_s"]) / 3600
        gpu = f"{r['gpu']['count']}× {r['gpu']['names'][0] if r['gpu']['names'] else '?'}"
        lines.append(
            f"| {r['run_name']} | {r['seed']} | {r['epochs_run']} | {r['best_epoch']} | {losses} | "
            f"{r['stopped_by_time_budget']} | {gpu} | {hours:.2f} |"
        )
    lines += ["", "## Val-A results (embargo excluded)", ""]
    lines += [
        "| | Model | IC | NW t | 95% CI (block bootstrap) | Days | Events |",
        "|---|---|---|---|---|---|---|",
    ]
    for who, rows in ctx["ics"].items():
        for row in rows:
            ci = row.get("ci95")
            ci_s = f"[{_fmt(ci[0])}, {_fmt(ci[1])}]" if ci else "–"
            name = row["name"].replace("|", "\\|")  # a literal bar inside a markdown table cell
            lines.append(
                f"| {name} | {who} | {_fmt(row['ic'])} | {_fmt(row['nw_t'], 2)} | {ci_s} | "
                f"{row['days']} | {row['events']:,} |"
            )
    lines += ["", "## Calibration (val-A, embargo excluded; 15-bin ECE)", ""]
    lines += [
        "| Head | Model | Temperature | ECE before | ECE after | NLL before | NLL after | n |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for who, heads in ctx["calibration"].items():
        for head, h in heads.items():
            t = ctx["temperatures"].get(who, {}).get(head)
            lines.append(
                f"| {head} | {who} | {_fmt(t, 3)} | {_fmt(h.get('ece_before'))} | {_fmt(h['ece_after'])} | "
                f"{_fmt(h.get('nll_before'))} | {_fmt(h['nll_after'])} | {h['n']:,} |"
            )
    lines += [
        "",
        "The ensemble averages calibrated probabilities, so it has no temperature of its own "
        "(ECE before = –).",
        "",
        "## Controls",
        "",
    ]
    ctl = ctx["controls"]
    sh, rp = ctl.get("shuffled_label", {}), ctl.get("reproducibility", {})
    if "pass" in sh:
        lines.append(
            f"- Shuffled labels ({sh['run']}): D0 N̂ vs e5 IC {_fmt(sh['ic_e5']['ic'])}, NW t "
            f"{_fmt(sh['ic_e5']['nw_t'], 2)}: {'PASS' if sh['pass'] else 'FAIL'} ({sh['rule']})."
        )
    else:
        lines.append(f"- Shuffled labels: {sh.get('status', 'not run')}.")
    if "pass" in rp:
        lines.append(
            f"- Reproducibility ({' vs '.join(rp['runs'])}): Δ IC {_fmt(rp['diff']['z_cc'])} (z_cc,t), "
            f"{_fmt(rp['diff']['e5'])} (e5): {'PASS' if rp['pass'] else 'FAIL'} ({rp['rule']})."
        )
    else:
        lines.append(f"- Reproducibility: {rp.get('status', 'not run')}.")
    lines += [
        "",
        "## Governance and limits",
        "",
        "- The Kaggle dataset is private and holds masked, third-party-OK states and train / val-A labels "
        "only; val-B and test labels never left this machine (CLAUDE.md D15–D16).",
        "- Nothing was pushed to the Hugging Face Hub: every run record says `hub_push: false`, the "
        "notebook has no upload call (tests/test_train_notebook.py) and the checkpoint stays in the "
        "kernel's output.",
        "- Labels are noisy realised returns; the result is reported as it is.",
    ]
    if init == "laya":
        lines.append(
            "- Laya's own training data is undisclosed (contamination unknown); the anchor exists for this "
            "reason."
        )
    return "\n".join(lines) + "\n"


def card_context(model: str, cfg: TrainingConfig, layout: Layout | None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    runs = [
        s.name for s in ensemble_runs(cfg)[model] if (lay.work / RUNS_DIR / f"{s.name}.parquet").is_file()
    ]
    if not runs:
        raise FileNotFoundError(f"no imported run of {model}")
    labels = io.read_parquet(LABELS, layout=lay)
    keys = event_keys(cfg, lay)
    ens = io.read_parquet(f"{PREDICTIONS_DIR}/{model}_val_a.parquet", layout=lay)
    ev_ens = with_targets(ens, labels)
    ic_rows = {"ensemble": ics(ev_ens, cfg)}
    cal = {"ensemble": head_calibration(ev_ens, cfg, raw=False)}
    temps: dict[str, dict[str, float]] = {}
    records = []
    for r in runs:
        ev = run_eval(r, keys, labels, cfg, lay)
        ic_rows[r] = ics(ev, cfg)
        cal[r] = head_calibration(ev, cfg, raw=True)
        rec = read_json(lay.work / PREDICTIONS_DIR / r / f"{PREFIX}{r}_run_record.json")
        records.append(rec)
        c = read_json(lay.work / PREDICTIONS_DIR / r / f"{PREFIX}{r}_calibration.json")
        temps[r] = {q: float(h["temperature"]) for q, h in c["heads"].items()}
    info = read_json(lay.work / DATASET_DIR / INFO_FILE)
    return {
        "cfg": cfg,
        "runs": runs,
        "n_seeds": len(runs),
        "records": records,
        "hparams": records[0]["hparams"],
        "world_size": records[0]["world_size"],
        "ics": ic_rows,
        "calibration": cal,
        "temperatures": temps,
        "info": info,
        "manifest_sha256": io.sha256_file(lay.work / DATASET_DIR / MANIFEST_FILE),
    }


def run(layout: Layout | None = None, cfg: TrainingConfig | None = None) -> dict[str, Any]:
    """Write controls.json and the model card of every model with imported runs; log the trials."""
    lay = resolve_layout(layout)
    cfg = load_training_config() if cfg is None else cfg
    out_dir = lay.artifacts / ARTIFACTS_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = io.read_parquet(LABELS, layout=lay)
    keys = event_keys(cfg, lay)
    ctl = controls(cfg, keys, labels, lay)
    (out_dir / CONTROLS_FILE).write_text(json.dumps(ctl, indent=2, default=float) + "\n", encoding="utf-8")
    summary: dict[str, Any] = {"controls": {k: v.get("pass") for k, v in ctl.items() if isinstance(v, dict)}}
    for model in MODEL_NAMES.values():
        try:
            ctx = card_context(model, cfg, lay)
        except FileNotFoundError:
            continue
        ctx["controls"] = ctl
        (out_dir / f"model_card_{model}.md").write_text(card_text(model, ctx), encoding="utf-8")
        primary = {
            who: rows[0]["ic"] for who, rows in ctx["ics"].items() if rows and rows[0]["name"] == PRIMARY[0]
        }
        for who, ic in primary.items():
            log_trial(
                f"{model}/{who}", {"model": model, "who": who, "runs": ctx["runs"]}, "ic_nhat_zcc_d0", ic, lay
            )
        summary[model] = primary
    return summary
