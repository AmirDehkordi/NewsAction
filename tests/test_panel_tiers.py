"""Companies, market caps and monthly tiers (PREREG §3.2-3.3; PRD NA-01 S5, AC5).

The split goldens recompute share counts through ``tiers.ShareBook`` from the snapshot (not from
the stored artifact), so removing the split adjustment turns them red.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.panel import adjust, tiers


def test_issuer_names_group_share_classes() -> None:
    symbols = pd.DataFrame(
        {
            "symbol_id": [649, 650, 1, 2],
            "ticker": ["GOOG", "GOOGL", "FOO", "BAR"],
            "name": ["Alphabet Inc. (Class C)", "Alphabet Inc. (Class A)", "Foo Corp", "Bar Corp"],
            "cik": [None, None, "0001", "0001"],
        }
    )
    c = tiers.companies(symbols).set_index("ticker")
    assert c.loc["GOOG", "company_id"] == c.loc["GOOGL", "company_id"] == 649
    assert c.loc["FOO", "company_id"] == c.loc["BAR", "company_id"] == 1  # same CIK
    assert c.loc["GOOG", "grouping"] == "name" and c.loc["FOO", "grouping"] == "cik"


def test_month_ranking_sessions_use_the_previous_month_end() -> None:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in calendar.sessions(date(2024, 5, 28), date(2024, 7, 3))])
    r = tiers.month_ranking_sessions(idx)
    assert r["2024-06"] == pd.Timestamp("2024-05-31") and r["2024-07"] == pd.Timestamp("2024-06-28")


def _book(restated: bool, spinoff: bool = False) -> tiers.ShareBook:
    shares = pd.DataFrame(
        {
            "symbol_id": [1, 1],
            "period_end": [date(2024, 3, 31), date(2024, 6, 30)],
            "period_type": ["Q", "Q"],
            "value": [1000.0, 1000.0] if restated else [100.0, 1000.0],
            "known_from": pd.to_datetime(["2024-05-15", "2024-08-14"], utc=True),
            "ingested_at": pd.to_datetime(["2026-07-31", "2026-07-31"], utc=True),
        }
    )
    splits = pd.DataFrame(
        {"symbol_id": [1], "ex_session": [pd.Timestamp("2024-06-10")], "split_ratio": [10.0]}
    )
    basis = tiers.share_basis(shares, splits)
    assert bool(basis["restated"].item()) is restated
    if spinoff:  # a spin-off is not a split row of kind "split"; it never enters the basis
        basis = basis.iloc[:0]
    return tiers.ShareBook(shares, basis)


@pytest.mark.parametrize("restated", [True, False])
def test_shares_follow_the_ranking_session_basis(restated: bool) -> None:
    book = _book(restated)
    known = lambda d: pd.Timestamp(d, tz="UTC")  # noqa: E731
    before, _ = book.at(1, pd.Timestamp("2024-05-31"), known("2024-05-31 20:00"))
    after, _ = book.at(1, pd.Timestamp("2024-06-28"), known("2024-06-28 20:00"))
    assert before == pytest.approx(100.0) and after == pytest.approx(1000.0)


def test_unknown_shares_are_not_used() -> None:
    v, pe = _book(True).at(1, pd.Timestamp("2024-04-30"), pd.Timestamp("2024-04-30 20:00", tz="UTC"))
    assert np.isnan(v) and pe is None


def test_ranks_ties_by_company_id_and_tier_sizes() -> None:
    vals = pd.Series([5.0, 5.0, 4.0, np.nan], index=[10, 11, 12, 13])
    ranks = tiers.assign_ranks(vals, [9, 3, 1, 2])
    assert ranks.tolist()[:3] == [2.0, 1.0, 3.0] and np.isnan(ranks.iloc[3])
    df = pd.DataFrame(
        {
            "company_id": np.arange(300),
            "member_at_ranking": [True] * 290 + [False] * 10,
            "cap_usd": np.linspace(1e12, 1e9, 300),
            "adv63_usd": np.linspace(1e9, 1e6, 300),
        }
    )
    out = tiers._rank_month(df)
    ranked = out[out["tier_source"] == "ranked"]
    assert (ranked["tier"] == tiers.TOP).sum() == 100 and (ranked["tier"] == tiers.MID).sum() == 150
    assert out.loc[out["company_id"] == 295, "tier"].item() == tiers.REST  # a joiner below the rank-250 cap


def test_dv_fallback_imputes_from_nearest_dollar_volume() -> None:
    cap = pd.Series([3e11, 2e11, np.nan, 1e11])
    adv = pd.Series([3e9, 2e9, 2.1e9, 1e9])
    assert tiers.impute_cap_from_dv(cap, adv).iloc[2] == 2e11


# --- integration (AC5) -------------------------------------------------------------------------


def test_ac5_exactly_100_top_and_150_mid_each_month(tiers_monthly: pd.DataFrame) -> None:
    ranked = tiers_monthly[tiers_monthly["tier_source"] == "ranked"]
    sizes = ranked.groupby("month")["tier"].value_counts().unstack(fill_value=0)
    assert (sizes[tiers.TOP] == 100).all() and (sizes[tiers.MID] == 150).all()
    assert ranked.groupby("month")["rank"].apply(lambda r: sorted(r) == list(range(1, len(r) + 1))).all()
    assert len(sizes) == 37  # 2023-07 .. 2026-07


def _tier(tm: pd.DataFrame, companies: pd.DataFrame, ticker: str, month: str) -> str:
    cid = int(companies.loc[companies["ticker"] == ticker, "company_id"].item())
    return str(tm.loc[(tm["company_id"] == cid) & (tm["month"] == month), "tier"].item())


def test_ac5_nvda_top100_around_its_split(tiers_monthly: pd.DataFrame, companies: pd.DataFrame) -> None:
    for month in ("2024-06", "2024-07", "2024-08"):
        assert _tier(tiers_monthly, companies, "NVDA", month) == tiers.TOP


@pytest.mark.parametrize(
    ("ticker", "before", "after"),
    [
        ("AVGO", "2024-07", "2024-08"),
        ("CMG", "2024-06", "2024-07"),
        ("WMT", "2024-02", "2024-03"),
        ("NVDA", "2024-06", "2024-07"),
    ],
)
def test_ac5_tiers_stable_across_splits(
    tiers_monthly: pd.DataFrame, companies: pd.DataFrame, ticker: str, before: str, after: str
) -> None:
    assert _tier(tiers_monthly, companies, ticker, before) == _tier(tiers_monthly, companies, ticker, after)


GOLDEN_CAPS = {  # (ticker, pre-split ranking session): plausible market-cap band in USD
    ("NVDA", "2024-05-31"): (2.0e12, 3.5e12),
    ("CMG", "2024-05-31"): (6.0e10, 1.2e11),
    ("AVGO", "2024-06-28"): (5.0e11, 1.0e12),
    ("WMT", "2024-01-31"): (3.5e11, 5.5e11),
    ("GE", "2024-02-29"): (1.7e11, 2.2e11),  # before the 2024-04-02 GE Vernova spin-off (a pseudo-split row)
}


@pytest.fixture(scope="module")
def share_book(snapshot: Callable[[str], pd.DataFrame]) -> tiers.ShareBook:
    return tiers.share_book(snapshot("shares_basic"), adjust.classify_actions(snapshot("corporate_actions")))


@pytest.mark.parametrize(("ticker", "session"), sorted(GOLDEN_CAPS))
def test_ac5_split_goldens_through_the_share_code(
    share_book: tiers.ShareBook, snapshot: Callable[[str], pd.DataFrame], ticker: str, session: str
) -> None:
    syms = snapshot("symbols")
    sid = int(syms.loc[syms["ticker"] == ticker, "symbol_id"].item())
    px = snapshot("prices_raw")
    m = pd.Timestamp(session)
    close = float(px.loc[(px["symbol_id"] == sid) & (pd.to_datetime(px["trade_date"]) == m), "close"].item())
    shares, _ = share_book.at(sid, m, calendar.close_utc(m.date()))
    lo, hi = GOLDEN_CAPS[(ticker, session)]
    assert lo < close * shares * 1e6 < hi


@pytest.mark.parametrize("ticker", ["NVDA", "CMG", "AVGO", "WMT"])
def test_ac5_cap_continuous_across_the_split(
    tiers_monthly: pd.DataFrame, companies: pd.DataFrame, ticker: str
) -> None:
    """Across the split month, the cap moves like the split-adjusted price (shares barely change)."""
    cid = int(companies.loc[companies["ticker"] == ticker, "company_id"].item())
    t = tiers_monthly[tiers_monthly["company_id"] == cid].set_index("month").sort_index()
    log_cap = np.log(t["cap_usd"]).diff().abs()
    assert log_cap.loc["2024-01":"2024-12"].max() < np.log(1.6)  # a split error is >= log 2


def test_fallback_count_reported(tiers_monthly: pd.DataFrame) -> None:
    ranked = tiers_monthly[tiers_monthly["tier_source"] == "ranked"]
    per_month = ranked.groupby("month")["fallback_dv"].sum()
    assert per_month.max() <= 25, per_month.to_dict()
