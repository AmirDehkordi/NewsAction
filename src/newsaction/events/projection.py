"""Call and cost projection for NA-11 production (PRD NA-03 S6; PREREG §13, A2.6).

Tokens per call = the event's news tokens + ``context_tokens`` + the question tokens: the core battery
for every model, plus ``extended_question_tokens`` for the primary API instrument (A2 extended group on
Call A, explain group on Call B). Exact question lengths come from ``configs/questions_v1.yaml`` in
NA-04.

Components, over the events of val-A, val-B and test (embargoed events included, conservatively):
- ``A_D0``: primary, Call A on D0 events, core + extended (minimal plan);
- ``B_D2``: primary, Call B on D2 events, core + explain (minimal plan);
- ``B_D1``: primary, Call B at D1 on D0 events, core + explain (only with NA-10 bars);
- ``A_D2``: primary, Call A on W2 news (A3.1), core + extended. A D2 event whose article list equals
  its D0 event's has an identical state, which hits the cache, so only the others count;
- ``final_selection``: NA-11 S2, the top-2 API survivors on every val-B D0 event, core;
- ``ablations``: NA-11 S8, 12,000 events × 3 calls (D2 news), core;
- ``llm_baseline``: NA-11 S8, a fixed allowance;
- ``market``: A3.5 (optional), one market state per val + test session; D0 mean tokens as a proxy.

The NA-11 cap is checked at ``flag_usd_per_m`` ($0.042/M, Jev's list price) for each plan total.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.config import load_project
from newsaction.events import EVENTS_D0, EVENTS_D2, ProjectionConfig, load_events_config
from newsaction.paths import Layout, resolve_layout

PRODUCTION_SPLITS: Final = ("val_a", "val_b", "test")
PLANS: Final[dict[str, tuple[str, ...]]] = {
    "minimal (S6: A_D0 + B_D2)": ("A_D0", "B_D2"),
    "minimal + D1": ("A_D0", "B_D2", "B_D1"),
    "NA-11 full (S2, S6, S8)": ("A_D0", "B_D2", "A_D2", "final_selection", "ablations", "llm_baseline"),
    "NA-11 full + D1 + A3.5": (
        "A_D0",
        "B_D2",
        "A_D2",
        "B_D1",
        "final_selection",
        "ablations",
        "llm_baseline",
        "market",
    ),
}


def _cost_cols(prices: tuple[float, ...]) -> list[str]:
    return [f"usd_at_{p:g}_per_m" for p in prices]


def event_counts(d0: pd.DataFrame, d2: pd.DataFrame) -> pd.DataFrame:
    """Events and news tokens per split × tier × window (every split)."""
    parts = []
    for window, ev, col in (("W0", d0, "news_tokens_w0"), ("W2", d2, "news_tokens_w2")):
        g = ev.assign(tier=ev["tier"].fillna("none")).groupby(["split", "tier"], dropna=False)[col]
        t = g.agg(events="size", news_tokens_total="sum", news_tokens_mean="mean").reset_index()
        t.insert(0, "window", window)
        parts.append(t)
    return pd.concat(parts, ignore_index=True)


def identical_lists(d0: pd.DataFrame, d2: pd.DataFrame) -> pd.Series:
    """For each D2 event: True when its article list equals its D0 event's (same company-session)."""
    ids0 = {
        (c, s): tuple(x["id"] for x in lst)
        for c, s, lst in zip(d0["company_id"], d0["session"], d0["news_w0"], strict=True)
    }
    return pd.Series(
        [
            ids0.get((c, s)) == tuple(x["id"] for x in lst)
            for c, s, lst in zip(d2["company_id"], d2["session"], d2["news_w2"], strict=True)
        ],
        index=d2.index,
    )


