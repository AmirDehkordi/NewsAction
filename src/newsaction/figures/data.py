"""NA-14 S2: each figure's CSV, assembled from the upstream rows it plots (PRD NA-14 S2, AC3–AC4).

    uv run python -m newsaction.figures.data

Every builder selects rows of NA-03, NA-06, NA-07, NA-11, NA-12 and NA-13 outputs (``sources``) and writes
them
in the long figure format with their provenance. Nothing here estimates anything: the only arithmetic is a
95% interval from a stored standard error or t statistic (``sources.rows``). The figure modules then read
only their CSV.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from newsaction.figures import sources as sc
from newsaction.paths import Layout, resolve_layout

# Event-time rungs of Figure 1 (PREREG A1.2): figure-data point → (position, axis label).
RUNGS: Final = {
    "car_pre1": (0, "C(t−1)"),
    "car_lvl_o0": (1, "O(t)"),
    "car_lvl_10": (2, "10:00"),
    "car_post0": (3, "C(t)"),
    "car_post1": (4, "t+1"),
    "car_post2": (5, "t+2"),
    "car_post5": (6, "t+5"),
    "car_post10": (7, "t+10"),
    "car_post20": (8, "t+20"),
}
# The κ ladder's rungs (t6) at the same positions.
LADDER_RUNGS: Final = {
    "O_t": "car_lvl_o0",
    "10:00": "car_lvl_10",
    "C_t": "car_post0",
    "C_t+1": "car_post1",
    "C_t+2": "car_post2",
    "C_t+5": "car_post5",
    "C_t+10": "car_post10",
    "C_t+20": "car_post20",
}
FIG1_MODELS: Final = ("laya_fin", "d1_ultra", "anchor")
T6: Final = f"{sc.NA12_TAB}/t6_convergence_ladder.csv"
T7: Final = f"{sc.NA12_TAB}/t7_gap_closure.csv"


def _pos(points: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    pos = points.map(lambda p: RUNGS[p][0]).to_numpy(dtype=float)
    lab = points.map(lambda p: RUNGS[p][1]).to_numpy()
    return pos, lab


def fig1(src: sc.Sources) -> pd.DataFrame:
    """Figure 1, convergence: V-decile paths with their mean V (a, b), the κ ladder (c), the signed RG-class
    paths (d) and the half-lives of the gap (annotation)."""
    out = []
    v = src.frame(sc.V_DECILES)
    for panel, model in (("a", "laya_fin"), ("b", "d1_ultra")):
        d = v[(v["model"] == model) & v["point"].isin(list(RUNGS))].copy()
        d["xpos"], d["xlab"] = _pos(d["point"])
        d["series"] = "decile_" + d["group"].astype(str)
        out.append(
            sc.rows(
                d,
                sc.V_DECILES,
                panel=panel,
                series="series",
                label="group",
                role="=path",
                x="xlab",
                xv="xpos",
                y_col="mean",
                ci="se",
                se_col="se",
            )
        )
        t = d[d["point"] == "car_post0"].copy()
        t["series"] = "decile_" + t["group"].astype(str)
        out.append(
            sc.rows(
                t,
                sc.V_DECILES,
                panel=panel,
                series="series",
                label="group",
                role="=target",
                x="=target",
                y_col="mean_v",
            )
        )
    t6 = src.frame(T6)
    for model in FIG1_MODELS:
        d = t6[
            (t6["model"] == model) & (t6["variant"] == "ladder") & t6["rung"].isin(list(LADDER_RUNGS))
        ].copy()
        pts = d["rung"].map(LADDER_RUNGS)
        d["xpos"], d["xlab"] = _pos(pts)
        out.append(
            sc.rows(
                d,
                T6,
                panel="c",
                series=f"={model}",
                label=f"={model}",
                role="=kappa",
                x="xlab",
                xv="xpos",
                y_col="kappa",
                ci="se",
                se_col="kappa_se",
            )
        )
    t7 = src.frame(T7)
    h = t7[t7["key"].isin([f"{m}:{p}:all:half_life" for m in FIG1_MODELS for p in ("D1", "D2")])].copy()
    out.append(
        sc.rows(
            h, T7, panel="c", series="model", label="point", role="=half_life", x="=half_life", y_col="lambda"
        )
    )
    rg = src.frame(sc.RG_CLASSES)
    rg_points = [p for p in RUNGS if p not in ("car_lvl_o0", "car_lvl_10")]
    d = rg[(rg["model"] == "d1_ultra") & (rg["figure"] == "rg_class_signed") & rg["point"].isin(rg_points)]
    d = d.copy()
    d["xpos"], d["xlab"] = _pos(d["point"])
    out.append(
        sc.rows(
            d,
            sc.RG_CLASSES,
            panel="d",
            series="group",
            label="group",
            role="=path",
            x="xlab",
            xv="xpos",
            y_col="mean",
            ci="se",
            se_col="se",
        )
    )
    t = d[d["point"] == "car_post0"]
    out.append(
        sc.rows(
            t,
            sc.RG_CLASSES,
            panel="d",
            series="group",
            label="group",
            role="=target",
            x="=target",
            y_col="mean_v",
        )
    )
    for model in ("d1_ultra", "laya_fin"):
        n = rg[(rg["model"] == model) & (rg["figure"] == "rg_class_signed") & (rg["point"] == "car_post0")]
        out.append(
            sc.rows(
                n,
                sc.RG_CLASSES,
                panel="d",
                series="group",
                label=f"={model}",
                role="=n_events",
                x="=n_group",
                y_col="n_group",
            )
        )
    return pd.concat(out, ignore_index=True)


# Figure 7: the books (NA-13 strategy table rules), S-CONV first (PREREG A1.6), each family at the exit that
# matches its hypothesis' horizon (H2 at D2: t+5; S-D0: the official close; S-D1: the close).
FIG7_PANELS: Final = (
    (
        "a",
        "S-CONV (D2 → t+5)",
        (
            ("laya_fin", "S-CONV|laya_fin|D2|u|close_t+5|all"),
            ("d1_ultra", "S-CONV|d1_ultra|D2|u|close_t+5|all"),
            ("anchor", "S-CONV|anchor|D2|u|close_t+5|all"),
            ("gap_fade", "gap_fade|-|D2|gap|close_t+5|all"),
        ),
    ),
    (
        "b",
        "S-D0 (open → close)",
        (
            ("laya_fin", "S-D0|laya_fin|D0|n_tilde|close_t|all"),
            ("laya_fin_gated", "S-D0|laya_fin|D0|n_tilde|close_t|gated"),
            ("d1_ultra", "S-D0|d1_ultra|D0|n_tilde|close_t|all"),
            ("sentiment", "vendor_sentiment|-|D0|sentiment|close_t|all"),
        ),
    ),
    (
        "c",
        "S-D1 J (10:00 → close)",
        (
            ("laya_fin", "S-D1|laya_fin|D1|j|close_t|all"),
            ("d1_ultra", "S-D1|d1_ultra|D1|j|close_t|all"),
            ("gap_fade", "gap_fade|-|D1|gap|close_t|all"),
        ),
    ),
    (
        "d",
        "S-D2 J (next open → t+5)",
        (
            ("laya_fin", "S-D2|laya_fin|D2|j|close_t+5|all"),
            ("d1_ultra", "S-D2|d1_ultra|D2|j|close_t+5|all"),
            ("gap_fade", "gap_fade|-|D2|gap|close_t+5|all"),
        ),
    ),
)
FIG7_TIERS: Final = (("e", "top100"), ("f", "mid"), ("g", "rest"))
FIG7_TIER_BOOKS: Final = (
    ("laya_fin", "S-CONV|laya_fin|D2|u|close_t+5|all"),
    ("gap_fade", "gap_fade|-|D2|gap|close_t+5|all"),
)


def _placebo_rule(src: sc.Sources, rule: str) -> str:
    st = src.frame(sc.STRATEGY)
    hit = st[(st["split"] == "test") & (st["rule"] == rule)]
    if len(hit) != 1:
        raise KeyError(f"{rule}: not one test row in the strategy table")
    return f"placebo|{hit['universe'].iloc[0]}"


def fig7(src: sc.Sources) -> pd.DataFrame:
    """Figure 7: cumulative net returns at 10 bp per side (test), S-CONV first, the benchmarks, the placebo's
    5th–95th percentile band of the primary instrument's universe (a–d) and the S-CONV book by tier (e–g)."""
    f = src.frame(sc.FIG7)
    out = []
    for panel, _, books in FIG7_PANELS:
        for series, rule in books:
            d = f[(f["rule"] == rule) & (f["tier"] == "all") & (f["series"] == "book")]
            if d.empty:
                raise KeyError(f"{rule}: no Figure 7 series")
            out.append(
                sc.rows(
                    d,
                    sc.FIG7,
                    panel=panel,
                    series=f"={series}",
                    label="=" + rule,
                    role="=book",
                    x="session",
                    y_col="cum_net_10",
                )
            )
        band = f[(f["rule"] == _placebo_rule(src, books[0][1])) & (f["series"] == "placebo_band")]
        out.append(
            sc.rows(
                band,
                sc.FIG7,
                panel=panel,
                series="=placebo",
                label="rule",
                role="=placebo_band",
                x="session",
                y_col="cum_net_10_q50",
                ci="table",
                lo_col="cum_net_10_q05",
                hi_col="cum_net_10_q95",
            )
        )
    for panel, tier in FIG7_TIERS:
        for series, rule in FIG7_TIER_BOOKS:
            d = f[(f["rule"] == rule) & (f["tier"] == tier) & (f["series"] == "book")]
            out.append(
                sc.rows(
                    d,
                    sc.FIG7,
                    panel=panel,
                    series=f"={series}",
                    label="=" + rule,
                    role="=" + tier,
                    x="session",
                    y_col="cum_net_10",
                )
            )
    return pd.concat(out, ignore_index=True)


