"""NA-13b, in four stages (run in this order):

    uv run python -m newsaction.selective.run validation  # (e) on val-A, val-B: cuts, statistics, selection
    uv run python -m newsaction.selective.run test        # once, after the selection is committed: (a)–(e)
    uv run python -m newsaction.selective.run trials      # log every evaluated variant (kind "exploratory")
    uv run python -m newsaction.selective.run dsr         # the books' deflated Sharpe at the final N

``validation`` uses no test row (the study frame is cut to val-A and val-B before any statistic) and writes
the selection;
``test`` refuses to run unless that selection is committed and unchanged, recomputes the val-A cut points and
refuses if they differ from the committed ones, then evaluates every pair on the test once, the books, the
coverage curves, the output distributions, the band disclosure and the D1 statistics.

Outputs: ``artifacts/NA-13b/results/*.json``, ``artifacts/NA-13b/tables/*.csv`` (each with a unique ``key``
column, read by NA-14's ``make paper``) and ``work/selective/books_daily.parquet``. No API call, no lock read:
2026 outcomes come from NA-12's frames and ``analysis/targets_test``, 2026 market returns from NA-13's
``strategy/market_test``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.analysis import spec
from newsaction.config import load_yaml
from newsaction.paths import CONFIGS, Layout, resolve_layout
from newsaction.provenance import git_sha, utc_now_iso
from newsaction.selective import books as bk
from newsaction.selective import conditioning as cg
from newsaction.selective import conditions as cd
from newsaction.selective import coverage as cv
from newsaction.selective import data as sd
from newsaction.selective import distributions as ds
from newsaction.selective import trials as tr
from newsaction.selective import watch as wt
from newsaction.strategy import dsr as dsr_

CHUNK: Final = "NA-13b"
ARTIFACTS: Final = "artifacts/NA-13b"
RESULTS: Final = f"{ARTIFACTS}/results"
TABLES: Final = f"{ARTIFACTS}/tables"
SELECTION_JSON: Final = f"{RESULTS}/selection_validation.json"
BOOKS_DAILY: Final = "selective/books_daily.parquet"
MAX_CANDIDATES: Final = 3
CANDIDATE_EXIT: Final = "close_t"  # the primary outcome z_id is the open → close move
FILES: Final = {
    "cuts": "cuts.csv",
    "selection_validation": "selection_validation.csv",
    "conditioning": "conditioning.csv",
    "selection": "selection.csv",
    "books": "books.csv",
    "coverage": "coverage.csv",
    "histograms": "histograms.csv",
    "output_summary": "output_summary.csv",
    "bands": "bands.csv",
    "watch_open": "watch_open.csv",
}


class RunError(RuntimeError):
    """A stage's precondition does not hold."""


# --- io --------------------------------------------------------------------------------------------------


def table_path(lay: Layout, name: str) -> Path:
    return lay.root / TABLES / FILES[name]


def write_table(lay: Layout, name: str, df: pd.DataFrame, key: Sequence[str]) -> None:
    out = df.copy()
    out.insert(0, "key", out[list(key)].astype(str).agg("|".join, axis=1))
    if out["key"].duplicated().any():
        raise RunError(f"{name}: duplicate keys")
    if out["key"].str.contains(r"[/@]").any():
        raise RunError(f"{name}: a key holds '/' or '@' (NA-14's citation syntax)")
    path = table_path(lay, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, lineterminator="\n")


def read_table(lay: Layout, name: str) -> pd.DataFrame:
    return pd.read_csv(table_path(lay, name), keep_default_na=False, na_values=[""])


def write_json(lay: Layout, rel: str, obj: Any) -> None:
    path = lay.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tr.clean(obj), indent=1) + "\n", encoding="utf-8")


def scalar_cuts(c: Mapping[str, Any]) -> dict[str, float]:
    return {k: float(v) for k, v in c.items() if not k.startswith("sorted_")}


def flagged(df: pd.DataFrame, col: str) -> list[str]:
    """``model|condition`` of the rows whose ``col`` is true."""
    return [f"{m}|{k}" for m, k, f in zip(df["model"], df["condition"], df[col], strict=True) if bool(f)]


def committed(lay: Layout, rel: str) -> bool:
    """``rel`` is tracked by git and has no uncommitted change."""
    tracked = subprocess.run(["git", "-C", str(lay.root), "ls-files", "--error-unmatch", rel],
                             capture_output=True, check=False)  # fmt: skip
    clean_ = subprocess.run(["git", "-C", str(lay.root), "diff", "--quiet", "HEAD", "--", rel],
                            capture_output=True, check=False)  # fmt: skip
    return tracked.returncode == 0 and clean_.returncode == 0


def frozen() -> dict[str, Any]:
    out: dict[str, Any] = load_yaml(CONFIGS / "frozen.yaml")
    return out


