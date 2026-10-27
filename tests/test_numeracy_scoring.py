"""PRD NA-07 S3 / AC1: the numeracy probe's synthetic blocks and its monotonicity score.

The score is re-derived here from the series in artifacts/NA-07/numeracy_series.csv; the synthetic block
changes only ``reaction_so_far``, and its move text grows with |z| in every encoding."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from newsaction.encoding import load_encoding_config
from newsaction.encoding.numeracy import (
    LARGE,
    SMALL,
    gate,
    grid,
    monotone,
    percentile_of,
    score,
    series_table,
    synthetic_reaction,
    with_reaction,
)
from newsaction.paths import ROOT
from newsaction.states.codebook import load_codebook

ART = ROOT / "artifacts" / "NA-07"
TOL = 1e-9


def test_monotone_definition() -> None:
    assert monotone([0.0, 0.1, 0.1, 0.5], [0.6, 0.4, 0.4, 0.0], TOL)
    assert not monotone([0.0, 0.2, 0.1, 0.5], [0.6, 0.4, 0.3, 0.0], TOL)  # L dips
    assert not monotone([0.0, 0.1, 0.2, 0.5], [0.6, 0.4, 0.45, 0.0], TOL)  # S rises
    assert monotone([0.1, 0.1 - 1e-12], [0.2, 0.2 + 1e-12], TOL)  # float noise within tol
    assert not monotone([0.1, 0.09], [0.2, 0.2], TOL)
    assert not monotone([0.1, math.nan], [0.2, 0.1], TOL)  # a missing answer is not monotone
    with pytest.raises(ValueError):
        monotone([0.1], [0.2], TOL)


def _answers() -> pd.DataFrame:
    rows = []
    good = [(0.0, 0.8), (0.1, 0.5), (0.3, 0.2), (0.6, 0.0)]
    bad = [(0.0, 0.8), (0.3, 0.5), (0.1, 0.2), (0.6, 0.0)]
    for m, series in (("m1", good), ("m2", bad)):
        for d in ("rise", "fall"):
            for i, (pl, ps) in enumerate(series):
                rows.append(
                    {
                        "model": m,
                        "event_id": "e1",
                        "direction": d,
                        "magnitude_idx": i,
                        "p_large": pl,
                        "p_small": ps,
                    }
                )
    df = pd.DataFrame(rows)
    df.loc[(df["model"] == "m1") & (df["direction"] == "fall") & (df["magnitude_idx"] == 3), "p_large"] = (
        math.nan
    )
    return df


def test_series_and_score() -> None:
    s = series_table(_answers(), 4, TOL)
    assert len(s) == 4
    m1 = s.loc[s["model"] == "m1"].set_index("direction")
    assert bool(m1.loc["rise", "monotone"]) and not bool(m1.loc["fall", "monotone"])  # missing → not monotone
    assert not bool(m1.loc["fall", "complete"])
    sc = score(s, 0.90).set_index("model")
    assert sc.loc["m1", "share"] == 0.5 and sc.loc["m2", "share"] == 0.0
    assert not sc["passes"].any()
    rise = s.loc[(s["model"] == "m1") & (s["direction"] == "rise")]
    assert score(rise, 0.90)["passes"].all()


def test_synthetic_reaction_moves_grow_with_the_magnitude() -> None:
    c = load_encoding_config().numeracy
    cb = load_codebook()
    for d, sign in (("rise", 1.0), ("fall", -1.0)):
        e3 = [
            synthetic_reaction(cb, sign * z, "E3", c)["stock_move_vs_market_and_sector"] for z in c.magnitudes
        ]
        mult = [float(t.split("(≈")[1].split("×")[0]) for t in e3]
        assert mult == sorted(mult) and all(t.endswith("a typical day's move)") for t in e3)
        assert all((d in t) for t in e3)
        e1 = [
            synthetic_reaction(cb, sign * z, "E1", c)["stock_move_vs_market_and_sector"] for z in c.magnitudes
        ]
        assert [abs(float(t.rstrip("σ"))) for t in e1] == sorted(abs(float(t.rstrip("σ"))) for t in e1)
        e0 = synthetic_reaction(cb, sign * 2.5, "E0", c)["stock_move_vs_market_and_sector"]
        assert e0.startswith("+3.8%" if sign > 0 else "-3.8%") and "(S&P 500 +0.1%)" in e0
        e4 = [
            synthetic_reaction(cb, sign * z, "E4", c)["stock_move_vs_market_and_sector"] for z in c.magnitudes
        ]
        pct = [int(t.split("larger than ")[1].split("%")[0]) for t in e4]
        assert pct == sorted(pct)
    fixed = {
        k: v
        for k, v in synthetic_reaction(cb, 2.5, "E3", c).items()
        if k != "stock_move_vs_market_and_sector"
    }
    assert fixed == {
        "time": "by the close",
        "stock_market_move": "negligible rise (≈0.1× a typical day's move)",
        "volume_vs_normal": "busy",
    }
    assert percentile_of(0.0) == 0.0 and 68 < percentile_of(1.0) < 69


def test_grid_has_both_directions_at_every_magnitude() -> None:
    g = grid((0.3, 0.7))
    assert g == [("rise", 0, 0.3), ("rise", 1, 0.7), ("fall", 0, -0.3), ("fall", 1, -0.7)]


def test_with_reaction_changes_only_the_reaction_block() -> None:
    state = {"company": {"size": "x"}, "news": [{"headline": "h"}], "reaction_so_far": {"time": "t"}}
    new = with_reaction(state, {"time": "by the close", "a": "b"})
    assert {k: v for k, v in new.items() if k != "reaction_so_far"} == {
        k: v for k, v in state.items() if k != "reaction_so_far"
    }
    assert new["reaction_so_far"] == {"a": "b", "time": "by the close"} and state["reaction_so_far"] == {
        "time": "t"
    }
    with pytest.raises(ValueError):
        with_reaction({"news": []}, {"time": "t"})


def test_probability_groups_are_the_q5_options() -> None:
    from newsaction.dm.parse import ADEQUACY_KEYS

    assert set(LARGE) | set(SMALL) <= set(ADEQUACY_KEYS)
    assert LARGE == ("too_large", "much_too_large") and SMALL == ("too_small", "much_too_small")


def test_gate_prefers_e3_per_model_and_follows_the_leading_model() -> None:
    shares = {"lead": 0.95, "b": 0.50, "c": 0.90}
    chosen, by_model = gate("E1", "E3", shares, "lead", 0.90)
    assert chosen == "E1" and by_model == {"lead": "E1", "b": "E3", "c": "E1"}  # 0.90 itself passes
    chosen, by_model = gate("E1", "E3", {**shares, "lead": 0.8999}, "lead", 0.90)
    assert chosen == "E3" and by_model["lead"] == "E3"
    assert gate("E3", "E3", {"lead": 0.0}, "lead", 0.90) == ("E3", {"lead": "E3"})  # E3 is never gated
    with pytest.raises(ValueError):
        gate("E1", "E3", {"b": 1.0}, "lead", 0.90)


def test_numeracy_csv_recomputed_from_the_series() -> None:
    if not (ART / "numeracy.csv").is_file():
        pytest.skip("NA-07 has not written numeracy.csv yet")
    c = load_encoding_config().numeracy
    series = pd.read_csv(ART / "numeracy_series.csv")
    again = []
    for rec in series.to_dict("records"):
        large, small = json.loads(rec["p_large"]), json.loads(rec["p_small"])
        assert len(large) == len(c.magnitudes)
        again.append(monotone([float(x) for x in large], [float(x) for x in small], c.tol))
    assert again == series["monotone"].astype(bool).tolist()
    tab = pd.read_csv(ART / "numeracy.csv")
    for e, g in series.groupby("encoding"):
        sc = score(g, 0.90).set_index("model")["share"].to_dict()
        assert sc == pytest.approx(tab.loc[tab["encoding"] == e].set_index("model")["share"].to_dict())
    assert (tab["passes"] == (tab["share"] >= 0.90)).all()
    assert (tab["n_series"] == 2 * c.n_news).all()
    assert set(tab["role"]) <= {"gate", "reference"} and (tab["role"] == "gate").sum() == 3
    assert tab.loc[tab["leading"], "model"].unique().tolist() == [load_encoding_config().models.expected[0]]
