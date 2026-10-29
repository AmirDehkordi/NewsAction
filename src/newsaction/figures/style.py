"""NA-14 S1: the one print style of every paper figure (CLAUDE.md F22; PRD NA-14 S1, AC3).

The colours are the dataviz skill's validated reference palette (light mode; print needs no dark mode), on a
white print surface. Its validator (``validate_palette.py``, run in NA-14 and quoted in
``docs/decisions/NA-14.md``) passes for the first three slots on *all* pairs against ``#ffffff``. The aqua
slot sits below 3:1 against the surface, so an aqua series always carries a direct label, and every figure
ships its CSV as the table view.

- **Entities keep one colour in every figure.** Laya-Fin, the primary instrument, is slot 1 (blue), d1-ultra,
  the API comparator, is slot 2 (orange), and the price-only benchmark (gap fade) is slot 3 (aqua). The
  anchor is drawn in the muted ink and labelled "uninformative (near-constant outputs)". The vendor-label
  baselines are drawn in the secondary ink with a dagger: a possibly look-ahead-contaminated upper bound.
- **Polarity** (V deciles) uses the diverging blue ↔ red pair with a neutral gray middle. The blue arm is the
  reference blue ramp's steps 450 and 650. The red arm is the red slot's hue at those two steps' OKLCH
  lightness (L 0.575 and 0.385, chroma clipped to the sRGB gamut), validated as an ordinal ramp.
- **Type.** DejaVu Sans, which ships with matplotlib, so the glyphs and the files are the same on every
  machine. No text is smaller than ``MIN_FONT_PT`` at print size: the figures are drawn at their print
  widths (3.3 in for one column, 6.9 in for two), so a point in matplotlib is a point on paper.
- **Marks.** Lines 1.5 pt (the skill's 2 px), context lines thinner; dots of 6 pt (8 px) with a 1 pt
  surface ring; hairline solid gridlines; bands at 12% opacity; confidence intervals drawn, never implied.
- **Files.** Vector PDF (TrueType fonts embedded, no creation date) and a 300-dpi PNG without a software
  stamp, so a rebuild writes the same bytes.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final, cast

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.axes import Axes
from matplotlib.dates import DateFormatter, MonthLocator
from matplotlib.figure import Figure
from matplotlib.text import Text

WIDTH_SINGLE: Final = 3.3
WIDTH_DOUBLE: Final = 6.9
WIDTHS: Final = (WIDTH_SINGLE, WIDTH_DOUBLE)
MIN_FONT_PT: Final = 7.0
DPI: Final = 300
Z95: Final = 1.959963984540054  # the two-sided 95% normal quantile

FONT: Final = "DejaVu Sans"
SIZE_TICK: Final = 7.0
SIZE_LABEL: Final = 7.5
SIZE_TITLE: Final = 8.0
SIZE_NOTE: Final = 7.0

# Surfaces and ink (the reference palette's chart chrome; white is the print surface).
SURFACE: Final = "#ffffff"
INK: Final = "#0b0b0b"
INK_2: Final = "#52514e"
MUTED: Final = "#898781"
GRID: Final = "#e1e0d9"
BASELINE: Final = "#c3c2b7"

# Categorical slots, fixed order (reference palette, light).
SLOTS: Final = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
BLUE: Final = {250: "#86b6ef", 300: "#6da7ec", 450: "#2a78d6", 550: "#1c5cab", 650: "#104281"}
RED_450: Final = "#d2383a"  # the red slot's hue at the OKLCH lightness of BLUE[450]
RED_650: Final = "#830011"  # the red slot's hue at the OKLCH lightness of BLUE[650]

LINE: Final = 1.5
LINE_THIN: Final = 0.9
DOT: Final = 6.0
RING: Final = 1.0
BAND_ALPHA: Final = 0.12

ANCHOR_NOTE: Final = "uninformative (near-constant outputs)"
VENDOR_NOTE: Final = "possibly look-ahead-contaminated upper bound"

# Entity → colour, the same in every figure.
COLOR: Final = {
    "laya_fin": SLOTS[0],
    "d1_ultra": SLOTS[1],
    "api": SLOTS[1],
    "price_only": SLOTS[2],
    "gap_fade": SLOTS[2],
    "anchor": MUTED,
    "vendor": INK_2,
    "sentiment": INK_2,
    "tags_gbm": INK_2,
    "other": BASELINE,
}
LABEL: Final = {
    "laya_fin": "Laya-Fin",
    "d1_ultra": "d1-ultra",
    "span_02": "span-02",
    "drex_v2": "drex-v2.0",
    "laya_zs": "Laya zero-shot",
    "anchor": "anchor",
    "price_only": "price-only",
    "gap_fade": "gap fade (price-only)",
    "sentiment": "vendor sentiment",
    "tags_gbm": "tags-GBM",
    "embed_ridge": "bge-ridge",
    "llm": "LLM baseline",
}
DAGGER: Final = "†"
DDAGGER: Final = "‡"


def rc() -> dict[str, Any]:
    """matplotlib settings of the paper style."""
    return {
        "font.family": "sans-serif",
        "font.sans-serif": [FONT],
        "font.size": SIZE_LABEL,
        "mathtext.fontset": "dejavusans",
        "axes.titlesize": SIZE_TITLE,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 4.0,
        "axes.labelsize": SIZE_LABEL,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": BASELINE,
        "axes.linewidth": 0.6,
        "axes.facecolor": SURFACE,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "grid.linestyle": "-",
        "xtick.labelsize": SIZE_TICK,
        "ytick.labelsize": SIZE_TICK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "legend.fontsize": SIZE_NOTE,
        "legend.frameon": False,
        "legend.handlelength": 1.6,
        "legend.borderaxespad": 0.3,
        "lines.linewidth": LINE,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "lines.markersize": DOT,
        "figure.facecolor": SURFACE,
        "figure.dpi": 100,
        "savefig.facecolor": SURFACE,
        "savefig.dpi": DPI,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
        "text.color": INK,
    }


@contextmanager
def paper_style() -> Iterator[None]:
    with mpl.rc_context(cast(Any, rc())):
        yield


def new(
    width: float, height: float, nrows: int = 1, ncols: int = 1, **kw: Any
) -> tuple[Figure, npt.NDArray[Any]]:
    """A figure at print size with a grid of axes (always returned as a 2-D array)."""
    if width not in WIDTHS:
        raise ValueError(f"a paper figure is {WIDTH_SINGLE} or {WIDTH_DOUBLE} in wide, not {width}")
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), squeeze=False, layout="constrained", **kw)
    _pads(fig)
    return fig, axes


def mosaic(width: float, height: float, layout: list[list[str]], **kw: Any) -> tuple[Figure, dict[str, Axes]]:
    """A figure at print size with a named-panel layout (``Figure.subplot_mosaic``)."""
    if width not in WIDTHS:
        raise ValueError(f"a paper figure is {WIDTH_SINGLE} or {WIDTH_DOUBLE} in wide, not {width}")
    fig = plt.figure(figsize=(width, height), layout="constrained")
    axd = fig.subplot_mosaic(cast(Any, layout), **kw)
    _pads(fig)
    return fig, dict(axd)


def _pads(fig: Figure) -> None:
    engine = fig.get_layout_engine()
    if engine is not None:
        engine.set(w_pad=0.03, h_pad=0.03, wspace=0.04, hspace=0.06)  # type: ignore[call-arg]


def ci95(est: npt.ArrayLike, se: npt.ArrayLike) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """est ± 1.96·se (the normal 95% interval from a stored standard error)."""
    e, s = np.asarray(est, dtype=float), np.asarray(se, dtype=float)
    return e - Z95 * s, e + Z95 * s


def se_from_t(est: npt.ArrayLike, t: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """The standard error implied by an estimate and its t statistic (|est / t|)."""
    e, tt = np.asarray(est, dtype=float), np.asarray(t, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out: npt.NDArray[np.float64] = np.abs(e / tt)
    return out


def month_ticks(ax: Axes, months: Sequence[int], fmt: str) -> None:
    """Date ticks on the given months (matplotlib.dates is untyped)."""
    ax.xaxis.set_major_locator(MonthLocator(bymonth=tuple(months)))  # type: ignore[no-untyped-call]
    ax.xaxis.set_major_formatter(DateFormatter(fmt))  # type: ignore[no-untyped-call]


def band(ax: Axes, x: Sequence[float], lo: Sequence[float], hi: Sequence[float], color: str) -> None:
    ax.fill_between(x, lo, hi, color=color, alpha=BAND_ALPHA, linewidth=0, zorder=1)


def dots(
    ax: Axes,
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    lo: npt.ArrayLike | None = None,
    hi: npt.ArrayLike | None = None,
    *,
    color: str,
    label: str | None = None,
    hollow: bool = False,
    marker: str = "o",
    size: float = DOT,
    horizontal: bool = False,
    zorder: float = 3.0,
) -> None:
    """Dots with a surface ring and, when given, their 95% interval as a thin bar."""
    xs, ys = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if lo is not None and hi is not None:
        a, b = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
        if horizontal:
            ax.hlines(ys, a, b, color=color, linewidth=LINE_THIN, zorder=zorder - 0.5)
        else:
            ax.vlines(xs, a, b, color=color, linewidth=LINE_THIN, zorder=zorder - 0.5)
    ax.plot(
        xs,
        ys,
        linestyle="none",
        marker=marker,
        markersize=size,
        markerfacecolor=SURFACE if hollow else color,
        markeredgecolor=color if hollow else SURFACE,
        markeredgewidth=RING,
        color=color,
        label=label,
        zorder=zorder,
    )


def zero_line(ax: Axes, y: float = 0.0, *, horizontal: bool = True) -> None:
    if horizontal:
        ax.axhline(y, color=BASELINE, linewidth=0.8, zorder=1.5)
    else:
        ax.axvline(y, color=BASELINE, linewidth=0.8, zorder=1.5)


def title(ax: Axes, letter: str, text: str) -> None:
    ax.set_title(f"({letter}) {text}", color=INK)


def note(ax: Axes, x: float, y: float, text: str, **kw: Any) -> Text:
    """Annotation text in axes coordinates, in the secondary ink."""
    kw.setdefault("fontsize", SIZE_NOTE)
    kw.setdefault("color", INK_2)
    kw.setdefault("transform", ax.transAxes)
    return ax.text(x, y, text, **kw)


def end_label(ax: Axes, x: float, y: float, text: str, **kw: Any) -> Text:
    """A direct label at a series' end, in the text ink (never the series colour)."""
    kw.setdefault("fontsize", SIZE_NOTE)
    kw.setdefault("color", INK_2)
    kw.setdefault("va", "center")
    return ax.text(x, y, text, **kw)


def text_sizes(fig: Figure) -> list[float]:
    """The font size of every visible, non-empty text of a figure (AC3's ≥ 7 pt check)."""
    out = []
    for t in fig.findobj(Text):
        if isinstance(t, Text) and t.get_visible() and t.get_text().strip():
            out.append(float(t.get_fontsize()))
    return out


def save(fig: Figure, stem: Path) -> list[Path]:
    """``stem``.pdf and ``stem``.png, byte-reproducible (no dates or software stamps)."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    pdf, png = stem.with_suffix(".pdf"), stem.with_suffix(".png")
    fig.savefig(pdf, format="pdf", metadata={"CreationDate": None, "ModDate": None, "Creator": None})
    fig.savefig(png, format="png", dpi=DPI, metadata={"Software": None})
    plt.close(fig)
    return [pdf, png]
