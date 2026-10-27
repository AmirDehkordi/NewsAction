"""NA-10 S3: the request plan and the fetch (PRD NA-10 S3; CLAUDE.md B8, E18).

    uv run python -m newsaction.bars.fetch --part public [--dry-run]
    uv run python -m newsaction.bars.fetch --part test [--dry-run]

**Symbols.** The representative class of every company that is an index member at any session from
``fetch.membership_start`` to the test end (``panel_public`` ∪ ``panel_test_inputs``: ``member`` and
``is_rep``, both known at open(s)), plus SPY. FMP is asked for the ATOM ticker.

**Windows.** A company's bars are needed from ``fetch.history_sessions`` sessions before its first member
session in the range (σ_30 and σ_rest need that history; never before ``fetch.stock_start``) to its last
member session. That span is cut at the public / test boundary, so no answer mixes the two, and each part
into windows of at most ``window_days`` calendar days (the probe's largest complete window,
``artifacts/NA-10/capability.json``). SPY spans ``fetch.spy_start`` to the test end. The request count is the
number of windows (``plan``); the probe refuses to let the fetch start if it exceeds the cap.

**Parts.** ``public``: windows ending on or before the val-B end; answers are cached under
``work/bars30/raw/`` and assembled into ``work/bars30/bars_public.parquet`` (rows dated ≤ val-B end).
``test``: windows from the test start; answers are held in memory, never cached or summarized, and written
once through ``lock.write_sealed`` (the lock's ``bars30_<year>`` file). Both parts use the probe's switches,
so every bar of a symbol is on one price basis.
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, Literal, cast

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction import calendar, io, lock
from newsaction.bars import (
    BARS_PUBLIC,
    CAPABILITY,
    PRODUCER,
    blinded_bars_name,
    load_bars_config,
)
from newsaction.bars.fmp30 import FIELDS, Answer, Api, BarRequest, FmpClient, FmpError
from newsaction.config import load_splits
from newsaction.paths import Layout, resolve_layout

Part = Literal["public", "test"]
PARTS: Final[tuple[Part, ...]] = ("public", "test")
BAR_COLUMNS: Final = (
    "symbol_id",
    "ticker",
    "session",
    "bar_start",
    "slot",
    "regular",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "request_key",
    "switches",
)


@dataclass(frozen=True)
class Switches:
    """The probe's choice, applied to every request of the fetch (one endpoint, one price basis)."""

    extended: bool
    nonadjusted: bool
    api: Api = "stable"

    def text(self) -> str:
        parts = [
            f"{k}=true" for k, v in (("extended", self.extended), ("nonadjusted", self.nonadjusted)) if v
        ]
        if self.api != "stable":
            parts.append(f"api={self.api}")
        return "&".join(parts) or "default"


@dataclass(frozen=True)
class Window:
    symbol_id: int
    ticker: str
    start: date
    end: date
    part: Part

    def request(self, sw: Switches) -> BarRequest:
        return BarRequest(
            self.ticker, self.start, self.end, extended=sw.extended, nonadjusted=sw.nonadjusted, api=sw.api
        )


# --- plan ---------------------------------------------------------------------------------------------


def public_end() -> date:
    return load_splits().splits["val_b"].end


def test_range() -> tuple[date, date]:
    t = load_splits().splits["test"]
    return t.start, t.end


def member_spans(layout: Layout | None = None) -> pd.DataFrame:
    """(symbol_id, ticker, first, last): member sessions of each representative class in the fetch range."""
    lay = resolve_layout(layout)
    cfg = load_bars_config().fetch
    cols = ["session", "symbol_id", "ticker", "member", "is_rep"]
    pub = io.read_parquet("panel/panel_public.parquet", columns=cols, layout=lay)
    tst = io.read_parquet("panel/panel_test_inputs.parquet", columns=cols, layout=lay)
    df = pd.concat([pub, tst], ignore_index=True)
    lo, hi = cfg.membership_start, test_range()[1]
    keep = df["member"].astype(bool) & df["is_rep"].astype(bool)
    keep &= np.asarray([lo <= d <= hi for d in df["session"]], dtype=bool)
    g = df.loc[keep].groupby("symbol_id")
    out = pd.DataFrame(
        {"ticker": g["ticker"].first(), "first": g["session"].min(), "last": g["session"].max()}
    ).reset_index()
    return out.sort_values("symbol_id").reset_index(drop=True)


