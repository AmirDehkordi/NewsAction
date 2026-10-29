"""NA-14 S1, S2 and AC3: print style, fonts, palette and one input per figure (``figures.style``, ``render``).

- each figure is drawn at the arXiv text width (6.5 in) or half of it (3.15 in), with no text below 7 pt, in
  Computer Modern, and with no text that cmr10 cannot print as written (a raw underscore, a unicode symbol);
- the palette is the dataviz skill's reference instance (light), entities keep one colour, and the ordinal
  ramps are the validated blue steps and the orange slot's hue at the same three lightnesses; the muted
  component palette holds the hues of slots 7, 5 and 4 at the documented chroma and lightness steps;
- no label touches a line, a marker, a bar, a spine, another label or an uncovered gridline, in any figure,
  and the check catches a planted one;
- the restored layouts (the polish pass): Figure 5's stacked bars beside the news-steps zoom, Figure 7's
  sorted bars with the labelled baseline and screening threshold, A9's six panels; panels of one quantity on
  one scale share their axis;
- a figure module reads no file, and drawing a figure reads only its CSV;
- drawing from the committed CSV writes the committed PDF and PNG byte for byte.
"""

from __future__ import annotations

import ast
import builtins
import math
import shutil
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from newsaction.figures import render, style
from newsaction.figures.sources import FIGURES
from newsaction.paths import ROOT, Layout

PKG = ROOT / "src" / "newsaction" / "figures"
REFERENCE = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
READERS = {
    "read_csv",
    "read_parquet",
    "read_json",
    "read_text",
    "read_bytes",
    "open",
    "load",
    "loadtxt",
    "imread",
}


@pytest.mark.parametrize("name", list(render.MODULES))
def test_print_width_font_and_text(name: str) -> None:
    with style.paper_style():
        assert mpl.rcParams["font.serif"][0] == "cmr10" and mpl.rcParams["mathtext.fontset"] == "cm"
        assert mpl.rcParams["axes.formatter.use_mathtext"]
        fig = render.module(name).plot(render.read(name))
        fig.canvas.draw()
        try:
            assert round(float(fig.get_size_inches()[0]), 3) in (3.15, 6.5)
            sizes = style.text_sizes(fig)
            assert sizes and min(sizes) >= style.MIN_FONT_PT
            texts = [t.get_text() for t in style.texts(fig)]
            assert all(style.plain_text_ok(t) for t in texts), [
                t for t in texts if not style.plain_text_ok(t)
            ]
            families = {t.get_fontfamily()[0] for t in style.texts(fig)}
            assert families <= {"serif", "cmr10", "cmti10"}, families
            assert style.overlaps(fig) == []
        finally:
            plt.close(fig)


def test_plain_text_rule() -> None:
    assert style.plain_text_ok(r"daily IC of $\hat N$ with $z_{cc}$ (val-B, 95%)")
    assert style.plain_text_ok(r"tags-GBM$^{\dagger}$")
    for bad in ("z_cc", "a < b", "−0.5", "tags-GBM†", "|G|", "odd $math"):
        assert not style.plain_text_ok(bad), bad


def test_palette_is_the_reference_instance() -> None:
    assert style.SLOTS == REFERENCE
    assert style.color("laya_fin") == REFERENCE[0] and style.color("d1_ultra") == REFERENCE[1]
    assert style.color("gap_fade") == style.color("price_only") == REFERENCE[2]
    for context in ("anchor", "span_02", "drex_v2", "laya_zs", "sentiment", "tags_gbm"):
        assert style.color(context) == style.CONTEXT
    assert style.RAMP["laya_fin"] == ("#86b6ef", "#2a78d6", "#104281")
    assert style.RAMP["d1_ultra"] == ("#ff9067", "#c94908", "#752600")
    assert style.COMPONENT == ("#514e93", "#c16e8d", "#daa75c")
    assert style.color("d1_ultra") == style.COMPARATOR
    assert style.FONT == "cmr10" and style.MIN_FONT_PT == 7.0 and style.WIDTHS == (3.15, 6.5)


def _oklch(hex_: str) -> tuple[float, float, float]:
    """OKLCH of an sRGB colour (Ottosson's OKLab)."""
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    lab = (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )
    return lab[0], math.hypot(lab[1], lab[2]), math.degrees(math.atan2(lab[2], lab[1])) % 360


def test_derived_steps_follow_the_method() -> None:
    """The muted components hold slots 7, 5, 4's hues at C 0.11 and L 0.46 / 0.64 / 0.76; the orange steps
    hold the orange slot's hue at the lightness of blue 250 / 450 / 650."""
    for c, slot, lightness in zip(style.COMPONENT, (6, 4, 3), (0.46, 0.64, 0.76), strict=True):
        ell, chroma, hue = _oklch(c)
        assert abs(ell - lightness) < 0.006 and abs(chroma - 0.11) < 0.006, c
        assert abs(hue - _oklch(REFERENCE[slot])[2]) < 1.5, c
    for c, blue in zip(style.RAMP["d1_ultra"], (250, 450, 650), strict=True):
        assert abs(_oklch(c)[0] - _oklch(style.BLUE[blue])[0]) < 0.005, c
        assert abs(_oklch(c)[2] - _oklch(REFERENCE[1])[2]) < 1.0, c


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            out.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return out


