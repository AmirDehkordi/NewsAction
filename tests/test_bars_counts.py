"""NA-10 AC2: bar counts and reconciliation on public member-sessions (PRD NA-10 AC2).

Member-sessions: the representative class of a member company on a public session from the first bar
session (``fetch.stock_start``) to the val-B end, with an EOD row. On at least 99% of them every regular
30-minute bar is there (13 on a full day, 7 on a half day: also checked on half days alone) and the session's
price basis is usable (``basis.session_qc``). The literal AC2 bound (first-bar open within 5 bp of the EOD raw
open on 99%) is a strict xfail: the vendor's first 30-minute bar opens at its first trade, not at the official
opening auction (REPORT §3). Every stored bar sits on the 30-minute grid of a public session.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

from newsaction import calendar, io
from newsaction.bars import BARS_PUBLIC, BARS_QC, load_bars_config
from newsaction.bars.fetch import NOT_ON_GRID
from newsaction.config import load_splits
from newsaction.paths import ROOT


@pytest.fixture(scope="module")
def member_qc() -> pd.DataFrame:
    for rel in (BARS_QC, BARS_PUBLIC):
        if not (ROOT / "work" / rel).is_file():
            pytest.skip(f"work/{rel} is absent (run newsaction.bars.fetch and derive)")
    lo, hi = load_bars_config().fetch.stock_start, load_splits().splits["val_b"].end
    pan = io.read_parquet(
        "panel/panel_public.parquet", columns=["session", "symbol_id", "member", "is_rep", "raw_open"]
    )
    pan = pan.loc[
        pan["member"]
        & pan["is_rep"]
        & pan["raw_open"].notna()
        & np.asarray([lo <= d <= hi for d in pan["session"]], dtype=bool)
    ]
    qc = io.read_parquet(BARS_QC)
    out = pan[["session", "symbol_id"]].merge(qc, on=["session", "symbol_id"], how="left")
    out["half_day"] = [calendar.is_half_day(d) for d in out["session"]]
    return out


def test_bars_complete_on_99pct_of_member_sessions(member_qc: pd.DataFrame) -> None:
    done = member_qc["complete"].fillna(False).astype(bool)
    assert done.mean() >= 0.99, done.mean()
    half = member_qc.loc[member_qc["half_day"]]
    assert len(half) > 0 and (half["n_regular"] == 7).mean() >= 0.99


def test_basis_usable_on_99pct_of_member_sessions(member_qc: pd.DataFrame) -> None:
    assert member_qc["usable"].fillna(False).astype(bool).mean() >= 0.99


@pytest.mark.xfail(
    strict=True, reason="AC2 as written: the vendor's first bar opens at its first trade (REPORT §3)"
)
def test_first_bar_open_within_5bp_on_99pct(member_qc: pd.DataFrame) -> None:
    assert member_qc["open_ok"].fillna(False).astype(bool).mean() >= 0.99


def test_bars_sit_on_the_grid_of_public_sessions() -> None:
    path = ROOT / "work" / BARS_PUBLIC
    if not path.is_file():
        pytest.skip(f"work/{BARS_PUBLIC} is absent")
    t = pq.read_table(path, columns=["session", "slot", "regular", "switches"])
    slots = np.asarray(t.column("slot"))
    assert (slots != NOT_ON_GRID).all() and int(slots.min()) >= -11 and int(slots.max()) <= 20
    assert pc.max(t.column("session")).as_py() <= load_splits().splits["val_b"].end
    assert set(t.column("switches").unique().to_pylist()) == {"extended=true&nonadjusted=true"}
