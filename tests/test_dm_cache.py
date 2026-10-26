"""The decision cache (PRD NA-05 AC2): a repeated request makes no network call and records no spend, and a
change to any part of the request (state, questions, model, params, repeat) misses."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from dm_fakes import MODEL, QUESTIONS, STATE, Recorder, make_client, spec, spend_events
from newsaction.dm.cache import CacheError, DecisionCache, request_key
from newsaction.dm.schemas import DecisionRequest, QuestionSpec
from newsaction.paths import Layout


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")


def test_repeat_request_hits_the_cache_without_network_or_spend(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    first = client.decide([spec()])[0]
    n_events = len(spend_events(tmp_layout))
    second = client.decide([spec()])[0]
    assert first.ok and not first.cached
    assert second.ok and second.cached and second.key == first.key
    assert rec.calls == 1
    assert len(spend_events(tmp_layout)) == n_events  # no reserve, no spend for the hit
    assert second.row is not None and second.row.response_json == first.row.response_json  # type: ignore[union-attr]


def test_duplicate_requests_in_one_batch_are_sent_once(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    out = client.decide([spec(), spec(), spec(repeat_idx=1)])
    assert rec.calls == 2
    assert out[0].key == out[1].key != out[2].key


def _key_of(req: DecisionRequest, params: dict[str, object] | None = None, repeat: int = 0) -> str:
    return request_key(req.model, req, params or {}, repeat)


def test_one_character_of_the_state_changes_the_key() -> None:
    base = DecisionRequest(model=MODEL, state=STATE, questions=QUESTIONS)
    edited = copy.deepcopy(STATE)
    edited["news"][0]["snippet"] = "y"
    other = DecisionRequest(model=MODEL, state=edited, questions=QUESTIONS)
    assert _key_of(base) != _key_of(other)
    as_text = DecisionRequest(model=MODEL, state="The company beats", questions=QUESTIONS)
    as_text2 = DecisionRequest(model=MODEL, state="The company beatz", questions=QUESTIONS)
    assert _key_of(as_text) != _key_of(as_text2)


def test_questions_model_params_and_repeat_change_the_key() -> None:
    base = DecisionRequest(model=MODEL, state=STATE, questions=QUESTIONS)
    q2 = dict(QUESTIONS)
    q2["materiality"] = QuestionSpec(
        type="choice",
        instructions="Is it new?",
        criteria={"new_information": "new!", "no_new_information": "not new"},
    )
    reordered = dict(QUESTIONS)
    reordered["materiality"] = QuestionSpec(
        type="choice",
        instructions="Is it new?",
        criteria={"no_new_information": "not new", "new_information": "new"},
    )
    swapped = {"materiality": QUESTIONS["materiality"], "justified_move": QUESTIONS["justified_move"]}
    keys = {
        _key_of(base),
        _key_of(DecisionRequest(model=MODEL, state=STATE, questions=q2)),
        _key_of(DecisionRequest(model=MODEL, state=STATE, questions=reordered)),  # option order counts
        _key_of(DecisionRequest(model=MODEL, state=STATE, questions=swapped)),  # question order counts
        _key_of(DecisionRequest(model="test/other", state=STATE, questions=QUESTIONS)),
        _key_of(base, {"seed": 1}),
        _key_of(base, repeat=1),
    }
    assert len(keys) == 7


def test_key_ignores_the_session_id_only() -> None:
    a = DecisionRequest(model=MODEL, state=STATE, questions=QUESTIONS)
    b = DecisionRequest(model=MODEL, state=STATE, questions=QUESTIONS, session_id="x")
    assert _key_of(a) == _key_of(b)


def test_changed_questions_miss_through_the_client(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    client.decide([spec()])
    one_question = {"justified_move": QUESTIONS["justified_move"]}
    res = client.decide([spec(questions=one_question)])[0]
    assert not res.cached and rec.calls == 2


def test_offline_client_serves_hits_and_refuses_misses(tmp_layout: Layout, tmp_path: Path) -> None:
    from newsaction.dm import CacheMiss

    rec = Recorder()
    online = make_client(tmp_layout, tmp_path, rec)
    online.decide([spec()])
    online.close()
    offline = make_client(tmp_layout, tmp_path, rec, offline=True)
    assert offline.decide([spec()])[0].cached
    with pytest.raises(CacheMiss):
        offline.decide([spec(repeat_idx=9)])
    assert rec.calls == 1


def test_a_key_is_written_once(tmp_path: Path, tmp_layout: Layout) -> None:
    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    row = client.decide([spec()])[0].row
    assert row is not None
    cache = DecisionCache(tmp_path / "cache.sqlite")
    cache.put(row)  # identical row: no-op
    with pytest.raises(CacheError):
        cache.put(row.__class__(**{**row.__dict__, "response_json": "{}"}))


def test_cached_rows_hold_the_request_as_sent(tmp_layout: Layout, tmp_path: Path) -> None:
    import json

    rec = Recorder()
    client = make_client(tmp_layout, tmp_path, rec)
    row = client.decide([spec()])[0].row
    assert row is not None
    sent = json.loads(row.request_json)
    assert sent == rec.bodies[0]
    assert sent["provider"] == {"data_collection": "deny"}
    assert "test-key" not in row.request_json and "test-key" not in row.meta_json
    assert row.chunk == "NA-05" and row.model_build == f"{MODEL}-build-7"
