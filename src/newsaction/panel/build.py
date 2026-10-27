"""NA-01 S7: build the daily point-in-time panel.

    uv run python -m newsaction.panel.build

Writes (through ``newsaction.io``; schemas in docs/DATA_CONTRACT.md):
- work/panel/panel_public.parquet: sessions PANEL_START .. end of val-B, every exported symbol on every
  session where it is an index member or has a raw price; ids, tiers, sector, returns, AR, sigma, z,
  betas, z_vol, momentum, QC flags, targets (purged) and the D2 reaction;
- work/panel/panel_test_inputs.parquet: test-period sessions x index members; only columns registered
  as ``static`` or ``t_minus_1`` (nothing dated t or later);
- work/panel/{companies,tiers_monthly,qc_flags,mapping}.parquet.

Inputs: the registered ATOM snapshot (public files only), Data/prices/prices.parquet (adjusted close and
volume) and work/market/market_prices.parquet (SPY close). The blinded raw prices are not read here;
``test_returns_panel`` is the route the post-freeze / post-unblinding code in ``targets`` and
``reactions`` uses, and it receives those frames from ``newsaction.lock``.

Test-period closes in Data/ are used only for t-1 features of test sessions (PREREG §15, NA-00 row 2).
Nothing in this module prints or summarizes a test-period value.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction import calendar, io
from newsaction.config import load_splits
from newsaction.panel import (
    HISTORY_START,
    PANEL_START,
    adjust,
    mapping,
    reactions,
    risk,
    sector,
    targets,
    tiers,
)
from newsaction.panel.grid import session_index, to_long, wide
from newsaction.paths import Layout, resolve_layout

PRODUCER: Final = "newsaction.panel.build (NA-01 S7)"
SNAPSHOT: Final = "snapshot"
SPY: Final = "SPY"
DV_UNIT_WINDOW: Final = 63
VOL_UNIT_WINDOW: Final = 20
POST_EXIT_SESSIONS: Final = 60  # longest target rung (PREREG A1.2, C_{t+60} exploratory)

STATIC_ID_COLUMNS: Final = (
    "ticker",
    "company_id",
    "member",
    "sector",
    "half_day",
    "split",
    "adj_source",
    "price_symbol",
)
TIER_COLUMNS: Final = ("tier", "rank", "dv_tier", "dv_rank", "tier_source", "is_rep")
T1_RISK_COLUMNS: Final = (
    "beta_m",
    "beta_s",
    "beta_n",
    "sigma_cc",
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
T1_PUBLIC_ONLY: Final = ("sigma_on", "sigma_id")  # need raw opens, blinded for test sessions
SAME_DAY_COLUMNS: Final = (
    "raw_open",
    "raw_close",
    "raw_volume",
    "adj_close",
    "adj_open",
    "adj_factor",
    "r_cc",
    "r_on",
    "r_id",
    "r_spy_cc",
    "r_spy_on",
    "r_spy_id",
    "r_sec_cc",
    "r_sec_on",
    "r_sec_id",
    "r_sec_n",
    "ar_cc",
    "ar_on",
    "ar_id",
    "z_cc",
    "z_on",
    "z_id",
    "z_vol",
)


@dataclass
class Inputs:
    members: pd.DataFrame
    symbols: pd.DataFrame
    symbol_tickers: pd.DataFrame
    gics: pd.DataFrame
    prices_raw: pd.DataFrame
    total: pd.DataFrame
    actions: pd.DataFrame
    shares: pd.DataFrame
    dp: pd.DataFrame
    spy_close: pd.Series
    yahoo_shares: pd.DataFrame
    public_end: date
    test_start: date
    test_end: date


@dataclass
class Assembled:
    sessions: pd.DatetimeIndex
    symbols: list[int]
    spy_id: int
    frames: dict[str, pd.DataFrame]
    static: pd.DataFrame  # per symbol: ticker, company_id, adj_source, price_symbol
    mapping: pd.DataFrame
    companies: pd.DataFrame
    tiers_monthly: pd.DataFrame
    qc: pd.DataFrame
    notes: dict[str, object] = field(default_factory=dict)


def _snap(name: str, layout: Layout | None) -> pd.DataFrame:
    return io.read_parquet(f"{SNAPSHOT}/{name}.parquet", layout=layout)


def load_inputs(layout: Layout | None = None) -> Inputs:
    """Registered public inputs (hash-verified reads)."""
    splits = load_splits().splits
    test_end = splits["test"].end
    dp = io.read_data_parquet("prices/prices.parquet", layout=layout)
    dp = dp[dp["date"] <= pd.Timestamp(test_end)]
    mp = io.read_parquet("market/market_prices.parquet", layout=layout)
    spy = mp[(mp["symbol"] == SPY) & (mp["date"] <= pd.Timestamp(test_end))]
    spy_close = pd.Series(spy["close"].to_numpy(), index=pd.to_datetime(spy["date"]).dt.normalize())
    ys = io.read_parquet("market/shares.parquet", layout=layout)  # share counts only, no prices
    ys = ys[ys["date"] <= pd.Timestamp(test_end)]
    return Inputs(
        members=_snap("members_by_session", layout),
        symbols=_snap("symbols", layout),
        symbol_tickers=_snap("symbol_tickers", layout),
        gics=_snap("gics", layout),
        prices_raw=_snap("prices_raw", layout),
        total=_snap("total_return_check", layout),
        actions=adjust.classify_actions(_snap("corporate_actions", layout)),
        shares=_snap("shares_basic", layout),
        dp=dp,
        spy_close=spy_close,
        yahoo_shares=ys,
        public_end=splits["val_b"].end,
        test_start=splits["test"].start,
        test_end=test_end,
    )


def _members_wide(members: pd.DataFrame, sessions: pd.DatetimeIndex, symbols: list[int]) -> pd.DataFrame:
    """Membership at open(s); sessions before the first snapshot use the first snapshot's set."""
    m = members.assign(one=1.0, session=pd.to_datetime(members["session"]))
    w = wide(m, "one", sessions, symbols).notna()
    first = pd.Timestamp(m["session"].min())
    w.loc[w.index < first] = w.loc[first].to_numpy()
    return w


