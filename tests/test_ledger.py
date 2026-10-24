"""Append-only ledgers, budget caps and concurrency (PRD NA-00 AC6)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from newsaction import ledger
from newsaction.config import BudgetConfig, load_project
from newsaction.ledger import (
    GENESIS,
    BudgetExceeded,
    FmpCapExceeded,
    FmpLedger,
    JsonlLedger,
    LedgerCorrupt,
    LedgerError,
    SpendLedger,
    TrialLedger,
    params_hash,
)

BUDGET = BudgetConfig(total_usd=1.0, reserve_usd=0.0, chunk_caps={"NA-05": 0.2, "NA-06": 0.6, "NA-07": 0.2})


@pytest.fixture
def spend_path(tmp_path: Path) -> Path:
    return tmp_path / "spend.jsonl"


# --- JSONL chain -----------------------------------------------------------------------------------


def test_append_and_read(tmp_path: Path) -> None:
    led = JsonlLedger(tmp_path / "x.jsonl")
    led.append({"a": 1})
    led.append({"a": 2, "s": "é"})
    recs = led.records()
    assert [r["a"] for r in recs] == [1, 2]
    assert recs[0]["prev"] == GENESIS
    assert all(r["ts"] for r in recs)
    assert led.verify() == 2


def test_reserved_keys_and_nan_rejected(tmp_path: Path) -> None:
    led = JsonlLedger(tmp_path / "x.jsonl")
    with pytest.raises(ValueError, match="set by the ledger"):
        led.append({"prev": "x"})
    with pytest.raises(ValueError):
        led.append({"v": float("nan")})
    assert led.verify() == 0


def _three(tmp_path: Path) -> Path:
    p = tmp_path / "x.jsonl"
    led = JsonlLedger(p)
    for i in range(3):
        led.append({"i": i})
    return p


def test_editing_an_earlier_line_is_detected(tmp_path: Path) -> None:
    p = _three(tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"i":0', '"i":9')
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LedgerCorrupt, match="chain"):
        JsonlLedger(p).verify()


def test_deleting_or_reordering_lines_is_detected(tmp_path: Path) -> None:
    p = _three(tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    with pytest.raises(LedgerCorrupt):
        JsonlLedger(p).verify()
    p.write_text("\n".join([lines[1], lines[0], lines[2]]) + "\n", encoding="utf-8")
    with pytest.raises(LedgerCorrupt):
        JsonlLedger(p).verify()


def test_partial_last_line_and_shrinking_detected(tmp_path: Path) -> None:
    p = _three(tmp_path)
    led = JsonlLedger(p)
    led.read_new()
    with p.open("ab") as fh:
        fh.write(b'{"i":')
    with pytest.raises(LedgerCorrupt, match="partial"):
        JsonlLedger(p).verify()
    p.write_text(p.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(LedgerCorrupt, match="shrank"):
        led.read_new()


_WORKER = """
import sys
from pathlib import Path
from newsaction.ledger import JsonlLedger
led = JsonlLedger(Path(sys.argv[1]))
for i in range(int(sys.argv[3])):
    led.append({"worker": int(sys.argv[2]), "i": i, "pad": "x" * 200})
