"""Generative LLM at matched cost (PREREG §10.7; PRD NA-09 S7).

- **Model** (``select``): one rule (``configs/baselines.yaml`` ``llm.selection``) applied to the live
  OpenRouter catalog, fixed before any call. General-purpose instruction models of their original developers
  with a text output, priced ≤ $0.30/M input, supporting strict JSON-schema output, ``seed`` and
  ``temperature``, not reasoning models, with a published knowledge cutoff before the train start (no
  sample-period news in their pre-training data). Among them, the one whose projected cost per 1,000 Call A
  decisions is closest to the median realized cost of the NA-06 API decision models (matched cost); a tie
  goes to the later release. ``artifacts/NA-09/llm_catalog.json`` records the snapshot, every candidate, the
  rule and the choice; ``configs/frozen.yaml`` ``chat_models`` lists the chosen model (the client's
  eligibility for ``chat_json``).
- **Sample** (``sample``): 2,000 val-B D0 events with a Call A state after the embargo, stratified by tier ×
  month (NA-04's ``stratified_sample``, seed 2026). The test subsample runs in NA-11 after the freeze.
- **Prompt** (``messages``): a fixed system message, then the event's masked Call A state (its canonical JSON,
  the bytes the decision models receive), Q1's wording and its nine levels. The answer is one JSON object
  with a probability per level (``schema``; strict json_schema), temperature 0, seed 2026.
- **Parse**: ``schemas.parse_chat_response`` with ``llm.sum_tol``: numbers in [0, 1] summing to 1 within
  0.05 (off by more than 1e-6: renormalized and flagged), anything else invalid; no re-asking.
- **Predictions**: N_hat = Σ p_k m_k with Q1's midpoints (PREREG §7), P_up / P_down = P(rise / fall
  levels), mag_hat = E|N̂|. These are verbalized probabilities, not the model's own token probabilities
  (PRD NA-09 risks).

Third-party rule: the client refuses any state that is not third-party OK; every request carries
``data_collection: deny``.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import pandas as pd

from newsaction import io
from newsaction.baselines import ARTIFACTS, CHUNK, PRODUCER, BaselineError, BaselinesConfig, baselines_config
from newsaction.config import load_frozen
from newsaction.dm.canary import state_info
from newsaction.dm.client import ChatResult, ChatSpec, DecisionClient
from newsaction.dm.parse import Q1_MIDPOINTS
from newsaction.dm.schemas import ChatMessage, ChatRequest
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso
from newsaction.states.build import stratified_sample
from newsaction.states.questions import load_battery

MODEL_NAME: Final = "llm"
SAMPLE: Final = "baselines/llm_sample.parquet"
CATALOG: Final = f"{ARTIFACTS}/llm_catalog.json"
TAG: Final = "na09_llm_valb"
SCHEMA_NAME: Final = "q1_probabilities"
SYSTEM: Final = (
    "You are an equity analyst. You will read a JSON description of a US-listed company's situation: its "
    "sector, size, recent stock performance, the market backdrop and the news published about it before "
    "today's market open. Company names, tickers, people and dates are masked. Answer the question with a "
    "probability for each answer option, as a JSON object with exactly the given keys. The probabilities "
    "are numbers between 0 and 1 and sum to 1."
)
FALL: Final = (0, 1, 2, 3)
RISE: Final = (5, 6, 7, 8)


# --- the model ----------------------------------------------------------------------------------------


def option_key(level: str) -> str:
    """'very large fall (> 3 typical daily moves)' -> 'very_large_fall'."""
    head = level.split("(")[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", head).strip("_")


def q1_levels(layout: Layout | None = None) -> tuple[str, list[str], list[str]]:
    """(Q1 instructions, its nine levels low to high, their answer keys)."""
    q = load_battery(resolve_layout(layout).configs / "questions_v1.yaml").request("A", ["core"])[
        "justified_move"
    ]
    levels = [str(c) for c in q["criteria"]]
    keys = [option_key(c) for c in levels]
    if len(set(keys)) != len(keys) or len(keys) != len(Q1_MIDPOINTS):
        raise BaselineError(f"Q1 levels do not give nine distinct keys: {keys}")
    return str(q["instructions"]), levels, keys


def schema(layout: Layout | None = None) -> dict[str, Any]:
    _, levels, keys = q1_levels(layout)
    return {
        "type": "object",
        "properties": {
            k: {"type": "number", "description": lvl} for k, lvl in zip(keys, levels, strict=True)
        },
        "required": keys,
        "additionalProperties": False,
    }


def messages(state_json: str, layout: Layout | None = None) -> list[dict[str, str]]:
    instructions, levels, keys = q1_levels(layout)
    opts = "\n".join(f"- {k}: {lvl}" for k, lvl in zip(keys, levels, strict=True))
    user = (
        f"State:\n{state_json}\n\nQuestion: {instructions}\n\n"
        f"Answer options, from the lowest to the highest (key: meaning):\n{opts}\n\n"
        "Give the probability of each option."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def reference_cost(cfg: BaselinesConfig, layout: Layout | None = None) -> float:
    """The median realized USD per 1,000 Call A requests of the NA-06 API decision models."""
    lb = pd.read_csv(resolve_layout(layout).root / cfg.llm.selection.reference)
    api = lb.loc[lb["kind"] == "api", "cost_per_1000_a"].dropna()
    return float(statistics.median(api.astype(float)))


def candidates(
    models: Sequence[Mapping[str, Any]], cfg: BaselinesConfig, mean_input_bytes: float
) -> list[dict[str, Any]]:
    """Every catalog model that passes the rule, with its projected USD per 1,000 decisions."""
    sel = cfg.llm.selection
    out = []
    for m in models:
        mid = str(m["id"])
        arch = m.get("architecture") or {}
        params = set(m.get("supported_parameters") or [])
        pricing = m.get("pricing") or {}
        try:
            prompt, completion = float(pricing.get("prompt", "nan")), float(pricing.get("completion", "nan"))
        except (TypeError, ValueError):
            continue
        cutoff = m.get("knowledge_cutoff")
        ok = (
            mid.split("/")[0] in sel.developers
            and not any(w in mid for w in sel.exclude_id_words)
            and "text" in (arch.get("input_modalities") or [])
            and list(arch.get("output_modalities") or []) == ["text"]
            and 0 < prompt <= sel.max_prompt_usd_per_m * 1e-6
            and completion >= 0
            and set(sel.required_parameters) <= params
            and (sel.reasoning or m.get("reasoning") is None)
            and isinstance(cutoff, str)
            and cutoff < sel.cutoff_before.isoformat()
        )
        if not ok:
            continue
        tokens_in = mean_input_bytes / sel.bytes_per_token
        usd = (prompt * tokens_in + completion * sel.output_tokens) * 1000.0
        out.append(
            {
                "id": mid,
                "name": m.get("name"),
                "created": m.get("created"),
                "knowledge_cutoff": cutoff,
                "context_length": m.get("context_length"),
                "pricing": pricing,
                "supported_parameters": sorted(params),
                "architecture": arch,
                "projected_usd_per_1000": usd,
            }
        )
    return out


def choose(cands: Sequence[Mapping[str, Any]], reference: float) -> list[str]:
    """Candidate ids in the rule's order: closest projected cost to ``reference``, then the later release."""
    ranked = sorted(
        cands, key=lambda c: (abs(float(c["projected_usd_per_1000"]) - reference), -int(c["created"]))
    )
    return [str(c["id"]) for c in ranked]


