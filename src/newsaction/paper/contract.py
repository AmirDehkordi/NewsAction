"""NA-16's entries in ``work/MANIFEST.json`` and ``docs/DATA_CONTRACT.md``, regenerated as a whole.

    uv run python -m newsaction.paper.contract

Registers the manuscript's generated files (``io.register_artifact``) and rewrites the "NA-16" section of the
contract with each file's sha256. The compiled PDF is not registered: tectonic's bundle decides its bytes,
as for NA-14's preview; its sha256 is reported by ``make paper-pdf`` and in the REPORT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from newsaction import io
from newsaction.paper import build as bd
from newsaction.paper import numbers as nb
from newsaction.paths import Layout, resolve_layout

HEADING: Final = "## NA-16 — the manuscript (`newsaction.paper`)"
CHUNK: Final = "NA-16"
AVAIL: Final = "after NA-14 (every number is a cell of NA-14's committed tables; nothing here reads the lock)"


@dataclass(frozen=True)
class Entry:
    path: str
    producer: str
    inputs: str
    schema: str
    key: str
    rows: str
    availability: str = AVAIL


ENTRIES: Final = (
    Entry(
        nb.OUTPUT,
        "`newsaction.paper.numbers` (`make paper-text`)",
        f"`{nb.REGISTRY}`, `{nb.KEYS}`",
        "LaTeX: `\\res` and one `\\@namedef{res@<name>}{<value>}` per registry name, the cell in a comment",
        "the registry name",
        "every result number the manuscript prints, rendered from NA-14's table keys",
    ),
    Entry(
        nb.ABSTRACT_TXT,
        "`newsaction.paper.numbers` (`make paper-text`)",
        f"`{nb.ABSTRACT_TEX}`, `{nb.REGISTRY}`, `{nb.KEYS}`",
        "plain ASCII text, one line",
        "one file",
        "the abstract for arXiv's abstract field (180 to 250 words), its numbers resolved",
    ),
    Entry(
        bd.BBL,
        "`newsaction.paper.build` (`make paper-pdf`: tectonic's BibTeX on `paper/references.bib`)",
        "`paper/references.bib`, the citations of `paper/sections/*.tex`",
        "BibTeX output (plainnat)",
        "one file",
        "the bibliography arXiv needs (it does not run BibTeX)",
    ),
)


def _block(e: Entry, sha: str) -> str:
    return (
        f"### `{e.path}`\n- **Producer:** {e.producer}\n- **Inputs:** {e.inputs}\n- **Schema:** {e.schema}\n"
        f"- **Key:** {e.key}\n- **Rows / coverage:** {e.rows}\n- **Availability:** {e.availability}\n"
        f"- **sha256:** `{sha}`\n"
    )


def write(layout: Layout | None = None) -> list[str]:
    """Register every NA-16 generated file and rewrite the NA-16 contract section; returns the paths."""
    lay = resolve_layout(layout)
    blocks = []
    for e in ENTRIES:
        io.register_artifact(e.path, producer=CHUNK, description=e.rows, layout=lay)
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
    return [e.path for e in ENTRIES]


def main() -> int:
    paths = write()
    print(f"{len(paths)} NA-16 artifacts registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
