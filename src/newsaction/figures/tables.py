"""NA-14 S3: the paper's tables in one format, with the keys its captions cite (PRD NA-14 S3–S4).

    uv run python -m newsaction.figures.tables

Writes ``artifacts/NA-14/tables/<name>.csv`` (and ``.tex`` for the paper tables), ``keys.json``
("<table>/<key>/
<column>" → value, NA-12's convention) and ``index.json``. Three kinds of table:

- **Copies.** NA-12's 20 tables (CSV byte for byte; ``keys.json`` equal to NA-12's), NA-13's strategy table
  and
  the figure sources of NA-03, NA-06, NA-07, NA-11 and NA-12, each with its row ``key`` in front (the figure
  data copies are data, without LaTeX).
- **Flattened results.** NA-12's exploratory "where the D0 signal lives" JSON and NA-13's MA-cross JSON, one
  row per object of scalars, keyed by its path, so post-hoc numbers can be cited too. The values are copied.
- **Records.** Release dates (NA-05 catalog; Laya from the operator), the spend and request ledgers, the
  S-CONV / gap-fade overlap of NA-13's stored positions (NA-13 REPORT §4 states it; no file held it), and the
  one sum a caption needs.

The LaTeX is one booktabs format for every table: readable headers, numbers right-aligned in math mode, the
model ids written out, and the operator's labels as table notes: the vendor-label baselines are a possibly
look-ahead-contaminated upper bound (CLAUDE.md A6; NA-12 owner decision 1), the anchor's readings are
uninformative, span-02 carries its S5 STOP, and exploratory tables say so.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
import yaml

from newsaction import io
from newsaction.config import load_project, load_splits
from newsaction.figures import keys as kz
from newsaction.figures import sources as sc
from newsaction.paths import Layout, resolve_layout

OPERATOR: Final = f"{sc.ARTIFACTS}/inputs/operator.yaml"
CATALOG: Final = "artifacts/NA-05/catalog.json"
MONTHLY_JSON: Final = "artifacts/NA-12/results/monthly_ic.json"
EXPLORATORY_JSON: Final = "artifacts/NA-12/results/exploratory_d0_signal.json"
MA_CROSS_JSON: Final = "artifacts/NA-13/results/ma_cross.json"
NA12_INDEX: Final = f"{sc.NA12_TAB}/index.json"
NA08_REPORT: Final = "artifacts/NA-08/REPORT.md"
NA11_REPORT: Final = "artifacts/NA-11/REPORT.md"
POSITIONS: Final = "strategy/positions_test.parquet"
BOOKS: Final = "strategy/books_test.parquet"
LONG_ROWS: Final = 40
WIDE_COLS: Final = 8
WRAP_CHARS: Final = 28  # a text column longer than this wraps in a ragged p-column of WRAP_EM
WRAP_EM: Final = 12
PT_PER_CHAR: Final = 3.6  # \scriptsize, roughly half an em
PORTRAIT_PT: Final = 470.0  # a little under the 6.9-in text width
# The paper view of a table too wide for a page: its rows and columns in LaTeX (the CSV keeps every cell and
# every column; the LaTeX notes say so).
LATEX_VIEW: Final[dict[str, tuple[Callable[[pd.DataFrame], pd.Series] | None, tuple[str, ...]]]] = {
    "t20_strategies": (
        lambda df: df["split"] == "test",
        (
            "family",
            "model",
            "point",
            "signal",
            "exit",
            "gated",
            "sharpe_gross",
            "sharpe_net_10",
            "placebo_pct_gross",
            "dsr_prob_net_10",
            "turnover_daily",
        ),
    ),
    "t10_explanation_ladder": (
        None,
        ("model", "cut", "step", "r2", "r2_ci_low", "r2_ci_high", "r2_p", "increment", "increment_p"),
    ),
    "t12_question_battery": (
        None,
        (
            "model",
            "analysis",
            "label",
            "level",
            "b",
            "b_p",
            "c",
            "c_p",
            "kappa_t20",
            "kappa_t20_p",
            "rho",
            "p",
            "delta_r2",
        ),
    ),
    "t16_robustness": (
        None,
        (
            "model",
            "point",
            "variant",
            "adjustment",
            "H1",
            "H1_p",
            "H1b",
            "H1b_p",
            "ic_z_cc",
            "ic_z_cc_t",
            "b",
            "b_p",
            "c",
            "c_p",
            "ic_y2",
            "ic_y2_t",
        ),
    ),
    "t17_sector_exploratory": (
        None,
        (
            "model",
            "kind",
            "sector",
            "ic_z_cc",
            "ic_z_cc_t",
            "ic_z_cc_n",
            "ic_z_on",
            "ic_z_on_t",
            "ic_z_id",
            "ic_z_id_t",
        ),
    ),
    "t25_ma_cross": (
        lambda df: df["key"].str.contains("statistics|fade_no_news$", regex=True),
        (
            "key",
            "group",
            "horizon",
            "mean_bp",
            "nw_t",
            "n_days",
            "n_crosses",
            "sharpe_gross",
            "sharpe_net_10",
            "placebo_pct_gross",
            "capacity_median_usd",
        ),
    ),
}

VENDOR: Final = ("sentiment", "tags_gbm")
EXPLORATORY_TABLES: Final = ("t17_sector_exploratory", "t24_exploratory_d0_signal", "t25_ma_cross")
NOTE_VENDOR: Final = (
    "† Vendor-label baseline (vendor sentiment, tags-GBM): the labels were produced retrospectively "
    "(CLAUDE.md "
    "A6), so this row is a possibly look-ahead-contaminated upper bound, not the benchmark. The clean "
    "benchmarks are bge-ridge, price-only, the LLM baseline and the random-signal placebo."
)
NOTE_ANCHOR: Final = (
    "The anchor's readings are uninformative (near-constant outputs: NA-11 REPORT §7.1 item 4); its rows are "
    "reported, not read as nulls."
)
NOTE_SPAN: Final = (
    "‡ span-02: the S5 canary fired a STOP after the freeze; the operator chose to proceed (PREREG §15, the "
    "post-freeze NA-11 S5 row)."
)
NOTE_EXPLORATORY: Final = (
    "Exploratory (post hoc): requested after unblinding; no hypothesis, outside every family, no claim."
)
DISPLAY: Final = {
    "laya_fin": "Laya-Fin",
    "anchor": "anchor (uninformative)",
    "d1_ultra": "d1-ultra",
    "span_02": "span-02‡",
    "respan/span-02": "respan/span-02‡",
    "drex_v2": "drex-v2.0",
    "laya_zs": "Laya zero-shot",
    "sentiment": "vendor sentiment†",
    "tags_gbm": "tags-GBM†",
    "embed_ridge": "bge-ridge",
    "llm": "LLM baseline",
    "price_only": "price-only",
}
HEADER_WORDS: Final = {
    "ic": "IC",
    "ci": "CI",
    "nw": "NW",
    "se": "SE",
    "dk": "DK",
    "p": "p",
    "q": "q",
    "n": "n",
    "r2": "R²",
    "oos": "OOS",
    "ece": "ECE",
    "auc": "AUC",
    "dsr": "DSR",
    "sr0": "SR0",
    "usd": "USD",
    "adv": "ADV",
    "mcs": "MCS",
    "id": "id",
    "holm": "Holm",
    "pct": "pct",
}
HEADER_PHRASES: Final = (
    ("val_a", "val-A"),
    ("val_b", "val-B"),
    ("z_cc", "z-cc"),
    ("z_on", "z-on"),
    ("z_id", "z-id"),
    ("n_hat", "N̂"),
)


@dataclass(frozen=True)
class PaperTable:
    name: str
    title: str
    frame: pd.DataFrame
    notes: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    latex: bool = True
    copy_of: str = ""  # an NA-12 table copied byte for byte
    extra: dict[str, Any] = field(default_factory=dict)


def _read_json(root: Path, rel: str) -> Any:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def _frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if "key" not in df.columns:
        raise ValueError("a table needs a key column")
    dup = df.loc[df["key"].duplicated(), "key"].tolist()
    if dup:
        raise ValueError(f"duplicate keys: {dup[:5]}")
    bad = [k for k in df["key"].astype(str) if "/" in k or "@" in k]
    if bad:
        raise ValueError(f"a key may not hold '/' or '@' (the cite syntax uses them): {bad[:5]}")
    return df[["key", *[c for c in df.columns if c != "key"]]]


# --- copies -------------------------------------------------------------------------------------------------


def na12_tables(root: Path) -> list[PaperTable]:
    out = []
    for t in _read_json(root, NA12_INDEX):
        path = f"{sc.NA12_TAB}/{t['name']}.csv"
        df = pd.read_csv(root / path)
        notes = tuple(t["notes"]) + ((NOTE_EXPLORATORY,) if t["name"] in EXPLORATORY_TABLES else ())
        out.append(PaperTable(t["name"], t["title"], df, notes, (path,), copy_of=path))
    return out


KEYED: Final = (
    (
        "t20_strategies",
        sc.STRATEGY,
        "NA-13 strategies, test and val-B (reference): every pre-registered book, "
        "S-CONV first, the benchmarks and the exploratory MA-cross fade",
        True,
    ),
    (
        "t23_company_identification",
        sc.COMPANY_ID,
        "Company identification with activity-matched distractors (NA-11; val-A, masked states)",
        True,
    ),
    (
        "t27_tournament",
        sc.TOURNAMENT,
        "NA-06 zero-shot tournament (val-A stage-1 sample): daily IC, cost per "
        "1,000 decisions, MCS membership, §8.3 screens",
        True,
    ),
    (
        "t28_filter_frontier",
        sc.FRONTIER,
        "NA-03 importance filters on val-A: selection share and recall by budget",
        True,
    ),
    (
        "t29_encoding",
        sc.ENCODING,
        "NA-07 encodings of numbers in states (val-A search, val-B confirmation)",
        True,
    ),
    ("f1_v_decile_paths", sc.V_DECILES, "Figure 1 data (NA-12): CAR^lvl paths by V decile", False),
    ("f1_rg_class_paths", sc.RG_CLASSES, "Figure 1 data (NA-12): CAR^lvl paths by RG class", False),
    (
        "f2_drift_vs_g",
        sc.DRIFT,
        "Figure 2 data (NA-12): sign(G)·y2 by |G| bin and news-strength tercile",
        False,
    ),
    ("f4_monthly_ic", sc.MONTHLY, "Figure 4 data (NA-12): monthly mean daily IC", False),
    ("f5_shapley_shares", sc.SHAPLEY, "Figure 5 data (NA-12): Shapley shares", False),
    ("f8_explanation_ladder", sc.LADDER, "Figure 8 data (NA-12): the explanation ladder", False),
    ("fa_reliability", sc.RELIABILITY, "Appendix data (NA-12): reliability bins", False),
)


def keyed_tables(root: Path) -> list[PaperTable]:
    src = sc.Sources(root)
    out = []
    for name, path, title, latex in KEYED:
        df = src.keyed(path)
        df["key"] = df["key"].str.replace(
            "/", ":", regex=False
        )  # model ids hold "/", which the cite syntax uses
        if df["key"].duplicated().any():
            raise ValueError(f"{name}: keys collide once '/' becomes ':'")
        notes: tuple[str, ...] = ()
        if name == "t20_strategies":
            notes = (
                "Sharpe ratios annualized with √252; costs per side on both legs and the SPY hedge; "
                "no borrow "
                "cost. DSR with n_trials from the trials ledger. The 'exploratory' family is the "
                "MA-cross add-on.",
                NOTE_EXPLORATORY.replace("Exploratory (post hoc)", "Exploratory rows (post hoc)"),
            )
        out.append(PaperTable(name, title, df, notes, (path,), latex=latex))
    return out


# --- flattened results --------------------------------------------------------------------------------------


def _scalar(v: Any) -> bool:
    return v is None or isinstance(v, str | int | float | bool)


def flatten(obj: Mapping[str, Any], path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """One row per object that holds scalars, keyed by its path (":"-joined); scalar lists become text."""
    rows: list[dict[str, Any]] = []
    own = {k: v for k, v in obj.items() if _scalar(v)}
    own |= {
        k: "; ".join(str(e) for e in v)
        for k, v in obj.items()
        if isinstance(v, list) and all(_scalar(e) for e in v)
    }
    if own and path:
        rows.append({"key": ":".join(path), **own})
    for k, v in obj.items():
        if isinstance(v, Mapping):
            rows += flatten(v, (*path, str(k)))
        elif isinstance(v, list) and v and all(isinstance(e, Mapping) for e in v):
            for i, e in enumerate(v):
                rows += flatten(e, (*path, str(k), str(i)))
    return rows


def flattened_tables(root: Path) -> list[PaperTable]:
    exp = _read_json(root, EXPLORATORY_JSON)
    ma = _read_json(root, MA_CROSS_JSON)
    return [
        PaperTable(
            "t24_exploratory_d0_signal",
            "Where the D0 signal lives (NA-12 §13): earnings days, size tiers, months, companies, "
            "market state",
            _frame(flatten({k: v for k, v in exp.items() if isinstance(v, Mapping)})),
            (
                NOTE_EXPLORATORY,
                "Copied from artifacts/NA-12/results/exploratory_d0_signal.json; key = JSON path.",
            ),
            (EXPLORATORY_JSON,),
            latex=False,
        ),
        PaperTable(
            "t25_ma_cross",
            "News and an MA20/MA50 cross (NA-13 §9, operator item 9): group statistics and the no-news fade",
            _frame(flatten(ma)),
            (NOTE_EXPLORATORY, "Copied from artifacts/NA-13/results/ma_cross.json; key = JSON path."),
            (MA_CROSS_JSON,),
        ),
    ]


# --- records ------------------------------------------------------------------------------------------------


def release_dates(root: Path) -> PaperTable:
    """Decision-model release dates against the sample (NA-05 catalog; Laya from the operator; the anchor's
    checkpoint month from NA-12)."""
    end = load_splits().splits["test"].end
    cat = {m["id"]: m for m in _read_json(root, CATALOG)["models"]}
    op = yaml.safe_load((root / OPERATOR).read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = [
        {
            "key": "sample_end",
            "name": "end of the test period (configs/splits.yaml)",
            "date": end.isoformat(),
            "days_after_sample_end": 0,
            "source": "configs/splits.yaml",
        },
    ]
    laya = op["laya_release"]
    d = date.fromisoformat(laya["date"])
    rows.append(
        {
            "key": "laya",
            "name": laya["name"],
            "date": d.isoformat(),
            "days_after_sample_end": (d - end).days,
            "source": laya["source"],
        }
    )
    for key, model in (
        ("drex_v2", "nace-ai/drex-v2.0"),
        ("d1_ultra", "liquid/d1-ultra"),
        ("span_02", "respan/span-02"),
    ):
        d = date.fromisoformat(cat[model]["created_iso"])
        rows.append(
            {
                "key": key,
                "name": model,
                "date": d.isoformat(),
                "days_after_sample_end": (d - end).days,
                "source": f"{CATALOG} (created)",
            }
        )
    anchor = _read_json(root, MONTHLY_JSON)["release"]["anchor"]
    rows.append(
        {
            "key": "anchor",
            "name": "answerdotai/ModernBERT-large checkpoint (the anchor)",
            "date": anchor["date"],
            "days_after_sample_end": math.nan,
            "source": anchor["source"],
        }
    )
    return PaperTable(
        "t21_release_dates",
        "Release dates of the decision models against the sample (test period ends at sample_end)",
        _frame(rows),
        ("Days after the end of the test period; the anchor's checkpoint is known to the month only.",),
        (CATALOG, OPERATOR, MONTHLY_JSON, "configs/splits.yaml"),
    )


def _spend(path: Path) -> tuple[dict[str, float], int]:
    by: dict[str, float] = {}
    n = 0
    with path.open("rb") as fh:
        for line in fh:
            if b'"event":"spend"' not in line:
                continue
            rec = json.loads(line)
            by[rec["chunk"]] = by.get(rec["chunk"], 0.0) + float(rec["usd"])
            n += 1
    return by, n


def _count(path: Path, needle: bytes | None = None) -> int:
    with path.open("rb") as fh:
        return sum(1 for line in fh if line.strip() and (needle is None or needle in line))


def _report_number(root: Path, rel: str, pattern: str) -> float:
    m = re.search(pattern, (root / rel).read_text(encoding="utf-8"))
    if m is None:
        raise ValueError(f"{rel}: no match for {pattern!r}")
    return float(m.group(1))


def spend(root: Path, ledgers: Path) -> PaperTable:
    """Spend and requests from the ledgers (read only), the caps from configs/project.yaml, Kaggle
    GPU-hours from
    the NA-08 and NA-11 REPORTs (Kaggle keeps no ledger here)."""
    by, n_spend = _spend(ledgers / "spend.jsonl")
    proj = load_project()
    k08 = _report_number(root, NA08_REPORT, r"\*\*Kaggle \(free tier\):\*\* ([0-9.]+) GPU-hours")
    k11 = _report_number(root, NA11_REPORT, r"Kaggle GPU-hours \| no: ([0-9.]+) h used")
    rows: list[dict[str, Any]] = [
        {
            "key": "openrouter_total",
            "item": "OpenRouter spend, all chunks (USD)",
            "value": sum(by.values()),
            "cap": proj.budget.total_usd,
            "source": "ledgers/spend.jsonl (Σ usd of spend lines)",
        },
    ]
    rows += [
        {
            "key": f"openrouter:{chunk}",
            "item": f"OpenRouter spend, {chunk} (USD)",
            "value": usd,
            "source": "ledgers/spend.jsonl",
        }
        for chunk, usd in sorted(by.items())
    ]
    rows += [
        {
            "key": "openrouter_spend_lines",
            "item": "spend lines in the ledger",
            "value": float(n_spend),
            "source": "ledgers/spend.jsonl",
        },
        {
            "key": "fmp_requests",
            "item": "FMP requests (NA-10)",
            "value": float(_count(ledgers / "fmp_requests.jsonl", b'"event":"request"')),
            "cap": float(proj.fmp_request_cap),
            "source": "ledgers/fmp_requests.jsonl",
        },
        {
            "key": "kaggle_na08_gpu_hours",
            "item": "Kaggle GPU-hours, NA-08 (training)",
            "value": k08,
            "source": NA08_REPORT,
        },
        {
            "key": "kaggle_na11_gpu_hours",
            "item": "Kaggle GPU-hours, NA-11 (test inference)",
            "value": k11,
            "source": NA11_REPORT,
        },
        {
            "key": "kaggle_total_gpu_hours",
            "item": "Kaggle GPU-hours, NA-08 + NA-11",
            "value": k08 + k11,
            "source": "the sum of the two rows above",
        },
        {
            "key": "trials",
            "item": "rows of the trials ledger (the DSR's N)",
            "value": float(_count(ledgers / "trials.jsonl")),
            "source": "ledgers/trials.jsonl",
        },
        {
            "key": "test_access",
            "item": "lines of the test-access ledger",
            "value": float(_count(ledgers / "test_access.jsonl")),
            "source": "ledgers/test_access.jsonl",
        },
    ]
    return PaperTable(
        "t22_spend",
        "Spend and requests of the whole project (ledgers; caps from configs/project.yaml)",
        _frame(rows),
        ("NA-12, NA-13 and NA-14 made no API call, Kaggle run or FMP request.",),
        (
            "ledgers/spend.jsonl",
            "ledgers/fmp_requests.jsonl",
            "ledgers/trials.jsonl",
            "ledgers/test_access.jsonl",
            NA08_REPORT,
            NA11_REPORT,
            "configs/project.yaml",
        ),
    )


OVERLAP: Final = (
    ("laya_fin:D2:close_t+5", "S-CONV|laya_fin|D2|u|close_t+5|all", "gap_fade|-|D2|gap|close_t+5|all"),
    ("laya_fin:D1:close_t", "S-CONV|laya_fin|D1|u|close_t|all", "gap_fade|-|D1|gap|close_t|all"),
    ("d1_ultra:D2:close_t+5", "S-CONV|d1_ultra|D2|u|close_t+5|all", "gap_fade|-|D2|gap|close_t+5|all"),
    ("anchor:D2:close_t+5", "S-CONV|anchor|D2|u|close_t+5|all", "gap_fade|-|D2|gap|close_t+5|all"),
)


def sconv_overlap(layout: Layout) -> PaperTable:
    """How much S-CONV is the gap fade, from NA-13's stored test positions and daily books (NA-13 REPORT
    §4)."""
    pos = io.read_parquet(POSITIONS, columns=["rule", "session", "symbol_id", "side"], layout=layout)
    books = io.read_parquet(BOOKS, columns=["rule", "tier", "session", "gross"], layout=layout)
    books = books[books["tier"] == "all"]
    rows = []
    for key, rule, bench in OVERLAP:
        a = (
            pos[pos["rule"] == rule]
            .drop_duplicates(["session", "symbol_id"])
            .set_index(["session", "symbol_id"])
        )
        b = (
            pos[pos["rule"] == bench]
            .drop_duplicates(["session", "symbol_id"])
            .set_index(["session", "symbol_id"])
        )
        shared = a.index.intersection(b.index)
        ga = books[books["rule"] == rule].set_index("session")["gross"]
        gb = books[books["rule"] == bench].set_index("session")["gross"]
        common = ga.index.intersection(gb.index)
        rows.append(
            {
                "key": key,
                "book": rule,
                "benchmark": bench,
                "n_positions": len(a),
                "n_benchmark": len(b),
                "shared_share": len(shared) / len(a),
                "same_side_share": float((a.loc[shared, "side"] == b.loc[shared, "side"]).mean()),
                "corr_gross": float(np.corrcoef(ga.loc[common], gb.loc[common])[0, 1]),
                "n_days": len(common),
            }
        )
    return PaperTable(
        "t26_sconv_overlap",
        "S-CONV against the price-only gap fade on test: shared positions, same side, daily-return "
        "correlation",
        _frame(rows),
        (
            "Positions are (session, symbol) pairs of the book; shared_share = |book ∩ gap fade| / |book|; "
            "same_side_share among the shared; corr_gross = Pearson correlation of the daily gross "
            "returns (tier "
            "all) over common sessions. Recomputed from work/strategy (NA-13) because NA-13 REPORT §4 states "
            "these numbers but no file held them.",
        ),
        (f"work/{POSITIONS}", f"work/{BOOKS}"),
    )


def derived(root: Path) -> PaperTable:
    """The one sum a caption cites (Laya-Fin's RG events), with its formula."""
    rg = pd.read_csv(root / sc.RG_CLASSES)
    m = rg[(rg["model"] == "laya_fin") & (rg["figure"] == "rg_class_signed") & (rg["point"] == "car_post0")]
    return PaperTable(
        "t30_derived",
        "Sums of figure-data cells cited in captions",
        _frame(
            [
                {
                    "key": "laya_fin:rg_events",
                    "value": int(m["n_group"].sum()),
                    "formula": "Σ n_group of Laya-Fin's three RG classes (rg_class_signed, car_post0)",
                    "source": sc.RG_CLASSES,
                }
            ]
        ),
        sources=(sc.RG_CLASSES,),
    )


# --- LaTeX --------------------------------------------------------------------------------------------------

_SPECIAL: Final = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
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
    "²": r"\textsuperscript{2}",
    "·": r"$\cdot$",
    "×": r"$\times$",
    "÷": r"$\div$",
    "Δ": r"$\Delta$",
    "Σ": r"$\Sigma$",
    "α": r"$\alpha$",
    "β": r"$\beta$",
    "θ": r"$\theta$",
    "κ": r"$\kappa$",
    "λ": r"$\lambda$",
    "ρ": r"$\rho$",
    "σ": r"$\sigma$",
    "τ": r"$\tau$",
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
    "†": r"\textsuperscript{\dag}",
    "‡": r"\textsuperscript{\ddag}",
    "…": r"\ldots{}",
    "Ñ": r"\~{N}",
}
_HAT: Final = "\u0302"


