"""NA-09 stages (PRD NA-09): ``python -m newsaction.baselines.run --stage <stage>``.

1. ``laya``: Laya zero-shot answers for the configured (split, call) pairs (long; run detached). ``--pairs
   val_a:A,val_b:B`` restricts it.
2. ``articles``: the article ids of every Call A D0 state (``data.rebuild_state_articles``, checked against
   every state) → ``work/baselines/state_articles.parquet``.
3. ``fit``: sentiment, embed_ridge, tags_gbm, price_only (D0 and D2): fit on train, tuned on val-A, models
   and fit records under ``work/baselines/models/``, predictions → ``work/baselines/<model>.parquet``.
4. ``llm_sample``: the 2,000 val-B D0 events → ``work/baselines/llm_sample.parquet``.
5. ``llm_select``: the live catalog (no spend), the selection rule → ``artifacts/NA-09/llm_catalog.json`` and
   ``configs/frozen.yaml`` ``chat_models``.
6. ``llm_dry`` / ``llm_run``: the projection (recorded in ``artifacts/NA-09/llm_dry_run.json``); ``llm_run``
   also checks the account's credit and sends.
7. ``laya_predictions`` / ``llm_predictions``: offline, from the cache → ``work/baselines/{laya_zeroshot,
   llm}.parquet`` (and ``artifacts/NA-09/llm_summary.json``).
8. ``metrics``: ``artifacts/NA-09/baseline_val_metrics.csv`` (val-A only) and its trials.
9. ``report``: ``artifacts/NA-09/summary.json`` (prediction counts, fit records, spend).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

import pandas as pd
import yaml

from newsaction import io
from newsaction.baselines import (
    ARTIFACTS,
    CHUNK,
    PRODUCER,
    WORK_DIR,
    BaselineError,
    baselines_config,
    data,
    embed_ridge,
    laya_zeroshot,
    llm_baseline,
    metrics,
    price_only,
    schema,
    sentiment,
    tags_gbm,
)
from newsaction.config import SplitName
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso

STAGES: Final = (
    "laya",
    "articles",
    "fit",
    "llm_sample",
    "llm_select",
    "llm_dry",
    "llm_run",
    "laya_predictions",
    "llm_predictions",
    "metrics",
    "report",
)
DESCRIPTIONS: Final = {
    "sentiment": "PREREG §10.1 vendor sentiment → isotonic N_hat (train), OLS mag_hat (train), val-A P maps",
    "embed_ridge": "PREREG §10.2 bge-small mean + attention → ridge (train; λ on val-A), val-A P maps",
    "tags_gbm": "PREREG §10.3 vendor tags, flags, sentiment, sources, novelty, attention, tier, sector → GBM",
    "price_only": "PREREG §10.4 price-only LightGBM: D0 (call A) N_hat / mag_hat; D2 (call B) y_hat of y2",
    "laya_zeroshot": "PREREG §10.5 local Laya typed-decisions zero-shot, core battery (Call A D0, Call B D2)",
    "llm": "PREREG §10.7 generative LLM (chat_json), Q1 probabilities on 2,000 val-B D0 events",
}


def log(msg: str) -> None:
    print(f"[{utc_now_iso()[:19]}] {msg}", flush=True)


def state_keys(layout: Layout | None = None) -> dict[str, pd.DataFrame]:
    cfg = baselines_config(layout)
    cols = ["event_id", "split", "session", "company_id"]
    return {
        "A": io.read_parquet(cfg.state_files.call_a, columns=cols, layout=layout),
        "B": io.read_parquet(cfg.state_files.call_b, columns=cols, layout=layout),
    }


def write_predictions(df: pd.DataFrame, model: str, layout: Layout | None = None) -> dict[str, Any]:
    """Attach missing state keys, validate (``schema.validate``) and write work/baselines/<model>.parquet."""
    keys = state_keys(layout)
    parts = []
    for call, g in df.groupby("call", sort=True):
        if "session" not in g.columns or "company_id" not in g.columns or g["session"].isna().any():
            k = keys[str(call)][["event_id", "session", "company_id"]]
            g = g.drop(columns=[c for c in ("session", "company_id") if c in g.columns])
            g = g.merge(k, on="event_id", how="left", validate="one_to_one")
        parts.append(g)
    out = schema.frame(pd.concat(parts, ignore_index=True))
    schema.validate(out, keys)
    return io.write_parquet(
        out, f"{WORK_DIR}/{model}.parquet", producer=PRODUCER, description=DESCRIPTIONS[model], layout=layout
    )


def _write_json(rel: str, obj: Any, layout: Layout | None, description: str) -> None:
    lay = resolve_layout(layout)
    io.atomic_write_bytes(lay.root / rel, (json.dumps(obj, indent=2, default=str) + "\n").encode("utf-8"))
    io.register_artifact(rel, producer=PRODUCER, description=description, layout=lay)


def stage_articles(layout: Layout | None = None) -> None:
    sa = data.rebuild_state_articles(layout)
    io.write_parquet(
        sa,
        data.STATE_ARTICLES,
        producer=PRODUCER,
        description="NA-09: article ids of every Call A D0 state (rebuilt from events_d0 and checked)",
        layout=layout,
    )
    log(f"state articles: {len(sa)} rows, {sa['event_id'].nunique()} states")


def stage_fit(layout: Layout | None = None) -> None:
    cfg = baselines_config(layout)
    d0 = data.d0_frame(cfg, layout)
    log(f"D0 frame {d0.shape}")
    for name, fn in (("sentiment", sentiment.fit_predict), ("embed_ridge", embed_ridge.fit_predict),
                     ("tags_gbm", tags_gbm.fit_predict)):  # fmt: skip
        write_predictions(fn(d0, cfg, layout), name, layout)
        log(f"{name}: written")
    d2 = data.d2_frame(cfg, layout)
    log(f"D2 frame {d2.shape}")
    po = pd.concat([price_only.fit_predict_d0(d0, cfg, layout), price_only.fit_predict_d2(d2, cfg, layout)])
    write_predictions(po, "price_only", layout)
    log("price_only: written")


def stage_llm_sample(layout: Layout | None = None) -> None:
    cfg = baselines_config(layout)
    smp = llm_baseline.sample(cfg, layout)
    io.write_parquet(
        smp,
        llm_baseline.SAMPLE,
        producer=PRODUCER,
        description="NA-09 S7: 2,000 val-B D0 events (tier × month, seed 2026) with their Call A states",
        layout=layout,
    )
    log(f"LLM sample: {len(smp)} events, {smp['session'].min()} … {smp['session'].max()}")


def write_frozen_chat_models(snap: Mapping[str, Any], layout: Layout | None = None) -> None:
    """Replace (or add, before ``allow_val_b``) the ``chat_models:`` section of configs/frozen.yaml."""
    path = resolve_layout(layout).configs / "frozen.yaml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    chosen = next(m for m in snap["models"] if m["id"] == snap["chosen"])
    p = chosen["pricing"]
    reason = (
        f"NA-09 S7 rule (configs/baselines.yaml llm.selection): closest projected cost per 1,000 Call A "
        f"decisions ({chosen['projected_usd_per_1000']:.4f} USD) to the NA-06 API median "
        f"({snap['reference_usd_per_1000']:.4f}); knowledge cutoff {chosen['knowledge_cutoff']}; catalog "
        f"{snap['raw_sha256'][:16]}"
    )
    entry = (
        f'  - {{id: "{chosen["id"]}", include: true, prompt_usd_per_token: "{p["prompt"]}", '
        f'completion_usd_per_token: "{p["completion"]}", reason: "{reason}"}}\n'
    )
    block = [
        "chat_models:       # NA-09 S7: the generative-LLM baseline, the only models chat_json may call "
        "(artifacts/NA-09/llm_catalog.json)\n",
        entry,
    ]
    starts = [i for i, ln in enumerate(lines) if re.match(r"^chat_models:", ln)]
    if starts:
        start = starts[0]
        end = start + 1
        while end < len(lines) and lines[end].startswith((" ", "\t")):
            end += 1
    else:
        start = end = next(i for i, ln in enumerate(lines) if re.match(r"^allow_val_b:", ln))
        block.append("\n")
    new = "".join(lines[:start] + block + lines[end:])
    parsed = yaml.safe_load(new)["chat_models"]
    if [r["id"] for r in parsed] != [chosen["id"]] or parsed[0]["include"] is not True:
        raise BaselineError("frozen.yaml chat_models does not round-trip")
    io.atomic_write_bytes(path, new.encode("utf-8"))


def stage_llm_select(layout: Layout | None = None) -> None:
    from newsaction.dm.client import DecisionClient

    cfg = baselines_config(layout)
    with DecisionClient(CHUNK, layout=layout) as client:
        raw = client.get_json(client.config.api.models_url)
    snap = llm_baseline.write_catalog(raw, cfg, layout)
    write_frozen_chat_models(snap, layout)
    top = [
        (m["id"], round(m["projected_usd_per_1000"], 4), m["knowledge_cutoff"]) for m in snap["models"][:8]
    ]
    log(f"reference {snap['reference_usd_per_1000']:.4f} USD/1,000; chosen {snap['chosen']}; order {top}")


def stage_llm(layout: Layout | None, *, send: bool) -> None:
    out = llm_baseline.run(layout, send=send)
    lay = resolve_layout(layout)
    rel = f"{ARTIFACTS}/llm_dry_run.json"
    old = json.loads((lay.root / rel).read_text(encoding="utf-8")) if (lay.root / rel).is_file() else []
    _write_json(
        rel, [*old, {"ts": utc_now_iso(), "send": send, **out}], layout, "NA-09 S7 projections and runs"
    )
    log(json.dumps(out))


def stage_laya_predictions(layout: Layout | None = None) -> None:
    pred = laya_zeroshot.predictions(layout)
    write_predictions(pred, "laya_zeroshot", layout)
    log(f"laya_zeroshot: {len(pred)} predictions")


def stage_llm_predictions(layout: Layout | None = None) -> None:
    write_predictions(llm_baseline.predictions(layout), "llm", layout)
    summ = llm_baseline.summary(layout)
    _write_json(f"{ARTIFACTS}/llm_summary.json", summ, layout, "NA-09 S7 LLM answers: validity, tokens, cost")
    log(json.dumps(summ))


def prediction_files(layout: Layout | None = None) -> dict[str, pd.DataFrame]:
    lay = resolve_layout(layout)
    out = {}
    for model in schema.MODELS:
        rel = f"{WORK_DIR}/{model}.parquet"
        if (lay.work / rel).is_file():
            out[model] = io.read_parquet(rel, layout=lay)
    return out


def event_table(layout: Layout | None = None) -> pd.DataFrame:
    cols = ["event_id", "symbol_id", "tier", "embargo"]
    return pd.concat(
        [io.read_parquet(f"events/events_{w}.parquet", columns=cols, layout=layout) for w in ("d0", "d2")],
        ignore_index=True,
    )


def stage_metrics(layout: Layout | None = None) -> None:
    cfg = baselines_config(layout)
    preds = prediction_files(layout)
    table = metrics.val_metrics(list(preds.values()), event_table(layout), cfg, layout)
    metrics.write(table, layout)
    n = metrics.log_metrics(table, layout)
    log(f"metrics: {len(table)} rows for {sorted(preds)}; {n} new trials")


def stage_report(layout: Layout | None = None) -> None:
    from newsaction.baselines.fitting import MODELS_DIR
    from newsaction.ledger import SPEND, SpendLedger

    lay = resolve_layout(layout)
    preds = prediction_files(lay)
    counts: dict[str, dict[str, int]] = {}
    for m, p in preds.items():
        sizes = p.groupby(["call", "split"]).size()
        counts[m] = {
            f"{c}:{sp}": int(n) for (c, sp), n in zip(sizes.index.tolist(), sizes.tolist(), strict=True)
        }
    records = {}
    for path in sorted((lay.work / MODELS_DIR).glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))["record"]
        records[path.stem] = {k: rec[k] for k in ("fit", "tune", "calibration", "selected")}
    key_usage = f"{ARTIFACTS}/key_usage.json"
    if (lay.root / key_usage).is_file():
        io.register_artifact(
            key_usage, producer=PRODUCER, description="NA-09 account / key snapshots", layout=lay
        )
    totals = SpendLedger(CHUNK, path=lay.ledgers / SPEND).totals()
    _write_json(
        f"{ARTIFACTS}/summary.json",
        {
            "predictions": counts,
            "fit_records": records,
            "spend": {
                "chunk_usd": totals.chunk_usd,
                "total_usd": totals.total_usd,
                "by_chunk": totals.by_chunk,
            },
        },
        layout,
        "NA-09 summary: prediction counts by call and split, fit records, spend",
    )
    log(json.dumps(counts))


def _pairs(text: str | None) -> list[tuple[SplitName, str]] | None:
    if not text:
        return None
    out = []
    for item in text.split(","):
        split, _, call = item.partition(":")
        out.append((cast(SplitName, split.strip()), call.strip()))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="newsaction.baselines.run")
    ap.add_argument("--stage", required=True, choices=STAGES)
    ap.add_argument(
        "--pairs", default=None, help="laya: split:call,… (default: configs/baselines.yaml order)"
    )
    args = ap.parse_args(argv)
    if args.stage == "laya":
        print(json.dumps(laya_zeroshot.run(_pairs(args.pairs)), indent=2))
    elif args.stage == "articles":
        stage_articles()
    elif args.stage == "fit":
        stage_fit()
    elif args.stage == "llm_sample":
        stage_llm_sample()
    elif args.stage == "llm_select":
        stage_llm_select()
    elif args.stage in ("llm_dry", "llm_run"):
        stage_llm(None, send=args.stage == "llm_run")
    elif args.stage == "laya_predictions":
        stage_laya_predictions()
    elif args.stage == "llm_predictions":
        stage_llm_predictions()
    elif args.stage == "metrics":
        stage_metrics()
    elif args.stage == "report":
        stage_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
