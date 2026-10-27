"""NA-10 S2: the capability probe, at most 5 FMP requests (PRD NA-10 S2).

    uv run python -m newsaction.bars.probe

1. AAPL, 30-minute bars, 2025-01-02 .. 2025-12-31, default switches: does one year come back whole
   (every regular bar of every session: 13 on a full day, 7 on a half day)?
2. The same with ``extended=true``: are pre-market bars served (the bar that ends at the open)?
3. NVDA 2024-06-03 .. 2024-06-14 with ``nonadjusted=true`` (10:1 split, ex-date 2024-06-10): are the levels
   as traded on both sides of the split (first-bar open ≈ ATOM's raw EOD open)?
4. A 2-year window, NVDA 2024-01-02 .. 2025-12-31, on the fetch's price basis (``nonadjusted`` if
   honoured): any cap at two years? ``extended`` is left out: probes 1 and 2 cover the same days with
   different row counts, so it changes rows, not the days an answer covers.
5. Only if 4 is not whole: the first year of that window with the same switches.

**Window cap.** A truncated answer that keeps every bar of its last sessions (oldest dropped, as IR-04 found
at 1 minute) bounds the calendar days N one answer covers: N ≥ days from its first served session to
``to``, and N < days from the latest unserved session before it to ``to`` + 1 (``day_bounds``). The window
used is the lower end of the bounds common to every truncated probe.

Every answer is cached (all windows end before the test period), so a re-run sends nothing; the probe's own
cap (``probe.max_requests`` over every run, counted in the ledger) refuses a sixth request. The projection is
the fetch plan's request count (``fetch.plan``) with that window, compared with the FMP requests left under
the cap: if it is larger the probe records ``stop`` and the fetch refuses to start (PRD: STOP and report).
Output: ``artifacts/NA-10/capability.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

import pandas as pd

from newsaction import calendar, io
from newsaction.bars import CAPABILITY, CHUNK, load_bars_config
from newsaction.bars.fetch import (
    NOT_ON_GRID,
    Switches,
    member_spans,
    plan,
    public_end,
    split_span,
    spy_symbol_id,
    test_range,
    to_frame,
)
from newsaction.bars.fmp30 import Answer, BarRequest, FmpClient, FmpError
from newsaction.config import load_project
from newsaction.ledger import FMP_REQUESTS, FmpLedger
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import git_sha, utc_now_iso

YEAR: Final = (date(2025, 1, 2), date(2025, 12, 31))
TWO_YEARS: Final = (date(2024, 1, 2), date(2025, 12, 31))
NVDA_SPLIT: Final = (date(2024, 6, 3), date(2024, 6, 14))
NVDA_EX: Final = date(2024, 6, 10)
AS_TRADED_TOLERANCE: Final = 0.01  # first-bar open within 1% of the EOD raw open: as traded (a split is ≥ 2×)
PRE_MARKET_SHARE: Final = 0.9  # pre-market bars served on at least this share of sessions


@dataclass(frozen=True)
class Probe:
    name: str
    request: BarRequest


def expected_regular(d: date) -> int:
    return calendar.session_minutes(d) // load_bars_config().vendor.bar_minutes


def raw_opens(symbol_ids: Sequence[int], layout: Layout | None = None) -> pd.DataFrame:
    """ATOM raw EOD opens (public snapshot) of the probed symbols: (symbol_id, session, open)."""
    px = io.read_parquet(
        "snapshot/prices_raw.parquet", columns=["symbol_id", "trade_date", "open"], layout=layout
    )
    px = px.loc[px["symbol_id"].isin(list(symbol_ids))].rename(columns={"trade_date": "session"})
    return px.reset_index(drop=True)


def summarize(answer: Answer, frame: pd.DataFrame, eod: pd.DataFrame) -> dict[str, Any]:
    """Counts and checks of one probe answer (no price statistic beyond the open reconciliation)."""
    req = answer.request
    want = calendar.sessions(req.start, req.end)
    inside = frame.loc[[s is not None and req.start <= s <= req.end for s in frame["session"]]]
    reg = inside.loc[inside["regular"]]
    per = reg.groupby("session").size()
    full = [d for d in want if int(per.get(d, 0)) == expected_regular(d)]
    pre = inside.loc[inside["slot"] == -1, "session"].nunique()
    n_reg = {d: expected_regular(d) for d in want}
    post = sum(int(((inside["session"] == d) & (inside["slot"] >= n)).sum()) for d, n in n_reg.items())
    first = reg.sort_values("bar_start").groupby("session").head(1)
    rec = first.merge(eod, on=["session", "symbol_id"], how="left")
    ratio = rec["open_x"] / rec["open_y"]
    labels = (
        frame["bar_start"].dt.tz_convert(load_bars_config().vendor.timezone).dt.strftime("%Y-%m-%d %H:%M")
    )
    return {
        "name": None,
        "request": req.describe(load_bars_config().vendor.interval),
        "from_cache": answer.from_cache,
        "rows": len(answer.bars),
        "first_bar": labels.min() if len(frame) else None,
        "last_bar": labels.max() if len(frame) else None,
        "rows_outside_window_or_grid": int(len(frame) - (inside["slot"] != NOT_ON_GRID).sum()),
        "sessions_expected": len(want),
        "sessions_with_regular_bars": int(per.size),
        "sessions_served": [d.isoformat() for d in sorted(per.index)],
        "sessions_complete": len(full),
        "first_missing_session": next((d.isoformat() for d in want if d not in set(full)), None),
        "regular_bars": len(reg),
        "regular_bars_expected": int(sum(n_reg.values())),
        "bars_outside_regular_hours": int((~inside["regular"]).sum()),
        "sessions_with_pre_market_bar": int(pre),
        "post_market_bars": post,
        "whole": len(full) == len(want) and len(reg) == sum(n_reg.values()),
        "first_open_vs_eod_open": {
            "sessions": int(ratio.notna().sum()),
            "within_5bp": int(((ratio - 1).abs() <= 5e-4).sum()),
            "within_1pct": int(((ratio - 1).abs() <= 0.01).sum()),
            "ratio_median": float(ratio.median()) if ratio.notna().any() else None,
        },
    }


def as_traded(frame: pd.DataFrame, eod: pd.DataFrame, sessions: Sequence[date]) -> dict[str, Any]:
    """First-bar open / ATOM raw EOD open on each of ``sessions``: ≈ 1 as traded, ≈ 1/10 split-adjusted."""
    reg = frame.loc[frame["regular"]].sort_values("bar_start").groupby("session").head(1)
    m = reg.merge(eod, on=["session", "symbol_id"], how="inner")
    ratios = {
        d.isoformat(): float(
            m.loc[m["session"] == d, "open_x"].iloc[0] / m.loc[m["session"] == d, "open_y"].iloc[0]
        )
        for d in sessions
        if (m["session"] == d).any()
    }
    ok = len(ratios) == len(sessions) and all(abs(r - 1) <= AS_TRADED_TOLERANCE for r in ratios.values())
    return {"first_open_over_eod_open": ratios, "as_traded": ok}


def day_bounds(summary: dict[str, Any]) -> tuple[int, int | None] | None:
    """[lo, hi] on the calendar days one answer covers (``hi`` None if the answer is whole); None if the
    answer is not a clean newest-first cut (a served session is incomplete, or a gap after the first one)."""
    req = summary["request"]
    lo_d, hi_d = date.fromisoformat(req["from"]), date.fromisoformat(req["to"])
    served = [date.fromisoformat(d) for d in summary["sessions_served"]]
    if not served:
        return None
    want = calendar.sessions(lo_d, hi_d)
    tail = [d for d in want if d >= served[0]]
    if tail != served or summary["sessions_complete"] != len(served):
        return None
    if len(served) == len(want):
        return (hi_d - lo_d).days + 1, None
    missing = [d for d in want if d < served[0]]
    return (hi_d - served[0]).days + 1, (hi_d - missing[-1]).days


def common_bounds(bounds: Sequence[tuple[int, int | None] | None]) -> tuple[int, int | None] | None:
    """Intersection of the truncated answers' bounds (None if one is unclean or they do not overlap)."""
    cut = [b for b in bounds if b is None or b[1] is not None]
    if not cut or any(b is None for b in cut):
        return None
    lo = max(b[0] for b in cut if b is not None)
    his = [b[1] for b in cut if b is not None and b[1] is not None]
    hi = min(his) if his else None
    return None if hi is not None and hi < lo else (lo, hi)


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    cfg = load_bars_config()
    tz = cfg.vendor.timezone
    sym = io.read_parquet("snapshot/symbols.parquet", columns=["symbol_id", "ticker"], layout=lay)
    sid = {str(t): int(s) for s, t in zip(sym["symbol_id"], sym["ticker"], strict=True)}
    eod = raw_opens([sid["AAPL"], sid["NVDA"]], lay)
    # The probe's own cap: its requests over every run never exceed probe.max_requests (PRD S2) plus the
    # operator's approved_extra (the v3 check).
    ledger = FmpLedger(lay.ledgers / FMP_REQUESTS)
    before = ledger.count()
    spent = sum(r.get("event") == "request" and r["meta"].get("purpose") == "probe" for r in ledger.records())
    allowed = cfg.probe.max_requests + cfg.probe.approved_extra
    cap = min(ledger.cap, before + max(0, allowed - spent))
    v3_errors: dict[str, str] = {}
    with FmpClient(layout=lay, ledger=FmpLedger(ledger.path, cap=cap)) as client:
        results: dict[str, dict[str, Any]] = {}
        frames: dict[str, pd.DataFrame] = {}

        def ask(p: Probe) -> None:
            ans = client.get(p.request, purpose="probe", cache=True)
            frame = to_frame(ans, sid[p.request.symbol], tz)
            frames[p.name] = frame
            results[p.name] = {**summarize(ans, frame, eod), "name": p.name}

        ask(Probe("1_default_1y", BarRequest("AAPL", *YEAR)))
        ask(Probe("2_extended_1y", BarRequest("AAPL", *YEAR, extended=True)))
        ask(Probe("3_nonadjusted_split", BarRequest("NVDA", *NVDA_SPLIT, nonadjusted=True)))

        ext = results["2_extended_1y"]
        pre_share = ext["sessions_with_pre_market_bar"] / max(1, ext["sessions_with_regular_bars"])
        extended_served = ext["bars_outside_regular_hours"] > 0 and pre_share >= PRE_MARKET_SHARE
        split_days = [calendar.prev_session(NVDA_EX), NVDA_EX]
        nonadj = as_traded(frames["3_nonadjusted_split"], eod, split_days)
        sw = Switches(extended=extended_served, nonadjusted=bool(nonadj["as_traded"]))
        cap_sw = Switches(extended=False, nonadjusted=sw.nonadjusted)

        ask(Probe("4_two_years", BarRequest("NVDA", *TWO_YEARS, nonadjusted=cap_sw.nonadjusted)))
        if not results["4_two_years"]["whole"]:
            one = (TWO_YEARS[0], date(TWO_YEARS[0].year, 12, 31))
            ask(Probe("5_one_year", BarRequest("NVDA", *one, nonadjusted=cap_sw.nonadjusted)))
            # 6-7 (operator approval 2026-10-27): does the legacy /api/v3 endpoint serve a longer window?
            v3 = [
                Probe("6_v3_1y", BarRequest("AAPL", *YEAR, api="v3")),
                Probe(
                    "7_v3_two_years",
                    BarRequest(
                        "NVDA", *TWO_YEARS, extended=sw.extended, nonadjusted=sw.nonadjusted, api="v3"
                    ),
                ),
            ]
            for p in v3:
                try:
                    ask(p)
                except FmpError as exc:
                    v3_errors[p.name] = str(exc)
                    break
                if not results[p.name]["whole"]:
                    break
        sent = client.sent
    after = ledger.count()

    per_probe = {k: day_bounds(v) for k, v in results.items() if k[0] in "1245"}
    bounds = common_bounds(list(per_probe.values()))
    window_days = 0 if bounds is None else bounds[0]
    v3_whole = [k for k in ("7_v3_two_years", "6_v3_1y") if results.get(k, {}).get("whole")]
    if v3_whole:  # a longer window on v3: its switches are what probe 7 shows (or none if 7 was not whole)
        best = v3_whole[0]
        req = results[best]["request"]
        window_days = (date.fromisoformat(req["to"]) - date.fromisoformat(req["from"])).days + 1
        if best == "7_v3_two_years":
            got = results[best]
            served = max(1, got["sessions_with_regular_bars"])
            v3_ext = sw.extended and got["sessions_with_pre_market_bar"] / served >= PRE_MARKET_SHARE
            v3_nonadj = sw.nonadjusted and bool(as_traded(frames[best], eod, split_days)["as_traded"])
            sw = Switches(extended=v3_ext, nonadjusted=v3_nonadj, api="v3")
        else:
            sw = Switches(extended=False, nonadjusted=False, api="v3")
    facts = {
        "one_year_whole_default": results["1_default_1y"]["whole"],
        "two_year_window_whole": results["4_two_years"]["whole"],
        "window_cap_days": None if bounds is None else {"lo": bounds[0], "hi": bounds[1]},
        "window_cap_per_probe": {
            k: None if b is None else {"lo": b[0], "hi": b[1]} for k, b in per_probe.items()
        },
        "window_cap_kind": "calendar days ending at `to`, oldest dropped" if bounds and bounds[1] else None,
        "extended_served": extended_served,
        "pre_market_bar_share_of_served_sessions": pre_share,
        "extended_adds_rows_not_days": results["1_default_1y"]["sessions_served"]
        == results["2_extended_1y"]["sessions_served"],
        "extended_regular_bars_equal_default": _same_regular(frames["1_default_1y"], frames["2_extended_1y"]),
        "nonadjusted_honoured": bool(nonadj["as_traded"]),
        "nonadjusted_check": nonadj,
        "extended_with_nonadjusted": "probe 7 (v3) only" if "7_v3_two_years" in results else "not tested",
        "v3_window_whole": {k: results[k]["whole"] for k in ("6_v3_1y", "7_v3_two_years") if k in results},
        "v3_window_cap_days": {
            k: None if (b := day_bounds(results[k])) is None else {"lo": b[0], "hi": b[1]}
            for k in ("6_v3_1y", "7_v3_two_years")
            if k in results
        },
        "v3_errors": v3_errors,
    }
    decision = {
        "api": sw.api,
        "extended": sw.extended,
        "nonadjusted": sw.nonadjusted,
        "basis": "as_traded" if sw.nonadjusted else "rescaled_to_eod_open",
        "window_days": window_days,
    }
    projection = project(window_days, sw, lay)
    out = {
        "chunk": CHUNK,
        "probe_date": utc_now_iso(),
        "git_sha": git_sha(lay.root),
        "endpoint": {
            "base_url": cfg.vendor.base_url,
            "path": cfg.vendor.path,
            "interval": cfg.vendor.interval,
        },
        "vendor_timezone": tz,
        "bar_label": "start (first regular bar at the open; ATOM IR-04)",
        "requests_sent_this_run": sent,
        "probe_requests_total": sum(
            r.get("event") == "request" and r["meta"].get("purpose") == "probe" for r in ledger.records()
        ),
        "ledger_requests_before": before,
        "ledger_requests_after": after,
        "probes": list(results.values()),
        "facts": facts,
        "decision": decision,
        "projection": projection,
        "fmp_request_cap": load_project().fmp_request_cap,
        "ledger_requests_remaining": ledger.remaining(),
        "corroboration": "ATOM IR-04 (docs/runbooks/fmp_intraday_capability.json, intervals.30min): a 30-day "
        "request 2023-12-21 .. 2024-01-19 came back whole (247 rows, 19 sessions)",
    }
    path = lay.root / CAPABILITY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    return out


