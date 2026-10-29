"""NA-14 S1: the one print style of every paper figure (CLAUDE.md F22; the dataviz skill; the operator's arXiv
format of the revision pass).

**Format.** The manuscript is a LaTeX article (11 pt, US letter, 1-inch margins, one column), so the text is
6.5 in wide. Figures are drawn at print size and placed at 100%: 6.5 in (full width) or 3.15 in (half
width), so a point in matplotlib is a point on paper.

**Type.** Computer Modern, as in a default LaTeX document: matplotlib's bundled ``cmr10`` with mathtext's
``cm`` set and math-formatted ticks (true minus signs). Text is 8 pt and nothing is below 7 pt. Bold marks
only the panel letters. cmr10 follows TeX's OT1 layout, so ``< > | _ ^ { } \\ ~`` and non-ASCII characters
print as the wrong glyph or none: every symbol and every piece of notation is written as math
(``$z_{cc}$``, ``$\\hat N$``, ``$\\kappa_h$``, ``tags-GBM$^{\\dagger}$``) and ``plain_text_ok`` refuses the
rest.

**Colour** (the dataviz skill's validated reference palette, light mode, on a white print surface). Colour
follows the entity in every figure: Laya-Fin, the primary instrument, is slot 1 (blue), d1-ultra, the API
comparator, slot 2 (orange), and the price-only benchmark (the gap fade) slot 3 (aqua); the validator passes
the three on all pairs against white (worst CVD ΔE 9.2, normal vision 24.0), and aqua's contrast (2.8:1)
is relieved by direct labels and the CSV beside every figure. Every other model, the placebo and the
reference lines are context in the greys; in Figure 7 the three production comparators (d1-ultra, span-02,
drex-v2.0) share the comparator colour, d1-ultra's slot. Classes of one model that are ordered
(news-strength terciles, the Under / Fair / Over classes) take that model's ordinal ramp: blue steps
250 / 450 / 650, and the orange slot's hue at the OKLCH lightness of the same three blue steps (both
validated with ``--ordinal``; as lines in one panel the orange steps pass the adjacent CVD and normal-vision
checks too, ΔE 16.6 and 19.2, where the earlier steps at blue 250, the slot and blue 550 failed the normal-
vision floor between Under and Fair, ΔE 7.7). Components (the steps of the explanation ladder in Figure 5,
the feature groups R, N, J in Figure A9) take the muted component palette: the reference hues of slots 7,
5 and 4 (violet, magenta, yellow) held, chroma muted to 0.11 and lightness stepped 0.46 / 0.64 / 0.76, so
the thin first steps of a stack are its darkest and the large last step its lightest; the validator
passes the three on all pairs against white (worst CVD ΔE 15.5, normal vision 18.5), and the sand step's
2.2:1 contrast is relieved by the value labels and the CSV. The anchor is uninformative and stays out of
the main figures.

**Marks.** Lines 1.2 pt, interval lines 0.7 pt, markers 4 pt with a white ring, bands at 15% opacity, light
horizontal gridlines only, no top or right spine. Text is ink, never the series colour; a label inside the
plot and a legend sit on a knockout of the surface, so a gridline stops at them, and no label touches a
line, a marker, a bar or a spine.

**Files.** Vector PDF (TrueType fonts embedded, no dates) and a 300-dpi PNG without a software stamp, so a
rebuild writes the same bytes.
"""

from __future__ import annotations

import logging
import re
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
from matplotlib.collections import LineCollection, PathCollection
from matplotlib.dates import DateFormatter, MonthLocator
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.text import Text

WIDTH_HALF: Final = 3.15
WIDTH_FULL: Final = 6.5
WIDTHS: Final = (WIDTH_HALF, WIDTH_FULL)
MIN_FONT_PT: Final = 7.0
DPI: Final = 300
Z95: Final = 1.959963984540054  # the two-sided 95% normal quantile

FONT: Final = "cmr10"
FONT_ITALIC: Final = "cmti10"
SIZE: Final = 8.0
SIZE_SMALL: Final = 7.0