G_BINS: Final = ("[0, 0.5)", "[0.5, 1)", "[1, 2)", "[2, 3)", "[3, inf)")
TERCILES: Final = (("a", "weak"), ("b", "medium"), ("c", "strong"))
FIG2_MODELS: Final = ("laya_fin", "d1_ultra", "anchor")


def fig2(src: sc.Sources) -> pd.DataFrame:
    """Figure 2: mean sign(G)·y2 (drift after D2) by |G| bin, one panel per tercile of news strength
    |V_W2|."""
    d = src.frame(sc.DRIFT)
    d = d[d["model"].isin(FIG2_MODELS)].copy()
    d["xpos"] = d["g_bin"].map({b: i for i, b in enumerate(G_BINS)}).astype(float)
    out = [
        sc.rows(
            d[d["tercile"] == t],
            sc.DRIFT,
            panel=panel,
            series="model",
            label="tercile",
            role="=drift",
            x="g_bin",
            xv="xpos",
            y_col="mean",
            ci="se",
            se_col="se",
        )
        for panel, t in TERCILES
    ]
    return pd.concat(out, ignore_index=True)


T14: Final = f"{sc.NA12_TAB}/t14_model_comparison.csv"
# Figure 3(b): the final instruments and the baselines, top to bottom.
FIG3_ROWS: Final = (
    ("laya_fin", "laya_fin"),
    ("anchor", "anchor"),
    ("laya_zs", "laya_zs"),
    ("d1_ultra", "d1_ultra"),
    ("span_02", "span_02"),
    ("drex_v2", "drex_v2"),
    ("price_only", "baseline:price_only"),
    ("embed_ridge", "baseline:embed_ridge"),
    ("llm", "baseline:llm"),
    ("sentiment", "baseline:sentiment"),
    ("tags_gbm", "baseline:tags_gbm"),
)


