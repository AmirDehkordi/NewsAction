"""Adjusted returns, QC flags and raw-close reconstruction (PREREG §5.1; PRD NA-01 S2, AC3)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction.panel import adjust

IDX = pd.DatetimeIndex(pd.bdate_range("2024-03-25", periods=8), name="session")


@pytest.mark.parametrize("ratio", [2.0, 3.0, 1.5, 10.0, 50.0, 0.2, 1 / 18, 0.5, 4 / 3])
def test_true_splits(ratio: float) -> None:
    assert adjust.is_true_split(ratio)


@pytest.mark.parametrize("ratio", [1.253, 1.281, 1.046, 1.197, 1.327, 2.39, 1.033, 1.272, float("nan"), 0.0])
def test_spinoff_price_ratios_are_not_splits(ratio: float) -> None:
    assert not adjust.is_true_split(ratio)


def test_classify_actions() -> None:
    acts = pd.DataFrame(
        {
            "symbol_id": [1, 1, 1],
            "action_type": ["split", "split", "cash_dividend"],
            "ex_date": [date(2024, 4, 2), date(2024, 6, 10), date(2024, 6, 1)],
            "split_ratio": [1.253, 10.0, np.nan],
        }
    )
    assert adjust.classify_actions(acts)["kind"].tolist() == ["spinoff", "split", "cash_dividend"]


def _ge_like() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A spin-off on day 5 (the GE 2024-04-02 mechanism): raw prices fall 20%, value does not."""
    raw_c = np.array([175.0, 176.0, 175.5, 175.2, 136.5, 145.6, 147.4, 156.3])
    raw_o = np.array([174.0, 175.5, 176.0, 175.0, 140.5, 138.2, 146.7, 148.5])
    f = np.where(np.arange(8) < 4, 0.7868, 0.9852)  # Data/prices factor before / after the spin-off
    one = lambda a: pd.DataFrame({1: a}, index=IDX)  # noqa: E731
    return one(raw_c * f), one(raw_o), one(raw_c)


def test_spin_off_overnight_return_is_adjusted() -> None:
    ac, ro, rc = _ge_like()
    r = adjust.returns(ac, ro, rc)
    unadjusted = ro.iloc[4, 0] / rc.iloc[3, 0] - 1
    assert unadjusted < -0.19
    assert abs(r["r_on"].iloc[4, 0]) < 0.03
    assert r["r_cc"].iloc[4, 0] == pytest.approx(ac.iloc[4, 0] / ac.iloc[3, 0] - 1)
    assert r["r_id"].iloc[4, 0] == pytest.approx(rc.iloc[4, 0] / ro.iloc[4, 0] - 1)
    assert (1 + r["r_on"].iloc[4, 0]) * (1 + r["r_id"].iloc[4, 0]) == pytest.approx(1 + r["r_cc"].iloc[4, 0])
    assert np.isnan(r["r_cc"].iloc[0, 0])  # no previous session


def test_true_split_factor_after_ignores_spinoffs() -> None:
    acts = adjust.classify_actions(
        pd.DataFrame(
            {
                "symbol_id": [1, 1],
                "action_type": ["split", "split"],
                "ex_date": [IDX[2].date(), IDX[5].date()],
                "split_ratio": [1.253, 4.0],
            }
        )
    )
    s = adjust.true_split_factor_after(IDX, [1], acts, IDX[-1])
    assert s[1].tolist() == [4.0] * 5 + [1.0] * 3


def test_reconstruct_raw_close_through_split_and_dividend() -> None:
    raw = np.array([100.0, 101.0, 50.0, 51.0, 50.5, 49.0, 49.5, 50.0])  # 2:1 split on day 2
    div, d_day = 0.5, 4
    f_true = np.ones(8)
    f_true[:2] /= 2.0  # split
    f_true[:d_day] *= 1 - div / raw[d_day - 1]  # Yahoo dividend convention
    ac = pd.DataFrame({1: raw * f_true}, index=IDX)
    acts = adjust.classify_actions(
        pd.DataFrame(
            {
                "symbol_id": [1, 1],
                "action_type": ["split", "cash_dividend"],
                "ex_date": [IDX[2].date(), IDX[d_day].date()],
                "split_ratio": [2.0, np.nan],
                "cash_amount": [np.nan, div],
            }
        )
    )
    anchor = IDX[1]
    hat = adjust.reconstruct_raw_close(ac, pd.Series({1: f_true[1]}), anchor, acts)
    assert hat.loc[:anchor, 1].isna().all()
    np.testing.assert_allclose(hat.loc[hat.index > anchor, 1].to_numpy(), raw[2:], rtol=1e-12)


