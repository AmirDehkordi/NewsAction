"""Exact Shapley over {R, N, J} (PREREG §11.5): efficiency, symmetry, null player, a planted interaction."""

from __future__ import annotations

import itertools
import math

import pytest

from newsaction.analysis import shapley as sh


def values(fn: dict[str, float]) -> dict[frozenset[str], float]:
    return {c: fn[sh.label(c)] for c in sh.coalitions()}


def test_coalitions_are_the_seven_non_empty_subsets() -> None:
    cs = sh.coalitions()
    assert [sh.label(c) for c in cs] == ["R", "N", "J", "R+N", "R+J", "N+J", "R+N+J"]


def test_additive_game_gives_each_group_its_own_value() -> None:
    w = {"R": 0.1, "N": 0.05, "J": 0.02}
    v = {c: sum(w[g] for g in c) for c in sh.coalitions()}
    phi = sh.shapley(v)
    assert phi == pytest.approx(w)
    assert sh.shares(phi) == pytest.approx({k: x / 0.17 for k, x in w.items()})
    assert all(abs(x) < 1e-12 for x in sh.interactions(v).values())


def test_efficiency_on_an_arbitrary_game() -> None:
    v = values({"R": 0.02, "N": 0.07, "J": -0.01, "R+N": 0.12, "R+J": 0.03, "N+J": 0.05, "R+N+J": 0.15})
    phi = sh.shapley(v)
    assert math.fsum(phi.values()) == pytest.approx(0.15)
    # the explicit permutation average gives the same values
    perm: dict[str, float] = {g: 0.0 for g in sh.GROUPS}
    for order in itertools.permutations(sh.GROUPS):
        seen: frozenset[str] = frozenset()
        for g in order:
            new = seen | {g}
            perm[g] += (v[new] - (v[seen] if seen else 0.0)) / 6
            seen = new
    assert phi == pytest.approx(perm)


def test_planted_pure_interaction_is_split_equally() -> None:
    """R and N are complements (each alone is worth 0, together 0.3); J is a null player."""
    v = values({"R": 0.0, "N": 0.0, "J": 0.0, "R+N": 0.3, "R+J": 0.0, "N+J": 0.0, "R+N+J": 0.3})
    phi = sh.shapley(v)
    assert (
        phi["R"] == pytest.approx(0.15) and phi["N"] == pytest.approx(0.15) and phi["J"] == pytest.approx(0.0)
    )
    assert sh.interactions(v)["RxN"] == pytest.approx(0.3)


def test_redundant_groups_share_and_show_negative_interaction() -> None:
    v = values({"R": 0.2, "N": 0.2, "J": 0.0, "R+N": 0.2, "R+J": 0.2, "N+J": 0.2, "R+N+J": 0.2})
    phi = sh.shapley(v)
    assert phi["R"] == pytest.approx(0.1) and phi["N"] == pytest.approx(0.1)
    assert sh.interactions(v)["RxN"] == pytest.approx(-0.2)


def test_missing_coalition_and_zero_total() -> None:
    v = values({"R": 0.0, "N": 0.0, "J": 0.0, "R+N": 0.0, "R+J": 0.0, "N+J": 0.0, "R+N+J": 0.0})
    assert all(math.isnan(x) for x in sh.shares(sh.shapley(v)).values())
    del v[frozenset({"R", "N"})]
    with pytest.raises(ValueError, match="R\\+N"):
        sh.shapley(v)