def fig3(src: sc.Sources) -> pd.DataFrame:
    """Figure 3: (a) the NA-06 tournament's daily IC (95% bootstrap CI) against the cost per 1,000 decisions,
    with MCS membership and the stage-2 screens; (b) val-B and test ICs of the final instruments and baselines
    (95% CIs from the Newey–West t), with their cost per 1,000 decisions."""
    t = src.frame(sc.TOURNAMENT)
    out = [
        sc.rows(
            t,
            sc.TOURNAMENT,
            panel="a",
            series="model",
            label="screen",
            role="=ic",
            x="kind",
            x_col="cost_per_1000_decisions",
            y_col="ic",
            ci="table",
            lo_col="ci_low",
            hi_col="ci_high",
        ),
        sc.rows(t, sc.TOURNAMENT, panel="a", series="model", role="=mcs_member", y_col="mcs_member"),
        sc.rows(t, sc.TOURNAMENT, panel="a", series="model", role="=stage2", y_col="stage2"),
    ]
    c = src.frame(T14).set_index("key", drop=False)
    for pos, (series, key) in enumerate(FIG3_ROWS):
        r = c.loc[[key]].copy()
        for split, col, tcol in (("val_b", "ic_val_b", "ic_val_b_t"), ("test", "ic_test", "ic_test_t")):
            out.append(
                sc.rows(
                    r,
                    T14,
                    panel="b",
                    series=f"={series}",
                    role=f"={split}",
                    x=f"={split}",
                    xv=float(pos),
                    y_col=col,
                    ci="t",
                    se_col=tcol,
                )
            )
        if pd.notna(r["cost_per_1000"].iloc[0]):
            out.append(
                sc.rows(
                    r,
                    T14,
                    panel="b",
                    series=f"={series}",
                    role="=cost",
                    x="=cost",
                    xv=float(pos),
                    y_col="cost_per_1000",
                )
            )
    return pd.concat(out, ignore_index=True)


