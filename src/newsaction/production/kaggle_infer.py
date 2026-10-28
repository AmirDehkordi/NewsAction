"""NA-11 S7: the frozen trained instruments' inference on Kaggle (PRD NA-11 S7; PREREG §9.4; CLAUDE.md
D15–D16).

1. ``export``: ``work/kaggle/dataset_na11/`` holds the files the plan names (``configs/production.yaml``
   ``trained.export``) plus a 500-example reproduction check; one row per (state, question) in NA-08's
   evaluation columns, no label column; masked, third-party-OK states only. A separate private dataset
   (``amirdehkordi98/newsaction-na11-infer``), so the NA-08 dataset that the deferred seed runs attach keeps
   its files.
   - ``test_callB``: Call B at D2 and at D1 (built after the freeze), questions react and cont;
   - ``val_callB_d1``: val-A and val-B Call B at D1 (react, cont);
   - ``robustness_callA``: Call A at D0 and D2 of the robustness split (react, mag);
   - ``probes``: NA-06's 200 counterfactual edits (variant ``flip_edit``) and 1,000 shuffled-news states
     (variant ``shuffled``), react (the operator's disclosed probes);
   - ``check_val_a``: 500 val-A D0 react examples of NA-08's export (the smallest sha256("2026:check:<id>")),
     re-predicted to show the checkpoint is the one behind NA-08's predictions.
2. ``kernels``: ``work/kaggle/kernels/infer-<run>/`` (private, GPU T4 ×2; the dataset and the training kernel,
   whose output holds ``ckpt/``, as sources) with the inference notebook and the run's parameters, including
   the run's NA-08 val-A temperatures, which the checkpoint must carry.
3. ``projection``: GPU-hours from the rows and NA-08's measured inference rate, plus setup, plus 10%.
4. ``import_run``: verifies a download and writes the instrument's files in NA-08's common schema (``runs`` =
   the frozen pin): ``work/kaggle/predictions/<model>_{test_callB,val_callB_d1,robustness_callA,probes}``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io, lock
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError, artifacts_dir
from newsaction.production.plan import load_plan
from newsaction.states.questions import canonical_json
from newsaction.train import PREDICTIONS_DIR, load_training_config, training_questions
from newsaction.train.import_preds import derive, frozen_runs, read_preds, softmax
from newsaction.train.kaggle_export import EVAL_COLUMNS, assert_no_labels

DATASET_DIR: Final = "kaggle/dataset_na11"
DATASET_ID: Final = "amirdehkordi98/newsaction-na11-infer"
MANIFEST: Final = "na11_manifest.json"
FILES: Final = ("test_callB", "val_callB_d1", "robustness_callA", "probes", "check_val_a")
N_CHECK: Final = 500
SETUP_HOURS: Final = 0.1
MARGIN: Final = 1.10
PROB_TOL: Final = 2e-4
CHECK_TOL: Final = 2e-3


def _rows(
    states: pd.DataFrame, questions: Sequence[str], qjson: Mapping[str, str], variant: str = "full"
) -> pd.DataFrame:
    """One row per (state, question) in NA-08's evaluation columns."""
    if not bool(states["masked"].all()) or not bool(states["third_party_ok_all"].all()):
        raise ProductionError("only masked, third-party-OK states may go to Kaggle (CLAUDE.md D15-D16)")
    parts = []
    for q in questions:
        r = states[["event_id", "split", "call", "window", "state_json", "n_tokens_state"]].copy()
        r["variant"], r["question_id"], r["question_json"] = variant, q, qjson[q]
        r["example_id"] = r["event_id"] + "|" + r["call"] + "|" + variant + "|" + q
        parts.append(r)
    out = pd.concat(parts, ignore_index=True)[list(EVAL_COLUMNS)]
    out["n_tokens_state"] = out["n_tokens_state"].astype("int64")
    return out


def _states(rel: str, splits: Sequence[str], layout: Layout) -> pd.DataFrame:
    cols = [
        "event_id",
        "split",
        "call",
        "window",
        "masked",
        "third_party_ok_all",
        "state_json",
        "n_tokens_state",
    ]
    df = io.read_parquet(rel, columns=cols, layout=layout)
    return df.loc[df["split"].isin(list(splits))].reset_index(drop=True)


