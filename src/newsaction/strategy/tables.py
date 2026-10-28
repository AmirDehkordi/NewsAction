"""NA-13 S5: the strategy table (CSV, booktabs LaTeX), Figure 7's data and the DSR at the final trial count.

    uv run python -m newsaction.strategy.tables

Run after ``run val_b``, ``run test``, ``ma_cross`` and ``run trials``: the DSR uses n_trials = every row of
``ledgers/trials.jsonl`` at that moment (``dsr.trial_count``), and refuses if NA-13's rows are not yet logged.

- ``artifacts/NA-13/strategy_table.csv``: every book on test and on val-B (reference), S-CONV first; gross and
  net Sharpe at 5 / 10 / 20 bp, annualized return, volatility, max drawdown, turnover, hit rate, the DSR
  (probability and statistic, analytic trial variance), placebo percentiles, capacity; the add-on last.
- ``strategy_table.tex``: the test books in a booktabs tabular (``analysis.tables.to_latex``).
- ``fig7_data.csv``: the test period's cumulative net return at 10 bp (``fig7``): every book, the tier
  sub-books (top100, mid, rest) of the two instruments' ungated books and of the benchmarks, the placebo's
  5th / 50th / 95th percentile path of those universes and the add-on's book.
- ``results/strategy_summary.json``: n_trials and its parts, the DSR settings, the lock reads, row counts.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.analysis.tables import Table, to_latex
from newsaction.config import load_splits
from newsaction.paths import Layout, resolve_layout
from newsaction.strategy import costs as cs
from newsaction.strategy import dsr, run
from newsaction.strategy import ma_cross as ma

TABLE_CSV: Final = f"{run.ARTIFACTS}/strategy_table.csv"
TABLE_TEX: Final = f"{run.ARTIFACTS}/strategy_table.tex"
FIG7: Final = f"{run.ARTIFACTS}/fig7_data.csv"
SUMMARY: Final = "strategy_summary.json"
ROLE: Final = {
    "laya_fin": "primary",
    "d1_ultra": "comparator (model-specific)",
    "anchor": "uninformative",
    "gap_fade": "benchmark (price-only)",
    "vendor_sentiment": "benchmark (possible look-ahead upper bound)",
    "exploratory": "exploratory (operator, after unblinding)",
}
FAMILY_ORDER: Final = ("S-CONV", "S-D0", "S-D1", "S-D2", "gap_fade", "vendor_sentiment", "exploratory")
MODEL_ORDER: Final = ("laya_fin", "d1_ultra", "anchor", None)
SPLIT_ORDER: Final = ("test", "val_b", "validation")
METRICS: Final = (
    "n_days",
    "n_positions",
    "mean_names_per_side",
    "sharpe_gross",
    "sharpe_net_5",
    "sharpe_net_10",
    "sharpe_net_20",
    "ann_return_gross",
    "ann_return_net_10",
    "vol",
    "max_dd_net_10",
    "turnover_daily",
    "hit_rate_net_10",
    "placebo_pct_gross",
    "placebo_pct_net_5",
    "placebo_pct_net_10",
    "placebo_pct_net_20",
    "placebo_pct_mean_net_10",
    "capacity_median_usd",
    "capacity_p10_usd",
)


class TablesError(RuntimeError):
    pass


def _role(family: str, model: str | None) -> str:
    if family in ROLE:
        return ROLE[family]
    return ROLE[model] if model else family


def _nets(daily: pd.DataFrame) -> dict[str, np.ndarray]:
    return {f"{int(bp)}": daily[f"net_{int(bp)}"].to_numpy(dtype=float) for bp in cs.LEVELS_BP}


def _dsr_cols(nets: Mapping[str, np.ndarray], n_trials: int) -> dict[str, float]:
    """The DSR of each daily net series (``tag`` = bp per side)."""
    out: dict[str, float] = {}
    for tag, r in nets.items():
        d = dsr.deflated_sharpe(r, n_trials=n_trials)
        out[f"dsr_prob_net_{tag}"] = d.prob
        out[f"dsr_stat_net_{tag}"] = d.deflated_stat
        out[f"dsr_sr0_net_{tag}"] = d.sr0
        out[f"sharpe_daily_net_{tag}"] = d.sharpe
    return out


def book_rows(lay: Layout, n_trials: int) -> pd.DataFrame:
    rows = []
    for split in run.SPLITS:
        doc = json.loads((lay.root / run.RESULTS / f"books_{split}.json").read_text(encoding="utf-8"))
        daily = io.read_parquet(run.OUT_DAILY.format(split=split), layout=lay)
        daily = daily.loc[daily["tier"] == "all"]
        by_rule = {k: g.sort_values("session") for k, g in daily.groupby("rule")}
        for b in doc["books"]:
            row = {
                "split": split,
                "family": b["family"],
                "model": b["model"],
                "point": b["point"],
                "signal": b["signal"],
                "exit": b["exit"],
                "gated": bool(b["gated"]),
                "role": _role(b["family"], b["model"]),
                "rule": b["rule"],
                "universe": b["universe"],
                "events": b.get("events", 0),
            }
            row.update({k: b.get(k) for k in METRICS})
            g = by_rule.get(b["rule"])
            if g is not None:
                row.update(_dsr_cols(_nets(g), n_trials))
            row["note"] = "" if b.get("n_positions") else "no position (|N̂| < 0.5 for every event)"
            rows.append(row)
    return pd.DataFrame(rows)


def exploratory_rows(lay: Layout, n_trials: int) -> pd.DataFrame:
    doc = json.loads((lay.root / run.RESULTS / ma.RESULT).read_text(encoding="utf-8"))
    daily = io.read_parquet(ma.OUT_BOOKS, layout=lay)
    rows = []
    for period, r in doc["periods"].items():
        b = r["fade_no_news"]
        g = daily.loc[daily["period"] == period].sort_values("session")
        row = {
            "split": period,
            "family": "exploratory",
            "model": None,
            "point": "D2",
            "signal": "ma_cross_fade_no_news",
            "exit": b["exit"],
            "gated": False,
            "role": ROLE["exploratory"],
            "rule": f"exploratory|ma_cross|fade_no_news|{b['exit']}",
            "universe": "",
            "events": b.get("events", 0),
        }
        row.update({k: b.get(k) for k in METRICS})
        row.update(_dsr_cols(_nets(g), n_trials))
        row["note"] = "fade the no-news MA20/MA50 crosses (preamble item 9); design chosen on validation"
        rows.append(row)
    return pd.DataFrame(rows)


def _order(df: pd.DataFrame) -> pd.DataFrame:
    fam = {f: i for i, f in enumerate(FAMILY_ORDER)}
    mod = {m: i for i, m in enumerate(MODEL_ORDER)}
    spl = {s: i for i, s in enumerate(SPLIT_ORDER)}
    pt = {"D2": 0, "D1": 1, "D0": 2}
    key = pd.DataFrame(
        {
            "s": df["split"].map(spl),
            "f": df["family"].map(fam),
            "m": df["model"].map(lambda x: mod.get(x, len(mod))),
            "p": df["point"].map(pt),
            "sig": df["signal"],
            "g": df["gated"].astype(int),
            "e": df["exit"].map(lambda e: int(e.split("+")[1]) if "+" in e else 0),
        }
    )
    return df.loc[key.sort_values(["s", "f", "m", "p", "sig", "g", "e"]).index].reset_index(drop=True)


LATEX_COLS: Final = {
    "book": "Book",
    "exit": "Exit",
    "sharpe_gross": "SR gross",
    "sharpe_net_5": "SR 5bp",
    "sharpe_net_10": "SR 10bp",
    "sharpe_net_20": "SR 20bp",
    "ann_return_net_10": "Ann. ret. 10bp",
    "vol": "Vol",
    "max_dd_net_10": "Max DD 10bp",
    "turnover_daily": "Turnover/day",
    "hit_rate_net_10": "Hit 10bp",
    "dsr_prob_net_10": "DSR 10bp",
    "placebo_pct_gross": "Placebo pct gross",
    "placebo_pct_net_10": "Placebo pct 10bp",
    "capacity_musd": "Capacity $M",
}
MODEL_LABEL: Final = {"laya_fin": "Laya-Fin", "d1_ultra": "d1-ultra", "anchor": "anchor (uninformative)"}


def latex_table(df: pd.DataFrame, n_trials: int) -> Table:
    sp = load_splits().splits["test"]
    t = df.loc[(df["split"] == "test") & (df["n_positions"].fillna(0) > 0)].copy()
    label = t["model"].map(lambda m: MODEL_LABEL.get(m, "") if isinstance(m, str) else "")
    t["book"] = (
        t["family"] + " " + label + " " + t["point"] + " " + t["signal"] + np.where(t["gated"], " gated", "")
    ).str.replace("  ", " ")
    t["exit"] = t["exit"].str.replace("close_", "C_")
    t["capacity_musd"] = t["capacity_median_usd"] / 1e6
    frame = t[list(LATEX_COLS)].rename(columns=LATEX_COLS).reset_index(drop=True)
    notes = (
        f"Test split {sp.start} to {sp.end}; daily net returns of beta-hedged, equal-weight long-short",
        "books; Sharpe annualized with sqrt(252); costs per side on both legs and the SPY hedge; borrow not",
        "modelled.",
        f"DSR: Bailey-Lopez de Prado with the Mertens correction, n_trials = {n_trials} (trials ledger).",
        "Placebo pct: percentile among 100 random-signal books on the same universe.",
        "Vendor sentiment: retrospective labels, a possibly look-ahead-contaminated upper bound.",
    )
    return Table("strategy_table", "NA-13 strategies on the test split", frame, notes)


FIG7_TIER_MODELS: Final = ("laya_fin", "d1_ultra")


def fig7(lay: Layout, df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative net return at 10 bp on test (join ``rule`` to ``strategy_table.csv`` for the labels): every
    book's whole book (tier "all"); the tier sub-books of Laya-Fin's and d1-ultra's ungated books and of the
    benchmarks; the placebo band of those books' universes; the exploratory fade."""
    meta = df.loc[(df["split"] == "test") & (df["n_positions"].fillna(0) > 0)].set_index("rule")
    by_tier = meta.index[
        (~meta["gated"].astype(bool) & meta["model"].isin(list(FIG7_TIER_MODELS)))
        | meta["family"].isin(["gap_fade", "vendor_sentiment"])
    ]
    daily = io.read_parquet(run.OUT_DAILY.format(split="test"), layout=lay)
    daily = daily.loc[(daily["tier"] == "all") | daily["rule"].isin(set(by_tier))]
    daily = daily.sort_values(["rule", "tier", "session"])
    daily["cum_net_10"] = daily.groupby(["rule", "tier"])["net_10"].transform(
        lambda s: np.cumprod(1.0 + s) - 1.0
    )
    out = daily[["rule", "tier", "session", "cum_net_10"]].assign(series="book")
    paths = io.read_parquet(run.OUT_PLACEBO_PATHS.format(split="test"), layout=lay)
    paths = paths.loc[paths["universe"].isin(set(meta.loc[by_tier, "universe"]))]
    paths = paths.rename(columns={"universe": "rule"}).assign(tier="all", series="placebo_band")
    paths["rule"] = "placebo|" + paths["rule"]
    ex = io.read_parquet(ma.OUT_BOOKS, layout=lay)
    ex = ex.loc[ex["period"] == "test"].sort_values("session")
    ex = pd.DataFrame(
        {
            "rule": "exploratory|ma_cross|fade_no_news|close_t+5",
            "tier": "all",
            "session": ex["session"],
            "cum_net_10": np.cumprod(1.0 + ex["net_10"].to_numpy()) - 1.0,
            "series": "book",
        }
    )
    full = pd.concat([out, paths, ex], ignore_index=True)
    num = full.select_dtypes("number").columns
    full[num] = full[num].round(6)
    return full


