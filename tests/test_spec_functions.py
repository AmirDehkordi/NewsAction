"""Every remaining spec function on synthetic frames with planted effects (PRD NA-11 S1): H6, H7, the A3
explanation analyses, A2.5 horizon validity, A1.4 tracking error, the explanation ladder, A3.5, the sector
tables, calibration and the frozen helpers on the daily panel (HAR, σ60, plateau), placebo and robustness."""

from __future__ import annotations

import itertools
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction.analysis import spec
from spec_fakes import TIERS, fast, panel


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(3000 + seed)


def test_h6_promotional_tone_predicts_reversal() -> None:
    rng = _rng(1)
    df = panel(seed=21)
    n = len(df)
    df["a2_n_hat"] = rng.normal(0, 1, n)
    df["g_d2"] = rng.normal(0, 1, n)
    df["a2_tone"] = rng.integers(0, 5, n).astype(float)
    df["a2_m"] = rng.random(n)
    df["vendor_quantified"] = rng.random(n) < 0.5
    df["vendor_event_type"] = rng.choice(["earnings_results", "analyst_action", "ma_deal"], n)
    df["y2"] = 0.2 * df["a2_n_hat"] - 0.15 * df["a2_tone"] * np.sign(df["a2_n_hat"]) + rng.normal(0, 1, n)
    r = spec.h6(df, "test", fast())
    assert r["d"] == pytest.approx(-0.15, abs=0.05) and r["p"] < 0.01 and r["estimate"] > 0


def test_h7_trained_beats_zero_shot() -> None:
    rng = _rng(2)
    df = panel(seed=22)
    n = len(df)
    signal = rng.normal(0, 1, n)
    df["z_cc"] = 0.4 * signal + rng.normal(0, 1, n)
    df["n_trained"] = signal + rng.normal(0, 0.5, n)
    df["n_zero"] = rng.normal(0, 1, n)
    r = spec.h7(df, "test", fast(), "n_trained", "n_zero")
    assert r["estimate"] > 0.2 and r["p"] < 0.01


def test_explained_share_and_persistence() -> None:
    rng = _rng(3)
    df = panel(seed=23)
    n = len(df)
    df["b2_x"] = rng.random(n)
    df["z_cc"] = np.where(df["b2_x"] >= 0.5, rng.normal(0, 2, n), rng.normal(0, 1, n))
    df["g_d2"] = df["z_cc"]
    df["a2_n_hat"] = rng.normal(0, 1, n)
    df["a2_label_event_type"] = rng.choice(["earnings_results", "analyst_action"], n)
    df["b2_label_move_reason"] = rng.choice(["earnings_results", "market_or_sector_move"], n)
    # explained moves persist: sign(G)·y2 rises with X
    df["y2"] = np.sign(df["g_d2"]) * (0.5 * df["b2_x"] - 0.25) + rng.normal(0, 1, n)
    es = spec.explained_share(df, "test", fast())
    assert es["share_explained"] > 0.6 and set(es["by_tier"]) == set(TIERS)
    assert set(es["by_reason"]) == {"earnings_results", "market_or_sector_move"}
    p = spec.persistence(df, "test", fast(), "D2")
    assert p["theta"] == pytest.approx(0.5, abs=0.15) and p["p"] < 0.01
    by = spec.persistence_by_reason(df, "test", fast())
    assert set(by) == {"earnings_results", "market_or_sector_move"}


def test_horizon_validity_negative_rank_correlation() -> None:
    rng = _rng(4)
    df = panel(seed=24)
    n = len(df)
    df["a0_h"] = rng.uniform(1, 60, n)
    share_now = 1 / (1 + df["a0_h"] / 10)  # a longer horizon realizes less of the move by C_t
    df["car_lvl_c20"] = rng.choice([-1, 1], n) * rng.uniform(1.5, 4, n)
    df["car_lvl_c0"] = share_now * df["car_lvl_c20"] + rng.normal(0, 0.1, n)
    r = spec.horizon_validity(df, "test", fast())
    assert r["rho"] < -0.5 and r["p"] < 0.01 and r["ci_high"] < 0


