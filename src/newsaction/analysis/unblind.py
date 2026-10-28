"""NA-12 S1: unblinding, the one "targets" access sequence (PREREG §4.3–4.4; PRD NA-12 S1 and AC1).

    uv run python -m newsaction.analysis.unblind check     # the lock's conditions; reads nothing sealed
    uv run python -m newsaction.analysis.unblind rehearse  # the same assembly on val-B, public routes
    NA_UNBLIND=1 uv run python -m newsaction.analysis.unblind run   # once, on the real layout

``run`` calls ``lock.require_unblind`` (the freeze hash, the Deviations log as an unchanged prefix,
``NA_UNBLIND=1``) and refuses when ``ledgers/test_access.jsonl`` already holds a "targets" entry or the output
exists, so the sequence runs once. Then, through the frozen routes and the lock:

1. ``targets.build_targets(…, "test")``: the daily outcomes (y2, e5, the CAR^lvl rungs, forward pieces);
2. ``targets.build_d1_targets(…, "test")``: the D1 outcomes (y1, the forward pieces from 10:00);
3. the test returns panel (``panel.build.test_returns_panel`` on the blinded prices, read with purpose
   "targets"): the same-day columns. The panel exposes AR and σ but of the same-day z only z_id, so z_cc and
   z_on come from ``panel.risk.zscore``, the function NA-01 computed them with;
4. ``reactions.build_reactions(…, "test", "D2" / "D1")``: G at D2 and D1 and the 10:00 rung, the route the
   NA-11 Call B states were built with;
5. the day-t 30-minute path (``slot_path``) from the blinded bars: figure data.

Output: ``work/analysis/targets_test.parquet``, one row per test-period (session, symbol_id) of the returns
panel. From here on 2026 outcomes are read only from this file (operator preamble NA-12, item 3), never
through ``load_targets`` again. ``rehearse`` assembles the same columns for val-B from the public routes and
compares each with ``panel_public`` / ``intraday_public``.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from newsaction import calendar, io, lock
from newsaction.analysis import slot_path
from newsaction.bars import BARS_PUBLIC, derive
from newsaction.bars import basis as bs
from newsaction.bars.fetch import spy_symbol_id
from newsaction.config import SplitName, load_splits
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.panel import build, reactions, risk, targets
from newsaction.paths import Layout, resolve_layout

CHUNK: Final = "NA-12"
ARTIFACTS: Final = "artifacts/NA-12"
OUT: Final = "analysis/targets_test.parquet"
RECORD: Final = "unblind.json"
REHEARSAL: Final = "unblind_rehearsal.json"
KEYS: Final = ("session", "symbol_id")
IDS: Final = ("split", "company_id", "member", "is_rep", "sector", "half_day")
SAME_DAY: Final = (
    "r_cc",
    "r_spy_cc",
    "ar_cc",
    "ar_on",
    "ar_id",
    "sigma_cc",
    "sigma_on",
    "sigma_id",
    "z_cc",
    "z_on",
    "z_id",
    "z_vol",
)
D2_REACTION: Final = ("g_d2", "g_d2_lvl")
D1_REACTION: Final = ("g_d1", "g_d1_lvl", "car_lvl_10")
CONSISTENCY_TOL: Final = 1e-12


class UnblindError(RuntimeError):
    """A pre-condition of the one access sequence does not hold; nothing sealed was read."""


def artifacts_dir(layout: Layout | None = None) -> Path:
    path = resolve_layout(layout).root / ARTIFACTS
    path.mkdir(parents=True, exist_ok=True)
    return path


def targets_accesses(layout: Layout | None = None) -> list[dict[str, Any]]:
    """The access ledger's "targets" entries, allowed or refused."""
    lay = resolve_layout(layout)
    return [e for e in AccessLedger(lay.ledgers / TEST_ACCESS).entries() if e.get("purpose") == "targets"]


def check(layout: Layout | None = None) -> dict[str, Any]:
    """The lock's conditions without reading anything sealed: ``require_unblind`` checks NA_UNBLIND last, so
    a refusal that names only it means the freeze hash and the Deviations log are intact."""
    lay = resolve_layout(layout)
    out: dict[str, Any] = {
        "hash_now": lock.compute_freeze_hash(lay).digest,
        "targets_entries": len(targets_accesses(lay)),
        "output_exists": (lay.work / OUT).exists(),
    }
    try:
        lock.require_unblind(lay)
        out["require_unblind"] = "passes"
    except lock.LockError as exc:
        out["require_unblind"] = str(exc)
    out["ready"] = (
        out["targets_entries"] == 0
        and not out["output_exists"]
        and (out["require_unblind"] == "passes" or lock.UNBLIND_ENV in out["require_unblind"])
    )
    return out


# --- assembly (shared by the real run and the rehearsal) ---------------------------------------------------


