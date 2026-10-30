"""NA-14 AC4: every plotted number traces to an NA-03 … NA-13 output (PRD NA-14 AC4; ``figures.sources``).

- each figure CSV's rows equal their upstream cells, values and intervals, and name only upstream files of
  NA-03, NA-06, NA-07, NA-11, NA-12, NA-13 or the NA-14 tables that copy or aggregate them;
- each committed figure CSV equals a fresh build from its sources;
- the trace is not vacuous: a changed value, interval or key is caught;
- the interval kinds, the Wilson interval among them, and the two aggregations of stored files: t33's placebo
  quantiles recomputed from NA-13's placebo books (and equal to the ones NA-13's REPORT §7 quotes), t35's
  break-even costs recomputed from NA-13's strategy table.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from newsaction import io
from newsaction.figures import data, render
from newsaction.figures import sources as sc
from newsaction.figures import tables as tb
from newsaction.paths import ROOT

ALLOWED = (
    "artifacts/NA-03/",
    "artifacts/NA-06/",
    "artifacts/NA-07/",
    "artifacts/NA-11/",
    "artifacts/NA-12/",
    "artifacts/NA-13/",
    "artifacts/NA-14/tables/",
)


@pytest.fixture(scope="module")
def src() -> sc.Sources:
    return sc.Sources(ROOT)


def test_every_figure_has_a_builder_and_a_drawing() -> None:
    assert set(data.BUILDERS) == set(render.MODULES)
    assert len([n for n in data.BUILDERS if not n.startswith("figA")]) == 7


@pytest.mark.parametrize("name", list(data.BUILDERS))
def test_every_plotted_value_traces_to_its_source(name: str, src: sc.Sources) -> None:
    df = render.read(name)
    assert len(df) > 0
    assert list(df.columns) == list(sc.COLUMNS)
    assert sc.trace(df, src) == []
    assert {s for s in df["source"] if not s.startswith(ALLOWED)} == set()


@pytest.mark.parametrize("name", list(data.BUILDERS))
def test_committed_csv_is_a_fresh_build(name: str, src: sc.Sources) -> None:
    text = data.BUILDERS[name](src).to_csv(index=False, lineterminator="\n")
    assert text == (ROOT / sc.FIGURES / f"{name}.csv").read_text(encoding="utf-8")


def test_trace_catches_a_changed_value_interval_or_key(src: sc.Sources) -> None:
    df = render.read("fig3_convergence")
    bad = df.copy()
    bad.loc[0, "y"] = float(bad.loc[0, "y"]) + 1e-6
    found = sc.trace(bad, src)  # the value, and the SE interval built around it
    assert len(found) == 2 and ": y " in found[0] and "interval" in found[1]
    bad = df.copy()
    i = bad.index[bad["ci"] == "se"][0]
    bad.loc[i, "hi"] = float(bad.loc[i, "hi"]) + 1e-6
    assert "interval" in sc.trace(bad, src)[0]
    bad = df.copy()
    bad.loc[0, "key"] = "d1_ultra|v_decile|99|car_post0"
    assert "no row" in sc.trace(bad, src)[0]
    w = render.read("fig7_memorisation")
    bad = w.copy()
    i = bad.index[bad["ci"] == "wilson"][0]
    bad.loc[i, "lo"] = float(bad.loc[i, "lo"]) - 1e-6
    assert "interval" in sc.trace(bad, src)[0]


def test_interval_kinds() -> None:
    frame = pd.DataFrame(
        {"model": ["m"], "est": [0.2], "se": [0.05], "t": [4.0], "lo": [0.1], "hi": [0.3], "n": [400.0]}
    )
    sc.KEYS["toy.csv"] = ("model",)
    try:
        se = sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="se", se_col="se")
        se1 = sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="se1", se_col="se")
        t = sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="t", se_col="t")
        wil = sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="wilson", se_col="n")
        table = sc.rows(
            frame, "toy.csv", panel="a", series="=m", y_col="est", ci="table", lo_col="lo", hi_col="hi"
        )
        with pytest.raises(ValueError):
            sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="bootstrap")
        with pytest.raises(ValueError, match="count"):
            sc.rows(
                frame.assign(n=[399.0]),
                "toy.csv",
                panel="a",
                series="=m",
                y_col="est",
                ci="wilson",
                se_col="n",
            )
    finally:
        del sc.KEYS["toy.csv"]
    assert math.isclose(se["lo"].iloc[0], 0.2 - 1.959963984540054 * 0.05)
    assert math.isclose(se1["hi"].iloc[0], 0.25)
    assert math.isclose(t["hi"].iloc[0], 0.2 + 1.959963984540054 * 0.05)
    assert (table["lo"].iloc[0], table["hi"].iloc[0]) == (0.1, 0.3)
    # Wilson (1927), 80 of 400: centre (p + z²/2n)/(1 + z²/n), half-width z √(p(1−p)/n + z²/4n²)/(1 + z²/n)
    assert math.isclose(wil["lo"].iloc[0], 0.1637, abs_tol=5e-5) and math.isclose(
        wil["hi"].iloc[0], 0.2420, abs_tol=5e-5
    )


def test_key_parts() -> None:
    assert sc.row_key(["laya_fin", 10, 0.3, 1.0, float("nan"), True]) == "laya_fin|10|0.3|1||True"


def test_placebo_quantiles_recompute_from_na13s_books() -> None:
    if not (ROOT / "work" / tb.PLACEBO).is_file():
        pytest.skip(f"work/{tb.PLACEBO} is absent (run NA-13)")
    placebo = io.read_parquet(tb.PLACEBO, columns=["universe", "seed", *tb.PLACEBO_COLUMNS])
    t33 = pd.read_csv(ROOT / sc.TABLES / "t33_placebo_sharpe.csv").set_index("key")
    assert len(t33) == placebo["universe"].nunique() and (t33["n_books"] == 100).all()
    for universe, g in placebo.groupby("universe"):
        for col in tb.PLACEBO_COLUMNS:
            for tag, q in tb.QUANTILES:
                assert t33.loc[universe, f"{col}_{tag}"] == pytest.approx(
                    float(np.quantile(g[col], q)), abs=1e-12
                )
    # NA-13 REPORT §7: S-CONV D2 / t+5 gross −2.12 / −0.04 / 2.23, net 10 bp −6.25 / −4.05 / −1.99
    sconv = t33.loc["D2|close_t+5|32ca4af468b92207"]
    assert [round(float(sconv[f"sharpe_gross_{t}"]), 2) for t, _ in tb.QUANTILES] == [-2.12, -0.04, 2.23]
    assert [round(float(sconv[f"sharpe_net_10_{t}"]), 2) for t, _ in tb.QUANTILES] == [-6.25, -4.05, -1.99]


def test_break_even_is_gross_mean_over_turnover() -> None:
    st = pd.read_csv(ROOT / sc.STRATEGY)
    t35 = pd.read_csv(ROOT / sc.TABLES / "t35_break_even.csv").set_index("key")
    test = st[(st["split"] == "test") & st["turnover_daily"].notna()].set_index("rule")
    assert set(t35.index) == set(test.index)
    want = test["ann_return_gross"] / 252.0 / test["turnover_daily"] * 1e4
    assert np.allclose(t35.loc[want.index, "break_even_bp"], want, atol=1e-9)
    # NA-13 REPORT §6: gated S-D0 8.3 bp (t+1) and 3.7 bp (close); S-CONV Laya-Fin D1 / t+5 5.1 bp
    for rule, bp in (
        ("S-D0|laya_fin|D0|n_tilde|close_t+1|gated", 8.3),
        ("S-D0|laya_fin|D0|n_tilde|close_t|gated", 3.7),
        ("S-CONV|laya_fin|D1|u|close_t+5|all", 5.1),
    ):
        assert round(float(t35.loc[rule, "break_even_bp"]), 1) == bp
