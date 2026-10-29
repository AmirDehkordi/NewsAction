"""Figure 2: drift after the close against the size of the day's move, by news strength (NA-12 figure data).

    uv run python -m newsaction.figures.fig2_drift_vs_move

Mean sign(G)·y2 (the D2 drift from the next open to the close of t+5, in the direction of the day's move G) by
bin of |G|, one panel per tercile of news strength |V_W2|, with 95% intervals (±1.96 event-level SE). Large
moves (|G| ≥ 3) reverse slightly in every tercile; smaller moves do not; there is no small-move
underreaction.
"""

from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from newsaction.figures import render, style

NAME = "fig2_drift_vs_move"
PANELS = (("a", "weak news"), ("b", "medium news"), ("c", "strong news"))
BINS = {"[0, 0.5)": "0–0.5", "[0.5, 1)": "0.5–1", "[1, 2)": "1–2", "[2, 3)": "2–3", "[3, inf)": "≥ 3"}
MODELS = ("laya_fin", "d1_ultra", "anchor")
DODGE = {"laya_fin": -0.2, "d1_ultra": 0.0, "anchor": 0.2}


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 2.6, 1, 3, sharey=True)
    for ax, (letter, title) in zip(axes[0], PANELS, strict=True):
        sub = df[df["panel"] == letter]
        ax.axvspan(3.5, 4.5, color=style.GRID, alpha=0.6, linewidth=0, zorder=0)
        for model in MODELS:
            m = sub[sub["series"] == model].sort_values("xv")
            style.dots(ax, m["xv"] + DODGE[model], m["y"], m["lo"], m["hi"], color=style.COLOR[model], size=5)
        style.zero_line(ax)
        ticks = sub.drop_duplicates("xv").sort_values("xv")
        ax.set_xticks(ticks["xv"].to_numpy(), [BINS[x] for x in ticks["x"]])
        ax.set_xlim(-0.5, 4.5)
        ax.grid(axis="x", visible=False)
        style.title(ax, letter, title)
    axes[0][0].set_ylabel("drift after D2: sign(G)·y2")
    fig.supxlabel(
        "|G|, the day's move at D2 (typical daily moves); panels: terciles of news strength |V|",
        fontsize=style.SIZE_LABEL,
        color=style.INK_2,
    )
    style.note(axes[0][2], 0.97, 0.97, "|G| ≥ 3", ha="right", va="top")
    handles = [
        Line2D(
            [],
            [],
            color=style.COLOR[m],
            marker="o",
            linestyle="none",
            markersize=5,
            markeredgecolor=style.SURFACE,
            label=style.LABEL[m] + suffix,
        )
        for m, suffix in (
            ("laya_fin", " (primary)"),
            ("d1_ultra", " (model-specific)"),
            ("anchor", f", {style.ANCHOR_NOTE}"),
        )
    ]
    fig.legend(handles=handles, loc="outside upper center", ncols=3, handletextpad=0.3, columnspacing=1.4)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
