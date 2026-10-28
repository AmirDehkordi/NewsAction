"""NA-11 S9: the production summary (PRD NA-11 S9, AC3, AC5).

- ``artifacts/NA-11/production_summary.csv``: per model, reading (``source``: a0 = Call A D0, a2 = Call A D2,
  b2 = Call B D2, b1 = Call B D1, m = market; ``abl_*`` the S8 ablations; ``llm`` / ``price_only`` the S8
  baselines) and split: the eligible events (the state rows the plan asks for), the answered and valid ones,
  coverage = valid / eligible, the invalid-response rate = (answered − valid) / answered, the latency of the
  answers (p50 / p95, API models) and their cost (cached answers carry the cost of the chunk that paid).
  A trained instrument's reading is valid when its react head gave finite probabilities.
- ``artifacts/NA-11/production_spend.csv``: NA-11's ledger spend per model and purpose.
- AC3: the primary instrument covers ≥ 99 % of its eligible events per call and split.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.config import load_frozen
from newsaction.dm.runner import load_states
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, artifacts_dir
from newsaction.production.plan import load_plan
from newsaction.production.run import PRODUCTION_DIR, slug
from newsaction.train import PREDICTIONS_DIR

SUMMARY: Final = "production_summary.csv"
SPEND: Final = "production_spend.csv"
AC3_MIN: Final = 0.99
TRAINED_FILES: Final = ("val_a", "val_b", "test_callA", "test_callB", "val_callB_d1", "robustness_callA")
SOURCE_OF: Final = {("A", "W0"): "a0", ("A", "W2"): "a2", ("B", "W2"): "b2", ("B", "W0"): "b1"}
STATES_OF: Final = {
    "a0": ("A_D0",),
    "a0_2024h1": ("A_D0",),
    "a2": ("A_D2",),
    "a2_2024h1": ("A_D2",),
    "b2": ("B_D2", "B_D2_test"),
    "b1": ("B_D1", "B_D1_test"),
    "m": ("market",),
}
PURPOSES: Final = (
    ("na11_abl_", "ablations"),
    ("na11_llm", "llm_baseline"),
    ("na11_drift", "canary_drift"),
    ("canary", "canary"),
    ("repeat", "canary"),
    ("p_company", "company_id"),
    ("na11_", "production"),
)


def eligible(layout: Layout | None = None) -> dict[tuple[str, str], int]:
    """(source, split) → the state rows a reading of that source and split is asked for."""
    plan = load_plan()
    out: dict[tuple[str, str], int] = {}
    for src, keys in STATES_OF.items():
        for k in keys:
            if not (resolve_layout(layout).work / plan.states[k]).is_file():
                continue
            rows = load_states(plan.states[k], layout=layout)
            for split, n in rows.groupby("split").size().items():
                out[(src, str(split))] = out.get((src, str(split)), 0) + int(n)
    return out


def _row(model: str, source: str, split: str, df: pd.DataFrame, n_eligible: int) -> dict[str, Any]:
    answered = int(df["ok"].sum()) if "ok" in df else len(df)
    valid = int(df["valid"].sum())
    lat = df["latency_ms"].dropna().astype(float) if "latency_ms" in df else pd.Series(dtype=float)
    cost = df["cost"].astype(float).fillna(0.0).sum() if "cost" in df else 0.0
    return {
        "model": model,
        "source": source,
        "split": split,
        "eligible": n_eligible,
        "rows": len(df),
        "answered": answered,
        "valid": valid,
        "coverage": valid / n_eligible if n_eligible else np.nan,
        "invalid_rate": (answered - valid) / answered if answered else np.nan,
        "latency_p50_ms": float(lat.quantile(0.5)) if len(lat) else np.nan,
        "latency_p95_ms": float(lat.quantile(0.95)) if len(lat) else np.nan,
        "cost_usd": float(cost),
    }


def api_rows(elig: dict[tuple[str, str], int], layout: Layout | None = None) -> list[dict[str, Any]]:
    lay = resolve_layout(layout)
    plan = load_plan()
    models = [plan.api.model, *sorted({c.model for c in plan.comparators_core if c.model})]
    out = []
    for m in models:
        path = f"{PRODUCTION_DIR}/{slug(m)}_api_comparators_market.parquet"
        if not (lay.work / path).is_file():
            continue
        df = io.read_parquet(path, layout=lay)
        for (comp, split), g in df.groupby(["component", "split"]):
            src = "m" if comp == "market" else str(comp)
            out.append(_row(m, src, str(split), g, elig.get((src, str(split)), 0)))
    local = f"{PRODUCTION_DIR}/{slug(plan.laya_zero_shot.model)}_test.parquet"
    if (lay.work / local).is_file():
        df = io.read_parquet(local, layout=lay)
        out.append(_row(plan.laya_zero_shot.model, "a0", "test", df, elig.get(("a0", "test"), 0)))
    return out


def trained_rows(elig: dict[tuple[str, str], int], layout: Layout | None = None) -> list[dict[str, Any]]:
    lay = resolve_layout(layout)
    frozen = load_frozen()
    out = []
    for model in frozen.selection["trained_runs"]:
        parts = []
        for f in TRAINED_FILES:
            rel = f"{PREDICTIONS_DIR}/{model}_{f}.parquet"
            if (lay.work / rel).is_file():
                parts.append(io.read_parquet(rel, layout=lay))
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True)
        df = df.loc[df["question"] == "react"]
        df["valid"] = [
            p is not None and bool(np.all(np.isfinite(np.asarray(p, float)))) for p in df["probabilities"]
        ]
        for (call, window, split), g in df.groupby(["call", "window", "split"]):
            src = SOURCE_OF[(str(call), str(window))]
            out.append(_row(str(model), src, str(split), g, elig.get((src, str(split)), 0)))
    return out


def s8_rows(layout: Layout | None = None) -> list[dict[str, Any]]:
    lay = resolve_layout(layout)
    plan = load_plan()
    out = []
    abl = f"{PRODUCTION_DIR}/{slug(plan.ablations.model)}_ablations.parquet"
    if (lay.work / abl).is_file():
        df = io.read_parquet(abl, layout=lay)
        smp = io.read_parquet(f"{PRODUCTION_DIR}/ablation_sample.parquet", layout=lay)
        for (name, split), g in df.groupby(["ablation", "split"]):
            base = next(c.base for c in plan.ablations.calls if c.name == name)
            n_split = int(((smp["base"] == base) & (smp["split"] == split)).sum())
            out.append(_row(plan.ablations.model, f"abl_{name}", str(split), g, n_split))
    llm = f"{PRODUCTION_DIR}/llm_test.parquet"
    if (lay.work / llm).is_file():
        info = json.loads((artifacts_dir(lay) / "llm_test.json").read_text(encoding="utf-8"))
        out.append(
            {
                "model": plan.llm_baseline.model,
                "source": "llm",
                "split": "test",
                "eligible": plan.llm_baseline.n,
                "rows": info["requests"],
                "answered": info["answered"],
                "valid": info["valid"],
                "coverage": info["valid"] / plan.llm_baseline.n,
                "invalid_rate": (info["answered"] - info["valid"]) / info["answered"]
                if info["answered"]
                else np.nan,
                "latency_p50_ms": np.nan,
                "latency_p95_ms": np.nan,
                "cost_usd": info["spent_usd"],
            }
        )
    po = f"{PRODUCTION_DIR}/price_only_test.parquet"
    if (lay.work / po).is_file():
        df = io.read_parquet(po, layout=lay).assign(valid=lambda d: np.isfinite(d["N_hat"]))
        n0 = len(load_states(plan.states["A_D0"], splits=["test"], layout=lay))
        out.append(_row("price_only", "price_only", "test", df, n0))
    return out


def purpose(tag: str) -> str:
    return next((p for prefix, p in PURPOSES if tag.startswith(prefix)), "other")


def spend(layout: Layout | None = None) -> pd.DataFrame:
    """NA-11's ledger spend per model and purpose (closed spend records)."""
    rows = []
    path = resolve_layout(layout).root / "ledgers" / "spend.jsonl"
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("chunk") == CHUNK and r.get("event") == "spend":
                meta = r.get("meta") or {}
                rows.append(
                    {
                        "model": meta.get("model", "?"),
                        "purpose": purpose(str(meta.get("tag", ""))),
                        "usd": r["usd"],
                    }
                )
    df = pd.DataFrame(rows)
    return df.groupby(["model", "purpose"], as_index=False).agg(requests=("usd", "size"), usd=("usd", "sum"))


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    elig = eligible(lay)
    table = pd.DataFrame(api_rows(elig, lay) + trained_rows(elig, lay) + s8_rows(lay))
    table = table.sort_values(["model", "source", "split"], kind="mergesort").reset_index(drop=True)
    table.to_csv(artifacts_dir(lay) / SUMMARY, index=False)
    sp = spend(lay)
    sp.to_csv(artifacts_dir(lay) / SPEND, index=False)
    primary = str(load_frozen().selection["primary_instrument"])
    prim = table.loc[(table["model"] == primary) & (table["eligible"] > 0)]
    low = prim.loc[prim["coverage"] < AC3_MIN, ["source", "split", "coverage"]]
    return {
        "rows": len(table),
        "primary": primary,
        "ac3_min_coverage": float(prim["coverage"].min()) if len(prim) else None,
        "ac3_pass": bool(len(prim)) and low.empty,
        "below_99": low.to_dict("records"),
        "spend_usd": float(sp["usd"].sum()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    print(json.dumps(run(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