def write_catalog(
    raw: Mapping[str, Any], cfg: BaselinesConfig, layout: Layout | None = None
) -> dict[str, Any]:
    """Apply the rule to a fetched catalog and write ``artifacts/NA-09/llm_catalog.json``."""
    lay = resolve_layout(layout)
    smp = io.read_parquet(SAMPLE, layout=lay)
    mean_state = statistics.fmean(len(str(t).encode("utf-8")) for t in smp["state_json"])
    prompt_bytes = len(json.dumps(messages("", lay)).encode("utf-8")) + len(
        json.dumps(schema(lay)).encode("utf-8")
    )
    cands = candidates(raw["data"], cfg, mean_state + prompt_bytes)
    ref = reference_cost(cfg, lay)
    order = choose(cands, ref)
    if not order:
        raise BaselineError("no catalog model passes the LLM selection rule")
    text = json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
    snap = {
        "fetched_at": utc_now_iso(),
        "url": "https://openrouter.ai/api/v1/models",
        "raw_sha256": hashlib.sha256(text).hexdigest(),
        "n_models": len(raw["data"]),
        "rule": cfg.llm.selection.model_dump(mode="json"),
        "reference_usd_per_1000": ref,
        "mean_input_bytes": mean_state + prompt_bytes,
        "order": order,
        "chosen": order[0],
        "models": sorted(cands, key=lambda c: order.index(str(c["id"]))),
    }
    path = lay.root / CATALOG
    io.atomic_write_bytes(path, (json.dumps(snap, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    io.register_artifact(
        CATALOG, producer=PRODUCER, description="NA-09 S7 chat-model catalog and choice", layout=lay
    )
    return snap


def chosen_model(layout: Layout | None = None) -> str:
    """The chat model listed (include: true) in ``configs/frozen.yaml`` ``chat_models``."""
    rows = getattr(load_frozen(resolve_layout(layout).configs / "frozen.yaml"), "chat_models", None) or []
    ids = [str(r["id"]) for r in rows if isinstance(r, Mapping) and r.get("include") is True]
    if len(ids) != 1:
        raise BaselineError(f"configs/frozen.yaml chat_models must include exactly one model, found {ids}")
    return ids[0]


# --- the sample and the requests ---------------------------------------------------------------------------


def sample(cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    """The 2,000 val-B D0 events (tier × month, seed), with their Call A state rows."""
    from newsaction.baselines.data import d0_events
    from newsaction.dm.canary import STATE_COLUMNS

    lay = resolve_layout(layout)
    ev = d0_events(cfg, lay)
    pool = ev.loc[(ev["split"] == "val_b") & ~ev["embargo"].astype(bool)]
    smp = stratified_sample(pool, cfg.llm.sample, cfg.llm.strata, cfg.seed)
    states = io.read_parquet(cfg.state_files.call_a, columns=STATE_COLUMNS, layout=lay)
    out = smp[["event_id", "tier", "month"]].merge(states, on="event_id", how="left", validate="one_to_one")
    if bool(out["state_json"].isna().any()):
        raise BaselineError("a sampled event has no Call A state")
    return out.sort_values(["session", "event_id"], kind="mergesort").reset_index(drop=True)


def specs(
    rows: pd.DataFrame, model: str, cfg: BaselinesConfig, layout: Layout | None = None
) -> list[ChatSpec]:
    sch = schema(layout)
    out = []
    for rec in rows.to_dict("records"):
        info = state_info(rec, f"work/{cfg.state_files.call_a}")
        req = ChatRequest(
            model=model,
            messages=tuple(ChatMessage.model_validate(m) for m in messages(str(rec["state_json"]), layout)),
            schema_name=SCHEMA_NAME,
            json_schema=sch,
            temperature=cfg.llm.temperature,
            seed=cfg.llm.seed,
            max_tokens=cfg.llm.max_tokens,
        )
        out.append(ChatSpec(req, info, str(rec["state_sha256"]), cfg.llm.sum_tol, tag=TAG))
    return out


def prediction_row(r: ChatResult) -> dict[str, Any]:
    """The common-schema fields of one answer; an invalid answer has null predictions and its problems."""
    p = r.parsed
    extra: dict[str, Any] = {"model_id": r.spec.request.model}
    if r.row is not None:
        extra |= {"model_build": r.row.model_build, "provider": r.row.provider, "cost": r.row.cost}
    if p is None or not p.valid or p.probs is None:
        extra["problems"] = [] if p is None else list(p.problems)
        return {"N_hat": None, "P_up": None, "P_down": None, "mag_hat": None, "extra": extra, "valid": False}
    q = p.probs
    extra |= {"q1_probs": list(q), "renormalized": p.renormalized, "raw_sum": p.raw_sum}
    return {
        "N_hat": sum(pk * mk for pk, mk in zip(q, Q1_MIDPOINTS, strict=True)),
        "P_up": sum(q[i] for i in RISE),
        "P_down": sum(q[i] for i in FALL),
        "mag_hat": sum(pk * abs(mk) for pk, mk in zip(q, Q1_MIDPOINTS, strict=True)),
        "extra": extra,
        "valid": True,
    }


def snapshot_key(client: DecisionClient, label: str, layout: Layout | None = None) -> dict[str, Any]:
    """Append the account's credits and the key's usage to ``artifacts/NA-09/key_usage.json``."""
    lay = resolve_layout(layout)
    rec = {"label": label, "ts": datetime.now(UTC).isoformat(), **client.key_usage(), **client.credits()}
    rec["ledger_chunk_usd"] = client.ledger.totals().chunk_usd
    path = lay.root / ARTIFACTS / "key_usage.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    io.atomic_write_bytes(path, (json.dumps([*old, rec], indent=2) + "\n").encode("utf-8"))
    return rec


def run(layout: Layout | None = None, *, send: bool = False) -> dict[str, Any]:
    """Dry run (always) and, with ``send``, the calls: refused unless the account can pay the projection
    (STOP: ask the operator to top up)."""
    lay = resolve_layout(layout)
    cfg = baselines_config(lay)
    model = chosen_model(lay)
    rows = io.read_parquet(SAMPLE, layout=lay)
    sp = specs(rows, model, cfg, lay)
    with DecisionClient(CHUNK, layout=lay, concurrency=cfg.llm.concurrency) as client:
        proj = client.dry_run_chat(sp)
        out: dict[str, Any] = {
            "model": model,
            "n_requests": proj.n_requests,
            "n_send": proj.n_send,
            "projected_usd": proj.usd,
            "projected_tokens": proj.tokens,
            "budget_left_usd": client.budget_left(),
        }
        if proj.n_send and send:
            left = client.account_left()
            out["account_left_usd"] = left
            if left < proj.usd:
                raise BaselineError(
                    f"the account has ${left:.4f} left, below the projection ${proj.usd:.4f}: STOP, ask the "
                    "operator to top up"
                )
            snapshot_key(client, "before NA-09 S7", lay)
            res = client.chat_json_batch(sp)
            snapshot_key(client, "after NA-09 S7", lay)
            out["answered"] = sum(r.ok for r in res)
            out["valid"] = sum(bool(r.parsed is not None and r.parsed.valid) for r in res)
            out["spent_usd"] = sum(r.row.cost for r in res if r.row is not None and not r.cached)
            out["reconcile"] = client.reconcile()
    return out


def predictions(layout: Layout | None = None) -> pd.DataFrame:
    """Every sampled event's answer from the cache (offline)."""
    lay = resolve_layout(layout)
    cfg = baselines_config(lay)
    rows = io.read_parquet(SAMPLE, layout=lay)
    with DecisionClient(CHUNK, layout=lay, offline=True) as client:
        res = client.chat_json_batch(specs(rows, chosen_model(lay), cfg, lay))
    out = []
    for r in res:
        d = prediction_row(r)
        info = r.spec.info
        if not d["valid"]:
            continue  # counted in the summary (``summary``); the schema needs a prediction per row
        out.append(
            {
                "event_id": info.event_id,
                "model": MODEL_NAME,
                "call": "A",
                "split": info.split,
                **{k: d[k] for k in ("N_hat", "P_up", "P_down", "mag_hat")},
                "extra": json.dumps(d["extra"], sort_keys=True),
            }
        )
    return pd.DataFrame(out)


def summary(layout: Layout | None = None) -> dict[str, Any]:
    """Validity, flags, tokens, cost (total and per 1,000 decisions) and latency of the sample's answers."""
    lay = resolve_layout(layout)
    cfg = baselines_config(lay)
    rows = io.read_parquet(SAMPLE, layout=lay)
    with DecisionClient(CHUNK, layout=lay, offline=True) as client:
        res = client.chat_json_batch(specs(rows, chosen_model(lay), cfg, lay))
    paid = [r.row for r in res if r.row is not None]
    valid = [r for r in res if r.parsed is not None and r.parsed.valid]
    problems: dict[str, int] = {}
    for r in res:
        for prob in [] if r.parsed is None or r.parsed.valid else r.parsed.problems:
            key = prob.split(" sum to ")[0] if " sum to " in prob else prob
            problems[key] = problems.get(key, 0) + 1
    cost = sum(row.cost for row in paid)
    lat = sorted(float(row.latency_ms) for row in paid if row.latency_ms is not None)
    return {
        "model": chosen_model(lay),
        "builds": sorted({str(row.model_build) for row in paid}),
        "providers": sorted({str(row.provider) for row in paid}),
        "n": len(res),
        "answered": len(paid),
        "valid": len(valid),
        "invalid": len(res) - len(valid),
        "problems": problems,
        "renormalized": sum(bool(r.parsed is not None and r.parsed.renormalized) for r in valid),
        "raw_sum_min": min(
            (float(r.parsed.raw_sum) for r in valid if r.parsed and r.parsed.raw_sum), default=None
        ),
        "raw_sum_max": max(
            (float(r.parsed.raw_sum) for r in valid if r.parsed and r.parsed.raw_sum), default=None
        ),
        "input_tokens_mean": statistics.fmean(float(row.input_tokens or 0) for row in paid) if paid else None,
        "output_tokens_mean": statistics.fmean(float(row.output_tokens or 0) for row in paid)
        if paid
        else None,
        "cost_usd": cost,
        "cost_per_1000": cost / len(paid) * 1000 if paid else None,
        "latency_ms_p50": lat[len(lat) // 2] if lat else None,
        "latency_ms_p95": lat[int(0.95 * (len(lat) - 1))] if lat else None,
    }
