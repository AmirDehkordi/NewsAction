"""PRD NA-02 S9: source classes; every top-100 member domain is classified explicitly."""

from __future__ import annotations

import pandas as pd
import pytest

from newsaction.news import sources
from newsaction.paths import ROOT


def test_classify_examples() -> None:
    sm = sources.load_source_map()
    assert sm.classify("www.prnewswire.com") == "press_wire_primary"
    assert sm.classify("it.marketscreener.com") == "aggregator"
    assert sm.classify("uk.finance.yahoo.com") == "aggregator"
    assert sm.classify("investor.apple.com") == "press_wire_primary"
    assert sm.classify("marketbeat.com") == "auto_generated"
    assert sm.classify("reuters.com") == "major_outlet"
    assert sm.classify("some-blog.example") == "other"
    assert sm.classify(None) == "other"


def test_vendor_primary_flag_overrides_the_domain() -> None:
    dom = pd.Series(["marketbeat.com", "marketbeat.com", None])
    prim = pd.Series([True, None, True], dtype="boolean")
    assert sources.source_class(dom, prim).tolist() == [
        "press_wire_primary",
        "auto_generated",
        "press_wire_primary",
    ]
    assert sources.source_class_domain(dom).tolist() == ["auto_generated", "auto_generated", "other"]


def test_config_lists_each_domain_once_with_valid_classes() -> None:
    sm = sources.SourceMap.from_yaml()
    assert set(sm.domains.values()) <= set(sources.SOURCE_CLASSES)


def test_top_100_domains_are_listed_explicitly() -> None:
    path = ROOT / "artifacts" / "NA-02" / "top_domains.csv"
    if not path.is_file():
        pytest.skip("artifacts/NA-02/top_domains.csv absent (run scripts/na02_report.py)")
    top = pd.read_csv(path).head(100)
    sm = sources.load_source_map()
    missing = [d for d in top["domain"] if sources.normalize_domain(d) not in sm.domains]
    assert missing == []
