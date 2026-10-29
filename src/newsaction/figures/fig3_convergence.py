"""Figure 3: convergence to the news-implied value (PREREG A1; NA-12 figure data, t6, t7).

    uv run python -m newsaction.figures.render fig3_convergence

(a) d1-ultra's top and bottom V deciles: CAR^lvl from the previous close with ±1.96 event-level SE bands,
against each decile's mean V (dashed target); the other deciles are in the appendix. (b) The convergence
ladder κ_h of Laya-Fin and d1-ultra with 95% intervals, against full convergence at κ = 1, and the gap's
half-life, which is not reached within t+20. Event time is not to scale.
"""

from __future__ import annotations

import math
from typing import Final

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from newsaction.figures import render, style

NAME = "fig3_convergence"
DECILES: Final = (("decile_10", "top decile"), ("decile_1", "bottom decile"))
DX: Final = {"laya_fin": -0.09, "d1_ultra": 0.09}


SPARSE: Final = ("car_pre1", "car_post0", "car_post5", "car_post20", "O_t", "C_t", "C_t+5", "C_t+20")


def ticks(ax: Axes, rows: pd.DataFrame, *, sparse: bool = False) -> None:
    """The event-time rungs of ``rows`` (``x`` and ``xv``); ``sparse`` labels only some of them (narrow
    panels)."""
    pts = rows.drop_duplicates("xv").sort_values("xv")
    labels = [style.RUNG_LABEL[str(x)] if not sparse or str(x) in SPARSE else "" for x in pts["x"]]
    style.rung_axis(ax, pts["xv"].tolist(), labels)


def deciles(ax: Axes, d: pd.DataFrame, model: str, groups: tuple[tuple[str, str], ...]) -> None:
    """The extreme deciles of one model: paths with SE bands and their dashed targets, labelled at the end."""
    c = style.color(model)
    for series, text in groups:
        p = d[(d["series"] == series) & (d["role"] == "path")].sort_values("xv")
        style.band(ax, p["xv"], p["lo"], p["hi"], c)
        ax.plot(p["xv"], p["y"], color=c, zorder=3)
        target = float(d[(d["series"] == series) & (d["role"] == "target")]["y"].iloc[0])
        style.ref_line(ax, target, color=c)
        end = p.iloc[-1]
        style.label(ax, float(end["xv"]) + 0.15, float(end["y"]), text, ha="left")
        style.label(ax, float(p["xv"].iloc[0]) + 0.1, target, "mean $V$", va="bottom", color=style.INK_2)


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_FULL, 2.55, 1, 2, width_ratios=[1.0, 1.0])
    a, b = axes[0]
    pa = df[df["panel"] == "a"]
    deciles(a, pa, "d1_ultra", DECILES)
    style.zero_line(a)
    ticks(a, pa[pa["role"] == "path"])
    a.set_xlim(-0.35, 10.2)
    a.set_ylabel(r"$\mathrm{CAR}^{\mathrm{lvl}}$ (typical daily moves)")
    style.title(a, "a", r"d1-ultra, extreme deciles of $V$")

    pb = df[df["panel"] == "b"]
    k = pb[pb["role"] == "kappa"]
    for model in ("laya_fin", "d1_ultra"):
        m = k[k["series"] == model].sort_values("xv")
        c = style.color(model)
        x = m["xv"] + DX[model]
        b.plot(x, m["y"], color=c, linewidth=style.LINE_THIN, zorder=2)
        style.dots(b, x, m["y"], m["lo"], m["hi"], color=c)
        style.label(b, 8.45, float(m["y"].iloc[-1]), style.NAME[model], ha="left")
    style.ref_line(b, 1.0, color=style.INK_2)
    style.label(b, 1.0, 1.0, r"$\kappa_h = 1$", ha="left", va="bottom", color=style.INK_2)
    style.zero_line(b)
    life = pb[pb["role"] == "half_life"]
    if not all(math.isinf(float(v)) for v in life["y"]):
        raise ValueError("a finite half-life: the panel's annotation would be wrong")
    style.label(
        b,
        0.03,
        0.04,
        r"half-life: not reached within $t{+}20$",
        ha="left",
        va="bottom",
        transform=b.transAxes,
        color=style.INK_2,
    )
    ticks(b, k)
    b.set_xlim(0.6, 10.3)
    b.set_ylim(-0.3, 1.12)
    b.set_ylabel(r"$\kappa_h$, slope of $\mathrm{CAR}^{\mathrm{lvl}}_h$ on $V$")
    style.title(b, "b", r"Convergence ladder $\kappa_h$")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