# Surfaces and ink (the reference palette's chart chrome; white is the print surface).
SURFACE: Final = "#ffffff"
INK: Final = "#0b0b0b"
INK_2: Final = "#52514e"
MUTED: Final = "#898781"
GRID: Final = "#e1e0d9"
BASELINE: Final = "#c3c2b7"
CONTEXT: Final = "#a8a69f"  # context marks between the muted ink and the baseline grey
BAND_GREY: Final = "#d6d5ce"

# Categorical slots, fixed order (reference palette, light).
SLOTS: Final = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
BLUE: Final = {250: "#86b6ef", 450: "#2a78d6", 550: "#1c5cab", 650: "#104281"}
# The orange slot's hue and chroma at the OKLCH lightness of BLUE[250], BLUE[450] and BLUE[650] (chroma
# clipped to sRGB).
ORANGE: Final = {250: "#ff9067", 450: "#c94908", 650: "#752600"}
RAMP: Final = {
    "laya_fin": (BLUE[250], BLUE[450], BLUE[650]),
    "d1_ultra": (ORANGE[250], ORANGE[450], ORANGE[650]),
}
# The muted component palette, in its fixed order (violet, magenta, yellow hues at OKLCH C 0.11).
COMPONENT: Final = ("#514e93", "#c16e8d", "#daa75c")
COMPARATOR: Final = SLOTS[1]

LINE: Final = 1.2
LINE_THIN: Final = 0.7
LINE_HAIR: Final = 0.5
DOT: Final = 4.0
RING: Final = 0.6
BAND_ALPHA: Final = 0.15

# Entity → colour, the same in every figure; everything not named here is context.
COLOR: Final = {
    "laya_fin": SLOTS[0],
    "d1_ultra": SLOTS[1],
    "price_only": SLOTS[2],
    "gap_fade": SLOTS[2],
}
# Names as the paper writes them (math where a symbol is needed; † and ‡ stay on the names).
NAME: Final = {
    "laya_fin": "Laya-Fin",
    "anchor": "anchor",
    "laya_zs": "Laya zero-shot",
    "d1_ultra": "d1-ultra",
    "span_02": r"span-02$^{\ddagger}$",
    "drex_v2": "drex-v2.0",
    "price_only": "price-only",
    "embed_ridge": "bge-ridge",
    "llm": "LLM baseline",
    "sentiment": r"vendor sentiment$^{\dagger}$",
    "tags_gbm": r"tags-GBM$^{\dagger}$",
    "gap_fade": "gap fade",
}


def color(entity: str) -> str:
    """The entity's colour; any other model is context."""
    return COLOR.get(entity, CONTEXT)


def rc() -> dict[str, Any]:
    """matplotlib settings of the paper style."""
    return {
        "font.family": "serif",
        "font.serif": [FONT],
        "font.size": SIZE,
        "mathtext.fontset": "cm",
        "axes.formatter.use_mathtext": True,
        "axes.unicode_minus": True,
        "axes.titlesize": SIZE,
        "axes.titleweight": "normal",
        "axes.titlelocation": "left",
        "axes.titlepad": 3.0,
        "axes.titlecolor": INK,
        "axes.labelsize": SIZE,
        "axes.labelcolor": INK,
        "axes.labelpad": 2.5,
        "axes.edgecolor": INK_2,
        "axes.linewidth": 0.6,
        "axes.facecolor": SURFACE,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.4,
        "grid.linestyle": "-",
        "xtick.labelsize": SIZE,
        "ytick.labelsize": SIZE,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelcolor": INK,
        "ytick.labelcolor": INK,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.major.pad": 2.0,
        "ytick.major.pad": 2.0,
        "legend.fontsize": SIZE,
        "legend.frameon": False,
        "legend.handlelength": 1.4,
        "legend.handletextpad": 0.4,
        "legend.borderaxespad": 0.2,
        "legend.borderpad": 0.2,
        "legend.columnspacing": 1.2,
        "legend.labelspacing": 0.3,
        "lines.linewidth": LINE,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "lines.dash_capstyle": "butt",
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


def _check_width(width: float) -> None:
    if width not in WIDTHS:
        raise ValueError(f"a paper figure is {WIDTH_HALF} or {WIDTH_FULL} in wide, not {width}")


def new(
    width: float, height: float, nrows: int = 1, ncols: int = 1, **kw: Any
) -> tuple[Figure, npt.NDArray[Any]]:
    """A figure at print size with a grid of axes (always returned as a 2-D array)."""
    _check_width(width)
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), squeeze=False, layout="constrained", **kw)
    _pads(fig)
    return fig, axes