def _event_days(actions: pd.DataFrame, until: pd.Timestamp) -> dict[int, pd.DatetimeIndex]:
    a = actions[actions["ex_session"] <= until]
    out: dict[int, list[pd.Timestamp]] = {}
    for sid, ex in zip(a["symbol_id"].tolist(), a["ex_session"].tolist(), strict=True):
        out.setdefault(int(sid), []).append(pd.Timestamp(ex))
    return {k: pd.DatetimeIndex(v) for k, v in out.items()}


def _row(frame: pd.DataFrame, ts: pd.Timestamp) -> pd.Series:
    out = frame.loc[ts]
    if not isinstance(out, pd.Series):
        raise TypeError(f"{ts} selects more than one row")
    return out


def _broadcast(row: pd.Series | npt.NDArray[np.float64], like: pd.DataFrame) -> pd.DataFrame:
    """A frame shaped like ``like`` whose every row is ``row`` (aligned on columns)."""
    vals = row.reindex(like.columns).to_numpy() if isinstance(row, pd.Series) else np.asarray(row)
    return pd.DataFrame(np.broadcast_to(vals, like.shape), index=like.index, columns=like.columns)


def _rows_mask(rows: npt.NDArray[np.bool_], like: pd.DataFrame) -> pd.DataFrame:
    """A bool frame shaped like ``like`` that is True on the selected rows."""
    return pd.DataFrame(np.broadcast_to(rows[:, None], like.shape), index=like.index, columns=like.columns)


def _month_keys(sessions: pd.Index) -> npt.NDArray[np.str_]:
    return np.array([tiers.month_key(pd.Timestamp(ts)) for ts in sessions])