def sessions_back(d: date, k: int) -> date:
    """The session k sessions before ``d`` (``d`` itself if k = 0)."""
    out = d
    for _ in range(k):
        out = calendar.prev_session(out)
    return out


def split_span(start: date, end: date, window_days: int) -> list[tuple[date, date]]:
    """Consecutive inclusive windows covering every session of [start, end]. Each starts on a session and
    ends on the last session within ``window_days`` calendar days of its start, so no window spends its
    calendar days on a weekend edge (the vendor's cap counts days ending at ``to``; IR-04 runbook)."""
    if window_days < 1:
        raise ValueError("window_days must be positive")
    days = calendar.sessions(start, end)
    out: list[tuple[date, date]] = []
    i = 0
    while i < len(days):
        a = days[i]
        last = a + timedelta(days=window_days - 1)
        j = i
        while j + 1 < len(days) and days[j + 1] <= last:
            j += 1
        out.append((a, days[j]))
        i = j + 1
    return out


def _parts(start: date, end: date) -> list[tuple[Part, date, date]]:
    pub_end = public_end()
    t0, t1 = test_range()
    out: list[tuple[Part, date, date]] = []
    if start <= pub_end:
        out.append(("public", start, min(end, pub_end)))
    if end >= t0:
        out.append(("test", max(start, t0), min(end, t1)))
    return out


def first_traded(layout: Layout | None = None) -> dict[int, date]:
    """First EOD trading day of each symbol in the public snapshot (no bar can precede it)."""
    px = io.read_parquet("snapshot/prices_raw.parquet", columns=["symbol_id", "trade_date"], layout=layout)
    first = px.groupby("symbol_id")["trade_date"].min()
    return dict(zip(first.index.astype("int64").tolist(), first.tolist(), strict=True))


def plan(
    window_days: int, *, spans: pd.DataFrame | None = None, layout: Layout | None = None
) -> list[Window]:
    """Every request of the fetch, in (part, symbol) order. A public span starts no earlier than the symbol's
    first EOD trading day; a symbol without public EOD rows (listed in the test period) has no public span."""
    cfg = load_bars_config().fetch
    spans = member_spans(layout) if spans is None else spans
    traded = first_traded(layout)
    out: list[Window] = []
    for rec in spans.to_dict("records"):
        sid = int(rec["symbol_id"])
        first = max(cfg.stock_start, sessions_back(rec["first"], cfg.history_sessions))
        for part, a, b in _parts(first, rec["last"]):
            if part == "public":
                if sid not in traded:
                    continue
                a = max(a, traded[sid])
            for lo, hi in split_span(a, b, window_days):
                out.append(Window(sid, str(rec["ticker"]), lo, hi, part))
    spy_id = spy_symbol_id(layout)
    for part, a, b in _parts(cfg.spy_start, test_range()[1]):
        for lo, hi in split_span(a, b, window_days):
            out.append(Window(spy_id, cfg.spy_symbol, lo, hi, part))
    for al in cfg.aliases:
        for rec in spans.loc[spans["ticker"] == al.ticker].to_dict("records"):
            for part, a, b in _parts(al.start, al.end):
                for lo, hi in split_span(a, b, window_days):
                    out.append(Window(int(rec["symbol_id"]), al.alias, lo, hi, part))
    order = {p: i for i, p in enumerate(PARTS)}
    return sorted(out, key=lambda w: (order[w.part], w.symbol_id, w.start))


def spy_symbol_id(layout: Layout | None = None) -> int:
    sym = io.read_parquet("snapshot/symbols.parquet", columns=["symbol_id", "ticker"], layout=layout)
    ids = sym.loc[sym["ticker"] == load_bars_config().fetch.spy_symbol, "symbol_id"].astype(int).tolist()
    if len(ids) != 1:
        raise ValueError(f"expected one SPY symbol in the snapshot, got {ids}")
    return ids[0]


