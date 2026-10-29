"""NA-13 books: the 20% sides within tier / pooled (PREREG §12), equal weights, the rule list, the placebo
draws, and AC6 (one test day's S-CONV D2 ranks rebuilt from the stored inputs)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from newsaction import io
from newsaction.analysis import metrics as mx
from newsaction.config import CONFIGS, load_yaml
from newsaction.paths import resolve_layout
from newsaction.strategy import portfolios as pf
from newsaction.strategy import run


def _sides(tiers: list[str], score: np.ndarray, cohort: np.ndarray | None = None) -> np.ndarray:
    c = np.zeros(len(tiers), dtype=np.int64) if cohort is None else cohort
    g = pf.groups(c, np.asarray(tiers, dtype=object))
    return pf.sides(c, g, score, None, np.zeros(len(tiers)))


def test_within_tier_when_each_side_has_ten() -> None:
    tiers = ["top100"] * 50 + ["rest"] * 60
    score = np.r_[np.arange(50.0), 100 + np.arange(60.0)]
    s = _sides(tiers, score)
    assert (s[:50] == 1).sum() == 10 and (s[:50] == -1).sum() == 10
    assert (s[50:] == 1).sum() == 12 and (s[50:] == -1).sum() == 12
    assert set(np.flatnonzero(s[:50] == 1)) == set(range(40, 50))


def test_small_tiers_pool_and_a_small_pool_takes_the_session() -> None:
    # top100 30 + mid 30 are small (6 a side) and pool to 60 (12 a side); rest 60 stands alone
    tiers = ["top100"] * 30 + ["mid"] * 30 + ["rest"] * 60
    g = pf.groups(np.zeros(120, dtype=np.int64), np.asarray(tiers, dtype=object))
    assert set(g[:60]) == {pf.POOL} and set(g[60:]) == {"rest"}
    # top100 20 alone is small (4 a side), rest 60 stands alone: the pool (20, 4 a side) is still below 10,
    # so the whole session is one group
    tiers2 = ["top100"] * 20 + ["rest"] * 60
    g2 = pf.groups(np.zeros(80, dtype=np.int64), np.asarray(tiers2, dtype=object))
    assert set(g2) == {pf.ALL}
    # every tier small: the pool is the session
    g3 = pf.groups(np.zeros(30, dtype=np.int64), np.asarray(["mid"] * 15 + ["rest"] * 15, dtype=object))
    assert set(g3) == {pf.POOL}


def test_side_size_floors_and_nan_never_trades() -> None:
    assert list(pf.side_size([4, 5, 9, 10, 49, 50])) == [0, 1, 1, 2, 9, 10]
    score = np.r_[np.arange(9.0), np.nan]
    s = _sides(["rest"] * 10, score)
    assert s[-1] == 0 and (s == 1).sum() == 1 and (s == -1).sum() == 1


def test_ties_break_on_the_tiebreak_then_the_draw() -> None:
    score = np.zeros(10)
    tb = np.arange(10.0)
    c = np.zeros(10, dtype=np.int64)
    g = pf.groups(c, np.asarray(["rest"] * 10, dtype=object))
    s = pf.sides(c, g, score, tb, np.zeros(10))
    assert list(np.flatnonzero(s == 1)) == [8, 9] and list(np.flatnonzero(s == -1)) == [0, 1]


def test_equal_weights() -> None:
    side = np.array([1, 1, -1, -1, 0, 1, -1], dtype=np.int8)
    cohort = np.array([0, 0, 0, 0, 0, 1, 1], dtype=np.int64)
    w = pf.weights(side, cohort, 2)
    np.testing.assert_allclose(w, [0.5, 0.5, -0.5, -0.5, 0, 1, -1])


def test_draws_do_not_depend_on_row_order() -> None:
    ids = [f"E{i}" for i in range(50)]
    a = pf.draws(ids, 2027)
    b = pf.draws(ids[::-1], 2027)
    np.testing.assert_array_equal(a, b[::-1])


def test_rules_follow_the_frozen_block_and_put_s_conv_first() -> None:
    rs = run.rules()
    assert rs[0].family == "S-CONV" and rs[0].model == "laya_fin"
    st = run.frozen_strategy()
    conv = [r for r in rs if r.family == "S-CONV"]
    assert len(conv) == len(run.MODELS) * (
        len(st["s_conv"]["points"]["D1"]["exits"]) + len(st["s_conv"]["points"]["D2"]["exits"])
    )
    assert not any(r.gated and r.point == "D1" for r in rs)  # no frozen D1 gate
    assert {r.point for r in rs if r.gated} == set(st["gating"]["points"])
    assert len({r.key for r in rs}) == len(rs)


def test_sharpe_and_drawdown() -> None:
    r = np.array([0.01, -0.005, 0.02, 0.0])
    assert pf.sharpe(r) == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(252))
    assert pf.max_drawdown(np.array([0.1, -0.5, 0.2])) == pytest.approx(0.5)


def test_ac6_rebuild_one_day_of_s_conv_d2_ranks() -> None:
    lay = resolve_layout(None)
    rel = run.OUT_POSITIONS.format(split="test")
    if not (lay.work / rel).exists():
        pytest.skip(f"{rel} not built")
    key = "S-CONV|laya_fin|D2|u|close_t+5|all"
    pos = io.read_parquet(rel)
    pos = pos.loc[pos["rule"] == key]
    day = pos.groupby("session").size().idxmax()
    # stored inputs: Laya-Fin's Call A on W2 (the frame's N̂), the frozen V map, G^lvl from targets_test
    fr = io.read_parquet(
        "analysis/frame_d2_laya_fin.parquet",
        columns=["event_id", "session", "symbol_id", "tier", "split", "embargo", "a2_n_hat"],
    )
    fr["session"] = pd.to_datetime(fr["session"]).dt.date
    fr = fr.loc[(fr["session"] == day) & (fr["split"] == "test") & ~fr["embargo"].astype(bool)]
    tt = io.read_parquet("analysis/targets_test.parquet", columns=["session", "symbol_id", "g_d2_lvl"])
    tt["session"] = pd.to_datetime(tt["session"]).dt.date
    fr = fr.merge(tt, on=["session", "symbol_id"], how="left")
    vmap = load_yaml(CONFIGS / "frozen.yaml")["calibration"]["laya_fin"]["a2"]["v"]
    fr["u"] = mx.apply_map(fr["a2_n_hat"].to_numpy(dtype=float), vmap) - fr["g_d2_lvl"]
    fr = fr.loc[fr["u"].notna()]
    mkt = io.read_parquet("strategy/market_test.parquet", columns=["session", "symbol_id", "raw_open"])
    mkt["session"] = pd.to_datetime(mkt["session"]).dt.date
    nxt = pf.session_after(day, 1)
    opened = set(mkt.loc[(mkt["session"] == nxt) & mkt["raw_open"].notna(), "symbol_id"])
    fr = fr.loc[fr["symbol_id"].isin(opened)].sort_values("u")
    # the pooling rule, written out
    n_t = fr.groupby("tier").size()
    alone = [t for t, n in n_t.items() if math.floor(0.2 * n + 1e-9) >= 10]
    pooled = [t for t in n_t.index if t not in alone]
    groups = [fr.loc[fr["tier"] == t] for t in alone]
    pool = fr.loc[fr["tier"].isin(pooled)]
    if len(pool) and math.floor(0.2 * len(pool) + 1e-9) < 10 and alone:
        groups = [fr]
    elif len(pool):
        groups.append(pool)
    longs, shorts = set(), set()
    for g in groups:
        k = math.floor(0.2 * len(g) + 1e-9)
        if k:
            shorts |= set(g["event_id"].iloc[:k])
            longs |= set(g["event_id"].iloc[-k:])
    got = pos.loc[pos["session"] == day]
    assert set(got.loc[got["side"] > 0, "event_id"]) == longs
    assert set(got.loc[got["side"] < 0, "event_id"]) == shorts
    np.testing.assert_allclose(
        got.set_index("event_id")["score"].sort_index(),
        fr.set_index("event_id").loc[sorted(longs | shorts), "u"],
        rtol=0,
        atol=1e-12,
    )


def test_signal_definitions() -> None:
    """S-CONV's U = V − G^lvl; J and RG signed by the move and the news (PREREG §7, §15 NA-13 row (iv))."""
    d2 = pd.DataFrame(
        {
            "a2_v": [0.4, -0.2, 0.1],
            "g_d2_lvl": [1.0, -0.5, 0.2],
            "g_d2": [2.0, -1.0, 0.4],
            "b2_j": [0.3, 0.3, -0.1],
            "a2_n_hat": [0.6, -0.7, 0.2],
        }
    )
    s = run._signals(d2.copy(), "D2", 0.5)
    np.testing.assert_allclose(s["u"], [-0.6, 0.3, -0.1])
    np.testing.assert_allclose(s["j"], [0.3, -0.3, -0.1])
    np.testing.assert_allclose(s["rg"].to_numpy()[:2], [0.6 - 2.0, -0.7 + 1.0])
    assert np.isnan(s["rg"].iloc[2])
    np.testing.assert_allclose(s["gap"], [-1.0, 0.5, -0.2])
    d1 = pd.DataFrame(
        {
            "a0_v": [0.4, -0.2],
            "g_d1_lvl": [0.1, 0.3],
            "g_d1": [-0.2, 0.6],
            "b1_j": [0.5, 0.5],
            "a0_n_hat": [-0.9, 0.1],
            "a0_n_tilde": [-0.3, 0.05],
        }
    )
    s1 = run._signals(d1.copy(), "D1", 0.5)
    np.testing.assert_allclose(s1["u"], [0.3, -0.5])
    np.testing.assert_allclose(s1["j"], [-0.5, 0.5])
    assert s1["rg"].iloc[0] == pytest.approx(-0.9 + 0.2) and np.isnan(s1["rg"].iloc[1])
    np.testing.assert_allclose(s1["gap"], [-0.1, -0.3])
    s0 = run._signals(d1.copy(), "D0", 0.5)
    np.testing.assert_allclose(s0["n_tilde"], [-0.3, 0.05])
    np.testing.assert_allclose(s0["tiebreak"], [-0.9, 0.1])
