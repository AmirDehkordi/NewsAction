"""Figure 1: validation against test (NA-12 t14).

    uv run python -m newsaction.figures.render fig1_validation_test

A dumbbell per instrument: the daily IC of N̂_W0 with z_cc on val-B (hollow) and on test (filled), joined by a
segment, each with its 95% interval from the Newey–West t. Rows are grouped (trained, zero-shot, API models,
baselines); the vendor-label baselines carry †. The anchor is uninformative and appears in the appendix.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
from matplotlib.figure import Figure

from newsaction.figures import render, style

NAME = "fig1_validation_test"
GROUPS: Final = (
    ("trained", "Trained"),
    ("zero-shot", "Zero-shot"),
    ("api", "API models"),
    ("baseline", "Baselines"),
)
OFFSET: Final = 0.17


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 3.05)
    ax = axes[0][0]
    d = df[df["panel"] == "a"].sort_values("xv", kind="stable")
    rows: list[tuple[str, str]] = []
    for group, head in GROUPS:
        rows.append(("head", head))
        rows += [(m, style.NAME[m]) for m in dict.fromkeys(d.loc[d["label"] == group, "series"])]
    ys = style.row_axis(ax, rows)
    for model, y in ys.items():
        v = d[(d["series"] == model) & (d["role"] == "val_b")].iloc[0]
        t = d[(d["series"] == model) & (d["role"] == "test")].iloc[0]
        c = style.color(model)
        ax.plot([v["y"], t["y"]], [y + OFFSET, y - OFFSET], color=c, linewidth=style.LINE_HAIR, zorder=2)
        style.dots(ax, [v["y"]], [y + OFFSET], [v["lo"]], [v["hi"]], color=c, hollow=True, horizontal=True)
        style.dots(ax, [t["y"]], [y - OFFSET], [t["lo"]], [t["hi"]], color=c, horizontal=True)
    style.zero_line(ax, horizontal=False)
    ax.set_xlabel(r"daily IC of $\hat N$ with $z_{cc}$")
    ax.set_xlim(-0.07, 0.155)
    ax.set_xticks([-0.05, 0.0, 0.05, 0.10, 0.15])
    style.legend(
        ax,
        [style.key(style.INK_2, hollow=True), style.key(style.INK_2)],
        ["val-B", "test"],
        loc="lower left",
        bbox_to_anchor=(0.0, 1.0),
        ncols=2,
        borderaxespad=0.1,
    )
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
