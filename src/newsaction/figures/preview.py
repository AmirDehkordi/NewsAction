"""NA-14: the LaTeX preview of the paper's figures and tables (the operator's revision pass).

    uv run python -m newsaction.figures.preview            # write artifacts/NA-14/paper_preview.tex
    uv run python -m newsaction.figures.preview --compile  # make paper-preview: also compile and check it

``write`` renders ``paper_preview.tex``: an article in the manuscript's format (11 pt, US letter, 1-inch
margins, one column) with the preamble the tables need, every main figure and table in the order of
``docs/paper_outline.md`` with its caption, then the appendix. It refuses an outline that misses or repeats a
figure or a LaTeX table. ``make paper`` writes it, so its digest is enforced.

``compile`` runs tectonic (deterministic mode, ``--keep-logs``) on it and checks the result: no TeX error, no
overfull box, no float taller than the page, no undefined reference, every font of the PDF embedded. It
copies the PDF to ``paper_preview.pdf`` and the log to ``paper_preview.log`` (not committed: it names the
temporary build directory), and reports the PDF's sha256 without enforcing it (tectonic's bundle and engine
decide the bytes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from newsaction.figures import captions, latex, render
from newsaction.figures import keys as kz
from newsaction.figures import sources as sc
from newsaction.paths import Layout, resolve_layout

PREVIEW: Final = f"{sc.ARTIFACTS}/paper_preview.tex"
PDF: Final = f"{sc.ARTIFACTS}/paper_preview.pdf"
LOG: Final = f"{sc.ARTIFACTS}/paper_preview.log"
TECTONIC: Final = ("tectonic", "/opt/homebrew/bin/tectonic")
OVERFULL_PT: Final = 0.0  # the polish pass: no overfull box at all

# The paper's sections and what each shows, in order (docs/paper_outline.md).
Outline = tuple[tuple[str, tuple[str, ...]], ...]
MAIN_OUTLINE: Final[Outline] = (
    ("Question and decision models", ("fig1_validation_test",)),
    ("Design: pre-registration, freeze, blinding, masking, ledgers", ()),
    ("Reading the news: priced at the open", ("fig2_priced_at_open", "tab1_primary", "tab2_ic_by_target")),
    (
        "Over- and under-reaction, and convergence to the news-implied value",
        ("fig3_convergence", "fig4_over_under", "tab3_over_under", "tab4_convergence"),
    ),
    ("Explaining realized moves", ("fig5_explaining_moves", "tab5_explaining_moves")),
    ("Economic significance", ("fig6_strategies", "tab6_strategies")),
    ("Memorisation and validation-to-test decay", ("fig7_memorisation",)),
)
APPENDIX_OUTLINE: Final[Outline] = (
    ("Decision models", ("figA1_tournament", "t14_model_comparison", "t27_tournament")),
    (
        "Design",
        (
            "figA2_filters",
            "figA3_encoding",
            "t28_filter_frontier",
            "t29_encoding",
            "t22_spend",
            "t34_prereg_deviations",
        ),
    ),
    (
        "Priced at the open",
        (
            "figA4_reliability",
            "figA5_robustness",
            "figA6_monthly_ic",
            "t1b_primary_by_model",
            "t3_ic",
            "t32_val_b_ic",
            "t15_calibration",
            "t16_robustness",
            "t19_monthly_ic",
        ),
    ),
    (
        "Over- and under-reaction, and convergence",
        (
            "figA7_convergence_detail",
            "figA8_drift_laya_fin",
            "figA9_shapley",
            "figA10_ablations",
            "t2_h2_over_under",
            "t4_secondary",
            "t5_heterogeneity",
            "t6_convergence_ladder",
            "t7_gap_closure",
            "t8_tracking_error",
            "t9_convergence_cuts",
            "t13_shapley",
            "t30_derived",
        ),
    ),
    (
        "Explaining realized moves",
        (
            "figA11_persistence",
            "t10_explanation_ladder",
            "t11_explanation_share_theta",
            "t12_question_battery",
        ),
    ),
    (
        "Economic significance",
        (
            "figA12_strategy_paths",
            "t20_strategies",
            "t26_sconv_overlap",
            "t33_placebo_sharpe",
            "t35_break_even",
        ),
    ),
    (
        "Memorisation",
        ("figA13_probes", "t21_release_dates", "t23_company_identification", "t18_probes_val_a"),
    ),
    (
        "Exploratory analyses (post hoc)",
        (
            "figA14_exploratory_d0",
            "figA15_exploratory_ma_cross",
            "t17_sector_exploratory",
            "t25_ma_cross",
            "t31_market_replication",
        ),
    ),
    (
        "When the D0 signal works (exploratory, post hoc; NA-13b)",
        (
            "figA16_selective_coverage",
            "figA17_watch_open",
            "figA18_conditioning_map",
            "figA19_output_histograms",
            "t36_selective_coverage",
            "t37_watch_open",
            "t38_conditioning",
            "t39_conditioning_books",
            "t43_band_disclosure",
        ),
    ),
)

PREAMBLE: Final = r"""% NA-14 paper preview: every figure and table of the paper, with captions, in the
% manuscript's format.
% Written by `python -m newsaction.figures.preview` (make paper); compiled by `make paper-preview` (tectonic).
\documentclass[11pt,letterpaper]{article}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs,array,longtable,threeparttable,threeparttablex,pdflscape}
\usepackage{siunitx}
\sisetup{group-separator={,},group-minimum-digits=4,group-digits=integer,table-align-text-before=false,table-align-text-after=false}
\usepackage[font=small,labelfont=bf,skip=4pt]{caption}
\setlength{\LTcapwidth}{\textwidth}
\renewcommand{\thetable}{\arabic{table}}
\graphicspath{{figures/}}
\begin{document}
\begin{center}
{\large NewsAction: paper figures and tables (preview)}\\[4pt]
{\small Every number is a cell of artifacts/NA-14/tables; captions from captions.yaml.}
\end{center}
"""


def items(outline: Sequence[tuple[str, Sequence[str]]]) -> list[str]:
    return [n for _, names in outline for n in names]


def check_outline(layout: Layout | None = None) -> list[str]:
    """Every figure and every LaTeX table exactly once, main ones in the main text."""
    lay = resolve_layout(layout)
    tabs = {t["name"]: t for t in json.loads((lay.root / latex.INDEX).read_text(encoding="utf-8"))}
    figs = set(render.MODULES)
    listed = items(MAIN_OUTLINE) + items(APPENDIX_OUTLINE)
    bad = [f"listed twice: {n}" for n in sorted({n for n in listed if listed.count(n) > 1})]
    bad += [f"not in the outline: {n}" for n in sorted((figs | set(tabs)) - set(listed))]
    bad += [f"unknown: {n}" for n in sorted(set(listed) - figs - set(tabs))]
    for n in items(MAIN_OUTLINE):
        if (n in tabs and tabs[n]["section"] != latex.MAIN) or (n in figs and not captions.main_figure(n)):
            bad.append(f"an appendix item in the main text: {n}")
    for n in items(APPENDIX_OUTLINE):
        if (n in tabs and tabs[n]["section"] == latex.MAIN) or (n in figs and captions.main_figure(n)):
            bad.append(f"a main item in the appendix: {n}")
    return bad


def caption_tex(name: str, entry: dict[str, Any], keys: dict[str, Any]) -> str:
    title = latex.tex(kz.cite(" ".join(str(entry["title"]).split()), keys))
    body = latex.tex(kz.cite(" ".join(str(entry["caption"]).split()), keys))
    return rf"\textbf{{{title}.}} {body}"


def figure_tex(name: str, entry: dict[str, Any] | None, keys: dict[str, Any]) -> str:
    cap = caption_tex(name, entry, keys) if entry else latex.tex(name.replace("_", " "))
    return "\n".join(
        (
            r"\begin{figure}[htbp]",
            r"\centering",
            rf"\includegraphics{{{name}.pdf}}",
            rf"\caption{{{cap}}}\label{{fig:{name}}}",
            r"\end{figure}",
        )
    )


def tex(layout: Layout | None = None) -> str:
    lay = resolve_layout(layout)
    bad = check_outline(lay)
    if bad:
        raise ValueError(f"paper outline: {bad[:5]}")
    keys = kz.load(lay.root / sc.TABLES / "keys.json")
    caps = captions.load(lay)
    figs = set(render.MODULES)
    out = [PREAMBLE]

    def put(name: str) -> None:
        out.append(
            figure_tex(name, caps.get(name), keys) if name in figs else rf"\input{{tables/{name}.tex}}"
        )

    for title, names in MAIN_OUTLINE:
        out.append(rf"\section{{{latex.tex(title)}}}")
        if not names:
            out.append(r"\noindent\emph{No main figure or table; this section's are in the appendix.}")
        for n in names:
            put(n)
        out.append(r"\clearpage")
    out.append(r"\appendix")
    out.append(r"\renewcommand{\thefigure}{A\arabic{figure}}\setcounter{figure}{0}")
    out.append(r"\renewcommand{\thetable}{A\arabic{table}}\setcounter{table}{0}")
    for title, names in APPENDIX_OUTLINE:
        out.append(rf"\section{{{latex.tex(title)}}}")
        for n in names:
            put(n)
            out.append(r"\clearpage")
    out.append(r"\end{document}")
    return "\n\n".join(out) + "\n"


def write(layout: Layout | None = None) -> Path:
    lay = resolve_layout(layout)
    path = lay.root / PREVIEW
    path.write_text(tex(lay), encoding="utf-8")
    return path


# --- compile and check --------------------------------------------------------------------------------------

_OVERFULL: Final = re.compile(
    r"Overfull \\[hv]box \((\d+(?:\.\d+)?)pt too (?:wide|high)\)(.*)$", re.MULTILINE
)
_WHERE: Final = re.compile(r"warning: (\S+?):\d+: Overfull \\[hv]box \((\d+(?:\.\d+)?)pt")
_UNDEFINED: Final = re.compile(
    r"(Reference|Citation) `[^']*' on page \d+ undefined|There were undefined references"
)


_TOO_LARGE: Final = re.compile(r"Float too large for page by \d+(?:\.\d+)?pt on input line \d+")


def undefined(log: str) -> list[str]:
    """The undefined references and citations a LaTeX log reports."""
    return sorted({m.group(0) for m in _UNDEFINED.finditer(log)})


def too_large(log: str) -> list[str]:
    """The floats a LaTeX log reports as taller than the page (they run into the bottom margin)."""
    return [m.group(0) for m in _TOO_LARGE.finditer(log)]


_STREAM: Final = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_DICT: Final = re.compile(rb"<<(?:[^<>]|<[^<]|>[^>])*?/Type\s*/FontDescriptor(?:[^<>]|<[^<]|>[^>])*?>>")
_FONTNAME: Final = re.compile(rb"/FontName\s*/([^\s/>\[]+)")
_BASEFONT: Final = re.compile(
    rb"/Type\s*/Font\b(?:[^<>]|<[^<]|>[^>])*?/Subtype\s*/(\w+)(?:[^<>]|<[^<]|>[^>])*?/BaseFont\s*/([^\s/>\[]+)"
)


def fonts(pdf: bytes) -> dict[str, bool]:
    """Font name → embedded (its descriptor has a font file), from the PDF and its compressed streams.
    A Type 3 font is embedded by construction; a simple font without a descriptor is not."""
    texts = [pdf]
    for m in _STREAM.finditer(pdf):
        try:
            texts.append(zlib.decompress(m.group(1)))
        except zlib.error:
            continue
    out: dict[str, bool] = {}
    for t in texts:
        for d in _DICT.finditer(t):
            name = _FONTNAME.search(d.group(0))
            key = name.group(1).decode("latin-1") if name else "?"
            out[key] = out.get(key, False) or bool(re.search(rb"/FontFile[23]?\b", d.group(0)))
        for f in _BASEFONT.finditer(t):
            sub, base = f.group(1).decode(), f.group(2).decode("latin-1")
            if sub == "Type3":
                out.setdefault(base, True)
            elif sub in ("Type1", "TrueType") and b"/FontDescriptor" not in f.group(0):
                out.setdefault(base, False)
    return out


def pages(pdf: bytes) -> int:
    """The number of pages: the /Count of the root page tree (also inside a compressed object stream)."""
    texts = [pdf]
    for m in _STREAM.finditer(pdf):
        try:
            texts.append(zlib.decompress(m.group(1)))
        except zlib.error:
            continue
    counts = [int(c) for t in texts for c in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", t)]
    counts += [int(c) for t in texts for c in re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", t)]
    return max(counts, default=0)


def tectonic() -> str:
    for t in TECTONIC:
        found = shutil.which(t) or (t if Path(t).is_file() else None)
        if found:
            return found
    raise FileNotFoundError("tectonic is not installed (brew install tectonic)")


def compile_pdf(layout: Layout | None = None) -> tuple[int, dict[str, Any]]:
    lay = resolve_layout(layout)
    src = lay.root / PREVIEW
    report: dict[str, Any] = {"tex": PREVIEW}
    with tempfile.TemporaryDirectory(prefix="na14-preview-") as tmp:
        cmd = [
            tectonic(),
            "-X",
            "compile",
            "--keep-logs",
            "-Z",
            "deterministic-mode",
            "-Z",
            f"search-path={src.parent}",
            "--outdir",
            tmp,
            str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=src.parent, check=False)
        log = (
            (Path(tmp) / "paper_preview.log").read_text(encoding="utf-8", errors="replace")
            if (Path(tmp) / "paper_preview.log").is_file()
            else ""
        )
        report["tectonic_exit"] = proc.returncode
        report["errors"] = [ln for ln in log.splitlines() if ln.startswith("!")][:10]
        # tectonic reports the boxes on its console (with the file and line), not always in the log
        boxes = [
            (float(m.group(1)), m.group(2).strip()) for m in _OVERFULL.finditer(proc.stderr + "\n" + log)
        ]
        report["overfull_files"] = sorted(
            {w for w, b in _WHERE.findall(proc.stderr) if float(b) > OVERFULL_PT}
        )
        report["overfull_max_pt"] = max((b for b, _ in boxes), default=0.0)
        report["overfull"] = [f"{b:.2f}pt {w}" for b, w in boxes if b > OVERFULL_PT]
        report["undefined"] = undefined(log)
        report["float_too_large"] = too_large(log)
        if log:
            (lay.root / LOG).write_text(log, encoding="utf-8")
        pdf_tmp = Path(tmp) / "paper_preview.pdf"
        if proc.returncode != 0 or not pdf_tmp.is_file():
            report["stderr"] = proc.stderr[-2000:]
            return 1, report
        data = pdf_tmp.read_bytes()
        shutil.copyfile(pdf_tmp, lay.root / PDF)
    f = fonts(data)
    report["fonts"] = len(f)
    report["fonts_not_embedded"] = sorted(n for n, ok in f.items() if not ok)
    report["pages"] = pages(data)
    report["pdf"] = PDF
    report["pdf_sha256"] = hashlib.sha256(data).hexdigest()
    ok = (
        not report["errors"]
        and not report["overfull"]
        and not report["undefined"]
        and not report["float_too_large"]
        and not report["fonts_not_embedded"]
        and f
    )
    return (0 if ok else 1), report


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m newsaction.figures.preview")
    ap.add_argument("--compile", action="store_true", help="compile with tectonic and check the PDF")
    args = ap.parse_args(argv)
    print(write())
    if not args.compile:
        return 0
    status, report = compile_pdf()
    print(json.dumps(report, indent=1))
    print(
        "paper-preview: OK" if status == 0 else "paper-preview: FAILED",
        file=sys.stdout if status == 0 else sys.stderr,
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
