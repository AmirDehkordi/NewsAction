"""Refusals of the decision client (PRD NA-05 AC3; CLAUDE.md B8, C13, D15).

Each rule raises ``Refused`` before the cache is read and before any transport call, also in offline mode:
(a) third-party, (b) test period before the freeze, (c) val-B before allow_val_b, (d) unmasked without a
registered probe, (e) not eligible (unless pilot=True), (f) :free without approval, and the pilot's
train-period rule.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from dm_fakes import LOCAL, MODEL, TRAIN_INFO, FakeLocal, Recorder, make_client, spec
from newsaction.dm import Refused
from newsaction.dm.client import StateInfo
from newsaction.paths import Layout


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")


def info(**kw: Any) -> StateInfo:
    return TRAIN_INFO.model_copy(update=kw)


def set_frozen(layout: Layout, **values: Any) -> None:
    path = layout.configs / "frozen.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(values)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def write_freeze_record(layout: Layout) -> None:
    path = layout.root / "artifacts" / "NA-11" / "freeze.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hash": "0" * 64, "files": {}, "deviations_log": {"sha256": "", "bytes": 0}}))


def assert_refused(client: Any, rec: Recorder, s: Any, rule: str) -> None:
    with pytest.raises(Refused) as exc:
        client.decide([s])
    assert exc.value.rule == rule
    with pytest.raises(Refused):
        client.dry_run([s])
    assert rec.calls == 0


TEST_STATE = info(event_id="W0:1:2026-03-02", session=date(2026, 3, 2), split="test")
VAL_B_STATE = info(event_id="W0:1:2025-11-03", session=date(2025, 11, 3), split="val_b")
VAL_A_STATE = info(event_id="W0:1:2025-08-01", session=date(2025, 8, 1), split="val_a")


@pytest.mark.parametrize("offline", [False, True])
def test_a_third_party_not_ok(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, offline=offline)
    assert_refused(client, rec, spec(info=info(third_party_ok_all=False)), "third_party")


def test_a_does_not_apply_to_local_models(tmp_layout: Layout, tmp_path: Path) -> None:
    rec, local = Recorder(), FakeLocal()
    client = make_client(tmp_layout, tmp_path, rec, local=local)
    assert client.decide([spec(model=LOCAL, info=info(third_party_ok_all=False))])[0].ok
    assert local.calls == 1 and rec.calls == 0


@pytest.mark.parametrize("offline", [False, True])
@pytest.mark.parametrize("model", [MODEL, LOCAL])
def test_b_test_period_before_the_freeze(
    tmp_layout: Layout, tmp_path: Path, offline: bool, model: str
) -> None:
    rec, local = Recorder(), FakeLocal()
    client = make_client(tmp_layout, tmp_path, rec, offline=offline, local=local)
    assert_refused(client, rec, spec(model=model, info=TEST_STATE), "test_period")
    # the session alone is enough, whatever the split label says
    assert_refused(client, rec, spec(model=model, info=info(session=date(2026, 1, 2))), "test_period")
    assert local.calls == 0


def test_b_allows_the_test_period_after_the_freeze(tmp_layout: Layout, tmp_path: Path) -> None:
    write_freeze_record(tmp_layout)
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, pilot=False)
    set_frozen(tmp_layout, eligible_models=[{"id": MODEL, "include": True, "reason": "test"}])
    assert client.decide([spec(info=TEST_STATE)])[0].ok


@pytest.mark.parametrize("offline", [False, True])
def test_c_val_b_before_allow_val_b(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, offline=offline, pilot=False)
    # the gate as it was before NA-06's hand-off (the repository's own frozen.yaml may have opened it)
    set_frozen(
        tmp_layout, eligible_models=[{"id": MODEL, "include": True, "reason": "test"}], allow_val_b=False
    )
    assert_refused(client, rec, spec(info=VAL_B_STATE), "val_b")
    assert_refused(client, rec, spec(info=info(session=date(2025, 12, 31))), "val_b")


def test_c_val_b_after_allow_val_b_and_for_local_models(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, pilot=False)
    set_frozen(
        tmp_layout,
        eligible_models=[{"id": m, "include": True, "reason": "test"} for m in (MODEL, LOCAL)],
        allow_val_b=False,
    )
    assert client.decide([spec(model=LOCAL, info=VAL_B_STATE)])[0].ok  # local: nothing is sent
    set_frozen(tmp_layout, allow_val_b=True)
    assert client.decide([spec(info=VAL_B_STATE)])[0].ok


def test_d_unmasked_needs_a_registered_probe(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    assert_refused(client, rec, spec(info=info(masked=False)), "unmasked")
    assert_refused(client, rec, spec(info=info(masked=False, probe="my_idea")), "unmasked")
    assert client.decide([spec(info=info(masked=False, probe="unmasked_twin"))])[0].ok


def test_e_model_not_eligible(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, pilot=False)
    set_frozen(tmp_layout, eligible_models=[{"id": MODEL, "include": False, "reason": "failed"}])
    assert_refused(client, rec, spec(), "eligibility")
    set_frozen(tmp_layout, eligible_models=None)
    assert_refused(client, rec, spec(), "eligibility")
    set_frozen(tmp_layout, eligible_models=[{"id": MODEL, "include": True, "reason": "ok"}])
    assert client.decide([spec()])[0].ok


def test_e_pilot_may_call_catalog_models(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, pilot=True)
    set_frozen(tmp_layout, eligible_models=None)
    assert client.decide([spec()])[0].ok


@pytest.mark.parametrize("pilot", [True, False])
def test_f_free_endpoints_need_approval(tmp_layout: Layout, tmp_path: Path, pilot: bool) -> None:
    free = f"{MODEL}:free"
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, pilot=pilot, prices={free: client_price()})
    set_frozen(tmp_layout, eligible_models=[{"id": free, "include": True, "reason": "test"}])
    assert_refused(client, rec, spec(model=free), "free")
    set_frozen(tmp_layout, free_model_approvals={free: "operator, 2026-10-26"})
    assert client.decide([spec(model=free)])[0].ok


def client_price() -> Any:
    from dm_fakes import PRICE

    return PRICE


@pytest.mark.parametrize("state", [VAL_A_STATE, VAL_B_STATE])
def test_pilot_states_are_train_period_or_synthetic(
    tmp_layout: Layout, tmp_path: Path, state: StateInfo
) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec, pilot=True)
    set_frozen(tmp_layout, allow_val_b=True)
    assert_refused(client, rec, spec(info=state), "pilot_period")
    synthetic = StateInfo(source="synthetic", masked=True, third_party_ok_all=True)
    assert client.decide([spec(info=synthetic)])[0].ok


def test_refusal_checks_every_request_of_a_batch(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    with pytest.raises(Refused):
        client.decide([spec(), spec(repeat_idx=1), spec(info=TEST_STATE)])
    assert rec.calls == 0  # nothing of the batch went out


def test_state_info_requires_provenance() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        StateInfo(source="states", masked=True, third_party_ok_all=True)
    with pytest.raises(ValidationError):
        StateInfo(
            source="synthetic", session=date(2024, 8, 1), split="train", masked=True, third_party_ok_all=True
        )


def test_provider_is_always_data_collection_deny() -> None:
    from pydantic import ValidationError

    from newsaction.dm.schemas import Provider

    with pytest.raises(ValidationError):
        Provider(data_collection="allow")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Provider.model_validate({"data_collection": "deny", "zdr": False})
