"""Availability registry and row-level visibility (CLAUDE.md A5; PRD NA-00 AC4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from newsaction import pit
from newsaction.config import ConfigError
from newsaction.pit import AvailabilityRegistry, PITError

# Expected visibility, written out independently of pit.VISIBLE (PRD NA-00 S7).
EXPECTED = {
    "D0": {"static", "t_minus_1", "w0"},
    "D1": {"static", "t_minus_1", "w0", "d1"},
    "D2": {"static", "t_minus_1", "w0", "d1", "w2", "d2_reaction"},
}
ALL_KINDS = ["static", "t_minus_1", "w0", "d1", "w2", "d2_reaction", "post", "selection_only"]


@pytest.fixture
def registry() -> AvailabilityRegistry:
    return AvailabilityRegistry({f"col_{k}": k for k in ALL_KINDS})


def test_z_id_is_post_and_refused_at_d0() -> None:
    reg = pit.default_registry()
    assert reg.kind("z_id") == "post"
    with pytest.raises(PITError, match="z_id"):
        pit.check_inputs(["z_id"], "D0")
    with pytest.raises(PITError, match="z_id"):
        reg.check_inputs(["z_id"], "D0")


@pytest.mark.parametrize("point", ["D0", "D1", "D2"])
def test_post_is_never_visible(point: pit.DecisionPoint) -> None:
    with pytest.raises(PITError):
        pit.check_inputs(["tier", "z_id"], point)


def test_unknown_column_raises() -> None:
    with pytest.raises(PITError, match="not_registered_anywhere"):
        pit.check_inputs(["tier", "not_registered_anywhere"], "D2")
    with pytest.raises(PITError, match="not registered"):
        pit.default_registry().kind("not_registered_anywhere")


@pytest.mark.parametrize("point", ["D0", "D1", "D2"])
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_visibility_matrix(registry: AvailabilityRegistry, point: pit.DecisionPoint, kind: str) -> None:
    col = f"col_{kind}"
    if kind in EXPECTED[point]:
        registry.check_inputs([col], point)
        pit.check_inputs([col], point, registry=registry)
    else:
        with pytest.raises(PITError):
            registry.check_inputs([col], point)
        with pytest.raises(PITError):
            pit.check_inputs([col], point, registry=registry)


def test_d0_accepts_its_seed_columns() -> None:
    pit.check_inputs(["session", "company_id", "tier", "beta_m", "news_w0"], "D0")
    pit.check_inputs(["tier", "news_w0", "g_d1"], "D1")
    pit.check_inputs(["tier", "news_w2", "g_d2", "g_d1"], "D2")
    with pytest.raises(PITError):
        pit.check_inputs(["g_d2"], "D1")
    with pytest.raises(PITError):
        pit.check_inputs(["news_w2"], "D0")


def test_unknown_decision_point(registry: AvailabilityRegistry) -> None:
    with pytest.raises(PITError, match="decision point"):
        registry.check_inputs(["col_static"], "D3")  # type: ignore[arg-type]


def test_error_lists_every_offender(registry: AvailabilityRegistry) -> None:
    with pytest.raises(PITError) as exc:
        registry.check_inputs(["col_post", "col_w2", "nope"], "D0")
    msg = str(exc.value)
    assert "col_post" in msg and "col_w2" in msg and "nope" in msg


def test_invalid_kind_rejected() -> None:
    with pytest.raises(PITError, match="unknown availability kinds"):
        AvailabilityRegistry({"x": "tomorrow"})


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "availability.yaml"
    p.write_text(text, encoding="utf-8")
    return p


KINDS_BLOCK = "kinds:\n" + "".join(f"  {k}: x\n" for k in ALL_KINDS)


def test_yaml_kinds_must_match_code(tmp_path: Path) -> None:
    p = _write(tmp_path, "kinds:\n  static: x\ncolumns:\n  a: static\n")
    with pytest.raises(PITError, match="kinds"):
        AvailabilityRegistry.from_yaml(p)


def test_yaml_duplicate_column_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, KINDS_BLOCK + "columns:\n  a: static\n  a: post\n")
    with pytest.raises(ConfigError, match="duplicate key 'a'"):
        AvailabilityRegistry.from_yaml(p)


def test_yaml_roundtrip(tmp_path: Path) -> None:
    p = _write(tmp_path, KINDS_BLOCK + "columns:\n  a: static\n  b: post\n")
    reg = AvailabilityRegistry.from_yaml(p)
    assert reg.columns == {"a": "static", "b": "post"}


def test_real_registry_declares_every_kind_once() -> None:
    reg = pit.default_registry()
    assert set(reg.columns.values()) <= set(ALL_KINDS)
    for target in ("z_on", "z_cc", "z_id", "y0", "y1", "y2", "e5"):
        assert reg.kind(target) == "post"


# --- assert_visible ---------------------------------------------------------------------------------


def _frame(article_ts: list[str], decision_ts: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t_avail": pd.to_datetime(article_ts, utc=True, format="ISO8601"),
            "decision": pd.to_datetime(decision_ts, utc=True, format="ISO8601"),
        }
    )


def test_assert_visible_passes_on_and_before_decision() -> None:
    df = _frame(["2024-03-11 13:00", "2024-03-11 13:15"], ["2024-03-11 13:15", "2024-03-11 13:15"])
    pit.assert_visible(df, "t_avail", "decision")


def test_assert_visible_raises_on_planted_future_row() -> None:
    df = _frame(
        ["2024-03-11 13:00", "2024-03-11 13:15:01", "2024-03-11 12:00"],
        ["2024-03-11 13:15", "2024-03-11 13:15", "2024-03-11 13:15"],
    )
    with pytest.raises(PITError, match="1 rows"):
        pit.assert_visible(df, "t_avail", "decision")


def test_assert_visible_raises_on_nat() -> None:
    df = _frame(["2024-03-11 13:00"], ["2024-03-11 13:15"])
    df.loc[0, "t_avail"] = pd.NaT
    with pytest.raises(PITError, match="NaT"):
        pit.assert_visible(df, "t_avail", "decision")


def test_assert_visible_requires_tz_aware_columns() -> None:
    df = pd.DataFrame(
        {"t_avail": pd.to_datetime(["2024-03-11 13:00"]), "decision": pd.to_datetime(["2024-03-11 13:15"])}
    )
    with pytest.raises(PITError, match="tz-aware"):
        pit.assert_visible(df, "t_avail", "decision")
    with pytest.raises(PITError, match="not in frame"):
        pit.assert_visible(df, "missing", "decision")
