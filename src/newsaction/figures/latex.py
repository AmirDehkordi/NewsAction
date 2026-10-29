"""NA-14 S3: the paper's tables in LaTeX (the operator's revision pass).

    uv run python -m newsaction.figures.latex

The CSV tables (``figures.tables``) are the record; this module only renders them. Every number printed is a
cell of ``tables/keys.json``, cited by (table, key, column), and the cells of each LaTeX table are listed in
``tables/latex.json``, so a test can trace them and check that no main table cites exploratory material.

**The tables.** At most six main tables (T1–T6: the primary hypotheses, the IC by target, the over/under
regression, convergence, explaining moves and the strategies), drawn from several CSVs each, and an appendix
table for every other CSV the paper shows, plus the summary of the pre-registration deviations.

**The style.** booktabs rules only; threeparttable with the notes (definitions, samples, †, ‡ and the
significance convention) under the table; siunitx S columns for decimal alignment and true minus signs; IC
to 3 decimals, t to 2, p to 3 or "<0.001"; standard errors in parentheses and confidence intervals in
brackets; panels with \\cmidrule; human headers with units and the figures' model names; the caption above
the table with a one-line takeaway and a \\label. Tables fit the 6.5-in text width, ``\\small`` or smaller; a
wide appendix table goes landscape, and a long one is a longtable whose notes follow it as a block.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pandas as pd

from newsaction.config import load_splits
from newsaction.figures import keys as kz
from newsaction.figures import sources as sc
from newsaction.figures import tables as tb
from newsaction.paths import Layout, resolve_layout

INDEX: Final = f"{sc.TABLES}/latex.json"
MAIN: Final = "main"
APPENDIX: Final = "appendix"

# --- text ---------------------------------------------------------------------------------------------------

_SPECIAL: Final = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
    "<": r"$<$",
    ">": r"$>$",
    "|": r"$|$",
}
_UNICODE: Final = {
    "§": r"\S{}",
    "²": r"$^2$",
    "⁴": r"$^4$",
    "·": r"$\cdot$",
    "×": r"$\times$",
    "÷": r"$\div$",
    "Δ": r"$\Delta$",
    "Σ": r"$\Sigma$",
    "θ": r"$\theta$",
    "κ": r"$\kappa$",
    "λ": r"$\lambda$",
    "ρ": r"$\rho$",
    "σ": r"$\sigma$",
    "ψ": r"$\psi$",
    "–": "--",
    "—": "---",
    "→": r"$\to$",
    "−": r"$-$",
    "∞": r"$\infty$",
    "≥": r"$\geq$",
    "≤": r"$\leq$",
    "≈": r"$\approx$",
    "±": r"$\pm$",
    "√": r"$\surd$",
    "∩": r"$\cap$",
    "†": r"$^{\dagger}$",
    "‡": r"$^{\ddagger}$",
    "…": r"\ldots{}",
    "’": "'",
    "é": r"\'e",
}
_HAT: Final = "̂"
_MATH: Final = re.compile(r"(\$[^$]*\$)")


def tex(s: str) -> str:
    """Text for LaTeX: math between dollar signs is kept, specials are escaped and the symbols of the tables
    become commands; a character without a rule is refused, so no raw underscore or stray glyph is printed."""
    out: list[str] = []
    for part in _MATH.split(s):
        if part.startswith("$") and part.endswith("$") and len(part) > 1:
            out.append(part)
            continue
        buf: list[str] = []
        for ch in part:
            if ch == _HAT:
                if not buf:
                    raise ValueError(f"a combining hat without a letter in {s!r}")
                buf[-1] = r"$\hat{" + buf[-1] + "}$"
            elif ch in _SPECIAL:
                buf.append(_SPECIAL[ch])
            elif ch in _UNICODE:
                buf.append(_UNICODE[ch])
            elif ord(ch) > 127:
                raise ValueError(f"no LaTeX for {ch!r} (U+{ord(ch):04X}) in {s!r}")
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "".join(out)


# Names as the paper writes them (the figures' names; † and ‡ stay on the names).
MODEL: Final = {
    "laya_fin": "Laya-Fin",
    "anchor": "anchor",
    "laya_zs": "Laya zero-shot",
    "d1_ultra": "d1-ultra",
    "span_02": r"span-02$^{\ddagger}$",
    "drex_v2": "drex-v2.0",
    "sentiment": r"vendor sentiment$^{\dagger}$",
    "tags_gbm": r"tags-GBM$^{\dagger}$",
    "embed_ridge": "bge-ridge",
    "llm": "LLM baseline",
    "price_only": "price-only",
    "price_only_d2": r"price-only (D2, with $y_2$)",
    "gap_fade": "gap fade (price-only)",
    "vendor_sentiment": r"vendor sentiment$^{\dagger}$",
    "liquid/d1-ultra": "d1-ultra",
    "liquid:d1-ultra": "d1-ultra",
    "respan/span-02": r"span-02$^{\ddagger}$",
    "respan:span-02": r"span-02$^{\ddagger}$",
    "nace-ai/drex-v2.0": "drex-v2.0",
    "nace-ai:drex-v2.0": "drex-v2.0",
    "local/laya-typed-decisions": "Laya zero-shot",
    "local:laya-typed-decisions": "Laya zero-shot",
    "local/laya-base": "Laya base (local)",
    "local:laya-base": "Laya base (local)",
    "openai/gpt-6-luna-decisions": "gpt-6-luna",  # as the figures name it
}
RUNG: Final = {
    "O_t": r"$O_t$",
    "10:00": "10:00",
    "C_t": r"$C_t$",
    "C_t+1": r"$t{+}1$",
    "C_t+2": r"$t{+}2$",
    "C_t+5": r"$t{+}5$",
    "C_t+10": r"$t{+}10$",
    "C_t+20": r"$t{+}20$",
    "close_t": r"$C_t$",
    "close_t+1": r"$t{+}1$",
    "close_t+5": r"$t{+}5$",
    "close_t+20": r"$t{+}20$",
    "plateau": r"plateau, $t{+}16$ to $t{+}20$",
    "increase": r"increase, $O_t$ to $t{+}20$",
    "half_life": "half-life",
}
TIER: Final = {"top100": "Top 100", "mid": "101 to 250", "rest": "251 to 500", "all": "all tiers"}
WORDS: Final = {
    "z_cc": "$z_{cc}$",
    "z_on": "$z_{on}$",
    "z_id": "$z_{id}$",
    "n_hat": r"$\hat N$",
    "n_tilde": r"$\tilde N$",
    "u": "$U$",
    "j": "$J$",
    "c": "$C$",
    "rg": "RG",
    "gap": "gap",
    "y2": "$y_2$",
    "val_a": "val-A",
    "val_b": "val-B",
    "test": "test",
    "validation": "validation",
    "D0": "D0",
    "D1": "D1",
    "D2": "D2",
    "r2": "$R^2$",
    "ic": "IC",
    "e5": "$e_5$",
    "raw": "raw",
    "placebo": "placebo-adjusted",
    "True": "yes",
    "False": "no",
    # cuts, steps and variants of the NA-12 tables, as the figures name them
    "event_days": "event days",
    "non_event_days": "non-event days",
    "ex_ante": "ex-ante news",
    "ex_post": "same-day news",
    "explanation": "explanation (reads the move)",
    "market+sector": "market and sector (Roll)",
    "tier_top100": "Top 100",
    "tier_mid": "101 to 250",
    "tier_rest": "251 to 500",
    "abs_g_gap_d1": r"$|G|$, D1 gap",
    "abs_g_gap_d2": r"$|G|$, D2 gap",
    "[0, 1)": "$[0, 1)$",
    "[1, 2)": "$[1, 2)$",
    "[2, inf)": r"$[2, \infty)$",
    "D2, |G| in [0, 1)": r"D2, $|G| \in [0, 1)$",
    "D2, |G| in [1, 2)": r"D2, $|G| \in [1, 2)$",
    "D2, |G| in [2, inf)": r"D2, $|G| \in [2, \infty)$",
    "|z_cc| >= 1": r"$|z_{cc}| \geq 1$",
    "ladder_clean": "ladder, clean windows",
    "ladder_h10": r"ladder, $h^{*} = t{+}10$",
    "ladder_plateau": "ladder",  # its rung says "plateau"
    "O_t → C_t+10": r"$O_t$ to $t{+}10$",
    "O_t → C_t+20": r"$O_t$ to $t{+}20$",
    "H2C_kappa_hstar": r"H2-C, $\kappa$ at $h^{*}$",
    "H2C_kappa_increase": r"H2-C, $\kappa$ increase",
    "H2C_lambda_t5": r"H2-C, $\lambda_{t+5}$",
    "H2C_tracking_naive": "H2-C, naive tracking",
    "h2_d2": "H2 at D2",
    # the robustness variants (t16), as Figure A5 names them
    "dollar_volume_tiers": "dollar-volume tiers",
    "exclude_date_only_hour": "no date-only or hour-stamped article",
    "exclude_half_days": "no half days",
    "non_overlapping": "non-overlapping events",
    "exclude_delisting_flag": "no delisting flag",
    "without_price_move_text": "without price-move text",
    "timing_before_04:00": "latest article before 04:00",
    "timing_04:00_08:00": "latest article 04:00 to 08:00",
    "timing_08:00_09:15": "latest article 08:00 to 09:15",
    "gated_s_d1": "gated S-D1",
    "summary_text_variant": "summary text",
    "unmasked_trained_models": "unmasked, trained models",
    "vendor_tags_in_text": "vendor tags in the text",
    # the vendor's event types (t12) where underscores alone would misread
    "ma_deal": "M\\&A deal",
    "deal_ma_partnership": "deal, M\\&A, partnership",
    # t12's mechanism-cut labels: a0_ is Call A on the pre-open news (W0), a2_ on the same-day news (W2)
    # (NA-12 ``analysis.frames.SOURCES``)
    "vendor_event_type": "vendor event type",
    "vendor_quantified": "vendor quantified flag",
    "a0_label_event_type": "own event type (Call A, pre-open news)",
    "a2_label_event_type": "own event type (Call A, same-day news)",
    "a0_label_quantified": "own quantified flag (Call A, pre-open news)",
    "a2_label_quantified": "own quantified flag (Call A, same-day news)",
    "horizon validity: Spearman(H, share of the t+20 move by C_t)": (
        r"horizon validity: Spearman($H$, share of the $t{+}20$ move by $C_t$)"
    ),
    "H4 width: ΔR² of U_unc and P(no_material_effect)": (
        r"H4 width: $\Delta R^2$ of the uncertainty score and $P$(no material effect)"
    ),
    # t5's cuts
    "usual_coverage_low": "low usual coverage",
}
# d1-ultra's move reasons (Q17), as Figure A11 names them
REASON: Final = {
    "analyst_action": "analyst action",
    "capital_returns_financing": "capital returns, financing",
    "deal_ma_partnership": "deal, M\\&A, partnership",
    "earnings_results": "earnings results",
    "guidance_outlook": "guidance, outlook",
    "legal_regulatory": "legal, regulatory",
    "management_governance": "management, governance",
    "market_or_sector_move": "market or sector move",
    "no_identifiable_news": "no identifiable news",
    "product_operations": "product, operations",
    "sector_or_macro": "sector or macro",
}
# the moving-average cross groups, as Figure A15 names them
MA_GROUP: Final = {
    "all": "all crosses",
    "none": "no news",
    "agree_laya_fin": "agree, Laya-Fin",
    "disagree_laya_fin": "disagree, Laya-Fin",
    "agree_d1_ultra": "agree, d1-ultra",
    "disagree_d1_ultra": "disagree, d1-ultra",
}
# the D0 cutoff variants, "w0_cutoff_<HH:MM>" with "_approx" when approximated (no clock literal in src/)
_CUTOFF: Final = re.compile(r"^w0_cutoff_(\d\d:\d\d)(_approx)?$")
_ABLATION: Final = re.compile(r"^b2_(no_news|shuffled): IC of b2_(c|j|n_hat) with y2 \((real|ablated)\)$")


def word(v: Any) -> str:
    """A categorical value as the paper writes it: a model, a rung, a tier, a symbol, a cut ("tier:mid",
    "event_type:…"), Call B's ablations, or the value with its underscores read as spaces (never a raw
    key)."""
    s = str(v)
    for table in (MODEL, RUNG, TIER, WORDS):
        if s in table:
            return table[s]
    head, sep, rest = s.partition(":")
    if sep and head == "tier" and rest in TIER:
        return TIER[rest]
    if sep and head == "event_type":
        return REASON.get(rest, tex(rest.replace("_", " ")))
    c = _CUTOFF.match(s)
    if c:
        return f"{c.group(1)} cutoff" + (" (approximated)" if c.group(2) else "")
    m = _ABLATION.match(s)
    if m:
        ablation = "news removed" if m.group(1) == "no_news" else "shuffled news"
        return f"Call B, {ablation}: {WORDS[m.group(2)]} ({m.group(3)})"
    return tex(s.replace("_", " "))


# --- cells --------------------------------------------------------------------------------------------------


# "<" before a number in an S column is text set against it (siunitx's comparator would leave a gap before an
# integer field wider than the number's), so the number stays on the decimal column.
LT: Final = "{$<$}"
DASH: Final = "---"


@dataclass(frozen=True)
class Num:
    """A keyed cell: ``fmt`` is "f0" … "f4", "p" (3 decimals or "<0.001"), "int", "pct0" … "pct2" (× 100),
    "se3" / "se4" (in parentheses), "t2" (a t statistic) or "bp1" (basis points, 1 decimal); a text cell is a
    value as the paper writes it, "text" (prose, as written) or "md" (an ISO date as month-day)."""

    table: str
    key: str
    column: str
    fmt: str = "f3"


@dataclass(frozen=True)
class CI:
    """A confidence interval "[lo, hi]" from two keyed cells."""

    table: str
    key: str
    lo: str
    hi: str
    decimals: int = 3


@dataclass(frozen=True)
class Txt:
    text: str  # LaTeX


Cell = Num | CI | Txt | None


@dataclass(frozen=True)
class Col:
    head: str  # LaTeX
    kind: str = "S"  # "S" (numbers), "l", "c", "r" or a p{} spec


@dataclass(frozen=True)
class Panel:
    title: str  # LaTeX; "" for none
    rows: tuple[tuple[str, tuple[Cell, ...]], ...]


@dataclass(frozen=True)
class Table:
    name: str
    label: str
    section: str  # MAIN or APPENDIX
    caption: str  # LaTeX: the takeaway first
    columns: tuple[Col, ...]  # the first is the row label
    panels: tuple[Panel, ...]
    notes: tuple[str, ...] = ()
    head: tuple[str, ...] = ()  # LaTeX rows above the column heads (spanners with their \cmidrule)
    size: str = r"\small"
    long: bool = False
    landscape: bool = False
    sources: tuple[str, ...] = ()
    colsep: str = ""  # a \tabcolsep for a dense table


class Cells:
    """The keyed cells (``keys.json``), formatted for LaTeX, with every cited key recorded."""

    def __init__(self, keys: Mapping[str, Any]) -> None:
        self.keys = keys
        self.cited: list[str] = []

    def value(self, table: str, key: str, column: str) -> Any:
        k = f"{table}/{key}/{column}"
        if k not in self.keys:
            return None
        self.cited.append(k)
        v = self.keys[k]
        return float(v) if v in ("inf", "-inf") else v

    def num(self, c: Num) -> str:
        v = self.value(c.table, c.key, c.column)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "{" + DASH + "}"
        if isinstance(v, str):
            if c.fmt == "md":  # an ISO date as month-day
                return "{" + v[5:] + "}"
            return "{" + (tex(v) if c.fmt == "text" else word(v)) + "}"
        if isinstance(v, bool):
            return "{" + ("yes" if v else "no") + "}"
        x = float(v)
        if math.isinf(x):
            return "{$\\infty$}" if x > 0 else "{$-\\infty$}"
        f = c.fmt
        if f == "p":
            return f"{LT}0.001" if x < 0.001 else f"{x:.3f}"
        if f == "int":
            return f"{round(x):d}"
        if f.startswith("pct"):
            return f"{100 * x:.{int(f[3:])}f}"
        if f.startswith("se"):
            return "{(}" + f"{x:.{int(f[2:])}f}" + "{)}"
        if f == "t2":
            return f"{x:.2f}"
        if f == "bp1":
            return f"{x:.1f}"
        if f.startswith("f"):
            return f"{x:.{int(f[1:])}f}"
        raise ValueError(f"unknown format {f!r}")

    def ci(self, c: CI) -> str:
        lo, hi = self.value(c.table, c.key, c.lo), self.value(c.table, c.key, c.hi)
        if lo is None or hi is None or any(isinstance(v, float) and math.isnan(v) for v in (lo, hi)):
            return DASH

        def m(v: Any) -> str:
            return f"${float(v):.{c.decimals}f}$"

        return f"[{m(lo)}, {m(hi)}]"

    def render(self, cell: Cell, kind: str) -> str:
        """A cell as LaTeX; an empty cell (``None``) shows a dash, whose meaning the table's notes give."""
        if cell is None:
            return "{" + DASH + "}" if kind == "S" else DASH
        if isinstance(cell, Txt):
            return "{" + cell.text + "}" if kind == "S" else cell.text
        if isinstance(cell, CI):
            s = self.ci(cell)
            return "{" + s + "}" if kind == "S" else s
        s = self.num(cell)
        if kind == "S":
            return s
        if s.startswith(LT):
            return f"$<{s[len(LT) :]}$"
        return s.strip("{}") if s.startswith("{") else f"${s.replace('{(}', '(').replace('{)}', ')')}$"