# --- stages ----------------------------------------------------------------------------------------------


def validation(layout: Layout | None = None) -> dict[str, Any]:
    """(e) on validation only: the val-A cut points, every pair's statistics and the selection."""
    lay = resolve_layout(layout)
    t0 = time.time()
    study = sd.study_frame(lay)
    study = study.loc[study["split"].isin(cg.VAL)].reset_index(drop=True)
    c = cd.cuts(study)
    val = cg.evaluate(study, c, list(cg.VAL))
    sel = cg.select(val)
    cuts = scalar_cuts(c)
    write_table(lay, "cuts", pd.DataFrame({"name": list(cuts), "value": list(cuts.values())}), ["name"])
    write_table(lay, "selection_validation", sel, ["model", "condition"])
    chosen = flagged(sel, "selected")
    out = {
        "exploratory": True,
        "stage": "validation (val-A and val-B only; test rows dropped before any statistic)",
        "written_at": utc_now_iso(),
        "git_sha": git_sha(lay.root),
        "rule": {"each": cg.T_EACH, "pooled": cg.T_POOLED, "val_b_only": cg.T_VAL_B_ONLY,
                 "outcome": cg.PRIMARY, "seen_on_test": [k.key for k in cd.CONDITIONS if k.seen_on_test]},
        "n_pairs": len(sel),
        "selected": chosen,
        "cuts": scalar_cuts(c),
        "conditions": {k.key: {"group": k.group, "label": k.label, "level": k.level, "note": k.note,
                               "models": list(k.models), "splits": list(k.splits)} for k in cd.CONDITIONS},
        "tables": {n: io.sha256_file(table_path(lay, n)) for n in ("cuts", "selection_validation")},
        "validation_rows": len(val),
        "seconds": round(time.time() - t0, 1),
    }  # fmt: skip
    write_json(lay, SELECTION_JSON, out)
    return {"selected": chosen, "n_pairs": len(sel), "path": SELECTION_JSON}


def _selected(lay: Layout) -> tuple[list[tuple[str, str]], pd.DataFrame, dict[str, Any]]:
    if not committed(lay, SELECTION_JSON) or not committed(lay, f"{TABLES}/{FILES['selection_validation']}"):
        raise RunError("commit the validation selection before the test stage (the test is evaluated once)")
    meta = json.loads((lay.root / SELECTION_JSON).read_text(encoding="utf-8"))
    sel = read_table(lay, "selection_validation")
    if io.sha256_file(table_path(lay, "selection_validation")) != meta["tables"]["selection_validation"]:
        raise RunError("the selection table differs from the one the selection record names")
    pairs = [(str(m), str(k)) for m, k, s in zip(sel["model"], sel["condition"], sel["selected"], strict=True)
             if bool(s)]  # fmt: skip
    return pairs, sel, meta


def candidates(fam: pd.DataFrame, books: pd.DataFrame, sel_val: pd.DataFrame) -> pd.DataFrame:
    """The operator's forward-test rule: SELECTED on validation, the same sign on the test with BH q < 0.10,
    and a tradable version (test, exit at the close) whose gross Sharpe is above its placebo's 90th
    percentile; at most three, ranked by the pooled-validation t (a validation quantity) if more qualify."""
    f = fam.copy()
    pairs = list(zip(f["model"], f["condition"], strict=True))
    b = books.loc[(books["split"] == "test") & (books["exit"] == CANDIDATE_EXIT)]
    b = b.set_index(["model", "condition"])
    f["book_sharpe_gross"] = [b["sharpe_gross"].get(p, np.nan) for p in pairs]
    f["book_placebo_q90"] = [b["placebo_q90_gross"].get(p, np.nan) for p in pairs]
    f["book_above_q90"] = f["book_sharpe_gross"] > f["book_placebo_q90"]
    f["eligible"] = f["confirmed"] & f["book_above_q90"]
    tv = sel_val.set_index(["model", "condition"])["t_pooled"]
    f["t_pooled_val"] = [tv.get(p, np.nan) for p in pairs]
    order = f.loc[f["eligible"]].sort_values("t_pooled_val", ascending=False).index[:MAX_CANDIDATES]
    f["candidate"] = f.index.isin(order)
    return f


