"""NA-06 stages: ``python -m newsaction.tournament.run --stage <stage>`` (PRD NA-06; PREREG §8.2–8.3).

Every request goes through ``dm.client.DecisionClient("NA-06")``: its refusals (val-B refused while
``allow_val_b`` is false, the test period refused, third-party, unmasked states only under the registered
``unmasked_twin`` probe), the cache, the dry run against the NA-06 cap and the total cap, and the spend
ledger.
Every answer is cached, so a stage can be re-run without spending again; ``report`` rebuilds every number
from the cache with an offline client.

Stages, in order:
1. ``samples``: the samples (``sample``), the probe designs (company and month options, shuffle donors) and
   the counterfactual selection (``edits``) → ``work/dm/tournament/{samples,counterfactual}.parquet``,
   ``artifacts/NA-06/counterfactual_edits.jsonl`` (the edits, without article text);
2. ``dryrun1``: the stage-1 projection per model → ``artifacts/NA-06/dry_run.json``; exits 2 above
   ``stage1.max_projected_usd`` (PRD S2);
3. ``stage1``: the dry run again, then every eligible API model and the two local Laya checkpoints on the
   stage-1 Call A states (core battery, E3, masked);
4. ``select``: stage-1 daily ICs and the MCS from the cache → ``artifacts/NA-06/{stage1_daily_ic.csv,
   mcs.json}``; the stage-2 models (<= 6 survivors, highest stage-1 IC, ties to the cheaper);
5. ``dryrun2``: the projection of stage 2 and probes a–e for the stage-2 models; exits 2 if it exceeds what
   the NA-06 cap or the total cap leaves (PREREG §13: STOP and ask);
6. ``stage2``: Call A on the 3,000 stage-2 events and Call B on their D2 twins; probes a–e;
7. ``validity``: probe f, core + extended battery on 500 stage-2 events for the top stage-2 model that passes
   the screens (the best overall if none passes);
8. ``report`` (offline): the work files, ``leaderboard.csv``, ``fig3_data.csv``, ``probe_details.csv``,
   ``reading_validity.csv``, ``cache_audit.json``, ``spend.json``, ``summary.json``, the trials and
   ``configs/frozen.yaml`` ``tournament``;
9. ``handoff``: ``allow_val_b: true`` in ``configs/frozen.yaml``, once every call is done (CLAUDE.md C13).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import resource
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, cast

import numpy as np
import pandas as pd
import yaml

from newsaction import io
from newsaction.config import load_frozen, load_splits
from newsaction.dm import CATALOG_FILE, dm_config, is_local
from newsaction.dm.canary import state_info
from newsaction.dm.client import CallResult, CallSpec, DecisionClient, Projection
from newsaction.dm.parse import derive
from newsaction.dm.runner import load_states, state_specs
from newsaction.dm.schemas import DecisionRequest, parse_response
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso
from newsaction.states.questions import Battery, canonical_json, load_battery
from newsaction.tournament import (
    ARTIFACTS,
    CHUNK,
    PROBES,
    PRODUCER,
    SAMPLES,
    STAGE1,
    STAGE2,
    WORK_DIR,
    TournamentConfig,
    TournamentError,
    log_trial,
    tournament_config,
)
from newsaction.tournament import mcs as mcs_mod
from newsaction.tournament import metrics as mx
from newsaction.tournament import probes as pr
from newsaction.tournament import sample as sm
from newsaction.tournament.edits import select as select_edits

COUNTERFACTUAL: Final = f"{WORK_DIR}/counterfactual.parquet"
EDITS_FILE: Final = f"{ARTIFACTS}/counterfactual_edits.jsonl"
DRY_RUN_FILE: Final = f"{ARTIFACTS}/dry_run.json"
DAILY_IC_FILE: Final = mcs_mod.DAILY_IC_FILE
MCS_FILE: Final = mcs_mod.MCS_FILE
LEADERBOARD: Final = f"{ARTIFACTS}/leaderboard.csv"
FIG3: Final = f"{ARTIFACTS}/fig3_data.csv"
PROBE_DETAILS: Final = f"{ARTIFACTS}/probe_details.csv"
VALIDITY_FILE: Final = f"{ARTIFACTS}/reading_validity.csv"
AUDIT_FILE: Final = f"{ARTIFACTS}/cache_audit.json"
SPEND_FILE: Final = f"{ARTIFACTS}/spend.json"
SUMMARY_FILE: Final = f"{ARTIFACTS}/summary.json"
PANEL: Final = "panel/panel_public.parquet"
COMPANIES: Final = "panel/companies.parquet"
ARTICLES: Final = "news/articles_clean.parquet"
MASKED: Final = "states/articles_masked.parquet"
CONTEXT: Final = "states/context_company.parquet"

TAG_S1: Final = "s1"
TAG_S2A: Final = "s2a"
TAG_S2B: Final = "s2b"
TAG_COMPANY: Final = "p_company"
TAG_MONTH: Final = "p_month"
TAG_CF: Final = "p_cf"
TAG_CF_ORIG: Final = "p_cf_orig"
TAG_UNMASKED: Final = "p_unmasked"
TAG_SHUFFLED: Final = "p_shuffled"
TAG_VALIDITY: Final = "p_validity"
STAGE_OF_TAG: Final = {
    TAG_S1: "stage1",
    TAG_S2A: "stage2",
    TAG_S2B: "stage2",
    TAG_COMPANY: "stage2",
    TAG_MONTH: "stage2",
    TAG_CF: "stage2",
    TAG_CF_ORIG: "stage2",
    TAG_UNMASKED: "stage2",
    TAG_SHUFFLED: "stage2",
    TAG_VALIDITY: "validity",
}
TARGET_COLUMNS: Final = ["session", "symbol_id", "z_cc", "e5", "e5_lvl", "y2"]


def log(msg: str) -> None:
    print(f"[{utc_now_iso()[:19]}] {msg}", flush=True)


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2  # bytes on macOS


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- context ---------------------------------------------------------------------------------------------


@dataclass
class Ctx:
    lay: Layout
    cfg: TournamentConfig
    battery: Battery
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, layout: Layout | None = None) -> Ctx:
        lay = resolve_layout(layout)
        return cls(lay, tournament_config(lay), load_battery(lay.configs / "questions_v1.yaml"))

    def client(self, *, offline: bool = False) -> DecisionClient:
        return DecisionClient(CHUNK, offline=offline, layout=self.lay, concurrency=self.cfg.concurrency)

    def _memo(self, key: str, make: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def eligible(self) -> list[str]:
        rows = getattr(load_frozen(self.lay.configs / "frozen.yaml"), "eligible_models", None) or []
        return [str(r["id"]) for r in rows if isinstance(r, Mapping) and r.get("include") is True]

    def samples(self) -> pd.DataFrame:
        return cast(pd.DataFrame, self._memo("samples", lambda: io.read_parquet(SAMPLES, layout=self.lay)))

    def ids(self, flag: str) -> list[str]:
        s = self.samples()
        return s.loc[s[flag].astype(bool), "event_id"].astype(str).tolist()

    def states_a(self) -> pd.DataFrame:
        def make() -> pd.DataFrame:
            ids = self.samples()["event_id"].astype(str).tolist()
            return load_states(
                self.cfg.state_files.call_a, splits=[self.cfg.samples.split], event_ids=ids, layout=self.lay
            )

        return self._memo("states_a", make)  # type: ignore[no-any-return]

    def states_b(self) -> pd.DataFrame:
        def make() -> pd.DataFrame:
            ids = self.samples()["b_event_id"].dropna().astype(str).tolist()
            return load_states(
                self.cfg.state_files.call_b, splits=[self.cfg.samples.split], event_ids=ids, layout=self.lay
            )

        return self._memo("states_b", make)  # type: ignore[no-any-return]

    def states_unmasked(self) -> pd.DataFrame:
        return self._memo(  # type: ignore[no-any-return]
            "unmasked", lambda: load_states(self.cfg.state_files.unmasked, layout=self.lay)
        )

    def counterfactual(self) -> pd.DataFrame:
        return self._memo("cf", lambda: io.read_parquet(COUNTERFACTUAL, layout=self.lay))  # type: ignore[no-any-return]


# --- specs -----------------------------------------------------------------------------------------------


def _rows(states: pd.DataFrame, ids: Sequence[str]) -> pd.DataFrame:
    want = set(ids)
    return states.loc[states["event_id"].isin(want)].reset_index(drop=True)


def call_a_specs(ctx: Ctx, model: str, ids: Sequence[str], tag: str) -> list[CallSpec]:
    return state_specs(
        _rows(ctx.states_a(), ids), ctx.cfg.state_files.call_a, model, call="A", groups=ctx.cfg.groups,
        battery=ctx.battery, tag=tag,
    )  # fmt: skip


def call_b_specs(ctx: Ctx, model: str, ids: Sequence[str]) -> list[CallSpec]:
    return state_specs(
        _rows(ctx.states_b(), ids), ctx.cfg.state_files.call_b, model, call="B", groups=ctx.cfg.groups,
        battery=ctx.battery, tag=TAG_S2B,
    )  # fmt: skip


def _probe_spec(
    rec: Mapping[Any, Any],
    file: str,
    model: str,
    state: Any,
    questions: Mapping[str, Any],
    probe: str,
    tag: str,
) -> CallSpec:
    info = state_info(rec, f"work/{file}").model_copy(update={"probe": probe})
    return CallSpec(DecisionRequest(model=model, state=state, questions=dict(questions)), info, tag=tag)


def choice_probe_specs(ctx: Ctx, model: str, which: str) -> list[CallSpec]:
    """Probe a (``company``) or b (``month``) on the identification events."""
    cfg = ctx.cfg
    s = ctx.samples().set_index("event_id")
    q = cfg.probes.company if which == "company" else cfg.probes.month
    tag, probe = (
        (TAG_COMPANY, cfg.probes.tags.company) if which == "company" else (TAG_MONTH, cfg.probes.tags.month)
    )
    out = []
    for rec in _rows(ctx.states_a(), ctx.ids("identification")).to_dict("records"):
        opts = json.loads(str(s.loc[rec["event_id"], f"{which}_options"]))
        question = pr.choice_question(q.qid, q.instructions, opts)
        out.append(
            _probe_spec(
                rec, cfg.state_files.call_a, model, json.loads(rec["state_json"]), question, probe, tag
            )
        )
    return out


def core_questions(ctx: Ctx, call: str, groups: Sequence[str] | None = None) -> dict[str, Any]:
    from newsaction.dm.schemas import questions_from

    return questions_from(ctx.battery.request(call, list(groups or ctx.cfg.groups)))


def counterfactual_specs(ctx: Ctx, model: str) -> tuple[list[CallSpec], list[CallSpec]]:
    """(edited states, originals outside stage 2): the originals inside stage 2 are stage 2's own Call A."""
    cf = ctx.counterfactual().set_index("event_id")
    rows = _rows(ctx.states_a(), cf.index.astype(str).tolist())
    qs = core_questions(ctx, "A")
    edited = [
        _probe_spec(
            rec, ctx.cfg.state_files.call_a, model,
            json.loads(str(cf.loc[rec["event_id"], "edited_state_json"])), qs,
            ctx.cfg.probes.tags.counterfactual, TAG_CF,
        )
        for rec in rows.to_dict("records")
    ]  # fmt: skip
    outside = cf.index[~cf["in_stage2"].astype(bool)].astype(str).tolist()
    return edited, call_a_specs(ctx, model, outside, TAG_CF_ORIG)


