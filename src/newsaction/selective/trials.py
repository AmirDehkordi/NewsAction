"""NA-13b (f): every evaluated variant as a row of ``ledgers/trials.jsonl`` (CLAUDE.md B10), kind
"exploratory", chunk "NA-13b"; the deflated Sharpe counts them all.

One row per split (val-A, val-B, test; NA-13's convention of one row per variant and split) of:

- (a) each model × ranking × coverage (a threshold set): metric = the mean signed z_id over covered events;
- (d) each model × statistic: metric = the statistic (an IC or a mean);
- (e) each model × condition × outcome: metric = the inside-minus-outside difference;
- the tradable versions, each book × exit: metric = the net Sharpe at 10 bp (NA-13's rule; the cost levels
  and the placebo seeds are not separate rows).

Logging is idempotent: a row already logged with the same value is skipped; another value is an error (the run
is deterministic).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction.ledger import TRIALS, TrialLedger, TrialRecord, params_hash
from newsaction.paths import Layout, resolve_layout

CHUNK: Final = "NA-13b"
KIND: Final = "exploratory"
LEDGER_SPLITS: Final = ("val_a", "val_b", "test")


class TrialsError(RuntimeError):
    """A logged row disagrees with this run."""


def clean(x: Any) -> Any:
    """JSON-safe: NaN / ±inf → None, numpy scalars → Python."""
    if isinstance(x, Mapping):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [clean(v) for v in x]
    if isinstance(x, bool | np.bool_):
        return bool(x)
    if isinstance(x, int | np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        return float(x) if math.isfinite(float(x)) else None
    return x if x is None or isinstance(x, str) else str(x)


def _row(name: str, split: str, metric: str, value: Any, params: Mapping[str, Any]) -> dict[str, Any]:
    return {"name": name, "split": split, "metric": metric, "value": clean(value), "params": dict(params)}


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(k): v for k, v in r.items()} for r in df.to_dict("records")]


def coverage_rows(cov: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for r in _records(cov.loc[cov["target"] == "z_id"]):
        level = f"{float(r['coverage']):g}"
        name = f"exploratory|selective|coverage|{r['model']}|{r['ranking']}|{level}|{r['split']}"
        params = {"part": "a", "model": r["model"], "ranking": r["ranking"], "coverage": float(r["coverage"]),
                  "threshold": r["threshold"]}  # fmt: skip
        out.append(_row(name, str(r["split"]), "mean_signed_z_id", r["signed"], params))
    return out


def watch_rows(watch: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for r in _records(watch):
        name = f"exploratory|selective|watch|{r['model']}|{r['statistic']}|{r['split']}"
        params = {"part": "d", "model": r["model"], "statistic": r["statistic"]}
        out.append(_row(name, str(r["split"]), str(r["statistic"]), r["value"], params))
    return out


def condition_rows(cond: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for r in _records(cond.loc[cond["split"].isin(LEDGER_SPLITS)]):
        name = f"exploratory|selective|condition|{r['model']}|{r['condition']}|{r['outcome']}|{r['split']}"
        params = {"part": "e", "model": r["model"], "condition": r["condition"], "outcome": r["outcome"],
                  "level": r["level"]}  # fmt: skip
        out.append(_row(name, str(r["split"]), f"diff_{r['outcome']}", r["diff"], params))
    return out


def book_rows(books: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for r in _records(books):
        params = {"part": "e-book", "book": r["book"], "exit": r["exit"], "bp": 10.0}
        name = f"{r['book']}|{r['exit']}|{r['split']}"
        out.append(_row(name, str(r["split"]), "sharpe_net_10", r.get("sharpe_net_10"), params))
    return out


def all_rows(
    cov: pd.DataFrame, watch: pd.DataFrame, cond: pd.DataFrame, books: pd.DataFrame
) -> list[dict[str, Any]]:
    return [*coverage_rows(cov), *watch_rows(watch), *condition_rows(cond), *book_rows(books)]


def log(
    rows: Sequence[Mapping[str, Any]], layout: Layout | None = None, path: Path | None = None
) -> dict[str, int]:
    lay = resolve_layout(layout)
    led = TrialLedger(path if path is not None else lay.ledgers / TRIALS)
    have = {(r["name"], r["split"]): r for r in led.records() if r["chunk"] == CHUNK}
    added = skipped = 0
    for r in rows:
        value = r["value"]
        old = have.get((r["name"], r["split"]))
        if old is not None:
            same = old["value"] == value or (
                old["value"] is not None and value is not None and abs(old["value"] - value) <= 1e-12
            )
            if not same:
                raise TrialsError(f"{r['name']} ({r['split']}) is logged with {old['value']}, now {value}")
            skipped += 1
            continue
        led.log(
            TrialRecord(
                chunk=CHUNK, kind=KIND, name=r["name"], params_hash=params_hash(clean(r["params"])),
                split=r["split"], metric=r["metric"], value=value,
            )
        )  # fmt: skip
        added += 1
    return {"added": added, "skipped": skipped, "ledger_rows": len(led.records())}
