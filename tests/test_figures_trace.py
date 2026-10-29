"""NA-14 AC4: every plotted number traces to an NA-03 … NA-13 output (PRD NA-14 AC4; ``figures.sources``).

- each figure CSV's rows equal their upstream cells, values and intervals, and name only upstream files of
  NA-03,
  NA-06, NA-07, NA-11, NA-12, NA-13 or the NA-14 tables that copy them (``test_figures_tables``);
- each committed figure CSV equals a fresh build from its sources;
- the trace is not vacuous: a changed value, interval or key is caught.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from newsaction.figures import data, render
from newsaction.figures import sources as sc
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
    df = render.read("fig1_convergence")
    bad = df.copy()
    bad.loc[0, "y"] = float(bad.loc[0, "y"]) + 1e-6
    found = sc.trace(bad, src)  # the value, and the SE interval built around it
    assert len(found) == 2 and ": y " in found[0] and "interval" in found[1]
    bad = df.copy()
    i = bad.index[bad["ci"] == "se"][0]
    bad.loc[i, "hi"] = float(bad.loc[i, "hi"]) + 1e-6
    assert "interval" in sc.trace(bad, src)[0]
    bad = df.copy()
    bad.loc[0, "key"] = "laya_fin|v_decile|99|car_post0"
    assert "no row" in sc.trace(bad, src)[0]


def test_interval_kinds() -> None:
    frame = pd.DataFrame({"model": ["m"], "est": [0.2], "se": [0.05], "t": [4.0], "lo": [0.1], "hi": [0.3]})
    sc.KEYS["toy.csv"] = ("model",)
    try:
        se = sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="se", se_col="se")
        t = sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="t", se_col="t")
        table = sc.rows(
            frame, "toy.csv", panel="a", series="=m", y_col="est", ci="table", lo_col="lo", hi_col="hi"
        )
    finally:
        del sc.KEYS["toy.csv"]
    assert math.isclose(se["lo"].iloc[0], 0.2 - 1.959963984540054 * 0.05)
    assert math.isclose(t["hi"].iloc[0], 0.2 + 1.959963984540054 * 0.05)
    assert (table["lo"].iloc[0], table["hi"].iloc[0]) == (0.1, 0.3)
    with pytest.raises(ValueError):
        sc.rows(frame, "toy.csv", panel="a", series="=m", y_col="est", ci="bootstrap")


def test_key_parts() -> None:
    assert sc.row_key(["laya_fin", 10, 0.3, 1.0, float("nan"), True]) == "laya_fin|10|0.3|1||True"