_NUMBER: Final = re.compile(r"^(-)?(\d*)(?:\.(\d+))?$")


def table_format(cells: Iterable[str]) -> str:
    """siunitx's table-format for an S column from its rendered numbers (text cells in braces are skipped);
    the text set against a number, "(" … ")" around a standard error or "<" before a bound, gets its
    space."""
    neg = False
    ints = decs = 0
    paren = lt = False
    for c in cells:
        if c.startswith("{(}"):
            paren = True
            c = c[3:-3]
        elif c.startswith(LT):
            lt = True
            c = c[len(LT) :]
        elif c.startswith("{") or not c:
            continue
        m = _NUMBER.match(c)
        if m is None:
            raise ValueError(f"not a number for an S column: {c!r}")
        neg |= bool(m.group(1))
        ints = max(ints, len(m.group(2) or "0"))
        decs = max(decs, len(m.group(3) or ""))
    if paren and lt:
        raise ValueError("an S column holds both standard errors and bounds")
    spec = f"{'-' if neg else ''}{max(ints, 1)}.{decs}"
    extra = ", table-space-text-pre=(, table-space-text-post=)" if paren else ""
    extra += f", table-space-text-pre={LT}" if lt else ""
    return f"S[table-format={spec}{extra}]"


def cite(text: str, cells: Cells) -> str:
    """Replace each {{table/key/column@spec}} of a caption or note with its cell (``keys.render``),
    recorded."""

    def sub(m: re.Match[str]) -> str:
        ref = m.group(1).strip()
        cells.cited.append(kz.split(ref)[0])
        return tex(kz.render(ref, cells.keys))

    return kz.CITE.sub(sub, text)


