"""Appendix figures A1–A19 (PRD NA-14 S2 "Appendix"; the operator's revision pass; NA-13b).

    uv run python -m newsaction.figures.render figA1_tournament ...

In the order of the paper's sections: A1 the zero-shot tournament; A2 the importance filters; A3 the encoding
study; A4 reliability; A5 the robustness forest; A6 the monthly IC (exploratory: its ±1 SE bands come from
NA-12 §13; the release dates are in its caption); A7 convergence in detail, with every V decile and the
anchor; A8 Figure 4 (b) for Laya-Fin; A9 the Shapley values by instrument and tier; A10 Call B with the news
removed or shuffled; A11 persistence by move reason; A12 the other books' paths and S-CONV by tier; A13 the
probes' descriptive columns (exploratory); A14 and A15 exploratory (post hoc): where the D0 signal lives, and
news with a moving-average cross; A16 to A19 exploratory (post hoc, NA-13b): when the D0 signal works, its
risk-coverage curves, the 10:00 reading against the pre-open one, the conditioning study and the distribution
of the outputs beside their reliability. Exploratory figures say so above their panels. Panels that show one
quantity on one scale share their axis. Each function draws one figure from its CSV (``render.draw`` reads it;
``NAMES`` maps function → figure).
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt
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
    "selective_coverage": "figA16_selective_coverage",
    "watch_open": "figA17_watch_open",
    "conditioning_map": "figA18_conditioning_map",
    "output_histograms": "figA19_output_histograms",
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
    tone = {"F5": (style.INK, style.LINE), "F6": (style.MUTED, style.LINE)}  # F6 mid-grey: it runs beside F5
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
            style.key(style.MUTED, line=True),
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
    """(a) and (d) both show H1, so they share a scale; H1b (b) and the IC (c) keep their own."""
    fig, axes = style.new(style.WIDTH_FULL, 3.6, 1, 4)
    axes[0][3].sharex(axes[0][0])
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
    """The y-range is the data's with a margin; the releases, all after the sample, are in the caption."""
    fig, axes = style.new(style.WIDTH_FULL, 2.4)
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
    for split, text in (("val_a", "val-A"), ("val_b", "val-B"), ("test", "test")):
        s = m[m["label"] == split]
        mid = s["date"].min() + (s["date"].max() - s["date"].min()) / 2
        style.label(
            ax, mid, 0.97, text, ha="center", va="top", color=style.INK_2, transform=ax.get_xaxis_transform()
        )
    style.zero_line(ax)
    margin = 0.02
    ax.set_ylim(float(m["lo"].min()) - margin, float(m["hi"].max()) + 2.0 * margin)
    ax.set_xlim(m["date"].min() - pd.Timedelta(days=20), m["date"].max() + pd.Timedelta(days=20))
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
    ticks(ax, paths)
    ax.set_xlim(-0.35, 9.6)


def convergence_detail(df: pd.DataFrame) -> Figure:
    """(a) and (b) share the CAR scale; (c), the ladder, spans the row below, so every rung is labelled."""
    fig, axd = style.mosaic(style.WIDTH_FULL, 4.4, [["a", "b"], ["c", "c"]], height_ratios=[1.15, 1.0])
    a, b, c = axd["a"], axd["b"], axd["c"]
    b.sharey(a)
    _all_deciles(a, df[df["panel"] == "a"], "laya_fin")
    _all_deciles(b, df[df["panel"] == "b"], "d1_ultra")
    b.tick_params(labelleft=False)
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
    ticks(c, k)
    c.set_xlim(0.6, 9.3)
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
}
SHAPLEY_TIER: Final = {"all": "all", "top100": "Top\n100", "mid": "101 to\n250", "rest": "251 to\n500"}
SHAPLEY_COLUMN: Final = {"laya_fin": "Laya-Fin", "d1_ultra": "d1-ultra", "anchor": "anchor, uninformative"}
SHAPLEY_ROW: Final = {
    "r2": ("$R^2$", r"Shapley value of $R^2$ ($\times 10^{-3}$)"),
    "ic": ("IC", r"Shapley value of IC ($\times 10^{-3}$)"),
}
BAR: Final = 0.23  # the slot of one group's bar; each bar leaves a surface gap within it


