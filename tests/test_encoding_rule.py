"""PRD NA-07 AC2: the encoding rule is mechanical (PREREG §8.4; PRD S1–S2; §15 NA-07 row).

Unit cases pin the pooling (mean rank over models), the tie rules (E3 first, then the higher mean IC, then the
lower index), the val-B check's boundary (Δ = −1 SE keeps the best), and the model choice from NA-06's
leaderboard. The recomputation re-derives the choice from artifacts/NA-07/encoding_ic.csv and
encoding_check.csv with the PREREG's numbers and compares it with configs/frozen.yaml."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from newsaction.config import load_frozen
from newsaction.encoding import EncodingError, load_encoding_config
from newsaction.encoding.numeracy import gate
from newsaction.encoding.study import (
    boot_indices,
    boot_means,
    choose_encoding,
    confirm,
    ranks,
    summarize,
    top_models,
    val_b_delta,
)
from newsaction.paths import ROOT
from test_encoding_config import prereg_rules

ENCS = ("E0", "E1", "E2", "E3", "E4")
ART = ROOT / "artifacts" / "NA-07"


def table(ics: dict[str, list[float]]) -> pd.DataFrame:
    """{model: [IC of E0..E4]} → long table."""
    return pd.DataFrame(
        [
            {"model": m, "encoding": e, "ic": v}
            for m, vals in ics.items()
            for e, v in zip(ENCS, vals, strict=True)
        ]
    )


def test_lowest_mean_rank_wins_even_against_a_higher_mean_ic() -> None:
    # E1 ranks 1, 1, 5 (mean 2.33); E0 ranks 2, 2, 1 (mean 1.67) → E0, though E1's mean IC is higher
    t = table(
        {
            "a": [0.05, 0.06, 0.01, 0.02, 0.03],
            "b": [0.05, 0.06, 0.01, 0.02, 0.03],
            "c": [0.50, -0.90, 0.01, 0.02, 0.03],
        }
    )
    ch = choose_encoding(t, ENCS, "E3")
    assert ch.best == "E0" and ch.reason == "lowest mean rank"
    assert ch.mean_rank["E0"] == pytest.approx(5 / 3)


def test_tie_including_e3_goes_to_e3() -> None:
    # E3 and E1 swap ranks 1 and 2 across two models: mean rank 1.5 each
    t = table({"a": [0.0, 0.05, 0.01, 0.04, 0.02], "b": [0.0, 0.04, 0.01, 0.05, 0.02]})
    ch = choose_encoding(t, ENCS, "E3")
    assert ch.best == "E3" and set(ch.tied) == {"E1", "E3"}


def test_tie_without_e3_goes_to_the_higher_mean_ic_then_the_lower_index() -> None:
    t = table({"a": [0.10, 0.05, 0.0, 0.01, 0.02], "b": [0.05, 0.06, 0.0, 0.01, 0.02]})
    ch = choose_encoding(t, ENCS, "E3")
    assert set(ch.tied) == {"E0", "E1"} and ch.best == "E0"  # mean IC 0.075 vs 0.055
    t2 = table({"a": [0.10, 0.05, 0.0, 0.01, 0.02], "b": [0.05, 0.10, 0.0, 0.01, 0.02]})
    assert choose_encoding(t2, ENCS, "E3").best == "E0"  # equal mean IC → the lower index


def test_ties_within_a_model_share_the_average_rank_and_missing_ranks_last() -> None:
    t = table({"a": [0.03, 0.03, math.nan, 0.01, 0.02]})
    r = ranks(t).tolist()
    assert r == [1.5, 1.5, 5.0, 4.0, 3.0]
    near = table({"a": [0.03, 0.03 + 1e-14, 0.0, 0.01, 0.02]})  # equal to 12 decimals
    assert ranks(near).tolist()[:2] == [1.5, 1.5]


def test_a_missing_row_is_an_error() -> None:
    t = table({"a": [0.0, 0.1, 0.2, 0.3, 0.4]}).iloc[:4]
    with pytest.raises(EncodingError):
        choose_encoding(t, ENCS, "E3")


def test_val_b_check_boundaries() -> None:
    k = prereg_rules()["confirm_se"]
    assert confirm("E1", "E3", -0.02, 0.02, k).chosen == "E1"  # exactly −1 SE: not "more than" 1 SE worse
    assert confirm("E1", "E3", -0.0201, 0.02, k).chosen == "E3"
    assert confirm("E1", "E3", 0.05, 0.02, k).kept_best
    c = confirm("E3", "E3", None, None, k)
    assert not c.needed and c.chosen == "E3"
    with pytest.raises(EncodingError):
        confirm("E1", "E3", None, 0.01, k)


def test_val_b_delta_uses_common_sessions_and_pools_models() -> None:
    rows = []
    for s, (a1, a3, b1, b3) in enumerate(
        [(0.2, 0.1, 0.0, 0.1), (0.1, 0.1, 0.3, 0.1), (0.5, math.nan, 0.1, 0.1)]
    ):
        for m, e, v in (("a", "E1", a1), ("a", "E3", a3), ("b", "E1", b1), ("b", "E3", b3)):
            rows.append({"model": m, "encoding": e, "session": s, "ic": v})
    d = val_b_delta(pd.DataFrame(rows), ["a", "b"], "E1", "E3")
    assert d.index.tolist() == [0, 1]  # session 2 lacks a's E3
    assert d.tolist() == pytest.approx([0.0, 0.1])


def test_bootstrap_is_seeded_and_handles_missing_sessions() -> None:
    a, b = boot_indices(30, 200, 5, 2026), boot_indices(30, 200, 5, 2026)
    assert np.array_equal(a, b)
    v = np.arange(30, dtype=float)
    v[3] = np.nan
    bm = boot_means(v, a)
    assert np.isfinite(bm).all() and abs(bm.mean() - np.nanmean(v)) < 2
    s = summarize(pd.Series(v, index=range(30)).dropna(), list(range(30)), a, 5, 0.95)
    assert s.ci_low < s.ic < s.ci_high and s.boot_se > 0 and s.n_days == 29


def test_top_models_ties_go_to_the_cheaper() -> None:
    lb = pd.DataFrame(
        {
            "model": ["x", "y", "z", "w"],
            "stage2": [True, True, True, False],
            "ic2_a_z_cc": [0.05, 0.07, 0.07, 0.9],
            "cost_per_1000_a2": [0.01, 0.05, 0.02, 0.0],
        }
    )
    assert top_models(lb, 2) == ["z", "y"]
    with pytest.raises(EncodingError):
        top_models(lb, 4)


def test_na06_leaderboard_gives_the_configured_models() -> None:
    lb = pd.read_csv(ROOT / "artifacts" / "NA-06" / "leaderboard.csv")
    c = load_encoding_config()
    assert top_models(lb, c.models.n) == list(c.models.expected)


# --- recomputation from the committed tables (AC2) -------------------------------------------------------


def _frozen_encoding() -> dict[str, object]:
    enc = load_frozen().encoding
    if enc is None or not (ART / "encoding_ic.csv").is_file():
        pytest.skip("NA-07 has not written its encoding decision yet")
    assert isinstance(enc, dict)
    return enc


def test_encoding_choice_recomputed_from_the_csvs_matches_frozen() -> None:
    enc = _frozen_encoding()
    c = load_encoding_config()
    t = pd.read_csv(ART / "encoding_ic.csv")
    va = t.loc[(t["split"] == "val_a") & (t["model"] != "pooled")]
    assert sorted(set(va["model"])) == sorted(c.models.expected) and len(va) == c.models.n * len(c.encodings)
    rec = choose_encoding(va, c.encodings, prereg_rules()["default"])  # type: ignore[arg-type]
    assert rec.best == enc["val_a_best"]
    assert ranks(va).tolist() == pytest.approx(va["rank"].tolist())
    pooled = t.loc[t["model"] == "pooled"].set_index("encoding")
    for e in c.encodings:
        assert pooled.loc[e, "rank"] == pytest.approx(rec.mean_rank[e])
    chk = pd.read_csv(ART / "encoding_check.csv")
    rule = chk.loc[chk["scope"] == "rule"].iloc[0]
    default = str(prereg_rules()["default"])
    if rec.best == default:
        assert not bool(rule["needed"]) and enc["chosen"] == default
        assert not (t["split"] == "val_b").any()  # no val-B value was computed
        kept = default
    else:
        pooled_b = chk.loc[chk["scope"] == "pooled"].iloc[0]
        again = confirm(
            rec.best,
            default,
            float(pooled_b["delta"]),
            float(pooled_b["boot_se"]),
            prereg_rules()["confirm_se"],
        )
        kept = again.chosen
        assert kept == rule["chosen"] == enc["val_b_kept"]
    # the numeracy gate (PREREG §15 NA-07 row): the leading model's share in the kept encoding
    num = pd.read_csv(ART / "numeracy.csv")
    gate_rows = num.loc[num["role"] == "gate"]
    assert set(gate_rows["encoding"]) == {kept}
    shares = {str(k): float(v) for k, v in gate_rows.set_index("model")["share"].items()}
    chosen, by_model = gate(kept, default, shares, c.models.expected[0], c.numeracy.target_share)
    assert chosen == enc["chosen"] and by_model == enc["by_model"]
    assert t.loc[t["chosen"], "encoding"].unique().tolist() == [enc["chosen"]]
    import hashlib

    assert hashlib.sha256((ART / "encoding_ic.csv").read_bytes()).hexdigest() == enc["val_a_table_sha"]
