"""configs/*.yaml must equal docs/PREREG.md (PRD NA-00 AC7).

Expected values are hard-coded here with their PREREG section; each is also checked against the
PREREG text so a silent edit to either side fails.
"""

from __future__ import annotations

import itertools
import re
from datetime import date, time
from pathlib import Path

import pydantic
import pytest
import yaml

from newsaction import calendar as cal
from newsaction.config import (
    SPLIT_ORDER,
    BudgetConfig,
    SplitsConfig,
    load_frozen,
    load_project,
    load_splits,
)
from newsaction.news import clean
from newsaction.paths import ROOT

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")

# PREREG §4 (splits table)
SPLITS = {
    "robustness": (date(2024, 1, 2), date(2024, 6, 28)),
    "train": (date(2024, 7, 1), date(2025, 6, 30)),
    "val_a": (date(2025, 7, 1), date(2025, 9, 30)),
    "val_b": (date(2025, 10, 1), date(2025, 12, 31)),
    "test": (date(2026, 1, 2), date(2026, 7, 31)),
}
EMBARGO_SESSIONS = 5  # PREREG §4.2
MAX_HORIZON = 20  # PREREG §5.6 (D2: -> C_{t+20})
TIMEZONE, EXCHANGE = "America/New_York", "XNYS"  # PREREG §2.1
D0_CUTOFF, D1_TIME = time(9, 15), time(10, 0)  # PREREG §2.4, §2.5
TOTAL_USD, RESERVE_USD = 30.0, 1.8  # PREREG §13
CHUNK_CAPS = {"NA-05": 0.2, "NA-06": 4.0, "NA-07": 2.0, "NA-09": 2.0, "NA-11": 18.0, "NA-15": 2.0}  # §13
FMP_REQUEST_CAP = 17000  # PREREG §13 (3,000), raised in the §15 row of NA-10 (operator decision 2026-10-27)
GLOBAL_SEED = 2026  # PREREG §8.2, §11.4


def test_split_dates() -> None:
    cfg = load_splits()
    assert tuple(cfg.splits) == SPLIT_ORDER
    assert {k: (v.start, v.end) for k, v in cfg.splits.items()} == SPLITS


def test_split_dates_match_prereg_table() -> None:
    labels = {"robustness": "robustness-only", "train": "**train**", "val_a": "**val-A**",
              "val_b": "**val-B**", "test": "**test**"}  # fmt: skip
    for name, (start, end) in SPLITS.items():
        row = f"| {labels[name]} | {start.isoformat()} → {end.isoformat()} |"
        assert row in PREREG, row


def test_splits_are_contiguous_sessions() -> None:
    ranges = list(SPLITS.values())
    for start, end in ranges:
        assert cal.is_session(start) and cal.is_session(end)
    for (_, end), (nxt, _) in itertools.pairwise(ranges):
        assert cal.next_session(end) == nxt


def test_embargo_and_horizon() -> None:
    cfg = load_splits()
    assert cfg.embargo_sessions == EMBARGO_SESSIONS
    assert cfg.max_horizon == MAX_HORIZON
    assert "first 5 sessions of val-A, val-B and test" in PREREG
    assert "C_{t+20}" in PREREG


def test_time_conventions() -> None:
    p = load_project()
    assert (p.timezone, p.exchange) == (TIMEZONE, EXCHANGE)
    assert p.d0_cutoff == D0_CUTOFF
    assert p.d1_time == D1_TIME
    assert "09:15 ET of s]" in PREREG
    assert "| **D1** (only with NA-10 bars) | 10:00 ET |" in PREREG
    assert "regular session 09:30–16:00 America/New_York; half days close 13:00" in PREREG


def test_budget_caps() -> None:
    b = load_project().budget
    assert b.total_usd == TOTAL_USD
    assert b.reserve_usd == RESERVE_USD
    assert b.chunk_caps == CHUNK_CAPS
    assert sum(CHUNK_CAPS.values()) + RESERVE_USD == pytest.approx(TOTAL_USD)
    line = next(ln for ln in PREREG.splitlines() if ln.startswith("- **OpenRouter:**"))
    assert "$30 total" in line
    assert {k: float(v) for k, v in re.findall(r"(NA-\d\d) \$([\d.]+)", line)} == CHUNK_CAPS
    assert f"reserve ${RESERVE_USD}" in line


