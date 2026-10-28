"""NA-11 S6: the frozen production plan's API calls (``configs/production.yaml``; PRD NA-11 S6, AC3, AC5).

Every component (model × state files × splits × question groups, PREREG A2.1) becomes ``dm.client`` requests
(cache, spend ledger, caps, refusals; a test-period state passes only after the freeze). ``project`` dry-runs
each component (PREREG §13: a projection above what the caps leave is a STOP); ``run`` sends them, one
component at a time, at the plan's concurrency.

**Output** (``work/dm/production/<model>.parquet``): one row per (event, source) with ``dm.parse``'s derived
quantities, Q1's nine probabilities (``q1``) and their three-class confidence (``conf3``), validity, build,
tokens, cost and latency; ``source`` is ``a0`` / ``a2`` / ``b2`` / ``b1`` (``analysis.frames.readings_api``)
or ``m`` for the A3.5 market states (``n_hat`` from the nine-level market move with Q1's midpoints, the reason
label and its probability).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io, lock
from newsaction.analysis import metrics as mx
from newsaction.dm.client import CallResult, CallSpec, DecisionClient
from newsaction.dm.parse import Q1_MIDPOINTS
from newsaction.dm.runner import derived_frame, load_states, state_specs
from newsaction.dm.schemas import DecisionRequest, questions_from
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError, artifacts_dir
from newsaction.production.plan import Component, ProductionPlan, load_plan

PRODUCTION_DIR: Final = "dm/production"
CONCURRENCY: Final = 16  # NA-05 item 6: no rate limit seen up to 16
SPLITS_NEEDING_FREEZE: Final = ("test",)


def slug(model: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", model).strip("_")


def source_of(component: str) -> str:
    return component.split("_")[0]


def component_specs(
    plan: ProductionPlan, comp: Component, model: str, layout: Layout | None = None
) -> list[CallSpec]:
    out: list[CallSpec] = []
    for key in comp.states:
        rel = plan.states[key]
        if not (resolve_layout(layout).work / rel).is_file():
            raise ProductionError(
                f"{comp.name}: the state file {rel} does not exist (S4 builds the test ones)"
            )
        rows = load_states(rel, splits=comp.splits, layout=layout)
        if len(rows):
            out += state_specs(rows, rel, model, call=comp.call, groups=comp.groups, tag=f"na11_{comp.name}")
    if any(s.info.split in SPLITS_NEEDING_FREEZE for s in out) and not lock.is_frozen(layout):
        raise ProductionError("test-period requests before the freeze")
    return out


def market_specs(plan: ProductionPlan, model: str, layout: Layout | None = None) -> list[CallSpec]:
    """A3.5: one request per market state with the plan's two market questions."""
    if plan.api.market is None:
        return []
    from newsaction.dm.canary import state_info

    rel = plan.states["market"]
    rows = load_states(rel, splits=plan.api.market.splits, layout=layout)
    qs = questions_from(dict(plan.api.market.questions))
    out = []
    for rec in rows.to_dict("records"):
        req = DecisionRequest(model=model, state=json.loads(rec["state_json"]), questions=qs)
        out.append(CallSpec(req, state_info(rec, f"work/{rel}"), tag="na11_market"))
    return out


def readings(results: Sequence[CallResult], source: str) -> pd.DataFrame:
    """One row per result: derived quantities, Q1's probabilities and their three-class confidence."""
    df = derived_frame(results)
    q1: list[list[float] | None] = []
    for r in results:
        a = r.parsed.answers.get("justified_move") if r.parsed is not None else None
        q1.append(None if a is None or a.probs is None else [float(x) for x in a.probs])
    df["q1"] = pd.Series(q1, dtype=object)
    have = df["q1"].notna()
    conf = np.full(len(df), np.nan)
    if have.any():
        conf[have.to_numpy()] = mx.entropy_confidence(mx.three_class(np.stack(df.loc[have, "q1"].to_list())))
    df["conf3"] = conf
    df["source"] = source
    df["split"] = [r.spec.info.split for r in results]
    return df


