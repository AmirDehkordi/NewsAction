"""NA-13b (e): the conditioning statistics, the operator's selection rule and the test family, on toy data."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from newsaction.selective import conditioning as cg
from newsaction.selective import conditions as cd
from newsaction.selective import run as rn

D = [date(2025, 7, 9), date(2025, 7, 10), date(2025, 7, 11)]


def toy() -> pd.DataFrame:
    """Three sessions, four events each; y = sign(N̂)·z_id is z_id here (N̂ > 0)."""
    rows = []
    z = {D[0]: [1.0, 0.0, -1.0, 2.0], D[1]: [0.5, 0.5, 0.0, 1.5], D[2]: [-1.0, 3.0, 1.0, 0.0]}
    for d in D:
        for i, v in enumerate(z[d]):
            rows.append({"session": d, "split": "val_a", "embargo": False, "n_laya_fin": 0.1, "z_id": v,
                         "inside": float(i < 2)})  # fmt: skip
    return pd.DataFrame(rows)


def test_event_level_difference_is_the_mean_of_daily_differences() -> None:
    f = cg.frame_for(toy(), "laya_fin", "z_id")
    rec, diff = cg.split_stats(f, cd.BY_KEY["e2_numbers"], f["inside"], {})
    daily = [np.mean([1.0, 0.0]) - np.mean([-1.0, 2.0]), 0.5 - 0.75, 1.0 - 0.5]
    assert list(diff) == pytest.approx(daily)
    assert rec["diff"] == pytest.approx(np.mean(daily))
    assert rec["diff_t"] == pytest.approx(np.mean(daily) / (np.std(daily, ddof=1) / math.sqrt(3)))
    assert rec["inside"] == pytest.approx(np.mean([0.5, 0.5, 1.0]))
    assert rec["n_in"] == 6 and rec["n_out"] == 6 and rec["days_in"] == 3


def test_day_level_compares_session_means_with_welch() -> None:
    f = cg.frame_for(toy(), "laya_fin", "z_id")
    flag = pd.Series(np.where(f["session"] == D[1], 1.0, 0.0), index=f.index)
    days = f.groupby("session")["y"].mean()
    rec, (a, b) = cg.split_stats(f, cd.BY_KEY["e4_friday"], flag, {})
    assert list(a) == [days[D[1]]] and list(b) == [days[D[0]], days[D[2]]]
    assert rec["diff"] == pytest.approx(days[D[1]] - np.mean([days[D[0]], days[D[2]]]))
    assert math.isnan(rec["diff_t"])  # one inside session: Welch needs two
    extra = toy().iloc[:4].assign(session=date(2025, 7, 14), z_id=[0.0, 1.0, 1.0, 2.0])
    g = cg.frame_for(pd.concat([toy(), extra], ignore_index=True), "laya_fin", "z_id")
    two = pd.Series(np.where(g["session"].isin([D[0], D[1]]), 1.0, 0.0), index=g.index)
    rec2, _ = cg.split_stats(g, cd.BY_KEY["e4_friday"], two, {})
    m = g.groupby("session")["y"].mean()
    r = stats.ttest_ind(m[[D[0], D[1]]], m[[D[2], date(2025, 7, 14)]], equal_var=False)
    assert rec2["diff_t"] == pytest.approx(float(r.statistic)) and rec2["diff_p"] == pytest.approx(
        float(r.pvalue)
    )


def test_a_missing_input_counts_as_outside() -> None:
    f = pd.DataFrame({"attention_ratio": [2.0, np.nan, 1.0], "n_laya_fin": [0.1, 0.1, 0.1]})
    got = cd.event_inside(
        f, "laya_fin", cd.BY_KEY["e4_busy_event"], {f"median_{c}": 0.0 for c in cd.EVENT_MEDIANS}
    )
    assert list(got) == [1.0, 0.0, 0.0]


def test_the_timing_comparison_leaves_out_earlier_articles() -> None:
    f = pd.DataFrame({"latest_et": [-30.0, 239.0, 240.0, 479.0, 480.0, 555.0], "n_laya_fin": 0.1})
    got = cd.event_inside(f, "laya_fin", cd.BY_KEY["e3_0400_0800"], {})
    assert got.isna().tolist() == [True, True, False, False, False, False]
    assert got.dropna().tolist() == [1.0, 1.0, 0.0, 0.0]


def _val(rows: list[tuple[str, str, str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"model": m, "condition": k, "split": s, "outcome": cg.PRIMARY, "diff": d, "diff_t": t}
         for m, k, s, d, t in rows]
    )  # fmt: skip


def test_the_selection_rule() -> None:
    conds = [cd.BY_KEY[k] for k in ("e2_numbers", "e2_material", "e2_new", "e1_earnings", "e7_api3")]
    val = _val(
        [
            ("laya_fin", "e2_numbers", "val_a", 0.06, 1.0), ("laya_fin", "e2_numbers", "val_b", 0.1, 1.2),
            ("laya_fin", "e2_numbers", "val_pooled", 0.08, 2.0),
            ("laya_fin", "e2_material", "val_a", 0.06, 0.99), ("laya_fin", "e2_material", "val_b", 0.1, 3.0),
            ("laya_fin", "e2_material", "val_pooled", 0.08, 3.0),
            ("laya_fin", "e2_new", "val_a", 0.06, 1.5), ("laya_fin", "e2_new", "val_b", 0.1, 1.5),
            ("laya_fin", "e2_new", "val_pooled", 0.08, 1.99),
            ("laya_fin", "e1_earnings", "val_a", 0.3, 5.0), ("laya_fin", "e1_earnings", "val_b", 0.3, 5.0),
            ("laya_fin", "e1_earnings", "val_pooled", 0.3, 7.0),
            ("laya_fin", "e7_api3", "val_b", 0.1, 2.5), ("d1_ultra", "e7_api3", "val_b", 0.1, 2.49),
        ]
    )  # fmt: skip
    sel = cg.select(val, conds).set_index(["model", "condition"])["selected"]
    assert sel[("laya_fin", "e2_numbers")]  # t >= 1 in both, pooled >= 2
    assert not sel[("laya_fin", "e2_material")]  # val-A t below 1
    assert not sel[("laya_fin", "e2_new")]  # pooled t below 2
    assert not sel[("laya_fin", "e1_earnings")]  # seen on test: never selected
    assert sel[("laya_fin", "e7_api3")] and not sel[("d1_ultra", "e7_api3")]  # val-B alone, t >= 2.5


def test_negative_differences_are_never_selected() -> None:
    val = _val([("laya_fin", "e2_numbers", s, -0.1, 5.0) for s in ("val_a", "val_b", "val_pooled")])
    assert not cg.select(val, [cd.BY_KEY["e2_numbers"]])["selected"].any()


def test_the_test_family_takes_benjamini_hochberg_over_every_pair() -> None:
    test = pd.DataFrame(
        {"model": ["laya_fin"] * 4, "condition": ["a", "b", "c", "s"], "outcome": cg.PRIMARY, "split": "test",
         "diff": [0.1, -0.2, 0.05, 0.3], "diff_p": [0.01, 0.02, 0.5, 0.001],
         "seen_on_test": [False, False, False, True]}
    )  # fmt: skip
    sel = pd.DataFrame(
        {"model": ["laya_fin"] * 4, "condition": ["a", "b", "c", "s"], "selected": [True, True, False, False]}
    )
    fam = cg.family_on_test(test, sel).set_index("condition")
    assert fam["bh_q"].tolist() == pytest.approx([0.02, 0.0266667, 0.5, 0.004], rel=1e-4)
    assert fam["bh_q_unseen"].iloc[:3].tolist() == pytest.approx([0.03, 0.03, 0.5])  # without the seen one
    assert math.isnan(fam.at["s", "bh_q_unseen"])
    assert fam["confirmed"].tolist() == [True, False, False, False]  # b's sign is wrong; c, s not selected


def test_a_missing_model_reading_puts_the_event_in_neither_group() -> None:
    f = pd.DataFrame(
        {"n_laya_fin": [0.1, 0.1, -0.1, 0.1], "n_d1_ultra": [0.2, np.nan, 0.3, 0.4],
         "a0_label_quantified": ["numbers", None, "numbers", "narrative"]}
    )  # fmt: skip
    agree = cd.event_inside(f, "laya_fin", cd.BY_KEY["e7_agree"], {})
    assert agree.isna().tolist() == [False, True, False, False] and agree.dropna().tolist() == [1.0, 0.0, 1.0]
    numbers = cd.event_inside(f, "laya_fin", cd.BY_KEY["e2_numbers"], {})
    assert numbers.isna().tolist() == [False, True, False, False]


def test_at_most_three_candidates_ranked_by_validation() -> None:
    fam = pd.DataFrame({"model": ["m"] * 5, "condition": list("abcde"), "confirmed": [True] * 4 + [False]})
    books = pd.DataFrame(
        {"model": ["m"] * 5, "condition": list("abcde"), "split": "test", "exit": rn.CANDIDATE_EXIT,
         "sharpe_gross": [2.0, 2.0, 2.0, 0.1, 9.0], "placebo_q90_gross": [1.0, 1.0, 1.0, 1.0, 1.0]}
    )  # fmt: skip
    sel = pd.DataFrame(
        {"model": ["m"] * 5, "condition": list("abcde"), "t_pooled": [2.1, 3.0, 2.5, 9.0, 9.0]}
    )
    got = rn.candidates(fam, books, sel).set_index("condition")["candidate"]
    assert got.tolist() == [True, True, True, False, False]  # d fails its placebo, e is not confirmed
    books.loc[books["condition"] == "d", "sharpe_gross"] = 2.0
    got = rn.candidates(fam, books, sel).set_index("condition")["candidate"]
    assert got.tolist() == [False, True, True, True, False]  # four qualify: the three best validation t's
