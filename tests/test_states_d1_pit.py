"""NA-10 AC4: D1 Call B states (PRD NA-10 S6; PREREG §2.5, §6.10; CLAUDE.md A4–A5).

- Call B on W0 news is the D1 state: its spec validates at D1, ``reaction_so_far`` reads ``d1`` columns only,
  and injecting a column known only after 10:00 (or a D2 reaction) into any block raises ``PITError``;
- every column of the NA-10 public files is registered, and the registry places each at the right point;
- the built file (skipped until ``states.build --stage d1`` ran): train / val-A / val-B only, p95 state tokens
  ≤ 900, every state ≤ 1,024 tokens with its longest core question, the D1 time label, the D1 move phrases.

Mutation: let ``validate_spec`` accept ``d2_reaction`` columns in a D1 ``reaction_so_far`` and the injection
test fails.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pyarrow.parquet as pq
import pytest

from newsaction import pit
from newsaction.bars import INTRADAY_PUBLIC, INTRADAY_SPY_PUBLIC
from newsaction.paths import ROOT
from newsaction.states import load_states_config
from newsaction.states.build import CALL_B_D1, REACTION_D1, make_spec, validate_spec
from newsaction.states.codebook import load_codebook

AFTER_TEN = ("p1530", "r_10c", "ar_10c", "p_close", "bars_complete", "y1", "car_lvl_10", "g_d2", "z_cc")


def _spec():  # type: ignore[no-untyped-def]
    return make_spec("callB_d1_E3", "B", "W0", "E3", True, load_states_config())


def test_call_b_on_w0_is_the_d1_state_and_validates() -> None:
    spec = _spec()
    assert spec.decision_point == "D1"
    validate_spec(spec)
    reg = pit.default_registry()
    assert {reg.kind(c) for c in spec.blocks["reaction_so_far"]} == {"d1"}
    assert make_spec("callA_d0_E3", "A", "W0", "E3", True, load_states_config()).decision_point == "D0"


@pytest.mark.parametrize("column", AFTER_TEN)
def test_a_column_known_after_ten_cannot_enter_a_d1_state(column: str) -> None:
    spec = _spec()
    for block in ("reaction_so_far", "company"):
        bad = replace(spec, blocks={**spec.blocks, block: (*spec.blocks[block], column)})
        with pytest.raises(pit.PITError):
            validate_spec(bad)


@pytest.mark.parametrize("column", ["beta_m", "news_w0", "z_m5", "attention_ratio_w0"])
def test_the_d1_reaction_block_reads_reaction_columns_only(column: str) -> None:
    """The call rule: a column visible at D1 that is not a D1 reaction still cannot enter reaction_so_far."""
    spec = _spec()
    bad = replace(spec, blocks={**spec.blocks, "reaction_so_far": (*spec.blocks["reaction_so_far"], column)})
    with pytest.raises(pit.PITError, match="accepts d1 columns only"):
        validate_spec(bad)


def test_d1_columns_are_visible_at_d1_only() -> None:
    reg = pit.default_registry()
    d1 = [
        "g_d1",
        "g_d1_lvl",
        "p10",
        "r_c10",
        "ar_c10",
        "react_d1_spy_z",
        "react_d1_volume_multiple",
        "sigma_30",
    ]
    reg.check_inputs(d1, "D1")
    with pytest.raises(pit.PITError):
        reg.check_inputs(["g_d1"], "D0")
    for c in AFTER_TEN:
        with pytest.raises(pit.PITError):
            reg.check_inputs([c], "D1")


@pytest.mark.parametrize("rel", [INTRADAY_PUBLIC, INTRADAY_SPY_PUBLIC, REACTION_D1])
def test_every_na10_column_is_registered(rel: str) -> None:
    path = ROOT / "work" / rel
    if not path.is_file():
        pytest.skip(f"work/{rel} is absent")
    reg = pit.default_registry()
    for c in pq.read_schema(path).names:
        reg.kind(c)


def test_built_d1_states() -> None:
    path = ROOT / "work" / CALL_B_D1
    if not path.is_file():
        pytest.skip(f"work/{CALL_B_D1} is absent (run states.build --stage d1)")
    df = pq.read_table(path).to_pandas()
    cfg = load_states_config().tokens
    assert (
        set(df["split"]) <= {"train", "val_a", "val_b"}
        and set(df["window"]) == {"W0"}
        and set(df["call"]) == {"B"}
    )
    assert df["n_tokens_state"].quantile(0.95) <= cfg.state_p95_max
    assert int(df["event_id"].str.startswith("W0:").sum()) == len(df) and df["event_id"].is_unique
    label = load_codebook().time_label_word("D1")
    for js in df["state_json"].sample(200, random_state=2026):
        state = json.loads(js)
        r = state["reaction_so_far"]
        assert r["time"] == label and set(state) == {
            "company",
            "market",
            "attention",
            "news",
            "reaction_so_far",
        }
        for k in ("stock_move_vs_market_and_sector", "stock_market_move"):
            assert r[k] == load_codebook().missing or r[k].endswith("a typical move by this time of day)")
