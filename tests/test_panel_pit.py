"""Rolling statistics end at t-1 (CLAUDE.md A3; PRD NA-01 S4, AC2).

- Synthetic: a +50 sigma return and a 100x volume are planted on day t0 whose original values are
  the smallest of every window, so each statistic (mean- or median-based) moves once the shock
  enters its window. Everything dated <= t0 must be unchanged and the next day must change.
  Removing any ``.shift(1)`` in risk.py turns this test red.
- Real data (AC2): the same plant on (AAPL, 2025-03-14) in a copy of the public inputs, rebuilt
  with ``build.assemble`` on AAPL's GICS sector; tiers for March 2025 must not move.
- Hand recomputation of beta and sigma for (MSFT, 2025-06-12) from panel columns.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction.panel import build, risk

T1_COLUMNS = (
    "beta_m",
    "beta_s",
    "beta_n",
    "sigma_cc",
    "sigma_on",
    "sigma_id",
    "logv_med60",
    "logv_mad60",
    "adv63",
    "car_m5",
    "car_m20",
    "car_m60",
    "z_m5",
    "z_m20",
    "z_m60",
)
ALWAYS_MOVE = (
    "beta_m",
    "beta_s",
    "sigma_cc",
    "sigma_on",
    "sigma_id",
    "logv_med60",
    "logv_mad60",
    "adv63",
    "car_m5",
)


def _same(a: float, b: float) -> bool:
    return (np.isnan(a) and np.isnan(b)) or a == b


def _synthetic(seed: int = 7) -> tuple[dict[str, object], int]:
    rng = np.random.default_rng(seed)
    n_t, n_s, t0 = 420, 6, 380
    idx = pd.DatetimeIndex(pd.bdate_range("2023-01-02", periods=n_t), name="session")
    cols = list(range(1, n_s + 1))
    r_m = {x: pd.Series(rng.normal(0, 0.01, n_t), index=idx) for x in risk.RETURN_TYPES}
    r_s = {
        x: pd.DataFrame(rng.normal(0, 0.01, (n_t, n_s)), index=idx, columns=cols) for x in risk.RETURN_TYPES
    }
    r = {
        x: 0.9 * pd.DataFrame(np.repeat(r_m[x].to_numpy()[:, None], n_s, 1), idx, cols)
        + 0.5 * r_s[x]
        + pd.DataFrame(rng.normal(0, 0.015, (n_t, n_s)), idx, cols)
        for x in risk.RETURN_TYPES
    }
    vol = pd.DataFrame(np.exp(rng.normal(14, 0.4, (n_t, n_s))), idx, cols)
    # day t0 of symbol 1 sits just below the window medians (no idiosyncratic move, typical volume),
    # so a planted extreme moves every median and every MAD of a window that contains it
    for x in risk.RETURN_TYPES:
        r[x].iloc[t0, 0] = 0.9 * r_m[x].iloc[t0] + 0.5 * r_s[x].iloc[t0, 0]
    others = np.log(vol.iloc[t0 - risk.VOL_WINDOW + 1 : t0, 0].to_numpy())
    vol.iloc[t0, 0] = np.exp(np.median(others) - 0.01)
    members = pd.DataFrame(True, idx, cols)
    minutes = pd.Series(390.0, index=idx)
    return {"r": r, "r_m": r_m, "r_s": r_s, "members": members, "minutes": minutes, "vol": vol}, t0


def _run(d: dict[str, object]) -> dict[str, pd.DataFrame]:
    vol = d["vol"]
    assert isinstance(vol, pd.DataFrame)
    return risk.compute_risk(d["r"], d["r_m"], d["r_s"], d["members"], d["minutes"], vol, vol * 50.0)


def test_planted_shock_moves_nothing_dated_t_synthetic() -> None:
    base_in, t0 = _synthetic()
    planted_in, _ = _synthetic()
    base = _run(base_in)
    shocked_r = planted_in["r"]
    assert isinstance(shocked_r, dict)
    sigma = float(base["sigma_cc"].iloc[t0, 0])
    for x in risk.RETURN_TYPES:
        shocked_r[x].iloc[t0, 0] += 50 * sigma
    vol = planted_in["vol"]
    assert isinstance(vol, pd.DataFrame)
    vol.iloc[t0, 0] *= 1e4
    planted = _run(planted_in)
    for col in T1_COLUMNS:
        for t in range(t0 - 3, t0 + 1):
            assert _same(float(base[col].iloc[t, 0]), float(planted[col].iloc[t, 0])), (col, t)
    for col in ALWAYS_MOVE:
        assert not _same(float(base[col].iloc[t0 + 1, 0]), float(planted[col].iloc[t0 + 1, 0])), col
    # same-day quantities do see the shock
    assert planted["ar_cc"].iloc[t0, 0] > base["ar_cc"].iloc[t0, 0] + 40 * sigma
    assert planted["z_cc"].iloc[t0, 0] == risk.Z_CLIP


def test_rolling_beta_matches_numpy_ols() -> None:
    d, _ = _synthetic()
    r, r_m, r_s = d["r"], d["r_m"], d["r_s"]
    assert isinstance(r, dict) and isinstance(r_m, dict) and isinstance(r_s, dict)
    beta_m, beta_s, _ = risk.rolling_betas(r["cc"], r_m["cc"], r_s["cc"])
    t = 300
    y = r["cc"].iloc[t - risk.BETA_WINDOW : t, 2].to_numpy()
    m = r_m["cc"].iloc[t - risk.BETA_WINDOW : t].to_numpy()
    s = r_s["cc"].iloc[t - risk.BETA_WINDOW : t, 2].to_numpy()
    x = np.column_stack([np.ones_like(m), m, s - m])
    b = np.linalg.lstsq(x, y, rcond=None)[0]
    assert beta_m.iloc[t, 2] == pytest.approx(b[1], abs=1e-9)
    assert beta_s.iloc[t, 2] == pytest.approx(b[2], abs=1e-9)


def test_sigma_floor_and_half_day_scale() -> None:
    idx = pd.DatetimeIndex(pd.bdate_range("2024-01-02", periods=3))
    sigma = pd.DataFrame({1: [0.01, 0.02, 0.03], 2: [0.02, 0.02, 0.02], 3: [0.05, 0.05, 0.05]}, index=idx)
    members = pd.DataFrame(True, idx, sigma.columns)
    floored = risk.floor_sigma(sigma, members, q=0.5)
    assert floored.iloc[0].tolist() == [0.02, 0.02, 0.05]
    scaled = risk.half_day_scale(sigma, pd.Series([390.0, 210.0, 390.0], index=idx))
    assert scaled.iloc[1, 0] == pytest.approx(0.02 * np.sqrt(210 / 390))


# --- real data ---------------------------------------------------------------------------------


AAPL_DAY, NEXT_DAY = pd.Timestamp("2025-03-14"), pd.Timestamp("2025-03-17")


def _sector_subset(inp: build.Inputs, ticker: str) -> build.Inputs:
    sid = int(inp.symbols.loc[inp.symbols["ticker"] == ticker, "symbol_id"].item())
    level1 = inp.gics.loc[inp.gics["symbol_id"] == sid, "level1_name"].item()
    keep = set(inp.gics.loc[inp.gics["level1_name"] == level1, "symbol_id"].astype(int))
    keep |= set(inp.symbols.loc[inp.symbols["ticker"] == build.SPY, "symbol_id"].astype(int))
    in_keep = lambda df: df[df["symbol_id"].isin(keep)]  # noqa: E731
    syms = in_keep(inp.symbols)
    public = pd.Timestamp(inp.public_end)
    tickers = set(syms["ticker"].str.replace(".", "-", regex=False))
    return replace(
        inp,
        members=in_keep(inp.members),
        symbols=syms,
        symbol_tickers=in_keep(inp.symbol_tickers),
        gics=in_keep(inp.gics),
        prices_raw=in_keep(inp.prices_raw),
        total=in_keep(inp.total),
        actions=in_keep(inp.actions),
        shares=in_keep(inp.shares),
        dp=inp.dp[inp.dp["symbol"].isin(tickers) & (inp.dp["date"] <= public)],  # no test-period data
        spy_close=inp.spy_close[inp.spy_close.index <= public],
    )


@pytest.fixture(scope="module")
def it_inputs(panel_public: pd.DataFrame) -> build.Inputs:
    return _sector_subset(build.load_inputs(), "AAPL")


def test_ac2_planted_shock_aapl(it_inputs: build.Inputs) -> None:
    base = build.assemble(it_inputs)
    sid = int(it_inputs.symbols.loc[it_inputs.symbols["ticker"] == "AAPL", "symbol_id"].item())
    sigma = float(base.frames["sigma_cc"].at[AAPL_DAY, sid])
    dp = it_inputs.dp.copy()
    hit = (dp["symbol"] == "AAPL") & (dp["date"] == AAPL_DAY)
    assert hit.sum() == 1
    dp.loc[hit, "close"] *= 1 + 50 * sigma
    px = it_inputs.prices_raw.copy()
    vhit = (px["symbol_id"] == sid) & (pd.to_datetime(px["trade_date"]) == AAPL_DAY)
    px.loc[vhit, "volume"] = px.loc[vhit, "volume"] * 100
    planted = build.assemble(replace(it_inputs, dp=dp, prices_raw=px))

    ar = planted.frames["ar_cc"].at[AAPL_DAY, sid] - base.frames["ar_cc"].at[AAPL_DAY, sid]
    assert ar / sigma == pytest.approx(50, rel=0.05)
    for col in T1_COLUMNS:
        b, p = base.frames[col], planted.frames[col]
        assert _same(float(b.at[AAPL_DAY, sid]), float(p.at[AAPL_DAY, sid])), col
        assert b.loc[:AAPL_DAY].equals(p.loc[:AAPL_DAY]), col  # nothing dated <= t moves, any symbol
    for col in ("beta_m", "beta_s", "adv63", "car_m5", "logv_mad60"):
        assert not _same(
            float(base.frames[col].at[NEXT_DAY, sid]), float(planted.frames[col].at[NEXT_DAY, sid])
        ), col
    # tiers use the previous month end: every March 2025 tier is unchanged; April's inputs move
    tb, tp = base.tiers_monthly, planted.tiers_monthly
    cols = ["company_id", "tier", "rank", "dv_tier", "dv_rank", "cap_usd", "adv63_usd"]
    assert tb.loc[tb["month"] == "2025-03", cols].equals(tp.loc[tp["month"] == "2025-03", cols])
    for name in ("tier", "rank", "is_rep"):
        assert (
            base.frames[name]
            .loc["2025-03-01":"2025-03-31"]
            .equals(planted.frames[name].loc["2025-03-01":"2025-03-31"])
        )
    apr_b = tb[(tb["month"] == "2025-04") & (tb["rep_symbol_id"] == sid)]["adv63_usd"].item()
    apr_p = tp[(tp["month"] == "2025-04") & (tp["rep_symbol_id"] == sid)]["adv63_usd"].item()
    assert apr_p > apr_b


def test_hand_recompute_msft_beta_sigma(panel_public: pd.DataFrame) -> None:
    """Verifier step 4: numpy OLS over the 252 prior sessions; 1.4826 * MAD of the 126 prior AR_cc."""
    from newsaction import calendar

    p = panel_public[panel_public["ticker"] == "MSFT"].set_index("session").sort_index()
    day = date(2025, 6, 12)
    prior = calendar.sessions(date(2024, 1, 2), calendar.prev_session(day))
    w = p.reindex(prior[-risk.BETA_WINDOW :])
    ok = w[["r_cc", "r_spy_cc", "r_sec_cc"]].notna().all(axis=1)
    x = np.column_stack(
        [np.ones(ok.sum()), w.loc[ok, "r_spy_cc"], w.loc[ok, "r_sec_cc"] - w.loc[ok, "r_spy_cc"]]
    )
    b = np.linalg.lstsq(x, w.loc[ok, "r_cc"].to_numpy(), rcond=None)[0]
    assert p.at[day, "beta_m"] == pytest.approx(b[1], abs=1e-6)
    assert p.at[day, "beta_s"] == pytest.approx(b[2], abs=1e-6)
    a = p.reindex(prior[-risk.SIGMA_WINDOW :])["ar_cc"].dropna().to_numpy()
    raw = risk.MAD_SCALE * np.median(np.abs(a - np.median(a)))
    sigma = float(p.at[day, "sigma_cc"])
    # every sigma below the cross-sectional floor is raised to it, so the floor is the day's minimum
    floor = panel_public.loc[(panel_public["session"] == day) & panel_public["member"], "sigma_cc"].min()
    assert sigma == pytest.approx(max(raw, floor), rel=1e-12)