T21: Final = f"{sc.TABLES}/t21_release_dates.csv"
FIG4_MODELS: Final = ("laya_fin", "d1_ultra", "span_02", "drex_v2", "anchor")
FIG4_RELEASES: Final = ("sample_end", "laya", "drex_v2", "d1_ultra", "span_02")


def fig4(src: sc.Sources) -> pd.DataFrame:
    """Figure 4: monthly mean daily IC of N̂_W0 with z_cc over val-A, val-B and test, and the release dates."""
    m = src.frame(sc.MONTHLY)
    m = m[m["model"].isin(FIG4_MODELS)]
    out = [
        sc.rows(
            m, sc.MONTHLY, panel="a", series="model", label="split", role="=monthly_ic", x="month", y_col="ic"
        )
    ]
    r = src.frame(T21)
    r = r[r["key"].isin(FIG4_RELEASES)]
    out.append(
        sc.rows(
            r,
            T21,
            panel="a",
            series="key",
            label="name",
            role="=release",
            x="date",
            y_col="days_after_sample_end",
        )
    )
    return pd.concat(out, ignore_index=True)


T13: Final = f"{sc.NA12_TAB}/t13_shapley.csv"
TIERS: Final = ("all", "top100", "mid", "rest")
GROUPS: Final = ("R", "N", "J", "R+N+J")


def fig5(src: sc.Sources) -> pd.DataFrame:
    """Figure 5: Shapley values of the out-of-sample R² and IC of y2 at D2 over the groups R, N, J, by tier,
    with the full model's total (t13). The shares are not drawn: their totals are about zero."""
    t = src.frame(T13)
    t = t[t["model"].isin(FIG1_MODELS) & t["tier"].isin(TIERS) & t["group"].isin(GROUPS)].copy()
    t["xpos"] = t["tier"].map({k: i for i, k in enumerate(TIERS)}).astype(float)
    out = []
    for panel, (metric, model) in zip(
        "abcdef", [(mt, m) for mt in ("r2", "ic") for m in FIG1_MODELS], strict=True
    ):
        d = t[(t["metric"] == metric) & (t["model"] == model)]
        out.append(
            sc.rows(
                d,
                T13,
                panel=panel,
                series="group",
                label=f"={model}",
                role=f"={metric}",
                x="tier",
                xv="xpos",
                y_col="shapley",
            )
        )
    return pd.concat(out, ignore_index=True)


NA03_SUMMARY: Final = "artifacts/NA-03/summary.json"


def fig6(src: sc.Sources) -> pd.DataFrame:
    """Figure 6: material recall against the share of days selected, per filter (NA-03 frontier on val-A),
    with
    the frozen filter at its budget (NA-03 summary)."""
    frozen = json.loads((src.root / NA03_SUMMARY).read_text(encoding="utf-8"))["frozen_filter"]
    f = src.frame(sc.FRONTIER)
    out = [
        sc.rows(
            f,
            sc.FRONTIER,
            panel="a",
            series="filter",
            role="=frontier",
            x="target_share",
            x_col="selected_share",
            y_col="recall_material",
        )
    ]
    pick = f[(f["filter"] == frozen["id"]) & np.isclose(f["target_share"], float(frozen["budget_share"]))]
    if len(pick) != 1:
        raise KeyError("the frozen filter's budget row is not in the frontier")
    out.append(
        sc.rows(
            pick,
            sc.FRONTIER,
            panel="a",
            series="filter",
            role="=chosen",
            x="target_share",
            x_col="selected_share",
            y_col="recall_material",
        )
    )
    return pd.concat(out, ignore_index=True)


