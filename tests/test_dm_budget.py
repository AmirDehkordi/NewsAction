"""Budget guard of the decision client (PRD NA-05 AC1; PREREG §13; CLAUDE.md C12).

A batch whose projection exceeds what the chunk cap leaves raises before any send; every sent call reserves
its estimate before it is sent and records ``usage.cost`` after it, so the ledger reconciles with the cache.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from dm_fakes import MODEL, Recorder, make_client, ok_response, spec, spend_events
from newsaction.config import BudgetConfig
from newsaction.ledger import BudgetExceeded
from newsaction.paths import Layout


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")


def test_projection_over_the_chunk_cap_raises_before_any_send(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    tiny = BudgetConfig(total_usd=1.0, reserve_usd=0.0, chunk_caps={"NA-05": 1e-6})
    client = make_client(tmp_layout, tmp_path, rec, budget=tiny)
    specs = [spec(repeat_idx=i) for i in range(5)]
    proj = client.dry_run(specs)
    assert proj.n_send == 5 and proj.usd > 1e-6
    with pytest.raises(BudgetExceeded, match="projection"):
        client.decide(specs)
    assert rec.calls == 0
    assert spend_events(tmp_layout) == []


def test_projection_counts_open_holds_and_spend(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    hold = client.ledger.reserve(0.2 - 1e-7, note="someone else's batch")
    with pytest.raises(BudgetExceeded):
        client.decide([spec()])
    assert rec.calls == 0
    client.ledger.release(hold)
    assert client.decide([spec()])[0].ok
    assert rec.calls == 1


def test_every_call_reserves_before_it_records(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    results = client.decide([spec(repeat_idx=i) for i in range(4)], concurrency=2)
    assert all(r.ok and not r.cached for r in results)
    events = spend_events(tmp_layout)
    reserves = {e["rid"]: i for i, e in enumerate(events) if e["event"] == "reserve"}
    spends = [(i, e) for i, e in enumerate(events) if e["event"] == "spend"]
    assert len(spends) == 4 and len(reserves) == 4
    for i, e in spends:
        assert e["rid"] in reserves and reserves[e["rid"]] < i  # reserved before the spend line
        assert e["unreserved"] is False and e["close"] is True
        assert e["usd"] == pytest.approx(0.0001)
    assert client.reconcile() == pytest.approx(0.0, abs=1e-12)
    totals = client.ledger.totals()
    assert totals.chunk_usd == pytest.approx(0.0004)
    assert totals.held_chunk_usd == pytest.approx(0.0)


def test_http_error_releases_the_hold_and_records_nothing(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(lambda body, n: httpx.Response(400, json={"error": {"code": 400, "message": "bad"}}))
    client = make_client(tmp_layout, tmp_path, rec)
    res = client.decide([spec()])[0]
    assert not res.ok and res.status == 400 and rec.calls == 1  # 4xx: no retry
    events = [e["event"] for e in spend_events(tmp_layout)]
    assert events == ["reserve", "release"]
    assert client.ledger.totals().held_chunk_usd == 0.0
    assert client.reconcile() == 0.0


def test_429_is_retried_and_billed_once(tmp_layout: Layout, tmp_path: Path) -> None:
    def respond(body: dict[str, Any], n: int) -> httpx.Response:
        if n == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"code": 429}})
        return httpx.Response(200, json=ok_response(body))

    rec = Recorder(respond)
    client = make_client(tmp_layout, tmp_path, rec)
    client.config = client.config.model_copy(
        update={
            "api": client.config.api.model_copy(
                update={"retry": client.config.api.retry.model_copy(update={"initial_s": 0.001})}
            )
        }
    )
    res = client.decide([spec()])[0]
    assert res.ok and res.attempts == 2 and rec.calls == 2
    assert [e["event"] for e in spend_events(tmp_layout)] == ["reserve", "spend"]
    attempts = client.cache.frame("attempts")
    assert attempts["status"].tolist() == [429, 200]


def test_missing_usage_cost_is_computed_and_recorded(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(lambda body, n: httpx.Response(200, json=ok_response(body, cost=None, tokens=250)))
    client = make_client(tmp_layout, tmp_path, rec)
    res = client.decide([spec()])[0]
    assert res.row is not None and res.row.cost_source == "computed"
    assert res.row.cost == pytest.approx(250e-6)
    assert client.reconcile() == pytest.approx(0.0, abs=1e-12)


def test_local_calls_spend_nothing(tmp_layout: Layout, tmp_path: Path) -> None:
    from dm_fakes import LOCAL

    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    res = client.decide([spec(model=LOCAL)])[0]
    assert res.ok and res.row is not None and res.row.cost == 0.0 and res.row.cost_source == "local"
    assert rec.calls == 0 and spend_events(tmp_layout) == []


def test_projection_is_zero_for_cached_requests(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    client.decide([spec()])
    proj = client.dry_run([spec(), spec(repeat_idx=1)])
    assert proj.n_cached == 1 and proj.n_send == 1
    assert proj.by_model[MODEL]["calls"] == 1
