"""PRD NA-03 AC2–AC3: the PREREG §6.8 rule is mechanical, and the choice keeps underreaction."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from newsaction.config import load_frozen
from newsaction.events import load_events_config
from newsaction.events.filters import apply_threshold, budget_select
from newsaction.events.select import CompareError, apply_rule, rule_trace, write_frozen_filter, yaml_float
from newsaction.paths import ROOT

ORDER = ("F1", "F2", "F3", "F4", "F5", "F6")
CSV = ROOT / "artifacts" / "NA-03" / "filter_comparison.csv"


def _table(recall: list[float], delayed: list[float], share: float = 0.3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "filter": ORDER,
            "role": "candidate",
            "selected_share": share,
            "recall_material": recall,
            "recall_delayed": delayed,
        }
    )


def test_constraint_binds() -> None:
    """F6 has the best recall but a lower delayed recall than F1: the rule must pass over it.

    Dropping the delayed-recall constraint from apply_rule makes this test fail (mutation, AC2).
    """
    df = _table([0.40, 0.30, 0.35, 0.38, 0.45, 0.50], [0.30, 0.20, 0.25, 0.29, 0.31, 0.29])
    assert apply_rule(df) == "F5"
    assert apply_rule(df, constrained=False) == "F6"
    t = rule_trace(df)
    assert t["constraint_binding"] is True and t["excluded_by_constraint"] == ["F2", "F3", "F4", "F6"]


def test_ties_go_to_fewer_inputs() -> None:
    df = _table([0.40, 0.30, 0.30, 0.30, 0.4099, 0.405], [0.3, 0.3, 0.3, 0.3, 0.3, 0.3])
    assert apply_rule(df) == "F1"  # F5 is < 1 pp better: a tie
    df = _table([0.40, 0.30, 0.30, 0.30, 0.4101, 0.405], [0.3, 0.3, 0.3, 0.3, 0.3, 0.3])
    assert apply_rule(df) == "F5"  # more than 1 pp better than F1, and F6 within 1 pp of F5 is later


def test_f1_always_meets_its_own_constraint() -> None:
    df = _table([0.40, 0.10, 0.10, 0.10, 0.10, 0.10], [0.05, 0.9, 0.9, 0.9, 0.9, 0.9])
    assert apply_rule(df) == "F1"


def test_budget_violation_and_missing_candidate_raise() -> None:
    df = _table([0.4] * 6, [0.3] * 6)
    df.loc[4, "selected_share"] = 0.31
    with pytest.raises(CompareError):
        apply_rule(df)
    with pytest.raises(CompareError):
        apply_rule(_table([0.4] * 6, [0.3] * 6).iloc[:5])


def test_budget_select_and_frozen_threshold_agree() -> None:
    rng = np.random.default_rng(7)
    n = 5000
    u = rng.random(n)
    for score in (rng.random(n), np.round(rng.random(n), 1), np.ones(n)):
        ok = rng.random(n) < 0.8
        k = 1500
        sel = budget_select(score, ok, u, k)
        assert sel.mask.sum() == min(k, ok.sum()) and not (sel.mask & ~ok).any()
        again = apply_threshold(score, ok, u, sel.threshold, sel.tie_u_max)
        assert np.array_equal(again, sel.mask)
    # a rule filter below the budget keeps its whole eligible set
    ok = rng.random(n) < 0.2
    sel = budget_select(np.ones(n), ok, u, 1500)
    assert np.array_equal(sel.mask, ok) and sel.tie_u_max == 1.0


def test_yaml_float_round_trip() -> None:
    for x in (0.1, 1e-05, 0.30000000000000004, 1.0, 123456.789, 2.5e-12):
        assert yaml.safe_load(yaml_float(x)) == x


def test_write_frozen_filter_touches_only_the_filter_block(tmp_path: Path) -> None:
    p = tmp_path / "frozen.yaml"
    shutil.copy(ROOT / "configs" / "frozen.yaml", p)
    before = yaml.safe_load(p.read_text())
    entry = {
        "id": "F5",
        "threshold": 0.123456789,
        "tie_u_max": 1.0,
        "rule_version": "x",
        "comparison_sha": "ab" * 32,
    }
    write_frozen_filter(entry, p)
    after = yaml.safe_load(p.read_text())
    assert after["filter"] == entry
    assert {k: v for k, v in after.items() if k != "filter"} == {
        k: v for k, v in before.items() if k != "filter"
    }
    write_frozen_filter({**entry, "id": "F6"}, p)  # a rerun replaces the block
    assert yaml.safe_load(p.read_text())["filter"]["id"] == "F6"


# --- the real comparison (committed artifact) --------------------------------------------------------


@pytest.fixture(scope="module")
def comparison() -> pd.DataFrame:
    if not CSV.is_file():
        pytest.skip("filter_comparison.csv not built")
    return pd.read_csv(CSV)


def test_frozen_choice_recomputed_from_csv(comparison: pd.DataFrame) -> None:
    ff = load_frozen().filter
    assert apply_rule(comparison) == ff["id"]
    assert hashlib.sha256(CSV.read_bytes()).hexdigest() == ff["comparison_sha"]
    chosen = comparison.loc[(comparison["filter"] == ff["id"]) & (comparison["role"] == "candidate")].iloc[0]
    assert float(chosen["threshold"]) == ff["threshold"]
    assert float(chosen["tie_u_max"]) == ff["tie_u_max"]
    assert ff["budget_share"] == load_events_config().compare.budget_share
    assert ff["rule_version"] == load_events_config().compare.rule_version
    assert bool(chosen["chosen"]) and int(comparison["chosen"].sum()) == 1
    assert ff["constraint_binding"] == rule_trace(comparison)["constraint_binding"]


def test_underreaction_kept(comparison: pd.DataFrame) -> None:
    """AC3: delayed recall reported for every candidate; the choice's is ≥ F1's."""
    cand = comparison.loc[comparison["role"] == "candidate"].set_index("filter")
    assert set(cand.index) == set(ORDER)
    assert cand["recall_delayed"].notna().all()
    chosen = load_frozen().filter["id"]
    assert cand.loc[chosen, "recall_delayed"] >= cand.loc["F1", "recall_delayed"]
    assert (cand["selected_share"] <= 0.30 + 1e-12).all()
