"""Sealing of the test period in the panel code (PRD NA-01 S6-S7, AC8; CLAUDE.md B8).

- panel_public holds no test-period session; panel_test_inputs holds only columns registered as
  ``static`` or ``t_minus_1`` in configs/availability.yaml;
- build_targets(..., "test") and build_reactions(..., "test", "D2") raise LockError before the
  freeze and log the refused attempt (a temporary ledger is used, so the real one stays clean);
- after a (temporary) freeze and unblinding, the test route reads the blinded prices only through
  ``lock.read_sealed`` with the right purpose.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from newsaction import io, lock
from newsaction.config import load_splits
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.panel import build, reactions, targets
from newsaction.paths import ROOT, Layout
from newsaction.pit import AvailabilityRegistry

TEST_START = load_splits().splits["test"].start
PANEL = ROOT / "work" / "panel"


@pytest.fixture(autouse=True)
def _no_unblind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(lock.UNBLIND_ENV, raising=False)


def _need(path: Path) -> None:
    if not path.is_file():
        pytest.skip(f"{path} is absent (run the NA-01 build)")


def test_ac8_panel_public_has_no_test_period_session() -> None:
    path = PANEL / "panel_public.parquet"
    _need(path)
    sessions = pq.read_table(path, columns=["session"]).column("session").to_pylist()
    assert max(sessions) < TEST_START


def test_ac8_test_inputs_columns_are_static_or_t_minus_1() -> None:
    path = PANEL / "panel_test_inputs.parquet"
    _need(path)
    reg = AvailabilityRegistry.from_yaml()
    kinds = {c: reg.kind(c) for c in pq.read_schema(path).names}
    assert set(kinds.values()) <= {"static", "t_minus_1"}, {
        c: k for c, k in kinds.items() if k not in ("static", "t_minus_1")
    }
    reg.check_inputs(list(kinds), "D0")  # every column is a legal D0 input


def test_ac8_test_inputs_sessions_are_test_sessions_only() -> None:
    path = PANEL / "panel_test_inputs.parquet"
    _need(path)
    sessions = set(pq.read_table(path, columns=["session"]).column("session").to_pylist())
    assert min(sessions) == TEST_START and max(sessions) <= load_splits().splits["test"].end


def test_ac8_registry_marks_every_panel_public_column() -> None:
    path = PANEL / "panel_public.parquet"
    _need(path)
    reg = AvailabilityRegistry.from_yaml()
    for c in pq.read_schema(path).names:
        reg.kind(c)  # raises for an unregistered column


def _layout(tmp_path: Path) -> Layout:
    return Layout(ROOT, ledgers_dir=tmp_path)


def test_ac8_build_targets_test_raises_and_logs(tmp_path: Path) -> None:
    with pytest.raises(lock.LockError):
        targets.build_targets(pd.DataFrame(), "test", layout=_layout(tmp_path))
    logged = AccessLedger(tmp_path / TEST_ACCESS).entries()
    assert [(e["purpose"], e["allowed"]) for e in logged] == [("targets", False)]
    assert logged[0]["name"] == targets.blinded_price_files()[0]


def test_ac8_build_reactions_test_raises_and_logs(tmp_path: Path) -> None:
    if lock.is_frozen():
        pytest.skip("repository is frozen (NA-11 done)")
    for point in ("D2", "D1"):
        with pytest.raises(lock.LockError):
            reactions.build_reactions(pd.DataFrame(), "test", point, layout=_layout(tmp_path))
    logged = AccessLedger(tmp_path / TEST_ACCESS).entries()
    assert [(e["purpose"], e["allowed"]) for e in logged] == [("reactions", False), ("reactions", False)]


def test_public_routes_refuse_test_period_rows() -> None:
    df = pd.DataFrame({"session": [TEST_START], "symbol_id": [1]})
    with pytest.raises(lock.LockError):
        targets.build_targets(df, "public")
    with pytest.raises(lock.LockError):
        reactions.build_reactions(df, "public", "D2")
    with pytest.raises(lock.LockError):
        targets.placebo_means(df.assign(tier="mid", y=0.0), ["y"], pd.Series([True]))


def test_d1_public_route_needs_the_intraday_columns() -> None:
    """NA-10 replaced the NA-01 stub: the public D1 route reads the intraday panel's columns."""
    with pytest.raises(ValueError, match="intraday panel lacks columns"):
        reactions.build_reactions(pd.DataFrame({"session": [date(2025, 1, 2)]}), "public", "D1")


def _frozen_layout(lay: Layout, monkeypatch: pytest.MonkeyPatch, *, unblind: bool) -> Layout:
    frozen = lay.configs / "frozen.yaml"
    frozen.write_text(frozen.read_text().replace("frozen_requested: false", "frozen_requested: true"))
    lock.freeze("NA-01 test of the post-freeze route", layout=lay)
    for name in targets.blinded_price_files():
        frame = pd.DataFrame({"symbol_id": [1], "trade_date": [TEST_START], "close": [1.0]})
        lock.write_sealed(frame, name, producer="test", description="synthetic", layout=lay)
    if unblind:
        monkeypatch.setenv(lock.UNBLIND_ENV, "1")
    return lay


@pytest.mark.parametrize("route", ["targets", "reactions"])
def test_post_freeze_route_reads_through_the_lock(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    lay = _frozen_layout(tmp_layout, monkeypatch, unblind=route == "targets")
    seen: list[tuple[int, int]] = []

    def fake_panel(
        prices: pd.DataFrame, total: pd.DataFrame, *, layout: Layout | None = None
    ) -> pd.DataFrame:
        seen.append((len(prices), len(total)))
        cols = (*targets.INPUT_COLUMNS, *reactions.INPUT_COLUMNS)
        return pd.DataFrame({c: [TEST_START] if c == "session" else [1.0] for c in dict.fromkeys(cols)})

    monkeypatch.setattr(build, "test_returns_panel", fake_panel)
    if route == "targets":
        out = targets.build_targets(pd.DataFrame(), "test", layout=lay)
    else:
        out = reactions.build_reactions(pd.DataFrame(), "test", "D2", layout=lay)
    assert seen == [(1, 1)] and len(out) == 1
    logged = AccessLedger(lay.ledgers / TEST_ACCESS).entries()
    reads = [e for e in logged if e["purpose"] == route]
    assert [e["name"] for e in reads] == list(targets.blinded_price_files())
    assert all(e["allowed"] for e in reads)


def test_targets_still_refused_after_freeze_without_unblind(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay = _frozen_layout(tmp_layout, monkeypatch, unblind=False)
    with pytest.raises(lock.LockError, match=lock.UNBLIND_ENV):
        targets.build_targets(pd.DataFrame(), "test", layout=lay)


def test_panel_modules_never_read_the_blinded_files_directly() -> None:
    """Only lock.read_sealed may open them (the AST blinding scan covers src/; this checks io)."""
    rel = f"snapshot/{'sealed'}/{targets.blinded_price_files()[0]}.parquet"
    if not (ROOT / "work" / rel).is_file():
        pytest.skip("snapshot absent")
    with pytest.raises(io.ManifestError):
        io.read_parquet(rel)
