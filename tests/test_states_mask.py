"""PRD NA-04 S3 / AC2: masking and the residual-leak scanner.

Golden cases cover the curated aliases (Google for Alphabet, Facebook for Meta, …), ticker forms, people,
dates, fiscal periods, price talk and price levels, including every leak the three NA-04 verifications found
(BOATS:NEE/PT, ODFL's, MSFT-1.19%, "Second Quarter", "25 septembre", "4/15", Super Micro Computer; then
"MET earnings per share", MS.N, "（紐交所：DE）", CY2025, "2025年8月7日（星期四）", "recently-18", option
codes, "· IP. -0.58%", Chinese company names, …; then "deuxième trimestre", "2분기", "'25", a lone "Aug.",
"H1", "21/04", "DGXjumped 6.4%"). The mutation "empty the alias list" turns the
curated-alias cases red. The scanner is checked to be independent of the masker (its imports, and it counts
every stoplisted ticker), and the val-A leak rates of the built states are read from
artifacts/NA-04/leak_scan.csv.
"""

from __future__ import annotations

import ast
import re
from dataclasses import replace
from functools import cache
from pathlib import Path

import pandas as pd
import pytest

from newsaction import io
from newsaction.paths import ROOT
from newsaction.states.mask import (
    CompanyAliases,
    Masker,
    build_aliases,
    cjk_company_names,
    load_alias_config,
    name_variants,
)
from newsaction.states.scan import LeakScanner, harvest_cjk_names, harvest_names

AAPL, GOOGL, META, LLY, HD, PANW, JPM, BAC = 6, 649, 946, 876, 691, 1111, 808, 145
NEE, ODFL, MSFT, SPGI, WFC, PGR, SMCI, WAB, DD, PEG, DAL, CPB, DASH, NOW = (
    1033, 1088, 996, 1340, 1555, 1147, 1320, 1537, 405, 1136, 401, 344, 403, 1057
)  # fmt: skip
ADI, ALL, COIN, COST, DE, EL, FE, GL, HOOD, IP, IT, MET, MS, PM, TSLA = (
    31, 65, 330, 337, 408, 480, 541, 632, 717, 772, 781, 945, 993, 1159, 1448
)  # fmt: skip


@cache
def aliases() -> dict[int, CompanyAliases]:
    if not (ROOT / "work" / "panel" / "companies.parquet").is_file():
        pytest.skip("work/panel/companies.parquet is absent")
    comp = io.read_parquet("panel/companies.parquet", columns=["symbol_id", "company_id", "ticker", "name"])
    return build_aliases(comp)


@cache
def masker() -> Masker:
    return Masker(aliases(), surnames=frozenset({"Bessent"}), vocabulary=ORDINARY)


# ordinary lower-case words: in a text mostly in capitals, a stoplisted ticker that is one of them stays
ORDINARY = frozenset({"all", "now", "eyes", "keys", "cost"})


@cache
def companies() -> pd.DataFrame:
    return io.read_parquet("panel/companies.parquet", columns=["company_id", "ticker", "name"])


@cache
def scanner() -> LeakScanner:
    """The independent scanner with a small hand-made harvest (the report stage harvests the corpus)."""
    return LeakScanner(
        companies(), [(META, "FB")], {GOOGL: ["Google"], META: ["Facebook"]}, frozenset({"price", "all"})
    )


def m(text: str, cid: int | None, title: bool = False) -> str:
    return masker().mask(text, cid, is_title=title)


@pytest.mark.parametrize(
    ("cid", "text", "gone"),
    [
        (GOOGL, "Alphabet's Google unit beats estimates as YouTube grows", ["Alphabet", "Google"]),
        (META, "Facebook parent Meta Platforms cuts 5% of staff", ["Facebook", "Meta"]),
        (
            JPM,
            "JPMorgan Chase and J.P. Morgan analysts expect Chase to grow",
            ["JPMorgan", "J.P. Morgan", "Chase"],
        ),
        (BAC, "BofA Securities upgrades Bank of America peers", ["BofA", "Bank of America"]),
        (LLY, "Eli Lilly's Zepbound tops forecasts; Lilly raises outlook", ["Lilly"]),
        (HD, "The Home Depot, Inc. to acquire a distributor", ["Home Depot"]),
        (PANW, "Palo Alto Networks, Inc. agrees to buy a security startup", ["Palo Alto"]),
    ],
)
def test_curated_and_derived_names(cid: int, text: str, gone: list[str]) -> None:
    out = m(text, cid)
    for g in gone:
        assert g not in out, out
    assert "the company" in out.lower()


def test_tickers_in_every_form() -> None:
    out = m(
        "Apple Inc. (NASDAQ: AAPL) and $AAPL holders; NASDAQ:AAPL, AAPL.O and AAPL rose in revenue terms",
        AAPL,
    )
    assert "AAPL" not in out and "Apple" not in out
    out = m("Shares of GOOGL and GOOG (NASDAQ:GOOGL, GOOG) are in focus", GOOGL)
    assert "GOOG" not in out
    assert "(" not in m("Alphabet (GOOGL) unveils a chip", GOOGL)


def test_bare_ticker_rules() -> None:
    out = m("ServiceNow (NYSE: NOW) beats; Now is the time", NOW)
    assert "NOW" not in out and "Now is" in out and "ServiceNow" not in out  # the word "Now" stays
    assert "NOW" in m("SERVICENOW AND NOW: ALL EYES ON EARNINGS", NOW, title=True)  # a text in capitals
    assert "NOW's" not in m("NOW's guidance", NOW)
    assert "AAPL" not in m("APPLE AND AAPL TO REPORT RESULTS", AAPL, title=True)
    assert "AAPLX" in m("AAPLX fund", AAPL)  # whole words only
    assert (
        m("DASH rose on volume of 1,000", DASH).count("$") == 0
    )  # an all-stoplist company has no empty pattern
    assert "$230" not in m("KGI Adjusts Price Target on DoorDash to $230 From $210, Maintains", DASH)


@pytest.mark.parametrize(
    ("cid", "text", "gone"),
    [
        (NEE, "NextEra Energy (BOATS:NEE/PT) and NEE/PR preferred units", ["NEE", "BOATS"]),
        (ODFL, "View ODFL's earnings results at MarketBeat; ODFL shares; ODFL beat estimates", ["ODFL"]),
        (
            MSFT,
            "Microsoft (MSFT-1.19%) slipped as MPC-1.32% and (AAPL +0.87%) moved",
            ["MSFT", "1.19", "1.32", "0.87"],
        ),
        (ANET := 92, "Was ist von der ANET-Aktie zu erwarten?", ["ANET"]),
        (SMCI, "Super Micro Computer Options Spot-On; Super Micro beats", ["Super Micro", "Computer"]),
        (WAB, "Westinghouse Air Brake Technologies raises outlook", ["Westinghouse"]),
        (DD, "DuPont de Nemours Q2 Earnings Report", ["DuPont", "Nemours"]),
        (PEG, "PSEG files rate case", ["PSEG"]),
        (WFC, "Citigroup Adjusts Price Target on Wells Fargo & Company", ["Wells Fargo", "Company"]),
        (DAL, "Delta 737 arrived at the gate", ["Delta"]),
        (CPB, "Zacks Forecasts Reduced Earnings for Campbell’s", ["Campbell"]),
    ],
)
def test_verifier_cases(cid: int, text: str, gone: list[str]) -> None:
    out = m(text, cid)
    for g in gone:
        assert g not in out, out


def test_other_companies_are_not_masked() -> None:
    out = m("Apple and Microsoft settle; Goldman Sachs advised", AAPL)
    assert "Microsoft" in out and "Goldman Sachs" in out and "Apple" not in out


