"""The analysis spec recovers planted effects (PRD NA-11 S1, AC2): H2's b > 0 and c < 0, H1's gap-vs-open
split, H3's ΔIC, H4's ΔR², a planted Shapley interaction, the convergence ladder κ_h rising to 1 and a gap
closure with a known half-life, and a heterogeneity cut that differs."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest

from newsaction.analysis import spec
from spec_fakes import fast, panel


def test_h2_recovers_b_positive_and_c_negative() -> None:
    rng = np.random.default_rng(1002)
    df = panel()
    n = len(df)
    df["a2_n_hat"] = rng.normal(0, 1, n)
    df["g_d2"] = 0.6 * df["a2_n_hat"] + rng.normal(0, 1, n)
    df["y2"] = 0.30 * df["a2_n_hat"] - 0.20 * df["g_d2"] + df["day_tier"] + rng.normal(0, 1, n)
    r = spec.h2(df, "test", fast(), "D2")
    assert r["b"] == pytest.approx(0.30, abs=0.06) and r["c"] == pytest.approx(-0.20, abs=0.05)
    assert r["b_p"] < 0.01 and r["c_p"] < 0.01 and r["p"] == max(r["b_p"], r["c_p"])
    # embargoed sessions are left out of the sample
    assert r["nobs"] == int(((df["split"] == "test") & ~df["embargo"]).sum())
    # the null: no effect gives no rejection of the joint claim
    df["y2"] = df["day_tier"] + rng.normal(0, 1, n)
    assert spec.h2(df, "test", fast(), "D2")["p"] > 0.05


def test_h1_gap_versus_open_close() -> None:
    rng = np.random.default_rng(1003)
    df = panel()
    n = len(df)
    df["a0_n_hat"] = rng.normal(0, 1, n)
    df["z_on"] = 0.5 * df["a0_n_hat"] + rng.normal(0, 1, n)
    df["z_id"] = rng.normal(0, 1, n)
    r = spec.h1(df, "test", fast())
    assert r["value"] > 0.3 and r["p"] < 0.01 and r["ic_on"] > 0.3 and abs(r["ic_id"]) < 0.05


def test_h1_null_rejects_at_about_the_nominal_rate() -> None:
    """20 null replications at the 5% level: P(>= 5 rejections) is 0.3% for a correct test."""
    cfg = fast(500)
    rejections = 0
    for seed in range(20):
        rng = np.random.default_rng(2000 + seed)
        df = panel(seed=seed)
        n = len(df)
        df["a0_n_hat"], df["z_on"], df["z_id"] = (rng.normal(0, 1, n) for _ in range(3))
        rejections += spec.h1(df, "test", cfg)["p"] < 0.05
    assert rejections <= 4


def test_h1b_recovers_a_planted_z_id_effect() -> None:
    rng = np.random.default_rng(1013)
    df = panel()
    n = len(df)
    df["a0_n_hat"] = rng.normal(0, 1, n)
    df["z_on"] = 0.4 * df["a0_n_hat"] + rng.normal(0, 1, n)
    df["z_id"] = 0.15 * df["a0_n_hat"] + rng.normal(0, 1, n)  # part of the news is priced after the open
    r = spec.h1b(df, "test", fast())
    assert r["test"] == "H1b" and r["value"] > 0.08 and r["p"] < 0.01
    both = spec.primary_d0(df, "test", fast())
    assert set(both) == {"H1", "H1b"} and both["H1b"]["value"] == pytest.approx(r["value"])
    assert both["H1"]["n_days"] == r["n_days"]  # the same sample and bootstrap draws as H1


def test_h1b_null_rejects_at_about_the_nominal_rate() -> None:
    """No z_id effect, 20 replications at the 5% level: P(>= 5 rejections) is 0.3% for a correct test."""
    cfg = fast(500)
    rejections = 0
    for seed in range(20):
        rng = np.random.default_rng(4000 + seed)
        df = panel(seed=seed)
        n = len(df)
        df["a0_n_hat"] = rng.normal(0, 1, n)
        df["z_on"] = 0.4 * df["a0_n_hat"] + rng.normal(0, 1, n)  # priced at the open only
        df["z_id"] = rng.normal(0, 1, n)
        rejections += spec.h1b(df, "test", cfg)["p"] < 0.05
    assert rejections <= 4


def _d2_frame(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = panel(seed=seed)
    n = len(df)
    for c in (
        "g_d2",
        "z_on",
        "z_m5",
        "z_m20",
        "z_m60",
        "z_vol",
        "a2_n_hat",
        "a2_m",
        "a2_surprise",
        "a2_tone",
        "b2_j",
        "b2_c",
        "b2_w",
    ):
        df[c] = rng.normal(0, 1, n)
    return df


def test_h3_delta_ic_when_j_carries_information() -> None:
    rng = np.random.default_rng(1004)
    df = _d2_frame(4)
    df["y2"] = 0.2 * df["a2_n_hat"] + 0.5 * df["b2_j"] + rng.normal(0, 1, len(df))
    groups = {"R": ["g_d2", "z_on"], "N": ["a2_n_hat", "a2_m"], "J": ["b2_j", "b2_c"]}
    r = spec.h3(df, fast(), groups)
    assert r["value"] > 0.1 and r["p"] < 0.01
    shares = r["shapley"]["all"]["r2"]["shares"]
    assert shares["J"] > shares["N"] > shares["R"]
    assert math.fsum(r["shapley"]["all"]["r2"]["shapley"].values()) == pytest.approx(
        r["shapley"]["all"]["r2"]["values"]["R+N+J"]
    )


def test_h3_recovers_a_planted_shapley_interaction() -> None:
    """y = x_R − x_N with x_R, x_N sharing a common factor: neither group alone explains y, both together do.
    Shapley splits the joint value equally and the R×N interaction carries it; J is a null player."""
    rng = np.random.default_rng(1005)
    df = _d2_frame(5)
    n = len(df)
    u = rng.normal(0, 1, n)
    df["g_d2"] = u + rng.normal(0, 0.3, n)
    df["a2_n_hat"] = u + rng.normal(0, 0.3, n)
    df["y2"] = df["g_d2"] - df["a2_n_hat"] + rng.normal(0, 0.05, n)
    groups = {"R": ["g_d2"], "N": ["a2_n_hat"], "J": ["b2_j"]}
    r2 = spec.h3(df, fast(), groups)["shapley"]["all"]["r2"]
    v = r2["values"]
    assert v["R"] < 0.05 and v["N"] < 0.05 and v["R+N"] > 0.9
    assert r2["shapley"]["R"] == pytest.approx(r2["shapley"]["N"], abs=0.03)
    assert abs(r2["shapley"]["J"]) < 0.01
    assert r2["interactions"]["RxN"] > 0.85


def test_h4_width_gain_from_news() -> None:
    rng = np.random.default_rng(1006)
    df = panel(seed=6)
    n = len(df)
    for c in (
        "har_d",
        "har_w",
        "har_m",
        "a0_m",
        "a0_surprise",
        "a0_abs_n_hat",
        "a0_u_unc",
        "a0_p_no_material_effect",
    ):
        df[c] = rng.gamma(2.0, 0.5, n)
    df["earnings"] = (rng.random(n) < 0.1).astype(float)
    df["abs_z_cc"] = (
        0.3 * df["har_w"] + 0.6 * df["a0_abs_n_hat"] + 0.8 * df["earnings"] + rng.gamma(2, 0.3, n)
    )
    r = spec.h4(
        df, fast(), ["a0_m", "a0_surprise", "a0_abs_n_hat"], extra=["a0_u_unc", "a0_p_no_material_effect"]
    )
    assert r["value"] > 0.05 and r["p"] < 0.01
    assert abs(r["a2_width"]["value"]) < 0.01  # the A2.5 additions are pure noise here


def _convergence_frame(seed: int, half_life: float) -> tuple[pd.DataFrame, dict[str, float]]:
    rng = np.random.default_rng(seed + 1000)
    df = panel(n_firms=80, seed=seed)
    n = len(df)
    v = rng.normal(0, 1.5, n)
    df["a0_v"] = v
    df["a2_v"] = v
    kappa = {
        "O_t": 0.30,
        "10:00": 0.40,
        "C_t": 0.50,
        "C_t+1": 0.60,
        "C_t+2": 0.70,
        "C_t+5": 0.85,
        "C_t+10": 0.95,
        "C_t+20": 1.00,
    }
    cfg = spec.load_config()
    for name, col in cfg.convergence.ladder.items():
        df[col] = kappa[name] * v + df["day_tier"] + rng.normal(0, 0.5, n)
    # gap closure at D2: the price closes a fraction λ_k = 1 − 2^(−k / half_life) of U = V − G^lvl by t+k
    g = 0.5 * v + rng.normal(0, 0.8, n)
    df["g_d2_lvl"] = g
    lam = {}
    for name, col in cfg.convergence.gap["D2"].rungs.items():
        k = cfg.convergence.rung_sessions[name]
        lam[name] = 1 - 2 ** (-k / half_life)
        df[col] = lam[name] * (v - g) + df["day_tier"] + rng.normal(0, 0.3, n)
    return df, lam


def test_ladder_rises_to_one() -> None:
    df, _ = _convergence_frame(7, 4.0)
    r = spec.ladder(df, "test", fast())
    k = {n: r["rungs"][n]["kappa"] for n in r["rungs"]}
    assert k["C_t+20"] == pytest.approx(1.0, abs=0.03)
    assert k["O_t"] == pytest.approx(0.30, abs=0.03)
    vals = list(k.values())
    assert all(b > a for a, b in itertools.pairwise(vals))
    assert r["share_h_star"]["C_t+5"] == pytest.approx(0.85, abs=0.04)
    assert r["increase"]["p"] < 0.01 and r["kappa_h_star_p"] < 0.01


def test_gap_closure_known_half_life() -> None:
    df, lam = _convergence_frame(8, 4.0)  # λ_1 = 0.16, λ_5 = 0.58, λ_20 = 0.97: half-life rung t+5
    r = spec.gap_closure(df, "test", fast(), "D2")
    for name, true in lam.items():
        assert r["rungs"][name]["lambda"] == pytest.approx(true, abs=0.04)
        assert abs(r["rungs"][name]["psi"]) < 0.05  # price converges to V itself: ψ = 0
    assert r["half_life_sessions"] == 5
    assert r["half_life_distribution"]["5"] > 0.95
    df2, _ = _convergence_frame(9, 0.5)  # fast: λ_1 = 0.75, the half-life is the first rung
    assert spec.gap_closure(df2, "test", fast(), "D2")["half_life_sessions"] == 1
    df3, _ = _convergence_frame(10, 60.0)  # slow: λ_20 = 0.21, never within t+20
    assert math.isinf(spec.gap_closure(df3, "test", fast(), "D2")["half_life_sessions"])


def test_heterogeneity_cut_detects_a_planted_difference() -> None:
    rng = np.random.default_rng(1011)
    df = panel(seed=11)
    n = len(df)
    df["a2_n_hat"] = rng.normal(0, 1, n)
    df["g_d2"] = rng.normal(0, 1, n)
    top = (df["tier"] == "top100").to_numpy()
    df["y2"] = np.where(top, 0.0, 0.4) * df["a2_n_hat"] - 0.1 * df["g_d2"] + rng.normal(0, 1, n)
    df["vendor_quantified"] = rng.random(n) < 0.5
    df["press_wire"] = rng.random(n) < 0.3
    df["attention_mean"] = rng.gamma(2, 3, n)
    df["attention_ratio"] = rng.gamma(2, 0.6, n)
    rows = {r["cut"]: r for r in spec.heterogeneity(df, "test", fast())}
    assert set(rows) == set(spec.load_config().cuts.list)
    assert rows["tier_top100"]["p"] < 0.01 and rows["tier_top100"]["b_diff"] < -0.2
    assert rows["quantified"]["p"] > 0.01 and rows["press_wire"]["p"] > 0.01
    assert all(0 <= r["q"] <= 1 for r in rows.values())


def test_cut_indicator_rules() -> None:
    cfg = spec.load_config()
    f = pd.DataFrame(
        {
            "session": [1, 1, 1, 1, 2, 2],
            "tier": ["mid"] * 6,
            "attention_mean": [1.0, 2.0, 3.0, np.nan, 5.0, 1.0],
            "attention_ratio": [1.5, 1.49, 3, np.nan, 0, 9],
        }
    )
    low = spec.cut_indicator(f, cfg.cuts.list["usual_coverage_low"])
    assert low.tolist()[:3] == [1.0, 0.0, 0.0] and math.isnan(low.iloc[3]) and low.tolist()[4:] == [0.0, 1.0]
    busy = spec.cut_indicator(f, cfg.cuts.list["busy_day"])
    assert busy.tolist()[:3] == [1.0, 0.0, 1.0] and math.isnan(busy.iloc[3])


def test_headline_rule() -> None:
    cfg = spec.load_config()
    prim = {t: {"estimate": 0.1, "p": 0.001} for t in ("H1", "H1b", "H2", "H3", "H4")}
    adj = spec.primary_family({t: 0.001 for t in prim}, cfg)
    anchor = {
        "H1": {"estimate": 0.05, "p": 0.01},
        "H2": {"estimate": -0.05, "p": 0.01},
        "H3": {"estimate": 0.05, "p": 0.2},
    }
    out = spec.headline(prim, anchor, adj, cfg)
    assert out == {
        "H1": "general",
        "H1b": "model-specific",
        "H2": "model-specific",
        "H3": "model-specific",
        "H4": "model-specific",
    }
    adj_fail = spec.primary_family({"H1": 0.03, "H1b": 0.5, "H2": 0.04, "H3": 0.001, "H4": 0.2}, cfg)
    assert set(adj_fail) == {"H1", "H1b", "H2", "H3", "H4"}  # Holm over five tests
    assert adj_fail["H1"] == pytest.approx(0.12)  # 0.03 · 4 (the 2nd smallest of five)
    assert spec.headline(prim, anchor, adj_fail, cfg)["H1"] == "not supported"


def test_directional_h2_needs_both_signs() -> None:
    assert spec.directional({"test": "H2", "b": 0.2, "c": 0.1, "p": 0.01})["estimate"] < 0
    assert spec.directional({"test": "H2", "b": 0.2, "c": -0.1, "p": 0.01})["estimate"] == pytest.approx(0.1)
