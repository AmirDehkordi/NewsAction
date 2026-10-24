"""configs/news.yaml equals docs/PREREG.md where PREREG fixes a value; news columns are registered (A5–A6)."""

from __future__ import annotations

import pytest

from newsaction import pit
from newsaction.news import build, load_news_config, mapping
from newsaction.paths import ROOT

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")


def test_dedupe_and_novelty_constants() -> None:
    cfg = load_news_config()
    assert (cfg.dedupe.cosine, cfg.dedupe.window_hours) == (0.93, 72)
    assert "bge cosine ≥ 0.93 within 72 h, same company" in PREREG  # §6.2
    assert cfg.novelty.window_days == 7
    assert "t_avail strictly earlier, within 7 days" in PREREG  # §6.5


def test_junk_tags_and_cutoffs() -> None:
    cfg = load_news_config()
    assert set(cfg.junk_tags) == {"price_commentary", "promotional_content"}
    assert "`tag_type` ∈ {price_commentary, promotional_content}" in PREREG  # §6.2
    assert cfg.audit.leak_t == 2.0 and "(t > 2)" in PREREG  # §6.4
    assert cfg.audit.nw_lags == 5 and "Newey–West with 5 lags" in PREREG  # §11.1


def test_sentiment_scale_is_symmetric() -> None:
    scale = load_news_config().sentiment_scale
    assert sorted(scale.values()) == [-2, -1, 0, 1, 2]
    assert scale["Strongly Negative"] == -scale["Strongly Positive"]


def test_alias_kinds() -> None:
    aliases = load_news_config().mapping.aliases
    assert {a.kind for a in aliases} <= {"rename", "class", "restrict"}
    assert len({(a.ticker, a.symbol_id) for a in aliases}) == len(aliases)
    assert mapping.normalize_symbol  # tickers are normalized when the map is built


def test_every_output_column_is_registered() -> None:
    reg = pit.default_registry()
    for col in build.OUTPUT_COLUMNS:
        reg.kind(col)


@pytest.mark.parametrize(
    "col",
    [
        "tag_type",
        "sentiment_direction",
        "event_age_days",
        "source_class",
        "keep",
        "summary_present",
        "dup_count",
    ],
)
def test_vendor_and_future_columns_are_never_state_inputs(col: str) -> None:
    for point in ("D0", "D1", "D2"):
        with pytest.raises(pit.PITError):
            pit.check_inputs([col], point)  # type: ignore[arg-type]


def test_text_columns_are_w0() -> None:
    pit.check_inputs(["title_clean", "snippet_clean", "novelty", "source_class_domain", "dup_count_w0"], "D0")
    with pytest.raises(pit.PITError):
        pit.check_inputs(["dup_count_w2"], "D0")
