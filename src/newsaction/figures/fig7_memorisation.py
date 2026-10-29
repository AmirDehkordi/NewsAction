"""Figure 7: memorisation (NA-11; PREREG §8.3).

    uv run python -m newsaction.figures.render fig7_memorisation

Company identification on masked val-A states with activity-matched distractors: each model's share of
correct identifications as a horizontal bar, sorted, with its Wilson 95% interval (from the share and the
number of valid answers) and its value at the bar's end, against the matched baseline (a no-reading guess;
solid) and the §8.3 screening threshold (dashed), both labelled above the axis. The three production
comparators (d1-ultra, span-02, drex-v2.0) take the comparator colour; the other API models and Laya
zero-shot are context.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from newsaction.figures import render, style

NAME = "fig7_memorisation"
MODELS: Final = {
    "liquid/d1-ultra": "d1-ultra",
    "openai/gpt-6-luna-decisions": "gpt-6-luna",
    "nace-ai/drex-v2.0": "drex-v2.0",
    "respan/span-02": style.NAME["span_02"],
    "cloudflare/clef": "clef",
    "inception/mercury-decide": "mercury-decide",
    "local/laya-typed-decisions": "Laya zero-shot",
}
COMPARATORS: Final = ("liquid/d1-ultra", "respan/span-02", "nace-ai/drex-v2.0")
HEIGHT: Final = 0.58
PAD: Final = 0.012  # share between a whisker's end (or a reference line) and the value
VALUE_WIDTH: Final = 0.07  # the width of a value such as "74%" in shares of the axis


def _pct(v: float) -> str:
    return f"{100 * v:.0f}%"


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_HALF, 2.5)
    ax = axes[0][0]
    acc = df[df["role"] == "accuracy"].sort_values("y")  # the highest share on top
    ys = list(range(len(acc)))
    colours = [style.COMPARATOR if m in COMPARATORS else style.CONTEXT for m in acc["series"]]
    ax.barh(ys, acc["y"], height=HEIGHT, color=colours, linewidth=0, zorder=2)
    ax.hlines(ys, acc["lo"], acc["hi"], color=style.INK, linewidth=style.LINE_THIN, zorder=3)
    base = float(df.loc[df["role"] == "baseline", "y"].iloc[0])
    threshold = float(df.loc[df["role"] == "screen", "y"].iloc[0])
    ax.axvline(base, color=style.INK_2, linewidth=style.LINE_THIN, zorder=2.5)
    style.ref_line(ax, threshold, horizontal=False, color=style.INK, zorder=2.5)
    for y, (_, r) in zip(ys, acc.iterrows(), strict=True):
        x = float(r["hi"]) + PAD
        for line in (base, threshold):  # a value never sits on a reference line
            if x - PAD / 2 < line < x + VALUE_WIDTH:
                x = line + PAD
        style.label(ax, x, y, _pct(float(r["y"])), ha="left")
    for x, text, ha, dx in (
        (base, f"matched\nbaseline ({_pct(base)})", "right", -2.0),
        (threshold, f"screening\nthreshold ({_pct(threshold)})", "left", 2.0),
    ):
        ax.annotate(
            text,
            (x, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(dx, 2.0),
            textcoords="offset points",
            ha=ha,
            va="bottom",
            fontsize=style.SIZE_SMALL,
            color=style.INK_2,
            linespacing=1.1,
        )
    ax.set_yticks(ys, [MODELS[str(m)] for m in acc["series"]])
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.6, len(ys) - 0.4)
    ax.grid(False)
    ax.set_xlim(0.0, 0.9)
    ax.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{100 * v:.0f}%"))
    ax.set_xlabel("company identified (share of masked states)")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
