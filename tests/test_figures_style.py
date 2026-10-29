"""NA-14 S1, S2 and AC3: print style, fonts, palette and one input per figure (``figures.style``, ``render``).

- each figure is drawn at one or two column widths with no text below 7 pt;
- the palette is the dataviz skill's reference instance (light), entities keep one colour, and the computed
  red
  arm matches the blue arm's lightness;
- a figure module reads no file, and drawing a figure reads only its CSV;
- drawing from the committed CSV writes the committed PDF and PNG byte for byte.
"""

from __future__ import annotations

import ast
import builtins
import shutil
from pathlib import Path
from typing import Any

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
def test_print_width_and_minimum_font(name: str) -> None:
    with style.paper_style():
        fig = render.module(name).plot(render.read(name))
        fig.canvas.draw()
        try:
            assert round(float(fig.get_size_inches()[0]), 3) in style.WIDTHS
            sizes = style.text_sizes(fig)
            assert sizes and min(sizes) >= style.MIN_FONT_PT
        finally:
            plt.close(fig)


def test_palette_is_the_reference_instance() -> None:
    assert style.SLOTS == REFERENCE
    assert style.COLOR["laya_fin"] == REFERENCE[0] and style.COLOR["d1_ultra"] == REFERENCE[1]
    assert style.COLOR["gap_fade"] == style.COLOR["price_only"] == REFERENCE[2]
    assert style.COLOR["anchor"] == style.MUTED
    assert style.FONT == "DejaVu Sans" and style.MIN_FONT_PT == 7.0


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


@pytest.mark.parametrize("name", ["fig1_convergence", "fig7_strategies", "figA6_exploratory_d0"])
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


@pytest.mark.parametrize("name", ["fig6_filters", "figA4_ablations"])
def test_drawing_writes_the_committed_bytes(name: str, tmp_path: Path) -> None:
    (tmp_path / FIGURES).mkdir(parents=True)
    shutil.copyfile(ROOT / FIGURES / f"{name}.csv", tmp_path / FIGURES / f"{name}.csv")
    for path in render.draw(name, Layout(tmp_path)):
        assert path.read_bytes() == (ROOT / FIGURES / path.name).read_bytes(), path.name


def test_check_refuses_small_text_and_odd_widths() -> None:
    with style.paper_style():
        fig, axes = style.new(style.WIDTH_SINGLE, 2.0)
        axes[0][0].text(0.5, 0.5, "tiny", fontsize=6)
        with pytest.raises(ValueError, match="below"):
            render.check(fig, "toy")
        plt.close(fig)
    with pytest.raises(ValueError):
        style.new(5.0, 2.0)