def test_tracking_error_ratios() -> None:
    rng = _rng(5)
    df = panel(seed=25)
    n = len(df)
    v = rng.normal(0, 1.5, n)
    df["a0_v"] = v
    df["po_v"] = rng.normal(0, 0.2, n)
    cfg = spec.load_config()
    for col in cfg.convergence.ladder.values():
        df[col] = v + rng.normal(0, 0.5, n)
    r = spec.tracking_error(df, "test", fast())
    row = r["rungs"]["C_t+20"]
    assert row["naive"]["ratio"] < 0.5 and row["naive"]["p"] < 0.01 and row["price_only"]["ratio"] < 0.5


def test_ladder_clean_window_and_h2c_tests() -> None:
    rng = _rng(6)
    df = panel(seed=26)
    n = len(df)
    v = rng.normal(0, 1, n)
    df["a0_v"], df["a2_v"] = v, v
    cfg = spec.load_config()
    for i, col in enumerate(cfg.convergence.ladder.values()):
        df[col] = (0.3 + 0.1 * i) * v + rng.normal(0, 0.5, n)
    for flag in cfg.convergence.clean_flags.values():
        df[flag] = rng.random(n) < 0.7
    df["g_d2_lvl"] = 0.5 * v + rng.normal(0, 0.5, n)
    for col in cfg.convergence.gap["D2"].rungs.values():
        df[col] = 0.6 * (v - df["g_d2_lvl"]) + rng.normal(0, 0.5, n)
    lad = spec.ladder(df, "test", fast(), clean=True)
    assert lad["rungs"]["C_t+20"]["nobs"] < lad["rungs"]["C_t"]["nobs"]  # clean flags apply to t+h rungs only
    gap = spec.gap_closure(df, "test", fast(), "D2")
    df["po_v"] = 0.0
    te = spec.tracking_error(df, "test", fast())
    p = spec.h2c_tests(spec.ladder(df, "test", fast()), gap, te, spec.load_config())
    assert set(p) == {"H2C_kappa_hstar", "H2C_kappa_increase", "H2C_lambda_t5", "H2C_tracking_naive"}
    assert all(0 < x <= 1 for x in p.values())
    q = spec.secondary_family({**p, "H5": 0.2, "H6": 0.5})
    assert all(q[k] >= p[k] for k in p)


def test_explanation_ladder_steps() -> None:
    rng = _rng(7)
    df = panel(seed=27)
    n = len(df)
    df["has_d0"] = (rng.random(n) < 0.3).astype(float)
    df["has_d2"] = np.maximum(df["has_d0"], (rng.random(n) < 0.2).astype(float))
    pre = rng.normal(0, 1, n) * df["has_d0"]
    post = rng.normal(0, 1, n) * df["has_d2"]
    df["a0_n_hat"], df["a2_n_hat"] = pre, pre + post
    for c in (
        "a0_abs_n_hat",
        "a0_m",
        "a0_surprise",
        "a0_tone",
        "a2_abs_n_hat",
        "a2_m",
        "a2_surprise",
        "a2_tone",
    ):
        df[c] = 0.0
    df["z_cc"] = 0.4 * pre + 0.6 * post + rng.normal(0, 1, n)
    steps = {k: v for k, v in spec.load_config().explanation.ladder_steps.items() if k != "explanation"}
    lad = spec.explanation_ladder(df, fast(), steps)
    a, p = lad["steps"]["ex_ante"]["value"], lad["steps"]["ex_post"]["value"]
    assert 0 < a < p and lad["steps"]["ex_post"]["increment"]["p"] < 0.01
    assert lad["knowable_before_open"] == pytest.approx(a / p)
    assert spec.h5(df, fast(), steps)["p"] < 0.01
    days = df.assign(ar_cc=0.5 * rng.normal(0, 1, n), r_cc=rng.normal(0, 1, n))
    assert 0 < spec.roll_r2(days, "test", fast())["r2"] < 1