def test_people() -> None:
    out = m("Apple CEO Tim Cook said demand was strong, according to Tim Cook.", AAPL)
    assert "Tim" not in out and "Cook" not in out
    assert "CEO said" in out
    out = m("Mark Zuckerberg's memo leaked", META, title=True)
    assert "Zuckerberg" not in out and "a person's memo" in out.lower()


def test_one_word_names() -> None:
    out = m("Trump said tariffs; Powell signaled cuts; Xi spoke; Bessent's plan; Musk tweeted", AAPL)
    for name in ("Trump", "Powell", "Xi", "Bessent", "Musk"):
        assert name not in out, out
    assert "a person's plan" in out


def test_title_case_words_are_not_people() -> None:
    vocab = frozenset({"balance", "sheet", "soar", "buy", "mark"})
    mk = Masker(aliases(), vocabulary=vocab)
    assert "Balance Sheet" in mk.mask("DexCom, Inc. Balance Sheet: Consolidated Financial Analysis", 459)
    out = mk.mask("Elon Musk said the company will grow. Musk added that launches come soon.", 1448)
    assert "Musk" not in out and "Elon" not in out
    assert "Zuckerberg" not in mk.mask("Mark Zuckerberg's memo leaked", META, is_title=True)


def test_dates_years_and_fiscal_periods() -> None:
    text = (
        "CUPERTINO, Calif., Oct. 30, 2025 /PRNewswire/ -- Apple reported Q3 FY2025 revenue of $94.0 billion "
        "on Thursday, July 31, 2025, up from the third quarter of 2024; fiscal 2026 guidance and FY25 EPS of "
        "$6.08 were also given in October. 1H25 and H2 2025 trends; 2024-2025 plan; ISIN US0378331005."
    )
    out = m(text, AAPL)
    assert not re.search(r"\b(?:19|20)\d{2}\b", out), out
    assert not re.search(r"\b(?:Q[1-4]|FY\s?\d|October|Thursday|July|Oct\.)", out), out
    assert "CUPERTINO" not in out and "US0378331005" not in out
    assert "$94.0 billion" in out and "$6.08" in out  # fundamental figures are kept
    assert "the quarter" in out and "the fiscal year" in out


def test_period_labels_in_any_case() -> None:
    out = m(
        "Reports Second Quarter Results; SECOND-QUARTER sales; first half of 2025; 2H25; the second half",
        AAPL,
    )
    assert not re.search(r"(?i)\b(?:second|first)[\s-]+(?:quarter|half)\b|\b2H25\b", out), out


def test_non_english_dates() -> None:
    out = m(
        "Le 25 septembre, la société a publié. Am Donnerstag, 23. Juli 2025 stieg der Umsatz. am 21. Mai",
        AAPL,
    )
    assert not re.search(r"(?i)septembre|donnerstag|juli|mai|\b2025\b|am 21", out), out


def test_numeric_month_day() -> None:
    out = m("Earnings due 4/15; 3/4 of revenue; on 7/8 the board met", AAPL)
    assert "4/15" not in out and "7/8" not in out and "3/4 of revenue" in out


def test_bare_years() -> None:
    out = m(
        "Sales should double by 2030 from 2019 levels; the 2025 plan and 2024's results; Russell 2000 fell",
        AAPL,
    )
    assert not re.search(r"(?<!Russell )\b(?:19|20)\d{2}\b", out), out
    assert "Russell 2000" in out


def test_price_talk_is_scrubbed_after_masking() -> None:
    out = m("Apple beat estimates. Apple shares rose 5% in early trading.", AAPL)
    assert "5%" not in out and "beat estimates" in out
    out = m("S&P Global shares fall 1.26% premarket. Revenue rose 5% to $3.6 billion.", SPGI)
    assert "1.26%" not in out and "Revenue rose 5% to $3.6 billion." in out
    out = m("Apple's quarter Earnings Disappoint, Shares Fall 8.3%", AAPL, title=True)
    assert "8.3%" not in out


def test_price_levels() -> None:
    """Price-target amounts become a relative change or go; deal prices go; EPS and dividends stay."""
    out = m(
        "Citigroup Adjusts Price Target on Wells Fargo & Company to $85 From $78, Maintains Neutral Rating",
        WFC,
    )
    assert "$" not in out and "raised by about 9%" in out
    out = m("Progressive had its price objective lowered by Keefe from $295.00 to $294.00.", PGR)
    assert "$" not in out and "lowered slightly" in out
    out = m(
        "set a price target of $288.00. A $35 price target; PT $404; a revenue target of $5 billion", AAPL
    )
    assert "$288" not in out and "$35" not in out and "$404" not in out and "$5 billion" in out
    out = m(
        "Agrees to be acquired for $45 per share in cash; Offering Of 7 Million Shares At $142.00 Per Share",
        AAPL,
    )
    assert "$45" not in out and "$142" not in out
    out = m("EPS of $1.99 per share; a dividend of $0.50 a share", AAPL)
    assert "$1.99 per share" in out and "$0.50 a share" in out


def test_name_variants() -> None:
    cfg = load_alias_config()
    assert name_variants("Home Depot (The)", cfg)[:2] == ["The Home Depot", "Home Depot"]
    assert "Eli Lilly" in name_variants("Lilly (Eli)", cfg)
    assert name_variants("Alphabet Inc. (Class C)", cfg) == ["Alphabet"]
    assert "American Airlines" in name_variants("American Airlines Group", cfg)
    assert "American" not in name_variants(
        "American Airlines Group", cfg
    )  # a common word alone is not an alias
    assert "Akamai" in name_variants("Akamai Technologies", cfg)


def test_empty_curated_list_leaks_and_the_scanner_sees_it() -> None:
    """Positive control: without the curated list, "Google" survives and the scanner counts it."""
    cfg = replace(load_alias_config(), companies={})
    comp = io.read_parquet("panel/companies.parquet", columns=["symbol_id", "company_id", "ticker", "name"])
    weak = Masker(build_aliases(comp, cfg=cfg), cfg=cfg)
    text = "Alphabet's Google unit beats estimates"
    leaked = weak.mask(text, GOOGL)
    assert "Google" in leaked
    assert scanner().scan_text(leaked, GOOGL).names >= 1
    assert scanner().scan_text(m(text, GOOGL), GOOGL).names == 0


