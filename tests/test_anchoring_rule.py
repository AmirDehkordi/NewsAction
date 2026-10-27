"""PRD NA-07 S4 / AC2: the anchoring rule is mechanical (PREREG §8.4; §15 NA-07 row).

The thresholds come from the PREREG text (``test_encoding_config.prereg_rules``), not from the code: the
boundary cases fail if ``anchoring.present`` or ``configs/encoding.yaml`` moves a threshold. The verdict is
recomputed from artifacts/NA-07/anchoring.csv and compared with configs/frozen.yaml."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from newsaction.config import load_frozen
from newsaction.encoding import load_encoding_config
from newsaction.encoding.anchoring import combine, ols, present, stats
from newsaction.paths import ROOT
from test_encoding_config import prereg_rules

ART = ROOT / "artifacts" / "NA-07"


def thresholds() -> tuple[float, float]:
    r = prereg_rules()
    return float(r["slope_min"]), float(r["corr_max"])


def test_config_thresholds_are_the_prereg_ones() -> None:
    a = load_encoding_config().anchoring
    assert (a.slope_min, a.corr_max) == pytest.approx(thresholds()) == (0.30, 0.70)


@pytest.mark.parametrize(
    ("slope", "corr", "expected"),
    [
        (0.30, 0.95, True),  # slope at the threshold: ≥
        (0.2999, 0.95, False),
        (0.0, 0.70, False),  # corr at the threshold: < is strict
        (0.0, 0.6999, True),
        (0.50, 0.50, True),
        (-0.40, 0.99, False),
        (0.10, 0.80, False),
    ],
)
def test_rule_boundaries(slope: float, corr: float, expected: bool) -> None:
    s, c = thresholds()
    assert present(slope, corr, s, c) is expected
    a = load_encoding_config().anchoring
    assert present(slope, corr, a.slope_min, a.corr_max) is expected


def test_combine_is_any_model_and_records_the_extremes() -> None:
    s, c = thresholds()
    v = combine({"a": (0.05, 0.95), "b": (0.10, 0.90)}, s, c)
    assert not v.present and v.calls_per_event == 1 and (v.slope, v.corr) == (0.10, 0.90)
    v = combine({"a": (0.05, 0.95), "b": (0.10, 0.65)}, s, c)
    assert v.present and v.calls_per_event == 2 and v.by_model == {"a": False, "b": True}
    assert present(v.slope, v.corr, s, c)  # the recorded pair gives the same verdict


def test_ols_matches_lstsq_and_the_slope_is_g() -> None:
    rng = np.random.default_rng(0)
    n = 400
    g = rng.normal(size=n)
    a = rng.normal(size=n)
    b = 0.1 + 0.4 * g + 0.7 * a + rng.normal(scale=0.3, size=n)
    sessions = np.repeat(np.arange(40), 10)
    fit = ols(b, np.column_stack([g, a]), sessions.tolist())
    ref = np.linalg.lstsq(np.column_stack([np.ones(n), g, a]), b, rcond=None)[0]
    assert fit.coef == pytest.approx(ref)
    assert fit.n_clusters == 40 and (fit.se_hc1 > 0).all() and (fit.se_cluster > 0).all()
    st = stats(pd.DataFrame({"n_hat_a": a, "n_hat_b": b, "g": g, "session": sessions}))
    assert st.slope == pytest.approx(ref[1]) and st.coef_n_hat_a == pytest.approx(ref[2])
    assert st.corr == pytest.approx(np.corrcoef(a, b)[0, 1])


def test_stats_drop_rows_with_a_missing_answer() -> None:
    df = pd.DataFrame(
        {"n_hat_a": [0.1, 0.2, np.nan, 0.4, 0.5], "n_hat_b": [0.2, 0.1, 0.3, 0.5, 0.4], "g": [1, -1, 2, 0, 1],
         "session": [1, 1, 2, 2, 3]}
    )  # fmt: skip
    assert stats(df).n == 4


def test_anchoring_csv_recomputed_matches_frozen() -> None:
    anc = load_frozen().anchoring
    if anc is None or not (ART / "anchoring.csv").is_file():
        pytest.skip("NA-07 has not written its anchoring decision yet")
    assert isinstance(anc, dict)
    s, c = thresholds()
    t = pd.read_csv(ART / "anchoring.csv")
    per = t.loc[t["model"] != "all"]
    assert sorted(per["model"]) == sorted(load_encoding_config().models.expected)
    again = [present(float(r["slope"]), float(r["corr"]), s, c) for r in per.to_dict("records")]
    assert again == per["present"].astype(bool).tolist()
    v = combine(
        {str(r["model"]): (float(r["slope"]), float(r["corr"])) for r in per.to_dict("records")}, s, c
    )
    assert v.present is anc["present"] and v.calls_per_event == anc["calls_per_event"]
    assert v.slope == pytest.approx(anc["slope"]) and v.corr == pytest.approx(anc["corr"])
    assert anc["by_model"] == v.by_model
    assert anc["calls_per_event"] == (2 if anc["present"] else 1)
    assert hashlib.sha256((ART / "anchoring.csv").read_bytes()).hexdigest() == anc["table_sha"]
