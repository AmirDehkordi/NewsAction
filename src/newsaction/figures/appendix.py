"""Appendix figures A1–A15 (PRD NA-14 S2 "Appendix"; the operator's revision pass).

    uv run python -m newsaction.figures.render figA1_tournament ...

In the order of the paper's sections: A1 the zero-shot tournament; A2 the importance filters; A3 the encoding
study; A4 reliability; A5 the robustness forest; A6 the monthly IC (exploratory: its ±1 SE bands come from
NA-12 §13); A7 convergence in detail, with every V decile and the anchor; A8 Figure 4 (b) for Laya-Fin; A9 the
Shapley values; A10 Call B with the news removed or shuffled; A11 persistence by move reason; A12 the other
books' paths and S-CONV by tier; A13 the probes' descriptive columns (exploratory); A14 and A15 exploratory
(post hoc): where the D0 signal lives, and news with a moving-average cross. Exploratory figures say so above
their panels. Each function draws one figure from its CSV (``render.draw`` reads it; ``NAMES`` maps function →
figure).
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator

from newsaction.figures import style
from newsaction.figures.fig3_convergence import ticks
from newsaction.figures.fig4_over_under import drift

NAMES: Final = {
    "tournament": "figA1_tournament",
    "filters": "figA2_filters",
    "encoding": "figA3_encoding",
    "reliability": "figA4_reliability",
    "robustness": "figA5_robustness",
    "monthly_ic": "figA6_monthly_ic",
    "convergence_detail": "figA7_convergence_detail",
    "drift_laya_fin": "figA8_drift_laya_fin",
    "shapley": "figA9_shapley",
    "ablations": "figA10_ablations",
    "persistence": "figA11_persistence",
    "strategy_paths": "figA12_strategy_paths",
    "probes": "figA13_probes",
    "exploratory_d0": "figA14_exploratory_d0",
    "exploratory_ma_cross": "figA15_exploratory_ma_cross",
}
EXPLORATORY: Final = "Exploratory (post hoc)"
# Model ids of NA-05/06/07/11 as the paper writes them; the entity decides the colour.
MODEL: Final = {
    "liquid/d1-ultra": ("d1_ultra", "d1-ultra"),
    "respan/span-02": ("span_02", style.NAME["span_02"]),
    "nace-ai/drex-v2.0": ("drex_v2", "drex-v2.0"),
    "local/laya-typed-decisions": ("laya_zs", "Laya zero-shot"),
    "local/laya-base": ("", "Laya base (local)"),
    "openai/gpt-6-luna-decisions": ("", "gpt-6-luna"),
    "cloudflare/clef": ("", "clef"),
    "inception/mercury-decide": ("", "mercury-decide"),
}
REASON: Final = {
    "analyst_action": "analyst action",
    "capital_returns_financing": "capital returns, financing",
    "deal_ma_partnership": "deal, M&A, partnership",
    "earnings_results": "earnings results",
    "guidance_outlook": "guidance, outlook",
    "legal_regulatory": "legal, regulatory",
    "management_governance": "management, governance",
    "market_or_sector_move": "market or sector move",
    "no_identifiable_news": "no identifiable news",
    "product_operations": "product, operations",
    "sector_or_macro": "sector or macro",
}
VARIANT: Final = {
    "main": "main estimate",
    "dollar_volume_tiers": "dollar-volume tiers",
    "exclude_date_only_hour": "no date-only or hour-stamped article",
    "exclude_half_days": "no half days",
    "non_overlapping": "non-overlapping events",
    "exclude_delisting_flag": "no delisting flag",
    "without_price_move_text": "without price-move text",
    "w0_cutoff_08:00_approx": "08:00 cutoff (approximated)",
    "timing_before_04:00": "latest article before 04:00",
    "timing_04:00_08:00": "latest article 04:00 to 08:00",
    "timing_08:00_09:15": "latest article 08:00 to 09:15",
}
TIER: Final = {"top100": "Top 100", "mid": "101 to 250", "rest": "251 to 500"}


def name_of(model: str) -> str:
    return MODEL[model][1] if model in MODEL else style.NAME.get(model, model.split("/")[-1])


def color_of(model: str) -> str:
    return style.color(MODEL[model][0] if model in MODEL else model)


def _exploratory(fig: Figure, what: str = EXPLORATORY) -> None:
    fig.suptitle(what, x=0.0, ha="left", fontsize=style.SIZE, color=style.INK_2, fontweight="normal")


def _pct(decimals: int) -> FuncFormatter:
    return FuncFormatter(lambda v, _: f"{100 * v:.{decimals}f}%")


# --- A1 the tournament --------------------------------------------------------------------------------------


def tournament(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 3.7, [["a", "b"]], width_ratios=[1.6, 1.0])
    a, b = axd["a"], axd["b"]
    ic = df[df["role"] == "ic"].sort_values("y", ascending=False)
    stage2 = df[df["role"] == "stage2"].set_index("series")["y"] > 0.5
    rows = [(str(m), name_of(str(m))) for m in ic["series"]]
    ys = style.row_axis(a, rows)
    style.row_axis(b, rows)
    b.tick_params(labelleft=False)
    for _, r in ic.iterrows():
        m = str(r["series"])
        marker = "s" if bool(stage2.get(m, False)) else "o"
        style.dots(
            a, [r["y"]], [ys[m]], [r["lo"]], [r["hi"]], color=color_of(m), marker=marker, horizontal=True
        )
        cost = float(r["xv"])
        if cost > 0:
            style.dots(b, [cost], [ys[m]], color=color_of(m), marker=marker)
        else:
            style.label(
                b, 0.013, ys[m], "local, no cost", ha="left", color=style.INK_2, fontsize=style.SIZE_SMALL
            )
    style.zero_line(a, horizontal=False)
    a.set_xlabel(r"daily IC of $\hat N$ with $z_{cc}$ (val-A, stage 1)")
    b.set_xscale("log")
    b.xaxis.set_major_locator(FixedLocator([0.02, 0.05, 0.1, 0.2]))
    b.xaxis.set_minor_locator(NullLocator())
    b.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}"))
    b.set_xlim(0.012, 0.26)
    b.set_xlabel("cost per 1,000 decisions (USD, log scale)")
    style.title(a, "a", "Daily IC")
    style.title(b, "b", "Cost")
    style.legend(
        fig,
        [style.key(style.INK_2, marker="s"), style.key(style.INK_2)],
        ["stage-2 screens run (all failed)", "stage 1 only"],
        loc="outside upper center",
        ncols=2,
    )
    return fig


# --- A2 the filters -----------------------------------------------------------------------------------------


def filters(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 2.6)
    ax = axes[0][0]
    f = df[df["role"] == "frontier"]
    ax.plot(
        [0, 0.55], [0, 0.55], color=style.BASELINE, linewidth=style.LINE_THIN, dashes=(3.0, 2.0), zorder=1
    )
    tone = {"F5": (style.INK, style.LINE), "F6": (style.INK_2, style.LINE)}
    for filt in sorted(f["series"].unique()):
        m = f[f["series"] == filt].sort_values("xv")
        c, lw = tone.get(str(filt), (style.CONTEXT, style.LINE_THIN))
        ax.plot(m["xv"], m["y"], color=c, linewidth=lw, zorder=3 if filt == "F5" else 2)
    pick = df[df["role"] == "chosen"].iloc[0]
    style.dots(ax, [pick["xv"]], [pick["y"]], color=style.INK, zorder=5)
    ax.set_xlim(0.0, 0.55)
    ax.set_ylim(0.0, 0.7)
    ax.xaxis.set_major_formatter(_pct(0))
    ax.yaxis.set_major_formatter(_pct(0))
    ax.set_xlabel("share of days selected (val-A)")
    ax.set_ylabel("material recall")
    style.legend(
        ax,
        [
            style.key(style.INK, line=True),
            style.key(style.INK),
            style.key(style.INK_2, line=True),
            Line2D([], [], color=style.CONTEXT, linewidth=style.LINE_THIN),
            style.key(style.BASELINE, dashed=True),
        ],
        [
            "F5, embeddings (frozen)",
            "F5 at its budget",
            "F6, gradient boosting",
            "F0 to F4, rules",
            "random selection",
        ],
        loc="upper left",
        borderaxespad=0.3,
    )
    return fig


# --- A3 encoding --------------------------------------------------------------------------------------------


def encoding(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.3, 1, 3, sharey=True)
    for ax, letter in zip(axes[0], "abc", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["label"].iloc[0])
        c = color_of(model)
        ic = sub[sub["role"] == "ic"]
        for split, dx, hollow in (("val_a", -0.1, False), ("val_b", 0.1, True)):
            m = ic[ic["series"] == split].sort_values("xv")
            style.dots(ax, m["xv"] + dx, m["y"], m["lo"], m["hi"], color=c, hollow=hollow)
        chosen = sub[(sub["role"] == "chosen") & (sub["series"] == "val_a") & (sub["y"] > 0.5)]
        for _, r in chosen.iterrows():
            ax.axvspan(
                float(r["xv"]) - 0.35,
                float(r["xv"]) + 0.35,
                color=style.GRID,
                alpha=0.6,
                zorder=0.5,
                linewidth=0,
            )
        style.zero_line(ax)
        e = ic.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(e["xv"].tolist(), e["x"].tolist())
        ax.set_xlim(-0.5, 4.5)
        ax.set_xlabel("encoding of numbers")
        style.title(ax, letter, name_of(model))
    axes[0][0].set_ylabel(r"daily IC of $\hat N$ with $z_{cc}$")
    style.legend(
        fig,
        [
            style.key(style.INK_2),
            style.key(style.INK_2, hollow=True),
            Rectangle((0, 0), 1, 1, facecolor=style.GRID, alpha=0.6),
        ],
        ["val-A (search)", "val-B (confirmation)", "frozen encoding"],
        loc="outside upper center",
        ncols=3,
    )
    return fig


# --- A4 reliability -----------------------------------------------------------------------------------------


def reliability(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 4.1, 2, 3, sharex=True, sharey=True)
    for ax, letter in zip(axes.ravel(), "abcdef", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["series"].iloc[0])
        c = style.color(model)
        hit = sub[sub["role"] == "hit_rate"].sort_values("xv")
        n = sub[sub["role"] == "n"].set_index("x")["y"]
        ax.plot([0, 1], [0, 1], color=style.BASELINE, linewidth=style.LINE_THIN, zorder=1)
        ax.plot(hit["xv"], hit["y"], color=c, linewidth=style.LINE_THIN, zorder=2)
        sizes = 3.0 + 22.0 * np.sqrt(n.reindex(hit["x"]).to_numpy() / float(n.max()))
        ax.scatter(
            hit["xv"], hit["y"], s=sizes**1.3, color=c, edgecolor=style.SURFACE, linewidth=0.5, zorder=3
        )
        ece = float(sub.loc[sub["role"] == "ece", "y"].iloc[0])
        style.title(ax, letter, style.NAME[model])
        style.label(
            ax, 0.04, 0.95, f"ECE {ece:.3f}", ha="left", va="top", transform=ax.transAxes, color=style.INK_2
        )
        ax.set_xlim(0.3, 1.0)
        ax.set_ylim(0.0, 1.0)
    for ax in axes[1]:
        ax.set_xlabel("top-class confidence (bin mean)")
    for ax in axes[:, 0]:
        ax.set_ylabel("hit rate")
    return fig


# --- A5 robustness ------------------------------------------------------------------------------------------

FOREST_TITLES: Final = {"a": "Laya-Fin, H1", "b": "Laya-Fin, H1b", "c": "Laya-Fin, IC", "d": "d1-ultra, H1"}


def robustness(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 3.6, 1, 4)
    variants = df.drop_duplicates("xv").sort_values("xv")
    rows = [(str(v), VARIANT[str(v)]) for v in variants["x"]]
    for ax, letter in zip(axes[0], "abcd", strict=True):
        sub = df[df["panel"] == letter]
        ys = style.row_axis(ax, rows)
        c = style.color(str(sub["series"].iloc[0]))
        for _, r in sub.iterrows():
            y = ys[str(r["x"])]
            if r["role"] == "main":
                style.dots(ax, [r["y"]], [y], [r["lo"]], [r["hi"]], color=c, marker="D", horizontal=True)
            else:
                dy = -0.17 if r["role"] == "placebo" else 0.17
                style.dots(
                    ax,
                    [r["y"]],
                    [y + dy],
                    [r["lo"]],
                    [r["hi"]],
                    color=c,
                    hollow=r["role"] == "placebo",
                    horizontal=True,
                )
        style.zero_line(ax, horizontal=False)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=3))
        style.title(ax, letter, FOREST_TITLES[letter])
        if letter != "a":
            ax.tick_params(labelleft=False)
    style.legend(
        fig,
        [style.key(style.INK_2, marker="D"), style.key(style.INK_2), style.key(style.INK_2, hollow=True)],
        ["main estimate (bootstrap)", "variant, raw", "variant, placebo-adjusted"],
        loc="outside upper center",
        ncols=3,
    )
    fig.supxlabel("estimate with its 95% interval (test)", fontsize=style.SIZE)
    return fig


# --- A6 the monthly IC (exploratory SE) ---------------------------------------------------------------------


def monthly_ic(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.5)
    ax = axes[0][0]
    m = df[df["role"] == "monthly_ic"].copy()
    m["date"] = pd.to_datetime(m["x"] + "-15")
    for model, dx in (("laya_fin", -3), ("d1_ultra", 3)):
        s = m[m["series"] == model].sort_values("date")
        c = style.color(model)
        style.band(ax, s["date"], s["lo"], s["hi"], c, alpha=0.12)
        for _, g in s.groupby("label", sort=False):
            gx = g["date"] + pd.Timedelta(days=dx)
            ax.plot(gx, g["y"], color=c, linewidth=style.LINE, zorder=3)
            style.dots(ax, gx, g["y"], color=c, zorder=4)
    style.legend(
        ax,
        [style.key(style.color(mm), line=True) for mm in ("laya_fin", "d1_ultra")],
        [style.NAME[mm] for mm in ("laya_fin", "d1_ultra")],
        loc="lower left",
        borderaxespad=0.4,
    )
    rel = df[df["role"] == "release"].copy()
    rel["date"] = pd.to_datetime(rel["x"])
    end = rel.loc[rel["series"] == "sample_end", "date"].iloc[0]
    last = rel["date"].max()
    ax.axvspan(end, last + pd.Timedelta(days=12), color=style.GRID, alpha=0.6, linewidth=0, zorder=0.5)
    top = 0.235
    for key in ("laya", "drex_v2", "d1_ultra", "span_02"):
        ax.axvline(
            rel.loc[rel["series"] == key, "date"].iloc[0],
            color=style.INK_2,
            linewidth=style.LINE_THIN,
            zorder=1.6,
        )
    for key, text in (("laya", "Laya released"), ("drex_v2", "API models released")):
        d = rel.loc[rel["series"] == key, "date"].iloc[0]
        style.label(
            ax, d - pd.Timedelta(days=3), 0.0, text, ha="right", va="center", rotation=90, color=style.INK_2
        )
    style.label(
        ax, end + pd.Timedelta(days=4), -0.14, "after the sample", ha="left", va="bottom", color=style.INK_2
    )
    for split, text in (("val_a", "val-A"), ("val_b", "val-B"), ("test", "test")):
        s = m[m["label"] == split]
        mid = s["date"].min() + (s["date"].max() - s["date"].min()) / 2
        style.label(ax, mid, top, text, ha="center", va="top", color=style.INK_2)
    style.zero_line(ax)
    ax.set_ylim(-0.15, 0.25)
    ax.set_xlim(m["date"].min() - pd.Timedelta(days=20), last + pd.Timedelta(days=12))
    style.month_ticks(ax, (1, 4, 7, 10), "%b %Y")
    ax.set_ylabel(r"monthly mean of the daily IC with $z_{cc}$")
    _exploratory(fig, r"Exploratory (post hoc): the bands are $\pm 1$ implied SE of a month's mean")
    return fig


# --- A7 convergence in detail -------------------------------------------------------------------------------


def _all_deciles(ax: Axes, d: pd.DataFrame, model: str) -> None:
    c = style.color(model)
    paths = d[d["role"] == "path"]
    for series in sorted(paths["series"].unique(), key=lambda s: int(str(s).split("_")[1])):
        p = paths[paths["series"] == series].sort_values("xv")
        extreme = series in ("decile_1", "decile_10")
        if extreme:
            style.band(ax, p["xv"], p["lo"], p["hi"], c)
            target = float(d[(d["series"] == series) & (d["role"] == "target")]["y"].iloc[0])
            style.ref_line(ax, target, color=c)
        ax.plot(
            p["xv"],
            p["y"],
            color=c if extreme else style.CONTEXT,
            linewidth=style.LINE if extreme else style.LINE_HAIR,
            zorder=3 if extreme else 2,
        )
    for series, text in (("decile_10", "top"), ("decile_1", "bottom")):
        p = paths[paths["series"] == series].sort_values("xv")
        style.label(ax, float(p["xv"].iloc[-1]) + 0.15, float(p["y"].iloc[-1]), text, ha="left")
    style.zero_line(ax)
    ticks(ax, paths, sparse=True)
    ax.set_xlim(-0.35, 9.6)


def convergence_detail(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.5, 1, 3)
    a, b, c = axes[0]
    _all_deciles(a, df[df["panel"] == "a"], "laya_fin")
    _all_deciles(b, df[df["panel"] == "b"], "d1_ultra")
    a.set_ylabel(r"$\mathrm{CAR}^{\mathrm{lvl}}$ (typical daily moves)")
    style.title(a, "a", r"Laya-Fin, deciles of $V$")
    style.title(b, "b", r"d1-ultra, deciles of $V$")
    pc = df[df["panel"] == "c"]
    k = pc[pc["role"] == "kappa"]
    for model, dx in (("laya_fin", -0.12), ("d1_ultra", 0.0), ("anchor", 0.12)):
        s = k[k["series"] == model].sort_values("xv")
        col = style.color(model)
        c.plot(s["xv"] + dx, s["y"], color=col, linewidth=style.LINE_THIN, zorder=2)
        style.dots(c, s["xv"] + dx, s["y"], s["lo"], s["hi"], color=col)
        style.label(c, 8.4, float(s["y"].iloc[-1]), style.NAME[model], ha="left")
    style.ref_line(c, 1.0, color=style.INK_2)
    style.zero_line(c)
    ticks(c, k, sparse=True)
    c.set_xlim(0.6, 11.4)
    c.set_ylabel(r"$\kappa_h$")
    style.title(c, "c", r"$\kappa_h$, with the anchor")
    return fig


# --- A8 Laya-Fin's drift by |G| -----------------------------------------------------------------------------


def drift_laya_fin(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 2.6)
    drift(axes[0][0], df, "laya_fin")
    return fig


# --- A9 Shapley ---------------------------------------------------------------------------------------------

GROUP: Final = {
    "R": r"$R$, price and reaction",
    "N": r"$N$, news (Call A)",
    "J": r"$J$, judgements (Call B)",
    "R+N+J": r"total, $R + N + J$",
}


def shapley(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 1.9, 1, 2)
    rows = [(g, GROUP[g]) for g in GROUP]
    for ax, letter, title in zip(
        axes[0], "ab", (r"Out-of-sample $R^2$ of $y_2$", r"Mean daily IC with $y_2$"), strict=True
    ):
        sub = df[df["panel"] == letter]
        ys = style.row_axis(ax, rows)
        for model, dy in (("laya_fin", 0.2), ("d1_ultra", 0.0), ("anchor", -0.2)):
            s = sub[sub["series"] == model]
            style.dots(ax, s["y"], [ys[str(x)] + dy for x in s["x"]], color=style.color(model))
        style.zero_line(ax, horizontal=False)
        style.title(ax, letter, title)
        if letter == "b":
            ax.tick_params(labelleft=False)
    style.legend(
        fig,
        [style.key(style.color(m)) for m in ("laya_fin", "d1_ultra", "anchor")],
        ["Laya-Fin", "d1-ultra", "anchor"],
        loc="outside upper center",
        ncols=3,
    )
    fig.supxlabel("Shapley value (test, D2, pooled over tiers)", fontsize=style.SIZE)
    return fig


# --- A10 ablations ------------------------------------------------------------------------------------------

FEATURE: Final = {"j": "$J$", "c": "$C$", "n_hat": r"$\hat N$"}


def ablations(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 2.3, 1, 2, sharey=True)
    c = style.color("d1_ultra")
    for ax, letter, title in zip(axes[0], "ab", ("News removed", "Shuffled news"), strict=True):
        sub = df[df["panel"] == letter]
        for role, dx, hollow in (("real", -0.12, False), ("ablated", 0.12, True)):
            m = sub[sub["role"] == role].sort_values("xv")
            style.dots(ax, m["xv"] + dx, m["y"], m["lo"], m["hi"], color=c, hollow=hollow)
        style.zero_line(ax)
        f = sub.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(f["xv"].tolist(), [FEATURE[str(x)] for x in f["x"]])
        ax.set_xlim(-0.5, 2.5)
        style.title(ax, letter, title)
    axes[0][0].set_ylabel(r"IC with $y_2$ (d1-ultra)")
    style.legend(
        fig,
        [style.key(c), style.key(c, hollow=True)],
        ["real news", "ablated"],
        loc="outside upper center",
        ncols=2,
    )
    return fig


# --- A11 persistence ----------------------------------------------------------------------------------------


def persistence(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 3.1)
    ax = axes[0][0]
    p = df[df["role"] == "persistence"].sort_values("y")
    rows: list[tuple[str, str]] = [("head", "By move reason (d1-ultra)")]
    rows += [(str(r), REASON[str(r)]) for r in p["series"]]
    rows += [("head", "Explained moves"), ("theta_d2", r"$\theta$ at D2")]
    ys = style.row_axis(ax, rows)
    c = style.color("d1_ultra")
    for _, r in df.iterrows():
        style.dots(
            ax,
            [r["y"]],
            [ys[str(r["series"])]],
            [r["lo"]],
            [r["hi"]],
            color=c,
            horizontal=True,
            marker="D" if r["role"] == "theta" else "o",
        )
    style.zero_line(ax, horizontal=False)
    ax.set_xlabel(r"$\mathrm{sign}(G)\,y_2$ (typical daily moves)")
    return fig


# --- A12 the other books ------------------------------------------------------------------------------------


def _path_panel(ax: Axes, sub: pd.DataFrame, band: bool) -> None:
    sub = sub.copy()
    sub["date"] = pd.to_datetime(sub["x"])
    if band:
        b = sub[sub["role"] == "placebo_band"].sort_values("date")
        ax.fill_between(
            b["date"], 100 * b["lo"], 100 * b["hi"], color=style.BAND_GREY, alpha=0.7, linewidth=0, zorder=1
        )
    for series in ("sentiment", "gap_fade", "d1_ultra", "laya_fin"):
        s = sub[(sub["series"] == series) & (sub["role"] != "placebo_band")].sort_values("date")
        if len(s):
            col = style.INK_2 if series == "sentiment" else style.color(series)
            ax.plot(
                s["date"],
                100 * s["y"],
                color=col,
                linewidth=style.LINE_THIN if series == "sentiment" else style.LINE,
                zorder=3,
            )
    style.zero_line(ax)
    style.month_ticks(ax, (1, 3, 5, 7), "%b")


A12_TITLES: Final = {
    "a": "S-D0, open to close",
    "b": r"S-D1 $J$, 10:00 to close",
    "c": r"S-D2 $J$, next open to $t{+}5$",
    "d": "S-CONV, Top 100",
    "e": "S-CONV, 101 to 250",
    "f": "S-CONV, 251 to 500",
}


def strategy_paths(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 4.0, 2, 3, sharex=True)
    for ax, letter in zip(axes.ravel(), "abcdef", strict=True):
        _path_panel(ax, df[df["panel"] == letter], band=letter in "abc")
        style.title(ax, letter, A12_TITLES[letter])
    for ax in axes[:, 0]:
        ax.set_ylabel("cumulative net, 10 bp (%)")
    style.legend(
        fig,
        [
            style.key(style.color("laya_fin"), line=True),
            style.key(style.color("d1_ultra"), line=True),
            style.key(style.color("gap_fade"), line=True),
            style.key(style.INK_2, line=True),
            Rectangle((0, 0), 1, 1, facecolor=style.BAND_GREY, alpha=0.7, edgecolor="none"),
        ],
        [
            "Laya-Fin",
            "d1-ultra",
            "gap fade (price-only)",
            r"vendor sentiment$^{\dagger}$",
            "placebo, 5th to 95th pct.",
        ],
        loc="outside upper center",
        ncols=5,
    )
    return fig


# --- A13 the probes (exploratory columns) -------------------------------------------------------------------


def probes(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.6, 1, 2)
    for ax, letter, roles, title in (
        (axes[0][0], "a", ("masked", "unmasked"), "Masked against unmasked states"),
        (axes[0][1], "b", ("real", "shuffled"), "Real against shuffled news"),
    ):
        sub = df[df["panel"] == letter]
        models = list(dict.fromkeys(sub["series"]))
        ys = style.row_axis(ax, [(str(m), name_of(str(m))) for m in models])
        for m in models:
            for role, dy, hollow in ((roles[0], 0.16, False), (roles[1], -0.16, True)):
                r = sub[(sub["series"] == m) & (sub["role"] == role)].iloc[0]
                style.dots(
                    ax,
                    [r["y"]],
                    [ys[str(m)] + dy],
                    [r["lo"]],
                    [r["hi"]],
                    color=color_of(str(m)),
                    hollow=hollow,
                    horizontal=True,
                )
        style.zero_line(ax, horizontal=False)
        ax.set_xlabel(r"daily IC of $\hat N$ (val-A)")
        style.title(ax, letter, title)
    style.legend(
        fig,
        [style.key(style.INK_2), style.key(style.INK_2, hollow=True)],
        ["(a) masked; (b) real news", "(a) unmasked; (b) shuffled news"],
        loc="outside upper right",
        ncols=2,
    )
    _exploratory(fig, "Exploratory: the probes' descriptive columns (NA-11)")
    return fig


# --- A14 where the D0 signal lives (post hoc) ---------------------------------------------------------------

SIGNAL_ORDER: Final = ("laya_fin", "laya_zs", "d1_ultra", "span_02", "drex_v2", "sentiment", "tags_gbm")


def exploratory_d0(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.9, 1, 3)
    a, b, c = axes[0]
    rows = [(s, style.NAME[s]) for s in SIGNAL_ORDER]
    ys = style.row_axis(a, rows)
    pa = df[df["panel"] == "a"]
    for _, r in pa.iterrows():
        dy = {"earnings": 0.18, "rest": -0.18}[str(r["role"])] + {"val_b": 0.06, "test": -0.06}[
            str(r["label"])
        ]
        col = style.color(str(r["series"]))
        style.dots(
            a,
            [r["y"]],
            [ys[str(r["series"])] + dy],
            [r["lo"]],
            [r["hi"]],
            color=col,
            hollow=r["label"] == "val_b",
            marker="s" if r["role"] == "earnings" else "o",
            horizontal=True,
            size=3.4,
        )
    style.zero_line(a, horizontal=False)
    a.set_xlabel(r"daily IC with $z_{cc}$")
    style.title(a, "a", "Earnings days and the rest")
    style.row_axis(b, rows)
    b.tick_params(labelleft=False)
    pb = df[df["panel"] == "b"]
    for _, r in pb.iterrows():
        dy = {"top100": 0.22, "mid": 0.0, "rest": -0.22}[str(r["label"])]
        tone = {"top100": style.INK, "mid": style.INK_2, "rest": style.CONTEXT}[str(r["label"])]
        style.dots(
            b,
            [r["y"]],
            [ys[str(r["series"])] + dy],
            [r["lo"]],
            [r["hi"]],
            color=tone,
            horizontal=True,
            size=3.4,
        )
    style.zero_line(b, horizontal=False)
    b.set_xlabel(r"daily IC with $z_{cc}$ (test)")
    style.title(b, "b", "Size tiers")
    style.row_axis(c, rows)
    c.tick_params(labelleft=False)
    pc = df[df["panel"] == "c"]
    for s in SIGNAL_ORDER:
        sd = pc[(pc["series"] == s) & (pc["role"] == "sd")].iloc[0]
        null = pc[(pc["series"] == s) & (pc["role"] == "null")].iloc[0]
        c.hlines(ys[s], null["lo"], null["hi"], color=style.BAND_GREY, linewidth=4.0, zorder=1)
        style.dots(c, [sd["y"]], [ys[s]], color=style.color(s))
    c.set_xlabel("SD across companies")
    style.title(c, "c", "Spread across companies")
    style.legend(
        fig,
        [
            style.key(style.INK_2, marker="s", hollow=True),
            style.key(style.INK_2, marker="s"),
            style.key(style.INK_2, hollow=True),
            style.key(style.INK_2),
            style.key(style.INK),
            style.key(style.INK_2),
            style.key(style.CONTEXT),
            Rectangle((0, 0), 1, 1, facecolor=style.BAND_GREY, edgecolor="none"),
        ],
        [
            "(a) earnings days, val-B",
            "earnings days, test",
            "other events, val-B",
            "other events, test",
            "(b) Top 100",
            "101 to 250",
            "251 to 500",
            "(c) shuffle null, 95% range",
        ],
        loc="outside lower center",
        ncols=4,
        columnspacing=1.0,
        handletextpad=0.3,
    )
    _exploratory(fig)
    return fig


# --- A15 news and a moving-average cross (post hoc) ---------------------------------------------------------

MA_GROUP: Final = {
    "all": "all crosses",
    "none": "no news",
    "agree_laya_fin": "agree, Laya-Fin",
    "disagree_laya_fin": "disagree, Laya-Fin",
    "agree_d1_ultra": "agree, d1-ultra",
    "disagree_d1_ultra": "disagree, d1-ultra",
}


def exploratory_ma_cross(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 2.6, [["a", "b", "c"]], width_ratios=[1.0, 1.0, 1.15])
    rows = [(g, MA_GROUP[g]) for g in MA_GROUP]
    for letter, title in (("a", "5 days after the cross"), ("b", "20 days after the cross")):
        ax = axd[letter]
        ys = style.row_axis(ax, rows)
        sub = df[df["panel"] == letter]
        for _, r in sub.iterrows():
            dy = 0.16 if r["role"] == "validation" else -0.16
            style.dots(
                ax,
                [r["y"]],
                [ys[str(r["series"])] + dy],
                [r["lo"]],
                [r["hi"]],
                color=style.INK_2,
                hollow=r["role"] == "validation",
                horizontal=True,
            )
        style.zero_line(ax, horizontal=False)
        ax.set_xlabel("signed abnormal return (bp)")
        style.title(ax, letter, title)
        if letter == "b":
            ax.tick_params(labelleft=False)
    c = axd["c"]
    f = df[df["panel"] == "c"].copy()
    f["date"] = pd.to_datetime(f["x"])
    f = f.sort_values("date")
    c.plot(f["date"], 100 * f["y"], color=style.INK_2, linewidth=style.LINE)
    style.zero_line(c)
    style.month_ticks(c, (1, 3, 5, 7), "%b")
    c.set_ylabel("cumulative net, 10 bp (%)")
    style.title(c, "c", "No-news fade, test")
    style.legend(
        fig,
        [style.key(style.INK_2, hollow=True), style.key(style.INK_2)],
        ["validation", "test"],
        loc="outside lower left",
        ncols=2,
    )
    _exploratory(fig)
    return fig