def _same_regular(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    cols = ["bar_start", "open", "high", "low", "close", "volume"]
    x = a.loc[a["regular"], cols].reset_index(drop=True)
    y = b.loc[b["regular"], cols].sort_values("bar_start").reset_index(drop=True)
    return bool(len(x) == len(y) and x.sort_values("bar_start").reset_index(drop=True).equals(y))


def project(window_days: int, sw: Switches, layout: Layout | None = None) -> dict[str, Any]:
    """Requests the fetch needs with ``window_days`` windows (cached answers excluded) vs those left."""
    cap = load_project().fmp_request_cap
    if window_days <= 0:
        return {
            "stop": True,
            "reason": "no window size returned whole bars: owner decision",
            "requests_needed": None,
        }
    windows = plan(window_days, layout=layout)
    with FmpClient(layout=layout) as client:
        cached = sum(client.cached(w.request(sw)) is not None for w in windows)
        used = client.ledger.count()
    by_part = {p: sum(w.part == p for w in windows) for p in ("public", "test")}
    spy = spy_symbol_id(layout)
    spans: dict[int, int] = {}
    for w in windows:
        spans[w.symbol_id] = spans.get(w.symbol_id, 0) + (w.end - w.start).days + 1
    prd_formula = sum(math.ceil(v / window_days) for v in spans.values())
    needed = len(windows) - cached
    stop = used + needed > cap
    return {
        "scopes": scope_counts(window_days, layout),
        "window_days": window_days,
        "symbols": len(spans) - (spy in spans),
        "spy": spy in spans,
        "windows": len(windows),
        "windows_by_part": by_part,
        "windows_cached": cached,
        "requests_needed": needed,
        "requests_prd_formula": prd_formula,
        "ledger_requests_used": used,
        "cap": cap,
        "headroom_after_fetch": cap - used - needed,
        "stop": stop,
        "reason": "projection exceeds the FMP cap: STOP, owner decision" if stop else "within the cap",
    }


def scope_counts(window_days: int, layout: Layout | None = None) -> dict[str, int]:
    """Requests for narrower scopes at the same window (for the owner's decision; no warm-up history)."""
    spans = member_spans(layout)
    pub_end = public_end()
    t0, t1 = test_range()

    def count(lo: date, hi: date, rows: pd.DataFrame) -> int:
        n = 0
        for rec in rows.to_dict("records"):
            a, b = max(lo, rec["first"]), min(hi, rec["last"])
            for part_lo, part_hi in ((a, min(b, pub_end)), (max(a, t0), b)):
                if part_lo <= part_hi:
                    n += len(split_span(part_lo, part_hi, window_days))
        return n

    return {
        "prd_span_2024_06_03_to_test_end": count(date(2024, 6, 3), t1, spans),
        "val_a_to_test_end": count(date(2025, 7, 1), t1, spans),
        "test_only": count(t0, t1, spans),
        "val_a_and_val_b_only": count(date(2025, 7, 1), pub_end, spans),
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="newsaction.bars.probe", description=__doc__).parse_args(argv)
    out = run()
    print(
        json.dumps(
            {k: out[k] for k in ("requests_sent_this_run", "facts", "decision", "projection")},
            indent=1,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
