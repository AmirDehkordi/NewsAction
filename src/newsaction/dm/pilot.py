"""The NA-05 measurement pilot (PRD NA-05 S8; PREREG §13): ``python -m newsaction.dm.pilot --stage <stage>``.

Pilot states are train-period or synthetic only (the client runs with ``pilot=True``, which refuses anything
else). Every request is cached, so a stage can be re-run without spending again; ``report`` rebuilds every
measurement from the cache with an offline client.

Stages, in order:
1. ``catalog``: the decision-model catalog snapshot (no spend) → ``artifacts/NA-05/catalog.json``; an existing
   snapshot is kept (``--force`` to refetch);
2. ``billing``: items 1–2 for the pilot models: the shortest and the longest Call A canary state with Q1,
   Q1+Q2, the core battery and core + extended; a ``seed`` probe; kev-4b with a state over its context (a
   failure probe); the key's usage before and after;
3. ``calibrate``: state copies billed per call (``costmodel.state_copies``) and the cost-model calibration →
   ``configs/dm.yaml`` ``costmodel.models``; exits 2 (STOP, PREREG §13) if a model bills the state per
   question;
4. ``measure``: items 3–8 for the pilot models: the canary (repeat 0, the baseline), repeats 1–4 of the 20
   Call A canary states, seeds, Q1 alone and core + extended, truncation at 2K/4K/8K tokens, latency at
   concurrency 1/4/8/16 (40 distinct train states each);
5. ``smoke``: every other catalog model that is not an alias or ``:free``: two canary states and the 2K
   truncation test (eligibility, PREREG §8.1);
6. ``laya``: the local checkpoints on the canary, repeats, interaction, truncation;
7. ``report``: ``artifacts/NA-05/pilot.json``, ``canary_baseline.parquet``, ``eligible_models`` in
   ``configs/frozen.yaml``, the final cost calibration and the key's usage after the pilot.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import re
import resource
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.dm import (
    ARTIFACTS,
    CANARY_BASELINE,
    CANARY_FILE,
    CATALOG_FILE,
    CHUNK,
    PILOT_FILE,
    PRODUCER,
    CostCalibration,
    DMError,
    dm_config,
)
from newsaction.dm.canary import (
    STATE_COLUMNS,
    SYNTHETIC_INFO,
    CanaryItem,
    load_canary,
    probability_rows,
    sample_train,
    state_info,
    synthetic_state,
)
from newsaction.dm.catalog import (
    Outcome,
    eligibility,
    free_base,
    load_snapshot,
    snapshot,
    write_eligibility,
    write_snapshot,
)
from newsaction.dm.client import CallResult, CallSpec, DecisionClient
from newsaction.dm.costmodel import (
    Observation,
    Price,
    basis_from_copies,
    billed_bytes,
    calibrate,
    state_copies,
)
from newsaction.dm.parse import ADEQUACY_KEYS, adequacy_j, adequacy_w, n_hat
from newsaction.dm.schemas import DecisionRequest, QuestionSpec, questions_from
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import git_sha, utc_now_iso
from newsaction.states.codebook import Codebook, load_codebook
from newsaction.states.questions import Battery, canonical_json, load_battery

PILOT_MODELS: Final = (
    "typesafe/jev-1.14",
    "openai/gpt-6-luna-decisions",
    "inception/mercury-decide",
    "liquid/d1",
    "perplexity/pplx-decider-v1.2",
)
LOCAL_MODELS: Final = ("local/laya-typed-decisions", "local/laya-base")
REPEATS: Final = 5  # repeat_idx 0 (the canary baseline) … 4
LAYA_REPEATS: Final = 2  # local checkpoints: repeats 1–2 (a determinism check)
SEEDS: Final = (1, 2)
SEED_STATES: Final = 5
TRUNC_TOKENS: Final = (2048, 4096, 8192)
SMOKE_TRUNC_TOKENS: Final = 2048
SMOKE_BILLING: Final = ("q1", "core")  # the smoke test's billing check: state copies with 4 questions
TOO_LONG: Final = {"jaredpalmer/kev-4b": 12288}  # over its 8,192-token context: a failure probe
CONCURRENCY: Final = (1, 4, 8, 16)
LATENCY_CALLS: Final = 40
SEED: Final = 2026
KEY_USAGE_FILE: Final = f"{ARTIFACTS}/key_usage.json"
DATA_POLICY: Final = re.compile(r"data.?(policy|collection)|no endpoints? found", re.IGNORECASE)
SESSION_ID: Final = "newsaction-NA-05-pilot"

SENTINEL_QUESTION: Final = QuestionSpec(
    type="choice",
    instructions="Does the text in `news` mention a purple giraffe?",
    criteria={
        "mentioned": "the news mentions a purple giraffe",
        "not_mentioned": "the news does not mention a purple giraffe",
    },
)
SENTINEL_ITEM: Final = {
    "headline": "Visitors report an unusual animal",
    "snippet": "In an unrelated note, a purple giraffe named Zephyrine was seen near the loading dock.",
}
_SUBJECTS: Final = (
    "The regional planning committee",
    "A local library",
    "The parks department",
    "A community choir",
    "The volunteer fire brigade",
    "A neighborhood bakery",
    "The county museum",
    "A school robotics club",
    "The harbor authority",
    "A cycling association",
    "The botanical garden",
    "A chess society",
)
_VERBS: Final = (
    "reviewed",
    "announced",
    "discussed",
    "published",
    "updated",
    "scheduled",
    "completed",
    "postponed",
    "approved",
    "described",
)
_OBJECTS: Final = (
    "its program for the coming season",
    "a plan to repaint the visitor center",
    "new opening hours for the summer",
    "a guide to the walking trails",
    "the results of a survey of its members",
    "a series of evening lectures",
    "repairs to the old clock tower",
    "a collection of recipes from local families",
    "a timetable for the shuttle bus",
    "an exhibition of historical maps",
    "a cleanup day along the river",
    "a workshop on home gardening",
)


# --- spec builders ----------------------------------------------------------------------------------


def question_sets(battery: Battery) -> dict[str, dict[str, QuestionSpec]]:
    core = questions_from(battery.request("A", ["core"]))
    full = questions_from(battery.request("A", ["core", "extended"]))
    return {
        "q1": {"justified_move": core["justified_move"]},
        "q1q2": {"justified_move": core["justified_move"], "materiality": core["materiality"]},
        "core": core,
        "core_ext": full,
    }


def item_spec(
    item: CanaryItem,
    model: str,
    questions: Mapping[str, QuestionSpec],
    *,
    tag: str,
    repeat_idx: int = 0,
    params: Mapping[str, Any] | None = None,
) -> CallSpec:
    req = DecisionRequest(model=model, state=item.state, questions=dict(questions))
    return CallSpec(req, item.info, params=dict(params or {}), repeat_idx=repeat_idx, tag=tag)


def train_a(items: Sequence[CanaryItem]) -> list[CanaryItem]:
    return [it for it in items if it.group == "train_A"]


def billing_items(items: Sequence[CanaryItem]) -> list[CanaryItem]:
    """The shortest and the longest Call A canary state (ModernBERT tokens)."""
    a = sorted(train_a(items), key=lambda it: (it.n_tokens_state or 0, it.canary_id))
    return [a[0], a[-1]]


def billing_specs(
    items: Sequence[CanaryItem], model: str, qsets: Mapping[str, Any], names: Sequence[str] | None = None
) -> list[CallSpec]:
    """The billing calls: the two billing states × the question sets ``names`` (all four by default)."""
    keep = list(qsets) if names is None else list(names)
    return [item_spec(it, model, qsets[q], tag=f"billing_{q}") for it in billing_items(items) for q in keep]


def seed_specs(items: Sequence[CanaryItem], model: str, core: Mapping[str, QuestionSpec]) -> list[CallSpec]:
    return [
        item_spec(it, model, core, tag="seed", repeat_idx=r, params={"seed": s})
        for it in train_a(items)[:SEED_STATES]
        for s in SEEDS
        for r in (0, 1)
    ]


def seed_probe(items: Sequence[CanaryItem], model: str, core: Mapping[str, QuestionSpec]) -> CallSpec:
    return seed_specs(items, model, core)[0]


def canary_specs(items: Sequence[CanaryItem], model: str) -> list[CallSpec]:
    return [it.spec(model, tag="canary") for it in items]


def repeat_specs(items: Sequence[CanaryItem], model: str) -> list[CallSpec]:
    return [it.spec(model, repeat_idx=r, tag="repeat") for it in train_a(items) for r in range(1, REPEATS)]


def interaction_specs(items: Sequence[CanaryItem], model: str, qsets: Mapping[str, Any]) -> list[CallSpec]:
    return [
        item_spec(it, model, qsets[q], tag=f"interaction_{q}")
        for it in train_a(items)
        for q in ("q1", "core_ext")
    ]


def filler_items(rng: random.Random, n: int) -> list[dict[str, str]]:
    out = []
    for _ in range(n):
        sentences = [
            f"{rng.choice(_SUBJECTS)} {rng.choice(_VERBS)} {rng.choice(_OBJECTS)}." for _ in range(4)
        ]
        out.append({"headline": sentences[0][:-1], "snippet": " ".join(sentences[1:])})
    return out


def _news(items: Sequence[Mapping[str, str]], cb: Codebook) -> list[dict[str, str]]:
    return [
        {**dict(it), "source_type": cb.source_type_word("aggregator"), "timing": cb.timing["overnight"]}
        for it in items
    ]


_TRUNCATION_STATES: dict[tuple[int, str], dict[str, Any]] = {}


def truncation_state(target: int, where: str, tok: Any, cb: Codebook) -> dict[str, Any]:
    """``_truncation_state`` memoized per (target, where): the report stage asks for them many times."""
    if (target, where) not in _TRUNCATION_STATES:
        _TRUNCATION_STATES[(target, where)] = _truncation_state(target, where, tok, cb)
    return _TRUNCATION_STATES[(target, where)]


def _truncation_state(target: int, where: str, tok: Any, cb: Codebook) -> dict[str, Any]:
    """A Call A-shaped synthetic state of about ``target`` ModernBERT tokens (canonical JSON, no special
    tokens), with the sentinel item first (``start``), last (``end``) or absent (``none``)."""
    rng = random.Random(f"{SEED}:{target}")

    def n_tok(state: dict[str, Any]) -> int:
        return len(tok(canonical_json(state), add_special_tokens=False)["input_ids"])

    filler: list[dict[str, str]] = []
    sentinel = [SENTINEL_ITEM]
    while True:
        news = sentinel + filler if where == "start" else filler + sentinel if where == "end" else filler
        state = synthetic_state(cb, _news(news, cb))
        if n_tok(state) >= target:
            return state
        filler += filler_items(rng, 1)


def truncation_specs(model: str, tok: Any, cb: Codebook, targets: Sequence[int]) -> list[CallSpec]:
    out = []
    for target in targets:
        for where in ("end", "start", "none"):
            req = DecisionRequest(
                model=model,
                state=truncation_state(target, where, tok, cb),
                questions={"sentinel": SENTINEL_QUESTION},
            )
            out.append(CallSpec(req, SYNTHETIC_INFO, tag=f"truncation_{target}_{where}"))
    return out


def latency_states(layout: Layout | None, items: Sequence[CanaryItem]) -> pd.DataFrame:
    rel = "states/callA_d0_E3.parquet"
    frame = io.read_parquet(rel, columns=STATE_COLUMNS, layout=layout)
    exclude = frozenset(str(it.info.event_id) for it in items if it.info.event_id)
    return sample_train(frame, LATENCY_CALLS * len(CONCURRENCY), exclude=exclude)


def latency_specs(
    states: pd.DataFrame, model: str, core: Mapping[str, QuestionSpec]
) -> dict[int, list[CallSpec]]:
    out: dict[int, list[CallSpec]] = {}
    recs = states.to_dict("records")
    for i, c in enumerate(CONCURRENCY):
        chunk = recs[i * LATENCY_CALLS : (i + 1) * LATENCY_CALLS]
        out[c] = [
            CallSpec(
                DecisionRequest(model=model, state=json.loads(r["state_json"]), questions=dict(core)),
                state_info(r, "work/states/callA_d0_E3.parquet"),
                tag=f"latency_c{c}",
            )
            for r in chunk
        ]
    return out


# --- context ----------------------------------------------------------------------------------------


@dataclass
class Pilot:
    layout: Layout
    items: list[CanaryItem]
    battery: Battery
    cb: Codebook
    qsets: dict[str, dict[str, QuestionSpec]]

    @classmethod
    def load(cls, layout: Layout | None = None) -> Pilot:
        lay = resolve_layout(layout)
        battery = load_battery(lay.configs / "questions_v1.yaml")
        return cls(
            lay,
            load_canary(lay.root / CANARY_FILE),
            battery,
            load_codebook(lay.configs / "codebook_v1.yaml"),
            question_sets(battery),
        )

    def client(self, *, offline: bool = False) -> DecisionClient:
        return DecisionClient(CHUNK, pilot=True, offline=offline, layout=self.layout, session_id=SESSION_ID)

    def tokenizer(self) -> Any:
        from newsaction.events import tokens

        return tokens.tokenizer()


def log(msg: str) -> None:
    print(f"[{utc_now_iso()[:19]}] {msg}", flush=True)


def run_batch(
    client: DecisionClient, specs: Sequence[CallSpec], label: str, *, concurrency: int | None = None
) -> list[CallResult]:
    proj = client.dry_run(specs)
    log(
        f"{label}: {proj.n_send} to send, {proj.n_cached} cached; projected ${proj.usd:.5f}; "
        f"left ${client.budget_left():.5f}"
    )
    t0 = time.perf_counter()
    res = client.decide(specs, concurrency=concurrency)
    bad = [r for r in res if not r.ok]
    log(
        f"{label}: done in {time.perf_counter() - t0:.1f} s; {len(bad)} failed; "
        f"spent so far ${client.ledger.totals().chunk_usd:.6f}"
    )
    for r in bad[:3]:
        log(f"  failed {r.spec.request.model} status={r.status} error={(r.error or '')[:200]}")
    return res


def record_key_usage(pilot: Pilot, client: DecisionClient, label: str) -> dict[str, Any]:
    path = pilot.layout.root / KEY_USAGE_FILE
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    snap = {
        "label": label,
        "ts": utc_now_iso(),
        **client.key_usage(),
        "ledger_chunk_usd": client.ledger.totals().chunk_usd,
    }
    rows.append(snap)
    io.atomic_write_bytes(path, (json.dumps(rows, indent=2) + "\n").encode("utf-8"))
    log(f"key usage [{label}]: {snap}")
    return snap


# --- stages -----------------------------------------------------------------------------------------


def stage_catalog(pilot: Pilot, force: bool = False) -> int:
    path = pilot.layout.root / CATALOG_FILE
    if path.is_file() and not force:
        log(f"{CATALOG_FILE} exists (sha256 {load_snapshot(pilot.layout.root)['sha256'][:16]}…); kept")
        return 0
    with pilot.client() as client:
        rec = snapshot(client)
    write_snapshot(rec, pilot.layout.root)
    log(f"catalog: {rec['n_models']} models, sha256 {rec['sha256']}")
    return 0


def stage_billing(pilot: Pilot) -> int:
    core = pilot.qsets["core"]
    with pilot.client() as client:
        record_key_usage(pilot, client, "before billing")
        for model in PILOT_MODELS:
            run_batch(client, billing_specs(pilot.items, model, pilot.qsets), f"billing {model}")
            run_batch(client, [seed_probe(pilot.items, model, core)], f"seed probe {model}")
        for model, n in TOO_LONG.items():
            spec = truncation_specs(model, pilot.tokenizer(), pilot.cb, [n])[0]
            run_batch(client, [replace_tag(spec, "too_long")], f"too-long probe {model}")
        time.sleep(20)  # let the key's usage catch up
        record_key_usage(pilot, client, "after billing")
    return 0


def replace_tag(spec: CallSpec, tag: str) -> CallSpec:
    return CallSpec(spec.request, spec.info, params=spec.params, repeat_idx=spec.repeat_idx, tag=tag)


def billing_table(
    pilot: Pilot, client: DecisionClient, model: str, names: Sequence[str] | None = None
) -> dict[str, Any]:
    specs = billing_specs(pilot.items, model, pilot.qsets, names)
    res = cached_results(client, specs)
    n_q = {q: len(v) for q, v in pilot.qsets.items() if names is None or q in names}
    short, long_ = billing_items(pilot.items)
    rows: list[dict[str, Any]] = []
    for s, r in zip(specs, res, strict=True):
        q = s.tag.removeprefix("billing_")
        row = None if r is None else r.row
        rows.append(
            {
                "canary_id": next(
                    it.canary_id for it in (short, long_) if it.info.event_id == s.info.event_id
                ),
                "questions": q,
                "n_questions": n_q[q],
                "input_tokens": None if row is None else row.input_tokens,
                "cost": None if row is None else row.cost,
                "billed_bytes_once": billed_bytes(s.request, "once"),
                "billed_bytes_per_question": billed_bytes(s.request, "per_question"),
            }
        )
    out: dict[str, Any] = {"calls": rows}
    if all(r["input_tokens"] is not None for r in rows):
        by = {(r["canary_id"], r["n_questions"]): int(r["input_tokens"]) for r in rows}
        ns = sorted(set(n_q.values()))
        copies = state_copies(
            ns, [by[(short.canary_id, n)] for n in ns], [by[(long_.canary_id, n)] for n in ns]
        )
        out["state_copies"] = {str(k): round(v, 4) for k, v in copies.items()}
        out["billing_basis"] = basis_from_copies(copies)
    return out


def observations(results: Sequence[CallResult]) -> list[Observation]:
    return [
        Observation(r.spec.request, int(r.row.input_tokens), float(r.row.cost))
        for r in results
        if r.row is not None and r.row.input_tokens is not None and r.row.cost_source == "usage"
    ]


def write_calibration(path: Path, models: Mapping[str, CostCalibration], note: str) -> None:
    text = path.read_text(encoding="utf-8")
    lines = [f"  models:                        # {note}\n"]
    for mid, cal in sorted(models.items()):
        d = cal.model_dump()
        body = ", ".join(
            f"{k}: {json.dumps(round(v, 6) if isinstance(v, float) else v)}" for k, v in d.items()
        )
        lines.append(f"    {json.dumps(mid)}: {{{body}}}\n")
    new, n = re.subn(r"^  models:.*\n(?:    .*\n)*", "".join(lines), text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise DMError(f"{path}: no costmodel.models block")
    io.atomic_write_bytes(path, new.encode("utf-8"))


def stage_calibrate(pilot: Pilot, *, final: bool = False) -> int:
    snap = load_snapshot(pilot.layout.root)
    prices = {m["id"]: Price.from_catalog(m["pricing"]) for m in snap["models"]}
    cals: dict[str, CostCalibration] = {}
    per_question = []
    tok = pilot.tokenizer() if final else None
    with pilot.client(offline=True) as client:
        for model in [*PILOT_MODELS, *(smoke_models(pilot) if final else [])]:
            names = None if model in PILOT_MODELS else SMOKE_BILLING
            table = billing_table(pilot, client, model, names)
            basis = table.get("billing_basis")
            if basis is None:
                if model in PILOT_MODELS:
                    raise DMError(f"{model}: billing calls incomplete; run --stage billing")
                continue  # a smoke model that answered nothing
            if basis == "per_question":
                per_question.append(model)
            specs = billing_specs(pilot.items, model, pilot.qsets, names)
            if final and model in PILOT_MODELS:
                specs += measured_specs(pilot, model)
            elif final:
                specs += smoke_specs(pilot, model, tok)[:2]  # its two canary calls
            obs = observations([r for r in cached_results(client, specs) if r is not None])
            cals[model] = calibrate(model, obs, basis, prices[model])
            log(f"{model}: copies {table['state_copies']} → {basis}; {cals[model]}")
    note = (
        "pilot calibration (python -m newsaction.dm.pilot --stage "
        + ("report" if final else "calibrate")
        + ")"
    )
    write_calibration(pilot.layout.configs / "dm.yaml", cals, note)
    if per_question:
        log(f"STOP (PREREG §13): the state is billed per question by {per_question}")
        return 2
    return 0


def measured_specs(pilot: Pilot, model: str) -> list[CallSpec]:
    lat = latency_specs(pilot_latency_states(pilot), model, pilot.qsets["core"])
    return (
        canary_specs(pilot.items, model)
        + repeat_specs(pilot.items, model)
        + interaction_specs(pilot.items, model, pilot.qsets)
        + [s for c in CONCURRENCY for s in lat[c]]
    )


_LATENCY_CACHE: dict[str, pd.DataFrame] = {}


def pilot_latency_states(pilot: Pilot) -> pd.DataFrame:
    if "states" not in _LATENCY_CACHE:
        _LATENCY_CACHE["states"] = latency_states(pilot.layout, pilot.items)
    return _LATENCY_CACHE["states"]


def seeds_accepted(client: DecisionClient, pilot: Pilot, model: str) -> bool:
    """True if the billing stage's ``seed`` probe was answered (only HTTP 200 responses are cached)."""
    return client.cache.get(client.key(seed_probe(pilot.items, model, pilot.qsets["core"]))) is not None


