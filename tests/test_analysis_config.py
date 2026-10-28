"""configs/analysis.yaml equals the numbers PREREG gives (§1.1–1.3, §11.1–11.4, A1.2–A1.5, A3.3, the operator
rows),
and the price-move pattern of the operator's robustness (a) matches what the row lists."""

from __future__ import annotations

import pytest

from newsaction.analysis import spec
from newsaction.paths import ROOT

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")


def test_numbers_match_prereg() -> None:
    cfg = spec.load_config()
    assert "Stationary block bootstrap over days, block 5, 10,000 reps, seed 2026" in PREREG
    assert (cfg.bootstrap.block, cfg.bootstrap.reps, cfg.bootstrap.seed) == (5, 10_000, 2026)
    assert "Newey–West with 5 lags" in PREREG and cfg.metrics.nw_lags == 5
    assert "ECE (15 bins)" in PREREG and cfg.metrics.ece_bins == 15
    assert "3 classes split at ±0.5σ" in PREREG and cfg.metrics.class_band == 0.5
    assert "AUC for |z| ≥ 1" in PREREG and cfg.metrics.auc_abs_z == 1.0
    assert "Holm-corrected, family α = 0.05" in PREREG
    assert cfg.multiple_testing.primary.alpha == 0.05 and cfg.multiple_testing.primary.tests == (
        "H1",
        "H1b",
        "H2",
        "H3",
        "H4",
    )
    assert (cfg.h1b.signal, cfg.h1b.target) == ("a0_n_hat", "z_id")  # H1b: PREREG §15 NA-11 row
    assert "Benjamini–Hochberg, q = 0.10" in PREREG
    assert cfg.multiple_testing.secondary.q == cfg.multiple_testing.heterogeneity.q == 0.10
    assert "Driscoll–Kraay (5 lags)" in PREREG and cfg.inference.dk_lags == 5
    assert cfg.inference.fe == ("session", "tier") and cfg.inference.cluster == ("session", "company_id")
    assert "the first h with λ_h ≥ 0.5" in PREREG and cfg.convergence.half_life_lambda == 0.5
    assert "h* = t+20 is the equilibrium horizon; t+5 is the short equilibrium" in PREREG
    assert (cfg.convergence.h_star, cfg.convergence.h_short, cfg.convergence.h_star_robust) == (
        "C_t+20",
        "C_t+5",
        "C_t+10",
    )
    assert "mean CAR^lvl over t+16..t+20" in PREREG and cfg.convergence.plateau == (16, 20)
    assert "explained* (X ≥ 0.5)" in PREREG and cfg.explanation.explained_x == 0.5
    assert "first event per company per 5 sessions" in PREREG and cfg.robustness.non_overlap_sessions == 5
    assert "y2 = AR(O_{t+1}→C_{t+5}) (primary)" in PREREG
    assert cfg.h2.primary_point == "D2" and cfg.h2.points["D2"].y == "y2" and cfg.h2.points["D2"].g == "g_d2"


def test_operator_rows_before_na11() -> None:
    cfg = spec.load_config()
    assert "They join the six in one BH family (≤ 8 cuts)" in PREREG
    assert len(cfg.cuts.list) == 8
    assert cfg.cuts.list["busy_day"].at_least == 1.5
    assert cfg.cuts.list["usual_coverage_low"].below_median_by == ("session", "tier")
    assert cfg.robustness.timing_strata_et == ("04:00", "08:00", "09:15")


def test_ladder_rungs_are_a12s() -> None:
    cfg = spec.load_config()
    assert list(cfg.convergence.ladder) == [
        "O_t",
        "10:00",
        "C_t",
        "C_t+1",
        "C_t+2",
        "C_t+5",
        "C_t+10",
        "C_t+20",
    ]
    assert list(cfg.convergence.gap["D2"].rungs) == ["C_t+1", "C_t+5", "C_t+20"]
    assert list(cfg.convergence.gap["D1"].rungs) == ["C_t", "C_t+1", "C_t+5", "C_t+20"]


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("Shares of the company rose 4% after the report", True),
        ("the company's stock fell sharply on the news", True),
        ("The stock is trading higher", True),
        ("Pre-market movers: the company", True),
        ("the company gains in premarket trading", True),
        ("after-hours trading", True),
        ("3 things to know today", True),
        ("Barron's: Stock Market Today: Dow slips", True),
        ("Nasdaq climbs: Stock Market Today", True),
        ("Live Coverage: earnings", True),
        ("The company raised its dividend by 5%", False),
        ("Stocks rally as yields fall", False),  # the market, not the company's shares
        ("Analyst upgrades the company to buy", False),
        ("The company reports record quarterly revenue", False),
    ],
)
def test_price_move_text_pattern(text: str, hit: bool) -> None:
    import json

    state = json.dumps(
        {"news": [{"headline": text, "snippet": ""}], "market": {"scheduled_releases_today": "x"}}
    )
    assert spec.price_move_text(state, spec.load_config()) is hit


def test_price_move_text_reads_only_the_news_block() -> None:
    import json

    state = json.dumps(
        {"market": {"scheduled_releases_today": "CPI today"}, "news": [{"headline": "Deal signed"}]}
    )
    assert spec.price_move_text(state, spec.load_config()) is False


def test_timing_strata() -> None:
    cfg = spec.load_config()
    out = spec.timing_stratum([-60, 0, 239, 240, 479, 480, 555, 556, float("nan")], cfg)
    assert out.tolist() == [
        "before_04:00",
        "before_04:00",
        "before_04:00",
        "04:00_08:00",
        "04:00_08:00",
        "08:00_09:15",
        "08:00_09:15",
        None,
        None,
    ]


def test_live_format_reads_headlines_only() -> None:
    import json

    cfg = spec.load_config()
    title = json.dumps(
        {"news": [{"headline": "Dow Leads as Merck Gains: Stock Market Today", "snippet": ""}]}
    )
    snippet = json.dumps({"news": [{"headline": "Deal", "snippet": "a standout in the stock market today"}]})
    assert spec.live_format(title, cfg) and not spec.live_format(snippet, cfg)
