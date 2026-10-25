"""PRD NA-03 AC7 / PREREG A1.2: clean_h = no other D2 event for the company in sessions (t, t+h]."""

from __future__ import annotations

import ast
from datetime import date

import pandas as pd
import pytest

from newsaction import calendar
from newsaction.events.clean_window import clean_flags
from newsaction.paths import ROOT

H = (1, 2, 5, 10, 20)
SESS = calendar.sessions(date(2025, 7, 1), date(2025, 9, 30))


def test_planted_second_event_three_sessions_later() -> None:
    t, t3 = SESS[10], SESS[13]
    d2 = pd.DataFrame({"company_id": [7, 7, 8], "session": [t, t3, SESS[11]]})
    events = pd.DataFrame({"company_id": [7], "session": [t]})
    f = clean_flags(events, d2, H, SESS[-1]).iloc[0]
    assert (f["clean_1"], f["clean_2"]) == (True, True)
    assert (f["clean_5"], f["clean_10"], f["clean_20"]) == (False, False, False)


@pytest.mark.parametrize("k", [1, 2, 5, 10, 20])
def test_window_boundary_is_inclusive(k: int) -> None:
    """A second D2 event exactly at t+k is inside (t, t+k]: clean_k False, clean_h True for h < k."""
    t = SESS[5]
    d2 = pd.DataFrame({"company_id": [7, 7], "session": [t, SESS[5 + k]]})
    f = clean_flags(pd.DataFrame({"company_id": [7], "session": [t]}), d2, H, SESS[-1]).iloc[0]
    assert [bool(f[f"clean_{h}"]) for h in H] == [h < k for h in H]


def test_same_session_and_other_companies_do_not_count() -> None:
    t = SESS[10]
    d2 = pd.DataFrame({"company_id": [7, 8, 8], "session": [t, SESS[11], SESS[12]]})
    d0 = pd.DataFrame({"company_id": [7], "session": [t]})
    f = clean_flags(d0, d2, H, SESS[-1]).iloc[0]
    assert all(f[f"clean_{h}"] for h in H)


def test_window_past_the_data_end_is_missing() -> None:
    t = SESS[-4]
    d2 = pd.DataFrame({"company_id": [7], "session": [t]})
    f = clean_flags(pd.DataFrame({"company_id": [7], "session": [t]}), d2, H, SESS[-1]).iloc[0]
    assert (f["clean_1"], f["clean_2"]) == (True, True)
    assert all(pd.isna(f[f"clean_{h}"]) for h in (5, 10, 20))
    # an event inside the window decides the flag even when the window runs past the data
    d2 = pd.DataFrame({"company_id": [7, 7], "session": [t, SESS[-1]]})
    f = clean_flags(pd.DataFrame({"company_id": [7], "session": [t]}), d2, H, SESS[-1]).iloc[0]
    assert [bool(f[f"clean_{h}"]) for h in H] == [True, True, False, False, False]


def test_clean_window_reads_events_only() -> None:
    """The flag module imports nothing but the calendar (no returns, panel, targets or lock)."""
    src = (ROOT / "src" / "newsaction" / "events" / "clean_window.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    project = {m for m in imported if m.startswith("newsaction")}
    assert project == {"newsaction.calendar"}
    for word in ("panel", "targets", "lock", "read_parquet", "ar_", "z_"):
        assert word not in src.split('"""', 2)[2], word


@pytest.mark.parametrize("rel", ["events/events_d0.parquet", "events/events_d2.parquet"])
def test_real_flags_recomputed_by_hand(rel: str) -> None:
    if not (ROOT / "work" / rel).is_file():
        pytest.skip(f"{rel} not built")
    from newsaction import io
    from newsaction.events.aggregate import event_span

    ev = io.read_parquet(rel)
    d2 = io.read_parquet("events/events_d2.parquet", columns=["company_id", "session"])
    for h in H:
        assert f"clean_{h}" in ev.columns
    last = event_span()[1]
    by_company = d2.groupby("company_id")["session"].apply(lambda s: sorted(set(s))).to_dict()
    for r in ev.sample(300, random_state=2026).itertuples(index=False):
        later = [s for s in by_company.get(r.company_id, []) if s > r.session]
        for h in H:
            end = r.session
            for _ in range(h):
                end = calendar.next_session(end) if end < last else date.max
            hit = any(s <= end for s in later)
            got = getattr(r, f"clean_{h}")
            if hit:
                assert not pd.isna(got) and bool(got) is False
            elif end <= last:
                assert bool(got) is True
            else:
                assert pd.isna(got)