def render(t: Table, keys: Mapping[str, Any]) -> tuple[str, list[str]]:
    """The LaTeX of a table and the keys it cites."""
    cells = Cells(keys)
    t = Table(
        **{**t.__dict__, "caption": cite(t.caption, cells), "notes": tuple(cite(n, cells) for n in t.notes)}
    )
    body: list[list[str]] = []
    blocks: list[tuple[str, list[str]]] = []  # each panel's title and its LaTeX rows (the title row first)
    ncol = len(t.columns)
    for p in t.panels:
        block = [rf"\multicolumn{{{ncol}}}{{@{{}}l}}{{\textit{{{p.title}}}}} \\"] if p.title else []
        seen: set[str] = set()
        for label, cs in p.rows:
            if len(cs) != ncol - 1:
                raise ValueError(f"{t.name}: row {label!r} has {len(cs)} cells for {ncol - 1} columns")
            if label and label in seen:  # an unlabelled row continues the one above (its SE or t)
                raise ValueError(f"{t.name}: the row label {label!r} repeats within a panel")
            seen.add(label)
            line = [label] + [cells.render(c, col.kind) for c, col in zip(cs, t.columns[1:], strict=True)]
            body.append(line)
            block.append(" & ".join(line) + r" \\")
        blocks.append((p.title, block))
    rows: list[str] = []
    for title, block in blocks:
        if title and rows:
            rows.append(r"\addlinespace")
        rows += block
    if any(c in ("{" + DASH + "}", DASH) for line in body for c in line[1:]) and not any(
        DASH in n for n in t.notes
    ):
        raise ValueError(f"{t.name}: a cell shows {DASH} but no note says what it means")
    shown = "\n".join([*rows, *t.head, *(c.head for c in t.columns)])
    for mark in (r"\dagger", r"\ddagger"):
        used = re.compile(re.escape(mark) + r"(?![A-Za-z])")
        if used.search(shown) and not any(used.search(n) for n in t.notes):
            raise ValueError(f"{t.name}: the table shows ${mark}$ but no note says what it marks")
    specs = []
    for j, col in enumerate(t.columns):
        if col.kind == "S":
            specs.append(table_format(r[j] for r in body))
        else:
            specs.append(col.kind)
    spec = "@{}" + "".join(specs) + "@{}"
    head = " & ".join(("{" + c.head + "}") if c.kind == "S" else c.head for c in t.columns) + r" \\"
    notes = [f"\\item {n}" for n in t.notes]
    lines = [f"% {t.name}: {t.label} (NA-14 figures.latex, from {', '.join(t.sources)})"]
    if t.landscape:
        lines.append(r"\begin{landscape}")
    if t.long:
        # A long table breaks across pages; its notes follow it as a block (threeparttablex's notes overflow a
        # longtable's foot), set like the tablenotes of the floats. With titled panels it is one longtable per
        # panel, the caption on the first, so a page that continues a panel names it.
        chunks = blocks if len(blocks) > 1 and all(title for title, _ in blocks) else [("", rows)]
        lines += [r"\begingroup", t.size, *([t.colsep] if t.colsep else [])]
        for i, (title, chunk) in enumerate(chunks):
            cont = (
                rf"\multicolumn{{{ncol}}}{{@{{}}l}}{{\textit{{Table \ref{{{t.label}}}, continued"
                + (f" ({title})" if title else "")
                + r"}} \\"
            )
            lines += [
                rf"\begin{{longtable}}{{{spec}}}",
                rf"\caption{{{t.caption}}}\label{{{t.label}}} \\" if i == 0 else cont,
                r"\toprule",
                *t.head,
                head,
                r"\midrule",
                r"\endfirsthead",
                cont,
                r"\toprule",
                *t.head,
                head,
                r"\midrule",
                r"\endhead",
                r"\midrule",
                rf"\multicolumn{{{ncol}}}{{r@{{}}}}{{\textit{{continued on the next page}}}} \\",
                r"\endfoot",
                r"\bottomrule",
                r"\endlastfoot",
                *chunk,
                r"\end{longtable}",
            ]
        lines += [
            r"\endgroup",
            *(
                [
                    r"\vspace{-0.5\baselineskip}",
                    r"{\footnotesize\raggedright",
                    *(f"{n}\\par" for n in t.notes),
                    "}",
                ]
                if t.notes
                else []
            ),
        ]
    else:
        lines += [
            r"\begin{table}[htbp]",
            r"\centering",
            t.size,
            *([t.colsep] if t.colsep else []),
            r"\begin{threeparttable}",
            rf"\caption{{{t.caption}}}\label{{{t.label}}}",
            rf"\begin{{tabular}}{{{spec}}}",
            r"\toprule",
            *t.head,
            head,
            r"\midrule",
            *rows,
            r"\bottomrule",
            r"\end{tabular}",
            *([r"\begin{tablenotes}[flushleft]\footnotesize", *notes, r"\end{tablenotes}"] if notes else []),
            r"\end{threeparttable}",
            r"\end{table}",
        ]
    if t.landscape:
        lines.append(r"\end{landscape}")
    return "\n".join(lines) + "\n", sorted(set(cells.cited))


# --- shared notes -------------------------------------------------------------------------------------------


def period() -> str:
    """The test period as the tables state it (from configs/splits.yaml; src holds no test-period date)."""
    s = load_splits().splits["test"]
    return f"{s.start.isoformat()} to {s.end.isoformat()}"


NOTE_VENDOR: Final = (
    r"$^{\dagger}$Vendor-label baseline (vendor sentiment, tags-GBM): the labels were produced "
    r"retrospectively, "
    "so its IC is a possibly look-ahead-contaminated upper bound, not the benchmark; the clean benchmarks "
    "are "
    "bge-ridge, price-only, the LLM baseline and the random-signal placebo."
)
# The vendor-label note of the strategy tables, whose † rows are books, not ICs.
NOTE_VENDOR_BOOKS: Final = (
    r"$^{\dagger}$Vendor sentiment: its labels were produced retrospectively, so its books are a possibly "
    "look-ahead-contaminated upper bound, not a benchmark; the clean benchmarks are the price-only gap fade "
    "and the random-signal placebo."
)
NOTE_SPAN: Final = (
    r"$^{\ddagger}$span-02: the S5 canary fired a STOP after the freeze; the operator chose to proceed "
    r"(PREREG "
    r"\S15, post-freeze NA-11 row)."
)
NOTE_ANCHOR: Final = (
    "The anchor's readings are uninformative (near-constant outputs after one epoch); its rows are reported, "
    "not read as nulls."
)
NOTE_API: Final = (
    r"The API models fail the \S8.3 contamination screens, so their results are model-specific (\S1.3)."
)
NOTE_EXPLORATORY: Final = (
    "Exploratory (post hoc): requested after unblinding; no hypothesis, outside every family, no claim."
)
NOTE_STARS: Final = "Significance: no stars are used; $p$ is one-sided unless stated."
NOTE_DASH: Final = (
    "---: the source table has no value for the row; the statistic does not apply to it or was not computed."
)
# What a dash means where the reason is one and plain (the other appendix tables carry NOTE_DASH).
DASH_NOTES: Final = {
    "t2_h2_over_under": "---: not estimated for that row (at D0 there is no $G$, so no $c$).",
    "t7_gap_closure": "---: the half-life is a rung, not an estimate, so it has no standard error, $p$, "
    "$\\psi_h$ or event count.",
    "t13_shapley": "---: a total has no share.",
    "t18_probes_val_a": "---: the probe was not run for that model.",
    "t21_release_dates": "---: the anchor's checkpoint is dated by month only, before the sample, so it has "
    "no day count.",
    "t22_spend": "---: no cap.",
    "t25_ma_cross": "---: the groups have mean returns and the tradable fades Sharpe ratios.",
}


# --- the main tables ----------------------------------------------------------------------------------------

T1: Final = "t1_primary"
T1B: Final = "t1b_primary_by_model"
T2: Final = "t2_h2_over_under"
T3: Final = "t3_ic"
T4: Final = "t4_secondary"
T6: Final = "t6_convergence_ladder"
T7: Final = "t7_gap_closure"
T10: Final = "t10_explanation_ladder"
T14: Final = "t14_model_comparison"
T20: Final = "t20_strategies"
T32: Final = "t32_val_b_ic"
T33: Final = "t33_placebo_sharpe"
T35: Final = "t35_break_even"


def main_primary() -> Table:
    tests = (
        ("H1", r"$\mathrm{IC}(\hat N, z_{on}) - \mathrm{IC}(\hat N, z_{id}) > 0$", 3),
        ("H1b", r"$\mathrm{IC}(\hat N, z_{id}) > 0$", 3),
        ("H2", r"$b > 0$ and $c < 0$ at D2", 3),
        ("H3", r"$\Delta\mathrm{IC}$ of $J$ for $y_2 > 0$", 4),
        ("H4", r"$\Delta R^2$ of the news for $|z_{cc}| > 0$", 4),
    )
    rows = tuple(
        (
            h,
            (
                Num(T1, h, "primary_estimate", f"f{d}"),
                CI(T1, h, "primary_ci_low", "primary_ci_high", d),
                Num(T1, h, "primary_p", "p"),
                Num(T1, h, "primary_p_holm", "p"),
                Num(T1, h, "anchor_estimate", f"f{d}"),
                Num(T1, h, "anchor_p", "p"),
                Num(T1, h, "verdict"),
            ),
        )
        for h, test, d in tests
    )
    return Table(
        "tab1_primary",
        "tab:primary",
        MAIN,
        "Primary hypotheses on the test period: none is supported for the primary instrument, Laya-Fin.",
        (
            Col("Hypothesis", "l"),
            Col("Estimate"),
            Col(r"95\% CI", "c"),
            Col("$p$"),
            Col("Holm $p$"),
            Col("Estimate"),
            Col("$p$"),
            Col(r"Verdict (\S1.3)", "l"),
        ),
        (Panel("", rows),),
        (
            "The tests: " + "; ".join(f"{h}, {test}" for h, test, _ in tests) + ".",
            f"Test period {period()}, events outside the embargo. Estimates in each hypothesis' direction; "
            "$p$ one-sided; 95\\% CIs and $p$ from a stationary block bootstrap over sessions (block 5, "
            "10,000 draws); Holm over H1, H1b, H2, H3 and H4 at 0.05.",
            "H2: the estimate is $\\min(b, -c)$ and $p = \\max(p_b, p_c)$ (both must hold), so it has no "
            "single interval (---); $b$ and $c$ with their standard errors are in "
            "Table~\\ref{tab:over-under}. Estimates and CIs to three decimals, H3's and H4's to four, since "
            "those increments are an order smaller.",
            "Verdict (\\S1.3): general if Laya-Fin's Holm $p < 0.05$ with the predicted sign and the "
            "anchor's "
            "own $p < 0.05$ with the same sign; model-specific if only Laya-Fin's holds; otherwise not "
            "supported. " + NOTE_ANCHOR + " Its $p$ is its own, not Holm-adjusted.",
            NOTE_STARS,
        ),
        (
            r" & \multicolumn{4}{c}{Laya-Fin (primary)} & \multicolumn{2}{c}{Anchor} & \\",
            r"\cmidrule(lr){2-5}\cmidrule(lr){6-7}",
        ),
        sources=(f"{sc.NA12_TAB}/{T1}.csv",),
    )


IC_MODELS: Final = (
    ("Trained and zero-shot", ("laya_fin", "anchor", "laya_zs")),
    (r"API models (model-specific)", ("d1_ultra", "span_02", "drex_v2")),
)