T10: Final = f"{sc.NA12_TAB}/t10_explanation_ladder.csv"
T11: Final = f"{sc.NA12_TAB}/t11_explanation_share_theta.csv"
FIG8_CUTS: Final = ("all", "event_days", "tier:top100", "tier:mid", "tier:rest")
FIG8_STEPS: Final = ("ex_ante", "ex_post", "explanation")


def fig8(src: sc.Sources) -> pd.DataFrame:
    """Figure 8 (PREREG A3): (a) d1-ultra's out-of-sample R² of z_cc by step, stacked from the increments, by
    cut; (b) the news-only steps (cumulative R², 95% bootstrap CI) of the three instruments by tier;
    (c) persistence (mean sign(G)·y2, 95% CI) by the model's move_reason, with θ at D2."""
    t = src.frame(T10)
    out = []
    a = t[(t["model"] == "d1_ultra") & t["cut"].isin(FIG8_CUTS) & t["step"].isin(FIG8_STEPS)].copy()
    a["xpos"] = a["cut"].map({k: i for i, k in enumerate(FIG8_CUTS)}).astype(float)
    first = a[a["step"] == "ex_ante"]
    out.append(
        sc.rows(
            first, T10, panel="a", series="step", label="cut", role="=segment", x="cut", xv="xpos", y_col="r2"
        )
    )
    rest = a[a["step"] != "ex_ante"]
    out.append(
        sc.rows(
            rest,
            T10,
            panel="a",
            series="step",
            label="cut",
            role="=segment",
            x="cut",
            xv="xpos",
            y_col="increment",
        )
    )
    out.append(
        sc.rows(
            a,
            T10,
            panel="a",
            series="step",
            label="cut",
            role="=cumulative",
            x="cut",
            xv="xpos",
            y_col="r2",
            ci="table",
            lo_col="r2_ci_low",
            hi_col="r2_ci_high",
        )
    )
    out.append(
        sc.rows(
            t[t["key"] == "roll_r2"],
            T10,
            panel="a",
            series="=market+sector",
            role="=roll",
            x="cut",
            y_col="r2",
        )
    )
    cuts = ("all", "tier:top100", "tier:mid", "tier:rest")
    b = t[t["model"].isin(FIG1_MODELS) & t["cut"].isin(cuts) & t["step"].isin(FIG8_STEPS[:2])].copy()
    b["xpos"] = b["cut"].map({k: i for i, k in enumerate(cuts)}).astype(float)
    out.append(
        sc.rows(
            b,
            T10,
            panel="b",
            series="model",
            label="step",
            role="=news_step",
            x="cut",
            xv="xpos",
            y_col="r2",
            ci="table",
            lo_col="r2_ci_low",
            hi_col="r2_ci_high",
        )
    )
    s = src.frame(T11)
    p = s[s["key"].str.startswith("persistence:")].copy()
    p["reason"] = p["key"].str.removeprefix("persistence:")
    out.append(
        sc.rows(
            p,
            T11,
            panel="c",
            series="reason",
            label="reason",
            role="=persistence",
            x="reason",
            y_col="value",
            ci="table",
            lo_col="ci_low",
            hi_col="ci_high",
        )
    )
    th = s[s["key"] == "theta:d2"]
    out.append(
        sc.rows(
            th,
            T11,
            panel="c",
            series="=theta_d2",
            role="=theta",
            x="=theta",
            y_col="value",
            ci="se",
            se_col="se",
        )
    )
    return pd.concat(out, ignore_index=True)


# --- appendix -----------------------------------------------------------------------------------------------

T1B: Final = f"{sc.NA12_TAB}/t1b_primary_by_model.csv"
T3: Final = f"{sc.NA12_TAB}/t3_ic.csv"
T15: Final = f"{sc.NA12_TAB}/t15_calibration.csv"
T16: Final = f"{sc.NA12_TAB}/t16_robustness.csv"
T24: Final = f"{sc.TABLES}/t24_exploratory_d0_signal.csv"
T25: Final = f"{sc.TABLES}/t25_ma_cross.csv"
CAL_MODELS: Final = ("laya_fin", "anchor", "laya_zs", "d1_ultra", "span_02", "drex_v2")
SIGNALS: Final = ("laya_fin", "laya_zs", "d1_ultra", "span_02", "drex_v2", "sentiment", "tags_gbm")


