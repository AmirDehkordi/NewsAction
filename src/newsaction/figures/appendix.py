"""Appendix figures A1–A7 (PRD NA-14 S2 "Appendix"; operator preamble items 4–5).

    uv run python -m newsaction.figures.render figA1_reliability ...

- A1 reliability diagrams (NA-12 bins, t15 ECE); A2 the encoding study (NA-07);
- A3 masking and identifiability (NA-11's company identification and probes; the probe panels are
  descriptive);
- A4 Call B with the news removed or shuffled (t16); A5 the robustness forest (t16, t1b, t3);
- A6 and A7 are exploratory (post hoc): where the D0 signal lives (NA-12 §13) and the MA cross (NA-13 §9).

Each function draws one figure from its CSV (``render.draw`` reads it; ``NAMES`` maps function → figure).
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

from newsaction.figures import style

NAMES: Final = {
    "reliability": "figA1_reliability",
    "encoding": "figA2_encoding",
    "identifiability": "figA3_identifiability",
    "ablations": "figA4_ablations",
    "robustness": "figA5_robustness",
    "exploratory_d0": "figA6_exploratory_d0",
    "exploratory_ma_cross": "figA7_exploratory_ma_cross",
}
EXPLORATORY: Final = "Exploratory (post hoc): requested after unblinding; no hypothesis, no claim"
VENDOR: Final = f"† vendor-label baseline: {style.VENDOR_NOTE}"
SPAN: Final = "‡ span-02: S5 canary STOP after the freeze; the operator proceeded (PREREG §15)"
NAME_OF: Final = {
    "laya_fin": "Laya-Fin",
    "anchor": "anchor, uninformative\n(near-constant outputs)",
    "laya_zs": "Laya zero-shot",
    "d1_ultra": "d1-ultra",
    "span_02": "span-02‡",
    "drex_v2": "drex-v2.0",
    "sentiment": "vendor sentiment†",
    "tags_gbm": "tags-GBM†",
    "liquid/d1-ultra": "d1-ultra",
    "respan/span-02": "span-02‡",
    "nace-ai/drex-v2.0": "drex-v2.0",
    "inception/mercury-decide": "mercury-decide",
    "cloudflare/clef": "clef",
    "openai/gpt-6-luna-decisions": "gpt-6-luna",
    "local/laya-typed-decisions": "Laya zero-shot",
}
API: Final = ("d1_ultra", "span_02", "drex_v2", "liquid/d1-ultra", "respan/span-02", "nace-ai/drex-v2.0")


def color(model: str) -> str:
    if model == "laya_fin":
        return style.COLOR["laya_fin"]
    if model in API:
        return style.COLOR["api"]
    if model in ("sentiment", "tags_gbm"):
        return style.COLOR["vendor"]
    return style.MUTED


def _banner(fig: Figure, *extra: str) -> None:
    fig.suptitle(
        "\n".join((EXPLORATORY, *extra)),
        x=0.01,
        ha="left",
        fontsize=style.SIZE_TITLE,
        color=style.INK_2,
        fontweight="normal",
    )


def _rows(ax: Axes, labels: list[str]) -> None:
    ax.set_yticks(range(len(labels)), labels)
    ax.set_ylim(-0.6, len(labels) - 0.4)
    ax.grid(axis="y", visible=False)
    ax.invert_yaxis()


def reliability(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 4.4, 2, 3, sharex=True, sharey=True)
    for ax, letter in zip(axes.ravel(), "abcdef", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["series"].iloc[0])
        hit = sub[sub["role"] == "hit_rate"].sort_values("xv")
        n = sub[sub["role"] == "n"].set_index("x")["y"]
        ax.plot([0, 1], [0, 1], color=style.GRID, linewidth=0.8, zorder=1)
        ax.plot(hit["xv"], hit["y"], color=color(model), linewidth=style.LINE_THIN, zorder=2)
        sizes = 4.0 + 26.0 * np.sqrt(n.reindex(hit["x"]).to_numpy() / float(n.max()))
        ax.scatter(
            hit["xv"],
            hit["y"],
            s=sizes**1.4,
            color=color(model),
            edgecolor=style.SURFACE,
            linewidth=0.6,
            zorder=3,
        )
        ece = float(sub.loc[sub["role"] == "ece", "y"].iloc[0])
        style.title(ax, letter, NAME_OF[model])
        style.note(ax, 0.97, 0.04, f"ECE {ece:.3f}", ha="right", va="bottom")
        ax.set_xlim(0.3, 1.0)
        ax.set_ylim(0.0, 1.0)
    for ax in axes[1]:
        ax.set_xlabel("mean top-class confidence (bin)")
    for ax in axes[:, 0]:
        ax.set_ylabel("hit rate")
    style.note(
        axes[0][0], 0.03, 0.97, "dot area ∝ events in the bin\ndiagonal: perfect calibration", va="top"
    )
    return fig


def encoding(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 2.5, 1, 3, sharey=True)
    for ax, letter in zip(axes[0], "abc", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["label"].iloc[0])
        ic = sub[sub["role"] == "ic"]
        for split, dx, hollow in (("val_a", -0.1, False), ("val_b", 0.1, True)):
            m = ic[ic["series"] == split].sort_values("xv")
            style.dots(
                ax, m["xv"] + dx, m["y"], m["lo"], m["hi"], color=style.COLOR["api"], hollow=hollow, size=5
            )
        for flag, text, dy in (("chosen", "frozen", -16), ("best", "val-A pick", 10)):
            f = sub[(sub["role"] == flag) & (sub["series"] == "val_a") & (sub["y"] > 0.5)]
            for _, r in f.iterrows():
                y = float(
                    ic.loc[(ic["series"] == "val_a") & (ic["xv"] == r["xv"]), "hi" if dy > 0 else "lo"].iloc[
                        0
                    ]
                )
                ax.annotate(
                    text,
                    (float(r["xv"]) - 0.1, y),
                    xytext=(0, 3 if dy > 0 else -3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if dy > 0 else "top",
                    fontsize=style.SIZE_NOTE,
                    color=style.INK_2,
                )
        style.zero_line(ax)
        ticks = ic.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(ticks["xv"].to_numpy(), ticks["x"].tolist())
        ax.set_xlim(-0.5, 4.5)
        ax.grid(axis="x", visible=False)
        ax.set_xlabel("encoding of numbers in the state")
        style.title(ax, letter, NAME_OF[model])
    axes[0][0].set_ylabel("daily IC of N̂ with z_cc (95% CI)")
    handles = [
        Line2D(
            [],
            [],
            color=style.COLOR["api"],
            marker="o",
            linestyle="none",
            markersize=5,
            markeredgecolor=style.SURFACE,
            label="val-A (search)",
        ),
        Line2D(
            [],
            [],
            color=style.COLOR["api"],
            marker="o",
            linestyle="none",
            markersize=5,
            markerfacecolor=style.SURFACE,
            label="val-B (confirmation)",
        ),
    ]
    fig.legend(handles=handles, loc="outside upper center", ncols=2, handletextpad=0.3)
    return fig


def identifiability(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_DOUBLE, 3.6, [["a", "b", "c"]], width_ratios=[1.1, 1.0, 1.15])
    a, b, c = axd["a"], axd["b"], axd["c"]
    acc = df[df["role"] == "accuracy"].sort_values("y", ascending=False).reset_index(drop=True)
    for i, (_, r) in enumerate(acc.iterrows()):
        a.barh(i, float(r["y"]), height=0.55, color=color(str(r["series"])), linewidth=0, zorder=2)
        a.text(
            float(r["y"]) + 0.01,
            i,
            f"{float(r['y']):.0%}",
            va="center",
            fontsize=style.SIZE_NOTE,
            color=style.INK_2,
        )
    _rows(a, [NAME_OF[str(s)] for s in acc["series"]])
    base = float(df.loc[df["role"] == "baseline", "y"].iloc[0])
    bar = float(df.loc[df["role"] == "threshold", "y"].iloc[0])
    a.axvline(base, color=style.INK_2, linewidth=0.8, zorder=3)
    a.axvline(bar, color=style.INK, linewidth=0.8, linestyle=(0, (3, 2)), zorder=3)

    a.set_xlim(0, 0.95)
    a.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    a.set_xlabel("company identified (masked states)")
    style.title(a, "a", "Company identification")
    for ax, letter, roles, title in (
        (b, "b", ("masked", "unmasked"), "Masked vs unmasked"),
        (c, "c", ("real", "shuffled"), "Real vs shuffled"),
    ):
        sub = df[df["panel"] == letter]
        models = list(dict.fromkeys(sub["series"]))
        for i, m in enumerate(models):
            for role, dy, hollow in ((roles[0], -0.15, False), (roles[1], 0.15, True)):
                r = sub[(sub["series"] == m) & (sub["role"] == role)]
                style.dots(
                    ax,
                    r["y"],
                    [i + dy],
                    r["lo"],
                    r["hi"],
                    color=color(str(m)),
                    hollow=hollow,
                    size=4.5,
                    horizontal=True,
                )
        _rows(ax, [NAME_OF.get(str(m), str(m)) for m in models])
        style.zero_line(ax, horizontal=False)
        ax.set_xlabel("daily IC (val-A, 95% CI)")
        style.title(ax, letter, title + "*")
    fig.legend(
        handles=[
            Line2D([], [], color=style.INK_2, linewidth=0.8, label=f"(a) matched baseline, {base:.0%}"),
            Line2D(
                [],
                [],
                color=style.INK,
                linewidth=0.8,
                linestyle=(0, (3, 2)),
                label=f"(a) §8.3 screen bar, {bar:.0%}",
            ),
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                label="(b) masked; (c) real news",
            ),
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4.5,
                markerfacecolor=style.SURFACE,
                label="(b) unmasked; (c) shuffled news",
            ),
        ],
        loc="outside lower center",
        ncols=2,
        handletextpad=0.4,
        handlelength=1.6,
    )
    fig.suptitle(
        "* exploratory (post hoc): the probes' descriptive columns (NA-11), not hypotheses",
        x=0.01,
        ha="left",
        fontsize=style.SIZE_NOTE,
        color=style.INK_2,
        fontweight="normal",
    )
    return fig


def ablations(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_SINGLE, 2.6, 1, 2, sharey=True)
    labels = {"j": "J", "c": "C", "n_hat": "N̂"}
    for ax, letter, title in zip(axes[0], "ab", ("News removed", "Shuffled news"), strict=True):
        sub = df[df["panel"] == letter]
        for role, dx, hollow in (("real", -0.12, False), ("ablated", 0.12, True)):
            m = sub[sub["role"] == role].sort_values("xv")
            style.dots(
                ax, m["xv"] + dx, m["y"], m["lo"], m["hi"], color=style.COLOR["api"], hollow=hollow, size=4.5
            )
        style.zero_line(ax)
        ticks = sub.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(ticks["xv"].to_numpy(), [labels[x] for x in ticks["x"]])
        ax.set_xlim(-0.5, 2.5)
        ax.grid(axis="x", visible=False)
        style.title(ax, letter, title)
    axes[0][0].set_ylabel("IC with y2 (d1-ultra, 95% CI)")
    axes[0][1].legend(
        handles=[
            Line2D(
                [],
                [],
                color=style.COLOR["api"],
                marker="o",
                linestyle="none",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                label="real",
            ),
            Line2D(
                [],
                [],
                color=style.COLOR["api"],
                marker="o",
                linestyle="none",
                markersize=4.5,
                markerfacecolor=style.SURFACE,
                label="ablated",
            ),
        ],
        loc="upper right",
        handletextpad=0.3,
    )
    return fig


VARIANTS: Final = {
    "main": "main estimate",
    "dollar_volume_tiers": "dollar-volume tiers",
    "exclude_date_only_hour": "no date-only / hour-stamped article",
    "exclude_half_days": "no half day",
    "non_overlapping": "non-overlapping (≥ 5 sessions)",
    "exclude_delisting_flag": "no delisting flag",
    "without_price_move_text": "without price-move text",
    "w0_cutoff_08:00_approx": "08:00 W0 cutoff (approx.)",
    "timing_before_04:00": "latest article before 04:00",
    "timing_04:00_08:00": "latest article 04:00–08:00",
    "timing_08:00_09:15": "latest article 08:00–09:15",
}
FOREST_TITLES: Final = {"a": "Laya-Fin: H1", "b": "Laya-Fin: H1b", "c": "Laya-Fin: IC", "d": "d1-ultra: H1"}


def robustness(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 3.6, 1, 4, sharey=True)
    for ax, letter in zip(axes[0], "abcd", strict=True):
        sub = df[df["panel"] == letter]
        model = str(sub["series"].iloc[0])
        for role, dy, hollow in (("main", 0.0, False), ("raw", -0.13, False), ("placebo", 0.13, True)):
            m = sub[sub["role"] == role]
            style.dots(
                ax,
                m["y"],
                m["xv"] + dy,
                m["lo"],
                m["hi"],
                color=style.COLOR[model],
                hollow=hollow,
                size=5 if role == "main" else 4,
                marker="D" if role == "main" else "o",
                horizontal=True,
            )
        style.zero_line(ax, horizontal=False)
        style.title(ax, letter, FOREST_TITLES[letter])
        ax.set_xlabel("estimate (95% CI)")
        ax.axhline(0.5, color=style.BASELINE, linewidth=0.6)
    labels = [VARIANTS[v] for v in VARIANTS]
    _rows(axes[0][0], labels)
    fig.legend(
        handles=[
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="D",
                linestyle="none",
                markersize=5,
                markeredgecolor=style.SURFACE,
                label="main (t1b; the IC from t3)",
            ),
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4,
                markeredgecolor=style.SURFACE,
                label="variant, raw",
            ),
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4,
                markerfacecolor=style.SURFACE,
                label="variant, placebo-adjusted",
            ),
        ],
        loc="outside upper center",
        ncols=3,
        handletextpad=0.3,
    )
    return fig


SIGNAL_ROWS: Final = ("laya_fin", "laya_zs", "d1_ultra", "span_02", "drex_v2", "sentiment", "tags_gbm")
TIER_MARK: Final = {"top100": ("o", "Top-100"), "mid": ("s", "101–250"), "rest": ("^", "251–500")}


def exploratory_d0(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 3.3, 1, 3, sharey=True)
    a, b, c = axes[0]
    labels = [NAME_OF[s] for s in SIGNAL_ROWS]
    e = df[df["panel"] == "a"]
    for _, r in e.iterrows():
        dy = {
            ("earnings", "test"): -0.24,
            ("earnings", "val_b"): -0.08,
            ("rest", "test"): 0.08,
            ("rest", "val_b"): 0.24,
        }[(str(r["role"]), str(r["label"]))]
        style.dots(
            a,
            [r["y"]],
            [float(r["xv"]) + dy],
            [r["lo"]],
            [r["hi"]],
            color=color(str(r["series"])),
            hollow=r["label"] == "val_b",
            marker="o" if r["role"] == "earnings" else "s",
            size=4,
            horizontal=True,
        )
    style.title(a, "a", "Earnings vs other days")
    a.set_xlabel("daily IC with z_cc (95% CI)")
    handles = [
        *[
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker=mk,
                linestyle="none",
                markersize=4,
                markeredgecolor=style.SURFACE,
                label=f"(b) {lab}",
            )
            for mk, lab in TIER_MARK.values()
        ],
    ]
    handles.append(
        Line2D(
            [],
            [],
            color=style.BASELINE,
            linewidth=3.0,
            label="(c) within-company shuffle: 95% range, tick = mean",
        )
    )
    fig.legend(
        handles=[
            *handles,
            *[
                Line2D(
                    [],
                    [],
                    color=style.INK_2,
                    marker="o",
                    linestyle="none",
                    markersize=4,
                    markeredgecolor=style.SURFACE,
                    label="(a) earnings days, test",
                ),
                Line2D(
                    [],
                    [],
                    color=style.INK_2,
                    marker="o",
                    linestyle="none",
                    markersize=4,
                    markerfacecolor=style.SURFACE,
                    label="(a) earnings days, val-B",
                ),
                Line2D(
                    [],
                    [],
                    color=style.INK_2,
                    marker="s",
                    linestyle="none",
                    markersize=4,
                    markeredgecolor=style.SURFACE,
                    label="(a) other events, test",
                ),
                Line2D(
                    [],
                    [],
                    color=style.INK_2,
                    marker="s",
                    linestyle="none",
                    markersize=4,
                    markerfacecolor=style.SURFACE,
                    label="(a) other events, val-B",
                ),
            ],
        ],
        loc="outside lower center",
        ncols=4,
        handletextpad=0.3,
    )
    t = df[df["panel"] == "b"]
    for _, r in t.iterrows():
        mk, _ = TIER_MARK[str(r["label"])]
        dy = {"top100": -0.2, "mid": 0.0, "rest": 0.2}[str(r["label"])]
        style.dots(
            b,
            [r["y"]],
            [float(r["xv"]) + dy],
            [r["lo"]],
            [r["hi"]],
            color=color(str(r["series"])),
            marker=mk,
            size=4,
            horizontal=True,
        )
    style.title(b, "b", "Size tiers (test)")
    b.set_xlabel("daily IC with z_cc (95% CI)")
    s = df[df["panel"] == "c"]
    for _, r in s[s["role"] == "null"].iterrows():
        c.hlines(float(r["xv"]), r["lo"], r["hi"], color=style.BASELINE, linewidth=3.0, zorder=1)
        c.plot([r["y"]], [r["xv"]], marker="|", markersize=7, color=style.MUTED, zorder=2)
    for _, r in s[s["role"] == "sd"].iterrows():
        style.dots(c, [r["y"]], [float(r["xv"])], color=color(str(r["series"])), size=5, horizontal=True)
    style.title(c, "c", "Per-company spread (test)")
    c.set_xlabel("SD of per-company correlations")
    for ax in (a, b):
        style.zero_line(ax, horizontal=False)
    _rows(a, labels)
    _banner(fig, VENDOR, SPAN)
    return fig


MA_LABELS: Final = {
    "all": "all crosses",
    "none": "no D0 event in t−2..t",
    "agree_laya_fin": "agree, Laya-Fin",
    "disagree_laya_fin": "disagree, Laya-Fin",
    "agree_d1_ultra": "agree, d1-ultra",
    "disagree_d1_ultra": "disagree, d1-ultra",
}


def exploratory_ma_cross(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_DOUBLE, 2.9, [["a", "b", "c"]], width_ratios=[1.0, 1.0, 1.1])
    for letter, title in (("a", "5 days after a cross"), ("b", "20 days")):
        ax = axd[letter]
        sub = df[df["panel"] == letter]
        for period, dy, hollow in (("validation", -0.14, True), ("test", 0.14, False)):
            m = sub[sub["role"] == period]
            style.dots(
                ax,
                m["y"],
                m["xv"] + dy,
                m["lo"],
                m["hi"],
                color=style.INK_2,
                hollow=hollow,
                size=4.5,
                horizontal=True,
            )
        style.zero_line(ax, horizontal=False)
        ax.set_xlabel("mean, bp (95% CI)")
        style.title(ax, letter, title)
    groups = list(dict.fromkeys(df.loc[df["panel"] == "a", "series"]))
    _rows(axd["a"], [MA_LABELS[g] for g in groups])
    _rows(axd["b"], [""] * len(groups))
    fig.legend(
        handles=[
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4.5,
                markerfacecolor=style.SURFACE,
                label="validation (the design was chosen here)",
            ),
            Line2D(
                [],
                [],
                color=style.INK_2,
                marker="o",
                linestyle="none",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                label="test (run once)",
            ),
        ],
        loc="outside lower center",
        ncols=2,
        handletextpad=0.3,
    )
    c = axd["c"]
    f = df[df["panel"] == "c"]
    c.plot(pd.to_datetime(f["x"]), f["y"], color=style.INK, linewidth=style.LINE)
    style.zero_line(c)
    c.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    style.month_ticks(c, (2, 4, 6), "%b")
    c.set_ylabel("cumulative net return, 10 bp")
    style.title(c, "c", "No-news fade, test")
    _banner(fig)
    return fig
