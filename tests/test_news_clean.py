"""PRD NA-02 S4: cleaning flags (13F / Form-4 title patterns, junk tags, third-party rule)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from newsaction.news import clean, load
from newsaction.paths import ROOT

THIRTEEN_F = [
    "Mariner LLC Has $279.27 Million Stock Position in Visa Inc. (NYSE:V)",
    "Northern Trust Corp Sells 197,655 Shares of T-Mobile US, Inc. $TMUS",
    "NVIDIA Corporation $NVDA Shares Sold by ORG Wealth Partners LLC",
    "9,863 Shares in Fiserv, Inc. $FI Acquired by Oliver Lagore Vanvalin Investment Group",
    "Alpha Wealth Funds LLC Buys Shares of 13,441 Apple Inc. (NASDAQ:AAPL)",
    "Ross Stores, Inc. (NASDAQ:ROST) is Marshfield Associates' Largest Position",
    "State Street Corp Purchases 104,521 Shares of The Cooper Companies, Inc. (NASDAQ:COO)",
    "Congress Asset Management Co. Has $143.92 Million Position in Parker-Hannifin Corporation $PH",
    "Treasurer of the State of North Carolina Acquires 1,251 Shares of Stryker Co. (NYSE:SYK)",
    "EagleClaw Capital Managment, LLC's Sysco Corp(SYY) Holding History",
]
NOT_THIRTEEN_F = [
    "Insider Selling: Datadog (NASDAQ:DDOG) CTO Sells 43,106 Shares of Stock",
    "Mani Sundaram Sells 10,683 Shares of Akamai Technologies, Inc. (NASDAQ:AKAM) Stock",
    "Rep. Jefferson Shreve Purchases Shares of Synopsys, Inc. (NASDAQ:SNPS)",
    "Nvidia takes stake in Intel",
    "Warren Buffett's Berkshire Hathaway Just More Than Tripled Its Stake in Alphabet",
    "Acme Reports Record Quarterly Revenue",
]
FORM4 = [
    "Insider Selling: Datadog (NASDAQ:DDOG) CTO Sells 43,106 Shares of Stock",
    "Walmart Inc. (NYSE:WMT) EVP John D. Rainey Sells 2,200 Shares",
    "Salesforce Insider Sold Shares Worth $597,990, According to a Recent SEC Filing",
    "HIMS insider files to sell 60,000 shares worth $3.2M (Form 144)",
    "Mani Sundaram Sells 10,683 Shares of Akamai Technologies, Inc. (NASDAQ:AKAM) Stock",
]


@pytest.mark.parametrize("title", THIRTEEN_F)
def test_13f_positive(title: str) -> None:
    assert clean.load_title_patterns().is_13f(title)


@pytest.mark.parametrize("title", NOT_THIRTEEN_F)
def test_13f_negative(title: str) -> None:
    assert not clean.load_title_patterns().is_13f(title)


@pytest.mark.parametrize("title", FORM4)
def test_form4_positive(title: str) -> None:
    assert clean.load_title_patterns().is_form4(title)


def test_form4_negative() -> None:
    pat = clean.load_title_patterns()
    assert not pat.is_form4(THIRTEEN_F[8])  # a state treasurer is a 13F filer, not an insider
    assert not pat.is_form4("Acme names Jane Doe CFO")


def test_clean_flags_and_third_party() -> None:
    df = pd.DataFrame(
        {
            "title": [THIRTEEN_F[0], "Acme beats estimates", "Acme beats estimates", FORM4[0]],
            "tag_type": ["insider_ownership", "price_commentary", "earnings_results", "insider_ownership"],
            "non_news": pd.array([False, None, True, False], dtype="boolean"),
            "parsing_allowed": pd.array([True, None, False, True], dtype="boolean"),
        }
    )
    f = clean.clean_flags(df)
    assert f["is_13f"].tolist() == [True, False, False, False]
    assert f["junk_tag"].tolist() == [False, True, False, False]
    assert f["non_news"].tolist() == [False, False, True, False]
    assert f["is_form4"].tolist() == [False, False, False, True]
    assert f["third_party_ok"].tolist() == clean.third_party_ok(df["parsing_allowed"]).tolist()
    assert clean.passes_clean(f).tolist() == [False, False, False, False]


def test_third_party_ok_none_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """PREREG §6.1 / CLAUDE.md D15: False never leaves the machine; None only when the operator allowed it."""
    pa = pd.Series(pd.array([True, None, False], dtype="boolean"))
    assert clean.third_party_ok(pa, none_ok=True).tolist() == [True, True, False]
    assert clean.third_party_ok(pa, none_ok=False).tolist() == [True, False, False]
    for policy, expected in [("allow", [True, True, False]), ("exclude", [True, False, False])]:
        monkeypatch.setattr(clean, "none_policy", lambda p=policy: p)
        assert clean.third_party_ok(pa).tolist() == expected
    monkeypatch.setattr(clean, "none_policy", lambda: "pending_operator")
    assert clean.third_party_ok(pa).tolist() == [True, False, False]  # undecided counts as excluded


@pytest.mark.parametrize("value", clean.NONE_POLICIES)
def test_none_policy_reads_frozen(tmp_path: Path, value: str) -> None:
    p = tmp_path / "frozen.yaml"
    p.write_text(f"news:\n  parsing_allowed_none: {value}\n", encoding="utf-8")
    assert clean.none_policy(p) == value


def test_none_policy_missing_or_unknown(tmp_path: Path) -> None:
    p = tmp_path / "frozen.yaml"
    p.write_text("news: null\n", encoding="utf-8")
    assert clean.none_policy(p) == "pending_operator"
    p.write_text("news:\n  parsing_allowed_none: maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="parsing_allowed_none"):
        clean.none_policy(p)


def test_summary_present() -> None:
    import pyarrow as pa

    s = pa.array(["A summary.", None, "", " nan ", "None"], type=pa.large_string())
    assert load.summary_present(s).to_pylist() == [True, False, False, False, False]


def test_judged_sample_meets_the_precision_bar() -> None:
    """AC5: the final judged round of artifacts/NA-02/spam_judgments.csv has 13F precision >= 0.95."""
    path = ROOT / "artifacts" / "NA-02" / "spam_judgments.csv"
    if not path.is_file():
        pytest.skip("spam_judgments.csv absent")
    j = pd.read_csv(path)
    final = j[(j["round"] == j["round"].max()) & (j["sample"] == "flagged")]
    assert len(final) == 200
    assert final["judged_13f"].mean() >= 0.95
    assert final["flagged_by_final_regex"].all()
