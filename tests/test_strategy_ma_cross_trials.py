"""NA-13: the exploratory add-on reproduces the operator's validation numbers; the trials ledger holds exactly
NA-13's rows (PRD NA-13 S3, AC3; operator preamble items 6 and 9)."""

from __future__ import annotations

import json

import pytest

from newsaction.ledger import TrialLedger
from newsaction.paths import resolve_layout
from newsaction.strategy import ma_cross as ma
from newsaction.strategy import run


def _result() -> dict[str, object]:
    path = resolve_layout(None).root / run.RESULTS / ma.RESULT
    if not path.exists():
        pytest.skip("the add-on has not run")
    out: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return out


def test_validation_reproduces_the_operator() -> None:
    st = _result()["periods"]["validation"]["statistics"]  # type: ignore[index]
    # the operator's validation reference: all −15.8 bp (NW t −0.9), none −41.1 bp (NW t −2.1) at 5 days
    assert round(st["all|5"]["mean_bp"], 1) == -15.8 and round(st["all|5"]["nw_t"], 1) == -0.9
    assert round(st["none|5"]["mean_bp"], 1) == -41.1 and round(st["none|5"]["nw_t"], 1) == -2.1
    assert all(abs(v["nw_t"]) < 2 for k, v in st.items() if k.endswith("|20"))


def test_trial_rows_logged_once() -> None:
    if not (resolve_layout(None).root / run.RESULTS / "books_test.json").exists():
        pytest.skip("the books have not run")
    expected = run.trial_rows()
    mine = [r for r in TrialLedger().records() if r["chunk"] == run.CHUNK]
    assert {r["kind"] for r in mine} == {run.TRIAL_KIND}
    assert len(mine) == len(expected)
    assert len({(r["name"], r["split"]) for r in mine}) == len(mine)
    assert {(r["name"], r["split"]) for r in mine} == {(r["name"], r["split"]) for r in expected}
