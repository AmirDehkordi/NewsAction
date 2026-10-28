"""Exact Shapley decomposition over feature groups (PREREG §11.5; H3). Hash-locked at the NA-11 freeze.

The value of a coalition S of feature groups is a model's out-of-sample score using the features of S (OOS R²
or the mean daily IC of its predictions); the empty coalition is worth 0 (the zero forecast, or no ranking).
Over n groups the Shapley value of group i is

    φ_i = Σ_{S ⊆ G∖{i}} |S|! (n − |S| − 1)! / n! · [v(S ∪ {i}) − v(S)],

which is exact here: §11.5 fits all 2^n − 1 = 7 non-empty coalitions of {R, N, J}. The values add up to the
full model's score (efficiency), so the **share** of group i is φ_i / v(G). The pairwise interaction
v({a, b}) − v({a}) − v({b}) is reported beside them: it is positive when two groups are complements (each
alone explains little) and negative when they carry the same information.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Final

GROUPS: Final = ("R", "N", "J")


def coalitions(groups: Sequence[str] = GROUPS) -> list[frozenset[str]]:
    """The non-empty coalitions, by size, then in the order of ``groups``."""
    out: list[frozenset[str]] = []
    for k in range(1, len(groups) + 1):
        out.extend(frozenset(c) for c in itertools.combinations(groups, k))
    return out


def label(coalition: frozenset[str], groups: Sequence[str] = GROUPS) -> str:
    """ "R+N" style name of a coalition, in the order of ``groups``."""
    return "+".join(g for g in groups if g in coalition)


def shapley(values: Mapping[frozenset[str], float], groups: Sequence[str] = GROUPS) -> dict[str, float]:
    """Exact Shapley values; ``values`` holds every non-empty coalition (the empty one is 0 unless given)."""
    n = len(groups)
    if len(set(groups)) != n:
        raise ValueError("groups must be distinct")
    v = {frozenset(): 0.0, **{frozenset(k): float(x) for k, x in values.items()}}
    missing = [label(c, groups) for c in coalitions(groups) if c not in v]
    if missing:
        raise ValueError(f"coalitions without a value: {missing}")
    out: dict[str, float] = {}
    for i in groups:
        rest = [g for g in groups if g != i]
        total = 0.0
        for k in range(len(rest) + 1):
            w = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            for s in itertools.combinations(rest, k):
                base = frozenset(s)
                total += w * (v[base | {i}] - v[base])
        out[i] = total
    return out


def shares(phi: Mapping[str, float]) -> dict[str, float]:
    """φ_i / Σ φ (= φ_i / v(G) by efficiency); NaN when the full value is 0 or not finite."""
    total = math.fsum(phi.values())
    if not math.isfinite(total) or total == 0:
        return {k: math.nan for k in phi}
    return {k: x / total for k, x in phi.items()}


def interactions(values: Mapping[frozenset[str], float], groups: Sequence[str] = GROUPS) -> dict[str, float]:
    """v({a, b}) − v({a}) − v({b}) for every pair (positive: complements; negative: overlap)."""
    out: dict[str, float] = {}
    for a, b in itertools.combinations(groups, 2):
        pair = values[frozenset((a, b))]
        out[f"{a}x{b}"] = float(pair - values[frozenset((a,))] - values[frozenset((b,))])
    return out
