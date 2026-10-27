"""NA-10 AC1: the FMP request cap (PREREG §13, raised in §15 by the operator; CLAUDE.md E18).

- ``FmpLedger`` refuses request cap + 1, from a ledger already holding cap requests; responses do not count;
- the client reserves every attempt before sending it, sends nothing once the cap is reached and reserves a
  retry again; the key never reaches the ledger or the cache; a test-period window is never cached; the
  interval cannot be anything but 30 minutes;
- the real ledger holds at most the cap, and every request has its response line.

Mutation (PRD AC1): drop the cap check in ``FmpLedger.reserve`` and the first three tests fail.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from newsaction.bars import VendorConfig, load_bars_config
from newsaction.bars.fmp30 import BarRequest, FmpClient
from newsaction.config import load_project, load_splits
from newsaction.ledger import GENESIS, FmpCapExceeded, FmpLedger, _encode, _hash
from newsaction.paths import Layout

KEY = "TESTKEY-not-a-real-key-0123456789"
BAR = {"date": "2025-01-02 09:30:00", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10}


def _prefill(path: Path, n: int) -> None:
    """``n`` chained request lines, written directly (the ledger's own encoding and hash chain)."""
    prev = GENESIS
    with path.open("wb") as fh:
        for i in range(1, n + 1):
            rec = {
                "event": "request",
                "n": i,
                "meta": {"symbol": "X"},
                "ts": "2026-10-27T00:00:00",
                "prev": prev,
            }
            line = _encode(rec)
            fh.write(line + b"\n")
            prev = _hash(line)


def _client(tmp_path: Path, handler: httpx.MockTransport, cap: int) -> tuple[FmpClient, list[httpx.Request]]:
    (tmp_path / "work").mkdir(exist_ok=True)
    (tmp_path / "ledgers").mkdir(exist_ok=True)
    led = FmpLedger(tmp_path / "ledgers" / "fmp_requests.jsonl", cap=cap)
    return FmpClient(
        layout=Layout(tmp_path), ledger=led, transport=handler, api_key=KEY, sleep=lambda s: None
    ), []


def test_ledger_refuses_the_request_after_the_configured_cap(tmp_path: Path) -> None:
    cap = load_project().fmp_request_cap
    path = tmp_path / "fmp.jsonl"
    _prefill(path, cap)
    led = FmpLedger(path)
    assert led.count() == cap and led.remaining() == 0
    with pytest.raises(FmpCapExceeded):
        led.reserve({"symbol": "Y"})
    assert FmpLedger(path).count() == cap  # the refused request left no line


def test_ledger_counts_requests_not_responses(tmp_path: Path) -> None:
    led = FmpLedger(tmp_path / "fmp.jsonl", cap=2)
    n = led.reserve({"symbol": "A"})
    led.record_response(n, status=200, rows=13)
    led.reserve({"symbol": "B"})
    led.record_response(2, status=None, rows=None, error="ConnectTimeout")
    assert led.count() == 2
    with pytest.raises(FmpCapExceeded):
        led.reserve({"symbol": "C"})


def test_client_sends_nothing_past_the_cap(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def answer(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=[BAR])

    client, _ = _client(tmp_path, httpx.MockTransport(answer), cap=2)
    for sym in ("AAA", "BBB"):
        client.get(BarRequest(sym, date(2025, 1, 2), date(2025, 1, 31)), purpose="test")
    with pytest.raises(FmpCapExceeded):
        client.get(BarRequest("CCC", date(2025, 1, 2), date(2025, 1, 31)), purpose="test")
    assert len(seen) == 2 and client.ledger.count() == 2
    lines = [json.loads(x) for x in client.ledger.path.read_text().splitlines()]
    assert [x["event"] for x in lines] == ["request", "response", "request", "response"]
    assert lines[0]["meta"]["symbol"] == "AAA" and lines[1]["rows"] == 1 and lines[1]["status"] == 200


def test_client_reserves_each_retry_and_reads_the_cache_for_free(tmp_path: Path) -> None:
    statuses = iter([503, 200])

    def answer(req: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), json=[BAR])

    client, _ = _client(tmp_path, httpx.MockTransport(answer), cap=10)
    req = BarRequest("AAA", date(2025, 1, 2), date(2025, 1, 31))
    first = client.get(req, purpose="test")
    assert client.ledger.count() == 2 and first.n == 2 and not first.from_cache
    again = client.get(req, purpose="test")
    assert again.from_cache and again.bars == first.bars and client.ledger.count() == 2


def test_key_never_reaches_ledger_or_cache(tmp_path: Path) -> None:
    sent: list[dict[str, str]] = []

    def answer(req: httpx.Request) -> httpx.Response:
        sent.append(dict(req.url.params))
        return httpx.Response(200, json=[BAR])

    client, _ = _client(tmp_path, httpx.MockTransport(answer), cap=5)
    client.get(BarRequest("AAA", date(2025, 1, 2), date(2025, 1, 31), extended=True), purpose="test")
    assert sent[0]["apikey"] == KEY and sent[0]["extended"] == "true"
    assert KEY not in client.ledger.path.read_text()
    cached = list((tmp_path / "work" / "bars30" / "raw").glob("*.json.gz"))
    assert len(cached) == 1 and KEY.encode() not in gzip.decompress(cached[0].read_bytes())


def test_test_period_window_is_never_cached(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, httpx.MockTransport(lambda r: httpx.Response(200, json=[])), cap=5)
    t0 = load_splits().splits["test"].start
    ans = client.get(BarRequest("AAA", t0, t0), purpose="test", cache=True)
    assert ans.status == 200 and not (tmp_path / "work" / "bars30" / "raw").exists()


def test_interval_is_thirty_minutes_only() -> None:
    cfg = load_bars_config().vendor
    assert cfg.interval == "30min" and "1min" not in cfg.path and "30min" in cfg.path_v3
    with pytest.raises(ValidationError):
        VendorConfig.model_validate({**cfg.model_dump(), "interval": "1min"})


def test_real_ledger_within_the_cap_and_every_request_answered() -> None:
    led = FmpLedger()
    recs = led.records()
    requests = [r for r in recs if r["event"] == "request"]
    answered = {r["n"] for r in recs if r["event"] == "response"}
    assert led.count() == len(requests) <= load_project().fmp_request_cap
    assert [r["n"] for r in requests] == list(range(1, len(requests) + 1))
    assert {r["n"] for r in requests} - answered <= {len(requests)}  # only a request in flight may lack one
