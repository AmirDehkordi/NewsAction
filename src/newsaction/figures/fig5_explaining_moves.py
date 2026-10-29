"""Figure 5: explaining realized moves (PREREG A3, after Kelly–Su–Zhang; NA-12 t10).

    uv run python -m newsaction.figures.render fig5_explaining_moves

(a) d1-ultra's out-of-sample R² of the stock-specific move z_cc by cut, stacked by step in the order of the
legend: the ex-ante (D0) news, + the same-day news, + the explanation (Call B reads the move), in the muted
component palette; each bar's total is written above its 95% bootstrap interval, and the two news steps,
too thin to read, are written beside the bar after a swatch of their colour (the ex-ante step's R², then
the same-day step's increment).
(b) The news steps on their own scale, the zoom that makes them readable: the R² after the ex-ante and after
the same-day news for Laya-Fin and d1-ultra, with 95% bootstrap intervals. R² in % of the stock-specific
variance.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.transforms import offset_copy

from newsaction.figures import render, style

NAME = "fig5_explaining_moves"
STEPS: Final = {
    "ex_ante": "ex-ante news (D0)",
    "ex_post": "+ same-day news (Call A)",
    "explanation": "+ explanation (Call B reads the move)",
}
CUTS: Final = {
    "all": "all days",
    "event_days": "event days",
    "tier:top100": "Top 100",
    "tier:mid": "101 to 250",
    "tier:rest": "251 to 500",
}
NEWS_STEPS: Final = {"ex_ante": "ex-ante\nnews (D0)", "ex_post": "same-day\nnews"}
WIDTH: Final = 0.44
GAP: Final = 0.4  # pt of surface between the stacked segments
DX: Final = {"laya_fin": -0.04, "d1_ultra": 0.04}
YLABEL: Final = r"out-of-sample $R^2$ of $z_{cc}$ (%)"


def _num(v: float, *, signed: bool = False) -> str:
    return f"${'+' if signed and v >= 0 else ''}{v:.2f}$"


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 2.7, [["a", "b"]], width_ratios=[1.55, 1.0])
    a, b = axd["a"], axd["b"]
    pa = df[df["panel"] == "a"]
    seg = pa[pa["role"] == "segment"]
    cuts = pa.drop_duplicates("xv").sort_values("xv")
    xs = cuts["xv"].to_numpy(dtype=float)
    bottom = np.zeros(len(xs))
    parts: dict[str, np.ndarray] = {}
    for step, colour in zip(STEPS, style.COMPONENT, strict=True):
        h = 100 * seg[seg["series"] == step].sort_values("xv")["y"].to_numpy(dtype=float)
        a.bar(
            xs,
            h,
            bottom=bottom,
            width=WIDTH,
            color=colour,
            edgecolor=style.SURFACE,
            linewidth=GAP,
            zorder=2,
        )
        parts[step] = h
        bottom = bottom + h
    tot = pa[pa["role"] == "total"].sort_values("xv")
    a.vlines(
        tot["xv"], 100 * tot["lo"], 100 * tot["hi"], color=style.INK, linewidth=style.LINE_THIN, zorder=3
    )
    for x, y, hi in zip(tot["xv"], tot["y"], tot["hi"], strict=True):
        t = a.annotate(
            f"${100 * float(y):.1f}$",
            (float(x), 100 * float(hi)),
            xytext=(0.0, 1.5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=style.SIZE,
            color=style.INK,
            bbox=dict(style.KNOCKOUT),
        )
        t.set_in_layout(False)
    # the news segments are a point or two tall: their values sit beside the bar, bottom to top as stacked,
    # each after a swatch of its segment's colour
    for x, v0, v1 in zip(xs, parts["ex_ante"], parts["ex_post"], strict=True):
        for i, (text, colour) in enumerate(
            ((_num(v0), style.COMPONENT[0]), (_num(v1, signed=True), style.COMPONENT[1]))
        ):
            dy = 3.8 + 7.6 * i
            key = offset_copy(a.transData, fig=fig, x=2.6, y=dy, units="points")
            a.plot(
                [x + WIDTH / 2],
                [0.0],
                marker="s",
                markersize=3.2,
                color=colour,
                linestyle="none",
                transform=key,
            )
            t = a.annotate(
                text,
                (x + WIDTH / 2, 0.0),
                xytext=(5.9, dy),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=style.SIZE_SMALL,
                color=style.INK_2,
            )
            t.set_in_layout(False)
    a.set_xticks(xs.tolist(), [CUTS[str(c)] for c in cuts["x"]])
    a.set_xlim(-0.45, float(xs.max()) + 0.75)
    a.set_ylim(0.0, 46.0)
    a.grid(axis="x", visible=False)
    a.set_ylabel(YLABEL)
    style.title(a, "a", "d1-ultra, by step")

    pb = df[df["panel"] == "b"]
    for model in ("laya_fin", "d1_ultra"):
        m = pb[pb["series"] == model].sort_values("xv")
        c = style.color(model)
        x = m["xv"] + DX[model]
        b.plot(x, 100 * m["y"], color=c, linewidth=style.LINE_THIN, zorder=2)
        style.dots(b, x, 100 * m["y"], 100 * m["lo"], 100 * m["hi"], color=c)
        style.label(b, float(x.iloc[-1]) + 0.08, 100 * float(m["y"].iloc[-1]), style.NAME[model], ha="left")
    steps = pb.drop_duplicates("xv").sort_values("xv")
    b.set_xticks(steps["xv"].tolist(), [NEWS_STEPS[str(s)] for s in steps["x"]])
    b.set_xlim(-0.35, 1.75)
    b.grid(axis="x", visible=False)
    style.zero_line(b)
    b.set_ylabel(YLABEL)
    style.title(b, "b", "News steps, on their own scale")

    style.legend(
        fig,
        [Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="none") for c in style.COMPONENT],
        list(STEPS.values()),
        loc="outside upper left",
        ncols=3,
        handlelength=1.0,
    )
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
