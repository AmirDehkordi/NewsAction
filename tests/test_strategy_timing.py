"""NA-13 AC1: every entry strictly after its decision; every input available at or before it (PREREG §2.5).

The synthetic market (val-B dates) checks the guard and the legs; the stored position files check the real
books. Mutations that must turn this file RED: enter S-D2 at the close of t (``ENTRY_OF_POINT["D2"]`` or
``ENTRIES["open_t+1"]``), or S-D0 at the previous close.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar, io
from newsaction.paths import resolve_layout
from newsaction.strategy import portfolios as pf
from newsaction.strategy import run

SESSIONS = calendar.sessions(date(2025, 10, 1), date(2025, 11, 28))
SYMBOLS = list(range(1, 61))
TIERS = ["top100"] * 20 + ["mid"] * 20 + ["rest"] * 20


def market(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    spy = {d: rng.normal(0, 0.01, 3) for d in SESSIONS}
    for d in SESSIONS:
        for s in SYMBOLS:
            r = rng.normal(0, 0.02, 3)
            rows.append(
                {
                    "session": d,
                    "symbol_id": s,
                    "raw_open": 100.0,
                    "raw_close": 101.0,
                    "p10": 100.5,
                    "r_cc": r[0],
                    "r_id": r[1],
                    "r_10c": r[2],
                    "r_spy_cc": spy[d][0],
                    "r_spy_id": spy[d][1],
                    "r_spy_10c": spy[d][2],
                    "beta_m": 0.5 + s / 60.0,
                    "adv20": 1e8 + s * 1e6,
                }
            )
    return pd.DataFrame(rows)


def events(days: list[date]) -> pd.DataFrame:
    rows = []
    for d in days:
        for s, t in zip(SYMBOLS, TIERS, strict=True):
            rows.append({"event_id": f"E:{s}:{d}", "session": d, "symbol_id": s, "company_id": s, "tier": t})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("point", ["D0", "D1", "D2"])
@pytest.mark.parametrize("d", [date(2025, 10, 6), date(2025, 11, 3), date(2025, 11, 26), date(2025, 11, 28)])
def test_entry_strictly_after_decision(point: pf.Point, d: date) -> None:
    assert pf.entry_utc(pf.entry_of(point), d) > pf.decision_utc(point, d)


def test_d2_enters_at_the_next_open_and_d0_at_the_open() -> None:
    d = date(2025, 10, 6)
    assert pf.entry_utc(pf.entry_of("D2"), d) == calendar.open_utc(calendar.next_session(d))
    assert pf.entry_utc(pf.entry_of("D0"), d) == calendar.open_utc(d)
    assert pf.entry_utc(pf.entry_of("D1"), d) == calendar.d1_utc(d) + pf.FILL_LAG
    assert pf.decision_utc("D2", d) == calendar.close_utc(d)


def test_code_entries_equal_the_frozen_text() -> None:
    run.check_entries()


@pytest.mark.parametrize(
    ("point", "exit_rule"), [("D0", "close_t"), ("D1", "close_t+5"), ("D2", "close_t+20")]
)
def test_universe_builds_for_every_point(point: pf.Point, exit_rule: str) -> None:
    u = pf.build_universe(events(SESSIONS[5:8]), market(), point, exit_rule, SESSIONS)
    assert len(u.events) == 3 * len(SYMBOLS)
    assert bool((u.events["entry_utc"] > u.events["decision_utc"]).all())


def test_a_close_entry_at_the_decision_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(pf.ENTRIES, "close_t", pf.Entry("close", 0))  # type: ignore[index]
    monkeypatch.setitem(pf.ENTRY_OF_POINT, "D2", "close_t")  # type: ignore[index]
    with pytest.raises(pf.TimingError):
        pf.build_universe(events(SESSIONS[5:6]), market(), "D2", "close_t+1", SESSIONS)


def test_a_previous_close_entry_for_d0_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(pf.ENTRIES, "close_t-1", pf.Entry("close", -1))  # type: ignore[index]
    monkeypatch.setitem(pf.ENTRY_OF_POINT, "D0", "close_t-1")  # type: ignore[index]
    with pytest.raises(pf.TimingError):
        pf.build_universe(events(SESSIONS[5:6]), market(), "D0", "close_t", SESSIONS)


def test_late_or_missing_inputs_are_refused() -> None:
    u = pf.build_universe(events(SESSIONS[5:6]), market(), "D0", "close_t", SESSIONS)
    ev = u.events.copy()
    ev["news_utc"] = ev["decision_utc"]
    pf.check_timing(ev, ["news_utc"])  # at the decision: allowed
    ev.loc[0, "news_utc"] = ev.loc[0, "decision_utc"] + pd.Timedelta(seconds=1)
    with pytest.raises(pf.TimingError):
        pf.check_timing(ev, ["news_utc"])
    ev["news_utc"] = pd.NaT
    with pytest.raises(pf.TimingError):
        pf.check_timing(ev, ["news_utc"])


def test_holding_legs_follow_the_entry() -> None:
    mkt = market()
    t = SESSIONS[5]
    ev = events([t]).iloc[[0]]
    sym = int(ev["symbol_id"].iloc[0])
    row = mkt.set_index(["session", "symbol_id"])
    beta = float(row.loc[(calendar.next_session(t), sym), "beta_m"])
    u = pf.build_universe(ev, mkt, "D2", "close_t+5", SESSIONS)
    assert u.holding == 5
    x = u.x.toarray()[0]
    days = [pf.session_after(t, k) for k in range(1, 6)]
    expect = [row.loc[(days[0], sym), "r_id"] - beta * row.loc[(days[0], sym), "r_spy_id"]]
    expect += [row.loc[(d, sym), "r_cc"] - beta * row.loc[(d, sym), "r_spy_cc"] for d in days[1:]]
    assert u.sessions == days
    np.testing.assert_allclose(x, expect, rtol=0, atol=1e-15)
    u1 = pf.build_universe(ev, mkt, "D1", "close_t", SESSIONS)
    b1 = float(row.loc[(t, sym), "beta_m"])
    np.testing.assert_allclose(
        u1.x.toarray()[0], [row.loc[(t, sym), "r_10c"] - b1 * row.loc[(t, sym), "r_spy_10c"]], atol=1e-15
    )


@pytest.mark.parametrize("split", ["val_b", "test"])
def test_stored_positions_respect_the_decision_time(split: str) -> None:
    rel = run.OUT_POSITIONS.format(split=split)
    if not (resolve_layout(None).work / rel).exists():
        pytest.skip(f"{rel} not built")
    p = io.read_parquet(rel)
    assert len(p) > 0
    assert bool((p["entry_utc"] > p["decision_utc"]).all())
    for col in run.AVAILABLE:
        need = p["rule"].map(lambda k, c=col: c in run.available_for(_rule(k)))
        assert not bool(p.loc[need, col].isna().any()), col
        assert bool((p.loc[need, col] <= p.loc[need, "decision_utc"]).all()), col


def _rule(key: str) -> pf.Rule:
    fam, model, point, signal, exit_rule, gate = key.split("|")
    return pf.Rule(fam, point, signal, exit_rule, None if model == "-" else model, gate == "gated")  # type: ignore[arg-type]
