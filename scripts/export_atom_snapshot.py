"""NA-01 S1: one-time READ-ONLY export of the ATOM snapshot (runs under ATOM's own venv).

    ATOM_DB_PASSWORD=... /Users/amir/GitHub/Atom/.venv/bin/python \
        scripts/export_atom_snapshot.py --out work/snapshot

Then, in the NewsAction environment, ``uv run python scripts/register_snapshot.py`` registers every
file in work/MANIFEST.json.

Read-only protocol (CLAUDE.md E17):
- one session, whose first statement is ``SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY``
  (``SHOW transaction_read_only`` is recorded); every query of the export runs in that one consistent
  snapshot, and the session is rolled back at the end;
- ``count(*)`` of md.price_eod and uni.member is recorded in separate read-only transactions before
  and after the export, and inside the export snapshot;
- prices and membership come from the PIT accessors (``get_prices_eod_by_id``,
  ``get_universe_members``, ``get_estimates``); raw SELECTs are used only for tables without an
  accessor (ref.*, md.corporate_action, fnd.financial_metric shares_basic).

Blinding (CLAUDE.md B8): price rows dated after the public period go to ``<out>/sealed/`` only. This
script never computes or prints anything from those rows except their count.

ATOM imports happen inside ``main`` so the pure helpers can be imported and tested from the
NewsAction environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
ATOM_ROOT = Path.home() / "GitHub" / "Atom"
PRODUCER = "scripts/export_atom_snapshot.py (NA-01 S1)"
MANIFEST_NAME = "MANIFEST_snapshot.json"
SEALED_DIR = "sealed"

EXCHANGE = "NYSE"  # atom_core.calendars alias for XNYS
UNIVERSE = "sp500"
SPY = "SPY"
MEMBERS_RANGE = (date(2023, 1, 3), date(2026, 7, 31))
PRICES_RANGE = (date(2022, 1, 3), date(2026, 7, 31))
CALENDAR_RANGE = (date(2022, 1, 3), date(2026, 10, 23))
ESTIMATE_MONTHS = ((2023, 1), (2026, 7))  # inclusive (year, month) range of snapshot months
ESTIMATE_PERIOD_ENDS = (date(2022, 1, 1), date(2029, 12, 31))
COUNT_TABLES = ("md.price_eod", "uni.member")
PRICE_CHUNK = 25  # ids per accessor call: one statement must finish within ATOM's 5 min statement_timeout

READ_ONLY_TXN = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"

SQL_SPY = "SELECT symbol_id FROM ref.symbol WHERE ticker = :ticker ORDER BY symbol_id"
SQL_SYMBOLS = """
SELECT s.symbol_id, s.ticker, s.name, s.cik, e.code AS exchange, s.asset_class,
       s.listing_date, s.delisting_date, s.is_active
  FROM ref.symbol s
  JOIN ref.exchange e USING (exchange_id)
 WHERE s.symbol_id = ANY(CAST(:ids AS bigint[]))
 ORDER BY s.symbol_id
"""
SQL_SYMBOL_TICKERS = """
SELECT st.symbol_id, st.ticker, e.code AS exchange,
       lower(st.valid_range) AS valid_from, upper(st.valid_range) AS valid_to, st.source
  FROM ref.symbol_ticker st
  JOIN ref.exchange e USING (exchange_id)
 WHERE st.symbol_id = ANY(CAST(:ids AS bigint[]))
 ORDER BY st.symbol_id, lower(st.valid_range), st.ticker
"""
SQL_TICKER_OWNERS = """
SELECT ticker, min(symbol_id) AS symbol_id
  FROM ref.symbol
 WHERE ticker = ANY(CAST(:tickers AS text[]))
 GROUP BY ticker
"""
SQL_SYMBOL_SECTOR = """
SELECT ss.symbol_id, ss.sector_id, lower(ss.valid_range) AS valid_from,
       upper(ss.valid_range) AS valid_to, ss.source
  FROM ref.symbol_sector ss
 WHERE ss.symbol_id = ANY(CAST(:ids AS bigint[]))
 ORDER BY ss.symbol_id, lower(ss.valid_range)
"""
SQL_SECTORS = "SELECT sector_id, taxonomy, code, level, name, parent_id FROM ref.sector ORDER BY sector_id"
SQL_CORPORATE_ACTIONS = """
SELECT action_id, symbol_id, action_type, announce_date, ex_date, record_date, pay_date,
       split_ratio, cash_amount, acquirer_symbol_id, exchange_ratio, source
  FROM md.corporate_action
 WHERE symbol_id = ANY(CAST(:ids AS bigint[]))
 ORDER BY symbol_id, ex_date, action_id
