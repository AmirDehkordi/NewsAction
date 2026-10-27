"""The decision-model client (PRD NA-05 S3; CLAUDE.md C12–C14, D15): the only sanctioned path to a decision
model, remote (OpenRouter Decisions API) or local (``laya_local``).

``DecisionClient.run(specs)`` (``decide`` is the synchronous form) goes through these steps:

1. **Refusals.** ``check`` raises ``Refused``; nothing is read from the cache and nothing is sent.
   - (a) ``third_party``: a state with ``third_party_ok_all`` False, to an API model (CLAUDE.md D15).
   - (b) ``test_period``: a state of a session on or after the test start (``configs/splits.yaml``), before
     the freeze (``lock.is_frozen``), for every model, local ones included (CLAUDE.md B8, C13).
   - (c) ``val_b``: a val-B state to an API model while ``configs/frozen.yaml`` ``allow_val_b`` is false
     (C13).
   - (d) ``unmasked``: an unmasked state without a registered probe tag (``configs/dm.yaml``
     ``registered_probes``).
   - (e) ``eligibility``: a model that ``configs/frozen.yaml`` ``eligible_models`` does not include, unless
     the client runs with ``pilot=True`` (the catalog smoke test and the pilot).
   - (f) ``free``: a ``:free`` model id without the operator's approval in ``frozen.yaml``
     ``free_model_approvals``; ``pilot=True`` does not lift it.
   - ``pilot_period``: with ``pilot=True``, a non-synthetic state after the train split (PRD NA-05: pilot
     states are train-period or synthetic).
2. **Cache** (``cache.DecisionCache``): a hit returns the stored response, with no network call and no spend.
   With ``offline=True`` any miss raises ``CacheMiss`` before anything is sent (verification, CLAUDE.md C14).
3. **Budget** (PREREG §13). ``dry_run`` projects tokens and USD for the requests to send (``costmodel``). If
   the projection exceeds what the chunk cap or the total cap leaves after recorded spend and open holds,
   ``BudgetExceeded`` is raised before any send. Each API call then reserves its estimate in
   ``ledgers/spend.jsonl`` before it is sent and records ``usage.cost`` after it. An HTTP error releases the
   hold; a call cancelled in flight keeps it, since it may have been billed.
4. **Transport.** httpx under an asyncio semaphore; 429, 5xx and transport errors are retried with tenacity
   (exponential backoff with full jitter, at least any ``Retry-After``; ``retry.max_attempts`` attempts).
   Every request carries ``provider = {"data_collection": "deny"}`` (the request schema allows nothing else).
   The API key comes from the environment or ``.env`` and appears only in the Authorization header.

Every HTTP 200 is stored in the cache, valid or not, with its cost; every attempt is logged in the cache's
``attempts`` table. ``reconcile()`` is the chunk's recorded spend minus Σ cost of its cached responses (GAC4).

**Chat completions** (PRD NA-09 S7). ``chat_json(model, messages, json_schema, info=…)`` (one request) and
``chat_json_batch(specs)`` send a ``ChatRequest`` (one JSON object answer, strict json_schema) to
``api.chat_url`` through the same steps: the refusals (a)–(f) and the pilot rule, with eligibility read from
``frozen.yaml`` ``chat_models`` instead of ``eligible_models`` and no local backend; the same cache (the key
payload carries ``endpoint: chat``, so it can never equal a decision key), the offline mode, the projection
check (``costmodel.estimate_chat``), the per-call reservation and record in the spend ledger, the retries and
the semaphore. The provider object can only say ``data_collection: deny`` (with ``require_parameters``).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, model_validator
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt

from newsaction import lock
from newsaction.config import load_frozen, load_splits
from newsaction.dm import CATALOG_FILE, CacheMiss, DmConfig, DMError, Refused, dm_config, is_local
from newsaction.dm.cache import CachedRow, DecisionCache, request_key
from newsaction.dm.costmodel import CostModel, Estimate
from newsaction.dm.schemas import (
    ChatMessage,
    ChatRequest,
    DecisionRequest,
    ParsedChat,
    ParsedResponse,
    parse_chat_response,
    parse_response,
)
from newsaction.ledger import SPEND, BudgetExceeded, Reservation, SpendLedger
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso
from newsaction.states.questions import canonical_json

RETRY_STATUS: Final = frozenset({429})
PILOT_SPLITS: Final = frozenset({"robustness", "train"})  # sessions ≤ the train end (PRD NA-05)
_EPS: Final = 1e-12
_JITTER: Final = random.Random(2026)  # retry timing only; no result depends on it


@dataclass(frozen=True)
class Rules:
    test_start: date
    val_b: tuple[date, date]
    train_end: date
    eligible: frozenset[str]
    chat_eligible: frozenset[str]
    free_approved: frozenset[str]
    allow_val_b: bool
    frozen: bool


class StateInfo(BaseModel):
    """Provenance of a state: what the refusal rules and the audit need to know."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["states", "synthetic"]
    file: str | None = None  # the registered state file (work/…) of a "states" row
    event_id: str | None = None
    session: date | None = None
    split: str | None = None
    call: Literal["A", "B", "M"] | None = None
    masked: bool
    third_party_ok_all: bool
    probe: str | None = None

    @model_validator(mode="after")
    def _complete(self) -> StateInfo:
        if self.source == "states" and (self.event_id is None or self.session is None or self.split is None):
            raise ValueError("a state from a state file needs event_id, session and split")
        if self.source == "synthetic" and (self.session is not None or self.split is not None):
            raise ValueError("a synthetic state has no session and no split")
        return self


