"""PRD NA-02 AC2: ticker parsing, renames, share classes, validity ranges, zero collisions.

Verifier mutation: map by the current ATOM ticker only (drop the history and alias rows from
``mapping.ticker_map``) -> test_block_sq_and_xyz_map_to_one_company RED.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pyarrow.parquet as pq
import pytest

from newsaction.news import Alias, MappingConfig, load_news_config, mapping
from newsaction.paths import ROOT

BLOCK = 1602
HEALTHPEAK = 440


def _utc(*stamps: str) -> pd.Series:
    return pd.Series(pd.to_datetime(list(stamps), utc=True))


@pytest.fixture(scope="module")
def tmap(snapshot: Callable[[str], pd.DataFrame]) -> pd.DataFrame:
    return mapping.ticker_map(snapshot("symbols"), snapshot("symbol_tickers"))


def _resolve(tmap: pd.DataFrame, raw: list[str], stamps: list[str]) -> list[object]:
    parsed = mapping.parse_tickers(pd.Series(raw))
    return mapping.resolve(parsed["ticker_norm"], _utc(*stamps), tmap).tolist()


def test_parse_and_normalize() -> None:
    p = mapping.parse_tickers(
        pd.Series(
            [
                "NYSE:BRK.B",
                "NYSE:BRK-B",
                "NYSE:brk/b",
                "^GSPC",
                "INDEXFTSE:UKX",
                "NYMEX:CL",
                "LSE:BA",
                "DX-Y.NYB",
                "CCC:BTC-USD",
                "NASDAQ:AAPL",
                "US10Y",
            ]
        )
    )
    assert p["ticker_norm"].tolist()[:3] == ["BRK-B", "BRK-B", "BRK-B"]
    assert p["ticker_class"].tolist() == [
        "us_equity",
        "us_equity",
        "us_equity",
        "non_equity",
        "non_equity",
        "other",
        "other",
        "non_equity",
        "non_equity",
        "us_equity",
        "non_equity",
    ]


def test_block_sq_and_xyz_map_to_one_company(tmap: pd.DataFrame, companies: pd.DataFrame) -> None:
    sid = _resolve(
        tmap,
        ["NYSE:SQ", "NYSE:SQ", "NYSE:XYZ"],
        ["2024-03-04T14:00:00Z", "2025-01-03T21:00:02Z", "2025-08-04T13:00:00Z"],
    )
    assert sid == [BLOCK, BLOCK, BLOCK]
    cid = mapping.attach_company(pd.Series(sid, dtype="Int64"), companies).tolist()
    assert len(set(cid)) == 1


def test_validity_ranges(tmap: pd.DataFrame) -> None:
    # SQ is Block's ticker until 2025-01-20; XYZ from 2025-01-21; NYSE:DOC is Healthpeak from 2024-03-01
    assert _resolve(tmap, ["NYSE:SQ", "NYSE:XYZ"], ["2025-02-03T15:00:00Z", "2024-06-03T15:00:00Z"]) == [
        pd.NA,
        pd.NA,
    ]
    assert _resolve(tmap, ["NYSE:DOC", "NYSE:DOC"], ["2023-11-02T10:23:00Z", "2024-06-03T15:00:00Z"]) == [
        pd.NA,
        HEALTHPEAK,
    ]


def test_atom_history_and_classes(tmap: pd.DataFrame, snapshot: Callable[[str], pd.DataFrame]) -> None:
    sym = snapshot("symbols").set_index("ticker")["symbol_id"]
    got = _resolve(
        tmap,
        ["NYSE:BK", "NYSE:MMC", "NYSE:FI", "NASDAQ:PARA", "NASDAQ:PARAA", "NYSE:BRK.B"],
        ["2025-06-02T15:00:00Z"] * 6,
    )
    assert got == [sym["BNY"], sym["MRSH"], sym["FISV"], sym["PSKY"], sym["PSKY"], sym["BRK-B"]]


def test_exchange_rule_rejects_non_us_homonyms(tmap: pd.DataFrame) -> None:
    raw = pd.Series(["NYMEX:CL", "LSE:BA", "NYSE:CL"])
    p = mapping.parse_tickers(raw)
    us = p["ticker_class"] == mapping.US_EQUITY
    assert us.tolist() == [False, False, True]
    sid = mapping.resolve(p.loc[us, "ticker_norm"], _utc("2025-06-02T15:00:00Z"), tmap)
    assert sid.notna().all()


def test_real_map_has_no_collisions(tmap: pd.DataFrame) -> None:
    mapping.check_collisions(tmap)
    assert not tmap.duplicated(["ticker", "symbol_id"]).any()


def test_collision_detection() -> None:
    open_from, open_to = pd.Timestamp("1900-01-01", tz="UTC"), pd.Timestamp("2200-01-01", tz="UTC")
    bad = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "symbol_id": [1, 2],
            "valid_from": [open_from] * 2,
            "valid_to": [open_to] * 2,
            "source": ["x", "y"],
        }
    )
    with pytest.raises(mapping.MappingError, match="collision"):
        mapping.check_collisions(bad)
    ok = bad.assign(
        valid_to=[pd.Timestamp("2020-01-01", tz="UTC"), open_to],
        valid_from=[open_from, pd.Timestamp("2020-01-01", tz="UTC")],
    )
    mapping.check_collisions(ok)
    with pytest.raises(mapping.MappingError, match="match two symbols"):
        mapping.resolve(pd.Series(["AAA"]), _utc("2021-01-01T00:00:00Z"), bad)


def test_alias_to_unknown_symbol_is_refused(snapshot: Callable[[str], pd.DataFrame]) -> None:
    cfg = load_news_config().mapping
    broken = MappingConfig(
        us_exchanges=cfg.us_exchanges,
        non_equity_prefixes=cfg.non_equity_prefixes,
        aliases=(
            Alias(
                ticker="ZZZZ", symbol_id=99_999_999, valid_from=None, valid_to=None, kind="rename", note="x"
            ),
        ),
    )
    with pytest.raises(mapping.MappingError, match="not in symbols"):
        mapping.ticker_map(snapshot("symbols"), snapshot("symbol_tickers"), broken)


def test_real_sq_rows_of_the_corpus_map_to_block(tmap: pd.DataFrame) -> None:
    """Every NYSE:SQ article in Data/news_2024 resolves to Block (the corpus has no NYSE:XYZ rows)."""
    path = ROOT / "Data" / "news_2024.parquet"
    if not path.is_file():
        pytest.skip("Data/news_2024.parquet absent")
    t = pq.read_table(path, columns=["ticker", "date"], filters=[("ticker", "=", "NYSE:SQ")]).to_pandas()
    assert len(t) > 1000
    ts = pd.Series(pd.to_datetime(t["date"], unit="s", utc=True))
    sid = mapping.resolve(mapping.parse_tickers(t["ticker"])["ticker_norm"], ts, tmap)
    assert set(sid.dropna()) == {BLOCK} and sid.notna().all()


def test_member_mask_uses_company_membership() -> None:
    from datetime import date

    pairs = pd.DataFrame({"session": [date(2025, 6, 2)], "company_id": [7]})
    got = mapping.member_mask(
        pd.Series([date(2025, 6, 2), date(2025, 6, 3), None]), pd.Series([7, 7, 7], dtype="Int64"), pairs
    )
    assert got.tolist() == [True, False, False]
