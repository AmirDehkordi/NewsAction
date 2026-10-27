"""NA-10 S3: the request plan and the one write of the test-period bars (PRD NA-10 S3; CLAUDE.md B8).

- ``write_test_part`` seals the test-period bars once through ``lock.write_sealed`` (a ``write`` entry in the
  access ledger, a manifest entry under the sealed directory), returns counts only and writes nothing public;
- the plan (real panel; skipped without it): every window starts and ends on a session, spans at most the
  probe's window, stays on one side of the public / test boundary, the windows of a symbol do not overlap
  and they cover every member session of its span; the alias windows are there.
"""

from __future__ import annotations

import itertools
from datetime import date

import numpy as np
import pytest

from newsaction import calendar, io
from newsaction.bars import load_bars_config
from newsaction.bars.fetch import Chunk, first_traded, member_spans, plan, write_test_part
from newsaction.config import load_splits
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.panel.targets import blinded_bars_file
from newsaction.paths import ROOT, Layout


def test_write_test_part_seals_once_and_reports_counts(tmp_layout: Layout) -> None:
    d = load_splits().splits["test"].start
    step = 30 * 60 * 1_000_000_000
    start = np.asarray([calendar.open_utc(d).value + k * step for k in range(-1, 13)], dtype=np.int64)
    ohlcv = np.tile([10.0, 10.5, 9.5, 10.2, 1e4], (len(start), 1))
    chunk = Chunk(1, "AAA", "0" * 64, "extended=true&nonadjusted=true", start, ohlcv)
    info = write_test_part([chunk], layout=tmp_layout)
    assert (
        info["rows"] == 14
        and info["rows_off_grid_or_range"] == 0
        and set(info)
        == {
            "rows_received",
            "rows_off_grid_or_range",
            "rows_duplicate",
            "rows",
            "sha256",
        }
    )
    writes = AccessLedger(tmp_layout.ledgers / TEST_ACCESS).entries()
    assert [(e["name"], e["purpose"]) for e in writes] == [(blinded_bars_file(), "write")]
    keys = set(io.load_manifest(tmp_layout)["artifacts"])
    assert keys == {f"work/snapshot/{'sealed'}/{blinded_bars_file()}.parquet"}
    assert not (tmp_layout.work / "bars30").exists()


@pytest.fixture(scope="module")
def windows() -> list:  # type: ignore[type-arg]
    if not (ROOT / "work" / "panel" / "panel_public.parquet").is_file():
        pytest.skip("work/panel is absent (run the NA-01 build)")
    return plan(30)


def test_plan_windows_respect_sessions_and_the_boundary(windows: list) -> None:  # type: ignore[type-arg]
    pub_end, (t0, t1) = (
        load_splits().splits["val_b"].end,
        (load_splits().splits["test"].start, load_splits().splits["test"].end),
    )
    for w in windows:
        assert calendar.is_session(w.start) and calendar.is_session(w.end) and w.start <= w.end
        assert (w.end - w.start).days < 30
        assert (w.part == "public" and w.end <= pub_end) or (
            w.part == "test" and t0 <= w.start and w.end <= t1
        )


def test_plan_covers_member_sessions_without_overlap(windows: list) -> None:  # type: ignore[type-arg]
    cfg = load_bars_config().fetch
    alias_tickers = {a.alias for a in cfg.aliases}
    spans = member_spans().set_index("symbol_id")
    traded = first_traded()
    t0 = load_splits().splits["test"].start
    by: dict[tuple[int, str], list[tuple[date, date]]] = {}
    for w in windows:
        by.setdefault((w.symbol_id, w.ticker), []).append((w.start, w.end))
    for (sid, ticker), ws in by.items():
        ws.sort()
        assert all(a[1] < b[0] for a, b in itertools.pairwise(ws)), ticker
        if sid not in spans.index or ticker in alias_tickers:
            continue
        covered = {d for a, b in ws for d in calendar.sessions(a, b)}
        lo = max(spans.at[sid, "first"], traded.get(sid, t0))
        assert set(calendar.sessions(lo, spans.at[sid, "last"])) <= covered, ticker
    assert alias_tickers <= {w.ticker for w in windows}
