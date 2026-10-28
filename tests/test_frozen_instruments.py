"""The frozen trained instruments are laya-s13 and anchor-s13 alone (operator preamble NA-11 item 3;
PREREG §15 NA-11 row): a seed run added later to configs/training.yaml never changes them."""

from __future__ import annotations

import pandas as pd
import pytest
import yaml

from newsaction import io
from newsaction.config import load_frozen
from newsaction.paths import Layout
from newsaction.train import RunSpec, load_training_config
from newsaction.train import import_preds as ip

PINS = {"laya_fin": ("laya-s13",), "anchor": ("anchor-s13",)}


def with_new_seed() -> tuple[object, object]:
    """configs/training.yaml with laya-s17 and anchor-s17 no longer deferred (as after a quota reset)."""
    cfg = load_training_config()
    runs = tuple(
        r.model_copy(update={"deferred": False}) if r.name in ("laya-s17", "anchor-s17") else r
        for r in cfg.kaggle.runs
    )
    return cfg, cfg.model_copy(update={"kaggle": cfg.kaggle.model_copy(update={"runs": runs})})


def names(runs: dict[str, list[RunSpec]]) -> dict[str, list[str]]:
    return {m: [r.name for r in rs] for m, rs in runs.items()}


def test_the_frozen_pin_is_seed_13_alone() -> None:
    assert ip.frozen_runs() == PINS
    sel = load_frozen().selection
    assert sel["trained_runs"] == {k: list(v) for k, v in PINS.items()}


def test_a_new_seed_run_cannot_change_a_pinned_instrument() -> None:
    _, cfg = with_new_seed()
    assert names(ip.ensemble_runs(cfg, PINS)) == {"laya_fin": ["laya-s13"], "anchor": ["anchor-s13"]}
    rob = names(ip.robustness_runs(cfg, PINS))
    assert "laya-s17" in rob["laya_fin"] and "anchor-s17" in rob["anchor"]
    assert "laya-s13" not in rob["laya_fin"]
    # without a pin every seed run would join (PREREG §9.1's ensemble): the pin is what keeps them out
    assert "laya-s17" in names(ip.ensemble_runs(cfg))["laya_fin"]


def test_a_pin_on_an_unplanned_run_is_refused() -> None:
    cfg, _ = with_new_seed()
    with pytest.raises(ip.RunImportError, match="pinned runs"):
        ip.ensemble_runs(cfg, {"laya_fin": ("laya-s99",), "anchor": ("anchor-s13",)})
    with pytest.raises(ip.RunImportError, match="pinned runs"):
        ip.ensemble_runs(cfg, {"laya_fin": ("laya-s13",)})  # the anchor has no pin


def _pin(lay: Layout, pins: dict[str, tuple[str, ...]]) -> None:
    path = lay.configs / "frozen.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["selection"] = {"trained_runs": {k: list(v) for k, v in pins.items()}}
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_read_instrument_refuses_a_file_from_other_runs(tmp_layout: Layout) -> None:
    _pin(tmp_layout, PINS)
    rows = pd.DataFrame({"event_id": ["W0:1:x"], "runs": ["laya-s13"], "n_hat": [0.1]})
    io.write_parquet(
        rows, "kaggle/predictions/laya_fin_val_b.parquet", producer="test", description="t", layout=tmp_layout
    )
    assert len(ip.read_instrument("laya_fin", "val_b", tmp_layout)) == 1
    mixed = rows.assign(runs="laya-s13,laya-s17")
    io.write_parquet(
        mixed, "kaggle/predictions/anchor_val_b.parquet", producer="test", description="t", layout=tmp_layout
    )
    with pytest.raises(ip.RunImportError, match="the pin"):
        ip.read_instrument("anchor", "val_b", tmp_layout)


def test_without_a_pin_read_instrument_refuses(tmp_layout: Layout) -> None:
    path = tmp_layout.configs / "frozen.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["selection"] = None
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    assert ip.frozen_runs(tmp_layout) is None
    with pytest.raises(ip.RunImportError, match="no frozen run pin"):
        ip.read_instrument("laya_fin", "val_b", tmp_layout)
