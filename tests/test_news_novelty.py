"""PRD NA-02 AC4: PIT novelty (PREREG §6.5).

- Deletion invariance: dropping every article with t_avail > τ (τ = 2025-06-15) leaves novelty unchanged for
  every article with t_avail ≤ τ (synthetic and, after the build, real articles of 20 companies).
- Verifier mutation: ``side="left"`` -> ``"right"`` for ``hi`` in ``novelty.scan`` (<= instead of <):
  test_strictly_earlier RED (a representative would see itself: novelty 0).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import io
from newsaction.news import ARTICLES, EMBEDDINGS, dedupe, embed, load_news_config, novelty
from newsaction.paths import ROOT

TAU = pd.Timestamp("2025-06-15T23:59:59Z")
WINDOW = pd.Timedelta(days=7)


def unit(*xs: float) -> np.ndarray:
    v = np.zeros(8, dtype=np.float32)
    v[: len(xs)] = xs
    return v / np.linalg.norm(v)


def run(df: pd.DataFrame, vecs: np.ndarray) -> pd.DataFrame:
    mask = np.ones(len(df), dtype=bool)
    out = df.copy()
    g = dedupe.near_duplicate_groups(out, vecs, mask=mask, cosine=0.93, window=pd.Timedelta(hours=72))
    out["is_representative"] = g["is_representative"].to_numpy()
    out["dup_group"] = g["dup_group"].to_numpy()
    out["novelty"] = novelty.pit_novelty(out, vecs, mask=mask, window=WINDOW).to_numpy()
    return out


def frame(stamps: list[str], company: int = 1) -> pd.DataFrame:
    n = len(stamps)
    return pd.DataFrame(
        {
            "id": [f"a{i}" for i in range(n)],
            "company_id": [company] * n,
            "t_avail": pd.to_datetime(stamps, utc=True),
            "session_w0": [None] * n,
            "session_w2": [date(2025, 3, 10)] * n,
        }
    )


def test_strictly_earlier() -> None:
    """First article 1.0; a repeat sees the earlier representative; equal stamps do not see each other."""
    df = frame(
        ["2025-03-03T10:00:00Z", "2025-03-04T10:00:00Z", "2025-03-05T10:00:00Z", "2025-03-05T10:00:00Z"]
    )
    vecs = np.stack([unit(1), unit(1), unit(0, 1), unit(0, 0, 1)])
    out = run(df, vecs)
    assert out["is_representative"].tolist() == [True, False, True, True]
    assert out["novelty"].tolist() == pytest.approx([1.0, 0.0, 1.0, 1.0])


def test_window_is_seven_days_and_compares_with_representatives_only() -> None:
    df = frame(
        ["2025-03-01T10:00:00Z", "2025-03-01T11:00:00Z", "2025-03-08T10:00:00Z", "2025-03-08T10:00:01Z"]
    )
    a, b = unit(1, 0), unit(1, 0.2)  # b duplicates a
    c = unit(0.6, 0.8)
    out = run(df, np.stack([a, b, c, c]))
    # row 2 is exactly 7 days after row 0 (in the window); row 3 is 1 s later (row 0 is out, row 2 is in)
    assert out["novelty"].iloc[2] == pytest.approx(1 - float(a @ c), abs=1e-6)
    assert out["novelty"].iloc[3] == pytest.approx(0.0, abs=1e-6)
    # b is not a representative: c's novelty is measured against a only
    assert out["novelty"].iloc[2] != pytest.approx(1 - float(b @ c), abs=1e-4)


def test_other_companies_are_ignored() -> None:
    df = pd.concat(
        [frame(["2025-03-03T10:00:00Z"], 1), frame(["2025-03-03T11:00:00Z"], 2)], ignore_index=True
    )
    df["id"] = ["x", "y"]
    out = run(df, np.stack([unit(1), unit(1)]))
    assert out["novelty"].tolist() == [1.0, 1.0]


def test_deletion_invariance_synthetic() -> None:
    rng = np.random.default_rng(2026)
    n = 600
    secs = np.sort(rng.integers(0, 120 * 86400, n))
    t = pd.Timestamp("2025-04-01T00:00:00Z") + pd.to_timedelta(secs, unit="s")
    base = rng.normal(size=(30, 8))
    vecs = (base[rng.integers(0, 30, n)] + 0.15 * rng.normal(size=(n, 8))).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    df = pd.DataFrame(
        {
            "id": [f"{i:04d}" for i in range(n)],
            "company_id": rng.integers(0, 4, n),
            "t_avail": t,
            "session_w0": [None] * n,
            "session_w2": [date(2025, 6, 2)] * n,
        }
    )
    full = run(df, vecs)
    early = (df["t_avail"] <= TAU).to_numpy()
    assert 0 < early.sum() < n
    part = run(df[early].reset_index(drop=True), vecs[early])
    np.testing.assert_array_equal(full.loc[early, "novelty"].to_numpy(), part["novelty"].to_numpy())
    assert full.loc[early, "dup_group"].tolist() == part["dup_group"].tolist()


def test_deletion_invariance_real_articles() -> None:
    """AC4 on the build: 20 random companies (seed 2026), τ = 2025-06-15."""
    if not (ROOT / "work" / ARTICLES).is_file() or not (ROOT / "work" / EMBEDDINGS).is_file():
        pytest.skip("work/news artifacts absent (run the NA-02 build)")
    cols = [
        "id",
        "company_id",
        "t_avail",
        "session_w0",
        "session_w2",
        "keep",
        "is_representative",
        "novelty",
        "dup_group",
        "non_news",
        "junk_tag",
        "is_13f",
        "is_form4",
        "has_clean_text",
    ]
    arts = io.read_parquet(ARTICLES, columns=cols)
    usable = ~arts[["non_news", "junk_tag", "is_13f", "is_form4"]].any(axis=1) & arts["has_clean_text"]
    arts = arts[usable]
    rng = np.random.default_rng(2026)
    picks = rng.choice(np.sort(arts["company_id"].unique()), 20, replace=False)
    sub = arts[arts["company_id"].isin(picks)].reset_index(drop=True)
    vecs = embed.read_embeddings().matrix_for(sub["id"])
    cfg = load_news_config()

    def recompute(df: pd.DataFrame, v: np.ndarray) -> pd.DataFrame:
        mask = np.ones(len(df), dtype=bool)
        out = df[["id", "company_id", "t_avail", "session_w0", "session_w2"]].copy()
        g = dedupe.near_duplicate_groups(
            out, v, mask=mask, cosine=cfg.dedupe.cosine, window=pd.Timedelta(hours=cfg.dedupe.window_hours)
        )
        out["is_representative"] = g["is_representative"].to_numpy()
        out["dup_group"] = g["dup_group"].to_numpy()
        out["novelty"] = novelty.pit_novelty(
            out, v, mask=mask, window=pd.Timedelta(days=cfg.novelty.window_days)
        )
        return out

    full = recompute(sub, vecs)
    # the recomputation on the subset equals the build (dedupe and novelty are per company)
    np.testing.assert_allclose(full["novelty"].to_numpy(), sub["novelty"].to_numpy(), atol=1e-6)
    early = (sub["t_avail"] <= TAU).to_numpy()
    part = recompute(sub[early].reset_index(drop=True), vecs[early])
    np.testing.assert_array_equal(full.loc[early, "novelty"].to_numpy(), part["novelty"].to_numpy())
    assert full.loc[early, "dup_group"].tolist() == part["dup_group"].tolist()