# --- bars as a frame ----------------------------------------------------------------------------------

NOT_ON_GRID: Final = np.iinfo(np.int64).min


@dataclass(frozen=True)
class Chunk:
    """One answer's bars as numeric arrays (converted on receipt, so no vendor dicts are kept)."""

    symbol_id: int
    ticker: str
    key: str
    switches: str
    start_ns: npt.NDArray[np.int64]  # bar start, UTC nanoseconds
    ohlcv: npt.NDArray[np.float64]  # (n, 5): open, high, low, close, volume


def chunk_of(answer: Answer, symbol_id: int, tz: str) -> Chunk:
    rows = answer.bars
    local = pd.to_datetime(
        pd.Series([str(r["date"]) for r in rows], dtype=object), format="%Y-%m-%d %H:%M:%S"
    )
    start = local.dt.tz_localize(tz, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
    ohlcv = np.asarray([[r[c] for c in FIELDS[1:]] for r in rows], dtype="float64").reshape(len(rows), 5)
    req = answer.request
    return Chunk(
        symbol_id,
        req.symbol,
        answer.key,
        Switches(req.extended, req.nonadjusted, req.api).text(),
        np.asarray(start.dt.as_unit("ns").astype("int64").to_numpy(), dtype=np.int64),
        ohlcv,
    )


def label_arrays(
    start_ns: npt.NDArray[np.int64], tz: str
) -> tuple[npt.NDArray[Any], npt.NDArray[np.int64], npt.NDArray[np.bool_]]:
    """(session, slot, regular) per bar. ``session``: the bar's New York date if it is a session, else None
    (an object array that shares one ``date`` per day). ``slot``: 30-minute steps from the open (0 is the
    first regular bar, -1 the bar that ends at the open; ``NOT_ON_GRID`` off a session or off the step).
    ``regular``: 0 ≤ slot < the session's regular bar count (13 on a full day, 7 on a half day)."""
    minutes = load_bars_config().vendor.bar_minutes
    utc = pd.DatetimeIndex(start_ns.astype("datetime64[ns]")).tz_localize("UTC")
    local_day = utc.tz_convert(tz).normalize().tz_localize(None).to_numpy().astype("datetime64[D]")
    days, inv = np.unique(local_day, return_inverse=True)
    objs = np.empty(len(days), dtype=object)
    opens = np.zeros(len(days), dtype=np.int64)
    n_reg = np.zeros(len(days), dtype=np.int64)
    for k, d64 in enumerate(days):
        d = pd.Timestamp(d64).date()
        if calendar.is_session(d):
            objs[k], opens[k] = d, calendar.open_utc(d).value
            n_reg[k] = calendar.session_minutes(d) // minutes
    is_sess = np.asarray([o is not None for o in objs], dtype=bool)[inv]
    step = minutes * 60 * 1_000_000_000
    rel = start_ns - opens[inv]
    exact = is_sess & (rel % step == 0)
    slot = np.where(exact, rel // step, NOT_ON_GRID).astype(np.int64)
    regular = exact & (slot >= 0) & (slot < n_reg[inv])
    return objs[inv], slot, regular


def drop_aliased(chunks: Sequence[Chunk]) -> list[Chunk]:
    """The chunks without the primary ticker's bars inside an alias span (``fetch.aliases``: there the alias
    ticker's bars are the company's) or an excluded span (``fetch.exclude``: no usable bars)."""
    cfg = load_bars_config()
    tz = cfg.vendor.timezone
    rules = [(al.ticker, al.start, al.end) for al in cfg.fetch.aliases]
    rules += [(ex.ticker, ex.start, ex.end) for ex in cfg.fetch.exclude]
    out = []
    for c in chunks:
        keep = np.ones(len(c.start_ns), dtype=bool)
        for ticker, start, end in rules:
            if c.ticker == ticker:
                lo = pd.Timestamp(start, tz=tz).tz_convert("UTC").value
                hi = pd.Timestamp(end + timedelta(days=1), tz=tz).tz_convert("UTC").value
                keep &= ~((c.start_ns >= lo) & (c.start_ns < hi))
        out.append(
            c
            if keep.all()
            else Chunk(c.symbol_id, c.ticker, c.key, c.switches, c.start_ns[keep], c.ohlcv[keep])
        )
    return out


def frame_of(
    chunks: Sequence[Chunk], lo: date | None = None, hi: date | None = None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """One typed frame (``BAR_COLUMNS``) of the chunks' bars. With ``lo`` / ``hi``: only bars on a 30-minute
    slot of a session in [lo, hi], one per (symbol, bar start) (the first chunk's wins)."""
    tz = load_bars_config().vendor.timezone
    sizes = np.asarray([len(c.start_ns) for c in chunks], dtype=np.int64)
    which = np.repeat(np.arange(len(chunks)), sizes)
    start_ns = np.concatenate([c.start_ns for c in chunks]) if chunks else np.zeros(0, dtype=np.int64)
    ohlcv = np.concatenate([c.ohlcv for c in chunks]) if chunks else np.zeros((0, 5))
    session, slot, regular = label_arrays(start_ns, tz)
    keep = np.ones(len(start_ns), dtype=bool)
    if lo is not None and hi is not None:
        keep = (slot != NOT_ON_GRID) & np.asarray(
            [s is not None and lo <= s <= hi for s in session], dtype=bool
        )
    n0, n1 = len(keep), int(keep.sum())
    df = pd.DataFrame(
        {
            "symbol_id": np.asarray([c.symbol_id for c in chunks], dtype=np.int64)[which][keep],
            "ticker": _cat([c.ticker for c in chunks], which[keep]),
            "session": session[keep],
            "bar_start": pd.DatetimeIndex(start_ns[keep].astype("datetime64[ns]")).tz_localize("UTC"),
            "slot": slot[keep],
            "regular": regular[keep],
            "open": ohlcv[keep, 0],
            "high": ohlcv[keep, 1],
            "low": ohlcv[keep, 2],
            "close": ohlcv[keep, 3],
            "volume": ohlcv[keep, 4],
            "request_key": _cat([c.key for c in chunks], which[keep]),
            "switches": _cat([c.switches for c in chunks], which[keep]),
        }
    )
    stats = {"rows_received": n0, "rows_off_grid_or_range": n0 - n1}
    if lo is not None and hi is not None:
        df = df.assign(_w=which[keep]).sort_values(["symbol_id", "bar_start", "_w"], kind="mergesort")
        df = df.drop_duplicates(["symbol_id", "bar_start"], keep="first").drop(columns="_w")
        stats["rows_duplicate"] = n1 - len(df)
    return df.reset_index(drop=True)[list(BAR_COLUMNS)], stats


def _cat(values: Sequence[str], codes: npt.NDArray[np.int64]) -> pd.Categorical[Any]:
    """A categorical with one entry per chunk value, indexed by each bar's chunk."""
    cats = pd.Index(sorted(set(values)))
    per_chunk = cats.get_indexer(pd.Index(values))
    return pd.Categorical.from_codes(per_chunk[codes], categories=cats)


def to_frame(answer: Answer, symbol_id: int, tz: str) -> pd.DataFrame:
    """Every bar of one answer (off-grid and out-of-window bars included; the probe counts them)."""
    return frame_of([chunk_of(answer, symbol_id, tz)])[0]


# --- capability and the two parts ---------------------------------------------------------------------


def capability(layout: Layout | None = None) -> dict[str, Any]:
    """The probe's decision (``artifacts/NA-10/capability.json``); refuses a fetch the probe stopped."""
    lay = resolve_layout(layout)
    path = lay.root / CAPABILITY
    if not path.is_file():
        raise FmpError(f"{CAPABILITY} is missing: run newsaction.bars.probe first")
    cap = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if cap["projection"]["stop"]:
        raise FmpError(f"the probe stopped the fetch: {cap['projection']['reason']}")
    return cap


def switches_of(cap: dict[str, Any]) -> Switches:
    d = cap["decision"]
    return Switches(bool(d["extended"]), bool(d["nonadjusted"]), cast(Api, d.get("api", "stable")))


def fetch_windows(
    client: FmpClient, windows: Iterable[Window], sw: Switches, *, cache: bool, purpose: str
) -> tuple[list[Chunk], list[dict[str, Any]], int]:
    """Each window's answer as a ``Chunk`` (window order), the failures (the run goes on) and the number of
    empty answers. Progress (counts only) is printed every 500 windows."""
    tz = load_bars_config().vendor.timezone
    chunks: list[Chunk] = []
    failed: list[dict[str, Any]] = []
    empty = 0
    t0 = time.time()
    for i, w in enumerate(windows, 1):
        try:
            ans = client.get(w.request(sw), purpose=purpose, cache=cache)
        except FmpError as exc:
            failed.append(
                {
                    "symbol_id": w.symbol_id,
                    "ticker": w.ticker,
                    "start": w.start,
                    "end": w.end,
                    "error": str(exc),
                }
            )
            continue
        if ans.bars:
            chunks.append(chunk_of(ans, w.symbol_id, tz))
        else:
            empty += 1
        if i % 500 == 0:
            print(
                f"{purpose}: {i} windows, {client.sent} sent, {len(failed)} failed, {time.time() - t0:,.0f}s",
                flush=True,
            )
    return chunks, failed, empty


def preflight(
    client: FmpClient, windows: Sequence[Window], sw: Switches, layout: Layout | None = None
) -> dict[str, Any]:
    """Before the bulk of the fetch: the NVDA window holding its 10:1 split (2024-06-10) on the fetch's
    switches. Raises unless the first-bar opens of the sessions before and on the ex-date are within 1% of
    ATOM's raw EOD open (as traded, when ``nonadjusted``) and pre-market bars come on ≥ 90% of its sessions
    (when ``extended``): the two switches were each probed alone, never together."""
    ex = date(2024, 6, 10)
    w = next(x for x in windows if x.ticker == "NVDA" and x.start <= ex <= x.end)
    frame = to_frame(
        client.get(w.request(sw), purpose="fetch:public", cache=True),
        w.symbol_id,
        load_bars_config().vendor.timezone,
    )
    raw = io.read_parquet(
        "snapshot/prices_raw.parquet", columns=["symbol_id", "trade_date", "open"], layout=layout
    )
    px = raw.loc[raw["symbol_id"] == w.symbol_id].set_index("trade_date")["open"]
    first = frame.loc[frame["regular"] & (frame["slot"] == 0)].set_index("session")["open"]
    days = [calendar.prev_session(ex), ex]
    ratios = {d.isoformat(): float(first.get(d, np.nan) / px.get(d, np.nan)) for d in days}
    sessions = {s for s in frame["session"] if s is not None and w.start <= s <= w.end}
    pre = {s for s, k in zip(frame["session"], frame["slot"], strict=True) if k == -1 and s in sessions}
    share = len(pre) / max(1, len(sessions))
    if sw.nonadjusted and not all(abs(r - 1) <= 0.01 for r in ratios.values()):
        raise FmpError(f"pre-flight: levels are not as traded around NVDA's split: {ratios}")
    if sw.extended and share < 0.9:
        raise FmpError(f"pre-flight: pre-market bars on {share:.0%} of sessions")
    return {"window": [w.start, w.end], "first_open_over_eod_open": ratios, "pre_market_share": share}


def run_public(*, dry_run: bool = False, layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    cap = capability(lay)
    sw = switches_of(cap)
    windows = [w for w in plan(int(cap["decision"]["window_days"]), layout=lay) if w.part == "public"]
    with FmpClient(layout=lay) as client:
        todo = [w for w in windows if client.cached(w.request(sw)) is None]
        info: dict[str, Any] = {
            "windows": len(windows),
            "to_request": len(todo),
            "remaining": client.ledger.remaining(),
        }
        if dry_run:
            return info
        if len(todo) > client.ledger.remaining():
            raise FmpError(f"public part needs {len(todo)} requests, {client.ledger.remaining()} remain")
        info["preflight"] = preflight(client, windows, sw, lay)
        chunks, failed, empty = fetch_windows(client, windows, sw, cache=True, purpose="fetch:public")
        info["sent"] = client.sent
    lo = load_bars_config().fetch.spy_start
    bars, stats = frame_of(drop_aliased(chunks), lo, public_end())
    del chunks
    entry = io.write_parquet(
        bars,
        BARS_PUBLIC,
        producer=PRODUCER,
        description="NA-10 S3: FMP 30-minute bars of public sessions (≤ val-B end), probe switches",
        layout=lay,
    )
    info.update(stats, failed=failed, empty_answers=empty, rows=entry["rows"], sha256=entry["sha256"])
    return info


def write_test_part(chunks: Sequence[Chunk], *, layout: Layout | None = None) -> dict[str, Any]:
    """Write the test-period chunks once through ``lock.write_sealed`` and return counts only. If framing
    fails, the chunks' raw arrays are sealed first (``<name>_raw``), so no request has to be repeated."""
    lay = resolve_layout(layout)
    t0, t1 = test_range()
    name = blinded_bars_name()
    try:
        bars, stats = frame_of(drop_aliased(chunks), t0, t1)
    except Exception:
        raw = pd.DataFrame(
            {
                "symbol_id": np.repeat([c.symbol_id for c in chunks], [len(c.start_ns) for c in chunks]),
                "bar_start_ns": np.concatenate([c.start_ns for c in chunks]),
                **{k: np.concatenate([c.ohlcv[:, i] for c in chunks]) for i, k in enumerate(FIELDS[1:])},
            }
        )
        lock.write_sealed(raw, f"{name}_raw", producer=PRODUCER, description="NA-10 S3 fallback", layout=lay)
        raise
    entry = lock.write_sealed(
        bars,
        name,
        producer=PRODUCER,
        description="NA-10 S3: FMP 30-minute bars of test-period sessions (blinded, never read here)",
        layout=lay,
    )
    return {**stats, "rows": entry["rows"], "sha256": entry["sha256"]}


def run_test(*, dry_run: bool = False, layout: Layout | None = None) -> dict[str, Any]:
    """Fetch the test-period windows and write them through the lock. Nothing about their content is
    printed: only counts of requests, answers and rows."""
    lay = resolve_layout(layout)
    cap = capability(lay)
    sw = switches_of(cap)
    windows = [w for w in plan(int(cap["decision"]["window_days"]), layout=lay) if w.part == "test"]
    with FmpClient(layout=lay) as client:
        info: dict[str, Any] = {"windows": len(windows), "remaining": client.ledger.remaining()}
        margin = math.ceil(1.05 * len(windows))
        if dry_run:
            return info
        if margin > client.ledger.remaining():
            raise FmpError(f"test part needs about {margin} requests, {client.ledger.remaining()} remain")
        chunks, failed, empty = fetch_windows(client, windows, sw, cache=False, purpose="fetch:test")
        for _ in range(2):  # failed windows are asked again before the one write (no later top-up)
            again = {(f["symbol_id"], f["start"]) for f in failed}
            retry = [w for w in windows if (w.symbol_id, w.start) in again]
            if not retry:
                break
            more, failed, more_empty = fetch_windows(client, retry, sw, cache=False, purpose="fetch:test")
            chunks += more
            empty += more_empty
        info["sent"] = client.sent
    info.update(write_test_part(chunks, layout=lay))
    info.update(failed=[{k: str(v) for k, v in f.items()} for f in failed], empty_answers=empty)
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="newsaction.bars.fetch", description=__doc__)
    ap.add_argument("--part", choices=PARTS, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    run = run_public if args.part == "public" else run_test
    info = run(dry_run=args.dry_run)
    rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS
    print(json.dumps(info, indent=1, default=str)[:6000])
    print(f"fetch {args.part}: {time.time() - t0:,.0f}s, peak RSS {rss_gb:.1f} GB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