def shapley(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 4.0, 2, 3, sharex=True, sharey="row")
    for ax, letter in zip(axes.ravel(), "abcdef", strict=True):
        sub = df[df["panel"] == letter]
        model, metric = str(sub["label"].iloc[0]), str(sub["role"].iloc[0])
        for i, (group, colour) in enumerate(zip(GROUP, style.COMPONENT, strict=True)):
            m = sub[sub["series"] == group].sort_values("xv")
            ax.bar(
                m["xv"] + (i - 1) * BAR, 1e3 * m["y"], width=BAR - 0.03, color=colour, linewidth=0, zorder=2
            )
        total = sub[sub["series"] == "R+N+J"].sort_values("xv")
        style.dots(ax, total["xv"], 1e3 * total["y"], color=style.INK, marker="D", size=style.DOT, zorder=4)
        style.zero_line(ax)
        tiers = sub.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(tiers["xv"].tolist(), [SHAPLEY_TIER[str(t)] for t in tiers["x"]])
        ax.set_xlim(-0.5, 3.5)
        ax.grid(axis="x", visible=False)
        style.title(ax, letter, f"{SHAPLEY_COLUMN[model]}: {SHAPLEY_ROW[metric][0]}")
        if letter in "ad":
            ax.set_ylabel(SHAPLEY_ROW[metric][1])
    style.legend(
        fig,
        [Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="none") for c in style.COMPONENT]
        + [style.key(style.INK, marker="D")],
        [*GROUP.values(), r"total, $R + N + J$"],
        loc="outside upper center",
        ncols=4,
        handlelength=1.0,
    )
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
    """(a) and (b) share a scale, as do the S-CONV tiers (d) to (f); S-D2 (c) loses far less, so it keeps its
    own (the caption says so)."""
    fig, axes = style.new(style.WIDTH_FULL, 4.0, 2, 3, sharex=True)
    axes[0][1].sharey(axes[0][0])
    axes[1][1].sharey(axes[1][0])
    axes[1][2].sharey(axes[1][0])
    for ax, letter in zip(axes.ravel(), "abcdef", strict=True):
        _path_panel(ax, df[df["panel"] == letter], band=letter in "abc")
        style.title(ax, letter, A12_TITLES[letter])
        if letter in "bef":
            ax.tick_params(labelleft=False)
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
    """Both panels show the daily IC of N̂ on val-A, so they share the x-axis."""
    fig, axes = style.new(style.WIDTH_FULL, 2.6, 1, 2, sharex=True)
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
    small = {"fontsize": style.SIZE_SMALL, "handletextpad": 0.3, "columnspacing": 0.8, "handlelength": 1.0}
    for ax, handles, labels, ncols in (
        (
            a,
            [
                style.key(style.INK_2, marker="s", hollow=True),
                style.key(style.INK_2, marker="s"),
                style.key(style.INK_2, hollow=True),
                style.key(style.INK_2),
            ],
            ["earnings, val-B", "earnings, test", "other, val-B", "other, test"],
            2,
        ),
        (b, [style.key(style.INK), style.key(style.INK_2), style.key(style.CONTEXT)], list(TIER.values()), 2),
        (
            c,
            [style.key(style.INK_2), Rectangle((0, 0), 1, 1, facecolor=style.BAND_GREY, edgecolor="none")],
            ["the signal's SD", "shuffle null, 95% range"],
            1,
        ),
    ):  # each legend narrower than its panel, two rows tall
        style.legend(
            ax, handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncols=ncols, **small
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


# --- A16 to A19: when the D0 signal works (NA-13b, post hoc) ------------------------------------------------

SPLIT: Final = {"val_a": "val-A", "val_b": "val-B", "test": "test"}
INSTRUMENTS: Final = ("d1_ultra", "laya_fin")  # in drawing order: the primary instrument on top
OTHERS: Final = ("span_02", "drex_v2", "laya_zs")
COVERAGE_TICKS: Final = (1.0, 0.7, 0.5, 0.3, 0.1, 0.05)
COVERAGE_ROW: Final = {
    "a": r"mean $\mathrm{sign}(\hat N)\,z_{on}$",
    "b": r"mean $\mathrm{sign}(\hat N)\,z_{id}$",
    "c": r"hit rate against $z_{cc}$",
}
GATE: Final = 0.3  # the frozen confidence gates keep the events at or above their val-A 70th percentile


def _sqrt(x: npt.ArrayLike) -> npt.NDArray[np.float64]:
    out: npt.NDArray[np.float64] = np.sqrt(np.maximum(np.asarray(x, dtype=float), 0.0))
    return out


def _square(x: npt.ArrayLike) -> npt.NDArray[np.float64]:
    out: npt.NDArray[np.float64] = np.square(np.asarray(x, dtype=float))
    return out


def _coverage_key() -> Line2D:
    """The legend key of a curve ranked by the stated confidence: a thin line with hollow dots."""
    return Line2D(
        [],
        [],
        color=style.INK_2,
        linewidth=style.LINE_THIN,
        marker="o",
        markersize=3.0,
        markerfacecolor=style.SURFACE,
        markeredgecolor=style.INK_2,
        markeredgewidth=0.9,
    )


def selective_coverage(df: pd.DataFrame) -> Figure:
    """A row per quantity and a column per split; each row shares its scale and every panel the coverage axis,
    from every event on the left to the 5% the model is surest of on the right. The axis is on a square-root
    scale: a linear one crowds the tail (10% and 5%), a log one the points from 100% to 30%."""
    fig, axes = style.new(style.WIDTH_FULL, 6.2, 3, 3, sharex=True, sharey="row")
    for i, letter in enumerate("abc"):
        for j, split in enumerate(SPLIT):
            ax = axes[i][j]
            sub = df[(df["panel"] == letter) & (df["label"] == split)]
            conviction = sub[sub["role"] == "conviction"]
            for model in OTHERS:
                m = conviction[conviction["series"] == model].sort_values("xv")
                ax.plot(m["xv"], m["y"], color=style.CONTEXT, linewidth=style.LINE_THIN, zorder=2)
            for model in INSTRUMENTS:
                c = style.color(model)
                m = conviction[conviction["series"] == model].sort_values("xv")
                style.band(ax, m["xv"], m["lo"], m["hi"], c)
                ax.plot(m["xv"], m["y"], color=c, linewidth=style.LINE, zorder=3)
                k = sub[(sub["role"] == "confidence") & (sub["series"] == model)].sort_values("xv")
                ax.plot(k["xv"], k["y"], color=c, linewidth=style.LINE_THIN, zorder=3.5)
                style.dots(ax, k["xv"], k["y"], color=c, hollow=True, size=3.0, zorder=4)
            style.zero_line(ax, 0.5 if letter == "c" else 0.0)
            style.ref_line(ax, GATE, horizontal=False)
            ax.set_xscale("function", functions=(_sqrt, _square))
            ax.xaxis.set_major_locator(FixedLocator(list(COVERAGE_TICKS)))
            ax.xaxis.set_minor_locator(NullLocator())
            ax.xaxis.set_major_formatter(_pct(0))
            if i == 0:
                ax.set_title(SPLIT[split])
        axes[i][0].set_ylabel(rf"$\mathbf{{({letter})}}$ {COVERAGE_ROW[letter]}")
    axes[0][0].set_xlim(1.12, 0.028)  # read left to right: fewer, surer events; room for the end labels
    style.label(
        axes[0][0],
        GATE * 1.06,
        0.97,
        "frozen gate\n(70th pct.)",
        ha="right",
        va="top",
        color=style.INK_2,
        fontsize=style.SIZE_SMALL,
        transform=axes[0][0].get_xaxis_transform(),
    )
    axes[2][1].set_xlabel("coverage: the share of events kept, the model's surest first (square-root scale)")
    style.legend(
        fig,
        [
            style.key(style.color("laya_fin"), line=True),
            style.key(style.color("d1_ultra"), line=True),
            Line2D([], [], color=style.CONTEXT, linewidth=style.LINE_THIN),
            _coverage_key(),
        ],
        [
            "Laya-Fin",
            "d1-ultra",
            rf"{style.NAME['span_02']}, drex-v2.0, Laya zero-shot",
            "by stated confidence",
        ],
        loc="outside lower center",
        ncols=4,
    )
    _exploratory(fig)
    return fig


# (label, marker, offset within the split's group) of the three readings of Figure A17
WATCH: Final = {
    "ic_pre_open": ("pre-open, D0", "o", -0.24),
    "ic_ten": ("10:00, D1", "s", 0.0),
    "ic_revision": ("revision", "D", 0.24),
}


def watch_open(df: pd.DataFrame) -> Figure:
    """Both panels show the daily IC with y1, so they share the y-axis; the colour is the model, the marker
    the reading."""
    fig, axes = style.new(style.WIDTH_HALF, 2.75, 1, 2, sharey=True)
    for ax, letter in zip(axes[0], "ab", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["series"].iloc[0])
        c = style.color(model)
        for statistic, (_, marker, dx) in WATCH.items():
            m = sub[sub["role"] == statistic].sort_values("xv")
            style.dots(ax, m["xv"] + dx, m["y"], m["lo"], m["hi"], color=c, marker=marker, size=3.4)
        style.zero_line(ax)
        groups = sub.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(groups["xv"].tolist(), [SPLIT[str(s)] for s in groups["x"]])
        ax.tick_params(axis="x", length=0)
        ax.set_xlim(-0.5, 2.5)
        style.title(ax, letter, style.NAME[model])
    axes[0][0].set_ylabel(r"daily IC with $y_1$")
    style.legend(
        fig,
        [style.key(style.INK_2, marker=marker) for _, marker, _ in WATCH.values()],
        [text for text, _, _ in WATCH.values()],
        loc="outside lower center",
        ncols=3,
        columnspacing=1.0,
        handletextpad=0.2,
    )
    _exploratory(fig)
    return fig


# The groups and conditions of NA-13b (e), as Figure A18 and its table name them (selective.conditions)
CONDITION_GROUP: Final = {
    "E1": "E1 the news item",
    "E2": "E2 d1-ultra's reading of the news",
    "E3": "E3 timing",
    "E4": "E4 the day",
    "E5": "E5 the stock",
    "E6": "E6 the model's reading",
    "E7": "E7 two or more models",
    "E8": "E8 the cost hurdle",
    "E9": "E9 Laya-Fin on d1-ultra's labels",
}
CONDITION: Final = {
    "e1_earnings": "earnings day",
    "e1_vendor_quantified": "quantified",
    "e1_press_wire": "press wire",
    "e1_imprecise": "imprecise timestamp",
    "e2_new": "new, not known",
    "e2_numbers": "numbers, not narrative",
    "e2_scheduled": "scheduled",
    "e2_company": "company-specific",
    "e2_confirmed": "confirmed",
    "e2_long_horizon": "impact horizon above median",
    "e2_low_uncertainty": "uncertainty below median",
    "e2_few_mixed": "mixed signals below median",
    "e2_material": "materiality above median",
    "e2_effect": r"$P$(no material effect) below median",
    "e3_before_0800": "latest article before 08:00",
    "e3_0400_0800": "04:00 to 08:00, not 08:00 to 09:15",
    "e4_friday": "Friday",
    "e4_monday": "Monday",
    "e4_busy_event": r"busy news day (ratio $\geq 1.5$)",
    "e4_busy_day": "news count above median",
    "e4_earnings_season": "earnings count above median",
    "e4_macro": "FOMC, CPI or payrolls day",
    "e4_vix": r"VIX at $t-1$ above median",
    "e4_spy_gap": r"$|$SPY overnight$|$ above median",
    "e5_tier": "size tier 251 to 500",
    "e5_dv_tier": "dollar-volume tier 251 to 500",
    "e5_low_coverage": "low usual coverage",
    "e5_high_sigma": r"$\sigma$ above median",
    "e5_momentum": r"direction agrees with $z_{m20}$",
    "e5_price_text": "price-move text",
    "e6_conviction": "conviction top 30%",
    "e6_lf_mag": "Laya-Fin's magnitude above median",
    "e6_d1_conf": "d1-ultra's confidence above median",
    "e7_agree": "Laya-Fin and d1-ultra agree",
    "e7_api3": "three API models agree",
    "e7_rank_avg": "rank average of the two models",
    "e8_cost": r"$|V|\,\sigma$ above the hurdle",
    "e9_division": "numbers and material",
}
# (marker, hollow, offset within the row, size) of each split in Figure A18; a filled dot needs more size than
# a hollow one to read as large
SPLIT_MARK: Final = {
    "val_a": ("o", True, 0.29, 2.8),
    "val_b": ("s", True, 0.0, 2.8),
    "test": ("o", False, -0.29, 3.4),
}


def _condition_rows(df: pd.DataFrame) -> list[tuple[str, str]]:
    """The rows of Figure A18, grouped E1 to E9: † marks a vendor field (a retrospective label), "(seen)" a
    condition seen on test before the study."""
    flags = df[df["role"].isin(("seen_on_test", "vendor"))].pivot_table(
        index="x", columns="role", values="y", aggfunc="max"
    )
    rows: list[tuple[str, str]] = []
    for group, g in df.drop_duplicates("x").sort_values("xv").groupby("label", sort=False):
        rows.append(("head", CONDITION_GROUP[str(group)]))
        for c in g["x"]:
            text = CONDITION[str(c)] + (r"$^{\dagger}$" if flags.loc[c, "vendor"] > 0.5 else "")
            rows.append((str(c), text + (" (seen)" if flags.loc[c, "seen_on_test"] > 0.5 else "")))
    return rows


def conditioning_map(df: pd.DataFrame) -> Figure:
    """Both panels share the rows (one per condition, grouped E1 to E9) and the scale of the difference."""
    fig, axes = style.new(style.WIDTH_FULL, 6.9, 1, 2, sharex=True)
    rows = _condition_rows(df)
    for ax, letter in zip(axes[0], "ab", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["series"].iloc[0])
        c = style.color(model)
        ys = style.row_axis(ax, rows)
        selected = sub[(sub["role"] == "selected") & (sub["y"] > 0.5)]
        for cond in selected["x"]:
            ax.axhspan(
                ys[str(cond)] - 0.5, ys[str(cond)] + 0.5, color=style.GRID, alpha=0.6, linewidth=0, zorder=0.4
            )
        for split, (marker, hollow, dy, size) in SPLIT_MARK.items():
            m = sub[sub["role"] == split]
            y = [ys[str(cond)] + dy for cond in m["x"]]
            style.dots(
                ax,
                m["y"],
                y,
                m["lo"],
                m["hi"],
                color=c,
                marker=marker,
                hollow=hollow,
                size=size,
                horizontal=True,
            )
        style.zero_line(ax, horizontal=False)
        # ticks where most differences lie (E1's earnings day runs wider); math prints a true minus sign
        ax.xaxis.set_major_locator(FixedLocator([-0.5, -0.25, 0.0, 0.25, 0.5]))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}$"))
        style.title(ax, letter, style.NAME[model])
    axes[0][1].sharey(axes[0][0])
    axes[0][1].tick_params(labelleft=False)
    fig.supxlabel(
        r"inside minus outside: mean $\mathrm{sign}(\hat N)\,z_{id}$ (typical daily moves)",
        fontsize=style.SIZE,
    )
    style.legend(
        fig,
        [
            style.key(style.INK_2, hollow=True),
            style.key(style.INK_2, marker="s", hollow=True),
            style.key(style.INK_2),
            Rectangle((0, 0), 1, 1, facecolor=style.GRID, alpha=0.6, edgecolor="none"),
        ],
        ["val-A", "val-B", "test", "selected on validation"],
        loc="outside upper right",
        ncols=4,
    )
    _exploratory(fig)
    return fig


