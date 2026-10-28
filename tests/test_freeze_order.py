"""The NA-11 freeze and its order (PREREG §4.4; PRD NA-11 S3, AC1): the pre-conditions, the one-way freeze,
and the evidence that the freeze precedes the first 2026 state and the first "reactions" access."""

from __future__ import annotations

import json
import re
import sqlite3

import pytest
import yaml

from newsaction import lock
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.paths import Layout
from newsaction.production import ProductionError
from newsaction.production import freeze as fz
from newsaction.provenance import utc_now_iso


def _set(lay: Layout, key: str, value: object) -> None:
    path = lay.configs / "frozen.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc[key] = value
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _cache_row(lay: Layout, split: str, session: str, created: str = "2026-10-28T10:00:00+00:00") -> None:
    path = lay.root / "cache" / "decisions.sqlite"
    path.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS responses (created_at TEXT, key TEXT, meta_json TEXT)")
    con.execute(
        "INSERT INTO responses VALUES (?, ?, ?)",
        (created, f"k-{split}-{session}", json.dumps({"split": split, "session": session})),
    )
    con.commit()
    con.close()


@pytest.fixture
def tmp_layout(tmp_layout: Layout) -> Layout:
    """The throwaway repository, with configs/frozen.yaml back in its pre-freeze state."""
    path = tmp_layout.configs / "frozen.yaml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^frozen_requested:.*$", "frozen_requested: false", text, flags=re.MULTILINE)
    text = re.sub(r"^frozen:.*$", "frozen: false", text, flags=re.MULTILINE)
    path.write_text(text, encoding="utf-8")
    return tmp_layout


def test_the_repository_is_ready(tmp_layout: Layout) -> None:
    assert fz.check(tmp_layout) == []


def test_a_missing_section_is_listed(tmp_layout: Layout) -> None:
    _set(tmp_layout, "calibration", None)
    assert any("calibration" in p for p in fz.check(tmp_layout))


def test_a_cached_test_state_blocks_the_freeze(tmp_layout: Layout) -> None:
    _cache_row(tmp_layout, "val_b", "2025-12-30")
    assert fz.check(tmp_layout) == []
    _cache_row(tmp_layout, "test", "2026-01-05")
    assert any("test-period state" in p for p in fz.check(tmp_layout))


def test_a_reactions_access_blocks_the_freeze(tmp_layout: Layout) -> None:
    AccessLedger(tmp_layout.ledgers / TEST_ACCESS).log(
        caller="t", name="prices_raw", purpose="reactions", allowed=False, reason="x", git_sha="0"
    )
    assert any("reactions" in p for p in fz.check(tmp_layout))


def test_freeze_needs_the_request(tmp_layout: Layout) -> None:
    with pytest.raises(lock.LockError, match="frozen_requested"):
        fz.run("t", tmp_layout)


def test_freeze_flow_and_order_evidence(tmp_layout: Layout) -> None:
    fz.request(tmp_layout)
    rec = fz.run("test freeze", tmp_layout)
    assert lock.is_frozen(tmp_layout) and rec["hash"] == lock.compute_freeze_hash(tmp_layout).digest
    for f in (
        "src/newsaction/analysis/spec.py",
        "src/newsaction/panel/targets.py",
        "src/newsaction/analysis/inference.py",
    ):
        assert f in rec["files"]
    ev = fz.evidence(tmp_layout)
    assert ev["order_ok"] and ev["first_reactions_access"] is None and ev["targets_entries"] == 0
    lock.sealed_path("prices_raw_2026", "reactions", layout=tmp_layout)  # after the freeze: allowed, logged
    _cache_row(tmp_layout, "test", "2026-01-05", created=utc_now_iso())  # a 2026 state sent after the freeze
    ev = fz.evidence(tmp_layout)
    assert ev["first_reactions_access"] > ev["freeze_ts"] and ev["order_ok"]
    with pytest.raises(ProductionError, match="already frozen"):
        fz.run("again", tmp_layout)


def test_request_changes_exactly_one_line(tmp_layout: Layout) -> None:
    path = tmp_layout.configs / "frozen.yaml"
    before = path.read_text(encoding="utf-8").splitlines()
    fz.request(tmp_layout)
    after = path.read_text(encoding="utf-8").splitlines()
    assert sum(a != b for a, b in zip(before, after, strict=True)) == 1
    with pytest.raises(ProductionError):
        fz.request(tmp_layout)
