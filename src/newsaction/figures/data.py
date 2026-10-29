"""NA-14 S2: each figure's CSV, assembled from the upstream rows it plots (PRD NA-14 S2, AC3–AC4).

    uv run python -m newsaction.figures.data

Every builder selects rows of NA-03, NA-06, NA-07, NA-11, NA-12 and NA-13 outputs, or of the NA-14 tables
that copy or aggregate them (``sources``; NA-13b's exploratory tables only through their NA-14 copies), and
writes them in the long figure format with their provenance.
Nothing here estimates anything. The arithmetic is an interval: ±1.96 (or, in an exploratory figure, ±1)
stored standard errors, ±1.96 × |value / t| from a stored t, or the Wilson interval of a stored proportion
and its stored number of trials (``sources.rows``). Two NA-14 tables hold simple aggregations of stored
files, each recomputed by its test: the placebo's Sharpe quantiles (t33, from NA-13's placebo books) and the
break-even costs (t30, gross mean ÷ turnover from NA-13's strategy table). The figure modules then read only
their CSV.

The main figures (1–7) follow the paper's findings; the appendix figures (A1–A19) hold the rest, the
anchor and every exploratory panel (A16–A19: NA-13b, when the D0 signal works).
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

T1B: Final = f"{sc.NA12_TAB}/t1b_primary_by_model.csv"
T3: Final = f"{sc.NA12_TAB}/t3_ic.csv"
T6: Final = f"{sc.NA12_TAB}/t6_convergence_ladder.csv"
T7: Final = f"{sc.NA12_TAB}/t7_gap_closure.csv"
T10: Final = f"{sc.NA12_TAB}/t10_explanation_ladder.csv"
T11: Final = f"{sc.NA12_TAB}/t11_explanation_share_theta.csv"
T13: Final = f"{sc.NA12_TAB}/t13_shapley.csv"
T14: Final = f"{sc.NA12_TAB}/t14_model_comparison.csv"
T15: Final = f"{sc.NA12_TAB}/t15_calibration.csv"
T16: Final = f"{sc.NA12_TAB}/t16_robustness.csv"
T24: Final = f"{sc.TABLES}/t24_exploratory_d0_signal.csv"
T25: Final = f"{sc.TABLES}/t25_ma_cross.csv"
T33: Final = f"{sc.TABLES}/t33_placebo_sharpe.csv"
T36: Final = f"{sc.TABLES}/t36_selective_coverage.csv"
T37: Final = f"{sc.TABLES}/t37_watch_open.csv"
T38: Final = f"{sc.TABLES}/t38_conditioning.csv"
T40: Final = f"{sc.TABLES}/t40_conditioning_detail.csv"
T41: Final = f"{sc.TABLES}/t41_output_histograms.csv"
FA_RELIABILITY: Final = f"{sc.TABLES}/fa_reliability.csv"
NA03_SUMMARY: Final = "artifacts/NA-03/summary.json"

# Event-time rungs (PREREG A1.2): figure-data point → position on an axis that is not to scale.
RUNGS: Final = {
    "car_pre1": 0,
    "car_lvl_o0": 1,
    "car_lvl_10": 2,
    "car_post0": 3,
    "car_post1": 4,
    "car_post2": 5,
    "car_post5": 6,
    "car_post10": 7,
    "car_post20": 8,
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
RG_POINTS: Final = (
    "car_pre1",
    "car_post0",
    "car_post1",
    "car_post2",
    "car_post5",
    "car_post10",
    "car_post20",
)
G_BINS: Final = ("[0, 0.5)", "[0.5, 1)", "[1, 2)", "[2, 3)", "[3, inf)")
TERCILES: Final = ("weak", "medium", "strong")


def _pos(points: pd.Series) -> np.ndarray:
    return points.map(RUNGS).to_numpy(dtype=float)


def _one(df: pd.DataFrame, mask: pd.Series, what: str) -> pd.DataFrame:
    hit = df[mask]
    if len(hit) != 1:
        raise KeyError(f"{what}: {len(hit)} rows, not one")
    return hit


# --- Figure 1: validation against test -------------------------------------------------------------------

# (row id, group, t14 key), top to bottom. The anchor is uninformative and stays in the appendix.
FIG1_ROWS: Final = (
    ("laya_fin", "trained", "laya_fin"),
    ("laya_zs", "zero-shot", "laya_zs"),
    ("d1_ultra", "api", "d1_ultra"),
    ("span_02", "api", "span_02"),
    ("drex_v2", "api", "drex_v2"),
    ("price_only", "baseline", "baseline:price_only"),
    ("embed_ridge", "baseline", "baseline:embed_ridge"),
    ("llm", "baseline", "baseline:llm"),
    ("sentiment", "baseline", "baseline:sentiment"),
    ("tags_gbm", "baseline", "baseline:tags_gbm"),
)


def fig1(src: sc.Sources) -> pd.DataFrame:
    """Figure 1: the daily IC of N̂_W0 with z_cc on val-B (panel a) and on test (panel b) for each instrument
    and baseline, with 95% intervals from the Newey–West t (NA-12 t14)."""
    c = src.frame(T14)
    out = []
    for pos, (series, group, key) in enumerate(FIG1_ROWS):
        r = _one(c, c["key"] == key, key)
        for split, col in (("val_b", "ic_val_b"), ("test", "ic_test")):
            out.append(
                sc.rows(
                    r,
                    T14,
                    panel="a" if split == "val_b" else "b",
                    series=f"={series}",
                    label=f"={group}",
                    role=f"={split}",
                    x=f"={split}",
                    xv=float(pos),
                    y_col=col,
                    ci="t",
                    se_col=f"{col}_t",
                )
            )
    return pd.concat(out, ignore_index=True)


# --- Figure 2: priced at the open ---------------------------------------------------------------------------

FIG2_MODELS: Final = ("laya_fin", "laya_zs", "d1_ultra", "span_02", "drex_v2")


def fig2(src: sc.Sources) -> pd.DataFrame:
    """Figure 2: the daily IC of N̂_W0 with (a) the overnight move z_on and (b) the move after the open z_id
    (NA-12 t3, 95% bootstrap intervals); (c) H1, their difference (t1b, 95% bootstrap interval)."""
    t3, t1b = src.frame(T3), src.frame(T1B)
    out = []
    for pos, model in enumerate(FIG2_MODELS):
        for target in ("z_on", "z_id"):
            r = _one(t3, t3["key"] == f"{model}:{target}", f"t3 {model}:{target}")
            out.append(
                sc.rows(
                    r,
                    T3,
                    panel="a" if target == "z_on" else "b",
                    series=f"={model}",
                    role=f"={target}",
                    x=f"={target}",
                    xv=float(pos),
                    y_col="ic",
                    ci="table",
                    lo_col="ic_ci_low",
                    hi_col="ic_ci_high",
                )
            )
        r = _one(t1b, t1b["key"] == f"{model}:H1", f"t1b {model}:H1")
        out.append(
            sc.rows(
                r,
                T1B,
                panel="c",
                series=f"={model}",
                role="=H1",
                x="=H1",
                xv=float(pos),
                y_col="estimate",
                ci="table",
                lo_col="ci_low",
                hi_col="ci_high",
            )
        )
    return pd.concat(out, ignore_index=True)


# --- Figure 3: convergence ----------------------------------------------------------------------------------


def _deciles(src: sc.Sources, model: str, groups: Sequence[int], panel: str) -> list[pd.DataFrame]:
    v = src.frame(sc.V_DECILES)
    d = v[(v["model"] == model) & (v["figure"] == "v_decile") & v["group"].isin(list(groups))]
    d = d[d["point"].isin(list(RUNGS))].copy()
    d["xpos"] = _pos(d["point"])
    d["series"] = "decile_" + d["group"].astype(str)
    out = [
        sc.rows(
            d,
            sc.V_DECILES,
            panel=panel,
            series="series",
            label=f"={model}",
            role="=path",
            x="point",
            xv="xpos",
            y_col="mean",
            ci="se",
            se_col="se",
        )
    ]
    t = d[d["point"] == "car_post0"]
    out.append(
        sc.rows(
            t,
            sc.V_DECILES,
            panel=panel,
            series="series",
            label=f"={model}",
            role="=target",
            x="=target",
            y_col="mean_v",
        )
    )
    return out


def _ladder(src: sc.Sources, models: Sequence[str], panel: str) -> list[pd.DataFrame]:
    t6 = src.frame(T6)
    out = []
    for model in models:
        d = t6[
            (t6["model"] == model) & (t6["variant"] == "ladder") & t6["rung"].isin(list(LADDER_RUNGS))
        ].copy()
        d["xpos"] = _pos(d["rung"].map(LADDER_RUNGS))
        out.append(
            sc.rows(
                d,
                T6,
                panel=panel,
                series=f"={model}",
                role="=kappa",
                x="rung",
                xv="xpos",
                y_col="kappa",
                ci="se",
                se_col="kappa_se",
            )
        )
    t7 = src.frame(T7)
    h = t7[t7["key"].isin([f"{m}:{p}:all:half_life" for m in models for p in ("D2", "D1")])]
    out.append(
        sc.rows(
            h,
            T7,
            panel=panel,
            series="model",
            label="point",
            role="=half_life",
            x="=half_life",
            y_col="lambda",
        )
    )
    return out


def fig3(src: sc.Sources) -> pd.DataFrame:
    """Figure 3: (a) d1-ultra's top and bottom V deciles, CAR^lvl from the previous close with ±1.96
    event-level SE bands, against each decile's mean V (NA-12 figure data); (b) the convergence ladder κ_h of
    Laya-Fin and d1-ultra with 95% intervals (t6) and the gap's half-life (t7)."""
    out = _deciles(src, "d1_ultra", (1, 10), "a")
    out += _ladder(src, ("laya_fin", "d1_ultra"), "b")
    return pd.concat(out, ignore_index=True)


