"""NA-10 AC3: the D1 route is sealed for the test period (CLAUDE.md B8; PREREG §4.3).

- ``build_reactions(..., "test", "D1")`` and ``build_d1_targets(..., "test")`` raise ``LockError`` before the
  freeze and log the refused attempt, the blinded bars first (a temporary ledger keeps the real one clean);
- the public routes refuse test-period rows;
- after a (temporary) freeze, the D1 route reads the blinded bars and prices only through
  ``lock.read_sealed``;
- no public NA-10 file holds a test-period session, and the blinded bars are unreadable through ``io``.

Mutation: let the D1 test route skip the lock (read the bars from ``bars_public``) and the first and third
tests fail.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from newsaction import io, lock
from newsaction.bars import BARS_PUBLIC, BARS_QC, INTRADAY_PUBLIC, INTRADAY_SPY_PUBLIC, derive
from newsaction.config import load_splits
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.panel import reactions, targets
from newsaction.paths import ROOT, Layout
from newsaction.states.build import CALL_B_D1, REACTION_D1

TEST_START = load_splits().splits["test"].start


@pytest.fixture(autouse=True)
def _no_unblind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(lock.UNBLIND_ENV, raising=False)


def _layout(tmp_path: Path) -> Layout:
    return Layout(ROOT, ledgers_dir=tmp_path)


def test_d1_test_reactions_raise_and_log_the_bars_first(tmp_path: Path) -> None:
    if lock.is_frozen():
        pytest.skip("repository is frozen (NA-11 done)")
    with pytest.raises(lock.LockError):
        reactions.build_reactions(pd.DataFrame(), "test", "D1", layout=_layout(tmp_path))
    logged = AccessLedger(tmp_path / TEST_ACCESS).entries()
    assert [(e["name"], e["purpose"], e["allowed"]) for e in logged] == [
        (targets.blinded_bars_file(), "reactions", False)
    ]


def test_d1_test_targets_raise_and_log(tmp_path: Path) -> None:
    with pytest.raises(lock.LockError):
        targets.build_d1_targets(pd.DataFrame(), pd.DataFrame(), "test", layout=_layout(tmp_path))
    logged = AccessLedger(tmp_path / TEST_ACCESS).entries()
    assert [(e["name"], e["purpose"], e["allowed"]) for e in logged] == [
        (targets.blinded_bars_file(), "targets", False)
    ]


def test_public_d1_routes_refuse_test_period_rows() -> None:
    row = {"session": [TEST_START], "symbol_id": [1]}
    with pytest.raises(lock.LockError):
        reactions.build_reactions(pd.DataFrame(row), "public", "D1")
    panel = pd.DataFrame({**row, "ar_cc": [0.0], "sigma_cc": [0.01]})
    intraday = pd.DataFrame({**row, "ar_10c": [0.0], "sigma_rest": [0.01]})
    with pytest.raises(lock.LockError):
        targets.build_d1_targets(panel, intraday, "public")


def test_post_freeze_d1_route_reads_through_the_lock(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay = tmp_layout
    frozen = lay.configs / "frozen.yaml"
    frozen.write_text(frozen.read_text().replace("frozen_requested: false", "frozen_requested: true"))
    lock.freeze("NA-10 test of the post-freeze D1 route", layout=lay)
    names = [targets.blinded_bars_file(), *targets.blinded_price_files()]
    for name in names:
        frame = pd.DataFrame({"symbol_id": [1], "trade_date": [TEST_START], "close": [1.0]})
        lock.write_sealed(frame, name, producer="test", description="synthetic", layout=lay)
    seen: list[int] = []

    def fake(
        bars: pd.DataFrame, prices: pd.DataFrame, total: pd.DataFrame, *, layout: Layout | None = None
    ) -> pd.DataFrame:
        seen.append(len(bars) + len(prices) + len(total))
        cols = dict.fromkeys(reactions.D1_INPUT_COLUMNS)
        return pd.DataFrame({c: [TEST_START] if c == "session" else [1.0] for c in cols})

    monkeypatch.setattr(derive, "test_intraday_panel", fake)
    out = reactions.build_reactions(pd.DataFrame(), "test", "D1", layout=lay)
    assert seen == [3] and len(out) == 1 and set(reactions.D1_COLUMNS) <= set(out.columns)
    reads = [e for e in AccessLedger(lay.ledgers / TEST_ACCESS).entries() if e["purpose"] == "reactions"]
    assert [e["name"] for e in reads] == names and all(e["allowed"] for e in reads)


@pytest.mark.parametrize(
    "rel", [BARS_PUBLIC, BARS_QC, INTRADAY_PUBLIC, INTRADAY_SPY_PUBLIC, REACTION_D1, CALL_B_D1]
)
def test_no_public_na10_file_holds_a_test_period_session(rel: str) -> None:
    path = ROOT / "work" / rel
    if not path.is_file():
        pytest.skip(f"work/{rel} is absent")
    sessions = pq.read_table(path, columns=["session"]).column("session").to_pylist()
    assert max(s for s in sessions if s is not None) < TEST_START


def test_blinded_bars_are_unreadable_outside_the_lock() -> None:
    rel = f"snapshot/{'sealed'}/{targets.blinded_bars_file()}.parquet"
    if not (ROOT / "work" / rel).is_file():
        pytest.skip("the test-period bars have not been fetched")
    assert rel in {k.removeprefix("work/") for k in io.load_manifest()["artifacts"]}
    with pytest.raises(io.ManifestError):
        io.read_parquet(rel)
