"""NA-11 S8: the generative LLM baseline on its test subsample (PREREG §10.7; ``configs/production.yaml``
``llm_baseline``), with NA-09's model, prompt, settings and parsing (``baselines.llm_baseline``).

- **Sample**: the plan's 2,000 test D0 events with a Call A state, outside the embargo, stratified by tier ×
  month with NA-04's ``stratified_sample`` and seed 2026: NA-09's val-B rule applied to the test split.
- **Requests**: NA-09's ``specs`` (temperature 0, seed 2026, strict JSON schema, ``data_collection: deny``),
  tagged ``na11_llm_test``. A projection above the plan's cap or what the caps leave is a STOP.
- **Predictions**: NA-09's ``prediction_row`` in the baselines' common schema; an invalid answer is counted
  in ``artifacts/NA-11/llm_test.json``, not written.

Outputs: ``work/dm/production/llm_sample_test.parquet``, ``work/dm/production/llm_test.parquet``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final

import pandas as pd

from newsaction import io, lock
from newsaction.baselines import baselines_config
from newsaction.baselines import llm_baseline as nb
from newsaction.baselines import schema as bs
from newsaction.baselines.data import d0_events
from newsaction.dm.canary import STATE_COLUMNS
from newsaction.dm.client import ChatSpec, DecisionClient
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError, artifacts_dir, record_key_usage
from newsaction.production.plan import load_plan
from newsaction.production.run import PRODUCTION_DIR
from newsaction.states.build import stratified_sample

SAMPLE: Final = f"{PRODUCTION_DIR}/llm_sample_test.parquet"
OUT: Final = f"{PRODUCTION_DIR}/llm_test.parquet"
TAG: Final = "na11_llm_test"


def write_sample(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if not lock.is_frozen(lay):
        raise ProductionError("the test subsample follows the freeze")
    plan, cfg = load_plan().llm_baseline, baselines_config(lay)
    ev = d0_events(cfg, lay)
    pool = ev.loc[(ev["split"] == plan.split) & ~ev["embargo"].astype(bool)]
    smp = stratified_sample(pool, plan.n, plan.strata, plan.seed)
    states = io.read_parquet(cfg.state_files.call_a, columns=STATE_COLUMNS, layout=lay)
    out = smp[["event_id", "tier", "month"]].merge(states, on="event_id", how="left", validate="one_to_one")
    if bool(out["state_json"].isna().any()):
        raise ProductionError("a sampled event has no Call A state")
    out = out.sort_values(["session", "event_id"], kind="mergesort").reset_index(drop=True)
    io.write_parquet(
        out,
        SAMPLE,
        producer=CHUNK,
        layout=lay,
        description="NA-11 S8: the LLM baseline's 2,000 test D0 events (tier × month, seed 2026, NA-09)",
    )
    return {"rows": len(out), "pool": len(pool)}


def specs(layout: Layout | None = None) -> list[ChatSpec]:
    lay = resolve_layout(layout)
    plan, cfg = load_plan().llm_baseline, baselines_config(lay)
    model = nb.chosen_model(lay)
    if model != plan.model:
        raise ProductionError(f"NA-09 chose {model}, the plan names {plan.model}")
    rows = io.read_parquet(SAMPLE, layout=lay)
    return [replace(s, tag=TAG) for s in nb.specs(rows, model, cfg, lay)]


def run(layout: Layout | None = None, *, send: bool = False) -> dict[str, Any]:
    """Dry run (always) and, with ``send``, the calls and the predictions."""
    lay = resolve_layout(layout)
    plan = load_plan().llm_baseline
    sp = specs(lay)
    with DecisionClient(CHUNK, layout=lay) as cl:
        proj = cl.dry_run_chat(sp)
        out: dict[str, Any] = {
            "model": plan.model,
            "requests": proj.n_requests,
            "send": proj.n_send,
            "projected_usd": proj.usd,
            "cap_usd": plan.cap_usd,
            "budget_left_usd": cl.budget_left(),
        }
        if proj.usd > min(plan.cap_usd, out["budget_left_usd"]):
            raise ProductionError(
                f"STOP: the projection ${proj.usd:.4f} exceeds the cap or what is left ({out})"
            )
        if not send:
            return out
        record_key_usage("before S8 LLM baseline", cl)
        res = cl.chat_json_batch(sp)
        record_key_usage("after S8 LLM baseline", cl)
    rows, problems = [], 0
    for r in res:
        d = nb.prediction_row(r)
        if not d["valid"]:
            problems += 1
            continue
        info = r.spec.info
        rows.append(
            {
                "event_id": info.event_id,
                "model": nb.MODEL_NAME,
                "call": "A",
                "split": info.split,
                "session": info.session,
                **{k: d[k] for k in ("N_hat", "P_up", "P_down", "mag_hat")},
                "extra": json.dumps(d["extra"], sort_keys=True),
            }
        )
    smp = io.read_parquet(SAMPLE, columns=["event_id", "company_id"], layout=lay)
    pred = bs.frame(pd.DataFrame(rows).merge(smp, on="event_id", how="left", validate="one_to_one"))
    io.write_parquet(
        pred,
        OUT,
        producer=CHUNK,
        layout=lay,
        description="NA-11 S8: the LLM baseline's test predictions (NA-09's schema; valid answers only)",
    )
    out |= {
        "answered": int(sum(r.ok for r in res)),
        "valid": len(pred),
        "invalid": problems,
        "spent_usd": float(sum(r.row.cost for r in res if r.row is not None and not r.cached)),
    }
    (artifacts_dir(lay) / "llm_test.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["sample"]:
        print(json.dumps(write_sample(), indent=1))
    else:
        print(json.dumps(run(send=args[:1] == ["send"]), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
