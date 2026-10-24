"""PRD NA-02 S7: near-duplicate groups (PREREG §6.2): window, threshold, no chaining, PIT."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from newsaction.news import dedupe

COS, WINDOW = 0.93, pd.Timedelta(hours=72)


def unit(*xs: float) -> np.ndarray:
    v = np.zeros(8, dtype=np.float32)
    v[: len(xs)] = xs
    return v / np.linalg.norm(v)


def frame(rows: list[tuple[str, int, str, date | None, date]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [r[0] for r in rows],
            "company_id": [r[1] for r in rows],
            "t_avail": pd.to_datetime([r[2] for r in rows], utc=True),
            "session_w0": [r[3] for r in rows],
            "session_w2": [r[4] for r in rows],
        }
    )


def groups(df: pd.DataFrame, vecs: np.ndarray, mask: np.ndarray | None = None) -> pd.DataFrame:
    m = np.ones(len(df), dtype=bool) if mask is None else mask
    return dedupe.near_duplicate_groups(df, vecs, mask=m, cosine=COS, window=WINDOW)


D1, D2, D3 = date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 14)


def test_duplicates_within_window_collapse_to_earliest() -> None:
    df = frame(
        [
            ("b", 1, "2025-03-10T12:00:00Z", D1, D1),
            ("a", 1, "2025-03-10T11:00:00Z", D1, D1),
            ("c", 1, "2025-03-10T15:00:00Z", None, D1),
            ("d", 1, "2025-03-14T12:00:00Z", D3, D3),  # 97 h after a: own group
            ("e", 2, "2025-03-10T12:30:00Z", D1, D1),  # other company
        ]
    )
    v = np.stack([unit(1, 0.01), unit(1), unit(1, 0.02), unit(1), unit(1)])
    g = groups(df, v)
    assert g["dup_group"].tolist() == ["a", "a", "a", "d", "e"]
    assert g["is_representative"].tolist() == [False, True, False, True, True]
    assert g["dup_count"].tolist() == [3, 3, 3, 1, 1]
    assert g["dup_count_w0"].tolist() == [2, 2, 2, 1, 1]  # c is after 09:15 ET
    assert g["dup_count_w2"].tolist() == [3, 3, 3, 1, 1]


def test_threshold_and_no_chaining() -> None:
    # b ~ a (cos >= 0.93); c ~ b but its similarity to a is below the threshold: c starts a group
    a, b = unit(1, 0), unit(1, 0.3)
    c = unit(1, 0.75)
    assert a @ b >= COS and b @ c >= COS and a @ c < COS
    df = frame(
        [
            ("a", 1, "2025-03-10T10:00:00Z", D1, D1),
            ("b", 1, "2025-03-10T11:00:00Z", D1, D1),
            ("c", 1, "2025-03-10T12:00:00Z", D1, D1),
        ]
    )
    g = groups(df, np.stack([a, b, c]))
    assert g["dup_group"].tolist() == ["a", "a", "c"]


def test_window_is_measured_to_the_representative() -> None:
    # b at +71 h joins a; c at +142 h is similar to both but a is out of window and b is not a representative
    df = frame(
        [
            ("a", 1, "2025-03-03T10:00:00Z", None, D1),
            ("b", 1, "2025-03-06T09:00:00Z", None, D1),
            ("c", 1, "2025-03-09T08:00:00Z", None, D2),
        ]
    )
    g = groups(df, np.stack([unit(1), unit(1), unit(1)]))
    assert g["dup_group"].tolist() == ["a", "a", "c"]


def test_equal_timestamps_order_by_id() -> None:
    df = frame([("z", 1, "2025-03-10T23:59:59Z", D2, D2), ("y", 1, "2025-03-10T23:59:59Z", D2, D2)])
    g = groups(df, np.stack([unit(1), unit(1)]))
    assert g["dup_group"].tolist() == ["y", "y"]
    assert g["is_representative"].tolist() == [False, True]


def test_masked_rows_get_no_group() -> None:
    df = frame([("a", 1, "2025-03-10T10:00:00Z", D1, D1), ("b", 1, "2025-03-10T11:00:00Z", D1, D1)])
    g = groups(df, np.stack([unit(1), unit(1)]), mask=np.array([False, True]))
    assert g["dup_group"].isna().tolist() == [True, False]
    assert g["is_representative"].tolist() == [False, True]


def test_groups_are_point_in_time() -> None:
    rng = np.random.default_rng(2026)
    n = 400
    t = pd.Timestamp("2025-01-01T00:00:00Z") + pd.to_timedelta(
        np.sort(rng.integers(0, 60 * 86400, n)), unit="s"
    )
    base = rng.normal(size=(20, 8))
    vecs = (base[rng.integers(0, 20, n)] + 0.1 * rng.normal(size=(n, 8))).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    df = pd.DataFrame(
        {
            "id": [f"{i:04d}" for i in range(n)],
            "company_id": rng.integers(0, 3, n),
            "t_avail": t,
            "session_w0": [None] * n,
            "session_w2": [D1] * n,
        }
    )
    full = groups(df, vecs)
    tau = t[n // 2]
    early = (df["t_avail"] <= tau).to_numpy()
    part = groups(df[early].reset_index(drop=True), vecs[early])
    assert full.loc[early, "dup_group"].tolist() == part["dup_group"].tolist()
    assert full.loc[early, "is_representative"].tolist() == part["is_representative"].tolist()
    assert full["is_representative"].sum() < n  # the fixture does contain duplicates
