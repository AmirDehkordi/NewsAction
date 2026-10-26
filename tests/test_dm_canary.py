"""canary_v1 and its baseline (PRD NA-05 S7, AC6)."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from newsaction import io
from newsaction.config import load_splits
from newsaction.dm import CANARY_BASELINE, CANARY_FILE, DMError
from newsaction.dm.canary import NUMERACY_Z, build_canary, load_canary, max_abs_delta, write_canary
from newsaction.paths import ROOT
from newsaction.states.questions import load_battery

PILOT_MODELS = (
    "typesafe/jev-1.14",
    "openai/gpt-6-luna-decisions",
    "inception/mercury-decide",
    "liquid/d1",
    "perplexity/pplx-decider-v1.2",
)


@pytest.fixture(scope="module")
def items() -> list:  # type: ignore[type-arg]
    path = ROOT / CANARY_FILE
    if not path.is_file():
        pytest.skip("canary_v1 not written yet")
    return load_canary(path)


def test_fifty_states_with_hashes(items: list) -> None:  # type: ignore[type-arg]
    assert len(items) == 50
    assert [it.canary_id for it in items] == [f"C{i:02d}" for i in range(1, 51)]
    kinds = Counter((it.kind, it.group, it.call) for it in items)
    assert kinds == {
        ("train", "train_A", "A"): 20,
        ("train", "train_B", "B"): 10,
        ("synthetic", "synthetic_A", "A"): 6,
        ("synthetic", "numeracy", "B"): 14,
    }
    assert len({it.state_sha256 for it in items}) == 50


def test_train_states_are_train_period_masked_and_third_party_ok(items: list) -> None:  # type: ignore[type-arg]
    train_end = load_splits().splits["train"].end
    for it in items:
        if it.kind == "train":
            assert it.info.split == "train" and it.info.session is not None
            assert it.info.session <= train_end <= date(2025, 6, 30)
            assert it.info.masked and it.info.third_party_ok_all and it.info.source == "states"
        else:
            assert it.info.source == "synthetic" and it.info.session is None


def test_questions_are_the_core_battery(items: list) -> None:  # type: ignore[type-arg]
    b = load_battery()
    for it in items:
        assert it.questions == b.request(it.call, ["core"])
        assert ("reaction_so_far" in it.state) == (it.call == "B")


def test_numeracy_grid(items: list) -> None:  # type: ignore[type-arg]
    grid = sorted(it.move_z for it in items if it.group == "numeracy")
    assert grid == sorted([z for z in NUMERACY_Z] + [-z for z in NUMERACY_Z])
    news = {str(it.state["news"]) for it in items if it.group == "numeracy"}
    assert len(news) == 1  # the same news in every numeracy state


def test_build_reproduces_the_file(tmp_path: Path) -> None:
    if not (ROOT / "work" / "states" / "callA_d0_E3.parquet").is_file():
        pytest.skip("work/states is absent")
    sha = write_canary(build_canary(), tmp_path / "canary.jsonl")
    assert sha == io.sha256_file(ROOT / CANARY_FILE)


def test_a_tampered_line_is_refused(tmp_path: Path) -> None:
    lines = (ROOT / CANARY_FILE).read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace("the company", "the firm", 1)
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(DMError, match="sha256"):
        load_canary(bad)


def test_max_abs_delta() -> None:
    base = pd.DataFrame(
        {"canary_id": ["C01", "C01"], "question": ["q", "q"], "option": ["a", "b"], "p": [0.6, 0.4]}
    )
    now = base.assign(p=[0.55, 0.45])
    out = max_abs_delta(base, now)
    assert out["cells"] == 2 and out["max_abs_dp"] == pytest.approx(0.05)
    assert max_abs_delta(base, now.iloc[:0])["cells"] == 0


@pytest.fixture(scope="module")
def baseline() -> pd.DataFrame:
    path = ROOT / CANARY_BASELINE
    if not path.is_file():
        pytest.skip("no canary baseline yet")
    return pd.read_parquet(path)


def test_baseline_has_every_pilot_model(baseline: pd.DataFrame, items: list) -> None:  # type: ignore[type-arg]
    assert set(PILOT_MODELS) <= set(baseline["model"])
    assert {"local/laya-typed-decisions", "local/laya-base"} <= set(baseline["model"])
    ids = {it.canary_id for it in items}
    for _, g in baseline.groupby("model"):
        assert set(g["canary_id"]) <= ids and g["canary_id"].nunique() >= 45
        assert (g["repeat_idx"] == 0).all()
    sums = baseline.groupby(["model", "canary_id", "question"])["p"].sum()
    assert ((sums - 1).abs() <= 1e-6).all()  # renormalized answers included
    assert baseline["p"].between(0, 1).all()
    assert baseline["renormalized"].dtype == bool
    flagged = baseline.loc[baseline["renormalized"], "model"].unique().tolist()
    assert set(flagged) <= {"typesafe/jev-1.14"}  # the only pilot model with rounded sums (a 0.01 grid)


def test_baseline_is_registered(baseline: pd.DataFrame) -> None:
    entry = io.load_manifest()["artifacts"].get(CANARY_BASELINE)
    if entry is None:
        pytest.skip("baseline not registered in this checkout's manifest")
    assert entry["sha256"] == io.sha256_file(ROOT / CANARY_BASELINE)
    assert entry["rows"] == len(baseline)
