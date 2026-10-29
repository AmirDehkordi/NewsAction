"""Figure 6: filter efficiency, material recall against the share of days selected (NA-03, val-A).

    uv run python -m newsaction.figures.fig6_filters

Each filter's frontier over NA-03's budgets; the frozen filter (F5, the embedding logistic regression) at its
30% budget is marked. F6 (LightGBM) is within one point and loses the tie on fewer inputs; the rule filters
F1–F4 sit near random selection (recall = share, the thin diagonal).
"""

from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from newsaction.figures import render, style

NAME = "fig6_filters"
FILTERS = {
    "F0": ("F0 clean", style.BASELINE, style.LINE_THIN),
    "F1": ("F1 material rules", style.BASELINE, style.LINE_THIN),
    "F2": ("F2 hard + timely", style.BASELINE, style.LINE_THIN),
    "F3": ("F3 source quality", style.BASELINE, style.LINE_THIN),
    "F4": ("F4 novelty", style.BASELINE, style.LINE_THIN),
    "F6": ("F6 LightGBM", style.INK_2, style.LINE_THIN),
    "F5": ("F5 embedding LR (frozen)", style.INK, style.LINE),
}


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_SINGLE, 2.9)
    ax = axes[0][0]
    ax.plot([0, 1], [0, 1], color=style.GRID, linewidth=0.8, zorder=1)
    fr = df[df["role"] == "frontier"]
    for f, (_, color, lw) in FILTERS.items():
        m = fr[fr["series"] == f].sort_values("xv")
        ax.plot(m["xv"], m["y"], color=color, linewidth=lw, zorder=3 if f == "F5" else 2)
    ch = df[df["role"] == "chosen"].iloc[0]
    style.dots(ax, [ch["xv"]], [ch["y"]], color=style.INK, size=6.5, zorder=5)
    ax.annotate(
        f"frozen: F5 at {float(ch['xv']):.0%} of days,\nmaterial recall {float(ch['y']):.3f}",
        (float(ch["xv"]), float(ch["y"])),
        xytext=(10, -22),
        textcoords="offset points",
        fontsize=style.SIZE_NOTE,
        color=style.INK_2,
        arrowprops={"arrowstyle": "-", "color": style.INK_2, "linewidth": 0.6},
    )
    lim = float(max(fr["xv"].max(), fr["y"].max())) * 1.04
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("share of eval days selected")
    ax.set_ylabel("material recall")
    handles = [
        Line2D([], [], color=style.INK, linewidth=style.LINE, label=FILTERS["F5"][0]),
        Line2D([], [], color=style.INK_2, linewidth=style.LINE_THIN, label=FILTERS["F6"][0]),
        Line2D(
            [], [], color=style.BASELINE, linewidth=style.LINE_THIN, label="F0–F4 (clean, rules, novelty)"
        ),
        Line2D([], [], color=style.GRID, linewidth=0.8, label="random days (recall = share)"),
    ]
    ax.legend(handles=handles, loc="upper left", handlelength=1.6)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
