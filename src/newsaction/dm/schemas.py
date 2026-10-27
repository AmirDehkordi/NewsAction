"""Request and response schemas (PRD NA-05 S1; OpenRouter Decisions API reference; Laya typed decisions).

**Requests** are built, never parsed. ``DecisionRequest`` holds the model id, the state (an object or a
string), the questions and ``provider = {"data_collection": "deny"}``, the only provider setting the schema
accepts (CLAUDE.md C12). PREREG §7 allows two question types: ``choice`` (criteria: option → description, at
least two) and ``score`` (criteria: 2–10 levels, lowest first). ``noul`` is refused.

**Responses** are parsed strictly (``parse_response``):
- the envelope needs ``model``, an ``answers`` object and ``usage`` {input_tokens, output_tokens}; otherwise
  the whole response is invalid;
- every question asked needs an answer, and every answer needs ``type``, the type of the question asked, and
  its typed field (``choice`` naming one of the options, or a numeric ``score``);
- ``probabilities`` must be present and keyed exactly by the question's options (a score's by "0" … "k−1"),
  each finite in [0, 1], summing to 1 within 1e-6;
- a score's ``legend``, when present, must map "0" … "k−1" to the levels as asked.

**Rounded probabilities** (operator decision, a change to PRD NA-05 S1; docs/decisions/NA-05.md). Some models
round their probabilities (Jev to 0.01, several others to 4 decimals), so a sum can be off 1 by one rounding
step. A sum off by more than 1e-6 but at most ``RENORM_TOL`` = 0.0105 is renormalized (p_k / Σp) and
the answer is flagged ``renormalized``, with the original sum kept in ``raw_sum``; a sum off by more than that
stays a problem.

An answer that breaks a rule keeps its fields and lists the rule in ``problems``; it is invalid and its
probabilities are not used. The raw answer is never altered: a renormalized vector exists only in the parsed
answer. Observations that do not invalidate an answer go to ``notes``: no legend, the chosen option is not the
most probable one, the score is not the probability-weighted position.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from newsaction.states.questions import canonical_json

PROB_TOL: Final = 1e-6
RENORM_TOL: Final = 0.0105  # one step of a 0.01 grid (and float noise); flagged beyond PROB_TOL
SCORE_TOL: Final = 1e-3  # |score − Σ i·p_i| above this is noted (item 7 of the pilot)
SUM_EPS: Final = 1e-9  # chat answers: a sum of exactly 1 ± sum_tol is inside the rule despite float rounding
MAX_SCORE_LEVELS: Final = 10
QuestionType = Literal["choice", "score"]


class SchemaError(ValueError):
    """A request that the API contract or PREREG §7 does not allow."""


class QuestionSpec(BaseModel):
    """One typed question: {type, instructions, criteria}."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: QuestionType
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] | list[str]

    @model_validator(mode="after")
    def _shape(self) -> QuestionSpec:
        if self.type == "choice":
            if not isinstance(self.criteria, dict) or len(self.criteria) < 2:
                raise ValueError("a choice needs a mapping of at least two options")
        elif not isinstance(self.criteria, list) or not 2 <= len(self.criteria) <= MAX_SCORE_LEVELS:
            raise ValueError(f"a score needs 2..{MAX_SCORE_LEVELS} ordered levels")
        return self

    def options(self) -> list[str]:
        """Option keys in asked order: a choice's keys, a score's level indices "0" … "k−1"."""
        if isinstance(self.criteria, dict):
            return list(self.criteria)
        return [str(i) for i in range(len(self.criteria))]

    def wire(self) -> dict[str, Any]:
        crit: Any = dict(self.criteria) if isinstance(self.criteria, dict) else list(self.criteria)
        return {"type": self.type, "instructions": self.instructions, "criteria": crit}

    def ordered(self) -> list[Any]:
        """The question as nested lists, so option order counts in a hash."""
        crit = list(self.criteria.items()) if isinstance(self.criteria, dict) else list(self.criteria)
        return [self.type, self.instructions, [list(c) if isinstance(c, tuple) else c for c in crit]]


