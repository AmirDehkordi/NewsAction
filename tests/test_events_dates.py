"""PRD NA-03 AC1: F5/F6 fit ≤ 2025-03-31 after purge, tuned ≤ 2025-06-30; the comparison uses val-A only."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar, io
from newsaction.events import DateWindow, load_events_config
from newsaction.events.learned import F5_META, F6_META, load_meta, window_ticker_days
from newsaction.events.select import CompareError, assert_val_a, compare
from newsaction.paths import ROOT

FIT_END, TUNE_START, TUNE_END = date(2025, 3, 31), date(2025, 4, 1), date(2025, 6, 30)


def _labels(start: date, end: date) -> pd.DataFrame:
    sess = calendar.sessions(start, end)
    hz = []
    for s in sess:
        e = s
        for _ in range(5):
            e = calendar.next_session(e)
        hz.append(e)
    return pd.DataFrame(
        {"session": sess, "horizon_end": hz, "label_ok": True, "company_id": 1, "material": False}
    )


def test_fit_window_is_purged_to_its_end() -> None:
    lab = _labels(date(2025, 3, 1), date(2025, 4, 30))
    fit = window_ticker_days(lab, load_events_config().learned.fit)
    assert max(fit["horizon_end"]) <= FIT_END
    assert max(fit["session"]) == date(2025, 3, 24)  # t+5 = 2025-03-31
    assert date(2025, 3, 25) not in set(fit["session"])
    tune = window_ticker_days(lab, load_events_config().learned.tune)
    assert min(tune["session"]) >= TUNE_START


def test_window_excludes_unlabelled_rows() -> None:
    lab = _labels(date(2025, 1, 2), date(2025, 1, 31))
    lab.loc[3, "label_ok"] = False
    got = window_ticker_days(lab, DateWindow(start=date(2025, 1, 1), end=date(2025, 2, 28)))
    assert len(got) == len(lab) - 1


@pytest.mark.parametrize("fid,meta", [("F5", F5_META), ("F6", F6_META)])
def test_stored_metadata_dates(fid: str, meta: str) -> None:
    if not (ROOT / "work" / meta).is_file():
        pytest.skip(f"{meta} not built")
    m = load_meta(fid)
    fit, tune = m["fit_range"], m["tune_range"]
    assert (fit["start"], fit["end"]) == ("2024-07-01", "2025-03-31")
    assert fit["min_session"] >= "2024-07-01"
    assert fit["max_session"] <= "2025-03-31" and fit["max_horizon_end"] <= "2025-03-31"
    assert tune["min_session"] >= "2025-04-01"
    assert tune["max_session"] <= "2025-06-30" and tune["max_horizon_end"] <= "2025-06-30"
    manifest = io.load_manifest()["artifacts"]
    for rel, sha in m["sha256"].items():
        assert manifest[f"work/{rel}"]["sha256"] == sha
        assert io.sha256_file(ROOT / "work" / rel) == sha


def test_assert_val_a() -> None:
    assert_val_a([date(2025, 7, 9), date(2025, 9, 30)])
    for bad in (date(2025, 6, 30), date(2025, 10, 1), date(2026, 1, 5)):
        with pytest.raises(CompareError):
            assert_val_a([date(2025, 7, 9), bad])


def _sample(sessions: list[date]) -> pd.DataFrame:
    n = len(sessions)
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "session": sessions,
            "company_id": np.arange(n),
            "tier": "mid",
            "material": rng.random(n) < 0.3,
            "delayed": rng.random(n) < 0.1,
            "material_on": False,
            "material_car": False,
            "material_vol": False,
            "z_cc": rng.normal(size=n),
            "tie_u": rng.random(n),
        }
    )
    for c in ("f0", "f1", "f2", "f3"):
        df[c] = (rng.random(n) < 0.5).astype(float)
    for c in ("f4", "f5", "f6"):
        df[c] = rng.random(n)
    return df


def test_compare_refuses_a_val_b_or_train_session() -> None:
    cfg = load_events_config().compare
    sess = calendar.sessions(date(2025, 7, 9), date(2025, 9, 30))
    compare(_sample(sess), cfg)  # val-A only: fine
    with pytest.raises(CompareError):
        compare(_sample([*sess, date(2025, 10, 1)]), cfg)
    with pytest.raises(CompareError):
        compare(_sample([date(2025, 6, 27), *sess]), cfg)


def test_run_compare_reads_only_val_a_rows() -> None:
    """run_compare restricts labels and ticker-days to val-A before anything else (source check)."""
    import inspect

    from newsaction.events import select

    src = inspect.getsource(select.run_compare)
    assert 'td.loc[td["split"] == VAL_A]' in src
    body = inspect.getsource(select.comparison_sample)
    assert 'labels["split"] == VAL_A' in body and body.count("assert_val_a(") == 2