def _probe_states(layout: Layout) -> pd.DataFrame:
    """NA-06's edited and shuffled val-A states (masked; a shuffled one with both sources third-party OK)."""
    from newsaction.events import load_events_config, tokens
    from newsaction.tournament import probes as pr
    from newsaction.tournament import run as tr

    ctx = tr.Ctx.load(layout)
    states = ctx.states_a().set_index("event_id")
    cf = ctx.counterfactual()
    rows = []
    for rec in cf.to_dict("records"):
        base = states.loc[rec["event_id"]]
        rows.append(
            {
                "event_id": rec["event_id"],
                "variant": "flip_edit",
                "state_json": rec["edited_state_json"],
                "third_party_ok_all": bool(base["third_party_ok_all"]),
            }
        )
    s = ctx.samples().set_index("event_id")
    for eid in ctx.ids("shuffled"):
        donor = str(s.loc[eid, "shuffle_donor"])
        st = pr.shuffled_state(
            json.loads(str(states.loc[eid, "state_json"])), json.loads(str(states.loc[donor, "state_json"]))
        )
        rows.append(
            {
                "event_id": eid,
                "variant": "shuffled",
                "state_json": canonical_json(st),
                "third_party_ok_all": bool(states.loc[eid, "third_party_ok_all"])
                and bool(states.loc[donor, "third_party_ok_all"]),
            }
        )
    df = pd.DataFrame(rows)
    df["split"], df["call"], df["window"], df["masked"] = "val_a", "A", "W0", True
    tok = tokens.tokenizer(load_events_config().events)
    df["n_tokens_state"] = [
        len(x) for x in tok(df["state_json"].tolist(), add_special_tokens=False)["input_ids"]
    ]
    return df


def build_files(layout: Layout | None = None) -> dict[str, pd.DataFrame]:
    lay = resolve_layout(layout)
    if not lock.is_frozen(lay):
        raise ProductionError("S7 exports test-period Call B states, which exist only after the freeze")
    plan = load_plan()
    qs = training_questions(load_training_config())
    qjson: dict[str, str] = {
        str(q): json.dumps(v, ensure_ascii=False, separators=(",", ":")) for q, v in qs.items()
    }
    st = plan.states
    test_b = [
        _rows(_states(st["B_D2_test"], ["test"], lay), ["react", "cont"], qjson),
        _rows(_states(st["B_D1_test"], ["test"], lay), ["react", "cont"], qjson),
    ]
    rob_a = [
        _rows(_states(st["A_D0"], ["robustness"], lay), ["react", "mag"], qjson),
        _rows(_states(st["A_D2"], ["robustness"], lay), ["react", "mag"], qjson),
    ]
    files: dict[str, pd.DataFrame] = {
        "test_callB": pd.concat(test_b, ignore_index=True),
        "val_callB_d1": _rows(_states(st["B_D1"], ["val_a", "val_b"], lay), ["react", "cont"], qjson),
        "robustness_callA": pd.concat(rob_a, ignore_index=True),
    }
    pst = _probe_states(lay)
    files["probes"] = pd.concat(
        [_rows(g, ["react"], qjson, str(v)) for v, g in pst.groupby("variant")], ignore_index=True
    )
    va = io.read_parquet("kaggle/dataset/val_a.parquet", columns=list(EVAL_COLUMNS), layout=lay)
    va = va.loc[
        (va["call"] == "A")
        & (va["window"] == "W0")
        & (va["variant"] == "full")
        & (va["question_id"] == "react")
    ]
    u = va["example_id"].map(lambda e: hashlib.sha256(f"2026:check:{e}".encode()).hexdigest())
    files["check_val_a"] = (
        va.assign(_u=u).sort_values("_u").head(N_CHECK).drop(columns="_u").reset_index(drop=True)
    )
    for name, df in files.items():
        assert_no_labels(df, name)
        if not df["example_id"].is_unique:
            raise ProductionError(f"{name}: example ids are not unique")
    return files


