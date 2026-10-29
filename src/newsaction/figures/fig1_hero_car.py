"""Figure 1 (hero): do prices converge to what the decision model says the news is worth? (PREREG A1)

    uv run python -m newsaction.figures.fig1_hero_car

(a, b) Mean CAR^lvl of the test period's D0 events by decile of the model's value V, from the previous close
through the open, 10:00, the close and t+1 … t+20, each against its decile's mean V (dashed): Laya-Fin, the
primary instrument, and d1-ultra, the API comparator (model-specific). Deciles 1, 2, 9 and 10 carry the
diverging colours, 3–8 are the gray middle; the extreme deciles carry 95% bands (±1.96 event-level SE).
(c) κ_h, the slope of CAR^lvl_h on V, with 95% intervals from the two-way clustered SE, against full
convergence at 1; the gap's half-life as stored (∞: not reached within t+20). (d) d1-ultra's signed
Under / Fair / Over paths (D2 events) against their mean signed V; Laya-Fin's classes are too few to draw.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from newsaction.figures import render, style

NAME = "fig1_convergence"
DECILE_COLOR = {10: style.BLUE[650], 9: style.BLUE[450], 2: style.RED_450, 1: style.RED_650}
CLASS_COLOR = {"Over": style.BLUE[450], "Fair": style.MUTED, "Under": style.RED_450}
DECISIONS = (1, 2, 3)
TICKS = {
    "C(t−1)": "C$_{t-1}$",
    "O(t)": "O$_t$\nD0",
    "10:00": "10:00\nD1",
    "C(t)": "C$_t$\nD2",
    "t+1": "+1",
    "t+2": "+2",
    "t+5": "+5",
    "t+10": "+10",
    "t+20": "+20",
}
XLABEL = "event time (+k: the close of session t + k)"
DODGE = {"laya_fin": -0.14, "d1_ultra": 0.0, "anchor": 0.14}
TARGET_DASH = (0, (3.0, 2.0))


def _rungs(ax: Axes, sub: pd.DataFrame, right: float = 8.4) -> None:
    """Ordinal event-time ticks; the decision points (D0 open, D1 10:00, D2 close) are named on the axis."""
    ticks = sub.dropna(subset=["xv"]).drop_duplicates("xv").sort_values("xv")
    ax.set_xticks(ticks["xv"].to_numpy(), [TICKS[x] for x in ticks["x"]])
    ax.set_xlim(-0.4, right)
    ax.set_xlabel(XLABEL)
    ax.grid(axis="x", visible=False)


def _decisions(ax: Axes, which: tuple[int, ...] = DECISIONS) -> None:
    for x in which:
        ax.axvline(x, color=style.BASELINE, linewidth=0.6, zorder=1)


def _deciles(ax: Axes, sub: pd.DataFrame) -> None:
    paths, targets = sub[sub["role"] == "path"], sub[sub["role"] == "target"]
    groups = sorted({int(s.split("_")[1]) for s in paths["series"]}, key=lambda g: (g in DECILE_COLOR, g))
    for g in groups:
        p = paths[paths["series"] == f"decile_{g}"].sort_values("xv")
        color = DECILE_COLOR.get(g, style.BASELINE)
        strong = g in DECILE_COLOR
        ax.plot(
            p["xv"],
            p["y"],
            color=color,
            linewidth=style.LINE if strong else style.LINE_THIN,
            zorder=3 if strong else 2,
        )
        if g in (1, 10):
            style.band(ax, p["xv"].tolist(), p["lo"].tolist(), p["hi"].tolist(), color)
        tv = float(targets.loc[targets["series"] == f"decile_{g}", "y"].iloc[0])
        ax.hlines(
            tv,
            0.6,
            8.4,
            colors=color,
            linestyles=TARGET_DASH,
            linewidth=style.LINE_THIN if strong else 0.6,
            zorder=2,
        )
    style.zero_line(ax)
    _rungs(ax, paths)
    _decisions(ax)


def _kappa(ax: Axes, sub: pd.DataFrame) -> None:
    k = sub[sub["role"] == "kappa"]
    handles = []
    for model in ("anchor", "d1_ultra", "laya_fin"):
        m = k[k["series"] == model].sort_values("xv")
        x = m["xv"].to_numpy() + DODGE[model]
        color = style.COLOR[model]
        ax.plot(x, m["y"], color=color, linewidth=style.LINE_THIN, zorder=2)
        style.dots(ax, x, m["y"], m["lo"], m["hi"], color=color, size=4.5)
        label = style.LABEL[model] + (f", {style.ANCHOR_NOTE}" if model == "anchor" else "")
        handles.append(
            Line2D(
                [],
                [],
                color=color,
                marker="o",
                markersize=4.5,
                markeredgecolor=style.SURFACE,
                linewidth=style.LINE_THIN,
                label=label,
            )
        )
    ax.axhline(1.0, color=style.INK_2, linewidth=0.8, zorder=1.5)
    ax.text(
        8.35,
        1.02,
        "full convergence, κ = 1",
        ha="right",
        va="bottom",
        fontsize=style.SIZE_NOTE,
        color=style.INK_2,
    )
    style.zero_line(ax)
    h = sub[sub["role"] == "half_life"]
    if len(h) and bool(np.isinf(h["y"].to_numpy()).all()):
        style.note(
            ax,
            0.98,
            0.03,
            "half-life of the gap U = V − G (λ ≥ 0.5):\nnot reached within t+20",
            ha="right",
            va="bottom",
        )
    _rungs(ax, k)
    ax.set_xlim(0.4, 8.4)
    ax.set_ylim(-0.62, 1.12)
    _decisions(ax)
    ax.legend(
        handles=[handles[2], handles[0], handles[1]],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.3),
        ncols=2,
        handletextpad=0.3,
        columnspacing=1.0,
    )


def _classes(ax: Axes, sub: pd.DataFrame) -> None:
    paths, targets = sub[sub["role"] == "path"], sub[sub["role"] == "target"]
    n = sub[sub["role"] == "n_events"]
    for g in ("Fair", "Under", "Over"):
        p = paths[paths["series"] == g].sort_values("xv")
        color = CLASS_COLOR[g]
        ax.plot(p["xv"], p["y"], color=color, linewidth=style.LINE, zorder=3)
        style.band(ax, p["xv"].tolist(), p["lo"].tolist(), p["hi"].tolist(), color)
        tv = float(targets.loc[targets["series"] == g, "y"].iloc[0])
        ax.hlines(tv, 2.6, 8.3, colors=color, linestyles=TARGET_DASH, linewidth=style.LINE_THIN, zorder=2)
        cnt = int(n.loc[(n["label"] == "d1_ultra") & (n["series"] == g), "y"].iloc[0])
        style.end_label(ax, 8.4, float(p["y"].iloc[-1]), f"{g}\nn = {cnt:,}", ha="left")
    style.zero_line(ax)
    _rungs(ax, paths, right=10.4)
    _decisions(ax, (3,))
    laya = int(n.loc[n["label"] == "laya_fin", "y"].sum())
    style.note(
        ax,
        0.6,
        0.6,
        f"Laya-Fin: only {laya:,} events have |N̂| ≥ 0.5,\nso its class paths are not drawn",
        ha="center",
        va="center",
    )


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 5.6, 2, 2)
    (a, b), (c, d) = axes
    _deciles(a, df[df["panel"] == "a"])
    _deciles(b, df[df["panel"] == "b"])
    lo = min(a.get_ylim()[0], b.get_ylim()[0])
    hi = max(a.get_ylim()[1], b.get_ylim()[1])
    for ax in (a, b):
        ax.set_ylim(lo, hi)
        ax.set_ylabel("CAR$^{lvl}$ (typical daily moves)")
    style.title(a, "a", "Laya-Fin (primary instrument)")
    style.title(b, "b", "d1-ultra (model-specific)")
    handles = [
        Line2D([], [], color=DECILE_COLOR[10], linewidth=style.LINE, label="V decile 10 (most positive)"),
        Line2D([], [], color=DECILE_COLOR[9], linewidth=style.LINE, label="decile 9"),
        Line2D([], [], color=style.BASELINE, linewidth=style.LINE_THIN, label="deciles 3–8"),
        Line2D([], [], color=DECILE_COLOR[2], linewidth=style.LINE, label="decile 2"),
        Line2D([], [], color=DECILE_COLOR[1], linewidth=style.LINE, label="decile 1 (most negative)"),
        Line2D(
            [],
            [],
            color=style.INK_2,
            linewidth=style.LINE_THIN,
            linestyle=TARGET_DASH,
            label="the decile's mean V (target)",
        ),
    ]
    fig.legend(handles=handles, loc="outside upper center", ncols=3, handlelength=1.8, columnspacing=1.2)
    _kappa(c, df[df["panel"] == "c"])
    c.set_ylabel("κ$_h$: slope of CAR$^{lvl}_h$ on V")
    style.title(c, "c", "Convergence ladder κ$_h$ (95% CI)")
    _classes(d, df[df["panel"] == "d"])
    d.set_ylabel("sign(N̂)·CAR$^{lvl}$")
    style.title(d, "d", "d1-ultra: Under / Fair / Over, D2")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