def main_ic() -> Table:
    panels = []
    for title, models in IC_MODELS:
        rows = []
        for m in models:
            val_on = (
                (Num(T32, m, "ic_z_on"), Num(T32, m, "ic_z_id"))
                if m in ("laya_fin", "anchor", "laya_zs")
                else (None, None)
            )
            val_on_t = (
                (Num(T32, m, "ic_z_on_t", "se2"), Num(T32, m, "ic_z_id_t", "se2"))
                if val_on[0]
                else (None, None)
            )
            rows.append(
                (
                    MODEL[m],
                    (
                        Num(T14, m, "ic_val_b"),
                        *val_on,
                        Num(T3, f"{m}:z_cc", "ic"),
                        Num(T3, f"{m}:z_on", "ic"),
                        Num(T3, f"{m}:z_id", "ic"),
                    ),
                )
            )
            rows.append(
                (
                    "",
                    (
                        Num(T14, m, "ic_val_b_t", "se2"),
                        *val_on_t,
                        Num(T3, f"{m}:z_cc", "ic_t", "se2"),
                        Num(T3, f"{m}:z_on", "ic_t", "se2"),
                        Num(T3, f"{m}:z_id", "ic_t", "se2"),
                    ),
                )
            )
        panels.append(Panel(title, tuple(rows)))
    return Table(
        "tab2_ic_by_target",
        "tab:ic-target",
        MAIN,
        "Daily IC by target: the API models' signal is in the overnight move, and no model predicts the move "
        "after the open.",
        (
            Col("Model", "l"),
            Col("$z_{cc}$"),
            Col("$z_{on}$"),
            Col("$z_{id}$"),
            Col("$z_{cc}$"),
            Col("$z_{on}$"),
            Col("$z_{id}$"),
        ),
        tuple(panels),
        (
            r"Mean daily Spearman IC of the pre-open news reading $\hat N$ with the close-to-close move "
            r"$z_{cc}$, "
            r"the overnight move $z_{on}$ (previous close to open) and the move after the open $z_{id}$ "
            r"(open to "
            "close), each in typical daily moves, to three decimals; Newey--West $t$ in parentheses, to two; "
            "D0 events outside the "
            "embargo "
            f"(val-B 2025-10-01 to 2025-12-31; test {period()}).",
            "Val-B ICs with $z_{on}$ and $z_{id}$ come from NA-11's run of the frozen spec on val-B before "
            "the "
            "freeze, which covered the trained and zero-shot Laya models only (---: not computed).",
            NOTE_ANCHOR + " " + NOTE_API + " " + NOTE_SPAN,
        ),
        (
            r" & \multicolumn{3}{c}{Val-B} & \multicolumn{3}{c}{Test} \\",
            r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
        ),
        sources=(f"{sc.NA12_TAB}/{T3}.csv", f"{sc.NA12_TAB}/{T14}.csv", f"{sc.TABLES}/{T32}.csv"),
    )


def main_over_under() -> Table:
    panels = []
    for m, title in (
        ("laya_fin", "Laya-Fin (primary)"),
        ("anchor", "Anchor (uninformative)"),
        ("d1_ultra", "d1-ultra (model-specific)"),
    ):
        rows = []
        for point, what in (("D2", "D2, close (H2)"), ("D1", "D1, 10:00"), ("D0", "D0, open")):
            k = f"{m}:{point}"
            rows.append(
                (
                    what,
                    (
                        Num(T2, k, "b"),
                        Num(T2, k, "b_se", "se3"),
                        Num(T2, k, "b_p", "p"),
                        Num(T2, k, "c"),
                        Num(T2, k, "c_se", "se3"),
                        Num(T2, k, "c_p", "p"),
                        Num(T2, k, "nobs", "int"),
                    ),
                )
            )
        panels.append(Panel(title, tuple(rows)))
    return Table(
        "tab3_over_under",
        "tab:over-under",
        MAIN,
        "The over/under regression: the reversal coefficient $c$ has the predicted sign but is not "
        "significant, "
        "and the news coefficient $b$ is not positive at the close.",
        (
            Col("Decision point", "l"),
            Col("$b$"),
            Col("SE"),
            Col("$p_b$"),
            Col("$c$"),
            Col("SE"),
            Col("$p_c$"),
            Col("Events"),
        ),
        tuple(panels),
        (
            r"$y = a + b\,\hat N + c\,G$ with day $\times$ tier fixed effects, on the test period: at D2 $y "
            r"= y_2$ "
            r"(next open to $t{+}5$), $\hat N$ from the day's news and $G$ the day's move; at D1 the move "
            r"after "
            r"10:00 on $\hat N$ from the pre-open news and the move to 10:00; at D0 $y = z_{id}$ and there "
            r"is no $G$, so no $c$ (---). "
            "Two-way clustered (session, firm) standard errors in parentheses; $p_b$ tests $b > 0$ and "
            "$p_c$ tests "
            "$c < 0$, one-sided. H2 is the D2 row of Laya-Fin.",
            NOTE_ANCHOR + " " + NOTE_API,
            NOTE_STARS,
        ),
        sources=(f"{sc.NA12_TAB}/{T2}.csv",),
    )


KAPPA_RUNGS: Final = ("O_t", "10:00", "C_t", "C_t+1", "C_t+2", "C_t+5", "C_t+10", "C_t+20")
LAMBDA_RUNGS: Final = {"D2": ("C_t+1", "C_t+5", "C_t+20"), "D1": ("C_t", "C_t+1", "C_t+5", "C_t+20")}


def main_convergence() -> Table:
    models = (("laya_fin", "Laya-Fin"), ("d1_ultra", "d1-ultra"), ("anchor", "anchor"))
    a = []
    for m, name in models:
        a.append((name, (*(Num(T6, f"{m}:ladder:{r}", "kappa", "f2") for r in KAPPA_RUNGS), None)))
        a.append(("", (*(Num(T6, f"{m}:ladder:{r}", "kappa_se", "se2") for r in KAPPA_RUNGS), None)))
    b = []
    for m, name in models:
        for point, rungs in LAMBDA_RUNGS.items():
            vals = tuple(
                Num(T7, f"{m}:{point}:all:{r}", "lambda", "f3") if r in rungs else None for r in KAPPA_RUNGS
            )
            ses = tuple(
                Num(T7, f"{m}:{point}:all:{r}", "lambda_se", "se3") if r in rungs else None
                for r in KAPPA_RUNGS
            )
            b.append((f"{name}, {point}", (*vals, Num(T7, f"{m}:{point}:all:half_life", "lambda"))))
            b.append(("", (*ses, None)))
    return Table(
        "tab4_convergence",
        "tab:convergence",
        MAIN,
        r"Convergence to the news-implied value $V$: prices reach part of $V$ on day $t$, then partly fade; "
        r"the "
        r"gap's half-life is not reached within $t{+}20$.",
        (Col("", "l"), *(Col(RUNG[r]) for r in KAPPA_RUNGS), Col("Half-life")),
        (
            Panel(r"Panel A: convergence ladder $\kappa_h$ (D0 events)", tuple(a)),
            Panel(r"Panel B: gap closure $\lambda_h$ and the half-life", tuple(b)),
        ),
        (
            r"Panel A: $\kappa_h$ is the slope of $\mathrm{CAR}^{\mathrm{lvl}}_h$, the abnormal return from "
            r"the "
            r"previous close to rung $h$ in typical daily moves, on $V$ with day $\times$ tier fixed "
            r"effects; "
            r"$\kappa_h = 1$ is full convergence. Panel B: $\lambda_h$ is the share of the gap $U = V - "
            r"G^{\mathrm{lvl}}$ closed by rung $h$, at D2 (from the close) and D1 (from 10:00); the "
            r"half-life is "
            r"the first rung with $\lambda_h \geq 0.5$ ($\infty$: not reached within $t{+}20$). Two-way "
            r"clustered "
            r"standard errors in parentheses; $t{+}k$ is the close of session $t+k$. ---: not estimated; "
            r"$\lambda_h$ is reported at $t{+}1$, $t{+}5$ and $t{+}20$ from D2 and also at $C_t$ from D1, "
            r"and the half-life belongs to $\lambda_h$ alone. $\kappa_h$ to two decimals, $\lambda_h$ to "
            r"three, since it is an order smaller.",
            NOTE_ANCHOR + " " + NOTE_API,
        ),
        size=r"\small",
        colsep=r"\setlength{\tabcolsep}{4pt}",
        sources=(f"{sc.NA12_TAB}/{T6}.csv", f"{sc.NA12_TAB}/{T7}.csv"),
    )


def main_explaining() -> Table:
    models = ("laya_fin", "d1_ultra", "anchor")
    steps = (
        ("ex_ante", "+ ex-ante news (D0)"),
        ("ex_post", "+ same-day news (Call A)"),
        ("explanation", "+ explanation (Call B reads the move)"),
    )
    rows = []
    for step, label in steps:
        rows.append(
            (
                label,
                tuple(
                    c
                    for m in models
                    for c in (
                        Num(T10, f"{m}:all:{step}", "r2", "pct2")
                        if (m == "d1_ultra" or step != "explanation")
                        else None,
                        Num(T10, f"{m}:all:{step}", "increment", "pct2")
                        if (m == "d1_ultra" or step != "explanation")
                        else None,
                    )
                ),
            )
        )
    rows.append(
        (
            "share knowable before the open (\\%)",
            tuple(c for m in models for c in (Num(T10, f"{m}:all:knowable", "r2", "pct2"), None)),
        )
    )
    h5 = []
    for what, col, fmt in (
        ("H5: same-day news step, $R^2 > 0$", "estimate", "pct2"),
        ("one-sided $p$", "p", "p"),
        ("BH $q$", "q", "p"),
    ):
        h5.append((what, tuple(c for m in models for c in (Num(T4, f"{m}:H5", col, fmt), None))))
    return Table(
        "tab5_explaining_moves",
        "tab:explaining",
        MAIN,
        "Explaining realized moves: same-day news explains a small share of the stock-specific variance (H5, "
        "supported for Laya-Fin); reading the move explains far more.",
        (Col("Step", "l"), *(Col(h) for m in models for h in (r"$R^2$", r"$\Delta R^2$"))),
        (
            Panel(r"Panel A: the explanation ladder, out-of-sample $R^2$ of $z_{cc}$ (\%)", tuple(rows)),
            Panel("Panel B: the secondary test H5", tuple(h5)),
        ),
        (
            r"Covered member-days of the test period; out-of-sample $R^2$ of the stock-specific move "
            r"$z_{cc}$ "
            r"(the market and sector removed) by cumulative step, in \%; $\Delta R^2$ is the step's "
            r"increment. "
            r"Roll's first step, the market and the sector, explains "
            r"{{t10_explanation_ladder/roll_r2/r2@pct1}} of "
            r"total daily variance, a different base. The explanation step needs "
            r"Call B's explanation answer, which only d1-ultra gives; it reads the realized move, so it is "
            r"not a "
            r"prediction. H5 is the only secondary test that survives Benjamini--Hochberg ($q$ 0.10) for "
            r"Laya-Fin. ---: not applicable (the first step has no increment; only d1-ultra answers the "
            r"explanation question; the share and Panel B have one value per model). $R^2$, $\Delta R^2$ and "
            r"the share in \% to two decimals; $p$ and $q$ to three.",
            NOTE_ANCHOR + " " + NOTE_API,
        ),
        (
            r" & \multicolumn{2}{c}{Laya-Fin} & \multicolumn{2}{c}{d1-ultra} & \multicolumn{2}{c}{Anchor} \\",
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
        ),
        sources=(f"{sc.NA12_TAB}/{T10}.csv", f"{sc.NA12_TAB}/{T4}.csv"),
    )


