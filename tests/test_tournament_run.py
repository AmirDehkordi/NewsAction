"""``tournament.run`` guards: the stage-2 choice (PREREG §8.3: <= 6 survivors, highest stage-1 IC, ties to the
cheaper), the ``tournament`` section of configs/frozen.yaml, and the hand-off that opens val-B only after the
report (CLAUDE.md C13)."""

from __future__ import annotations

import pandas as pd
import pytest
import yaml

from newsaction.config import load_frozen
from newsaction.paths import Layout
from newsaction.tournament import TournamentError
from newsaction.tournament.run import Ctx, choose_stage2, stage_handoff, write_frozen_tournament


def test_choose_stage2_by_ic_then_cost() -> None:
    t = pd.DataFrame(
        {
            "model": ["a", "b", "c", "d", "e"],
            "ic1_z_cc": [0.05, 0.09, 0.07, 0.07, 0.10],
            "cost_per_1000_a": [0.01, 0.05, 0.08, 0.02, 0.03],
        }
    )
    assert choose_stage2(t, ["a", "b", "c", "d"], 3) == ["b", "d", "c"]  # "e" is not a survivor; c/d tie
    assert choose_stage2(t, ["a", "b", "c", "d", "e"], 6) == ["e", "b", "d", "c", "a"]


def entry() -> dict[str, object]:
    return {
        "stage1_survivors": ["x/m1", "x/m2"],
        "stage2_models": ["x/m1"],
        "stage2_survivors_passing": [],
        "leaderboard_file": "artifacts/NA-06/leaderboard.csv",
        "leaderboard_sha": "0" * 63 + "1",
        "mcs_statistic": "R",
    }


def test_frozen_tournament_section_round_trips(tmp_layout: Layout) -> None:
    ctx = Ctx.load(tmp_layout)
    path = tmp_layout.configs / "frozen.yaml"
    before = yaml.safe_load(path.read_text(encoding="utf-8"))
    write_frozen_tournament(ctx, entry())
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["tournament"] == entry()
    assert {k: v for k, v in after.items() if k != "tournament"} == {
        k: v for k, v in before.items() if k != "tournament"
    }
    # a second write replaces the section rather than adding one
    write_frozen_tournament(ctx, {**entry(), "stage2_survivors_passing": ["x/m1"]})
    assert load_frozen(path).tournament["stage2_survivors_passing"] == ["x/m1"]


def test_handoff_needs_the_tournament(tmp_layout: Layout) -> None:
    ctx = Ctx.load(tmp_layout)
    path = tmp_layout.configs / "frozen.yaml"
    text = path.read_text(encoding="utf-8")
    if load_frozen(path).tournament:  # a copy of a repository after the report: reset to the NA-05 state
        lines = text.splitlines(keepends=True)
        start = next(i for i, ln in enumerate(lines) if ln.startswith("tournament:"))
        end = start + 1
        while end < len(lines) and lines[end].startswith(" "):
            end += 1
        text = "".join([*lines[:start], "tournament: null\n", *lines[end:]])
        text = text.replace("allow_val_b: true", "allow_val_b: false")
        path.write_text(text, encoding="utf-8")
    assert load_frozen(path).allow_val_b is False
    with pytest.raises(TournamentError, match="no tournament section"):
        stage_handoff(ctx)
    assert load_frozen(path).allow_val_b is False
    write_frozen_tournament(ctx, entry())
    assert stage_handoff(ctx) == 0
    assert load_frozen(path).allow_val_b is True


def test_log_trial_appends_once(tmp_layout: Layout) -> None:
    from newsaction.ledger import TrialLedger
    from newsaction.tournament import log_trial

    args = ("dm_tournament_stage1", "x/m1", {"model": "x/m1"}, "val_a", "ic1_z_cc", 0.05)
    assert log_trial(*args, layout=tmp_layout) is True
    assert log_trial(*args, layout=tmp_layout) is False
    assert log_trial(*args[:5], float("nan"), layout=tmp_layout) is True  # a missing value is logged as null
    recs = TrialLedger(tmp_layout.ledgers / "trials.jsonl").records()
    assert [r["value"] for r in recs] == [0.05, None] and {r["chunk"] for r in recs} == {"NA-06"}
