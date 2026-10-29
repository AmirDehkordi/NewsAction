"""NA-14 S5: ``make paper``, the offline rebuild of every paper table, figure and caption (PRD NA-14 AC1).

    uv run python -m newsaction.figures.paper [--root DIR] [--write-digests]

1. **Inputs.** Each file NA-14 reads (``INPUTS``: the NA-03 … NA-13b artifacts, NA-13's stored test
   positions and
   books, the operator's input file, the captions, two configs and the ledgers) must have the sha256
   recorded in
   ``artifacts/NA-14/digests.json``; a changed input stops the run before anything is rebuilt.
2. **Rebuild.** The tables (``tables``), their LaTeX (``latex``), the figure CSVs (``data``), every figure
   (``render``), the captions (``captions``, which first checks every cited number against its table cell) and
   the LaTeX preview (``preview``; ``make paper-preview`` compiles it).
3. **Outputs.** The sha256 of every CSV, LaTeX, JSON and Markdown output must equal the committed digest.
   The PDF
   and PNG digests are compared too but only reported: their bytes depend on the matplotlib and FreeType
   builds, while the plotted numbers are the CSVs.
4. **Guards.** No ledger may change (sha256 of every ``ledgers/*.jsonl`` before and after), and the run
   must not
   import the decision-model client, ``newsaction.lock``, ``panel.targets`` or ``panel.reactions``: nothing
   here calls an API, reads the lock or rebuilds an outcome.

``--write-digests`` records the current inputs and outputs (the author, once the outputs are final).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from newsaction.figures import captions, data, guard, latex, preview, render, tables
from newsaction.figures import sources as sc
from newsaction.paths import Layout

DIGESTS: Final = f"{sc.ARTIFACTS}/digests.json"
REPORT: Final = f"{sc.ARTIFACTS}/REPORT.md"
FORBIDDEN: Final = (
    "newsaction.lock",
    "newsaction.dm.client",
    "newsaction.panel.targets",
    "newsaction.panel.reactions",
    "newsaction.analysis.unblind",
)
TEXT_SUFFIXES: Final = (".csv", ".tex", ".json", ".md")
FIGURE_SUFFIXES: Final = (".pdf", ".png")
LEDGERS: Final = ("spend.jsonl", "fmp_requests.jsonl", "trials.jsonl", "test_access.jsonl")


def inputs() -> list[str]:
    """Every file NA-14 reads, as repository-relative paths."""
    fixed = {
        *sc.KEYS,
        sc.STRATEGY,
        f"{sc.NA12_TAB}/index.json",
        f"{sc.NA12_TAB}/keys.json",
        tables.OPERATOR,
        tables.CATALOG,
        tables.MONTHLY_JSON,
        tables.EXPLORATORY_JSON,
        tables.MA_CROSS_JSON,
        tables.SMOKE_JSON,
        tables.DEVIATIONS,
        tables.PREREG,
        tables.NA08_REPORT,
        tables.NA11_REPORT,
        tables.ABLATIONS,
        data.NA03_SUMMARY,
        captions.CAPTIONS,
        f"work/{tables.POSITIONS}",
        f"work/{tables.BOOKS}",
        f"work/{tables.PLACEBO}",
        "configs/splits.yaml",
        "configs/project.yaml",
        *(f"ledgers/{name}" for name in LEDGERS),
    }
    return sorted(fixed)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _na12_tables(root: Path) -> list[str]:
    return sorted(f"{sc.NA12_TAB}/{p.name}" for p in (root / sc.NA12_TAB).glob("*.csv"))


def outputs(root: Path) -> list[str]:
    """Every file ``make paper`` writes (under artifacts/NA-14, except its inputs and the digests)."""
    base = root / sc.ARTIFACTS
    skip = {captions.CAPTIONS, tables.OPERATOR, tables.DEVIATIONS, DIGESTS, REPORT, preview.PDF}
    files = [p for p in base.rglob("*") if p.is_file() and p.suffix in (*TEXT_SUFFIXES, *FIGURE_SUFFIXES)]
    return sorted(r for r in (p.relative_to(root).as_posix() for p in files) if r not in skip)


def digest(root: Path, paths: Iterable[str]) -> dict[str, str]:
    return {p: _sha(root / p) for p in paths}


def _diff(want: Mapping[str, str], got: Mapping[str, str]) -> list[str]:
    out = [f"missing {p}" for p in sorted(set(want) - set(got))]
    out += [f"new {p}" for p in sorted(set(got) - set(want))]
    out += [f"changed {p}" for p in sorted(set(want) & set(got)) if want[p] != got[p]]
    return out


def build(lay: Layout) -> dict[str, Any]:
    t0 = time.monotonic()
    tab = tables.write(lay)
    tex = latex.write(lay)
    csvs = data.write(lay)
    figs = [p for name in render.MODULES for p in render.draw(name, lay)]
    cap = captions.write(lay)
    bad = guard.violations(lay)
    if bad:
        raise ValueError(f"exploratory material in a main figure or table: {bad[:5]}")
    pre = preview.write(lay)
    return {
        "tables": tab,
        "latex": tex,
        "preview": str(pre),
        "figure_csvs": len(csvs),
        "figure_files": len(figs),
        "captions": str(cap),
        "seconds": round(time.monotonic() - t0, 1),
    }


def run(lay: Layout, *, write_digests: bool = False) -> tuple[int, dict[str, Any]]:
    root = lay.root
    report: dict[str, Any] = {"root": str(root)}
    ledgers_before = digest(root, [f"ledgers/{n}" for n in LEDGERS])
    committed = json.loads((root / DIGESTS).read_text(encoding="utf-8")) if (root / DIGESTS).is_file() else {}
    have_in = digest(root, inputs())
    if not write_digests:
        bad_in = _diff(committed.get("inputs", {}), have_in)
        if bad_in:
            report["inputs"] = bad_in
            return 1, report
    report["build"] = build(lay)
    out = outputs(root)
    have_text = digest(root, [p for p in out if p.endswith(TEXT_SUFFIXES)])
    have_fig = digest(root, [p for p in out if p.endswith(FIGURE_SUFFIXES)])
    ledgers_after = digest(root, [f"ledgers/{n}" for n in LEDGERS])
    report["ledgers_unchanged"] = ledgers_before == ledgers_after
    report["forbidden_imports"] = sorted(m for m in FORBIDDEN if m in sys.modules)
    status = 0
    if not report["ledgers_unchanged"] or report["forbidden_imports"]:
        status = 1
    if write_digests:
        payload = {"inputs": have_in, "outputs": have_text, "figures": have_fig}
        (root / DIGESTS).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        report["written"] = DIGESTS
        return status, report
    report["outputs"] = _diff(committed.get("outputs", {}), have_text) or "all equal"
    report["figures"] = _diff(committed.get("figures", {}), have_fig) or "all equal"
    if report["outputs"] != "all equal":
        status = 1
    report["counts"] = {"inputs": len(have_in), "outputs": len(have_text), "figures": len(have_fig)}
    return status, report


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m newsaction.figures.paper")
    ap.add_argument("--root", type=Path, default=None, help="repository root (default: this checkout)")
    ap.add_argument("--write-digests", action="store_true", help="record the current inputs and outputs")
    args = ap.parse_args(argv)
    from newsaction.paths import resolve_layout

    lay = Layout(args.root.resolve()) if args.root else resolve_layout(None)
    status, report = run(lay, write_digests=args.write_digests)
    print(json.dumps(report, indent=1, default=str))
    print("paper: OK" if status == 0 else "paper: FAILED", file=sys.stderr if status else sys.stdout)
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
