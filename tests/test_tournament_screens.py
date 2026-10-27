"""PRD NA-06 AC3: the PREREG §8.3 screens are mechanical. Their thresholds come from docs/PREREG.md through
configs/tournament.yaml (parsed here from the §8.3 table), ``probes.screens`` applies them at the boundaries,
and the leaderboard's pass/fail is recomputed from artifacts/NA-06/probe_details.csv."""

from __future__ import annotations

import math
import re

import pandas as pd
import pytest

from newsaction.paths import ROOT
from newsaction.tournament import ScreenConfig, load_tournament_config
from newsaction.tournament.probes import SCREENS, screens

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
SECTION = PREREG[PREREG.index("- **8.3 Stage 2 (NA-06).**") : PREREG.index("- **8.4 Encoding")]
PROBE_DETAILS = ROOT / "artifacts" / "NA-06" / "probe_details.csv"
LEADERBOARD = ROOT / "artifacts" / "NA-06" / "leaderboard.csv"


def prereg_thresholds() -> dict[str, float]:
    """The pass conditions of PREREG §8.3's screen table."""

    def grab(pattern: str) -> re.Match[str]:
        m = re.search(pattern, SECTION)
        assert m is not None, pattern
        return m

    um = grab(r"unmasked − masked ≤ ([\d.]+), or paired \\\|t\\\| < ([\d.]+)")
    return {
        "company_id_max": float(grab(r"\| Company identification \(1 of 4[^|]*\| ≤ (\d+)% \|").group(1))
        / 100,
        "flip_rate_min": float(grab(r"\| Counterfactual flip rate[^|]*\| ≥ (\d+)% \|").group(1)) / 100,
        "unmasked_minus_masked_max": float(um.group(1)),
        "unmasked_paired_t": float(um.group(2)),
        "shuffled_t": float(
            grab(
                r"Shuffled-news mean daily IC \| not significantly different from 0 \(\\\|t\\\| < ([\d.]+)"
            ).group(1)
        ),
    }


def cfg() -> ScreenConfig:
    return load_tournament_config().screens


def test_config_thresholds_are_prereg() -> None:
    c = cfg()
    for k, v in prereg_thresholds().items():
        assert getattr(c, k) == pytest.approx(v), k
    assert c.flip_min_abs_n_hat == 0.25  # PRD NA-06 S4c


def run(**kw: float) -> dict[str, bool]:
    base = {
        "company_id_acc": 0.30,
        "flip": 0.80,
        "unmasked_minus_masked": 0.0,
        "unmasked_t": 0.0,
        "shuffled_t": 0.0,
    }
    return screens(**{**base, **kw}, cfg=cfg())


@pytest.mark.parametrize(
    ("acc", "ok"), [(0.25, True), (0.40, True), (0.4025, False), (0.90, False), (math.nan, False)]
)
def test_company_identification_boundary(acc: float, ok: bool) -> None:
    assert run(company_id_acc=acc)["company_identification"] is ok


@pytest.mark.parametrize(("flip", "ok"), [(1.0, True), (0.70, True), (0.6975, False), (math.nan, False)])
def test_flip_boundary(flip: float, ok: bool) -> None:
    assert run(flip=flip)["counterfactual_flip"] is ok


@pytest.mark.parametrize(
    ("diff", "t", "ok"),
    [
        (0.02, 9.0, True),
        (0.021, 2.5, False),
        (0.05, 1.99, True),
        (0.05, -1.99, True),
        (0.05, 2.0, False),
        (-0.1, 5.0, True),
    ],
)
def test_masked_vs_unmasked_rule(diff: float, t: float, ok: bool) -> None:
    assert run(unmasked_minus_masked=diff, unmasked_t=t)["masked_vs_unmasked"] is ok


@pytest.mark.parametrize(
    ("t", "ok"), [(0.0, True), (1.99, True), (-1.99, True), (2.0, False), (-2.5, False), (math.nan, False)]
)
def test_shuffled_rule(t: float, ok: bool) -> None:
    assert run(shuffled_t=t)["shuffled_news"] is ok


def test_all_needs_every_screen() -> None:
    assert run()["all"] is True
    assert run(company_id_acc=0.5)["all"] is False


def recompute(details: pd.DataFrame) -> pd.DataFrame:
    """Pass/fail per model from probe_details.csv with the PREREG thresholds (independent of probes.py)."""
    th = prereg_thresholds()
    rows = []
    for m, g in details.groupby("model"):
        d = g.set_index("probe")
        um = d.loc["masked_vs_unmasked"]
        rec = {
            "model": m,
            "company_identification": bool(d.loc["company_identification", "value"] <= th["company_id_max"]),
            "counterfactual_flip": bool(d.loc["counterfactual_flip", "value"] >= th["flip_rate_min"]),
            "masked_vs_unmasked": bool(
                um["value"] <= th["unmasked_minus_masked_max"] or abs(um["t"]) < th["unmasked_paired_t"]
            ),
            "shuffled_news": bool(abs(d.loc["shuffled_news", "t"]) < th["shuffled_t"]),
        }
        rec["all"] = all(rec[s] for s in SCREENS)
        rows.append(rec)
    return pd.DataFrame(rows).set_index("model")


def test_leaderboard_screens_recompute_from_probe_details() -> None:
    if not PROBE_DETAILS.is_file() or not LEADERBOARD.is_file():
        pytest.skip("the NA-06 report has not run")
    details = pd.read_csv(PROBE_DETAILS)
    lb = pd.read_csv(LEADERBOARD).set_index("model")
    again = recompute(details)
    assert set(again.index) == set(lb.index[lb["stage2"].astype(bool)])
    for m, r in again.iterrows():
        for s in SCREENS:
            assert bool(lb.loc[m, f"screen_{s}"]) is bool(r[s]), (m, s)
            assert bool(details.set_index(["model", "probe"]).loc[(m, s), "passed"]) is bool(r[s]), (m, s)
        assert bool(lb.loc[m, "screens_pass"]) is bool(r["all"]), m


def test_missing_values_fail_every_screen() -> None:
    """A probe without a value (None or NaN) fails its screen: passing must be shown."""
    for v in (None, math.nan):
        out = screens(
            company_id_acc=v,
            flip=v,
            unmasked_minus_masked=v,
            unmasked_t=v,
            shuffled_t=v,
            cfg=cfg(),  # type: ignore[arg-type]
        )
        assert not any(out.values()), (v, out)