def market_readings(results: Sequence[CallResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        rec: dict[str, Any] = {
            "event_id": r.spec.info.event_id,
            "split": r.spec.info.split,
            "ok": r.ok,
            "valid": bool(r.parsed is not None and r.parsed.valid),
            "source": "m",
            "cost": None if r.row is None else r.row.cost,
        }
        if r.parsed is not None:
            mv = r.parsed.answers.get("market_move")
            if mv is not None and mv.probs is not None:
                rec["n_hat"] = float(np.dot(mv.probs, Q1_MIDPOINTS))
            rs = r.parsed.answers.get("market_reason")
            if rs is not None and rs.probs is not None:
                opts = r.spec.request.questions["market_reason"].options()
                i = int(np.argmax(rs.probs))
                rec["label_market_reason"], rec["plabel_market_reason"] = opts[i], float(rs.probs[i])
        rows.append(rec)
    return pd.DataFrame(rows)


def jobs(plan: ProductionPlan, which: str) -> list[tuple[str, str, Component | None]]:
    """(model, component name, component) of ``which``: api, comparators or market."""
    if which == "api":
        return [(plan.api.model, c.name, c) for c in plan.api.components]
    if which == "comparators":
        return [(str(c.model), c.name, c) for c in plan.comparators_core]
    if which == "market":
        return [(plan.api.model, "market", None)]
    raise ProductionError(f"unknown job set {which!r}")


def specs_of(
    plan: ProductionPlan, model: str, comp: Component | None, layout: Layout | None
) -> list[CallSpec]:
    return market_specs(plan, model, layout) if comp is None else component_specs(plan, comp, model, layout)


def project(which: Sequence[str], layout: Layout | None = None) -> dict[str, Any]:
    plan = load_plan()
    out: dict[str, Any] = {"components": [], "usd": 0.0}
    with DecisionClient(CHUNK, offline=True, layout=layout) as cl:
        for w in which:
            for model, name, comp in jobs(plan, w):
                specs = specs_of(plan, model, comp, layout)
                p = cl.dry_run(specs)
                out["components"].append(
                    {
                        "model": model,
                        "component": name,
                        "requests": p.n_requests,
                        "send": p.n_send,
                        "cached": p.n_cached,
                        "usd": p.usd,
                    }
                )
                out["usd"] += p.usd
        out["budget_left"] = cl.budget_left()
    out["fits"] = out["usd"] <= out["budget_left"]
    return out


def run(which: Sequence[str], layout: Layout | None = None, concurrency: int = CONCURRENCY) -> dict[str, Any]:
    """Send every component of ``which`` (each batch re-checks the caps) and write the per-model readings."""
    lay = resolve_layout(layout)
    plan = load_plan()
    frames: dict[str, list[pd.DataFrame]] = {}
    summary: list[dict[str, Any]] = []
    with DecisionClient(CHUNK, layout=lay) as cl:
        for w in which:
            for model, name, comp in jobs(plan, w):
                specs = specs_of(plan, model, comp, lay)
                res = cl.decide(specs, concurrency=concurrency)
                df = market_readings(res) if comp is None else readings(res, source_of(name))
                df["component"] = name
                frames.setdefault(model, []).append(df)
                summary.append(
                    {
                        "model": model,
                        "component": name,
                        "requests": len(res),
                        "ok": int(sum(r.ok for r in res)),
                        "valid": int(df["valid"].sum()),
                        "cost": float(np.nansum(df["cost"].astype(float))),
                    }
                )
                print(json.dumps(summary[-1]), flush=True)
    for model, parts in frames.items():
        df = pd.concat(parts, ignore_index=True)
        for c in df.columns:
            if df[c].dtype == object and c not in ("q1",):
                df[c] = df[c].astype("string")
        io.write_parquet(
            df,
            f"{PRODUCTION_DIR}/{slug(model)}_{'_'.join(which)}.parquet",
            producer=CHUNK,
            description=f"NA-11 S6: {model} readings ({', '.join(which)}) per event and source "
            "(configs/production.yaml)",
            layout=lay,
        )
    (artifacts_dir(lay) / f"production_runs_{'_'.join(which)}.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8"
    )
    return {"components": summary}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd, which = (args[0], args[1:]) if args else ("project", ["api", "comparators", "market"])
    if cmd == "project":
        print(json.dumps(project(which or ["api", "comparators", "market"]), indent=1))
        return 0
    if cmd == "run":
        print(json.dumps(run(which), indent=1))
        return 0
    raise SystemExit("usage: python -m newsaction.production.run project|run [api] [comparators] [market]")


if __name__ == "__main__":
    raise SystemExit(main())
