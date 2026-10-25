"""PRD NA-03 S6 / AC6: call and cost projection arithmetic, and the committed projection file."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from newsaction.events import load_events_config
from newsaction.events.projection import identical_lists, plan_components, plan_totals
from newsaction.paths import ROOT

CFG = load_events_config().projection


def _events(window: str, rows: list[tuple[int, date, str, int, list[str]]]) -> pd.DataFrame:
    sfx = window.lower()
    return pd.DataFrame(
        {
            "company_id": [r[0] for r in rows],
            "session": [r[1] for r in rows],
            "split": [r[2] for r in rows],
            "tier": "mid",
            f"news_tokens_{sfx}": [r[3] for r in rows],
            f"news_{sfx}": [[{"id": i} for i in r[4]] for r in rows],
        }
    )


D = date(2025, 8, 5)
D0 = _events("W0", [(1, D, "val_a", 100, ["a"]), (2, D, "val_b", 200, ["b"]), (3, D, "train", 50, ["c"])])
D2 = _events(
    "W2",
    [
        (1, D, "val_a", 100, ["a"]),
        (2, D, "val_b", 300, ["b", "x"]),
        (4, D, "test", 400, ["d"]),
        (3, D, "train", 9, ["c"]),
    ],
)


def test_identical_lists_hit_the_cache() -> None:
    assert identical_lists(D0, D2).tolist() == [True, False, False, True]


def test_component_arithmetic() -> None:
    comp = plan_components(D0, D2, CFG).set_index(["component", "split"])
    ext = 250 + 350 + 600
    assert comp.loc[("A_D0", "val_a"), "calls"] == 1 and comp.loc[("A_D0", "val_a"), "tokens"] == 100 + ext
    assert comp.loc[("B_D2", "val_b"), "tokens"] == 300 + ext
    assert comp.loc[("B_D2", "test"), "calls"] == 1
    assert comp.loc[("A_D2", "val_a"), "calls"] == 0  # identical to the D0 list
    assert comp.loc[("A_D2", "val_b"), "calls"] == 1
    assert comp.loc[("final_selection", "val_b"), "calls"] == 2
    assert comp.loc[("final_selection", "val_b"), "tokens"] == 2 * (200 + 600)
    assert "train" not in comp.index.get_level_values("split")
    price = comp.loc[("A_D0", "val_a"), "usd_at_0.042_per_m"]
    assert price == pytest.approx((100 + ext) * 0.042 / 1e6)
    assert comp.loc[("llm_baseline", "val_b+test"), "usd_at_0.01_per_m"] == CFG.llm_baseline_usd


def test_plan_flags() -> None:
    comp = plan_components(D0, D2, CFG)
    tot = plan_totals(comp, CFG, 18.0).set_index("plan")
    assert not tot["exceeds_cap_at_0.042"].any()
    tiny = plan_totals(comp, CFG, 1e-9).set_index("plan")
    assert tiny["exceeds_cap_at_0.042"].all()


def test_committed_projection() -> None:
    path = ROOT / "artifacts" / "NA-03" / "call_projection.csv"
    if not path.is_file():
        pytest.skip("projection not built")
    df = pd.read_csv(path)
    assert set(df["section"]) == {"events", "component", "plan"}
    plans = df.loc[df["section"] == "plan"]
    assert {"exceeds_cap_at_0.042", "exceeds_cap_at_0.1"} <= set(df.columns)
    assert len(plans) == 4 and plans["na11_cap_usd"].eq(18.0).all()
    ev = df.loc[df["section"] == "events"]
    assert set(ev["window"]) == {"W0", "W2"} and {"val_a", "val_b", "test"} <= set(ev["split"])
