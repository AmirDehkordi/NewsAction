"""Projected tokens and USD of a decision request (PRD NA-05 S3 ``dry_run``; PREREG §13).

- **Billed bytes.** The canonical JSON of the state and of each question (``{id: {type, instructions,
  criteria}}``). With billing basis ``once`` the state is counted once and every question once; with
  ``per_question`` the state is counted again with every question.
- **Tokens** = overhead + billed bytes / bytes_per_token for a model without a calibration; a calibrated
  model has separate rates for state bytes and question bytes, which tokenize differently (the states carry
  "≈", "×" and dense JSON).
- **USD** = (prompt price × tokens + request price) × (1 − discount) × cost_ratio × safety, with the prices of
  the catalog snapshot (``artifacts/NA-05/catalog.json``; USD per token). Output tokens are free for decision
  models, and a ``completion`` price is never charged here because no output tokens are projected.
- **Chat requests** (NA-09 ``chat_json``): input tokens from the bytes of the messages and the answer schema
  (``costmodel.chat``), output tokens = the request's ``max_tokens``, priced with the prompt and completion
  prices of the chat-model snapshot (``api.chat_catalog``).

A model without a pilot calibration uses ``configs/dm.yaml`` ``costmodel.default``: per-question billing,
3.0 bytes per token and a safety factor of 1.5, which over-projects on purpose. ``calibrate`` fits a model's
basis, its two bytes-per-token rates, overhead and cost ratio from its pilot calls (least squares, trimmed of
outliers such as calls a provider's prompt cache billed below their size); the pilot writes the result to
``costmodel.models`` (PRD NA-05 S8: "update dm/costmodel.py from (1)–(2)").
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from newsaction.dm import BillingBasis, CostCalibration, CostConfig, DMError, is_local
from newsaction.dm.schemas import ChatRequest, DecisionRequest
from newsaction.states.questions import canonical_json

CALIBRATED_SAFETY: Final = 1.1


@dataclass(frozen=True)
class Price:
    prompt: float  # USD per input token
    request: float  # USD per request
    discount: float  # fraction off
    completion: float = 0.0  # USD per output token (chat models; decision models bill no output)

    @classmethod
    def from_catalog(cls, pricing: Mapping[str, Any]) -> Price:
        def num(key: str) -> float:
            raw = pricing.get(key)
            v = 0.0 if raw in (None, "") else float(raw)
            if not math.isfinite(v) or v < 0:
                raise DMError(f"catalog price {key}={raw!r} is not a non-negative number")
            return v

        return cls(
            prompt=num("prompt"),
            request=num("request"),
            discount=num("discount"),
            completion=num("completion"),
        )

    def usd(self, tokens: float, output_tokens: float = 0.0) -> float:
        return (self.prompt * tokens + self.completion * output_tokens + self.request) * (1.0 - self.discount)


FREE: Final = Price(prompt=0.0, request=0.0, discount=0.0)


def billed_parts(request: DecisionRequest, basis: BillingBasis) -> tuple[int, int]:
    """(billed state bytes, question bytes): the state once, or once per question."""
    state = len(request.state_text().encode("utf-8"))
    qs = [len(canonical_json({qid: q.wire()}).encode("utf-8")) for qid, q in request.questions.items()]
    return (state if basis == "once" else state * len(qs)), sum(qs)


def billed_bytes(request: DecisionRequest, basis: BillingBasis) -> int:
    return sum(billed_parts(request, basis))


@dataclass(frozen=True)
class Estimate:
    tokens: float
    usd: float


class CostModel:
    """Per-request projections from catalog prices and the pilot calibration."""

    def __init__(self, config: CostConfig, prices: Mapping[str, Price]) -> None:
        self.config = config
        self.prices = dict(prices)

    @classmethod
    def from_files(cls, config: CostConfig, catalog_path: Path, *more: Path) -> CostModel:
        """Prices of the decision-model catalog snapshot and of any further snapshots of the same shape (the
        NA-09 chat-model snapshot); a missing file adds nothing, a model priced twice is an error."""
        prices: dict[str, Price] = {}
        for path in (catalog_path, *more):
            if not path.is_file():
                continue
            snap = json.loads(path.read_text(encoding="utf-8"))
            for m in snap["models"]:
                if str(m["id"]) in prices:
                    raise DMError(f"{m['id']} is priced in two catalog snapshots")
                prices[str(m["id"])] = Price.from_catalog(m["pricing"])
        return cls(config, prices)

    def price(self, model: str) -> Price:
        if is_local(model):
            return FREE
        try:
            return self.prices[model]
        except KeyError:
            raise DMError(f"no catalog price for {model!r}: fetch the catalog first") from None

    def calibration(self, model: str) -> CostCalibration | None:
        return self.config.models.get(model)

    def tokens(self, model: str, request: DecisionRequest) -> float:
        cal = self.calibration(model)
        if cal is None:
            d = self.config.default
            return d.overhead_tokens + billed_bytes(request, d.billing_basis) / d.bytes_per_token
        state, questions = billed_parts(request, cal.billing_basis)
        return cal.overhead_tokens + state / cal.bytes_per_token + questions / cal.question_bytes_per_token

    def estimate(self, model: str, request: DecisionRequest) -> Estimate:
        if is_local(model):
            return Estimate(tokens=0.0, usd=0.0)
        tokens = self.tokens(model, request)
        cal = self.calibration(model)
        ratio, safety = (1.0, self.config.default.safety) if cal is None else (cal.cost_ratio, cal.safety)
        return Estimate(tokens=tokens, usd=self.price(model).usd(tokens) * ratio * safety)

    def estimate_chat(self, model: str, request: ChatRequest) -> Estimate:
        """A chat request: input tokens = overhead + bytes of the messages and the schema / bytes_per_token,
        output tokens = ``max_tokens`` (an upper bound), times the chat safety factor."""
        c = self.config.chat
        sent = canonical_json([[m.model_dump() for m in request.messages], request.json_schema])
        tokens = c.overhead_tokens + len(sent.encode("utf-8")) / c.bytes_per_token
        return Estimate(tokens=tokens, usd=self.price(model).usd(tokens, request.max_tokens) * c.safety)


# --- calibration (pilot items 1–2) ------------------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """One answered pilot call: what was sent and what was billed."""

    request: DecisionRequest
    input_tokens: int
    cost: float


def state_copies(n_questions: Sequence[int], short: Sequence[int], long: Sequence[int]) -> dict[int, float]:
    """Pilot item 1: the number of state copies billed with n questions.

    For the same question set, the difference in input tokens between a long and a short state is k_n times
    the difference in their own lengths, where k_n is the number of times the state is billed. With one
    question the state is billed once by definition, so k_n = Δ_n / Δ_1 (≈ 1: once per request; ≈ n: per
    question). ``short`` and ``long`` are input tokens aligned with ``n_questions``, which must contain 1.
    """
    by_n = {int(n): (int(s), int(lg)) for n, s, lg in zip(n_questions, short, long, strict=True)}
    if 1 not in by_n:
        raise DMError("state_copies needs the one-question calls")
    base = by_n[1][1] - by_n[1][0]
    if base <= 0:
        raise DMError("the long state is not longer than the short one")
    return {n: (lg - s) / base for n, (s, lg) in sorted(by_n.items())}


def basis_from_copies(copies: Mapping[int, float]) -> BillingBasis:
    """``per_question`` if the multi-question calls bill the state more than 1.5 times (the median over the
    question counts, so that one anomalous usage report cannot decide it), else ``once``."""
    multi = [k for n, k in copies.items() if n > 1]
    if not multi:
        raise DMError("no multi-question calls to decide the billing basis")
    return "per_question" if float(np.median(multi)) > 1.5 else "once"


def fit_tokens(
    state: Sequence[float], questions: Sequence[float], tokens: Sequence[float]
) -> tuple[float, float, float, int]:
    """Tokens on [1, state bytes, question bytes]: a least-absolute-deviation fit (iteratively reweighted),
    then least squares on the points within max(4 × 1.4826 × MAD of its residuals, 2% of the tokens). Returns
    (overhead, tokens per state byte, tokens per question byte, points kept)."""
    x = np.column_stack([np.ones(len(tokens)), np.asarray(state, float), np.asarray(questions, float)])
    y = np.asarray(tokens, dtype=float)
    w = np.ones(len(y))
    for _ in range(200):
        coef, *_ = np.linalg.lstsq(x * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)
        resid = y - x @ coef
        w = 1.0 / np.maximum(np.abs(resid), 1e-6 * np.maximum(1.0, np.abs(y)))
    mad = 1.4826 * float(np.median(np.abs(resid - np.median(resid))))
    keep = np.abs(resid) <= np.maximum(4 * mad, 0.02 * y)
    coef, *_ = np.linalg.lstsq(x[keep], y[keep], rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2]), int(keep.sum())


def calibrate(model: str, obs: Sequence[Observation], basis: BillingBasis, price: Price) -> CostCalibration:
    """``fit_tokens`` on the model's answered pilot calls, and the median ratio of usage.cost to the catalog
    price × input tokens."""
    if len(obs) < 4:
        raise DMError(f"{model}: {len(obs)} observations are too few to calibrate")
    parts = [billed_parts(o.request, basis) for o in obs]
    overhead, per_state, per_question, kept = fit_tokens(
        [p[0] for p in parts], [p[1] for p in parts], [o.input_tokens for o in obs]
    )
    if per_state <= 0 or per_question <= 0:
        raise DMError(f"{model}: input tokens do not grow with the billed bytes")
    priced = [o.cost / price.usd(o.input_tokens) for o in obs if price.usd(o.input_tokens) > 0]
    ratio = float(np.median(priced)) if priced else 1.0
    return CostCalibration(
        billing_basis=basis,
        bytes_per_token=1.0 / per_state,
        question_bytes_per_token=1.0 / per_question,
        overhead_tokens=max(overhead, 0.0),
        safety=CALIBRATED_SAFETY,
        cost_ratio=ratio if ratio > 0 else 1.0,
        n_calls=int(kept),
    )