"""
SQL_SHARES_BASIC = """
SELECT f.symbol_id, f.period_end_date AS period_end, f.period_type, f.fiscal_year, f.fiscal_period,
       f.value, lower(f.knowledge_range) AS known_from, upper(f.knowledge_range) AS known_to,
       f.source, f.ingested_at
  FROM fnd.financial_metric f
  JOIN fnd.metric m USING (metric_id)
 WHERE m.code = 'shares_basic'
   AND f.symbol_id = ANY(CAST(:ids AS bigint[]))
 ORDER BY f.symbol_id, f.period_end_date, f.period_type, lower(f.knowledge_range)
"""
SQL_ESTIMATE_PERIODS = """
SELECT DISTINCT ae.period_end_date
  FROM est.analyst_estimate ae
  JOIN fnd.metric m USING (metric_id)
 WHERE m.code = 'eps_diluted'
   AND ae.period_type = 'A'
   AND ae.symbol_id = ANY(CAST(:ids AS bigint[]))
   AND ae.period_end_date BETWEEN CAST(:lo AS date) AND CAST(:hi AS date)
 ORDER BY 1
"""
RAW_SQL = {
    "spy_symbol_id": SQL_SPY,
    "symbols": SQL_SYMBOLS,
    "symbol_tickers": SQL_SYMBOL_TICKERS,
    "estimate_ticker_owners": SQL_TICKER_OWNERS,
    "gics.symbol_sector": SQL_SYMBOL_SECTOR,
    "gics.sector": SQL_SECTORS,
    "corporate_actions": SQL_CORPORATE_ACTIONS,
    "shares_basic": SQL_SHARES_BASIC,
    "estimate_periods": SQL_ESTIMATE_PERIODS,
}
ACCESSORS = {
    "members_by_session": "atom_research.accessors.get_universe_members(code, as_of=session_open_instant)",
    "prices_raw": "atom_research.accessors.get_prices_eod_by_id(..., adjust='raw')",
    "total_return_check": "atom_research.accessors.get_prices_eod_by_id(..., adjust='total')",
    "estimates_fy1": "atom_research.accessors.get_estimates(['eps_diluted'], ['mean', 'count'], A periods)",
    "calendar_atom": "atom_core.calendars.sessions_between / session_open_instant / session_close_instant",
}

UTC_TS = pa.timestamp("us", tz="UTC")
SCHEMAS: dict[str, pa.Schema] = {
    "members_by_session": pa.schema(
        [("session", pa.date32()), ("symbol_id", pa.int64()), ("ticker", pa.string()), ("as_of", UTC_TS)]
    ),
    "symbols": pa.schema(
        [
            ("symbol_id", pa.int64()),
            ("ticker", pa.string()),
            ("name", pa.string()),
            ("cik", pa.string()),
            ("exchange", pa.string()),
            ("asset_class", pa.string()),
            ("listing_date", pa.date32()),
            ("delisting_date", pa.date32()),
            ("is_active", pa.bool_()),
        ]
    ),
    "symbol_tickers": pa.schema(
        [
            ("symbol_id", pa.int64()),
            ("ticker", pa.string()),
            ("exchange", pa.string()),
            ("valid_from", UTC_TS),
            ("valid_to", UTC_TS),
            ("source", pa.string()),
        ]
    ),
    "gics": pa.schema(
        [
            ("symbol_id", pa.int64()),
            ("sector_id", pa.int64()),
            ("node_level", pa.int32()),
            ("taxonomy", pa.string()),
            ("level1_code", pa.string()),
            ("level1_name", pa.string()),
            ("level2_code", pa.string()),
            ("level2_name", pa.string()),
            ("level3_code", pa.string()),
            ("level3_name", pa.string()),
            ("level4_code", pa.string()),
            ("level4_name", pa.string()),
            ("valid_from", UTC_TS),
            ("valid_to", UTC_TS),
            ("source", pa.string()),
        ]
    ),
    "prices": pa.schema(
        [
            ("symbol_id", pa.int64()),
            ("trade_date", pa.date32()),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.int64()),
        ]
    ),
    "corporate_actions": pa.schema(
        [
            ("action_id", pa.int64()),
            ("symbol_id", pa.int64()),
            ("action_type", pa.string()),
            ("announce_date", pa.date32()),
            ("ex_date", pa.date32()),
            ("record_date", pa.date32()),
            ("pay_date", pa.date32()),
            ("split_ratio", pa.float64()),
            ("cash_amount", pa.float64()),
            ("acquirer_symbol_id", pa.int64()),
            ("exchange_ratio", pa.float64()),
            ("source", pa.string()),
        ]
    ),
    "shares_basic": pa.schema(
        [
            ("symbol_id", pa.int64()),
            ("period_end", pa.date32()),
            ("period_type", pa.string()),
            ("fiscal_year", pa.int32()),
            ("fiscal_period", pa.int32()),
            ("value", pa.float64()),
            ("known_from", UTC_TS),
            ("known_to", UTC_TS),
            ("source", pa.string()),
            ("ingested_at", UTC_TS),
        ]
    ),
    "estimates_fy1": pa.schema(
        [
            ("symbol_id", pa.int64()),
            ("ticker", pa.string()),
            ("period_end", pa.date32()),
            ("as_of_date", pa.date32()),
            ("mean", pa.float64()),
            ("n", pa.int64()),
            ("count", pa.float64()),
            ("visible_at", UTC_TS),
        ]
    ),
    "calendar_atom": pa.schema([("session", pa.date32()), ("open_utc", UTC_TS), ("close_utc", UTC_TS)]),
}


# --- pure helpers (importable without ATOM) -------------------------------------------------------


def blinding_bounds(splits_yaml: Path) -> tuple[date, date]:
    """(last public session date bound, first test date) from configs/splits.yaml (PREREG §4)."""
    splits = yaml.safe_load(splits_yaml.read_text(encoding="utf-8"))["splits"]
    public_end, test_start = splits["val_b"]["end"], splits["test"]["start"]
    if not isinstance(public_end, date) or not isinstance(test_start, date) or public_end >= test_start:
        raise ValueError(f"bad split bounds in {splits_yaml}: {public_end!r}, {test_start!r}")
    return public_end, test_start


def split_public_sealed(
    table: pa.Table, date_col: str, public_end: date, test_start: date
) -> tuple[pa.Table, pa.Table]:
    """Partition rows into (date <= public_end, date >= test_start); no row may fall in between."""
    d = table.column(date_col)
    public_mask = pc.less_equal(d, pa.scalar(public_end, pa.date32()))
    sealed_mask = pc.greater_equal(d, pa.scalar(test_start, pa.date32()))
    public, sealed = table.filter(public_mask), table.filter(sealed_mask)
    if public.num_rows + sealed.num_rows != table.num_rows:
        raise ValueError(f"{table.num_rows - public.num_rows - sealed.num_rows} rows between the splits")
    return public, sealed


def month_windows(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[date, datetime]]:
    """(first day, last instant) of every calendar month in [first, last], instants in UTC."""
    out: list[tuple[date, datetime]] = []
    y, m = first
    while (y, m) <= last:
        start = date(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((start, datetime(ny, nm, 1, tzinfo=UTC) - timedelta(microseconds=1)))
        y, m = ny, nm
    return out


def gics_rows(
    symbol_sector: Iterable[dict[str, Any]], sectors: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve each symbol's sector node to its level 1-4 ancestors (codes and names)."""
    by_id = {int(s["sector_id"]): s for s in sectors}
    out = []
    for row in symbol_sector:
        node = by_id[int(row["sector_id"])]
        rec: dict[str, Any] = {
            "symbol_id": int(row["symbol_id"]),
            "sector_id": int(row["sector_id"]),
            "node_level": int(node["level"]),
            "taxonomy": node["taxonomy"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "source": row["source"],
        }
        for lvl in range(1, 5):
            rec[f"level{lvl}_code"] = rec[f"level{lvl}_name"] = None
        cur: dict[str, Any] | None = node
        while cur is not None:
            rec[f"level{int(cur['level'])}_code"] = cur["code"]
            rec[f"level{int(cur['level'])}_name"] = cur["name"]
            cur = by_id.get(int(cur["parent_id"])) if cur["parent_id"] is not None else None
        out.append(rec)
    return out


def pivot_estimates(
    rows: Iterable[dict[str, Any]], owners: dict[str, int], visible_at: datetime
) -> list[dict[str, Any]]:
    """Long accessor rows (one per aggregation) -> one row per (ticker, period_end, as_of_date).

    ``n`` is the analyst count on the mean snapshot; ``count`` is the value of the 'count'
    aggregation when a snapshot of it exists that day (snapshots are stored only on change).
    """
    acc: dict[tuple[str, date, date], dict[str, Any]] = {}
    for r in rows:
        key = (r["ticker"], r["period_end_date"], r["as_of_date"])
        rec = acc.setdefault(
            key,
            {
                "symbol_id": owners[r["ticker"]],
                "ticker": r["ticker"],
                "period_end": r["period_end_date"],
                "as_of_date": r["as_of_date"],
                "mean": None,
                "n": None,
                "count": None,
                "visible_at": visible_at,
            },
        )
        if r["aggregation"] == "mean":
            rec["mean"] = r["value"]
            rec["n"] = r["num_analysts"]
        elif r["aggregation"] == "count":
            rec["count"] = r["value"]
    return [rec for rec in acc.values() if rec["mean"] is not None]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def write_table(table: pa.Table, path: Path) -> None:
    """Atomic parquet write (pyarrow, default compression; deterministic for equal input)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        pq.write_table(table, tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def file_record(
    path: Path, out: Path, table: pa.Table, description: str, date_col: str | None
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "path": path.relative_to(out).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": table.num_rows,
        "columns": [{"name": f.name, "type": str(f.type)} for f in table.schema],
        "sealed": path.parent.name == SEALED_DIR,
        "description": description,
    }
    if date_col is not None and table.num_rows:
        lo, hi = pc.min_max(table.column(date_col)).values()
        rec["date_min"], rec["date_max"] = lo.as_py().isoformat(), hi.as_py().isoformat()
    return rec


def git_head(repo: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout

    return {
        "sha": run("rev-parse", "HEAD").strip(),
        "dirty_files": len(run("status", "--porcelain").splitlines()),
    }


# --- export (ATOM venv only) ----------------------------------------------------------------------


@dataclass
class Exporter:
    out: Path
    session: Any
    as_of: datetime
    public_end: date
    test_start: date
    files: list[dict[str, Any]]

    def query(self, sql: str, **binds: Any) -> list[dict[str, Any]]:
        from sqlalchemy import text

        return [dict(r) for r in self.session.execute(text(sql), binds).mappings().all()]

    def save(self, name: str, table: pa.Table, description: str, date_col: str | None = None) -> None:
        path = self.out / f"{name}.parquet"
        write_table(table, path)
        self.files.append(file_record(path, self.out, table, description, date_col))
        print(f"  {name}: {table.num_rows:,} rows")

    def save_split(self, name: str, table: pa.Table, description: str, date_col: str) -> None:
        public, sealed = split_public_sealed(table, date_col, self.public_end, self.test_start)
        self.save(name, public, f"{description} (sessions <= {self.public_end})", date_col)
        path = self.out / SEALED_DIR / f"{name}_{self.test_start.year}.parquet"
        write_table(sealed, path)
        rec = file_record(
            path, self.out, sealed, f"{description} (SEALED: sessions >= {self.test_start})", None
        )
        self.files.append(rec)
        print(f"  {SEALED_DIR}/{path.name}: {sealed.num_rows:,} rows (not inspected)")


def _counts(engine: Any) -> dict[str, int]:
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        out = {t: int(conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()) for t in COUNT_TABLES}
        conn.rollback()
    return out


def _session_counts(session: Any) -> dict[str, int]:
    from sqlalchemy import text

    return {t: int(session.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()) for t in COUNT_TABLES}


def run_export(ex: Exporter) -> dict[str, Any]:
    import polars as pl
    from atom_core import Period
    from atom_core.calendars import session_close_instant, session_open_instant, sessions_between
    from atom_research.accessors import get_estimates, get_prices_eod_by_id, get_universe_members

    s = ex.session
    info: dict[str, Any] = {}

    print("members_by_session")
    member_rows = []
    member_sessions = sessions_between(EXCHANGE, *MEMBERS_RANGE)
    for d in member_sessions:
        as_of = session_open_instant(EXCHANGE, d)
        for r in get_universe_members(UNIVERSE, as_of, session=s).iter_rows(named=True):
            member_rows.append(
                {"session": d, "symbol_id": r["symbol_id"], "ticker": r["ticker"], "as_of": as_of}
            )
    members = pa.Table.from_pylist(member_rows, schema=SCHEMAS["members_by_session"])
    ex.save(
        "members_by_session",
        members,
        f"PIT {UNIVERSE} members at session_open_instant of every XNYS session "
        f"{MEMBERS_RANGE[0]}..{MEMBERS_RANGE[1]}",
        "session",
    )

    spy = [int(r["symbol_id"]) for r in ex.query(SQL_SPY, ticker=SPY)]
    if len(spy) != 1:
        raise RuntimeError(f"expected exactly one {SPY} symbol_id, got {spy}")
    member_ids = sorted({int(r["symbol_id"]) for r in member_rows})
    ids = sorted({*member_ids, spy[0]})
    info.update({"spy_symbol_id": spy[0], "member_ids": len(member_ids), "export_ids": len(ids)})

    print("symbols / symbol_tickers / gics")
    symbols = ex.query(SQL_SYMBOLS, ids=ids)
    ex.save(
        "symbols",
        pa.Table.from_pylist(symbols, schema=SCHEMAS["symbols"]),
        "ref.symbol rows of members + SPY",
    )
    ex.save(
        "symbol_tickers",
        pa.Table.from_pylist(ex.query(SQL_SYMBOL_TICKERS, ids=ids), schema=SCHEMAS["symbol_tickers"]),
        "ref.symbol_ticker alias history of members + SPY",
    )
    gics = gics_rows(ex.query(SQL_SYMBOL_SECTOR, ids=ids), ex.query(SQL_SECTORS))
    ex.save(
        "gics", pa.Table.from_pylist(gics, schema=SCHEMAS["gics"]), "ref.symbol_sector + ref.sector hierarchy"
    )

    for adjust, name, desc in (
        ("raw", "prices_raw", "md.price_eod raw OHLCV (get_prices_eod_by_id adjust='raw')"),
        (
            "total",
            "total_return_check",
            "split + cash-dividend adjusted OHLCV (get_prices_eod_by_id adjust='total')",
        ),
    ):
        print(name)
        rows: list[dict[str, Any]] = []
        for i in range(0, len(ids), PRICE_CHUNK):  # md.price_adjusted_total is slow per statement
            chunk = ids[i : i + PRICE_CHUNK]
            rows += get_prices_eod_by_id(chunk, *PRICES_RANGE, ex.as_of, session=s, adjust=adjust).to_dicts()
        table = pa.Table.from_pylist(rows, schema=SCHEMAS["prices"])
        ex.save_split(name, table, desc, "trade_date")

    print("corporate_actions / shares_basic")
    ex.save(
        "corporate_actions",
        pa.Table.from_pylist(ex.query(SQL_CORPORATE_ACTIONS, ids=ids), schema=SCHEMAS["corporate_actions"]),
        "md.corporate_action rows of members + SPY (all dates; no prices)",
        "ex_date",
    )
    ex.save(
        "shares_basic",
        pa.Table.from_pylist(ex.query(SQL_SHARES_BASIC, ids=ids), schema=SCHEMAS["shares_basic"]),
        "fnd.financial_metric shares_basic (known_from = lower(knowledge_range))",
        "period_end",
    )

    print("estimates_fy1")
    tickers = sorted({str(r["ticker"]) for r in symbols if int(r["symbol_id"]) in set(member_ids)})
    owners_all = {str(r["ticker"]): int(r["symbol_id"]) for r in ex.query(SQL_TICKER_OWNERS, tickers=tickers)}
    by_ticker = {str(r["ticker"]): int(r["symbol_id"]) for r in symbols}
    owners = {t: by_ticker[t] for t in tickers if owners_all.get(t) == by_ticker[t]}
    info["estimate_tickers_aliased_out"] = sorted(set(tickers) - set(owners))
    periods = [
        (r["period_end_date"], Period.A)
        for r in ex.query(
            SQL_ESTIMATE_PERIODS, ids=member_ids, lo=ESTIMATE_PERIOD_ENDS[0], hi=ESTIMATE_PERIOD_ENDS[1]
        )
    ]
    est_rows: list[dict[str, Any]] = []
    for month_start, month_end in month_windows(*ESTIMATE_MONTHS):
        long = get_estimates(
            sorted(owners),
            ["eps_diluted"],
            ["mean", "count"],
            periods,
            month_end,
            snapshot_start=month_start,
            session=s,
        )
        est_rows += pivot_estimates(long.iter_rows(named=True), owners, month_end)
    est_rows.sort(key=lambda r: (r["symbol_id"], r["period_end"], r["as_of_date"]))
    ex.save(
        "estimates_fy1",
        pa.Table.from_pylist(est_rows, schema=SCHEMAS["estimates_fy1"]),
        "CIQ annual eps_diluted consensus snapshots (mean, analysts) per month, visible_at = month end",
        "as_of_date",
    )
    info["estimate_periods"] = len(periods)

    print("calendar_atom")
    cal = [
        {
            "session": d,
            "open_utc": session_open_instant(EXCHANGE, d),
            "close_utc": session_close_instant(EXCHANGE, d),
        }
        for d in sessions_between(EXCHANGE, *CALENDAR_RANGE)
    ]
    ex.save(
        "calendar_atom",
        pa.Table.from_pylist(cal, schema=SCHEMAS["calendar_atom"]),
        "atom_core.calendars XNYS",
        "session",
    )
    info["polars"] = pl.__version__
    return info


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path, help="output directory (work/snapshot)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing snapshot")
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    if out != (ROOT / "work" / "snapshot").resolve():
        parser.error(f"--out must be {ROOT / 'work' / 'snapshot'}")
    if (out / MANIFEST_NAME).exists() and not args.force:
        parser.error(f"{out / MANIFEST_NAME} exists: the export is one-time (use --force to redo it)")
    password = os.environ.get("ATOM_DB_PASSWORD")
    if not password:
        parser.error("ATOM_DB_PASSWORD is not set")

    import pandas
    import sqlalchemy
    import structlog
    from atom_core.config import DatabaseSettings
    from atom_data.db import get_engine, get_session
    from pydantic import SecretStr
    from sqlalchemy import text

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    public_end, test_start = blinding_bounds(ROOT / "configs" / "splits.yaml")
    engine = get_engine(DatabaseSettings(password=SecretStr(password)))

    counts_before = _counts(engine)
    export_instant = datetime.now(UTC)
    session = get_session(engine)
    files: list[dict[str, Any]] = []
    try:
        session.execute(text(READ_ONLY_TXN))
        txn = {
            "statement": READ_ONLY_TXN,
            "transaction_read_only": session.execute(text("SHOW transaction_read_only")).scalar_one(),
            "transaction_isolation": session.execute(text("SHOW transaction_isolation")).scalar_one(),
        }
        if txn["transaction_read_only"] != "on":
            raise RuntimeError(f"transaction is not read-only: {txn}")
        in_snapshot_before = _session_counts(session)
        ex = Exporter(out, session, export_instant, public_end, test_start, files)
        info = run_export(ex)
        in_snapshot_after = _session_counts(session)
    finally:
        session.rollback()
        session.close()
    counts_after = _counts(engine)

    manifest = {
        "version": 1,
        "producer": PRODUCER,
        "export_instant": export_instant.isoformat(),
        "atom_repo": str(ATOM_ROOT),
        "atom_git": git_head(ATOM_ROOT),
        "newsaction_git": git_head(ROOT),
        "read_only": txn,
        "counts": {
            "before": counts_before,
            "in_snapshot_before": in_snapshot_before,
            "in_snapshot_after": in_snapshot_after,
            "after": counts_after,
            "equal": counts_before == counts_after == in_snapshot_before == in_snapshot_after,
        },
        "blinding": {
            "public_end": public_end.isoformat(),
            "test_start": test_start.isoformat(),
            "sealed_dir": SEALED_DIR,
        },
        "ranges": {
            "members": [d.isoformat() for d in MEMBERS_RANGE],
            "prices": [d.isoformat() for d in PRICES_RANGE],
            "calendar": [d.isoformat() for d in CALENDAR_RANGE],
            "estimate_months": [f"{y}-{m:02d}" for y, m in ESTIMATE_MONTHS],
        },
        "universe": UNIVERSE,
        "accessors": ACCESSORS,
        "raw_sql": {k: " ".join(v.split()) for k, v in RAW_SQL.items()},
        "info": info,
        "environment": {
            "python": platform.python_version(),
            "pandas": pandas.__version__,
            "pyarrow": pa.__version__,
            "sqlalchemy": sqlalchemy.__version__,
        },
        "files": files,
    }
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"counts before={counts_before} after={counts_after} equal={manifest['counts']['equal']}")
    print(f"wrote {out / MANIFEST_NAME} ({len(files)} files)")
    return 0 if manifest["counts"]["equal"] else 2


if __name__ == "__main__":
    sys.exit(main())