def test_figure_modules_read_no_file() -> None:
    mods = sorted({m.split(":")[0].rsplit(".", 1)[1] for m in render.MODULES.values()})
    for m in mods:
        assert _calls(PKG / f"{m}.py") & READERS == set(), m


@pytest.mark.parametrize("name", ["fig3_convergence", "fig6_strategies", "figA14_exploratory_d0"])
def test_drawing_reads_only_its_csv(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real_csv, real_open = pd.read_csv, builtins.open

    def read_csv(path: Any, *a: Any, **k: Any) -> pd.DataFrame:
        seen.append(str(path))
        return real_csv(path, *a, **k)

    def opener(path: Any, *a: Any, **k: Any) -> Any:
        if str(path).startswith(str(ROOT)):
            seen.append(str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr(pd, "read_csv", read_csv)
    monkeypatch.setattr(builtins, "open", opener)
    with style.paper_style():
        fig = render.module(name).plot(render.read(name))
        plt.close(fig)
    assert {Path(p).resolve() for p in seen} == {(ROOT / FIGURES / f"{name}.csv").resolve()}


@pytest.mark.parametrize("name", ["fig1_validation_test", "figA2_filters"])
def test_drawing_writes_the_committed_bytes(name: str, tmp_path: Path) -> None:
    (tmp_path / FIGURES).mkdir(parents=True)
    shutil.copyfile(ROOT / FIGURES / f"{name}.csv", tmp_path / FIGURES / f"{name}.csv")
    for path in render.draw(name, Layout(tmp_path)):
        assert path.read_bytes() == (ROOT / FIGURES / path.name).read_bytes(), path.name


def test_check_refuses_small_text_odd_widths_and_unprintable_text() -> None:
    with style.paper_style():
        fig, axes = style.new(style.WIDTH_HALF, 2.0)
        axes[0][0].text(0.5, 0.5, "tiny", fontsize=6)
        with pytest.raises(ValueError, match="below"):
            render.check(fig, "toy")
        plt.close(fig)
        fig, axes = style.new(style.WIDTH_HALF, 2.0)
        axes[0][0].set_xlabel("ic_z_cc")
        with pytest.raises(ValueError, match="cannot print"):
            render.check(fig, "toy")
        plt.close(fig)
        fig, axes = style.new(style.WIDTH_HALF, 2.0)
        axes[0][0].plot([0, 1], [0.5, 0.5], color=style.INK)
        axes[0][0].text(0.5, 0.5, "a label on the line", fontsize=8)
        with pytest.raises(ValueError, match="overlaps a mark"):
            render.check(fig, "toy")
        plt.close(fig)
    with pytest.raises(ValueError):
        style.new(6.9, 2.0)


def _drawn(name: str) -> Any:
    with style.paper_style():
        fig = render.module(name).plot(render.read(name))
        fig.canvas.draw()
    return fig


def _shared(fig: Any, axis: str, *pairs: tuple[int, int]) -> list[bool]:
    group = fig.axes[0].get_shared_y_axes() if axis == "y" else fig.axes[0].get_shared_x_axes()
    return [group.joined(fig.axes[i], fig.axes[j]) for i, j in pairs]


def test_restored_layouts_and_shared_axes() -> None:
    fig = _drawn("fig5_explaining_moves")
    a, b = fig.axes[:2]
    bars = [p for p in a.patches if p.get_height() > 0]
    assert len(bars) == 15  # five cuts, three steps
    colours = [mpl.colors.to_hex(p.get_facecolor()) for p in bars]
    assert colours == [c for c in style.COMPONENT for _ in range(5)]  # stacked in the legend's order
    legend = [t.get_text() for t in fig.legends[0].get_texts()]
    assert (
        legend[0].startswith("ex-ante") and legend[1].startswith("+ same-day") and "explanation" in legend[2]
    )
    assert a.get_ylim()[1] > 40 and b.get_ylim()[1] < 2  # (b) is the zoom
    plt.close(fig)
    fig = _drawn("fig7_memorisation")
    ax = fig.axes[0]
    widths = [p.get_width() for p in ax.patches]
    assert len(widths) == 7 and widths == sorted(widths)  # the largest share on top
    texts = [t.get_text() for t in ax.texts]
    assert "matched\nbaseline (28%)" in texts and "screening\nthreshold (40%)" in texts
    assert not any("screen bar" in t for t in texts)
    plt.close(fig)
    fig = _drawn("figA9_shapley")
    assert len(fig.axes) == 6
    assert all(_shared(fig, "y", (0, 1), (1, 2), (3, 4), (4, 5))) and not any(_shared(fig, "y", (0, 3)))
    assert all(_shared(fig, "x", (0, 3), (1, 4), (2, 5)))
    plt.close(fig)
    fig = _drawn("figA12_strategy_paths")
    assert all(_shared(fig, "y", (0, 1), (3, 4), (3, 5))) and not any(_shared(fig, "y", (0, 2), (2, 5)))
    plt.close(fig)
    for name, axis, pairs in (
        ("figA7_convergence_detail", "y", ((0, 1),)),
        ("figA13_probes", "x", ((0, 1),)),
        ("figA5_robustness", "x", ((0, 3),)),
    ):
        fig = _drawn(name)
        assert all(_shared(fig, axis, *pairs)), name
        plt.close(fig)
    fig = _drawn("fig2_priced_at_open")
    assert fig.axes[0].get_xlim() == fig.axes[1].get_xlim()
    plt.close(fig)