STRATEGY_BOOKS: Final = (
    (
        "Laya-Fin (primary)",
        (
            ("S-CONV", "S-CONV|laya_fin|D2|u|close_t+5|all", r"D2 to $t{+}5$"),
            ("S-D0", "S-D0|laya_fin|D0|n_tilde|close_t|all", "open to close"),
            ("S-D0, gated", "S-D0|laya_fin|D0|n_tilde|close_t+1|gated", r"open to $t{+}1$"),
            ("S-D1 $J$", "S-D1|laya_fin|D1|j|close_t|all", "10:00 to close"),
            ("S-D2 $J$", "S-D2|laya_fin|D2|j|close_t+5|all", r"next open to $t{+}5$"),
            ("S-D2 RG", "S-D2|laya_fin|D2|rg|close_t+5|all", r"next open to $t{+}5$"),
        ),
    ),
    (
        "d1-ultra (model-specific)",
        (
            ("S-CONV", "S-CONV|d1_ultra|D2|u|close_t+5|all", r"D2 to $t{+}5$"),
            ("S-D0", "S-D0|d1_ultra|D0|n_tilde|close_t|all", "open to close"),
            ("S-D1 $J$", "S-D1|d1_ultra|D1|j|close_t|all", "10:00 to close"),
            ("S-D2 $J$", "S-D2|d1_ultra|D2|j|close_t+5|all", r"next open to $t{+}5$"),
        ),
    ),
    (
        "Benchmarks",
        (
            ("gap fade (price-only)", "gap_fade|-|D2|gap|close_t+5|all", r"D2 to $t{+}5$"),
            (r"vendor sentiment$^{\dagger}$", "vendor_sentiment|-|D0|sentiment|close_t|all", "open to close"),
        ),
    ),
)


def main_strategies() -> Table:
    panels = []
    for title, books in STRATEGY_BOOKS:
        rows = []
        for book, rule, hold in books:
            k = f"test|{rule}"
            rows.append(
                (
                    book,
                    (
                        Txt(hold),
                        Num(T20, k, "sharpe_gross", "f2"),
                        Num(T20, k, "sharpe_net_10", "f2"),
                        Num(T20, k, "turnover_daily", "f2"),
                        Num(T35, rule, "break_even_bp", "bp1"),
                        Num(T20, k, "placebo_pct_gross", "f0"),
                        Num(T20, k, "dsr_prob_net_10", "p"),
                    ),
                )
            )
        panels.append(Panel(title, tuple(rows)))
    return Table(
        "tab6_strategies",
        "tab:strategies",
        MAIN,
        "Strategies on the test period: no pre-registered book survives costs and the deflated Sharpe ratio.",
        (
            Col("Book", "l"),
            Col("Holding", "l"),
            Col("Gross"),
            Col("Net"),
            Col("Turnover"),
            Col("Break-even (bp)"),
            Col("Placebo pct."),
            Col("DSR"),
        ),
        tuple(panels),
        (
            r"Annualized Sharpe ratios ($\sqrt{252}$), gross and net of 10 bp per side on both legs and the "
            r"SPY "
            r"hedge; no borrow cost. Turnover: dollars traded a day per dollar of capital. Break-even: the "
            r"cost "
            r"per side, in basis points, at which the mean net return is zero (gross mean $\div$ turnover). "
            r"Placebo: the percentile of the gross Sharpe among 100 random-signal books on the same events. "
            r"DSR: "
            r"the deflated-Sharpe probability at 10 bp with the {{t22_spend/trials/value@int}} trials of "
            r"the trials "
            r"ledger. Each family is "
            r"shown at its hypothesis' horizon; every book is in Table~\ref{tab:a-strategies}. S-CONV ranks "
            r"by "
            r"the gap $U = V - G^{\mathrm{lvl}}$; S-D0 by $\tilde N$; S-D1 and S-D2 by the judgment $J$ "
            r"signed by the move; RG books trade the cases the model calls a misreaction (one name a side).",
            NOTE_VENDOR_BOOKS + " " + NOTE_API,
        ),
        (
            r" & & \multicolumn{2}{c}{Sharpe ratio} & & & & \\",
            r"\cmidrule(lr){3-4}",
        ),
        colsep=r"\setlength{\tabcolsep}{3pt}",
        sources=(f"{sc.TABLES}/{T20}.csv", f"{sc.TABLES}/{T35}.csv"),
    )


def main_tables() -> list[Table]:
    return [
        main_primary(),
        main_ic(),
        main_over_under(),
        main_convergence(),
        main_explaining(),
        main_strategies(),
    ]


# --- the appendix tables: one view of each CSV --------------------------------------------------------------


@dataclass(frozen=True)
class View:
    """A column view of one CSV table: the row label from ``label`` columns, numbers from ``cols``
    (column, header, format), rows by ``where``, panels by ``panel`` (a column)."""

    name: str
    caption: str
    label_cols: tuple[str, ...]
    label_head: str
    cols: tuple[tuple[str, str, str], ...]
    where: Callable[[pd.DataFrame], pd.Series] | None = None
    panel: str = ""
    notes: tuple[str, ...] = ()
    head: tuple[str, ...] = ()
    landscape: bool = False
    size: str = r"\small"
    label_fn: Callable[[Mapping[str, Any]], str] | None = None
    ci: tuple[str, str, str, int] | None = None  # (lo, hi, header, decimals) after the first number column
    label_width: str = ""  # a wrapped label column of this width (long labels)
    colsep: str = ""
    int_keys: tuple[str, ...] = ()  # rows that are counts: their numbers print as whole numbers
    extra: dict[str, Any] = field(default_factory=dict)


def _label(v: View, row: Mapping[str, Any]) -> str:
    """The row label: the label columns' words, a part said twice in a row once ("all tiers, all tiers")."""
    if v.label_fn is not None:
        return v.label_fn(row)
    parts = [word(row[c]) for c in v.label_cols if not (isinstance(row[c], float) and math.isnan(row[c]))]
    return ", ".join(p for i, p in enumerate(parts) if i == 0 or p != parts[i - 1])


def _ma_label(row: Mapping[str, Any]) -> str:
    period, _, rest = str(row["key"]).removeprefix("periods:").partition(":")
    if rest == "fade_no_news":
        return f"{word(period)}, the no-news fade"
    group, _, days = rest.removeprefix("statistics:").partition("|")
    return f"{word(period)}, {MA_GROUP[group]}, {days} days"


def _share_label(row: Mapping[str, Any]) -> str:
    """t11's items: the explained share by cut, θ by decision point, persistence by move reason."""
    kind, _, rest = str(row["key"]).partition(":")
    if kind == "share":
        cut, _, level = rest.partition(":")
        what = "all" if cut == "all" else TIER[level] if cut == "tier" else REASON[level]
        return f"explained share ({what})"
    if kind == "theta":
        return rf"$\theta$ at {rest.upper()}"
    if kind == "persistence":
        return f"persistence ({REASON[rest]})"
    return word(str(row["key"]).replace(":", ", "))


def view_table(v: View, df: pd.DataFrame, label: str) -> Table:
    d = df if v.where is None else df[v.where(df)]
    groups = [("", d)] if not v.panel else [(word(g), x) for g, x in d.groupby(v.panel, sort=False)]
    panels = []
    for title, g in groups:
        rows = []
        for row in g.to_dict("records"):
            k = str(row["key"])
            cells: list[Cell] = []
            for j, (col, _h, fmt) in enumerate(v.cols):
                f = "int" if k in v.int_keys and fmt.startswith("f") else fmt
                cells.append(Num(v.name, k, col, f) if col in row else None)
                if v.ci is not None and j == 0:
                    cells.append(CI(v.name, k, v.ci[0], v.ci[1], v.ci[3]))
            rows.append((_label(v, {str(c): x for c, x in row.items()}), tuple(cells)))
        panels.append(Panel(title, tuple(rows)))
    lab = rf">{{\raggedright\arraybackslash}}p{{{v.label_width}}}" if v.label_width else "l"
    cols = [Col(v.label_head, lab)]
    for j, (_c, h, _f) in enumerate(v.cols):
        cols.append(Col(h))
        if v.ci is not None and j == 0:
            cols.append(Col(v.ci[2], "c"))
    nrows = sum(len(p.rows) for p in panels)
    return Table(
        v.name,
        label,
        APPENDIX,
        v.caption,
        tuple(cols),
        tuple(panels),
        v.notes,
        v.head,
        size=v.size if nrows <= 40 else r"\footnotesize",
        long=nrows > 40,
        landscape=v.landscape,
        sources=(f"{sc.TABLES}/{v.name}.csv",),
        colsep=v.colsep,
    )


def _is(col: str, *values: Any) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda df: df[col].isin(values)