def test(layout: Layout | None = None) -> dict[str, Any]:
    """Every remaining output, the test evaluated once."""
    lay = resolve_layout(layout)
    t0 = time.time()
    pairs, sel_val, meta = _selected(lay)
    cfg = spec.load_config()
    fz = frozen()
    study = sd.study_frame(lay)
    c = cd.cuts(study.loc[study["split"].isin(cg.VAL)].reset_index(drop=True))
    if scalar_cuts(c) != {k: float(v) for k, v in meta["cuts"].items()}:
        raise RunError("the val-A cut points differ from the committed selection's")
    cond_all = cg.evaluate(study, c, list(sd.SPLITS))
    write_table(lay, "conditioning", cond_all, ["model", "condition", "outcome", "split"])
    fam = cg.family_on_test(cond_all, sel_val)
    book_list = bk.books_for(pairs)
    summ, daily = bk.run_books(study, book_list, c, fz, layout=lay)
    summ = summ.rename(columns={"key": "book_key"})
    write_table(lay, "books", summ, ["book_key"])
    what = "the tradable versions' daily gross, turnover and net returns at 5 and 10 bp, val-B and test"
    io.write_parquet(
        daily.reset_index(drop=True), BOOKS_DAILY, producer=CHUNK,
        description=f"NA-13b exploratory: {what}, exits close_t and close_t+1", layout=lay,
    )  # fmt: skip
    fam = candidates(fam, summ, sel_val)
    val_cols = ["diff_val_a", "t_val_a", "diff_val_b", "t_val_b", "rule"]
    fam = fam.merge(sel_val[["model", "condition", *val_cols]], on=["model", "condition"], how="left")
    write_table(lay, "selection", fam, ["model", "condition"])
    ev = sd.events(lay)
    by_model = {m: sd.model_frame(m, ev, lay) for m in sd.MODELS}
    cov = cv.curves(by_model, cv.boots(ev, cfg), cfg)
    write_table(lay, "coverage", cov, ["model", "ranking", "coverage", "split", "target"])
    dist = ds.run(by_model)
    write_table(lay, "histograms", dist["histograms"], ["model", "measure", "split", "bin"])
    write_table(lay, "output_summary", dist["summaries"], ["model", "measure", "split"])
    band_rows = []
    for m in sd.MAIN:
        q, g = cv.bands(
            sd.frame(m, ["event_id", "split", "embargo", "a0_n_hat", "z_cc", "z_on", "z_id"], lay)
        )
        band_rows.append(g.assign(model=m, cut_50=q[0], cut_70=q[1], cut_90=q[2]))
    write_table(lay, "bands", pd.concat(band_rows, ignore_index=True), ["model", "split", "band"])
    write_table(lay, "watch_open", wt.run(cfg, lay), ["model", "split", "statistic"])
    out = {
        "exploratory": True,
        "stage": "test (once, after the validation selection was committed)",
        "written_at": utc_now_iso(),
        "git_sha": git_sha(lay.root),
        "selection_record": SELECTION_JSON,
        "selected": [f"{m}|{k}" for m, k in pairs],
        "books": [b.key for b in book_list],
        "candidates": flagged(fam, "candidate"),
        "lock_reads": 0,
        "seconds": round(time.time() - t0, 1),
    }  # fmt: skip
    write_json(lay, f"{RESULTS}/test_run.json", out)
    return out


def trials(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    rows = tr.all_rows(
        read_table(lay, "coverage"),
        read_table(lay, "watch_open"),
        read_table(lay, "conditioning"),
        read_table(lay, "books"),
    )
    return tr.log(rows, lay)


def dsr(layout: Layout | None = None) -> dict[str, Any]:
    """The books' deflated Sharpe (5 and 10 bp) with N = every row of the trial ledger now."""
    lay = resolve_layout(layout)
    n = dsr_.trial_count(lay.ledgers / "trials.jsonl")
    parts = dsr_.trial_parts(lay.ledgers / "trials.jsonl")
    if parts.get(tr.KIND, 0) == 0:
        raise RunError("log the NA-13b trials first (the DSR counts them)")
    books = read_table(lay, "books")
    daily = io.read_parquet(BOOKS_DAILY, layout=lay)
    for bp in bk.COSTS_BP:
        tag = int(bp)
        probs, sr0s = [], []
        for r in books.itertuples():
            d = daily.loc[(daily["book"] == r.book) & (daily["split"] == r.split) & (daily["exit"] == r.exit)]
            res = dsr_.deflated_sharpe(d[f"net_{tag}"].to_numpy(dtype=float), n_trials=n)
            probs.append(res.prob)
            sr0s.append(res.sr0)
        books[f"dsr_prob_net_{tag}"] = probs
        books[f"dsr_sr0_net_{tag}"] = sr0s
    books["n_trials"] = n
    books = books.drop(columns=["key"])
    write_table(lay, "books", books, ["book_key"])
    out = {"n_trials": n, "parts": parts, "written_at": utc_now_iso(), "git_sha": git_sha(lay.root)}
    write_json(lay, f"{RESULTS}/dsr.json", out)
    return out


STAGES: Final = {"validation": validation, "test": test, "trials": trials, "dsr": dsr}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in STAGES:
        print(f"usage: python -m newsaction.selective.run {{{','.join(STAGES)}}}", file=sys.stderr)
        return 2
    print(json.dumps(tr.clean(STAGES[args[0]]()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
