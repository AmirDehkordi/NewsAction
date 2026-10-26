"""PRD NA-04 AC3: availability of every state input (CLAUDE.md A3, A5).

- A D0 Call A spec refuses z_id, z_cc and every post / w2 / reaction / selection-only column (PITError).
- Call B at D2 reads the D2 reaction (kind d2_reaction) in ``reaction_so_far`` only.
- Context values dated t do not move when day t (or a later day) changes: planted shocks.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar, pit
from newsaction.states import context as ctx
from newsaction.states import load_states_config
from newsaction.states.build import StatesError, build_event_states, make_spec, validate_spec
from newsaction.states.codebook import load_codebook

CFG = load_states_config()
REG = pit.default_registry()
ENCODINGS = ("E0", "E1", "E2", "E3", "E4")


def _with(spec_block: str, column: str, call: str = "A", window: str = "W0", encoding: str = "E3"):  # type: ignore[no-untyped-def]
    spec = make_spec("t", call, window, encoding, True, CFG)  # type: ignore[arg-type]
    blocks = dict(spec.blocks)
    blocks[spec_block] = (*blocks[spec_block], column)
    return replace(spec, blocks=blocks)


@pytest.mark.parametrize("encoding", ENCODINGS)
@pytest.mark.parametrize(("call", "window"), [("A", "W0"), ("A", "W2"), ("B", "W2"), ("M", "W2")])
def test_every_built_spec_is_valid(call: str, window: str, encoding: str) -> None:
    validate_spec(make_spec("t", call, window, encoding, True, CFG))  # type: ignore[arg-type]


def test_unmasked_spec_is_valid() -> None:
    validate_spec(make_spec("t", "A", "W0", "E3", False, CFG))


@pytest.mark.parametrize(
    "column",
    [
        "z_id",
        "z_cc",
        "z_on",
        "y0",
        "e5",
        "g_d2",
        "react_r_cc",
        "react_spy_z",
        "news_w2",
        "attention_ratio_w2",
        "ctx_earnings_w2",
        "n_stories_w2",
        "dup_count",
        "tag_type",
        "sentiment_direction",
        "filter_score_w0",
        "third_party_ok",
        "material",
        "clean_5",
        "r_cc",
        "adj_close",
    ],
)
@pytest.mark.parametrize("block", ["company", "market", "attention", "news"])
def test_d0_call_a_refuses_late_columns(block: str, column: str) -> None:
    with pytest.raises(pit.PITError):
        validate_spec(_with(block, column))


def test_z_cc_and_z_id_are_post_in_the_registry() -> None:
    """The mutation "register z_cc as t_minus_1" turns this and the test above red."""
    assert REG.kind("z_cc") == "post"
    assert REG.kind("z_id") == "post"
    with pytest.raises(pit.PITError):
        pit.check_inputs(["z_cc"], "D0")


def test_d0_context_columns_are_visible_at_d0() -> None:
    spec = make_spec("t", "A", "W0", "E4", True, CFG)
    for cols in spec.blocks.values():
        assert all(REG.kind(c) in {"static", "t_minus_1", "w0"} for c in cols), cols


@pytest.mark.parametrize("column", ["z_cc", "y2", "e5", "ar_cc", "g_d1", "raw_close"])
def test_call_b_reaction_accepts_the_d2_reaction_only(column: str) -> None:
    with pytest.raises(pit.PITError):
        validate_spec(_with("reaction_so_far", column, call="B", window="W2"))


def test_call_b_reaction_columns_are_d2_reaction() -> None:
    for e in ENCODINGS:
        spec = make_spec("t", "B", "W2", e, True, CFG)  # type: ignore[arg-type]
        assert {REG.kind(c) for c in spec.blocks["reaction_so_far"]} == {"d2_reaction"}


@pytest.mark.parametrize("column", ["g_d2", "react_volume_multiple", "react_r_spy_cc"])
def test_reaction_columns_stay_out_of_other_blocks(column: str) -> None:
    for call in ("A", "B"):
        with pytest.raises(pit.PITError, match="reaction"):
            validate_spec(_with("company", column, call=call, window="W2"))


def test_call_a_has_no_reaction_block() -> None:
    spec = make_spec("t", "A", "W2", "E3", True, CFG)
    bad = replace(spec, blocks={**spec.blocks, "reaction_so_far": ("g_d2",)})
    with pytest.raises(pit.PITError, match="Call B"):
        validate_spec(bad)
    with pytest.raises(ctx.ContextError):
        ctx.block_columns("reaction_so_far", "W0", "E3", CFG)


def test_build_validates_before_reading_rows() -> None:
    with pytest.raises(pit.PITError):
        build_event_states(pd.DataFrame(), _with("company", "z_cc"), None, CFG)  # type: ignore[arg-type]


def test_call_b_refuses_test_period_events() -> None:
    ev = pd.DataFrame({"event_id": ["W2:1:2026-02-02"], "split": ["test"], "session": [date(2026, 2, 2)]})
    with pytest.raises(StatesError, match="test-period"):
        build_event_states(ev, make_spec("callB", "B", "W2", "E3", True, CFG), None, CFG)  # type: ignore[arg-type]


def test_renderer_reads_declared_columns_only() -> None:
    row = ctx.Row({"a": 1.0, "b": 2.0}, ["a"])
    assert row["a"] == 1.0
    with pytest.raises(ctx.ContextError):
        row["b"]


# --- planted shocks --------------------------------------------------------------------------------


def test_history_stats_exclude_the_scored_value() -> None:
    x = np.r_[np.random.default_rng(0).normal(0, 1, 300), 50.0, 0.1]
    st = ctx.history_stats(x, 252, 126)
    head = ctx.history_stats(x[:301], 252, 126)
    assert np.array_equal(st.sigma[:301], head.sigma, equal_nan=True)  # later values change nothing earlier
    h = x[48:300]
    assert st.sigma[300] == pytest.approx(1.4826 * np.median(np.abs(h - np.median(h))))  # x[300] excluded
    assert st.pct_abs[300] == 100.0
    assert np.isnan(st.sigma[125]) and not np.isnan(st.sigma[126])  # 126 observations needed


def _market_frames(shock_day: int | None) -> pd.DataFrame:
    sessions = calendar.sessions(date(2023, 1, 3), date(2025, 6, 30))
    rng = np.random.default_rng(7)
    spy = 400 * np.cumprod(1 + rng.normal(0, 0.01, len(sessions)))
    if shock_day is not None:
        spy[shock_day:] *= 1.5  # a +50% day (about +50 sigma) on session index shock_day
    mp = pd.concat(
        [
            pd.DataFrame(
                {
                    "symbol": s,
                    "date": pd.to_datetime(sessions),
                    "close": spy if s == "SPY" else 20.0 + 0 * spy,
                }
            )
            for s in ("SPY", "^VIX", "DX-Y.NYB", "CL=F")
        ]
    )
    fred = pd.concat(
        [
            pd.DataFrame(
                {
                    "series_id": s,
                    "date": pd.to_datetime(sessions),
                    "value": 4.0 + rng.normal(0, 0.05, len(sessions)),
                }
            )
            for s in ("DGS10", "BAMLH0A0HYM2")
        ]
    )
    levels = ctx.series_levels(mp, fred, sessions, CFG)
    return ctx.market_context(levels, sessions, CFG)


def test_market_context_ignores_day_t() -> None:
    t = 500
    base, shocked = _market_frames(None), _market_frames(t)
    cols = [c for c in base.columns if c.startswith("mkt_stock_market") or c.startswith("mkt_spy")]
    cols = [c for c in cols if c != "mkt_stock_market_sigma_same"]  # history through prev(s), checked below
    pd.testing.assert_frame_equal(base.loc[:t, cols], shocked.loc[:t, cols])
    assert shocked.loc[t + 1, "mkt_stock_market_z"] > 20
    assert base.loc[t, "mkt_stock_market_sigma_same"] == shocked.loc[t, "mkt_stock_market_sigma_same"]
    assert base.loc[t + 1, "mkt_stock_market_sigma_same"] != shocked.loc[t + 1, "mkt_stock_market_sigma_same"]


def _company_frames(shock_day: int | None) -> pd.DataFrame:
    sessions = calendar.sessions(date(2023, 1, 3), date(2025, 6, 30))
    rng = np.random.default_rng(3)
    n = len(sessions)
    panel = pd.DataFrame({"session": sessions, "symbol_id": 1, "sigma_cc": 0.01 + rng.uniform(0, 0.005, n)})
    for k in CFG.context.perf_windows.values():
        panel[f"z_m{k}"] = rng.normal(0, 1, n)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    if shock_day is not None:
        close[shock_day:] *= 1.5
    adj = pd.DataFrame({"session": sessions, "symbol_id": 1, "adj_close": close})
    return ctx.company_context(panel, adj, sessions, CFG)


def test_company_context_ignores_day_t() -> None:
    t = 400
    base, shocked = _company_frames(None), _company_frames(t)
    pd.testing.assert_frame_equal(base.iloc[: t + 1], shocked.iloc[: t + 1])
    assert shocked.loc[t + 1, "ctx_ret_m5"] > 0.3


def test_eps_revision_uses_snapshots_before_the_session() -> None:
    cb = load_codebook()
    s = date(2025, 3, 3)
    est = pd.DataFrame(
        {
            "company_id": 1,
            "period_end": [date(2025, 12, 31)] * 3,
            "as_of_date": [date(2025, 1, 15), date(2025, 2, 20), s],
            "mean": [2.0, 2.0, 3.0],
        }
    )
    keys = pd.DataFrame({"company_id": [1, 1], "session": [s, date(2025, 3, 4)]})
    out = ctx.eps_revision(keys, est, 30, cb).set_index("session")
    assert out.loc[s, "ctx_eps_fy1_now"] == 2.0  # the snapshot dated on the session is not yet usable
    assert out.loc[date(2025, 3, 4), "ctx_eps_fy1_now"] == 3.0
    assert out.loc[s, "ctx_eps_revision"] == 0.0


def test_fy1_is_the_first_period_ending_after_the_session() -> None:
    cb = load_codebook()
    est = pd.DataFrame(
        {
            "company_id": 1,
            "period_end": [date(2024, 12, 31), date(2025, 12, 31)],
            "as_of_date": [date(2024, 12, 1)] * 2,
            "mean": [1.0, 5.0],
        }
    )
    out = ctx.eps_revision(pd.DataFrame({"company_id": [1], "session": [date(2025, 1, 6)]}), est, 30, cb)
    assert out["ctx_eps_fy1_now"].iloc[0] == 5.0


def test_earnings_window_edges() -> None:
    s = date(2025, 7, 15)
    prev, nxt = calendar.prev_session(s), calendar.next_session(s)
    earn = pd.DataFrame(
        {"ticker": "X", "earnings_ts": pd.to_datetime([f"{prev} 16:00", f"{s} 10:00", f"{s} 16:00"])}
    )
    keys = pd.DataFrame({"company_id": [1, 1, 1], "session": [prev, s, nxt]})
    f = ctx.earnings_flags(keys, earn, {"X": 1}, "America/New_York").set_index("session")
    assert bool(f.loc[s, "ctx_earnings_w0"])  # the 16:00 report of prev(s) falls in W0(s)
    assert bool(f.loc[s, "ctx_earnings_w2"])  # and so does the 10:00 one in W2(s)
    assert bool(f.loc[nxt, "ctx_earnings_w0"])  # the 16:00 report of s belongs to the next session
    assert not bool(f.loc[prev, "ctx_earnings_w2"])  # not to W2(prev): a stamp at the close is after it


def test_cpi_release_dates_skip_re_vintages() -> None:
    from newsaction.states.macro import cpi_release_dates

    v = pd.DataFrame(
        {
            "series_id": "CPIAUCSL",
            "date": pd.to_datetime(["2023-12-01", "2023-12-01", "2024-01-01"]),
            "realtime_start": pd.to_datetime(["2024-01-11", "2024-02-09", "2024-02-13"]),
        }
    )
    assert cpi_release_dates(v, "CPIAUCSL") == {date(2024, 1, 11), date(2024, 2, 13)}


def test_macro_calendar() -> None:
    from newsaction.states.macro import load_macro

    cal = load_macro()
    assert len(cal.fomc_dates) == 24 and date(2025, 12, 10) in cal.fomc_dates
    assert date(2025, 8, 22) not in cal.fomc_dates  # a notation vote, not a statement
    assert cal.words(False, False) == "none scheduled"
    assert cal.words(True, True).count(";") == 1


def test_articles_must_be_third_party_ok() -> None:
    """CLAUDE.md D15: a state is never built from an article that is not third-party OK."""
    from newsaction.states.build import Inputs, news_items

    t = pd.Timestamp("2025-07-15 11:00", tz="UTC")
    item = {"id": "x", "title": "t", "snippet": "s", "source_class_domain": "other", "t_avail": t}
    empty = pd.DataFrame()
    ok = Inputs(empty, empty, empty, masked={"x": ("t", "s")}, third_party={"x": True})
    assert news_items([item], date(2025, 7, 15), True, ok, "W0")[1] == ["x"]
    for flag in ({"x": False}, {}):
        bad = Inputs(empty, empty, empty, masked={"x": ("t", "s")}, third_party=flag)
        with pytest.raises(StatesError, match="third-party"):
            news_items([item], date(2025, 7, 15), True, bad, "W0")
