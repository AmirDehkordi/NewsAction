"""Local Laya checkpoints behind the decision-response shape (PRD NA-05 S5; PREREG §8.1, §9.1).

``LayaLocal(model_id, config)`` serves ``local/laya-typed-decisions`` (subfolder ``typed-decisions``) and
``local/laya-base`` (the repository root) of ``convaiinnovations/laya`` at the revision pinned in
``configs/dm.yaml``; the checkpoint's ``model.safetensors`` sha256 is verified before any weight is loaded
(laya's ``expected_sha256``). Install group: ``laya`` (``uv sync --extra laya``).

- **Device.** MPS, else CPU; laya itself falls back to CPU when placement fails. The device used is the
  response's ``provider`` ("local:mps" / "local:cpu").
- **Precision.** fp32 throughout (``fp32: true``). laya autocasts to fp16 on MPS from five question rows on,
  so otherwise an answer would depend on how many questions share the call.
- **Length.** ``max_len`` 1024 (PREREG §9.1) for both checkpoints; ``head_max_len`` the checkpoint's own
  unless configured. The state is passed as its canonical JSON text (the bytes an API model receives). laya's
  truncation report (``usage.truncated``, ``state_tokens``, ``state_tokens_dropped``) is kept.
- **Probabilities.** laya rounds them to 4 decimals, so they need not sum to 1 within 1e-6. The wrapper
  recomputes each answer's probabilities in float64 from the same logits and temperature (``exact_answers``),
  keeps laya's values as ``probabilities_rounded`` and recomputes a score's position from the exact values;
  it refuses to answer if rounding the exact values does not give laya's (a laya change).
- **Response.** {id: None, model: "<model_id>@<revision>", provider, answers, usage{input_tokens,
  output_tokens 0, cost 0, laya's length fields}}. ``input_tokens`` is laya's count over all question rows:
  every row re-encodes the state.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np

from newsaction.dm import DMError, LayaConfig
from newsaction.dm.schemas import DecisionRequest

ROUND_TOL: Final = 5e-5 + 1e-7  # laya rounds to 4 decimals


class LayaLocal:
    """One local Laya checkpoint (lazy: the weights load on the first ``predict``)."""

    def __init__(self, model_id: str, config: LayaConfig) -> None:
        if model_id not in config.variants:
            raise DMError(f"unknown local model {model_id!r}; configured: {sorted(config.variants)}")
        self.model_id = model_id
        self.config = config
        self.subfolder = config.variants[model_id]
        self._agent: Any = None
        self.load_seconds: float | None = None

    @property
    def build(self) -> str:
        return f"{self.model_id}@{self.config.revision}"

    @property
    def params(self) -> dict[str, Any]:
        """Checkpoint settings, part of every cache key of this model."""
        c = self.config
        return {
            "revision": c.revision,
            "subfolder": self.subfolder,
            "max_len": c.max_len,
            "head_max_len": c.head_max_len,
            "device": c.device,
            "fp32": c.fp32,
        }

    def load(self) -> Any:
        if self._agent is not None:
            return self._agent
        import laya
        import torch

        c = self.config
        device = c.device if c.device == "cpu" or torch.backends.mps.is_available() else "cpu"
        t0 = time.perf_counter()
        agent = laya.load(
            c.repo,
            subfolder=self.subfolder or None,
            device=device,
            revision=c.revision,
            expected_sha256={"model.safetensors": c.weights_sha256[self.subfolder]},
        )
        if agent.revision not in (None, c.revision):
            raise DMError(f"{self.model_id}: loaded revision {agent.revision}, configured {c.revision}")
        if c.fp32:
            agent.amp_enabled = False
        agent._decode_answers = _exact_decoder(agent)
        self.load_seconds = time.perf_counter() - t0
        self._agent = agent
        return agent

    @property
    def device(self) -> str:
        return "unloaded" if self._agent is None else str(self._agent.device.type)

    def predict(self, request: DecisionRequest) -> dict[str, Any]:
        agent = self.load()
        questions = {qid: q.wire() for qid, q in request.questions.items()}
        res = agent.predict(
            request.state_text(),
            questions,
            max_len=self.config.max_len,
            head_max_len=self.config.head_max_len,
        )
        usage = {str(k): v for k, v in res["usage"].items()}
        usage["output_tokens"] = 0
        usage["cost"] = 0.0
        return {
            "id": None,
            "model": self.build,
            "provider": f"local:{self.device}",
            "answers": {str(k): dict(v) for k, v in res["answers"].items()},
            "usage": usage,
        }


def softmax64(logits: Any, temperature: float) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64) / float(temperature)
    p = np.exp(z - z.max())
    out: np.ndarray = p / p.sum()
    return out


def exact_answers(
    answers: Mapping[str, dict[str, Any]], exact: Mapping[str, Sequence[float]]
) -> dict[str, dict[str, Any]]:
    """laya's answers with float64 probabilities (and score); laya's rounded values are kept beside them."""
    out: dict[str, dict[str, Any]] = {}
    for qid, ans in answers.items():
        p = [float(v) for v in exact[qid]]
        rounded = ans.get("probabilities")
        if not isinstance(rounded, dict) or len(rounded) != len(p):
            raise DMError(f"laya answer {qid}: unexpected probabilities {rounded!r}")
        keys = list(rounded)
        drift = max(abs(float(rounded[k]) - v) for k, v in zip(keys, p, strict=True))
        if drift > ROUND_TOL:
            raise DMError(f"laya answer {qid}: exact probabilities differ from laya's by {drift:.2e}")
        new = dict(ans)
        new["probabilities_rounded"] = dict(rounded)
        new["probabilities"] = dict(zip(keys, p, strict=True))
        if ans.get("type") == "score":
            new["score_rounded"] = ans.get("score")
            new["score"] = float(sum(i * v for i, v in enumerate(p)))
        out[qid] = new
    return out


def _exact_decoder(agent: Any) -> Any:
    """Wrap ``agent._decode_answers`` (laya 0.4.14) to put in float64 probabilities from the same logits."""
    from laya import agent as la
    from laya.common import QTYPES, temp_bucket, unpermute_probs

    original = agent._decode_answers

    def decode(
        logits: Any,
        act: Any,
        items: list[dict[str, Any]],
        ids: list[str],
        internal: dict[str, dict[str, Any]],
        offset: int,
        lang: str | None = None,
    ) -> dict[str, Any]:
        if lang:
            raise DMError("language-specific temperatures are not used here")
        answers = original(logits, act, items, ids, internal, offset)
        rows = la._option_logits(logits, items, offset)
        exact: dict[str, list[float]] = {}
        for j, qid in enumerate(ids):
            q = internal[qid]
            k = len(items[j]["markers"])
            qt = QTYPES[q["t"]]
            t = agent.temperature_by_options.get(temp_bucket(qt, k), agent.temperature[qt])
            p = unpermute_probs(softmax64(rows[j], t), q.get("option_order"))
            exact[qid] = [float(v) for v in p]
        return exact_answers(answers, exact)

    return decode