def stage_measure(pilot: Pilot, models: Sequence[str] = PILOT_MODELS) -> int:
    core = pilot.qsets["core"]
    tok = pilot.tokenizer()
    lat_states = pilot_latency_states(pilot)
    with pilot.client() as client:
        for model in models:
            run_batch(client, canary_specs(pilot.items, model), f"canary {model}")
            run_batch(client, repeat_specs(pilot.items, model), f"repeats {model}")
            if seeds_accepted(client, pilot, model):
                run_batch(client, seed_specs(pilot.items, model, core), f"seeds {model}")
            run_batch(client, interaction_specs(pilot.items, model, pilot.qsets), f"interaction {model}")
            run_batch(client, truncation_specs(model, tok, pilot.cb, TRUNC_TOKENS), f"truncation {model}")
        for model in models:
            for c, specs in latency_specs(lat_states, model, core).items():
                run_batch(client, specs, f"latency {model} c={c}", concurrency=c)
    return 0


def smoke_models(pilot: Pilot) -> list[str]:
    snap = load_snapshot(pilot.layout.root)
    ids = [str(m["id"]) for m in snap["models"]]
    return [m for m in ids if not m.startswith("~") and free_base(m) is None and m not in PILOT_MODELS]


STATE_SHAPE: Final = re.compile(r"state must be a string or an object with only", re.IGNORECASE)


