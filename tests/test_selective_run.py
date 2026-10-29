"""NA-13b stage guards: the validation stage reads no test row; the test stage needs the committed selection
and the same val-A cut points; table keys are unique and citable."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from newsaction.paths import Layout
from newsaction.selective import conditioning as cg
from newsaction.selective import conditions as cd
from newsaction.selective import data as sd
from newsaction.selective import run as rn


def test_the_validation_stage_passes_no_test_row_to_the_statistics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    study = pd.DataFrame({"split": ["val_a", "val_b", "test"], "x": [1.0, 2.0, 3.0]})
    monkeypatch.setattr(sd, "study_frame", lambda layout=None: study.copy())

    def cuts(s: pd.DataFrame) -> dict[str, float]:
        seen["cuts"] = set(s["split"])
        return {"median_x": 1.0}

    def evaluate(s: pd.DataFrame, c: Any, splits: Any, **kw: Any) -> pd.DataFrame:
        seen["evaluate"] = set(s["split"])
        return pd.DataFrame()

    monkeypatch.setattr(cd, "cuts", cuts)
    monkeypatch.setattr(cg, "evaluate", evaluate)
    monkeypatch.setattr(
        cg, "select", lambda v: pd.DataFrame({"model": ["m"], "condition": ["c"], "selected": [True]})
    )
    out = rn.validation(Layout(tmp_path))
    assert seen == {"cuts": {"val_a", "val_b"}, "evaluate": {"val_a", "val_b"}}
    assert out["selected"] == ["m|c"]
    assert (tmp_path / rn.SELECTION_JSON).is_file()


def test_the_test_stage_refuses_an_uncommitted_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rn, "committed", lambda lay, rel: False)
    with pytest.raises(rn.RunError, match="commit the validation selection"):
        rn.test(Layout(tmp_path))


def test_the_test_stage_refuses_changed_cut_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rn, "_selected", lambda lay: ([], pd.DataFrame(), {"cuts": {"median_x": 1.0}}))
    monkeypatch.setattr(sd, "study_frame", lambda layout=None: pd.DataFrame({"split": ["val_a"], "x": [1.0]}))
    monkeypatch.setattr(cd, "cuts", lambda s: {"median_x": 1.5})
    with pytest.raises(rn.RunError, match="cut points differ"):
        rn.test(Layout(tmp_path))


def test_tables_refuse_duplicate_or_uncitable_keys(tmp_path: Path) -> None:
    lay = Layout(tmp_path)
    with pytest.raises(rn.RunError, match="duplicate"):
        rn.write_table(lay, "cuts", pd.DataFrame({"name": ["a", "a"], "value": [1, 2]}), ["name"])
    with pytest.raises(rn.RunError, match="citation"):
        rn.write_table(lay, "cuts", pd.DataFrame({"name": ["liquid/d1-ultra"], "value": [1]}), ["name"])
    rn.write_table(lay, "cuts", pd.DataFrame({"name": ["a", "b"], "value": [1, 2]}), ["name"])
    got = rn.read_table(lay, "cuts")
    assert got["key"].tolist() == ["a", "b"] and got["value"].tolist() == [1, 2]


def test_vix_is_the_close_of_the_session_before(monkeypatch: pytest.MonkeyPatch) -> None:
    fri, mon, tue = date(2025, 10, 3), date(2025, 10, 6), date(2025, 10, 7)
    prices = pd.DataFrame(
        {"symbol": ["^VIX"] * 3 + ["SPY"], "date": pd.to_datetime([fri, mon, tue, tue]),
         "close": [20.0, 30.0, 40.0, 600.0]}
    )  # fmt: skip
    monkeypatch.setattr(sd.io, "read_parquet", lambda rel, columns=None, layout=None: prices)
    got = sd.vix_prev([mon, tue])
    assert got[mon] == 20.0 and got[tue] == 30.0  # never the session's own close
