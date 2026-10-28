"""NA-11 canaries (PRD NA-11 S5; ``configs/dm.yaml`` ``canary``, NA-05 operator decision 3; the operator's
NA-11 instructions).

Before the freeze, for every production API model without an NA-05 canary baseline (the three comparators):

1. **Baseline** (NA-05's design, ``dm.pilot``): canary_v1 at repeat 0 (all 50 items) and repeats 1–4 of its 20
   train Call A items. The repeat noise is the mean |Δp| of repeats 1–4 against repeat 0 over every option
   (NA-05 pilot item 4); the per-repeat means give its range.
2. **Drift since NA-06**: 100 of NA-06's stage-2 val-A Call A states (core battery; the smallest
   u = sha256("2026:canary_drift:<event_id>")), asked again under repeat 1 (a new key) and compared with the
   cached NA-06 answers (repeat 0): mean |Δp| over every option, and the model builds of both. Repeat 2 of the
   same states gives the same-state noise (context only).
   **Rule (operator):** STOP and report if the drift's mean |Δp| exceeds the baseline's repeat noise.

After the freeze (S5, and again at the end of S6), ``compare`` asks the canary under a new repeat index and
compares it with the baseline (``dm.canary.compare``) under the ``configs/dm.yaml`` rule.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.dm.canary import CanaryItem, load_canary, probability_rows
from newsaction.dm.client import CallResult, CallSpec, DecisionClient
from newsaction.dm.pilot import REPEATS, cached_results, canary_specs, option_probs, repeat_specs, train_a
from newsaction.dm.runner import load_states, state_specs
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError, artifacts_dir

CANARY_FILE: Final = "artifacts/NA-05/canary_v1.jsonl"
BASELINE: Final = "canary_baseline_na11.parquet"
DRIFT: Final = "canary_drift_na06.csv"
STAGE2: Final = "dm/tournament/stage2.parquet"
STATES_A: Final = "states/callA_d0_E3.parquet"
N_DRIFT: Final = 100
DRIFT_REPEATS: Final = (1, 2)


def items(layout: Layout | None = None) -> list[CanaryItem]:
    return load_canary(resolve_layout(layout).root / CANARY_FILE)


def drift_events(model: str, layout: Layout | None = None) -> list[str]:
    """The 100 NA-06 stage-2 val-A Call A events with a valid answer from ``model``, smallest u first."""
    s2 = io.read_parquet(STAGE2, columns=["model", "event_id", "tag", "valid"], layout=layout)
    ev = s2.loc[(s2["model"] == model) & (s2["tag"] == "s2a") & s2["valid"].astype(bool), "event_id"].unique()
    u = {e: hashlib.sha256(f"2026:canary_drift:{e}".encode()).hexdigest() for e in ev}
    return sorted(ev, key=lambda e: u[e])[:N_DRIFT]


def drift_specs(
    model: str, events: Sequence[str], repeat_idx: int, layout: Layout | None = None
) -> list[CallSpec]:
    rows = load_states(STATES_A, event_ids=events, layout=layout)
    return state_specs(
        rows,
        STATES_A,
        model,
        call="A",
        groups=("core",),
        repeat_idx=repeat_idx,
        tag=f"na11_drift_r{repeat_idx}",
    )


def mean_abs_dp(a: Sequence[CallResult | None], b: Sequence[CallResult | None]) -> tuple[float, int]:
    """Mean |Δp| over the options both answers of each pair hold, and the number of pairs."""
    d: list[float] = []
    n = 0
    for x, y in zip(a, b, strict=True):
        px, py = option_probs(x), option_probs(y)
        if not px or not py:
            continue
        n += 1
        d += [abs(px[k] - py[k]) for k in px if k in py]
    return (float(np.mean(d)) if d else float("nan")), n


def builds(results: Sequence[CallResult | None]) -> list[str]:
    return sorted({str(r.row.model_build) for r in results if r is not None and r.row is not None})


def specs_for(model: str, layout: Layout | None = None) -> list[CallSpec]:
    """Every request of the pre-freeze check for ``model`` (for the dry run)."""
    its = items(layout)
    ev = drift_events(model, layout)
    out = canary_specs(its, model) + repeat_specs(its, model)
    for r in DRIFT_REPEATS:
        out += drift_specs(model, ev, r, layout)
    return out


def check_model(client: DecisionClient, model: str, layout: Layout | None = None) -> dict[str, Any]:
    """Run (or read from the cache) one model's baseline and drift requests and summarize them."""
    its = items(layout)
    client.decide(canary_specs(its, model) + repeat_specs(its, model))
    base = cached_results(client, [it.spec(model, tag="canary") for it in train_a(its)])
    per_repeat = []
    for r in range(1, REPEATS):
        rep = cached_results(client, [it.spec(model, repeat_idx=r, tag="repeat") for it in train_a(its)])
        per_repeat.append(mean_abs_dp(base, rep)[0])
    ev = drift_events(model, layout)
    old = cached_results(client, drift_specs(model, ev, 0, layout))
    if any(r is None for r in old):
        raise ProductionError(f"{model}: {sum(r is None for r in old)} NA-06 answers are not in the cache")
    for r in DRIFT_REPEATS:
        client.decide(drift_specs(model, ev, r, layout))
    new1 = cached_results(client, drift_specs(model, ev, 1, layout))
    new2 = cached_results(client, drift_specs(model, ev, 2, layout))
    drift, n_pairs = mean_abs_dp(old, new1)
    same, _ = mean_abs_dp(new1, new2)
    noise = float(np.mean(per_repeat))
    return {
        "model": model,
        "canary_noise_mean_abs_dp": noise,
        "canary_noise_per_repeat": per_repeat,
        "drift_mean_abs_dp_vs_na06": drift,
        "drift_pairs": n_pairs,
        "same_state_noise_mean_abs_dp": same,
        "builds_na06": builds(old),
        "builds_now": builds(new1 + new2),
        "stop": bool(drift > noise),
    }


def baseline_rows(
    client: DecisionClient, models: Sequence[str], layout: Layout | None = None
) -> pd.DataFrame:
    """The new baselines in NA-05's long format: repeat 0 of every item, repeats 1–4 of the train Call A
    items."""
    its = items(layout)
    parts = []
    for m in models:
        pairs = [(it, it.spec(m, tag="canary")) for it in its]
        reps = range(1, REPEATS)
        pairs += [(it, it.spec(m, repeat_idx=r, tag="repeat")) for it in train_a(its) for r in reps]
        res = cached_results(client, [s for _, s in pairs])
        ok = [(it, r) for (it, _), r in zip(pairs, res, strict=True) if r is not None]
        if ok:
            parts.append(probability_rows([it for it, _ in ok], [r for _, r in ok]))
    return pd.concat(parts, ignore_index=True)


def run(models: Sequence[str], *, send: bool, layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    with DecisionClient(CHUNK, layout=lay) as cl:
        specs = [s for m in models for s in specs_for(m, lay)]
        proj = cl.dry_run(specs)
        out: dict[str, Any] = {
            "n_requests": proj.n_requests,
            "n_send": proj.n_send,
            "n_cached": proj.n_cached,
            "projection_usd": proj.usd,
            "budget_left": cl.budget_left(),
        }
        if not send:
            return out
        rows = [check_model(cl, m, lay) for m in models]
        base = baseline_rows(cl, models, lay)
    path = artifacts_dir(lay)
    base.to_parquet(path / BASELINE, index=False)
    table = pd.DataFrame(rows)
    table.to_csv(path / DRIFT, index=False)
    out["table"] = rows
    out["stop"] = bool(table["stop"].any())
    return out
