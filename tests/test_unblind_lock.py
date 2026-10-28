"""NA-12 S1 / AC1: the unblinding runs once, through the lock, after a matching freeze hash (PRD NA-12).

On throwaway frozen layouts with synthetic sealed files (the panel builders are replaced by synthetic frames,
as in ``test_panel_sealing``):
- without ``NA_UNBLIND=1`` or with a changed frozen file, ``run`` refuses before any sealed read (the ledger
  holds no "targets" entry);
- with them, one run reads through the frozen routes in a fixed order, writes ``targets_test`` (test sessions
  only) and its record; a second run, or any run after a "targets" entry, refuses without reading;
- ``check`` reads nothing sealed; ``assemble`` refuses inconsistent outcome columns.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar, io, lock
from newsaction.analysis import slot_path, unblind
from newsaction.bars import derive
from newsaction.config import load_splits
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.panel import build, targets
from newsaction.paths import ROOT, Layout

TEST = load_splits().splits["test"]
DAYS = calendar.sessions(TEST.start, TEST.end)[:30]
BEFORE = calendar.prev_session(TEST.start)
SYMBOLS = (1, 2, 3)


@pytest.fixture(autouse=True)
def _no_unblind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(lock.UNBLIND_ENV, raising=False)


def _entries(lay: Layout, purpose: str | None = None) -> list[dict[str, object]]:
    rows = AccessLedger(lay.ledgers / TEST_ACCESS).entries()
    return [e for e in rows if purpose is None or e["purpose"] == purpose]


def _daily() -> pd.DataFrame:
    rng = np.random.default_rng(13)
    rows = [(d, s) for d in [BEFORE, *DAYS] for s in SYMBOLS]
    n = len(rows)
    df = pd.DataFrame(rows, columns=["session", "symbol_id"])
    df["company_id"] = df["symbol_id"] + 100
    df["member"], df["is_rep"], df["sector"], df["half_day"] = True, True, "Energy", False
    df["split"] = ["test" if d >= TEST.start else "val_b" for d in df["session"]]
    for c in ("ar_cc", "ar_on", "ar_id", "r_cc", "r_spy_cc", "r_on", "r_spy_on", "z_vol"):
        df[c] = rng.normal(0.0, 0.01, n)
    for c in ("sigma_cc", "sigma_on", "sigma_id"):
        df[c] = rng.uniform(0.01, 0.02, n)
    df["z_id"] = (df["ar_id"] / df["sigma_id"]).clip(-10, 10)
    df["raw_open"], df["raw_close"], df["beta_m"], df["beta_s"] = 100.0, 101.0, 1.0, 0.5
    return df


def _intraday() -> pd.DataFrame:
    d = _daily()[["session", "symbol_id", "sigma_on", "sigma_cc"]].copy()
    rng = np.random.default_rng(17)
    for c in ("ar_10c", "ar_c10", "r_c10", "r_spy_c10", "z_vol10"):
        d[c] = rng.normal(0.0, 0.01, len(d))
    d["sigma_rest"], d["sigma_30"] = 0.012, 0.006
    return d


def _fake_path(daily: pd.DataFrame, bars: pd.DataFrame, ref: pd.DataFrame, spy_id: int) -> pd.DataFrame:
    i = _intraday()
    i = i.loc[[s in set(daily["session"]) for s in i["session"]]]
    out = i[["session", "symbol_id"]].copy()
    for k, col in enumerate(slot_path.POINT_COLUMNS):
        out[col] = i["ar_c10"] / i["sigma_cc"] * (1 + k)  # point 0 is the 10:00 rung
    return out.reset_index(drop=True)


def _frozen(lay: Layout, monkeypatch: pytest.MonkeyPatch) -> Layout:
    frozen = lay.configs / "frozen.yaml"
    frozen.write_text(frozen.read_text().replace("frozen_requested: false", "frozen_requested: true"))
    lock.freeze("NA-12 test of the unblinding", layout=lay)
    sealed = pd.DataFrame({"symbol_id": [1], "trade_date": [TEST.start], "close": [1.0]})
    for name in targets.blinded_price_files():
        lock.write_sealed(sealed, name, producer="test", description="synthetic", layout=lay)
    bars = pd.DataFrame({c: [0] for c in derive.BAR_READ})
    lock.write_sealed(bars, targets.blinded_bars_file(), producer="test", description="synthetic", layout=lay)
    monkeypatch.setattr(build, "test_returns_panel", lambda prices, total, layout=None: _daily())
    monkeypatch.setattr(derive, "test_intraday_panel", lambda bars, prices, total, layout=None: _intraday())
    monkeypatch.setattr(unblind, "bar_inputs", lambda bars, prices, layout=None: (bars, prices, 0))
    monkeypatch.setattr(slot_path, "path", _fake_path)
    return lay


def test_run_refuses_without_the_env_and_reads_nothing(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay = _frozen(tmp_layout, monkeypatch)
    with pytest.raises(lock.LockError, match=lock.UNBLIND_ENV):
        unblind.run(lay)
    assert _entries(lay, "targets") == [] and _entries(lay, "reactions") == []
    assert not (lay.work / unblind.OUT).exists()


def test_run_refuses_on_a_changed_frozen_file(tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch) -> None:
    lay = _frozen(tmp_layout, monkeypatch)
    cfg = lay.configs / "analysis.yaml"
    cfg.write_text(cfg.read_text() + "\n# one more line\n")
    monkeypatch.setenv(lock.UNBLIND_ENV, "1")
    with pytest.raises(lock.LockError, match="freeze hash mismatch"):
        unblind.run(lay)
    assert _entries(lay, "targets") == []
    assert unblind.check(lay)["ready"] is False


def test_run_refuses_after_any_targets_entry(tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch) -> None:
    lay = _frozen(tmp_layout, monkeypatch)
    AccessLedger(lay.ledgers / TEST_ACCESS).log(
        caller="test", name="x", purpose="targets", allowed=False, reason="earlier refusal", git_sha="0"
    )
    monkeypatch.setenv(lock.UNBLIND_ENV, "1")
    with pytest.raises(unblind.UnblindError, match="already holds 1 'targets'"):
        unblind.run(lay)
    assert len(_entries(lay, "targets")) == 1


def test_check_reads_nothing_sealed(tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch) -> None:
    lay = _frozen(tmp_layout, monkeypatch)
    before = _entries(lay)
    out = unblind.check(lay)
    assert out["ready"] is True and lock.UNBLIND_ENV in out["require_unblind"]
    assert _entries(lay) == before


def test_one_run_reads_in_order_writes_test_rows_and_refuses_a_second(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay = _frozen(tmp_layout, monkeypatch)
    monkeypatch.setenv(lock.UNBLIND_ENV, "1")
    rec = unblind.run(lay)
    p, t = targets.blinded_price_files()
    b = targets.blinded_bars_file()
    reads = [e for e in _entries(lay) if e["purpose"] != "write"]
    assert [(e["purpose"], e["name"]) for e in reads] == [
        *[("targets", n) for n in (p, t, b, p, t, p, t, b)],  # build_targets, build_d1_targets, the panel
        *[("reactions", n) for n in (p, t, b, p, t)],  # G at D2, then G at D1
    ]
    assert all(e["allowed"] for e in reads)
    out = io.read_parquet(unblind.OUT, layout=lay)
    assert set(out["split"]) == {"test"} and min(out["session"]) == TEST.start
    assert len(out) == len(DAYS) * len(SYMBOLS)
    for col in ("z_cc", "z_on", "z_id", "y2", "e5", "car_lvl_c20", "g_d2", "y1", "g_d1", "car_lvl_b11"):
        assert col in out.columns
    d = _daily().set_index(["session", "symbol_id"])
    o = out.set_index(["session", "symbol_id"])
    expect = (d["ar_on"] / d["sigma_on"]).clip(-10, 10).reindex(o.index)
    assert np.allclose(o["z_on"], expect)  # NA-01's same-day z (risk.zscore)
    saved = json.loads((lay.root / unblind.ARTIFACTS / unblind.RECORD).read_text())
    assert len(saved["targets_entries"]) == 8 and saved["rows"] == len(out) == rec["rows"]
    assert saved["consistency_gaps"] == {k: 0.0 for k in saved["consistency_gaps"]}
    n = len(_entries(lay))
    with pytest.raises(unblind.UnblindError):
        unblind.run(lay)
    assert len(_entries(lay)) == n


def test_assemble_refuses_inconsistent_outcomes() -> None:
    panel = _daily()
    keys = panel[["session", "symbol_id"]]
    tg = keys.assign(split="test", y0=panel["z_id"])
    d1 = keys.assign(split="test", y1=0.0)
    rx2 = keys.assign(g_d2=(panel["ar_cc"] / panel["sigma_cc"]).clip(-10, 10) + 1.0, g_d2_lvl=0.0)
    rx1 = keys.assign(g_d1=0.0, g_d1_lvl=0.0, car_lvl_10=0.0)
    path = keys.assign(car_lvl_b0=0.0)
    with pytest.raises(unblind.UnblindError, match="g_d2_vs_z_cc"):
        unblind.assemble(panel, tg, d1, rx2, rx1, path)


def test_real_repository_refuses_without_the_env(tmp_path: Path) -> None:
    lay = Layout(ROOT, ledgers_dir=tmp_path)
    with pytest.raises(lock.LockError):
        unblind.run(lay)
    assert AccessLedger(tmp_path / TEST_ACCESS).entries() == []
