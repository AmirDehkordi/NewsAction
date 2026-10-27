"""PRD NA-06 AC1 (val-A only) and AC6 (trials), read independently of ``tournament.run``.

Every cache row NA-06 paid for is a val-A state after the embargo (the probes carry their tag), and
trials.jsonl holds one entry per (model, stage, metric). The cache is read from a copy opened immutable (the
client's own connection writes)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from newsaction.config import load_splits
from newsaction.ledger import TrialLedger
from newsaction.paths import ROOT
from newsaction.tournament.sample import embargo_sessions

CACHE = ROOT / "cache" / "decisions.sqlite"
LEADERBOARD = ROOT / "artifacts" / "NA-06" / "leaderboard.csv"


def na06_meta(tmp_path: Path) -> list[dict[str, object]]:
    if not CACHE.is_file():
        pytest.skip("no decision cache in this checkout")
    copy = tmp_path / "decisions.sqlite"
    shutil.copy(CACHE, copy)
    for ext in ("-wal", "-shm"):
        if Path(f"{CACHE}{ext}").is_file():
            shutil.copy(f"{CACHE}{ext}", f"{copy}{ext}")
    db = sqlite3.connect(f"file:{copy}?immutable=1", uri=True)
    try:
        rows = db.execute("SELECT meta_json, tag FROM responses WHERE chunk = 'NA-06'").fetchall()
    finally:
        db.close()
    if not rows:
        pytest.skip("NA-06 has no cache rows yet")
    return [{**json.loads(m), "_tag": t} for m, t in rows]


def test_every_na06_state_is_val_a_after_the_embargo(tmp_path: Path) -> None:
    va = load_splits().splits["val_a"]
    first_ok = embargo_sessions("val_a")[-1].date()
    for meta in na06_meta(tmp_path):
        assert meta["source"] == "states", meta
        assert meta["split"] == "val_a", meta
        s = date.fromisoformat(str(meta["session"]))
        assert first_ok < s <= va.end, meta


def test_probe_rows_carry_their_tag(tmp_path: Path) -> None:
    tags = Counter((m["_tag"], m.get("probe")) for m in na06_meta(tmp_path))
    for (tag, probe), _ in tags.items():
        if str(tag).startswith("p_") and tag != "p_cf_orig":
            assert probe is not None, tag
        if tag in ("s1", "s2a", "s2b", "p_cf_orig"):
            assert probe is None, tag
        if probe == "unmasked_twin":
            assert tag == "p_unmasked"


def test_one_trial_per_model_stage_metric() -> None:
    if not LEADERBOARD.is_file():
        pytest.skip("the NA-06 report has not run")
    recs = [r for r in TrialLedger(ROOT / "ledgers" / "trials.jsonl").records() if r["chunk"] == "NA-06"]
    keys = Counter((r["kind"], r["name"], r["metric"]) for r in recs)
    assert all(n == 1 for n in keys.values()), [k for k, n in keys.items() if n > 1]
    lb = pd.read_csv(LEADERBOARD)
    for m in lb["model"]:
        for metric in ("ic1_z_cc", "ic1_e5"):
            assert keys[("dm_tournament_stage1", m, metric)] == 1, (m, metric)
    for m in lb.loc[lb["stage2"].astype(bool), "model"]:
        for metric in ("ic2_a_z_cc", "ic2_a_e5", "ic2_j_y2", "ic2_b_z_cc", "ece2_a_z_cc"):
            assert keys[("dm_tournament_stage2", m, metric)] == 1, (m, metric)
        for metric in ("company_id_acc", "month_id_acc", "flip_rate", "unmasked_minus_masked", "ic_shuffled"):
            assert keys[("dm_tournament_probe", m, metric)] == 1, (m, metric)
    assert all(r["split"] == "val_a" for r in recs)
