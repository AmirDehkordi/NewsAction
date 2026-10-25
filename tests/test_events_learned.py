"""F5/F6 building blocks (PRD NA-03 S3): persistence, PCA, streamed embedding order, recall at budget."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from newsaction import calendar
from newsaction.events.learned import (
    LogReg,
    Pca,
    f6_feature_names,
    f6_frame,
    fit_logreg,
    fit_pca,
    make_prep,
    map_embeddings,
    recall_at_budget,
)
from newsaction.news import EMBEDDINGS
from newsaction.paths import Layout


def test_logreg_json_round_trip_and_fit() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(2000, 8)).astype(np.float32)
    y = (x[:, 0] + 0.1 * rng.normal(size=2000)) > 0
    m = fit_logreg(x, y, 1.0, 500)
    back = LogReg.from_json(json.loads(json.dumps(m.to_json())))
    assert np.array_equal(m.predict(x), back.predict(x))
    assert np.argmax(np.abs(m.coef)) == 0
    assert ((m.predict(x) > 0.5) == y).mean() > 0.9


def test_pca_recovers_the_dominant_axis_with_fixed_sign() -> None:
    rng = np.random.default_rng(2)
    x = rng.normal(size=(5000, 6)) * np.array([5.0, 1, 1, 1, 1, 0.5])
    p = fit_pca(x.astype(np.float32), 2, chunk=700)
    assert abs(p.components[0, 0]) > 0.99 and p.components[0, 0] > 0
    back = Pca.from_json(json.loads(json.dumps(p.to_json())))
    assert np.array_equal(p.transform(x), back.transform(x))


def test_f6_frame_columns_and_missing_categories() -> None:
    arts = pd.DataFrame(
        {
            "tag_type": ["ma_deal", "unknown_tag", None],
            "sentiment_intensity": ["Immediate", None, "Long-Term"],
            "source_class": ["other", "other", "major_outlet"],
            "tag_scheduled": [True, False, None],
            "tag_forward_looking": [False, False, True],
            "tag_primary_source": [True, True, True],
            "tag_quantified": [False, True, False],
            "tag_rumor": [False, False, False],
            "sentiment_direction": ["Positive", "Strongly Negative", "Neutral"],
            "novelty": [0.1, 0.2, 0.3],
        }
    )
    pca = Pca(np.zeros(4), np.eye(4)[:2])
    prep = make_prep(arts.iloc[:1], pca)
    f = f6_frame(arts, pca.transform(np.ones((3, 4))), np.array([1.0, np.nan, 3.0]), prep)
    assert tuple(f.columns) == f6_feature_names(2) == prep.features
    assert (
        f["tag_type"].tolist()[0] == 0 and np.isnan(f["tag_type"].iloc[1]) and np.isnan(f["tag_type"].iloc[2])
    )
    assert f["sentiment"].tolist() == [1.0, -2.0, 0.0]
    assert np.isnan(f["tag_scheduled"].iloc[2])


def test_map_embeddings_preserves_requested_order(tmp_layout: Layout) -> None:
    n, d = 1000, 4
    vecs = np.arange(n * d, dtype=np.float16).reshape(n, d) % 512
    path = tmp_layout.work / EMBEDDINGS
    path.parent.mkdir(parents=True)
    col = pa.FixedSizeListArray.from_arrays(pa.array(vecs.reshape(-1), type=pa.float16()), d)
    pq.write_table(pa.table({"id": [str(i) for i in range(n)], "embedding": col}), path, row_group_size=128)
    pos = np.array([999, 3, 500, 3, 128, 127, 0], dtype=np.int64)
    got = map_embeddings(pos, lambda x: x.astype(np.float32), layout=tmp_layout, batch_rows=100)
    assert np.array_equal(got, vecs[pos].astype(np.float32))


def test_recall_at_budget_uses_ticker_day_max() -> None:
    sess = calendar.sessions(date(2025, 4, 1), date(2025, 4, 30))[:10]
    td = pd.DataFrame({"company_id": list(range(10)), "session": sess, "material": [True] * 3 + [False] * 7})
    # two articles per day; the material days get one high-scoring article each
    rows = np.repeat(np.arange(10), 2)
    scores = np.array([0.9 if (r < 3 and i % 2) else 0.1 + 0.01 * r for i, r in enumerate(rows)])
    assert recall_at_budget(scores, rows, td, 0.3, 2026) == pytest.approx(1.0)
    # max, not mean: one high article on each of three non-material days takes the whole budget
    other = np.where((rows >= 7) & (np.arange(len(rows)) % 2 == 0), 0.95, 0.05)
    assert recall_at_budget(other, rows, td, 0.3, 2026) == 0.0
