"""Figure 7: no pre-registered book survives costs (PREREG §12, A1.6; NA-13).

    uv run python -m newsaction.figures.fig7_strategies

Cumulative net returns at 10 bp per side on the test period. (a) S-CONV, the primary strategy, against the
price-only gap fade it nearly equals, d1-ultra's and the anchor's S-CONV; (b–d) S-D0, S-D1 and S-D2 with
their benchmarks. The gray band is the 5th–95th percentile path of 100 random-signal books on Laya-Fin's
events. (e–g) Laya-Fin's S-CONV book and the gap fade by tier (descriptive sub-books, no placebo).
"""

from __future__ import annotations

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator, PercentFormatter

from newsaction.figures import render, style

NAME = "fig7_strategies"
PANELS = (
    ("a", "S-CONV, exit t+5"),
    ("b", "S-D0, exit close"),
    ("c", "S-D1 J, exit close"),
    ("d", "S-D2 J, exit t+5"),
)
TIERS = (("e", "S-CONV by tier: Top-100"), ("f", "101–250"), ("g", "251–500"))
SERIES = {
    "laya_fin": (style.COLOR["laya_fin"], style.LINE, "Laya-Fin"),
    "laya_fin_gated": (style.BLUE[300], style.LINE_THIN, "Laya-Fin, confidence-gated"),
    "d1_ultra": (style.COLOR["d1_ultra"], style.LINE_THIN, "d1-ultra (model-specific)"),
    "anchor": (style.COLOR["anchor"], style.LINE_THIN, f"anchor, {style.ANCHOR_NOTE}"),
    "gap_fade": (style.COLOR["gap_fade"], style.LINE, "gap fade (price-only benchmark)"),
    "sentiment": (
        style.COLOR["sentiment"],
        style.LINE_THIN,
        f"vendor sentiment{style.DAGGER}, {style.VENDOR_NOTE}",
    ),
}
ORDER = ("anchor", "sentiment", "d1_ultra", "laya_fin_gated", "gap_fade", "laya_fin")


def _dates(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["x"])


def _panel(ax: Axes, sub: pd.DataFrame) -> None:
    band = sub[sub["role"] == "placebo_band"]
    if len(band):
        ax.fill_between(
            _dates(band),
            band["lo"],
            band["hi"],
            color=style.MUTED,
            alpha=style.BAND_ALPHA,
            linewidth=0,
            zorder=1,
        )
    for s in ORDER:
        m = sub[(sub["series"] == s) & (sub["role"] != "placebo_band")]
        if m.empty:
            continue
        color, lw, _ = SERIES[s]
        ax.plot(_dates(m), m["y"], color=color, linewidth=lw, zorder=3 if s == "laya_fin" else 2)
    style.zero_line(ax)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    style.month_ticks(ax, (2, 4, 6), "%b")


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(
        style.WIDTH_DOUBLE,
        4.9,
        [
            ["a", "a", "a", "b", "b", "b", "c", "c", "c", "d", "d", "d"],
            ["e", "e", "e", "e", "f", "f", "f", "f", "g", "g", "g", "g"],
        ],
    )
    for letter, title in PANELS:
        _panel(axd[letter], df[df["panel"] == letter])
        style.title(axd[letter], letter, title)
    tier_axes = [axd[letter] for letter, _ in TIERS]
    for letter, title in TIERS:
        _panel(axd[letter], df[df["panel"] == letter])
        style.title(axd[letter], letter, title)
    lo = min(ax.get_ylim()[0] for ax in tier_axes)
    hi = max(ax.get_ylim()[1] for ax in tier_axes)
    for ax in tier_axes:
        ax.set_ylim(lo, hi)
    axd["a"].set_ylabel("cumulative net return, 10 bp")
    axd["e"].set_ylabel("cumulative net return, 10 bp")
    handles: list[Line2D | Patch] = [
        Line2D([], [], color=SERIES[s][0], linewidth=SERIES[s][1], label=SERIES[s][2])
        for s in ("laya_fin", "laya_fin_gated", "d1_ultra", "gap_fade", "anchor", "sentiment")
    ]
    handles.append(
        Patch(
            color=style.MUTED,
            alpha=style.BAND_ALPHA * 2,
            linewidth=0,
            label="placebo: 5th–95th percentile, 100 random books (a–d)",
        )
    )
    fig.legend(handles=handles, loc="outside upper center", ncols=2, handlelength=1.8, columnspacing=1.5)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