"""


def test_concurrent_appends_from_four_processes(tmp_path: Path) -> None:
    p = tmp_path / "concurrent.jsonl"
    n = 150
    procs = [subprocess.Popen([sys.executable, "-c", _WORKER, str(p), str(w), str(n)]) for w in range(4)]
    assert [pr.wait(timeout=120) for pr in procs] == [0, 0, 0, 0]
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 * n
    assert all(isinstance(json.loads(line), dict) for line in lines)
    recs = JsonlLedger(p).records()  # chain intact across processes
    for w in range(4):
        assert [r["i"] for r in recs if r["worker"] == w] == list(range(n))


# --- spend -----------------------------------------------------------------------------------------


def test_reserve_refuses_when_chunk_cap_would_be_exceeded(spend_path: Path) -> None:
    led = SpendLedger("NA-05", path=spend_path, budget=BUDGET)
    with pytest.raises(BudgetExceeded, match="NA-05 cap"):
        led.reserve(0.25)  # 0.25 <= total 1.0 but > chunk cap 0.20
    r = led.reserve(0.20)  # equal to the cap is allowed
    led.record(0.15, {"call": 1}, reservation=r)
    with pytest.raises(BudgetExceeded, match="NA-05 cap"):
        led.reserve(0.06)
    led.reserve(0.05)


def test_reserve_refuses_when_total_cap_would_be_exceeded(spend_path: Path) -> None:
    na06 = SpendLedger("NA-06", path=spend_path, budget=BUDGET)
    r = na06.reserve(0.6)
    with pytest.raises(BudgetExceeded):
        na06.record(0.85, {"call": "overrun"}, reservation=r)  # written, then flagged
    assert na06.totals().total_usd == pytest.approx(0.85)
    na07 = SpendLedger("NA-07", path=spend_path, budget=BUDGET)
    with pytest.raises(BudgetExceeded, match="total cap"):
        na07.reserve(0.2)  # the NA-07 cap allows 0.2, but 0.85 + 0.2 > 1.0 total
    na07.reserve(0.1)


def test_unlisted_chunk_has_zero_cap(spend_path: Path) -> None:
    led = SpendLedger("NA-01", path=spend_path, budget=BUDGET)
    with pytest.raises(BudgetExceeded):
        led.reserve(0.0001)
    led.reserve(0.0)


def test_open_reservations_hold_budget_across_instances(spend_path: Path) -> None:
    a = SpendLedger("NA-05", path=spend_path, budget=BUDGET)
    b = SpendLedger("NA-05", path=spend_path, budget=BUDGET)
    r = a.reserve(0.15)
    with pytest.raises(BudgetExceeded):
        b.reserve(0.06)
    a.release(r)
    b.reserve(0.06)
    assert b.totals().held_chunk_usd == pytest.approx(0.06)


def test_batch_reservation_spent_incrementally(spend_path: Path) -> None:
    led = SpendLedger("NA-06", path=spend_path, budget=BUDGET)
    r = led.reserve(0.5)
    for _ in range(4):
        led.record(0.1, {"call": "x"}, reservation=r, final=False)
    t = led.totals()
    assert t.chunk_usd == pytest.approx(0.4)
    assert t.held_chunk_usd == pytest.approx(0.1)
    led.release(r)
    assert led.totals().held_chunk_usd == 0.0


def test_record_without_reservation_is_written_then_raises(spend_path: Path) -> None:
    led = SpendLedger("NA-05", path=spend_path, budget=BUDGET)
    with pytest.raises(LedgerError, match="without a reservation"):
        led.record(0.01, {"call": "unguarded"})
    (rec,) = JsonlLedger(spend_path).records()
    assert rec["unreserved"] is True and rec["usd"] == 0.01
    led.record(0.0, {"call": "free local model"})  # zero-cost records need no reservation


def test_negative_or_nan_amounts_rejected(spend_path: Path) -> None:
    led = SpendLedger("NA-05", path=spend_path, budget=BUDGET)
    for bad in (-0.01, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            led.reserve(bad)


def test_reconcile_and_totals(spend_path: Path) -> None:
    led = SpendLedger("NA-06", path=spend_path, budget=BUDGET)
    for cost in (0.011, 0.022, 0.033):
        led.record(cost, {"call": cost}, reservation=led.reserve(0.05))
    assert led.reconcile([0.011, 0.022, 0.033]) == pytest.approx(0.0, abs=1e-12)
    assert led.reconcile([0.011]) == pytest.approx(0.055)
    t = led.totals()
    assert t.by_chunk == {"NA-06": pytest.approx(0.066)}
    assert t.held_total_usd == 0.0
    assert t.chunk_cap_usd == 0.6 and t.total_cap_usd == 1.0


def test_reservation_of_other_chunk_rejected(spend_path: Path) -> None:
    r = SpendLedger("NA-05", path=spend_path, budget=BUDGET).reserve(0.01)
    with pytest.raises(LedgerError):
        SpendLedger("NA-06", path=spend_path, budget=BUDGET).record(0.01, reservation=r)


def test_real_config_caps_are_used_by_default(spend_path: Path) -> None:
    led = SpendLedger("NA-11", path=spend_path)
    assert led.budget == load_project().budget
    assert led.totals().chunk_cap_usd == 18.0
    with pytest.raises(BudgetExceeded):
        led.reserve(18.01)


# --- FMP, trials, CLI ------------------------------------------------------------------------------


def test_fmp_ledger_refuses_request_over_cap(tmp_path: Path) -> None:
    p = tmp_path / "fmp.jsonl"
    led = FmpLedger(p, cap=3)
    assert [led.reserve({"symbol": s}) for s in "ABC"] == [1, 2, 3]
    with pytest.raises(FmpCapExceeded):
        led.reserve({"symbol": "D"})
    assert FmpLedger(p, cap=3).count() == 3
    assert len(p.read_text(encoding="utf-8").splitlines()) == 3
    assert FmpLedger(p).cap == 3000


def test_trial_ledger(tmp_path: Path) -> None:
    led = TrialLedger(tmp_path / "trials.jsonl")
    good = {
        "chunk": "NA-06",
        "kind": "model",
        "name": "jev",
        "params_hash": params_hash({"temp": 0}),
        "split": "val_a",
        "metric": "ic",
        "value": 0.03,
    }
    led.log(good)
    led.log({**good, "kind": "encoding", "value": None})
    assert led.count() == 2 and led.count(kind="model") == 1 and led.count(chunk="NA-07") == 0
    for bad in ({"split": "holdout"}, {"chunk": "06"}, {"params_hash": "abc"}, {"value": float("nan")},
                {"extra": 1}):  # fmt: skip
        with pytest.raises(ValueError):
            led.log({**good, **bad})
    assert params_hash({"a": 1, "b": 2}) == params_hash({"b": 2, "a": 1})


def test_cli_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for name in ledger.LEDGER_FILES:
        (tmp_path / name).touch()
    JsonlLedger(tmp_path / ledger.TRIALS).append({"x": 1})
    assert ledger.main(["check", "--dir", str(tmp_path)]) == 0
    assert "trials.jsonl=1" in capsys.readouterr().out
    with (tmp_path / ledger.TRIALS).open("a", encoding="utf-8") as fh:
        fh.write('{"x": 2, "prev": "bogus"}\n')
    assert ledger.main(["check", "--dir", str(tmp_path)]) == 1
    (tmp_path / ledger.SPEND).unlink()
    assert ledger.main(["check", "--dir", str(tmp_path)]) == 1