class Provider(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_collection: Literal["deny"] = "deny"


class DecisionRequest(BaseModel):
    """The body of POST /api/alpha/decisions, without per-run extras (``params``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    state: dict[str, Any] | str
    questions: dict[str, QuestionSpec] = Field(min_length=1)
    provider: Provider = Field(default_factory=Provider)
    session_id: str | None = Field(default=None, max_length=256)

    def state_text(self) -> str:
        """The state as sent: an object as canonical JSON (sorted keys, as NA-04 stores it), or a string."""
        return self.state if isinstance(self.state, str) else canonical_json(self.state)

    def state_sha256(self) -> str:
        return hashlib.sha256(self.state_text().encode("utf-8")).hexdigest()

    def questions_ordered(self) -> list[Any]:
        return [[qid, q.ordered()] for qid, q in self.questions.items()]

    def questions_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.questions_ordered()).encode("utf-8")).hexdigest()

    def body(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """The JSON body: the state with sorted keys, questions and options as asked, then ``params``."""
        clash = set(params) & {"model", "state", "questions", "provider", "session_id"}
        if clash:
            raise SchemaError(f"params may not set {sorted(clash)}")
        state: Any = self.state if isinstance(self.state, str) else json.loads(canonical_json(self.state))
        body: dict[str, Any] = {
            "model": self.model,
            "state": state,
            "questions": {qid: q.wire() for qid, q in self.questions.items()},
            "provider": self.provider.model_dump(),
        }
        if self.session_id is not None:
            body["session_id"] = self.session_id
        body.update(params)
        return body


def questions_from(raw: Mapping[str, Mapping[str, Any]]) -> dict[str, QuestionSpec]:
    """Typed questions from the battery's request object (``states.questions.Battery.request``)."""
    try:
        return {str(k): QuestionSpec.model_validate(dict(v)) for k, v in raw.items()}
    except ValidationError as exc:
        raise SchemaError(f"invalid question: {exc.errors()[0]['msg']}") from None


# --- responses ------------------------------------------------------------------------------------


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float] | None = None
    confidence: float | None = None


class ScoreAnswer(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    type: Literal["score"]
    score: float
    legend: dict[str, Any] | None = None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost: float | None = Field(default=None, ge=0)


class DecisionResponse(BaseModel):
    """The envelope of a 200 response; answers stay raw until ``parse_response`` types them per question."""

    model_config = ConfigDict(extra="allow", frozen=True)

    id: str | None = None
    model: str = Field(min_length=1)
    provider: str | None = None
    answers: dict[str, Any]
    usage: Usage


@dataclass(frozen=True)
class ParsedAnswer:
    qid: str
    type: str | None
    answer: ChoiceAnswer | ScoreAnswer | None
    probs: tuple[float, ...] | None  # in the question's option order; None unless the answer is valid
    confidence: float | None
    problems: tuple[str, ...]
    notes: tuple[str, ...]
    renormalized: bool = False  # the returned sum was off 1 by more than PROB_TOL and at most RENORM_TOL
    raw_sum: float | None = None  # Σ of the returned probabilities

    @property
    def valid(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class ParsedResponse:
    response: DecisionResponse | None
    answers: Mapping[str, ParsedAnswer]
    problems: tuple[str, ...]  # envelope problems, missing and unexpected answers

    @property
    def valid(self) -> bool:
        return not self.problems and all(a.valid for a in self.answers.values())

    def problem_list(self) -> list[str]:
        out = list(self.problems)
        for qid, a in self.answers.items():
            out += [f"{qid}: {p}" for p in a.problems]
        return out


@dataclass(frozen=True)
class _Probs:
    problems: list[str]
    probs: tuple[float, ...] | None  # in option order, renormalized if flagged; None with a problem
    renormalized: bool = False
    raw_sum: float | None = None


def _probabilities(probs: Mapping[str, Any], options: list[str]) -> _Probs:
    keys = [str(k) for k in probs]
    if set(keys) != set(options) or len(keys) != len(options):
        return _Probs([f"probability keys {sorted(keys)} differ from the options {options}"], None)
    vals = [probs[k] for k in options]
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in vals):
        return _Probs(["a probability is not a number"], None)
    return _sum_rule(tuple(float(v) for v in vals), RENORM_TOL)


def _argmax_ok(p: tuple[float, ...], options: list[str], chosen: str) -> bool:
    top = max(p)
    return chosen in options and p[options.index(chosen)] >= top - PROB_TOL


def parse_answer(qid: str, raw: Any, question: QuestionSpec) -> ParsedAnswer:
    problems: list[str] = []
    notes: list[str] = []
    if not isinstance(raw, dict):
        return ParsedAnswer(qid, None, None, None, None, ("the answer is not an object",), ())
    qtype = raw.get("type")
    if qtype is None:
        return ParsedAnswer(qid, None, None, None, None, ("missing type",), ())
    if qtype != question.type:
        return ParsedAnswer(
            qid, str(qtype), None, None, None, (f"type {qtype!r}, asked {question.type!r}",), ()
        )
    model: type[ChoiceAnswer] | type[ScoreAnswer] = ChoiceAnswer if qtype == "choice" else ScoreAnswer
    try:
        ans = model.model_validate(raw)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(x) for x in err["loc"])
        return ParsedAnswer(qid, str(qtype), None, None, None, (f"{where}: {err['msg']}",), ())
    options = question.options()
    pr = _Probs([], None)
    if ans.probabilities is None:
        problems.append("missing probabilities")
    else:
        pr = _probabilities(ans.probabilities, options)
        problems += pr.problems
    probs = pr.probs
    if isinstance(ans, ChoiceAnswer):
        if ans.choice not in options:
            problems.append(f"choice {ans.choice!r} is not an option")
        elif probs is not None and not _argmax_ok(probs, options, ans.choice):
            notes.append("the chosen option is not the most probable one")
    else:
        if ans.legend is None:
            notes.append("no legend")
        else:
            levels = list(question.criteria)
            want = {str(i): lvl for i, lvl in enumerate(levels)}
            got = {str(k): v for k, v in ans.legend.items()}
            if got != want:
                problems.append("the legend differs from the levels asked")
        if not math.isfinite(ans.score):
            problems.append("the score is not finite")
        elif probs is not None and abs(ans.score - sum(i * v for i, v in enumerate(probs))) > SCORE_TOL:
            notes.append("the score is not the probability-weighted position")
    conf = ans.confidence
    if conf is not None and not (math.isfinite(conf) and 0.0 <= conf <= 1.0):
        notes.append("confidence outside [0, 1]")
    return ParsedAnswer(
        qid,
        str(qtype),
        ans,
        probs if not problems else None,
        conf,
        tuple(problems),
        tuple(notes),
        renormalized=pr.renormalized and not problems,
        raw_sum=pr.raw_sum,
    )


