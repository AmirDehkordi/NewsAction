"""NA-07 stages: ``python -m newsaction.encoding.run --stage <stage>`` (PRD NA-07; PREREG §8.4).

Every request goes through ``dm.client.DecisionClient("NA-07")``: its refusals (val-B is open since NA-06; the
test period is refused; third-party; masked states only), the cache, the dry run against the NA-07 cap and the
total cap, and the spend ledger. Requests NA-06 already made (the E3 val-A search states, the Call B D2 twins)
are cache hits and cost nothing. ``report`` rebuilds every number from the cache with an offline client.

Stages, in order:
1. ``samples``: ``work/dm/encoding/samples.parquet``: NA-04's 1,500 val-A + 1,500 val-B D0 sample events with
   tier, month and symbol, their D2 twins and the 30 numeracy events. Asserts that the E0–E4 files hold the
   same events, that every val-A twin has a Call A and a Call B D2 state, and that the two differ only in
   ``reaction_so_far``;
2. ``dryrun``: the projection of every part (S1 search, S4 anchoring, the worst case of S2 and S3 over the
   encodings that could be chosen) → ``artifacts/NA-07/dry_run.json``, and the account's credit →
   ``artifacts/NA-07/key_usage.json``; exits 2 if the projection exceeds what the NA-07 cap, the total cap or
   the account's credit leaves (PREREG §13: STOP and ask);
3. ``search``: S1, the three models × E0–E4 on the val-A sample (Call A);
4. ``anchoring``: S4, Call A on D2 for the val-A twins (Call B is NA-06's);
5. ``select`` (offline): the val-A encoding table and the best encoding → ``artifacts/NA-07/selection.json``;
6. ``confirm``: S2, the val-B sample in {best, E3}, only if the best is not E3;
7. ``numeracy``: S3 in the encoding the val-B check kept, and in E3 as a reference when that is not E3;
8. ``report`` (offline): the work files, ``encoding_ic.csv``, ``encoding_daily_ic.csv``,
   ``encoding_check.csv``, ``numeracy.csv``, ``numeracy_series.csv``, ``anchoring.csv``, ``spend.json``,
   ``cache_audit.json``, ``summary.json``, the trials and ``configs/frozen.yaml`` ``encoding`` and
   ``anchoring``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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

from newsaction import calendar, io
from newsaction.config import SplitName, load_frozen, load_splits
from newsaction.dm import CATALOG_FILE
from newsaction.dm.canary import state_info
from newsaction.dm.client import CallResult, CallSpec, DecisionClient, Projection
from newsaction.dm.runner import load_states, state_specs
from newsaction.dm.schemas import DecisionRequest, questions_from
from newsaction.encoding import (
    ANCHORING,
    ARTIFACTS,
    CHUNK,
    CONFIRM,
    NUMERACY,
    PRODUCER,
    SAMPLES,
    SEARCH,
    EncodingConfig,
    EncodingError,
    encoding_config,
    log_trial,
)
from newsaction.encoding import anchoring as an
from newsaction.encoding import numeracy as nu
from newsaction.encoding import study as st
from newsaction.ledger import TRIALS, TrialLedger
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso
from newsaction.states import Encoding
from newsaction.states.build import stratified_sample
from newsaction.states.codebook import load_codebook
from newsaction.states.questions import Battery, load_battery
from newsaction.tournament import metrics as mx
from newsaction.tournament.run import cached_results, option_probs, peak_rss_mb, result_rows

EVENTS_D0: Final = "events/events_d0.parquet"
PANEL: Final = "panel/panel_public.parquet"
LEADERBOARD: Final = "artifacts/NA-06/leaderboard.csv"
DRY_RUN_FILE: Final = f"{ARTIFACTS}/dry_run.json"
KEY_USAGE_FILE: Final = f"{ARTIFACTS}/key_usage.json"
SELECTION_FILE: Final = f"{ARTIFACTS}/selection.json"
ENCODING_IC: Final = f"{ARTIFACTS}/encoding_ic.csv"
ENCODING_DAILY: Final = f"{ARTIFACTS}/encoding_daily_ic.csv"
ENCODING_CHECK: Final = f"{ARTIFACTS}/encoding_check.csv"
NUMERACY_CSV: Final = f"{ARTIFACTS}/numeracy.csv"
NUMERACY_SERIES: Final = f"{ARTIFACTS}/numeracy_series.csv"
ANCHORING_CSV: Final = f"{ARTIFACTS}/anchoring.csv"
SPEND_FILE: Final = f"{ARTIFACTS}/spend.json"
AUDIT_FILE: Final = f"{ARTIFACTS}/cache_audit.json"
SUMMARY_FILE: Final = f"{ARTIFACTS}/summary.json"
CREDITS_URL: Final = "https://openrouter.ai/api/v1/credits"
VAL_A: Final[SplitName] = "val_a"
VAL_B: Final[SplitName] = "val_b"
TAG_PREFIX: Final = "na07"
TAG_S4_A: Final = f"{TAG_PREFIX}_s4_a"
TAG_S4_B: Final = f"{TAG_PREFIX}_s4_b"
PROBE_NUMERACY: Final = "numeracy"
PART_SPLIT: Final[dict[str, SplitName]] = {"s1": VAL_A, "s2": VAL_B, "s3": VAL_A, "s4": VAL_A}
EVENT_COLUMNS: Final = ["event_id", "company_id", "symbol_id", "session", "month", "tier", "split", "embargo"]
DROP_TARGETS: Final = ("z_cc",)


def tag_search(part: str, encoding: str) -> str:
    return f"{TAG_PREFIX}_{part}_{encoding}"


def tag_numeracy(encoding: str) -> str:
    return f"{TAG_PREFIX}_s3_{encoding}"


def part_of(tag: str) -> str:
    """``na07_s1_E0`` → ``s1``."""
    return tag.split("_")[1] if tag.startswith(f"{TAG_PREFIX}_") else "other"


def log(msg: str) -> None:
    print(f"[{utc_now_iso()[:19]}] {msg}", flush=True)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- context ---------------------------------------------------------------------------------------------


@dataclass
class Ctx:
    lay: Layout
    cfg: EncodingConfig
    battery: Battery
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, layout: Layout | None = None) -> Ctx:
        lay = resolve_layout(layout)
        return cls(lay, encoding_config(lay), load_battery(lay.configs / "questions_v1.yaml"))

    def client(self, *, offline: bool = False) -> DecisionClient:
        return DecisionClient(CHUNK, offline=offline, layout=self.lay, concurrency=self.cfg.concurrency)

    def _memo(self, key: str, make: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def models(self) -> list[str]:
        """The operator's three, recomputed from NA-06's leaderboard (sha-checked against frozen.yaml)."""

        def make() -> list[str]:
            path = self.lay.root / LEADERBOARD
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            frozen = load_frozen(self.lay.configs / "frozen.yaml").tournament or {}
            if sha != frozen.get("leaderboard_sha"):
                raise EncodingError(
                    "artifacts/NA-06/leaderboard.csv does not match frozen.yaml leaderboard_sha"
                )
            top = st.top_models(pd.read_csv(path), self.cfg.models.n, self.cfg.rule.tie_decimals)
            if top != list(self.cfg.models.expected):
                raise EncodingError(f"leaderboard top {self.cfg.models.n} {top} != configs {self.cfg.models}")
            return top

        return self._memo("models", make)  # type: ignore[no-any-return]

    def samples(self) -> pd.DataFrame:
        return cast(pd.DataFrame, self._memo("samples", lambda: io.read_parquet(SAMPLES, layout=self.lay)))

    def ids(self, split: SplitName, column: str = "event_id", flag: str | None = None) -> list[str]:
        s = self.samples()
        keep = s["split"] == split
        if flag is not None:
            keep &= s[flag].astype(bool)
        return s.loc[keep, column].astype(str).tolist()

    def sample_states(self, encoding: str, split: SplitName) -> pd.DataFrame:
        rel = self.cfg.state_files.sample_file(encoding)
        return self._memo(  # type: ignore[no-any-return]
            f"sample:{encoding}:{split}",
            lambda: load_states(rel, splits=[split], event_ids=self.ids(split), layout=self.lay),
        )

    def d2_states(self, which: str) -> pd.DataFrame:
        rel = self.cfg.state_files.call_a_d2 if which == "A" else self.cfg.state_files.call_b_d2
        return self._memo(  # type: ignore[no-any-return]
            f"d2:{which}",
            lambda: load_states(
                rel, splits=[VAL_A], event_ids=self.ids(VAL_A, "d2_event_id"), layout=self.lay
            ),
        )


# --- samples ---------------------------------------------------------------------------------------------


def _strip_reaction(state: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in state.items() if k != nu.REACTION}


def build_samples(ctx: Ctx) -> pd.DataFrame:
    cfg, lay = ctx.cfg, ctx.lay
    frames = {
        e: io.read_parquet(
            cfg.state_files.sample_file(e), columns=["event_id", "split", "encoding"], layout=lay
        )
        for e in cfg.encodings
    }
    base = frames[cfg.default_encoding]
    for e, f in frames.items():
        if set(f["event_id"]) != set(base["event_id"]) or not (f["encoding"] == e).all():
            raise EncodingError(f"the {e} sample does not hold the {cfg.default_encoding} sample's events")
    counts = base["split"].value_counts().to_dict()
    if counts != {VAL_A: cfg.samples.val_a, VAL_B: cfg.samples.val_b}:
        raise EncodingError(f"sample sizes {counts} differ from configs/encoding.yaml")
    ev = io.read_parquet(EVENTS_D0, columns=EVENT_COLUMNS, layout=lay)
    s = base[["event_id", "split"]].merge(
        ev, on="event_id", how="left", validate="one_to_one", suffixes=("", "_ev")
    )
    if s["session"].isna().any() or not (s["split"] == s["split_ev"]).all():
        raise EncodingError("a sample event is missing from events_d0 or has another split")
    if s["embargo"].astype(bool).any():
        raise EncodingError("a sample event is inside the embargo (PREREG §4.2)")
    s = s.drop(columns=["split_ev", "embargo"])
    s["d2_event_id"] = s["event_id"].str.replace("W0:", "W2:", n=1, regex=False)
    # S4: every val-A twin has both D2 states, which differ only in reaction_so_far
    twins = s.loc[s["split"] == VAL_A, "d2_event_id"].astype(str).tolist()
    cols = ["event_id", "split", "state_json", "third_party_ok_all"]
    a = io.read_parquet(cfg.state_files.call_a_d2, columns=cols, layout=lay).set_index("event_id")
    b = io.read_parquet(cfg.state_files.call_b_d2, columns=cols, layout=lay).set_index("event_id")
    missing = [e for e in twins if e not in a.index or e not in b.index]
    if missing:
        raise EncodingError(
            f"{len(missing)} val-A twins lack a Call A or Call B D2 state, e.g. {missing[:3]}"
        )
    for e in twins:
        sa, sb = json.loads(str(a.at[e, "state_json"])), json.loads(str(b.at[e, "state_json"]))
        if nu.REACTION in sa or _strip_reaction(sb) != sa:
            raise EncodingError(f"{e}: Call A and Call B D2 states differ outside reaction_so_far")
        if not (a.at[e, "split"] == VAL_A == b.at[e, "split"]):
            raise EncodingError(f"{e}: a D2 twin outside val-A")
    s["anchoring"] = s["split"] == VAL_A
    va = s.loc[s["anchoring"], ["d2_event_id", "company_id", "session", "tier", "month"]]
    draw = stratified_sample(
        va.rename(columns={"d2_event_id": "event_id"}),
        cfg.numeracy.n_news,
        list(cfg.samples.strata),
        cfg.seed,
    )
    s["numeracy"] = s["d2_event_id"].isin(set(draw["event_id"]))
    return s.sort_values(["split", "session", "company_id"], kind="mergesort").reset_index(drop=True)


def stage_samples(ctx: Ctx) -> int:
    s = build_samples(ctx)
    io.write_parquet(
        s,
        SAMPLES,
        producer=PRODUCER,
        description="NA-07 samples: NA-04's val-A / val-B D0 sample events, D2 twins, numeracy flag",
        layout=ctx.lay,
    )
    log(
        f"samples: {s['split'].value_counts().to_dict()}; anchoring {int(s['anchoring'].sum())}; "
        f"numeracy {int(s['numeracy'].sum())}"
    )
    return 0


# --- specs -----------------------------------------------------------------------------------------------


def search_specs(ctx: Ctx, model: str, encoding: str, split: SplitName) -> list[CallSpec]:
    part = "s1" if split == VAL_A else "s2"
    return state_specs(
        ctx.sample_states(encoding, split), ctx.cfg.state_files.sample_file(encoding), model, call="A",
        groups=ctx.cfg.groups, battery=ctx.battery, tag=tag_search(part, encoding),
    )  # fmt: skip


def anchoring_specs(ctx: Ctx, model: str, which: str) -> list[CallSpec]:
    rel = ctx.cfg.state_files.call_a_d2 if which == "A" else ctx.cfg.state_files.call_b_d2
    return state_specs(
        ctx.d2_states(which), rel, model, call=which, groups=ctx.cfg.groups, battery=ctx.battery,
        tag=TAG_S4_A if which == "A" else TAG_S4_B,
    )  # fmt: skip


@dataclass(frozen=True)
class NumeracyItem:
    event_id: str
    direction: str
    magnitude_idx: int
    z: float
    spec: CallSpec


def numeracy_items(ctx: Ctx, model: str, encoding: str) -> list[NumeracyItem]:
    cfg = ctx.cfg
    cb = load_codebook(ctx.lay.configs / "codebook_v1.yaml")
    questions = questions_from(ctx.battery.request("B", list(cfg.groups)))
    rows = ctx.d2_states("B")
    rows = rows.loc[rows["event_id"].isin(set(ctx.ids(VAL_A, "d2_event_id", "numeracy")))]
    out: list[NumeracyItem] = []
    enc = cast(Encoding, encoding)
    for rec in rows.sort_values("event_id").to_dict("records"):
        base = json.loads(rec["state_json"])
        info = state_info(rec, f"work/{cfg.state_files.call_b_d2}").model_copy(
            update={"probe": PROBE_NUMERACY}
        )
        for direction, i, z in nu.grid(cfg.numeracy.magnitudes):
            state = nu.with_reaction(base, nu.synthetic_reaction(cb, z, enc, cfg.numeracy))
            req = DecisionRequest(model=model, state=state, questions=questions)
            out.append(
                NumeracyItem(
                    str(rec["event_id"]), direction, i, z, CallSpec(req, info, tag=tag_numeracy(encoding))
                )
            )
    return out


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
    path.parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(path, (json.dumps(runs, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def account_credit(client: DecisionClient) -> dict[str, Any]:
    """The key's usage and the account's credit (no spend; the key never leaves the client)."""
    key = client.key_usage()
    data = client.get_json(CREDITS_URL)["data"]
    total, used = float(data.get("total_credits") or 0.0), float(data.get("total_usage") or 0.0)
    return {**key, "total_credits": total, "total_usage": used, "credit_remaining": total - used}


def record_credit(ctx: Ctx, client: DecisionClient, label: str) -> dict[str, Any]:
    path = ctx.lay.root / KEY_USAGE_FILE
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    snap = {
        "label": label,
        "ts": utc_now_iso(),
        **account_credit(client),
        "ledger_chunk_usd": client.ledger.totals().chunk_usd,
    }
    rows.append(snap)
    path.parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(path, (json.dumps(rows, indent=2) + "\n").encode("utf-8"))
    log(
        f"credit [{label}]: remaining ${snap['credit_remaining']:.4f} of ${snap['total_credits']:.2f}; "
        f"NA-07 ledger ${snap['ledger_chunk_usd']:.6f}"
    )
    return snap


def print_projection(label: str, proj: Projection, left: float) -> None:
    log(
        f"{label}: {proj.n_send} requests to send ({proj.n_cached} cached); projected ${proj.usd:.4f}; "
        f"NA-07 left ${left:.4f}"
    )
    for m, v in sorted(proj.by_model.items(), key=lambda kv: -kv[1]["usd"]):
        log(f"  {m:45s} {int(v['calls']):6d} calls  {v['tokens']:12.0f} tokens  ${v['usd']:.5f}")


def guarded(ctx: Ctx, client: DecisionClient, label: str, specs: Sequence[CallSpec]) -> bool:
    """Dry run, record it, check the caps and the account's credit; False = STOP (PREREG §13)."""
    proj = client.dry_run(specs)
    left = client.budget_left()
    print_projection(label, proj, left)
    if proj.n_send == 0:
        record_dry_run(ctx, label, proj, {"left_usd": left})
        return True
    snap = record_credit(ctx, client, f"before {label}")
    record_dry_run(ctx, label, proj, {"left_usd": left, "credit_remaining": snap["credit_remaining"]})
    if proj.usd > left:
        log(f"STOP: {label} projects ${proj.usd:.4f} > ${left:.4f} left under the NA-07 / total caps")
        return False
    if proj.usd > snap["credit_remaining"]:
        log(f"STOP: {label} projects ${proj.usd:.4f} > the account's ${snap['credit_remaining']:.4f} credit")
        return False
    return True