def export(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    files = build_files(lay)
    out = lay.work / DATASET_DIR
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"files": {}}
    for name, df in files.items():
        entry = io.write_parquet(
            df,
            f"{DATASET_DIR}/{name}.parquet",
            producer=CHUNK,
            layout=lay,
            description=f"NA-11 S7 Kaggle inference file {name} (masked, no label)",
        )
        manifest["files"][f"{name}.parquet"] = {"sha256": entry["sha256"], "rows": len(df)}
    (out / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    meta = {
        "title": "NewsAction NA-11 inference states",
        "id": DATASET_ID,
        "licenses": [{"name": "other"}],
        "isPrivate": True,
    }
    (out / "dataset-metadata.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return {name: len(df) for name, df in files.items()}


def temperatures(run: str, layout: Layout | None = None) -> dict[str, float]:
    path = resolve_layout(layout).work / PREDICTIONS_DIR / run / f"na08_{run}_calibration.json"
    cal = json.loads(path.read_text(encoding="utf-8"))
    return {q: float(h["temperature"]) for q, h in cal["heads"].items()}


def kernels(layout: Layout | None = None) -> list[str]:
    """Kernel directories for the frozen runs (the notebook with each run's parameters)."""
    from newsaction.train import infer_nbbuild as nbi

    lay = resolve_layout(layout)
    cfg = load_training_config()
    pins = frozen_runs(lay)
    if pins is None:
        raise ProductionError("no frozen run pin")
    nb = nbi.build_notebook()
    out = []
    for runs in pins.values():
        run = runs[0]
        d = lay.work / "kaggle" / "kernels" / f"infer-{run}"
        d.mkdir(parents=True, exist_ok=True)
        params = {
            "RUN_NAME": run,
            "CKPT_KERNEL": f"{cfg.kaggle.kernel_prefix}-{run}",
            "TEMPERATURES": temperatures(run, lay),
            "FILES": list(FILES),
            "MAX_LEN": cfg.model.max_len,
            "HEAD_MAX_LEN": cfg.model.head_max_len,
            "HPARAMS": {"eval_batch": cfg.model.eval_batch, "amp": cfg.model.amp},
            "PIP": list(cfg.model.pip),
            "LOCAL": None,
        }
        (d / "newsaction_infer.ipynb").write_text(
            nbi.notebook_text(nbi.with_params(nb, params)), encoding="utf-8"
        )
        user = DATASET_ID.split("/")[0]
        meta = {
            "id": f"{user}/newsaction-na11-infer-{run}",
            "title": f"newsaction-na11-infer-{run}",
            "code_file": "newsaction_infer.ipynb",
            "language": "python",
            "kernel_type": "notebook",
            "is_private": True,
            "enable_gpu": True,
            "enable_tpu": False,
            "enable_internet": True,
            "machine_shape": cfg.kaggle.accelerator,
            "dataset_sources": [DATASET_ID],
            "kernel_sources": [f"{user}/{cfg.kaggle.kernel_prefix}-{run}"],
            "competition_sources": [],
            "model_sources": [],
        }
        (d / "kernel-metadata.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        out.append(str(d.relative_to(lay.root)))
    return out


def projection(layout: Layout | None = None) -> dict[str, Any]:
    """GPU-hours per kernel: the rows over NA-08's slowest measured inference rate, plus setup, plus 10%."""
    lay = resolve_layout(layout)
    man = json.loads((lay.work / DATASET_DIR / MANIFEST).read_text(encoding="utf-8"))
    rows = sum(int(e["rows"]) for e in man["files"].values())
    rates = []
    for run in ("laya-s13", "anchor-s13"):
        rec = json.loads((lay.work / PREDICTIONS_DIR / run / f"na08_{run}_run_record.json").read_text())
        rates.append(float(rec["throughput"]["eval_seq_per_s"]))
    rate = min(rates)
    per_kernel = (rows / rate / 3600.0 + SETUP_HOURS) * MARGIN
    return {
        "rows_per_kernel": rows,
        "rows_by_file": {k: v["rows"] for k, v in man["files"].items()},
        "rate_seq_per_s": rate,
        "hours_per_kernel": per_kernel,
        "kernels": 2,
        "hours_total": 2 * per_kernel,
    }


def import_run(run: str, layout: Layout | None = None) -> dict[str, Any]:
    """Verify ``work/kaggle/predictions/infer-<run>/`` and write the instrument's NA-11 prediction files."""
    from newsaction.train import infer_nbbuild as nbi
    from newsaction.train.import_preds import event_keys
    from newsaction.train.nbbuild import PROGRAM

    lay = resolve_layout(layout)
    pins = frozen_runs(lay) or {}
    model = next((m for m, r in pins.items() if r == (run,)), None)
    if model is None:
        raise ProductionError(f"{run} is not a frozen instrument's pinned run")
    d = lay.work / PREDICTIONS_DIR / f"infer-{run}"
    outputs = json.loads((d / "na11_outputs.json").read_text(encoding="utf-8"))
    for name, sha in outputs.items():
        if io.sha256_file(d / name) != sha:
            raise ProductionError(f"{name}: sha256 differs from na11_outputs.json")
    rec = json.loads((d / f"na11_{run}_infer_record.json").read_text(encoding="utf-8"))
    problems = []
    if rec["trained"] is not False or rec["hub_push"] is not False or rec["labels_read"] is not False:
        problems.append("the record does not say trained, hub_push and labels_read false")
    if rec["checkpoint"]["temperatures"] != temperatures(run, lay):
        problems.append("checkpoint temperatures differ from NA-08's verified run")
    progs = rec["program_sha256"]
    if progs["train_ddp.py"] != io.sha256_file(PROGRAM) or progs["infer_ddp.py"] != io.sha256_file(
        nbi.INFER_PROGRAM
    ):
        problems.append("a program differs from the committed one")
    man = json.loads((lay.work / DATASET_DIR / MANIFEST).read_text(encoding="utf-8"))
    if rec["dataset"]["files"] != {k: v["sha256"] for k, v in man["files"].items()}:
        problems.append("the kernel read other dataset files")
    if problems:
        raise ProductionError(f"{run}: " + "; ".join(problems))
    keys = event_keys(load_training_config(), lay)
    summary: dict[str, Any] = {"run": run, "model": model}
    for name in FILES:
        src = pd.read_parquet(
            lay.work / DATASET_DIR / f"{name}.parquet",
            columns=["example_id", "event_id", "split", "call", "window", "variant", "question_id"],
        )
        p = read_preds(d / f"na11_{run}_{name}.arrow")
        if set(p["example_id"]) != set(src["example_id"]) or len(p) != len(src):
            raise ProductionError(f"{name}: predictions do not cover the dataset's examples exactly")
        t = temperatures(run, lay)
        for z, pr, q in zip(p["logits"], p["probs"], p["question_id"], strict=True):
            if np.max(np.abs(softmax(np.asarray(z), t[q]) - np.asarray(pr))) > PROB_TOL:
                raise ProductionError(f"{name}: probabilities are not softmax(logits / T)")
        df = src.merge(p[["example_id", "k", "probs"]], on="example_id", how="inner")
        if name == "check_val_a":
            ref = pd.read_parquet(
                lay.work / PREDICTIONS_DIR / "runs" / f"{run}.parquet",
                columns=["example_id", "probabilities"],
            )
            m = df.merge(ref, on="example_id", how="inner")
            diff = max(
                float(np.max(np.abs(np.asarray(a) - np.asarray(b))))
                for a, b in zip(m["probs"], m["probabilities"], strict=True)
            )
            summary["check_max_abs_dp"], summary["check_rows"] = diff, len(m)
            if len(m) != len(df) or diff > CHECK_TOL:
                raise ProductionError(
                    f"{run}: the checkpoint does not reproduce NA-08's val-A predictions ({diff})"
                )
            continue
        parts = []
        for q, g in df.groupby("question_id", sort=True):
            g = g.reset_index(drop=True)
            parts.append(pd.concat([g, derive(str(q), list(g["probs"]))], axis=1))
        out = pd.concat(parts, ignore_index=True).rename(
            columns={"question_id": "question", "probs": "probabilities"}
        )
        out = out.merge(keys, on="event_id", how="left", validate="many_to_one")
        out["decision_point"] = np.where(
            out["call"] == "B",
            np.where(out["window"] == "W0", "D1", "D2"),
            np.where(out["window"] == "W0", "D0", "D2"),
        )
        out["model"], out["runs"], out["n_seeds"] = model, run, 1
        out["probabilities"] = [np.asarray(x, dtype=np.float64).tolist() for x in out["probabilities"]]
        io.write_parquet(
            out.drop(columns=["example_id"]),
            f"{PREDICTIONS_DIR}/{model}_{name}.parquet",
            producer=CHUNK,
            layout=lay,
            description=f"NA-11 S7: {model} ({run}, the frozen pin) on {name}, NA-08's schema "
            "plus variant; inference only on Kaggle",
        )
        summary[name] = len(out)
    (artifacts_dir(lay) / f"kaggle_import_{run}.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "projection"
    if cmd == "export":
        print(json.dumps(export(), indent=1))
    elif cmd == "kernels":
        print("\n".join(kernels()))
    elif cmd == "projection":
        print(json.dumps(projection(), indent=1))
    elif cmd == "import":
        print(json.dumps([import_run(r) for r in args[1:] or ["laya-s13", "anchor-s13"]], indent=1))
    else:
        raise SystemExit(
            "usage: python -m newsaction.production.kaggle_infer export|kernels|projection|import"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
