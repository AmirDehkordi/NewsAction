"""PRD NA-04 S3 / AC2: masking and the residual-leak scanner.

Golden cases cover the curated aliases (Google for Alphabet, Facebook for Meta, …), ticker forms, people,
dates, fiscal periods, price talk and price levels, including every leak the NA-04 verification found
(BOATS:NEE/PT, ODFL's, MSFT-1.19%, "Second Quarter", "25 septembre", "4/15", Super Micro Computer, …). The
mutation "empty the alias list" turns the curated-alias cases red. The scanner is checked to be independent
of the masker (its imports), and the val-A leak rates of the built states are read from
artifacts/NA-04/leak_scan.csv.
"""

from __future__ import annotations

import ast
import re
from dataclasses import replace
from functools import cache

import pandas as pd
import pytest

from newsaction import io
from newsaction.paths import ROOT
from newsaction.states.mask import CompanyAliases, Masker, build_aliases, load_alias_config, name_variants
from newsaction.states.scan import LeakScanner, harvest_names

AAPL, GOOGL, META, LLY, HD, PANW, JPM, BAC = 6, 649, 946, 876, 691, 1111, 808, 145
NEE, ODFL, MSFT, SPGI, WFC, PGR, SMCI, WAB, DD, PEG, DAL, CPB, DASH, NOW = (
    1033, 1088, 996, 1340, 1555, 1147, 1320, 1537, 405, 1136, 401, 344, 403, 1057
)  # fmt: skip


@cache
def aliases() -> dict[int, CompanyAliases]:
    if not (ROOT / "work" / "panel" / "companies.parquet").is_file():
        pytest.skip("work/panel/companies.parquet is absent")
    comp = io.read_parquet("panel/companies.parquet", columns=["symbol_id", "company_id", "ticker", "name"])
    return build_aliases(comp)


@cache
def masker() -> Masker:
    return Masker(aliases(), surnames=frozenset({"Bessent"}))


@cache
def companies() -> pd.DataFrame:
    return io.read_parquet("panel/companies.parquet", columns=["company_id", "ticker", "name"])


@cache
def scanner() -> LeakScanner:
    """The independent scanner with a small hand-made harvest (the report stage harvests the corpus)."""
    return LeakScanner(
        companies(), [(META, "FB")], {GOOGL: ["Google"], META: ["Facebook"]}, frozenset({"price"})
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
    out = m("ServiceNow (NYSE: NOW) beats; NOW is the time", NOW)
    assert out.count("NOW") == 1 and "ServiceNow" not in out  # a stoplisted bare word stays, the form goes
    assert "NOW's" not in m("NOW's guidance", NOW)  # ... but not as a possessive
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
