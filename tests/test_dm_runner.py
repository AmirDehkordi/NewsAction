"""Runner: registered state rows → CallSpecs → answer frames (PRD NA-05; used from NA-06 on)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from dm_fakes import MODEL, Recorder, make_client
from newsaction.dm.runner import answers_frame, derived_frame, load_states, state_specs
from newsaction.paths import ROOT, Layout
from newsaction.states.questions import canonical_json, load_battery


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")


def rows(n: int = 2) -> pd.DataFrame:
    out = []
    for i in range(n):
        state = {
            "company": {"sector": "Energy"},
            "news": [{"headline": f"The company item {i}", "snippet": "x"}],
        }
        js = canonical_json(state)
        out.append(
            {
                "event_id": f"W0:{i}:2024-08-01",
                "session": date(2024, 8, 1),
                "split": "train",
                "call": "A",
                "encoding": "E3",
                "masked": True,
                "state_json": js,
                "state_sha256": hashlib.sha256(js.encode()).hexdigest(),
                "n_tokens_state": 10,
                "third_party_ok_all": True,
            }
        )
    return pd.DataFrame(out)


def test_state_specs_carry_provenance_and_the_battery() -> None:
    specs = state_specs(
        rows(), "states/callA_d0_E3.parquet", MODEL, call="A", groups=["core", "extended"], tag="t"
    )
    assert len(specs) == 2
    s = specs[0]
    assert list(s.request.questions) == load_battery().keys("A", ["core", "extended"])
    assert s.info.event_id == "W0:0:2024-08-01" and s.info.file == "work/states/callA_d0_E3.parquet"
    assert s.request.state_sha256() == rows().iloc[0]["state_sha256"]
    probe = state_specs(rows(1), "states/samples/unmasked.parquet", MODEL, call="A", probe="unmasked_twin")
    assert probe[0].info.probe == "unmasked_twin"


def test_state_specs_refuse_a_mismatched_hash() -> None:
    bad = rows(1).assign(state_sha256="0" * 64)
    with pytest.raises(ValueError, match="state_sha256"):
        state_specs(bad, "states/callA_d0_E3.parquet", MODEL, call="A")


def test_frames_from_results(tmp_layout: Layout, tmp_path: Path) -> None:
    client = make_client(tmp_layout, tmp_path, Recorder())
    specs = state_specs(rows(), "states/callA_d0_E3.parquet", MODEL, call="A")
    results = client.decide(specs)
    ans = answers_frame(results)
    assert set(ans["question"]) == {"justified_move", "materiality", "surprise", "tone"}
    sums = ans.groupby(["key", "question"])["p"].sum()
    assert ((sums - 1).abs() < 1e-9).all()
    der = derived_frame(results)
    assert len(der) == 2 and der["valid"].all() and der["ok"].all()
    assert der["n_hat"].abs().max() < 1e-9  # uniform answers: N̂ = 0
    assert (der["m"] == 0.5).all() and (der["model_build"] == f"{MODEL}-build-7").all()
    assert json.loads(results[0].row.meta_json)["event_id"] == "W0:0:2024-08-01"  # type: ignore[union-attr]


def test_load_states_filters() -> None:
    if not (ROOT / "work" / "states" / "callB_d2_E3.parquet").is_file():
        pytest.skip("work/states is absent")
    df = load_states("states/callB_d2_E3.parquet", splits=["train"], event_ids=["W2:144:2024-07-01"])
    assert len(df) == 1 and df["split"].iloc[0] == "train"
