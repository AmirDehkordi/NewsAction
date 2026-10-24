"""Typed configuration (``configs/*.yaml``). Values mirror docs/PREREG.md; tests/test_configs_match_prereg.py
enforces the correspondence.
"""

from __future__ import annotations

import functools
import hashlib
import itertools
from datetime import date, time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsaction.paths import CONFIGS

SplitName = Literal["robustness", "train", "val_a", "val_b", "test"]
SPLIT_ORDER: tuple[SplitName, ...] = ("robustness", "train", "val_a", "val_b", "test")


class ConfigError(Exception):
    """A configuration file is missing, malformed or inconsistent."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (PyYAML silently keeps the last one)."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise ConfigError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML mapping, rejecting duplicate keys."""
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        obj = yaml.load(fh, Loader=_UniqueKeyLoader)  # a SafeLoader subclass
    if not isinstance(obj, dict):
        raise ConfigError(f"{path} must contain a mapping at top level")
    return obj


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DateRange(_Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.start > self.end:
            raise ValueError(f"start {self.start} is after end {self.end}")
        return self

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


class BudgetConfig(_Strict):
    """OpenRouter budget in USD (PREREG §13). Chunks without an entry have a cap of 0."""

    total_usd: float = Field(gt=0)
    reserve_usd: float = Field(ge=0)
    chunk_caps: dict[str, float]

    @model_validator(mode="after")
    def _caps_fit(self) -> BudgetConfig:
        if any(v < 0 for v in self.chunk_caps.values()):
            raise ValueError("chunk caps must be >= 0")
        allotted = sum(self.chunk_caps.values()) + self.reserve_usd
        if allotted > self.total_usd + 1e-9:
            raise ValueError(f"chunk caps + reserve = {allotted} exceed total {self.total_usd}")
        return self

    def chunk_cap(self, chunk_id: str) -> float:
        return self.chunk_caps.get(chunk_id, 0.0)


class ProjectConfig(_Strict):
    timezone: str
    exchange: str
    d0_cutoff: time
    d1_time: time
    calendar: DateRange
    budget: BudgetConfig
    fmp_request_cap: int = Field(gt=0)
    seeds: dict[str, int]


class SplitsConfig(_Strict):
    splits: dict[SplitName, DateRange]
    embargo_sessions: int = Field(ge=0)
    max_horizon: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered_disjoint(self) -> SplitsConfig:
        if tuple(self.splits) != SPLIT_ORDER:
            raise ValueError(f"splits must be exactly {SPLIT_ORDER} in this order")
        ranges = list(self.splits.values())
        for prev, nxt in itertools.pairwise(ranges):
            if not prev.end < nxt.start:
                raise ValueError(f"splits overlap or are out of order: {prev} / {nxt}")
        return self

    def split_of(self, d: date) -> SplitName | None:
        for name, rng in self.splits.items():
            if rng.contains(d):
                return name
        return None


class FrozenConfig(BaseModel):
    """``configs/frozen.yaml``: selections recorded by the protocol; later chunks add keys."""

    model_config = ConfigDict(extra="allow", frozen=True)

    news: Any = None
    filter: Any = None
    encoding: Any = None
    anchoring: Any = None
    tournament: Any = None
    selection: Any = None
    thresholds: Any = None
    calibration: Any = None
    allow_val_b: bool = False
    frozen_requested: bool = False
    frozen: bool = False


@functools.cache
def load_project(path: Path = CONFIGS / "project.yaml") -> ProjectConfig:
    return ProjectConfig.model_validate(load_yaml(path))


@functools.cache
def load_splits(path: Path = CONFIGS / "splits.yaml") -> SplitsConfig:
    return SplitsConfig.model_validate(load_yaml(path))


def load_frozen(path: Path = CONFIGS / "frozen.yaml") -> FrozenConfig:
    """Not cached: NA-06 and NA-11 change this file during a session."""
    return FrozenConfig.model_validate(load_yaml(path))


def config_sha256(configs_dir: Path = CONFIGS) -> str:
    """sha256 over every ``configs/*.yaml`` (name + bytes), recorded in run records (CLAUDE.md F20)."""
    h = hashlib.sha256()
    for p in sorted(configs_dir.glob("*.yaml")):
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()
