"""NA-16: the arXiv source bundle and its pdflatex check (``make paper-arxiv``, ``make paper-arxiv-check``).

    uv run python -m newsaction.paper.bundle             # write artifacts/NA-16/arxiv_source.tar.gz
    uv run python -m newsaction.paper.bundle --pdflatex  # and compile it with pdflatex (TeX Live, Docker)

arXiv compiles a submission with pdflatex from the uploaded files alone and does not run BibTeX. The
bundle therefore holds ``main.tex`` with ``\\pdfoutput=1`` on its first line (arXiv's cue for pdflatex)
and the two path macros (``\\figdir``, ``\\tabdir``) pointing into the bundle; ``main.bbl``
(``paper/generated/main.bbl``, written by the same ``make paper-pdf``); the sections, the generated number
macros and the TikZ source of Figure 1; and, in ``figures/`` and ``tables/``, the NA-14 figures and tables
that the sources name. Nothing else goes in.

Checks (``problems``): every file the sources name exists and is packed; no member path is absolute or
climbs out of the bundle; every text member is ASCII; ``main.tex`` names no path outside the bundle. The
archive is deterministic (sorted members, fixed mtime, owner 0, mode 0644, gzip mtime 0): the same sources
give the same sha256.

``--pdflatex`` unpacks the bundle in a temporary directory and runs pdflatex three times in Docker's
``texlive/texlive`` image (default ``TL2023-historic``, the oldest TeX Live arXiv may still use;
``--image`` picks another), without network, then applies ``make paper-pdf``'s checks to the log and the
PDF: no TeX error, no overfull box, no undefined reference or citation, no float taller than the page,
every font embedded. The report goes to ``artifacts/NA-16/arxiv_check.json``; ``--keep DIR`` also keeps
the PDF and the log there. Nothing here reads data, calls an API or imports the lock.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io as bytes_io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from newsaction.figures import preview as pv
from newsaction.paper import build as bd
from newsaction.paper import numbers as nb
from newsaction.paths import Layout, resolve_layout

BUNDLE: Final = f"{bd.OUT_DIR}/arxiv_source.tar.gz"
CHECK: Final = f"{bd.OUT_DIR}/arxiv_check.json"
IMAGE: Final = "texlive/texlive:TL2023-historic"
MTIME: Final = 1_767_225_600  # 2026-01-01T00:00:00Z: a fixed member time, so the archive is reproducible
PDFOUTPUT: Final = "\\pdfoutput=1"
# The path macros of paper/main.tex: their value under paper/ and in the bundle.
MACROS: Final = {
    "\\figdir": ("../artifacts/NA-14/figures", "figures"),
    "\\tabdir": ("../artifacts/NA-14/tables", "tables"),
}
SYSTEM_INPUTS: Final = frozenset({"glyphtounicode"})  # from the TeX distribution, not the bundle
_NEEDS: Final = re.compile(r"\\(input|includegraphics)(?:\[[^\]]*\])?\{([^{}]+)\}")


def members(root: Path) -> dict[str, Path]:
    """Every bundle member (its path in the bundle) and its source file: ``main.tex``, ``main.bbl`` and
    each file that ``main.tex`` names through ``\\input`` or ``\\includegraphics``, followed into the files
    it names."""
    paper = root / nb.PAPER
    out: dict[str, Path] = {"main.tex": paper / "main.tex", "main.bbl": root / bd.BBL}
    todo = [paper / "main.tex"]
    while todo:
        text = nb.COMMENT.sub("", todo.pop().read_text(encoding="utf-8"))
        for m in _NEEDS.finditer(text):
            name = m.group(2)
            if name in SYSTEM_INPUTS:
                continue
            member = name
            for macro, (src, dst) in MACROS.items():
                if name.startswith(macro + "/"):
                    member = dst + name[len(macro) :]
                    name = src + name[len(macro) :]
            if m.group(1) == "input" and not name.endswith(".tex"):
                name, member = name + ".tex", member + ".tex"
            src_path = (paper / name).resolve()
            if member in out and out[member] != src_path:
                raise ValueError(f"two sources for bundle member {member}: {out[member]}, {src_path}")
            if member not in out:
                out[member] = src_path
                if src_path.suffix == ".tex" and src_path.is_file():
                    todo.append(src_path)
    return dict(sorted(out.items()))


def main_tex(text: str) -> str:
    """paper/main.tex as arXiv compiles it: ``\\pdfoutput=1`` first, the path macros pointing into the
    bundle."""
    for macro, (src, dst) in MACROS.items():
        old = f"\\newcommand{{{macro}}}{{{src}}}"
        if text.count(old) != 1:
            raise ValueError(f"main.tex must define {macro} as {src} exactly once")
        text = text.replace(old, f"\\newcommand{{{macro}}}{{{dst}}}")
    return f"{PDFOUTPUT}\n{text}"


def problems(files: dict[str, bytes]) -> list[str]:
    """What would make the bundle fail on arXiv or leak a path: see the module docstring."""
    out: list[str] = []
    for name, data in files.items():
        if name.startswith("/") or ".." in Path(name).parts:
            out.append(f"{name}: leaves the bundle")
        if name.endswith((".tex", ".bbl")):
            try:
                data.decode("ascii")
            except UnicodeDecodeError:
                out.append(f"{name}: not ASCII")
    main = files.get("main.tex", b"").decode("ascii", errors="replace")
    if main.splitlines()[:1] != [PDFOUTPUT]:
        out.append("main.tex: \\pdfoutput=1 is not its first line")
    if "../" in nb.COMMENT.sub("", main):
        out.append("main.tex: names a path outside the bundle")
    if "main.bbl" not in files:
        out.append("main.bbl is missing (arXiv does not run BibTeX)")
    return out


def build_bundle(layout: Layout | None = None) -> tuple[int, dict[str, Any]]:
    """Write the bundle; returns (status, report)."""
    lay = resolve_layout(layout)
    root = lay.root
    srcs = members(root)
    missing = [f"{m} <- {p}" for m, p in srcs.items() if not p.is_file()]
    if missing:
        return 1, {"missing": missing}
    files = {m: p.read_bytes() for m, p in srcs.items()}
    files["main.tex"] = main_tex(files["main.tex"].decode("ascii")).encode("ascii")
    bad = problems(files)
    if bad:
        return 1, {"problems": bad}
    buf = bytes_io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), MTIME, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tf.addfile(info, bytes_io.BytesIO(data))
    out = root / BUNDLE
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh, gzip.GzipFile(filename="", fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(buf.getvalue())
    data = out.read_bytes()
    return 0, {
        "bundle": BUNDLE,
        "members": len(files),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "figures": sum(m.startswith("figures/") for m in files),
        "tables": sum(m.startswith("tables/") for m in files),
    }


def check_pdflatex(
    layout: Layout | None = None, *, image: str = IMAGE, keep: Path | None = None
) -> tuple[int, dict[str, Any]]:
    """Compile the bundle with pdflatex (three passes) in ``image`` and check the log and the PDF."""
    lay = resolve_layout(layout)
    data_in = (lay.root / BUNDLE).read_bytes()
    report: dict[str, Any] = {
        "image": image,
        "bundle": BUNDLE,
        "bundle_sha256": hashlib.sha256(data_in).hexdigest(),
    }
    with tempfile.TemporaryDirectory(prefix="na16-arxiv-") as tmp:
        with tarfile.open(lay.root / BUNDLE, mode="r:gz") as tf:
            tf.extractall(tmp, filter="data")
        script = (
            "for i in 1 2 3; do "
            "pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null || exit 1; done"
        )
        cmd = ["docker", "run", "--rm", "--network", "none", "-e", f"SOURCE_DATE_EPOCH={MTIME}"]
        cmd += ["-e", "FORCE_SOURCE_DATE=1", "-v", f"{tmp}:/work", "-w", "/work", image, "sh", "-c", script]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, check=False)
        t = Path(tmp)
        log = (t / "main.log").read_text(encoding="latin-1") if (t / "main.log").is_file() else ""
        report["engine"] = log.splitlines()[0] if log else proc.stderr[-500:]
        report["exit"] = proc.returncode
        report["errors"] = [ln for ln in log.splitlines() if ln.startswith("!")][:10]
        boxes = [float(m.group(1)) for m in pv._OVERFULL.finditer(log)]
        report["overfull"] = [f"{b:.2f}pt" for b in boxes if b > pv.OVERFULL_PT]
        report["underfull"] = log.count("Underfull \\hbox")
        report["undefined"] = pv.undefined(log)
        report["float_too_large"] = pv.too_large(log)
        report["rerun"] = "Rerun to get" in log
        pdf = t / "main.pdf"
        data = pdf.read_bytes() if pdf.is_file() else b""
        if keep is not None and data:
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pdf, keep / "main.pdf")
            (keep / "main.log").write_text(log, encoding="utf-8")
    fonts = pv.fonts(data) if data else {}
    report["pages"] = pv.pages(data) if data else 0
    report["fonts"] = len(fonts)
    report["fonts_not_embedded"] = sorted(n for n, ok in fonts.items() if not ok)
    ok = (
        proc.returncode == 0
        and bool(data)
        and not report["errors"]
        and not report["overfull"]
        and not report["undefined"]
        and not report["float_too_large"]
        and not report["rerun"]
        and not report["fonts_not_embedded"]
    )
    out = lay.root / CHECK
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return (0 if ok else 1), report


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m newsaction.paper.bundle")
    ap.add_argument("--pdflatex", action="store_true", help="also compile the bundle with pdflatex (Docker)")
    ap.add_argument("--image", default=IMAGE, help=f"TeX Live image (default {IMAGE})")
    ap.add_argument("--keep", type=Path, default=None, help="keep the pdflatex PDF and log in this directory")
    args = ap.parse_args(argv)
    status, report = build_bundle()
    if status == 0 and args.pdflatex:
        status, report["pdflatex"] = check_pdflatex(image=args.image, keep=args.keep)
    print(json.dumps(report, indent=1))
    print(
        "paper-arxiv: OK" if status == 0 else "paper-arxiv: FAILED",
        file=sys.stdout if status == 0 else sys.stderr,
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