@dataclass(frozen=True)
class CallSpec:
    """One decision request with its provenance. ``params`` are extra body fields (part of the cache key);
    ``repeat_idx`` asks the same request again under another key; ``tag`` labels the call in the cache."""

    request: DecisionRequest
    info: StateInfo
    params: Mapping[str, Any] = field(default_factory=dict)
    repeat_idx: int = 0
    tag: str = ""


@dataclass(frozen=True)
class CallResult:
    spec: CallSpec
    key: str
    cached: bool
    row: CachedRow | None  # the stored response; None after an HTTP error
    parsed: ParsedResponse | None
    status: int | None
    error: str | None
    attempts: int
    latency_ms: float | None

    @property
    def ok(self) -> bool:
        return self.row is not None


@dataclass(frozen=True)
class ChatSpec:
    """One chat request with its provenance. ``state_sha256`` is that of the state the messages carry (audit);
    ``sum_tol`` makes the answer a probability vector over the schema's keys (``parse_chat_response``)."""

    request: ChatRequest
    info: StateInfo
    state_sha256: str | None = None
    sum_tol: float | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    repeat_idx: int = 0
    tag: str = ""


@dataclass(frozen=True)
class ChatResult:
    spec: ChatSpec
    key: str
    cached: bool
    row: CachedRow | None
    parsed: ParsedChat | None
    status: int | None
    error: str | None
    attempts: int
    latency_ms: float | None

    @property
    def ok(self) -> bool:
        return self.row is not None


AnySpec = CallSpec | ChatSpec


@dataclass(frozen=True)
class Projection:
    n_requests: int
    n_unique: int
    n_cached: int
    n_send: int
    tokens: float
    usd: float
    by_model: dict[str, dict[str, float]]


class LocalModel(Protocol):
    """A local decision model (``local/…``): nothing leaves the machine, usage.cost is 0."""

    @property
    def build(self) -> str: ...

    @property
    def params(self) -> dict[str, Any]: ...

    def predict(self, request: DecisionRequest) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _Outcome:
    status: int | None
    text: str
    headers: dict[str, str]
    latency_ms: float
    attempt: int
    error: str | None

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status in RETRY_STATUS or self.status >= 500


class _Retry(Exception):
    def __init__(self, outcome: _Outcome) -> None:
        super().__init__(f"status {outcome.status}")
        self.outcome = outcome


def read_api_key(env: str, root: Path) -> str:
    """The API key from the environment, else from ``<root>/.env``. Never printed or logged."""
    value = os.environ.get(env, "").strip()
    if value:
        return value
    path = root / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, rest = line.strip().partition("=")
            if sep and name.strip() == env:
                value = rest.split(" #", 1)[0].strip().strip("\"'")
                if value:
                    return value
    raise DMError(f"{env} is not set (environment or .env)")


def _eligible(frozen: Any, section: str = "eligible_models") -> set[str]:
    rows = getattr(frozen, section, None) or []
    return {str(r["id"]) for r in rows if isinstance(r, Mapping) and r.get("include") is True}