def _sum_rule(p: tuple[float, ...], tol: float) -> _Probs:
    """Finite values in [0, 1] whose sum is 1 within ``tol``: off by more than PROB_TOL is renormalized and
    flagged, off by more than ``tol`` is a problem."""
    out = []
    if not all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in p):
        out.append("a probability is outside [0, 1]")
    total = math.fsum(p) if all(math.isfinite(v) for v in p) else math.nan
    off = abs(total - 1.0)
    if not off <= tol:
        out.append(f"probabilities sum to {total:.9f}")
    if out:
        return _Probs(out, None, raw_sum=total)
    if off > PROB_TOL:
        return _Probs([], tuple(v / total for v in p), renormalized=True, raw_sum=total)
    return _Probs([], p, raw_sum=total)


def parse_response(raw: Any, questions: Mapping[str, QuestionSpec]) -> ParsedResponse:
    """Strict parse of a decision response against the questions asked (see the module docstring)."""
    if not isinstance(raw, dict):
        return ParsedResponse(None, {}, ("the response is not a JSON object",))
    try:
        resp = DecisionResponse.model_validate(raw)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(x) for x in err["loc"])
        return ParsedResponse(None, {}, (f"envelope {where}: {err['msg']}",))
    problems = [f"no answer for {qid}" for qid in questions if qid not in resp.answers]
    problems += [f"unexpected answer {qid}" for qid in resp.answers if qid not in questions]
    answers = {
        qid: parse_answer(qid, resp.answers[qid], q) for qid, q in questions.items() if qid in resp.answers
    }
    return ParsedResponse(resp, answers, tuple(problems))


# --- chat completions with a JSON-schema answer (PRD NA-09 S7) --------------------------------------


