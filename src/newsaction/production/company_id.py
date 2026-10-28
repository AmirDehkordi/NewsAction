"""Company identification with activity-matched distractors (PREREG §15 NA-06 operator row (iv); NA-11, before
the freeze). A disclosed robustness probe: it never changes the §8.3 screens, §8.5 or the comparators' labels.

**Why.** NA-06's probe drew the 3 distractors at random among the session's members with the same GICS sector
and tier, while the true company always had selected news that day; choosing the candidate with the most
training-period events then scores about 0.36 without reading the state (the NA-06 verification).

**Design.** NA-06's 400 identification events (val-A D0, masked Call A states), its question, neutral option
keys and company names (``tournament.probes``). The 3 distractors are other members of the session in the same
GICS sector that also have a selected D0 event that session (an event with a Call A state): same tier first,
drawn at random with the seed sha256("2026:company_matched:<event_id>"); then the sector's other event
companies by nearest size rank; then the sector's members without an event by nearest W0 article count that
session.

**Report** (``artifacts/NA-11/company_id_matched.csv``): accuracy per model (the six NA-06 stage-2 models and
local Laya zero-shot) beside NA-06's, and the no-reading baseline of both designs (the candidate with the most
train D0 events; ties shared evenly).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.dm.canary import STATE_COLUMNS, state_info
from newsaction.dm.client import CallResult, CallSpec, DecisionClient
from newsaction.dm.schemas import DecisionRequest
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError, artifacts_dir
from newsaction.tournament import SAMPLES, tournament_config
from newsaction.tournament import probes as pr

PROBE: Final = "company_matched"
TAG: Final = "p_company_matched"
OUT: Final = "dm/production/company_id_matched.parquet"
STATES: Final = "states/callA_d0_E3.parquet"
LOCAL: Final = "local/laya-typed-decisions"


def _members(layout: Layout | None) -> pd.DataFrame:
    p = io.read_parquet(
        "panel/panel_public.parquet",
        columns=["session", "company_id", "member", "is_rep", "sector", "tier", "rank", "split"],
        layout=layout,
    )
    p = p.loc[(p["split"] == "val_a") & p["member"].astype(bool) & p["is_rep"].astype(bool)]
    return p.drop(columns=["member", "is_rep", "split"]).reset_index(drop=True)


def matched_distractors(
    event: Mapping[str, Any],
    members: pd.DataFrame,
    active: set[int],
    articles: Mapping[int, float],
    n: int,
    rng: np.random.Generator,
) -> tuple[list[int], str]:
    """``n`` same-sector members of the session matched on news activity (module docstring)."""
    me = members.loc[members["company_id"] == event["company_id"]]
    if me.empty:
        raise ProductionError(f"{event['event_id']}: the company is not a member of its session")
    own = me.iloc[0]
    sector = members.loc[(members["sector"] == own["sector"]) & (members["company_id"] != own["company_id"])]
    with_event = sector.loc[sector["company_id"].isin(active)]
    same_tier = with_event.loc[with_event["tier"] == own["tier"]].sort_values("company_id")
    if len(same_tier) >= n:
        pick = rng.choice(same_tier["company_id"].to_numpy(), size=n, replace=False)
        return [int(c) for c in pick], "event_sector_tier"
    ids = [int(c) for c in same_tier["company_id"]]
    rest = with_event.loc[~with_event["company_id"].isin(ids)].copy()
    rest["dist"] = (rest["rank"] - own["rank"]).abs()
    ids += [int(c) for c in rest.sort_values(["dist", "company_id"])["company_id"].head(n - len(ids))]
    how = "event_sector_rank"
    if len(ids) < n:
        quiet = sector.loc[~sector["company_id"].isin([*ids, *active])].copy()
        mine = articles.get(int(own["company_id"]), 0.0)
        quiet["dist"] = (quiet["company_id"].map(lambda c: articles.get(int(c), 0.0)) - mine).abs()
        ids += [int(c) for c in quiet.sort_values(["dist", "company_id"])["company_id"].head(n - len(ids))]
        how = "articles_fill"
    if len(ids) < n:
        raise ProductionError(f"{event['event_id']}: fewer than {n} other members in the sector")
    return ids, how


def design(layout: Layout | None = None) -> pd.DataFrame:
    """The matched design on NA-06's identification events (deterministic)."""
    lay = resolve_layout(layout)
    cfg = tournament_config(lay)
    smp = io.read_parquet(SAMPLES, layout=lay)
    ev = smp.loc[smp["identification"].astype(bool), ["event_id", "company_id", "session"]]
    d0 = io.read_parquet(
        "events/events_d0.parquet", columns=["event_id", "company_id", "session"], layout=lay
    )
    st = io.read_parquet(STATES, columns=["event_id"], layout=lay)
    d0 = d0.loc[d0["event_id"].isin(set(st["event_id"]))]
    active = {s: set(g["company_id"].astype(int)) for s, g in d0.groupby("session")}
    wc = io.read_parquet(
        "events/window_counts.parquet", columns=["session", "company_id", "n_articles_w0"], layout=lay
    )
    arts = {
        s: dict(zip(g["company_id"].astype(int), g["n_articles_w0"].astype(float), strict=True))
        for s, g in wc.groupby("session")
    }
    members = {s: g for s, g in _members(lay).groupby("session")}
    names = pr.company_names(
        io.read_parquet("panel/companies.parquet", columns=["company_id", "symbol_id", "name"], layout=lay)
    )
    keys = cfg.probes.option_keys
    rows = []
    for raw in ev.to_dict("records"):
        rec = {str(k): v for k, v in raw.items()}
        rng = pr.probe_rng(cfg.seed, PROBE, str(rec["event_id"]))
        ids, how = matched_distractors(
            rec,
            members[rec["session"]],
            active.get(rec["session"], set()),
            arts.get(rec["session"], {}),
            len(keys) - 1,
            rng,
        )
        pairs, true_key = pr.options(int(rec["company_id"]), ids, keys, rng)
        rows.append(
            {
                **rec,
                "options": json.dumps([[k, int(c), names[int(c)]] for k, c in pairs], ensure_ascii=False),
                "true_key": true_key,
                "draw": how,
            }
        )
    return pd.DataFrame(rows)


