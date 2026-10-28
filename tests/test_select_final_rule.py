"""PREREG §8.5's final-selection rule (production.select_final), the val-A maps, and the consistency of
configs/frozen.yaml with artifacts/NA-11/final_selection.csv (PRD NA-11 S2, AC2)."""

from __future__ import annotations

import hashlib
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction.config import load_frozen, load_splits
from newsaction.paths import ROOT
from newsaction.production import select_final as sf

TABLE = ROOT / "artifacts" / "NA-11" / "final_selection.csv"


def table(*rows: tuple[str, float, float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"model": m, "role": "candidate", "ic": ic, "ic_j_y2": j, "cost_per_1000": c}
            for m, ic, j, c in rows
        ]
    )


def test_highest_ic_wins_outside_the_tie_band() -> None:
    assert sf.choose(table(("a", 0.060, 0.0, 0.0), ("b", 0.050, 0.9, 0.0))) == ("a", "highest val-B IC")


def test_tie_breaks_in_prereg_order() -> None:
    w, why = sf.choose(table(("a", 0.060, 0.01, 0.0), ("b", 0.0571, 0.02, 0.0), ("c", 0.01, 0.9, 0.0)))
    assert w == "b" and "IC(J, y2)" in why  # ΔIC < 0.005: the higher IC of J with y2
    w, why = sf.choose(table(("a", 0.060, 0.02, 0.05), ("b", 0.0571, 0.02, 0.0)))
    assert w == "b" and "cost" in why  # then the lower cost per 1,000 decisions
    w, why = sf.choose(table(("a", 0.060, 0.02, 0.0), ("b", 0.0571, 0.02, 0.0)))
    assert w == "a" and "higher IC" in why  # then the higher IC


def test_a_comparator_is_never_selected() -> None:
    t = pd.concat(
        [table(("a", 0.03, 0.0, 0.0)), pd.DataFrame([{"model": "api", "role": "comparator", "ic": 0.2}])]
    )
    assert sf.choose(t)[0] == "a"


def test_fit_map_is_increasing_and_flat_outside() -> None:
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=500))
    y = pd.Series(0.3 * x + rng.normal(size=500))
    m = sf.fit_map(x, y)
    assert np.all(np.diff(m["x"]) > 0) and np.all(np.diff(m["y"]) >= 0) and m["n"] == 500
    with pytest.raises(sf.ProductionError):
        sf.fit_map(x.head(10), y.head(10))


def test_frozen_selection_matches_the_table() -> None:
    sel = load_frozen().selection
    assert hashlib.sha256(TABLE.read_bytes()).hexdigest() == sel["ic_table_sha"]
    t = pd.read_csv(TABLE)
    assert sf.choose(t)[0] == sel["primary_instrument"]
    assert (
        sorted(t.loc[t["role"] == "candidate", "model"]) == sorted(sf.CANDIDATES) == sorted(sel["candidates"])
    )
    assert sel["trained_runs"] == {"laya_fin": ["laya-s13"], "anchor": ["anchor-s13"]}
    assert not t.loc[t["role"] != "candidate", "selected"].fillna(False).astype(bool).any()


def test_maps_and_gates_are_val_a_fits() -> None:
    va = load_splits().splits["val_a"]
    for model, entry in load_frozen().calibration.items():
        for src in ("a0", "a2"):
            if src not in entry:
                continue
            e = entry[src]
            lo, hi = (date.fromisoformat(d) for d in e["fit_range"])
            assert e["split"] == "val_a" and va.start <= lo <= hi <= va.end, (model, src)
            for name in ("v", "n_tilde"):
                assert np.all(np.diff(e[name]["x"]) > 0) and np.all(np.diff(e[name]["y"]) >= 0), (model, src)
                assert e[name]["n"] >= 30
        for g in entry.get("gates", {}).values():
            assert g["percentile"] == 0.7 and 0 <= g["value"] <= 1
    assert "price_only" in load_frozen().calibration


def test_strategy_section_holds_s_conv() -> None:
    st = load_frozen().model_extra["strategy"]
    assert st["s_conv"]["primary"] and set(st["s_conv"]["points"]) == {"D1", "D2"}
    assert (
        st["quantile"] == 0.2 and st["costs_bp_per_side"] == [5, 10, 20] and st["gating"]["percentile"] == 0.7
    )