class ChatProvider(BaseModel):
    """Provider preferences of a chat request: ``data_collection`` deny, the only value the schema accepts
    (CLAUDE.md C12), and ``require_parameters``, so a request is routed only to an endpoint that supports
    every parameter it sends (a structured-output request is never answered by one that ignores the
    schema)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_collection: Literal["deny"] = "deny"
    require_parameters: Literal[True] = True


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """The body of POST /api/v1/chat/completions asking for one JSON object (``response_format`` json_schema,
    strict): every property required, no other property allowed, ``required`` in answer order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    schema_name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    json_schema: dict[str, Any]
    temperature: float = Field(ge=0, le=2)
    seed: int | None = None
    max_tokens: int = Field(gt=0)
    provider: ChatProvider = Field(default_factory=ChatProvider)

    @model_validator(mode="after")
    def _object_schema(self) -> ChatRequest:
        s = self.json_schema
        props, req = s.get("properties"), s.get("required")
        if s.get("type") != "object" or not isinstance(props, dict) or not props:
            raise ValueError("json_schema must be an object schema with properties")
        if not isinstance(req, list) or sorted(req) != sorted(props) or len(set(req)) != len(req):
            raise ValueError("json_schema must require every property exactly once")
        if s.get("additionalProperties") is not False:
            raise ValueError("json_schema must set additionalProperties: false")
        return self

    def keys(self) -> list[str]:
        """The answer's keys in order (``required``)."""
        return [str(k) for k in self.json_schema["required"]]

    def body(self, params: Mapping[str, Any]) -> dict[str, Any]:
        clash = set(params) & {"model", "messages", "response_format", "provider", "temperature", "seed"}
        if clash:
            raise SchemaError(f"params may not set {sorted(clash)}")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in self.messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": self.schema_name, "strict": True, "schema": self.json_schema},
            },
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "provider": self.provider.model_dump(),
            "usage": {"include": True},
        }
        if self.seed is not None:
            body["seed"] = self.seed
        body.update(params)
        return body

    def messages_sha256(self) -> str:
        return hashlib.sha256(canonical_json([m.model_dump() for m in self.messages]).encode()).hexdigest()

    def schema_sha256(self) -> str:
        return hashlib.sha256(canonical_json([self.schema_name, self.json_schema]).encode()).hexdigest()


class ChatUsage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost: float | None = Field(default=None, ge=0)


class ChatResponse(BaseModel):
    """The envelope of a 200 chat completion; the answer is ``choices[0].message.content``."""

    model_config = ConfigDict(extra="allow", frozen=True)

    id: str | None = None
    model: str = Field(min_length=1)
    provider: str | None = None
    choices: list[dict[str, Any]] = Field(min_length=1)
    usage: ChatUsage


@dataclass(frozen=True)
class ParsedChat:
    response: ChatResponse | None
    content: str | None
    finish_reason: str | None
    values: dict[str, Any] | None  # the JSON object as returned (never altered)
    probs: tuple[float, ...] | None  # probability answers: in key order, renormalized if flagged
    problems: tuple[str, ...]
    renormalized: bool = False
    raw_sum: float | None = None

    @property
    def valid(self) -> bool:
        return not self.problems

    def problem_list(self) -> list[str]:
        return list(self.problems)


def parse_chat_response(raw: Any, keys: list[str], sum_tol: float | None) -> ParsedChat:
    """Strict parse of a chat completion: an envelope with usage, ``finish_reason`` "stop", content that is
    one JSON object with exactly ``keys``. With ``sum_tol`` the values are probabilities: numbers in [0, 1]
    whose sum is 1 within ``sum_tol`` (``SUM_EPS`` absorbs float rounding: 0.4 + 0.4 + 0.25 is 0.05 + 4e-17
    away from 1; off by more than 1e-6: renormalized and flagged). Nothing is repaired beyond that rule."""
    if not isinstance(raw, dict):
        return ParsedChat(None, None, None, None, None, ("the response is not a JSON object",))
    try:
        resp = ChatResponse.model_validate(raw)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(x) for x in err["loc"])
        return ParsedChat(None, None, None, None, None, (f"envelope {where}: {err['msg']}",))
    choice = resp.choices[0]
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    finish = choice.get("finish_reason")
    finish = str(finish) if finish is not None else None
    problems: list[str] = []
    if finish != "stop":
        problems.append(f"finish_reason {finish!r}")
    if not isinstance(content, str):
        return ParsedChat(resp, None, finish, None, None, (*problems, "no message content"))
    try:
        values = json.loads(content)
    except json.JSONDecodeError:
        return ParsedChat(resp, content, finish, None, None, (*problems, "content is not JSON"))
    if not isinstance(values, dict):
        return ParsedChat(resp, content, finish, None, None, (*problems, "content is not a JSON object"))
    if sorted(values) != sorted(keys):
        problems.append(f"answer keys {sorted(values)} differ from {sorted(keys)}")
    if sum_tol is None or problems:
        return ParsedChat(resp, content, finish, values, None, tuple(problems))
    vals = [values[k] for k in keys]
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in vals):
        return ParsedChat(resp, content, finish, values, None, ("a probability is not a number",))
    pr = _sum_rule(tuple(float(v) for v in vals), sum_tol + SUM_EPS)
    return ParsedChat(
        resp, content, finish, values, pr.probs, tuple(pr.problems), pr.renormalized, pr.raw_sum
    )