def tex_text(s: str, *, breakable: bool = False) -> str:
    """Plain text for LaTeX (T1 encoding): specials escaped, the symbols used in the tables as commands; with
    ``breakable`` a line may break after "|", ":" or "_" (long keys and rule names in a wrapped column)."""
    out: list[str] = []
    for ch in s:
        if breakable and out and out[-1] in (_SPECIAL["|"], ":", _SPECIAL["_"]):
            out[-1] += r"\allowbreak{}"
        if ch == _HAT:
            if not out:
                raise ValueError(f"a combining hat without a letter in {s!r}")
            out[-1] = r"\^{" + out[-1] + "}"
        elif ch in _SPECIAL:
            out.append(_SPECIAL[ch])
        elif ch in _UNICODE:
            out.append(_UNICODE[ch])
        elif ord(ch) > 127:
            raise ValueError(f"no LaTeX for {ch!r} (U+{ord(ch):04X}) in {s!r}")
        else:
            out.append(ch)
    return "".join(out)


def tex_number(cell: str) -> str:
    """A formatted number in math mode, with a true minus sign and ∞."""
    if cell == "—":
        return "---"
    m = re.fullmatch(r"(-?)([0-9.]+)e([+-])0*([0-9]+)", cell)
    if m:
        sign = "-" if m.group(3) == "-" else ""
        return f"${m.group(1)}{m.group(2)}\\times 10^{{{sign}{m.group(4)}}}$"
    body = cell.replace("−∞", r"-\infty").replace("∞", r"\infty").replace(",", "{,}")
    return f"${body}$"


