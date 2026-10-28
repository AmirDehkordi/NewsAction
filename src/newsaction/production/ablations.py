"""NA-11 S8: the ablations of the API comparator (PRD NA-11 S8; PREREG §11.6; ``configs/production.yaml``
``ablations``), core battery.

- **Samples.** Per base state set (``B_D2``: Call B at D2; ``A_D0``: Call A at D0), the plan's ``n`` events of
  val-A, val-B and test with a state, outside the embargo (PREREG §4.2, as NA-04's samples), allocated
  proportionally over (split, tier, month) with the largest remainder and, within a stratum, the smallest
  u = sha256("2026:ablation:<event_id>") (NA-04's ``stratified_sample``).
- **Calls.**
  - ``b2_no_news``: the Call B D2 state without its ``news`` block;
  - ``b2_shuffled``: the Call B D2 state with the ``news`` block of another sampled event of the same split
    and another company (NA-06's derangement, seed sha256("2026:ablation:shuffle:<split>"));
  - ``a0_unmasked``: the unmasked twin of the Call A D0 state, NA-04's builder with ``masked: false`` on the
    articles the masked state kept (NA-09's rebuild, ``baselines/state_articles.parquet``), under the
    registered probe tag ``unmasked_robustness``. The same build with masking must reproduce every sampled
    masked state, and the sampled NA-04 twins must come out unchanged.
- The S6 readings of the same events (``b2``, ``a0``) are the paired reference; nothing here reads an
  outcome.

Outputs: ``work/dm/production/ablation_sample.parquet``, ``work/states/samples/unmasked_robustness.parquet``,
``work/dm/production/<model>_ablations.parquet`` (``run.readings`` plus ``ablation``) and
``artifacts/NA-11/ablation_runs.json``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

from newsaction import io
from newsaction.dm.canary import state_info
from newsaction.dm.client import CallSpec, DecisionClient
from newsaction.dm.runner import load_states, state_specs
from newsaction.dm.schemas import DecisionRequest, questions_from
from newsaction.events import EVENTS_D0, EVENTS_D2, load_events_config
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError, artifacts_dir, record_key_usage
from newsaction.production.plan import ProductionPlan, load_plan
from newsaction.production.run import CONCURRENCY, PRODUCTION_DIR, readings, slug
from newsaction.states import build as sb
from newsaction.states import load_states_config
from newsaction.states.questions import load_battery
from newsaction.tournament import probes as pr

SAMPLE_FILE: Final = f"{PRODUCTION_DIR}/ablation_sample.parquet"
UNMASKED_FILE: Final = "states/samples/unmasked_robustness.parquet"
NA04_TWINS: Final = "states/samples/unmasked.parquet"
STATE_ARTICLES_D0: Final = "baselines/state_articles.parquet"
BASES: Final = {"B_D2": (("B_D2", "B_D2_test"), EVENTS_D2), "A_D0": (("A_D0",), EVENTS_D0)}
SOURCE: Final = {"B_D2": "b2", "A_D0": "a0"}


def out_file(model: str) -> str:
    return f"{PRODUCTION_DIR}/{slug(model)}_ablations.parquet"


def _u(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:15], 16)


def pool(plan: ProductionPlan, base: str, layout: Layout | None = None) -> pd.DataFrame:
    """The state rows of ``base`` in the plan's splits, outside the embargo, with tier and month."""
    keys, events = BASES[base]
    rows = pd.concat(
        [load_states(plan.states[k], splits=plan.ablations.splits, layout=layout) for k in keys],
        ignore_index=True,
    )
    ev = io.read_parquet(
        events, columns=["event_id", "company_id", "tier", "month", "embargo"], layout=layout
    )
    out = rows.merge(ev, on="event_id", how="left", validate="one_to_one")
    if bool(out["tier"].isna().any()):
        raise ProductionError(f"{base}: a state without its event")
    return out.loc[~out["embargo"].astype(bool)].drop(columns=["embargo"]).reset_index(drop=True)


def draw(plan: ProductionPlan, layout: Layout | None = None) -> pd.DataFrame:
    """Both samples (``base``) with the shuffled-news donor of every ``B_D2`` event."""
    a = plan.ablations
    bases = sorted({c.base for c in a.calls})
    parts = []
    for base in bases:
        s = sb.stratified_sample(pool(plan, base, layout), a.n, a.strata, f"{a.seed}:ablation")
        s["base"] = base
        s["donor"] = None
        if base == "B_D2":
            for split, g in s.groupby("split"):
                donors = pr.derangement(
                    g["event_id"].astype(str).tolist(),
                    g["company_id"].astype(int).tolist(),
                    _u(f"{a.seed}:ablation:shuffle:{split}"),
                )
                s.loc[g.index, "donor"] = g["event_id"].map(donors)
        parts.append(s)
    cols = ["event_id", "base", "split", "session", "company_id", "tier", "month", "donor"]
    out = pd.concat(parts, ignore_index=True)[cols]
    out["donor"] = out["donor"].astype("string")
    return out