def as_text(spec: CallSpec) -> CallSpec:
    req = spec.request.model_copy(update={"state": spec.request.state_text()})
    return CallSpec(req, spec.info, params=spec.params, repeat_idx=spec.repeat_idx, tag=f"{spec.tag}_text")


def rejects_object_states(client: DecisionClient, model: str) -> bool:
    """True if the model refused our state objects with "state must be a string or an object with only …"."""
    att = client.cache.frame("attempts")
    errors = att.loc[(att["model"] == model) & (att["status"] == 400), "error"].dropna()
    return any(STATE_SHAPE.search(str(e)) for e in errors)


def smoke_specs(pilot: Pilot, model: str, tok: Any) -> list[CallSpec]:
    by_id = {it.canary_id: it for it in pilot.items}
    first_a = train_a(pilot.items)[0]
    first_b = next(it for it in pilot.items if it.group == "train_B")
    return [
        by_id[first_a.canary_id].spec(model, tag="canary"),
        by_id[first_b.canary_id].spec(model, tag="canary"),
        *truncation_specs(model, tok, pilot.cb, [SMOKE_TRUNC_TOKENS]),
    ]


def stage_smoke(pilot: Pilot) -> int:
    tok = pilot.tokenizer()
    with pilot.client() as client:
        for model in smoke_models(pilot):
            run_batch(client, smoke_specs(pilot, model, tok), f"smoke {model}")
            if rejects_object_states(client, model) and model not in client.config.state_as_text:
                specs = [as_text(s) for s in smoke_specs(pilot, model, tok)]
                run_batch(client, specs, f"smoke {model} (state as text)")
            if client.cache.get(client.key(smoke_specs(pilot, model, tok)[0])) is not None:
                specs = billing_specs(pilot.items, model, pilot.qsets, SMOKE_BILLING)
                run_batch(client, specs, f"smoke billing {model}")
        time.sleep(20)
        record_key_usage(pilot, client, "after smoke")
    return 0


def stage_laya(pilot: Pilot) -> int:
    tok = pilot.tokenizer()
    with pilot.client() as client:
        for model in LOCAL_MODELS:
            run_batch(client, canary_specs(pilot.items, model), f"canary {model}")
            reps = [s for s in repeat_specs(pilot.items, model) if s.repeat_idx <= LAYA_REPEATS]
            run_batch(client, reps, f"repeats {model}")
            run_batch(client, interaction_specs(pilot.items, model, pilot.qsets), f"interaction {model}")
            run_batch(client, truncation_specs(model, tok, pilot.cb, TRUNC_TOKENS), f"truncation {model}")
            backend = client.local_model(model)
            log(
                f"{model}: device {getattr(backend, 'device', '?')}, "
                f"load {getattr(backend, 'load_seconds', None)} s"
            )
    return 0


# --- report -----------------------------------------------------------------------------------------


def cached_results(client: DecisionClient, specs: Sequence[CallSpec]) -> list[CallResult | None]:
    """The cached result of each spec, or None (a failed call is not cached); nothing is sent."""
    from newsaction.dm.schemas import parse_response

    out: list[CallResult | None] = []
    for s in specs:
        key = client.key(s)
        row = client.cache.get(key)
        if row is None:
            out.append(None)
            continue
        parsed = parse_response(row.response, s.request.questions)
        out.append(CallResult(s, key, True, row, parsed, 200, None, 0, row.latency_ms))
    return out


def probs_of(r: CallResult | None, qid: str) -> tuple[float, ...] | None:
    if r is None or r.parsed is None or qid not in r.parsed.answers:
        return None
    return r.parsed.answers[qid].probs


def option_probs(r: CallResult | None) -> dict[tuple[str, str], float]:
    if r is None or r.parsed is None:
        return {}
    out = {}
    for qid, a in r.parsed.answers.items():
        if a.probs is not None:
            for opt, p in zip(r.spec.request.questions[qid].options(), a.probs, strict=True):
                out[(qid, opt)] = p
    return out


def nhat_of(r: CallResult | None) -> float | None:
    p = probs_of(r, "justified_move")
    return None if p is None else n_hat(p)


def _stats(xs: Sequence[float]) -> dict[str, float | int | None]:
    v = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    if not v:
        return {"n": 0, "mean": None, "median": None, "p95": None, "max": None}
    a = np.asarray(v)
    return {
        "n": len(v),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "p95": float(np.percentile(a, 95)),
        "max": float(a.max()),
    }


