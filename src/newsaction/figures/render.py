"""NA-14: draw one figure from its CSV (PRD NA-14 S2: "each reads ONLY its CSV"; AC3).

    uv run python -m newsaction.figures.render [fig1_convergence ...]

A figure module holds ``NAME`` and ``plot(df) -> Figure`` and reads no file. ``draw`` reads
``artifacts/NA-14/figures/<NAME>.csv``, the only input of the figure, draws it in the paper style, refuses
text below 7 pt or a width other than one or two columns, and writes the PDF and the PNG next to the CSV.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import pandas as pd
from matplotlib.figure import Figure

from newsaction.figures import style
from newsaction.figures.sources import FIGURES
from newsaction.paths import Layout, resolve_layout

MODULES: Final = {
    "fig1_convergence": "newsaction.figures.fig1_hero_car",
    "fig2_drift_vs_move": "newsaction.figures.fig2_drift_vs_move",
    "fig3_tournament": "newsaction.figures.fig3_tournament",
    "fig4_monthly_ic": "newsaction.figures.fig4_monthly_ic",
    "fig5_shapley": "newsaction.figures.fig5_shapley",
    "fig6_filters": "newsaction.figures.fig6_filters",
    "fig7_strategies": "newsaction.figures.fig7_strategies",
    "fig8_explain_move": "newsaction.figures.fig8_explain_move",
    "figA1_reliability": "newsaction.figures.appendix:reliability",
    "figA2_encoding": "newsaction.figures.appendix:encoding",
    "figA3_identifiability": "newsaction.figures.appendix:identifiability",
    "figA4_ablations": "newsaction.figures.appendix:ablations",
    "figA5_robustness": "newsaction.figures.appendix:robustness",
    "figA6_exploratory_d0": "newsaction.figures.appendix:exploratory_d0",
    "figA7_exploratory_ma_cross": "newsaction.figures.appendix:exploratory_ma_cross",
}


class FigureModule(Protocol):
    @property
    def NAME(self) -> str: ...  # noqa: N802 (a module constant)

    def plot(self, df: pd.DataFrame) -> Figure: ...


@dataclass(frozen=True)
class AppendixFigure:
    NAME: str
    draw: Callable[[pd.DataFrame], Figure]

    def plot(self, df: pd.DataFrame) -> Figure:
        return self.draw(df)


def module(name: str) -> FigureModule:
    """The module of a main figure, or an appendix figure ("module:function", the function's ``NAMES``
    entry)."""
    path, _, func = MODULES[name].partition(":")
    mod = importlib.import_module(path)
    if func:
        if mod.NAMES[func] != name:
            raise ValueError(f"{MODULES[name]} draws {mod.NAMES[func]!r}, not {name!r}")
        return AppendixFigure(name, getattr(mod, func))
    fig: FigureModule = mod
    if name != fig.NAME:
        raise ValueError(f"{MODULES[name]} draws {fig.NAME!r}, not {name!r}")
    return fig


def read(name: str, layout: Layout | None = None) -> pd.DataFrame:
    """A figure's CSV, with its text columns as text (empty cells stay empty strings)."""
    path = resolve_layout(layout).root / FIGURES / f"{name}.csv"
    df = pd.read_csv(
        path,
        dtype={"series": str, "label": str, "role": str, "x": str, "ci": str},
        keep_default_na=False,
        na_values=[""],
    )
    for c in ("series", "label", "role", "x", "ci"):
        df[c] = df[c].fillna("")
    return df


def check(fig: Figure, name: str) -> None:
    w = round(float(fig.get_size_inches()[0]), 3)
    if w not in style.WIDTHS:
        raise ValueError(f"{name}: width {w} in is neither one nor two columns")
    sizes = style.text_sizes(fig)
    if sizes and min(sizes) < style.MIN_FONT_PT:
        raise ValueError(f"{name}: text at {min(sizes)} pt is below {style.MIN_FONT_PT} pt")


def draw(name: str, layout: Layout | None = None) -> list[Path]:
    df = read(name, layout)
    with style.paper_style():
        fig = module(name).plot(df)
        fig.canvas.draw()
        check(fig, name)
        return style.save(fig, resolve_layout(layout).root / FIGURES / name)


def main(argv: Sequence[str] | None = None) -> int:
    for name in list(argv) if argv else list(MODULES):
        for p in draw(name):
            print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