def figa1(src: sc.Sources) -> pd.DataFrame:
    """Appendix A1: reliability of Q1's three classes against e5 (15 bins; NA-12), with each model's ECE
    (t15)."""
    r = src.frame(sc.RELIABILITY)
    r = r[(r["target"] == "e5") & (r["n"] > 0)]
    out = []
    for panel, model in zip("abcdef", CAL_MODELS, strict=True):
        d = r[r["model"] == model]
        out.append(
            sc.rows(
                d,
                sc.RELIABILITY,
                panel=panel,
                series=f"={model}",
                role="=hit_rate",
                x="bin",
                x_col="confidence",
                y_col="hit_rate",
            )
        )
        out.append(
            sc.rows(
                d,
                sc.RELIABILITY,
                panel=panel,
                series=f"={model}",
                role="=n",
                x="bin",
                x_col="confidence",
                y_col="n",
            )
        )
        e = src.frame(T15)
        out.append(
            sc.rows(
                e[e["key"] == f"{model}:e5"],
                T15,
                panel=panel,
                series=f"={model}",
                role="=ece",
                x="=ece",
                y_col="ece",
            )
        )
    return pd.concat(out, ignore_index=True)


def figa2(src: sc.Sources) -> pd.DataFrame:
    """Appendix A2: the encoding study (NA-07): daily IC by encoding on val-A (search) and val-B
    (confirmation)."""
    e = src.frame(sc.ENCODING)
    e = e[e["model"] != "pooled"].copy()
    e["xpos"] = e["encoding"].str.removeprefix("E").astype(float)
    out = []
    for panel, model in zip("abc", ("liquid/d1-ultra", "respan/span-02", "nace-ai/drex-v2.0"), strict=True):
        d = e[e["model"] == model]
        out.append(
            sc.rows(
                d,
                sc.ENCODING,
                panel=panel,
                series="split",
                label=f"={model}",
                role="=ic",
                x="encoding",
                xv="xpos",
                y_col="ic",
                ci="table",
                lo_col="ci_low",
                hi_col="ci_high",
            )
        )
        for flag in ("chosen", "best"):
            out.append(
                sc.rows(
                    d,
                    sc.ENCODING,
                    panel=panel,
                    series="split",
                    label=f"={model}",
                    role=f"={flag}",
                    x="encoding",
                    xv="xpos",
                    y_col=flag,
                )
            )
    return pd.concat(out, ignore_index=True)


def figa3(src: sc.Sources) -> pd.DataFrame:
    """Appendix A3: masking and identifiability (NA-11): company identification with activity-matched
    distractors
    against the matched baseline and the §8.3 bar; the probes' masked vs unmasked and real vs shuffled ICs."""
    c = src.frame(sc.COMPANY_ID)
    out = [
        sc.rows(c, sc.COMPANY_ID, panel="a", series="model", role="=accuracy", x="model", y_col="accuracy"),
        sc.rows(
            c, sc.COMPANY_ID, panel="a", series="model", role="=baseline", x="model", y_col="baseline_matched"
        ),
        sc.rows(
            c,
            sc.COMPANY_ID,
            panel="a",
            series="model",
            role="=threshold",
            x="model",
            y_col="screen_threshold",
        ),
    ]
    p = src.frame(sc.PROBES)
    api = p[p["ic_masked"].notna()]
    for role, col, tcol in (
        ("masked", "ic_masked", "ic_masked_t"),
        ("unmasked", "ic_unmasked", "ic_unmasked_t"),
    ):
        out.append(
            sc.rows(
                api,
                sc.PROBES,
                panel="b",
                series="model",
                role=f"={role}",
                x="model",
                y_col=col,
                ci="t",
                se_col=tcol,
            )
        )
    for role, col, tcol in (
        ("real", "ic_real_same_events", "ic_real_same_events_t"),
        ("shuffled", "ic_shuffled", "ic_shuffled_t"),
    ):
        out.append(
            sc.rows(
                p,
                sc.PROBES,
                panel="c",
                series="model",
                role=f"={role}",
                x="model",
                y_col=col,
                ci="t",
                se_col=tcol,
            )
        )
    return pd.concat(out, ignore_index=True)