def unmasked_specs(ctx: Ctx, model: str) -> list[CallSpec]:
    return state_specs(
        ctx.states_unmasked(), ctx.cfg.state_files.unmasked, model, call="A", groups=ctx.cfg.groups,
        battery=ctx.battery, tag=TAG_UNMASKED, probe=ctx.cfg.probes.tags.unmasked,
    )  # fmt: skip


def shuffled_specs(ctx: Ctx, model: str) -> list[CallSpec]:
    s = ctx.samples().set_index("event_id")
    states = ctx.states_a().set_index("event_id")
    qs = core_questions(ctx, "A")
    out = []
    for eid in ctx.ids("shuffled"):
        donor = str(s.loc[eid, "shuffle_donor"])
        rec = {"event_id": eid, **states.loc[eid].to_dict()}
        rec["third_party_ok_all"] = bool(rec["third_party_ok_all"]) and bool(
            states.loc[donor, "third_party_ok_all"]
        )
        state = pr.shuffled_state(
            json.loads(rec["state_json"]), json.loads(str(states.loc[donor, "state_json"]))
        )
        out.append(
            _probe_spec(
                rec, ctx.cfg.state_files.call_a, model, state, qs, ctx.cfg.probes.tags.shuffled, TAG_SHUFFLED
            )
        )
    return out


def validity_specs(ctx: Ctx, model: str) -> list[CallSpec]:
    rows = _rows(ctx.states_a(), ctx.ids("reading_validity"))
    specs = state_specs(
        rows, ctx.cfg.state_files.call_a, model, call="A", groups=ctx.cfg.reading_validity.groups,
        battery=ctx.battery, tag=TAG_VALIDITY, probe=ctx.cfg.probes.tags.reading_validity,
    )  # fmt: skip
    return specs


def stage1_specs(ctx: Ctx, model: str) -> list[CallSpec]:
    return call_a_specs(ctx, model, ctx.ids("stage1"), TAG_S1)


def stage2_specs(ctx: Ctx, model: str) -> list[CallSpec]:
    """Stage 2 (Call A on the stage-2 events, Call B on their twins) and probes a–e of one model."""
    twins = ctx.samples()["b_event_id"].dropna().astype(str).tolist()
    edited, originals = counterfactual_specs(ctx, model)
    return [
        *call_a_specs(ctx, model, ctx.ids("stage2"), TAG_S2A),
        *call_b_specs(ctx, model, twins),
        *choice_probe_specs(ctx, model, "company"),
        *choice_probe_specs(ctx, model, "month"),
        *edited,
        *originals,
        *unmasked_specs(ctx, model),
        *shuffled_specs(ctx, model),
    ]


# --- running ---------------------------------------------------------------------------------------------


