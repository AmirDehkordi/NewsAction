"""NA-14 S4: render the captions and check every number in them against the tables (PRD NA-14 S4, AC2).

    uv run python -m newsaction.figures.captions

``artifacts/NA-14/captions.yaml`` holds one entry per figure (section, title, caption). A caption cites each
number as ``{{table/key/column[@spec]}}`` (``keys``); ``check`` returns every problem:

- a cited key missing from ``tables/keys.json``, or a format spec that does not apply;
- a cited value that differs from the cell of ``tables/<table>.csv`` (row ``key``, column ``column``), and,
  for a
  copied NA-12 table, from the NA-12 CSV it copies;
- a digit outside every citation and ``[[literal]]`` (an uncited number);
- in a main figure (1–7), a citation of an exploratory table or row (``index.json``): exploratory material
  appears only in the appendix;
- a caption without its figure or a figure without its caption.

``write`` renders ``captions.md`` (title, caption, files) after ``check`` passes.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import pandas as pd
import yaml

from newsaction.figures import keys as kz
from newsaction.figures import sources as sc
from newsaction.paths import Layout, resolve_layout

CAPTIONS: Final = f"{sc.ARTIFACTS}/captions.yaml"
RENDERED: Final = f"{sc.ARTIFACTS}/captions.md"
RTOL: Final = 1e-9


def load(layout: Layout | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = yaml.safe_load(
        (resolve_layout(layout).root / CAPTIONS).read_text(encoding="utf-8")
    )
    return out


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        if isinstance(a, str) and a in ("inf", "-inf"):
            a = float(a)
        if isinstance(b, str) and b in ("inf", "-inf"):
            b = float(b)
        if isinstance(a, str) or isinstance(b, str):
            return str(a) == str(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    fa, fb = float(a), float(b)
    if math.isinf(fa) or math.isinf(fb):
        return fa == fb
    return math.isclose(fa, fb, rel_tol=RTOL, abs_tol=1e-15)


class Cells:
    """The tables' CSV cells by (table, key, column), read once."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._t: dict[str, pd.DataFrame] = {}

    def cell(self, table: str, key: str, column: str, *, base: str = sc.TABLES) -> Any:
        path = f"{base}/{table}.csv"
        if path not in self._t:
            df = pd.read_csv(self.root / path, keep_default_na=False, na_values=[""])
            self._t[path] = df.set_index(df["key"].astype(str))
        df = self._t[path]
        if key not in df.index or column not in df.columns:
            raise KeyError(f"{path}: no cell ({key!r}, {column!r})")
        v = df.loc[key, column]
        return v.item() if hasattr(v, "item") else v


def main_figure(name: str) -> bool:
    """Figures 1–7 are the paper's; A1–A19 (every ``figA…`` stem) are the appendix's."""
    return not name.startswith("figA")


def _split_key(k: str, tables: Sequence[str]) -> tuple[str, str, str]:
    """``table/key/column`` → its parts; the key may itself hold "/" (an NA-12 key never does)."""
    table = next((t for t in sorted(tables, key=len, reverse=True) if k.startswith(t + "/")), None)
    if table is None:
        raise KeyError(f"{k!r} names no table")
    rest = k[len(table) + 1 :]
    key, _, column = rest.rpartition("/")
    return table, key, column


def check(layout: Layout | None = None, captions: Mapping[str, Mapping[str, Any]] | None = None) -> list[str]:
    lay = resolve_layout(layout)
    caps = captions if captions is not None else load(lay)
    keys = kz.load(lay.root / sc.TABLES / "keys.json")
    listing: list[dict[str, Any]] = json.loads(
        (lay.root / sc.TABLES / "index.json").read_text(encoding="utf-8")
    )
    index = {t["name"]: t for t in listing}
    exploratory = {n for n, t in index.items() if t.get("exploratory")}
    exploratory_rows = {(n, k) for n, t in index.items() for k in t.get("exploratory_rows", [])}
    cells = Cells(lay.root)
    bad: list[str] = []
    figures = {p.stem for p in (lay.root / sc.FIGURES).glob("*.pdf")}
    for name in sorted(figures - set(caps)):
        bad.append(f"{name}: a figure without a caption")
    for name, entry in caps.items():
        if name not in figures:
            bad.append(f"{name}: a caption without its figure")
        text = " ".join(str(entry.get(f, "")) for f in ("title", "caption"))
        for word in kz.bare_digits(text):
            bad.append(f"{name}: uncited number {word!r}")
        for ref in kz.refs(text):
            k, _spec = kz.split(ref)
            if k not in keys:
                bad.append(f"{name}: unknown key {k!r}")
                continue
            try:
                kz.render(ref, keys)
            except (TypeError, ValueError) as exc:
                bad.append(f"{name}: {ref!r}: {exc}")
            try:
                table, key, column = _split_key(k, list(index))
                if main_figure(name) and (table in exploratory or (table, key) in exploratory_rows):
                    bad.append(f"{name}: {k!r} is exploratory, which only the appendix may cite")
                v = cells.cell(table, key, column)
                if not _equal(keys[k], v):
                    bad.append(f"{name}: {k!r} is {keys[k]!r} in keys.json but {v!r} in {table}.csv")
                copy = index[table].get("copy_of", "")
                if copy:
                    u = cells.cell(table, key, column, base=str(Path(copy).parent))
                    if not _equal(v, u):
                        bad.append(f"{name}: {k!r} is {v!r} in {table}.csv but {u!r} in {copy}")
            except KeyError as exc:
                bad.append(f"{name}: {exc}")
    return bad


def render(layout: Layout | None = None) -> str:
    lay = resolve_layout(layout)
    caps = load(lay)
    keys = kz.load(lay.root / sc.TABLES / "keys.json")
    lines = [
        "# NA-14 figure captions",
        "",
        "Rendered from `captions.yaml` by `python -m newsaction.figures.captions`; every number is a "
        "table cell "
        "(`tables/keys.json`); notation is LaTeX math. Figures 1–7 are the paper's; A1–A19 the appendix's. "
        "Section "
        "numbers follow `docs/paper_outline.md`.",
        "",
    ]
    for name, entry in caps.items():
        lines += [
            f"## {name}: {kz.cite(str(entry['title']), keys)}",
            "",
            f"*Section {entry['section']}. Files: `figures/{name}.pdf`, `figures/{name}.png`, data "
            f"`figures/{name}.csv`.*",
            "",
            kz.cite(" ".join(str(entry["caption"]).split()), keys),
            "",
        ]
    return "\n".join(lines)


def write(layout: Layout | None = None) -> Path:
    lay = resolve_layout(layout)
    bad = check(lay)
    if bad:
        raise ValueError(f"{len(bad)} caption problems, e.g. {bad[:5]}")
    path = lay.root / RENDERED
    path.write_text(render(lay), encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    bad = check()
    for b in bad:
        print(b, file=sys.stderr)
    if bad:
        print(f"captions: {len(bad)} problems", file=sys.stderr)
        return 1
    print(write())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
