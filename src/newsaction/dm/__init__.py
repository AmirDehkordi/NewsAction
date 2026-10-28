"""NA-05: the decision-model client, the only sanctioned path to any decision model (PRD NA-05; CLAUDE.md
C12–C14, D15).

Modules:
- ``schemas``: typed requests and strictly parsed responses (OpenRouter Decisions API, local Laya);
- ``cache``: the sqlite response cache, keyed by sha256 of {model, state, questions, provider, params,
  repeat_idx};
- ``costmodel``: projected tokens and USD of a request (catalog price × estimated tokens), calibrated by the
  pilot;
- ``client``: refusals, dry runs, the spend ledger, retries, concurrency and the offline mode;
- ``catalog``: the decision-model catalog snapshot and eligibility (PREREG §8.1);
- ``laya_local``: local Laya checkpoints behind the same response shape;
- ``parse``: the PREREG §7 / A2.4 derived quantities from answer probabilities;
- ``canary``: the fixed canary set and the drift comparison;
- ``runner``: registered state files → requests → answers;
- ``pilot``: the NA-05 measurement pilot (``artifacts/NA-05/pilot.json``).

Configuration: ``configs/dm.yaml``. Selections live in ``configs/frozen.yaml``: ``eligible_models`` (written
here), ``free_model_approvals`` (the operator's) and ``allow_val_b`` (NA-06's).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS, Layout, resolve_layout

CHUNK: Final = "NA-05"
PRODUCER: Final = "newsaction.dm (NA-05)"
DM_CONFIG_PATH: Final = CONFIGS / "dm.yaml"
ARTIFACTS: Final = "artifacts/NA-05"
CATALOG_FILE: Final = f"{ARTIFACTS}/catalog.json"
PILOT_FILE: Final = f"{ARTIFACTS}/pilot.json"
CANARY_FILE: Final = f"{ARTIFACTS}/canary_v1.jsonl"
CANARY_BASELINE: Final = f"{ARTIFACTS}/canary_baseline.parquet"
LOCAL_PREFIX: Final = "local/"

BillingBasis = Literal["once", "per_question"]


class DMError(Exception):
    """A decision-model call could not be made or answered."""


class Refused(DMError):
    """The client refused a request before sending it (CLAUDE.md C12–C13, D15; PRD NA-05 S3)."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"refused ({rule}): {message}")
        self.rule = rule


class CacheMiss(DMError):
    """Offline mode: the request is not in the cache, and offline clients never send (CLAUDE.md C14)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetryConfig(_Strict):
    max_attempts: int = Field(ge=1)
    initial_s: float = Field(gt=0)
    max_s: float = Field(gt=0)


class ApiConfig(_Strict):
    decisions_url: str
    chat_url: str
    models_url: str
    key_url: str
    credits_url: str
    chat_catalog: str  # the chat-model price snapshot (NA-09 S7), same shape as CATALOG_FILE
    catalog_params: dict[str, str]
    key_env: str
    timeout_s: float = Field(gt=0)
    concurrency: int = Field(ge=1)
    retry: RetryConfig
    record_headers: tuple[str, ...]


class CostDefault(_Strict):
    billing_basis: BillingBasis
    bytes_per_token: float = Field(gt=0)
    overhead_tokens: float = Field(ge=0)
    safety: float = Field(ge=1)


class CostCalibration(_Strict):
    """One model's pilot calibration (``costmodel``): tokens = overhead + billed state bytes /
    bytes_per_token + question bytes / question_bytes_per_token."""

    billing_basis: BillingBasis
    bytes_per_token: float = Field(gt=0)  # state bytes (each billed copy)
    question_bytes_per_token: float = Field(gt=0)
    overhead_tokens: float = Field(ge=0)
    safety: float = Field(ge=1)
    cost_ratio: float = Field(gt=0)  # usage.cost / (catalog price × input_tokens), median over pilot calls
    n_calls: int = Field(ge=1)


class ChatCost(_Strict):
    """Projection of a chat request (``costmodel.estimate_chat``): conservative on purpose."""

    bytes_per_token: float = Field(default=3.0, gt=0)
    overhead_tokens: float = Field(default=64.0, ge=0)
    safety: float = Field(default=1.5, ge=1)


class CostConfig(_Strict):
    default: CostDefault
    models: dict[str, CostCalibration]
    chat: ChatCost = Field(default_factory=ChatCost)


class LayaConfig(_Strict):
    repo: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    weights_sha256: dict[str, str]
    variants: dict[str, str]
    max_len: int = Field(gt=0)
    head_max_len: int | None = Field(default=None, gt=0)
    device: Literal["mps", "cpu"]
    fp32: bool


class CanaryConfig(_Strict):
    """NA-11 S5's drift rule (operator decision, docs/decisions/NA-05.md): max |Δp| for deterministic models,
    mean |Δp| against the model's own repeat noise for the others."""

    noise_repeats: int = Field(ge=2)
    deterministic_max_abs_dp: float = Field(gt=0)
    noisy_rule: Literal["mean_abs_dp_vs_repeat_noise"]
    deterministic: tuple[str, ...]


class DmConfig(_Strict):
    version: int
    api: ApiConfig
    cache: str
    state_as_text: tuple[str, ...]  # models that take the state only as a string (its canonical JSON text)
    canary: CanaryConfig
    registered_probes: dict[str, str]
    costmodel: CostConfig
    laya: LayaConfig


def load_dm_config(path: Path = DM_CONFIG_PATH) -> DmConfig:
    """Not cached: the pilot writes the cost calibration during a session."""
    return DmConfig.model_validate(load_yaml(path))


def dm_config(layout: Layout | None = None) -> DmConfig:
    return load_dm_config(resolve_layout(layout).configs / "dm.yaml")


def is_local(model: str) -> bool:
    """Local open-weight models (``local/…``) run on this machine; nothing is sent to a third party."""
    return model.startswith(LOCAL_PREFIX)
