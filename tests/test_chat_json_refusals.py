"""``DecisionClient.chat_json`` shares every guard of the decision path (PRD NA-09 S7, AC4; CLAUDE.md B8,
C12–C14, D15).

Each refusal raises ``Refused`` before the cache is read and before any transport call, online and offline:
(a) third party, (b) test period before the freeze, (c) val-B before allow_val_b, (d) unmasked without a
registered probe, (e) not in ``frozen.yaml`` ``chat_models``, (f) ``:free`` without approval, and no local
backend. The cache, the offline mode, the projection check, the per-call reservation, the provider's
``data_collection: deny`` and the strict answer parser are tested on a mock transport.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from dm_fakes import LOCAL, MODEL, TRAIN_INFO, Recorder, make_client, spec, spend_events
from newsaction.config import BudgetConfig
from newsaction.dm import CacheMiss, Refused
from newsaction.dm.client import ChatSpec, DecisionClient, StateInfo
from newsaction.dm.costmodel import Price
from newsaction.dm.schemas import ChatMessage, ChatProvider, ChatRequest, parse_chat_response
from newsaction.ledger import BudgetExceeded
from newsaction.paths import Layout

CHAT = "test/chatter"
CHAT_PRICE = Price(prompt=1e-6, request=0.0, discount=0.0, completion=4e-6)
KEYS = ["fall", "flat", "rise"]
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {k: {"type": "number"} for k in KEYS},
    "required": KEYS,
    "additionalProperties": False,
}
MESSAGES = [{"role": "system", "content": "Answer in JSON."}, {"role": "user", "content": "State: {}"}]


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")


def info(**kw: Any) -> StateInfo:
    return TRAIN_INFO.model_copy(update=kw)


def chat_body(values: dict[str, Any], *, finish: str = "stop", cost: float | None = 2e-5) -> dict[str, Any]:
    usage: dict[str, Any] = {"prompt_tokens": 120, "completion_tokens": 30}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-chat-1",
        "model": f"{CHAT}-2026-01-01",
        "provider": "TestProvider",
        "choices": [
            {"finish_reason": finish, "message": {"role": "assistant", "content": json.dumps(values)}}
        ],
        "usage": usage,
    }


def chat_ok(body: dict[str, Any], n: int) -> httpx.Response:
    return httpx.Response(200, json=chat_body({"fall": 0.2, "flat": 0.5, "rise": 0.3}))


def set_frozen(layout: Layout, **values: Any) -> None:
    path = layout.configs / "frozen.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(values)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def client_for(
    layout: Layout,
    tmp_path: Path,
    rec: Recorder,
    *,
    offline: bool = False,
    budget: BudgetConfig | None = None,
) -> DecisionClient:
    set_frozen(layout, chat_models=[{"id": CHAT, "include": True, "reason": "test"}])
    kw: dict[str, Any] = {"pilot": False, "offline": offline, "prices": {CHAT: CHAT_PRICE}}
    if budget is not None:
        kw["budget"] = budget
    return make_client(layout, tmp_path, rec, **kw)


def chat_spec(model: str = CHAT, state_info: StateInfo = TRAIN_INFO, **kw: Any) -> ChatSpec:
    req = ChatRequest(
        model=model,
        messages=tuple(ChatMessage.model_validate(m) for m in MESSAGES),
        schema_name="answer",
        json_schema=SCHEMA,
        temperature=0.0,
        seed=2026,
        max_tokens=50,
    )
    return ChatSpec(req, state_info, state_sha256="ab" * 32, sum_tol=0.05, tag="test", **kw)


def assert_refused(client: DecisionClient, rec: Recorder, s: ChatSpec, rule: str) -> None:
    with pytest.raises(Refused) as exc:
        client.chat_json_batch([s])
    assert exc.value.rule == rule
    with pytest.raises(Refused):
        client.dry_run_chat([s])
    with pytest.raises(Refused):
        client.chat_json(
            s.request.model,
            [m.model_dump() for m in s.request.messages],
            SCHEMA,
            info=s.info,
            sum_tol=0.05,
        )
    assert rec.calls == 0


TEST_STATE = info(event_id="W0:1:2026-03-02", session=date(2026, 3, 2), split="test")
VAL_B_STATE = info(event_id="W0:1:2025-11-03", session=date(2025, 11, 3), split="val_b")


@pytest.mark.parametrize("offline", [False, True])
def test_a_third_party(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec, offline=offline)
    assert_refused(client, rec, chat_spec(state_info=info(third_party_ok_all=False)), "third_party")


@pytest.mark.parametrize("offline", [False, True])
def test_b_test_period_before_the_freeze(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec, offline=offline)
    assert_refused(client, rec, chat_spec(state_info=TEST_STATE), "test_period")
    # the session alone is enough, whatever the split label says, and so is the label alone
    assert_refused(client, rec, chat_spec(state_info=info(session=date(2026, 1, 2))), "test_period")
    assert_refused(client, rec, chat_spec(state_info=info(split="test")), "test_period")


@pytest.mark.parametrize("offline", [False, True])
def test_c_val_b_before_allow_val_b(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec, offline=offline)
    set_frozen(tmp_layout, allow_val_b=False)
    assert_refused(client, rec, chat_spec(state_info=VAL_B_STATE), "val_b")
    assert_refused(client, rec, chat_spec(state_info=info(session=date(2025, 12, 31))), "val_b")


def test_c_val_b_after_allow_val_b(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec)
    set_frozen(tmp_layout, allow_val_b=True)
    assert client.chat_json_batch([chat_spec(state_info=VAL_B_STATE)])[0].ok
    assert rec.calls == 1


@pytest.mark.parametrize("offline", [False, True])
def test_d_unmasked_without_probe(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec, offline=offline)
    assert_refused(client, rec, chat_spec(state_info=info(masked=False)), "unmasked")


@pytest.mark.parametrize("offline", [False, True])
def test_e_not_in_chat_models(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec, offline=offline)
    assert_refused(client, rec, chat_spec(model="test/other-chatter"), "eligibility")
    # a decision model's eligibility does not make it a chat model, and the reverse
    set_frozen(tmp_layout, eligible_models=[{"id": MODEL, "include": True, "reason": "test"}])
    assert_refused(client, rec, chat_spec(model=MODEL), "eligibility")
    with pytest.raises(Refused) as exc:
        client.decide([spec(model=CHAT)])
    assert exc.value.rule == "eligibility"
    set_frozen(tmp_layout, chat_models=[{"id": CHAT, "include": False, "reason": "excluded"}])
    assert_refused(client, rec, chat_spec(), "eligibility")


@pytest.mark.parametrize("offline", [False, True])
def test_f_free_without_approval(tmp_layout: Layout, tmp_path: Path, offline: bool) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec, offline=offline)
    free = f"{CHAT}:free"
    set_frozen(tmp_layout, chat_models=[{"id": free, "include": True, "reason": "test"}])
    assert_refused(client, rec, chat_spec(model=free), "free")


def test_no_local_backend(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec)
    set_frozen(tmp_layout, chat_models=[{"id": LOCAL, "include": True, "reason": "test"}])
    assert_refused(client, rec, chat_spec(model=LOCAL), "eligibility")


def test_one_bad_request_sends_nothing(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec)
    with pytest.raises(Refused):
        client.chat_json_batch([chat_spec(), chat_spec(state_info=TEST_STATE)])
    assert rec.calls == 0


def test_provider_is_deny_only_and_sent_with_every_request(tmp_layout: Layout, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ChatProvider(data_collection="allow")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ChatProvider(require_parameters=False)  # type: ignore[arg-type]
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec)
    res = client.chat_json(CHAT, MESSAGES, SCHEMA, info=TRAIN_INFO, seed=2026, sum_tol=0.05)
    assert res.ok and res.parsed is not None and res.parsed.valid
    body = rec.bodies[0]
    assert body["provider"] == {"data_collection": "deny", "require_parameters": True}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["temperature"] == 0.0 and body["seed"] == 2026
    assert rec.headers[0]["authorization"] == "Bearer test-key-not-real"
    assert res.parsed.probs == (0.2, 0.5, 0.3)


def test_cache_hit_and_offline(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec)
    first = client.chat_json_batch([chat_spec()])[0]
    lines = len(spend_events(tmp_layout))
    again = client.chat_json_batch([chat_spec(), chat_spec()])
    assert rec.calls == 1 and all(r.cached for r in again) and again[0].key == first.key
    assert len(spend_events(tmp_layout)) == lines  # a hit writes no ledger line
    # another repeat index is another key; the offline client refuses to send it
    offline = DecisionClient(
        "NA-05", layout=tmp_layout, offline=True, cache=client.cache, ledger=client.ledger,
        cost_model=client.cost_model,
    )  # fmt: skip
    assert offline.chat_json_batch([chat_spec()])[0].cached
    with pytest.raises(CacheMiss):
        offline.chat_json_batch([chat_spec(repeat_idx=1)])
    assert rec.calls == 1


def test_chat_key_differs_from_every_field(tmp_layout: Layout, tmp_path: Path) -> None:
    client = client_for(tmp_layout, tmp_path, Recorder(chat_ok))
    base = chat_spec()
    keys = {client.chat_key(base)}
    req = base.request
    for upd in (
        {"model": "test/chatter-2"},
        {"temperature": 0.5},
        {"seed": 7},
        {"max_tokens": 51},
        {"schema_name": "other"},
        {"messages": (*req.messages, ChatMessage(role="user", content="more"))},
    ):
        keys.add(client.chat_key(ChatSpec(req.model_copy(update=upd), base.info)))
    keys.add(client.chat_key(chat_spec(repeat_idx=1)))
    assert len(keys) == 8
    assert client.chat_key(base) != client.key(spec())


def test_budget_projection_refuses_before_sending(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(chat_ok)
    tiny = BudgetConfig(total_usd=1.0, reserve_usd=0.0, chunk_caps={"NA-05": 1e-9})
    client = client_for(tmp_layout, tmp_path, rec, budget=tiny)
    with pytest.raises(BudgetExceeded):
        client.chat_json_batch([chat_spec()])
    assert rec.calls == 0
    assert not [e for e in spend_events(tmp_layout) if e["event"] in ("reserve", "spend")]


def test_reserve_then_record_and_reconcile(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(chat_ok)
    client = client_for(tmp_layout, tmp_path, rec)
    client.chat_json_batch([chat_spec(repeat_idx=i) for i in range(4)], concurrency=2)
    ev = spend_events(tmp_layout)
    reserves = {e["rid"]: i for i, e in enumerate(ev) if e["event"] == "reserve"}
    spends = [(i, e) for i, e in enumerate(ev) if e["event"] == "spend"]
    assert len(spends) == 4
    for i, e in spends:
        assert e["rid"] in reserves and reserves[e["rid"]] < i and e["close"]
        assert e["usd"] == pytest.approx(2e-5)
    assert abs(client.reconcile()) < 1e-12


def test_http_error_releases_the_hold(tmp_layout: Layout, tmp_path: Path) -> None:
    rec = Recorder(lambda body, n: httpx.Response(404, json={"error": "no endpoint for this data policy"}))
    client = client_for(tmp_layout, tmp_path, rec)
    res = client.chat_json_batch([chat_spec()])[0]
    assert not res.ok and res.status == 404
    ev = spend_events(tmp_layout)
    assert [e["event"] for e in ev] == ["reserve", "release"]
    assert client.cache.get(res.key) is None


def test_usage_without_cost_is_priced(tmp_layout: Layout, tmp_path: Path) -> None:
    def no_cost(body: dict[str, Any], n: int) -> httpx.Response:
        return httpx.Response(200, json=chat_body({"fall": 0.2, "flat": 0.5, "rise": 0.3}, cost=None))

    rec = Recorder(no_cost)
    client = client_for(tmp_layout, tmp_path, rec)
    res = client.chat_json_batch([chat_spec()])[0]
    assert res.row is not None and res.row.cost_source == "computed"
    assert res.row.cost == pytest.approx(120 * 1e-6 + 30 * 4e-6)
    assert abs(client.reconcile()) < 1e-12


@pytest.mark.parametrize(
    ("values", "finish", "valid", "renorm"),
    [
        ({"fall": 0.2, "flat": 0.5, "rise": 0.3}, "stop", True, False),
        ({"fall": 0.2, "flat": 0.5, "rise": 0.33}, "stop", True, True),  # 1.03: within 0.05
        (
            {"fall": 0.35, "flat": 0.35, "rise": 0.35},
            "stop",
            True,
            True,
        ),  # exactly 1.05 (float 1.0500000000000003)
        ({"fall": 0.35, "flat": 0.3, "rise": 0.3}, "stop", True, True),  # exactly 0.95
        ({"fall": 0.35, "flat": 0.35, "rise": 0.3501}, "stop", False, False),  # 1.0501
        ({"fall": 0.2, "flat": 0.5, "rise": 0.4}, "stop", False, False),  # 1.10
        ({"fall": 0.2, "flat": 0.5, "rise": -0.1}, "stop", False, False),
        ({"fall": 0.2, "flat": 0.8}, "stop", False, False),
        ({"fall": 0.2, "flat": 0.5, "rise": 0.3, "x": 0.0}, "stop", False, False),
        ({"fall": "0.2", "flat": 0.5, "rise": 0.3}, "stop", False, False),
        ({"fall": 0.2, "flat": 0.5, "rise": 0.3}, "length", False, False),
    ],
)
def test_parser(values: dict[str, Any], finish: str, valid: bool, renorm: bool) -> None:
    p = parse_chat_response(chat_body(values, finish=finish), KEYS, 0.05)
    assert p.valid is valid
    assert p.renormalized is renorm
    if valid:
        assert p.probs is not None and sum(p.probs) == pytest.approx(1.0)
    else:
        assert p.probs is None
    assert p.values == values  # the raw answer is never altered


def test_parser_envelope() -> None:
    assert not parse_chat_response(None, KEYS, 0.05).valid
    assert not parse_chat_response({"model": "x", "choices": [], "usage": {}}, KEYS, 0.05).valid
    body = chat_body({"fall": 0.2, "flat": 0.5, "rise": 0.3})
    body["choices"][0]["message"]["content"] = "not json"
    assert not parse_chat_response(body, KEYS, 0.05).valid


def test_schema_must_require_every_property() -> None:
    with pytest.raises(ValueError):
        ChatRequest(
            model=CHAT,
            messages=(ChatMessage(role="user", content="x"),),
            schema_name="answer",
            json_schema={**SCHEMA, "required": KEYS[:2]},
            temperature=0.0,
            max_tokens=10,
        )
    with pytest.raises(ValueError):
        ChatRequest(
            model=CHAT,
            messages=(ChatMessage(role="user", content="x"),),
            schema_name="answer",
            json_schema={k: v for k, v in SCHEMA.items() if k != "additionalProperties"},
            temperature=0.0,
            max_tokens=10,
        )


def test_the_batch_projection_is_checked_before_the_first_send(tmp_layout: Layout, tmp_path: Path) -> None:
    """A cap that one call fits but three do not: the projection refuses the batch before anything is sent
    (the per-call reservation alone would send the first call)."""
    probe = client_for(tmp_layout, tmp_path / "probe", Recorder(chat_ok))
    one = probe.cost_model.estimate_chat(CHAT, chat_spec().request).usd
    rec = Recorder(chat_ok)
    cap = BudgetConfig(total_usd=1.0, reserve_usd=0.0, chunk_caps={"NA-05": 1.5 * one})
    client = client_for(tmp_layout, tmp_path, rec, budget=cap)
    with pytest.raises(BudgetExceeded):
        client.chat_json_batch([chat_spec(repeat_idx=i) for i in range(3)], concurrency=1)
    assert rec.calls == 0
    assert client.chat_json_batch([chat_spec()])[0].ok and rec.calls == 1
