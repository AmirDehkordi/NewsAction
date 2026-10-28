"""NA-11 S8 guards: the ablation sample, states and reproduction check (production.ablations), the LLM
baseline's test step (production.llm_test) and the price-only test step (production.price_only_test)."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sklearn.isotonic import IsotonicRegression

from newsaction.dm import load_dm_config
from newsaction.production import ProductionError, llm_test, price_only_test
from newsaction.production import ablations as ab
from newsaction.production.plan import load_plan


def _pool(base: str, per_split: int = 60) -> pd.DataFrame:
    rows = []
    for split, start in (
        ("val_a", date(2025, 7, 1)),
        ("val_b", date(2025, 10, 1)),
        ("test", date(2026, 1, 5)),
    ):
        for i in range(per_split):
            rows.append(
                {
                    "event_id": f"{base}:{i % 9}:{split}:{i}",
                    "company_id": i % 9,
                    "session": start + timedelta(days=i % 20),
                    "split": split,
                    "tier": ("top100", "mid", "rest")[i % 3],
                    "month": f"{start.year}-{start.month + i % 2:02d}",
                }
            )
    return pd.DataFrame(rows)


def _small_plan(n: int) -> Any:
    plan = load_plan()
    return plan.model_copy(update={"ablations": plan.ablations.model_copy(update={"n": n})})


def test_the_ablation_sample_is_stratified_and_deranged_within_splits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ab, "pool", lambda plan, base, layout=None: _pool(base))
    smp = ab.draw(_small_plan(45), None)
    assert smp.groupby("base").size().to_dict() == {"A_D0": 45, "B_D2": 45}
    assert smp.loc[smp["base"] == "A_D0", "donor"].isna().all()
    b = smp.loc[smp["base"] == "B_D2"].set_index("event_id")
    assert set(b["donor"]) == set(b.index)  # a permutation of the sampled events
    for eid, rec in b.iterrows():
        donor = b.loc[rec["donor"]]
        assert rec["donor"] != eid and donor["split"] == rec["split"]
        assert donor["company_id"] != rec["company_id"]
    assert ab.draw(_small_plan(45), None).equals(smp)  # seeded


def test_within_a_stratum_the_smallest_u_is_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ab, "pool", lambda plan, base, layout=None: _pool(base))
    smp = ab.draw(_small_plan(45), None)
    pool = _pool("B_D2")
    pool["u"] = [
        int(hashlib.sha256(f"2026:ablation:{e}".encode()).hexdigest()[:16], 16) for e in pool["event_id"]
    ]
    got = set(smp.loc[smp["base"] == "B_D2", "event_id"])
    for _, g in pool.groupby(["split", "tier", "month"]):
        taken = g.loc[g["event_id"].isin(got)]
        if 0 < len(taken) < len(g):
            assert taken["u"].max() < g.loc[~g["event_id"].isin(got), "u"].min()


def test_ablated_states_change_only_the_news_block() -> None:
    state = {"company": {"size": "large"}, "news": [{"headline": "a"}], "reaction_so_far": {"move": "up"}}
    donor = {"company": {"size": "small"}, "news": [{"headline": "b"}], "reaction_so_far": {"move": "down"}}
    assert ab.ablated_state("b2_no_news", state) == {
        "company": {"size": "large"},
        "reaction_so_far": {"move": "up"},
    }
    assert ab.ablated_state("b2_shuffled", state, donor) == {**state, "news": [{"headline": "b"}]}
    assert state["news"] == [{"headline": "a"}]  # the original is untouched
    with pytest.raises(ProductionError, match="donor"):
        ab.ablated_state("b2_shuffled", state)
    with pytest.raises(ProductionError, match="unknown ablation"):
        ab.ablated_state("b2_other", state)


def test_a_rebuild_that_differs_or_misses_a_state_is_caught() -> None:
    ref = pd.DataFrame({"event_id": ["a", "b", "c"], "state_sha256": ["1", "2", "3"]})
    assert ab.rebuild_differs(ref, ref) == 0
    assert ab.rebuild_differs(ref.assign(state_sha256=["1", "x", "3"]), ref) == 1
    assert ab.rebuild_differs(ref.iloc[:2], ref) == 1


def test_the_unmasked_ablation_uses_a_registered_probe_tag() -> None:
    calls = {c.name: c for c in load_plan().ablations.calls}
    probe = calls["a0_unmasked"].probe
    assert probe is not None and probe in load_dm_config().registered_probes
    assert calls["b2_no_news"].probe is None and calls["b2_shuffled"].probe is None


def test_the_llm_test_sample_waits_for_the_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_test.lock, "is_frozen", lambda layout=None: False)
    with pytest.raises(ProductionError, match="follows the freeze"):
        llm_test.write_sample()


class _Client:
    def __init__(self, usd: float, left: float) -> None:
        self.usd, self.left = usd, left

    def __call__(self, *args: Any, **kwargs: Any) -> _Client:
        return self

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def dry_run_chat(self, specs: Any) -> SimpleNamespace:
        return SimpleNamespace(n_requests=2000, n_send=2000, usd=self.usd)

    def budget_left(self) -> float:
        return self.left


@pytest.mark.parametrize(("usd", "left"), [(1.5, 10.0), (0.5, 0.4)])
def test_the_llm_test_stops_above_its_cap_or_what_is_left(
    monkeypatch: pytest.MonkeyPatch, usd: float, left: float
) -> None:
    monkeypatch.setattr(llm_test, "specs", lambda layout=None: [])
    monkeypatch.setattr(llm_test, "DecisionClient", _Client(usd, left))
    with pytest.raises(ProductionError, match="STOP"):
        llm_test.run(send=True)


def test_the_llm_test_dry_run_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_test, "specs", lambda layout=None: [])
    monkeypatch.setattr(
        llm_test, "DecisionClient", _Client(0.2, 10.0)
    )  # no chat_json_batch: a send would fail
    out = llm_test.run()
    assert out["projected_usd"] == 0.2 and "valid" not in out


def test_the_price_only_test_step_waits_for_the_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(price_only_test.lock, "is_frozen", lambda layout=None: False)
    with pytest.raises(ProductionError, match="follow the freeze"):
        price_only_test.run()


def test_the_price_only_check_fails_unless_na09_is_reproduced(monkeypatch: pytest.MonkeyPatch) -> None:
    pred = pd.DataFrame(
        {
            "event_id": ["a", "b"],
            "call": "A",
            "split": "val_a",
            "N_hat": [0.1, 0.2],
            "P_up": [0.3, 0.4],
            "P_down": [0.2, 0.1],
            "mag_hat": [1.0, 1.1],
        }
    )
    monkeypatch.setattr(price_only_test, "frame", lambda splits, layout=None: pd.DataFrame())
    monkeypatch.setattr(price_only_test, "predict", lambda df, layout=None: pred)
    monkeypatch.setattr(price_only_test.io, "read_parquet", lambda rel, layout=None: pred)
    assert price_only_test.check()["rows"] == 2
    off = pred.assign(N_hat=[0.1, 0.2001])
    monkeypatch.setattr(price_only_test.io, "read_parquet", lambda rel, layout=None: off)
    with pytest.raises(ProductionError, match="not reproduced"):
        price_only_test.check()


def test_the_stored_isotonic_thresholds_predict_as_sklearn() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = (x + rng.normal(size=400) > 0.5).astype(float)
    iso = IsotonicRegression(increasing=True, out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(x, y)
    m = {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()}
    grid = np.linspace(-5, 5, 201)
    assert np.allclose(price_only_test._iso(grid, m), iso.predict(grid))
