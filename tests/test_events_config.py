"""configs/events.yaml equals PREREG §6.6–6.9, A1.2 and PRD NA-03 (each value is also found in the text)."""

from __future__ import annotations

from datetime import date

import pytest

from newsaction.events import load_events_config
from newsaction.paths import ROOT

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
PRD = (ROOT / "NewsAction PRD.md").read_text(encoding="utf-8")

HARD = (
    "earnings_results, guidance_outlook, analyst_action, ma_deal, legal_regulatory, financing_dilution, "
    "capital_returns"
)
MATERIAL = (
    f"{HARD}, leadership_governance, operations_supply, partnership_customer, product_launch, competition"
)


def test_tag_sets_equal_prereg() -> None:
    f = load_events_config().filters
    assert f"MATERIAL = {{{MATERIAL}}}" in PREREG
    assert f"HARD = {{{HARD}}}" in PREREG
    assert ", ".join(f.material_tags) == MATERIAL
    assert ", ".join(f.hard_tags) == HARD


def test_rule_filter_fields() -> None:
    f = load_events_config().filters
    assert "sentiment ≠ Neutral ∩ `event_age_days == 0`" in PREREG
    assert "intensity ∈ {Immediate, Short-Term}" in PREREG
    assert "source class ∈ {press wire / primary source, major outlet}" in PREREG
    assert f.neutral_sentiment == "Neutral"
    assert f.timely_intensity == ("Immediate", "Short-Term")
    assert f.quality_sources == ("press_wire_primary", "major_outlet")
    assert "16 embedding PCs" in PREREG and f.pca_components == 16
    assert "articles today / 60-session mean" in PRD and f.attention_lookback == 60


def test_label_constants() -> None:
    lab = load_events_config().label
    assert "|z_on,t| ≥ 2;" in PREREG
    assert "|Σ_{j=0..5} AR_cc,t+j| / (σ_cc·√6) ≥ 2;" in PREREG
    assert "z_vol,t ≥ 2." in PREREG
    assert "(|z_on| < 1 and |CAR z over t+1..t+5| ≥ 2)" in PREREG
    assert (lab.material_on_z, lab.material_car_days, lab.material_car_z, lab.material_vol_z) == (
        2.0,
        6,
        2.0,
        2.0,
    )
    assert (lab.delayed_on_max, lab.delayed_car_days, lab.delayed_car_z) == (1.0, 5, 2.0)


def test_fit_and_tune_windows() -> None:
    lc = load_events_config().learned
    assert "fit on 2024-07-01 → 2025-03-31 (purged) and tuned on 2025-04-01 → 2025-06-30" in PREREG
    assert (lc.fit.start, lc.fit.end) == (date(2024, 7, 1), date(2025, 3, 31))
    assert (lc.tune.start, lc.tune.end) == (date(2025, 4, 1), date(2025, 6, 30))
    assert lc.label_horizon == 5


def test_comparison_protocol() -> None:
    c = load_events_config().compare
    assert "selected ticker-days ≤ 30% of covered member-days" in PREREG and c.budget_share == 0.30
    assert "Ties (< 1 pp) go to fewer inputs, in the order F1 < F2 < F3 < F4 < F5 < F6." in PREREG
    assert c.tie_pp == 0.01
    assert c.tie_order == ("F1", "F2", "F3", "F4", "F5", "F6")
    assert len(c.frontier_shares) == 10 and "10\n    thresholds" in PRD


def test_event_constants() -> None:
    e = load_events_config().events
    assert "At most 6 articles (highest filter score after deduplication) and ≤ 600 news tokens" in PREREG
    assert (e.max_articles, e.max_news_tokens) == (6, 600)
    assert e.tokenizer == "answerdotai/ModernBERT-large"
    assert "h ∈ {1, 2, 5, 10, 20}" in PRD and e.clean_horizons == (1, 2, 5, 10, 20)


def test_projection_constants() -> None:
    p = load_events_config().projection
    assert "$0.01, $0.02,\n    $0.042, $0.10, $0.24 per M" in PRD
    assert p.usd_per_m == (0.01, 0.02, 0.042, 0.10, 0.24)
    assert (p.context_tokens, p.core_question_tokens, p.extended_question_tokens) == (250, 350, 600)
    assert p.flag_usd_per_m == 0.042 and p.chunk == "NA-11"


def test_config_rejects_hard_outside_material(tmp_path: pytest.TempPathFactory) -> None:
    from pydantic import ValidationError

    from newsaction.events import FilterConfig

    f = load_events_config().filters.model_dump()
    f["hard_tags"] = (*f["hard_tags"], "macro_sector")
    with pytest.raises(ValidationError):
        FilterConfig.model_validate(f)