def mosaic(width: float, height: float, layout: list[list[str]], **kw: Any) -> tuple[Figure, dict[str, Axes]]:
    """A figure at print size with a named-panel layout (``Figure.subplot_mosaic``)."""
    _check_width(width)
    fig = plt.figure(figsize=(width, height), layout="constrained")
    axd = fig.subplot_mosaic(cast(Any, layout), **kw)
    _pads(fig)
    return fig, dict(axd)


def _pads(fig: Figure) -> None:
    engine = fig.get_layout_engine()
    if engine is not None:
        engine.set(w_pad=0.02, h_pad=0.02, wspace=0.05, hspace=0.06)  # type: ignore[call-arg]


def ci95(est: npt.ArrayLike, se: npt.ArrayLike) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """est ± 1.96·se (the normal 95% interval from a stored standard error)."""
    e, s = np.asarray(est, dtype=float), np.asarray(se, dtype=float)
    return e - Z95 * s, e + Z95 * s


def month_ticks(ax: Axes, months: Sequence[int], fmt: str) -> None:
    """Date ticks on the given months (matplotlib.dates is untyped)."""
    ax.xaxis.set_major_locator(MonthLocator(bymonth=tuple(months)))  # type: ignore[no-untyped-call]
    ax.xaxis.set_major_formatter(DateFormatter(fmt))  # type: ignore[no-untyped-call]


def title(ax: Axes, letter: str, text: str = "") -> None:
    """A short panel title; only the panel letter is bold."""
    head = rf"$\mathbf{{({letter})}}$" if letter else ""
    ax.set_title(f"{head} {text}".strip(), color=INK)


def band(ax: Axes, x: npt.ArrayLike, lo: npt.ArrayLike, hi: npt.ArrayLike, color: str, **kw: Any) -> None:
    kw.setdefault("alpha", BAND_ALPHA)
    kw.setdefault("zorder", 1)
    ax.fill_between(np.asarray(x), lo, hi, color=color, linewidth=0, **kw)  # x may be dates


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
    """Dots with a surface ring and, when given, their 95% interval as a thin line (x may be dates)."""
    xs = np.asarray(x) if horizontal is False else np.asarray(x, dtype=float)
    ys = np.asarray(y, dtype=float)
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
        markeredgewidth=0.9 if hollow else RING,
        color=color,
        label=label,
        zorder=zorder,
    )


def zero_line(ax: Axes, value: float = 0.0, *, horizontal: bool = True) -> None:
    if horizontal:
        ax.axhline(value, color=BASELINE, linewidth=0.7, zorder=1.5)
    else:
        ax.axvline(value, color=BASELINE, linewidth=0.7, zorder=1.5)


def ref_line(ax: Axes, value: float, *, horizontal: bool = True, color: str = INK_2, **kw: Any) -> None:
    """A dashed reference (a target, a baseline or a bar), thinner than the data."""
    kw.setdefault("linewidth", LINE_THIN)
    kw.setdefault("zorder", 1.6)
    kw.setdefault("dashes", (3.0, 2.0))
    if horizontal:
        ax.axhline(value, color=color, **kw)
    else:
        ax.axvline(value, color=color, **kw)


# A label's knockout: the surface behind its text, so a gridline stops at the label instead of crossing it
# (a label never sits on a data mark; the knockout only hides the hairline grid).
KNOCKOUT: Final = {"boxstyle": "square,pad=0.08", "facecolor": SURFACE, "edgecolor": "none"}


def label(ax: Axes, x: float, y: float, text: str, **kw: Any) -> Text:
    """A direct label in the text ink (never the series colour), data coordinates by default, on a
    knockout."""
    kw.setdefault("fontsize", SIZE)
    kw.setdefault("color", INK)
    kw.setdefault("va", "center")
    kw.setdefault("bbox", dict(KNOCKOUT))
    t = ax.text(x, y, text, **kw)
    t.set_in_layout(False)
    return t