# --- Figure 4: over- and under-reaction -------------------------------------------------------------------


def _rg(src: sc.Sources, model: str, panel: str) -> list[pd.DataFrame]:
    rg = src.frame(sc.RG_CLASSES)
    d = rg[
        (rg["model"] == model) & (rg["figure"] == "rg_class_signed") & rg["point"].isin(list(RG_POINTS))
    ].copy()
    d["xpos"] = _pos(d["point"])
    out = [
        sc.rows(
            d,
            sc.RG_CLASSES,
            panel=panel,
            series="group",
            label=f"={model}",
            role="=path",
            x="point",
            xv="xpos",
            y_col="mean",
            ci="se",
            se_col="se",
        )
    ]
    t = d[d["point"] == "car_post0"]
    out.append(
        sc.rows(
            t,
            sc.RG_CLASSES,
            panel=panel,
            series="group",
            label=f"={model}",
            role="=target",
            x="=target",
            y_col="mean_v",
        )
    )
    out.append(
        sc.rows(
            t,
            sc.RG_CLASSES,
            panel=panel,
            series="group",
            label=f"={model}",
            role="=n_events",
            x="=n",
            y_col="n_group",
        )
    )
    return out


def _drift(src: sc.Sources, model: str, panel: str) -> pd.DataFrame:
    d = src.frame(sc.DRIFT)
    d = d[d["model"] == model].copy()
    d["xpos"] = d["g_bin"].map({b: i for i, b in enumerate(G_BINS)}).astype(float)
    return sc.rows(
        d,
        sc.DRIFT,
        panel=panel,
        series="tercile",
        label=f"={model}",
        role="=drift",
        x="g_bin",
        xv="xpos",
        y_col="mean",
        ci="se",
        se_col="se",
    )


