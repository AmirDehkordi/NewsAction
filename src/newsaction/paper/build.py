"""NA-16: compile the manuscript and check it (``make paper-pdf``).

    uv run python -m newsaction.paper.build

Runs tectonic on ``paper/main.tex`` (deterministic mode, ``--keep-logs``, BibTeX included) in a temporary
directory and fails on a TeX error, any overfull box, an undefined reference or citation, a float taller than
the page, a font that is not embedded, or a figure or table numbered out of the order of its first mention (or
never mentioned). It copies the PDF to ``artifacts/NA-16/paper.pdf``, the log to ``artifacts/NA-16/paper.log``
(not committed: it names the temporary directory) and the bibliography to ``paper/generated/main.bbl`` (arXiv
needs the ``.bbl``; it does not run BibTeX), and reports the page count and the PDF's sha256 (not enforced:
tectonic's bundle decides the bytes).

The log and font checks are NA-14's (``figures.preview``).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from newsaction.figures import preview as pv
from newsaction.paper import numbers as nb
from newsaction.paths import Layout, resolve_layout

OUT_DIR: Final = "artifacts/NA-16"
PDF: Final = f"{OUT_DIR}/paper.pdf"
LOG: Final = f"{OUT_DIR}/paper.log"
BBL: Final = f"{nb.PAPER}/generated/main.bbl"

_INPUT: Final = re.compile(r"\\input\{([^{}]+)\}")
_REF: Final = re.compile(r"\\ref\{((?:fig|tab):[^{}]+)\}")
_LABEL: Final = re.compile(r"\\label\{((?:fig|tab):[^{}]+)\}")
_NEWLABEL: Final = re.compile(r"\\newlabel\{((?:fig|tab):[^{}]+)\}\{\{([^{}]*)\}")


def document(root: Path) -> str:
    """main.tex with every \\input expanded in place (the sections, the generated macros and NA-14's tables),
    comments dropped: the text in the order LaTeX reads it."""
    paper = root / nb.PAPER
    macros = {
        "\\figdir": "../artifacts/NA-14/figures",
        "\\tabdir": "../artifacts/NA-14/tables",
    }

    def expand(text: str, depth: int = 0) -> str:
        if depth > 5:
            raise ValueError("\\input nested too deep")

        def sub(m: re.Match[str]) -> str:
            name = m.group(1)
            for k, v in macros.items():
                name = name.replace(k, v)
            path = (paper / name).resolve()
            if path.suffix != ".tex":
                path = path.with_suffix(".tex")
            if not path.is_file():
                return m.group(0)  # e.g. glyphtounicode, from the TeX distribution
            return expand(nb.COMMENT.sub("", path.read_text(encoding="utf-8")), depth + 1)

        return _INPUT.sub(sub, text)

    return expand(nb.COMMENT.sub("", (paper / "main.tex").read_text(encoding="utf-8")))


def float_order(root: Path, aux: str) -> list[str]:
    """Problems with the numbering of figures and tables: each float must be referenced in the text, and
    within each series (main 1, 2, ... and appendix A1, A2, ...) the numbers must follow the order of first
    mention, with no gap."""
    doc = document(root)
    numbers = {m.group(1): m.group(2) for m in _NEWLABEL.finditer(aux)}
    labels = [m.group(1) for m in _LABEL.finditer(doc)]
    out: list[str] = []
    first: dict[str, int] = {}
    for m in _REF.finditer(doc):
        first.setdefault(m.group(1), m.start())
    for lab in labels:
        if lab not in first:
            out.append(f"{lab} is never referenced")
    for kind in ("fig", "tab"):
        for series in ("main", "appendix"):
            labs = [
                lab
                for lab in labels
                if lab.startswith(kind + ":")
                and lab in numbers
                and numbers[lab].startswith("A") == (series == "appendix")
                and lab in first
            ]
            by_mention = sorted(labs, key=lambda lab: first[lab])
            nums = [numbers[lab] for lab in by_mention]
            expected = [f"{'A' if series == 'appendix' else ''}{i}" for i in range(1, len(nums) + 1)]
            if nums != expected:
                out.append(
                    f"{kind} {series}: numbers in order of first mention are {nums}, expected {expected}"
                )
    return out


def compile_pdf(layout: Layout | None = None) -> tuple[int, dict[str, Any]]:
    lay = resolve_layout(layout)
    root = lay.root
    src = root / nb.MAIN
    report: dict[str, Any] = {"tex": nb.MAIN}
    with tempfile.TemporaryDirectory(prefix="na16-paper-") as tmp:
        cmd = [
            pv.tectonic(),
            "-X",
            "compile",
            "--keep-logs",
            "--keep-intermediates",
            "-Z",
            "deterministic-mode",
            "--outdir",
            tmp,
            str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=src.parent, check=False)
        t = Path(tmp)
        log = (
            (t / "main.log").read_text(encoding="utf-8", errors="replace")
            if (t / "main.log").is_file()
            else ""
        )
        aux = (
            (t / "main.aux").read_text(encoding="utf-8", errors="replace")
            if (t / "main.aux").is_file()
            else ""
        )
        report["tectonic_exit"] = proc.returncode
        report["errors"] = [ln for ln in log.splitlines() if ln.startswith("!")][:10]
        boxes = [
            (float(m.group(1)), m.group(2).strip()) for m in pv._OVERFULL.finditer(proc.stderr + "\n" + log)
        ]
        report["overfull_max_pt"] = max((b for b, _ in boxes), default=0.0)
        report["overfull"] = [f"{b:.2f}pt {w}" for b, w in boxes if b > pv.OVERFULL_PT]
        report["undefined"] = pv.undefined(log)
        report["float_too_large"] = pv.too_large(log)
        report["latex_warnings"] = sorted(
            {ln.strip() for ln in log.splitlines() if "LaTeX Warning" in ln and "Font" not in ln}
        )[:20]
        report["float_order"] = float_order(root, aux) if aux else ["no .aux file"]
        out_dir = root / OUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        if log:
            (root / LOG).write_text(log, encoding="utf-8")
        if (t / "main.bbl").is_file():
            shutil.copyfile(t / "main.bbl", root / BBL)
        pdf_tmp = t / "main.pdf"
        if proc.returncode != 0 or not pdf_tmp.is_file():
            report["stderr"] = proc.stderr[-3000:]
            return 1, report
        data = pdf_tmp.read_bytes()
        shutil.copyfile(pdf_tmp, root / PDF)
    fonts = pv.fonts(data)
    report["fonts"] = len(fonts)
    report["fonts_not_embedded"] = sorted(n for n, ok in fonts.items() if not ok)
    report["pages"] = pv.pages(data)
    report["pdf"] = PDF
    report["pdf_sha256"] = hashlib.sha256(data).hexdigest()
    ok = (
        not report["errors"]
        and not report["overfull"]
        and not report["undefined"]
        and not report["float_too_large"]
        and not report["fonts_not_embedded"]
        and not report["float_order"]
        and bool(fonts)
    )
    return (0 if ok else 1), report


def main(argv: Sequence[str] | None = None, layout: Layout | None = None) -> int:
    del argv
    status, report = compile_pdf(layout)
    print(json.dumps(report, indent=1))
    print(
        "paper-pdf: OK" if status == 0 else "paper-pdf: FAILED",
        file=sys.stdout if status == 0 else sys.stderr,
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
