"""Figure 2: priced at the open (NA-12 t3, t1b).

    uv run python -m newsaction.figures.render fig2_priced_at_open

(a) For each model, the daily IC of N̂_W0 with the overnight move z_on (filled) beside the IC with the move
after
the open z_id (hollow), with 95% bootstrap intervals; (b) H1, their difference, with its 95% bootstrap
interval. The anchor is uninformative and appears in the appendix tables.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
from matplotlib.figure import Figure

from newsaction.figures import render, style

NAME = "fig2_priced_at_open"
ROWS: Final = (
    ("head", "Trained"),
    ("laya_fin", "Laya-Fin"),
    ("head", "Zero-shot"),
    ("laya_zs", "Laya zero-shot"),
    ("head", "API models"),
    ("d1_ultra", "d1-ultra"),
    ("span_02", style.NAME["span_02"]),
    ("drex_v2", "drex-v2.0"),
)
OFFSET: Final = 0.16


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 2.25, [["a", "b"]], width_ratios=[1.75, 1.0])
    a, b = axd["a"], axd["b"]
    ys = style.row_axis(a, list(ROWS))
    style.row_axis(b, list(ROWS))
    b.tick_params(labelleft=False)
    pa, pb = df[df["panel"] == "a"], df[df["panel"] == "b"]
    for model, y in ys.items():
        c = style.color(model)
        on = pa[(pa["series"] == model) & (pa["role"] == "z_on")].iloc[0]
        idd = pa[(pa["series"] == model) & (pa["role"] == "z_id")].iloc[0]
        style.dots(a, [on["y"]], [y + OFFSET], [on["lo"]], [on["hi"]], color=c, horizontal=True)
        style.dots(
            a, [idd["y"]], [y - OFFSET], [idd["lo"]], [idd["hi"]], color=c, hollow=True, horizontal=True
        )
        h = pb[pb["series"] == model].iloc[0]
        style.dots(b, [h["y"]], [y], [h["lo"]], [h["hi"]], color=c, horizontal=True)
    for ax in (a, b):
        style.zero_line(ax, horizontal=False)
    a.set_xlabel(r"daily IC of $\hat N$ (test)")
    a.set_xlim(-0.065, 0.135)
    a.set_xticks([-0.05, 0.0, 0.05, 0.10])
    b.set_xlabel(r"$\mathrm{IC}(z_{on}) - \mathrm{IC}(z_{id})$")
    b.set_xlim(-0.06, 0.135)
    b.set_xticks([-0.05, 0.0, 0.05, 0.10])
    style.title(a, "a", "Overnight and after the open")
    style.title(b, "b", "H1")
    style.legend(
        fig,
        [style.key(style.INK_2), style.key(style.INK_2, hollow=True)],
        [r"overnight, $z_{on}$", r"after the open, $z_{id}$"],
        loc="outside upper center",
        ncols=2,
    )
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
