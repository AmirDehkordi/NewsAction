"""NA-13: the daily returns the strategies trade on (PREREG §5.1–5.3, §12; operator preamble NA-13, item 3).

    uv run python -m newsaction.strategy.market public          # val-A and val-B; nothing blinded
    NA_UNBLIND=1 uv run python -m newsaction.strategy.market test   # once: three reads through the lock

One long panel per (session, symbol_id) from NA-01's own grid (``panel.build.assemble``), so every return is
the panel's:

- ``r_id`` (raw open → raw close), ``r_cc`` (adjusted close → close), SPY's ``r_spy_id`` and ``r_spy_cc``;
- ``beta_m`` (252 sessions ending t−1, §5.3) for the SPY hedge; ``ar_cc`` (the exploratory add-on);
- ``adv20``: the mean dollar volume (raw close × raw volume on the traded basis) over the 20 sessions ending
  t−1 (≥ 15 of them), for capacity at 1% of ADV (§12);
- ``ma20``, ``ma50`` and their values at t−1 (``*_prev``): moving averages of the adjusted close (the
  operator's exploratory add-on, item 9);
- the D1 entry leg from NA-10's intraday panel: ``p10`` (the 10:00 bar close), ``r_10c`` and ``r_spy_10c``.

``public`` assembles the public inputs and keeps val-A and val-B (``targets_test`` lacks raw open→close,
SPY's open, the volumes and the 10:00 legs). ``test`` reads the blinded prices and bars once through
``lock.read_sealed(…, "targets")`` (logged in ``ledgers/test_access.jsonl``), assembles them the way
``panel.build.test_returns_panel`` and ``bars.derive.test_intraday_panel`` do, and refuses to write unless its
val-B rows equal the public build's and its test ``r_cc``, ``r_spy_cc`` and ``ar_cc`` equal
``work/analysis/targets_test.parquet`` (NA-12's single source of 2026 outcomes).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import calendar, io, lock
from newsaction.config import load_splits
from newsaction.panel import build, targets
from newsaction.paths import Layout, resolve_layout

CHUNK: Final = "NA-13"
ARTIFACTS: Final = "artifacts/NA-13"
PUBLIC_OUT: Final = "strategy/market_public.parquet"
TEST_OUT: Final = "strategy/market_test.parquet"
RECORD: Final = "market_test.json"
INTRADAY_PUBLIC: Final = "panel/intraday_public.parquet"
TARGETS_TEST: Final = "analysis/targets_test.parquet"
ADV_WINDOW: Final = 20  # PRD NA-13 S2: 20-session ADV
ADV_MIN: Final = 15
MA_SHORT: Final = 20  # operator item 9
MA_LONG: Final = 50
KEYS: Final = ("session", "symbol_id")
IDS: Final = ("company_id", "split", "member", "is_rep")
GRID: Final = (
    "member",
    "is_rep",
    "raw_open",
    "raw_close",
    "adj_close",
    "r_cc",
    "r_id",
    "r_spy_cc",
    "r_spy_id",
    "beta_m",
    "ar_cc",
    "adv20",
    "ma20",
    "ma50",
    "ma20_prev",
    "ma50_prev",
)
INTRADAY: Final = ("p10", "r_10c", "r_spy_10c")
COLUMNS: Final = (*KEYS, *IDS, *GRID[2:], *INTRADAY)
SAME_AS_TARGETS: Final = ("r_cc", "r_spy_cc", "ar_cc")
SAME_AS_PANEL: Final = (
    "raw_open",
    "raw_close",
    "adj_close",
    "r_cc",
    "r_id",
    "r_spy_cc",
    "r_spy_id",
    "beta_m",
    "ar_cc",
)
PUBLIC_PANEL: Final = "panel/panel_public.parquet"
TOL: Final = 1e-12


class MarketError(RuntimeError):
    """The returns panel failed a consistency check (nothing is written)."""


def adv(dollar_volume: pd.DataFrame, window: int = ADV_WINDOW, min_obs: int = ADV_MIN) -> pd.DataFrame:
    """Mean dollar volume over the ``window`` sessions ending t−1 (rows = consecutive sessions)."""
    return dollar_volume.rolling(window, min_periods=min_obs).mean().shift(1)


def moving_average(close: pd.DataFrame, window: int) -> pd.DataFrame:
    """Mean adjusted close over the ``window`` sessions ending t (all of them present)."""
    return close.rolling(window, min_periods=window).mean()


def add_grid_columns(asm: build.Assembled) -> None:
    """Add ``adv20`` and the moving averages to the grid (wide: every session, not just the member rows)."""
    f = asm.frames
    f["adv20"] = adv(f["raw_close"] * f["raw_volume"])
    for k, w in (("ma20", MA_SHORT), ("ma50", MA_LONG)):
        f[k] = moving_average(f["adj_close"], w)
        f[f"{k}_prev"] = f[k].shift(1)


def long_rows(asm: build.Assembled, start: date, end: date) -> pd.DataFrame:
    """The grid's member and post-exit rows (``build.panel_rows``) for sessions in [start, end]."""
    sess = asm.sessions[(asm.sessions >= pd.Timestamp(start)) & (asm.sessions <= pd.Timestamp(end))]
    df = build.long_panel(asm, sess, GRID, build.panel_rows(asm))
    return df


