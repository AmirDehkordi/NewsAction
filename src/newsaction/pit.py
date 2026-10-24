"""Point-in-time availability registry (CLAUDE.md A5).

``configs/availability.yaml`` declares, for every column a state or model may consume, the kind of
information it is. ``check_inputs`` refuses unknown columns and columns not yet known at the
decision point; ``assert_visible`` checks row-level timestamps against the decision instant.

``selection_only`` (NA-02) marks vendor labels produced retrospectively (tags, sentiment, summaries,
event clusters; CLAUDE.md A6): they may select news but are visible at no decision point, so a state
builder that passes one to ``check_inputs`` fails like it would for ``post``.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, Literal, cast, get_args

import pandas as pd

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS

Kind = Literal["static", "t_minus_1", "w0", "d1", "w2", "d2_reaction", "post", "selection_only"]
DecisionPoint = Literal["D0", "D1", "D2"]
KINDS: Final[frozenset[str]] = frozenset(get_args(Kind))

_D0: Final[frozenset[Kind]] = frozenset({"static", "t_minus_1", "w0"})
_D1: Final[frozenset[Kind]] = _D0 | {"d1"}
_D2: Final[frozenset[Kind]] = _D1 | {"w2", "d2_reaction"}
VISIBLE: Final[Mapping[DecisionPoint, frozenset[Kind]]] = {"D0": _D0, "D1": _D1, "D2": _D2}

DEFAULT_REGISTRY_PATH: Final = CONFIGS / "availability.yaml"


class PITError(Exception):
    """A point-in-time violation: an input not available at the decision point."""


class AvailabilityRegistry:
    """Column name -> availability kind, loaded from ``configs/availability.yaml``."""

    def __init__(self, columns: Mapping[str, str]) -> None:
        bad = {c: k for c, k in columns.items() if k not in KINDS}
        if bad:
            raise PITError(f"unknown availability kinds {bad}; allowed: {sorted(KINDS)}")
        self._columns: dict[str, Kind] = {c: cast(Kind, k) for c, k in columns.items()}

    @classmethod
    def from_yaml(cls, path: Path = DEFAULT_REGISTRY_PATH) -> AvailabilityRegistry:
        raw = load_yaml(path)
        declared = set(raw.get("kinds") or {})
        if declared != KINDS:
            raise PITError(f"{path}: 'kinds' {sorted(declared)} must equal {sorted(KINDS)}")
        columns = raw.get("columns")
        if not isinstance(columns, dict) or not columns:
            raise PITError(f"{path}: 'columns' must be a non-empty mapping")
        return cls({str(c): str(k) for c, k in columns.items()})

    @property
    def columns(self) -> Mapping[str, Kind]:
        return dict(self._columns)

    def kind(self, column: str) -> Kind:
        try:
            return self._columns[column]
        except KeyError:
            raise PITError(f"column {column!r} is not registered in the availability registry") from None

    def check_inputs(self, columns: Iterable[str], decision_point: DecisionPoint) -> None:
        """Raise PITError unless every column is registered and visible at ``decision_point``."""
        if decision_point not in VISIBLE:
            raise PITError(f"unknown decision point {decision_point!r}; expected one of {sorted(VISIBLE)}")
        visible = VISIBLE[decision_point]
        cols = list(columns)
        unknown = [c for c in cols if c not in self._columns]
        late = {c: self._columns[c] for c in cols if c in self._columns and self._columns[c] not in visible}
        if unknown or late:
            parts = []
            if unknown:
                parts.append(f"unregistered columns {unknown}")
            if late:
                parts.append(f"columns not available at {decision_point}: {late}")
            raise PITError("; ".join(parts))


@functools.cache
def _load_cached(path: Path, mtime_ns: int) -> AvailabilityRegistry:
    return AvailabilityRegistry.from_yaml(path)


def default_registry(path: Path = DEFAULT_REGISTRY_PATH) -> AvailabilityRegistry:
    """The registry in ``configs/availability.yaml`` (reloaded when the file changes)."""
    return _load_cached(path, path.stat().st_mtime_ns)


def check_inputs(
    columns: Iterable[str], decision_point: DecisionPoint, registry: AvailabilityRegistry | None = None
) -> None:
    """Module-level form of ``AvailabilityRegistry.check_inputs`` on the default registry."""
    (default_registry() if registry is None else registry).check_inputs(columns, decision_point)


def assert_visible(df: pd.DataFrame, ts_col: str, decision_ts_col: str) -> None:
    """Raise PITError if any row's ``ts_col`` is later than its ``decision_ts_col`` (or either is NaT)."""
    for col in (ts_col, decision_ts_col):
        if col not in df.columns:
            raise PITError(f"column {col!r} not in frame")
        if not isinstance(df[col].dtype, pd.DatetimeTZDtype):
            raise PITError(f"column {col!r} must be tz-aware datetime, got {df[col].dtype}")
    ts = df[ts_col]
    decision = df[decision_ts_col]
    missing = ts.isna() | decision.isna()
    future = (ts > decision).fillna(False).astype(bool)
    bad = missing | future
    if bool(bad.any()):
        first = df.index[bad.to_numpy()][0]
        raise PITError(
            f"{int(future.sum())} rows have {ts_col} > {decision_ts_col} and {int(missing.sum())} rows have "
            f"NaT; first offending index {first!r}"
        )
