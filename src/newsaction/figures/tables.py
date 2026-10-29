"""NA-14 S3: the paper's tables as keyed CSVs, with the keys its captions and LaTeX cite (PRD NA-14 S3–S4).

    uv run python -m newsaction.figures.tables

Writes ``artifacts/NA-14/tables/<name>.csv``, ``keys.json`` ("<table>/<key>/<column>" → value, NA-12's
convention) and ``index.json``. The LaTeX of the paper tables is a separate view of these cells
(``figures.latex``); the CSVs are the record. Four kinds of table:

- **Copies.** NA-12's 20 tables (CSV byte for byte; ``keys.json`` equal to NA-12's), NA-13's strategy table
  and the figure sources of NA-03, NA-06, NA-07, NA-11 and NA-12, each with its row ``key`` in front (the
  figure-data copies are data only).
- **Flattened results.** NA-12's exploratory "where the D0 signal lives" JSON, NA-13's MA-cross JSON and the
  val-B step of NA-11's run of the frozen spec, one row per object of scalars, so their numbers can be cited.
  The values are copied.
- **Records.** Release dates (NA-05 catalog; Laya from the operator), the spend and request ledgers, the
  S-CONV / gap-fade overlap of NA-13's stored positions (NA-13 REPORT §4 states it; no file held it), NA-12's
  A3.5 market row for the appendix (t31) and the summary of PREREG §15 (t34; the operator's revision pass).
- **Simple aggregations of stored files**, each with its formula: the RG events a caption cites (t30), the
  quantiles of NA-13's 100 random-signal books per universe (t33) and the break-even cost of each of NA-13's
  books, gross mean ÷ turnover (t35).

Every table has a paper section (``SECTION``, as in ``docs/paper_outline.md``). Exploratory material appears
only in the appendix: the exploratory tables are appendix tables, and their rows never reach a main table
(``EXPLORATORY_ROWS`` marks the exploratory rows of the other tables; ``index.json`` lists them).
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
DEVIATIONS: Final = f"{sc.ARTIFACTS}/inputs/prereg_deviations.yaml"
PREREG: Final = "docs/PREREG.md"
CATALOG: Final = "artifacts/NA-05/catalog.json"
MONTHLY_JSON: Final = "artifacts/NA-12/results/monthly_ic.json"
EXPLORATORY_JSON: Final = "artifacts/NA-12/results/exploratory_d0_signal.json"
MA_CROSS_JSON: Final = "artifacts/NA-13/results/ma_cross.json"
SMOKE_JSON: Final = "artifacts/NA-11/spec_smoke_val_b.json"
NA12_INDEX: Final = f"{sc.NA12_TAB}/index.json"
NA08_REPORT: Final = "artifacts/NA-08/REPORT.md"
NA11_REPORT: Final = "artifacts/NA-11/REPORT.md"
POSITIONS: Final = "strategy/positions_test.parquet"
BOOKS: Final = "strategy/books_test.parquet"
PLACEBO: Final = "strategy/placebo_test.parquet"

VENDOR: Final = ("sentiment", "tags_gbm")
EXPLORATORY_TABLES: Final = (
    "t17_sector_exploratory",
    "t24_exploratory_d0_signal",
    "t25_ma_cross",
    "t31_market_replication",
)
# Exploratory rows of the other tables: the CSV keeps them; the LaTeX of the table leaves them out and says
# where the appendix shows them (operator check 5e; tests/test_figures_exploratory.py).
EXPLORATORY_ROWS: Final[dict[str, tuple[Callable[[pd.DataFrame], pd.Series], str]]] = {
    "t11_explanation_share_theta": (
        lambda df: df["key"] == "market:r2",
        "The A3.5 market-level replication (exploratory) is in Table t31.",
    ),
    "t20_strategies": (
        lambda df: df["family"] == "exploratory",
        "The exploratory MA-cross fade (post hoc) is in Table t25 and Figure A15.",
    ),
}
# The paper section of every table (docs/paper_outline.md): 1–7 the main text, "appendix" the rest. A
# table's LaTeX may sit in a different place (the main tables T1–T6 draw on these; ``figures.latex``).
MAIN_SECTIONS: Final = ("1", "2", "3", "4", "5", "6", "7")
SECTION: Final = {
    "t1_primary": "3",
    "t1b_primary_by_model": "3",
    "t2_h2_over_under": "4",
    "t3_ic": "3",
    "t4_secondary": "4",
    "t5_heterogeneity": "4",
    "t6_convergence_ladder": "4",
    "t7_gap_closure": "4",
    "t8_tracking_error": "4",
    "t9_convergence_cuts": "4",
    "t10_explanation_ladder": "5",
    "t11_explanation_share_theta": "5",
    "t12_question_battery": "5",
    "t13_shapley": "4",
    "t14_model_comparison": "1",
    "t15_calibration": "appendix",
    "t16_robustness": "appendix",
    "t17_sector_exploratory": "appendix",
    "t18_probes_val_a": "appendix",
    "t19_monthly_ic": "appendix",
    "t20_strategies": "6",
    "t21_release_dates": "7",
    "t22_spend": "2",
    "t23_company_identification": "7",
    "t24_exploratory_d0_signal": "appendix",
    "t25_ma_cross": "appendix",
    "t26_sconv_overlap": "6",
    "t27_tournament": "1",
    "t28_filter_frontier": "2",
    "t29_encoding": "appendix",
    "t30_derived": "4",
    "t31_market_replication": "appendix",
    "t32_val_b_ic": "3",
    "t33_placebo_sharpe": "6",
    "t34_prereg_deviations": "appendix",
    "t35_break_even": "6",
    "f1_v_decile_paths": "4",
    "f1_rg_class_paths": "4",
    "f2_drift_vs_g": "4",
    "f4_monthly_ic": "appendix",
    "f5_shapley_shares": "appendix",
    "f8_explanation_ladder": "5",
    "fa_reliability": "appendix",
}
NOTE_EXPLORATORY: Final = (
    "Exploratory (post hoc): requested after unblinding; no hypothesis, outside every family, no claim."
)


@dataclass(frozen=True)
class PaperTable:
    name: str
    title: str
    frame: pd.DataFrame
    notes: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
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
        "NA-13 strategies, test and val-B (reference): every pre-registered book, S-CONV first, and the "
        "benchmarks",
    ),
    (
        "t23_company_identification",
        sc.COMPANY_ID,
        "Company identification with activity-matched distractors (NA-11; val-A, masked states)",
    ),
    (
        "t27_tournament",
        sc.TOURNAMENT,
        "NA-06 zero-shot tournament (val-A stage-1 sample): daily IC, cost per 1,000 decisions, MCS "
        "membership, §8.3 screens",
    ),
    (
        "t28_filter_frontier",
        sc.FRONTIER,
        "NA-03 importance filters on val-A: selection share and recall by budget",
    ),
    ("t29_encoding", sc.ENCODING, "NA-07 encodings of numbers in states (val-A search, val-B confirmation)"),
    ("f1_v_decile_paths", sc.V_DECILES, "Figure 3 data (NA-12): CAR^lvl paths by V decile"),
    ("f1_rg_class_paths", sc.RG_CLASSES, "Figure 4 data (NA-12): CAR^lvl paths by RG class"),
    ("f2_drift_vs_g", sc.DRIFT, "Figure 4 data (NA-12): sign(G)·y2 by |G| bin and news-strength tercile"),
    ("f4_monthly_ic", sc.MONTHLY, "Appendix Figure A6 data (NA-12): monthly mean daily IC"),
    ("f5_shapley_shares", sc.SHAPLEY, "NA-12 Shapley shares (not drawn: their totals are about zero)"),
    ("f8_explanation_ladder", sc.LADDER, "Figure 7 data (NA-12): the explanation ladder"),
    ("fa_reliability", sc.RELIABILITY, "Appendix Figure A4 data (NA-12): reliability bins"),
)


def keyed_tables(root: Path) -> list[PaperTable]:
    src = sc.Sources(root)
    out = []
    for name, path, title in KEYED:
        df = src.keyed(path)
        df["key"] = df["key"].str.replace("/", ":", regex=False)  # model ids hold "/", which cites use
        if df["key"].duplicated().any():
            raise ValueError(f"{name}: keys collide once '/' becomes ':'")
        notes: tuple[str, ...] = ()
        if name == "t20_strategies":
            notes = (
                "Sharpe ratios annualized with √252; costs per side on both legs and the SPY hedge; "
                "no borrow cost. DSR with n_trials from the trials ledger.",
            )
        out.append(PaperTable(name, title, df, notes, (path,)))
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


SMOKE_MODELS: Final = (
    ("laya_fin", "laya_fin"),
    ("anchor", "anchor"),
    ("laya_zs", "local/laya-typed-decisions"),
)


def flattened_tables(root: Path) -> list[PaperTable]:
    exp = _read_json(root, EXPLORATORY_JSON)
    ma = _read_json(root, MA_CROSS_JSON)
    ic = _read_json(root, SMOKE_JSON)["steps"]["ic_targets"]["result"]
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
        ),
        PaperTable(
            "t25_ma_cross",
            "News and an MA20/MA50 cross (NA-13 §9, operator item 9): group statistics and the no-news fade",
            _frame(flatten(ma)),
            (NOTE_EXPLORATORY, "Copied from artifacts/NA-13/results/ma_cross.json; key = JSON path."),
            (MA_CROSS_JSON,),
        ),
        PaperTable(
            "t32_val_b_ic",
            "Val-B daily ICs of N̂_W0 with z_cc, z_on and z_id (NA-11's run of the frozen spec on val-B, "
            "before the freeze)",
            _frame(
                {"key": key, "model_id": mid, **ic[mid], "source": f"{SMOKE_JSON} (steps.ic_targets)"}
                for key, mid in SMOKE_MODELS
            ),
            (
                "Copied from the val-B smoke run of NA-11 (production.smoke_spec), the frozen spec's code on "
                "val-B; it covers the trained and zero-shot Laya models only, so the API models have no "
                "val-B "
                "IC with z_on or z_id.",
            ),
            (SMOKE_JSON,),
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
    """Spend and requests from the ledgers (read only), the caps from configs/project.yaml, Kaggle GPU-hours
    from the NA-08 and NA-11 REPORTs (Kaggle keeps no ledger here)."""
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
            "same_side_share among the shared; corr_gross = Pearson correlation of the daily gross returns "
            "(tier all) over common sessions. Recomputed from work/strategy (NA-13) because NA-13 REPORT §4 "
            "states these numbers but no file held them.",
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


BREAK_EVEN: Final = "ann_return_gross ÷ 252 ÷ turnover_daily × 10⁴ (NA-13 REPORT §6: gross mean ÷ turnover)"


def break_even(root: Path) -> PaperTable:
    """The break-even cost per side of every non-empty test book of NA-13, in basis points: the cost at which
    its mean net return is zero, gross mean ÷ turnover (NA-13 REPORT §6 states some; no file held them)."""
    st = pd.read_csv(root / sc.STRATEGY)
    t = st[(st["split"] == "test") & st["turnover_daily"].notna() & st["ann_return_gross"].notna()]
    return PaperTable(
        "t35_break_even",
        "Break-even cost per side of each test book (NA-13): the cost at which the mean net return is zero",
        _frame(
            {
                "key": str(r["rule"]),
                "ann_return_gross": float(r["ann_return_gross"]),
                "turnover_daily": float(r["turnover_daily"]),
                "break_even_bp": float(r["ann_return_gross"]) / 252.0 / float(r["turnover_daily"]) * 1e4,
                "formula": BREAK_EVEN,
                "source": f"{sc.STRATEGY} (split test)",
            }
            for r in t.to_dict("records")
        ),
        (
            "Net daily return = gross − cost × turnover (NA-13 strategy.costs), so the mean net return is "
            "zero at "
            "cost = mean gross ÷ mean turnover; ann_return_gross and turnover_daily are copied from NA-13's "
            "strategy table.",
        ),
        (sc.STRATEGY,),
    )


MARKET_ROW: Final = ("t11_explanation_share_theta", "market:r2")


def market_replication(root: Path) -> PaperTable:
    """NA-12's A3.5 market-level replication, the exploratory row of t11, for the appendix (its non-empty
    cells copied)."""
    name, key = MARKET_ROW
    path = f"{sc.NA12_TAB}/{name}.csv"
    df = pd.read_csv(root / path)
    row = df[df["key"] == key].dropna(axis=1, how="all")
    if len(row) != 1:
        raise ValueError(f"{path}: {len(row)} rows with key {key!r}")
    return PaperTable(
        "t31_market_replication",
        "A3.5 market-level replication (exploratory; d1-ultra): out-of-sample R² of SPY's daily return on "
        "the model's reading of the market news",
        _frame([{**{str(c): v for c, v in row.iloc[0].items()}, "source": f"{path} (row {key})"}]),
        (
            "Exploratory (PREREG A3.5: optional, exploratory): outside every family, no claim. The row of "
            "t11_explanation_share_theta.csv (NA-12) that the LaTeX of t11 leaves out; fit on validation, "
            "evaluated on the test sessions (n).",
        ),
        (path,),
    )


QUANTILES: Final = (("q05", 0.05), ("q50", 0.5), ("q95", 0.95))
PLACEBO_COLUMNS: Final = ("sharpe_gross", "sharpe_net_5", "sharpe_net_10", "sharpe_net_20")


def placebo_quantiles(placebo: pd.DataFrame) -> pd.DataFrame:
    """The 5th, 50th and 95th percentile (numpy's linear rule, as NA-13) of the annualized Sharpe ratios of
    each universe's random-signal books."""
    rows = []
    for universe, g in placebo.groupby("universe", sort=True):
        point, exit_, _ = str(universe).split("|")
        rec: dict[str, Any] = {"key": str(universe), "point": point, "exit": exit_, "n_books": len(g)}
        for col in PLACEBO_COLUMNS:
            x = g[col].to_numpy(dtype=float)
            for tag, q in QUANTILES:
                rec[f"{col}_{tag}"] = float(np.quantile(x, q))
        rows.append(rec)
    return _frame(rows)


def placebo_sharpe(layout: Layout) -> PaperTable:
    """Quantiles of the Sharpe ratios of NA-13's 100 random-signal books per test universe (NA-13 REPORT §7
    states some; no committed file held them)."""
    placebo = io.read_parquet(PLACEBO, columns=["universe", "seed", *PLACEBO_COLUMNS], layout=layout)
    df = placebo_quantiles(placebo)
    df["source"] = f"work/{PLACEBO}"
    return PaperTable(
        "t33_placebo_sharpe",
        "Random-signal placebo (NA-13): 5th, 50th and 95th percentile of the annualized Sharpe ratios of the "
        "100 placebo books of each test universe, gross and net of 5, 10 and 20 bp per side",
        df,
        (
            "numpy.quantile (linear interpolation, as NA-13) over the universe's 100 books (seeds 2027–2126) "
            "in work/strategy/placebo_test.parquet (registered, hash-checked on read). A universe is a "
            "decision point, an exit and a set of events; Laya-Fin's, d1-ultra's and the gap fade's books "
            "of one family share it.",
        ),
        (f"work/{PLACEBO}",),
    )


def _cells(line: str) -> list[str]:
    """The cells of a Markdown table row; a pipe that is escaped or inside a code span is text."""
    cells: list[str] = []
    cur: list[str] = []
    code, prev = False, ""
    for ch in line.strip().strip("|"):
        if ch == "`":
            code = not code
        if ch == "|" and not code and prev != "\\":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        prev = ch
    cells.append("".join(cur).strip())
    return cells


def prereg_rows(text: str) -> list[dict[str, str]]:
    """The rows of PREREG §15 (the Deviations log, split by its amendment headings), in order."""
    log = text[text.index("## 15. Deviations log") :]
    rows = []
    for line in log.splitlines():
        if not re.match(r"^\| 20\d\d-\d\d-\d\d \|", line):
            continue
        cells = _cells(line)
        if len(cells) < 6:
            raise ValueError(f"a §15 row with {len(cells)} cells: {line[:80]}")
        if len(cells) > 6:  # an unescaped pipe in the change text (row 25 quotes "|Price:49.32|Chg%:…")
            cells = [*cells[:3], "|".join(cells[3:-2]), *cells[-2:]]
        rows.append(dict(zip(("date", "chunk", "section", "change", "reason", "timing"), cells, strict=True)))
    return rows


SUMMARY_LENGTH: Final = {"chunk": 12, "change": 58, "reason": 34}  # one line of the one-page table


def prereg_deviations(root: Path) -> PaperTable:
    """One line per row of PREREG §15: its date and timing from the log, the chunk, change and reason in short
    from the author's summary (``inputs/prereg_deviations.yaml``), checked row for row against the log."""
    log = prereg_rows((root / PREREG).read_text(encoding="utf-8"))
    summary = yaml.safe_load((root / DEVIATIONS).read_text(encoding="utf-8"))["rows"]
    if len(summary) != len(log):
        raise ValueError(f"{DEVIATIONS}: {len(summary)} summaries for {len(log)} rows of PREREG §15")
    rows = []
    for i, (s, r) in enumerate(zip(summary, log, strict=True), start=1):
        if int(s["row"]) != i or str(s["date"]) != r["date"]:
            raise ValueError(
                f"{DEVIATIONS}: summary {s.get('row')} ({s.get('date')}) is not §15 row {i} ({r['date']})"
            )
        for col, most in SUMMARY_LENGTH.items():
            if len(str(s[col])) > most:
                raise ValueError(f"{DEVIATIONS}: row {i}'s {col} is longer than {most} characters (one line)")
        timing = r["timing"].split()[0].lower()
        if timing not in ("before", "after"):
            raise ValueError(f"§15 row {i}: timing {r['timing']!r}")
        rows.append(
            {
                "key": f"row:{i:02d}",
                "row": i,
                "date": r["date"],
                "chunk": s["chunk"],
                "change": s["change"],
                "reason": s["reason"],
                "freeze": timing,
            }
        )
    return PaperTable(
        "t34_prereg_deviations",
        "Pre-registration deviations: every row of PREREG §15 in one line",
        _frame(rows),
        (
            "Date and timing (before or after the NA-11 freeze) as in PREREG §15; chunk, change and "
            "reason summarized by NA-14 (inputs/prereg_deviations.yaml); the full text is in the log.",
        ),
        (PREREG, DEVIATIONS),
    )


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
        lambda: [
            release_dates(root),
            spend(root, lay.ledgers),
            sconv_overlap(lay),
            derived(root),
            break_even(root),
            market_replication(root),
            placebo_sharpe(lay),
            prereg_deviations(root),
        ],
    ]
    tables = [t for b in builders for t in b()]
    names = [t.name for t in tables]
    if len(set(names)) != len(names):
        raise ValueError("duplicate table names")
    if set(names) != set(SECTION):
        raise ValueError(f"tables and SECTION differ: {sorted(set(names) ^ set(SECTION))}")
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
    for t in tables:
        if t.copy_of:
            shutil.copyfile(lay.root / t.copy_of, d / f"{t.name}.csv")
        else:
            t.frame.to_csv(d / f"{t.name}.csv", index=False, lineterminator="\n")
        allkeys |= keys_of(t, na12)
        drop = EXPLORATORY_ROWS.get(t.name)
        index.append(
            {
                "name": t.name,
                "title": t.title,
                "section": SECTION[t.name],
                "exploratory": t.name in EXPLORATORY_TABLES,
                "exploratory_rows": sorted(t.frame.loc[drop[0](t.frame), "key"].astype(str)) if drop else [],
                "columns": list(t.frame.columns),
                "rows": len(t.frame),
                "notes": list(t.notes),
                "sources": list(t.sources),
                "copy_of": t.copy_of,
                "files": [f"{t.name}.csv"],
            }
        )
    (d / "keys.json").write_text(json.dumps(allkeys, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (d / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return {"tables": len(tables), "keys": len(allkeys)}


def main(argv: Sequence[str] | None = None) -> int:
    print(json.dumps(write(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