def status_counts(statuses: pd.Series) -> dict[str, int]:
    """Final HTTP statuses as {"200": n, "429": n, "transport": n} (a transport error has no status)."""
    out: dict[str, int] = {}
    for v in statuses.tolist():
        k = "transport" if v is None or (isinstance(v, float) and math.isnan(v)) else str(int(v))
        out[k] = out.get(k, 0) + 1
    return out


def _dp(a: Mapping[tuple[str, str], float], b: Mapping[tuple[str, str], float]) -> list[float]:
    return [abs(a[k] - b[k]) for k in a if k in b]


def item_repeats(pilot: Pilot, client: DecisionClient, model: str) -> dict[str, Any]:
    items = train_a(pilot.items)
    base = cached_results(client, [it.spec(model, tag="canary") for it in items])
    reps = cached_results(client, repeat_specs(pilot.items, model))
    by_item: dict[str, list[CallResult | None]] = defaultdict(list)
    for s, r in zip(repeat_specs(pilot.items, model), reps, strict=True):
        by_item[str(s.info.event_id)].append(r)
    dps, dns, identical, compared = [], [], 0, 0
    for it, b in zip(items, base, strict=True):
        pb, nb = option_probs(b), nhat_of(b)
        for r in by_item[str(it.info.event_id)]:
            pr = option_probs(r)
            if not pb or not pr:
                continue
            d = _dp(pb, pr)
            compared += 1
            identical += int(max(d) == 0.0)
            dps += d
            n = nhat_of(r)
            if nb is not None and n is not None:
                dns.append(abs(n - nb))
    return {
        "states": len(items),
        "repeats": REPEATS,
        "pairs_compared": compared,
        "identical_share": None if compared == 0 else identical / compared,
        "abs_dp_vs_repeat0": _stats(dps),
        "abs_dn_hat_vs_repeat0": _stats(dns),
    }


def item_seeds(pilot: Pilot, client: DecisionClient, model: str) -> dict[str, Any]:
    probe = seed_probe(pilot.items, model, pilot.qsets["core"])
    key = client.key(probe)
    if client.cache.get(key) is None:
        att = client.cache.frame("attempts")
        att = att.loc[att["key"] == key]
        status = None if att.empty else att["status"].iloc[-1]
        error = None if att.empty else str(att["error"].iloc[-1])[:300]
        return {"accepted": False, "status": None if status is None else int(status), "error": error}
    specs = seed_specs(pilot.items, model, pilot.qsets["core"])
    res = dict(
        zip(
            [(str(s.info.event_id), s.params["seed"], s.repeat_idx) for s in specs],
            cached_results(client, specs),
            strict=True,
        )
    )
    base = {
        str(it.info.event_id): r
        for it, r in zip(
            train_a(pilot.items)[:SEED_STATES],
            cached_results(
                client, [it.spec(model, tag="canary") for it in train_a(pilot.items)[:SEED_STATES]]
            ),
            strict=True,
        )
    }
    across, within, vs_none = [], [], []
    for eid in base:
        a1, a2 = option_probs(res.get((eid, 1, 0))), option_probs(res.get((eid, 2, 0)))
        b1 = option_probs(res.get((eid, 1, 1)))
        across += _dp(a1, a2)
        within += _dp(a1, b1)
        vs_none += _dp(a1, option_probs(base[eid]))
    return {
        "accepted": True,
        "abs_dp_seed1_vs_seed2": _stats(across),
        "abs_dp_same_seed_two_calls": _stats(within),
        "abs_dp_seed1_vs_no_seed": _stats(vs_none),
    }


def item_interaction(pilot: Pilot, client: DecisionClient, model: str) -> dict[str, Any]:
    items = train_a(pilot.items)
    core = cached_results(client, [it.spec(model, tag="canary") for it in items])
    inter = cached_results(client, interaction_specs(pilot.items, model, pilot.qsets))
    q1 = inter[0::2]
    ext = inter[1::2]
    d_q1 = [
        abs(a - b)
        for a, b in ((nhat_of(x), nhat_of(c)) for x, c in zip(q1, core, strict=True))
        if a is not None and b is not None
    ]
    d_ext = [
        abs(a - b)
        for a, b in ((nhat_of(x), nhat_of(c)) for x, c in zip(ext, core, strict=True))
        if a is not None and b is not None
    ]
    others = []
    for x, c in zip(ext, core, strict=True):
        px, pc = option_probs(x), option_probs(c)
        others += [abs(px[k] - pc[k]) for k in pc if k in px and k[0] != "justified_move"]
    return {
        "states": len(items),
        "abs_dn_hat_q1_alone_vs_core": _stats(d_q1),
        "abs_dn_hat_core_ext_vs_core": _stats(d_ext),
        "abs_dp_q2_q4_core_ext_vs_core": _stats(others),
    }


def item_truncation(
    pilot: Pilot, client: DecisionClient, model: str, targets: Sequence[int], tok: Any
) -> dict[str, Any]:
    specs = truncation_specs(model, tok, pilot.cb, targets)
    res = cached_results(client, specs)
    out: dict[str, Any] = {}
    for target in targets:
        cells: dict[str, Any] = {}
        for s, r in zip(specs, res, strict=True):
            if not s.tag.startswith(f"truncation_{target}_"):
                continue
            where = s.tag.rsplit("_", 1)[1]
            p = probs_of(r, "sentinel")
            usage = (
                {}
                if r is None or r.parsed is None or r.parsed.response is None
                else r.parsed.response.usage.model_dump()
            )
            cells[where] = {
                "p_mentioned": None if p is None else p[0],
                "detected": None if p is None else p[0] > 0.5,
                "input_tokens": usage.get("input_tokens"),
                "reported_truncation": usage.get("truncated"),
                "status": 200 if r is not None else last_status(client, client.key(s)),
            }
        end, start, none = (cells.get(w, {}) for w in ("end", "start", "none"))
        valid_control = start.get("detected") is True and none.get("detected") is False
        if end.get("detected") is None:
            verdict: str = "no answer"
        elif not valid_control:
            verdict = "inconclusive (controls failed)"
        elif end["detected"]:
            verdict = "read to the end"
        else:
            verdict = "reported truncation" if end.get("reported_truncation") else "silent truncation"
        out[str(target)] = {"cells": cells, "verdict": verdict}
    return out


def last_status(client: DecisionClient, key: str) -> int | None:
    att = client.cache.frame("attempts")
    att = att.loc[att["key"] == key]
    return None if att.empty or pd.isna(att["status"].iloc[-1]) else int(att["status"].iloc[-1])


def item_latency(pilot: Pilot, client: DecisionClient, model: str) -> dict[str, Any]:
    specs = latency_specs(pilot_latency_states(pilot), model, pilot.qsets["core"])
    att = client.cache.frame("attempts")
    att = att.loc[att["model"] == model]
    out: dict[str, Any] = {}
    for c, ss in specs.items():
        keys = [client.key(s) for s in ss]
        a = att.loc[att["key"].isin(keys)]
        ok = a.loc[a["status"] == 200]
        times = pd.to_datetime(a["created_at"], utc=True)
        span = (times.max() - times.min()).total_seconds() if len(a) else None
        out[str(c)] = {
            "calls": len(keys),
            "answered": int(ok["key"].nunique()),
            "attempts": len(a),
            "status_counts": status_counts(a["status"]),
            "latency_ms": _stats(ok["latency_ms"].tolist()),
            "wall_s_first_to_last_attempt": span,
        }
    headers: Counter[str] = Counter()
    for h in att["headers_json"]:
        for k, v in json.loads(h).items():
            headers[f"{k}={v}"] += 1
    return {"by_concurrency": out, "rate_limit_headers_seen": dict(headers.most_common(10))}


def model_rows(client: DecisionClient, model: str) -> list[Any]:
    return [r for r in client.cache.rows(chunk=CHUNK) if r.model == model]