def _dates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["session"] = pd.to_datetime(out["session"]).dt.date
    return out


def _zscore(ar: pd.Series, sigma: pd.Series) -> pd.Series:
    """``panel.risk.zscore`` (NA-01's same-day z, clipped) on one column."""
    return risk.zscore(ar.to_frame("z"), sigma.to_frame("z"))["z"]


def _max_gap(a: pd.Series, b: pd.Series) -> float:
    both = a.notna() & b.notna()
    return float((a[both] - b[both]).abs().max()) if bool(both.any()) else 0.0


def assemble(
    panel: pd.DataFrame,
    tg: pd.DataFrame,
    d1: pd.DataFrame,
    rx2: pd.DataFrame,
    rx1: pd.DataFrame,
    path: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """One row per ``panel`` row: ids, the same-day columns (z_cc and z_on by ``risk.zscore``), the daily
    targets, G at D2, the D1 targets and reactions, the slot path; and the consistency gaps (each 0)."""
    p = _dates(panel)
    out = p[[*KEYS, *IDS]].copy()
    for c in SAME_DAY:
        if c in ("z_cc", "z_on"):
            continue
        out[c] = p[c].to_numpy()
    out["z_cc"] = _zscore(p["ar_cc"], p["sigma_cc"]).to_numpy()
    out["z_on"] = _zscore(p["ar_on"], p["sigma_on"]).to_numpy()
    if out.duplicated(list(KEYS)).any():
        raise UnblindError("the returns panel repeats a (session, symbol_id)")
    t = _dates(tg).drop(columns=["split"])
    out = out.merge(t, on=list(KEYS), how="left", validate="one_to_one")
    out = out.merge(_dates(rx2)[[*KEYS, *D2_REACTION]], on=list(KEYS), how="left", validate="one_to_one")
    out = out.merge(_dates(d1).drop(columns=["split"]), on=list(KEYS), how="left", validate="one_to_one")
    out = out.merge(_dates(rx1)[[*KEYS, *D1_REACTION]], on=list(KEYS), how="left", validate="one_to_one")
    out = out.merge(_dates(path), on=list(KEYS), how="left", validate="one_to_one")
    gaps = {
        "y0_vs_z_id": _max_gap(out["y0"], out["z_id"]),
        "g_d2_vs_z_cc": _max_gap(out["g_d2"], out["z_cc"]),
        "path_b0_vs_car_lvl_10": _max_gap(out["car_lvl_b0"], out["car_lvl_10"]),
    }
    bad = {k: v for k, v in gaps.items() if not v <= CONSISTENCY_TOL}
    if bad:
        raise UnblindError(f"inconsistent outcome columns: {bad}")
    return out.sort_values(list(KEYS)).reset_index(drop=True), gaps


def _summary(out: pd.DataFrame) -> dict[str, Any]:
    """Counts only (rows, sessions, non-missing values per column): no statistic of any outcome."""
    return {
        "rows": len(out),
        "sessions": int(out["session"].nunique()),
        "first_session": str(min(out["session"])) if len(out) else None,
        "last_session": str(max(out["session"])) if len(out) else None,
        "symbols": int(out["symbol_id"].nunique()),
        "non_missing": {c: int(out[c].notna().sum()) for c in out.columns if c not in (*KEYS, *IDS)},
    }


# --- the real run ------------------------------------------------------------------------------------------


def _refuse_second_run(lay: Layout) -> None:
    seen = targets_accesses(lay)
    if seen:
        raise UnblindError(
            f"the access ledger already holds {len(seen)} 'targets' entries (first {seen[0]['ts']}): the "
            f"unblinding ran; read work/{OUT} instead (a failed run is a STOP for the operator)"
        )
    if (lay.work / OUT).exists():
        raise UnblindError(f"work/{OUT} exists already")


def bar_inputs(
    bars: pd.DataFrame, prices: pd.DataFrame, layout: Layout | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """(public + blinded bars, the EOD reference with the blinded prices, SPY's id), as
    ``bars.derive.test_intraday_panel`` assembles them."""
    lay = resolve_layout(layout)
    allbars = pd.concat(
        [io.read_parquet(BARS_PUBLIC, columns=list(derive.BAR_READ), layout=lay), bars[derive.BAR_READ]],
        ignore_index=True,
    )
    return allbars, bs.reference_prices(lay, extra=prices), spy_symbol_id(lay)


def run(layout: Layout | None = None) -> dict[str, Any]:
    """The one access sequence (module docstring)."""
    lay = resolve_layout(layout)
    lock.require_unblind(lay)  # STOP on a hash mismatch: never "fix" it (operator preamble NA-12, item 3)
    _refuse_second_run(lay)
    t0 = time.time()
    empty = pd.DataFrame()
    test = load_splits().splits["test"]
    days = set(calendar.sessions(test.start, test.end))
    tg = targets.build_targets(empty, targets.TEST, layout=lay)
    d1 = targets.build_d1_targets(empty, empty, targets.TEST, layout=lay)
    prices, total = (lock.read_sealed(n, "targets", layout=lay) for n in targets.blinded_price_files())
    bars = lock.read_sealed(targets.blinded_bars_file(), "targets", layout=lay)
    daily = build.test_returns_panel(prices, total, layout=lay)
    panel = daily.loc[[d in days for d in pd.to_datetime(daily["session"]).dt.date]].reset_index(drop=True)
    rx2 = reactions.build_reactions(empty, "test", "D2", layout=lay)
    rx1 = reactions.build_reactions(empty, "test", "D1", layout=lay)
    allbars, ref, spy_id = bar_inputs(bars, prices, lay)
    path = slot_path.path(panel[list(derive.PANEL_COLUMNS)], allbars, ref, spy_id)
    out, gaps = assemble(panel, tg, d1, rx2, rx1, path)
    if set(out["split"]) != {"test"}:
        raise UnblindError(f"rows outside the test split: {sorted(set(out['split']))}")
    entry = io.write_parquet(
        out,
        OUT,
        producer=CHUNK,
        description="NA-12 S1: the test period's outcomes, written once after unblinding "
        "(targets.build_targets and build_d1_targets, the returns panel's same-day columns, G at D2 and D1, "
        "the day-t 30-minute path)",
        layout=lay,
    )
    record = {
        "freeze_hash": lock.compute_freeze_hash(lay).digest,
        "targets_entries": [
            {k: e[k] for k in ("ts", "name", "caller", "allowed")} for e in targets_accesses(lay)
        ],
        "output": {"path": f"work/{OUT}", "sha256": entry["sha256"]},
        "consistency_gaps": gaps,
        "seconds": round(time.time() - t0, 1),
        **_summary(out),
    }
    text = json.dumps(record, indent=1, default=str) + "\n"
    (artifacts_dir(lay) / RECORD).write_text(text, encoding="utf-8")
    return record


# --- the rehearsal on val-B (public routes; nothing sealed) -----------------------------------------------


def rehearse(layout: Layout | None = None, split: str = "val_b") -> dict[str, Any]:
    """The same assembly on ``split`` from the public routes; every column must equal the public panels."""
    lay = resolve_layout(layout)
    sp = load_splits().splits[cast(SplitName, split)]
    days = set(calendar.sessions(sp.start, sp.end))
    full = io.read_parquet("panel/panel_public.parquet", layout=lay)
    intraday = io.read_parquet("panel/intraday_public.parquet", layout=lay)
    panel = full.loc[[d in days for d in full["session"]]].reset_index(drop=True)
    tg = targets.build_targets(full[list(targets.INPUT_COLUMNS)], split, layout=lay)
    d1 = targets.build_d1_targets(full[["session", "symbol_id", "ar_cc", "sigma_cc"]], intraday, split)
    rx2 = reactions.build_reactions(full, split, "D2")
    rx1 = reactions.build_reactions(intraday, split, "D1")
    daily, bars, ref, spy_id = slot_path.public_inputs(sorted(days), lay)
    path = slot_path.path(daily, bars, ref, spy_id)
    out, gaps = assemble(panel, tg, d1, rx2, rx1, path)
    ref_d = _dates(panel)
    ref_i = _dates(intraday)
    diffs: dict[str, float] = {}
    for name, refer in (("panel_public", ref_d), ("intraday_public", ref_i)):
        cols = [c for c in out.columns if c in refer.columns and c not in (*KEYS, *IDS)]
        m = out[[*KEYS, *cols]].merge(refer[[*KEYS, *cols]], on=list(KEYS), suffixes=("", "_ref"))
        for c in cols:
            a, b = m[c].astype(float), m[f"{c}_ref"].astype(float)
            nan_mismatch = int((a.isna() != b.isna()).sum())
            diffs[f"{name}:{c}"] = _max_gap(a, b) if nan_mismatch == 0 else float("inf")
    bad = {k: v for k, v in diffs.items() if not v <= CONSISTENCY_TOL}
    record = {
        "split": split,
        "consistency_gaps": gaps,
        "columns_compared": len(diffs),
        "max_abs_diff": max(diffs.values()) if diffs else None,
        "mismatches": bad,
        **_summary(out),
    }
    (artifacts_dir(lay) / REHEARSAL).write_text(
        json.dumps(record, indent=1, default=str) + "\n", encoding="utf-8"
    )
    if bad:
        raise UnblindError(f"the rehearsal differs from the public panels: {bad}")
    return record


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "check"
    fns = {"check": check, "rehearse": rehearse, "run": run}
    if cmd not in fns:
        print(f"usage: python -m newsaction.analysis.unblind {{{'|'.join(fns)}}}", file=sys.stderr)
        return 2
    out = fns[cmd]()
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