def fig4(src: sc.Sources) -> pd.DataFrame:
    """Figure 4: (a) d1-ultra's D2 events by RG class (Under, Fair, Over), sign(N̂)·CAR^lvl with ±1.96 SE
    bands, against each class's mean signed V; (b) d1-ultra's drift sign(G)·y2 by |G| bin within terciles of
    news strength |V| (NA-12 figure data)."""
    out = _rg(src, "d1_ultra", "a")
    out.append(_drift(src, "d1_ultra", "b"))
    return pd.concat(out, ignore_index=True)


# --- Figure 5: explaining moves -----------------------------------------------------------------------------

FIG5_CUTS: Final = ("all", "event_days", "tier:top100", "tier:mid", "tier:rest")


FIG5_STEPS: Final = ("ex_ante", "ex_post", "explanation")


def fig5(src: sc.Sources) -> pd.DataFrame:
    """Figure 5 (PREREG A3; NA-12 t10): (a) d1-ultra's out-of-sample R² of z_cc by cut, stacked by step: the
    ex-ante (D0) news' R², then the stored increments of the same-day news and of the explanation (Call B
    sees the move), with each bar's total and its 95% bootstrap interval; (b) the news steps on their own
    scale, the R² after the ex-ante and after the same-day news, for Laya-Fin and d1-ultra (all covered
    member-days)."""
    t = src.frame(T10)
    out = []
    for pos, cut in enumerate(FIG5_CUTS):
        for step in FIG5_STEPS:
            r = _one(t, t["key"] == f"d1_ultra:{cut}:{step}", f"t10 d1_ultra:{cut}:{step}")
            out.append(
                sc.rows(
                    r,
                    T10,
                    panel="a",
                    series=f"={step}",
                    label="=d1_ultra",
                    role="=segment",
                    x=f"={cut}",
                    xv=float(pos),
                    y_col="r2" if step == "ex_ante" else "increment",
                )
            )
        r = _one(t, t["key"] == f"d1_ultra:{cut}:explanation", f"t10 d1_ultra:{cut}:explanation")
        out.append(
            sc.rows(
                r,
                T10,
                panel="a",
                series="=explanation",
                label="=d1_ultra",
                role="=total",
                x=f"={cut}",
                xv=float(pos),
                y_col="r2",
                ci="table",
                lo_col="r2_ci_low",
                hi_col="r2_ci_high",
            )
        )
    for model in ("laya_fin", "d1_ultra"):
        for pos, step in enumerate(FIG5_STEPS[:2]):
            r = _one(t, t["key"] == f"{model}:all:{step}", f"t10 {model}:all:{step}")
            out.append(
                sc.rows(
                    r,
                    T10,
                    panel="b",
                    series=f"={model}",
                    role=f"={step}",
                    x=f"={step}",
                    xv=float(pos),
                    y_col="r2",
                    ci="table",
                    lo_col="r2_ci_low",
                    hi_col="r2_ci_high",
                )
            )
    return pd.concat(out, ignore_index=True)


# --- Figure 6: strategies -----------------------------------------------------------------------------------