def _approved_free(frozen: Any) -> set[str]:
    approvals = getattr(frozen, "free_model_approvals", None) or {}
    return {str(k) for k, v in approvals.items() if v}


class DecisionClient:
    """See the module docstring. One client per chunk; ``close()`` releases the cache."""

    def __init__(
        self,
        chunk: str,
        *,
        offline: bool = False,
        pilot: bool = False,
        layout: Layout | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        cache: DecisionCache | None = None,
        ledger: SpendLedger | None = None,
        cost_model: CostModel | None = None,
        local_models: Mapping[str, LocalModel] | None = None,
        concurrency: int | None = None,
        session_id: str | None = None,
    ) -> None:
        self.lay = resolve_layout(layout)
        self.chunk = chunk
        self.offline = offline
        self.pilot = pilot
        self.config: DmConfig = dm_config(self.lay)
        self.cache = cache if cache is not None else DecisionCache(self.lay.root / self.config.cache)
        self.ledger = ledger if ledger is not None else SpendLedger(chunk, path=self.lay.ledgers / SPEND)
        self.cost_model = (
            cost_model
            if cost_model is not None
            else CostModel.from_files(
                self.config.costmodel,
                self.lay.root / CATALOG_FILE,
                self.lay.root / self.config.api.chat_catalog,
            )
        )
        self._transport = transport
        self._local: dict[str, LocalModel] = dict(local_models or {})
        self.concurrency = concurrency or self.config.api.concurrency
        self.session_id = session_id if session_id is not None else f"newsaction-{chunk}"
        self._key: str | None = None

    def close(self) -> None:
        self.cache.close()

    def __enter__(self) -> DecisionClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- refusals --------------------------------------------------------------------------------

    def rules(self) -> Rules:
        """The inputs of the refusal rules, read once per batch (``frozen.yaml`` can change in a session)."""
        splits = load_splits(self.lay.configs / "splits.yaml").splits
        frozen = load_frozen(self.lay.configs / "frozen.yaml")
        return Rules(
            test_start=splits["test"].start,
            val_b=(splits["val_b"].start, splits["val_b"].end),
            train_end=splits["train"].end,
            eligible=frozenset(_eligible(frozen)),
            chat_eligible=frozenset(_eligible(frozen, "chat_models")),
            free_approved=frozenset(_approved_free(frozen)),
            allow_val_b=bool(frozen.allow_val_b),
            frozen=lock.is_frozen(self.lay),
        )

    def check(self, spec: AnySpec, rules: Rules | None = None) -> None:
        """Raise ``Refused`` if ``spec`` may not be sent (rules (a)–(f) of the module docstring)."""
        r = self.rules() if rules is None else rules
        model, info = spec.request.model, spec.info
        chat = isinstance(spec, ChatSpec)
        local = is_local(model)
        if chat and local:
            raise Refused("eligibility", f"{model}: chat_json has no local backend")
        if model.endswith(":free") and model not in r.free_approved:
            raise Refused("free", f"{model} is a :free endpoint without operator approval (CLAUDE.md C13)")
        if not self.pilot and model not in (r.chat_eligible if chat else r.eligible):
            section = "chat_models" if chat else "eligible_models"
            raise Refused("eligibility", f"{model} is not in configs/frozen.yaml {section}")
        if not local and not info.third_party_ok_all:
            raise Refused("third_party", f"state {info.event_id} holds an article that is not third-party OK")
        in_test = info.split == "test" or (info.session is not None and info.session >= r.test_start)
        if in_test and not r.frozen:
            raise Refused("test_period", f"state {info.event_id} is in the test period and nothing is frozen")
        in_val_b = info.split == "val_b" or (
            info.session is not None and r.val_b[0] <= info.session <= r.val_b[1]
        )
        if not local and in_val_b and not r.allow_val_b:
            raise Refused("val_b", f"state {info.event_id} is val-B and allow_val_b is false")
        if not info.masked and info.probe not in self.config.registered_probes:
            raise Refused("unmasked", f"state {info.event_id} is unmasked and has no registered probe tag")
        if self.pilot and info.source == "states":
            late = info.session is None or info.session > r.train_end
            if late or info.split not in PILOT_SPLITS:
                raise Refused("pilot_period", f"pilot state {info.event_id} is after the train split")

    def check_all(self, specs: Sequence[AnySpec]) -> None:
        rules = self.rules()
        for s in specs:
            self.check(s, rules)

    # --- keys, projections -----------------------------------------------------------------------

    def local_model(self, model: str) -> LocalModel:
        if model not in self._local:
            from newsaction.dm.laya_local import LayaLocal

            self._local[model] = LayaLocal(model, self.config.laya)
        return self._local[model]

    def prepare(self, spec: CallSpec) -> CallSpec:
        """The spec as sent: a model in ``state_as_text`` gets an object state as its canonical JSON text."""
        req = spec.request
        if req.model in self.config.state_as_text and not isinstance(req.state, str):
            return replace(spec, request=req.model_copy(update={"state": req.state_text()}))
        return spec

    def key_params(self, spec: CallSpec) -> dict[str, Any]:
        model = spec.request.model
        if is_local(model):
            return {**self.local_model(model).params, **spec.params}
        return dict(spec.params)

    def key(self, spec: CallSpec) -> str:
        spec = self.prepare(spec)
        return request_key(spec.request.model, spec.request, self.key_params(spec), spec.repeat_idx)

    def estimate(self, spec: CallSpec) -> Estimate:
        return self.cost_model.estimate(spec.request.model, spec.request)

    def _unique(self, specs: Sequence[CallSpec]) -> dict[str, CallSpec]:
        out: dict[str, CallSpec] = {}
        for s in specs:
            out.setdefault(self.key(s), s)
        return out

    def dry_run(self, specs: Sequence[CallSpec]) -> Projection:
        """Projected tokens and USD of the requests that would be sent (refusals checked first)."""
        self.check_all(specs)
        specs = [self.prepare(s) for s in specs]
        unique = self._unique(specs)
        send = {k: s for k, s in unique.items() if self.cache.get(k) is None}
        by_model: dict[str, dict[str, float]] = {}
        tokens = usd = 0.0
        for s in send.values():
            est = self.estimate(s)
            m = by_model.setdefault(s.request.model, {"calls": 0.0, "tokens": 0.0, "usd": 0.0})
            m["calls"] += 1
            m["tokens"] += est.tokens
            m["usd"] += est.usd
            tokens += est.tokens
            usd += est.usd
        return Projection(
            n_requests=len(specs),
            n_unique=len(unique),
            n_cached=len(unique) - len(send),
            n_send=len(send),
            tokens=tokens,
            usd=usd,
            by_model=by_model,
        )

    def budget_left(self) -> float:
        t = self.ledger.totals()
        return min(
            t.chunk_cap_usd - t.chunk_usd - t.held_chunk_usd,
            t.total_cap_usd - t.total_usd - t.held_total_usd,
        )

    def _check_budget(self, proj: Projection) -> None:
        left = self.budget_left()
        if proj.usd > left + _EPS:
            raise BudgetExceeded(
                f"{self.chunk}: projection ${proj.usd:.6f} for {proj.n_send} calls exceeds the ${left:.6f} "
                "left under the chunk and total caps (PREREG §13: STOP and report)"
            )

    # --- running ---------------------------------------------------------------------------------

    def decide(self, specs: Sequence[CallSpec], *, concurrency: int | None = None) -> list[CallResult]:
        return asyncio.run(self.run(specs, concurrency=concurrency))

    async def run(self, specs: Sequence[CallSpec], *, concurrency: int | None = None) -> list[CallResult]:
        self.check_all(specs)
        specs = [self.prepare(s) for s in specs]
        keys = [self.key(s) for s in specs]
        done: dict[str, CallResult] = {}
        send: dict[str, CallSpec] = {}
        for k, s in zip(keys, specs, strict=True):
            if k in done or k in send:
                continue
            row = self.cache.get(k)
            if row is None:
                send[k] = s
            else:
                parsed = parse_response(row.response, s.request.questions)
                done[k] = CallResult(s, k, True, row, parsed, 200, None, 0, row.latency_ms)
        if send and self.offline:
            raise CacheMiss(f"{len(send)} of {len(keys)} requests are not in the cache (offline client)")
        remote = [s for s in send.values() if not is_local(s.request.model)]
        if remote:
            self._check_budget(self.dry_run(remote))
        conc = concurrency or self.concurrency
        if send:
            sem = asyncio.Semaphore(conc)
            try:
                async with self._http() as http, asyncio.TaskGroup() as tg:
                    tasks = [tg.create_task(self._one(http, sem, k, s, conc)) for k, s in send.items()]
            except ExceptionGroup as eg:  # surface the first failure (budget, ledger, cache) as itself
                raise eg.exceptions[0] from None
            for t in tasks:
                r = t.result()
                done[r.key] = r
        return [
            done[k] if done[k].spec is s else replace(done[k], spec=s)
            for k, s in zip(keys, specs, strict=True)
        ]

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=self.config.api.timeout_s,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
        )

    def _api_key(self) -> str:
        if self._key is None:
            self._key = read_api_key(self.config.api.key_env, self.lay.root)
        return self._key

    async def _one(
        self, http: httpx.AsyncClient, sem: asyncio.Semaphore, key: str, spec: CallSpec, conc: int
    ) -> CallResult:
        async with sem:
            if is_local(spec.request.model):
                return self._local_call(key, spec)
            return await self._remote_call(http, key, spec, conc)

    def _local_call(self, key: str, spec: CallSpec) -> CallResult:
        backend = self.local_model(spec.request.model)
        t0 = time.perf_counter()
        raw = backend.predict(spec.request)
        latency = (time.perf_counter() - t0) * 1000.0
        text = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        parsed = parse_response(raw, spec.request.questions)
        row = self._row(key, spec, text, parsed, cost=0.0, cost_source="local", latency_ms=latency)
        self.cache.put(row)
        return CallResult(spec, key, False, row, parsed, 200, None, 1, latency)

    async def _remote_call(self, http: httpx.AsyncClient, key: str, spec: CallSpec, conc: int) -> CallResult:
        est = self.estimate(spec)
        hold: Reservation = self.ledger.reserve(est.usd, note=f"{spec.request.model} {key[:16]}")
        url, body = self.config.api.decisions_url, self._body(spec)
        out = await self._post(http, key, spec.request.model, spec.tag, url, body, conc)  # cancel: hold kept
        if out.status != 200:
            self.ledger.release(hold)
            return CallResult(
                spec, key, False, None, None, out.status, out.error, out.attempt, out.latency_ms
            )
        try:
            raw: Any = json.loads(out.text)
        except json.JSONDecodeError:
            raw = None
        parsed = parse_response(raw, spec.request.questions)
        cost, source = self._cost(spec, parsed, est)
        row = self._row(key, spec, out.text, parsed, cost=cost, cost_source=source, latency_ms=out.latency_ms)
        try:
            self.ledger.record(
                cost,
                {"model": spec.request.model, "key": key, "cost_source": source, "tag": spec.tag},
                reservation=hold,
            )
        finally:
            self.cache.put(row)  # the answer is paid for: keep it even if the record raised over a cap
        return CallResult(spec, key, False, row, parsed, 200, None, out.attempt, out.latency_ms)

    def _cost(self, spec: CallSpec, parsed: ParsedResponse, est: Estimate) -> tuple[float, str]:
        resp = parsed.response
        if resp is not None and resp.usage.cost is not None:
            return float(resp.usage.cost), "usage"
        tokens = float(resp.usage.input_tokens) if resp is not None else est.tokens
        return self.cost_model.price(spec.request.model).usd(tokens), "computed"

    def _body(self, spec: CallSpec) -> bytes:
        req = spec.request
        if req.session_id is None and self.session_id:
            req = req.model_copy(update={"session_id": self.session_id})
        return json.dumps(req.body(spec.params), ensure_ascii=False).encode("utf-8")

    def _row(
        self,
        key: str,
        spec: CallSpec,
        response_text: str,
        parsed: ParsedResponse,
        *,
        cost: float,
        cost_source: str,
        latency_ms: float | None,
    ) -> CachedRow:
        resp = parsed.response
        meta = {**spec.info.model_dump(mode="json"), "tag": spec.tag}
        return CachedRow(
            key=key,
            model=spec.request.model,
            state_sha256=spec.request.state_sha256(),
            questions_sha256=spec.request.questions_sha256(),
            provider_json=canonical_json(spec.request.provider.model_dump()),
            params_json=canonical_json(self.key_params(spec)),
            repeat_idx=spec.repeat_idx,
            request_json=self._body(spec).decode("utf-8"),
            response_json=response_text,
            model_build=None if resp is None else resp.model,
            provider=None if resp is None else resp.provider,
            input_tokens=None if resp is None else resp.usage.input_tokens,
            output_tokens=None if resp is None else resp.usage.output_tokens,
            cost=cost,
            cost_source=cost_source,
            latency_ms=latency_ms,
            created_at=utc_now_iso(),
            chunk=self.chunk,
            tag=spec.tag,
            meta_json=canonical_json(meta),
            valid=parsed.valid,
            problems_json=json.dumps(parsed.problem_list(), ensure_ascii=False),
        )

    # --- chat completions (NA-09 S7) -------------------------------------------------------------

    def chat_key(self, spec: ChatSpec) -> str:
        """sha256 of {endpoint: chat, the request body, repeat_idx}; never equal to a decision key, whose
        payload has no ``endpoint``."""
        payload = {"endpoint": "chat", "body": spec.request.body(spec.params), "repeat_idx": spec.repeat_idx}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def dry_run_chat(self, specs: Sequence[ChatSpec]) -> Projection:
        """Projected tokens and USD of the chat requests that would be sent (refusals checked first)."""
        self.check_all(specs)
        unique: dict[str, ChatSpec] = {}
        for s in specs:
            unique.setdefault(self.chat_key(s), s)
        send = {k: s for k, s in unique.items() if self.cache.get(k) is None}
        by_model: dict[str, dict[str, float]] = {}
        tokens = usd = 0.0
        for s in send.values():
            est = self.cost_model.estimate_chat(s.request.model, s.request)
            m = by_model.setdefault(s.request.model, {"calls": 0.0, "tokens": 0.0, "usd": 0.0})
            m["calls"] += 1
            m["tokens"] += est.tokens
            m["usd"] += est.usd
            tokens += est.tokens
            usd += est.usd
        return Projection(
            n_requests=len(specs),
            n_unique=len(unique),
            n_cached=len(unique) - len(send),
            n_send=len(send),
            tokens=tokens,
            usd=usd,
            by_model=by_model,
        )

    def chat_json(
        self,
        model: str,
        messages: Sequence[Mapping[str, str]],
        json_schema: Mapping[str, Any],
        *,
        info: StateInfo,
        schema_name: str = "answer",
        temperature: float = 0.0,
        seed: int | None = None,
        max_tokens: int = 300,
        sum_tol: float | None = None,
        state_sha256: str | None = None,
        tag: str = "",
        repeat_idx: int = 0,
    ) -> ChatResult:
        """One chat request whose answer is a JSON object (PRD NA-09 S7), through every guard of ``run``."""
        request = ChatRequest(
            model=model,
            messages=tuple(ChatMessage.model_validate(dict(m)) for m in messages),
            schema_name=schema_name,
            json_schema=dict(json_schema),
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
        )
        spec = ChatSpec(request, info, state_sha256, sum_tol, repeat_idx=repeat_idx, tag=tag)
        return self.chat_json_batch([spec])[0]

    def chat_json_batch(
        self, specs: Sequence[ChatSpec], *, concurrency: int | None = None
    ) -> list[ChatResult]:
        return asyncio.run(self.run_chat(specs, concurrency=concurrency))

    async def run_chat(
        self, specs: Sequence[ChatSpec], *, concurrency: int | None = None
    ) -> list[ChatResult]:
        self.check_all(specs)
        keys = [self.chat_key(s) for s in specs]
        done: dict[str, ChatResult] = {}
        send: dict[str, ChatSpec] = {}
        for k, s in zip(keys, specs, strict=True):
            if k in done or k in send:
                continue
            row = self.cache.get(k)
            if row is None:
                send[k] = s
            else:
                parsed = parse_chat_response(row.response, s.request.keys(), s.sum_tol)
                done[k] = ChatResult(s, k, True, row, parsed, 200, None, 0, row.latency_ms)
        if send and self.offline:
            raise CacheMiss(f"{len(send)} of {len(keys)} chat requests are not in the cache (offline client)")
        if send:
            self._check_budget(self.dry_run_chat(list(send.values())))
            conc = concurrency or self.concurrency
            sem = asyncio.Semaphore(conc)
            try:
                async with self._http() as http, asyncio.TaskGroup() as tg:
                    tasks = [tg.create_task(self._chat_one(http, sem, k, s, conc)) for k, s in send.items()]
            except ExceptionGroup as eg:  # surface the first failure (budget, ledger, cache) as itself
                raise eg.exceptions[0] from None
            for t in tasks:
                r = t.result()
                done[r.key] = r
        return [
            done[k] if done[k].spec is s else replace(done[k], spec=s)
            for k, s in zip(keys, specs, strict=True)
        ]

    async def _chat_one(
        self, http: httpx.AsyncClient, sem: asyncio.Semaphore, key: str, spec: ChatSpec, conc: int
    ) -> ChatResult:
        async with sem:
            req = spec.request
            est = self.cost_model.estimate_chat(req.model, req)
            hold = self.ledger.reserve(est.usd, note=f"{req.model} {key[:16]}")
            body = json.dumps(req.body(spec.params), ensure_ascii=False).encode("utf-8")
            out = await self._post(http, key, req.model, spec.tag, self.config.api.chat_url, body, conc)
            if out.status != 200:
                self.ledger.release(hold)
                return ChatResult(
                    spec, key, False, None, None, out.status, out.error, out.attempt, out.latency_ms
                )
            try:
                raw: Any = json.loads(out.text)
            except json.JSONDecodeError:
                raw = None
            parsed = parse_chat_response(raw, req.keys(), spec.sum_tol)
            cost, source = self._chat_cost(spec, parsed, est)
            row = self._chat_row(key, spec, body, out.text, parsed, cost, source, out.latency_ms)
            try:
                self.ledger.record(
                    cost,
                    {"model": req.model, "key": key, "cost_source": source, "tag": spec.tag},
                    reservation=hold,
                )
            finally:
                self.cache.put(row)  # paid for: keep it even if the record raised over a cap
            return ChatResult(spec, key, False, row, parsed, 200, None, out.attempt, out.latency_ms)

    def _chat_cost(self, spec: ChatSpec, parsed: ParsedChat, est: Estimate) -> tuple[float, str]:
        resp = parsed.response
        if resp is not None and resp.usage.cost is not None:
            return float(resp.usage.cost), "usage"
        if resp is not None:
            u = resp.usage
            return self.cost_model.price(spec.request.model).usd(
                u.prompt_tokens, u.completion_tokens
            ), "computed"
        return est.usd, "estimated"  # an unreadable 200: the projection (an upper bound) is recorded

    def _chat_row(
        self,
        key: str,
        spec: ChatSpec,
        body: bytes,
        response_text: str,
        parsed: ParsedChat,
        cost: float,
        cost_source: str,
        latency_ms: float | None,
    ) -> CachedRow:
        req, resp = spec.request, parsed.response
        meta = {**spec.info.model_dump(mode="json"), "tag": spec.tag, "endpoint": "chat"}
        params = {
            "temperature": req.temperature,
            "seed": req.seed,
            "max_tokens": req.max_tokens,
            **spec.params,
        }
        return CachedRow(
            key=key,
            model=req.model,
            state_sha256=spec.state_sha256 or req.messages_sha256(),
            questions_sha256=req.schema_sha256(),
            provider_json=canonical_json(req.provider.model_dump()),
            params_json=canonical_json(params),
            repeat_idx=spec.repeat_idx,
            request_json=body.decode("utf-8"),
            response_json=response_text,
            model_build=None if resp is None else resp.model,
            provider=None if resp is None else resp.provider,
            input_tokens=None if resp is None else resp.usage.prompt_tokens,
            output_tokens=None if resp is None else resp.usage.completion_tokens,
            cost=cost,
            cost_source=cost_source,
            latency_ms=latency_ms,
            created_at=utc_now_iso(),
            chunk=self.chunk,
            tag=spec.tag,
            meta_json=canonical_json(meta),
            valid=parsed.valid,
            problems_json=json.dumps(parsed.problem_list(), ensure_ascii=False),
        )

    # --- transport -------------------------------------------------------------------------------

    def _wait(self, state: RetryCallState) -> float:
        r = self.config.api.retry
        cap = min(r.max_s, r.initial_s * 2 ** (state.attempt_number - 1))
        wait = _JITTER.uniform(0.0, cap)
        exc = state.outcome.exception() if state.outcome is not None else None
        if isinstance(exc, _Retry):
            with contextlib.suppress(ValueError):
                wait = max(wait, min(float(exc.outcome.headers.get("retry-after", "")), r.max_s))
        return wait

    async def _attempt(
        self,
        http: httpx.AsyncClient,
        key: str,
        model: str,
        tag: str,
        url: str,
        body: bytes,
        n: int,
        conc: int,
    ) -> _Outcome:
        api = self.config.api
        headers = {"Authorization": f"Bearer {self._api_key()}", "Content-Type": "application/json"}
        t0 = time.perf_counter()
        status: int | None = None
        text, error, kept = "", None, {}
        try:
            resp = await http.post(url, content=body, headers=headers)
            status, text = resp.status_code, resp.text
            kept = {h: resp.headers[h] for h in api.record_headers if h in resp.headers}
            if status != 200:
                error = text[:2000]
        except httpx.TransportError as exc:
            error = f"{type(exc).__name__}: {exc}"[:2000]
        latency = (time.perf_counter() - t0) * 1000.0
        self.cache.log_attempt(
            key=key,
            model=model,
            attempt=n,
            status=status,
            error=error,
            latency_ms=latency,
            headers=kept,
            concurrency=conc,
            chunk=self.chunk,
            tag=tag,
        )
        return _Outcome(status, text, kept, latency, n, error)

    async def _post(
        self, http: httpx.AsyncClient, key: str, model: str, tag: str, url: str, body: bytes, conc: int
    ) -> _Outcome:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.config.api.retry.max_attempts),
            wait=self._wait,
            retry=retry_if_exception_type(_Retry),
            reraise=True,
        )
        try:
            async for att in retrying:
                with att:
                    n = att.retry_state.attempt_number
                    out = await self._attempt(http, key, model, tag, url, body, n, conc)
                    if out.retryable:
                        raise _Retry(out)
                    return out
        except _Retry as exc:
            return exc.outcome  # attempts exhausted: the last outcome is the result
        raise DMError("retry loop ended without an outcome")  # pragma: no cover

    # --- read-only endpoints (no spend) ----------------------------------------------------------

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        """GET an OpenRouter endpoint (catalog, key usage) with the same retries; no spend, no cache."""
        if self.offline:
            raise CacheMiss("an offline client makes no network call")

        async def go() -> Any:
            async with self._http() as http:
                headers = {"Authorization": f"Bearer {self._api_key()}"}
                last: httpx.Response | None = None
                for n in range(1, self.config.api.retry.max_attempts + 1):
                    last = await http.get(url, params=dict(params or {}), headers=headers)
                    if last.status_code != 429 and last.status_code < 500:
                        break
                    await asyncio.sleep(
                        min(self.config.api.retry.max_s, self.config.api.retry.initial_s * 2**n)
                    )
                assert last is not None
                if last.status_code != 200:
                    raise DMError(f"GET {url}: HTTP {last.status_code}: {last.text[:300]}")
                return last.json()

        return asyncio.run(go())

    def key_usage(self) -> dict[str, Any]:
        """The key's own accounting (GET /api/v1/key; USD), for the pilot's billing checks."""
        data = self.get_json(self.config.api.key_url)["data"]
        fields = ("usage", "usage_daily", "limit", "limit_remaining", "is_free_tier")
        return {k: data.get(k) for k in fields}

    def credits(self) -> dict[str, Any]:
        """The account's credits (GET /api/v1/credits; USD): purchased, used and what is left."""
        data = self.get_json(self.config.api.credits_url)["data"]
        total, used = float(data.get("total_credits", 0.0)), float(data.get("total_usage", 0.0))
        return {"total_credits": total, "total_usage": used, "remaining": total - used}

    def account_left(self) -> float:
        """USD this key can still spend: the account's remaining credits, and the key's own limit if set."""
        left = float(self.credits()["remaining"])
        limit = self.key_usage().get("limit_remaining")
        return left if limit is None else min(left, float(limit))

    def reconcile(self) -> float:
        """Recorded spend of this chunk minus Σ cost of its cached responses (GAC4: ~0)."""
        return self.ledger.reconcile(self.cache.costs(self.chunk))