def test_scanner_is_independent_of_the_masker() -> None:
    """The scanner must not reuse the masker's definitions (NA-04 verification, AC2)."""
    source = (ROOT / "src" / "newsaction" / "states" / "scan.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(str(mod).startswith("newsaction") for mod in modules), modules
    code = source.replace(ast.get_docstring(tree, clean=False) or "", "")
    assert "aliases" not in code and "mask" not in code.replace("masked", "")


def test_harvest_names() -> None:
    arts = pd.DataFrame(
        {
            "company_id": [SMCI] * 3 + [AAPL],
            "title": ["Shares of Super Micro Computer (SMCI) rise"] * 3 + ["Apple Inc. (NASDAQ: AAPL) beats"],
            "snippet": [""] * 4,
        }
    )
    got = harvest_names(arts, {SMCI: ["SMCI"], AAPL: ["AAPL"]})
    assert got[SMCI] == ["Super Micro Computer"] and not got.get(AAPL)  # Apple: seen fewer than 3 times


def test_scanner_counts() -> None:
    sc = scanner()
    c = sc.scan_text("Apple (AAPL) said on Monday, Oct. 3 that 2025 sales $AAPL, BOATS:AAPL, AAPL's", AAPL)
    assert c.names == 1 and c.tickers == 4 and c.years == 1 and c.dates >= 2
    clean = sc.scan_text("the company said recently that the year sales rose", AAPL)
    assert not any(clean.as_dict().values())
    assert sc.scan_text("Target price raised", 1416).names == 1  # a one-word ATOM name counts as written
    assert sc.scan_text("a price target raised", 1416).names == 0
    f = sc.scan_text(
        "Second Quarter; le 25 septembre; 4/15; MPC-1.32%; shares fall 2% premarket; Trump", AAPL
    )
    assert f.dates >= 3 and f.quotes == 1 and f.price_moves >= 1 and f.people == 1
    assert sc.scan_text("set a price target of $288; EPS per share of $0.25", AAPL).price_levels == 1


def test_val_a_leak_rates_below_target() -> None:
    """AC2 on the built val-A states (artifacts/NA-04/leak_scan.csv)."""
    path = ROOT / "artifacts" / "NA-04" / "leak_scan.csv"
    if not path.is_file():
        pytest.skip("artifacts/NA-04/leak_scan.csv is absent (run the report stage)")
    scan = pd.read_csv(path)
    masked = scan.loc[scan["masked"].astype(bool)]
    assert len(masked) > 20_000
    for _, g in masked.groupby("file"):
        assert ((g["names"] + g["tickers"]) > 0).mean() < 0.005
        assert ((g["years"] + g["dates"]) > 0).mean() < 0.005
    twin = scan.loc[~scan["masked"].astype(bool)]
    assert ((twin["names"] + twin["tickers"]) > 0).mean() > 0.5  # the scanner finds names when they are there
    assert ((twin["years"] + twin["dates"]) > 0).mean() > 0.5


def test_corpus_surnames() -> None:
    mk = Masker(aliases(), vocabulary=frozenset({"inn"}))
    cands = [[(0, 13, ["Jerome", "Powell"])]] * 3 + [[(0, 16, ["Piper", "Oppenheimer"])]] * 4
    cands += [[(0, 9, ["Holiday", "Inn"])]] * 3 + [[(0, 10, ["Das", "Potenzial"])]] * 3
    foreign = [False] * 10 + [True] * 3
    got = mk.corpus_surnames(cands, foreign, {"Oppenheimer": 5})
    assert got == {"Powell"}  # an ORG word, an ordinary word and a word of foreign texts are not surnames


def test_ampersand_emails_ticker_lists_and_previous_targets() -> None:
    chd, wmt = 277, 1569
    assert "Dwight" not in m("Church and Dwight's fiscal year beat; Church & Dwight Co.", chd)
    out = m("Contact erick.gustafson@mmc.com or visit www.marsh.com and https://marsh.com/news", AAPL)
    assert "@" not in out and "marsh" not in out.lower()
    assert "WMT" not in m("mixed WMT/TGT/TJX earnings", wmt)
    out = m("has adjusted its price target for the company, dropping it from the previous $2250, while", AAPL)
    assert "$" not in out


def test_zero_padded_month_day() -> None:
    out = m(
        "Stock Market Week in Review – 07/07 - 07/11; up 20 1/2 cents; a 1/4,000th interest; 5/8-inch", AAPL
    )
    assert "07/" not in out and "1/2 cents" in out and "1/4,000th" in out and "5/8-inch" in out


@pytest.mark.parametrize(
    ("cid", "text", "gone"),
    [
        (MET, "MET earnings per share for the last quarter; View the latest MET revenue; MET/PF", ["MET"]),
        (MS, "Recently, the company's MS.N profit beat estimates; MS initiates coverage", ["MS"]),
        (ALL, "The company ALL, ALL is expected to show a rise in quarterly revenue", ["ALL"]),
        (COST, "Brokers Issue Forecasts for COST the quarter Earnings", ["COST"]),
        (IT, "IT earnings per share; View IT operating, investing, and financing activities", ["IT "]),
        (PM, "PM Dividend Announcement; Marlboro maker PM missed revenue expectations", ["PM"]),
    ],
)
def test_upper_case_stoplisted_tickers(cid: int, text: str, gone: list[str]) -> None:
    """Second NA-04 verification: a stoplisted ticker in upper case in mixed-case text is the company."""
    out = m(text, cid)
    for g in gone:
        assert g not in out, out


def test_upper_case_words_that_are_not_the_company() -> None:
    assert "IT Spending" in m("Global IT Spending to Grow; IT services firms; IT- en communicatie", IT)
    assert "4:30 PM ET" in m("Call at 4:30 PM ET", PM)
    caps = masker().patterns(MET).caps_ticker
    assert caps is not None and caps.search("METÁL") is None  # an accented letter continues the word
    assert "PMČR" not in m("PMČR: Firma uvedla", PM)  # Philip Morris ČR, PMI's Czech unit (a curated alias)
    assert "ALL EYES" in m("ALL EYES ON THE FED AS ALLSTATE REPORTS", ALL, title=True)
    assert "KEYS" not in m("AFTER-HOURS EARNINGS: ALC, KEYS, TOL, JHX", 820, title=True)  # a list of tickers
    assert "IR:" not in m("IR: INGERSOLL RAND ACCELERATES VALUE CREATION", 778, title=True)  # not a word


def test_quote_widget_inside_a_name() -> None:
    """ "Constellation · CEG. +3.58%. Energy's": the widget goes before the company step."""
    out = m("Constellation · CEG. +3.58%. Energy's stock price over the past year has sparked debate", 259)
    assert "Constellation" not in out and "CEG" not in out and "%" not in out


def test_price_change_lines_codes_and_levels() -> None:
    text = "mean price target of $334.69, per FactSet. Price: 152.75, Change: -15.87, Percent Change: -9.4%"
    out = m(text, AAPL)
    assert "152.75" not in out and "15.87" not in out and "Price:" not in out
    out = m("The company Advances ABBV-400 Study; Apple Inc. AAPL-2.96%. Get Free Report.", AAPL)
    assert "AAPL" not in out and "2.96" not in out
    assert "ABBV" not in m("AbbVie Advances ABBV-400 Phase 2 Study", 9)
    out = m("Citi's seven-session winning streak boosts stock to $102.89. Revenue rose 5%.", 226)
    assert "$102.89" not in out and "Revenue rose 5%" in out
    assert "$0.23" in m("Net income per diluted share at $0.23, up from $0.17", AAPL)  # a per-share figure
    out = m("raised the price target for the company shares from $280.00.1; the company signed", AAPL)
    assert "$280" not in out
    assert "/27" not in m("We cut the FY26/27 earnings per share by 7%", AAPL)
    out = m("Jul 15, 2025 - 08:30 AM. CHICAGO --(BUSINESS WIRE)-- Apple announced", AAPL)
    assert "CHICAGO" not in out and "BUSINESS WIRE" not in out


def test_cjk_name_with_a_function_character() -> None:
    """ "奧的斯" (Otis) holds 的: the whole short word before the ticker is a name too."""
    otis = 1104
    title = "奧的斯（紐交所：OTIS）穩健的收益已被保守地計入賬目。"
    arts = pd.DataFrame({"company_id": [otis], "title": [title], "snippet": [""]})
    names = cjk_company_names(arts, aliases())
    assert "奧的斯" in names[otis]
    mk = Masker(aliases(), surnames=frozenset(), cjk_names=names)
    out = mk.mask("市場似乎對奧的斯（紐交所:OTIS）最近公佈的穩健收益反應平淡", otis)
    assert "奧的斯" not in out and "OTIS" not in out and "紐交所" not in out


def test_cjk_and_venue_ticker_forms_and_option_codes() -> None:
    out = m("多位分析師上調了對迪爾股份（紐交所：DE）的價格預期", DE)
    assert "DE" not in out and "紐交所" not in out and "（" not in out  # the whole parenthesis goes
    assert "HOOD" not in m("入門：ロビンフッド・マーケッツ（HOOD US）", HOOD)
    assert "COIN" not in m("Coinbase（納斯達克：COIN）和 COIN.US", COIN)
    out = m("Analog Devices 250703 305.00C (ADI250703C305000) Stock Options Chain", ADI)
    assert "ADI" not in out and "250703" not in out and "305.00" not in out and "option" in out


def test_glued_years_and_periods() -> None:
    out = m("2025Q2 preview; FY2025Q2; Q2-25 EPS; Q1 CY2025 results; EHA2025 data; 於2025年; 3Q25", GL)
    assert not re.search(r"(?:19|20)\d{2}|Q[1-4]|-25", out), out
    assert "the quarter results" in out


def test_cjk_dates_and_periods() -> None:
    text = "將於2025年8月7日（星期四）舉行；8月7日；週一的動向；木曜日に；2025年第二季度；上半年；2025年度"
    out = m(text, AAPL)
    assert not re.search(r"\d|星期|週一|曜|季度|半年", out), out


def test_day_ranges() -> None:
    out = m("minutes of the July 17-18 meeting; floods on July 4–5, 2025, killed; week of July 7-11", AAPL)
    assert not re.search(r"\d", out), out


def test_quote_widgets() -> None:
    out = m("Tesla · TSLA. +3.52%. plans to launch; FSLR0.00%. Top News", AAPL)
    assert "%" not in out and "TSLA" not in out and "plans to launch" in out
    assert "%" not in m("The company · IP. -0.58%. has sparked a debate", IP)
    assert "49.32" not in m("FE|FirstEnergy|Price:49.320|Chg%:-0.600", FE)


def test_cjk_company_names_and_people() -> None:
    arts = pd.DataFrame(
        {
            "company_id": [DE, DE, DE, EL],
            "title": [
                "多位分析師上調了對迪爾股份（紐交所：DE）的價格預期",
                "我們認爲迪爾(紐約證券交易所代碼：DE）正在冒一些債務風險",
                "迪爾（紐交所：DE）公佈業績",
                "エスティ・ローダー・カンパニーズ（NYSE：EL）とM·A·Cコスメティックスは",
            ],
            "snippet": [""] * 4,
        }
    )
    names = cjk_company_names(arts, aliases())
    assert {"迪爾股份", "迪爾"} <= set(names[DE]) and "エスティ・ローダー・カンパニーズ" in names[EL]
    mk = Masker(aliases(), surnames=frozenset(), cjk_names=names)
    assert "迪爾" not in mk.mask("迪爾股份公佈業績，迪爾表示", DE)
    out = mk.mask("但Wedbush證券分析師丹·艾夫斯卻持不同看法", AAPL)
    assert "艾夫斯" not in out and "分析師" in out and "a person" in out
    got = harvest_cjk_names(arts, {DE: ["DE"], EL: ["EL"]})
    assert "迪爾" in got[DE]  # the scanner's own harvest (every ending seen twice)


def test_alias_config_refuses_yaml_booleans(tmp_path: Path) -> None:
    """A bare ON in YAML is the boolean true: the stoplist held "True", not "ON" (second verification)."""
    path = tmp_path / "aliases.yaml"
    path.write_text(
        "legal_suffixes: [Inc]\ncommon_words: [the]\nbare_ticker_stoplist: [ON, IT]\ncompanies: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-string"):
        load_alias_config(path)
    assert "ON" in load_alias_config().bare_ticker_stoplist and "ON" in load_alias_config().companies


def test_scanner_counts_every_stoplisted_ticker() -> None:
    """The scanner has no list of English-word tickers of its own: every stoplisted ticker of the masker
    counts in upper case in mixed-case text (the test reads the alias file; the scanner does not)."""
    sc = scanner()
    stop = load_alias_config().bare_ticker_stoplist
    checked = 0
    for cid, t in zip(companies()["company_id"], companies()["ticker"], strict=True):
        if t in stop and len(t) >= 2:  # ATOM tickers (the scanner does not know the curated ones)
            assert sc.scan_text(f"Analysts expect {t} earnings per share to rise", int(cid)).tickers >= 1, t
            checked += 1
    assert checked >= 45


def test_scanner_sees_the_second_verification_forms() -> None:
    sc = scanner()
    assert sc.scan_text("MET earnings per share for the last quarter", MET).tickers == 1
    assert sc.scan_text("the company's MS.N profit beat", MS).tickers == 1
    assert sc.scan_text("多位分析師上調了對the company（紐交所：DE）的價格預期", DE).tickers >= 1
    assert sc.scan_text("the company 250703 305.00C (ADI250703C305000)", ADI).tickers == 1
    assert sc.scan_text("the quarter CY2025 results; EHA2025 data", AAPL).years == 2
    c = sc.scan_text("阿克邁科技將於2025年8月7日（星期四）; the yearQ2; the quarter-25; recently-18", AAPL)
    assert c.years == 1 and c.dates >= 5
    quotes = sc.scan_text("The company · the company. +0.05%. presents; FE|x|Price:49.3|Chg%:-0.6", FE)
    assert quotes.quotes >= 2
    assert sc.scan_text("Results at 4:30 PM ET", PM).tickers == 0  # a clock time
    assert sc.scan_text("ALL EYES ON THE FED", ALL).tickers == 0  # a text in capitals, an ordinary word
    assert sc.scan_text("分析師薩姆·阿爾特曼", AAPL).people == 1
    assert sc.scan_text("Recently - 08:30 AM. the company announced", AAPL).dates == 0  # a time
    assert sc.scan_text("Price Target Raised Amidst $35 Billion Acquisition", AAPL).price_levels == 0
    assert sc.scan_text("Seltene Erden: A person droht", 1).tickers == 0  # Agilent's ticker is A
    assert sc.scan_text("the company: price: Price: 152.75, Change: -1.2", AAPL).price_levels == 1


def test_exchange_letters_truncated_names_and_slashed_dates() -> None:
    nke, wbd = 1046, 1543
    out = m("Nike NKE-N reported; Apple Inc. AAPL-Q -1.05%decrease. forecast revenue", nke)
    assert "NKE" not in out
    out = m("Apple Inc. AAPL-Q -1.05%decrease. forecast revenue well above estimates", AAPL)
    assert "AAPL" not in out and "1.05" not in out and "decrease" not in out
    assert "Warner" not in m("analysts lowered their Q3 EPS estimates for Warner...", wbd)
    assert "Warner" in m("Warner Music signed a deal", AAPL)  # another company's name stays
    assert not re.search(r"\d", m("本新聞稿由Insight發佈於2025/08/08，由發布之企業", AAPL))
    assert "-25" not in m("operating profit rose for Q4 2024-25, with revenue up", AAPL)


def test_tickers_glued_listed_or_with_digits() -> None:
    anet, ctra, abbv, tgt, ipg, ge = 92, 379, 9, 1416, 773, 612
    assert "ANET" not in m("Arista Networks, Inc.ANET is witnessing solid demand", anet)
    assert "CTRA" not in m("紐交所:CTRA1年股價與公允價值對比", ctra)
    assert "ABBV" not in m("Earnings and Revenue – SET:ABBV19; ABBV19 earnings per share", abbv)
    assert "TGT" not in m("mixed WMT/TGT/TJX earnings", tgt)
    assert "IPG" not in m("paves the way for the Omnicom-IPG merger", ipg)
    assert "GE9X" not in m("orders for GE9X engines", ge)
    assert m("Apple Inc. AAPL reported", AAPL).lower().count("the company") == 1  # name + ticker: one mention


def test_glued_names() -> None:
    hum = 733
    out = m("Key TakeawaysHumana aims to streamline prior authorizations", hum)
    assert "Humana" not in out and "Takeaways" in out
    assert "Stanford" in m("a Stanford study of Ford drivers", 520)  # case-sensitive: Stanford stays
    assert scanner().scan_text("Key TakeawaysHumana aims to streamline", hum).names == 1


def test_names_written_together_or_after_a_number() -> None:
    assert "Molson" not in m("MolsonCoors Brewing raises prices", 1392)
    assert "Depot" not in m("HomeDepot$ is a ticker on social media", HD)
    out = m("Jul 28, 2025Principal Financial Group® announced", 1143)
    assert "Principal" not in out and "the year the company" in out.lower()
    assert "Fargo" not in m("Wells Fargo & Co Fargo Investment Research raised", WFC)
    assert "MAR" not in m("MARRIOTT INTERNATIONAL : MAR Q2 2025 TRANSCRIPT FINAL", 917, title=True)


def test_ordinal_period_after_a_number_and_caps_ticker_labels() -> None:
    out = m("Results from 2025Second quarter results show growth", AAPL)
    assert "Second quarter" not in out and "2025" not in out
    assert "MAR" not in m("MARRIOTT INTERNATIONAL INC /MD/ MAR: MARRIOTT DECLARES DIVIDEND", 917, title=True)
    assert "Edison" not in m("Consolidated. Edison, one of the largest utilities", 472)


# --- revision 3: the third verification's date forms and glued move verbs ---------------------------

REVISION3_DATES = (  # (text, a fragment that must be gone)
    ("bénéfice au deuxième trimestre grâce à la souscription", "deuxième trimestre"),
    ("für das dritte Quartal meldete", "dritte Quartal"),
    ("im zweiten Quartal 2025 stieg", "zweiten Quartal"),
    ("Umsatz des zweiten Quartals", "Quartal"),
    ("resultados del tercer trimestre fiscal", "tercer trimestre"),
    ("il secondo trimestre è diminuito", "secondo trimestre"),
    ("no segundo trimestre de 2025", "segundo trimestre"),
    ("premier semestre 2025", "semestre"),
    ("het eerste halfjaar", "halfjaar"),
    ("het tweede kwartaal", "kwartaal"),
    ("supera expectativas no 3T25 com lucro", "3T25"),
    ("lucro do 2T 2025", "2T"),
    ("focus sur les résultats T2 et les tarifs", "T2"),
    ("dépassent les attentes au T1 alors", "T1"),
    ("2025년 2분기 실적", "분기"),
    ("상반기 실적", "반기"),
    ("Raises '25 EPS View", "'25"),
    ("Strong Results For Q4 FY’25, Outperforms", "’25"),
    ("Q1 ‘25 results", "‘25"),
    ("September’25 outlook", "’25"),
    ("reports the quarter results on Aug.", "Aug."),
    ("CHICAGO, Aug.", "Aug."),
    ("manufacturing PMI (Sept.)", "Sept."),
    ("The company's 7% H1 Net Income Growth", "H1"),
    ("but 2H tariff risks loom", "2H"),
    ("dltr-20250909", "20250909"),
    ("pire séance depuis 21/04, après NFP", "21/04"),
    ("Earnings Summary. 31/7 13:40. (RTTNews)", "31/7"),
    ("17/09/2025POR REUTERS", "17/09"),
    ("informó el domingo que", "domingo"),
)
REVISION3_KEEP = (
    "using it for T1/PRI lines",
    "type T2 diabetes drug",
    "the '90s boom",
    "rock 'n' roll",
    "H2 Production plant",
    "H2 fuel cell trucks",
    "green H2 strategy",
    "H1-B visa",
    "1H timeframe",
    "</h1>",
    "24/7 Wall St.",
    "24/5 trading",
    "1/2 cents a bushel",
    "3/4 of revenue",
)


@pytest.mark.parametrize(("text", "gone"), REVISION3_DATES)
def test_revision3_date_forms(text: str, gone: str) -> None:
    out = m(text, AAPL)
    assert gone not in out, out
    assert not re.search(r"(?<![\d.,$])(?:19|20)\d{2}(?!\d)", out), out


@pytest.mark.parametrize("text", REVISION3_KEEP)
def test_revision3_lookalikes_are_kept(text: str) -> None:
    assert m(text, AAPL) == text


def test_glued_ticker_price_move() -> None:
    """A move verb glued to a ticker ("DGXjumped 6.4%"): the sentence goes, fundamentals stay."""
    out = m(
        "Shares of healthcare diagnostics company Apple AAPLjumped 6.4% in the morning session after the "
        "company reported strong results. Revenue rose 5% to $94 billion.",
        AAPL,
    )
    assert "6.4%" not in out and "Revenue rose 5% to $94 billion." in out, out
    out = m(
        "What Happened?Shares of software company Autodesk NASDAQ:ADSKfell 7.1% in the morning session.", AAPL
    )
    assert "7.1%" not in out, out
    assert "Slower 6%" in m("Stock Faces Slower 6% Earnings Outlook", AAPL, title=True)  # not "S" + "lower"


def test_scanner_sees_the_third_verification_forms() -> None:
    sc = scanner()
    for text, _ in REVISION3_DATES:
        c = sc.scan_text(text, AAPL)
        assert c.dates + c.years >= 1, text
    for text in REVISION3_KEEP:
        assert sc.scan_text(text, AAPL).dates == 0, text


# the fourth verification (revision 4): share prices, price targets and moves that the English rules missed
REVISION4_GONE = (
    ("Apple's shares opened today at $307.00.", "$307"),
    ("The company's shares closed yesterday at $242.66.", "$242"),
    ("The stock traded as high as $145.16 and last traded at $144.50.", "$145"),
    ("The stock price for the company currently stands at $768.57.", "$768"),
    ("TSMC Stock (NYSE:TSM) Holds $273 After Earnings Beat", "$273"),
    ("Shares open at $143.45, 24.2% above IPO price.", "$143"),
    ("AMD Stock Sees Clearer Path to $200 After Recent Downturn", "$200"),
    ("Qualcomm Stock Forecast: NASDAQ:QCOM at $165.42 With AI Edge Growth", "$165"),
    ("Apple shares hit a record $388.14 recently, driven by strong earnings.", "$388"),
    ("Apple declines with $385 stock price and $57B valuation.", "$385"),
    ("its stock price decreased by $1.04, settling at approximately $54.94.", "$54"),
    ("The shares were sold at an average price of $45.20, for a total value of $45,200.", "$45.20"),
    ("The stock traded as low as C$2.77 and last traded at C$2.96.", "2.77"),
    ("Apple (NASDAQ:AAPL) Trading 2.4% Higher on Analyst Upgrade", "2.4%"),
    ("Apple's $4.89B UK REIT Acquisition Drives 1.95% Stock Rise", "1.95%"),
    ("Apple's 0.69% Gains Defy 50.47% Volume Drop to 329th Trading Rank", "0.69%"),
    ("Recently, Apple closed at a 1.18% decline with a trading volume of $490 million.", "1.18%"),
    ("Investors cheered a 3% rise in shares after the call.", "3%"),
    ("The target price is still set at USD 210.", "210"),
    ("The average one-year price target for Apple has been revised to €151.88 / share.", "151.88"),
    ("Apple Price Target Raised to 315.00 USD by JMP Securities", "315"),
    ("Goldman Sachs initiated Apple with a Sell rating, targeting a price of $80.", "$80"),
    ("Apple Stock Looks Appropriately Priced With $185 Price Estimate", "$185"),
    ("Apple to Acquire Chart Industries for $210/Share; Secures $14.9B Bridge", "$210"),
    ("Mogo (TSE:MOGO) Trading 99.4% Higher - Here's What Happened.", "99.4%"),  # no share word before it
    ("Recently, Norfolk Southern (NSC) closed at a 1.13% decline with a volume of $0.7 billion.", "1.13%"),
    ("Apple Moves 22.8% Higher: Will This Strength Last?", "22.8%"),
    ("Why Apple Zoomed 4% Higher Today", "4%"),
    ("Apple's shares, part of the earnings season rally, traded as high as $242.66.", "$242"),  # verb rule
    ("Apple shares snapped a six-session winning streak, closing 1% lower recently.", "1%"),
    ("Lowe's shares snapped their six-day winning streak, closing 0.47% lower at $240.02 recently.", "$240"),
    # second pass: any cents-precision amount without a per-share fundamental, moves "of N%", options chatter
    ("Apple traded as high as $155.51 and last traded at $154.20.", "$155"),
    ("Apple Receives $49.11 Average Price Target from Analysts", "$49"),
    ("Apple has a one-year high of $66.44 and a one-year low of $47.90.", "$66"),
    ("An executive has sold 2,500 shares at a price of $251.12 per...", "$251"),
    ("Truist Financial Reiterates \u201c$415.00\u201d Price Target for Apple", "$415"),
    ("With a recent closing price of $34.01, Apple continues to capture investor attention.", "$34"),
    ("In a notable move, shares of Apple saw an increase of 2.4% during after-hours trading.", "2.4%"),
    ("Duolingo shares added 16% after the app reported strong results.", "16%"),
    ("Notable profits for the buyer who lifted the $0.37 offer for 1,967 Apple 9/12 weekly 20 puts.", "puts"),
    ("Crude for Sep-25 delivery rose on Tuesday.", "Sep-25"),
    ("The most active strikes are the 9/12 weekly 26 puts and Oct-25 24 puts.", "26 puts"),
    ("Trading News Apple rallies to $202.34 as AI-driven AWS and booming ad revenue fuel growth.", "$202"),
    ("Results beat revenue estimates, with intrinsic value ($261.36) above current price ($246.03).", "$246"),
    ("Apple ended the latest trading session unchanged at $27.75, after gains driven by earnings.", "$27"),
    ("Apple Presents at Morgan Stanley Conference, Jun-12-2025 02:30 PM", "Jun-12"),
    ("Apple Receives $645.36 Consensus Price Target from Analysts", "$645"),
    ("Apple faces mixed ratings, with 8 Buy vs. 10 Hold and a $422.37 average price target.", "$422"),
    ("GE VernovaGEV $554.00 (-3.11%) posted its best day after a strong earnings report.", "$554"),
    ("Apple will pay Metsera $47.50 in cash a share and a further $22.50 in a deal.", "$47.50"),
)
REVISION4_KEEP = (
    "Apple reported earnings of $1.71 per share, beating estimates by $0.04.",
    "Apple declared a quarterly dividend of $0.40 per share.",
    "Revenue was 5% higher than a year ago at $94.9 billion.",
    "The company's 7% gain in revenue beat estimates.",
    "Apple's CFO sold 16,820 shares worth $2,975,458 recently.",
    "Apple sold 13M shares for $3.02B.",
    "Apple will buy back up to $10 billion of its stock.",
    "Apple returned $758 million to its shareholders through buybacks.",
    "On a per-share basis, the company said it had profit of $3.06.",
    "Apple's adjusted EPS of $2.24 beat the consensus of $2.15.",
    "The company the quarter 10-Q: Sales −1.6%, EPS +4.9% to $2.13; AUM +14% to $686B",
    "Adjusted earnings per share (EPS) surged 78%, beating estimates.",
    "Western Digital and the company report 30% higher revenue, fueling a resurgence.",
    "The company reported 26% lower the quarter net income amid tariff losses.",
    "If you invested $1,000 in the company stock 10 years ago, you would have approximately $3,000 today.",
    "Apple is expected to report earnings of $0.72 per share, indicating an increase of 16.1% on a year ago.",
    "Apple's EPS for the quarter was $1.72, surpassing the previous year's $1.57 and the estimated $1.67.",
    "Home Furnishings Stores Market Expansion Continues, with Forecast Valuation of $286.39 Billion",
    "Adjusted earnings per share rose 8.3% year over year in the quarter to $1.44.",
    "Apple's EPS rose to $1.44, beating the consensus of $1.40.",
    "Apple's quarterly revenue fell 1.6% to $6.16 bln, beating estimates.",
    "Earnings Flash Apple Posts Adjusted EPS $2.47 per Share, vs. FactSet Est of $2.44",
)


@pytest.mark.parametrize(("text", "gone"), REVISION4_GONE)
def test_revision4_price_talk(text: str, gone: str) -> None:
    assert gone not in m(text, AAPL), m(text, AAPL)


@pytest.mark.parametrize("text", REVISION4_KEEP)
def test_revision4_fundamentals_are_kept(text: str) -> None:
    out = m(text, AAPL)
    assert all(a in out for a in re.findall(r"\$[\d.,]+[MB]?|\d+%", text)), out


def test_deal_prices_are_not_dividends() -> None:
    """The price step alone (NA-02's scrubber already drops most "$X per share" phrasings): "pay" is a deal
    word, unless a fundamental is on either side."""
    out, _ = masker().mask_prices("The company will pay Metsera $47.50 in cash a share in the deal.")
    assert "$47.50" not in out and "a per-share price" in out, out
    out, _ = masker().mask_prices("The company will pay $1.02 per share in dividends next quarter.")
    assert "$1.02 per share" in out, out


def test_price_targets_in_other_notations_become_a_relative_change() -> None:
    out = m("UBS is positive on the stock. The target price is increased from USD 500 to USD 600.", AAPL)
    assert "USD" not in out and "raised by about 20%" in out, out
    out = m("Barclays had its price objective boosted by analysts from GBX 420 to GBX 500 in a report.", AAPL)
    assert "GBX" not in out and "raised by about 19%" in out, out
    out = m(
        "Apple had its price target cut by analysts at JPMorgan Chase & Co. from $215.00 to $175.00", AAPL
    )
    assert "$" not in out and "lowered by about 19%" in out, out  # an abbreviation's period ("Co.")
    out = m("Offering Of 7 Million Shares At $142.00 Per Share", AAPL)  # the whole amount, not "$142"
    assert "$142" not in out and "a per-share price" in out, out
    assert Masker.amount("1.209,24 USD") == 1209.24 and Masker.amount("GBX 1,410") == 1410.0


def test_scanner_sees_the_fourth_verification_forms() -> None:
    sc = scanner()
    for text, _ in REVISION4_GONE:  # as a state shows them, the company's name masked
        c = sc.scan_text(text.replace("Apple", "The company"), AAPL)
        assert c.price_levels + c.price_moves + c.dates + c.years >= 1, text
    for text in REVISION4_KEEP:
        c = sc.scan_text(text, AAPL)
        assert c.price_levels + c.price_moves + c.quotes == 0, text


def test_val_a_price_talk_below_target() -> None:
    """Price levels, ticker quotes and price moves (PREREG §6.3, §6.4) in the built val-A states, with the
    same 0.5% bar as names and dates (fourth verification; the scanner's broader price rules)."""
    path = ROOT / "artifacts" / "NA-04" / "leak_scan.csv"
    if not path.is_file():
        pytest.skip("artifacts/NA-04/leak_scan.csv is absent (run the report stage)")
    scan = pd.read_csv(path)
    for _, g in scan.loc[scan["masked"].astype(bool)].groupby("file"):
        assert ((g["price_moves"] + g["quotes"] + g["price_levels"]) > 0).mean() < 0.005
    twin = scan.loc[~scan["masked"].astype(bool)]
    assert ((twin["price_moves"] + twin["quotes"] + twin["price_levels"]) > 0).mean() > 0.05


# the fifth verification (revision 5): date forms the masker and the scanner both missed, and (operator
# decision 2026-10-26) every price move of any security and every index or commodity level
REVISION5_DATES = (
    ("24-Jun-2025. Apple. Investor Day.", "Jun"),
    ("by Theneighborhoodplugman | Jul, 2025", "Jul"),
    ("Sep nat-gas prices extended the drop.", "Sep"),
    ("StockSavvyThursday, Jul 3, 2025 4:24 am ET. 1min read.", "Thursday"),
    ("OnJuly 27, local time, the President stated", "July"),
    ("Financial Results for the half-year, 30thSeptember 2025.", "September"),
    ("It had an update when i turned it on. Recently july 14th.", "july"),
    ("ESTAug 22nd in the last two hours of trading", "Aug"),
    ("the top performer on September 23rd and 24th, 2025, injecting gains", "24th"),
    ("completing 53 aircraft by the 23rd of the month.", "23rd"),
    ("Apple FY-25 profit 47% as Costs Surge", "FY-25"),
    ("weight-loss data expected in 4th qtr", "qtr"),
    ("EPS Towards Upper Half Of Range - Update. 6/8 15:18. (RTTNews)", "6/8"),
    ("Coffee News Recap, 29 Aug: Keurig Dr Pepper seals deal", "Aug"),
    ("14:00/US: Jul Employment Trends Index. 14:00/US: Jan CPI", "Jan"),
    ("highest in more than two years in Aug, according to FAO", "Aug"),
    # the revision-5 build, read by hand
    ("AJuly filing shows that a senator reported a sale.", "July"),
    ("standalone net profit declines in the june 2025 quarter", "june"),
    ("tariffs-on-home-goods-effective-october-2025", "october"),
    ("julyinvestordeck", "july"),
    ("Boeing. Jul. 25. Boeing Reports Q2 Results.", "25"),
)
# remnants that only a masked text holds ("Jul. 25." → "Recently 25.")
REVISION5_MASKED_DATES = ("Boeing. Recently 25. Boeing Reports the quarter Results.",)
REVISION5_DATE_LOOKALIKES = (
    "the Del Mar Fairgrounds hosted the event",
    "Nový Battlefield bude",
    "Apple Surges to 77th in Daily Trading Volume",
    "ranked 24th in the Fortune list",
    "Augusta Farmers Coop",
    "Clare-Mar Farms Limited",
    "Recently 18:09 ET - News Release.",
)
# look-alikes the scanner must not count (spaCy reads this one as a person, so the masker test cannot use it)
REVISION5_SCANNER_LOOKALIKES = ("Archer Daniels the quarter Earnings: Will Soft Segment Trends Mar Results?",)
REVISION5_MOVES = (
    "The S&P 500 Index is up +0.20% today as tech leads.",
    "Nvidia dropped solidly by -3.50% on the session.",
    "Shares have added about 8.5% in that time frame, outpacing the S&P 500.",
    "The S&P 500 pulled back 0.17% to close at 5,069.76.",
    "Strength in the tech sector helped the Nasdaq add 1.7% and the Dow closed the session higher.",
    "Revenue rose 5%, sending shares up 2%.",
    "The Dow fell 300 points on Tuesday.",
    "Stock Market Today: Dow 46,414 Hits Record",
    "Stock Market Today: Dow Hits Record, Gold Surges to $3,816",
    "WTI crude settled at $63.56 a barrel.",
    "Bitcoin rebounded to $97,000.",
    "The 10-year Treasury yield rose to 4.25%.",
    "European stocks closed 0.6% lower.",
    "Microsoft rose 1.2% and Alphabet gained 0.8%.",
    "802.72 USD -22.59 (-2.74%) Volume: 2.0M.",
    # a market subject after the clause's fundamental, and commodity levels behind a level word
    "Strong earnings sent shares up 7%.",
    "Weak jobs data sent the Dow down 1.2%.",
    "Manufacturing stocks fell 2% on the report.",
    "Gold Falls Below $4,000",
    "Brent oil price drops to $64",
    # the recall sample of revision 5: a move named after the number, a subject elsewhere in the sentence
    "The company recently faced a 3% price decline over the last quarter.",
    "The company Announces Positive Phase 2 Results Amid 6% Quarterly Price Dip",
    "The company Sees 13% Weekly Drop;",
    "After a rally of 7.8% in a single week, shares of the company are catching investor attention.",
    "The S&P 500 has printed 55 record high closes and is riding a year gain of 26.8%.",
    "Shares of exchange operator the company rise as much as 1.9%, outperforming rivals;",
    "On the day: S&P 500 +1.2%;",
    "S&P 500 SP:SPX rises second consecutive week, adds 1.7%, aided by a solid jobs report",
    "The company Dives 37% on Lower Price Target, Pessimistic Rating",
    "US natgas prices edge up 1% ahead of storage report",
    "Berkshire Hathaway (BRK.B) saw a minor decline of 0.42% over the past week.",
    "Recent price decline (-1.02%) contrasts with strong institutional inflows.",
    "US Sanctions on Russian Oil Spark 5% Crude Price Surge, Rattle Global Markets",
    "Cencora (COR) faces mixed signals and a 1.24% recent price drop despite strong fundamentals.",
    # the revision-5 build, read by hand (val-A)
    "The blue-chip Dow followed its +500-point gain by selling off -316 points.",
    "Major indexes are in the green: the Dow is +67 points at this hour.",
    "FDA Approval Boosts nvo stock Despite 3.897% Dip on Earnings Volatility",
    "The company Options Sentiment Mixed Despite 1.47% Share Price Increase",
    "That reading put the index ahead on the week by 180 points.",
    "The company experienced a notable 68% price increase over the past quarter.",
    "The company saw a 17% upward price movement over the last month.",
    "The company traded 600M shares, ranking 234th in market activity with a 0.68% closing decline.",
    "The S&P 500 index reached an intraday record high of 6,565 points recently.",
    "Amcor's stock shows weak technical indicators and a 4.38% recent decline.",
    "Corpay (CPAY) faces a 9.52% 5-day decline amid mixed analyst ratings.",
    "Let's look at how major indexes are doing: S&P 500: +16.43 (+.30%) Nasdaq.",
    "New World extends gain to 7.7% as family weighs capital boost",
    "The company Lists Bio Protocol and Euler Spurring 18.99% BIO and 22.22% EUL Gains",
    "A Promising Partnership with Potential UpsideBX-1.48%.",
    "The recent 11.9% single-day plunge in.",
    "While the S&P Telecom Select Industry Index has recorded a 40%+ rise over the last year.",
    "Fees, Fines & Gains: Mastercard's 13% 3-Month Rise Laughs at Headlines",
    "When a Healthcare Giant Gets Sick: Elevance Health's 20% YTD Decline",
    "Micron Technology (MU) has seen a modest rise of 0.93% recently, but the technical outlook remains "
    "bearish.",
    "Dutch Bros (NYSE: BROS) is currently trading at 26% below its all-time high.",
    "Bitcoin Retakes $112K, SOL Hits 7-Month High",
    "Bitcoin's Sub-$110,000 Plunge Rattles Digital Asset Markets",
    "Crude Eyes $68: What's Moving Markets",
    "Rate Cut Euphoria Propels Bitcoin Towards $150,000 Mark",
    "Gold's Breakout Moment: Positioning for a $3,400 Threshold",
    "Bitcoin $200K?",
    "Energy services face mixed prospects amid $74–$90/b Brent crude prices.",
    "Wall Street Balances Shutdown Fears, Record Gold, and Nvidia’s $185 Rally",
    "The barley tender failed, triggering 15% CBOT barley futures surges.",
    "Shares fell 5% in reaction to weak sales.",
    "Shares jumped 5% after the price target was raised by about 10%.",
    "The stock has run roughly +69–71% year-to-date.",
    "Is This AI Stock -- a 251% Gainer Since Its IPO -- Becoming a Meme Stock?",
    "Wall Street is shifting into a risk-on mode, with the S&P 500 sitting just 2% shy of the record.",
    "The S&P 500 suffered its first “2% down day” in 356 days recently.",
    "ASX cops a beating with every sector hit, as Wall Street's 6% dive drags down miners and banks.",
    "Yields jumped 5% this week.",
)
REVISION5_FUNDAMENTALS = (
    "Revenue rose 5% year over year to $94.9 billion.",
    "Same-store sales increased 3.2%.",
    "Inflation rose 0.3% in the month.",
    "Unemployment ticked up to 4.3%.",
    "The quarter was marked by a 7.2% rise in sales and continued growth.",
    "Revenue: US$26.6b (up 8.2% from the year before)",
    "The company reported revenue of $1.94 billion, up 9.5% over the same period last year.",
    "Federal Realty booked a net profit margin of 27.2%, up from last year's 24%.",
    "The company Declared A Quarterly Dividend Of $0.84 Per Share, Representing An Increase Of 5.0% Versus "
    "Prior Year",
    "The firm also reported a 3 percent increase in preliminary full-year revenues.",
    "Energy giant raises $3B through three note tranches with yields up to 6.25%.",
    "Market share rose 2 points to 31%.",
    "The company cut 5% of its workforce.",
    "President's Day Sale - 70% Off.",
    # the precision sample of revision 5 (articles before the test period)
    "The oil and gas company reported $1.76 earnings per share (EPS) for the quarter.",
    "Major copper producer keeps dividend steady with $0.075 base plus $0.075 variable payout.",
    "The company Business Platinum $50 Hilton Credit No Longer Works on Gift Cards",
    "30%-50% Furniture Tariffs Slam Wayfair, RH Stocks",
    "The company's Long Position In H Shares Of COSCO Shipping Increases To 5.75%",
    "The projected upside for the SPDR Portfolio S&P 1500 Composite Stock Market ETF indicates a gain.",
    "The ISM manufacturing index rose 2 points to 49.",
    "U.S. MBA index shows 25% higher purchase activity.",
    "Outstanding shares fell 2% after the buyback.",
    "Earnings per share rose 10%.",
    "The Consumer Price Index rose 0.3% in the month.",
    "Gold production rose 5%.",
    "Tesla's deliveries jumped 20%.",
    "The company to add 20% more flights out of SFO.",
    "The company's tirzepatide showed an average weight loss of 20.2% vs. 13.7%.",
    "Short percent of float has risen 7.14% since its last report.",
    "The new processors deliver up to 35% higher performance.",
    "The drug showed a 68% lower death risk.",
    "The company decreased by 5.5% to $5.51 billion in the quarter.",
    "The company's ROE is 8.8%, lower than the industry's 11%.",
    "Financial giants have made a bullish move on the company, with 43% of traders bullish.",
    "The company announced a 5% price increase on its products.",
    "Restaurant Prices Are Up 4% as chains respond.",
    "EPS rose 12% to $1.20, beating estimates.",
    "The company issued bonds with a 5.5% coupon, up from 4.5%.",
    "ETF inflows rose 20% in the quarter.",
    "Analysts' price target on the shares increased 10%.",
    "The company: Losses Deepen 47% Annually, Profit Growth Outlook Tests Bullish Views",
    "The GDP growth rate for the last quarter surged to 3.8%, a turnaround from the previous quarter's "
    "contraction of -0.6%.",
    "Banking Stock: Dissecting a -19.71% Quarterly Revenue Decline Amid Growth",
    "Short Interest in the company Decreases By 6.6%",
    "The report finds global installs +11% YoY, sessions +16%.",
    "Analysts See +100% Upside",
    "US Economy Surges with Revised 3.8% the quarter GDP Growth",
    # the scanner's revision-5 hits, read by hand (val-A), and the verification's price script
    "The company has seen its institutional ownership surge to a remarkable 90.09%.",
    "Broadcom (NASDAQ:AVGO) jumps 46% YoY in AI sales to $4.4B.",
    "Revenue (GAAP) declined 42.4% year over year.",
    "The Consumer Price Index (CPI), which surprised markets by rising to 2.7% year-over-year, marks a "
    "juncture.",
    "The company Reports Quarterly Loss Despite 35% Sales Rise",
    "StepStone (STEP) AUM Jumps 18%",
    "SoftBank Sells 13M Shares for $3.02B; Ownership Drops Below 5%",
    "Cyber incidents in the region rose by 29% year-over-year.",
    "The short interest in the company's stock has decreased by 10.37% since its last report.",
    "The recent 66.21% price target increase for the company.",
    "Recent moves by Washington, such as taking a 10% share of a chipmaker.",
    "The company reports $2.06 trillion AUM, up 1.9% from previous month-end.",
    "The fund experienced a 2.9% decrease in units outstanding.",
    "While the Pending Home Sales Index (PHSI) rose 1.8% compared to the prior month.",
    "Retailers face 26% shoplifting surge, deploying AI locks.",
    "The company's Solar Stadium Push Drives 46.63% Trading Surge to 182nd in Market Activity",
    "Value Fund ETF (WTV) Potential 10% Gain: Analysts' Target Prices",
    "The company: European Stocks Are Forecast to Rise 5% After a Stellar Start",
    "The company Business Platinum $50 Hilton Credit No Longer Works",
    # the precision sample of the second revision-5 pass (articles before the test period)
    "The company, a REIT, reported 22% higher the year earnings ($3.42/share) and 94.1% occupancy.",
    "Delta Air Lines (NYSE:DAL) Reports 63% Increase In Net Income To US$2,130 Million",
    "Wall Street expects a 0.2% monthly overall increase and a 0.3% uptick in the core CPI.",
    "JP Morgan has raised the price target for Dell Technologies (DELL) raised by about 16%, a 16% increase.",
    "S&P 500 multifamily REIT the company, managing over 60000 apartment homes, announces earnings.",
    "Revenue growth of 5-10% is expected.",
    "The company Added as Top 10 Utility Dividend Stock With 2.71% Yield",
    "The Centers for Medicare & Medicaid Services (CMS) announced a 5.06% Medicare Advantage payment "
    "increase.",
    "The company the quarter Win: 65% Ad Surge Driven By Super Bowl, Tubi Growth",
    "The company Unveils 23-Point Action Plan Following Independent Business Audit",
    "Short Interest in Bank of America Co. (NYSE:BAC) Decreases By 8.1%",
    "The U.S. MBA Mortgage Refinance Index has surged to 1,596.7, reflecting a 1609.8-point increase.",
    "Revenue climbed 6% to $45 billion, fueled by higher premium yields and a 19% rise in policies.",
)


@pytest.mark.parametrize(("text", "gone"), REVISION5_DATES)
def test_revision5_dates(text: str, gone: str) -> None:
    out = m(text, AAPL)
    assert gone not in out, out


@pytest.mark.parametrize("text", REVISION5_DATE_LOOKALIKES)
def test_revision5_date_lookalikes_are_kept(text: str) -> None:
    assert m(text, AAPL) == text.replace("Apple", "The company")


@pytest.mark.parametrize("text", REVISION5_MOVES)
def test_revision5_every_price_move_goes(text: str) -> None:
    assert Masker.has_market_move(text), text
    assert not re.search(r"\d+(?:\.\d+)?\s?%|\d{1,3},\d{3}|\$\d", m(text, AAPL)), m(text, AAPL)


@pytest.mark.parametrize("text", REVISION5_FUNDAMENTALS)
def test_revision5_fundamental_percents_stay(text: str) -> None:
    assert not Masker.has_market_move(text), text


def test_scanner_sees_the_fifth_verification_forms() -> None:
    sc = scanner()
    for text, _ in REVISION5_DATES:
        c = sc.scan_text(m_raw_dates(text), AAPL)
        assert c.dates + c.years >= 1, text
    for text in REVISION5_MASKED_DATES:
        assert sc.scan_text(text, AAPL).dates >= 1, text
    for text in REVISION5_DATE_LOOKALIKES + REVISION5_SCANNER_LOOKALIKES:
        assert sc.scan_text(text, AAPL).dates == 0, text
    for text in REVISION5_MOVES:
        c = sc.scan_text(text.replace("Apple", "The company"), AAPL)
        assert c.price_moves + c.price_levels + c.quotes >= 1, text
    for text in REVISION5_FUNDAMENTALS:
        c = sc.scan_text(text, AAPL)
        assert c.price_moves + c.price_levels == 0, (text, c)


def m_raw_dates(text: str) -> str:
    """The text as the old masker left it (years masked, the rest as written): what the scanner reads."""
    return re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", "the year", text)