def _not_exploratory(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    drop = tb.EXPLORATORY_ROWS[name][0]
    return lambda df: ~drop(df)


def _strategy_label(row: Mapping[str, Any]) -> str:
    fam = {"gap_fade": "gap fade", "vendor_sentiment": r"vendor sentiment$^{\dagger}$"}.get(
        str(row["family"]), str(row["family"])
    )
    model = word(row["model"]) if isinstance(row["model"], str) else ""
    sig = "" if str(row["signal"]) == "sentiment" else f" {word(row['signal'])}"  # the family names it
    gated = ", gated" if bool(row["gated"]) else ""
    parts = [p for p in (fam, model, f"{row['point']}{sig}") if p]
    return ", ".join(parts) + f", to {RUNG.get(str(row['exit']), word(row['exit']))}{gated}"


def _rule_label(row: Mapping[str, Any]) -> str:
    """A book keyed by its NA-13 rule, "family|model|point|signal|exit|gate" ("-" for no model), as t20
    names it."""
    fam, model, point, signal, exit_, gate = str(row["key"]).split("|")
    book = {"family": fam, "model": math.nan if model == "-" else model, "point": point, "signal": signal}
    return _strategy_label({**book, "exit": exit_, "gated": gate == "gated"})


VIEWS: Final[tuple[View, ...]] = (
    View(
        "t14_model_comparison",
        "Model comparison: the daily IC with $z_{cc}$ on val-B and test, the cost and the latency.",
        ("model",),
        "Model",
        (
            ("ic_val_b", "IC val-B", "f3"),
            ("ic_val_b_t", "$t$", "f2"),
            ("ic_test", "IC test", "f3"),
            ("ic_test_t", "$t$", "f2"),
            ("ic_test_n", "Events", "int"),
            ("cost_per_1000", "USD/1,000", "f3"),
            ("latency_p50_ms", "p50 (ms)", "int"),
        ),
        label_width="1.75in",
        size=r"\footnotesize",
        label_fn=lambda r: {
            "llm_subsample:laya_fin": "Laya-Fin, LLM's 2,000-event subsample",
            "llm_subsample:llm": "LLM baseline, its subsample",
            "baseline:price_only_d2": r"price-only (D2, IC with $y_2$)",
        }.get(str(r["key"]), MODEL.get(str(r["key"]).removeprefix("baseline:"), word(r["model"]))),
        notes=(NOTE_DASH, NOTE_VENDOR, NOTE_SPAN, NOTE_ANCHOR, NOTE_API),
    ),
    View(
        "t27_tournament",
        "The zero-shot tournament on NA-06's val-A stage-1 sample: no model is excluded by the model "
        "confidence set.",
        ("model",),
        "Model",
        (("ic", "IC", "f3"), ("cost_per_1000_decisions", "USD per 1,000", "f3")),
        ci=("ci_low", "ci_high", r"95\% CI", 3),
        label_fn=lambda r: MODEL.get(str(r["model"]), word(str(r["model"]).split("/")[-1])),
        notes=(
            "Daily IC of Call A's $\\hat N$ with $z_{cc}$ on NA-06's val-A stage-1 sample, 95\\% bootstrap "
            "CI. Every model is in "
            "the model confidence set; the six best ran the stage-2 screens and failed them (\\S8.3).",
            NOTE_SPAN,
        ),
    ),
    View(
        "t21_release_dates",
        "Release dates: every decision model came out after the sample; only the anchor's checkpoint "
        "predates it.",
        ("name",),
        "Model",
        (("days_after_sample_end", "Days after the sample", "int"),),
        label_fn=lambda r: (
            {
                "sample_end": "end of the test period",
                "laya": "Laya (open weights; Laya-Fin's base)",
                "anchor": "ModernBERT-large (the anchor's checkpoint)",
            }.get(str(r["key"]), MODEL.get(str(r["name"]), word(r["name"])))
            + f", {r['date']}"
        ),
        notes=(
            DASH_NOTES["t21_release_dates"],
            "Release dates from the NA-05 catalog; Laya's from the operator (Convai's release, weights on "
            "Hugging Face); the anchor's checkpoint is known to the month only.",
            NOTE_SPAN,
        ),
    ),
    View(
        "t22_spend",
        "Spend and requests of the whole project, from the ledgers.",
        ("item",),
        "Item",
        (("value", "Value", "f2"), ("cap", "Cap", "f0")),
        int_keys=("openrouter_spend_lines", "fmp_requests", "trials", "test_access"),
        notes=(
            DASH_NOTES["t22_spend"],
            "Spend in USD and GPU-hours to two decimals; counts are whole numbers. "
            "Kaggle GPU-hours from the NA-08 and NA-11 reports (Kaggle keeps no ledger here). "
            "NA-12, "
            "NA-13 and NA-14 made no API call, Kaggle run or FMP request.",
        ),
    ),
    View(
        "t28_filter_frontier",
        "The importance filters on val-A: material recall at each budget.",
        ("filter", "target_share"),
        "Filter, budget",
        (
            ("selected_share", "Selected", "f3"),
            ("threshold", "Threshold", "f3"),
            ("recall_material", "Recall (material)", "f3"),
            ("recall_delayed", "Recall (delayed)", "f3"),
            ("precision", "Precision", "f3"),
        ),
        notes=(
            "Shares of NA-03's val-A comparison sample of member-days. F5, logistic regression on bge-small "
            "embeddings, is the frozen filter at a 30\\% budget.",
        ),
    ),
    View(
        "t29_encoding",
        "Encodings of numbers in states: E1 ranked best in the val-A search but fell short of E3 on val-B, "
        "so E3 was kept.",
        ("split", "model", "encoding"),
        "Split, model, encoding",
        (("ic", "IC", "f3"), ("t", "$t$", "f2"), ("n_events", "Events", "int"), ("rank", "Rank", "int")),
        where=lambda df: df["model"] != "pooled",
        ci=("ci_low", "ci_high", r"95\% CI", 3),
        notes=(NOTE_SPAN, NOTE_API),
    ),
    View(
        "t1b_primary_by_model",
        "The primary tests for every model.",
        ("test",),
        "Test",
        (
            ("estimate", "Estimate", "f4"),
            ("nw_t", "$t$", "f2"),
            ("p", "$p$", "p"),
            ("p_holm_within_model", "Holm $p$", "p"),
            ("n_obs", "Events", "int"),
        ),
        ci=("ci_low", "ci_high", r"95\% CI", 4),
        panel="model",
        notes=(
            NOTE_DASH,
            "Holm within each model; the verdict is Laya-Fin's (Table~\\ref{tab:primary}).",
            NOTE_ANCHOR,
            NOTE_API,
            NOTE_SPAN,
        ),
    ),
    View(
        "t3_ic",
        "Daily IC by target on the test period, with the quintile spread.",
        ("model", "target"),
        "Model, target",
        (
            ("ic", "IC", "f3"),
            ("ic_t", "$t$", "f2"),
            ("n_obs", "Events", "int"),
            ("qspread", "Top $-$ bottom", "f3"),
            ("qspread_p", "$p$", "p"),
        ),
        ci=("ic_ci_low", "ic_ci_high", r"95\% CI", 3),
        head=(r" & & & & & \multicolumn{2}{c}{Quintile spread} \\", r"\cmidrule(lr){6-7}"),
        notes=(
            "Quintile spread: the mean target in the top quintile of $\\hat N$ minus the bottom quintile, in "
            "typical daily moves, and its $p$; the IC's own test is its $t$.",
            NOTE_ANCHOR,
            NOTE_API,
            NOTE_SPAN,
        ),
    ),
    View(
        "t32_val_b_ic",
        "Val-B daily ICs by target of the trained and zero-shot Laya models (NA-11, before the freeze).",
        ("key",),
        "Model",
        (
            ("ic_z_cc", "IC $z_{cc}$", "f3"),
            ("ic_z_cc_t", "$t$", "f2"),
            ("ic_z_on", "IC $z_{on}$", "f3"),
            ("ic_z_on_t", "$t$", "f2"),
            ("ic_z_id", "IC $z_{id}$", "f3"),
            ("ic_z_id_t", "$t$", "f2"),
            ("ic_z_id_n", "Events", "int"),
        ),
        notes=("From NA-11's run of the frozen spec on val-B, before the freeze.", NOTE_ANCHOR),
    ),
    View(
        "t15_calibration",
        "Calibration of the three-class forecasts: the trained models are calibrated but barely informative.",
        ("model", "target"),
        "Model, target",
        (
            ("ece", "ECE", "f3"),
            ("log_loss_skill", "Log-loss skill", "f3"),
            ("brier_skill", "Brier skill", "f3"),
            ("auc", "AUC", "f2"),
            ("temperature", "$T$", "f2"),
            ("ece_before", "ECE before", "f3"),
            ("ece_after", "ECE after", "f3"),
        ),
        label_fn=lambda r: (
            f"{word(r['model'])}, {word(r['target'])}"
            + (", temperature scaling" if str(r["key"]).endswith(":temperature") else "")
        ),
        label_width="1.6in",
        notes=(
            NOTE_DASH,
            "Q1's three classes against the targets; skill against val-A climatology; $T$ the temperature "
            "fit on val-A.",
            NOTE_ANCHOR,
            NOTE_SPAN,
        ),
    ),
    View(
        "t16_robustness",
        "Robustness of the primary results: no variant changes a conclusion.",
        ("model", "point", "variant", "adjustment"),
        "Model, point, variant",
        (
            ("H1", "H1", "f3"),
            ("H1_p", "$p$", "p"),
            ("H1b", "H1b", "f3"),
            ("H1b_p", "$p$", "p"),
            ("ic_z_cc", "IC $z_{cc}$", "f3"),
            ("b", "$b$", "f3"),
            ("b_p", "$p_b$", "p"),
            ("c", "$c$", "f3"),
            ("c_p", "$p_c$", "p"),
            ("ic_y2", "IC $y_2$", "f3"),
        ),
        landscape=True,
        colsep=r"\setlength{\tabcolsep}{4pt}",  # the longest variant names fit on one line
        notes=(
            NOTE_DASH,
            "Each variant raw and placebo-adjusted (\\S5.7). Call B ablations: IC of $J$, $C$ and $\\hat N$ "
            "with $y_2$, real against "
            "ablated.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t2_h2_over_under",
        "The over/under regression for every model, decision point and $|G|$ bin.",
        ("model", "variant"),
        "Model, regression",
        (
            ("b", "$b$", "f3"),
            ("b_se", "SE", "se3"),
            ("b_p", "$p_b$", "p"),
            ("c", "$c$", "f3"),
            ("c_se", "SE", "se3"),
            ("c_p", "$p_c$", "p"),
            ("b_p_dk", "$p_b$ DK", "p"),
            ("c_p_dk", "$p_c$ DK", "p"),
            ("nobs", "Events", "int"),
        ),
        landscape=True,
        notes=(
            DASH_NOTES["t2_h2_over_under"],
            "DK: Driscoll--Kraay standard errors (5 lags) as robustness.",
            NOTE_ANCHOR,
            NOTE_API,
            NOTE_SPAN,
        ),
    ),
    View(
        "t4_secondary",
        "Secondary hypotheses: only H5 survives Benjamini--Hochberg for Laya-Fin.",
        ("model", "test"),
        "Model, test",
        (
            ("estimate", "Estimate", "f4"),
            ("se", "SE", "se4"),
            ("p", "$p$", "p"),
            ("q", "BH $q$", "p"),
            ("q_pooled", "Pooled $q$", "p"),
        ),
        ci=("ci_low", "ci_high", r"95\% CI", 4),
        notes=(
            NOTE_DASH,
            "BH at $q = 0.10$ within each instrument; the pooled family adds d1-ultra's H6 and A3.4 to "
            "Laya-Fin's. The anchor's H7 is reported outside its family, so it has no $q$. Each test has "
            "either an SE or a 95\\% CI, as NA-12 states it.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t5_heterogeneity",
        "Heterogeneity of H2: no cut differs.",
        ("model", "cut"),
        "Model, cut",
        (
            ("n_in", "Events", "int"),
            ("wald_f", "Wald $F$", "f2"),
            ("p", "$p$", "p"),
            ("q", "BH $q$", "p"),
            ("b_diff", "$\\Delta b$", "f3"),
            ("b_diff_se", "SE", "se3"),
            ("c_diff", "$\\Delta c$", "f3"),
            ("c_diff_se", "SE", "se3"),
        ),
        notes=(
            "Wald test of $\\hat N\\cdot 1[\\mathrm{cut}]$ and $G\\cdot 1[\\mathrm{cut}]$ added to H2 at "
            "D2; BH over each model's eight cuts. Events: the D2 events in the cut.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t6_convergence_ladder",
        "The convergence ladder $\\kappa_h$ in every variant.",
        ("model", "variant", "rung"),
        "Model, variant, rung",
        (
            ("kappa", "$\\kappa_h$", "f3"),
            ("kappa_se", "SE", "se3"),
            ("kappa_p", "$p$", "p"),
            ("kappa_p_dk", "$p$ DK", "p"),
            ("nobs", "Events", "int"),
        ),
        notes=(
            NOTE_DASH,
            "Variants: the ladder; clean windows (no other selected event in the window); $h^{*} = t{+}10$; "
            "the plateau.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t7_gap_closure",
        "Gap closure $\\lambda_h$ and $\\psi_h$ at D1 and D2.",
        ("model", "point", "variant", "rung"),
        "Model, point, variant, rung",
        (
            ("lambda", "$\\lambda_h$", "f3"),
            ("lambda_se", "SE", "se3"),
            ("lambda_p", "$p$", "p"),
            ("psi", "$\\psi_h$", "f3"),
            ("psi_p_two", "$p$ (two-sided)", "p"),
            ("nobs", "Events", "int"),
        ),
        notes=(
            DASH_NOTES["t7_gap_closure"],
            "The half-life rows hold the first rung with $\\lambda_h \\geq 0.5$ ($\\infty$: not reached "
            "within $t{+}20$).",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t8_tracking_error",
        "Tracking error of $V$: no better than a naive zero.",
        ("model", "rung"),
        "Model, rung",
        (
            ("rmse", "RMSE", "f3"),
            ("naive_ratio", "Ratio to naive", "f3"),
            ("naive_p", "$p$", "p"),
            ("price_only_ratio", "Ratio to price-only", "f3"),
            ("price_only_p", "$p$", "p"),
            ("nobs", "Events", "int"),
        ),
        notes=(
            "RMSE of $\\mathrm{CAR}^{\\mathrm{lvl}}_h - V$ relative to a naive 0 and to the price-only $V$.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t9_convergence_cuts",
        "Convergence by cut.",
        ("model", "cut", "level"),
        "Model, cut, level",
        (
            ("kappa_t20", "$\\kappa_{t+20}$", "f3"),
            ("kappa_t20_p", "$p$", "p"),
            ("kappa_ct", "$\\kappa_{C_t}$", "f3"),
            ("kappa_ct_p", "$p$", "p"),
            ("lambda_t5", "$\\lambda_{t+5}$", "f3"),
            ("lambda_t5_p", "$p$", "p"),
            ("nobs_d0", "Events ($\\kappa$)", "int"),
            ("nobs_gap", "Events ($\\lambda$)", "int"),
        ),
        notes=(
            NOTE_DASH,
            "Events ($\\kappa$): the D0 events behind $\\kappa$; events ($\\lambda$): the gap events behind "
            "$\\lambda_{t+5}$.",
            NOTE_ANCHOR,
            NOTE_API,
        ),  # portrait: 36 rows overflow a landscape page
        size=r"\footnotesize",  # two event counts fit the text width at the long tables' size
        colsep=r"\setlength{\tabcolsep}{4pt}",
    ),
    View(
        "t13_shapley",
        "Shapley values of the out-of-sample $R^2$ and IC of $y_2$ at D2: every total is about zero.",
        ("model", "tier", "metric", "group"),
        "Model, tier, metric, group",
        (("shapley", "Shapley value", "f4"), ("share", "Share", "f3"), ("n", "Events", "int")),
        notes=(
            DASH_NOTES["t13_shapley"],
            "Shares are of a total that is about zero, so they carry no information.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t10_explanation_ladder",
        "The explanation ladder for every model and cut.",
        ("model", "cut", "step"),
        "Model, cut, step",
        (
            ("r2", "$R^2$", "f4"),
            ("r2_p", "$p$", "p"),
            ("increment", "$\\Delta R^2$", "f4"),
            ("increment_p", "$p$", "p"),
            ("n", "Member-days", "int"),
        ),
        ci=("r2_ci_low", "r2_ci_high", r"95\% CI", 4),
        label_width="2.2in",
        colsep=r"\setlength{\tabcolsep}{4pt}",  # the member-days column fits the text width
        notes=(
            NOTE_DASH,
            "Out-of-sample $R^2$ of $z_{cc}$, cumulative by step; bootstrap CIs.",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t11_explanation_share_theta",
        "Explained share, $\\theta$ and persistence by reason (d1-ultra): explained moves do not persist "
        "more.",
        ("item",),
        "Item",
        (
            ("value", "Value", "f3"),
            ("events_share", "Share of events", "f3"),
            ("se", "SE", "se3"),
            ("p", "$p$", "p"),
            ("n", "Events", "int"),
        ),
        where=_not_exploratory("t11_explanation_share_theta"),
        label_fn=_share_label,
        notes=(
            NOTE_DASH,
            r"The exploratory A3.5 market-level replication is in Table~\ref{tab:a-market-replication}.",
            NOTE_API,
        ),
    ),
    View(
        "t12_question_battery",
        "Question battery v2: mechanism cuts, horizon validity and width.",
        ("model", "analysis", "label", "level"),
        "Model, analysis, label, level",
        (
            ("b", "$b$", "f3"),
            ("b_p", "$p_b$", "p"),
            ("c", "$c$", "f3"),
            ("c_p", "$p_c$", "p"),
            ("kappa_t20", "$\\kappa_{t+20}$", "f3"),
            ("rho", "$\\rho$", "f3"),
            ("p", "$p$", "p"),
            ("delta_r2", "$\\Delta R^2$", "f4"),
            ("agreement", "Agreement", "f3"),
            ("nobs", "Events", "int"),
        ),
        landscape=True,
        colsep=r"\setlength{\tabcolsep}{4pt}",
        label_width="3.5in",  # the long analysis names wrap, so the agreement column fits the page
        notes=(
            NOTE_DASH,
            "Reading validity: the share of the 500 val-A events on which d1-ultra's answer agrees with the "
            "vendor's tag (event type, the raw tag, quantified; the rumor tag for credibility) or with the "
            "earnings calendar (scheduled).",
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t20_strategies",
        "Every pre-registered book and the benchmarks, test and val-B.",
        ("split",),
        "Book",
        (
            ("sharpe_gross", "Gross", "f2"),
            ("sharpe_net_5", "5 bp", "f2"),
            ("sharpe_net_10", "10 bp", "f2"),
            ("sharpe_net_20", "20 bp", "f2"),
            ("turnover_daily", "Turnover", "f2"),
            ("placebo_pct_gross", "Placebo", "f0"),
            ("placebo_pct_net_10", "Placebo net", "f0"),
            ("dsr_prob_net_10", "DSR", "p"),
            ("capacity_median_usd", "Capacity (USD)", "int"),
        ),
        where=lambda df: (df["family"] != "exploratory") & df["sharpe_gross"].notna(),
        panel="split",
        landscape=True,
        label_fn=_strategy_label,
        notes=(
            "Annualized Sharpe ratios gross and net of 5, 10 and 20 bp per side; placebo percentiles among "
            "100 "
            "random-signal books; DSR at 10 bp with the {{t22_spend/trials/value@int}} trials of the "
            "ledger; capacity at 1\\% of the 20-session "
            "ADV (median over decisions). Empty RG books of the anchor are left out. "
            + r"The exploratory MA-cross fade (post hoc) is in Table~\ref{tab:a-ma-cross} and Figure A15.",
            NOTE_VENDOR_BOOKS,
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t26_sconv_overlap",
        "S-CONV against the price-only gap fade: the same positions on the same side.",
        ("key",),
        "Book",
        (
            ("shared_share", "Shared", "f3"),
            ("same_side_share", "Same side", "f3"),
            ("corr_gross", "Correlation", "f2"),
            ("n_days", "Days", "int"),
        ),
        label_fn=lambda r: (
            word(str(r["key"]).split(":")[0])
            + ", "
            + str(r["key"]).split(":")[1]
            + " to "
            + RUNG.get(str(r["key"]).split(":")[2], "")
        ),
        notes=(
            "Shared: the share of the book's (session, symbol) positions also held by the gap fade; same "
            "side among "
            "those; correlation of the daily gross returns. Recomputed from NA-13's stored positions and "
            "books.",
            NOTE_ANCHOR,
        ),
    ),
    View(
        "t33_placebo_sharpe",
        "The random-signal placebo: 5th, 50th and 95th percentile of the Sharpe ratio per universe.",
        ("point", "exit"),
        "Decision point, exit: books",
        (
            ("sharpe_gross_q05", "5th", "f2"),
            ("sharpe_gross_q50", "50th", "f2"),
            ("sharpe_gross_q95", "95th", "f2"),
            ("sharpe_net_10_q05", "5th", "f2"),
            ("sharpe_net_10_q50", "50th", "f2"),
            ("sharpe_net_10_q95", "95th", "f2"),
            ("n_books", "Books", "int"),
        ),
        head=(
            r" & \multicolumn{3}{c}{Gross} & \multicolumn{3}{c}{Net of 10 bp} & \\",
            r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
        ),
        label_width="2.3in",
        notes=(
            "Annualized Sharpe ratios of the 100 random-signal books of each test universe (a decision "
            "point, an exit and "
            "a set of events), numpy's linear quantiles; from NA-13's stored placebo books. A universe is "
            "named by the books that trade on it, with the model where its events are that model's alone.",
            NOTE_VENDOR_BOOKS,
        ),
    ),
    View(
        "t35_break_even",
        "Break-even cost per side of every test book.",
        ("key",),
        "Book",
        (
            ("ann_return_gross", "Gross return (annual)", "f3"),
            ("turnover_daily", "Turnover", "f2"),
            ("break_even_bp", "Break-even (bp)", "bp1"),
        ),
        where=_not_exploratory("t35_break_even"),
        label_fn=_rule_label,
        notes=(
            "Gross mean $\\div$ turnover, from NA-13's strategy table. "
            + r"The exploratory MA-cross fade (post hoc) is in Table~\ref{tab:a-ma-cross} and Figure A15.",
            NOTE_VENDOR_BOOKS,
            NOTE_ANCHOR,
            NOTE_API,
        ),
    ),
    View(
        "t23_company_identification",
        "Company identification on masked states: the API models name the company far above the matched "
        "baseline.",
        ("model",),
        "Model",
        (
            ("accuracy", "Identified", "f3"),
            ("valid", "States", "int"),
            ("baseline_matched", "Matched baseline", "f3"),
            ("screen_threshold", "Screen bar", "f2"),
        ),
        label_fn=lambda r: MODEL.get(str(r["model"]), word(str(r["model"]).split("/")[-1])),
        notes=(
            "NA-06's val-A events with activity-matched distractors (NA-11); States: the valid answers.",
            NOTE_SPAN,
        ),
    ),
    View(
        "t18_probes_val_a",
        "The disclosed val-A probes (descriptive columns exploratory).",
        ("model",),
        "Model",
        (
            ("flip_rate", "Flip rate", "f2"),
            ("right_way", "Right way", "f2"),
            ("shift_sd", "Shift (SD)", "f2"),
            ("ic_masked", "IC masked", "f3"),
            ("ic_unmasked", "IC unmasked", "f3"),
            ("ic_real_same_events", "IC real", "f3"),
            ("ic_shuffled", "IC shuffled", "f3"),
        ),
        label_fn=lambda r: MODEL.get(str(r["model"]), word(str(r["model"]).split("/")[-1])),
        size=r"\footnotesize",
        colsep=r"\setlength{\tabcolsep}{4pt}",
        notes=(
            DASH_NOTES["t18_probes_val_a"],
            "Exploratory: the probes' descriptive columns (NA-11), not hypotheses.",
            NOTE_ANCHOR,
            NOTE_SPAN,
        ),
    ),
    View(
        "t19_monthly_ic",
        "Monthly mean of the daily IC with $z_{cc}$.",
        ("model", "split", "month"),
        "Model, split, month",
        (("ic", "IC", "f3"), ("n_days", "Days", "int")),
        notes=(NOTE_ANCHOR, NOTE_API, NOTE_SPAN),
    ),
    View(
        "t17_sector_exploratory",
        "Exploratory: the IC by GICS sector.",
        ("model", "kind", "sector"),
        "Model, kind, sector",
        (
            ("ic_z_cc", "IC $z_{cc}$", "f3"),
            ("ic_z_cc_t", "$t$", "f2"),
            ("ic_z_cc_n", "Events", "int"),
            ("ic_z_on", "IC $z_{on}$", "f3"),
            ("ic_z_id", "IC $z_{id}$", "f3"),
        ),
        notes=(NOTE_EXPLORATORY, NOTE_API),
    ),
    View(
        "t25_ma_cross",
        "Exploratory: news and a moving-average cross; the validation result did not replicate.",
        ("key",),
        "Group",
        (
            ("mean_bp", "Mean (bp)", "f1"),
            ("nw_t", "$t$", "f2"),
            ("n_days", "Days", "int"),
            ("sharpe_gross", "Gross Sharpe", "f2"),
            ("sharpe_net_10", "Net 10 bp", "f2"),
        ),
        where=lambda df: df["key"].str.contains("statistics|fade_no_news$", regex=True),
        label_fn=_ma_label,
        notes=(
            DASH_NOTES["t25_ma_cross"],
            NOTE_EXPLORATORY,
            "MA20/MA50 crosses; signed abnormal return over 5 or 20 days by group; the tradable no-news "
            "fade.",
        ),
    ),
    View(
        "t31_market_replication",
        "Exploratory: the A3.5 market-level replication.",
        ("item",),
        "Item",
        (("value", "OOS $R^2$", "f3"), ("p", "$p$", "p"), ("n", "Sessions", "int")),
        ci=None,
        label_fn=lambda r: "SPY's daily return on d1-ultra's market reading",
        notes=(
            "Exploratory (PREREG A3.5: optional, exploratory); fit on the validation sessions, evaluated on "
            "test.",
        ),
    ),
    View(
        "t30_derived",
        "Sums of figure-data cells cited in captions.",
        ("key",),
        "Quantity",
        (("value", "Value", "int"),),
        label_fn=lambda r: "Laya-Fin's events with $|\\hat N| \\geq 0.5$ (its three RG classes)",
    ),
)


def deviations_table(df: pd.DataFrame) -> Table:
    name = "t34_prereg_deviations"
    rows = tuple(
        (
            str(int(r["row"])),
            (
                Num(name, str(r["key"]), "date", "md"),
                Num(name, str(r["key"]), "chunk", "text"),
                Num(name, str(r["key"]), "change", "text"),
                Num(name, str(r["key"]), "reason", "text"),
                Num(name, str(r["key"]), "freeze", "text"),
            ),
        )
        for r in df.to_dict("records")
    )
    return Table(
        "t34_prereg_deviations",
        "tab:a-deviations",
        APPENDIX,
        "Pre-registration deviations (PREREG \\S15), one line per row of the log.",
        (
            Col("Row", "r"),
            Col("Date", "l"),
            Col("Chunk", "l"),
            Col("Change", r">{\raggedright\arraybackslash}p{2.85in}"),
            Col("Reason", r">{\raggedright\arraybackslash}p{1.7in}"),
            Col("Freeze", "l"),
        ),
        (Panel("", rows),),
        (
            "Dates are in the sample's last calendar year (MM-DD); Freeze: written before or after the "
            "freeze. Summaries by "
            "NA-14; the full text is in PREREG \\S15.",
        ),
        size=r"\scriptsize",
        colsep=r"\setlength{\tabcolsep}{3pt}",
        long=True,
        sources=(f"{sc.TABLES}/t34_prereg_deviations.csv",),
    )


# --- writing ------------------------------------------------------------------------------------------------


BOOK_NAME: Final = {
    "gap_fade": "gap fade",
    "vendor_sentiment": r"sentiment$^{\dagger}$",
    "exploratory": "MA fade",
}
SIGNAL_NAME: Final = {"j": " $J$", "rg": " RG"}


def universe_books(root: Path) -> dict[str, str]:
    """Each test universe of the placebo (t33) → the books of t20 that trade on it; a book whose universe
    holds only one model's events (a gated or RG book) is named with that model, so no two universes read
    alike."""
    st = pd.read_csv(root / sc.TABLES / "t20_strategies.csv", keep_default_na=False, na_values=[""])
    out: dict[str, dict[str, list[str]]] = {}
    for r in st[st["split"] == "test"].to_dict("records"):
        fam = str(r["family"])
        name = BOOK_NAME.get(fam, fam + SIGNAL_NAME.get(str(r["signal"]), ""))
        name += " gated" if bool(r["gated"]) else ""
        models = out.setdefault(str(r["universe"]), {}).setdefault(name, [])
        if isinstance(r["model"], str) and r["model"] not in models:
            models.append(r["model"])
    return {
        u: ", ".join(f"{n} ({word(m[0])})" if len(m) == 1 else n for n, m in books.items())
        for u, books in out.items()
    }


def appendix_tables(root: Path) -> list[Table]:
    out = []
    books = universe_books(root)
    for v in VIEWS:
        if v.name == "t33_placebo_sharpe":
            v = View(
                **{
                    **v.__dict__,
                    "label_fn": lambda r: f"{r['point']}, {RUNG[str(r['exit'])]}: {books[str(r['key'])]}",
                }
            )
        df = pd.read_csv(root / sc.TABLES / f"{v.name}.csv", keep_default_na=False, na_values=[""])
        out.append(view_table(v, df, f"tab:a-{v.name.split('_', 1)[1].replace('_', '-')}"))
    dev = pd.read_csv(root / sc.TABLES / "t34_prereg_deviations.csv", keep_default_na=False, na_values=[""])
    out.append(deviations_table(dev))
    return out


def build(layout: Layout | None = None) -> list[Table]:
    lay = resolve_layout(layout)
    return [*main_tables(), *appendix_tables(lay.root)]


def write(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    d = lay.root / sc.TABLES
    keys = kz.load(d / "keys.json")
    index = []
    for t in build(lay):
        text, cited = render(t, keys)
        (d / f"{t.name}.tex").write_text(text, encoding="utf-8")
        index.append(
            {
                "name": t.name,
                "label": t.label,
                "section": t.section,
                "file": f"{t.name}.tex",
                "sources": list(t.sources),
                "cells": cited,
            }
        )
    (lay.root / INDEX).write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return {"latex_tables": len(index), "main": sum(1 for t in index if t["section"] == MAIN)}


def main(argv: Sequence[str] | None = None) -> int:
    print(json.dumps(write(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
