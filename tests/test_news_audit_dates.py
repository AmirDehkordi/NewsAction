"""PRD NA-02 AC6: the leakage audit and the re-derived diagnostics use public sessions only (≤ 2025-12-31).

Verifier mutation: drop the ``assert_public`` call in ``audit.join_targets`` ->
test_join_refuses_test_sessions RED; make ``public_only`` keep every row ->
test_public_only_drops_test_sessions RED.
"""

from __future__ import annotations

import ast
from datetime import date

import pandas as pd
import pytest
import yaml

from newsaction.news import audit
from newsaction.paths import ROOT

PANEL = pd.DataFrame(
    {
        "company_id": [1, 1],
        "session": [date(2025, 12, 31), date(2025, 12, 30)],
        "z_on": [1.0, -1.0],
        "z_id": [0.5, 0.2],
        "ar_on": [0.01, -0.01],
    }
)


def test_public_end_is_the_end_of_val_b() -> None:
    assert date(2025, 12, 31) == audit.PUBLIC_END


def test_assert_public() -> None:
    audit.assert_public([date(2025, 12, 31), None])
    with pytest.raises(audit.AuditError, match="2026-01-02"):
        audit.assert_public([date(2025, 6, 2), date(2026, 1, 2)])


def test_public_only_drops_test_sessions() -> None:
    df = pd.DataFrame({"s": [date(2025, 12, 31), date(2026, 1, 2), None]})
    assert audit.public_only(df, "s")["s"].tolist() == [date(2025, 12, 31)]


def test_join_refuses_test_sessions() -> None:
    td = pd.DataFrame({"company_id": [1], "session": [date(2026, 1, 2)], "sent": [1.0], "n_articles": [1]})
    with pytest.raises(audit.AuditError):
        audit.join_targets(td, PANEL)


def test_ticker_day_drops_2026_articles_before_any_join() -> None:
    arts = pd.DataFrame(
        {
            "id": ["a", "b"],
            "company_id": [1, 1],
            "session_w0": [date(2025, 12, 31), date(2026, 1, 2)],
            "sentiment_direction": ["Positive", "Negative"],
        }
    )
    td = audit.ticker_day(arts, "session_w0")
    assert td["session"].tolist() == [date(2025, 12, 31)]
    joined = audit.join_targets(td, PANEL)
    assert len(joined) == 1


def test_every_return_join_goes_through_the_guard() -> None:
    """In audit.py, every merge with the panel happens inside join_targets (which asserts first)."""
    src = (ROOT / "src" / "newsaction" / "news" / "audit.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    join = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "join_targets")
    first = join.body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
    assert getattr(first.value.func, "id", None) == "assert_public"
    targets = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "public_targets")
    assert "assert_public" in ast.unparse(targets)


def test_leaky_rule() -> None:
    assert audit.is_leaky({"ic_z_on": 0.02, "ic_z_id": 0.03, "t_z_id": 2.5}, 2.0)
    assert not audit.is_leaky({"ic_z_on": 0.05, "ic_z_id": 0.03, "t_z_id": 2.5}, 2.0)  # gap IC larger
    assert not audit.is_leaky({"ic_z_on": 0.01, "ic_z_id": 0.03, "t_z_id": 1.5}, 2.0)  # not significant
    assert not audit.is_leaky({"ic_z_on": float("nan"), "ic_z_id": 0.03, "t_z_id": 3.0}, 2.0)


def test_nw_t_matches_iid_formula_without_lags() -> None:
    x = pd.Series([0.1, 0.3, -0.2, 0.4, 0.0, 0.2])
    m, t, n = audit.nw_t(x, 0)
    assert n == 6 and m == pytest.approx(x.mean())
    assert t == pytest.approx(x.mean() / (x.std(ddof=0) / len(x) ** 0.5))


def test_daily_ic_is_spearman_per_session() -> None:
    df = pd.DataFrame(
        {
            "session": [1] * 4 + [2] * 4,
            "sent": [1, 2, 3, 4, 1, 2, 3, 4],
            "z": [0.1, 0.2, 0.3, 0.4, 0.4, 0.3, 0.2, 0.1],
        }
    )
    ic = audit.daily_ic(df, "sent", "z", min_names=4)
    assert ic.tolist() == pytest.approx([1.0, -1.0])
    assert audit.daily_ic(df, "sent", "z", min_names=5).empty


def test_frozen_news_section_matches_leakage_table() -> None:
    csv = ROOT / "artifacts" / "NA-02" / "leakage_ic.csv"
    if not csv.is_file():
        pytest.skip("artifacts/NA-02/leakage_ic.csv absent (run the NA-02 audit)")
    leak = pd.read_csv(csv, dtype={"value": str})
    want = audit.frozen_news_section(leak, csv)
    got = yaml.safe_load((ROOT / "configs" / "frozen.yaml").read_text(encoding="utf-8"))["news"]
    for key in ("summary_variant_allowed", "excluded_sources", "leakage_audit_sha"):
        assert got[key] == want[key], key
    assert set(leak["value"][leak["cell"] == "source_class"]) <= {
        "press_wire_primary",
        "major_outlet",
        "aggregator",
        "retail_analysis",
        "auto_generated",
        "other",
    }


def test_same_session_treats_two_missing_values_as_equal() -> None:
    a = pd.Series([date(2025, 3, 10), None, None, date(2025, 3, 10)], dtype=object)
    b = pd.Series(
        [date(2025, 3, 10), float("nan"), date(2025, 3, 11), pd.Timestamp("2025-03-11")], dtype=object
    )
    assert audit.same_session(a, b).tolist() == [True, True, False, False]