def test_market_replication() -> None:
    rng = _rng(8)
    sessions = pd.bdate_range("2011-01-03", periods=300)
    split = ["val_a"] * 64 + ["val_b"] * 64 + ["test"] * 172
    m = pd.DataFrame({"session": sessions.date, "split": split, "m_n_hat": rng.normal(0, 1, 300)})
    m["r_spy_cc"] = 0.006 * m["m_n_hat"] + rng.normal(0, 0.006, 300)
    r = spec.market_replication(m, fast())
    assert r["available"] and r["r2_value"] > 0.25 and r["r2_p"] < 0.01


def test_sector_tables_and_ic_targets() -> None:
    rng = _rng(9)
    df = panel(seed=29)
    n = len(df)
    df["sector"] = rng.choice(["Energy", "Utilities", "Financials"], n)
    df["a0_n_hat"] = rng.normal(0, 1, n)
    df["z_cc"] = np.where(df["sector"] == "Energy", 0.8, 0.0) * df["a0_n_hat"] + rng.normal(0, 1, n)
    df["z_on"], df["z_id"] = df["z_cc"], rng.normal(0, 1, n)
    r = spec.sector_ic(df, "test", fast())
    assert r["by_sector"]["Energy"]["ic_z_cc"] > 0.3 and abs(r["by_sector"]["Utilities"]["ic_z_cc"]) < 0.15
    assert r["leave_one_out"]["Energy"]["ic_z_cc"] < r["leave_one_out"]["Utilities"]["ic_z_cc"]


def test_calibration_and_auc() -> None:
    rng = _rng(10)
    n = 4000
    z = rng.normal(0, 1, n)
    good = np.zeros((n, 9))
    good[:, 0], good[:, 4], good[:, 8] = (z < -0.5) * 0.9 + 0.05, (abs(z) < 0.5) * 0.9 + 0.05, (z > 0.5) * 0.9
    good = good / good.sum(axis=1, keepdims=True)
    flat = np.full((n, 9), 1 / 9)
    cfg = spec.load_config()
    a, b = spec.calibration(good, z, z, cfg), spec.calibration(flat, z, z, cfg)
    assert a["brier_skill"] > 0.5 and b["log_loss_skill"] < 0 and a["n"] == n
    assert spec.auc_large(np.abs(z), z, cfg) == pytest.approx(1.0)


def test_daily_panel_helpers() -> None:
    rng = _rng(11)
    days = pd.bdate_range("2011-01-03", periods=120)
    rows = [
        {
            "session": d.date(),
            "symbol_id": s,
            "z_cc": rng.normal(),
            "ar_cc": rng.normal(0, 0.01),
            "ar_on": rng.normal(0, 0.005),
            "ar_id": rng.normal(0, 0.008),
            "sigma_cc": 0.01,
        }
        for d in days
        for s in (1, 2)
    ]
    daily = pd.DataFrame(rows)
    cfg = spec.load_config()
    har = spec.har_features(daily, cfg).set_index(["session", "symbol_id"])
    d = daily.set_index(["session", "symbol_id"])["z_cc"].abs().unstack()
    t = days[30].date()
    assert har.loc[(t, 1), "har_d"] == pytest.approx(d[1].iloc[29])
    assert har.loc[(t, 1), "har_w"] == pytest.approx(d[1].iloc[25:30].mean())
    assert har.loc[(t, 1), "har_m"] == pytest.approx(d[1].iloc[8:30].mean())
    s60 = spec.sigma60(daily, cfg).set_index(["session", "symbol_id"])
    ar = daily.set_index(["session", "symbol_id"])["ar_cc"].unstack()
    t = days[80].date()
    assert s60.loc[(t, 2), "s60_cc"] == pytest.approx(ar[2].iloc[20:80].std(ddof=1))
    rows_q = pd.DataFrame(
        {"session": [days[10].date(), days[110].date()], "symbol_id": [1, 1], "split": ["test", "test"]}
    )
    pl = spec.plateau_rungs(daily, rows_q, {"test": days[-1].date()}, cfg)
    expect = ar[1].iloc[10:27].sum() / 0.01  # Σ_{j=0..16} AR_cc,t+j / σ_cc,t
    assert pl.iloc[0]["car_lvl_c16"] == pytest.approx(expect)
    assert math.isnan(pl.iloc[1]["car_lvl_c16"])  # t+16 leaves the grid: purged
    f = pl.assign(car_lvl_c17=1.0, car_lvl_c18=1.0, car_lvl_c19=1.0, car_lvl_c20=1.0)
    assert spec.plateau(f, cfg).notna().sum() == 1


