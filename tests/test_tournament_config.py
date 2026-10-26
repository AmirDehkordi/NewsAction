"""configs/tournament.yaml must equal docs/PREREG.md §8.2–8.3 and §11.1–11.2.

Every number PREREG gives is checked against the PREREG text; the val-B gate stays closed until the
hand-off."""

from __future__ import annotations

from newsaction.config import load_frozen, load_project
from newsaction.paths import ROOT
from newsaction.tournament import load_tournament_config

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")


def test_samples_and_mcs_match_prereg() -> None:
    c = load_tournament_config()
    assert "all eligible models × 700 val-A D0 events, stratified by tier × month (seed 2026)" in PREREG
    assert (c.samples.stage1, c.seed, tuple(c.samples.strata)) == (700, 2026, ("tier", "month"))
    assert c.seed == load_project().seeds["global"]
    assert "≤ 6 survivors (highest stage-1 IC; ties go to the cheaper model) × 3,000 val-A events" in PREREG
    assert (c.stage2.max_models, c.samples.stage2) == (6, 3000)
    assert "Counterfactual flip rate (200 edited states" in PREREG and c.samples.counterfactual == 200
    mcs_text = "Model Confidence Set at α = 0.10, using a stationary block bootstrap over days"
    assert f"{mcs_text} (block 5, 10,000 reps)" in PREREG
    assert (c.mcs.alpha, c.mcs.block, c.mcs.reps) == (0.10, 5, 10000)
    assert "500-event validity sample in NA-06 stage 2" in PREREG and c.samples.reading_validity == 500
    assert c.samples.exclude_embargo and "first 5 sessions of val-A, val-B and test" in PREREG


def test_metric_constants_match_prereg() -> None:
    m = load_tournament_config().metric
    assert (
        "**Primary metric:** mean daily Spearman IC of N̂ vs. z_cc,t." in PREREG and m.primary_target == "z_cc"
    )
    assert "Newey–West with 5 lags on the daily series" in PREREG and m.nw_lags == 5
    assert "ECE (15 bins)" in PREREG and m.ece_bins == 15
    assert "3 classes split at ±0.5σ" in PREREG and m.class_band == 0.5


def test_encoding_and_battery() -> None:
    c = load_tournament_config()
    assert "The default before NA-07 is **E3**." in PREREG and c.encoding == "E3"
    assert c.groups == ("core",)
    assert c.reading_validity.groups == ("core", "extended")
    assert c.state_files.call_a.endswith("callA_d0_E3.parquet") and c.state_files.call_b.endswith(
        "callB_d2_E3.parquet"
    )


def test_probe_tags_are_registered_where_needed() -> None:
    from newsaction.dm import dm_config

    c = load_tournament_config()
    assert c.probes.tags.unmasked in dm_config().registered_probes
    assert len(c.probes.option_keys) == 4  # 1 of 4 candidates (PREREG §8.3)
    assert c.probes.company.instructions == "Which company is this news most likely about?"  # PRD NA-06 S4a
    assert (c.probes.month.first, c.probes.month.last) == ("2024-07", "2025-12")  # PRD NA-06 S4b


def test_val_b_gate_follows_the_tournament() -> None:
    """allow_val_b may be true only once frozen.yaml records the tournament (CLAUDE.md C13)."""
    f = load_frozen()
    if f.allow_val_b:
        assert f.tournament and f.tournament.get("leaderboard_sha")
