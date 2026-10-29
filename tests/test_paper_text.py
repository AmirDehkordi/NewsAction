"""NA-16: the manuscript's numbers, abstract and source checks (``paper.numbers``, ``paper.build``).

- the committed macros and the arXiv abstract equal what the registry and NA-14's keys produce now;
- the committed sources break no rule (ASCII, every macro registered and used, no hand-typed result number,
  exploratory sentences labelled, an abstract of 180 to 250 words);
- each check catches a planted violation: a typed number in text or math, an unknown or unused macro, an
  unlabelled exploratory sentence, a non-ASCII character;
- values render as ASCII LaTeX that works in text and in math;
- the float-order check catches a figure numbered out of the order of its first mention, and one never cited.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from newsaction.paper import build as bd
from newsaction.paper import numbers as nb
from newsaction.paths import Layout

ROOT = Path(__file__).resolve().parents[1]


def _copy(tmp_path: Path) -> Path:
    """The manuscript sources, the registry, the allowlist and NA-14's keys in a scratch root."""
    shutil.copytree(ROOT / nb.PAPER, tmp_path / nb.PAPER, ignore=shutil.ignore_patterns("build"))
    shutil.copytree(ROOT / nb.ARXIV, tmp_path / nb.ARXIV)
    (tmp_path / nb.KEYS).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / nb.KEYS, tmp_path / nb.KEYS)
    return tmp_path


def test_the_committed_macros_and_abstract_are_current() -> None:
    for rel, text in nb.outputs(ROOT).items():
        assert (ROOT / rel).read_text(encoding="utf-8") == text, f"{rel} is stale: run make paper-text"


def test_the_committed_sources_break_no_rule() -> None:
    assert nb.problems(ROOT) == []


def test_every_registry_cell_exists_and_renders_as_ascii() -> None:
    values = nb.values(ROOT)
    assert len(values) == len(nb.load_registry(ROOT)) > 100
    for name, v in values.items():
        assert nb.latex_value(v).isascii(), name


def test_values_render_for_text_and_math() -> None:
    assert nb.latex_value("\u22120.044") == "\\ensuremath{-}0.044"
    assert nb.latex_value("13,748") == "13{,}748"
    assert nb.latex_value("62%") == "62\\%"
    assert nb.latex_value("<0.001") == "\\ensuremath{<}0.001"
    assert nb.latex_value("\u221e") == "\\ensuremath{\\infty}"
    assert nb.plain_value("\u22121.98") == "-1.98"


def test_the_abstract_is_plain_text_of_the_right_length() -> None:
    text = nb.abstract_text(ROOT)
    assert text.isascii() and "\\" not in text and "{" not in text and "$" not in text
    assert nb.ABSTRACT_WORDS[0] <= nb.words(text) <= nb.ABSTRACT_WORDS[1]
    assert "0.065" in text and "0.020" in text  # the numbers are resolved, not names


def test_a_typed_result_number_is_caught_in_text_and_in_math() -> None:
    allow = nb.load_allowlist(ROOT)
    assert nb.bare_numbers("The IC fell to 0.020 on the test.", allow) == ["0.020"]
    assert nb.bare_numbers("We find $b = -0.044$ here.", allow) == ["-0.044"]
    assert nb.bare_numbers("Of the 75 pairs, 8 passed.", allow) == ["75", "8"]
    # macros, references, dates, clock times, indices in math and allowlisted design constants pass
    ok = (
        "The IC fell to \\res{lf-ic-test} (Section~\\ref{sec:design}) on 2026-01-02 at 09:15, by $t+20$, "
        "with 10,000 draws at 0.05 and H1b \\citep{chan2003}."
    )
    assert nb.bare_numbers(ok, allow) == []


def test_unknown_and_unused_macros_are_reported(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    concl = root / nb.SECTIONS / "conclusion.tex"
    concl.write_text(concl.read_text(encoding="utf-8") + "\nSee \\res{no-such-number}.\n", encoding="utf-8")
    reg = root / nb.REGISTRY
    reg.write_text(
        reg.read_text(encoding="utf-8") + "  unused-name: t22_spend/trials/value@int\n", encoding="utf-8"
    )
    found = "\n".join(nb.problems(root))
    assert "no-such-number" in found and "is not in" in found
    assert "unused-name is not used by the text" in found


def test_an_unlabelled_exploratory_sentence_and_a_non_ascii_line_are_reported(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    explo = root / nb.EXPLORATORY_TEX
    explo.write_text(
        explo.read_text(encoding="utf-8")
        + "\nThe top decile moved \\res{sel-d1-on-10-test} typical moves.\n",
        encoding="utf-8",
    )
    concl = root / nb.SECTIONS / "conclusion.tex"
    concl.write_text(concl.read_text(encoding="utf-8") + "\nA caf\u00e9.\n", encoding="utf-8")
    found = "\n".join(nb.problems(root))
    assert "without 'exploratory' or 'post hoc'" in found
    assert "non-ASCII line conclusion.tex" in found


def test_an_allowlist_entry_needs_a_reason(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    allow = root / nb.ALLOWLIST
    allow.write_text(
        allow.read_text(encoding="utf-8").replace("phrases:\n", "phrases:\n  - {text: 'x'}\n", 1)
    )
    with pytest.raises(ValueError, match="no reason"):
        nb.load_allowlist(root)


def _float_root(tmp_path: Path, body: str) -> Path:
    (tmp_path / nb.PAPER).mkdir(parents=True)
    (tmp_path / nb.MAIN).write_text(
        "\\documentclass{article}\\begin{document}\n" + body + "\n\\end{document}\n", encoding="utf-8"
    )
    return tmp_path


def test_float_order_follows_first_mention(tmp_path: Path) -> None:
    good = (
        "See Figure~\\ref{fig:a}. \\begin{figure}\\caption{A}\\label{fig:a}\\end{figure} "
        "Then Figure~\\ref{fig:b}. \\begin{figure}\\caption{B}\\label{fig:b}\\end{figure}"
    )
    aux = "\\newlabel{fig:a}{{1}{2}}\n\\newlabel{fig:b}{{2}{3}}\n"
    assert bd.float_order(_float_root(tmp_path / "good", good), aux) == []
    swapped = (
        "See Figure~\\ref{fig:b} and Figure~\\ref{fig:a}. "
        "\\begin{figure}\\caption{A}\\label{fig:a}\\end{figure} "
        "\\begin{figure}\\caption{B}\\label{fig:b}\\end{figure}"
    )
    found = bd.float_order(_float_root(tmp_path / "swapped", swapped), aux)
    assert found and "order of first mention" in found[0]
    unref = "\\begin{figure}\\caption{A}\\label{fig:a}\\end{figure}"
    found = bd.float_order(_float_root(tmp_path / "unref", unref), "\\newlabel{fig:a}{{1}{2}}\n")
    assert found == ["fig:a is never referenced"]


def test_paper_text_writes_and_checks(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    (root / nb.OUTPUT).unlink()
    assert nb.main(["--check"], layout=Layout(root)) == 1  # a missing output is stale
    assert nb.main([], layout=Layout(root)) == 0
    assert nb.main(["--check"], layout=Layout(root)) == 0
