"""Figure 1: validation against test (NA-12 t14).

    uv run python -m newsaction.figures.render fig1_validation_test

Two aligned panels, (a) val-B and (b) the test period, with one row per instrument and the same IC scale: each
dot is the daily IC of N̂_W0 with z_cc, with its 95% interval from the Newey–West t, on its model's row. Rows
are grouped (trained, zero-shot, API models, baselines); the vendor-label baselines carry †. The anchor is
uninformative and appears in the appendix.
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
PANELS: Final = (
    ("a", "val_b", "val-B: October to December 2025"),
    ("b", "test", "Test: January to July 2026"),
)


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 2.85, [["a", "b"]], sharex=True)
    d = df.sort_values("xv", kind="stable")
    rows: list[tuple[str, str]] = []
    for group, head in GROUPS:
        rows.append(("head", head))
        rows += [(m, style.NAME[m]) for m in dict.fromkeys(d.loc[d["label"] == group, "series"])]
    for letter, role, text in PANELS:
        ax = axd[letter]
        ys = style.row_axis(ax, rows)
        for model, y in ys.items():
            r = d[(d["series"] == model) & (d["role"] == role)].iloc[0]
            style.dots(ax, [r["y"]], [y], [r["lo"]], [r["hi"]], color=style.color(model), horizontal=True)
        style.zero_line(ax, horizontal=False)
        style.title(ax, letter, text)
        ax.set_xlabel(r"daily IC of $\hat N$ with $z_{cc}$")
    axd["b"].tick_params(labelleft=False)
    axd["a"].set_xlim(-0.07, 0.155)
    axd["a"].set_xticks([-0.05, 0.0, 0.05, 0.10, 0.15])
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
