"""NA-12 S3 / AC4: the tables' machine-readable keys (PRD NA-12).

- ``cite`` renders {{table/key/column}} with the tables' formatting and refuses an unknown key, so NA-14's
  captions can be tested against the tables;
- keys are unique within a table, the LaTeX has one line per row between booktabs rules, and ``keys_of``
  holds every non-empty cell;
- ``required`` names a row for every pre-registered test (each primary and secondary test, each cut, each
  ladder and gap rung, the robustness items not run);
- once ``artifacts/NA-12/tables`` exists: every key resolves to its CSV cell, every table has its CSV and
  LaTeX, and no required key is missing (AC4).
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from newsaction.analysis import spec, tables
from newsaction.analysis.run_all import FOCUS, TESTS
from newsaction.paths import ROOT

TABLES_DIR = ROOT / "artifacts" / "NA-12" / "tables"


def _toy() -> tables.Table:
    frame = tables._frame(
        [
            {"key": "H1", "estimate": 0.0123, "primary_p": 0.0004, "n_obs": 1500.0, "verdict": "general"},
            {
                "key": "H2",
                "estimate": float("nan"),
                "primary_p": 0.2,
                "n_obs": 10.0,
                "verdict": "not supported",
            },
        ]
    )
    return tables.Table("t_toy", "A toy table with an under_score", frame, ("a note",))


def test_cite_formats_and_refuses_unknown_keys() -> None:
    keys = tables.keys_of(_toy())
    assert tables.cite("p = {{t_toy/H1/primary_p}}, n = {{t_toy/H1/n_obs}}", keys) == "p = <0.001, n = 1,500"
    assert tables.cite("{{ t_toy/H1/estimate }} ({{t_toy/H1/verdict}})", keys) == "0.012 (general)"
    assert "t_toy/H2/estimate" not in keys  # empty cells have no key
    with pytest.raises(KeyError):
        tables.cite("{{t_toy/H3/estimate}}", keys)


def test_fmt_rules() -> None:
    assert tables.fmt(0.0004, "b_p") == "<0.001" and tables.fmt(0.04567, "q") == "0.046"
    assert tables.fmt(12.0, "nobs") == "12" and tables.fmt(math.inf, "lambda") == "∞"
    assert tables.fmt(float("nan"), "x") == "—" and tables.fmt(True, "in_family") == "yes"
    assert tables.fmt(0.00012, "kappa") == "1.20e-04"


def test_keys_are_unique_and_latex_has_a_line_per_row() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        tables._frame([{"key": "a"}, {"key": "a"}])
    with pytest.raises(ValueError, match="key column"):
        tables._frame([{"x": 1}])
    tex = tables.to_latex(_toy()).splitlines()
    assert tex[0].startswith("% t_toy") and r"\toprule" in tex and r"\bottomrule" in tex
    body = tex[tex.index(r"\midrule") + 1 : tex.index(r"\bottomrule")]
    assert len(body) == 2 and all(line.endswith(r"\\") for line in body)
    assert r"primary\_p" in tex[tex.index(r"\toprule") + 1]


def test_required_covers_every_pre_registered_test() -> None:
    req = tables.required()
    cfg = spec.load_config()
    assert len(req) == len(set(req))
    assert {f"t1_primary/{t}/verdict" for t in TESTS} <= set(req)
    assert all(f"t5_heterogeneity/{k}:{c}/cut" in req for k in FOCUS for c in cfg.cuts.list)
    assert all(
        f"t6_convergence_ladder/{k}:ladder:{r}/rung" in req for k in FOCUS for r in cfg.convergence.ladder
    )
    for pt in ("D1", "D2"):
        assert all(
            f"t7_gap_closure/{k}:{pt}:all:{r}/rung" in req
            for k in FOCUS
            for r in cfg.convergence.gap[pt].rungs
        )
    assert all(f"t4_secondary/{k}:{t}/test" in req for k in FOCUS for t in tables.SECONDARY_TESTS)
    assert "t16_robustness/not_run:w0_cutoff_09:30/note" in req


@pytest.mark.skipif(not (TABLES_DIR / "keys.json").is_file(), reason="NA-12 tables not written yet")
def test_written_keys_resolve_to_the_csv_cells_and_nothing_is_missing() -> None:
    keys = json.loads((TABLES_DIR / "keys.json").read_text())
    index = json.loads((TABLES_DIR / "index.json").read_text())
    assert tables.missing(keys) == []
    for t in index:
        assert all((TABLES_DIR / f).is_file() for f in t["files"])
        df = pd.read_csv(
            TABLES_DIR / f"{t['name']}.csv", dtype={"key": str}, keep_default_na=False, na_values=[""]
        )
        assert df["key"].is_unique and len(df) == t["rows"]
        cells = df.set_index("key")
        for k, v in keys.items():
            name, row, col = k.split("/", 2)
            if name != t["name"]:
                continue
            got = cells.at[row, col]
            if isinstance(v, int | float) and not isinstance(v, bool):
                assert float(got) == pytest.approx(float(v), rel=1e-9, abs=1e-12), k
            elif v in ("inf", "-inf"):
                assert float(got) == float(v), k
            else:
                assert str(got) == str(v), k