OUTPUT_TITLE: Final = {"a": r"$\hat N$", "b": "stated confidence", "c": "reliability on test"}
SPLIT_TONE: Final = {
    "val_a": (style.MUTED, style.LINE_THIN),
    "val_b": (style.INK_2, style.LINE_THIN),
    "test": (style.INK, style.LINE),
}


def _steps(
    mid: npt.NDArray[np.float64], share: npt.NDArray[np.float64]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """The outline of a histogram of equal-width bins centred on ``mid``: up from zero at the first edge,
    across every bin, down to zero at the last."""
    w = float(np.median(np.diff(mid)))
    edges = np.append(mid - w / 2, mid[-1] + w / 2)
    return np.repeat(edges, 2), np.concatenate([[0.0], np.repeat(share, 2), [0.0]])


def output_histograms(df: pd.DataFrame) -> Figure:
    """A row per model. The histograms (a, b) show one quantity, the share of events per bin, so they share
    the row's scale; the reliability diagrams (c) share both axes down the column."""
    models = list(dict.fromkeys(df["series"]))
    fig, axes = style.new(style.WIDTH_FULL, 6.7, len(models), 3)
    for i, model in enumerate(models):
        a, b, c = axes[i]
        b.sharey(a)
        if i:
            c.sharex(axes[0][2])
            c.sharey(axes[0][2])
        for ax, letter in ((a, "a"), (b, "b")):
            sub = df[(df["panel"] == letter) & (df["series"] == model)]
            for split, (tone, width) in SPLIT_TONE.items():
                h = sub[sub["label"] == split].sort_values("xv")
                x, y = _steps(h["xv"].to_numpy(dtype=float), h["y"].to_numpy(dtype=float))
                ax.plot(x, y, color=tone, linewidth=width, zorder=3 if split == "test" else 2)
        a.set_ylim(bottom=0.0)  # after both histograms, so the shared scale holds the taller
        sub = df[(df["panel"] == "c") & (df["series"] == model)]
        col = style.color(model)
        hit = sub[sub["role"] == "hit_rate"].sort_values("xv")
        n = sub[sub["role"] == "n"].set_index("x")["y"]
        c.plot([0, 1], [0, 1], color=style.BASELINE, linewidth=style.LINE_THIN, dashes=(3.0, 2.0), zorder=1)
        c.plot(hit["xv"], hit["y"], color=col, linewidth=style.LINE_THIN, zorder=2)
        sizes = 2.0 + 14.0 * np.sqrt(n.reindex(hit["x"]).to_numpy() / float(n.max()))
        c.scatter(
            hit["xv"], hit["y"], s=sizes**1.3, color=col, edgecolor=style.SURFACE, linewidth=0.5, zorder=3
        )
        ece = float(sub.loc[sub["role"] == "ece", "y"].iloc[0])
        style.label(
            c, 0.04, 0.95, f"ECE {ece:.3f}", ha="left", va="top", transform=c.transAxes, color=style.INK_2
        )
        c.set_xlim(0.3, 1.0)
        c.set_ylim(0.0, 1.0)
        c.set_ylabel("hit rate")
        a.set_ylabel(f"{style.NAME[model]}\nshare of events")
        b.tick_params(labelleft=False)
        if i == 0:
            for ax, letter in ((a, "a"), (b, "b"), (c, "c")):
                style.title(ax, letter, OUTPUT_TITLE[letter])
    axes[-1][0].set_xlabel(r"$\hat N$, bins from val-A")
    axes[-1][1].set_xlabel("stated confidence, bins from val-A")
    axes[-1][2].set_xlabel("top-class confidence (bin mean)")
    style.legend(
        fig,
        [Line2D([], [], color=tone, linewidth=width) for tone, width in SPLIT_TONE.values()],
        [SPLIT[s] for s in SPLIT_TONE],
        loc="outside upper center",
        ncols=3,
    )
    _exploratory(fig)
    return fig
