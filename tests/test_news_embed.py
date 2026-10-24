"""PRD NA-02 S6 / AC7: embedding text, storage format, alignment; the real file (after the build)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from newsaction import io
from newsaction.news import ARTICLES, EMBEDDINGS, embed
from newsaction.paths import ROOT, Layout


def test_embed_text_joins_non_empty_parts() -> None:
    t = pd.Series(["Acme beats", "", None, "Title only"])
    s = pd.Series(["Revenue rose.", "Snippet only", None, ""])
    assert embed.embed_text(t, s).tolist() == ["Acme beats. Revenue rose.", "Snippet only", "", "Title only"]
    sha = embed.text_sha(embed.embed_text(t, s))
    assert sha.str.len().eq(16).all() and sha.iloc[0] != sha.iloc[1]


def test_storage_roundtrip_and_alignment() -> None:
    rng = np.random.default_rng(0)
    v = rng.normal(size=(3, 4)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    table = embed.to_table(pd.Series(["a", "b", "c"]), pd.Series(["1", "2", "3"]), v.astype(np.float16))
    assert table.schema.field("embedding").type == pa.list_(pa.float16(), 4)
    assert table.schema.metadata is None  # no pandas metadata: pandas can read the other columns back
    mat = embed._fixed_list_matrix(table.column("embedding"))
    e = embed.Embeddings(pd.Series(table.column("id").to_pylist()), pd.Series(["1", "2", "3"]), mat)
    assert e.matrix_for(pd.Series(["a", "b", "c"])) is mat  # same order: no copy
    np.testing.assert_array_equal(e.matrix_for(pd.Series(["c", "a"])), mat[[2, 0]])
    with pytest.raises(ValueError, match="no embedding"):
        e.matrix_for(pd.Series(["z"]))


def test_write_and_read_back(tmp_layout: Layout) -> None:
    v = np.eye(3, 4, dtype=np.float16)
    embed.write_embeddings(pd.Series(["a", "b", "c"]), pd.Series(["x", "y", "z"]), v, layout=tmp_layout)
    back = embed.read_embeddings(layout=tmp_layout)
    assert back.ids.tolist() == ["a", "b", "c"] and back.text_sha.tolist() == ["x", "y", "z"]
    np.testing.assert_array_equal(back.vecs, v)


def test_real_embeddings_ac7() -> None:
    """AC7: one row per kept article id; float16; L2 norm within 1 ± 1e-2."""
    if not (ROOT / "work" / EMBEDDINGS).is_file() or not (ROOT / "work" / ARTICLES).is_file():
        pytest.skip("work/news artifacts absent (run the NA-02 build)")
    emb = embed.read_embeddings()
    assert emb.vecs.dtype == np.float16 and emb.vecs.shape[1] == 384
    assert emb.ids.is_unique
    kept = io.read_parquet(ARTICLES, columns=["id", "keep"])
    kept_ids = kept.loc[kept["keep"], "id"]
    assert kept_ids.isin(set(emb.ids)).all()
    norms = np.linalg.norm(emb.vecs.astype(np.float32), axis=1)
    assert np.abs(norms - 1).max() <= 1e-2