def key(
    color: str, *, marker: str = "o", hollow: bool = False, line: bool = False, dashed: bool = False
) -> Line2D:
    """A legend handle: a dot (filled or hollow), a line, or a dashed line."""
    if line or dashed:
        return Line2D(
            [],
            [],
            color=color,
            linewidth=LINE_THIN if dashed else LINE,
            dashes=(3.0, 2.0) if dashed else (None, None),
        )
    return Line2D(
        [],
        [],
        color=color,
        marker=marker,
        linestyle="none",
        markersize=DOT,
        markerfacecolor=SURFACE if hollow else color,
        markeredgecolor=color if hollow else SURFACE,
        markeredgewidth=0.9 if hollow else RING,
    )


def legend(where: Axes | Figure, handles: Sequence[Any], labels: Sequence[str], **kw: Any) -> Legend:
    """A small legend outside the data (the caller places it), on a knockout without a visible frame."""
    kw.setdefault("frameon", True)
    kw.setdefault("fancybox", False)
    kw.setdefault("facecolor", SURFACE)
    kw.setdefault("edgecolor", SURFACE)
    kw.setdefault("framealpha", 1.0)
    kw.setdefault("fontsize", SIZE)
    kw.setdefault("handlelength", 1.4)
    leg = where.legend(list(handles), list(labels), **kw)
    leg.get_frame().set_linewidth(0.0)
    return leg


def rung_axis(ax: Axes, positions: Sequence[float], labels: Sequence[str]) -> None:
    """An event-time axis whose rungs are equally spaced, though the clock time between them is not."""
    ax.set_xticks(list(positions), list(labels))
    ax.set_xlabel("event time (not to scale)")
    ax.set_xlim(min(positions) - 0.35, max(positions) + 0.35)


def row_axis(ax: Axes, rows: Sequence[tuple[str, str]], *, gap: float = 1.0) -> dict[str, float]:
    """Rows of a dot plot from the top: ``(kind, text)`` with kind "head" (a group heading, italic, no marks)
    or a row id; returns the y position of each row id. Light horizontal guides run through the rows."""
    ys: dict[str, float] = {}
    ticks: list[float] = []
    texts: list[str] = []
    heads: list[bool] = []
    y = 0.0
    for kind, text in rows:
        if kind == "head" and ticks:
            y -= 0.3 * gap
        ticks.append(y)
        texts.append(text)
        heads.append(kind == "head")
        if kind != "head":
            ys[kind] = y
        y -= gap
    ax.set_yticks(ticks, texts)
    for t, is_head in zip(ax.get_yticklabels(), heads, strict=True):
        if is_head:
            t.set_fontfamily(FONT_ITALIC)
            t.set_color(INK_2)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(y + gap - 0.6 * gap, 0.6 * gap)
    ax.grid(False)
    for yy in ys.values():
        ax.axhline(yy, color=GRID, linewidth=0.4, zorder=0.5)
    return ys


# Plain text (outside $…$) that cmr10 prints as written; everything else goes in math.
_PLAIN: Final = re.compile(r"[A-Za-z0-9 \-.,()\[\]/%+=&;:?!'\n]*")
_MATH: Final = re.compile(r"\$[^$]*\$")


def plain_text_ok(s: str) -> bool:
    """True if the text outside math holds only characters cmr10 prints as written (no ``_``, no unicode)."""
    if s.count("$") % 2:
        return False
    return bool(_PLAIN.fullmatch(_MATH.sub("", s)))


def texts(fig: Figure) -> list[Text]:
    """Every visible, non-empty text of a figure."""
    out = []
    for t in fig.findobj(Text):
        if isinstance(t, Text) and t.get_visible() and t.get_text().strip():
            out.append(t)
    return out


def text_sizes(fig: Figure) -> list[float]:
    """The font size of every visible, non-empty text of a figure (the ≥ 7 pt check)."""
    return [float(t.get_fontsize()) for t in texts(fig)]


# --- no label on a mark -------------------------------------------------------------------------------------

