"""Figure 5: explaining realized moves (PREREG A3, after Kelly–Su–Zhang; NA-12 t10).

    uv run python -m newsaction.figures.render fig5_explaining_moves

(a) The news steps of the explanation ladder on their own scale: the out-of-sample R² of the stock-specific
move z_cc after the ex-ante (D0) news and after the same-day news, for Laya-Fin and d1-ultra, with 95%
bootstrap intervals. (b) d1-ultra's R² once the explanation features are added (Call B reads the move), by
cut, on a scale a hundred times larger.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from newsaction.figures import render, style

NAME = "fig5_explaining_moves"
STEPS: Final = {"ex_ante": "ex-ante news (D0)", "ex_post": "same-day news"}
CUTS: Final = {
    "all": "all member-days",
    "event_days": "event days",
    "tier:top100": "Top 100",
    "tier:mid": "101 to 250",
    "tier:rest": "251 to 500",
}
DX: Final = {"laya_fin": -0.04, "d1_ultra": 0.04}


def _pct(decimals: int) -> FuncFormatter:
    return FuncFormatter(lambda v, _: f"{100 * v:.{decimals}f}%")


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 2.3, [["a", "b"]], width_ratios=[1.0, 1.25])
    a, b = axd["a"], axd["b"]
    pa = df[df["panel"] == "a"]
    for model in ("laya_fin", "d1_ultra"):
        m = pa[pa["series"] == model].sort_values("xv")
        c = style.color(model)
        x = m["xv"] + DX[model]
        a.plot(x, m["y"], color=c, linewidth=style.LINE_THIN, zorder=2)
        style.dots(a, x, m["y"], m["lo"], m["hi"], color=c)
        style.label(a, float(x.iloc[-1]) + 0.08, float(m["y"].iloc[-1]), style.NAME[model], ha="left")
    steps = pa.drop_duplicates("xv").sort_values("xv")
    a.set_xticks(steps["xv"].tolist(), [STEPS[str(s)] for s in steps["x"]])
    a.set_xlim(-0.35, 1.75)
    a.grid(axis="x", visible=False)
    style.zero_line(a)
    a.yaxis.set_major_formatter(_pct(1))
    a.set_ylabel(r"out-of-sample $R^2$ of $z_{cc}$")
    style.title(a, "a", "News steps")

    pb = df[df["panel"] == "b"]
    rows = [(str(x), CUTS[str(x)]) for x in pb.sort_values("xv")["x"]]
    ys = style.row_axis(b, rows)
    for cut, y in ys.items():
        r = pb[pb["x"] == cut].iloc[0]
        style.dots(b, [r["y"]], [y], [r["lo"]], [r["hi"]], color=style.color("d1_ultra"), horizontal=True)
    style.zero_line(b, horizontal=False)
    b.set_xlim(0.0, 0.45)
    b.xaxis.set_major_formatter(_pct(0))
    b.set_xlabel(r"out-of-sample $R^2$ of $z_{cc}$, with the explanation")
    style.title(b, "b", "d1-ultra, after reading the move")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
