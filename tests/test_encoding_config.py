"""configs/encoding.yaml must equal docs/PREREG.md §8.4, §6.11, §11.1, §11.4 and PRD NA-07 (S1–S4).

Every number the PREREG or the PRD gives is checked against their text; the models are the operator's three
of the §15 row of 2026-10-27, and the numeracy grid is NA-05's."""

from __future__ import annotations

import re

import pytest

from newsaction.config import load_project
from newsaction.dm.canary import NUMERACY_Z
from newsaction.encoding import load_encoding_config
from newsaction.paths import ROOT
from newsaction.tournament import load_tournament_config

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
PRD = (ROOT / "NewsAction PRD.md").read_text(encoding="utf-8")
RULES = PREREG[
    PREREG.index("- **8.4 Encoding and anchoring (NA-07).**") : PREREG.index("- **8.5 Final selection")
]
PROMPT = PRD[PRD.index("You are implementing NA-07") : PRD.index("### Verification prompt — NA-07")]


def prereg_rules() -> dict[str, float]:
    """The numbers of PREREG §8.4's encoding and anchoring rules."""
    se = re.search(r"worse than (E\d) on val-B by more than (\d+(?:\.\d+)?) SE \(then (E\d)\)", RULES)
    num = r"(\d+(?:\.\d+)?)"
    anc = re.search(rf"slope of Call B's N̂ on G is ≥ {num} or corr\(N̂_A, N̂_B\) < {num}", RULES)
    assert se is not None and anc is not None
    assert se.group(1) == se.group(3)
    return {
        "confirm_se": float(se.group(2)),
        "slope_min": float(anc.group(1)),
        "corr_max": float(anc.group(2)),
        "default": se.group(1),  # type: ignore[dict-item]
    }


def test_rule_thresholds_are_prereg() -> None:
    c = load_encoding_config()
    r = prereg_rules()
    assert c.rule.confirm_se == pytest.approx(r["confirm_se"])
    assert c.anchoring.slope_min == pytest.approx(r["slope_min"])
    assert c.anchoring.corr_max == pytest.approx(r["corr_max"])
    assert c.default_encoding == r["default"] == "E3"
    assert "The default before NA-07 is **E3**." in PREREG
    assert "If anchoring is present, N̂ always comes from Call A (two calls per event)." in RULES


def test_encodings_are_prereg() -> None:
    c = load_encoding_config()
    table = PREREG[PREREG.index("**Encodings:**") : PREREG.index("The default before NA-07")]
    assert tuple(re.findall(r"^\| (E\d) \|", table, flags=re.MULTILINE)) == c.encodings == (
        "E0", "E1", "E2", "E3", "E4",
    )  # fmt: skip


def test_metric_and_bootstrap_match_prereg_and_na06() -> None:
    c, t = load_encoding_config(), load_tournament_config()
    assert "Newey–West with 5 lags on the daily series" in PREREG and c.metric.nw_lags == 5
    assert "Stationary block bootstrap over days, block 5, 10,000 reps, seed 2026." in PREREG
    assert (c.bootstrap.block, c.bootstrap.reps, c.seed) == (5, 10000, 2026)
    assert c.seed == load_project().seeds["global"]
    # NA-06's daily IC (PREREG §15 row of 2026-10-26), so NA-07's ICs are comparable with the leaderboard
    assert (c.metric.target, c.metric.min_names_per_day) == (
        t.metric.primary_target,
        t.metric.min_names_per_day,
    )
    assert c.groups == ("core",) and "the encoding/anchoring study" in PREREG  # A2.1: core battery only


def test_samples_and_probe_sizes_match_prd() -> None:
    c = load_encoding_config()
    assert "E0–E4 × the 1,500 val-A sample (Call A)" in PROMPT and c.samples.val_a == 1500
    assert "on the 1,500 val-B sample in {best, E3}" in PROMPT and c.samples.val_b == 1500
    assert "30 real masked val-A news blocks" in PROMPT and c.numeracy.n_news == 30
    assert "7 magnitudes (negligible…extreme) × 2 directions" in PROMPT
    assert c.numeracy.magnitudes == NUMERACY_Z and len(c.numeracy.magnitudes) == 7  # NA-05's grid
    assert "Target ≥ 0.90" in PROMPT and c.numeracy.target_share == 0.90
    assert "on 1,500 val-A D2 events" in PROMPT
    assert "pooled across the 3 models by mean rank; ties → E3" in PROMPT and c.models.n == 3


def test_models_are_the_operator_decision() -> None:
    c = load_encoding_config()
    row = next(ln for ln in PREREG.splitlines() if ln.startswith("| 2026-10-27 | NA-06 (operator"))
    named = re.findall(r"([a-z0-9-]+/[a-z0-9.-]+) \d\.\d{3}", row)
    assert tuple(named) == c.models.expected


def test_numeracy_grid_spans_negligible_to_extreme() -> None:
    from newsaction.states.codebook import load_codebook

    cb = load_codebook()
    words = [cb.move_magnitude(z) for z in load_encoding_config().numeracy.magnitudes]
    assert words[0] == "negligible" and words[-1] == "extreme"
    assert set(words) == set(cb.move.words)  # every move word is visited
