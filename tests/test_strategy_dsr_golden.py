"""NA-13 AC3: the deflated Sharpe equals ATOM's within 1e-6 on the golden cases; n_trials = the ledger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from newsaction.ledger import TrialLedger
from newsaction.strategy import dsr

GOLDEN = Path(__file__).parent / "golden" / "dsr_atom.json"
CASES = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_matches_atom(case: dict[str, object]) -> None:
    got = dsr.deflated_sharpe(case["returns"], **case["kwargs"]).as_dict()  # type: ignore[arg-type]
    for k, v in case["atom"].items():  # type: ignore[attr-defined]
        assert abs(float(got[k]) - float(v)) <= 1e-6, (k, got[k], v)


def test_golden_covers_the_branches() -> None:
    names = {c["name"] for c in CASES}
    assert {"one_obs", "zero_dispersion", "normal_n1", "normal_n600_var", "fat_n563_bench"} <= names
    assert len(CASES) >= 10


def test_deflation_grows_with_trials() -> None:
    r = CASES[0]["returns"]
    a = dsr.deflated_sharpe(r, n_trials=10)
    b = dsr.deflated_sharpe(r, n_trials=1000)
    assert b.sr0 > a.sr0 and b.prob < a.prob


def test_n_trials_is_the_ledger_count() -> None:
    parts = dsr.trial_parts()
    assert dsr.trial_count() == sum(parts.values()) == len(TrialLedger().records())
    assert all(v > 0 for v in parts.values())
