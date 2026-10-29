"""NA-13b (f): every evaluated variant is one valid, unique ledger row, logged once (CLAUDE.md B10)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from newsaction.ledger import TrialLedger
from newsaction.selective import trials as tr


def tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cov = pd.DataFrame(
        {"model": ["laya_fin"] * 4, "ranking": ["conviction"] * 4, "coverage": [1.0, 0.1, 1.0, 0.1],
         "split": ["val_a", "val_a", "test", "test"], "target": "z_id",
         "signed": [0.01, 0.1, float("nan"), 0.05], "threshold": [float("-inf"), 0.13, float("-inf"), 0.13]}
    )  # fmt: skip
    cov = pd.concat([cov, cov.assign(target="z_cc")], ignore_index=True)  # only z_id rows are logged
    watch = pd.DataFrame({"model": ["d1_ultra"] * 2, "statistic": ["ic_pre_open", "mean_with"],
                          "split": ["val_b", "val_b"], "value": [0.019, -0.013]})  # fmt: skip
    cond = pd.DataFrame(
        {"model": "laya_fin", "condition": "e2_numbers", "outcome": "z_id", "level": "event",
         "split": ["val_a", "val_b", "val_pooled", "test"], "diff": [0.06, 0.15, 0.1, 0.02]}
    )  # fmt: skip
    books = pd.DataFrame({"book": ["exploratory|selective|laya_fin|e2_numbers"] * 2, "exit": "close_t",
                          "split": ["val_b", "test"], "sharpe_net_10": [-0.4, 0.3]})  # fmt: skip
    return cov, watch, cond, books


def test_rows_are_unique_valid_and_skip_the_pooled_split(tmp_path: Path) -> None:
    rows = tr.all_rows(*tables())
    assert len(rows) == 4 + 2 + 3 + 2  # the pooled-validation row is not a ledger split
    assert len({(r["name"], r["split"]) for r in rows}) == len(rows)
    assert all(r["name"].startswith("exploratory|selective|") for r in rows)
    assert [r["value"] for r in rows][2] is None  # NaN → None
    out = tr.log(rows, path=tmp_path / "trials.jsonl")
    assert out == {"added": len(rows), "skipped": 0, "ledger_rows": len(rows)}
    recs = TrialLedger(tmp_path / "trials.jsonl").records()
    assert {r["chunk"] for r in recs} == {"NA-13b"} and {r["kind"] for r in recs} == {"exploratory"}


def test_logging_is_idempotent_and_refuses_a_changed_value(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    rows = tr.all_rows(*tables())
    tr.log(rows, path=path)
    assert tr.log(rows, path=path) == {"added": 0, "skipped": len(rows), "ledger_rows": len(rows)}
    changed = [dict(r) for r in rows]
    changed[0]["value"] = 0.5
    with pytest.raises(tr.TrialsError):
        tr.log(changed, path=path)
