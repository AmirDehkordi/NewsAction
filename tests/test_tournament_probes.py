"""Probe designs and scores (``tournament.probes``; PRD NA-06 S4): company candidates of the same sector and
size tier, month options, the shuffled-news derangement, accuracy, the flip rate, reading-validity tables,
and the probe requests built by ``run`` (neutral keys, probe tags, the masked state)."""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction.paths import ROOT
from newsaction.tournament import load_tournament_config
from newsaction.tournament.probes import (
    accuracy,
    company_design,
    company_names,
    derangement,
    distractors,
    flip_rate,
    month_design,
    month_label,
    months_between,
    shuffled_state,
    validity_tables,
)

CFG = load_tournament_config()


def members() -> pd.DataFrame:
    rows = []
    for i in range(30):
        rows.append(
            {
                "company_id": i,
                "sector": "Energy" if i < 20 else "Utilities",
                "tier": "top100" if i < 4 else "mid" if i < 12 else "rest",
                "rank": float(i * 10),
            }
        )
    return pd.DataFrame(rows)


def test_distractors_share_sector_and_tier() -> None:
    ev = {"event_id": "W0:7:2025-08-01", "company_id": 7}
    ids, how = distractors(ev, members(), 3, np.random.default_rng(0))
    m = members().set_index("company_id")
    assert how == "sector_tier" and len(set(ids)) == 3 and 7 not in ids
    assert all(m.loc[c, "sector"] == "Energy" and m.loc[c, "tier"] == "mid" for c in ids)


def test_distractors_fill_by_nearest_rank() -> None:
    ev = {"event_id": "W0:2:2025-08-01", "company_id": 2}
    mem = members().loc[lambda d: d["company_id"] != 1]  # top100 Energy: 0, 2, 3
    ids, how = distractors(ev, mem, 3, np.random.default_rng(0))
    assert how == "sector_rank_fill"
    assert sorted(ids)[:2] == [0, 3] and ids[-1] == 4  # same tier first, then the nearest rank (40)


def test_company_design_keys_and_truth() -> None:
    ev = {"event_id": "W0:7:2025-08-01", "company_id": 7}
    names = {i: f"Company {i}" for i in range(30)}
    d = company_design(ev, members(), names, CFG)
    keys = [k for k, _, _ in d["company_options"]]
    assert keys == list(CFG.probes.option_keys)
    truth = {k: c for k, c, _ in d["company_options"]}[d["company_true_key"]]
    assert truth == 7
    assert company_design(ev, members(), names, CFG) == d  # seeded per event


def test_month_design() -> None:
    assert len(months_between(CFG.probes.month.first, CFG.probes.month.last)) == 18
    assert month_label("2025-07") == "July 2025"
    d = month_design({"event_id": "W0:1:2025-08-04", "month": "2025-08"}, CFG)
    months = [m for _, m, _ in d["month_options"]]
    assert len(set(months)) == 4 and "2025-08" in months
    assert {k: m for k, m, _ in d["month_options"]}[d["month_true_key"]] == "2025-08"
    assert all("2024-07" <= m <= "2025-12" for m in months)


def test_derangement() -> None:
    ids = [f"e{i}" for i in range(50)]
    comp = [i % 10 for i in range(50)]
    d = derangement(ids, comp, 7)
    assert sorted(d.values()) == sorted(ids)
    pos = {e: i for i, e in enumerate(ids)}
    assert all(comp[pos[r]] != comp[pos[dn]] for r, dn in d.items())
    assert derangement(ids, comp, 7) == d


def test_shuffled_state_replaces_only_news() -> None:
    a = {
        "company": {"sector": "Energy"},
        "market": {"x": 1},
        "attention": {"y": 2},
        "news": [{"headline": "A"}],
    }
    b = {"company": {"sector": "Utilities"}, "news": [{"headline": "B"}]}
    s = shuffled_state(a, b)
    assert s["news"] == b["news"] and {k: v for k, v in s.items() if k != "news"} == {
        k: v for k, v in a.items() if k != "news"
    }
    assert a["news"] == [{"headline": "A"}]


def test_accuracy_and_flip_rate() -> None:
    acc, ptrue, n = accuracy([{"a": 0.7, "b": 0.3}, {"a": 0.2, "b": 0.8}, {}], ["a", "a", "a"])
    assert (acc, n) == (0.5, 2) and ptrue == pytest.approx(0.45)
    rate, pairs = flip_rate([1.0, -0.5, 0.1, 2.0, math.nan], [-0.2, 0.3, -1.0, 1.5, 1.0], 0.25)
    assert pairs == 3 and rate == pytest.approx(2 / 3)  # 0.1 is below 0.25; the NaN pair drops


def test_validity_tables() -> None:
    f = pd.DataFrame(
        {
            "label_event_type": ["earnings_results", "analyst_action", "other"],
            "label_quantified": ["numbers", "narrative", "numbers"],
            "label_scheduled": ["scheduled", "unscheduled", "unscheduled"],
            "label_credibility": ["confirmed", "rumor", "credible_report"],
            "tag_type": ["earnings_results", "analyst_action", "macro_sector"],
            "tag_quantified": [True, False, False],
            "tag_rumor": [False, True, False],
            "earnings_w0": [True, False, True],
        }
    )
    tables, summary = validity_tables(f, CFG.reading_validity.event_type_map)
    agree = summary.set_index("comparison")["agreement"]
    assert agree["event_type"] == pytest.approx(2 / 3)
    assert agree["quantified"] == pytest.approx(2 / 3)
    assert agree["scheduled"] == pytest.approx(2 / 3)
    assert agree["credibility"] == pytest.approx(1.0)
    assert set(tables["comparison"]) >= {"event_type", "quantified", "scheduled", "credibility"}


def test_company_names_drop_class_suffix() -> None:
    c = pd.DataFrame(
        {
            "company_id": [649, 649, 6],
            "symbol_id": [2, 1, 3],
            "name": ["Alphabet Inc. (Class C)", "Alphabet Inc. (Class A)", "Apple Inc."],
        }
    )
    assert company_names(c) == {649: "Alphabet Inc.", 6: "Apple Inc."}


def test_built_probe_requests() -> None:
    """The requests ``run`` sends for probes a, b, d, e (when the samples exist): masked state, one choice
    over the neutral keys, the probe tag in the provenance; the unmasked twin under ``unmasked_twin``."""
    if not (ROOT / "work" / "dm" / "tournament" / "samples.parquet").is_file():
        pytest.skip("the samples stage has not run")
    from newsaction.tournament.run import Ctx, choice_probe_specs, shuffled_specs, unmasked_specs

    ctx = Ctx.load()
    a = choice_probe_specs(ctx, "local/laya-typed-decisions", "company")
    assert len(a) == 400 and {s.info.probe for s in a} == {CFG.probes.tags.company}
    q = a[0].request.questions[CFG.probes.company.qid]
    assert q.instructions == CFG.probes.company.instructions and q.options() == list(CFG.probes.option_keys)
    assert all(s.info.masked and s.info.split == "val_a" and s.info.session > date(2025, 7, 8) for s in a)
    states = ctx.states_a().set_index("event_id")
    assert all(json.loads(states.loc[s.info.event_id, "state_json"]) == s.request.state for s in a[:20])
    u = unmasked_specs(ctx, "local/laya-typed-decisions")
    assert len(u) == 1000 and all(not s.info.masked and s.info.probe == "unmasked_twin" for s in u)
    sh = shuffled_specs(ctx, "local/laya-typed-decisions")
    assert len(sh) == 1000 and all(s.info.probe == CFG.probes.tags.shuffled for s in sh)
