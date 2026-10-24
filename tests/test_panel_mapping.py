"""ATOM -> Data/prices mapping (PRD NA-01 S2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from newsaction.panel import mapping

IDX = pd.bdate_range("2024-01-02", periods=300)


def _walk(seed: int, n: int = len(IDX)) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), index=IDX)


def test_normalize_ticker() -> None:
    assert mapping.normalize_ticker(" brk.b ") == "BRK-B"


def test_alias_counts_only_when_its_window_overlaps_the_price_history() -> None:
    symbols = pd.DataFrame({"symbol_id": [1], "ticker": ["NEW"]})
    utc = "UTC"
    aliases = pd.DataFrame(
        {
            "symbol_id": [1, 1],
            "ticker": ["OLD", "GONE"],
            "valid_from": [pd.Timestamp("2020-01-01", tz=utc), pd.Timestamp("2000-01-01", tz=utc)],
            "valid_to": [None, pd.Timestamp("2001-01-01", tz=utc)],
        }
    )
    ranges = {k: (IDX[0], IDX[-1]) for k in ("OLD", "GONE")}
    out = mapping.candidates(symbols, aliases, ranges)
    assert out["candidate"].tolist() == ["OLD"] and out["source"].tolist() == ["alias"]


def test_one_bad_raw_print_does_not_fail_a_correct_mapping() -> None:
    adj = _walk(1)
    raw = adj * 3.0  # different level, same returns
    raw.iloc[150] *= 1.15  # one bad raw close (cf. GNRC 2023-02-08 in ATOM)
    n, pearson, spearman = mapping.score(raw, adj, pd.DatetimeIndex([]))
    assert pearson < mapping.MIN_CORR <= spearman and n == len(IDX) - 1


def test_map_symbols_validates_rejects_and_resolves_conflicts() -> None:
    a, b = _walk(1), _walk(2)
    symbols = pd.DataFrame({"symbol_id": [1, 2, 3, 4], "ticker": ["AAA", "BBB", "AAA", "ZZZ"]})
    raw = pd.DataFrame({1: a * 2, 2: _walk(3), 3: a * 2 * (1 + 0.02 * np.sin(np.arange(len(IDX)))), 4: b})
    adj = pd.DataFrame({"AAA": a, "BBB": b})
    out = mapping.map_symbols(symbols, symbols.iloc[:0].assign(valid_from=None, valid_to=None), raw, adj, {})
    status = dict(zip(out["symbol_id"], out["status"], strict=True))
    assert status[1] == mapping.MAPPED and out.loc[out["symbol_id"] == 1, "price_symbol"].item() == "AAA"
    assert status[2] == mapping.FAILED_CORR  # BBB's prices belong to another company
    assert status[3] in (mapping.CONFLICT, mapping.FAILED_CORR)  # AAA already taken by the better id
    assert status[4] == mapping.NO_CANDIDATE


def test_real_mapping_report(panel_public: pd.DataFrame) -> None:
    from newsaction import io

    mp = io.read_parquet("panel/mapping.parquet")
    mapped = mp[mp["status"] == mapping.MAPPED]
    assert (mapped["corr_spearman"] >= mapping.MIN_CORR).all()
    assert (mapped["n_obs"] >= mapping.MIN_OVERLAP).all()
    assert set(mp["adj_source"]) <= {"data_prices", "atom_total"}
    assert (mp["status"] == mapping.MAPPED).sum() == (mp["adj_source"] == "data_prices").sum()
    if len(mp) < 500:
        pytest.fail(f"only {len(mp)} ids in the mapping table")