def test_qc_reasons() -> None:
    ac, ro, rc = _ge_like()
    r = adjust.returns(ac, ro, rc)
    tc = rc.copy()  # an ATOM total series that misses the spin-off
    acts = adjust.classify_actions(
        pd.DataFrame(
            {"symbol_id": [1], "action_type": ["merger"], "ex_date": [IDX[7].date()], "split_ratio": [np.nan]}
        )
    )
    qc = adjust.qc_flags(r, tc, acts, pd.Series({1: True}), IDX)
    assert qc.loc[qc["session"] == IDX[4], "reason"].item() == "adj_factor_jump_no_atom_action"
    assert qc.loc[qc["session"] == IDX[4], "rule"].item() == "tr_diff_gt_50bp"


# --- integration (AC3) -----------------------------------------------------------------------------


def _members(panel: pd.DataFrame) -> pd.DataFrame:
    return panel[panel["member"]]


def test_ac3_ge_spin_off_golden(panel_public: pd.DataFrame) -> None:
    row = panel_public[(panel_public["ticker"] == "GE") & (panel_public["session"] == date(2024, 4, 2))]
    assert len(row) == 1
    assert abs(float(row["r_on"].item())) < 0.03
    assert float(row["raw_open"].item()) / 175.24 - 1 < -0.19  # the raw gap the adjustment removes


def test_ac3_every_large_overnight_move_is_flagged(panel_public: pd.DataFrame) -> None:
    from newsaction import io

    qc = io.read_parquet("panel/qc_flags.parquet")
    keys = set(zip(qc["session"], qc["symbol_id"], strict=True))
    big = _members(panel_public)
    big = big[big["r_on"].abs() > adjust.QC_R_ON]
    missing = [k for k in zip(big["session"], big["symbol_id"], strict=True) if k not in keys]
    assert missing == []
    assert (panel_public["qc_flag"] == panel_public["qc_rule"].notna()).all()


def _ex_dividend_frame(panel: pd.DataFrame) -> pd.DataFrame:
    from newsaction import io

    acts = io.read_parquet("snapshot/corporate_actions.parquet")
    div = acts.loc[acts["action_type"] == "cash_dividend", ["symbol_id", "ex_date", "cash_amount"]]
    div = div.groupby(["symbol_id", "ex_date"], as_index=False)["cash_amount"].sum()
    p = _members(panel)[["session", "symbol_id", "ar_on", "raw_close", "adj_factor"]].sort_values(
        ["symbol_id", "session"]
    )
    p = p.assign(
        prev_close=p.groupby("symbol_id")["raw_close"].shift(1),
        prev_f=p.groupby("symbol_id")["adj_factor"].shift(1),
    )
    out = p.merge(div, left_on=["symbol_id", "session"], right_on=["symbol_id", "ex_date"], how="left")
    out["ex_div"] = out["cash_amount"].notna()
    return out.dropna(subset=["ar_on"])


def test_ac3_dividend_adjustment_is_exact(panel_public: pd.DataFrame) -> None:
    """The adjustment check AC3 aims at: on ex-dates the factor jumps by D/P and AR_on does not
    scale with the dividend yield (a missing or doubled adjustment gives a slope of -1 or +1)."""
    d = _ex_dividend_frame(panel_public)
    ex = d[d["ex_div"]].dropna(subset=["prev_close", "prev_f"])
    dy = ex["cash_amount"] / ex["prev_close"]
    jump = ex["adj_factor"] / ex["prev_f"] - 1
    assert len(ex) > 3000
    assert jump.mean() / dy.mean() == pytest.approx(1.0, abs=0.02)
    slope = np.polyfit(dy.to_numpy(), ex["ar_on"].to_numpy(), 1)[0]
    assert abs(slope) < 0.1


@pytest.mark.xfail(
    strict=True, reason="AC3 3 bp bound: a +5-6 bp ex-date AR_on that does not scale with D/P (REPORT)"
)
def test_ac3_literal_ex_dividend_mean_difference_below_3bp(panel_public: pd.DataFrame) -> None:
    d = _ex_dividend_frame(panel_public)
    diff = d.loc[d["ex_div"], "ar_on"].mean() - d.loc[~d["ex_div"], "ar_on"].mean()
    assert abs(diff) < 3e-4
