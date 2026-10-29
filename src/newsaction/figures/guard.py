"""NA-14 operator check 5e: exploratory material appears only in the appendix.

    uv run python -m newsaction.figures.guard

``violations`` lists every place where a main figure or a main table cites exploratory material, which
``make paper`` refuses (``paper.build``):

- a main figure's title or caption citing an exploratory table or an exploratory row (``captions.yaml``);
- a main LaTeX table (T1–T6) printing a cell of one (``tables/latex.json``);
- a main figure's CSV plotting a row of one (``figures/*.csv``, its ``source`` and ``key``), read from the
  NA-14 table or from the NA-12 table it copies, or any upstream row whose key names NA-13's "exploratory"
  family (its MA-cross fade in the strategy table and the Figure 7 data).

The exploratory tables and rows are those ``tables/index.json`` marks (``tables.EXPLORATORY_TABLES`` and
``tables.EXPLORATORY_ROWS``); a figure is main unless it is an appendix figure (``figA…``).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from newsaction.figures import captions, latex, render
from newsaction.figures import keys as kz
from newsaction.figures import sources as sc
from newsaction.paths import Layout, resolve_layout

NA14_TABLE: Final = f"{sc.TABLES}/"
EXPLORATORY_FAMILY: Final = "exploratory"  # NA-13's family of its post hoc MA-cross fade, a part of its keys


def exploratory(layout: Layout | None = None) -> tuple[set[str], set[tuple[str, str]]]:
    """The exploratory tables and (table, row key) pairs, as ``index.json`` records them."""
    lay = resolve_layout(layout)
    index = json.loads((lay.root / sc.TABLES / "index.json").read_text(encoding="utf-8"))
    tables = {t["name"] for t in index if t.get("exploratory")}
    rows = {(t["name"], str(k)) for t in index for k in t.get("exploratory_rows", [])}
    return tables, rows


def _split(cited: str, names: Sequence[str]) -> tuple[str, str]:
    table = next((n for n in sorted(names, key=len, reverse=True) if cited.startswith(f"{n}/")), "")
    return table, cited[len(table) + 1 :].rpartition("/")[0]


def violations(
    layout: Layout | None = None,
    caps: Mapping[str, Mapping[str, Any]] | None = None,
    tex_index: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    lay = resolve_layout(layout)
    tables, rows = exploratory(lay)
    listing = json.loads((lay.root / sc.TABLES / "index.json").read_text(encoding="utf-8"))
    names = [t["name"] for t in listing]
    copies = {str(t["copy_of"]): t["name"] for t in listing if t.get("copy_of")}  # NA-12 path → NA-14 table

    def bad(cited: str) -> bool:
        table, key = _split(cited, names)
        return table in tables or (table, key) in rows

    out: list[str] = []
    for fig, entry in (caps if caps is not None else captions.load(lay)).items():
        if captions.main_figure(fig):
            text = f"{entry.get('title', '')} {entry.get('caption', '')}"
            out += [f"{fig} caption: {k}" for k in (kz.split(r)[0] for r in kz.refs(text)) if bad(k)]
    index = (
        tex_index
        if tex_index is not None
        else json.loads((lay.root / latex.INDEX).read_text(encoding="utf-8"))
    )
    for t in index:
        if t["section"] == latex.MAIN:
            out += [f"{t['name']} cell: {k}" for k in t["cells"] if bad(k)]
    for fig in render.MODULES:
        if not captions.main_figure(fig):
            continue
        df = render.read(fig, lay)
        for src, key in zip(df["source"], df["key"], strict=True):
            s, k = str(src), str(key)
            table = Path(s).stem if s.startswith(NA14_TABLE) else copies.get(s, "")
            if (table and (table in tables or (table, k) in rows)) or EXPLORATORY_FAMILY in k.split("|"):
                out.append(f"{fig} data: {table or s}/{k}")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    bad = violations()
    for b in bad:
        print(b, file=sys.stderr)
    print(f"guard: {len(bad)} citations of exploratory material in main figures or tables")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
