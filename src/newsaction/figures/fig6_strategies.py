"""Figure 6: strategies (PREREG §12, A1.6; NA-13 strategy table and Figure 7 data; t33).

    uv run python -m newsaction.figures.render fig6_strategies

(a, b) The annualized Sharpe ratio of each main book of Laya-Fin and d1-ultra on test, gross and net of 10 bp
per side, at the exit of its hypothesis' horizon, with the gap fade beside S-CONV; the gray box behind a
book's
rows is the 5th–95th percentile of its 100 random-signal books (t33; one universe per book). (c) S-CONV's
cumulative net return at 10 bp against the gap fade, with the placebo's 5th–95th percentile band.
"""

from __future__ import annotations

from typing import Any, Final

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator

from newsaction.figures import render, style

NAME = "fig6_strategies"
BOOKS: Final = {
    "S-CONV": r"S-CONV, D2 to $t{+}5$",
    "S-D0": "S-D0, open to close",
    "S-D1": r"S-D1 $J$, 10:00 to close",
    "S-D2": r"S-D2 $J$, next open to $t{+}5$",
}
LINES: Final = ("gap_fade", "d1_ultra", "laya_fin")


def _rows(d: pd.DataFrame) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for book, head in BOOKS.items():
        rows.append(("head", head))
        for series in dict.fromkeys(d.loc[d["label"] == book, "series"]):
            rows.append((f"{book}|{series}", style.NAME[str(series)]))
    return rows


def sharpe(ax: Axes, d: pd.DataFrame, rows: list[tuple[str, str]]) -> None:
    ys = style.row_axis(ax, rows)
    for book in BOOKS:
        mine = [y for k, y in ys.items() if k.startswith(f"{book}|")]
        p = d[(d["label"] == book) & (d["role"] == "placebo")].iloc[0]
        lo, hi = float(p["lo"]), float(p["hi"])
        ax.add_patch(
            Rectangle(
                (lo, min(mine) - 0.42),
                hi - lo,
                max(mine) - min(mine) + 0.84,
                facecolor=style.BAND_GREY,
                edgecolor="none",
                alpha=0.7,
                zorder=0.6,
            )
        )
    for key, y in ys.items():
        book, series = key.split("|")
        r = d[(d["label"] == book) & (d["series"] == series) & (d["role"] == "book")].iloc[0]
        style.dots(ax, [r["y"]], [y], color=style.color(series), size=style.DOT + 0.5)
    style.zero_line(ax, horizontal=False)


def plot(df: pd.DataFrame) -> Figure:
    fig, axd = style.mosaic(style.WIDTH_FULL, 2.75, [["a", "b", "c"]], width_ratios=[1.0, 0.9, 1.35])
    a, b, c = axd["a"], axd["b"], axd["c"]
    pa, pb = df[df["panel"] == "a"], df[df["panel"] == "b"]
    rows = _rows(pa)
    sharpe(a, pa, rows)
    sharpe(b, pb, rows)
    b.tick_params(labelleft=False)
    a.set_xlim(-4.2, 4.2)
    a.set_xticks([-4, -2, 0, 2, 4])
    b.set_xlim(-14.0, 3.0)
    b.set_xticks([-12, -8, -4, 0])
    a.set_xlabel("Sharpe ratio, gross")
    b.set_xlabel("Sharpe ratio, net of 10 bp")
    style.title(a, "a", "Gross")
    style.title(b, "b", "Net of costs")

    pc = df[df["panel"] == "c"].copy()
    pc["date"] = pd.to_datetime(pc["x"])
    band = pc[pc["role"] == "placebo_band"].sort_values("date")
    c.fill_between(
        band["date"],
        100 * band["lo"],
        100 * band["hi"],
        color=style.BAND_GREY,
        alpha=0.7,
        linewidth=0,
        zorder=1,
    )
    handles: list[Any] = []
    labels: list[str] = []
    for series in LINES:
        m = pc[(pc["series"] == series) & (pc["role"] == "book")].sort_values("date")
        col = style.color(series)
        c.plot(m["date"], 100 * m["y"], color=col, linewidth=style.LINE, zorder=3)
        handles.append(style.key(col, line=True))
        labels.append(style.NAME[series] if series != "gap_fade" else "gap fade (price-only)")
    handles.append(Rectangle((0, 0), 1, 1, facecolor=style.BAND_GREY, alpha=0.7, edgecolor="none"))
    labels.append("placebo, 5th to 95th pct.")
    order = [2, 1, 0, 3]
    style.legend(
        c, [handles[i] for i in order], [labels[i] for i in order], loc="lower left", borderaxespad=0.3
    )
    style.zero_line(c)
    start = band["date"].min().to_period("M").start_time
    c.set_xlim(start, band["date"].max() + pd.Timedelta(days=3))
    style.month_ticks(c, (1, 3, 5, 7), "%b")
    c.yaxis.set_major_locator(MultipleLocator(5))
    c.set_ylabel("cumulative net return, 10 bp (%)")
    c.set_xlabel(f"test period, {start.year}")
    style.title(c, "c", "S-CONV and the gap fade")
    return fig


def main() -> int:
    for p in render.draw(NAME):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
