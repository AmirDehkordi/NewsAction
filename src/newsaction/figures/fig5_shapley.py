"""Figure 5: Shapley value of information at D2: price and reaction (R), news (N), judgments (J) (NA-12 t13).

    uv run python -m newsaction.figures.fig5_shapley

Exact Shapley values of the test-period out-of-sample R² (top row) and mean daily IC (bottom row) of y2 over
the feature groups R, N and J, by tier, with the full model's total (black diamond). The totals are about
zero or negative, so the shares of t13 are shares of nothing and are not drawn; the values are. H3's ridge
fits are at D2 only, so there is one decision point.
"""

from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from newsaction.figures import render, style

NAME = "fig5_shapley"
GROUPS = (
    ("R", style.SLOTS[4], "R: price and reaction"),
    ("N", style.SLOTS[5], "N: news (Call A)"),
    ("J", style.SLOTS[6], "J: judgments (Call B)"),
)
TIERS = {"all": "all", "top100": "Top-100", "mid": "101–250", "rest": "251–500"}
MODELS = (("laya_fin", "Laya-Fin"), ("d1_ultra", "d1-ultra"), ("anchor", f"anchor, {style.ANCHOR_NOTE}"))
WIDTH = 0.22
SCALE = 1e3


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 4.0, 2, 3, sharey="row")
    for row, metric, ylabel in (
        (0, "r2", "Shapley value of OOS R² (×10⁻³)"),
        (1, "ic", "Shapley value of IC (×10⁻³)"),
    ):
        for col, (model, name) in enumerate(MODELS):
            ax = axes[row][col]
            sub = df[(df["role"] == metric) & (df["label"] == model)]
            for i, (g, color, _) in enumerate(GROUPS):
                m = sub[sub["series"] == g].sort_values("xv")
                ax.bar(
                    m["xv"] + (i - 1) * WIDTH,
                    m["y"] * SCALE,
                    width=WIDTH - 0.03,
                    color=color,
                    linewidth=0,
                    zorder=2,
                )
            tot = sub[sub["series"] == "R+N+J"].sort_values("xv")
            ax.plot(
                tot["xv"],
                tot["y"] * SCALE,
                linestyle="none",
                marker="D",
                markersize=4.5,
                color=style.INK,
                markeredgecolor=style.SURFACE,
                markeredgewidth=0.8,
                zorder=4,
            )
            style.zero_line(ax)
            ticks = sub.drop_duplicates("xv").sort_values("xv")
            ax.set_xticks(ticks["xv"].to_numpy(), [TIERS[x] for x in ticks["x"]])
            ax.grid(axis="x", visible=False)
            if col == 0:
                ax.set_ylabel(ylabel)
            letter = "abcdef"[row * 3 + col]
            short = "anchor (uninformative)" if model == "anchor" else name
            style.title(ax, letter, f"{short}: {'R²' if metric == 'r2' else 'IC'}")
    handles: list[Patch | Line2D] = [Patch(color=c, linewidth=0, label=lab) for _, c, lab in GROUPS]
    handles.append(
        Line2D(
            [],
            [],
            linestyle="none",
            marker="D",
            markersize=4.5,
            color=style.INK,
            markeredgecolor=style.SURFACE,
            label="total, R + N + J",
        )
    )
    handles.append(Line2D([], [], linestyle="none", label=f"anchor: {style.ANCHOR_NOTE}"))
    fig.legend(handles=handles, loc="outside upper center", ncols=3, handlelength=1.4, columnspacing=1.4)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
