"""NA-14 S4: table keys, cell formatting and caption citations (PRD NA-14 S4, AC2).

A caption cites a table cell as ``{{table/key/column}}`` (NA-12's convention, ``analysis.tables.cite``), or
``{{table/key/column@spec}}`` with a display format:

- ``f0`` … ``f4``: fixed decimals; ``pct0`` … ``pct2``: the value × 100 with a percent sign; ``int``: a count
  with thousands separators; ``abs2``: the absolute value to 2 decimals; ``signed2``: an explicit sign.

Any other digit in a caption must sit in ``[[...]]``, which marks a label or a design constant (``[[H1]]``,
``[[t+20]]``, ``[[10 bp]]``, ``[[|G| ≥ 3]]``) and is rendered without the brackets; ``bare_digits`` finds
the rest.

Without a spec a cell is rendered by ``fmt``, which equals NA-12's formatter (``tests/test_figures_keys.py``
checks that). It is repeated here so that ``make paper`` never imports ``newsaction.analysis.tables``, whose
imports reach ``newsaction.lock``, ``panel.targets`` and ``panel.reactions``.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

CITE: Final = re.compile(r"\{\{([^{}]+)\}\}")
LITERAL: Final = re.compile(r"\[\[([^\[\]]+)\]\]")
P_COLUMNS: Final = re.compile(r"(^|_)(p|q)(_|$)|p_holm|p_two|p_dk")
COUNTS: Final = re.compile(r"^(n|nobs.*|n_.*|.*_n|df_t|rows)$")
SPECS: Final = ("f0", "f1", "f2", "f3", "f4", "pct0", "pct1", "pct2", "int", "abs2", "signed2")
MINUS: Final = "−"


def fmt(value: Any, column: str) -> str:
    """A cell for LaTeX and captions: p and q to 3 decimals ("<0.001"), counts as integers, other numbers to
    3 decimals (scientific below 0.001)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if math.isinf(value):
            return "∞" if value > 0 else "−∞"
        if P_COLUMNS.search(column):
            return "<0.001" if value < 0.001 else f"{value:.3f}"
        if COUNTS.match(column) and value.is_integer():
            return f"{int(value):,}"
        return f"{value:.3f}" if abs(value) >= 0.001 or value == 0 else f"{value:.2e}"
    return str(value)


def _number(v: Any) -> float:
    if isinstance(v, str) and v in ("inf", "-inf"):
        return float(v)
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise TypeError(f"a format spec needs a number, got {v!r}")
    return float(v)


def _minus(s: str) -> str:
    return s.replace("-", MINUS)


def spec_format(v: Any, spec: str) -> str:
    x = _number(v)
    if math.isinf(x):
        return "∞" if x > 0 else "−∞"
    if spec not in SPECS:
        raise ValueError(f"unknown format spec {spec!r} (known: {', '.join(SPECS)})")
    if spec.startswith("f"):
        return _minus(f"{x:,.{int(spec[1:])}f}")
    if spec.startswith("pct"):
        return _minus(f"{100.0 * x:.{int(spec[3:])}f}%")
    if spec == "int":
        if not x.is_integer():
            raise ValueError(f"{v!r} is not a count")
        return _minus(f"{int(x):,}")
    if spec == "abs2":
        return f"{abs(x):.2f}"
    if spec == "signed2":
        return _minus(f"{x:+.2f}")
    raise ValueError(f"unknown format spec {spec!r} (known: {', '.join(SPECS)})")


def split(ref: str) -> tuple[str, str]:
    """``table/key/column@spec`` → (``table/key/column``, ``spec``)."""
    ref = ref.strip()
    if "@" in ref:
        k, spec = ref.rsplit("@", 1)
        return k, spec
    return ref, ""


def render(ref: str, keys: Mapping[str, Any]) -> str:
    k, spec = split(ref)
    if k not in keys:
        raise KeyError(f"unknown table key {k!r}")
    v = keys[k]
    if spec:
        return spec_format(v, spec)
    if v in ("inf", "-inf"):
        v = float(v)
    return _minus(fmt(v, k.rsplit("/", 1)[1])) if isinstance(v, int | float) else fmt(v, k.rsplit("/", 1)[1])


def cite(text: str, keys: Mapping[str, Any]) -> str:
    """Replace each {{table/key/column[@spec]}} with its formatted value and unwrap each [[literal]]; an
    unknown
    key raises KeyError."""
    return LITERAL.sub(lambda m: m.group(1), CITE.sub(lambda m: render(m.group(1), keys), text))


# Names that hold digits but are not numbers: models, decision points, hypotheses, windows, sections, tables,
# chunks, figures, event-time labels and clock times. A statistic never matches.
IDENTIFIER: Final = re.compile(
    r"(d1-ultra|span-0[12]|drex-v[12]\.\d|gpt-6-luna|bge-small|[ADEFHQSWfx]\d+[a-z]?|H2-C|NA-\d\d|t\d+[a-z]?"
    r"|S-D[012]|e5|Top-100|y[02]|N̂_W[02]|§\d+(\.\d+)*|stage-[12]|MA20|MA50|95%|t\+\d+|C_t(\+\d+)?|\d\d:\d\d|R²|Σz²_cc|5th|95th"
    r"|R2|Ct[+-]\d+|tab\d|fig\d|A\d+)"
)
_TOKEN_SPLIT: Final = re.compile(r"[\s()\[\]{},;·/–]+")
_MATH: Final = re.compile(r"\$([^$]*)\$")
_COMMAND: Final = re.compile(r"\\[A-Za-z]+")


def _math(m: re.Match[str]) -> str:
    """A math segment read as plain tokens: commands, braces, sub- and superscript marks dropped, so that
    ``$y_2$`` reads "y2" and ``$t{+}20$`` "t+20", while a number such as ``$0.5$`` stays a number."""
    return " " + re.sub(r"[{}_^\\,]", "", _COMMAND.sub(" ", m.group(1))) + " "


def bare_digits(text: str) -> list[str]:
    """The tokens of ``text`` that hold a digit outside every citation, literal and name (AC2: none may).
    Math is read too: a number inside ``$…$`` must be cited or a literal like any other."""
    rest = _MATH.sub(_math, LITERAL.sub(" ", CITE.sub(" ", text)))
    out = []
    for tok in _TOKEN_SPLIT.split(rest):
        t = tok.strip(".:\"'").removesuffix("'s").removesuffix("’s")
        if any(ch.isdigit() for ch in t) and not IDENTIFIER.fullmatch(t):
            out.append(t)
    return out


def refs(text: str) -> list[str]:
    return [m.group(1).strip() for m in CITE.finditer(text)]


def load(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return out