TRIM: Final = 0.3  # px trimmed off each side of a text box (a glyph box is a little larger than its ink)
Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in display pixels


def _drawn(fig: Figure, t: Text) -> bool:
    """False for a tick label whose tick lies outside the view: matplotlib keeps it visible but never draws
    it."""
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if t is tick.label1 or t is tick.label2:
                    lo, hi = sorted(axis.get_view_interval())
                    return bool(tick.get_visible()) and lo - 1e-9 <= float(tick.get_loc()) <= hi + 1e-9
    return True


def _box(b: Any, grow: float = 0.0) -> Box:
    return (float(b.x0) - grow, float(b.y0) - grow, float(b.x1) + grow, float(b.y1) + grow)


def _meets(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _crosses(box: Box, xy: npt.NDArray[np.float64]) -> bool:
    """True if the polyline ``xy`` (display pixels) passes through ``box`` (Liang–Barsky clipping per
    segment)."""
    xy = xy[np.isfinite(xy).all(axis=1)]
    if len(xy) == 1:
        return bool(box[0] < xy[0, 0] < box[2] and box[1] < xy[0, 1] < box[3])
    if len(xy) < 2:
        return False
    x0, y0, x1, y1 = xy[:-1, 0], xy[:-1, 1], xy[1:, 0], xy[1:, 1]
    t0, t1 = np.zeros(len(x0)), np.ones(len(x0))
    ok = np.ones(len(x0), dtype=bool)
    for p, q in (
        (x0 - x1, x0 - box[0]),
        (x1 - x0, box[2] - x0),
        (y0 - y1, y0 - box[1]),
        (y1 - y0, box[3] - y0),
    ):
        flat = p == 0
        ok &= ~(flat & (q < 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(flat, 0.0, q / np.where(flat, 1.0, p))
        t0 = np.where(~flat & (p < 0), np.maximum(t0, r), t0)
        t1 = np.where(~flat & (p > 0), np.minimum(t1, r), t1)
    return bool((ok & (t0 <= t1)).any())


def _knocked_out(t: Text) -> bool:
    patch = t.get_bbox_patch()
    return patch is not None and mpl.colors.to_hex(patch.get_facecolor()) == SURFACE


def overlaps(fig: Figure) -> list[str]:
    """Every text or legend of a drawn figure that touches a line, a whisker, a marker, a bar, a spine or
    another text, and every one that crosses a gridline without a knockout (``KNOCKOUT``, a legend's surface
    frame). A line counts with its width; bands (``fill_between``) are not marks."""
    r = cast(Any, fig.canvas).get_renderer()
    legends = [leg for leg in fig.findobj(Legend) if isinstance(leg, Legend)]
    member: dict[int, Legend] = {id(a): leg for leg in legends for a in leg.findobj()}
    labels: list[tuple[str, Box, object, bool]] = []  # text, box, its axes (or None), knocked out
    for t in texts(fig):
        if id(t) in member or not _drawn(fig, t):
            continue
        labels.append((t.get_text(), _box(t.get_window_extent(r), -TRIM), t.axes, _knocked_out(t)))
    for leg in legends:
        frame = leg.get_frame()
        knocked = leg.get_frame_on() and mpl.colors.to_hex(frame.get_facecolor()) == SURFACE
        names = ", ".join(x.get_text() for x in leg.get_texts()[:2])
        labels.append((f"the legend ({names})", _box(leg.get_window_extent(r), -TRIM), None, knocked))
    px = fig.dpi / 72.0
    found: list[str] = []
    for ax in fig.axes:
        lines: list[tuple[str, npt.NDArray[np.float64], float]] = []  # what, polyline, half width (px)
        boxes: list[tuple[str, Box]] = []
        for ln in ax.get_lines():
            if id(ln) in member or not ln.get_visible() or ln.get_color() == GRID:  # GRID: a row guide
                continue
            xy = np.asarray(
                ln.get_transform().transform(np.asarray(ln.get_xydata(), dtype=float)), dtype=float
            )
            if ln.get_linestyle() not in ("None", "none", "", " "):
                lines.append((f"a line ({ln.get_color()})", xy, float(ln.get_linewidth()) * px / 2))
            if ln.get_marker() not in (None, "None", "none", "", " "):
                half = float(ln.get_markersize()) * px / 2
                boxes += [
                    ("a marker", (x - half, y - half, x + half, y + half)) for x, y in xy if np.isfinite(x)
                ]
        for col in ax.collections:
            if id(col) in member or not col.get_visible():
                continue
            if isinstance(col, LineCollection):
                half = float(np.max(np.atleast_1d(col.get_linewidth()))) * px / 2
                for seg in col.get_segments():
                    xy = np.asarray(col.get_transform().transform(np.asarray(seg, dtype=float)), dtype=float)
                    lines.append(("a whisker", xy, half))
            elif isinstance(col, PathCollection):
                offs = col.get_offset_transform().transform(col.get_offsets())
                sizes = np.broadcast_to(
                    np.sqrt(np.asarray(col.get_sizes(), dtype=float)) * px / 2, (len(offs),)
                )
                boxes += [
                    ("a marker", (x - s, y - s, x + s, y + s)) for (x, y), s in zip(offs, sizes, strict=True)
                ]
        for patch in ax.patches:
            if id(patch) not in member and patch.get_visible():
                boxes.append(("a bar", _box(patch.get_window_extent(r))))
        for side, spine in ax.spines.items():
            if spine.get_visible():
                boxes.append((f"the {side} spine", _box(spine.get_window_extent(r))))
        grid: list[npt.NDArray[np.float64]] = []
        for axis in (ax.xaxis, ax.yaxis):
            lo, hi = sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks():
                gl = tick.gridline
                if gl.get_visible() and lo <= float(tick.get_loc()) <= hi:
                    data = np.column_stack(
                        np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in gl.get_data()))
                    )
                    grid.append(np.asarray(gl.get_transform().transform(data), dtype=float))
        for text, box, owner, knocked in labels:
            if owner is not ax and not (owner is None and _meets(box, _box(ax.bbox))):
                continue
            hits = [
                w
                for w, xy, half in lines
                if _crosses((box[0] - half, box[1] - half, box[2] + half, box[3] + half), xy)
            ]
            hits += [w for w, b in boxes if _meets(box, b)]
            if not knocked and any(_crosses(box, xy) for xy in grid):
                hits.append("a gridline (no knockout)")
            found += [f"{text!r} touches {w}" for w in dict.fromkeys(hits)]
    for i, (a, ba, _, _) in enumerate(labels):
        for b, bb, _, _ in labels[i + 1 :]:
            if _meets(ba, bb):
                found.append(f"{a!r} touches {b!r}")
    return found


def save(fig: Figure, stem: Path) -> list[Path]:
    """``stem``.pdf and ``stem``.png, byte-reproducible (no dates or software stamps)."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    pdf, png = stem.with_suffix(".pdf"), stem.with_suffix(".png")
    quiet = logging.getLogger("fontTools")
    level = quiet.level
    quiet.setLevel(logging.ERROR)  # the bundled cm fonts carry zero timestamps, which fontTools reports
    try:
        fig.savefig(pdf, format="pdf", metadata={"CreationDate": None, "ModDate": None, "Creator": None})
        fig.savefig(png, format="png", dpi=DPI, metadata={"Software": None})
    finally:
        quiet.setLevel(level)
        plt.close(fig)
    return [pdf, png]


# Event-time rungs as the paper writes them (figure-data points and t6 rungs); +k is the close of t+k.
RUNG_LABEL: Final = {
    "car_pre1": r"$C_{t-1}$",
    "car_lvl_o0": r"$O_t$",
    "car_lvl_10": "10:00",
    "car_post0": r"$C_t$",
    "car_post1": r"$+1$",
    "car_post2": r"$+2$",
    "car_post5": r"$+5$",
    "car_post10": r"$+10$",
    "car_post20": r"$+20$",
    "O_t": r"$O_t$",
    "10:00": "10:00",
    "C_t": r"$C_t$",
    "C_t+1": r"$+1$",
    "C_t+2": r"$+2$",
    "C_t+5": r"$+5$",
    "C_t+10": r"$+10$",
    "C_t+20": r"$+20$",
}