# (book group, series, NA-13 rule): each family at the exit of its hypothesis' horizon (S-CONV and S-D2 at
# t+5, S-D0 and S-D1 at the close); the gap fade is S-CONV's benchmark.
FIG6_BOOKS: Final = (
    ("S-CONV", "laya_fin", "S-CONV|laya_fin|D2|u|close_t+5|all"),
    ("S-CONV", "d1_ultra", "S-CONV|d1_ultra|D2|u|close_t+5|all"),
    ("S-CONV", "gap_fade", "gap_fade|-|D2|gap|close_t+5|all"),
    ("S-D0", "laya_fin", "S-D0|laya_fin|D0|n_tilde|close_t|all"),
    ("S-D0", "d1_ultra", "S-D0|d1_ultra|D0|n_tilde|close_t|all"),
    ("S-D1", "laya_fin", "S-D1|laya_fin|D1|j|close_t|all"),
    ("S-D1", "d1_ultra", "S-D1|d1_ultra|D1|j|close_t|all"),
    ("S-D2", "laya_fin", "S-D2|laya_fin|D2|j|close_t+5|all"),
    ("S-D2", "d1_ultra", "S-D2|d1_ultra|D2|j|close_t+5|all"),
)
FIG6_PATHS: Final = FIG6_BOOKS[:3]


def _test_rule(src: sc.Sources, rule: str) -> pd.DataFrame:
    st = src.frame(sc.STRATEGY)
    return _one(st, (st["split"] == "test") & (st["rule"] == rule), f"test {rule}")


def _paths(
    src: sc.Sources, books: Sequence[tuple[str, str, str]], panel: str, tier: str = "all"
) -> list[pd.DataFrame]:
    f = src.frame(sc.FIG7)
    out = []
    for _, series, rule in books:
        d = f[(f["rule"] == rule) & (f["tier"] == tier) & (f["series"] == "book")]
        if d.empty:
            raise KeyError(f"{rule} {tier}: no Figure 7 series")
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
    return out