def test_sigma60_rescale_and_robustness_variants() -> None:
    rng = _rng(12)
    df = panel(seed=32)
    n = len(df)
    for c in ("ar_on", "ar_id", "ar_cc", "ar_o1_c5"):
        df[c] = rng.normal(0, 0.01, n)
    for c in ("s60_cc", "s60_on", "s60_id", "s60_cc_next", "s60_id_next"):
        df[c] = 0.01
    out = spec.sigma60_rescale(df)
    assert out["z_cc"].abs().max() <= 10 and np.allclose(out["g_d2"], out["z_cc"])
    assert np.allclose(out["y2"], df["ar_o1_c5"] / np.sqrt(0.01**2 + 4 * 0.01**2))
    df["dv_tier"], df["half_day"], df["imprecise"] = df["tier"], rng.random(n) < 0.05, rng.random(n) < 0.1
    df["delist_within_c20"], df["price_move_text"] = False, rng.random(n) < 0.1
    df["latest_et"] = rng.uniform(-300, 555, n)
    sessions = sorted(df["session"].unique())
    names = dict(spec.robustness_variants(df, spec.load_config(), sessions))
    assert {
        "dollar_volume_tiers",
        "exclude_date_only_hour",
        "exclude_half_days",
        "non_overlapping",
        "exclude_delisting_flag",
        "without_price_move_text",
    } <= set(names)
    assert {k for k in names if k.startswith("timing_")} == {
        "timing_before_04:00",
        "timing_04:00_08:00",
        "timing_08:00_09:15",
    }
    d2_names = dict(spec.robustness_variants(df, spec.load_config(), sessions, "D2"))
    assert "without_price_move_text" not in d2_names and not any(k.startswith("timing_") for k in d2_names)
    no = names["non_overlapping"]
    for _, g in no.groupby("company_id"):
        pos = sorted(sessions.index(s) for s in g["session"])
        assert all(b - a >= 5 for a, b in itertools.pairwise(pos))


def test_placebo_adjust() -> None:
    days = pd.DataFrame(
        {
            "session": [date(2011, 1, 3)] * 4,
            "tier": ["mid"] * 4,
            "z": [1.0, 3.0, 5.0, 7.0],
            "placebo_eligible": [True, True, False, True],
        }
    )
    means = spec.placebo_means(days, ["z"])
    assert means["z_placebo"].iloc[0] == pytest.approx(11 / 3)
    ev = pd.DataFrame({"session": [date(2011, 1, 3)], "tier": ["mid"], "z": [4.0]})
    out = spec.placebo_adjust(ev, means, ["z"])
    assert out["z"].iloc[0] == pytest.approx(4 - 11 / 3) and "z_placebo" in out.columns


def test_mechanism_cuts_by_label() -> None:
    rng = _rng(13)
    df = panel(seed=33)
    n = len(df)
    df["a2_n_hat"], df["g_d2"] = rng.normal(0, 1, n), rng.normal(0, 1, n)
    df["a2_label_event_type"] = rng.choice(["earnings_results", "analyst_action"], n)
    df["vendor_event_type"] = df["a2_label_event_type"]
    df["y2"] = np.where(df["a2_label_event_type"] == "earnings_results", 0.5, 0.0) * df[
        "a2_n_hat"
    ] + rng.normal(0, 1, n)
    cfg = fast()
    out = spec.mechanism_cuts(df, "test", cfg, lambda f: spec.h2(f, "test", cfg, "D2"), "a2_")
    by = out["a2_label_event_type"]
    assert by["earnings_results"]["b"] > 0.3 and abs(by["analyst_action"]["b"]) < 0.15
    assert "vendor_event_type" in out