def header(col: str) -> str:
    for a, b in HEADER_PHRASES:
        col = col.replace(a, b)
    words = [HEADER_WORDS.get(w, w) for w in col.split("_")]
    return " ".join(words)


def display(v: str) -> str:
    return DISPLAY.get(v, v)


def flags(df: pd.DataFrame) -> set[str]:
    """Which labels a table needs: vendor-label rows, the anchor, span-02."""
    text = " ".join(
        str(v)
        for c in df.columns
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
        for v in df[c].dropna().unique()
    )
    out = set()
    if re.search(r"(^|[^a-z])(sentiment|tags_gbm)([^a-z]|$)", text):
        out.add("vendor")
    if re.search(r"(^|[^a-z_])anchor([^a-z]|$)", text):
        out.add("anchor")
    if "span_02" in text or "span-02" in text:
        out.add("span")
    return out


def latex(t: PaperTable) -> str:
    df = t.frame
    view = LATEX_VIEW.get(t.name)
    if view is not None:
        keep, columns = view
        df = df[keep(df)] if keep is not None else df
        df = df[[c for c in columns if c in df.columns]]
    elif df.shape[1] > 1:
        df = df.drop(columns=["key"])
    cols = list(df.columns)
    numeric = {
        c: bool(pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])) for c in cols
    }
    marks = flags(t.frame)
    notes = list(t.notes)
    if view is not None:
        notes.append(
            f"Selected columns{' and rows' if view[0] is not None else ''}; every cell is in {t.name}.csv."
        )
    if "vendor" in marks:
        notes.append(NOTE_VENDOR)
    if "anchor" in marks:
        notes.append(NOTE_ANCHOR)
    if "span" in marks and not any("S5" in n for n in notes):
        notes.append(NOTE_SPAN)

    def cell(v: Any, c: str, wrapped: bool = False) -> str:
        if isinstance(v, float | int | np.floating | np.integer) and not isinstance(v, bool | np.bool_):
            x = v.item() if isinstance(v, np.generic) else v
            return tex_number(kz.fmt(x, c))
        if isinstance(v, bool | np.bool_):
            return "yes" if bool(v) else "no"
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "---"
        return tex_text(display(str(v)), breakable=wrapped)

    rows = list(df.itertuples(index=False, name=None))
    shown = {
        c: max(
            [len(header(c))]
            + [len(display(str(r[i]))) if not numeric[c] else len(kz.fmt(r[i], c)) for r in rows]
        )
        for i, c in enumerate(cols)
    }
    wrap = {c: not numeric[c] and shown[c] > WRAP_CHARS for c in cols}
    spec = "".join(
        "r" if numeric[c] else (rf">{{\raggedright\arraybackslash}}p{{{WRAP_EM}em}}" if wrap[c] else "l")
        for c in cols
    )
    est = sum(min(shown[c], 2 * WRAP_EM) * PT_PER_CHAR + 6.0 for c in cols)
    head = " & ".join(tex_text(header(c)) for c in cols) + r" \\"
    body = [" & ".join(cell(v, c, wrap[c]) for c, v in zip(cols, row, strict=True)) + r" \\" for row in rows]
    note_tex = (
        r"\par\smallskip{\footnotesize\raggedright " + " ".join(tex_text(n) for n in notes) + r"\par}"
        if notes
        else ""
    )
    cap = tex_text(t.title)
    label = f"tab:{t.name}"
    lines = [f"% {t.name} (NA-14, from {', '.join(t.sources)})"]
    if len(df) > LONG_ROWS:
        wide = est > PORTRAIT_PT
        lines += [
            r"\begin{landscape}" if wide else "",
            r"{\scriptsize\setlength{\tabcolsep}{3pt}",
            f"\\begin{{longtable}}{{{spec}}}",
            f"\\caption{{{cap}}}\\label{{{label}}}\\\\",
            r"\toprule",
            head,
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            head,
            r"\midrule",
            r"\endhead",
            r"\bottomrule",
            r"\endfoot",
            *body,
            r"\end{longtable}",
            note_tex,
            "}",
            r"\end{landscape}" if wide else "",
        ]
    else:
        env = "table*" if len(cols) > WIDE_COLS else "table"
        width = r"\textwidth" if env == "table*" else r"\linewidth"
        lines += [
            f"\\begin{{{env}}}[tbp]",
            r"\centering\small",
            f"\\caption{{{cap}}}\\label{{{label}}}",
            f"\\begin{{adjustbox}}{{max width={width}}}",
            f"\\begin{{tabular}}{{{spec}}}",
            r"\toprule",
            head,
            r"\midrule",
            *body,
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{adjustbox}",
            note_tex,
            f"\\end{{{env}}}",
        ]
    return "\n".join(x for x in lines if x) + "\n"