def write_sample(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    smp = draw(load_plan(), lay)
    io.write_parquet(
        smp,
        SAMPLE_FILE,
        producer=CHUNK,
        layout=lay,
        description="NA-11 S8: the ablation samples (split × tier × month, u = sha256('2026:ablation:<id>')) "
        "and each Call B event's shuffled-news donor",
    )
    return {
        "rows": len(smp),
        "by_base_split": {f"{b}/{s}": len(g) for (b, s), g in smp.groupby(["base", "split"])},
    }


def rebuild_differs(rebuilt: pd.DataFrame, reference: pd.DataFrame) -> int:
    """Reference events whose rebuilt state is missing or has another sha256 (``event_id``,
    ``state_sha256``)."""
    got = rebuilt.set_index("event_id")["state_sha256"]
    ref = reference.set_index("event_id")["state_sha256"]
    return int((ref != got.reindex(ref.index)).sum())


def build_unmasked(layout: Layout | None = None) -> dict[str, Any]:
    """The unmasked twins of the sampled Call A D0 events (NA-04's builder; module docstring checks)."""
    lay = resolve_layout(layout)
    plan = load_plan()
    cfg = load_states_config()
    from newsaction.events import tokens

    tok = tokens.tokenizer(load_events_config().events)
    qtok = sb.question_tokens(load_battery(), tok)
    smp = io.read_parquet(SAMPLE_FILE, layout=lay)
    ids = set(smp.loc[smp["base"] == "A_D0", "event_id"])
    ref = load_states(plan.states["A_D0"], event_ids=ids, layout=lay).set_index("event_id")
    sa = io.read_parquet(STATE_ARTICLES_D0, layout=lay)
    sa = sa.loc[sa["event_id"].isin(ids)].sort_values(["event_id", "rank"])
    keep = {str(e): g["article_id"].astype(str).tolist() for e, g in sa.groupby("event_id")}
    d0 = io.read_parquet(EVENTS_D0, layout=lay)
    ev = d0.loc[d0["event_id"].isin(ids)]
    inp = sb.load_inputs(lay)
    spec = sb.make_spec("callA_d0_E3", "A", "W0", "E3", True, cfg)
    masked, _ = sb.build_event_states(ev, spec, inp, cfg, keep=keep)
    differ = rebuild_differs(masked, ref.reset_index())
    if differ:
        raise ProductionError(f"the masked rebuild differs from NA-04's state for {differ} sampled events")
    spec = sb.make_spec("unmasked_robustness", "A", "W0", "E3", False, cfg)
    um, _ = sb.build_event_states(ev, spec, inp, cfg, keep=keep)
    twins = io.read_parquet(NA04_TWINS, columns=["event_id", "state_sha256"], layout=lay)
    twins = twins.loc[twins["event_id"].isin(ids)]
    if rebuild_differs(um.loc[um["event_id"].isin(twins["event_id"])], twins):
        raise ProductionError("an unmasked twin differs from NA-04's build of the same event")
    if len(um) != len(ids):
        raise ProductionError(f"{len(ids) - len(um)} sampled events have no unmasked state")
    both = twins
    entry = sb.write_states(
        sb.add_tokens(um, tok, qtok),
        UNMASKED_FILE,
        "NA-11 S8: unmasked twins of the 12,000 sampled Call A D0 events (E3; probe unmasked_robustness)",
        lay,
        CHUNK,
    )
    return {"states": len(um), "masked_rebuilt_equal": len(masked), "na04_twins_equal": len(both), **entry}


def _spec(
    rec: Mapping[Any, Any],
    rel: str,
    model: str,
    state: Any,
    questions: Mapping[str, Any],
    probe: str,
    tag: str,
) -> CallSpec:
    info = state_info(rec, f"work/{rel}").model_copy(update={"probe": probe})
    return CallSpec(DecisionRequest(model=model, state=state, questions=dict(questions)), info, tag=tag)


def ablated_state(
    name: str, state: Mapping[str, Any], donor: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The Call B D2 state of ablation ``name``: without its ``news`` block, or with the donor's."""
    if name == "b2_no_news":
        return {k: v for k, v in state.items() if k != "news"}
    if name == "b2_shuffled":
        if donor is None:
            raise ProductionError("b2_shuffled needs the donor's state")
        return pr.shuffled_state(state, donor)
    raise ProductionError(f"unknown ablation {name!r}")


def specs(layout: Layout | None = None) -> dict[str, list[CallSpec]]:
    lay = resolve_layout(layout)
    plan = load_plan()
    a = plan.ablations
    smp = io.read_parquet(SAMPLE_FILE, layout=lay)
    battery = load_battery()
    out: dict[str, list[CallSpec]] = {}
    for call in a.calls:
        tag = f"na11_abl_{call.name}"
        if call.name == "a0_unmasked":
            rows = load_states(UNMASKED_FILE, layout=lay)
            out[call.name] = state_specs(
                rows, UNMASKED_FILE, a.model, call="A", groups=("core",), tag=tag, probe=call.probe
            )
            continue
        keys = BASES[call.base][0]
        drawn = smp.loc[smp["base"] == call.base]
        need = set(drawn["event_id"]) | set(drawn["donor"].dropna())
        frames = {k: load_states(plan.states[k], event_ids=need, layout=lay) for k in keys}
        by_id = {
            str(r["event_id"]): (plan.states[k], r) for k, f in frames.items() for r in f.to_dict("records")
        }
        qs = questions_from(battery.request("B", ("core",)))
        specs_: list[CallSpec] = []
        for rec in drawn.to_dict("records"):
            rel, row = by_id[str(rec["event_id"])]
            donor = None
            if call.name == "b2_shuffled":
                _, drow = by_id[str(rec["donor"])]
                donor = json.loads(drow["state_json"])
                ok = bool(row["third_party_ok_all"]) and bool(drow["third_party_ok_all"])
                row = {**row, "third_party_ok_all": ok}
            state = ablated_state(call.name, json.loads(row["state_json"]), donor)
            specs_.append(_spec(row, rel, a.model, state, qs, call.name, tag))
        out[call.name] = specs_
    return out


def project(layout: Layout | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"calls": {}, "usd": 0.0}
    with DecisionClient(CHUNK, offline=True, layout=layout) as cl:
        for name, sp in specs(layout).items():
            p = cl.dry_run(sp)
            out["calls"][name] = {"requests": p.n_requests, "send": p.n_send, "usd": p.usd}
            out["usd"] += p.usd
        out["budget_left"] = cl.budget_left()
    out["fits"] = out["usd"] <= out["budget_left"]
    return out


def run(layout: Layout | None = None, concurrency: int = CONCURRENCY) -> dict[str, Any]:
    lay = resolve_layout(layout)
    plan = load_plan()
    smp = io.read_parquet(SAMPLE_FILE, layout=lay).set_index("event_id")
    parts, summary = [], []
    with DecisionClient(CHUNK, layout=lay) as cl:
        record_key_usage("before S8 ablations", cl)
        for name, sp in specs(lay).items():
            res = cl.decide(sp, concurrency=concurrency)
            base = next(c.base for c in plan.ablations.calls if c.name == name)
            df = readings(res, SOURCE[base]).assign(ablation=name)
            parts.append(df)
            summary.append(
                {
                    "ablation": name,
                    "requests": len(res),
                    "ok": int(sum(r.ok for r in res)),
                    "valid": int(df["valid"].sum()),
                    "cost": float(df["cost"].astype(float).fillna(0.0).sum()),
                }
            )
            print(json.dumps(summary[-1]), flush=True)
        record_key_usage("after S8 ablations", cl)
    df = pd.concat(parts, ignore_index=True)
    df["donor"] = df["event_id"].map(smp["donor"]).where(df["ablation"] == "b2_shuffled")
    for c in df.columns:
        if df[c].dtype == object and c != "q1":
            df[c] = df[c].astype("string")
    io.write_parquet(
        df,
        out_file(plan.ablations.model),
        producer=CHUNK,
        layout=lay,
        description="NA-11 S8: the API comparator's ablation readings (no news, shuffled news, unmasked)",
    )
    path = artifacts_dir(lay) / "ablation_runs.json"
    path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return {"ablations": summary}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    steps = {"sample": write_sample, "unmasked": build_unmasked, "project": project, "run": run}
    for step in args or ["sample", "unmasked", "project"]:
        if step not in steps:
            raise ProductionError(f"unknown step {step!r} ({' | '.join(steps)})")
        print(json.dumps({step: steps[step]()}, indent=1, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