def plan_components(d0: pd.DataFrame, d2: pd.DataFrame, cfg: ProjectionConfig) -> pd.DataFrame:
    """One row per (component, split): calls and total tokens."""
    base = cfg.context_tokens + cfg.core_question_tokens
    ext = base + cfg.extended_question_tokens
    p0 = d0.loc[d0["split"].isin(PRODUCTION_SPLITS)]
    p2 = d2.loc[d2["split"].isin(PRODUCTION_SPLITS)]
    same = identical_lists(d0, d2).loc[p2.index]
    rows: list[dict[str, Any]] = []

    def add(comp: str, split: str, calls: int, tokens: float, battery: str, note: str) -> None:
        rows.append(
            {
                "component": comp,
                "split": split,
                "battery": battery,
                "calls": calls,
                "tokens": tokens,
                "note": note,
            }
        )

    for split in PRODUCTION_SPLITS:
        e0 = p0.loc[p0["split"] == split, "news_tokens_w0"]
        e2 = p2.loc[p2["split"] == split, "news_tokens_w2"]
        e2_new = p2.loc[(p2["split"] == split) & ~same, "news_tokens_w2"]
        add(
            "A_D0",
            split,
            len(e0),
            float(e0.sum() + ext * len(e0)),
            "core+extended",
            "primary, Call A, D0 events",
        )
        add(
            "B_D2",
            split,
            len(e2),
            float(e2.sum() + ext * len(e2)),
            "core+explain",
            "primary, Call B, D2 events",
        )
        add(
            "B_D1",
            split,
            len(e0),
            float(e0.sum() + ext * len(e0)),
            "core+explain",
            "primary, Call B at 10:00 (NA-10 bars)",
        )
        add(
            "A_D2",
            split,
            len(e2_new),
            float(e2_new.sum() + ext * len(e2_new)),
            "core+extended",
            f"primary, Call A on W2 news (A3.1); {len(e2) - len(e2_new)} identical to D0 hit the cache",
        )
    vb = p0.loc[p0["split"] == "val_b", "news_tokens_w0"]
    m = cfg.final_selection_models
    add(
        "final_selection",
        "val_b",
        m * len(vb),
        float(m * (vb.sum() + base * len(vb))),
        "core",
        f"top-{m} API survivors, Call A",
    )
    mean2 = float(p2["news_tokens_w2"].mean()) if len(p2) else 0.0
    n_ab = cfg.ablation_events * cfg.ablation_calls_per_event
    add(
        "ablations",
        "val+test",
        n_ab,
        n_ab * (mean2 + base),
        "core",
        "no-news / shuffled Call B, unmasked Call A",
    )
    add("llm_baseline", "val_b+test", 0, 0.0, "fixed", f"generative LLM, fixed ${cfg.llm_baseline_usd:g}")
    mean0 = float(p0["news_tokens_w0"].mean()) if len(p0) else 0.0
    add(
        "market",
        "val+test",
        cfg.market_calls,
        cfg.market_calls * (mean0 + base),
        "core",
        "A3.5 market states (optional)",
    )
    out = pd.DataFrame(rows)
    for price, col in zip(cfg.usd_per_m, _cost_cols(cfg.usd_per_m), strict=True):
        out[col] = out["tokens"] * price / 1e6
        out.loc[out["component"] == "llm_baseline", col] = cfg.llm_baseline_usd
    return out


def plan_totals(comp: pd.DataFrame, cfg: ProjectionConfig, cap: float) -> pd.DataFrame:
    cols = _cost_cols(cfg.usd_per_m)
    flag_col = f"usd_at_{cfg.flag_usd_per_m:g}_per_m"
    rows = []
    for name, parts in PLANS.items():
        sub = comp.loc[comp["component"].isin(parts)]
        row: dict[str, Any] = {
            "plan": name,
            "components": "+".join(parts),
            "calls": int(sub["calls"].sum()),
            "tokens": float(sub["tokens"].sum()),
        }
        row.update({c: float(sub[c].sum()) for c in cols})
        row["na11_cap_usd"] = cap
        row[f"exceeds_cap_at_{cfg.flag_usd_per_m:g}"] = bool(row[flag_col] > cap)
        row["exceeds_cap_at_0.1"] = bool(row.get("usd_at_0.1_per_m", np.nan) > cap)
        rows.append(row)
    return pd.DataFrame(rows)


def run_projection(layout: Layout | None = None) -> dict[str, pd.DataFrame]:
    """Write artifacts/NA-03/call_projection.csv (sections: events, components, plans)."""
    lay = resolve_layout(layout)
    cfg = load_events_config().projection
    cap = load_project().budget.chunk_cap(cfg.chunk)
    d0 = io.read_parquet(
        EVENTS_D0, columns=["company_id", "session", "split", "tier", "news_tokens_w0", "news_w0"], layout=lay
    )
    d2 = io.read_parquet(
        EVENTS_D2, columns=["company_id", "session", "split", "tier", "news_tokens_w2", "news_w2"], layout=lay
    )
    counts = event_counts(d0, d2)
    comp = plan_components(d0, d2, cfg)
    totals = plan_totals(comp, cfg, cap)
    out = pd.concat(
        [counts.assign(section="events"), comp.assign(section="component"), totals.assign(section="plan")],
        ignore_index=True,
    )
    lead = ["section", "plan", "component", "window", "split", "tier"]
    out = out[[c for c in lead if c in out.columns] + [c for c in out.columns if c not in lead]]
    path = lay.artifacts / "NA-03" / "call_projection.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(path, out.to_csv(index=False, lineterminator="\n").encode())
    return {"events": counts, "components": comp, "plans": totals}