def write(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    from newsaction.ledger import TRIALS, TrialLedger

    recs = TrialLedger(lay.ledgers / TRIALS).records()
    mine = [r for r in recs if r["chunk"] == run.CHUNK and r["kind"] == run.TRIAL_KIND]
    expected = run.trial_rows(lay)
    if len(mine) != len(expected):
        raise TablesError(f"log the NA-13 trials first: {len(mine)} logged, {len(expected)} expected")
    n_trials = dsr.trial_count(lay.ledgers / TRIALS)
    df = _order(pd.concat([book_rows(lay, n_trials), exploratory_rows(lay, n_trials)], ignore_index=True))
    df.insert(0, "order", range(1, len(df) + 1))
    df["n_trials"] = n_trials
    (lay.root / TABLE_CSV).write_text(df.to_csv(index=False), encoding="utf-8")
    (lay.root / TABLE_TEX).write_text(to_latex(latex_table(df, n_trials)), encoding="utf-8")
    f7 = fig7(lay, df)
    (lay.root / FIG7).write_text(f7.to_csv(index=False), encoding="utf-8")
    market = json.loads((lay.root / run.ARTIFACTS / "market_test.json").read_text(encoding="utf-8"))
    parts = dsr.trial_parts(lay.ledgers / TRIALS)
    summary = {
        "n_trials": n_trials,
        "n_trials_parts": parts,
        "n_trials_rule": "every row of ledgers/trials.jsonl: NA-13's 'strategy' rows plus the model, "
        "encoding and filter selection trials of NA-03..NA-11 (PRD NA-13 S3; PREREG §12)",
        "selection_trials": n_trials - parts.get(run.TRIAL_KIND, 0),
        "strategy_rows": {
            "pre_registered": sum(1 for r in mine if not r["name"].startswith("exploratory|")),
            "exploratory": sum(1 for r in mine if r["name"].startswith("exploratory|")),
        },
        "dsr": {"trials_sr_var": "analytic (1 + SR^2/2)/(T - 1)", "returns": "daily net, per period"},
        "lock_reads": market["lock_reads"],
        "rows": {"strategy_table": len(df), "fig7": len(f7)},
    }
    run.write_json(lay, SUMMARY, summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    _ = list(sys.argv[1:] if argv is None else argv)
    print(json.dumps(write(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
