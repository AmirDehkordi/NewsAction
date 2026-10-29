"""NA-14's entries in ``work/MANIFEST.json`` and ``docs/DATA_CONTRACT.md`` (GAC5), regenerated as a whole.

    uv run python -m newsaction.figures.contract

Registers every file under ``artifacts/NA-14`` (``io.register_artifact``) and rewrites the "NA-14" section
of the
contract with each file's current sha256. Run it after ``make paper`` has produced the final outputs; ``make
paper`` itself writes no manifest entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from newsaction import io
from newsaction.figures import captions, data, latex, paper, preview, render, tables
from newsaction.figures import sources as sc
from newsaction.paths import Layout, resolve_layout

HEADING: Final = "## NA-14 — paper figures, tables and replication (`newsaction.figures`)"
AVAIL: Final = (
    "after NA-12 and NA-13 (test-period results are their stored outputs; nothing here reads the lock)"
)
FIG_SCHEMA: Final = ", ".join(f"`{c}`" for c in sc.COLUMNS)


@dataclass(frozen=True)
class Entry:
    path: str
    producer: str
    inputs: str
    schema: str
    key: str
    rows: str
    availability: str = AVAIL


def _figure_entries(root: Path) -> list[Entry]:
    out = []
    for name in render.MODULES:
        builder = data.BUILDERS[name]
        doc = (builder.__doc__ or name).split("\n\n")[0].replace("\n", " ")
        srcs = sorted(set(render.read(name, Layout(root))["source"]))
        out.append(
            Entry(
                f"{sc.FIGURES}/{name}.csv",
                f"`newsaction.figures.data` (`{builder.__name__}`)",
                ", ".join(f"`{s}`" for s in srcs),
                FIG_SCHEMA,
                "one row per plotted value; (`source`, `key`, `y_col`) name its upstream cell",
                doc,
            )
        )
        for ext in ("pdf", "png"):
            out.append(
                Entry(
                    f"{sc.FIGURES}/{name}.{ext}",
                    f"`newsaction.figures.render` (`{render.MODULES[name]}`)",
                    f"`{sc.FIGURES}/{name}.csv` only",
                    "vector PDF (TrueType fonts embedded)" if ext == "pdf" else "PNG, 300 dpi",
                    "one file",
                    f"the figure {name} at print size",
                )
            )
    return out


def _table_entries(root: Path) -> list[Entry]:
    index = json.loads((root / sc.TABLES / "index.json").read_text(encoding="utf-8"))
    out = []
    for t in index:
        how = f"byte copy of `{t['copy_of']}`" if t["copy_of"] else ", ".join(f"`{s}`" for s in t["sources"])
        out.append(
            Entry(
                f"{sc.TABLES}/{t['name']}.csv",
                "`newsaction.figures.tables`",
                how,
                ", ".join(f"`{c}`" for c in t["columns"]),
                "`key` unique",
                f"{t['rows']} rows: {t['title']}",
            )
        )
    for t in json.loads((root / latex.INDEX).read_text(encoding="utf-8")):
        out.append(
            Entry(
                f"{sc.TABLES}/{t['file']}",
                "`newsaction.figures.latex`",
                ", ".join(f"`{s}`" for s in t["sources"]) + " (the cells of `keys.json`)",
                "LaTeX: booktabs, threeparttable(x) notes, siunitx S columns; a float or a longtable",
                "one file",
                f"{'main' if t['section'] == latex.MAIN else 'appendix'} table {t['label']} "
                f"({len(t['cells'])} cited cells)",
            )
        )
    out += [
        Entry(
            latex.INDEX,
            "`newsaction.figures.latex`",
            "the LaTeX tables",
            "JSON list: name, label, section (main or appendix), file, sources, cells (every cited key)",
            "one entry per LaTeX table",
            "which cells each LaTeX table prints",
        ),
        Entry(
            f"{sc.TABLES}/keys.json",
            "`newsaction.figures.tables`",
            "every NA-14 table (NA-12's own keys for its copies)",
            '"<table>/<key>/<column>" → value',
            "one file",
            "the cells the captions cite",
        ),
        Entry(
            f"{sc.TABLES}/index.json",
            "`newsaction.figures.tables`",
            "every NA-14 table",
            "name, title, section, exploratory, exploratory_rows, columns, rows, notes, sources, copy_of, "
            "files",
            "one file",
            "the table index",
        ),
    ]
    return out


def _fixed() -> list[Entry]:
    return [
        Entry(
            tables.OPERATOR,
            "the operator (NA-14 preamble item 3)",
            "—",
            "YAML: `laya_release` {date, name, source}",
            "one file",
            "facts no earlier artifact records (Laya's release date)",
        ),
        Entry(
            tables.DEVIATIONS,
            "NA-14 (author; the operator's revision pass)",
            f"`{tables.PREREG}` §15",
            "YAML: rows → {row, date, chunk, change, reason}",
            "one entry per row of PREREG §15",
            "the one-line summaries of the deviations (t34 checks each against its row)",
        ),
        Entry(
            preview.PREVIEW,
            "`newsaction.figures.preview` (make paper)",
            "the figures, the LaTeX tables and `captions.yaml`",
            "LaTeX article (11 pt, US letter, 1-inch margins): every main figure and table in outline "
            "order, then "
            "the appendix",
            "one file",
            "the paper preview; `make paper-preview` compiles it with tectonic (the PDF's digest is "
            "reported, "
            "not registered)",
        ),
        Entry(
            captions.CAPTIONS,
            "NA-14 (author)",
            "the tables' keys",
            "YAML: figure → {section, title, caption}; "
            "numbers as {{table/key/column[@spec]}}, labels as [[...]]",
            "one entry per figure",
            "the caption templates; `python -m newsaction.figures.captions` checks every number",
        ),
        Entry(
            captions.RENDERED,
            "`newsaction.figures.captions`",
            f"`{captions.CAPTIONS}`, `{sc.TABLES}/keys.json`",
            "Markdown: one section per figure",
            "one file",
            "the rendered captions",
        ),
        Entry(
            paper.DIGESTS,
            "`newsaction.figures.paper --write-digests`",
            "the inputs and outputs of `make paper`",
            "JSON: inputs, outputs (text files), figures (PDF and PNG) → sha256",
            "one file",
            "what `make paper` must reproduce",
        ),
    ]


def _block(e: Entry, sha: str) -> str:
    return (
        f"### `{e.path}`\n- **Producer:** {e.producer}\n- **Inputs:** {e.inputs}\n- **Schema:** {e.schema}\n"
        f"- **Key:** {e.key}\n- **Rows / coverage:** {e.rows}\n- **Availability:** {e.availability}\n"
        f"- **sha256:** `{sha}`\n"
    )


def write(layout: Layout | None = None) -> list[str]:
    """Register every NA-14 artifact and rewrite the NA-14 contract section; returns the paths."""
    lay = resolve_layout(layout)
    entries = [*_fixed(), *_figure_entries(lay.root), *_table_entries(lay.root)]
    on_disk = {
        p.relative_to(lay.root).as_posix() for p in (lay.root / sc.ARTIFACTS).rglob("*") if p.is_file()
    }
    # The REPORT is documentation, as in NA-12 and NA-13; the compiled preview depends on tectonic's bundle,
    # so its digest is reported in the REPORT, not registered; its log names the build directory and is not
    # committed.
    listed = {e.path for e in entries} | {paper.REPORT, preview.PDF, preview.LOG}
    if on_disk - listed:
        raise ValueError(f"NA-14 files without a contract entry: {sorted(on_disk - listed)[:5]}")
    keep = {e.path for e in entries}
    with io._manifest_txn(lay) as m:  # drop the entries of NA-14 files that no longer exist (renamed figures)
        for rel in [r for r in m["artifacts"] if r.startswith(f"{sc.ARTIFACTS}/") and r not in keep]:
            del m["artifacts"][rel]
    blocks = []
    for e in entries:
        io.register_artifact(e.path, producer=sc.CHUNK, description=e.rows, layout=lay)
        blocks.append(_block(e, io.sha256_file(lay.root / e.path)))
    contract = lay.root / "docs" / "DATA_CONTRACT.md"
    text = contract.read_text(encoding="utf-8")
    section = HEADING + "\n\n" + "\n".join(blocks)
    if HEADING in text:
        start = text.index(HEADING)
        nxt = text.find("\n## ", start + len(HEADING))
        text = text[:start] + section + (text[nxt:] if nxt >= 0 else "")
    else:
        text = text.rstrip("\n") + "\n\n" + section
    io.atomic_write_bytes(contract, text.encode("utf-8"))
    return [e.path for e in entries]


def main() -> int:
    paths = write()
    print(f"{len(paths)} NA-14 artifacts registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