def _month_frames(
    tm: pd.DataFrame, sessions: pd.DatetimeIndex, symbols: list[int], company: dict[int, int]
) -> dict[str, pd.DataFrame]:
    """Per-session tier columns: the row of the session's month for the symbol's company."""
    months = _month_keys(sessions)
    cid = [company[s] for s in symbols]
    shape = (len(sessions), len(symbols))
    obj = {c: np.full(shape, None, dtype=object) for c in ("tier", "dv_tier", "tier_source")}
    num = {c: np.full(shape, np.nan) for c in ("rank", "dv_rank")}
    rep = np.zeros(shape, dtype=bool)
    sym_arr = np.asarray(symbols)
    for mo in sorted(set(tm["month"].tolist())):
        rows = months == mo
        g = tm[tm["month"] == mo].set_index("company_id")
        for c in obj:
            obj[c][rows] = g[c].reindex(cid).to_numpy(dtype=object)
        for c in num:
            num[c][rows] = g[c].reindex(cid).to_numpy(dtype="float64")
        rep[rows] = np.isin(sym_arr, g["rep_symbol_id"].to_numpy(dtype="int64"))
    out = {c: pd.DataFrame(v, index=sessions, columns=symbols) for c, v in {**obj, **num}.items()}
    out["is_rep"] = pd.DataFrame(rep, index=sessions, columns=symbols)
    return out


@dataclass
class _Prices:
    ro: pd.DataFrame
    rc: pd.DataFrame
    rv: pd.DataFrame
    tc: pd.DataFrame
    ac: pd.DataFrame
    vol_dp: pd.DataFrame
    mapping: pd.DataFrame


def _prices(inp: Inputs, sessions: pd.DatetimeIndex, symbols: list[int], spy_id: int) -> _Prices:
    """Raw OHLCV, ATOM total close, and the adjusted close chosen by the validated mapping (S2)."""
    public = sessions[sessions <= pd.Timestamp(inp.public_end)]
    all_ids = [*symbols, spy_id]
    px = inp.prices_raw.rename(columns={"trade_date": "session"})
    ro, rc, rv = (wide(px, c, sessions, all_ids) for c in ("open", "close", "volume"))
    tc = wide(inp.total.rename(columns={"trade_date": "session"}), "close", sessions, all_ids)
    dp = inp.dp.rename(columns={"date": "session"})
    price_syms = sorted(str(x) for x in dp["symbol"].unique())
    ac_dp = wide(dp, "close", sessions, price_syms, symbol_col="symbol")
    dpv = wide(dp, "volume", sessions, price_syms, symbol_col="symbol")
    stocks = inp.symbols[inp.symbols["symbol_id"].isin(symbols)]
    events = _event_days(inp.actions, pd.Timestamp(inp.public_end))
    mp = mapping.map_symbols(stocks, inp.symbol_tickers, rc.loc[public, symbols], ac_dp.loc[public], events)
    mp["adj_source"] = np.where(mp["price_symbol"].notna(), "data_prices", "atom_total")
    chosen = {
        int(k): str(v) for k, v in zip(mp["symbol_id"], mp["price_symbol"], strict=True) if isinstance(v, str)
    }
    ac = pd.DataFrame(np.nan, index=sessions, columns=all_ids)
    vol_dp = pd.DataFrame(np.nan, index=sessions, columns=symbols)
    for sid in symbols:
        if sid in chosen:
            ac[sid], vol_dp[sid] = ac_dp[chosen[sid]], dpv[chosen[sid]]
        else:
            ac[sid] = tc[sid]
    ac[spy_id] = inp.spy_close.reindex(sessions)
    return _Prices(ro, rc, rv, tc, ac, vol_dp, mp)


