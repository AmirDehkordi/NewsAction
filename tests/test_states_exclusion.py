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

Revision 6 (row 10; the sixth verification): running market stories are in no W0 state. Live blogs and running
market reports keep their first vendor stamp while their text is the latest version ("The S&P 500 ended
Tuesday's choppy session" stamped 05:57 ET that Tuesday), so in W0 they carry the session's own cash-market
outcome; W2 ends at the close and keeps them. ``build.running_story`` has five rules; every rule has a golden
case that only it catches, the look-alikes stay (pre-open pieces, schedules, Asian closes, European mornings,
recaps of the previous session, companies named like an index), and the built W0 files carry no live format.
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
from newsaction.states.build import (
    Inputs,
    excluded_ids,
    news_items,
    non_english,
    running_story,
    running_story_ids,
    skipped,
    story_rule,
)

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
        news, ids = news_items(items, date(2025, 7, 15), is_masked, inp, "W2")
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


# --- revision 6: running market stories (PREREG §15 NA-04 row 10) -------------------------------------------

# (raw title, raw snippet, t_avail UTC, the rule that alone catches it or ""): the sixth verification
RUNNING = (
    (  # rule 1: a Yahoo live blog stamped the evening before, its title written during the session
        "Stock market today: S&P 500, Nasdaq pull back from record run as Senate passes Trump tax bill, "
        "Tesla sinks",
        "Wall Street is watching for progress on trade talks and on President Trump's massive budget bill.",
        "2025-07-01 02:55:11",
        "live",
    ),
    (
        "Markets News, July 16, 2025: Stocks Close Higher After Trump Denies He Plans to Fire Fed Chair "
        "Powell",
        "Stocks finished higher Wednesday after sliding briefly this morning following reports.",
        "2025-07-16 12:17:00",
        "",
    ),
    (
        "Stock Market Live August 14: Wholesale Inflation Rises, S&P 500 (VOO) Falls",
        "Live Updates Live Coverage Has Ended Thursday Wrap-up 4:20 pm The Vanguard S&P 500 ETF closed "
        "Thursday.",
        "2025-08-14 13:03:00",
        "",
    ),
    (
        "Live: Why Lockheed Martin Is Plunging After Q2 Earnings",
        "Live Updates Live Coverage Updates appear automatically as they are published.",
        "2025-07-22 11:45:38",
        "live",
    ),
    (  # Investing.com stamps the page the evening before; its text reports the session's close
        "Stock market today: S&P 500 ends higher as cyclicals offset tech wreck",
        "Investing.com -- The S&P 500 closed higher after cutting losses Monday as a jump in cyclical "
        "stocks.",
        "2025-01-12 23:50:00",
        "",
    ),
    ("Nasdaq Today: Markets Edge Higher with Tech and Telecom Momentum", "", "2025-07-23 04:13:00", "live"),
    (  # rule 2: an update after the open, and a live entry
        "Goldman among the three most bullish Wall Street firms",
        "Published Tue, Jul 8 20258:14 AM EDT Updated Tue, Jul 8 202512:00 PM",
        "2025-07-08 12:14:00",
        "clock",
    ),
    (
        "UnitedHealth reports billions in revenue and profit amid controversy",
        "Updated at 10:28 AM EST. UnitedHealth Group posted stronger-than-expected fourth quarter earnings.",
        "2025-01-16 11:30:00",
        "clock",
    ),
    (  # a London live page: 4.17pm is 11:17 ET
        "FTSE 100 rises with handbrake on after Iran-Israel ceasefire hits oil, gold and defence",
        "FTSE 100 rises 20 points to 8778 4.17pm: FTSE closes higher as oil prices plunge",
        "2025-06-24 05:30:00",
        "clock",
    ),
    (  # rule 3: a market close on the weekday of s, Reuters and Europe
        "Wall St stocks edge lower as investors look for tariff clarity",
        "(Reuters) -The S&P 500 ended Tuesday's choppy session slightly lower as investors waited for "
        "clarity.",
        "2025-07-08 09:58:00",
        "",
    ),
    (
        "European shares rise on energy, healthcare boost; tariff uncertainty lingers",
        "(Reuters) -European shares ended higher on Tuesday, boosted by healthcare and energy shares.",
        "2025-07-08 07:22:00",
        "close",
    ),
    (  # rule 4: AP's running text, and Reuters' "early trading" (after the open in its style)
        "Global markets react to tariffs",
        "NEW YORK (AP) — Wall Street is holding steadier following its see-saw ride. "
        "The S&P 500 was up 0.1% in early trading Tuesday.",
        "2025-08-05 05:42:00",
        "intraday",
    ),
    (
        "Alphabet jumps as AI-driven spending fuels cloud revenue surge",
        "(Reuters) -Alphabet shares rose more than 3% in early trading on Thursday as the Google parent's "
        "earnings.",
        "2025-07-24 06:07:00",
        "intraday",
    ),
    (  # rule 5: a wrap title stamped the morning of the session
        "Dow Swings To Drop 224 Points; Nasdaq Ekes Out A Gain",
        "",
        "2025-08-07 12:07:00",
        "wrap",
    ),
    (
        "US stocks end mixed on report Trump wants higher EU tariff. S&P 500, Nasdaq off records",
        "US stocks close mixed after the FT says Trump wants an at least 15%-20% tariff on all EU goods.",
        "2025-07-18 10:11:00",
        "wrap",
    ),
    (  # a forecast word after the move word does not veto
        "U.S. stocks indexes fall after Bloomberg News reports Trump likely to fire Powell",
        "U.S. stock indexes reversed course to fall on Wednesday after Bloomberg News reported the plan.",
        "2025-07-16 10:05:00",
        "wrap",
    ),
    (  # an AP photo caption names an Asian market, but not as the subject of its first words
        "Stocks slip on Wall Street after last week's rally",
        "A dealer watches computer monitors near screens showing the Korea Composite Stock Price Index.",
        "2025-08-25 05:22:00",
        "wrap",
    ),
    ("FTSE 100 Live: Blue-chips slump as bond market flexes muscles", "", "2025-05-22 05:15:00", "live"),
    (
        "LIVE MARKETS-Nasdaq, S&P 500 hit records; earnings and Iran in focus",
        "",
        "2025-07-23 11:00:00",
        "live",
    ),
    (  # a live page known by its snippet
        "Markets close lower as banks drag",
        "Stock Market today: get the latest updates on Sensex, Nifty, BSE and share prices.",
        "2025-02-03 06:00:00",
        "live",
    ),
    (
        "Live Vanguard IT ETF (VGT): Markets Embroiled in Selling amid Economic Slowdown",
        "",
        "2025-07-13 19:12:00",
        "live",
    ),
    # the session's close named as a noun, on a page stamped the evening before (s = Fri 2025-08-22)
    ("Dow, S&P 500, Nasdaq Surge on Friday Close", "", "2025-08-22 00:14:00", "close"),
    (  # an overseas word after the running phrase does not veto
        "Markets react to the trade deal",
        "NEW YORK (AP) — U.S. stocks are hanging near record highs Monday after the United States agreed to "
        "tax products coming from the European Union.",
        "2025-07-28 08:45:00",
        "intraday",
    ),
)
RUNNING_KEPT = (  # (raw title, raw snippet, t_avail UTC)
    (
        "US Stocks Likely To Open Lower After A Week Of Records: Tesla In Focus",
        "U.S. stock futures declined on Monday after scaling fresh records in the previous truncated week.",
        "2025-07-07 10:43:00",
    ),
    (
        "U.S. Stock Futures Flat ahead of Key Fed Decision",
        "U.S. stock futures were flat ahead of Wednesday's session as traders looked ahead to the Fed "
        "meeting.",
        "2025-09-17 04:33:00",
    ),
    (
        "Wall St set to open higher with big earnings, inflation data on deck",
        "Wall Street was poised for a firm start on Monday as investors prepared for a wave of earnings.",
        "2025-10-20 13:03:00",
    ),
    (
        "Healthpeak Properties (DOC) to Release Earnings on Thursday",
        "Healthpeak Properties is expected to announce its results after the market closes on Thursday, "
        "July 24th.",
        "2025-07-17 07:44:00",
    ),
    (
        "Alexandria Real Estate Equities Sets Q3 2025 Earnings Call for October 28",
        "It has scheduled its earnings conference call and webcast for October 28, 2025 at 2:00 p.m. ET.",
        "2025-08-26 12:30:00",
    ),
    (
        "Asian Shares Drift Lower After Fed's Hawkish Rate Cut",
        "CANBERA (dpa-AFX) - Asian stocks ended mostly lower on Thursday following the Federal Reserve "
        "decision.",
        "2025-09-18 09:12:00",
    ),
    (
        "Dell slides after weak margins eclipse upbeat full-year forecast",
        "(Reuters) -Shares of Dell Technologies dropped nearly 6% in premarket trading on Friday.",
        "2025-08-29 10:05:00",
    ),
    (
        "European Truck Shares Mixed After Trump's Tariff Plan",
        "STOCKHOLM--Shares in European truckmakers were mixed in early trade Friday, reflecting their "
        "fortunes.",
        "2025-09-26 09:00:00",
    ),
    (
        "FTSE 100 slips as UK public deficit surprises",
        "12.30pm: LSEG buoyed by upgrade as new matched bargain platform inches forward.",
        "2024-12-17 12:30:00",
    ),
    (
        "Colgate Palmolive (India) shares fall 2.08% in today's trading session",
        "Shares of Colgate Palmolive (India) declined by 2.08%, trading at Rs 2,227.00 at 10:32 am.",
        "2025-09-26 05:13:00",
    ),
    (
        "Coca-Cola Shares Rise as Q4 Beats Estimates with 6.5% Revenue Growth",
        "Coca-Cola (KO, Financial) climbed 3.7% higher in early trading Tuesday after its Q4 earnings "
        "report.",
        "2025-02-11 13:11:00",
    ),
    (
        "Everybody's talking about AI, but Goldman Sachs says it's still not showing up in bottom lines",
        "AI-linked stocks are up 17% this year, fueled by big tech's massive investments.",
        "2025-09-05 06:01:00",
    ),
    (  # the previous session's close, stamped that evening
        "Stocks closed slightly higher Monday as investors digested tariff threats",
        "Stocks closed slightly higher Monday as investors digested President Donald Trump's latest threats.",
        "2025-07-14 22:00:00",
    ),
    (
        "Earnings Flash (LYV) Live Nation Entertainment, Inc. Reports Q2 Revenue $7.01B, vs. FactSet Est "
        "of $6.85B",
        "Earnings Flash (LYV) Live Nation Entertainment, Inc. Reports Q2 Revenue. Published on 08/07/2025 "
        "at 04:10 pm EDT.",
        "2025-08-07 20:10:36",
    ),
    (
        "Class Action Lawsuit Filed Against Dow Inc. (DOW) - Recover Losses",
        "If you suffered a loss on your Dow Inc. (NYSE:DOW) investment and want to learn about a potential "
        "recovery.",
        "2025-10-01 04:10:10",
    ),
    ("Nasdaq Inc shares fall on earnings but CEO hails 'transformational year'", "", "2025-01-29 09:44:59"),
    (
        "S&P Global Keeps Quarterly Dividend at $0.96 a Share, Payable Dec. 10",
        "S&P Global Keeps Quarterly Dividend. Published on 09/16/2025 at 05:21 pm EDT. MT Newswires.",
        "2025-09-16 21:21:28",
    ),
    ("Live Nation shares rise after concert demand stays strong", "", "2025-08-08 12:00:00"),
    (
        "Live Nation Entertainment (LYV): Analyst Raises Price Target to $185 | LYV Stock News",
        "",
        "2025-07-24 12:00:00",
    ),
    ("Nasdaq (NASDAQ:NDAQ) Trading 2% Higher After Analyst Upgrade", "", "2025-08-12 11:00:00"),
    ("Dow Inc shares fall after it halves its dividend", "", "2025-07-24 11:00:00"),
    ("S&P Global shares rise after its ratings unit grows", "", "2025-07-29 11:00:00"),
    # each veto alone keeps one of these: a foreign time zone, a schedule, pre-market words, a forecast, an
    # overseas market, the title veto, the same-day rule, the nearest weekday, another weekday
    (
        "Sensex rises in early deals",
        "Updated at 10:45 AM IST. The Sensex rose 300 points as banks gained.",
        "2025-09-26 05:30:00",
    ),
    ("Agilent to webcast its investor day", "The webcast starts as of 10:00 a.m. ET.", "2025-09-26 11:30:00"),
    (
        "Wall Street hovers near records ahead of the jobs report",
        "Wall Street is drifting near its records in premarket trading ahead of the jobs report.",
        "2025-07-03 07:00:00",
    ),
    (
        "US Stocks On Edge As Investors Await November Inflation Data",
        "US indices slightly down in premarket trading on Mon amid mixed global trade.",
        "2024-12-09 11:46:00",
    ),
    (
        "U.S. Stocks May Lack Direction As Traders Digest Latest Data",
        "(RTTNews) - Stocks may show a lack of direction in early trading on Thursday.",
        "2025-09-11 12:53:00",
    ),
    (
        "Gloomy opening on the European markets",
        "Leading European stock indexes opened lower on Monday as investors weighed tariffs.",
        "2025-08-25 09:09:00",
    ),
    (
        "Stocks Rise; Prysmian Leads on the Mib",
        "On Thursday, major European stock indices met expectations by opening in positive territory.",
        "2025-07-17 07:49:00",
    ),
    ("Stocks Decline Pre-Bell as Traders Await Fed Chair Speech", "", "2025-08-19 11:15:00"),
    (  # stamped on the US holiday before the session (s = Tue 2025-01-21): a London close of the day before
        "FTSE 100 notches new high as dollar and oil weaken",
        "4.06pm: Gains for European stocks, but not as much as earlier.",
        "2025-01-20 05:00:00",
    ),
    (
        "Market Monitor News June 06",
        "Wall Street ended Thursday's session in the red, as investor caution ahead of Friday's jobs report.",
        "2025-06-06 00:01:00",
    ),
    (
        "Weekly market notes",
        "Wall Street is drifting on Friday toward the finish of a winning week.",
        "2025-07-21 08:00:00",
    ),
    (
        "Earnings season notes",
        "Wall Street is drifting this afternoon as investors react to earnings.",
        "2025-04-25 23:59:59",
    ),
)


def running_frame(rows: tuple[tuple[str, ...], ...]) -> pd.DataFrame:
    full = [(f"r{i}", r[0], r[1], pd.Timestamp(r[2], tz="UTC")) for i, r in enumerate(rows)]
    return pd.DataFrame(full, columns=["id", "title", "snippet", "t_avail"])


@pytest.mark.parametrize(("title", "snippet", "t_avail", "rule"), RUNNING)
def test_running_market_stories_leave_w0(title: str, snippet: str, t_avail: str, rule: str) -> None:
    cfg = load_states_config().news_exclusion.running_story
    assert running_story(title, snippet, pd.Timestamp(t_avail, tz="UTC"), cfg), title


@pytest.mark.parametrize(("title", "snippet", "t_avail"), RUNNING_KEPT)
def test_running_story_look_alikes_stay(title: str, snippet: str, t_avail: str) -> None:
    cfg = load_states_config().news_exclusion.running_story
    assert not running_story(title, snippet, pd.Timestamp(t_avail, tz="UTC"), cfg), title


def test_each_running_story_rule_has_its_own_case() -> None:
    """Every rule catches a golden case that no other rule does (so removing any rule turns a test red)."""
    from newsaction.states import build as b

    cfg = load_states_config().news_exclusion.running_story
    r = story_rule(cfg)
    for title, snippet, t_avail, rule in RUNNING:
        if not rule:
            continue
        ts = pd.Timestamp(t_avail, tz="UTC")
        s = b.calendar.session_of_w0(ts)
        assert s is not None
        tz = b.ZoneInfo(b.load_project().timezone)
        opens = b.calendar.open_utc(s).tz_convert(tz)
        london = opens.tz_convert(b.ZoneInfo(cfg.european_zone))
        european = r.european.search(f"{title} {snippet}") is not None
        shift = (london.hour - opens.hour) * 60 + london.minute - opens.minute if european else 0
        same = ts.tz_convert(tz).date() == s
        day = b.WEEKDAYS[s.weekday()]
        texts = (title, snippet)
        fired = {
            "live": b.live_format(title, snippet, r),
            "clock": same
            and any(b.post_open_clock(t, opens.hour * 60 + opens.minute, shift, r) for t in texts),
            "close": any(b.closed_on(t, day, r) for t in texts),
            "intraday": any(b.intraday(t, day, same, r) for t in texts),
            "wrap": b.morning_wrap(title, snippet, same, r),
        }
        assert [k for k, v in fired.items() if v] == [rule], (title, fired)


def test_running_story_ids_and_outside_w0() -> None:
    cfg = load_states_config()
    ids = running_story_ids(running_frame(tuple(r[:3] for r in RUNNING) + RUNNING_KEPT), cfg)
    assert ids == frozenset(f"r{i}" for i in range(len(RUNNING)))
    # stamped after the D0 cutoff and before the close: in no W0
    late = running_frame((("Stock market today: Dow slides", "", "2025-07-08 15:00:00"),))
    assert running_story_ids(late, cfg) == frozenset()


def test_running_stories_leave_w0_states_only() -> None:
    """The scope: W0 states leave a running story out, W2 states keep it (W2 ends at the close)."""
    t = pd.Timestamp("2025-07-15 11:00", tz="UTC")
    items = [
        {"id": i, "title": "t", "snippet": "s", "source_class_domain": "other", "t_avail": t}
        for i in ("x", "y")
    ]
    empty = pd.DataFrame()
    inp = Inputs(
        empty,
        empty,
        empty,
        masked={"x": ("t", "s"), "y": ("u", "v")},
        third_party={"x": True, "y": True},
        excluded_w0=frozenset({"y"}),
    )
    assert news_items(items, date(2025, 7, 15), True, inp, "W0")[1] == ["x"]
    assert news_items(items, date(2025, 7, 15), True, inp, "W2")[1] == ["x", "y"]
    assert skipped(inp, "W0") == frozenset({"y"}) and skipped(inp, "W2") == frozenset()


W0_FILES = (
    "states/callA_d0_E3.parquet",
    "states/samples/callA_d0_E0.parquet",
    "states/samples/callA_d0_E3.parquet",
    "states/samples/unmasked.parquet",
)


def test_built_w0_states_carry_no_live_format() -> None:
    """Exact for the live formats that survive masking: no W0 news item has a live-blog title, and the D0
    build left running stories out while the D2 build kept them."""
    if not all((ROOT / "work" / rel).is_file() for rel in W0_FILES):
        pytest.skip("NA-04 state files are absent (run the build)")
    live = re.compile(
        r"(?i)^\s*(?:stock market (?:today|news today|live)\b|markets news,|live\s*:|live markets\b"
        r"|live (?:updates|coverage)\b|live\s+(?!nation\b)[^:|]{1,60}\([A-Z]{2,5}\)\s*:)"
    )
    for rel in W0_FILES:
        df = io.read_parquet(rel, columns=["window", "state_json"])
        assert set(df["window"]) == {"W0"}
        for js in df["state_json"]:
            for item in json.loads(js)["news"]:
                assert not live.search(item["headline"]), (rel, item)
                assert not live.search(item["snippet"]), (rel, item)
    built = json.loads((ROOT / "artifacts" / "NA-04" / "build_states.json").read_text(encoding="utf-8"))
    assert built["callA_d0_E3"]["articles_excluded_running"] > 1_000
    assert built["callA_d2_E3"]["articles_excluded_running"] == 0
    assert built["callB_d2_E3"]["articles_excluded_running"] == 0
