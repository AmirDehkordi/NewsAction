"""NA-16: the arXiv source bundle (``newsaction.paper.bundle``).

- the members are ``main.tex``, ``main.bbl`` and every file the sources name (each figure, table and section),
  nothing else, each from an existing source;
- the bundle's ``main.tex`` starts with ``\\pdfoutput=1`` and points its two path macros into the bundle;
- ``problems`` catches a member that leaves the bundle, a non-ASCII text member, a ``main.tex`` without
  ``\\pdfoutput=1`` or naming a path outside the bundle, and a missing ``main.bbl`` (each case fails if its
  guard is removed);
- rebuilt in a scratch copy, the bundle is byte-identical twice and equal to the committed one.

The pdflatex compile itself needs Docker's TeX Live image: ``make paper-arxiv-check``, not a unit test.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from newsaction.paper import bundle
from newsaction.paper import numbers as nb
from newsaction.paths import ROOT, Layout


def _named_by_sources() -> tuple[set[str], set[str]]:
    """The figure and table files the sections name, found independently of ``bundle.members``."""
    text = "\n".join(
        nb.COMMENT.sub("", p.read_text(encoding="utf-8")) for p in sorted((ROOT / nb.SECTIONS).glob("*.tex"))
    )
    graphics = r"\\includegraphics(?:\[[^\]]*\])?\{\\figdir/([^{}]+)\}"
    figs = {f"figures/{m}" for m in re.findall(graphics, text)}
    tabs = {f"tables/{m}" for m in re.findall(r"\\input\{\\tabdir/([^{}]+)\}", text)}
    return figs, tabs


def test_members_are_the_files_the_sources_name() -> None:
    members = bundle.members(ROOT)
    figs, tabs = _named_by_sources()
    assert figs and tabs
    assert {m for m in members if m.startswith("figures/")} == figs | {"figures/design_timeline.tex"}
    assert {m for m in members if m.startswith("tables/")} == tabs
    sections = {f"sections/{p.name}" for p in (ROOT / nb.SECTIONS).glob("*.tex")}
    assert {m for m in members if m.startswith("sections/")} == sections
    assert {"main.tex", "main.bbl", "generated/numbers.tex"} <= set(members)
    assert all(p.is_file() for p in members.values())


def test_main_tex_for_arxiv() -> None:
    text = bundle.main_tex((ROOT / nb.MAIN).read_text(encoding="utf-8"))
    assert text.splitlines()[0] == bundle.PDFOUTPUT
    assert "\\newcommand{\\figdir}{figures}" in text and "\\newcommand{\\tabdir}{tables}" in text
    assert "../" not in nb.COMMENT.sub("", text)
    with pytest.raises(ValueError, match="figdir"):
        bundle.main_tex("\\documentclass{article}\n")


GOOD = {
    "main.tex": b"\\pdfoutput=1\n\\documentclass{article}\n\\input{sections/a}\n",
    "main.bbl": b"\\begin{thebibliography}{1}\\end{thebibliography}\n",
    "sections/a.tex": b"Text.\n",
}


def test_a_good_bundle_has_no_problems() -> None:
    assert bundle.problems(dict(GOOD)) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"../outside.tex": b"x"}, "leaves the bundle"),
        ({"/abs/path.tex": b"x"}, "leaves the bundle"),
        ({"sections/a.tex": "na\u00efve\n".encode()}, "not ASCII"),
        ({"main.tex": b"\\documentclass{article}\n"}, "pdfoutput"),
        ({"main.tex": b"\\pdfoutput=1\n\\input{../paper/x}\n"}, "outside the bundle"),
        ({"main.bbl": None}, "main.bbl is missing"),
    ],
)
def test_problems_catch_each_defect(change: dict[str, bytes | None], expected: str) -> None:
    files = dict(GOOD)
    for name, data in change.items():
        if data is None:
            files.pop(name)
        else:
            files[name] = data
    assert any(expected in p for p in bundle.problems(files)), bundle.problems(files)


def test_the_bundle_is_reproducible_and_equals_the_committed_one(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "artifacts").mkdir(parents=True)
    (root / "paper").symlink_to(ROOT / "paper")
    (root / "artifacts" / "NA-14").symlink_to(ROOT / "artifacts" / "NA-14")
    shas = []
    for _ in range(2):
        status, report = bundle.build_bundle(Layout(root))
        assert status == 0, report
        shas.append(hashlib.sha256((root / bundle.BUNDLE).read_bytes()).hexdigest())
    assert shas[0] == shas[1] == hashlib.sha256((ROOT / bundle.BUNDLE).read_bytes()).hexdigest()
