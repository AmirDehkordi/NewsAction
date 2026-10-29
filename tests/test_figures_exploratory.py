"""NA-14 operator check 5e: exploratory material appears only in the appendix (``figures.guard``).

- no main figure (1–7) and no main table (T1–T6) cites exploratory material: not in a caption, not in a
  cell of its LaTeX, not in a row of its CSV; ``make paper`` refuses one that does;
- the guard is not vacuous: Figure 4's old month-effect sentence (t24) planted in a main caption, a t24 cell
  planted in a main table, and a t24 row planted in a main figure's data are each caught; so are NA-13's
  MA-cross fade cited through t35, its path from the Figure 7 data and NA-12's market row from NA-12's own t11
  planted in a main figure's data (the re-verification found these three routes open), and so is a row of
  NA-13b's own tables (exploratory as a whole) planted in a main figure's data;
- the index marks every exploratory table and row, including any row whose own text or key calls it
  exploratory;
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
NA13B = {
    "t36_selective_coverage",
    "t37_watch_open",
    "t38_conditioning",
    "t39_conditioning_books",
    "t40_conditioning_detail",
    "t41_output_histograms",
    "t42_output_summary",
    "t43_band_disclosure",
}
TABLES = {
    "t17_sector_exploratory",
    "t24_exploratory_d0_signal",
    "t25_ma_cross",
    "t31_market_replication",
    *NA13B,
}
FADE = "test|exploratory|ma_cross|fade_no_news|close_t+5"
ROWS = {
    ("t11_explanation_share_theta", "market:r2"),
    ("t20_strategies", FADE),
    ("t20_strategies", "validation|exploratory|ma_cross|fade_no_news|close_t+5"),
    ("t35_break_even", FADE.split("|", 1)[1]),
    # NA-16: the conditioning study's counts the paper cites (exploratory, post hoc)
    ("t30_derived", "conditioning:pairs"),
    ("t30_derived", "conditioning:selected"),
    ("t30_derived", "conditioning:selected_reversed"),
    ("t30_derived", "conditioning:selected_positive"),
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
    """The keys of the rows whose own text or key says "exploratory" (read without the index)."""
    df = pd.read_csv(T / f"{name}.csv", dtype=str, keep_default_na=False)
    text = df.agg(" ".join, axis=1)
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


def test_the_ma_cross_fade_cited_through_t35_is_caught() -> None:
    caps = captions.load()
    cite = f"{{{{t35_break_even/{FADE.split('|', 1)[1]}/break_even_bp@f1}}}}"
    caps["fig6_strategies"] = {
        **caps["fig6_strategies"],
        "caption": f"{caps['fig6_strategies']['caption']} The MA-cross fade breaks even at {cite} bp.",
    }
    assert guard.violations(caps=caps) == [
        f"fig6_strategies caption: t35_break_even/{FADE.split('|', 1)[1]}/break_even_bp"
    ]
    assert [b for b in captions.check(captions=caps) if "only the appendix may cite" in b]


def test_upstream_exploratory_rows_in_a_main_figure_are_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    real = render.read

    paths = real("fig6_strategies")
    session = str(paths.loc[paths["source"] == sc.FIG7, "key"].iloc[0]).rsplit("|", 1)[1]
    fade_path = f"{FADE.split('|', 1)[1]}|all|{session}"  # NA-13's MA-cross path on a real session

    def read(name: str, layout: Any = None) -> pd.DataFrame:
        df = real(name, layout)
        if name == "fig6_strategies":
            extra = df.iloc[[0, 0]].copy()
            extra["source"] = [sc.FIG7, f"{sc.NA12_TAB}/t11_explanation_share_theta.csv"]
            extra["key"] = [fade_path, "market:r2"]
            df = pd.concat([df, extra], ignore_index=True)
        return df

    monkeypatch.setattr(render, "read", read)
    assert guard.violations() == [
        f"fig6_strategies data: {sc.FIG7}/{fade_path}",
        "fig6_strategies data: t11_explanation_share_theta/market:r2",
    ]


def test_na13b_rows_in_a_main_figure_are_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    real = render.read

    def read(name: str, layout: Any = None) -> pd.DataFrame:
        df = real(name, layout)
        if name == "fig2_priced_at_open":
            extra = df.iloc[[0, 0]].copy()
            extra["source"] = [sc.COVERAGE, f"{sc.TABLES}/t36_selective_coverage.csv"]
            extra["key"] = "laya_fin|conviction|0.1|test|z_id"
            df = pd.concat([df, extra], ignore_index=True)
        return df

    monkeypatch.setattr(render, "read", read)
    assert guard.violations() == [
        f"fig2_priced_at_open data: {sc.COVERAGE}/laya_fin|conviction|0.1|test|z_id",
        "fig2_priced_at_open data: t36_selective_coverage/laya_fin|conviction|0.1|test|z_id",
    ]


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
    t35 = pd.read_csv(T / "t35_break_even.csv").set_index("key")
    assert FADE.split("|", 1)[1] in t35.index  # the CSV keeps NA-13's row
    cited = {t["name"]: t["cells"] for t in _latex()}
    assert not [c for c in cited["t11_explanation_share_theta"] if "/market:r2/" in c]
    assert not [c for c in cited["t20_strategies"] if "|exploratory|" in c]
    assert not [c for c in cited["t35_break_even"] if "/exploratory|" in c]
    assert r"\ref{tab:a-ma-cross} and Figure A15" in (T / "t35_break_even.tex").read_text(encoding="utf-8")
    assert r"\ref{tab:a-market-replication}" in (T / "t11_explanation_share_theta.tex").read_text(
        encoding="utf-8"
    )
    assert r"\ref{tab:a-ma-cross} and Figure A15" in (T / "t20_strategies.tex").read_text(encoding="utf-8")


def test_the_rule_is_stated_as_it_holds() -> None:
    for doc in ("docs/paper_outline.md", "docs/decisions/NA-14.md", "artifacts/NA-14/REPORT.md"):
        text = " ".join((ROOT / doc).read_text(encoding="utf-8").split())
        assert "Exploratory material appears only in the appendix" in text, doc
        assert "exploratory only in A6 and A7" not in text, doc
