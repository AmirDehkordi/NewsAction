"""PRD NA-06 S1: the tournament samples (``tournament.sample``): sizes, tier × month stratification, nesting,
the embargo (PREREG §4.2) and determinism, on a synthetic pool and on the written samples file."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from newsaction import calendar, io
from newsaction.config import load_splits
from newsaction.paths import ROOT
from newsaction.states.build import stratified_sample
from newsaction.tournament import TournamentError, load_tournament_config
from newsaction.tournament.sample import SAMPLE_FLAGS, draw, embargo_sessions

CFG = load_tournament_config()
SAMPLES = "dm/tournament/samples.parquet"


def pool(n: int = 6000) -> pd.DataFrame:
    sessions = calendar.sessions(date(2025, 7, 10), date(2025, 9, 30))
    rows = []
    for i in range(n):
        s = sessions[i % len(sessions)]
        rows.append(
            {
                "event_id": f"W0:{i % 500}:{s.isoformat()}:{i}",
                "company_id": i % 500,
                "symbol_id": i % 500,
                "session": s,
                "month": s.strftime("%Y-%m"),
                "tier": ("top100", "mid", "rest")[i % 3],
            }
        )
    return pd.DataFrame(rows)


def test_draw_nests_and_stratifies() -> None:
    p = pool()
    twins = stratified_sample(p, CFG.samples.shuffled, list(CFG.samples.strata), CFG.seed)["event_id"]
    out = draw(p, CFG, unmasked_ids=twins, call_b_ids=p["event_id"].str.replace("W0:", "W2:", n=1).head(100))
    assert len(out) == CFG.samples.stage2
    sizes = {k: int(out[k].sum()) for k in SAMPLE_FLAGS}
    assert sizes == {
        "stage1": 700,
        "identification": 400,
        "reading_validity": 500,
        "shuffled": 1000,
        "stage2": 3000,
    }
    for small, big in (
        ("identification", "reading_validity"),
        ("reading_validity", "stage1"),
        ("stage1", "shuffled"),
    ):
        assert (~out[small] | out[big]).all(), (small, big)
    # proportional to the pool's tier × month cells (largest remainder: within one event)
    share = p.groupby(["tier", "month"]).size() / len(p)
    got = out.loc[out["stage1"]].groupby(["tier", "month"]).size()
    assert ((got - share * 700).abs() <= 1).all()
    assert out["b_event_id"].notna().sum() <= 100


def test_draw_is_deterministic() -> None:
    p = pool()
    twins = stratified_sample(p, 1000, list(CFG.samples.strata), CFG.seed)["event_id"]
    a = draw(p, CFG, unmasked_ids=twins, call_b_ids=[])
    b = draw(p.sample(frac=1.0, random_state=3), CFG, unmasked_ids=twins, call_b_ids=[])
    pd.testing.assert_frame_equal(a, b)


def test_draw_refuses_other_twins() -> None:
    p = pool()
    with pytest.raises(TournamentError, match="unmasked twins"):
        draw(p, CFG, unmasked_ids=p["event_id"].head(1000), call_b_ids=[])


def test_embargo_is_the_first_five_val_a_sessions() -> None:
    emb = [d.date() for d in embargo_sessions("val_a")]
    va = load_splits().splits["val_a"]
    assert emb == calendar.sessions(va.start, va.end)[:5]
    assert emb[0] == date(2025, 7, 1) and emb[-1] == date(2025, 7, 8)


@pytest.fixture(scope="module")
def written() -> pd.DataFrame:
    if not (ROOT / "work" / SAMPLES).is_file():
        pytest.skip("the samples stage has not run")
    return io.read_parquet(SAMPLES)


def test_written_samples(written: pd.DataFrame) -> None:
    s = written
    assert int(s["stage2"].sum()) == 3000 and int(s["stage1"].sum()) == 700
    assert int(s["identification"].sum()) == 400 and int(s["counterfactual"].sum()) == 200
    va = load_splits().splits["val_a"]
    last_embargo = embargo_sessions("val_a")[-1].date()
    assert (s["session"] > last_embargo).all() and (s["session"] <= va.end).all()
    assert s["event_id"].is_unique
    twins = io.read_parquet("states/samples/unmasked.parquet", columns=["event_id"])["event_id"]
    assert set(s.loc[s["shuffled"], "event_id"]) == set(twins) == set(s.loc[s["unmasked_twin"], "event_id"])
    assert s.loc[s["stage2"], "b_event_id"].notna().all()
    donors = s.loc[s["shuffled"]].set_index("event_id")
    assert (donors["shuffle_donor"] != donors.index).all()
    comp = s.set_index("event_id")["company_id"]
    assert (comp.loc[donors["shuffle_donor"]].to_numpy() != donors["company_id"].to_numpy()).all()
    assert set(donors["shuffle_donor"]) == set(donors.index)  # a permutation
    assert s.loc[s["identification"], "company_true_key"].notna().all()


def test_counterfactual_prefers_stage2(written: pd.DataFrame) -> None:
    cf = written.loc[written["counterfactual"]]
    extra = cf.loc[~cf["stage2"]]
    assert len(extra) == 200 - int(cf["stage2"].sum())
    assert (extra["session"] - timedelta(0) > embargo_sessions("val_a")[-1].date()).all()


def test_pool_excludes_the_embargo() -> None:
    """``event_pool`` on the registered files: val-A only, no session of the embargo (PREREG §4.2)."""
    if not (ROOT / "work" / "events" / "events_d0.parquet").is_file():
        pytest.skip("work/events is absent")
    from newsaction.tournament.sample import event_pool

    p = event_pool(CFG)
    last = embargo_sessions("val_a")[-1].date()
    va = load_splits().splits["val_a"]
    assert len(p) == 8376
    assert (p["session"] > last).all() and (p["session"] <= va.end).all()
    assert p["third_party_ok_all"].all()
