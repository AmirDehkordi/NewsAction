"""NA-14: the LaTeX preview of the paper (``figures.preview``; the operator's revision pass).

- the outline holds every figure and every LaTeX table exactly once, the main ones (Figures 1–7, Tables
  1–6) in the main text in their order and the rest after ``\\appendix``;
- the committed ``paper_preview.tex`` is the current rendering, every figure is included at its natural size
  (no scaling) and every table by ``\\input``;
- the PDF checks are not vacuous: every font of a figure PDF is embedded, the page count is read, and an
  overfull box on tectonic's console is caught;
- the committed preview PDF, if present, has every font embedded.
"""

from __future__ import annotations

import re

from newsaction.figures import preview, render, style
from newsaction.paths import ROOT

FIGURES = ROOT / "artifacts" / "NA-14" / "figures"


def test_the_outline_holds_every_figure_and_table_once() -> None:
    assert preview.check_outline() == []
    main = preview.items(preview.MAIN_OUTLINE)
    assert [n for n in main if n.startswith("fig")] == [n for n in render.MODULES if not n.startswith("figA")]
    tabs = [n for n in main if n.startswith("tab")]
    assert len(tabs) == 6 and all(n.startswith(f"tab{i}_") for i, n in enumerate(tabs, start=1))


def test_the_committed_preview_is_current() -> None:
    tex = preview.tex()
    assert tex == (ROOT / preview.PREVIEW).read_text(encoding="utf-8")
    assert r"\documentclass[11pt,letterpaper]{article}" in tex and r"\usepackage[margin=1in]{geometry}" in tex
    body, appendix = tex.split(r"\appendix", 1)
    for name in render.MODULES:
        assert f"\\includegraphics{{{name}.pdf}}" in (appendix if name.startswith("figA") else body), name
    assert "width=" not in tex and "scale=" not in tex  # figures at 100%
    order = [m.group(1) for m in re.finditer(r"\\includegraphics\{(fig\d)_", body)]
    assert order == sorted(order)


def test_figure_pdfs_embed_their_fonts() -> None:
    for name in ("fig1_validation_test", "fig6_strategies", "figA1_tournament"):
        fonts = preview.fonts((FIGURES / f"{name}.pdf").read_bytes())
        assert fonts and all(fonts.values()), fonts
        assert any("CMR10" in f.upper() for f in fonts)
    assert preview.pages((FIGURES / "fig1_validation_test.pdf").read_bytes()) == 1


def test_an_overfull_box_on_the_console_is_caught() -> None:
    line = r"warning: tables/x.tex:26: Overfull \hbox (9.23401pt too wide) in paragraph at lines 26--26"
    boxes = [float(m.group(1)) for m in preview._OVERFULL.finditer(line)]
    assert boxes == [9.23401] and preview._WHERE.findall(line) == [("tables/x.tex", "9.23401")]


def test_the_committed_pdf_embeds_every_font() -> None:
    pdf = ROOT / preview.PDF
    if pdf.is_file():
        fonts = preview.fonts(pdf.read_bytes())
        assert fonts and all(fonts.values())
        assert preview.pages(pdf.read_bytes()) > 20
    assert style.WIDTH_FULL == 6.5  # the preview's text width
