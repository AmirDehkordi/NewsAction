"""Figure 4: monthly IC across validation and test, against the decision models' release dates (NA-12; t21).

    uv run python -m newsaction.figures.fig4_monthly_ic

The monthly mean of the daily IC of Call A's N̂_W0 with z_cc, from val-A through the test period, for Laya-Fin,
the API comparators and the anchor. Every release date lies after the sample: Laya's weights (the base of
Laya-Fin) and the API models were released after the test period ended, so a contamination cliff at a
release would fall outside the data. The gray region has no data.
"""

from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from newsaction.figures import render, style

NAME = "fig4_monthly_ic"
LINES = (
    ("anchor", style.COLOR["anchor"], style.LINE_THIN, f"anchor, {style.ANCHOR_NOTE}"),
    ("span_02", style.COLOR["api"], 0.7, "span-02‡, drex-v2.0 (thin)"),
    ("drex_v2", style.COLOR["api"], 0.7, ""),
    ("d1_ultra", style.COLOR["d1_ultra"], style.LINE, "d1-ultra (model-specific)"),
    ("laya_fin", style.COLOR["laya_fin"], style.LINE, "Laya-Fin (primary)"),
)
SPLITS = (("val_a", "val-A"), ("val_b", "val-B"), ("test", "test"))


def _mid(month: pd.Series) -> pd.Series:
    return pd.to_datetime(month + "-15")


def plot(df: pd.DataFrame) -> Figure:
    fig, axes = style.new(style.WIDTH_DOUBLE, 2.7)
    ax = axes[0][0]
    ic = df[df["role"] == "monthly_ic"]
    rel = df[df["role"] == "release"].set_index("series")
    end = pd.Timestamp(str(rel.loc["sample_end", "x"]))
    right = pd.Timestamp(str(rel["x"].max())) + pd.Timedelta(days=20)
    ax.axvspan(end + pd.Timedelta(days=1), right, color=style.GRID, alpha=0.7, linewidth=0, zorder=0)
    ax.text(
        end + pd.Timedelta(days=6),
        0.04,
        "after the sample: no data",
        transform=ax.get_xaxis_transform(),
        rotation=90,
        ha="left",
        va="bottom",
        fontsize=style.SIZE_NOTE,
        color=style.INK_2,
    )
    for split, label in SPLITS:
        months = _mid(ic.loc[ic["label"] == split, "x"])
        lo, hi = months.min() - pd.Timedelta(days=14), months.max() + pd.Timedelta(days=15)
        ax.axvline(lo, color=style.BASELINE, linewidth=0.6, zorder=1)
        ax.text(
            lo + (hi - lo) / 2,
            1.0,
            label,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=style.SIZE_NOTE,
            color=style.INK_2,
        )
    for model, color, lw, _ in LINES:
        m = ic[ic["series"] == model].sort_values("x")
        ax.plot(
            _mid(m["x"]),
            m["y"],
            color=color,
            linewidth=lw,
            marker="o",
            markersize=3.5 if lw > 1 else 0,
            markeredgecolor=style.SURFACE,
            markeredgewidth=0.6,
            zorder=3 if lw > 1 else 2,
        )
    style.zero_line(ax)
    for key, text in (
        ("laya", "Laya released"),
        ("drex_v2", ""),
        ("d1_ultra", ""),
        ("span_02", "API models released"),
    ):
        d = pd.Timestamp(str(rel.loc[key, "x"]))
        ax.axvline(d, color=style.INK_2, linewidth=0.7, zorder=2)
        if text:
            ax.text(
                d,
                0.93,
                text + " ",
                transform=ax.get_xaxis_transform(),
                rotation=90,
                ha="right",
                va="top",
                fontsize=style.SIZE_NOTE,
                color=style.INK_2,
            )
    ax.set_xlim(_mid(ic["x"]).min() - pd.Timedelta(days=20), right)
    style.month_ticks(ax, (1, 4, 7, 10), "%b %Y")
    ax.set_ylabel("monthly mean daily IC")
    handles = [Line2D([], [], color=c, linewidth=w, label=lab) for _, c, w, lab in LINES if lab][::-1]
    fig.legend(handles=handles, loc="outside upper center", ncols=2, handlelength=1.8, columnspacing=1.5)
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
