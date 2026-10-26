"""PREREG §15 NA-04 row 6 (revision 3): move explainers and TradingView reposts are in no state.

"Why … Stock Is Up Today" articles and StockStory's "What Happened? Shares of …" template explain the
session's move, and some are stamped before it (the third verification: DGX, stamped 2025-07-21 09:01 ET,
describing the move of 07-22). TradingView reposts carry batch timestamps that precede their content (DGX's
earnings summary had the same stamp). ``build.excluded_ids`` finds both in NA-02's raw title / snippet and the
domain, ``news_items`` leaves them out of every state, and the built files must not carry explainer text. The
mutations "skip removed" and "patterns never match" turn these tests red.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pandas as pd
import pytest

from newsaction import io
from newsaction.paths import ROOT
from newsaction.states import load_states_config
from newsaction.states.build import Inputs, excluded_ids, news_items

EXCLUDED = (  # (raw title, raw snippet[, domain])
    ("Why Quest (DGX) Stock Is Up Today", ""),
    ("Here's Why Intel Stock Is Gaining Today", ""),
    ("Why Humana (HUM) Shares Are Falling Today", ""),
    (
        "Intel (INTC) Stock Trades Up, Here Is Why",
        "What Happened? Shares of chipmaker Intel jumped 4.1% in the",
    ),
    (
        "Why Is Molson Coors (TAP) Stock Soaring Today",
        "What Happened?Shares of beer company Molson Coors jumped",
    ),
    (
        "Semiconductor Stocks Q2 Teardown",
        "Recap. What Happened? A number of stocks fell in the afternoon session",
    ),
    ("Quest Diagnostics Inc reports results for the quarter ended June 30", "", "tradingview.com"),
    ("Les résultats de Quest", "", "fr.tradingview.com"),
)
KEPT = (
    ("Microsoft hits $4 trillion", "What Happened: As of Thursday, Microsoft's current valuation..."),
    ("Why Apple stock could rally in 2026", ""),
    ("Why Nvidia's new chip matters", "Shares of Nvidia rose 2% in early trading."),
    ("Today's top movers: stocks to watch", ""),
    ("Quest Diagnostics Inc reports results for the quarter ended June 30", "", "reuters.com"),
    ("A chart idea", "", "nottradingview.com"),
)
STATE_FILES = (
    "states/callA_d0_E3.parquet",
    "states/callA_d2_E3.parquet",
    "states/callB_d2_E3.parquet",
    "states/market_E3.parquet",
    "states/samples/unmasked.parquet",
)


def frame(rows: tuple[tuple[str, ...], ...]) -> pd.DataFrame:
    full = [(f"a{i}", r[0], r[1], r[2] if len(r) > 2 else "finance.yahoo.com") for i, r in enumerate(rows)]
    return pd.DataFrame(full, columns=["id", "title", "snippet", "domain"])


def test_excluded_ids_golden_cases() -> None:
    cfg = load_states_config()
    assert excluded_ids(frame(EXCLUDED), cfg) == frozenset(f"a{i}" for i in range(len(EXCLUDED)))
    assert excluded_ids(frame(KEPT), cfg) == frozenset()


def test_news_items_leaves_out_explainers() -> None:
    t = pd.Timestamp("2025-07-15 11:00", tz="UTC")
    items = [
        {"id": i, "title": "t", "snippet": "s", "source_class_domain": "other", "t_avail": t}
        for i in ("x", "y")
    ]
    empty = pd.DataFrame()
    masked = {"x": ("t", "s"), "y": ("u", "v")}
    inp = Inputs(
        empty, empty, empty, masked=masked, third_party={"x": True, "y": True}, excluded=frozenset({"y"})
    )
    for is_masked in (True, False):  # the masked states and the unmasked twin
        news, ids = news_items(items, date(2025, 7, 15), is_masked, inp)
        assert ids == ["x"] and len(news) == 1


def test_built_states_carry_no_explainer_text() -> None:
    if not all((ROOT / "work" / rel).is_file() for rel in STATE_FILES):
        pytest.skip("NA-04 state files are absent (run the build)")
    session_move = re.compile(r"\d%\s+in\s+the\s+(?:morning|afternoon)\s+session")
    # StockStory's template, or what is left of it once the move sentence is scrubbed ("What Happened?")
    stockstory = re.compile(r"What Happened\?\s*(?:Shares of|A number of|$)")
    for rel in STATE_FILES:
        df = io.read_parquet(rel, columns=["window", "state_json"])
        for js, window in zip(df["state_json"], df["window"], strict=True):
            for item in json.loads(js)["news"]:
                assert not stockstory.match(item["snippet"]), (rel, item)
                if window == "W0":
                    assert not session_move.search(item["headline"] + " " + item["snippet"]), (rel, item)
    built = json.loads((ROOT / "artifacts" / "NA-04" / "build_states.json").read_text(encoding="utf-8"))
    assert built["callA_d0_E3"]["articles_excluded"] > 0 and built["callA_d2_E3"]["articles_excluded"] > 0
