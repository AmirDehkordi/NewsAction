"""State context through t−1 and the D2 reaction (PREREG §6.10; PRD NA-04 S2, S5).

Numbers first, words second: ``company_context``, ``market_context`` and ``reaction_d2`` compute registered
numeric columns (``configs/availability.yaml``); the ``*_block`` functions turn one row into a state block
through the codebook, reading only the columns ``block_columns`` declares (``build`` checks those columns
with ``pit.check_inputs`` before rendering).

**Company** (per representative symbol and session; panel rows ``panel_public`` ∪ ``panel_test_inputs``, t−1
columns only):
- ``sector``, ``tier``, ``beta_m`` (NA-01, t−1);
- ``ctx_sigma_cc_pct``: percent of the symbol's previous 252 ``sigma_cc`` values below today's (≥ 126);
- ``z_m{5,20,60}`` (NA-01 momentum through t−1) and, for E4, ``ctx_z_m{k}_pct`` (percent of the previous
  252 |z_m{k}| below today's); for E0, ``ctx_ret_m{k}`` = AdjClose(t−1) / AdjClose(t−1−k) − 1 (public
  sessions only; E0 states exist only for the val samples);
- ``ctx_eps_revision``: FY1 = the first annual period ending after the session; consensus mean as of the
  last snapshot dated before the session vs as of 30 days earlier (``codebook.revision_value``);
- ``ctx_earnings_w0`` / ``ctx_earnings_w2``: an earnings timestamp (naive America/New_York wall time) in
  [close(prev s), 09:15 ET of s] / [close(prev s), close(s)). The window is closed on the left and open on
  the right because a timestamp at the close means "after the close": it belongs to the next session.

**Market** (per session; ``configs/states.yaml`` ``market.series``): each series is taken as of the last
observation dated on or before each session; its daily change (return or difference) on the previous session
(``extra_lag`` sessions earlier for slow publishers) is scored against the 252 changes before it:
``z`` = change / (1.4826 · MAD), ``pct`` = percent of past |changes| below |change| (≥ 126). The VIX also gets
its level percentile. ``mkt_spy_ret_m{k}`` is SPY's k-session return through t−1 (E0 benchmark).

**Reaction at D2** (Call B; public sessions only): ``panel.reactions.build_reactions`` gives G = z_cc,t and
the stock's and SPY's close-to-close returns and z_vol,t; the state adds SPY's same-day z against its 252
changes through t−1, the E4 percentiles, and the volume multiple exp(z_vol,t · 1.4826·MAD) = V_t / median V.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, Literal, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from newsaction import calendar
from newsaction.states import Encoding, StatesConfig, StateWindow
from newsaction.states.codebook import Codebook, Horizon, Move, Unit
from newsaction.states.macro import MacroCalendar

FloatArray = npt.NDArray[np.float64]
MAD_SCALE: Final = 1.4826
PERF_KEYS: Final[Mapping[str, str]] = {
    "week": "past_week",
    "month": "past_month",
    "three_months": "past_three_months",
}
MARKET_KEYS: Final[Mapping[str, str]] = {
    "stock_market": "stock_market_previous_session",
    "vix": "vix_change",
    "ten_year_yield": "ten_year_yield_change",
    "high_yield_spread": "high_yield_spread_change",
    "dollar": "dollar_change",
    "oil": "oil_change",
}
Block = Literal["company", "market", "attention", "news", "reaction_so_far"]


class ContextError(ValueError):
    """A context input is missing or inconsistent."""


# --- trailing-history statistics --------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryStats:
    """For each position j, statistics of x[j − window : j] (the history before j) against x[j]."""

    sigma: FloatArray  # 1.4826 · MAD of the history
    pct_abs: FloatArray  # percent of |history| strictly below |x[j]|
    pct_level: FloatArray  # percent of history strictly below x[j]
    count: npt.NDArray[np.int64]


def history_stats(x: Sequence[float] | FloatArray, window: int, min_obs: int) -> HistoryStats:
    """Trailing statistics that never include x[j] itself; NaN where fewer than ``min_obs`` are valid."""
    arr = np.asarray(x, dtype=np.float64)
    n = len(arr)
    pad = np.concatenate([np.full(window, np.nan), arr])
    win = sliding_window_view(pad, window)[:n]  # win[j] = arr[j - window : j]
    valid = ~np.isnan(win)
    count = valid.sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(win, axis=1)
        mad = np.nanmedian(np.abs(win - med[:, None]), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            pct_abs = 100.0 * (np.abs(win) < np.abs(arr)[:, None]).sum(axis=1) / count
            pct_level = 100.0 * (win < arr[:, None]).sum(axis=1) / count
    enough = count >= min_obs
    sigma = np.where(enough, MAD_SCALE * mad, np.nan)
    own = ~np.isnan(arr)
    return HistoryStats(
        sigma=sigma,
        pct_abs=np.where(enough & own, pct_abs, np.nan),
        pct_level=np.where(enough & own, pct_level, np.nan),
        count=count.astype(np.int64),
    )


def _shift(a: FloatArray, k: int) -> FloatArray:
    out = np.full_like(a, np.nan)
    if k < len(a):
        out[k:] = a[: len(a) - k]
    return out


# --- market ------------------------------------------------------------------------------------------


def session_grid(first: date, last: date, history_sessions: int) -> list[date]:
    """Sessions from enough history before ``first`` (3 × history, for lags and min obs) to ``last``."""
    start = first - timedelta(days=int(history_sessions * 3 * 1.5))
    return calendar.sessions(start, last)


def as_of_levels(values: pd.Series, sessions: Sequence[date]) -> FloatArray:
    """The last non-NaN value dated on or before each session (calendar dates)."""
    s = values.dropna()
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    target = pd.DatetimeIndex(pd.to_datetime(list(sessions)))
    pos = s.index.searchsorted(target, side="right") - 1
    vals = s.to_numpy(dtype=np.float64)
    return np.where(pos >= 0, vals[np.clip(pos, 0, None)], np.nan)


def series_levels(
    market_prices: pd.DataFrame, fred: pd.DataFrame, sessions: Sequence[date], cfg: StatesConfig
) -> dict[str, FloatArray]:
    out: dict[str, FloatArray] = {}
    for name, sc in cfg.market.series.items():
        if sc.source == "market_prices":
            sub = market_prices.loc[market_prices["symbol"] == sc.symbol]
            values = pd.Series(sub["close"].to_numpy(dtype=np.float64), index=sub["date"])
        else:
            sub = fred.loc[fred["series_id"] == sc.symbol]
            values = pd.Series(sub["value"].to_numpy(dtype=np.float64), index=sub["date"])
        if values.empty:
            raise ContextError(f"no data for market series {name} ({sc.symbol})")
        out[name] = as_of_levels(values, sessions)
    return out


def daily_change(level: FloatArray, kind: str, scale: float) -> FloatArray:
    prev = _shift(level, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "return":
            return (level / prev - 1.0) * scale
        return (level - prev) * scale


def market_context(
    levels: Mapping[str, FloatArray], sessions: Sequence[date], cfg: StatesConfig
) -> pd.DataFrame:
    """One row per session of ``sessions``; every value uses data through the previous session or earlier."""
    w, m = cfg.context.history_sessions, cfg.context.history_min
    out: dict[str, Any] = {"session": list(sessions)}
    for name, sc in cfg.market.series.items():
        chg = daily_change(levels[name], sc.change, sc.value_scale)
        st = history_stats(chg, w, m)
        k = 1 + sc.extra_lag  # the change dated k sessions before s
        with np.errstate(invalid="ignore", divide="ignore"):
            z = chg / st.sigma
        out[f"mkt_{name}_chg"] = _shift(chg, k)
        out[f"mkt_{name}_z"] = _shift(z, k)
        out[f"mkt_{name}_pct"] = _shift(st.pct_abs, k)
        if name in cfg.market.level_percentile:
            lv = history_stats(levels[name], w, m)
            out[f"mkt_{name}_level_pct"] = _shift(lv.pct_level, k)
        if name == "stock_market":
            out["mkt_stock_market_sigma_same"] = st.sigma  # history through prev(s): scores the move of s
            spy = levels[name]
            for k_win in cfg.context.perf_windows.values():
                with np.errstate(invalid="ignore", divide="ignore"):
                    out[f"mkt_spy_ret_m{k_win}"] = _shift(spy, 1) / _shift(spy, 1 + k_win) - 1.0
    return pd.DataFrame(out)


# --- company -----------------------------------------------------------------------------------------


def _grid(panel: pd.DataFrame, column: str, sessions: Sequence[date]) -> pd.DataFrame:
    g = panel.pivot(index="session", columns="symbol_id", values=column)
    return g.reindex(list(sessions)).astype("float64")


def company_context(
    panel: pd.DataFrame, adj_close: pd.DataFrame, sessions: Sequence[date], cfg: StatesConfig
) -> pd.DataFrame:
    """t−1 company statistics on the (session, symbol_id) rows of ``panel``.

    ``panel``: t−1 columns of panel_public ∪ panel_test_inputs (session, symbol_id, sigma_cc, z_m*).
    ``adj_close``: public (session, symbol_id, adj_close) rows; same-day closes, used only shifted by one.
    """
    w, m = cfg.context.history_sessions, cfg.context.history_min
    keys = panel[["session", "symbol_id"]]
    cols: dict[str, pd.DataFrame] = {}
    sig = _grid(panel, "sigma_cc", sessions)
    cols["ctx_sigma_cc_pct"] = sig.apply(
        lambda c: pd.Series(history_stats(c.to_numpy(), w, m).pct_level, c.index)
    )
    for k in cfg.context.perf_windows.values():
        zg = _grid(panel, f"z_m{k}", sessions)
        cols[f"ctx_z_m{k}_pct"] = zg.apply(
            lambda c: pd.Series(history_stats(c.to_numpy(), w, m).pct_abs, c.index)
        )
    ac = _grid(adj_close, "adj_close", sessions)
    for k in cfg.context.perf_windows.values():
        cols[f"ctx_ret_m{k}"] = ac.shift(1) / ac.shift(1 + k) - 1.0
    out = keys.copy()
    for name, g in cols.items():
        stacked = cast(pd.Series, g.stack(future_stack=True)).rename(name)
        stacked.index = stacked.index.set_names(["session", "symbol_id"])
        out = out.merge(stacked.reset_index(), on=["session", "symbol_id"], how="left")
    return out


def eps_revision(
    keys: pd.DataFrame, estimates: pd.DataFrame, revision_days: int, cb: Codebook
) -> pd.DataFrame:
    """FY1 EPS consensus now (snapshot dated before the session) and ``revision_days`` earlier.

    ``keys``: (company_id, session); ``estimates``: estimates_fy1 rows with ``company_id``.
    """
    est = estimates.dropna(subset=["mean"]).copy()
    est["as_of"] = pd.to_datetime(est["as_of_date"]).astype("datetime64[ns]")
    est["period_end"] = pd.to_datetime(est["period_end"]).astype("datetime64[ns]")
    k = keys[["company_id", "session"]].drop_duplicates().copy()
    k["session_ts"] = pd.to_datetime(k["session"]).astype("datetime64[ns]")
    ends = est.groupby("company_id")["period_end"].unique()
    fy1 = []
    for cid, s in zip(k["company_id"], k["session_ts"], strict=True):
        e = ends.get(cid)
        if e is None:
            fy1.append(pd.NaT)
            continue
        later = np.sort(e[e > s])
        fy1.append(later[0] if len(later) else pd.NaT)
    k["period_end"] = pd.to_datetime(pd.Series(fy1, index=k.index)).astype("datetime64[ns]")
    res = k.copy()
    for label, offset in (("now", 1), ("before", 1 + revision_days)):
        q = k.dropna(subset=["period_end"]).copy()
        q["as_of"] = q["session_ts"] - pd.Timedelta(days=offset)  # as_of_date <= session - offset days
        q = q.sort_values("as_of")
        e = est.sort_values("as_of")[["company_id", "period_end", "as_of", "mean"]]
        hit = pd.merge_asof(q, e, on="as_of", by=["company_id", "period_end"], direction="backward")
        res = res.merge(
            hit[["company_id", "session", "mean"]].rename(columns={"mean": f"ctx_eps_fy1_{label}"}),
            on=["company_id", "session"],
            how="left",
        )
    res["ctx_eps_revision"] = [
        cb.revision_value(a, b)
        for a, b in zip(res["ctx_eps_fy1_now"], res["ctx_eps_fy1_before"], strict=True)
    ]
    return res[["company_id", "session", "ctx_eps_fy1_now", "ctx_eps_fy1_before", "ctx_eps_revision"]]


def normalize_ticker(t: str) -> str:
    return t.strip().upper().replace(".", "-").replace("/", "-")


def earnings_flags(
    keys: pd.DataFrame, earnings: pd.DataFrame, ticker_company: Mapping[str, int], tz: str
) -> pd.DataFrame:
    """``ctx_earnings_w0`` / ``ctx_earnings_w2`` for (company_id, session) keys (module docstring)."""
    e = earnings.copy()
    e["company_id"] = e["ticker"].map(lambda t: ticker_company.get(normalize_ticker(str(t))))
    e = e.dropna(subset=["company_id", "earnings_ts"])
    local = pd.to_datetime(e["earnings_ts"]).dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    utc = local.dt.tz_convert("UTC") + pd.Timedelta(microseconds=1)  # a stamp at the close -> next session
    e = e.assign(ts=utc).dropna(subset=["ts"])
    e["s_w0"] = calendar.session_of_w0_series(e["ts"])
    e["s_w2"] = calendar.session_of_w2_series(e["ts"])
    out = keys[["company_id", "session"]].drop_duplicates().copy()
    for w in ("w0", "w2"):
        hits = set(zip(e["company_id"].astype("int64"), e[f"s_{w}"], strict=True))
        out[f"ctx_earnings_{w}"] = [
            (int(c), s) in hits for c, s in zip(out["company_id"], out["session"], strict=True)
        ]
    return out


# --- D2 reaction -------------------------------------------------------------------------------------


def reaction_d2(
    reactions: pd.DataFrame,
    panel: pd.DataFrame,
    spy_change: FloatArray,
    sessions: Sequence[date],
    cfg: StatesConfig,
) -> pd.DataFrame:
    """Call B ``reaction_so_far`` inputs per (session, symbol_id) of ``reactions`` (public sessions).

    ``reactions``: ``panel.reactions.build_reactions`` output; ``panel``: public rows with ``z_cc`` (for the
    E4 history of the stock's own daily moves, rows before t) and ``logv_mad60`` (t−1);
    ``spy_change``: SPY daily returns on ``sessions`` (market_prices) for the SPY σ and E4 history.
    """
    w, m = cfg.context.history_sessions, cfg.context.history_min
    zg = _grid(panel, "z_cc", sessions)
    react = reactions.merge(
        panel[["session", "symbol_id", "logv_mad60"]], on=["session", "symbol_id"], how="left"
    )
    pos = {d: i for i, d in enumerate(sessions)}
    pad = np.concatenate([np.full(w, np.nan), spy_change])
    spy_win = sliding_window_view(pad, w)[: len(spy_change)]
    spy_stats = history_stats(spy_change, w, m)
    pct_g, spy_z, spy_pct = [], [], []
    col_pos = {c: i for i, c in enumerate(zg.columns)}
    zarr = zg.to_numpy()
    for s, sym, g, r_spy in zip(
        react["session"], react["symbol_id"], react["g_d2"], react["react_r_spy_cc"], strict=True
    ):
        i = pos.get(s)
        if i is None:
            raise ContextError(f"session {s} is not on the context grid")
        j = col_pos.get(sym)
        hist = zarr[max(0, i - w) : i, j] if j is not None else np.array([])
        hist = hist[~np.isnan(hist)]
        pct_g.append(
            100.0 * float((np.abs(hist) < abs(g)).mean())
            if len(hist) >= m and not math.isnan(g)
            else math.nan
        )
        sh = spy_win[i][~np.isnan(spy_win[i])]
        sigma = spy_stats.sigma[i]
        spy_z.append(r_spy / sigma if not (math.isnan(sigma) or math.isnan(r_spy)) else math.nan)
        spy_pct.append(
            100.0 * float((np.abs(sh) < abs(r_spy)).mean())
            if len(sh) >= m and not math.isnan(r_spy)
            else math.nan
        )
    react["react_g_pct"] = pct_g
    react["react_spy_z"] = spy_z
    react["react_spy_pct"] = spy_pct
    react["react_volume_multiple"] = np.exp(react["react_z_vol"] * react["logv_mad60"])
    return react.drop(columns=["logv_mad60"])


# --- rendering ---------------------------------------------------------------------------------------


def _perf_columns(encoding: Encoding, k: int) -> list[str]:
    if encoding == "E0":
        return [f"ctx_ret_m{k}", f"mkt_spy_ret_m{k}"]
    if encoding == "E4":
        return [f"z_m{k}", f"ctx_z_m{k}_pct"]
    return [f"z_m{k}"]


def _move_columns(prefix: str, encoding: Encoding) -> list[str]:
    if encoding == "E0":
        return [f"{prefix}_chg"]
    if encoding == "E4":
        return [f"{prefix}_z", f"{prefix}_pct"]
    return [f"{prefix}_z"]


def block_columns(block: Block, window: StateWindow, encoding: Encoding, cfg: StatesConfig) -> list[str]:
    """Every input column a block reads (checked with ``pit.check_inputs`` by ``build``)."""
    sfx = window.lower()
    if block == "company":
        cols = ["sector", "tier", "beta_m", "ctx_sigma_cc_pct", "ctx_eps_revision", f"ctx_earnings_{sfx}"]
        for k in cfg.context.perf_windows.values():
            cols += _perf_columns(encoding, k)
        return cols
    if block == "market":
        cols = ["macro_cpi_today", "macro_fomc_today"]
        for name in cfg.market.series:
            cols += _move_columns(f"mkt_{name}", encoding)
            if name in cfg.market.level_percentile:
                cols.append(f"mkt_{name}_level_pct")
        return cols
    if block == "attention":
        return [f"attention_ratio_{sfx}", f"n_stories_{sfx}"]
    if block == "news":
        return [f"news_{sfx}", "title_masked", "snippet_masked", "t_avail", "source_class_domain"]
    if block == "reaction_so_far":
        if window != "W2":
            raise ContextError("reaction_so_far exists only at D2 (D1 needs the NA-10 bars)")
        cols = ["react_volume_multiple"]
        cols += {
            "E0": ["react_r_cc", "react_r_spy_cc"],
            "E4": ["g_d2", "react_g_pct", "react_spy_z", "react_spy_pct"],
        }.get(encoding, ["g_d2", "react_spy_z"])
        return cols
    raise ContextError(f"unknown block {block!r}")


class Row:
    """A read-only view of the declared columns of one input row; reading anything else is an error."""

    def __init__(self, values: Mapping[str, Any], declared: Sequence[str]) -> None:
        missing = [c for c in declared if c not in values]
        if missing:
            raise ContextError(f"row lacks declared columns {missing}")
        self._v = {c: values[c] for c in declared}

    def __getitem__(self, column: str) -> Any:
        try:
            return self._v[column]
        except KeyError:
            raise ContextError(f"column {column!r} was not declared for this block") from None

    def get(self, column: str) -> Any:
        return self._v.get(column, math.nan)

    def num(self, column: str) -> float:
        v = self[column]
        return math.nan if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)) else float(v)


def _move(
    row: Row,
    cb: Codebook,
    encoding: Encoding,
    *,
    z: str | None,
    raw: str | None,
    pct: str | None,
    bench: str | None = None,
    horizon: Horizon = "day",
    unit: Unit = "pct",
) -> str:
    def val(col: str | None) -> float:
        return math.nan if col is None or encoding_unused(col) else row.num(col)

    def encoding_unused(col: str) -> bool:
        return col not in row._v

    move = Move(z=val(z), horizon=horizon, raw=val(raw), unit=unit, benchmark=val(bench), pct=val(pct))
    return cb.encode_move(move, encoding)


def company_block(
    row: Row, window: StateWindow, encoding: Encoding, cb: Codebook, cfg: StatesConfig
) -> dict[str, Any]:
    sfx = window.lower()
    perf = {}
    for name, k in cfg.context.perf_windows.items():
        horizon: Horizon = name  # type: ignore[assignment]
        perf[PERF_KEYS[name]] = _move(
            row,
            cb,
            encoding,
            z=f"z_m{k}",
            raw=f"ctx_ret_m{k}",
            pct=f"ctx_z_m{k}_pct",
            bench=f"mkt_spy_ret_m{k}",
            horizon=horizon,
        )
    sector = row["sector"]
    return {
        "sector": sector if isinstance(sector, str) and sector else cb.missing,
        "size": cb.tier_word(row["tier"]),
        "market_sensitivity": cb.beta_word(row.num("beta_m")),
        "volatility_vs_its_past_year": cb.percentile_word(row.num("ctx_sigma_cc_pct")),
        "performance_vs_market_and_sector": perf,
        "analyst_estimates_past_month": cb.revision_word(row.num("ctx_eps_revision")),
        "earnings_report": cb.earnings_word(bool(row[f"ctx_earnings_{sfx}"])),
    }


def market_block(
    row: Row, encoding: Encoding, cb: Codebook, cfg: StatesConfig, macro: MacroCalendar
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, sc in cfg.market.series.items():
        p = f"mkt_{name}"
        out[MARKET_KEYS[name]] = _move(
            row, cb, encoding, z=f"{p}_z", raw=f"{p}_chg", pct=f"{p}_pct", unit=sc.e0_unit
        )
        if name in cfg.market.level_percentile:
            out[f"{name}_level_vs_past_year"] = cb.percentile_word(row.num(f"{p}_level_pct"))
    out["scheduled_releases_today"] = macro.words(bool(row["macro_cpi_today"]), bool(row["macro_fomc_today"]))
    return out


def attention_block(row: Row, window: StateWindow, cb: Codebook) -> dict[str, Any]:
    sfx = window.lower()
    return {
        "articles_vs_usual": cb.attention_word(row.num(f"attention_ratio_{sfx}")),
        "distinct_stories": cb.count_word(row.num(f"n_stories_{sfx}")),
    }


def reaction_block(row: Row, encoding: Encoding, cb: Codebook) -> dict[str, Any]:
    return {
        "time": cb.time_label_word("D2"),
        "stock_move_vs_market_and_sector": _move(
            row, cb, encoding, z="g_d2", raw="react_r_cc", pct="react_g_pct", bench="react_r_spy_cc"
        ),
        "stock_market_move": _move(
            row, cb, encoding, z="react_spy_z", raw="react_r_spy_cc", pct="react_spy_pct"
        ),
        "volume_vs_normal": cb.attention_word(row.num("react_volume_multiple")),
    }