def _band(src: sc.Sources, rule: str, panel: str) -> pd.DataFrame:
    f = src.frame(sc.FIG7)
    universe = str(_test_rule(src, rule)["universe"].iloc[0])
    band = f[(f["rule"] == f"placebo|{universe}") & (f["series"] == "placebo_band")]
    return sc.rows(
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


def fig6(src: sc.Sources) -> pd.DataFrame:
    """Figure 6: (a, b) the annualized gross and net (10 bp per side) Sharpe ratio of each main book of
    Laya-Fin and d1-ultra and of the gap fade, test period (NA-13 strategy table), against the 5th–95th
    percentile of its 100 random-signal books (t33); (c) S-CONV's cumulative net return at 10 bp against the
    gap fade, with the placebo's 5th–95th percentile band (NA-13 Figure 7 data)."""
    t33 = src.frame(T33)
    out = []
    for pos, (group, series, rule) in enumerate(FIG6_BOOKS):
        r = _test_rule(src, rule)
        universe = str(r["universe"].iloc[0])
        p = _one(t33, t33["key"] == universe, f"t33 {universe}")
        for panel, col, q in (("a", "sharpe_gross", "sharpe_gross"), ("b", "sharpe_net_10", "sharpe_net_10")):
            out.append(
                sc.rows(
                    r,
                    sc.STRATEGY,
                    panel=panel,
                    series=f"={series}",
                    label=f"={group}",
                    role="=book",
                    x="=" + rule,
                    xv=float(pos),
                    y_col=col,
                )
            )
            out.append(
                sc.rows(
                    p,
                    T33,
                    panel=panel,
                    series=f"={series}",
                    label=f"={group}",
                    role="=placebo",
                    x="=" + rule,
                    xv=float(pos),
                    y_col=f"{q}_q50",
                    ci="table",
                    lo_col=f"{q}_q05",
                    hi_col=f"{q}_q95",
                )
            )
    out += _paths(src, FIG6_PATHS, "c")
    out.append(_band(src, FIG6_PATHS[0][2], "c"))
    return pd.concat(out, ignore_index=True)


# --- Figure 7: memorisation ---------------------------------------------------------------------------------


def fig7(src: sc.Sources) -> pd.DataFrame:
    """Figure 7: company identification on masked val-A states with activity-matched distractors (NA-11): each
    model's share of correct identifications with its Wilson 95% interval (from the share and the valid
    answers), the matched baseline and the §8.3 screening threshold."""
    c = src.frame(sc.COMPANY_ID)
    out = [
        sc.rows(
            c,
            sc.COMPANY_ID,
            panel="a",
            series="model",
            role="=accuracy",
            x="model",
            y_col="accuracy",
            ci="wilson",
            se_col="valid",
        )
    ]
    ref = c[c["model"] == "liquid/d1-ultra"]
    out.append(
        sc.rows(
            ref,
            sc.COMPANY_ID,
            panel="a",
            series="=reference",
            role="=baseline",
            x="=baseline",
            y_col="baseline_matched",
        )
    )
    out.append(
        sc.rows(
            ref,
            sc.COMPANY_ID,
            panel="a",
            series="=reference",
            role="=screen",
            x="=screen",
            y_col="screen_threshold",
        )
    )
    return pd.concat(out, ignore_index=True)


# --- appendix -----------------------------------------------------------------------------------------------


def figa1(src: sc.Sources) -> pd.DataFrame:
    """Appendix A1: the zero-shot tournament on NA-06's val-A stage-1 sample: daily IC of Call A's N̂ with z_cc
    (95% bootstrap interval) against the cost per 1,000 decisions, with membership of the model confidence set
    and the stage-2 screens."""
    t = src.frame(sc.TOURNAMENT)
    return pd.concat(
        [
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
        ],
        ignore_index=True,
    )


def figa2(src: sc.Sources) -> pd.DataFrame:
    """Appendix A2: material recall against the share of days selected, per importance filter (NA-03 frontier
    on val-A), with the frozen filter at its budget (NA-03 summary)."""
    frozen = json.loads((src.root / NA03_SUMMARY).read_text(encoding="utf-8"))["frozen_filter"]
    f = src.frame(sc.FRONTIER)
    pick = f[(f["filter"] == frozen["id"]) & np.isclose(f["target_share"], float(frozen["budget_share"]))]
    if len(pick) != 1:
        raise KeyError("the frozen filter's budget row is not in the frontier")
    return pd.concat(
        [
            sc.rows(
                f,
                sc.FRONTIER,
                panel="a",
                series="filter",
                role="=frontier",
                x="target_share",
                x_col="selected_share",
                y_col="recall_material",
            ),
            sc.rows(
                pick,
                sc.FRONTIER,
                panel="a",
                series="filter",
                role="=chosen",
                x="target_share",
                x_col="selected_share",
                y_col="recall_material",
            ),
        ],
        ignore_index=True,
    )


ENCODING_MODELS: Final = ("liquid/d1-ultra", "respan/span-02", "nace-ai/drex-v2.0")


def figa3(src: sc.Sources) -> pd.DataFrame:
    """Appendix A3: the encodings of numbers in states (NA-07): daily IC by encoding on val-A (search) and the
    val-B confirmation (95% bootstrap intervals), with the chosen encoding."""
    e = src.frame(sc.ENCODING)
    e = e[e["model"] != "pooled"].copy()
    e["xpos"] = e["encoding"].str.removeprefix("E").astype(float)
    out = []
    for panel, model in zip("abc", ENCODING_MODELS, strict=True):
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
        out.append(
            sc.rows(
                d,
                sc.ENCODING,
                panel=panel,
                series="split",
                label=f"={model}",
                role="=chosen",
                x="encoding",
                xv="xpos",
                y_col="chosen",
            )
        )
    return pd.concat(out, ignore_index=True)


CAL_MODELS: Final = ("laya_fin", "anchor", "laya_zs", "d1_ultra", "span_02", "drex_v2")


def figa4(src: sc.Sources) -> pd.DataFrame:
    """Appendix A4: reliability of Q1's three classes against e5 (15 bins; NA-12 figure data), with each
    model's ECE (t15)."""
    r = src.frame(sc.RELIABILITY)
    r = r[(r["target"] == "e5") & (r["n"] > 0)]
    e = src.frame(T15)
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
    """Appendix A5: robustness of the D0 results (§11.6; t16): each variant raw and placebo-adjusted with 95%
    intervals from the Newey–West t, below the main estimate (t1b; the IC from t3) and its bootstrap
    interval."""
    t = src.frame(T16)
    out = []
    for panel, model, metric in FOREST:
        tcol = f"{metric}_t"
        for i, v in enumerate(FOREST_VARIANTS):
            for adj in ("raw", "placebo"):
                d = t[t["key"] == f"{model}:D0:{v}:{adj}"]
                if d.empty or pd.isna(d[metric].iloc[0]):
                    continue
                ok = pd.notna(d[tcol].iloc[0])
                out.append(
                    sc.rows(
                        d,
                        T16,
                        panel=panel,
                        series=f"={model}",
                        label="variant",
                        role=f"={adj}",
                        x="variant",
                        xv=float(i + 1),
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


MONTHLY_MODELS: Final = ("laya_fin", "d1_ultra")


def figa6(src: sc.Sources) -> pd.DataFrame:
    """Appendix A6, exploratory: the monthly mean of the daily IC of N̂_W0 with z_cc over val-A, val-B and
    test, with ±1 implied standard error of a month's mean (NA-12 §13.3 via t24, exploratory). The release
    dates, all after the sample, are in the caption (t21), not on the time axis."""
    t = src.frame(T24)
    out = []
    for model in MONTHLY_MODELS:
        d = t[t["key"].str.match(rf"^monthly:{model}:(val_a|val_b|test):months:\d+$")].copy()
        d["split"] = d["key"].str.split(":").str[2]
        out.append(
            sc.rows(
                d,
                T24,
                panel="a",
                series=f"={model}",
                label="split",
                role="=monthly_ic",
                x="month",
                y_col="ic",
                ci="se1",
                se_col="se",
            )
        )
    return pd.concat(out, ignore_index=True)


def figa7(src: sc.Sources) -> pd.DataFrame:
    """Appendix A7: convergence in detail: (a) Laya-Fin's and (b) d1-ultra's ten V deciles, CAR^lvl from the
    previous close (±1.96 SE bands on the extreme deciles) against their mean V (NA-12 figure data); (c) the
    ladder κ_h of the three trained and API instruments, the anchor included (t6), with the half-lives
    (t7)."""
    out = _deciles(src, "laya_fin", range(1, 11), "a")
    out += _deciles(src, "d1_ultra", range(1, 11), "b")
    out += _ladder(src, ("laya_fin", "d1_ultra", "anchor"), "c")
    return pd.concat(out, ignore_index=True)


def figa8(src: sc.Sources) -> pd.DataFrame:
    """Appendix A8: Laya-Fin's drift sign(G)·y2 by |G| bin within terciles of news strength |V| (Figure 4 (b)
    for the primary instrument; NA-12 figure data)."""
    return _drift(src, "laya_fin", "a")


SHAPLEY_GROUPS: Final = ("R", "N", "J", "total")
SHAPLEY_MODELS: Final = ("laya_fin", "d1_ultra", "anchor")
SHAPLEY_TIERS: Final = ("all", "top100", "mid", "rest")


def figa9(src: sc.Sources) -> pd.DataFrame:
    """Appendix A9: exact Shapley values of the out-of-sample R² (panels a–c) and of the mean daily IC (d–f)
    of y2 at D2 over the feature groups R, N and J, with the full model's total, for all member-days and by
    tier; one panel per instrument (t13)."""
    t = src.frame(T13)
    out = []
    panels = iter("abcdef")
    for metric in ("r2", "ic"):
        for model in SHAPLEY_MODELS:
            keys = [f"{model}:{tier}:{metric}:{g}" for tier in SHAPLEY_TIERS for g in SHAPLEY_GROUPS]
            d = t.set_index("key").loc[keys].reset_index()
            d["xpos"] = d["tier"].map({k: float(i) for i, k in enumerate(SHAPLEY_TIERS)})
            out.append(
                sc.rows(
                    d,
                    T13,
                    panel=next(panels),
                    series="group",
                    label=f"={model}",
                    role=f"={metric}",
                    x="tier",
                    xv="xpos",
                    y_col="shapley",
                )
            )
    return pd.concat(out, ignore_index=True)


def figa10(src: sc.Sources) -> pd.DataFrame:
    """Appendix A10: d1-ultra's Call B with the news removed and with shuffled news (S8; t16): IC of J, C
    and N̂
    with y2, real against ablated on the same events (95% intervals from the Newey–West t)."""
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


def figa11(src: sc.Sources) -> pd.DataFrame:
    """Appendix A11: persistence after D2, mean sign(G)·y2 by d1-ultra's move_reason (95% intervals), and θ,
    the D2 regression of persistence on being explained (t11)."""
    s = src.frame(T11)
    p = s[s["key"].str.startswith("persistence:")].copy()
    p["reason"] = p["key"].str.removeprefix("persistence:")
    th = s[s["key"] == "theta:d2"]
    return pd.concat(
        [
            sc.rows(
                p,
                T11,
                panel="a",
                series="reason",
                label="reason",
                role="=persistence",
                x="reason",
                y_col="value",
                ci="table",
                lo_col="ci_low",
                hi_col="ci_high",
            ),
            sc.rows(
                th,
                T11,
                panel="a",
                series="=theta_d2",
                role="=theta",
                x="=theta",
                y_col="value",
                ci="se",
                se_col="se",
            ),
        ],
        ignore_index=True,
    )


A12_PANELS: Final = (
    (
        "a",
        (
            ("S-D0", "laya_fin", "S-D0|laya_fin|D0|n_tilde|close_t|all"),
            ("S-D0", "d1_ultra", "S-D0|d1_ultra|D0|n_tilde|close_t|all"),
            ("S-D0", "sentiment", "vendor_sentiment|-|D0|sentiment|close_t|all"),
        ),
    ),
    (
        "b",
        (
            ("S-D1", "laya_fin", "S-D1|laya_fin|D1|j|close_t|all"),
            ("S-D1", "d1_ultra", "S-D1|d1_ultra|D1|j|close_t|all"),
            ("S-D1", "gap_fade", "gap_fade|-|D1|gap|close_t|all"),
        ),
    ),
    (
        "c",
        (
            ("S-D2", "laya_fin", "S-D2|laya_fin|D2|j|close_t+5|all"),
            ("S-D2", "d1_ultra", "S-D2|d1_ultra|D2|j|close_t+5|all"),
            ("S-D2", "gap_fade", "gap_fade|-|D2|gap|close_t+5|all"),
        ),
    ),
)
A12_TIERS: Final = (("d", "top100"), ("e", "mid"), ("f", "rest"))
A12_TIER_BOOKS: Final = (
    ("S-CONV", "laya_fin", "S-CONV|laya_fin|D2|u|close_t+5|all"),
    ("S-CONV", "gap_fade", "gap_fade|-|D2|gap|close_t+5|all"),
)


def figa12(src: sc.Sources) -> pd.DataFrame:
    """Appendix A12: cumulative net returns at 10 bp per side on test (NA-13 Figure 7 data): (a) S-D0, (b)
    S-D1
    J and (c) S-D2 J with their benchmarks and the placebo's 5th–95th percentile band of Laya-Fin's universe;
    (d–f) Laya-Fin's S-CONV and the gap fade by tier (descriptive sub-books)."""
    out = []
    for panel, books in A12_PANELS:
        out += _paths(src, books, panel)
        out.append(_band(src, books[0][2], panel))
    for panel, tier in A12_TIERS:
        rows = _paths(src, A12_TIER_BOOKS, panel, tier)
        out += [r.assign(role=tier) for r in rows]
    return pd.concat(out, ignore_index=True)


def figa13(src: sc.Sources) -> pd.DataFrame:
    """Appendix A13, exploratory: the probes' descriptive columns (NA-11, val-A): (a) ICs on masked and
    unmasked
    states; (b) ICs on real and shuffled news on the same events (95% intervals from the Newey–West t)."""
    p = src.frame(sc.PROBES)
    api = p[p["ic_masked"].notna()]
    out = []
    for role, col in (("masked", "ic_masked"), ("unmasked", "ic_unmasked")):
        out.append(
            sc.rows(
                api,
                sc.PROBES,
                panel="a",
                series="model",
                role=f"={role}",
                x="model",
                y_col=col,
                ci="t",
                se_col=f"{col}_t",
            )
        )
    for role, col in (("real", "ic_real_same_events"), ("shuffled", "ic_shuffled")):
        out.append(
            sc.rows(
                p,
                sc.PROBES,
                panel="b",
                series="model",
                role=f"={role}",
                x="model",
                y_col=col,
                ci="t",
                se_col=f"{col}_t",
            )
        )
    return pd.concat(out, ignore_index=True)


SIGNALS: Final = ("laya_fin", "laya_zs", "d1_ultra", "span_02", "drex_v2", "sentiment", "tags_gbm")


def figa14(src: sc.Sources) -> pd.DataFrame:
    """Appendix A14, exploratory (post hoc; NA-12 §13 via t24): where the D0 signal lives: earnings-day events
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
        for tier in ("top100", "mid", "rest"):
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


def figa15(src: sc.Sources) -> pd.DataFrame:
    """Appendix A15, exploratory (post hoc; NA-13 §9 via t25): the MA20/MA50-cross group means at 5 and 20
    days, validation against test (95% intervals from the Newey–West t), and the tradable no-news fade on test
    (NA-13 Figure 7 data, cumulative net at 10 bp)."""
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


# --- NA-13b (exploratory, post hoc): when the D0 signal works ----------------------------------------------

SELECTIVE_MODELS: Final = ("laya_fin", "d1_ultra", "span_02", "drex_v2", "laya_zs")
INSTRUMENTS: Final = ("laya_fin", "d1_ultra")  # drawn in colour, with their intervals
SPLITS: Final = ("val_a", "val_b", "test")
# (panel, target, column of t36): the rows of Figure A16
COVERAGE_PANELS: Final = (("a", "z_on", "signed"), ("b", "z_id", "signed"), ("c", "z_cc", "hit"))
WATCH_STATISTICS: Final = ("ic_pre_open", "ic_ten", "ic_revision")
CONDITION_FLAGS: Final = ("selected", "seen_on_test", "vendor")
OUTPUT_MEASURES: Final = (("a", "n_hat"), ("b", "conf"))


def figa16(src: sc.Sources) -> pd.DataFrame:
    """Appendix A16, exploratory (post hoc; NA-13b via t36): risk-coverage curves of the D0 reading, the mean
    signed z_on (a) and z_id (b) and the hit rate against z_cc (c) of the events kept at each coverage, on
    val-A, val-B and test, ranked by conviction |N̂| for every model (95% bootstrap intervals for Laya-Fin and
    d1-ultra) and by the stated confidence for Laya-Fin and d1-ultra (thresholds from val-A)."""
    t = src.frame(T36)
    out = []
    for panel, target, col in COVERAGE_PANELS:
        for ranking, models in (("conviction", SELECTIVE_MODELS), ("confidence", INSTRUMENTS)):
            for model in models:
                d = t[(t["model"] == model) & (t["ranking"] == ranking) & (t["target"] == target)]
                band = ranking == "conviction" and model in INSTRUMENTS
                out.append(
                    sc.rows(
                        d,
                        T36,
                        panel=panel,
                        series=f"={model}",
                        label="split",
                        role=f"={ranking}",
                        x=f"={target}",
                        x_col="coverage",
                        y_col=col,
                        ci="table" if band else "",
                        lo_col=f"{col}_ci_low" if band else "",
                        hi_col=f"{col}_ci_high" if band else "",
                    )
                )
    return pd.concat(out, ignore_index=True)


def figa17(src: sc.Sources) -> pd.DataFrame:
    """Appendix A17, exploratory (post hoc; NA-13b via t37): watching the open, the daily IC with y1 of the
    pre-open reading N̂_D0, of the 10:00 reading N̂_D1 and of their revision for Laya-Fin (a) and d1-ultra (b)
    on val-A, val-B and test, with the stored 95% intervals (mean ± 1.96 Newey–West SE)."""
    t = src.frame(T37)
    out = []
    for panel, model in (("a", "laya_fin"), ("b", "d1_ultra")):
        for i, split in enumerate(SPLITS):
            d = t[(t["model"] == model) & (t["split"] == split) & t["statistic"].isin(list(WATCH_STATISTICS))]
            out.append(
                sc.rows(
                    d,
                    T37,
                    panel=panel,
                    series=f"={model}",
                    role="statistic",
                    x=f"={split}",
                    xv=float(i),
                    y_col="value",
                    ci="table",
                    lo_col="ci_low",
                    hi_col="ci_high",
                )
            )
    return pd.concat(out, ignore_index=True)


def figa18(src: sc.Sources) -> pd.DataFrame:
    """Appendix A18, exploratory (post hoc; NA-13b via t40 and t38): the conditioning study, the
    inside-minus-outside difference of the primary outcome sign(N̂)·z_id for every condition E1–E9 on val-A,
    val-B and test (95% intervals from the t), for Laya-Fin (a) and d1-ultra (b), with each pair's validation
    selection, its [seen on test] mark and its vendor-field mark (t38)."""
    detail, pairs = src.frame(T40), src.frame(T38)
    order = {c: float(i) for i, c in enumerate(dict.fromkeys(pairs["condition"]))}
    out = []
    for panel, model in (("a", "laya_fin"), ("b", "d1_ultra")):
        d = detail[
            (detail["model"] == model) & (detail["outcome"] == "z_id") & detail["split"].isin(list(SPLITS))
        ].copy()
        d["xpos"] = d["condition"].map(order)
        out.append(
            sc.rows(
                d,
                T40,
                panel=panel,
                series=f"={model}",
                label="group",
                role="split",
                x="condition",
                xv="xpos",
                y_col="diff",
                ci="t",
                se_col="diff_t",
            )
        )
        p = pairs[pairs["model"] == model].copy()
        p["xpos"] = p["condition"].map(order)
        for flag in CONDITION_FLAGS:
            out.append(
                sc.rows(
                    p,
                    T38,
                    panel=panel,
                    series=f"={model}",
                    label="group",
                    role=f"={flag}",
                    x="condition",
                    xv="xpos",
                    y_col=flag,
                )
            )
    return pd.concat(out, ignore_index=True)


def figa19(src: sc.Sources) -> pd.DataFrame:
    """Appendix A19, exploratory (post hoc; NA-13b via t41): each model's outputs, the share of its events per
    bin of N̂ (a) and of the stated confidence (b) on val-A, val-B and test (bins from val-A), beside NA-12's
    reliability diagram on test (c): the hit rate of Q1's top class against e5 by bin of its probability, with
    the events per bin and the ECE (fa_reliability, t15)."""
    h, e = src.frame(T41), src.frame(T15)
    r = src.frame(FA_RELIABILITY)
    r = r[(r["target"] == "e5") & (r["n"] > 0)]
    out = []
    for model in SELECTIVE_MODELS:
        for panel, measure in OUTPUT_MEASURES:
            d = h[(h["model"] == model) & (h["measure"] == measure)]
            out.append(
                sc.rows(
                    d,
                    T41,
                    panel=panel,
                    series=f"={model}",
                    label="split",
                    role=f"={measure}",
                    x="bin",
                    x_col="mid",
                    y_col="share",
                )
            )
        d = r[r["model"] == model]
        for role in ("hit_rate", "n"):
            out.append(
                sc.rows(
                    d,
                    FA_RELIABILITY,
                    panel="c",
                    series=f"={model}",
                    label="=test",
                    role=f"={role}",
                    x="bin",
                    x_col="confidence",
                    y_col=role,
                )
            )
        out.append(
            sc.rows(
                e[e["key"] == f"{model}:e5"],
                T15,
                panel="c",
                series=f"={model}",
                label="=test",
                role="=ece",
                x="=ece",
                y_col="ece",
            )
        )
    return pd.concat(out, ignore_index=True)


BUILDERS: Final[Mapping[str, Callable[[sc.Sources], pd.DataFrame]]] = {
    "fig1_validation_test": fig1,
    "fig2_priced_at_open": fig2,
    "fig3_convergence": fig3,
    "fig4_over_under": fig4,
    "fig5_explaining_moves": fig5,
    "fig6_strategies": fig6,
    "fig7_memorisation": fig7,
    "figA1_tournament": figa1,
    "figA2_filters": figa2,
    "figA3_encoding": figa3,
    "figA4_reliability": figa4,
    "figA5_robustness": figa5,
    "figA6_monthly_ic": figa6,
    "figA7_convergence_detail": figa7,
    "figA8_drift_laya_fin": figa8,
    "figA9_shapley": figa9,
    "figA10_ablations": figa10,
    "figA11_persistence": figa11,
    "figA12_strategy_paths": figa12,
    "figA13_probes": figa13,
    "figA14_exploratory_d0": figa14,
    "figA15_exploratory_ma_cross": figa15,
    "figA16_selective_coverage": figa16,
    "figA17_watch_open": figa17,
    "figA18_conditioning_map": figa18,
    "figA19_output_histograms": figa19,
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
