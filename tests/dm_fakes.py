"""Shared fakes for the tests/test_dm_*.py files: a mock OpenRouter transport, a fake local model and a client
wired to a throwaway repository (no network, no real ledger, no real cache)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from newsaction.config import BudgetConfig
from newsaction.dm import CostConfig, CostDefault
from newsaction.dm.cache import DecisionCache
from newsaction.dm.client import CallSpec, DecisionClient, StateInfo
from newsaction.dm.costmodel import CostModel, Price
from newsaction.dm.schemas import DecisionRequest, QuestionSpec
from newsaction.ledger import SpendLedger
from newsaction.paths import Layout

MODEL = "test/decider"
LOCAL = "local/fake"
PRICE = Price(prompt=1e-6, request=0.0, discount=0.0)  # $1 per million tokens
BUDGET = BudgetConfig(total_usd=1.0, reserve_usd=0.0, chunk_caps={"NA-05": 0.2, "NA-06": 0.5})
COST_CONFIG = CostConfig(
    default=CostDefault(billing_basis="per_question", bytes_per_token=3.0, overhead_tokens=64, safety=1.5),
    models={},
)
QUESTIONS = {
    "justified_move": QuestionSpec(
        type="score",
        instructions="How will the stock move?",
        criteria=["big fall", "fall", "flat", "rise", "big rise"],
    ),
    "materiality": QuestionSpec(
        type="choice",
        instructions="Is it new?",
        criteria={"new_information": "new", "no_new_information": "not new"},
    ),
}
STATE: dict[str, Any] = {
    "company": {"sector": "Energy"},
    "news": [{"headline": "The company beats", "snippet": "x"}],
}
TRAIN_INFO = StateInfo(
    source="states",
    file="work/states/callA_d0_E3.parquet",
    event_id="W0:1:2024-08-01",
    session=date(2024, 8, 1),
    split="train",
    call="A",
    masked=True,
    third_party_ok_all=True,
)


def answers_for(questions: Mapping[str, Any]) -> dict[str, Any]:
    """Uniform, well-formed answers to the questions of a request body."""
    out: dict[str, Any] = {}
    for qid, q in questions.items():
        crit = q["criteria"]
        if q["type"] == "choice":
            keys = list(crit)
            p = {k: 1.0 / len(keys) for k in keys}
            out[qid] = {"type": "choice", "choice": keys[0], "probabilities": p, "confidence": 0.1}
        else:
            k = len(crit)
            p = {str(i): 1.0 / k for i in range(k)}
            legend = {str(i): c for i, c in enumerate(crit)}
            score = sum(i / k for i in range(k))
            out[qid] = {
                "type": "score",
                "score": score,
                "legend": legend,
                "probabilities": p,
                "confidence": 0.1,
            }
    return out


def ok_response(body: Mapping[str, Any], *, cost: float | None = 0.0001, tokens: int = 100) -> dict[str, Any]:
    usage: dict[str, Any] = {"input_tokens": tokens, "output_tokens": 0}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "model": f"{body['model']}-build-7",
        "provider": "TestProvider",
        "answers": answers_for(body["questions"]),
        "usage": usage,
    }


class Recorder:
    """A mock transport handler that records every request body and answers with ``respond``."""

    def __init__(self, respond: Callable[[dict[str, Any], int], httpx.Response] | None = None) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []
        self._respond = respond

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        self.headers.append(request.headers)
        if self._respond is not None:
            return self._respond(body, len(self.bodies))
        return httpx.Response(200, json=ok_response(body))

    @property
    def calls(self) -> int:
        return len(self.bodies)


class FakeLocal:
    """A local model that answers uniformly (cost 0)."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def build(self) -> str:
        return f"{LOCAL}@abc"

    @property
    def params(self) -> dict[str, Any]:
        return {"revision": "abc"}

    def predict(self, request: DecisionRequest) -> dict[str, Any]:
        self.calls += 1
        body = request.body({})
        out = ok_response(body, cost=0.0)
        out["model"] = self.build
        return out


def make_client(
    layout: Layout,
    tmp_path: Path,
    handler: Recorder,
    *,
    pilot: bool = True,
    offline: bool = False,
    budget: BudgetConfig = BUDGET,
    local: FakeLocal | None = None,
    prices: Mapping[str, Price] | None = None,
) -> DecisionClient:
    return DecisionClient(
        "NA-05",
        layout=layout,
        transport=httpx.MockTransport(handler),
        cache=DecisionCache(tmp_path / "cache.sqlite"),
        ledger=SpendLedger("NA-05", path=layout.ledgers / "spend.jsonl", budget=budget),
        cost_model=CostModel(COST_CONFIG, {MODEL: PRICE, **(prices or {})}),
        local_models={LOCAL: local or FakeLocal()},
        pilot=pilot,
        offline=offline,
    )


def spec(
    *,
    model: str = MODEL,
    state: Any = None,
    questions: Mapping[str, QuestionSpec] | None = None,
    info: StateInfo = TRAIN_INFO,
    params: Mapping[str, Any] | None = None,
    repeat_idx: int = 0,
) -> CallSpec:
    req = DecisionRequest(
        model=model, state=STATE if state is None else state, questions=dict(questions or QUESTIONS)
    )
    return CallSpec(req, info, params=dict(params or {}), repeat_idx=repeat_idx, tag="test")


def spend_events(layout: Layout) -> list[dict[str, Any]]:
    path = layout.ledgers / "spend.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