def item_format(client: DecisionClient, model: str) -> dict[str, Any]:
    from newsaction.dm.schemas import parse_response

    n_ans = with_p = valid = renorm = legend = legend_ok = choice_argmax = n_choice = n_score = 0
    sums, score_gap, grid = [], [], []
    notes: Counter[str] = Counter()
    problems: Counter[str] = Counter()
    for row in model_rows(client, model):
        req = json.loads(row.request_json)
        qs = questions_from(req["questions"])
        parsed = parse_response(row.response, qs)
        for qid, a in parsed.answers.items():
            n_ans += 1
            valid += int(a.valid)
            renorm += int(a.renormalized)
            notes.update(a.notes)
            problems.update(p.split(" ")[0] if "sum to" not in p else "sum" for p in a.problems)
            raw = a.answer
            if raw is None or raw.probabilities is None:
                continue
            with_p += 1
            vals = [float(v) for v in raw.probabilities.values()]
            sums.append(abs(math.fsum(vals) - 1.0))
            grid.append(all(abs(v * 100 - round(v * 100)) < 1e-6 for v in vals))
            if qs[qid].type == "score":
                n_score += 1
                legend += int(getattr(raw, "legend", None) is not None)
                legend_ok += int("no legend" not in a.notes and not any("legend" in p for p in a.problems))
                if a.probs is not None:
                    score_gap.append(
                        abs(float(getattr(raw, "score", 0.0)) - sum(i * v for i, v in enumerate(a.probs)))
                    )
            else:
                n_choice += 1
                choice_argmax += int("the chosen option is not the most probable one" not in a.notes)
        for p in parsed.problems:
            problems[p] += 1
    return {
        "responses": len(model_rows(client, model)),
        "answers": n_ans,
        "valid_share": None if not n_ans else valid / n_ans,
        "renormalized": renorm,
        "renormalized_share": None if not n_ans else renorm / n_ans,
        "with_probabilities_share": None if not n_ans else with_p / n_ans,
        "abs_sum_minus_1": _stats(sums),  # of the probabilities as returned
        "probabilities_on_0.01_grid_share": None if not grid else sum(grid) / len(grid),
        "score_answers": n_score,
        "legend_present_share": None if not n_score else legend / n_score,
        "legend_matches_share": None if not n_score else legend_ok / n_score,
        "abs_score_minus_weighted_position": _stats(score_gap),
        "choice_is_argmax_share": None if not n_choice else choice_argmax / n_choice,
        "notes": dict(notes),
        "problems": dict(problems),
    }


def item_numeracy(pilot: Pilot, client: DecisionClient, model: str) -> dict[str, Any]:
    items = [it for it in pilot.items if it.group == "numeracy"]
    res = cached_results(client, [it.spec(model, tag="canary") for it in items])
    qs = questions_from(pilot.battery.request("B", ["core"]))
    keys = list(qs["reaction_adequacy"].options())
    rows: list[dict[str, Any]] = []
    for it, r in zip(items, res, strict=True):
        p = probs_of(r, "reaction_adequacy")
        if p is None:
            rows.append({"move_z": it.move_z, "answered": False})
            continue
        pm = dict(zip(keys, p, strict=True))
        rows.append(
            {
                "move_z": it.move_z,
                "answered": True,
                "j": adequacy_j(pm),
                "w": adequacy_w(pm),
                "expected_level": sum(
                    ADEQUACY_KEYS.index(k) * v for k, v in pm.items() if k != "wrong_direction"
                )
                / max(1e-12, 1 - pm["wrong_direction"]),
                "argmax": max(pm, key=lambda k: pm[k]),
                "n_hat": nhat_of(r),
            }
        )
    rises = sorted((x for x in rows if x["answered"] and x["move_z"] > 0), key=lambda x: x["move_z"])
    falls = sorted((x for x in rows if x["answered"] and x["move_z"] < 0), key=lambda x: -x["move_z"])
    j = [x["j"] for x in rises]
    steps_up = [b - a for a, b in itertools.pairwise(j)]
    rho = (
        float(pd.Series([x["move_z"] for x in rises]).corr(pd.Series(j), method="spearman"))
        if len(set(j)) > 1
        else None
    )
    return {
        "rows": rows,
        "rises_answered": len(rises),
        "j_non_increasing_in_rise": None if len(rises) < 2 else all(s <= 1e-9 for s in steps_up),
        "j_largest_step_up": None if not steps_up else max(steps_up),
        "spearman_j_vs_rise": rho,
        "mean_w_falls": None if not falls else float(np.mean([x["w"] for x in falls])),
        "mean_w_rises": None if not rises else float(np.mean([x["w"] for x in rises])),
    }


def item_policy_and_builds(client: DecisionClient, model: str) -> dict[str, Any]:
    rows = model_rows(client, model)
    att = client.cache.frame("attempts")
    att = att.loc[(att["model"] == model) & (att["chunk"] == CHUNK)]
    final = att.groupby("key").tail(1)
    failed = final.loc[final["status"] != 200]
    policy = [e for e in failed["error"].dropna() if DATA_POLICY.search(str(e))]
    return {
        "responses_200": len(rows),
        "final_failures": len(failed),
        "failure_statuses": status_counts(failed["status"]),
        "data_policy_rejections": len(policy),
        "data_policy_example": policy[0][:300] if policy else None,
        "deny_accepted": bool(rows) and not policy,
        "builds": dict(Counter(r.model_build for r in rows)),
        "providers": dict(Counter(r.provider for r in rows)),
    }


def cost_ratios(client: DecisionClient, model: str, price: Price) -> dict[str, Any]:
    ratios = [
        r.cost / price.usd(r.input_tokens)
        for r in model_rows(client, model)
        if r.input_tokens and r.cost_source == "usage" and price.usd(r.input_tokens) > 0
    ]
    sources = Counter(r.cost_source for r in model_rows(client, model))
    return {
        "price_per_m": price.prompt * 1e6,
        "ratio_cost_to_price_x_tokens": _stats(ratios),
        "cost_sources": dict(sources),
    }


def well_formed_specs(pilot: Pilot, model: str, tok: Any) -> list[CallSpec]:
    """The calls that count for eligibility: everything but the seed and too-long probes."""
    if model in PILOT_MODELS:
        return (
            billing_specs(pilot.items, model, pilot.qsets)
            + measured_specs(pilot, model)
            + truncation_specs(model, tok, pilot.cb, TRUNC_TOKENS)
        )
    return smoke_specs(pilot, model, tok)