def with_intraday(daily: pd.DataFrame, intraday: pd.DataFrame) -> pd.DataFrame:
    cols = [*KEYS, *INTRADAY]
    out = daily.merge(intraday[cols], on=list(KEYS), how="left", validate="one_to_one")
    return out[list(COLUMNS)].sort_values(list(KEYS)).reset_index(drop=True)


def _span(first: str, last: str) -> tuple[date, date]:
    sp = load_splits().splits
    return sp[first].start, sp[last].end  # type: ignore[index]


def public_panel(layout: Layout | None = None) -> pd.DataFrame:
    """val-A and val-B rows from the public inputs (no blinded file)."""
    lay = resolve_layout(layout)
    asm = build.assemble(build.load_inputs(lay))
    add_grid_columns(asm)
    start, end = _span("val_a", "val_b")
    daily = long_rows(asm, start, end)
    del asm
    intraday = io.read_parquet(INTRADAY_PUBLIC, columns=[*KEYS, *INTRADAY], layout=lay)
    return with_intraday(daily, intraday)


def write_public(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    df = public_panel(lay)
    if (pd.to_datetime(df["session"]) > pd.Timestamp(load_splits().splits["val_b"].end)).any():
        raise MarketError("the public returns panel would hold a test-period session")
    days = set(df["session"])
    ref = io.read_parquet(PUBLIC_PANEL, columns=[*KEYS, *SAME_AS_PANEL], layout=lay)
    gaps = compare(df, ref.loc[[d in days for d in ref["session"]]], list(SAME_AS_PANEL))
    if not all(v <= TOL for v in gaps.values()):
        raise MarketError(f"the public build differs from panel_public: {gaps}")
    return io.write_parquet(
        df,
        PUBLIC_OUT,
        producer=CHUNK,
        description="NA-13: val-A and val-B daily returns for the strategies (raw open-close, adjusted "
        "close-close, SPY, beta_m, 20-session dollar ADV, MA20/MA50, the 10:00 legs)",
        layout=lay,
    )


# --- the test build (one access sequence through the lock) -------------------------------------------------


def _max_gap(a: pd.Series, b: pd.Series) -> float:
    x, y = a.astype(float).to_numpy(), b.astype(float).to_numpy()
    if bool((np.isnan(x) != np.isnan(y)).any()):
        return float("inf")
    d = np.abs(x - y)
    return float(np.nanmax(d)) if np.isfinite(d).any() else 0.0


def compare(new: pd.DataFrame, ref: pd.DataFrame, cols: Sequence[str]) -> dict[str, float]:
    """Largest |difference| per column on the rows both frames hold (∞ when the rows or NaNs differ)."""
    m = new[[*KEYS, *cols]].merge(ref[[*KEYS, *cols]], on=list(KEYS), how="outer", suffixes=("", "_ref"))
    out = {}
    for c in cols:
        out[c] = _max_gap(m[c], m[f"{c}_ref"])
    return out


def test_panel(layout: Layout | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """(val-B and test rows assembled with the blinded files, the consistency gaps)."""
    from newsaction.bars import derive

    lay = resolve_layout(layout)
    lock.require_unblind(lay)  # STOP on a freeze-hash mismatch (operator preamble NA-13, item 3)
    prices, total = (lock.read_sealed(n, "targets", layout=lay) for n in targets.blinded_price_files())
    bars = lock.read_sealed(targets.blinded_bars_file(), "targets", layout=lay)
    inp = build.load_inputs(lay)
    inp = replace(
        inp,
        prices_raw=pd.concat([inp.prices_raw, prices], ignore_index=True),
        total=pd.concat([inp.total, total], ignore_index=True),
    )
    asm = build.assemble(inp)
    add_grid_columns(asm)
    start, end = _span("val_b", "test")
    daily = long_rows(asm, start, end)
    del asm, inp
    intraday = derive.test_intraday_panel(bars, prices, total, layout=lay)
    out = with_intraday(daily, intraday)
    del intraday
    vb = load_splits().splits["val_b"]
    pub = io.read_parquet(PUBLIC_OUT, layout=lay)
    pub = pub.loc[[vb.start <= d <= vb.end for d in pub["session"]]]
    new_vb = out.loc[[vb.start <= d <= vb.end for d in out["session"]]]
    gaps = {"val_b_vs_public": compare(new_vb, pub, [c for c in COLUMNS if c not in (*KEYS, *IDS)])}
    tt = io.read_parquet(TARGETS_TEST, columns=[*KEYS, *SAME_AS_TARGETS], layout=lay)
    test = out.loc[out["split"] == "test"].reset_index(drop=True)
    gaps["test_vs_targets_test"] = compare(test, tt, list(SAME_AS_TARGETS))
    bad = {f"{k}:{c}": v for k, g in gaps.items() for c, v in g.items() if not v <= TOL}
    if bad:
        raise MarketError(f"the test build differs from the public build or targets_test: {bad}")
    return test, gaps


def write_test(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    test, gaps = test_panel(lay)
    entry = io.write_parquet(
        test,
        TEST_OUT,
        producer=CHUNK,
        description="NA-13: test-period daily returns for the strategies, assembled once from the blinded "
        "prices and bars read through newsaction.lock (purpose targets)",
        layout=lay,
    )
    accesses = [
        {k: e[k] for k in ("ts", "name", "purpose", "caller", "allowed")}
        for e in lock_entries(lay)
        if e.get("caller", "").find("strategy/market.py") >= 0
    ]
    record = {
        "output": {"path": f"work/{TEST_OUT}", "sha256": entry["sha256"], "rows": len(test)},
        "sessions": [str(min(test["session"])), str(max(test["session"]))],
        "n_sessions": int(test["session"].nunique()),
        "lock_reads": accesses,
        "consistency_gaps": gaps,
        "tolerance": TOL,
    }
    path = lay.root / ARTIFACTS / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, default=str) + "\n", encoding="utf-8")
    return record


def lock_entries(layout: Layout | None = None) -> list[dict[str, Any]]:
    from newsaction.ledger import TEST_ACCESS, AccessLedger

    lay = resolve_layout(layout)
    return AccessLedger(lay.ledgers / TEST_ACCESS).entries()


def entry_session(session: date, offset: int) -> date:
    """The session ``offset`` sessions after ``session`` (``offset`` ≥ 0)."""
    d = session
    for _ in range(offset):
        d = calendar.next_session(d)
    return d


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "public"
    if cmd == "public":
        print(json.dumps(write_public(), indent=1, default=str))
    elif cmd == "test":
        print(json.dumps(write_test(), indent=1, default=str))
    else:
        print(f"unknown command {cmd!r}; expected public or test", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