def test_fmp_cap_and_seed() -> None:
    p = load_project()
    assert p.fmp_request_cap == FMP_REQUEST_CAP
    assert "**FMP:** ≤ 3,000 requests" in PREREG
    log = PREREG[PREREG.index("## 15. Deviations log") :]
    assert "| NA-10 (operator decision) | §13 (FMP ≤ 3,000 requests)" in log
    assert "raised from 3,000 to **17,000**" in log
    assert p.seeds["global"] == GLOBAL_SEED
    assert "seed 2026" in PREREG


def test_frozen_skeleton() -> None:
    f = load_frozen()
    assert f.frozen_requested is False
    assert f.frozen is False
    for section in ("selection", "thresholds", "calibration"):
        assert getattr(f, section) is None
    # NA-07 (PRD S5) owns ``encoding:`` and ``anchoring:`` (PREREG §8.4); its report writes both together
    assert (f.encoding is None) is (f.anchoring is None)
    if f.encoding:
        assert {"chosen", "val_a_best", "val_a_table_sha", "val_b_check"} <= set(f.encoding)
        assert f.encoding["chosen"] in ("E0", "E1", "E2", "E3", "E4")
        assert {"present", "slope", "corr", "calls_per_event"} <= set(f.anchoring)
        assert f.anchoring["calls_per_event"] == (2 if f.anchoring["present"] else 1)
    # NA-06 (PRD S6) owns ``tournament:`` and opens val-B only once it is recorded (CLAUDE.md C13)
    assert f.allow_val_b is bool(f.tournament)
    if f.tournament:
        keys = {"stage1_survivors", "stage2_models", "stage2_survivors_passing", "leaderboard_sha"}
        assert keys <= set(f.tournament) and len(str(f.tournament["leaderboard_sha"])) == 64


def test_frozen_filter_section_from_na03() -> None:
    """NA-03 (PRD S4) owns ``filter:`` (PREREG §6.8); it is null before the NA-03 comparison runs."""
    ff = load_frozen().filter
    if ff is None:
        return
    keys = {"id", "threshold", "budget_share", "rule_version", "comparison_sha"}
    assert keys <= set(ff)
    assert ff["id"] in {"F1", "F2", "F3", "F4", "F5", "F6"}
    assert ff["budget_share"] == 0.30 and "selected ticker-days ≤ 30% of covered member-days" in PREREG
    assert isinstance(ff["threshold"], float) and 0.0 <= ff["tie_u_max"] <= 1.0
    assert len(str(ff["comparison_sha"])) == 64


def test_frozen_news_section_from_na02() -> None:
    """NA-02 (PRD S10) owns ``news:``; it is null before the NA-02 audit runs."""
    news = load_frozen().news
    if news is None:
        return
    keys = {"summary_variant_allowed", "excluded_sources", "leakage_audit_sha", "leakage_audit_file"}
    assert set(news) == keys | {"parsing_allowed_none"}
    assert news["parsing_allowed_none"] in clean.NONE_POLICIES  # PREREG §6.1; the operator's decision, §15
    assert isinstance(news["summary_variant_allowed"], bool)
    assert isinstance(news["excluded_sources"], list)
    assert len(str(news["leakage_audit_sha"])) == 64


def test_times_are_quoted_in_yaml() -> None:
    """Unquoted 10:00 is the sexagesimal integer 600 in YAML 1.1."""
    raw = yaml.safe_load((ROOT / "configs" / "project.yaml").read_text(encoding="utf-8"))
    assert raw["d0_cutoff"] == "09:15" and raw["d1_time"] == "10:00"


def test_split_validation_rejects_overlap(tmp_path: Path) -> None:
    bad = {
        "splits": {k: {"start": s, "end": e} for k, (s, e) in SPLITS.items()},
        "embargo_sessions": 5,
        "max_horizon": 20,
    }
    bad["splits"]["val_a"]["start"] = date(2025, 6, 30)
    with pytest.raises(pydantic.ValidationError, match="overlap"):
        SplitsConfig.model_validate(bad)


def test_budget_validation_rejects_caps_over_total() -> None:
    with pytest.raises(pydantic.ValidationError, match="exceed total"):
        BudgetConfig(total_usd=30.0, reserve_usd=1.8, chunk_caps={**CHUNK_CAPS, "NA-12": 1.0})