def figa4(src: sc.Sources) -> pd.DataFrame:
    """Appendix A4: d1-ultra's Call B with the news removed and with shuffled news (S8 ablations; t16): IC of
    J, C and N̂ with y2, real against ablated on the same events (95% CI from the Newey–West t)."""
    t = src.frame(T16)
    out = []
    for panel, ab in (("a", "b2_no_news"), ("b", "b2_shuffled")):
        d = t[t["key"].str.startswith(f"d1_ultra:D2:{ab}:")].copy()
        parts = d["key"].str.split(":")
        d["feature"], d["kind"] = parts.str[3], parts.str[4]
        d["xpos"] = d["feature"].map({"j": 0.0, "c": 1.0, "n_hat": 2.0})
        out.append(
            sc.rows(
                d,
                T16,
                panel=panel,
                series="feature",
                role="kind",
                x="feature",
                xv="xpos",
                y_col="ic_y2",
                ci="t",
                se_col="ic_y2_t",
            )
        )
    return pd.concat(out, ignore_index=True)


FOREST_VARIANTS: Final = (
    "dollar_volume_tiers",
    "exclude_date_only_hour",
    "exclude_half_days",
    "non_overlapping",
    "exclude_delisting_flag",
    "without_price_move_text",
    "w0_cutoff_08:00_approx",
    "timing_before_04:00",
    "timing_04:00_08:00",
    "timing_08:00_09:15",
)
FOREST: Final = (
    ("a", "laya_fin", "H1"),
    ("b", "laya_fin", "H1b"),
    ("c", "laya_fin", "ic_z_cc"),
    ("d", "d1_ultra", "H1"),
)


def figa5(src: sc.Sources) -> pd.DataFrame:
    """Appendix A5: robustness forest (§11.6; t16): the D0 estimates by variant, raw (filled) and placebo-
    adjusted (hollow), with the main estimate on top (t1b; IC from t3) and 95% intervals."""
    t = src.frame(T16)
    out = []
    for panel, model, metric in FOREST:
        tcol = f"{metric}_t"
        rows = []
        for i, v in enumerate(FOREST_VARIANTS):
            for adj in ("raw", "placebo"):
                k = f"{model}:D0:{v}:{adj}"
                if (t["key"] == k).any():
                    rows.append((t[t["key"] == k], float(i + 1), adj))
        for d, pos, adj in rows:
            ok = pd.notna(d[tcol].iloc[0]) and pd.notna(d[metric].iloc[0])
            if pd.isna(d[metric].iloc[0]):
                continue
            out.append(
                sc.rows(
                    d,
                    T16,
                    panel=panel,
                    series=f"={model}",
                    label="variant",
                    role=f"={adj}",
                    x="variant",
                    xv=pos,
                    y_col=metric,
                    ci="t" if ok else "",
                    se_col=tcol if ok else "",
                )
            )
        if metric == "ic_z_cc":
            m = src.frame(T3)
            out.append(
                sc.rows(
                    m[m["key"] == f"{model}:z_cc"],
                    T3,
                    panel=panel,
                    series=f"={model}",
                    label="=main",
                    role="=main",
                    x="=main",
                    xv=0.0,
                    y_col="ic",
                    ci="table",
                    lo_col="ic_ci_low",
                    hi_col="ic_ci_high",
                )
            )
        else:
            m = src.frame(T1B)
            out.append(
                sc.rows(
                    m[m["key"] == f"{model}:{metric}"],
                    T1B,
                    panel=panel,
                    series=f"={model}",
                    label="=main",
                    role="=main",
                    x="=main",
                    xv=0.0,
                    y_col="estimate",
                    ci="table",
                    lo_col="ci_low",
                    hi_col="ci_high",
                )
            )
    return pd.concat(out, ignore_index=True)


