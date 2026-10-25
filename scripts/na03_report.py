"""NA-03 report tables: selection by split and the rule-filter ranking sensitivity.

``uv run python scripts/na03_report.py`` writes, under artifacts/NA-03/:
- ``selection_by_split.csv``: per window and split, the covered member-days, those with ≥ 1 kept article,
  the ticker-days the frozen filter selects, events and the selected days dropped for lack of a
  third-party-OK article. Articles and counts only: no return is read.
- ``sensitivity_rule_ranking.csv``: F1 and F3 at the 30% budget ranked by their count of qualifying
  articles instead of random thinning (PREREG §15 NA-03 row 1). Val-A only; both evaluations are logged
  in ledgers/trials.jsonl (idempotently), together with the rule's choice under this variant.
- ``summary.json``: the headline numbers quoted in REPORT.md.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

from newsaction import io
from newsaction.config import load_frozen
from newsaction.events import EVENTS_D0, EVENTS_D2, LABELS, TICKER_DAYS, load_events_config, select
from newsaction.events.aggregate import select_ticker_days
from newsaction.events.attention import member_company_sessions
from newsaction.events.filters import budget_select, eligible
from newsaction.events.learned import load_meta
from newsaction.events.scores import split_name
from newsaction.events.trials import log_trial
from newsaction.news import COVERAGE
from newsaction.paths import ARTIFACTS

OUT = ARTIFACTS / "NA-03"


def selection_by_split() -> pd.DataFrame:
    ff = dict(load_frozen().filter)
    m = member_company_sessions()
    cov = io.read_parquet(COVERAGE)
    m["month"] = pd.to_datetime(m["session"]).dt.strftime("%Y-%m")
    m = m.merge(cov[["month", "company_id", "covered"]], on=["month", "company_id"], how="left")
    m = m.loc[m["covered"].fillna(False).astype(bool)]
    m["split"] = split_name(m["session"])
    td = io.read_parquet(TICKER_DAYS)
    parts = []
    for window, rel in (("W0", EVENTS_D0), ("W2", EVENTS_D2)):
        t = td.loc[td["window"] == window]
        with_kept = t.merge(m[["session", "company_id"]], on=["session", "company_id"])
        sel = select_ticker_days(t, ff)
        sel["split"] = split_name(sel["session"])
        ev = io.read_parquet(rel, columns=["split"])
        g = pd.DataFrame(
            {
                "covered_days": m.groupby("split").size(),
                "with_kept_article": with_kept.groupby("split").size(),
                "selected": sel.groupby("split").size(),
                "events": ev.groupby("split").size(),
            }
        ).fillna(0)
        g = g.astype("int64")
        g["selected_share"] = g["selected"] / g["covered_days"]
        g["dropped_no_third_party"] = (g["selected"] - g["events"]).where(g.index != "warmup", 0)
        g.insert(0, "window", window)
        parts.append(g.rename_axis("split").reset_index())
    return pd.concat(parts, ignore_index=True)


def sensitivity() -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = load_events_config()
    td = io.read_parquet(TICKER_DAYS)
    sample = select.comparison_sample(io.read_parquet(LABELS), td.loc[td["split"] == select.VAL_A])
    k = math.floor(cfg.compare.budget_share * len(sample))
    comp = pd.read_csv(OUT / "filter_comparison.csv")
    rows = []
    for fid, count in (("F1", "n_f1"), ("F3", "n_f3")):
        score = sample[count].fillna(0).to_numpy(dtype="float64")
        sel = budget_select(score, eligible(sample, fid), sample["tie_u"].to_numpy(dtype="float64"), k)
        m = select.evaluate(sel.mask, sample)
        rows.append({"filter": fid, "variant": "count-ranked", "threshold_count": sel.threshold, **m})
        params = {"filter": fid, "rank": count, "budget": cfg.compare.budget_share}
        log_trial(
            "filter_sensitivity",
            f"{fid} count-ranked",
            params,
            "val_a",
            "recall_material",
            m["recall_material"],
        )
    alt = comp.copy()
    for r in rows:
        i = alt.index[(alt["filter"] == r["filter"]) & (alt["role"] == "candidate")][0]
        for c in ("selected_share", "recall_material", "recall_delayed"):
            alt.loc[i, c] = r[c]
    return pd.DataFrame(rows), select.rule_trace(alt)


def main() -> None:
    by_split = selection_by_split()
    sens, trace = sensitivity()
    OUT.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(
        OUT / "selection_by_split.csv", by_split.to_csv(index=False, lineterminator="\n").encode()
    )
    io.atomic_write_bytes(
        OUT / "sensitivity_rule_ranking.csv", sens.to_csv(index=False, lineterminator="\n").encode()
    )
    comp = pd.read_csv(OUT / "filter_comparison.csv")
    labels = io.read_parquet(LABELS, columns=["split", "label_ok", "material", "delayed"])
    pub = labels.loc[labels["label_ok"] & labels["split"].isin(["train", select.VAL_A])]
    base = pub.groupby("split")[["material", "delayed"]].mean().astype(float).round(4).to_dict("index")
    summary = {
        "label_base_rates_label_ok": base,
        "comparison_n_eval": int(comp["n_eval"].iloc[0]),
        "rule_trace": select.rule_trace(comp),
        "frozen_filter": dict(load_frozen().filter),
        "sensitivity_rule_trace": trace,
        "f5_meta": {k: load_meta("F5")[k] for k in ("fit_range", "tune_range", "params", "grid")},
        "f6_meta": {k: load_meta("F6")[k] for k in ("fit_range", "tune_range", "params", "grid")},
    }
    io.atomic_write_bytes(OUT / "summary.json", (json.dumps(summary, indent=1, default=str) + "\n").encode())
    print(by_split.round(4).to_string())
    print(sens.round(4).to_string())
    print(json.dumps(trace))


if __name__ == "__main__":
    main()
