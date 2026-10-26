"""PREREG §15 NA-04 rows 6 and 8: explainers, TradingView reposts and non-English articles are in no state.

"Why … Stock Is Up Today" articles and StockStory's "What Happened? Shares of …" template explain the
session's move, and some are stamped before it (the third verification: DGX, stamped 2025-07-21 09:01 ET,
describing the move of 07-22). TradingView reposts carry batch timestamps that precede their content (DGX's
earnings summary had the same stamp). ``build.excluded_ids`` finds both in NA-02's raw title / snippet and the
domain, ``news_items`` leaves them out of every state, and the built files must not carry explainer text. The
mutations "skip removed" and "patterns never match" turn these tests red.

Revision 4 (operator decision B): non-English articles go too (``build.non_english``), because the masker
and the price-talk scrubbers are English-only; the fourth verification found "dispararam mais de 27% ...
pré-mercado" and "Das Papier kostete zuletzt 72,99 US-Dollar" in Call A states. Golden cases in eleven
languages, English look-alikes ("Los Angeles", "DuPont de Nemours", Deere's ticker DE), and no built state
carries two characters of a non-Latin script (exact: masking only removes text).
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
from newsaction.states.build import Inputs, excluded_ids, news_items, non_english

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
    ("Why Micron Technology Rallied Today", ""),  # revision 4: a move word, no "stock"
    ("Why CoreWeave Rocketed as High as 26% Today", ""),
    ("Why Teradyne Zoomed 4% Higher Today", ""),
)
KEPT = (
    ("Microsoft hits $4 trillion", "What Happened: As of Thursday, Microsoft's current valuation..."),
    ("Why Apple stock could rally in 2026", ""),
    ("Why Nvidia's new chip matters", "Shares of Nvidia rose 2% in early trading."),
    ("Today's top movers: stocks to watch", ""),
    ("Quest Diagnostics Inc reports results for the quarter ended June 30", "", "reuters.com"),
    ("A chart idea", "", "nottradingview.com"),
    ("Here's Why We Think F5 (NASDAQ:FFIV) Might Deserve Your Attention Today", ""),
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


NON_ENGLISH = (  # (raw title, raw snippet): the fourth verification's cases and one per language
    (
        "Thoma Bravo avalia aquisição da Dayforce",
        "As ações da Dayforce Inc. dispararam mais de 27% no pré-mercado",
    ),
    (
        "Omnicom-Aktie im Minus",
        "Im Minus liegt gegenwärtig die Aktie. Das Papier kostete zuletzt 72,99 US-Dollar.",
    ),
    (
        "Acciones de Global Payments suben tras informes",
        "Las acciones subieron más del 6% en las operaciones previas",
    ),
    (
        "Emerson Electric Co. : Citigroup à l'achat",
        "L'objectif de cours est modifié à la baisse et passe de 132 USD",
    ),
    ("APPLE INC: JP Morgan è per il Buy", "Il prezzo obiettivo viene portato a 255 USD dal precedente"),
    (
        "Aflac Incorporated: Barclays ancora valutazione negativa",
        "Barclays ribadisce la valutazione Sell. In precedenza posizionato a 96 USD, il prezzo obiettivo",
    ),
    ("Intel-aandeel stijgt 3,5% na ontmoeting", "De aandelen van Frontier zijn dinsdag met 15% gestegen"),
    ("Visa annoncerer investering i Mynt", "Visa har netop annonceret et udvidet partnerskab i hele Europa"),
    (
        "Kaita Groupi võlakirjad",
        "Nasdaq Balti börsid teatab, et täna algas kauplemine ning see on oluline",
    ),
    (
        "Firma UPS ogłasza kwartalną dywidendę",
        "Firma UPS ogłosiła regularną kwartalną dywidendę za czwarty kwartał",
    ),
    ("Akcie těžařů zlata lámou rekordy", "Globální finanční trhy v roce zažívají výrazný růst"),
    ("苹果股价下跌2.1%", "苹果公司周二股价下跌"),
    ("보잉, 중국으로 항공기 인도 재개", "보잉 주가는 3.32% 상승했다"),
)
ENGLISH = (
    (
        "Flight From Detroit To Los Angeles Makes Emergency Landing",
        "A flight to Los Angeles diverted on Monday.",
    ),
    (
        "DuPont de Nemours Stock: Earnings Release Scheduled for Today",
        "DuPont de Nemours will report results.",
    ),
    ("Deere (DE) Q4 Earnings Miss Estimates", "Deere & Co (DE) DE earnings forecast"),
    (
        "Estée Lauder names a new chief executive",
        "The Estée Lauder Companies said on Monday that it appointed a CEO.",
    ),
    ("Nestlé and Société Générale in talks", "Nestlé said the deal would close next year."),
    ("Guillermo del Toro's Frankenstein review", "Frankenstein is a powerful, visceral film from del Toro."),
    ("Las Vegas Sands beats estimates", "Las Vegas Sands reported revenue of $3 billion."),
    ("Deere (DE), Estée Lauder (EL) and Dana (DAN) report", ""),  # tickers are not "de", "el", "dan"
    ("Hilton Expands Luxury Portfolio: Conrad Los Cabos, Del Mar", ""),  # a place name is not Spanish text
)


@pytest.mark.parametrize(("title", "snippet"), NON_ENGLISH)
def test_non_english_articles_are_excluded(title: str, snippet: str) -> None:
    cfg = load_states_config()
    assert non_english(f"{title} {snippet}", cfg.news_exclusion.non_english)
    assert excluded_ids(frame(((title, snippet),)), cfg) == frozenset({"a0"})


@pytest.mark.parametrize(("title", "snippet"), ENGLISH)
def test_english_look_alikes_are_kept(title: str, snippet: str) -> None:
    cfg = load_states_config()
    assert not non_english(f"{title} {snippet}", cfg.news_exclusion.non_english)
    assert excluded_ids(frame(((title, snippet),)), cfg) == frozenset()


def test_built_states_carry_no_non_latin_script() -> None:
    """Exact: an article whose raw text has two characters of a non-Latin script is excluded, and masking only
    removes text, so no news item of a built state has two."""
    if not all((ROOT / "work" / rel).is_file() for rel in STATE_FILES):
        pytest.skip("NA-04 state files are absent (run the build)")
    script = re.compile(load_states_config().news_exclusion.non_english.script)
    for rel in STATE_FILES:
        df = io.read_parquet(rel, columns=["state_json"])
        for js in df["state_json"]:
            for item in json.loads(js)["news"]:
                assert len(script.findall(item["headline"] + " " + item["snippet"])) < 2, (rel, item)
    built = json.loads((ROOT / "artifacts" / "NA-04" / "build_states.json").read_text(encoding="utf-8"))
    assert built["callA_d0_E3"]["articles_excluded_non_english"] > 0
