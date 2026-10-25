"""PRD NA-04 S6 / AC5: token counts (ModernBERT-large tokenizer) and the Laya budget.

- Stored ``n_tokens_state`` equals a fresh count of ``state_json`` on 200 states per file.
- ``n_tokens_with_questions`` = state + the call's core questions as canonical JSON.
- p95(state, Call A, E3) ≤ 900 and p95(state + the longest core question + special tokens) ≤ 1,024
  (artifacts/NA-04/token_stats.csv).
"""

from __future__ import annotations

from functools import cache

import pandas as pd
import pytest

from newsaction import io
from newsaction.events import load_events_config, tokens
from newsaction.paths import ROOT
from newsaction.states import load_states_config
from newsaction.states.build import question_tokens
from newsaction.states.questions import load_battery

FILES = (
    "callA_d0_E3",
    "callA_d2_E3",
    "callB_d2_E3",
    "market_E3",
    "samples/callA_d0_E0",
    "samples/callA_d0_E4",
)


@cache
def tok() -> object:
    return tokens.tokenizer(load_events_config().events)


@pytest.mark.parametrize("name", FILES)
def test_stored_counts_match_a_fresh_count(name: str) -> None:
    rel = f"states/{name}.parquet"
    if not (ROOT / "work" / rel).is_file():
        pytest.skip(f"work/{rel} is absent")
    df = io.read_parquet(rel).sample(200, random_state=11)
    fresh = tokens.count_batch(tok(), df["state_json"].tolist())
    assert fresh == df["n_tokens_state"].tolist()
    q = question_tokens(load_battery(), tok())
    assert (
        df["n_tokens_with_questions"] - df["n_tokens_state"] == df["call"].map(lambda c: q[c]["core"])
    ).all()


def test_budget() -> None:
    path = ROOT / "artifacts" / "NA-04" / "token_stats.csv"
    if not path.is_file():
        pytest.skip("artifacts/NA-04/token_stats.csv is absent")
    cfg = load_states_config().tokens
    ts = pd.read_csv(path)
    a = ts.loc[(ts["file"] == "callA_d0_E3") & (ts["encoding"] == "E3")].iloc[0]
    assert a["state_p95"] <= cfg.state_p95_max
    for _, r in ts.loc[ts["file"].isin(["callA_d0_E3", "callA_d2_E3", "callB_d2_E3"])].iterrows():
        assert r["with_longest_q_p95"] <= cfg.total_max, r["file"]
