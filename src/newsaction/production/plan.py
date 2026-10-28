"""The frozen production plan (``configs/production.yaml``; NA-11 S4–S9), typed and checked against
``configs/frozen.yaml``: the primary instrument, the encoding, calls per event and the trained-run pin must
agree.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from newsaction.config import load_frozen, load_yaml
from newsaction.paths import CONFIGS
from newsaction.production import ProductionError

PLAN_PATH: Final = CONFIGS / "production.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Component(_Strict):
    name: str
    states: tuple[str, ...]
    call: Literal["A", "B"]
    splits: tuple[str, ...]
    groups: tuple[str, ...]
    model: str | None = None


class MarketPlan(_Strict):
    splits: tuple[str, ...]
    questions: dict[str, dict[str, Any]]


class ApiPlan(_Strict):
    model: str
    groups_role: Literal["primary_api"]
    components: tuple[Component, ...]
    market: MarketPlan | None = None
    cut_order: tuple[str, ...]


class LocalPlan(_Strict):
    model: str
    components: tuple[Component, ...]


class ExportItem(_Strict):
    name: str
    states: str
    splits: tuple[str, ...]
    questions: tuple[str, ...]


class TrainedPlan(_Strict):
    runs: dict[str, str]
    export: tuple[ExportItem, ...]
    max_gpu_hours: float = Field(gt=0)


class ProbesPlan(_Strict):
    samples: str
    edits: str
    unmasked: str
    laya_zero_shot: tuple[Literal["counterfactual_flip", "masked_vs_unmasked", "shuffled_news"], ...]
    trained: tuple[Literal["counterfactual_flip", "shuffled_news"], ...]


class AblationCall(_Strict):
    name: str
    base: str
    change: str
    probe: str | None = None


class AblationPlan(_Strict):
    model: str
    n: int = Field(gt=0)
    splits: tuple[str, ...]
    strata: tuple[str, ...]
    seed: int
    calls: tuple[AblationCall, ...]


class LlmPlan(_Strict):
    model: str
    split: str
    n: int = Field(gt=0)
    strata: tuple[str, ...]
    seed: int
    cap_usd: float = Field(gt=0)


class CanaryPlan(_Strict):
    file: str
    baseline: str
    repeats_for_noise: int = Field(gt=0)


class ProductionPlan(_Strict):
    version: int
    chunk: str
    cap_usd: float = Field(gt=0)
    primary_instrument: str
    encoding: str
    calls_per_event: int
    states: dict[str, str]
    api: ApiPlan
    comparators_core: tuple[Component, ...]
    laya_zero_shot: LocalPlan
    trained: TrainedPlan
    probes: ProbesPlan
    ablations: AblationPlan
    llm_baseline: LlmPlan
    price_only: dict[str, tuple[str, ...]]
    canary: CanaryPlan


@functools.cache
def _load(path: Path, mtime_ns: int) -> ProductionPlan:
    return ProductionPlan.model_validate(load_yaml(path))


def load_plan(path: Path = PLAN_PATH, frozen_path: Path | None = None) -> ProductionPlan:
    """The plan, refused unless it agrees with configs/frozen.yaml."""
    plan = _load(path, path.stat().st_mtime_ns)
    fz = load_frozen(frozen_path or path.parent / "frozen.yaml")
    sel = fz.selection if isinstance(fz.selection, dict) else {}
    checks = {
        "primary_instrument": (plan.primary_instrument, sel.get("primary_instrument")),
        "encoding": (plan.encoding, (fz.encoding or {}).get("chosen")),
        "calls_per_event": (plan.calls_per_event, (fz.anchoring or {}).get("calls_per_event")),
        "trained runs": ({k: [v] for k, v in plan.trained.runs.items()}, sel.get("trained_runs")),
    }
    bad = [f"{k}: plan {a!r} vs frozen {b!r}" for k, (a, b) in checks.items() if a != b]
    if bad:
        raise ProductionError("configs/production.yaml disagrees with configs/frozen.yaml: " + "; ".join(bad))
    missing = [c.states for c in plan.api.components for s in c.states if s not in plan.states]
    if missing:
        raise ProductionError(f"plan components name unknown state files: {missing}")
    return plan