def _ranking_inputs(
    pr: _Prices,
    r: dict[str, pd.DataFrame],
    symbols: list[int],
    public_end: pd.Timestamp,
    actions: pd.DataFrame,
    level: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(dollar volume, raw close for ranking, its source, 63-session ADV ending at each session).

    Public sessions use ATOM raw prices. Test sessions (raw prices blinded): dollar volume from
    Data/prices (unit-matched to ATOM over the last 63 public sessions); raw close reconstructed from
    the adjusted close (``adjust.reconstruct_raw_close``); names without Data/prices keep their last
    public close and ADV (``stale_public``). PREREG §15.

    ``level`` (per symbol) rescales ATOM raw closes that are not on the traded price level
    (``adjust.raw_level_check``) and, inversely, their raw volume: ATOM's error is split-like (HON:
    price halved, volume doubled; tests/test_panel_adjust.py). Those symbols also take
    ``stale_public`` closes in test months, because their reconstructed level would depend on how each
    vendor treated a later split.
    """
    sessions = pr.rc.index
    test = _rows_mask(np.asarray(sessions > public_end), pr.rc[symbols])
    public = sessions[sessions <= public_end]
    dv_yahoo = pr.ac[symbols] * pr.vol_dp
    raw = pr.rc[symbols] * _broadcast(level, pr.rc[symbols])  # raw close on the traded level
    dv = raw * (pr.rv[symbols] / _broadcast(level, pr.rv[symbols]))  # x volume on the traded level
    kappa = adjust.unit_ratio(dv, dv_yahoo, public[-DV_UNIT_WINDOW:])
    dv = dv.mask(test & dv.isna(), dv_yahoo * _broadcast(kappa, dv))
    f_level = r["f"][symbols] / _broadcast(level, raw)
    rc_hat = adjust.reconstruct_raw_close(pr.ac[symbols], _row(f_level, public_end), public_end, actions)
    rc_hat.loc[:, list(level.index[level != 1.0])] = np.nan
    close = raw.combine_first(rc_hat)
    source = pd.DataFrame(None, index=sessions, columns=symbols, dtype=object)
    source = source.mask(rc_hat.notna(), "reconstructed").mask(raw.notna(), "atom_raw")
    stale = test & close.isna()
    close = close.mask(stale, _broadcast(_row(raw, public_end), close))
    source = source.mask(stale & close.notna(), "stale_public")
    adv = dv.rolling(risk.ADV_WINDOW, min_periods=risk.ADV_MIN).mean()  # window ending at the session itself
    adv = adv.mask(test & adv.isna(), _broadcast(_row(adv, public_end), adv))
    return dv, close, source, adv


def _sector_pool(
    adv: pd.DataFrame, members: pd.DataFrame, company: dict[int, int], ranking: dict[str, pd.Timestamp]
) -> pd.DataFrame:
    """Representative class of each member company per session (the sector-factor pool)."""
    sessions = adv.index
    months = _month_keys(sessions)
    month_rank = {mo: ranking.get(mo, pd.Timestamp(sessions[0])) for mo in sorted(set(months.tolist()))}
    rep = tiers.representative(adv.loc[sorted(set(month_rank.values()))], pd.Series(company))
    pool = pd.DataFrame(False, index=sessions, columns=members.columns)
    for mo, m in month_rank.items():
        reps = rep.loc[rep["ranking_session"] == m, "rep_symbol_id"].astype(int).tolist()
        pool.loc[months == mo, reps] = True
    return pool & members


def _volume(pr: _Prices, symbols: list[int], public_end: pd.Timestamp, actions: pd.DataFrame) -> pd.DataFrame:
    """Share volume on one true-split basis: ATOM raw (public), Data/prices unit-matched (test).

    After a true split dated in the test period, Data/prices' volume basis cannot be verified without
    inspecting test data, so test-period volume from that ex-date on is NaN.
    """
    sessions = pr.rv.index
    public = sessions[sessions <= public_end]
    until = pd.Timestamp(actions["ex_session"].max())
    vol = adjust.split_adjusted_volume(
        pr.rv[symbols], adjust.true_split_factor_after(sessions, symbols, actions, until)
    )
    vol_test = pr.vol_dp * _broadcast(adjust.unit_ratio(vol, pr.vol_dp, public[-VOL_UNIT_WINDOW:]), pr.vol_dp)
    late = actions[(actions["kind"] == "split") & (actions["ex_session"] > public_end)]
    for sid, ex in zip(late["symbol_id"].tolist(), late["ex_session"].tolist(), strict=True):
        if sid in vol_test.columns:
            vol_test.loc[vol_test.index >= ex, sid] = np.nan
    test = _rows_mask(np.asarray(sessions > public_end), vol)
    return vol.mask(test & vol.isna(), vol_test)


def _yahoo_shares(inp: Inputs, mp: pd.DataFrame, symbols: list[int]) -> tiers.YahooShares:
    """Yahoo share counts per symbol: the Data/prices symbol, else the ATOM ticker or an alias."""
    aliases: dict[int, list[str]] = {}
    for sid, t in zip(inp.symbol_tickers["symbol_id"], inp.symbol_tickers["ticker"], strict=True):
        aliases.setdefault(int(sid), []).append(mapping.normalize_ticker(str(t)))
    tickers: dict[int, list[str]] = {}
    for rec in mp.to_dict("records"):
        sid = int(rec["symbol_id"])
        if sid in symbols:
            first = [str(rec["price_symbol"])] if isinstance(rec["price_symbol"], str) else []
            tickers[sid] = [*first, mapping.normalize_ticker(str(rec["atom_ticker"])), *aliases.get(sid, [])]
    spl = inp.actions[inp.actions["kind"] == "split"]
    splits: dict[int, list[tuple[pd.Timestamp, float]]] = {}
    for sid, ex, ratio in zip(spl["symbol_id"], spl["ex_session"], spl["split_ratio"], strict=True):
        splits.setdefault(int(sid), []).append((pd.Timestamp(ex), float(ratio)))
    return tiers.YahooShares(inp.yahoo_shares, tickers, splits)


def assemble(inp: Inputs) -> Assembled:
    """The full grid computation (pure: no I/O)."""
    sessions = session_index(HISTORY_START, inp.test_end)
    public_end = pd.Timestamp(inp.public_end)
    public = sessions[sessions <= public_end]
    spy_ids = [int(x) for x in inp.symbols.loc[inp.symbols["ticker"] == SPY, "symbol_id"]]
    if len(spy_ids) != 1:
        raise ValueError(f"expected one SPY symbol, got {spy_ids}")
    spy_id = spy_ids[0]
    symbols = sorted(int(x) for x in inp.symbols["symbol_id"] if int(x) != spy_id)

    pr = _prices(inp, sessions, symbols, spy_id)
    pr.rv, vol_fixes = adjust.volume_basis_check(pr.rv, pr.vol_dp, inp.actions, public)
    r = adjust.returns(pr.ac, pr.ro, pr.rc)
    mapped = pd.Series(True, index=pr.mapping.loc[pr.mapping["price_symbol"].notna(), "symbol_id"])
    qc = adjust.qc_flags(r, pr.tc, inp.actions, mapped, public)
    lvl = adjust.raw_level_check(r["f"][symbols], pr.rc[symbols], inp.actions, public)
    level = lvl["level_factor"].astype("float64")
    pr.mapping = pr.mapping.merge(lvl.reset_index(), on="symbol_id", how="left")
    fixed_days = vol_fixes.groupby("symbol_id").size()
    pr.mapping["volume_basis_days"] = pr.mapping["symbol_id"].map(fixed_days).fillna(0).astype("int64")

    comp = tiers.companies(inp.symbols[inp.symbols["symbol_id"].isin(symbols)])
    company = {int(a): int(b) for a, b in zip(comp["symbol_id"], comp["company_id"], strict=True)}
    members = _members_wide(inp.members, sessions, symbols)
    dv, close_rank, close_source, adv = _ranking_inputs(pr, r, symbols, public_end, inp.actions, level)
    ranking = tiers.month_ranking_sessions(sessions)

    # S3: sector and leave-one-company-out sector returns
    pool = _sector_pool(adv, members, company, ranking)
    sec = sector.sector_of(inp.gics, sessions, symbols)
    r_stock = {x: r[f"r_{x}"][symbols] for x in risk.RETURN_TYPES}
    r_mkt = {x: r[f"r_{x}"][spy_id] for x in risk.RETURN_TYPES}
    r_s: dict[str, pd.DataFrame] = {}
    sec_n: dict[str, pd.DataFrame] = {}
    for x in risk.RETURN_TYPES:
        r_s[x], sec_n[x] = sector.loo_sector_return(r_stock[x], sec, pool, pd.Series(company))

    # S4: risk
    minutes = pd.Series({ts: float(calendar.session_minutes(ts.date())) for ts in sessions})
    vol = _volume(pr, symbols, public_end, inp.actions)
    rk = risk.compute_risk(r_stock, r_mkt, r_s, members, minutes, vol, dv)

    # S5: monthly tiers, months PANEL_START .. test end
    months = _month_keys(sessions)
    applied = [mo for mo in sorted(set(months.tolist())) if mo >= tiers.month_key(pd.Timestamp(PANEL_START))]
    rank_sessions = pd.DatetimeIndex([ranking[mo] for mo in applied])
    known_by = {m: calendar.close_utc(m.date()) for m in rank_sessions}
    members_by_month: dict[str, tuple[set[int], set[int]]] = {}
    for mo in applied:
        at_m = _row(members, ranking[mo])
        during = members.loc[months == mo].any(axis=0)
        members_by_month[mo] = (
            {int(c) for c in at_m.index[at_m.to_numpy(dtype=bool)]},
            {int(c) for c in during.index[during.to_numpy(dtype=bool)]},
        )
    tm = tiers.monthly_tiers(
        applied,
        ranking,
        close_rank.loc[rank_sessions],
        close_source.loc[rank_sessions],
        adv.loc[rank_sessions],
        members_by_month,
        company,
        tiers.share_book(inp.shares, inp.actions),
        known_by,
        yahoo=_yahoo_shares(inp, pr.mapping, symbols),
        stale_basis=public_end,
    )
    # test months keep ranks and tiers; their price-level columns come from test closes and are dropped
    blind = pd.to_datetime(tm["ranking_session"]) > public_end
    tm.loc[blind, ["raw_close", "cap_usd", "cap_rank_value", "adv63_usd"]] = np.nan

    spy = {
        f"r_spy_{x}": pd.DataFrame(
            np.repeat(r_mkt[x].to_numpy()[:, None], len(symbols), axis=1), sessions, symbols
        )
        for x in risk.RETURN_TYPES
    }
    frames: dict[str, pd.DataFrame] = {
        "member": members,
        "raw_open": pr.ro[symbols],
        "raw_close": pr.rc[symbols],
        "raw_volume": pr.rv[symbols],
        "adj_close": pr.ac[symbols],
        "adj_open": r["adj_open"][symbols],
        "adj_factor": r["f"][symbols],
        **{f"r_{x}": r_stock[x] for x in risk.RETURN_TYPES},
        **spy,
        **{f"r_sec_{x}": r_s[x] for x in risk.RETURN_TYPES},
        "r_sec_n": sec_n["cc"],
        "sector": sec,
        **_month_frames(tm, sessions, symbols, company),
        **rk,
    }
    static = comp[["symbol_id", "ticker", "company_id"]].merge(
        pr.mapping[["symbol_id", "adj_source", "price_symbol"]], on="symbol_id"
    )
    notes: dict[str, object] = {"close_source": close_source.loc[rank_sessions], "volume_basis": vol_fixes}
    return Assembled(sessions, symbols, spy_id, frames, static, pr.mapping, comp, tm, qc, notes)


def panel_rows(asm: Assembled, after_exit: int = POST_EXIT_SESSIONS) -> pd.DataFrame:
    """Cells kept in the long panels: member sessions, plus priced sessions up to ``after_exit``
    sessions after a membership spell (so every target horizon of a leaver stays computable)."""
    member = asm.frames["member"].to_numpy(dtype=bool)
    priced = asm.frames["raw_close"].notna().to_numpy() | asm.frames["adj_close"].notna().to_numpy()
    pos = np.arange(member.shape[0])[:, None]
    last_member = np.maximum.accumulate(np.where(member, pos, -1), axis=0)
    recent = (last_member >= 0) & (pos - last_member <= after_exit)
    keep = member | (priced & recent)
    return pd.DataFrame(keep, index=asm.sessions, columns=asm.symbols)


# --- long panels ------------------------------------------------------------------------------------


def long_panel(
    asm: Assembled, sessions: pd.DatetimeIndex, columns: tuple[str, ...], rows: pd.DataFrame
) -> pd.DataFrame:
    """Long frame of the grid columns for the selected (session, symbol) cells."""
    frames = {c: asm.frames[c].loc[sessions, asm.symbols] for c in columns if c in asm.frames}
    df = to_long(frames, rows.loc[sessions, asm.symbols])
    df = df.merge(asm.static, on="symbol_id", how="left")
    days = pd.Index(pd.to_datetime(df["session"]).unique())
    df["half_day"] = df["session"].map({d: calendar.is_half_day(d.date()) for d in days})
    df["split"] = df["session"].map({d: targets.split_of_session(d.date()) for d in days})
    df["session"] = pd.to_datetime(df["session"]).dt.date
    return df


def test_returns_panel(
    prices: pd.DataFrame, total: pd.DataFrame, *, layout: Layout | None = None
) -> pd.DataFrame:
    """Returns panel over public + test sessions with the blinded prices added.

    Only ``targets.build_targets(..., "test")`` and ``reactions.build_reactions(..., "test", ...)`` call
    this, with frames they obtained from ``newsaction.lock`` (after the freeze / unblinding).
    """
    inp = load_inputs(layout)
    inp = replace(
        inp,
        prices_raw=pd.concat([inp.prices_raw, prices], ignore_index=True),
        total=pd.concat([inp.total, total], ignore_index=True),
    )
    asm = assemble(inp)
    cols = (
        "ar_cc",
        "ar_on",
        "ar_id",
        "sigma_cc",
        "sigma_on",
        "sigma_id",
        "z_id",
        "r_cc",
        "r_spy_cc",
        "z_vol",
        "member",
        # the D1 route (bars.derive.test_intraday_panel, NA-10)
        "is_rep",
        "sector",
        "raw_open",
        "raw_close",
        "r_on",
        "r_spy_on",
        "beta_m",
        "beta_s",
    )
    return long_panel(asm, asm.sessions, cols, panel_rows(asm))


PANEL_PUBLIC_COLUMNS: Final = (
    "member",
    "is_rep",
    "tier",
    "rank",
    "dv_tier",
    "dv_rank",
    "tier_source",
    "sector",
    *SAME_DAY_COLUMNS,
    *T1_RISK_COLUMNS,
    *T1_PUBLIC_ONLY,
)
PANEL_TEST_COLUMNS: Final = ("member", "is_rep", *TIER_COLUMNS[:-1], "sector", *T1_RISK_COLUMNS)


def public_panel(asm: Assembled, public_end: date) -> pd.DataFrame:
    sess = asm.sessions[
        (asm.sessions >= pd.Timestamp(PANEL_START)) & (asm.sessions <= pd.Timestamp(public_end))
    ]
    df = long_panel(asm, sess, PANEL_PUBLIC_COLUMNS, panel_rows(asm))
    qc = asm.qc.assign(session=pd.to_datetime(asm.qc["session"]).dt.date)
    qc = (
        qc.groupby(["session", "symbol_id"])["rule"]
        .agg(lambda s: "+".join(sorted(set(s))))
        .rename("qc_rule")
        .reset_index()
    )
    df = df.merge(qc, on=["session", "symbol_id"], how="left")
    df["qc_flag"] = df["qc_rule"].notna()
    tg = targets.build_targets(df, targets.PUBLIC)
    rx = reactions.build_reactions(df, "public", "D2")[["session", "symbol_id", "g_d2", "g_d2_lvl"]]
    df = df.merge(tg.drop(columns=["split"]), on=["session", "symbol_id"], how="left")
    df = df.merge(rx, on=["session", "symbol_id"], how="left")
    return df.sort_values(["session", "symbol_id"]).reset_index(drop=True)


def test_inputs_panel(asm: Assembled, test_start: date, test_end: date) -> pd.DataFrame:
    sess = asm.sessions[(asm.sessions >= pd.Timestamp(test_start)) & (asm.sessions <= pd.Timestamp(test_end))]
    df = long_panel(asm, sess, PANEL_TEST_COLUMNS, asm.frames["member"])
    return df.sort_values(["session", "symbol_id"]).reset_index(drop=True)


def _order(df: pd.DataFrame, first: tuple[str, ...]) -> pd.DataFrame:
    cols = [c for c in first if c in df.columns] + [c for c in df.columns if c not in first]
    return df[cols]


ID_ORDER: Final = ("session", "symbol_id", *STATIC_ID_COLUMNS)


def write_all(asm: Assembled, inp: Inputs, layout: Layout | None = None) -> dict[str, dict[str, object]]:
    lay = resolve_layout(layout)
    out: dict[str, dict[str, object]] = {}
    pub = _order(public_panel(asm, inp.public_end), ID_ORDER)
    tst = _order(test_inputs_panel(asm, inp.test_start, inp.test_end), ID_ORDER)
    comp = asm.companies.merge(
        asm.mapping[["symbol_id", "price_symbol", "status", "adj_source"]], on="symbol_id", how="left"
    )
    mem = asm.frames["member"]
    span = {}
    for sid in asm.symbols:
        on = mem.index[mem[sid].to_numpy(dtype=bool)]
        span[sid] = (on[0].date(), on[-1].date()) if len(on) else (None, None)
    comp["first_member_session"] = [span[int(x)][0] for x in comp["symbol_id"]]
    comp["last_member_session"] = [span[int(x)][1] for x in comp["symbol_id"]]
    sec = asm.frames["sector"].iloc[-1]
    comp["sector"] = comp["symbol_id"].map(sec)
    qc = asm.qc.merge(asm.static[["symbol_id", "ticker"]], on="symbol_id", how="left")
    qc["session"] = pd.to_datetime(qc["session"]).dt.date
    tm = asm.tiers_monthly.copy()
    for c in ("ranking_session", "ciq_period_end", "yahoo_obs_date"):
        tm[c] = pd.to_datetime(tm[c]).dt.date
    files = {
        "panel/panel_public.parquet": (
            pub,
            "daily public panel (PANEL_START .. val-B end): ids, tiers, returns, AR, sigma, z, beta, targets",
        ),
        "panel/panel_test_inputs.parquet": (
            tst,
            "test-period sessions x members: static and t-1 columns only",
        ),
        "panel/companies.parquet": (
            comp,
            "symbol -> company (share classes grouped), mapping status, membership span",
        ),
        "panel/tiers_monthly.parquet": (
            tm,
            "monthly size and DV tiers (ranking session = last session of the previous month)",
        ),
        "panel/qc_flags.parquet": (
            qc,
            "public symbol-days with |r_cc - ATOM total| > 50 bp or |r_on| > 25%, with reasons",
        ),
        "panel/mapping.parquet": (
            asm.mapping,
            "ATOM symbol_id -> Data/prices symbol with correlation validation",
        ),
    }
    for rel, (df, desc) in files.items():
        out[rel] = io.write_parquet(
            df.reset_index(drop=True), rel, producer=PRODUCER, description=desc, layout=lay
        )
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="python -m newsaction.panel.build", description=__doc__).parse_args(argv)
    inp = load_inputs()
    asm = assemble(inp)
    written = write_all(asm, inp)
    for rel, entry in written.items():
        print(f"wrote work/{rel}: {entry['rows']:,} rows, sha256 {str(entry['sha256'])[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