def specs(dsg: pd.DataFrame, models: Sequence[str], layout: Layout | None = None) -> list[CallSpec]:
    lay = resolve_layout(layout)
    q = tournament_config(lay).probes.company
    probe_tag = tournament_config(lay).probes.tags.company
    st = io.read_parquet(STATES, columns=list(STATE_COLUMNS), layout=lay).set_index("event_id")
    out = []
    for model in models:
        for rec in dsg.to_dict("records"):
            row = st.loc[rec["event_id"]]
            info = state_info({**row.to_dict(), "event_id": rec["event_id"]}, f"work/{STATES}")
            question = pr.choice_question(q.qid, q.instructions, json.loads(rec["options"]))
            req = DecisionRequest(model=model, state=json.loads(str(row["state_json"])), questions=question)
            out.append(CallSpec(req, info.model_copy(update={"probe": probe_tag}), tag=TAG))
    return out


def answers(dsg: pd.DataFrame, results: Sequence[CallResult]) -> pd.DataFrame:
    truth = dsg.set_index("event_id")["true_key"]
    rows = []
    for r in results:
        qid = next(iter(r.spec.request.questions))
        ans = r.parsed.answers.get(qid) if r.parsed is not None else None
        probs = (
            None
            if ans is None or ans.probs is None
            else dict(zip(r.spec.request.questions[qid].options(), ans.probs, strict=True))
        )
        true_key = str(truth[str(r.spec.info.event_id)])
        rows.append(
            {
                "model": r.spec.request.model,
                "event_id": r.spec.info.event_id,
                "key": r.key,
                "ok": r.ok,
                "valid": probs is not None,
                "true_key": true_key,
                "argmax_key": None if probs is None else max(probs, key=lambda k: probs[k]),
                "p_true": None if probs is None else float(probs[true_key]),
                "cost": None if r.row is None else r.row.cost,
            }
        )
    df = pd.DataFrame(rows)
    df["correct"] = (df["argmax_key"] == df["true_key"]).where(df["valid"])
    return df


def no_reading_baseline(
    dsg: pd.DataFrame, option_col: str, true_col: str, layout: Layout | None = None
) -> float:
    """Accuracy of picking the candidate with the most train D0 events (ties shared evenly)."""
    d0 = io.read_parquet("events/events_d0.parquet", columns=["company_id", "split"], layout=layout)
    counts = d0.loc[d0["split"] == "train", "company_id"].value_counts().to_dict()
    acc = []
    for opts, true_key in zip(dsg[option_col], dsg[true_col], strict=True):
        cands = json.loads(opts) if isinstance(opts, str) else opts
        n = {k: counts.get(int(c), 0) for k, c, _ in cands}
        best = [k for k, v in n.items() if v == max(n.values())]
        acc.append(1.0 / len(best) if true_key in best else 0.0)
    return float(np.mean(acc))


def run(models: Sequence[str], *, send: bool, layout: Layout | None = None) -> dict[str, Any]:
    """Dry run (``send=False``) or the paid run; writes the answers and the summary table on a real run."""
    lay = resolve_layout(layout)
    dsg = design(lay)
    all_specs = specs(dsg, models, lay)
    with DecisionClient(CHUNK, layout=lay) as cl:
        api = [s for s in all_specs if not s.request.model.startswith("local/")]
        proj = cl.dry_run(api)
        out: dict[str, Any] = {
            "events": len(dsg),
            "draw": dsg["draw"].value_counts().to_dict(),
            "projection_usd": proj.usd,
            "n_send": proj.n_send,
            "n_cached": proj.n_cached,
            "budget_left": cl.budget_left(),
        }
        if not send:
            return out
        results = cl.decide(all_specs)
    ans = answers(dsg, results)
    io.write_parquet(
        ans.assign(cost=ans["cost"].astype(float)),
        OUT,
        producer=CHUNK,
        description="NA-11 option (iv): company identification with activity-matched distractors "
        "(NA-06's 400 val-A events; one choice per request)",
        layout=lay,
    )
    smp = io.read_parquet(SAMPLES, layout=lay)
    old = smp.loc[smp["identification"].astype(bool)]
    probes = io.read_parquet("dm/tournament/probes.parquet", layout=lay)
    prior = probes.loc[probes["probe"] == "company"].groupby("model")["correct"].mean()
    table = (
        ans.groupby("model")
        .agg(
            n=("event_id", "size"),
            valid=("valid", "sum"),
            accuracy=("correct", "mean"),
            mean_p_true=("p_true", "mean"),
            cost=("cost", "sum"),
        )
        .reset_index()
    )
    table["accuracy_na06_design"] = table["model"].map(prior)
    table["baseline_matched"] = no_reading_baseline(dsg, "options", "true_key", lay)
    table["baseline_na06_design"] = no_reading_baseline(old, "company_options", "company_true_key", lay)
    table["screen_threshold"] = tournament_config(lay).screens.company_id_max
    table.to_csv(artifacts_dir(lay) / "company_id_matched.csv", index=False)
    out["table"] = table.to_dict("records")
    return out
