"""PRD NA-04 S3 / AC2: masking and the residual-leak scanner.

Golden cases cover the curated aliases (Google for Alphabet, Facebook for Meta, …), ticker forms, people,
dates, fiscal periods and price talk. The mutation "empty the alias list" turns the curated-alias cases red.
The val-A leak rates of the built states are read from artifacts/NA-04/leak_scan.csv.
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import cache

import pandas as pd
import pytest

from newsaction import io
from newsaction.paths import ROOT
from newsaction.states.mask import CompanyAliases, Masker, build_aliases, load_alias_config, name_variants
from newsaction.states.scan import LeakScanner

AAPL, GOOGL, META, LLY, HD, PANW, JPM, BAC = 6, 649, 946, 876, 691, 1111, 808, 145


@cache
def aliases() -> dict[int, CompanyAliases]:
    if not (ROOT / "work" / "panel" / "companies.parquet").is_file():
        pytest.skip("work/panel/companies.parquet is absent")
    comp = io.read_parquet("panel/companies.parquet", columns=["symbol_id", "company_id", "ticker", "name"])
    return build_aliases(comp)


@cache
def masker() -> Masker:
    return Masker(aliases())


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
    out = m("ServiceNow (NYSE: NOW) beats; NOW is the time", 1057)
    assert out.count("NOW") == 1 and "ServiceNow" not in out  # a stoplisted bare word stays, the form goes
    assert "AAPL" not in m("APPLE AND AAPL TO REPORT RESULTS", AAPL, title=True)
    assert "AAPLX" in m("AAPLX fund", AAPL)  # whole words only


def test_other_companies_are_not_masked() -> None:
    out = m("Apple and Microsoft settle; Goldman Sachs advised", AAPL)
    assert "Microsoft" in out and "Goldman Sachs" in out and "Apple" not in out


def test_people() -> None:
    out = m("Apple CEO Tim Cook said demand was strong, according to Tim Cook.", AAPL)
    assert "Tim" not in out and "Cook" not in out
    assert "CEO said" in out
    out = m("Mark Zuckerberg's memo leaked", META, title=True)
    assert "Zuckerberg" not in out and "a person's memo" in out.lower()


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
    scanner = LeakScanner(aliases())
    assert scanner.residual_leaks(leaked, GOOGL).names >= 1
    assert scanner.residual_leaks(m(text, GOOGL), GOOGL).names == 0


def test_scanner_counts() -> None:
    sc = LeakScanner(aliases())
    c = sc.residual_leaks('{"headline":"apple (AAPL) said on Monday, Oct. 3 that 2025 sales $AAPL"}', AAPL)
    assert c.names == 1 and c.tickers == 2 and c.years == 1 and c.dates >= 2
    clean = sc.residual_leaks('{"headline":"the company said recently that the year sales rose"}', AAPL)
    assert clean.as_dict() == {"names": 0, "tickers": 0, "years": 0, "dates": 0}
    assert sc.residual_leaks("Target price raised", 1416).names == 1  # a common-word name counts as written
    assert sc.residual_leaks("a price target raised", 1416).names == 0


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
