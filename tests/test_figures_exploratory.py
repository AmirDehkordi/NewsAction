"""NA-14 operator check 5e: exploratory material appears only in the appendix (``figures.guard``).

- no main figure (1–7) and no main table (T1–T6) cites exploratory material: not in a caption, not in a
  cell of its LaTeX, not in a row of its CSV; ``make paper`` refuses one that does;
- the guard is not vacuous: Figure 4's old month-effect sentence (t24) planted in a main caption, a t24 cell
  planted in a main table, and a t24 row planted in a main figure's data are each caught;
- the index marks every exploratory table and row, including any row whose own text calls it exploratory;
- the CSVs keep their exploratory rows, the appendix shows them (A15 and t25 for NA-13's MA-cross fade, t31
  for NA-12's A3.5 market replication), and the appendix LaTeX of t11 and t20 points there;
- the documents state the rule as it holds: exploratory material appears only in the appendix.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
import pytest

from newsaction.figures import captions, guard, latex, render
from newsaction.figures import sources as sc
from newsaction.paths import ROOT

T = ROOT / sc.TABLES
WORD = re.compile(r"\bexploratory\b", re.IGNORECASE)
TABLES = {"t17_sector_exploratory", "t24_exploratory_d0_signal", "t25_ma_cross", "t31_market_replication"}
FADE = "test|exploratory|ma_cross|fade_no_news|close_t+5"
ROWS = {
    ("t11_explanation_share_theta", "market:r2"),
    ("t20_strategies", FADE),
    ("t20_strategies", "validation|exploratory|ma_cross|fade_no_news|close_t+5"),
}
MONTH_EFFECT = (
    "A one-way test of the daily ICs on the calendar month finds no month effect "
    "(test p {{t24_exploratory_d0_signal/monthly:laya_fin:test/p@f2}} for Laya-Fin and "
    "{{t24_exploratory_d0_signal/monthly:d1_ultra:test/p@f2}} for d1-ultra)."
)


def _index() -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in json.loads((T / "index.json").read_text(encoding="utf-8"))}


def _latex() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = json.loads((ROOT / latex.INDEX).read_text(encoding="utf-8"))
    return out


def _worded(name: str) -> set[str]:
    """The keys of the rows whose own text says "exploratory" (read without the index)."""
    df = pd.read_csv(T / f"{name}.csv", dtype=str, keep_default_na=False)
    text = df.drop(columns=["key"]).agg(" ".join, axis=1)
    return set(df.loc[text.str.contains(WORD), "key"])


def test_no_main_figure_or_table_cites_exploratory_material() -> None:
    assert guard.violations() == []
    main = [t for t in _latex() if t["section"] == latex.MAIN]
    assert len(main) == 6
    for t in main:
        assert not {c.split("/", 1)[0] for c in t["cells"]} & TABLES, t["name"]


def test_a_planted_month_effect_sentence_is_caught() -> None:
    caps = captions.load()
    caps["fig2_priced_at_open"] = {
        **caps["fig2_priced_at_open"],
        "caption": f"{caps['fig2_priced_at_open']['caption']} {MONTH_EFFECT}",
    }
    bad = guard.violations(caps=caps)
    assert len(bad) == 2 and all(b.startswith("fig2_priced_at_open caption: t24_") for b in bad)
    found = [b for b in captions.check(captions=caps) if "only the appendix may cite" in b]
    assert len(found) == 2


def test_a_planted_exploratory_cell_in_a_main_table_is_caught() -> None:
    index = _latex()
    for t in index:
        if t["name"] == "tab2_ic_by_target":
            t["cells"] = [*t["cells"], "t24_exploratory_d0_signal/monthly:laya_fin:test/p"]
    bad = guard.violations(tex_index=index)
    assert bad == ["tab2_ic_by_target cell: t24_exploratory_d0_signal/monthly:laya_fin:test/p"]
    for t in index:
        if t["name"] == "tab6_strategies":
            t["cells"] = [*t["cells"], f"t20_strategies/{FADE}/sharpe_net_10"]
    assert len(guard.violations(tex_index=index)) == 2


def test_a_planted_exploratory_row_in_a_main_figure_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    real = render.read

    def read(name: str, layout: Any = None) -> pd.DataFrame:
        df = real(name, layout)
        if name == "fig1_validation_test":
            extra = df.iloc[[0]].copy()
            extra["source"], extra["key"] = f"{sc.TABLES}/t24_exploratory_d0_signal.csv", "company:laya_fin"
            df = pd.concat([df, extra], ignore_index=True)
        return df

    monkeypatch.setattr(render, "read", read)
    assert guard.violations() == ["fig1_validation_test data: t24_exploratory_d0_signal/company:laya_fin"]


def test_the_index_marks_every_exploratory_table_and_row() -> None:
    index = _index()
    assert {n for n, t in index.items() if t["exploratory"]} == TABLES
    assert {(n, k) for n, t in index.items() for k in t["exploratory_rows"]} == ROWS
    for name in sorted(n for n in set(index) - TABLES if index[n]["section"] != "appendix"):
        assert {(name, k) for k in _worded(name)} <= ROWS, name
    assert {index[n]["section"] for n in TABLES} == {"appendix"}


def test_the_csv_keeps_the_rows_and_the_appendix_shows_them() -> None:
    t20 = pd.read_csv(T / "t20_strategies.csv").set_index("key")
    assert t20.loc[FADE, "family"] == "exploratory"
    a15 = render.read("figA15_exploratory_ma_cross")
    assert (a15["key"].str.startswith(FADE.split("|", 1)[1]) & (a15["source"] == sc.FIG7)).any()
    t11 = pd.read_csv(T / "t11_explanation_share_theta.csv").set_index("key").loc["market:r2"]
    t31 = pd.read_csv(T / "t31_market_replication.csv").set_index("key").loc["market:r2"]
    assert t31["source"] == f"{sc.NA12_TAB}/t11_explanation_share_theta.csv (row market:r2)"
    cells = t31.drop("source")
    assert len(cells) >= 6 and all(cells[c] == t11[c] for c in cells.index)
    cited = {t["name"]: t["cells"] for t in _latex()}
    assert not [c for c in cited["t11_explanation_share_theta"] if "/market:r2/" in c]
    assert not [c for c in cited["t20_strategies"] if "|exploratory|" in c]
    assert r"\ref{tab:a-market-replication}" in (T / "t11_explanation_share_theta.tex").read_text(
        encoding="utf-8"
    )
    assert r"\ref{tab:a-ma-cross} and Figure A15" in (T / "t20_strategies.tex").read_text(encoding="utf-8")


def test_the_rule_is_stated_as_it_holds() -> None:
    for doc in ("docs/paper_outline.md", "docs/decisions/NA-14.md", "artifacts/NA-14/REPORT.md"):
        text = " ".join((ROOT / doc).read_text(encoding="utf-8").split())
        assert "Exploratory material appears only in the appendix" in text, doc
        assert "exploratory only in A6 and A7" not in text, doc
