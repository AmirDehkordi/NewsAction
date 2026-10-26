"""Catalog snapshot and eligibility (PRD NA-05 S4, AC7; PREREG §8.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from newsaction.config import load_frozen
from newsaction.dm import CATALOG_FILE
from newsaction.dm.catalog import Outcome, catalog_sha256, eligibility, write_eligibility
from newsaction.paths import ROOT

PASS = Outcome(10, 10, False, 0.0, 0.0, False, False, "2K sentinel: read to the end")
CATALOG = {
    "models": [
        {"id": "a/model"},
        {"id": "a/model:free"},
        {"id": "b/solo:free"},
        {"id": "~a/model-latest"},
        {"id": "c/broken"},
        {"id": "d/untested"},
        {"id": "e/denies"},
        {"id": "f/truncates"},
    ]
}


def test_eligibility_rules() -> None:
    outcomes = {
        "a/model": PASS,
        "c/broken": Outcome(5, 0, False, 1.0, 0.0, False, None),
        "e/denies": Outcome(5, 0, True, 1.0, 0.0, False, None),
        "f/truncates": Outcome(5, 5, False, 0.0, 0.0, False, True),
    }
    rows = {r["id"]: r for r in eligibility(CATALOG, outcomes, ["local/laya"])}
    assert set(rows) == {m["id"] for m in CATALOG["models"]} | {"local/laya"}
    assert rows["a/model"]["include"] and "10/10" in rows["a/model"]["reason"]
    assert not rows["a/model:free"]["include"] and "duplicate of a/model" in rows["a/model:free"]["reason"]
    assert not rows["b/solo:free"]["include"] and "without operator approval" in rows["b/solo:free"]["reason"]
    assert not rows["~a/model-latest"]["include"] and "alias" in rows["~a/model-latest"]["reason"]
    assert not rows["c/broken"]["include"] and "errors" in rows["c/broken"]["reason"]
    assert not rows["d/untested"]["include"]
    assert not rows["e/denies"]["include"] and "data_collection" in rows["e/denies"]["reason"]
    assert not rows["f/truncates"]["include"] and "truncates" in rows["f/truncates"]["reason"]
    assert rows["local/laya"]["include"]


def test_outcome_failures() -> None:
    assert PASS.failure() is None
    assert (
        Outcome(10, 10, False, 0.0, 0.0, True, False).failure()
        == "answers without probabilities (PREREG §8.1)"
    )
    assert "malformed answers" in str(Outcome(10, 10, False, 0.0, 0.5, False, False).failure())
    rounded = Outcome(10, 10, False, 0.0, 0.0, False, False, renormalized_share=0.4)
    assert rounded.failure() is None  # renormalized (rounded) probabilities are not a PREREG §8.1 failure
    assert Outcome(10, 10, False, 0.0, 0.0, False, None).failure() is None  # inconclusive truncation


def test_write_eligibility_replaces_its_block(tmp_path: Path) -> None:
    frozen = tmp_path / "frozen.yaml"
    frozen.write_text("news: null   # keep me\n\nallow_val_b: false\nfrozen: false\n", encoding="utf-8")
    rows = eligibility(CATALOG, {"a/model": PASS}, ["local/laya"])
    write_eligibility(frozen, rows, catalog_sha="ab" * 32)
    once = frozen.read_text(encoding="utf-8")
    write_eligibility(frozen, rows, catalog_sha="ab" * 32)
    assert frozen.read_text(encoding="utf-8") == once
    raw = yaml.safe_load(once)
    assert [r["id"] for r in raw["eligible_models"]] == [r["id"] for r in rows]
    assert raw["free_model_approvals"] == {} and raw["allow_val_b"] is False
    assert once.startswith("news: null   # keep me\n") and once.count("free_model_approvals") == 1


# --- the committed snapshot and configs/frozen.yaml (AC7) -------------------------------------------


@pytest.fixture(scope="module")
def snapshot() -> dict[str, object]:
    path = ROOT / CATALOG_FILE
    if not path.is_file():
        pytest.skip("no catalog snapshot yet")
    out: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return out


def test_snapshot_shape(snapshot: dict[str, object]) -> None:
    models = snapshot["models"]
    assert isinstance(models, list) and len(models) == snapshot["n_models"]
    ids = [m["id"] for m in models]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    for m in models:
        assert {"id", "name", "created", "context_length", "pricing"} <= set(m)
    assert len(str(snapshot["sha256"])) == 64


def test_frozen_lists_every_catalog_id_with_a_reason(snapshot: dict[str, object]) -> None:
    rows = load_frozen().model_extra.get("eligible_models") if load_frozen().model_extra else None  # type: ignore[union-attr]
    if not rows:
        pytest.skip("eligible_models not written yet")
    ids = {m["id"] for m in snapshot["models"]}  # type: ignore[attr-defined]
    listed = {r["id"]: r for r in rows}
    assert ids <= set(listed)
    assert set(listed) - ids == {"local/laya-typed-decisions", "local/laya-base"}
    for r in rows:
        assert isinstance(r["include"], bool) and str(r["reason"]).strip()
    for mid in ids:
        if mid.startswith("~") or mid.endswith(":free"):
            assert listed[mid]["include"] is False
    assert load_frozen().model_extra.get("free_model_approvals") == {}  # type: ignore[union-attr]


def test_catalog_sha256_is_order_free() -> None:
    a = [{"id": "x", "p": 1}, {"id": "y", "p": 2}]
    assert catalog_sha256(a) == catalog_sha256(list(reversed(a)))
    assert catalog_sha256(a) != catalog_sha256([{"id": "x", "p": 1}, {"id": "y", "p": 3}])


def test_snapshot_sha256_recomputes_from_the_file(snapshot: dict[str, object]) -> None:
    assert catalog_sha256(snapshot["models"]) == snapshot["sha256"]  # type: ignore[arg-type]
