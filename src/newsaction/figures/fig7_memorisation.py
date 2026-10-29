"""Figure 7: memorisation (NA-11; PREREG §8.3).

    uv run python -m newsaction.figures.render fig7_memorisation

Company identification on masked val-A states with activity-matched distractors: each model's share of correct
identifications with its Wilson 95% interval (from the share and the number of valid answers), against the
matched baseline (a no-reading guess) and the §8.3 screen bar. d1-ultra is the API comparator; the other
models
are context.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from newsaction.figures import render, style

NAME = "fig7_memorisation"
MODELS: Final = {
    "liquid/d1-ultra": ("d1_ultra", "d1-ultra"),
    "openai/gpt-6-luna-decisions": ("", "gpt-6-luna"),
    "nace-ai/drex-v2.0": ("", "drex-v2.0"),
    "respan/span-02": ("", style.NAME["span_02"]),
    "cloudflare/clef": ("", "clef"),
    "inception/mercury-decide": ("", "mercury-decide"),
    "local/laya-typed-decisions": ("", "Laya zero-shot"),
}


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 2.45)
    ax = axes[0][0]
    acc = df[df["role"] == "accuracy"].set_index("series")
    api = [m for m in acc.sort_values("y", ascending=False).index if not str(m).startswith("local/")]
    rows: list[tuple[str, str]] = [("head", "API models")]
    rows += [(str(m), MODELS[str(m)][1]) for m in api]
    rows += [("head", "Local"), ("local/laya-typed-decisions", MODELS["local/laya-typed-decisions"][1])]
    ys = style.row_axis(ax, rows)
    base = float(df.loc[df["role"] == "baseline", "y"].iloc[0])
    bar = float(df.loc[df["role"] == "screen", "y"].iloc[0])
    style.ref_line(ax, base, horizontal=False, color=style.INK_2)
    style.ref_line(ax, bar, horizontal=False, color=style.INK, dashes=(1.2, 1.6))
    top = max(ys.values()) + 0.55
    style.label(
        ax,
        base,
        top,
        "matched\nbaseline",
        ha="right",
        va="bottom",
        color=style.INK_2,
        fontsize=style.SIZE_SMALL,
    )
    style.label(
        ax, bar, top, "screen\nbar", ha="left", va="bottom", color=style.INK, fontsize=style.SIZE_SMALL
    )
    for model, y in ys.items():
        r = acc.loc[model]
        entity = MODELS[model][0]
        style.dots(ax, [r["y"]], [y], [r["lo"]], [r["hi"]], color=style.color(entity), horizontal=True)
    ax.set_xlim(0.0, 0.85)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{100 * v:.0f}%"))
    ax.set_xlabel("company identified (share of masked states)")
    ax.set_ylim(min(ys.values()) - 0.7, top + 1.05)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