def api_message(error: str) -> str:
    """The ``error.message`` of an OpenRouter error body, else the text."""
    try:
        return str(json.loads(error)["error"]["message"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return error


def probability_decimals(results: Sequence[CallResult]) -> int | None:
    """The most decimals any returned probability needs (2: a 0.01 grid; None: more than 8)."""
    worst = 0
    for r in results:
        if r.parsed is None:
            continue
        for a in r.parsed.answers.values():
            raw = None if a.answer is None else a.answer.probabilities
            for v in (raw or {}).values():
                d = next((d for d in range(9) if abs(v * 10**d - round(v * 10**d)) < 1e-6), None)
                if d is None:
                    return None
                worst = max(worst, d)
    return worst


def outcome_note(
    client: DecisionClient, model: str, trunc: str, renormalized: float, decimals: int | None
) -> str:
    cal = client.config.costmodel.models.get(model)
    parts = [f"2K sentinel: {trunc}"]
    if cal is not None:
        parts.append(f"state billed {'per question' if cal.billing_basis == 'per_question' else 'once'}")
    if decimals is not None and decimals <= 6:
        parts.append(f"probabilities to {decimals} decimals ({renormalized:.0%} of answers renormalized)")
    if model in client.config.state_as_text:
        parts.append("state sent as text")
    return "; ".join(parts)


def outcome_of(pilot: Pilot, client: DecisionClient, model: str, tok: Any) -> tuple[Outcome, dict[str, Any]]:
    specs = well_formed_specs(pilot, model, tok)
    unique = {client.key(s): s for s in specs}
    res = cached_results(client, list(unique.values()))
    ok = [r for r in res if r is not None]
    failed_keys = [k for k, r in zip(unique, res, strict=True) if r is None]
    att = client.cache.frame("attempts")
    errors = att.loc[att["key"].isin(failed_keys)].groupby("key").tail(1)
    policy = bool(len(errors)) and all(DATA_POLICY.search(str(e) or "") for e in errors["error"])
    answers = [a for r in ok if r.parsed is not None for a in r.parsed.answers.values()]
    invalid = [a for a in answers if not a.valid]
    renormalized = [a for a in answers if a.renormalized]
    trunc = item_truncation(pilot, client, model, [SMOKE_TRUNC_TOKENS], tok)[str(SMOKE_TRUNC_TOKENS)][
        "verdict"
    ]
    silent = (
        True
        if trunc == "silent truncation"
        else False
        if trunc in ("read to the end", "reported truncation")
        else None
    )
    envelope_bad = sum(1 for r in ok if r.parsed is not None and r.parsed.problems)
    final = att.loc[att["model"] == model].groupby("key").tail(1)  # every form tried, object or text state
    messages = Counter(api_message(str(e)) for e in final.loc[final["status"] != 200, "error"].dropna())
    o = Outcome(
        calls=len(unique),
        ok=len(ok),
        data_policy_rejected=policy and not ok,
        error_share=(len(unique) - len(ok)) / len(unique) if unique else 0.0,
        invalid_share=(len(invalid) + envelope_bad) / max(1, len(answers)),
        renormalized_share=len(renormalized) / max(1, len(answers)),
        missing_probabilities=any("missing probabilities" in a.problems for a in answers),
        silent_truncation=silent,
        note=outcome_note(
            client, model, trunc, len(renormalized) / max(1, len(answers)), probability_decimals(ok)
        ),
        rejection=" | ".join(m[:160] for m, _ in messages.most_common(2)) or None,
    )
    detail = {
        "calls": len(unique),
        "answered": len(ok),
        "failure_statuses": status_counts(errors["status"]),
        "failure_example": None if errors.empty else api_message(str(errors["error"].iloc[0]))[:300],
        "object_state_rejected": rejects_object_states(client, model),
        "state_as_text": model in client.config.state_as_text,
        "invalid_answers": len(invalid),
        "renormalized_answers": len(renormalized),
        "answers": len(answers),
        "probability_decimals": probability_decimals(ok),
        "invalid_examples": [f"{a.qid}: {'; '.join(a.problems)}" for a in invalid[:3]],
        "truncation_2k": trunc,
        "builds": dict(Counter(r.row.model_build for r in ok if r.row is not None)),
        "input_tokens_canary": [r.row.input_tokens for r in ok[:2] if r.row is not None],
        "cost": float(sum(r.row.cost for r in ok if r.row is not None)),
    }
    return o, detail


def laya_summary(pilot: Pilot, client: DecisionClient, model: str, tok: Any) -> dict[str, Any]:
    res = cached_results(client, canary_specs(pilot.items, model))
    ok = [r for r in res if r is not None and r.parsed is not None]
    sums: list[float] = []
    valid = truncated = 0
    for r in ok:
        assert r.parsed is not None
        valid += int(r.parsed.valid)
        sums += [abs(math.fsum(a.probs) - 1.0) for a in r.parsed.answers.values() if a.probs is not None]
        if r.parsed.response is not None:
            truncated += int(bool(r.parsed.response.usage.model_dump().get("truncated")))
    first20 = res[:20]
    return {
        "build": None if not ok or ok[0].row is None else ok[0].row.model_build,
        "provider": None if not ok or ok[0].row is None else ok[0].row.provider,
        "canary_answered": len(ok),
        "canary_valid": valid,
        "first_20_canary_valid": all(
            r is not None and r.parsed is not None and r.parsed.valid for r in first20
        ),
        "abs_sum_minus_1": _stats(sums),
        "canary_truncated": truncated,
        "latency_ms_canary": _stats([r.latency_ms for r in ok if r.latency_ms is not None]),
        "repeats": item_repeats_local(pilot, client, model),
        "interaction": item_interaction(pilot, client, model),
        "truncation": item_truncation(pilot, client, model, TRUNC_TOKENS, tok),
        "numeracy": item_numeracy(pilot, client, model),
    }


def item_repeats_local(pilot: Pilot, client: DecisionClient, model: str) -> dict[str, Any]:
    out = item_repeats(pilot, client, model)
    out["repeats"] = LAYA_REPEATS + 1  # repeat 0 (the canary) and repeats 1–2
    return out


# --- NA-11 projection (NA-04 owner decision 3) ------------------------------------------------------

PROJECTION_SOURCES: Final = {  # NA-03 component -> (state file, call, groups, splits used for the mean state)
    "A_D0": ("states/callA_d0_E3.parquet", "A", ("core", "extended"), None),
    "B_D2": ("states/callB_d2_E3.parquet", "B", ("core", "explain"), None),
    "B_D1": ("states/callB_d2_E3.parquet", "B", ("core", "explain"), None),
    "A_D2": ("states/callA_d2_E3.parquet", "A", ("core", "extended"), None),
    "final_selection": ("states/callA_d0_E3.parquet", "A", ("core",), ("val_b",)),
    "ablations": ("states/callB_d2_E3.parquet", "B", ("core",), ("val_a", "val_b")),
    "market": ("states/market_E3.parquet", "A", ("core",), ("val_a", "val_b", "test")),
}


REDUCED_BATTERY: Final = {
    "A": ("justified_move",),
    "B": ("justified_move", "reaction_adequacy"),
}  # PREREG §13


def na11_projection(
    pilot: Pilot, cals: Mapping[str, CostCalibration], prices: Mapping[str, Price]
) -> dict[str, Any]:
    """NA-03's NA-11 call counts × each calibrated model's tokens per call × its price (PREREG §13), with the
    planned batteries and with §13's reduced battery (Q1, + Q5 for Call B) for models billed per question."""
    csv = pd.read_csv(pilot.layout.root / "artifacts/NA-03/call_projection.csv")
    comps = csv.loc[csv["section"] == "component"]
    plans = csv.loc[csv["section"] == "plan"]
    mean_bytes: dict[tuple[str, str], float] = {}
    for rel in sorted({v[0] for v in PROJECTION_SOURCES.values()}):
        df = io.read_parquet(rel, columns=["split", "state_json"], layout=pilot.layout)
        df = df.assign(nbytes=[len(str(x).encode("utf-8")) for x in df["state_json"]])
        for split, g in df.groupby("split"):
            mean_bytes[(rel, str(split))] = float(g["nbytes"].mean())

    def questions(call: str, groups: tuple[str, ...], reduced: bool) -> dict[str, Any]:
        full = pilot.battery.request(call, list(groups))
        return {k: v for k, v in full.items() if k in REDUCED_BATTERY[call]} if reduced else full

    def component_usd(cal: CostCalibration, price: Price, reduced: bool) -> dict[str, float]:
        usd: dict[str, float] = {}
        for comp, g in comps.groupby("component"):
            if comp == "llm_baseline":
                usd[str(comp)] = 1.0
                continue
            rel, call, groups, splits = PROJECTION_SOURCES[str(comp)]
            qs = questions(call, groups, reduced)
            q_bytes = sum(len(canonical_json({k: v}).encode("utf-8")) for k, v in qs.items())
            tokens = 0.0
            for _, row in g.iterrows():
                sp = [str(row["split"])] if splits is None else list(splits)
                vals = [mean_bytes[(rel, x)] for x in sp if (rel, x) in mean_bytes]
                if not vals:  # no Call B state of the test period exists before the freeze: val-A/val-B mean
                    vals = [mean_bytes[(rel, x)] for x in ("val_a", "val_b") if (rel, x) in mean_bytes]
                tokens += float(row["calls"]) * cal_tokens(cal, float(np.mean(vals)), q_bytes, len(qs))
            usd[str(comp)] = price.usd(tokens) * cal.cost_ratio
        return usd

    def plan_usd(usd: Mapping[str, float]) -> dict[str, float]:
        return {
            str(p["plan"]): float(sum(usd[c] for c in str(p["components"]).split("+")))
            for _, p in plans.iterrows()
        }

    out: dict[str, Any] = {
        "source": "artifacts/NA-03/call_projection.csv (calls); work/states/* (state bytes)",
        "na11_cap_usd": float(plans["na11_cap_usd"].iloc[0]),
    }
    for model, cal in sorted(cals.items()):
        usd = component_usd(cal, prices[model], reduced=False)
        out[model] = {"billing_basis": cal.billing_basis, "components_usd": usd, "plans_usd": plan_usd(usd)}
        if cal.billing_basis == "per_question":
            out[model]["reduced_battery_plans_usd"] = plan_usd(
                component_usd(cal, prices[model], reduced=True)
            )
    return out


# --- report stage -----------------------------------------------------------------------------------


def write_artifact_parquet(pilot: Pilot, df: pd.DataFrame, rel: str, description: str) -> str:
    path = pilot.layout.root / rel
    tmp = path.with_name(f".{path.name}.tmp")
    df.reset_index(drop=True).to_parquet(tmp, index=False, engine="pyarrow")
    tmp.replace(path)
    entry = io.register_artifact(rel, producer=PRODUCER, description=description, layout=pilot.layout)
    return str(entry["sha256"])


def spend_summary(pilot: Pilot, client: DecisionClient) -> dict[str, Any]:
    t = client.ledger.totals()
    usage_path = pilot.layout.root / KEY_USAGE_FILE
    snaps = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.is_file() else []
    att = client.cache.frame("attempts")
    att = att.loc[att["chunk"] == CHUNK]
    failed_attempts = att.loc[att["status"] != 200]
    out: dict[str, Any] = {
        "ledger_chunk_usd": t.chunk_usd,
        "ledger_total_usd": t.total_usd,
        "held_chunk_usd": t.held_chunk_usd,
        "chunk_cap_usd": t.chunk_cap_usd,
        "cache_cost_sum_usd": math.fsum(client.cache.costs(CHUNK)),
        "reconcile_usd": client.reconcile(),
        "api_responses": int((client.cache.frame()["chunk"] == CHUNK).sum()),
        "attempts": len(att),
        "failed_attempts": len(failed_attempts),
        "failed_attempt_statuses": status_counts(failed_attempts["status"]),
        "key_usage_snapshots": snaps,
    }
    if snaps:
        first, last = snaps[0], snaps[-1]
        d_key = float(last["usage"]) - float(first["usage"])
        d_led = float(last["ledger_chunk_usd"]) - float(first["ledger_chunk_usd"])
        out["key_usage_delta_usd"] = d_key
        out["ledger_delta_usd"] = d_led
        out["key_minus_ledger_usd"] = d_key - d_led
    return out


def _clean(obj: Any) -> Any:
    """JSON-safe: NaN / inf → None, numpy scalars → Python, tuples → lists."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _answers(
    models: Mapping[str, Mapping[str, Any]], smoke: Mapping[str, Any], spend: Mapping[str, Any]
) -> dict[str, Any]:
    def by(fn: Any) -> dict[str, Any]:
        return {m: fn(v) for m, v in models.items()}

    copies = by(lambda v: v["billing"].get("state_copies"))
    medians = {
        m: float(np.median([float(k) for n, k in c.items() if int(n) > 1])) if c else None
        for m, c in copies.items()
    }
    smoke_basis = {m: d["billing"].get("billing_basis") for m, d in smoke.items()}
    ratios = [
        s
        for v in models.values()
        for s in (v["cost"]["ratio_cost_to_price_x_tokens"]["mean"],)
        if s is not None
    ]
    gap = spend.get("key_minus_ledger_usd")
    seeds = by(lambda v: v["seeds"])
    seed_change = {
        m: (
            None
            if not s.get("accepted")
            else (s["abs_dp_seed1_vs_seed2"]["mean"] or 0.0)
            > (s["abs_dp_same_seed_two_calls"]["mean"] or 0.0) + 0.005
        )
        for m, s in seeds.items()
    }
    trunc = by(lambda v: {L: c["verdict"] for L, c in v["truncation"].items()})
    lat = by(
        lambda v: {
            c: {
                "p50_ms": d["latency_ms"]["median"],
                "p95_ms": d["latency_ms"]["p95"],
                "answered": d["answered"],
                "calls": d["calls"],
                "statuses": d["status_counts"],
            }
            for c, d in v["latency"]["by_concurrency"].items()
        }
    )
    deny: dict[str, bool | None] = {
        **by(lambda v: v["policy_builds"]["deny_accepted"]),
        **{
            m: True if d["answered"] > 0 else False if d["outcome"]["data_policy_rejected"] else None
            for m, d in smoke.items()
        },
    }
    return {
        "1_billing_basis": {
            "question": "Is the state billed once per request or once per question?",
            "state_billed_once_all_pilot_models": all(
                v["billing"].get("billing_basis") == "once" for v in models.values()
            ),
            "median_state_copies_multi_question_by_model": medians,
            "state_copies_by_model": copies,
            "billing_basis_by_model": by(lambda v: v["billing"].get("billing_basis")),
            "smoke_state_copies_by_model": {m: d["billing"].get("state_copies") for m, d in smoke.items()},
            "smoke_billing_basis_by_model": smoke_basis,
            "billed_per_question": sorted(
                [m for m, b in smoke_basis.items() if b == "per_question"]
                + [m for m, v in models.items() if v["billing"].get("billing_basis") == "per_question"]
            ),
        },
        "2_cost_vs_price": {
            "question": "usage.cost vs catalog price × input_tokens; are failed calls billed?",
            "cost_ratio_mean_min": min(ratios) if ratios else None,
            "cost_ratio_mean_max": max(ratios) if ratios else None,
            "cost_ratio_by_model": by(lambda v: v["cost"]["ratio_cost_to_price_x_tokens"]),
            "failed_attempts": spend.get("failed_attempts"),
            "key_usage_minus_ledger_usd": gap,
            "failed_calls_billed": None
            if gap is None or not spend.get("failed_attempts")
            else bool(gap > 1e-6),
        },
        "3_truncation": {
            "question": "Is a sentinel at the end of 2K/4K/8K-token states detected?",
            "silent_truncation_any_model": any(
                x == "silent truncation" for t in trunc.values() for x in t.values()
            ),
            "verdict_by_model": trunc,
            "p_mentioned_end_by_model": by(
                lambda v: {
                    L: c["cells"].get("end", {}).get("p_mentioned") for L, c in v["truncation"].items()
                }
            ),
        },
        "4_repeat_variance": {
            "question": "20 states × 5 repeats: mean / max |Δp|; does a seed change it?",
            "mean_abs_dp_by_model": by(lambda v: v["repeats"]["abs_dp_vs_repeat0"]["mean"]),
            "max_abs_dp_by_model": by(lambda v: v["repeats"]["abs_dp_vs_repeat0"]["max"]),
            "mean_abs_dn_hat_by_model": by(lambda v: v["repeats"]["abs_dn_hat_vs_repeat0"]["mean"]),
            "identical_share_by_model": by(lambda v: v["repeats"]["identical_share"]),
            "seed_accepted_by_model": {m: bool(s.get("accepted")) for m, s in seeds.items()},
            "seed_changes_answers_by_model": seed_change,
        },
        "5_question_interaction": {
            "question": "Q1 alone vs within core vs within core + extended: mean |ΔN̂|",
            "mean_abs_dn_hat_q1_alone_vs_core_by_model": by(
                lambda v: v["interaction"]["abs_dn_hat_q1_alone_vs_core"]["mean"]
            ),
            "mean_abs_dn_hat_core_ext_vs_core_by_model": by(
                lambda v: v["interaction"]["abs_dn_hat_core_ext_vs_core"]["mean"]
            ),
            "repeat_noise_mean_abs_dn_hat_by_model": by(
                lambda v: v["repeats"]["abs_dn_hat_vs_repeat0"]["mean"]
            ),
        },
        "6_latency": {
            "question": "Latency p50 / p95 and errors at concurrency 1/4/8/16 (40 calls each); rate limits",
            "by_model": lat,
            "rate_limit_headers_seen": any(v["latency"]["rate_limit_headers_seen"] for v in models.values()),
        },
        "7_response_format": {
            "question": "Probabilities sum, legend present, score position consistent with probabilities",
            "valid_share_by_model": by(lambda v: v["format"]["valid_share"]),
            "renormalized_share_by_model": by(lambda v: v["format"]["renormalized_share"]),
            "max_abs_sum_minus_1_by_model": by(lambda v: v["format"]["abs_sum_minus_1"]["max"]),
            "legend_present_share_by_model": by(lambda v: v["format"]["legend_present_share"]),
            "mean_abs_score_minus_weighted_position_by_model": by(
                lambda v: v["format"]["abs_score_minus_weighted_position"]["mean"]
            ),
            "probabilities_on_0.01_grid_share_by_model": by(
                lambda v: v["format"]["probabilities_on_0.01_grid_share"]
            ),
        },
        "8_numeracy": {
            "question": "Fixed positive news, the reaction at 7 magnitudes × 2 directions (Call B): is "
            "reaction_adequacy monotone?",
            "j_non_increasing_in_rise_by_model": by(lambda v: v["numeracy"]["j_non_increasing_in_rise"]),
            "spearman_j_vs_rise_by_model": by(lambda v: v["numeracy"]["spearman_j_vs_rise"]),
            "mean_w_falls_by_model": by(lambda v: v["numeracy"]["mean_w_falls"]),
            "mean_w_rises_by_model": by(lambda v: v["numeracy"]["mean_w_rises"]),
        },
        "9_data_policy": {
            "question": "Are requests with provider.data_collection = deny accepted, per model?",
            "deny_accepted_by_model": deny,  # None: refused for another reason (state or question format)
            "any_rejected": any(v is False for v in deny.values()),
        },
        "10_builds": {
            "question": "Model build ids returned; catalog snapshot hash",
            "builds_by_model": by(lambda v: v["policy_builds"]["builds"]),
            "providers_by_model": by(lambda v: v["policy_builds"]["providers"]),
            "smoke_builds_by_model": {m: d["builds"] for m, d in smoke.items()},
        },
    }


REGISTERED: Final = {
    CATALOG_FILE: "decision-model catalog snapshot (GET /api/v1/models?output_modalities=decisions)",
    CANARY_FILE: "canary_v1: 50 fixed requests (30 train-period masked states, 20 synthetic) with sha256s",
    PILOT_FILE: "NA-05 pilot measurements (items 1-10), eligibility, cost calibration, projections, spend",
    KEY_USAGE_FILE: "OpenRouter key usage snapshots (GET /api/v1/key) during the NA-05 pilot",
}


def stage_report(pilot: Pilot, *, offline: bool = False) -> int:
    """Everything from the cache with an offline client; ``offline`` also skips the key-usage snapshot (GET
    /api/v1/key), so the stage makes no network call at all."""
    from dataclasses import asdict

    tok = pilot.tokenizer()
    root = pilot.layout.root
    snap = load_snapshot(root)
    prices = {str(m["id"]): Price.from_catalog(m["pricing"]) for m in snap["models"]}
    stop = stage_calibrate(pilot, final=True)
    cfg = dm_config(pilot.layout)
    if not offline:
        with pilot.client() as live:
            record_key_usage(pilot, live, "report")
    with pilot.client(offline=True) as client:
        models: dict[str, dict[str, Any]] = {}
        for m in PILOT_MODELS:
            log(f"report {m}")
            models[m] = {
                "billing": billing_table(pilot, client, m),
                "cost": cost_ratios(client, m, prices[m]),
                "truncation": item_truncation(pilot, client, m, TRUNC_TOKENS, tok),
                "repeats": item_repeats(pilot, client, m),
                "seeds": item_seeds(pilot, client, m),
                "interaction": item_interaction(pilot, client, m),
                "latency": item_latency(pilot, client, m),
                "format": item_format(client, m),
                "numeracy": item_numeracy(pilot, client, m),
                "policy_builds": item_policy_and_builds(client, m),
                "prompt_cache": prompt_cache_hits(client, m),
                "calibration": cfg.costmodel.models[m].model_dump() if m in cfg.costmodel.models else None,
            }
        outcomes: dict[str, Outcome] = {}
        smoke: dict[str, Any] = {}
        for m in [*PILOT_MODELS, *smoke_models(pilot)]:
            o, detail = outcome_of(pilot, client, m, tok)
            outcomes[m] = o
            entry = {**detail, "outcome": asdict(o), "failure": o.failure()}
            if m in PILOT_MODELS:
                models[m]["outcome"] = entry
            else:
                smoke[m] = {**entry, "billing": billing_table(pilot, client, m, SMOKE_BILLING)}
        laya = {m: laya_summary(pilot, client, m, tok) for m in LOCAL_MODELS}
        spend = spend_summary(pilot, client)
        frames = []
        for m in [*PILOT_MODELS, *LOCAL_MODELS]:
            pairs = [
                (it, r)
                for it, r in zip(
                    pilot.items, cached_results(client, canary_specs(pilot.items, m)), strict=True
                )
                if r is not None
            ]
            frames.append(probability_rows([p[0] for p in pairs], [p[1] for p in pairs]))
        baseline = pd.concat(frames, ignore_index=True)
        rows = eligibility(snap, outcomes, LOCAL_MODELS)
        included = [str(r["id"]) for r in rows if r["include"]]
        stage1 = na06_projection(pilot, client, included, cfg.costmodel.models, prices)
    write_eligibility(pilot.layout.configs / "frozen.yaml", rows, catalog_sha=str(snap["sha256"]))
    base_sha = write_artifact_parquet(
        pilot,
        baseline,
        CANARY_BASELINE,
        "canary_v1 baseline: p per model × canary id × question × option (repeat 0)",
    )
    canary_sha = io.sha256_file(root / CANARY_FILE)
    projection = na11_projection(
        pilot, {m: c for m, c in cfg.costmodel.models.items() if m in included}, prices
    )
    out = {
        "version": 1,
        "chunk": CHUNK,
        "generated_at": utc_now_iso(),
        "git_sha": git_sha(root),
        "catalog": {
            "file": CATALOG_FILE,
            "sha256": snap["sha256"],
            "fetched_at": snap["fetched_at"],
            "n_models": snap["n_models"],
        },
        "pilot_models": list(PILOT_MODELS),
        "local_models": list(LOCAL_MODELS),
        "stop_per_question_billing": stop == 2,
        "items": _answers(models, smoke, spend),
        "per_model": models,
        "smoke": smoke,
        "laya": laya,
        "eligibility": rows,
        "costmodel": {m: c.model_dump() for m, c in cfg.costmodel.models.items()},
        "na11_projection": projection,
        "na06_stage1_projection": stage1,
        "spend": spend,
        "canary": {
            "file": CANARY_FILE,
            "sha256": canary_sha,
            "states": len(pilot.items),
            "baseline_file": CANARY_BASELINE,
            "baseline_sha256": base_sha,
            "baseline_rows": len(baseline),
            "baseline_models": sorted(baseline["model"].unique().tolist()),
        },
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20,
    }
    text = json.dumps(_clean(out), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    io.atomic_write_bytes(root / PILOT_FILE, text.encode("utf-8"))
    for rel, description in REGISTERED.items():
        io.register_artifact(rel, producer=PRODUCER, description=description, layout=pilot.layout)
    log(
        f"wrote {PILOT_FILE} ({len(text)} bytes); spend ${spend['ledger_chunk_usd']:.6f}; "
        f"reconcile {spend['reconcile_usd']:.2e}"
    )
    return stop


STAGES: Final = ("catalog", "billing", "calibrate", "measure", "smoke", "laya", "report")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m newsaction.dm.pilot", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--force", action="store_true", help="catalog: refetch an existing snapshot")
    parser.add_argument("--models", nargs="*", default=None, help="measure: a subset of the pilot models")
    parser.add_argument(
        "--offline", action="store_true", help="report: no network call (no key-usage snapshot)"
    )
    args = parser.parse_args(argv)
    pilot = Pilot.load()
    t0 = time.perf_counter()
    if args.stage == "catalog":
        rc = stage_catalog(pilot, force=args.force)
    elif args.stage == "billing":
        rc = stage_billing(pilot)
    elif args.stage == "calibrate":
        rc = stage_calibrate(pilot)
    elif args.stage == "measure":
        rc = stage_measure(pilot, tuple(args.models) if args.models else PILOT_MODELS)
    elif args.stage == "smoke":
        rc = stage_smoke(pilot)
    elif args.stage == "laya":
        rc = stage_laya(pilot)
    else:
        rc = stage_report(pilot, offline=args.offline)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30  # bytes on macOS
    log(f"stage {args.stage}: exit {rc}, {time.perf_counter() - t0:.0f} s, peak RSS {rss:.2f} GB")
    return rc


def cal_tokens(cal: CostCalibration, state_bytes: float, question_bytes: float, n_questions: int) -> float:
    """Calibrated tokens of one request (``costmodel.CostModel.tokens``): the state once or per question."""
    copies = n_questions if cal.billing_basis == "per_question" else 1
    return (
        cal.overhead_tokens
        + copies * state_bytes / cal.bytes_per_token
        + question_bytes / cal.question_bytes_per_token
    )


def na06_projection(
    pilot: Pilot,
    client: DecisionClient,
    eligible: Sequence[str],
    cals: Mapping[str, CostCalibration],
    prices: Mapping[str, Price],
) -> dict[str, Any]:
    """PREREG §8.2 stage 1 (NA-06): 700 val-A D0 events × Call A core per eligible API model. Tokens per call
    from the pilot calibration, or for a smoke-tested model from its train Call A canary call (bytes per
    token)."""
    df = io.read_parquet("states/callA_d0_E3.parquet", columns=["split", "state_json"], layout=pilot.layout)
    val_a = [len(str(s).encode("utf-8")) for s in df.loc[df["split"] == "val_a", "state_json"]]
    core = pilot.battery.request("A", ["core"])
    q_bytes = sum(len(canonical_json({k: v}).encode("utf-8")) for k, v in core.items())
    req_bytes = float(np.mean(val_a)) + q_bytes
    first_a = train_a(pilot.items)[0]
    out: dict[str, Any] = {"events": 700, "mean_request_bytes": req_bytes, "by_model": {}}
    for m in eligible:
        if m.startswith("local/") or m not in prices:
            continue
        if m in cals:
            c = cals[m]
            tokens = cal_tokens(c, float(np.mean(val_a)), q_bytes, len(core))
            source = "pilot calibration"
        else:
            r = cached_results(client, [first_a.spec(m, tag="canary")])[0]
            if r is None or r.row is None or not r.row.input_tokens:
                continue
            sent = r.row.request_json
            body = json.loads(sent)
            state = body["state"] if isinstance(body["state"], str) else canonical_json(body["state"])
            b = len(state.encode("utf-8")) + sum(
                len(canonical_json({k: v}).encode("utf-8")) for k, v in body["questions"].items()
            )
            tokens = r.row.input_tokens * req_bytes / b
            source = f"{first_a.canary_id} canary call ({b / r.row.input_tokens:.2f} bytes per token)"
        usd = 700 * prices[m].usd(tokens)
        out["by_model"][m] = {
            "tokens_per_call": tokens,
            "usd": usd,
            "usd_per_1000_calls": usd / 0.7,
            "source": source,
        }
        if m in cals and cals[m].billing_basis == "per_question":  # PREREG §13's reduced battery: Q1 alone
            q1 = len(canonical_json({"justified_move": core["justified_move"]}).encode("utf-8"))
            out["by_model"][m]["usd_q1_only"] = 700 * prices[m].usd(
                cal_tokens(cals[m], float(np.mean(val_a)), q1, 1)
            )
    out["total_usd"] = float(sum(v["usd"] for v in out["by_model"].values()))
    return out


def prompt_cache_hits(client: DecisionClient, model: str) -> dict[str, Any]:
    """Calls billed far below their size (under half the model's median tokens per byte): a prompt cache."""
    rows = [r for r in model_rows(client, model) if r.input_tokens]
    ratios = []
    for r in rows:
        body = json.loads(r.request_json)
        state = body["state"] if isinstance(body["state"], str) else canonical_json(body["state"])
        b = len(state.encode("utf-8")) + sum(
            len(canonical_json({k: v}).encode("utf-8")) for k, v in body["questions"].items()
        )
        ratios.append((int(r.input_tokens or 0) / b, r.tag))
    if not ratios:
        return {"calls": 0, "reduced": 0}
    med = float(np.median([x for x, _ in ratios]))
    low = [tag for x, tag in ratios if x < med / 2]
    return {
        "calls": len(ratios),
        "median_tokens_per_byte": med,
        "reduced": len(low),
        "reduced_tags": dict(Counter(low)),
    }


if __name__ == "__main__":
    sys.exit(main())
