"""NA-14 S1, S2 and AC3: print style, fonts, palette and one input per figure (``figures.style``, ``render``).

- each figure is drawn at the arXiv text width (6.5 in) or half of it (3.15 in), with no text below 7 pt, in
  Computer Modern, and with no text that cmr10 cannot print as written (a raw underscore, a unicode symbol);
- the palette is the dataviz skill's reference instance (light), entities keep one colour, and the ordinal
  ramps are the validated blue steps and the orange slot's hue at blue's lightness;
- a figure module reads no file, and drawing a figure reads only its CSV;
- drawing from the committed CSV writes the committed PDF and PNG byte for byte.
"""

from __future__ import annotations

import ast
import builtins
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
    assert style.RAMP["d1_ultra"] == ("#ff8653", REFERENCE[1], "#a82800")
    assert style.FONT == "cmr10" and style.MIN_FONT_PT == 7.0 and style.WIDTHS == (3.15, 6.5)


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
    with pytest.raises(ValueError):
        style.new(6.9, 2.0)
