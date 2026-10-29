"""NA-14 S3: the paper tables copy their sources and carry the operator's labels (``figures.tables``).

- NA-12's tables are byte-identical copies whose keys equal NA-12's ``keys.json``; the keyed copies equal
  their
  source cells; the flattened tables copy their JSON values;
- the records: the S-CONV / gap-fade overlap reproduces NA-13 REPORT §4, the spend table the ledgers and
  reports,
  the release dates the NA-05 catalog and the operator's file, all after the sample;
- the LaTeX marks the vendor-label baselines, the anchor and span-02, says when a table is exploratory, and
  refuses a character it cannot write;
- no NA-14 key holds "/" or "@", which the cite syntax uses.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest
import yaml

from newsaction.figures import keys as kz
from newsaction.figures import sources as sc
from newsaction.figures import tables as tb
from newsaction.paths import ROOT

T = ROOT / sc.TABLES


def _index() -> dict[str, dict[str, object]]:
    return {t["name"]: t for t in json.loads((T / "index.json").read_text(encoding="utf-8"))}


def test_na12_copies_are_byte_identical_and_keep_na12_keys() -> None:
    keys = kz.load(T / "keys.json")
    na12 = kz.load(ROOT / sc.NA12_TAB / "keys.json")
    copies = [t for t in _index().values() if t["copy_of"]]
    assert len(copies) == 20
    for t in copies:
        assert (T / f"{t['name']}.csv").read_bytes() == (ROOT / str(t["copy_of"])).read_bytes()
        mine = {k: v for k, v in keys.items() if k.startswith(f"{t['name']}/")}
        assert mine == {k: v for k, v in na12.items() if k.startswith(f"{t['name']}/")}


@pytest.mark.parametrize("name,path", [(n, p) for n, p, _, _ in tb.KEYED])
def test_keyed_copies_equal_their_sources(name: str, path: str) -> None:
    mine = pd.read_csv(T / f"{name}.csv")
    src = pd.read_csv(ROOT / path)
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
    assert t.loc["trials", "value"] == lines == 545


def test_release_dates_follow_the_sample() -> None:
    t = pd.read_csv(T / "t21_release_dates.csv").set_index("key")
    cat = {m["id"]: m for m in json.loads((ROOT / tb.CATALOG).read_text(encoding="utf-8"))["models"]}
    assert t.loc["d1_ultra", "date"] == cat["liquid/d1-ultra"]["created_iso"]
    op = yaml.safe_load((ROOT / tb.OPERATOR).read_text(encoding="utf-8"))
    assert t.loc["laya", "date"] == op["laya_release"]["date"]
    for k in ("laya", "drex_v2", "d1_ultra", "span_02"):
        assert t.loc[k, "days_after_sample_end"] > 0
    assert math.isnan(t.loc["anchor", "days_after_sample_end"])


def test_latex_carries_the_operator_labels() -> None:
    t14 = (T / "t14_model_comparison.tex").read_text(encoding="utf-8")
    assert r"vendor sentiment\textsuperscript{\dag}" in t14 and "look-ahead-contaminated upper bound" in t14
    assert "anchor (uninformative)" in t14 and "near-constant outputs" in t14
    assert r"span-02\textsuperscript{\ddag}" in t14 and "S5" in t14
    assert "Exploratory (post hoc)" in (T / "t17_sector_exploratory.tex").read_text(encoding="utf-8")
    assert r"\^{N}" in tb.tex_text("N̂_W0") and tb.tex_text("a_b & 50%") == r"a\_b \& 50\%"
    with pytest.raises(ValueError):
        tb.tex_text("€")


def test_no_key_holds_the_cite_separators() -> None:
    for name, t in _index().items():
        if t["copy_of"]:
            continue
        keys = pd.read_csv(T / f"{name}.csv", usecols=["key"])["key"].astype(str)
        assert not keys.str.contains("/|@", regex=True).any(), name
