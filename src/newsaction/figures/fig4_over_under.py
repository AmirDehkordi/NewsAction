"""Figure 4: over- and under-reaction (PREREG §1.1 H2, A1; NA-12 figure data).

    uv run python -m newsaction.figures.render fig4_over_under

(a) d1-ultra's D2 events by RG class (Under, Fair, Over; pooled over the tiers), sign(N̂)·CAR^lvl with ±1.96
event-level SE bands, against each class's mean signed V, which each label gives (dashed in the class's
colour, dotted for Under, short dashes for Fair, long dashes for Over, because the three lie close).
(b) d1-ultra's drift after the close, sign(G)·y2, by bin of the day's move |G|, one line per tercile of news
strength |V|, with ±1.96 SE bands. The classes and terciles are ordered, so they take d1-ultra's orange ramp
(light to dark). Laya-Fin's panel (b) is Appendix Figure A8. Event time is not to scale.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from newsaction.figures import render, style

NAME = "fig4_over_under"
CLASSES: Final = ("Under", "Fair", "Over")
# The classes' mean V lie close together, so each dashed target has its own pattern besides its colour.
TARGET_DASHES: Final = {"Under": (1.0, 1.4), "Fair": (3.0, 1.6), "Over": (6.0, 1.6)}
TERCILES: Final = ("weak", "medium", "strong")
BINS: Final = {
    "[0, 0.5)": r"$[0, 0.5)$",
    "[0.5, 1)": r"$[0.5, 1)$",
    "[1, 2)": r"$[1, 2)$",
    "[2, 3)": r"$[2, 3)$",
    "[3, inf)": r"$\geq 3$",
}


def drift(ax: Axes, d: pd.DataFrame, model: str) -> None:
    """Mean sign(G)·y2 by |G| bin, one line per news-strength tercile of one model (its ordinal ramp), with
    thin
    95% intervals on dots offset within the bin."""
    ramp = style.RAMP[model]
    handles = []
    for t, c, dx in zip(TERCILES, ramp, (-0.13, 0.0, 0.13), strict=True):
        m = d[d["series"] == t].sort_values("xv")
        x = m["xv"] + dx
        ax.plot(x, m["y"], color=c, linewidth=style.LINE_THIN, zorder=3)
        style.dots(ax, x, m["y"], m["lo"], m["hi"], color=c, zorder=4)
        handles.append(style.key(c))
    style.zero_line(ax)
    bins = d.drop_duplicates("xv").sort_values("xv")
    ax.set_xticks(bins["xv"].tolist(), [BINS[str(b)] for b in bins["x"]])
    ax.set_xlim(-0.35, 4.35)
    ax.set_ylim(-0.45, 0.5)
    ax.set_xlabel(r"$|G|$, the day's move (typical daily moves)")
    ax.set_ylabel(r"$\mathrm{sign}(G)\,y_2$ (typical daily moves)")
    style.legend(
        ax,
        handles,
        list(TERCILES),
        title=r"news strength (tercile of $|V|$)",
        title_fontsize=style.SIZE,
        loc="upper left",
        ncols=3,
        borderaxespad=0.2,
        columnspacing=0.8,
        handletextpad=0.2,
    )


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.6, 1, 2, width_ratios=[1.0, 1.0])
    a, b = axes[0]
    pa = df[df["panel"] == "a"]
    paths = pa[pa["role"] == "path"]
    pos = {x: i for i, x in enumerate(sorted(paths["xv"].unique()))}
    for cls, c in zip(CLASSES, style.RAMP["d1_ultra"], strict=True):
        p = paths[paths["series"] == cls].sort_values("xv")
        x = p["xv"].map(pos)
        style.band(a, x, p["lo"], p["hi"], c)
        a.plot(x, p["y"], color=c, zorder=3)
        target = float(pa[(pa["series"] == cls) & (pa["role"] == "target")]["y"].iloc[0])
        a.plot(
            [0.0, float(x.iloc[-1])],
            [target, target],
            color=c,
            linewidth=0.9,
            dashes=TARGET_DASHES[cls],
            dash_capstyle="butt",
            zorder=2,
        )
        style.label(
            a,
            float(x.iloc[-1]) + 0.15,
            float(p["y"].iloc[-1]),
            f"{cls}, " + rf"$\bar V = {target:.2f}$",
            ha="left",
        )
    style.zero_line(a)
    pts = paths.drop_duplicates("xv").sort_values("xv")
    style.rung_axis(a, [pos[v] for v in pts["xv"]], [style.RUNG_LABEL[str(x)] for x in pts["x"]])
    a.set_xlim(-0.3, 9.3)
    a.set_ylabel(r"$\mathrm{sign}(\hat N)\cdot\mathrm{CAR}^{\mathrm{lvl}}$ (typical daily moves)")
    style.title(a, "a", "d1-ultra, Under, Fair and Over (D2)")

    drift(b, df[df["panel"] == "b"], "d1_ultra")
    style.title(b, "b", r"d1-ultra, drift after the close by $|G|$")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