def run_batch(client: DecisionClient, specs: Sequence[CallSpec], label: str) -> list[CallResult]:
    t0 = time.perf_counter()
    res = client.decide(specs)
    bad = [r for r in res if not r.ok]
    invalid = sum(1 for r in res if r.ok and r.parsed is not None and not r.parsed.valid)
    log(
        f"{label}: {len(res)} in {time.perf_counter() - t0:.1f} s; {len(bad)} failed, {invalid} invalid; "
        f"NA-07 spent ${client.ledger.totals().chunk_usd:.6f}"
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


def s1_specs(ctx: Ctx) -> dict[str, list[CallSpec]]:
    return {m: [s for e in ctx.cfg.encodings for s in search_specs(ctx, m, e, VAL_A)] for m in ctx.models()}


def s2_specs(ctx: Ctx, best: str) -> dict[str, list[CallSpec]]:
    encs = sorted({best, ctx.cfg.default_encoding})
    return {m: [s for e in encs for s in search_specs(ctx, m, e, VAL_B)] for m in ctx.models()}


def numeracy_encodings(ctx: Ctx, kept: str) -> list[str]:
    """The encoding the val-B check kept, and the default as a report-only reference when it differs."""
    default = ctx.cfg.default_encoding
    return [kept] if kept == default else [kept, default]


def s3_specs(ctx: Ctx, encodings: Sequence[str]) -> dict[str, list[CallSpec]]:
    return {m: [it.spec for e in encodings for it in numeracy_items(ctx, m, e)] for m in ctx.models()}


def s4_specs(ctx: Ctx) -> dict[str, list[CallSpec]]:
    return {m: [*anchoring_specs(ctx, m, "A"), *anchoring_specs(ctx, m, "B")] for m in ctx.models()}


def _flat(by_model: Mapping[str, list[CallSpec]]) -> list[CallSpec]:
    return [s for v in by_model.values() for s in v]


def stage_dryrun(ctx: Ctx) -> int:
    """Every part; S2 and S3 at their worst case over the encodings that could be chosen."""
    default = ctx.cfg.default_encoding
    others = [e for e in ctx.cfg.encodings if e != default]
    with ctx.client() as client:
        parts: dict[str, Projection] = {
            "s1": client.dry_run(_flat(s1_specs(ctx))),
            "s4": client.dry_run(_flat(s4_specs(ctx))),
        }
        s2 = {e: client.dry_run(_flat(s2_specs(ctx, e))) for e in others}
        s3 = {e: client.dry_run(_flat(s3_specs(ctx, numeracy_encodings(ctx, e)))) for e in ctx.cfg.encodings}
        parts["s2_worst"] = max(s2.values(), key=lambda p: p.usd)
        parts["s3_worst"] = max(s3.values(), key=lambda p: p.usd)
        left = client.budget_left()
        snap = record_credit(ctx, client, "dryrun")
    total = sum(p.usd for p in parts.values())
    for label, p in parts.items():
        print_projection(f"dry run {label}", p, left)
        record_dry_run(ctx, f"plan_{label}", p, {"left_usd": left})
    log(f"S2 by best encoding: { {e: round(p.usd, 4) for e, p in s2.items()} }")
    log(f"S3 by chosen encoding: { {e: round(p.usd, 4) for e, p in s3.items()} }")
    log(f"total worst case ${total:.4f}; NA-07 left ${left:.4f}; credit ${snap['credit_remaining']:.4f}")
    if total > left or total > snap["credit_remaining"]:
        log("STOP: the worst-case projection exceeds what is left (PREREG §13): ask the operator")
        return 2
    return 0


def stage_search(ctx: Ctx) -> int:
    by_model = s1_specs(ctx)
    with ctx.client() as client:
        if not guarded(ctx, client, "s1", _flat(by_model)):
            return 2
        run_models(client, by_model, "S1 search")
        record_credit(ctx, client, "after s1")
    return 0


def stage_anchoring(ctx: Ctx) -> int:
    by_model = s4_specs(ctx)
    with ctx.client() as client:
        if not guarded(ctx, client, "s4", _flat(by_model)):
            return 2
        run_models(client, by_model, "S4 anchoring")
        record_credit(ctx, client, "after s4")
    return 0


# --- frames ----------------------------------------------------------------------------------------------


def targets(ctx: Ctx, split: SplitName) -> pd.DataFrame:
    """z_cc,t of the sample events of ``split`` (panel_public; PREREG §5.4), keyed by D0 and D2 event id.
    Val-B targets are read only for the S2 check (CLAUDE.md B9, C13): ``allow_val_b`` must be true and the
    val-A best must differ from the default."""

    def make() -> pd.DataFrame:
        if split == VAL_B:
            if not load_frozen(ctx.lay.configs / "frozen.yaml").allow_val_b:
                raise EncodingError("val-B targets requested while allow_val_b is false")
            if selection(ctx)["best"] == ctx.cfg.default_encoding:
                raise EncodingError("val-B targets requested although the val-A best is the default")
        p = io.read_parquet(PANEL, columns=["session", "symbol_id", "z_cc", "split"], layout=ctx.lay)
        p = p.loc[p["split"] == split, ["session", "symbol_id", "z_cc"]]
        s = ctx.samples()
        ev = s.loc[s["split"] == split, ["event_id", "d2_event_id", "session", "symbol_id"]]
        out = ev.merge(p, on=["session", "symbol_id"], how="left", validate="one_to_one")
        if out["z_cc"].isna().any():
            raise EncodingError(f"{int(out['z_cc'].isna().sum())} {split} sample events have no z_cc")
        return out

    return ctx._memo(f"targets:{split}", make)  # type: ignore[no-any-return]


def answers(client: DecisionClient, specs: Sequence[CallSpec]) -> pd.DataFrame:
    return result_rows(specs, cached_results(client, specs))


def search_frame(
    ctx: Ctx, client: DecisionClient, split: SplitName, encodings: Sequence[str]
) -> pd.DataFrame:
    parts = []
    for m in ctx.models():
        for e in encodings:
            parts.append(answers(client, search_specs(ctx, m, e, split)).assign(encoding=e, split=split))
    return pd.concat(parts, ignore_index=True)


def daily_long(ctx: Ctx, frame: pd.DataFrame, split: SplitName) -> pd.DataFrame:
    """(model, encoding, session, ic, n) daily ICs of N̂ with z_cc,t."""
    t = targets(ctx, split)[["event_id", "z_cc"]]
    f = frame.merge(t, on="event_id", how="left", validate="many_to_one")
    rows = []
    mc = ctx.cfg.metric
    for (m, e), g in f.groupby(["model", "encoding"], sort=False):
        d = (
            mx.daily_ic(g, "n_hat", mc.target, mc.min_names_per_day)
            if "n_hat" in g
            else pd.Series(dtype=float)
        )
        n_day: dict[Any, int] = (
            g.dropna(subset=["n_hat", mc.target]).groupby("session").size().to_dict() if "n_hat" in g else {}
        )
        for s, v in d.items():
            rows.append({"split": split, "model": m, "encoding": e, "session": s, "ic": v, "n": n_day[s]})
    return pd.DataFrame(rows, columns=["split", "model", "encoding", "session", "ic", "n"])


def session_grid(ctx: Ctx, split: SplitName) -> list[date]:
    s = ctx.samples()
    return sorted(set(s.loc[s["split"] == split, "session"]))


def split_indices(ctx: Ctx, split: SplitName) -> np.ndarray[Any, np.dtype[np.int64]]:
    b = ctx.cfg.bootstrap
    return st.boot_indices(len(session_grid(ctx, split)), b.reps, b.block, ctx.cfg.seed)


def ic_table(ctx: Ctx, frame: pd.DataFrame, daily: pd.DataFrame, split: SplitName) -> pd.DataFrame:
    grid = session_grid(ctx, split)
    idx = split_indices(ctx, split)
    rows = []
    for (m, e), g in frame.groupby(["model", "encoding"], sort=False):
        d = daily.loc[(daily["model"] == m) & (daily["encoding"] == e)].set_index("session")["ic"]
        summ = st.summarize(d, grid, idx, ctx.cfg.metric.nw_lags, ctx.cfg.bootstrap.ci)
        rows.append(
            {
                "split": split,
                "model": m,
                "encoding": e,
                "n_events": len(g),
                "n_answered": int(g["n_hat"].notna().sum()) if "n_hat" in g else 0,
                "n_paid_na07": int((g["paid_chunk"] == CHUNK).sum()) if "paid_chunk" in g else 0,
                **summ.as_dict(),
            }
        )
    t = pd.DataFrame(rows)
    t["rank"] = st.ranks(t, ctx.cfg.rule.tie_decimals)
    return t


def selection(ctx: Ctx) -> dict[str, Any]:
    path = ctx.lay.root / SELECTION_FILE
    if not path.is_file():
        raise EncodingError(f"{SELECTION_FILE} is missing: run --stage select first")
    out: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return out


def search_results(
    ctx: Ctx, client: DecisionClient
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, st.Choice]:
    frame = search_frame(ctx, client, VAL_A, ctx.cfg.encodings)
    if frame["n_hat"].isna().all():
        raise EncodingError("no S1 answer is cached: run --stage search first")
    daily = daily_long(ctx, frame, VAL_A)
    table = ic_table(ctx, frame, daily, VAL_A)
    choice = st.choose_encoding(table, ctx.cfg.encodings, ctx.cfg.default_encoding, ctx.cfg.rule.tie_decimals)
    return frame, daily, table, choice


def stage_select(ctx: Ctx) -> int:
    with ctx.client(offline=True) as client:
        _, _, table, choice = search_results(ctx, client)
    out = {"best": choice.best, "choice": choice.as_dict(), "ts": utc_now_iso()}
    path = ctx.lay.root / SELECTION_FILE
    io.atomic_write_bytes(path, (json.dumps(out, indent=1) + "\n").encode("utf-8"))
    log(table[["model", "encoding", "ic", "t", "boot_se", "rank"]].to_string(index=False))
    log(f"select: best {choice.best} ({choice.reason}); mean ranks {choice.mean_rank}")
    if choice.best != ctx.cfg.default_encoding:
        log(f"NOTE: the val-A best is {choice.best}, not {ctx.cfg.default_encoding}: the val-B check decides")
    return 0


@dataclass(frozen=True)
class ValB:
    check: st.Check
    detail: pd.DataFrame  # pooled and per-model Δ with bootstrap SE
    table: pd.DataFrame  # per (model, encoding) val-B ICs
    daily: pd.DataFrame
    frame: pd.DataFrame | None  # the val-B answers


def check_results(ctx: Ctx, client: DecisionClient, best: str) -> ValB:
    """The val-B check (and its per-model rows); no val-B value is read when the best is the default."""
    default = ctx.cfg.default_encoding
    if best == default:
        check = st.confirm(best, default, None, None, ctx.cfg.rule.confirm_se)
        return ValB(check, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None)
    encs = sorted({best, default})
    frame = search_frame(ctx, client, VAL_B, encs)
    if frame["n_hat"].isna().all():
        raise EncodingError("no S2 answer is cached: run --stage confirm first")
    daily = daily_long(ctx, frame, VAL_B)
    grid = session_grid(ctx, VAL_B)
    idx = split_indices(ctx, VAL_B)
    models = ctx.models()
    delta = st.val_b_delta(daily, models, best, default)
    summ = st.summarize(delta, grid, idx, ctx.cfg.metric.nw_lags, ctx.cfg.bootstrap.ci)
    check = st.confirm(best, default, summ.ic, summ.boot_se, ctx.cfg.rule.confirm_se, summ.n_days)
    rows = [{"scope": "pooled", **summ.as_dict()}]
    for m in models:
        dm = st.val_b_delta(daily, [m], best, default)
        rows.append(
            {
                "scope": m,
                **st.summarize(dm, grid, idx, ctx.cfg.metric.nw_lags, ctx.cfg.bootstrap.ci).as_dict(),
            }
        )
    detail = pd.DataFrame(rows).rename(columns={"ic": "delta"})
    return ValB(check, detail, ic_table(ctx, frame, daily, VAL_B), daily, frame)


def stage_confirm(ctx: Ctx) -> int:
    best = str(selection(ctx)["best"])
    if best == ctx.cfg.default_encoding:
        log(f"confirm: the val-A best is {best}, the default: no val-B call (PRD S2 has nothing to check)")
        return 0
    by_model = s2_specs(ctx, best)
    with ctx.client() as client:
        if not guarded(ctx, client, "s2", _flat(by_model)):
            return 2
        run_models(client, by_model, "S2 confirm")
        record_credit(ctx, client, "after s2")
    with ctx.client(offline=True) as client:
        vb = check_results(ctx, client, best)
    log(f"confirm: {vb.check.as_dict()}")
    log(vb.detail.to_string(index=False))
    return 0


def kept_encoding(ctx: Ctx, client: DecisionClient) -> tuple[str, st.Check]:
    """The encoding the val-B check kept (the val-A best when it is the default)."""
    check = check_results(ctx, client, str(selection(ctx)["best"])).check
    return check.chosen, check


def stage_numeracy(ctx: Ctx) -> int:
    with ctx.client(offline=True) as client:
        kept, _ = kept_encoding(ctx, client)
    encs = numeracy_encodings(ctx, kept)
    by_model = s3_specs(ctx, encs)
    log(f"numeracy in {encs}: {sum(len(v) for v in by_model.values())} requests")
    with ctx.client() as client:
        if not guarded(ctx, client, "s3", _flat(by_model)):
            return 2
        run_models(client, by_model, "S3 numeracy")
        record_credit(ctx, client, "after s3")
    return 0


def reaction_text(spec: CallSpec) -> str:
    state = spec.request.state
    if not isinstance(state, dict):
        raise EncodingError("a numeracy state must be an object")
    return str(state[nu.REACTION]["stock_move_vs_market_and_sector"])


def numeracy_frame(ctx: Ctx, client: DecisionClient, encoding: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for m in ctx.models():
        items = numeracy_items(ctx, m, encoding)
        res = cached_results(client, [it.spec for it in items])
        for it, r in zip(items, res, strict=True):
            p = option_probs(r, "reaction_adequacy")
            rows.append(
                {
                    "model": m,
                    "event_id": it.event_id,
                    "session": it.spec.info.session,
                    "encoding": encoding,
                    "direction": it.direction,
                    "magnitude_idx": it.magnitude_idx,
                    "z": it.z,
                    "reaction_text": reaction_text(it.spec),
                    "ok": r is not None,
                    "key": None if r is None else r.key,
                    "paid_chunk": None if r is None or r.row is None else r.row.chunk,
                    **{
                        f"p_{k}": p.get(k, math.nan)
                        for k in ("wrong_direction", *nu.SMALL, "about_right", *nu.LARGE)
                    },
                    "p_large": sum(p[k] for k in nu.LARGE) if p else math.nan,
                    "p_small": sum(p[k] for k in nu.SMALL) if p else math.nan,
                }
            )
    return pd.DataFrame(rows)


def anchoring_frame(ctx: Ctx, client: DecisionClient) -> pd.DataFrame:
    t = targets(ctx, VAL_A)[["d2_event_id", "z_cc"]].rename(columns={"d2_event_id": "event_id", "z_cc": "g"})
    parts = []
    for m in ctx.models():
        a = answers(client, anchoring_specs(ctx, m, "A"))
        b = answers(client, anchoring_specs(ctx, m, "B"))
        keep = ["event_id", "session", "ok", "valid", "n_hat", "paid_chunk", "cost"]
        f = a[[c for c in keep if c in a]].merge(
            b[[c for c in keep if c in b] + [c for c in ("j", "w", "c") if c in b]],
            on=["event_id", "session"],
            how="outer",
            suffixes=("_a", "_b"),
            validate="one_to_one",
        )
        parts.append(f.merge(t, on="event_id", how="left", validate="one_to_one").assign(model=m))
    return pd.concat(parts, ignore_index=True)


def anchoring_table(ctx: Ctx, frame: pd.DataFrame) -> tuple[pd.DataFrame, an.Verdict]:
    a = ctx.cfg.anchoring
    rows, pairs = [], {}
    for m in ctx.models():
        s = an.stats(frame.loc[frame["model"] == m])
        rows.append(
            {"model": m, **s.as_dict(), "present": an.present(s.slope, s.corr, a.slope_min, a.corr_max)}
        )
        pairs[m] = (s.slope, s.corr)
    v = an.combine(pairs, a.slope_min, a.corr_max)
    rows.append({"model": "all", "slope": v.slope, "corr": v.corr, "present": v.present})
    t = pd.DataFrame(rows)
    t["slope_min"], t["corr_max"] = a.slope_min, a.corr_max
    t["calls_per_event"] = [None] * (len(t) - 1) + [v.calls_per_event]
    return t, v


# --- report ----------------------------------------------------------------------------------------------


def catalog_prices(lay: Layout) -> dict[str, float]:
    snap = json.loads((lay.root / CATALOG_FILE).read_text(encoding="utf-8"))
    return {str(m["id"]): float(m["pricing"].get("prompt") or 0.0) for m in snap["models"]}


def spend_report(ctx: Ctx, client: DecisionClient) -> dict[str, Any]:
    rows = client.cache.rows(chunk=CHUNK)
    prices = catalog_prices(ctx.lay)
    df = pd.DataFrame(
        [{"model": r.model, "tag": r.tag, "cost": r.cost, "tokens": r.input_tokens} for r in rows],
        columns=["model", "tag", "cost", "tokens"],
    )
    t = client.ledger.totals()
    out: dict[str, Any] = {
        "ledger": {
            "na07_usd": t.chunk_usd,
            "total_usd": t.total_usd,
            "by_chunk": t.by_chunk,
            "cap_usd": t.chunk_cap_usd,
        },
        "reconcile": client.reconcile(),
        "n_rows": len(df),
    }
    if df.empty:
        return out
    df["part"] = df["tag"].map(part_of)
    df["priced"] = [prices.get(m, 0.0) * (tok or 0) for m, tok in zip(df["model"], df["tokens"], strict=True)]
    out["actual_by_part"] = df.groupby("part")["cost"].sum().to_dict()
    out["calls_by_part"] = df.groupby("part").size().to_dict()
    out["by_model"] = {
        m: {
            "usd": float(g["cost"].sum()),
            "calls": len(g),
            "cost_ratio": float(g["cost"].sum() / g["priced"].sum()) if g["priced"].sum() > 0 else None,
        }
        for m, g in df.groupby("model")
    }
    runs = json.loads((ctx.lay.root / DRY_RUN_FILE).read_text(encoding="utf-8"))
    first: dict[str, dict[str, Any]] = {}
    for r in runs:  # the projection made just before a part's paid calls
        if r["label"] in PART_SPLIT and r["n_send"] > 0 and r["label"] not in first:
            first[r["label"]] = r
    out["projection_vs_actual"] = {}
    for label, r in first.items():
        actual = float(out["actual_by_part"].get(label, 0.0))
        out["projection_vs_actual"][label] = {
            "projected": r["usd"],
            "actual": actual,
            "actual_over_projected": actual / r["usd"] if r["usd"] else None,
            "within_20pct": bool(r["usd"] and abs(actual / r["usd"] - 1.0) <= 0.20),
        }
    proj_total = sum(r["usd"] for r in first.values())
    out["projection_total"] = proj_total
    out["actual_total"] = float(df["cost"].sum())
    out["actual_over_projected_total"] = out["actual_total"] / proj_total if proj_total else None
    out["within_20pct_total"] = bool(proj_total and abs(out["actual_total"] / proj_total - 1.0) <= 0.20)
    return out


def cache_audit(ctx: Ctx, client: DecisionClient, used: pd.DataFrame) -> dict[str, Any]:
    """AC3: every NA-07 cache row, and every request the report uses (paid by NA-06 or NA-07), is a state of
    the split its part may use: val-A after the embargo for S1, S3 and S4; val-B after the embargo for S2."""
    splits = load_splits(ctx.lay.configs / "splits.yaml")
    emb = splits.embargo_sessions
    allowed: dict[str, tuple[date, date]] = {}
    for name in (VAL_A, VAL_B):
        rng = splits.splits[name]
        days = calendar.sessions(rng.start, rng.end)
        allowed[name] = (days[emb], rng.end)
    bad: list[dict[str, Any]] = []
    by_part: Counter[str] = Counter()
    by_part_split: Counter[str] = Counter()
    for r in client.cache.rows(chunk=CHUNK):
        meta = r.meta
        part = part_of(r.tag)
        by_part[part] += 1
        by_part_split[f"{part}:{meta.get('split')}"] += 1
        want = PART_SPLIT.get(part)
        ok = bool(meta.get("source") == "states" and meta.get("split") == want and meta.get("masked"))
        if ok and want is not None:
            lo, hi = allowed[want]
            ok = lo <= date.fromisoformat(str(meta["session"])) <= hi
        if part == "s3" and meta.get("probe") != PROBE_NUMERACY:
            ok = False
        if not ok:
            bad.append(
                {"key": r.key, "tag": r.tag, "split": meta.get("split"), "session": meta.get("session")}
            )
    used_bad = 0
    used_counts: dict[str, dict[str, int]] = {}
    for part_key, g in used.groupby("part"):
        part = str(part_key)
        want_split = PART_SPLIT[part]
        lo, hi = allowed[want_split]
        sess = pd.to_datetime(g["session"]).dt.date
        n_bad = int(((g["split"] != want_split) | (sess < lo) | (sess > hi)).sum())
        used_bad += n_bad
        by_split = {str(k): int(v) for k, v in g["split"].value_counts().items()}
        used_counts[part] = {"requests": len(g), "outside": n_bad, **by_split}
    return {
        "chunk": CHUNK,
        "n_rows_na07": sum(by_part.values()),
        "na07_rows_by_part": dict(by_part),
        "na07_rows_by_part_split": dict(by_part_split),
        "used_requests_by_part": used_counts,
        "allowed": {k: [v[0].isoformat(), v[1].isoformat()] for k, v in allowed.items()},
        "part_split": PART_SPLIT,
        "violations": bad[:20],
        "n_violations": len(bad) + used_bad,
        "ok": not bad and used_bad == 0,
    }


def write_frozen_section(lay: Layout, name: str, comment: str, entry: Mapping[str, Any]) -> None:
    """Replace the ``name:`` section of configs/frozen.yaml (its line and the indented lines after it)."""
    path = lay.configs / "frozen.yaml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if re.match(rf"^{name}:", ln))
    end = start + 1
    while end < len(lines) and lines[end].startswith((" ", "\t")):
        end += 1
    body = yaml.safe_dump(
        dict(entry), sort_keys=False, allow_unicode=True, default_flow_style=None, width=110
    )
    block = [f"{name}:".ljust(21) + f"# {comment}\n"] + [f"  {ln}\n" for ln in body.splitlines()]
    new = "".join(lines[:start] + block + lines[end:])
    if yaml.safe_load(new)[name] != json.loads(json.dumps(dict(entry))):
        raise EncodingError(f"frozen.yaml {name} block does not round-trip")
    io.atomic_write_bytes(path, new.encode("utf-8"))


def log_trials(
    ctx: Ctx, tables: Sequence[pd.DataFrame], numeracy: pd.DataFrame, anchoring: pd.DataFrame
) -> dict[str, int]:
    base = {
        "groups": list(ctx.cfg.groups),
        "questions_sha256": _sha((ctx.lay.configs / "questions_v1.yaml").read_text(encoding="utf-8")),
        "codebook_sha256": _sha((ctx.lay.configs / "codebook_v1.yaml").read_text(encoding="utf-8")),
        "config_sha256": _sha((ctx.lay.configs / "encoding.yaml").read_text(encoding="utf-8")),
        "samples_sha256": io.load_manifest(ctx.lay)["artifacts"][f"work/{SAMPLES}"]["sha256"],
    }
    n: Counter[str] = Counter()
    for t in tables:
        for rec in t.to_dict("records"):
            params = {**base, "model": rec["model"], "encoding": rec["encoding"], "split": rec["split"]}
            name = f"{rec['model']} {rec['encoding']}"
            n["na07_encoding"] += log_trial(
                "na07_encoding", name, params, rec["split"], "ic_z_cc", rec["ic"], layout=ctx.lay
            )
    for rec in numeracy.to_dict("records"):
        params = {**base, "model": rec["model"], "encoding": rec["encoding"], "n_series": rec["n_series"]}
        name = f"{rec['model']} {rec['encoding']}"
        n["na07_numeracy"] += log_trial(
            "na07_numeracy", name, params, VAL_A, "monotone_share", rec["share"], layout=ctx.lay
        )
    for rec in anchoring.loc[anchoring["model"] != "all"].to_dict("records"):
        params = {**base, "model": rec["model"], "encoding": ctx.cfg.default_encoding, "corr": rec["corr"]}
        n["na07_anchoring"] += log_trial(
            "na07_anchoring", f"{rec['model']} {ctx.cfg.default_encoding}", params, VAL_A, "anchoring_slope",
            rec["slope"], layout=ctx.lay,
        )  # fmt: skip
    return dict(n)


def _csv(lay: Layout, df: pd.DataFrame, rel: str, desc: str) -> str:
    (lay.root / rel).parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(
        lay.root / rel, df.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode()
    )
    return str(io.register_artifact(rel, producer=PRODUCER, description=desc, layout=lay)["sha256"])


def _json(lay: Layout, obj: Any, rel: str, desc: str) -> str:
    io.atomic_write_bytes(lay.root / rel, (json.dumps(obj, indent=1, default=str) + "\n").encode("utf-8"))
    return str(io.register_artifact(rel, producer=PRODUCER, description=desc, layout=lay)["sha256"])


def _drop_targets(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in DROP_TARGETS if c in df.columns])


def stage_report(ctx: Ctx) -> int:
    t0 = time.perf_counter()
    lay, cfg = ctx.lay, ctx.cfg
    sel = selection(ctx)
    with ctx.client(offline=True) as client:
        s1, daily_a, table_a, choice = search_results(ctx, client)
        if choice.best != sel["best"]:
            raise EncodingError(
                f"the cache gives best {choice.best}, selection.json {sel['best']}: rerun select"
            )
        vb = check_results(ctx, client, choice.best)
        check, kept, s2 = vb.check, vb.check.chosen, vb.frame
        num_encs = numeracy_encodings(ctx, kept)
        num = pd.concat([numeracy_frame(ctx, client, e) for e in num_encs], ignore_index=True)
        anc = anchoring_frame(ctx, client)
        spend = spend_report(ctx, client)
        used = pd.concat(
            [
                s1.assign(part="s1"),
                *([] if s2 is None else [s2.assign(part="s2")]),
                num.assign(part="s3", split=VAL_A),
                anc.assign(part="s4", split=VAL_A),  # one row per event holds two requests (A and B)
                anc.assign(part="s4", split=VAL_A),
            ],
            ignore_index=True,
        )[["part", "split", "session"]]
        audit = cache_audit(ctx, client, used)
    for e, g in num.groupby("encoding"):
        if g["p_large"].isna().all():
            raise EncodingError(f"no S3 answer in {e} is cached: run --stage numeracy first")
    if anc["n_hat_a"].isna().all():
        raise EncodingError("no S4 answer is cached: run --stage anchoring first")
    # work files
    io.write_parquet(
        _drop_targets(s1),
        SEARCH,
        producer=PRODUCER,
        description="NA-07 S1 answers (val-A, E0–E4)",
        layout=lay,
    )
    if s2 is not None:
        io.write_parquet(
            _drop_targets(s2), CONFIRM, producer=PRODUCER, description="NA-07 S2 answers (val-B)", layout=lay
        )
    io.write_parquet(
        num,
        NUMERACY,
        producer=PRODUCER,
        description="NA-07 S3 numeracy answers (synthetic reactions)",
        layout=lay,
    )
    io.write_parquet(
        anc.drop(columns=["g"]),
        ANCHORING,
        producer=PRODUCER,
        description="NA-07 S4 answers (Call A vs Call B, D2)",
        layout=lay,
    )
    # tables
    pooled = pd.DataFrame(
        [
            {
                "split": VAL_A,
                "model": "pooled",
                "encoding": e,
                "ic": choice.mean_ic[e],
                "rank": choice.mean_rank[e],
            }
            for e in cfg.encodings
        ]
    )
    # numeracy and its gate (PREREG §15 NA-07 rows)
    series = pd.concat(
        [
            nu.series_table(g, len(cfg.numeracy.magnitudes), cfg.numeracy.tol).assign(encoding=e)
            for e, g in num.groupby("encoding", sort=False)
        ],
        ignore_index=True,
    )
    num_table = pd.concat(
        [
            nu.score(g, cfg.numeracy.target_share).assign(encoding=e)
            for e, g in series.groupby("encoding", sort=False)
        ],
        ignore_index=True,
    )
    num_table["role"] = np.where(num_table["encoding"] == kept, "gate", "reference")
    gate_rows = num_table.loc[num_table["role"] == "gate"]
    shares = {str(m): float(v) for m, v in zip(gate_rows["model"], gate_rows["share"], strict=True)}
    leading = ctx.models()[0]
    chosen, enc_by_model = nu.gate(kept, cfg.default_encoding, shares, leading, cfg.numeracy.target_share)
    tables = [table_a]
    daily = [daily_a]
    if check.needed:
        tables.append(vb.table)
        daily.append(vb.daily)
    enc_table = pd.concat([*tables, pooled], ignore_index=True)
    enc_table["best"] = (enc_table["split"] == VAL_A) & (enc_table["encoding"] == choice.best)
    enc_table["chosen"] = enc_table["encoding"] == chosen
    sha_ic = _csv(
        lay, enc_table, ENCODING_IC, "NA-07 S1/S2: mean daily IC of N̂ vs z_cc per (split, model, encoding)"
    )
    _csv(lay, pd.concat(daily, ignore_index=True), ENCODING_DAILY, "NA-07 daily ICs behind encoding_ic.csv")
    check_rows = pd.DataFrame([{**check.as_dict(), "scope": "rule"}])
    if not vb.detail.empty:
        check_rows = pd.concat([check_rows, vb.detail], ignore_index=True)
    _csv(lay, check_rows, ENCODING_CHECK, "NA-07 S2: the val-B check (Δ = IC(best) − IC(E3), bootstrap SE)")
    num_cols = ["model", "encoding", "role"]
    num_table = num_table[num_cols + [c for c in num_table.columns if c not in num_cols]]
    num_table["leading"] = num_table["model"] == leading
    _csv(lay, num_table, NUMERACY_CSV, "NA-07 S3: monotone share per (model, encoding) (numeracy probe)")
    _csv(lay, series, NUMERACY_SERIES, "NA-07 S3: one row per (model, encoding, news, direction) series")
    anc_table, verdict = anchoring_table(ctx, anc)
    sha_anc = _csv(lay, anc_table, ANCHORING_CSV, "NA-07 S4: slope of N̂_B on G (N̂_A control), corr(N̂_A, N̂_B)")
    _json(lay, spend, SPEND_FILE, "NA-07 spend by part and model, projection vs actual")
    _json(lay, audit, AUDIT_FILE, "NA-07 AC3 cache audit: splits and sessions of every request")
    for rel, desc in (
        (DRY_RUN_FILE, "NA-07 dry-run projections"),
        (KEY_USAGE_FILE, "NA-07 key usage and account credit snapshots"),
        (SELECTION_FILE, "NA-07 val-A selection (best encoding) written by --stage select"),
    ):
        io.register_artifact(rel, producer=PRODUCER, description=desc, layout=lay)
    # hand-off
    write_frozen_section(
        lay,
        "encoding",
        "NA-07: PREREG §8.4 (artifacts/NA-07/encoding_ic.csv, encoding_check.csv)",
        {
            "chosen": chosen,
            "by_model": enc_by_model,
            "val_a_best": choice.best,
            "val_a_rule": choice.reason,
            "val_a_mean_rank": choice.mean_rank,
            "val_a_table_file": ENCODING_IC,
            "val_a_table_sha": sha_ic,
            "val_b_check": {
                "needed": check.needed,
                "delta": check.delta,
                "se": check.se,
                "kept_best": check.kept_best,
                "n_days": check.n_days,
            },
            "val_b_kept": kept,
            "numeracy_gate": {
                "applies": kept != cfg.default_encoding,
                "leading_model": leading,
                "leading_share": shares[leading],
                "target": cfg.numeracy.target_share,
                "shares": shares,
                "file": NUMERACY_CSV,
            },
            "models": ctx.models(),
            "model_specific": True,
        },
    )
    write_frozen_section(
        lay,
        "anchoring",
        "NA-07: PREREG §8.4 (artifacts/NA-07/anchoring.csv)",
        {
            "present": verdict.present,
            "slope": verdict.slope,
            "corr": verdict.corr,
            "calls_per_event": verdict.calls_per_event,
            "by_model": verdict.by_model,
            "encoding": cfg.default_encoding,
            "table_file": ANCHORING_CSV,
            "table_sha": sha_anc,
        },
    )
    n_trials = log_trials(ctx, tables, num_table, anc_table)
    summary = {
        "models": ctx.models(),
        "val_a_best": choice.as_dict(),
        "val_b_check": check.as_dict(),
        "val_b_kept": kept,
        "chosen": chosen,
        "by_model": enc_by_model,
        "numeracy": num_table.to_dict("records"),
        "anchoring": verdict.as_dict(),
        "trials_appended": n_trials,
        "trials_na07": {
            k: TrialLedger(lay.ledgers / TRIALS).count(kind=k, chunk=CHUNK)
            for k in ("na07_encoding", "na07_numeracy", "na07_anchoring")
        },
        "spend": spend,
        "audit_ok": audit["ok"],
    }
    _json(lay, summary, SUMMARY_FILE, "NA-07 summary of the report stage")
    log(f"report: chosen {chosen}; anchoring {verdict.as_dict()}; trials {n_trials}; audit ok {audit['ok']}")
    log(f"report done in {time.perf_counter() - t0:.0f} s; peak RSS {peak_rss_mb():.0f} MB")
    return 0


STAGES: Final[dict[str, Callable[[Ctx], int]]] = {
    "samples": stage_samples,
    "dryrun": stage_dryrun,
    "search": stage_search,
    "anchoring": stage_anchoring,
    "select": stage_select,
    "confirm": stage_confirm,
    "numeracy": stage_numeracy,
    "report": stage_report,
}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--stage", choices=list(STAGES), required=True)
    args = ap.parse_args(argv)
    ctx = Ctx.load()
    rc = STAGES[args.stage](ctx)
    log(f"{args.stage}: exit {rc}; peak RSS {peak_rss_mb():.0f} MB")
    return rc


if __name__ == "__main__":
    sys.exit(main())