def record_dry_run(ctx: Ctx, label: str, proj: Projection, extra: Mapping[str, Any] | None = None) -> None:
    path = ctx.lay.root / DRY_RUN_FILE
    runs: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    runs.append(
        {
            "label": label,
            "ts": utc_now_iso(),
            "n_requests": proj.n_requests,
            "n_unique": proj.n_unique,
            "n_cached": proj.n_cached,
            "n_send": proj.n_send,
            "tokens": proj.tokens,
            "usd": proj.usd,
            "by_model": proj.by_model,
            **dict(extra or {}),
        }
    )
    io.atomic_write_bytes(path, (json.dumps(runs, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def print_projection(label: str, proj: Projection, left: float) -> None:
    log(
        f"{label}: {proj.n_send} requests to send ({proj.n_cached} cached); projected ${proj.usd:.4f}; "
        f"left ${left:.4f}"
    )
    for m, v in sorted(proj.by_model.items(), key=lambda kv: -kv[1]["usd"]):
        log(f"  {m:45s} {int(v['calls']):6d} calls  {v['tokens']:12.0f} tokens  ${v['usd']:.5f}")


def run_batch(client: DecisionClient, specs: Sequence[CallSpec], label: str) -> list[CallResult]:
    t0 = time.perf_counter()
    res = client.decide(specs)
    bad = [r for r in res if not r.ok]
    invalid = sum(1 for r in res if r.ok and r.parsed is not None and not r.parsed.valid)
    log(
        f"{label}: {len(res)} in {time.perf_counter() - t0:.1f} s; {len(bad)} failed, {invalid} invalid; "
        f"NA-06 spent ${client.ledger.totals().chunk_usd:.6f}"
    )
    for r in bad[:3]:
        log(f"  failed status={r.status} error={(r.error or '')[:200]}")
    return res


def run_models(
    client: DecisionClient, by_model: Mapping[str, list[CallSpec]], label: str, passes: int = 3
) -> None:
    """Each model's batch; failed calls (never cached) are sent again up to ``passes`` times."""
    for model, specs in by_model.items():
        for n in range(passes):
            res = run_batch(client, specs, f"{label} {model} (pass {n + 1})")
            if all(r.ok for r in res):
                break


# --- stages ----------------------------------------------------------------------------------------------


def members_frame(ctx: Ctx) -> pd.DataFrame:
    p = io.read_parquet(
        PANEL,
        columns=["session", "company_id", "member", "is_rep", "sector", "tier", "rank", "split"],
        layout=ctx.lay,
    )
    p = p.loc[(p["split"] == ctx.cfg.samples.split) & p["member"].astype(bool) & p["is_rep"].astype(bool)]
    return p.drop(columns=["member", "is_rep", "split"]).reset_index(drop=True)


def stage_samples(ctx: Ctx) -> int:
    cfg, lay = ctx.cfg, ctx.lay
    pool = sm.event_pool(cfg, lay)
    smp = sm.build_samples(cfg, lay)
    states = load_states(
        cfg.state_files.call_a, splits=[cfg.samples.split], event_ids=pool["event_id"], layout=lay
    )
    sel, reasons = select_edits(
        states, cfg.samples.counterfactual, cfg.seed, preferred=smp.loc[smp["stage2"], "event_id"]
    )
    log(f"counterfactual: {reasons}; selected {len(sel)} ({int(sel['preferred'].sum())} in stage 2)")
    extra = pool.loc[pool["event_id"].isin(sel["event_id"]) & ~pool["event_id"].isin(smp["event_id"])]
    frame = pd.concat(
        [smp, extra[["event_id", "company_id", "symbol_id", "session", "month", "tier"]]], ignore_index=True
    )
    for flag in (*sm.SAMPLE_FLAGS, "unmasked_twin"):
        frame[flag] = frame[flag].fillna(False).astype(bool)
    frame["counterfactual"] = frame["event_id"].isin(sel["event_id"])
    # probe e: donors; probes a and b: options
    sh = frame.loc[frame["shuffled"]]
    donors = pr.derangement(
        sh["event_id"].astype(str).tolist(),
        sh["company_id"].astype(int).tolist(),
        int(_sha(f"{cfg.seed}:shuffle")[:15], 16),
    )
    frame["shuffle_donor"] = frame["event_id"].map(donors)
    members = members_frame(ctx)
    by_session = {s: g for s, g in members.groupby("session")}
    names = pr.company_names(
        io.read_parquet(COMPANIES, columns=["company_id", "symbol_id", "name"], layout=lay)
    )
    cols: dict[str, list[Any]] = {
        k: []
        for k in ("company_options", "company_true_key", "company_draw", "month_options", "month_true_key")
    }
    for rec in frame.to_dict("records"):
        if rec["identification"]:
            c = pr.company_design(rec, by_session[rec["session"]], names, cfg)
            m = pr.month_design(rec, cfg)
            cols["company_options"].append(json.dumps(c["company_options"], ensure_ascii=False))
            cols["company_true_key"].append(c["company_true_key"])
            cols["company_draw"].append(c["company_draw"])
            cols["month_options"].append(json.dumps(m["month_options"]))
            cols["month_true_key"].append(m["month_true_key"])
        else:
            for k in cols:
                cols[k].append(None)
    for k, v in cols.items():
        frame[k] = v
    frame = frame.sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)
    io.write_parquet(
        frame,
        SAMPLES,
        producer=PRODUCER,
        description="NA-06 samples of val-A D0 events (stage 1/2, probes) with the probe designs",
        layout=lay,
    )
    orig = states.set_index("event_id")
    cf = pd.DataFrame(
        {
            "event_id": sel["event_id"].astype(str),
            "in_stage2": sel["preferred"].astype(bool),
            "polarity": sel["polarity"].astype("int64"),
            "families": sel["families"].astype(str),
            "n_edits": sel["n_edits"].astype("int64"),
            "edits_json": sel["edits_json"].astype(str),
            "state_sha256": [str(orig.loc[e, "state_sha256"]) for e in sel["event_id"]],
            "edited_state_json": [canonical_json(s) for s in sel["edited_state"]],
        }
    )
    cf["edited_state_sha256"] = [_sha(s) for s in cf["edited_state_json"]]
    cf = cf.sort_values("event_id").reset_index(drop=True)
    io.write_parquet(
        cf,
        COUNTERFACTUAL,
        producer=PRODUCER,
        description="NA-06 probe c: original and edited Call A states",
        layout=lay,
    )
    lines = [
        canonical_json(
            {
                "event_id": r["event_id"],
                "in_stage2": bool(r["in_stage2"]),
                "polarity": int(r["polarity"]),
                "families": r["families"],
                "edits": json.loads(r["edits_json"]),
                "state_sha256": r["state_sha256"],
                "edited_state_sha256": r["edited_state_sha256"],
            }
        )
        for r in cf.to_dict("records")
    ]
    io.atomic_write_bytes(lay.root / EDITS_FILE, ("\n".join(lines) + "\n").encode("utf-8"))
    io.register_artifact(
        EDITS_FILE, producer=PRODUCER, description="NA-06 probe c: the edits of each pair", layout=lay
    )
    summary = {
        "rejections": reasons,
        **{f"n_{k}": int(frame[k].sum()) for k in (*sm.SAMPLE_FLAGS, "unmasked_twin", "counterfactual")},
        "n_rows": len(frame),
        "n_b_twins": int(frame["b_event_id"].notna().sum()),
        "company_draw": dict(Counter(x for x in frame["company_draw"] if isinstance(x, str))),
    }
    log(f"samples: {summary}")
    return 0


def api_models(ctx: Ctx) -> list[str]:
    return [m for m in ctx.eligible() if not is_local(m)]


def local_models(ctx: Ctx) -> list[str]:
    return [m for m in ctx.eligible() if is_local(m)]


def stage_dryrun1(ctx: Ctx) -> int:
    with ctx.client() as client:
        specs = [s for m in api_models(ctx) for s in stage1_specs(ctx, m)]
        proj = client.dry_run(specs)
        left = client.budget_left()
    print_projection("stage 1 dry run", proj, left)
    record_dry_run(ctx, "stage1", proj, {"limit_usd": ctx.cfg.stage1.max_projected_usd, "left_usd": left})
    if proj.usd > ctx.cfg.stage1.max_projected_usd:
        log(f"STOP: stage 1 projects ${proj.usd:.4f} > ${ctx.cfg.stage1.max_projected_usd} (PRD NA-06 S2)")
        return 2
    return 0


def stage_stage1(ctx: Ctx, models: Sequence[str] | None = None) -> int:
    rc = stage_dryrun1(ctx)
    if rc:
        return rc
    chosen = list(models or ctx.eligible())
    with ctx.client() as client:
        run_models(client, {m: stage1_specs(ctx, m) for m in chosen if not is_local(m)}, "stage 1")
        run_models(client, {m: stage1_specs(ctx, m) for m in chosen if is_local(m)}, "stage 1 local")
    log(f"stage 1 done; peak RSS {peak_rss_mb():.0f} MB")
    return 0


# --- frames ----------------------------------------------------------------------------------------------


def cached_results(client: DecisionClient, specs: Sequence[CallSpec]) -> list[CallResult | None]:
    """The cached result of each spec, or None (a failed call is not cached); nothing is sent."""
    out: list[CallResult | None] = []
    for s in specs:
        s = client.prepare(s)
        key = client.key(s)
        row = client.cache.get(key)
        if row is None:
            out.append(None)
            continue
        out.append(
            CallResult(
                s,
                key,
                True,
                row,
                parse_response(row.response, s.request.questions),
                200,
                None,
                0,
                row.latency_ms,
            )
        )
    return out


def option_probs(r: CallResult | None, qid: str) -> dict[str, float]:
    if r is None or r.parsed is None or qid not in r.parsed.answers:
        return {}
    a = r.parsed.answers[qid]
    if a.probs is None:
        return {}
    return dict(zip(r.spec.request.questions[qid].options(), a.probs, strict=True))


def result_rows(specs: Sequence[CallSpec], results: Sequence[CallResult | None]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for s, r in zip(specs, results, strict=True):
        base: dict[str, Any] = {
            "model": s.request.model,
            "event_id": s.info.event_id,
            "session": s.info.session,
            "call": s.info.call,
            "tag": s.tag,
            "probe": s.info.probe,
            "ok": r is not None,
            "valid": bool(r is not None and r.parsed is not None and r.parsed.valid),
        }
        if r is not None and r.row is not None:
            base |= {
                "key": r.key,
                "paid_chunk": r.row.chunk,
                "paid_tag": r.row.tag,
                "model_build": r.row.model_build,
                "provider": r.row.provider,
                "input_tokens": r.row.input_tokens,
                "cost": r.row.cost,
                "latency_ms": r.row.latency_ms,
            }
        if r is not None and r.parsed is not None:
            d = derive(r.parsed.answers, s.request.questions)
            base |= {k: v for k, v in d.items() if not k.startswith(("conf_", "pmax_", "entconf_"))}
            base["n_renormalized"] = sum(a.renormalized for a in r.parsed.answers.values())
            q1 = option_probs(r, "justified_move")
            if q1:
                p3 = mx.three_class([[q1[str(i)] for i in range(mx.Q1_LEVELS)]])[0]
                base |= {"p_fall": p3[0], "p_flat": p3[1], "p_rise": p3[2]}
        rows.append(base)
    return pd.DataFrame(rows)


def targets(ctx: Ctx) -> pd.DataFrame:
    """Val-A targets of the sampled events (panel_public, PREREG §5.6; purged by the panel)."""

    def make() -> pd.DataFrame:
        p = io.read_parquet(PANEL, columns=[*TARGET_COLUMNS, "split"], layout=ctx.lay)
        p = p.loc[p["split"] == ctx.cfg.samples.split, TARGET_COLUMNS]
        ev = ctx.samples()[["event_id", "session", "symbol_id", "b_event_id"]]
        out = ev.merge(p, on=["session", "symbol_id"], how="left", validate="one_to_one")
        if out["z_cc"].isna().any():
            raise TournamentError(f"{int(out['z_cc'].isna().sum())} sampled events have no z_cc")
        return out

    return ctx._memo("targets", make)  # type: ignore[no-any-return]


def with_targets(ctx: Ctx, frame: pd.DataFrame, key: str = "event_id") -> pd.DataFrame:
    t = targets(ctx).drop(columns=["session"])
    if key == "b_event_id":
        t = (
            t.dropna(subset=["b_event_id"])
            .drop(columns=["event_id"])
            .rename(columns={"b_event_id": "event_id"})
        )
    else:
        t = t.drop(columns=["b_event_id"])
    return frame.merge(t, on="event_id", how="left", validate="many_to_one")


def ic(ctx: Ctx, frame: pd.DataFrame, signal: str, target: str) -> mx.ICStats:
    m = ctx.cfg.metric
    if signal not in frame.columns:
        return mx.ICStats(math.nan, math.nan, math.nan, 0)
    return mx.ic_stats(mx.daily_ic(frame, signal, target, m.min_names_per_day), m.nw_lags)


def daily(ctx: Ctx, frame: pd.DataFrame, signal: str, target: str) -> pd.Series:
    if signal not in frame.columns:
        return pd.Series(dtype=float)
    return mx.daily_ic(frame, signal, target, ctx.cfg.metric.min_names_per_day)


def stage1_frame(ctx: Ctx, client: DecisionClient, models: Sequence[str]) -> pd.DataFrame:
    parts = []
    for m in models:
        specs = stage1_specs(ctx, m)
        parts.append(result_rows(specs, cached_results(client, specs)))
    return with_targets(ctx, pd.concat(parts, ignore_index=True))


def stage1_table(ctx: Ctx, s1: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per model: stage-1 ICs, validity, cost; and the long daily IC (model, session, ic, n)."""
    rows, daily_rows = [], []
    for m, g in s1.groupby("model", sort=False):
        d = daily(ctx, g, "n_hat", ctx.cfg.metric.primary_target)
        n_day = g.dropna(subset=["n_hat"]).groupby("session").size() if "n_hat" in g else pd.Series(dtype=int)
        for s, v in d.items():
            daily_rows.append({"model": m, "session": s, "ic": v, "n": int(n_day.get(s, 0))})
        a = ic(ctx, g, "n_hat", ctx.cfg.metric.primary_target)
        b = ic(ctx, g, "n_hat", ctx.cfg.metric.secondary_target)
        paid = g.loc[g["paid_chunk"].eq(CHUNK)] if "paid_chunk" in g else g.iloc[0:0]
        rows.append(
            {
                "model": m,
                "n1": len(g),
                "ok1": int(g["ok"].sum()),
                "valid1": int(g["valid"].sum()),
                "q1_valid1": int(g["n_hat"].notna().sum()) if "n_hat" in g else 0,
                "invalid_rate1": 1.0 - g["valid"].mean(),
                **a.as_dict("ic1_z_cc"),
                **b.as_dict("ic1_e5"),
                "cost_per_1000_a": 1000.0 * float(paid["cost"].mean()) if len(paid) else 0.0,
                "latency_p50_ms_1": mx.quantiles(paid["latency_ms"])[0] if len(paid) else math.nan,
                "latency_p95_ms_1": mx.quantiles(paid["latency_ms"])[1] if len(paid) else math.nan,
                "providers1": json.dumps(dict(Counter(paid["provider"].dropna()))) if len(paid) else "{}",
                "builds1": json.dumps(sorted(set(paid["model_build"].dropna()))) if len(paid) else "[]",
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(daily_rows)


def run_mcs(
    ctx: Ctx, daily_ic: pd.DataFrame, statistic: str | None = None, seed: int | None = None
) -> mcs_mod.MCSResult:
    c = ctx.cfg.mcs
    losses = mcs_mod.loss_matrix(daily_ic)
    return mcs_mod.mcs(
        losses, alpha=c.alpha, reps=c.reps, block=c.block, seed=ctx.cfg.seed if seed is None else seed,
        statistic=(statistic or c.statistic),  # type: ignore[arg-type]
    )  # fmt: skip


def choose_stage2(table: pd.DataFrame, survivors: Sequence[str], n: int) -> list[str]:
    """<= n survivors with the highest stage-1 IC (z_cc); ties (equal to 12 decimals) to the cheaper."""
    t = table.loc[table["model"].isin(list(survivors))].copy()
    t["_ic"] = t["ic1_z_cc"].round(12)
    t = t.sort_values(["_ic", "cost_per_1000_a", "model"], ascending=[False, True, True], kind="mergesort")
    return t["model"].head(n).astype(str).tolist()


def stage_select(ctx: Ctx) -> int:
    models = ctx.eligible()
    with ctx.client(offline=True) as client:
        s1 = stage1_frame(ctx, client, models)
    table, daily_ic = stage1_table(ctx, s1)
    have = table.loc[table["ic1_z_cc_days"] > 0, "model"].tolist()
    missing = sorted(set(models) - set(have))
    daily_ic = daily_ic.loc[daily_ic["model"].isin(have)]
    io.atomic_write_bytes(
        ctx.lay.root / DAILY_IC_FILE, daily_ic.to_csv(index=False, lineterminator="\n").encode()
    )
    res = run_mcs(ctx, daily_ic)
    alt = run_mcs(ctx, daily_ic, statistic="max" if ctx.cfg.mcs.statistic == "R" else "R")
    chosen = choose_stage2(table, res.included, ctx.cfg.stage2.max_models)
    out = {
        "stage1": res.as_dict(),
        "robustness_other_statistic": alt.as_dict(),
        "no_daily_ic": missing,
        "n_common_days": int(mcs_mod.loss_matrix(daily_ic).shape[0]),
        "stage2_models": chosen,
    }
    io.atomic_write_bytes(ctx.lay.root / MCS_FILE, (json.dumps(out, indent=1) + "\n").encode("utf-8"))
    for f, d in ((DAILY_IC_FILE, "NA-06 stage-1 daily IC (MCS input)"), (MCS_FILE, "NA-06 stage-1 MCS")):
        io.register_artifact(f, producer=PRODUCER, description=d, layout=ctx.lay)
    pd.set_option("display.width", 220)
    log(
        "stage 1:\n"
        + table[
            ["model", "ic1_z_cc", "ic1_z_cc_t", "ic1_z_cc_days", "ic1_e5", "invalid_rate1", "cost_per_1000_a"]
        ]
        .sort_values("ic1_z_cc", ascending=False)
        .to_string(index=False)
    )
    log(f"MCS ({res.statistic}, {res.n_days} days): {res.included}")
    log(f"MCS ({alt.statistic}, robustness): {alt.included}")
    log(f"stage-2 models: {chosen}")
    return 0


def stage2_models(ctx: Ctx) -> list[str]:
    rec = json.loads((ctx.lay.root / MCS_FILE).read_text(encoding="utf-8"))
    return [str(m) for m in rec["stage2_models"]]


def stage_dryrun2(ctx: Ctx) -> int:
    models = stage2_models(ctx)
    with ctx.client() as client:
        specs = [s for m in models for s in stage2_specs(ctx, m)]
        proj = client.dry_run([s for s in specs if not is_local(s.request.model)])
        left = client.budget_left()
        t = client.ledger.totals()
    print_projection("stage 2 + probes dry run", proj, left)
    record_dry_run(ctx, "stage2", proj, {"left_usd": left, "models": models})
    log(
        f"spent so far: NA-06 ${t.chunk_usd:.4f}, all chunks ${t.total_usd:.4f}; after this projection all "
        f"chunks would be at ${t.total_usd + proj.usd:.4f}"
    )
    if proj.usd > left:
        log(f"STOP: stage 2 projects ${proj.usd:.4f} > ${left:.4f} left (PREREG §13): ask the operator")
        return 2
    return 0


def stage_stage2(ctx: Ctx) -> int:
    rc = stage_dryrun2(ctx)
    if rc:
        return rc
    models = stage2_models(ctx)
    with ctx.client() as client:
        run_models(client, {m: stage2_specs(ctx, m) for m in models}, "stage 2")
    log(f"stage 2 done; peak RSS {peak_rss_mb():.0f} MB")
    return 0


# --- stage 2 and probe frames ----------------------------------------------------------------------------


@dataclass
class ModelFrames:
    a: pd.DataFrame  # stage-2 Call A, with targets
    b: pd.DataFrame  # stage-2 Call B (D2 twins), with targets
    probes: pd.DataFrame  # every probe answer of the model


def choice_rows(ctx: Ctx, client: DecisionClient, model: str, which: str) -> pd.DataFrame:
    specs = choice_probe_specs(ctx, model, which)
    res = cached_results(client, specs)
    df = result_rows(specs, res)
    s = ctx.samples().set_index("event_id")
    qid = ctx.cfg.probes.company.qid if which == "company" else ctx.cfg.probes.month.qid
    probs = [option_probs(r, qid) for r in res]
    truth = [str(s.loc[e, f"{which}_true_key"]) for e in df["event_id"]]
    df["true_key"] = truth
    df["argmax_key"] = [max(p, key=lambda k: p[k]) if p else None for p in probs]
    df["p_true"] = [p.get(k, math.nan) if p else math.nan for p, k in zip(probs, truth, strict=True)]
    df["correct"] = [
        (a == k) if a is not None else None for a, k in zip(df["argmax_key"], truth, strict=True)
    ]
    df["probe"] = which
    return df


def model_frames(ctx: Ctx, client: DecisionClient, model: str) -> ModelFrames:
    twins = ctx.samples()["b_event_id"].dropna().astype(str).tolist()
    sa = call_a_specs(ctx, model, ctx.ids("stage2"), TAG_S2A)
    a = with_targets(ctx, result_rows(sa, cached_results(client, sa)))
    sb = call_b_specs(ctx, model, twins)
    b = with_targets(ctx, result_rows(sb, cached_results(client, sb)), key="b_event_id")
    parts = [choice_rows(ctx, client, model, "company"), choice_rows(ctx, client, model, "month")]
    edited, originals = counterfactual_specs(ctx, model)
    e = result_rows(edited, cached_results(client, edited))
    e["probe"] = "counterfactual_edit"
    o_out = result_rows(originals, cached_results(client, originals))
    cf = ctx.counterfactual()
    o_in = a.loc[a["event_id"].isin(cf.loc[cf["in_stage2"].astype(bool), "event_id"])].drop(
        columns=[c for c in ("z_cc", "e5", "e5_lvl", "y2") if c in a.columns]
    )
    o = pd.concat([o_in, o_out], ignore_index=True)
    o["probe"] = "counterfactual_orig"
    pol = cf.set_index("event_id")["polarity"]
    for d in (e, o):
        d["polarity"] = d["event_id"].map(pol)
    su = unmasked_specs(ctx, model)
    u = with_targets(ctx, result_rows(su, cached_results(client, su)))
    u["probe"] = "unmasked"
    twins_a = a.loc[a["event_id"].isin(ctx.ids("unmasked_twin"))].copy()
    twins_a["probe"] = "masked"
    ss = shuffled_specs(ctx, model)
    sh = with_targets(ctx, result_rows(ss, cached_results(client, ss)))
    sh["probe"] = "shuffled"
    sh["donor_event_id"] = sh["event_id"].map(ctx.samples().set_index("event_id")["shuffle_donor"])
    sv = validity_specs(ctx, model)
    v = result_rows(sv, cached_results(client, sv))
    v = v.loc[v["ok"]]
    v["probe"] = "reading_validity"
    parts += [e, o, u, twins_a, sh, v]
    return ModelFrames(a=a, b=b, probes=pd.concat(parts, ignore_index=True))


def stage2_metrics(ctx: Ctx, f: ModelFrames) -> dict[str, Any]:
    m = ctx.cfg.metric
    a, b = f.a, f.b
    out: dict[str, Any] = {}
    out |= ic(ctx, a, "n_hat", m.primary_target).as_dict("ic2_a_z_cc")
    out |= ic(ctx, a, "n_hat", m.secondary_target).as_dict("ic2_a_e5")
    out |= ic(ctx, b, "j", "y2").as_dict("ic2_j_y2")
    out |= ic(ctx, b, "n_hat", m.primary_target).as_dict("ic2_b_z_cc")
    probs = a[["p_fall", "p_flat", "p_rise"]].to_numpy(dtype=float) if "p_fall" in a else np.empty((0, 3))
    keep = np.isfinite(probs).all(axis=1) if len(probs) else np.zeros(0, dtype=bool)
    out["ece2_a_z_cc"] = mx.ece(
        probs[keep], mx.realized_class(a.loc[keep, m.primary_target], m.class_band), m.ece_bins
    )
    out["ece2_a_e5_lvl"] = mx.ece(
        probs[keep], mx.realized_class(a.loc[keep, "e5_lvl"], m.class_band), m.ece_bins
    )
    for name, d, tags in (("a", a, (TAG_S2A, TAG_S1)), ("b", b, (TAG_S2B,))):
        paid = (
            d.loc[d["paid_chunk"].eq(CHUNK) & d["paid_tag"].isin(tags)] if "paid_chunk" in d else d.iloc[0:0]
        )
        out[f"cost_per_1000_{name}2"] = 1000.0 * float(paid["cost"].mean()) if len(paid) else 0.0
        out[f"n2_{name}"] = len(d)
        out[f"invalid_rate2_{name}"] = 1.0 - float(d["valid"].mean()) if len(d) else math.nan
        out[f"failed2_{name}"] = int((~d["ok"]).sum())
    both = pd.concat([a, b])
    lat = (
        both.loc[both["paid_chunk"].eq(CHUNK), "latency_ms"]
        if "paid_chunk" in both
        else pd.Series(dtype=float)
    )
    out["latency_p50_ms"], out["latency_p95_ms"] = mx.quantiles(lat)
    return out


def probe_metrics(ctx: Ctx, f: ModelFrames) -> dict[str, Any]:
    cfg = ctx.cfg
    p = f.probes
    out: dict[str, Any] = {}
    for which in ("company", "month"):
        d = p.loc[p["probe"] == which]
        valid = d.loc[d["argmax_key"].notna()]
        n = len(valid)
        out[f"{which}_id_acc"] = float(valid["correct"].astype(bool).mean()) if n else math.nan
        out[f"{which}_id_p_true"] = float(valid["p_true"].mean()) if n else math.nan
        out[f"{which}_id_n"] = n
    e = p.loc[p["probe"] == "counterfactual_edit"].set_index("event_id")
    o = p.loc[p["probe"] == "counterfactual_orig"].set_index("event_id")
    pairs = pd.DataFrame(
        {"orig": o.get("n_hat"), "edit": e.get("n_hat"), "polarity": e.get("polarity")}
    ).dropna(subset=["orig", "edit"])
    flip, n_flip = pr.flip_rate(pairs["orig"], pairs["edit"], cfg.screens.flip_min_abs_n_hat)
    out["flip_rate"], out["flip_n"] = flip, n_flip
    out["flip_pairs_valid"] = len(pairs)
    out["edit_mean_shift"] = (
        float(((pairs["edit"] - pairs["orig"]) * -pairs["polarity"]).mean()) if len(pairs) else math.nan
    )
    masked = p.loc[p["probe"] == "masked"]
    unmasked = p.loc[p["probe"] == "unmasked"]
    dm = daily(ctx, masked, "n_hat", cfg.metric.primary_target)
    du = daily(ctx, unmasked, "n_hat", cfg.metric.primary_target)
    lags = cfg.metric.nw_lags
    out |= mx.ic_stats(dm, lags).as_dict("ic_masked")
    out |= mx.ic_stats(du, lags).as_dict("ic_unmasked")
    out |= mx.paired(du, dm, lags).as_dict("unmasked_minus_masked")
    sh = p.loc[p["probe"] == "shuffled"]
    out |= ic(ctx, sh, "n_hat", cfg.metric.primary_target).as_dict("ic_shuffled")
    sc = pr.screens(
        company_id_acc=out["company_id_acc"],
        flip=out["flip_rate"],
        unmasked_minus_masked=out["unmasked_minus_masked"],
        unmasked_t=out["unmasked_minus_masked_t"],
        shuffled_t=out["ic_shuffled_t"],
        cfg=cfg.screens,
    )
    out |= {f"screen_{k}": v for k, v in sc.items()}
    out["contamination_score"] = out["company_id_acc"] - 0.25
    return out


def probe_details(model_metrics: Mapping[str, Mapping[Any, Any]]) -> pd.DataFrame:
    """One row per (model, probe): the value the screen reads, its t (where one applies), n and the result."""
    rows = []
    for m, r in model_metrics.items():
        rows += [
            {"model": m, "probe": "company_identification", "value": r["company_id_acc"], "t": math.nan,
             "n": r["company_id_n"], "passed": r["screen_company_identification"]},
            {"model": m, "probe": "month_identification", "value": r["month_id_acc"], "t": math.nan,
             "n": r["month_id_n"], "passed": None},
            {"model": m, "probe": "counterfactual_flip", "value": r["flip_rate"], "t": math.nan,
             "n": r["flip_n"], "passed": r["screen_counterfactual_flip"]},
            {"model": m, "probe": "masked_vs_unmasked", "value": r["unmasked_minus_masked"],
             "t": r["unmasked_minus_masked_t"], "n": r["unmasked_minus_masked_days"],
             "passed": r["screen_masked_vs_unmasked"]},
            {"model": m, "probe": "shuffled_news", "value": r["ic_shuffled"], "t": r["ic_shuffled_t"],
             "n": r["ic_shuffled_days"], "passed": r["screen_shuffled_news"]},
        ]  # fmt: skip
    return pd.DataFrame(rows)


# --- validity (probe f) ----------------------------------------------------------------------------------


def top_model(ctx: Ctx, table: pd.DataFrame) -> str:
    """The stage-2 model with the highest stage-2 Call A IC among those that pass every screen (else the
    highest overall)."""
    t = table.dropna(subset=["ic2_a_z_cc"]).sort_values(["ic2_a_z_cc", "model"], ascending=[False, True])
    passing = t.loc[t["screen_all"].astype(bool)]
    return str((passing if len(passing) else t)["model"].iloc[0])


def stage2_table(ctx: Ctx, client: DecisionClient) -> tuple[pd.DataFrame, dict[str, ModelFrames]]:
    rows, frames = [], {}
    for m in stage2_models(ctx):
        f = model_frames(ctx, client, m)
        frames[m] = f
        rows.append({"model": m, **stage2_metrics(ctx, f), **probe_metrics(ctx, f)})
    return pd.DataFrame(rows), frames


def stage_validity(ctx: Ctx) -> int:
    with ctx.client(offline=True) as client:
        table, _ = stage2_table(ctx, client)
    model = top_model(ctx, table)
    with ctx.client() as client:
        specs = validity_specs(ctx, model)
        proj = client.dry_run([s for s in specs if not is_local(s.request.model)])
        left = client.budget_left()
        print_projection(f"reading validity ({model}) dry run", proj, left)
        record_dry_run(ctx, "validity", proj, {"left_usd": left, "model": model})
        if proj.usd > left:
            log(f"STOP: reading validity projects ${proj.usd:.4f} > ${left:.4f} left (PREREG §13)")
            return 2
        run_models(client, {model: specs}, "reading validity")
    return 0


def reference_tags(ctx: Ctx, events: pd.DataFrame) -> pd.DataFrame:
    """The main article of each state (its first news item, matched to NA-04's masked text) with its vendor
    tags, and the earnings-calendar flag of the event (PREREG A2.5)."""
    ev = io.read_parquet(sm.EVENTS_D0, columns=["event_id", "news_w0"], layout=ctx.lay)
    ev = ev.loc[ev["event_id"].isin(events["event_id"])].set_index("event_id")
    ids = [str(it["id"]) for e in ev.index for it in ev.loc[e, "news_w0"]]
    am = io.read_parquet(MASKED, columns=["id", "title_masked", "snippet_masked"], layout=ctx.lay)
    am = am.loc[am["id"].isin(ids)].set_index("id")
    tags = io.read_parquet(
        ARTICLES, columns=["id", "tag_type", "tag_quantified", "tag_rumor"], layout=ctx.lay
    )
    tags = tags.loc[tags["id"].isin(ids)].set_index("id")
    states = ctx.states_a().set_index("event_id")
    ctxc = io.read_parquet(CONTEXT, columns=["session", "symbol_id", "ctx_earnings_w0"], layout=ctx.lay)
    rows = []
    for rec in events.to_dict("records"):
        first = json.loads(str(states.loc[rec["event_id"], "state_json"]))["news"][0]
        main = next(
            (
                str(it["id"])
                for it in ev.loc[rec["event_id"], "news_w0"]
                if str(it["id"]) in am.index
                and am.loc[str(it["id"]), "title_masked"] == first["headline"]
                and am.loc[str(it["id"]), "snippet_masked"] == first["snippet"]
            ),
            None,
        )
        t = tags.loc[main] if main is not None else None
        rows.append(
            {
                "event_id": rec["event_id"],
                "session": rec["session"],
                "symbol_id": rec["symbol_id"],
                "main_article": main,
                "tag_type": None if t is None else t["tag_type"],
                "tag_quantified": None if t is None else t["tag_quantified"],
                "tag_rumor": None if t is None else t["tag_rumor"],
            }
        )
    out = pd.DataFrame(rows).merge(ctxc, on=["session", "symbol_id"], how="left")
    return out.rename(columns={"ctx_earnings_w0": "earnings_w0"})


# --- report ----------------------------------------------------------------------------------------------


def catalog_prices(ctx: Ctx) -> dict[str, float]:
    snap = json.loads((ctx.lay.root / CATALOG_FILE).read_text(encoding="utf-8"))
    return {str(m["id"]): float(m["pricing"].get("prompt") or 0.0) for m in snap["models"]}


def spend_report(ctx: Ctx, client: DecisionClient) -> dict[str, Any]:
    """Spend by stage and model (the cache rows NA-06 paid for), realized cost ratios, the ledger and the
    dry runs."""
    rows = client.cache.rows(chunk=CHUNK)
    prices = catalog_prices(ctx)
    df = pd.DataFrame(
        [
            {
                "model": r.model,
                "tag": r.tag,
                "cost": r.cost,
                "tokens": r.input_tokens,
                "local": is_local(r.model),
            }
            for r in rows
        ]
    )
    t = client.ledger.totals()
    out: dict[str, Any] = {
        "ledger": {
            "na06_usd": t.chunk_usd,
            "total_usd": t.total_usd,
            "by_chunk": t.by_chunk,
            "cap_usd": t.chunk_cap_usd,
        },
        "reconcile": client.reconcile(),
        "n_rows": len(df),
    }
    if df.empty:
        return out
    df["stage"] = df["tag"].map(STAGE_OF_TAG).fillna("other")
    df["priced"] = [prices.get(m, 0.0) * (tok or 0) for m, tok in zip(df["model"], df["tokens"], strict=True)]
    api = df.loc[~df["local"]]
    out["actual_by_stage"] = api.groupby("stage")["cost"].sum().to_dict()
    out["calls_by_stage"] = df.groupby("stage").size().to_dict()
    out["by_model"] = {
        m: {
            "usd": float(g["cost"].sum()),
            "calls": len(g),
            "cost_ratio": float(g["cost"].sum() / g["priced"].sum()) if g["priced"].sum() > 0 else None,
            "cost_ratio_max": float((g["cost"] / g["priced"]).max()) if (g["priced"] > 0).all() else None,
        }
        for m, g in api.groupby("model")
    }
    runs = json.loads((ctx.lay.root / DRY_RUN_FILE).read_text(encoding="utf-8"))
    first: dict[str, dict[str, Any]] = {}
    for r in runs:  # the first projection of a stage with something to send
        if r["n_send"] > 0 and r["label"] not in first:
            first[r["label"]] = r
    out["projection_vs_actual"] = {}
    for label, r in first.items():
        actual = float(out["actual_by_stage"].get(label, 0.0))
        by_model = {}
        for m, v in r["by_model"].items():
            act = float(api.loc[(api["model"] == m) & (api["stage"] == label), "cost"].sum())
            by_model[m] = {
                "projected": v["usd"],
                "actual": act,
                "actual_over_projected": act / v["usd"] if v["usd"] else None,
            }
        out["projection_vs_actual"][label] = {
            "projected": r["usd"],
            "actual": actual,
            "actual_over_projected": actual / r["usd"] if r["usd"] else None,
            "within_20pct": bool(r["usd"] and abs(actual / r["usd"] - 1.0) <= 0.20),
            "by_model": by_model,
        }
    proj_total = sum(r["usd"] for r in first.values())
    out["projection_total"] = proj_total
    out["actual_total"] = float(api["cost"].sum())
    out["actual_over_projected_total"] = out["actual_total"] / proj_total if proj_total else None
    return out


def cache_audit(ctx: Ctx, client: DecisionClient) -> dict[str, Any]:
    """AC1: every NA-06 cache row is a val-A state after the embargo (or a probe of one); no val-B, no
    test."""
    splits = load_splits(ctx.lay.configs / "splits.yaml")
    va = splits.splits[ctx.cfg.samples.split]
    first_ok = sm.embargo_sessions(ctx.cfg.samples.split)[-1].date()
    rows = client.cache.rows(chunk=CHUNK)
    bad: list[dict[str, Any]] = []
    sessions: list[date] = []
    by_probe: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    for r in rows:
        meta = r.meta
        by_source[str(meta.get("source"))] += 1
        by_probe[str(meta.get("probe"))] += 1
        if meta.get("source") != "states":
            bad.append({"key": r.key, "why": "not a state-file row"})
            continue
        s = date.fromisoformat(str(meta["session"]))
        sessions.append(s)
        if meta.get("split") != ctx.cfg.samples.split or not (first_ok < s <= va.end):
            bad.append({"key": r.key, "session": s.isoformat(), "split": meta.get("split")})
    smp = ctx.samples()
    donors = smp.loc[smp["shuffled"], "shuffle_donor"].astype(str)
    donor_sessions = smp.set_index("event_id").loc[donors, "session"]
    donors_ok = bool(((donor_sessions > first_ok) & (donor_sessions <= va.end)).all())
    return {
        "chunk": CHUNK,
        "n_rows": len(rows),
        "by_source": dict(by_source),
        "by_probe": dict(by_probe),
        "min_session": min(sessions).isoformat() if sessions else None,
        "max_session": max(sessions).isoformat() if sessions else None,
        "allowed": {
            "after": first_ok.isoformat(),
            "through": va.end.isoformat(),
            "split": ctx.cfg.samples.split,
        },
        "violations": bad[:20],
        "n_violations": len(bad),
        "shuffle_donors_in_val_a_after_embargo": donors_ok,
        "ok": not bad and donors_ok,
    }


def _yaml_list(xs: Sequence[str]) -> str:
    return "[" + ", ".join(json.dumps(x) for x in xs) + "]"


def write_frozen_tournament(ctx: Ctx, entry: Mapping[str, Any]) -> None:
    """Replace the ``tournament:`` section of configs/frozen.yaml; nothing else changes."""
    path = ctx.lay.configs / "frozen.yaml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if re.match(r"^tournament:", ln))
    end = start + 1
    while end < len(lines) and lines[end].startswith((" ", "\t")):
        end += 1
    block = ["tournament:          # NA-06: PREREG §8.2–8.3 (artifacts/NA-06/leaderboard.csv, mcs.json)\n"]
    for k, v in entry.items():
        if isinstance(v, list):
            block.append(f"  {k}: {_yaml_list([str(x) for x in v])}\n")
        elif isinstance(v, bool):
            block.append(f"  {k}: {'true' if v else 'false'}\n")
        else:
            block.append(f"  {k}: {json.dumps(v) if isinstance(v, str) else v}\n")
    new = "".join(lines[:start] + block + lines[end:])
    parsed = yaml.safe_load(new)["tournament"]
    if {k: parsed[k] for k in entry} != dict(entry):
        raise TournamentError("frozen.yaml tournament block does not round-trip")
    io.atomic_write_bytes(path, new.encode("utf-8"))


def log_trials(ctx: Ctx, table: pd.DataFrame, validity: Mapping[str, Any]) -> int:
    base = {
        "encoding": ctx.cfg.encoding,
        "groups": list(ctx.cfg.groups),
        "questions_sha256": _sha((ctx.lay.configs / "questions_v1.yaml").read_text(encoding="utf-8")),
        "config_sha256": _sha((ctx.lay.configs / "tournament.yaml").read_text(encoding="utf-8")),
        "samples_sha256": io.load_manifest(ctx.lay)["artifacts"][f"work/{SAMPLES}"]["sha256"],
    }
    plan = {
        "dm_tournament_stage1": ["ic1_z_cc", "ic1_e5"],
        "dm_tournament_stage2": ["ic2_a_z_cc", "ic2_a_e5", "ic2_j_y2", "ic2_b_z_cc", "ece2_a_z_cc"],
        "dm_tournament_probe": [
            "company_id_acc", "month_id_acc", "flip_rate", "unmasked_minus_masked", "ic_shuffled",
        ],
    }  # fmt: skip
    n = 0
    for kind, metrics_ in plan.items():
        for rec in table.to_dict("records"):
            for metric in metrics_:
                v = rec.get(metric)
                if v is None or (kind != "dm_tournament_stage1" and not rec.get("stage2")):
                    continue
                params = {**base, "model": rec["model"], "kind": kind, "metric": metric}
                n += log_trial(kind, str(rec["model"]), params, "val_a", metric, float(v), layout=ctx.lay)
    for comp, v in validity.get("agreement", {}).items():
        params = {**base, "model": validity["model"], "metric": f"agreement_{comp}"}
        n += log_trial(
            "dm_reading_validity", validity["model"], params, "val_a", f"agreement_{comp}", v, layout=ctx.lay
        )
    return n


def leaderboard(ctx: Ctx, s1: pd.DataFrame, res: Mapping[str, Any], s2: pd.DataFrame) -> pd.DataFrame:
    prices = catalog_prices(ctx)
    costcfg = {m: c.billing_basis for m, c in dm_config(ctx.lay).costmodel.models.items()}
    mcs1 = res["stage1"]
    lb = s1.copy()
    lb.insert(1, "kind", ["local" if is_local(m) else "api" for m in lb["model"]])
    lb.insert(
        2,
        "price_prompt_usd_per_m",
        [0.0 if is_local(m) else prices.get(m, math.nan) * 1e6 for m in lb["model"]],
    )
    lb.insert(3, "billing_basis", [("local" if is_local(m) else costcfg.get(m, "")) for m in lb["model"]])
    lb["mcs_pvalue"] = lb["model"].map(mcs1["pvalues"])
    lb["mcs_member"] = lb["model"].isin(mcs1["included"])
    lb["stage2"] = lb["model"].isin(res["stage2_models"])
    lb = lb.merge(s2, on="model", how="left")
    lb["screens_pass"] = lb.get("screen_all")
    lb = lb.sort_values(["ic1_z_cc", "model"], ascending=[False, True], kind="mergesort").reset_index(
        drop=True
    )
    lb.insert(1, "rank1", np.arange(1, len(lb) + 1))
    return lb


def stage_report(ctx: Ctx) -> int:
    t0 = time.perf_counter()
    lay = ctx.lay
    models = ctx.eligible()
    res = json.loads((lay.root / MCS_FILE).read_text(encoding="utf-8"))
    with ctx.client(offline=True) as client:
        s1 = stage1_frame(ctx, client, models)
        table1, daily_ic = stage1_table(ctx, s1)
        s2_table, frames = stage2_table(ctx, client)
        spend = spend_report(ctx, client)
        audit = cache_audit(ctx, client)
    # the recorded MCS must be what the cache gives now
    again = run_mcs(ctx, daily_ic.loc[daily_ic["model"].isin([m for m in res["stage1"]["models"]])])
    if again.included != res["stage1"]["included"]:
        raise TournamentError("the stage-1 MCS from the cache differs from mcs.json; rerun --stage select")
    lb = leaderboard(ctx, table1, res, s2_table)
    s1_out = s1.drop(columns=[c for c in ("z_cc", "e5", "e5_lvl", "y2", "b_event_id") if c in s1.columns])
    io.write_parquet(
        s1_out,
        STAGE1,
        producer=PRODUCER,
        description="NA-06 stage-1 answers (per model and event)",
        layout=lay,
    )
    s2 = pd.concat(
        [pd.concat([f.a.assign(part="A"), f.b.assign(part="B")]) for f in frames.values()], ignore_index=True
    )
    s2 = s2.drop(columns=[c for c in ("z_cc", "e5", "e5_lvl", "y2", "b_event_id") if c in s2.columns])
    io.write_parquet(
        s2, STAGE2, producer=PRODUCER, description="NA-06 stage-2 answers (Call A and Call B)", layout=lay
    )
    pb = pd.concat([f.probes for f in frames.values()], ignore_index=True)
    pb = pb.drop(columns=[c for c in ("z_cc", "e5", "e5_lvl", "y2", "b_event_id") if c in pb.columns])
    pb["correct"] = pb["correct"].astype("boolean") if "correct" in pb else None
    io.write_parquet(pb, PROBES, producer=PRODUCER, description="NA-06 probe answers (a–f)", layout=lay)
    # probe f
    validity: dict[str, Any] = {}
    vt = pd.DataFrame()
    v_models = [m for m, f in frames.items() if (f.probes["probe"] == "reading_validity").any()]
    if v_models:
        vm = v_models[0]
        v = frames[vm].probes.loc[frames[vm].probes["probe"] == "reading_validity"]
        ref = reference_tags(ctx, ctx.samples().loc[ctx.samples()["reading_validity"]])
        merged = v[["event_id", *[c for c in v.columns if c.startswith("label_")]]].merge(
            ref, on="event_id", how="right"
        )
        for c in ("label_event_type", "label_quantified", "label_scheduled", "label_credibility"):
            if c not in merged:
                merged[c] = None
        vt, summ = pr.validity_tables(merged, ctx.cfg.reading_validity.event_type_map)
        vt.insert(0, "model", vm)
        validity = {
            "model": vm,
            "n_events": len(merged),
            "n_answered": int(merged["label_event_type"].notna().sum()),
            "main_article_matched": int(merged["main_article"].notna().sum()),
            "agreement": {r["comparison"]: r["agreement"] for r in summ.to_dict("records")},
            "n": {r["comparison"]: int(r["n"]) for r in summ.to_dict("records")},
        }
    # artifacts
    out = lay.root / ARTIFACTS
    out.mkdir(parents=True, exist_ok=True)

    def csv(df: pd.DataFrame, rel: str, desc: str) -> str:
        io.atomic_write_bytes(
            lay.root / rel, df.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode()
        )
        return str(io.register_artifact(rel, producer=PRODUCER, description=desc, layout=lay)["sha256"])

    lb_sha = csv(
        lb, LEADERBOARD, "NA-06 leaderboard: every eligible model, stage 1, MCS, stage 2, probes, screens"
    )
    pdt = probe_details({r["model"]: r for r in s2_table.to_dict("records")})
    csv(pdt, PROBE_DETAILS, "NA-06 probe values and screen results per stage-2 model (PREREG §8.3)")
    fig = pd.DataFrame(
        {
            "model": lb["model"],
            "kind": lb["kind"],
            "cost_per_1000_decisions": lb["cost_per_1000_a"],
            "ic": lb["ic1_z_cc"],
            "ci_low": lb["ic1_z_cc"] - 1.96 * lb["ic1_z_cc_se"],
            "ci_high": lb["ic1_z_cc"] + 1.96 * lb["ic1_z_cc_se"],
            "mcs_member": lb["mcs_member"],
            "stage2": lb["stage2"],
            "screen": [
                "not_tested" if pd.isna(x) else ("pass" if bool(x) else "fail") for x in lb["screens_pass"]
            ],
        }
    )
    csv(
        fig,
        FIG3,
        "NA-06 Figure 3 data: cost per 1,000 decisions vs stage-1 IC (95% CI), MCS and screen flags",
    )
    if not vt.empty:
        csv(vt, VALIDITY_FILE, "NA-06 probe f: reading-validity confusion tables (PREREG A2.5, report only)")
    io.register_artifact(DRY_RUN_FILE, producer=PRODUCER, description="NA-06 dry-run projections", layout=lay)
    for rel, obj, desc in (
        (SPEND_FILE, spend, "NA-06 spend by stage and model, cost ratios, projection vs actual"),
        (AUDIT_FILE, audit, "NA-06 AC1 cache audit: sessions of every NA-06 cache row"),
    ):
        io.atomic_write_bytes(lay.root / rel, (json.dumps(obj, indent=1, default=str) + "\n").encode("utf-8"))
        io.register_artifact(rel, producer=PRODUCER, description=desc, layout=lay)
    # skill vs memorisation (AC5)
    t2 = lb.loc[lb["stage2"]].dropna(subset=["contamination_score", "ic2_a_z_cc"])
    corr: dict[str, Any] = {"n_models": len(t2)}
    if len(t2) >= 3:
        rho2, p2, _ = mx.spearman(t2["ic2_a_z_cc"], t2["contamination_score"])
        rho1, p1, _ = mx.spearman(t2["ic1_z_cc"], t2["contamination_score"])
        corr |= {
            "rho_ic2_vs_contamination": float(rho2),
            "p_ic2": float(p2),
            "rho_ic1_vs_contamination": float(rho1),
            "p_ic1": float(p1),
        }
    passing = lb.loc[lb["stage2"] & lb["screens_pass"].fillna(False).astype(bool), "model"].tolist()
    summary = {
        "stage1_survivors": res["stage1"]["included"],
        "stage1_survivors_other_statistic": res["robustness_other_statistic"]["included"],
        "stage2_models": res["stage2_models"],
        "stage2_survivors_passing": passing,
        "rank_vs_contamination": corr,
        "reading_validity": validity,
        "spend": spend,
        "audit_ok": audit["ok"],
        "leaderboard_sha256": lb_sha,
    }
    io.atomic_write_bytes(
        lay.root / SUMMARY_FILE, (json.dumps(summary, indent=1, default=str) + "\n").encode("utf-8")
    )
    io.register_artifact(
        SUMMARY_FILE, producer=PRODUCER, description="NA-06 summary of the report stage", layout=lay
    )
    write_frozen_tournament(
        ctx,
        {
            "stage1_survivors": res["stage1"]["included"],
            "stage2_models": res["stage2_models"],
            "stage2_survivors_passing": passing,
            "leaderboard_file": LEADERBOARD,
            "leaderboard_sha": lb_sha,
            "mcs_statistic": ctx.cfg.mcs.statistic,
        },
    )
    n_trials = log_trials(ctx, lb, validity)
    log(
        f"report: {len(lb)} models; trials appended {n_trials}; audit ok {audit['ok']}; "
        f"{time.perf_counter() - t0:.0f} s"
    )
    log(f"peak RSS {peak_rss_mb():.0f} MB")
    return 0


def stage_handoff(ctx: Ctx) -> int:
    """``allow_val_b: true`` (CLAUDE.md C13): val-B may now be used by NA-07's confirmation and NA-11's
    selection. Refuses unless the report recorded the tournament."""
    path = ctx.lay.configs / "frozen.yaml"
    frozen = load_frozen(path)
    if not frozen.tournament or not frozen.tournament.get("leaderboard_sha"):
        raise TournamentError("frozen.yaml has no tournament section: run --stage report first")
    text = path.read_text(encoding="utf-8")
    new = re.sub(
        r"^allow_val_b:.*$",
        "allow_val_b: true        # NA-06 set it after the tournament: val-B for NA-07's confirmation and "
        "NA-11's selection only (CLAUDE.md C13)",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if yaml.safe_load(new)["allow_val_b"] is not True:
        raise TournamentError("allow_val_b did not round-trip")
    io.atomic_write_bytes(path, new.encode("utf-8"))
    log("configs/frozen.yaml: allow_val_b: true")
    return 0


STAGES: Final[dict[str, Callable[[Ctx], int]]] = {
    "samples": stage_samples,
    "dryrun1": stage_dryrun1,
    "stage1": stage_stage1,
    "select": stage_select,
    "dryrun2": stage_dryrun2,
    "stage2": stage_stage2,
    "validity": stage_validity,
    "report": stage_report,
    "handoff": stage_handoff,
}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", choices=list(STAGES), required=True)
    args = ap.parse_args(argv)
    ctx = Ctx.load()
    rc = STAGES[args.stage](ctx)
    log(f"{args.stage}: exit {rc}; peak RSS {peak_rss_mb():.0f} MB")
    return rc


if __name__ == "__main__":
    sys.exit(main())