def figa6(src: sc.Sources) -> pd.DataFrame:
    """Appendix A6, exploratory (post hoc; NA-12 §13 via t24): where the D0 signal lives: earnings-day events
    against the rest, the size tiers, and the per-company spread against its within-company shuffle null."""
    t = src.frame(T24).set_index("key", drop=False)
    out = []
    for i, s in enumerate(SIGNALS):
        for kind in ("earnings", "rest"):
            for split in ("val_b", "test"):
                k = f"earnings:{s}:{split}:{kind}"
                if k in t.index:
                    out.append(
                        sc.rows(
                            t.loc[[k]],
                            T24,
                            panel="a",
                            series=f"={s}",
                            label=f"={split}",
                            role=f"={kind}",
                            x=f"={split}",
                            xv=float(i),
                            y_col="ic_z_cc",
                            ci="table",
                            lo_col="ic_z_cc_ci_low",
                            hi_col="ic_z_cc_ci_high",
                        )
                    )
        for _j, tier in enumerate(("top100", "mid", "rest")):
            k = f"tier:{s}:test:{tier}"
            out.append(
                sc.rows(
                    t.loc[[k]],
                    T24,
                    panel="b",
                    series=f"={s}",
                    label=f"={tier}",
                    role="=tier",
                    x=f"={tier}",
                    xv=float(i),
                    y_col="ic_z_cc",
                    ci="table",
                    lo_col="ic_z_cc_ci_low",
                    hi_col="ic_z_cc_ci_high",
                )
            )
        k = f"company:{s}"
        out.append(
            sc.rows(t.loc[[k]], T24, panel="c", series=f"={s}", role="=sd", x="=sd", xv=float(i), y_col="sd")
        )
        out.append(
            sc.rows(
                t.loc[[k]],
                T24,
                panel="c",
                series=f"={s}",
                role="=null",
                x="=null",
                xv=float(i),
                y_col="null_sd_mean",
                ci="table",
                lo_col="null_sd_p2_5",
                hi_col="null_sd_p97_5",
            )
        )
    return pd.concat(out, ignore_index=True)


MA_GROUPS: Final = (
    "all",
    "none",
    "agree_laya_fin",
    "disagree_laya_fin",
    "agree_d1_ultra",
    "disagree_d1_ultra",
)
MA_FADE: Final = "exploratory|ma_cross|fade_no_news|close_t+5"


def figa7(src: sc.Sources) -> pd.DataFrame:
    """Appendix A7, exploratory (post hoc; NA-13 §9 via t25): the MA20/MA50-cross group means at 5 and 20
    days,
    validation against test (95% CI from the Newey–West t), and the tradable no-news fade on test (Figure 7
    data, cumulative net at 10 bp)."""
    t = src.frame(T25).set_index("key", drop=False)
    out = []
    for panel, h in (("a", 5), ("b", 20)):
        for i, g in enumerate(MA_GROUPS):
            for period in ("validation", "test"):
                k = f"periods:{period}:statistics:{g}|{h}"
                out.append(
                    sc.rows(
                        t.loc[[k]],
                        T25,
                        panel=panel,
                        series=f"={g}",
                        role=f"={period}",
                        x=f"={g}",
                        xv=float(i),
                        y_col="mean_bp",
                        ci="t",
                        se_col="nw_t",
                    )
                )
    f = src.frame(sc.FIG7)
    d = f[(f["rule"] == MA_FADE) & (f["series"] == "book")]
    out.append(sc.rows(d, sc.FIG7, panel="c", series="=fade", role="=book", x="session", y_col="cum_net_10"))
    return pd.concat(out, ignore_index=True)


BUILDERS: Final[Mapping[str, Callable[[sc.Sources], pd.DataFrame]]] = {
    "fig1_convergence": fig1,
    "fig2_drift_vs_move": fig2,
    "fig3_tournament": fig3,
    "fig4_monthly_ic": fig4,
    "fig5_shapley": fig5,
    "fig6_filters": fig6,
    "fig7_strategies": fig7,
    "fig8_explain_move": fig8,
    "figA1_reliability": figa1,
    "figA2_encoding": figa2,
    "figA3_identifiability": figa3,
    "figA4_ablations": figa4,
    "figA5_robustness": figa5,
    "figA6_exploratory_d0": figa6,
    "figA7_exploratory_ma_cross": figa7,
}


def csv_path(layout: Layout | None, name: str) -> Path:
    return resolve_layout(layout).root / sc.FIGURES / f"{name}.csv"


def write(layout: Layout | None = None, names: Sequence[str] | None = None) -> list[Path]:
    """Write each figure's CSV (all by default); refuse one whose rows do not trace to their sources."""
    lay = resolve_layout(layout)
    src = sc.Sources(lay.root)
    done = []
    for name in names or list(BUILDERS):
        df = BUILDERS[name](src)
        bad = sc.trace(df, src)
        if bad:
            raise ValueError(f"{name}: {len(bad)} rows do not trace to their sources, e.g. {bad[:3]}")
        path = csv_path(lay, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, lineterminator="\n")
        done.append(path)
    return done


def main(argv: Sequence[str] | None = None) -> int:
    for p in write(names=list(argv) if argv else None):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
