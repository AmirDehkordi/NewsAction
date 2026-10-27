"""Probe c's counterfactual edits (``tournament.edits``; PRD NA-06 S4c).

Each rule flips the outcome, nothing else changes, and states the rules cannot flip coherently are
refused."""

from __future__ import annotations

import copy
import json
from typing import Any

import pandas as pd
import pytest

from newsaction import io
from newsaction.paths import ROOT
from newsaction.tournament.edits import edit_state, match_case, select


def state(*items: tuple[str, str]) -> dict[str, Any]:
    return {
        "company": {"sector": "Energy"},
        "market": {"vix_change": "small rise"},
        "news": [
            {"headline": h, "snippet": s, "source_type": "press wire", "timing": "overnight"}
            for h, s in items
        ],
    }


def edited(*items: tuple[str, str]) -> list[tuple[str, str]]:
    res = edit_state(state(*items))
    assert res.ok, res.reason
    assert res.state is not None
    return [(n["headline"], n["snippet"]) for n in res.state["news"]]


def test_beat_and_miss_flip_with_case_kept() -> None:
    assert edited(("The company Beats Quarterly Profit Estimates", "")) == [
        ("The company Misses Quarterly Profit Estimates", "")
    ]
    assert edited(("", "the company missed analysts' estimates for revenue."))[0][1] == (
        "the company beat analysts' estimates for revenue."
    )
    assert edited(("The company quarter Earnings Miss on Rising Costs", ""))[0][0] == (
        "The company quarter Earnings Beat on Rising Costs"
    )
    assert (
        edited(("The company's earnings beat estimates", ""))[0][0] == "The company's earnings miss estimates"
    )


def test_guidance_rating_and_expectations_flip() -> None:
    assert edited(("The company raises full-year revenue guidance", ""))[0][0] == (
        "The company lowers full-year revenue guidance"
    )
    assert (
        edited(("The company EPS Forecast Raised by Analyst", ""))[0][0]
        == "The company EPS Forecast Lowered by Analyst"
    )
    assert edited(("", "The company reported profit below expectations."))[0][1] == (
        "The company reported profit above expectations."
    )
    out = edited(("Goldman Sachs Downgrades the company to Neutral From Buy", ""))
    assert out[0][0] == "Goldman Sachs Upgrades the company to Buy From Neutral"


def test_rating_ladder_swaps_with_articles() -> None:
    out = edited(
        ("", 'The company was upgraded by analysts at X from an "underperform" rating to a "hold" rating.')
    )
    assert (
        out[0][1]
        == 'The company was downgraded by analysts at X from a "hold" rating to an "underperform" rating.'
    )


def test_price_target_companion_flips_with_the_outcome() -> None:
    out = edited(
        ("The company Beats Estimates By $0.06 EPS", ""),
        ("Morgan Stanley Adjusts Price Target on the company raised by about 2%, Maintains Overweight", ""),
    )
    assert out[0][0] == "The company Misses Estimates By $0.06 EPS"
    assert out[1][0].endswith("lowered by about 2%, Maintains Overweight")


def test_nothing_else_changes() -> None:
    original = state(
        ("The company Beats Estimates", "The company beat Wall Street estimates for quarterly profit.")
    )
    before = copy.deepcopy(original)
    res = edit_state(original)
    assert original == before  # the input is not mutated
    assert res.ok and res.state is not None
    assert {k: v for k, v in res.state.items() if k != "news"} == {
        k: v for k, v in original.items() if k != "news"
    }
    for a, b in zip(original["news"], res.state["news"], strict=True):
        assert {k: v for k, v in a.items() if k in {"source_type", "timing"}} == {
            k: v for k, v in b.items() if k in {"source_type", "timing"}
        }
        for f in ("headline", "snippet"):
            assert len(a[f].split()) == len(b[f].split())  # word-for-word replacements only
    assert res.polarity == +1


