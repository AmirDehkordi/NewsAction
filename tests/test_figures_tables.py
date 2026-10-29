"""NA-14 S3: the paper tables copy their sources, and their LaTeX is publication-ready (``figures.tables``,
``figures.latex``).

- NA-12's tables are byte-identical copies whose keys equal NA-12's ``keys.json``; the keyed copies equal
  their source cells (NA-13b's with their own key); the flattened tables copy their JSON values;
- the records: the S-CONV / gap-fade overlap reproduces NA-13 REPORT §4, the spend table the ledgers and
  reports, the release dates the NA-05 catalog and the operator's file, the deviations PREREG §15 row by row;
- a DSR states the N it was computed with: NA-13's books the trials in the ledger when NA-13 ran (t20's
  n_trials), NA-13b's books theirs (t39's), not the ledger's current count (t22);
- NA-13b's LaTeX tables are appendix tables that say "Exploratory (post hoc)" and name NA-13b; t38 marks the
  conditions seen on test, t39 has both exits of every book and t37 prints the pre-registered D1 results;
- the LaTeX: at most six main tables; booktabs rules and no vertical rule; threeparttable notes; siunitx
  S columns; a caption above with a label; no raw underscore or internal key in the visible text; every
  number a cited cell of ``keys.json``; the operator's labels on the vendor-label rows, the anchor, span-02;
- the polish pass: an empty cell shows a dash and every table with a dash says in its notes what it means
  (``latex.render`` refuses one that does not); "<" is text set against its number, so the number stays on
  the decimal column; Table 5's share knowable before the open has its column's two decimals;
- no NA-14 key holds "/" or "@", which the cite syntax uses;
- ``docs/paper_outline.md`` maps every table, and every LaTeX table, to the section ``index.json`` records;
- the fix pass after the re-verification: a † or ‡ in a table has its note and no row label repeats within a
  panel (``latex.render`` refuses either); no key with its separators read as spaces is a label (t35); t12
  prints the reading-validity agreement, t4 every CI that stands for an SE, t3 the quintile spread's own $p$,
  t9 both event counts, t10 member-days; t21's and t29's captions state the facts; t20's pages name their
  period.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

from newsaction.figures import keys as kz
from newsaction.figures import latex
from newsaction.figures import sources as sc
from newsaction.figures import tables as tb
from newsaction.paths import ROOT

T = ROOT / sc.TABLES


def _index() -> dict[str, dict[str, object]]:
    return {t["name"]: t for t in json.loads((T / "index.json").read_text(encoding="utf-8"))}


def _latex() -> list[dict[str, object]]:
    out: list[dict[str, object]] = json.loads((ROOT / latex.INDEX).read_text(encoding="utf-8"))
    return out


def test_na12_copies_are_byte_identical_and_keep_na12_keys() -> None:
    keys = kz.load(T / "keys.json")
    na12 = kz.load(ROOT / sc.NA12_TAB / "keys.json")
    copies = [t for t in _index().values() if t["copy_of"]]
    assert len(copies) == 20
    for t in copies:
        assert (T / f"{t['name']}.csv").read_bytes() == (ROOT / str(t["copy_of"])).read_bytes()
        mine = {k: v for k, v in keys.items() if k.startswith(f"{t['name']}/")}
        assert mine == {k: v for k, v in na12.items() if k.startswith(f"{t['name']}/")}


@pytest.mark.parametrize("name,path", [(n, p) for n, p, _ in tb.KEYED])
def test_keyed_copies_equal_their_sources(name: str, path: str) -> None:
    mine = pd.read_csv(T / f"{name}.csv")
    src = pd.read_csv(ROOT / path)
    if "key" in src.columns:  # NA-13b's tables hold their own key, which the copy keeps
        pd.testing.assert_frame_equal(mine, src, check_exact=False, rtol=1e-12)
    else:
        pd.testing.assert_frame_equal(mine.drop(columns=["key"]), src, check_exact=False, rtol=1e-12)
    assert mine["key"].is_unique


def test_flattened_tables_copy_the_json() -> None:
    exp = json.loads((ROOT / tb.EXPLORATORY_JSON).read_text(encoding="utf-8"))
    t24 = pd.read_csv(T / "t24_exploratory_d0_signal.csv").set_index("key")
    want = exp["earnings"]["laya_fin"]["test"]["earnings"]["ic_z_cc"]
    assert t24.loc["earnings:laya_fin:test:earnings", "ic_z_cc"] == pytest.approx(want, rel=1e-12)
    ma = json.loads((ROOT / tb.MA_CROSS_JSON).read_text(encoding="utf-8"))
    t25 = pd.read_csv(T / "t25_ma_cross.csv").set_index("key")
    want = ma["periods"]["test"]["statistics"]["none|5"]["mean_bp"]
    assert t25.loc["periods:test:statistics:none|5", "mean_bp"] == pytest.approx(want, rel=1e-12)
    smoke = json.loads((ROOT / tb.SMOKE_JSON).read_text(encoding="utf-8"))["steps"]["ic_targets"]["result"]
    t32 = pd.read_csv(T / "t32_val_b_ic.csv").set_index("key")
    for key, mid in tb.SMOKE_MODELS:
        for col in ("ic_z_cc", "ic_z_on", "ic_z_id", "ic_z_id_t"):
            assert t32.loc[key, col] == pytest.approx(smoke[mid][col], rel=1e-12)
    t14 = pd.read_csv(T / "t14_model_comparison.csv").set_index("key")
    assert t32.loc["laya_fin", "ic_z_cc"] == pytest.approx(t14.loc["laya_fin", "ic_val_b"], rel=1e-9)


def test_sconv_overlap_reproduces_na13_report() -> None:
    t = pd.read_csv(T / "t26_sconv_overlap.csv").set_index("key")
    report = (ROOT / "artifacts" / "NA-13" / "REPORT.md").read_text(encoding="utf-8")
    assert (
        "92% of its positions" in report and "99.8% on the same side" in report and "correlate 0.96" in report
    )
    row = t.loc["laya_fin:D2:close_t+5"]
    assert round(row["shared_share"], 2) == 0.92 and round(row["same_side_share"], 3) == 0.998
    assert round(row["corr_gross"], 2) == 0.96
    assert round(t.loc["anchor:D2:close_t+5", "corr_gross"], 2) == 0.98


def test_spend_matches_the_ledgers_and_reports() -> None:
    t = pd.read_csv(T / "t22_spend.csv").set_index("key")
    assert round(t.loc["openrouter_total", "value"], 2) == 15.73 and t.loc["openrouter_total", "cap"] == 30.0
    assert t.loc["fmp_requests", "value"] == 15858 and t.loc["fmp_requests", "cap"] == 17000
    assert t.loc["kaggle_na08_gpu_hours", "value"] == 23.38 and t.loc["kaggle_na11_gpu_hours", "value"] == 2.0
    lines = (ROOT / "ledgers" / "trials.jsonl").read_text(encoding="utf-8").count("\n")
    assert t.loc["trials", "value"] == lines  # the ledger now; NA-13's DSRs used the 545 rows it then held
    t20 = pd.read_csv(T / "t20_strategies.csv")
    assert (t20["n_trials"] == 545).all() and lines >= 545


def test_release_dates_follow_the_sample() -> None:
    t = pd.read_csv(T / "t21_release_dates.csv").set_index("key")
    cat = {m["id"]: m for m in json.loads((ROOT / tb.CATALOG).read_text(encoding="utf-8"))["models"]}
    assert t.loc["d1_ultra", "date"] == cat["liquid/d1-ultra"]["created_iso"]
    op = yaml.safe_load((ROOT / tb.OPERATOR).read_text(encoding="utf-8"))
    assert t.loc["laya", "date"] == op["laya_release"]["date"]
    assert "huggingface.co/convaiinnovations/laya" in t.loc["laya", "source"]  # owner decision 2
    for k in ("laya", "drex_v2", "d1_ultra", "span_02"):
        assert t.loc[k, "days_after_sample_end"] > 0
    assert math.isnan(t.loc["anchor", "days_after_sample_end"])


def test_deviations_summary_follows_prereg_15_row_by_row() -> None:
    log = tb.prereg_rows((ROOT / tb.PREREG).read_text(encoding="utf-8"))
    t34 = pd.read_csv(T / "t34_prereg_deviations.csv")
    assert len(t34) == len(log) >= 65
    for r, (_, s) in zip(log, t34.iterrows(), strict=True):
        assert s["date"] == r["date"] and s["freeze"] == r["timing"].split()[0].lower()
    assert set(t34["freeze"]) == {"before", "after"}
    for col, most in tb.SUMMARY_LENGTH.items():
        assert t34[col].astype(str).str.len().max() <= most, col


def test_deviations_summary_refuses_a_missing_or_long_row(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    shutil.copyfile(ROOT / tb.PREREG, tmp_path / tb.PREREG)
    dev = tmp_path / tb.DEVIATIONS
    dev.parent.mkdir(parents=True)
    rows = yaml.safe_load((ROOT / tb.DEVIATIONS).read_text(encoding="utf-8"))["rows"]
    dev.write_text(yaml.safe_dump({"rows": rows[:-1]}), encoding="utf-8")
    with pytest.raises(ValueError, match="summaries for"):
        tb.prereg_deviations(tmp_path)
    rows[0]["change"] = "x" * (tb.SUMMARY_LENGTH["change"] + 1)
    dev.write_text(yaml.safe_dump({"rows": rows}), encoding="utf-8")
    with pytest.raises(ValueError, match="longer than"):
        tb.prereg_deviations(tmp_path)


def test_latex_main_tables_and_style() -> None:
    index = _latex()
    main = [t for t in index if t["section"] == latex.MAIN]
    assert [t["name"] for t in main] == [
        f"tab{i}_{n}"
        for i, n in enumerate(
            ("primary", "ic_by_target", "over_under", "convergence", "explaining_moves", "strategies"),
            start=1,
        )
    ]
    keys = kz.load(T / "keys.json")
    for t in index:
        tex = (T / str(t["file"])).read_text(encoding="utf-8")
        body = "\n".join(ln for ln in tex.splitlines() if not ln.lstrip().startswith("%"))
        specs = re.findall(r"\\begin\{(?:tabular|longtable)\}\{(.*)\}\s*$", body, flags=re.MULTILINE)
        assert specs and "|" not in specs[0], t["name"]
        assert (
            r"\toprule" in body and r"\midrule" in body and r"\bottomrule" in body and r"\hline" not in body
        )
        assert body.index(r"\caption{") < body.index(r"\toprule") and r"\label{tab:" in body
        visible = re.sub(r"\$[^$]*\$", " ", body)  # notation is math; outside it no underscore prints
        assert "_" not in visible, t["name"]
        for k in ("laya_fin", "d1_ultra", "ic_z_cc", "a2_v", "close_t+5", "n_tilde"):
            assert k not in visible, (t["name"], k)
        # nor a key with its separators read as spaces (t35's labels were "S-CONV, laya fin, D2, u, …")
        for k in ("laya fin", "d1 ultra", "laya zs", "n tilde", "span 02", "drex v2", "close t+", ", -,"):
            assert k not in visible, (t["name"], k)
        assert t["cells"] and all(c in keys for c in t["cells"]), t["name"]
        if t["section"] == latex.MAIN:
            assert (
                r"\begin{threeparttable}" in body
                and r"\begin{tablenotes}" in body
                and "S[table-format=" in body
            )


def test_latex_carries_the_operator_labels() -> None:
    t14 = (T / "t14_model_comparison.tex").read_text(encoding="utf-8")
    assert r"vendor sentiment$^{\dagger}$" in t14 and "look-ahead-contaminated upper bound" in t14
    assert "near-constant outputs" in t14 and r"span-02$^{\ddagger}$" in t14 and "S5" in t14
    assert "Exploratory (post hoc)" in (T / "t17_sector_exploratory.tex").read_text(encoding="utf-8")
    assert r"$\hat{N}$" in latex.tex("N̂_W0") and latex.tex("a_b & 50%") == r"a\_b \& 50\%"
    assert latex.tex("$z_{cc}$ and −1") == "$z_{cc}$ and $-$1"
    with pytest.raises(ValueError):
        latex.tex("€")


def test_empty_cells_show_a_dash_that_the_notes_explain() -> None:
    blank = re.compile(r"&\s*\{\}\s*(?=&|\\\\)")
    for t in _latex():
        tex = (T / str(t["file"])).read_text(encoding="utf-8")
        body = "\n".join(ln for ln in tex.splitlines() if not ln.lstrip().startswith("%"))
        table, _, notes = body.partition(r"\bottomrule")
        assert not blank.search(table), t["name"]
        if "{---}" in table or "& --- " in table:
            assert "---" in notes, t["name"]
    toy = latex.Table(
        "toy",
        "tab:toy",
        latex.APPENDIX,
        "A toy.",
        (latex.Col("Row", "l"), latex.Col("Value")),
        (latex.Panel("", (("a", (None,)),)),),
        ("No word on the dash.",),
    )
    with pytest.raises(ValueError, match="no note says"):
        latex.render(toy, {})
    explained = latex.Table(**{**toy.__dict__, "notes": ("---: not computed.",)})
    assert r"a & {---} \\" in latex.render(explained, {})[0]


def test_a_bound_sits_against_its_number() -> None:
    cells = latex.Cells({"t/k/p": 0.0004, "t/k/q": 0.02})
    assert (
        cells.num(latex.Num("t", "k", "p", "p")) == "{$<$}0.001"
        and cells.num(latex.Num("t", "k", "q", "p")) == "0.020"
    )
    assert cells.render(latex.Num("t", "k", "p", "p"), "c") == "$<0.001$"
    assert (
        latex.table_format(["0.020", "{$<$}0.001", "{---}"])
        == "S[table-format=1.3, table-space-text-pre={$<$}]"
    )
    for t in _latex():
        tex = (T / str(t["file"])).read_text(encoding="utf-8")
        assert not re.search(r"&\s*<", tex), t["name"]  # no bare comparator in an S column
    tab5 = (T / "tab5_explaining_moves.tex").read_text(encoding="utf-8")
    share = next(ln for ln in tab5.splitlines() if ln.startswith("share knowable"))
    assert re.fullmatch(
        r"share knowable before the open \(\\%\) & \d+\.\d\d & \{---\} & \d+\.\d\d & .*", share
    ), share


def test_a_mark_needs_its_note_and_a_label_appears_once_in_a_panel() -> None:
    toy = latex.Table(
        "toy",
        "tab:toy",
        latex.APPENDIX,
        "A toy.",
        (latex.Col("Row", "l"), latex.Col("Value")),
        (latex.Panel("", ((r"vendor sentiment$^{\dagger}$", (latex.Txt("1"),)),)),),
        ("No word on the mark.",),
    )
    with pytest.raises(ValueError, match="no note says what it marks"):
        latex.render(toy, {})
    assert latex.render(latex.Table(**{**toy.__dict__, "notes": (latex.NOTE_VENDOR_BOOKS,)}), {})
    twice = latex.Table(
        **{**toy.__dict__, "panels": (latex.Panel("", (("a", (latex.Txt("1"),)), ("a", (latex.Txt("2"),)))),)}
    )
    with pytest.raises(ValueError, match="repeats within a panel"):
        latex.render(twice, {})
    for t in _latex():  # what the guards hold, checked on the committed LaTeX too
        tex = (T / str(t["file"])).read_text(encoding="utf-8")
        if r"\begin{longtable}" in tex:  # a longtable's \bottomrule is its foot, set before the rows
            table, _, notes = tex.rpartition(r"\end{longtable}")
        else:
            table, _, notes = tex.partition(r"\bottomrule")
        for mark in (r"$^{\dagger}$", r"$^{\ddagger}$"):
            if mark in table:
                assert mark in notes, (t["name"], mark)


def test_a_value_that_rounds_to_zero_shows_no_sign() -> None:
    cells = latex.Cells({"t/k/tiny": -0.00004, "t/k/neg": -0.0016, "t/k/hi": 0.1})
    assert cells.num(latex.Num("t", "k", "tiny", "f3")) == "0.000"
    assert cells.num(latex.Num("t", "k", "tiny", "se3")) == "{(}0.000{)}"
    assert cells.num(latex.Num("t", "k", "tiny", "pct1")) == "0.0"
    assert cells.num(latex.Num("t", "k", "neg", "f3")) == "-0.002"  # not zero once rounded: keeps its sign
    assert cells.ci(latex.CI("t", "k", "tiny", "hi", 3)) == "[$0.000$, $0.100$]"
    toy = latex.Table(
        "toy",
        "tab:toy",
        latex.APPENDIX,
        "A toy.",
        (latex.Col("Row", "l"), latex.Col("Value")),
        (latex.Panel("", (("a", (latex.Txt("-0.00"),)),)),),
        ("A note.",),
    )
    with pytest.raises(ValueError, match="negative zero"):
        latex.render(toy, {})
    for t in _latex():  # and none in the committed LaTeX
        table = (T / str(t["file"])).read_text(encoding="utf-8").partition(r"\begin{tablenotes}")[0]
        assert not latex.NEGATIVE_ZERO.search(table), (t["name"], latex.NEGATIVE_ZERO.findall(table))


def test_the_reverification_fixes() -> None:
    keys = kz.load(T / "keys.json")

    def tex(name: str) -> str:
        return (T / f"{name}.tex").read_text(encoding="utf-8")

    t12 = tex("t12_question_battery")
    for item in ("credibility", "event_type", "event_type_vs_raw_tag", "quantified", "scheduled"):
        v = keys[f"t12_question_battery/reading:liquid_d1-ultra:{item}/agreement"]
        row = next(ln for ln in t12.splitlines() if f"): {item.replace('_', ' ')} &" in ln)
        assert f" & {v:.3f} & 500 " in row, row
    t4 = pd.read_csv(T / "t4_secondary.csv", keep_default_na=False, na_values=[""])
    with_ci = t4[t4["se"].isna() & t4["ci_low"].notna()]
    assert len(with_ci) >= 3 and all(
        f"[${r.ci_low:.4f}$, ${r.ci_high:.4f}$]" in tex("t4_secondary") for r in with_ci.itertuples()
    )
    assert r"\multicolumn{2}{c}{Quintile spread}" in tex("t3_ic")
    assert r"{Events ($\kappa$)} & {Events ($\lambda$)}" in tex("t9_convergence_cuts")
    assert "{Member-days}" in tex("t10_explanation_ladder") and "{Days}" not in tex("t10_explanation_ladder")
    assert "only the anchor's checkpoint predates it" in tex("t21_release_dates")
    assert "(created)" not in tex("t21_release_dates")
    t29 = pd.read_csv(T / "t29_encoding.csv")
    val_a = t29[(t29["split"] == "val_a") & (t29["model"] == "pooled")].set_index("encoding")["rank"]
    assert val_a.idxmin() == "E1" and "E1 ranked best in the val-A search" in tex("t29_encoding")
    t20 = tex("t20_strategies")
    assert t20.count(r"\begin{longtable}") == 2 and t20.count(r"\caption{") == 1
    assert "continued (test)" in t20 and "continued (val-B)" in t20
    assert "S-CONV, Laya-Fin, D2 $U$, to $t{+}1$ &" in tex("t35_break_even")


def test_no_key_holds_the_cite_separators() -> None:
    for name, t in _index().items():
        if t["copy_of"]:
            continue
        keys = pd.read_csv(T / f"{name}.csv", usecols=["key"])["key"].astype(str)
        assert not keys.str.contains("/|@", regex=True).any(), name


def test_the_outline_maps_every_table_to_its_section() -> None:
    outline = (ROOT / "docs" / "paper_outline.md").read_text(encoding="utf-8")
    listed = dict(re.findall(r"^\| `([a-z0-9_]+)` \| ([^|]+?) \|", outline, flags=re.MULTILINE))
    csvs = {name: str(t["section"]) for name, t in _index().items()}
    assert {k: v for k, v in listed.items() if k in csvs} == csvs
    assert set(tb.SECTION) == set(csvs)
    for t in _latex():
        assert f"`{t['file']}`" in outline, t["file"]


def test_a_dsr_states_the_n_it_was_computed_with() -> None:
    cited = {t["name"]: t["cells"] for t in _latex()}
    n13 = "t20_strategies/test|S-CONV|laya_fin|D2|u|close_t+5|all/n_trials"
    for name in ("tab6_strategies", "t20_strategies"):
        assert n13 in cited[name] and "t22_spend/trials/value" not in cited[name], name
    caps = (ROOT / "artifacts" / "NA-14" / "captions.yaml").read_text(encoding="utf-8")
    assert "t22_spend/trials/value" not in caps and f"{{{{{n13}@int}}}}" in caps
    t39 = pd.read_csv(T / "t39_conditioning_books.csv")
    assert t39["n_trials"].nunique() == 1
    assert [c for c in cited["t39_conditioning_books"] if c.endswith("/n_trials")]


def test_na13b_latex_tables() -> None:
    tables = {t["name"]: t for t in _latex()}
    na13b = ("t36_selective_coverage", "t37_watch_open", "t38_conditioning", "t39_conditioning_books")
    for name in (*na13b, "t43_band_disclosure"):
        tex = (T / f"{name}.tex").read_text(encoding="utf-8")
        assert tables[name]["section"] == latex.APPENDIX, name
        assert r"\caption{Exploratory (post hoc):" in tex and "NA-13b" in tex, name
    t38 = pd.read_csv(T / "t38_conditioning.csv")
    tex = (T / "t38_conditioning.tex").read_text(encoding="utf-8")
    assert tex.count("[seen on test]") == int(t38["seen_on_test"].sum()) + 1  # the rows and their note
    assert tex.count("& yes &") == int(t38["selected"].sum())
    t39 = pd.read_csv(T / "t39_conditioning_books.csv")
    tex = (T / "t39_conditioning_books.tex").read_text(encoding="utf-8")
    assert tex.count("& $C_t$ &") == tex.count("& $t{+}1$ &") == len(t39) // 2
    b = [c for c in tables["t37_watch_open"]["cells"] if not c.startswith("t37_watch_open/")]
    assert len(b) == 12 and {c.split("/", 1)[0] for c in b} == {
        "t2_h2_over_under",
        "t6_convergence_ladder",
        "t7_gap_closure",
        "t20_strategies",
    }
