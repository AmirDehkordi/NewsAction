"""Laya zero-shot (PREREG §10.5; PRD NA-09 S6): local Laya typed-decisions on the Call A (D0) and Call B (D2)
states, core battery, through ``DecisionClient`` (cache, refusals; local, so no spend and no third party).

- **Run** (``run``): the (split, call) pairs of ``configs/baselines.yaml`` ``laya_zeroshot.order``, in
  batches of ``chunk_size`` requests. Every answer is cached as it arrives, so a stopped run resumes where it
  stopped, and requests NA-05 and NA-06 already answered (same model, state, questions and checkpoint
  settings) are cache hits. One request at a time: on MPS, laya's ``predict_batch`` (4, 8 or 16 states per
  forward pass) and two concurrent processes were both slower per state than single requests (NA-09
  decisions), and a single request gives the same float64 probabilities as a batched one.
- **Test period.** The client refuses every test-period state until the NA-11 freeze, for local models too
  (rule (b)); test Call A predictions are made in NA-11 after the freeze. ``run`` also refuses a test split
  before building any request.
- **Predictions** (``predictions``): offline (cache only), the common schema (``schema``): N_hat = N̂ of Q1,
  P_up / P_down = P(rise levels) / P(fall levels) of Q1, mag_hat = E|N̂|; ``extra`` holds M, surprise, tone
  (Call A) or J, W, C (Call B), the nine Q1 probabilities, the build and laya's truncation flag.
"""

from __future__ import annotations

import json
import resource
import time
from collections.abc import Sequence
from typing import Any, Final

import pandas as pd

from newsaction.baselines import CHUNK, BaselineError, BaselinesConfig, baselines_config
from newsaction.config import SplitName
from newsaction.dm.client import CallResult, CallSpec, DecisionClient
from newsaction.dm.parse import derive
from newsaction.dm.runner import load_states, state_specs
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso
from newsaction.states.questions import load_battery

MODEL_NAME: Final = "laya_zeroshot"
TAG: Final = "na09_laya_zs"
Q1: Final = "justified_move"
FALL_LEVELS: Final = (0, 1, 2, 3)
RISE_LEVELS: Final = (5, 6, 7, 8)


def log(msg: str) -> None:
    print(f"[{utc_now_iso()[:19]}] {msg}", flush=True)


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2  # bytes on macOS


def state_file(cfg: BaselinesConfig, call: str) -> str:
    if call == "A":
        return cfg.state_files.call_a
    if call == "B":
        return cfg.state_files.call_b
    raise BaselineError(f"unknown call {call!r}")


def specs_for(
    cfg: BaselinesConfig, split: SplitName, call: str, layout: Layout | None = None
) -> list[CallSpec]:
    """Core-battery requests of every state of ``split`` in the call's state file."""
    if split == "test":
        raise BaselineError("test-period Laya predictions are made in NA-11 after the freeze (CLAUDE.md B8)")
    lay = resolve_layout(layout)
    rel = state_file(cfg, call)
    rows = load_states(rel, splits=[split], layout=lay)
    battery = load_battery(lay.configs / "questions_v1.yaml")
    return state_specs(
        rows, rel, cfg.laya_zeroshot.model, call=call, groups=cfg.laya_zeroshot.groups, battery=battery,
        tag=f"{TAG}_{call}",
    )  # fmt: skip


def run(
    pairs: Sequence[tuple[SplitName, str]] | None = None,
    *,
    layout: Layout | None = None,
    chunk_size: int | None = None,
) -> dict[str, Any]:
    """Answer every request of ``pairs`` (default: the configured order); returns counts per pair."""
    lay = resolve_layout(layout)
    cfg = baselines_config(lay)
    todo = list(pairs if pairs is not None else cfg.laya_zeroshot.order)
    size = chunk_size or cfg.laya_zeroshot.chunk_size
    out: dict[str, Any] = {}
    with DecisionClient(CHUNK, layout=lay, concurrency=1) as client:
        for split, call in todo:
            specs = specs_for(cfg, split, call, lay)
            n_new = n_hit = 0
            t0 = time.perf_counter()
            log(f"{split} {call}: {len(specs)} requests")
            for i in range(0, len(specs), size):
                res = client.decide(specs[i : i + size], concurrency=1)
                bad = [r.spec.info.event_id for r in res if not (r.parsed is not None and r.parsed.valid)]
                if bad:
                    raise BaselineError(f"{split} {call}: invalid Laya answers for {bad[:5]}")
                hit = sum(r.cached for r in res)
                n_hit += hit
                n_new += len(res) - hit
                el = time.perf_counter() - t0
                rate = el / n_new if n_new else float("nan")
                left = (len(specs) - i - len(res)) * (rate if n_new else 0.0)
                log(
                    f"{split} {call}: {i + len(res)}/{len(specs)} (new {n_new}, cached {n_hit}); "
                    f"{rate:.3f} s per new request; about {left / 3600:.2f} h left; "
                    f"peak RSS {peak_rss_mb():.0f} MB"
                )
            out[f"{split}_{call}"] = {"requests": len(specs), "new": n_new, "cached": n_hit}
    return out


# --- predictions (offline) -------------------------------------------------------------------------------


def prediction_row(r: CallResult, call: str) -> dict[str, Any]:
    """One request's common-schema fields (``schema.PREDICTION_COLUMNS`` without the event keys)."""
    if r.parsed is None or not r.parsed.valid or r.row is None:
        raise BaselineError(f"{r.spec.info.event_id}: no valid Laya answer")
    q1 = r.parsed.answers[Q1].probs
    if q1 is None:
        raise BaselineError(f"{r.spec.info.event_id}: no Q1 probabilities")
    d = derive(r.parsed.answers, r.spec.request.questions)
    keep = ("m", "surprise", "tone") if call == "A" else ("j", "w", "c")
    usage = json.loads(r.row.response_json).get("usage", {})
    extra = {
        **{k: float(d[k]) for k in keep if k in d},
        "q1_probs": [float(p) for p in q1],
        "model_build": r.row.model_build,
        "truncated": bool(usage.get("truncated", False)),
    }
    return {
        "N_hat": float(d["n_hat"]),
        "P_up": float(sum(q1[i] for i in RISE_LEVELS)),
        "P_down": float(sum(q1[i] for i in FALL_LEVELS)),
        "mag_hat": float(d["abs_n_hat"]),
        "y_hat": None,
        "extra": json.dumps(extra, sort_keys=True),
    }


def predictions(layout: Layout | None = None) -> pd.DataFrame:
    """Every configured (split, call) from the cache (offline: a missing answer raises ``CacheMiss``)."""
    lay = resolve_layout(layout)
    cfg = baselines_config(lay)
    rows: list[dict[str, Any]] = []
    with DecisionClient(CHUNK, layout=lay, offline=True) as client:
        for split, call in cfg.laya_zeroshot.order:
            specs = specs_for(cfg, split, call, lay)
            for r in client.decide(specs):
                info = r.spec.info
                rows.append(
                    {
                        "event_id": info.event_id,
                        "model": MODEL_NAME,
                        "call": call,
                        "split": split,
                        **prediction_row(r, call),
                    }
                )
    return pd.DataFrame(rows)