@pytest.mark.parametrize(
    ("items", "reason"),
    [
        ((("Will the company Beat Estimates Again in Its Next Earnings Report?", ""),), "forward_looking"),
        ((("T-Mobile dials up a big earnings beat as it bests the company", ""),), "other_subject"),
        ((("Verizon raised earnings guidance", ""), ("The company news", "")), "other_subject"),
        ((("The company Upgraded to Hold at Jefferies", ""),), "bare_rating"),
        ((("The company Beats Estimates", "Revenue topped estimates."),), "uncovered_cue"),
        ((("The company EPS $1.20 beats the $1.10 estimate", ""),), "numbers"),
        ((("The company beats revenue estimates", "The company missed profit estimates."),), "mixed"),
        ((("The company opens a new plant", ""),), "no_phrase"),
        ((("The company Shares Rise As Earnings Beat Estimates", ""),), "uncovered_cue"),
        ((("The company's beat and raise quarter", "The company beat estimates."),), "uncovered_cue"),
        ((("DoubleVerify was upgraded by equities research analysts at the company", ""),), "other_subject"),
    ],
)
def test_refusals(items: tuple[tuple[str, str], ...], reason: str) -> None:
    res = edit_state(state(*items))
    assert not res.ok and res.reason == reason and res.state is None


def test_non_outcome_words_are_not_edited() -> None:
    res = edit_state(
        state(
            ("The company: don't miss this", "Apple Beats headphones sale"),
            ("The company beats estimates", ""),
        )
    )
    assert res.ok and res.state is not None
    assert (
        res.state["news"][0]
        == state(("The company: don't miss this", "Apple Beats headphones sale"))["news"][0]
    )


def test_match_case() -> None:
    assert [match_case(s, "missed") for s in ("BEAT", "Beat", "beat")] == ["MISSED", "Missed", "missed"]


def test_select_prefers_listed_events_and_is_deterministic() -> None:
    rows = pd.DataFrame(
        {
            "event_id": [f"W0:{i}:2025-08-01" for i in range(6)],
            "state_json": [json.dumps(state((f"The company beats estimates {i}", ""))) for i in range(6)],
        }
    )
    a, reasons = select(rows, 3, 2026, preferred=["W0:5:2025-08-01"])
    b, _ = select(rows, 3, 2026, preferred=["W0:5:2025-08-01"])
    assert a["event_id"].tolist() == b["event_id"].tolist()
    assert a["event_id"].iloc[0] == "W0:5:2025-08-01" and reasons == {"editable": 6}
    with pytest.raises(ValueError, match="only 6 editable"):
        select(rows, 7, 2026, preferred=[])


def test_selected_pairs_on_disk_flip_and_differ_only_in_news_text() -> None:
    """The 200 written pairs: the edited state is the original with only the listed words replaced."""
    rel = "dm/tournament/counterfactual.parquet"
    if not (ROOT / "work" / rel).is_file():
        pytest.skip("the samples stage has not run")
    cf = io.read_parquet(rel)
    states = io.read_parquet("states/callA_d0_E3.parquet", columns=["event_id", "state_json"]).set_index(
        "event_id"
    )
    assert len(cf) == 200 and cf["polarity"].isin([-1, 1]).all()
    for rec in cf.to_dict("records"):
        orig = json.loads(states.loc[rec["event_id"], "state_json"])
        new = json.loads(rec["edited_state_json"])
        assert {k: v for k, v in orig.items() if k != "news"} == {k: v for k, v in new.items() if k != "news"}
        redo = edit_state(orig)
        assert redo.ok and redo.state == new
        assert sum(o != n for o, n in zip(orig["news"], new["news"], strict=True)) >= 1


def test_guidance_cut_is_the_prereg_counterpart() -> None:
    """PREREG §8.3 names raise↔cut; the PRD raised↔lowered: both negative forms flip to "raise"."""
    assert (
        edited(("The company cuts full-year revenue guidance", ""))[0][0]
        == "The company raises full-year revenue guidance"
    )
    assert (
        edited(("The company Guidance Cut on weak demand", ""))[0][0]
        == "The company Guidance Raised on weak demand"
    )
    out = edited(("The company cut 500 jobs and lowered its outlook", ""))
    assert out[0][0] == "The company cut 500 jobs and raised its outlook"
