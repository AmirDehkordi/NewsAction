"""Figure 2: priced at the open (NA-12 t3, t1b).

    uv run python -m newsaction.figures.render fig2_priced_at_open

Three aligned panels with one row per model and the same IC scale: (a) the daily IC of N̂_W0 with the
overnight move z_on, (b) with the move after the open z_id, each with its 95% bootstrap interval, and (c) H1,
their difference, with its 95% bootstrap interval. The anchor is uninformative and appears in the appendix
tables.
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
PANELS: Final = (
    ("a", "z_on", "Overnight", r"IC with $z_{on}$"),
    ("b", "z_id", "After the open", r"IC with $z_{id}$"),
    ("c", "H1", "H1 = (a) $-$ (b)", r"$\mathrm{IC}(z_{on}) - \mathrm{IC}(z_{id})$"),
)


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 1.95, [["a", "b", "c"]], sharex=True)
    for letter, role, text, xlabel in PANELS:
        ax = axd[letter]
        ys = style.row_axis(ax, list(ROWS))
        for model, y in ys.items():
            r = df[(df["series"] == model) & (df["role"] == role)].iloc[0]
            style.dots(ax, [r["y"]], [y], [r["lo"]], [r["hi"]], color=style.color(model), horizontal=True)
        style.zero_line(ax, horizontal=False)
        style.title(ax, letter, text)
        ax.set_xlabel(xlabel)
        if letter != "a":
            ax.tick_params(labelleft=False)
    axd["a"].set_xlim(-0.065, 0.135)  # one IC scale for the three panels
    axd["a"].set_xticks([-0.05, 0.0, 0.05, 0.10])
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