MASTER_PREAMBLE: Final = r"""% All NA-14 tables in one document (compile with pdflatex, LuaLaTeX or XeLaTeX).
\documentclass[10pt]{article}
\usepackage[T1]{fontenc}
\usepackage[margin=0.8in]{geometry}
\usepackage{array,booktabs,longtable,graphicx,amssymb,adjustbox,pdflscape}
\begin{document}
"""


# --- keys and files -----------------------------------------------------------------------------------------


def _plain(x: Any) -> Any:
    if isinstance(x, float) and math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return x.item() if hasattr(x, "item") else x


def keys_of(t: PaperTable, na12: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """ "<table>/<key>/<column>" → value for every non-empty cell (NA-12's ``keys_of``). An NA-12 copy takes
    NA-12's own keys, which hold the full precision its CSV rounds to 10 digits."""
    if t.copy_of and na12 is not None:
        return {k: v for k, v in na12.items() if k.startswith(f"{t.name}/")}
    out: dict[str, Any] = {}
    for row in t.frame.to_dict("records"):
        for c, v in row.items():
            if c == "key" or v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
                continue
            out[f"{t.name}/{row['key']}/{c}"] = _plain(v)
    return out


def build(layout: Layout | None = None) -> list[PaperTable]:
    lay = resolve_layout(layout)
    root = lay.root
    builders: list[Callable[[], list[PaperTable]]] = [
        lambda: na12_tables(root),
        lambda: keyed_tables(root),
        lambda: flattened_tables(root),
        lambda: [release_dates(root), spend(root, lay.ledgers), sconv_overlap(lay), derived(root)],
    ]
    tables = [t for b in builders for t in b()]
    names = [t.name for t in tables]
    if len(set(names)) != len(names):
        raise ValueError("duplicate table names")
    return sorted(tables, key=lambda t: _order(t.name))


def _order(name: str) -> tuple[int, int, str]:
    m = re.match(r"t(\d+)", name)
    return (0, int(m.group(1)), name) if m else (1, 0, name)


def write(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    d = lay.root / sc.TABLES
    d.mkdir(parents=True, exist_ok=True)
    tables = build(lay)
    na12 = kz.load(lay.root / sc.NA12_TAB / "keys.json")
    allkeys: dict[str, Any] = {}
    index = []
    master = [MASTER_PREAMBLE]
    for t in tables:
        files = [f"{t.name}.csv"]
        if t.copy_of:
            shutil.copyfile(lay.root / t.copy_of, d / f"{t.name}.csv")
        else:
            t.frame.to_csv(d / f"{t.name}.csv", index=False, lineterminator="\n")
        if t.latex:
            (d / f"{t.name}.tex").write_text(latex(t), encoding="utf-8")
            files.append(f"{t.name}.tex")
            master.append(f"\\input{{{t.name}.tex}}\n\\clearpage\n")
        allkeys |= keys_of(t, na12)
        index.append(
            {
                "name": t.name,
                "title": t.title,
                "columns": list(t.frame.columns),
                "rows": len(t.frame),
                "notes": list(t.notes),
                "sources": list(t.sources),
                "copy_of": t.copy_of,
                "files": files,
            }
        )
    master.append("\\end{document}\n")
    (d / "paper_tables.tex").write_text("".join(master), encoding="utf-8")
    (d / "keys.json").write_text(json.dumps(allkeys, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (d / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return {"tables": len(tables), "keys": len(allkeys)}


def main(argv: Sequence[str] | None = None) -> int:
    print(json.dumps(write(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
