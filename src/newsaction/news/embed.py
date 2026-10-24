"""PRD NA-02 S6: bge-small embeddings of title_clean + ". " + snippet_clean (``configs/news.yaml`` embed).

- Model ``BAAI/bge-small-en-v1.5`` at the pinned revision, sentence-transformers on MPS,
  ``normalize_embeddings=True``, computed in ``embed.compute_dtype`` (float16 on MPS) and stored as float16
  (fixed-size list of 384).
- ``work/news/embeddings_ts.parquet``: ``id``, ``text_sha`` (first 16 hex of sha256 of the embedded text),
  ``embedding``. A rebuild reuses every row whose (id, text_sha) is unchanged, so only new or re-scrubbed
  texts are embedded again.
- Runs locally; nothing leaves the machine. The model weights come from the Hugging Face cache.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from newsaction import io
from newsaction.news import EMBEDDINGS, EmbedConfig, load_news_config
from newsaction.paths import Layout, resolve_layout

PRODUCER: Final = "newsaction.news.embed (NA-02 S6)"


def embed_text(title_clean: pd.Series, snippet_clean: pd.Series) -> pd.Series:
    """The embedded text: non-empty parts of (title_clean, snippet_clean) joined by ". "."""
    t = title_clean.fillna("").astype("str").str.strip()
    s = snippet_clean.fillna("").astype("str").str.strip()
    both = (t != "") & (s != "")
    return (t + np.where(both, ". ", "") + s).astype("str")


def text_sha(texts: pd.Series) -> pd.Series:
    return texts.map(lambda x: hashlib.sha256(str(x).encode()).hexdigest()[:16]).astype("str")


def _model(cfg: EmbedConfig) -> Any:
    from sentence_transformers import SentenceTransformer  # optional "embed" extra

    model = SentenceTransformer(cfg.model, revision=cfg.revision, device=cfg.device)
    return model.half() if cfg.compute_dtype == "float16" else model


def encode(texts: list[str], cfg: EmbedConfig | None = None, *, model: Any = None) -> npt.NDArray[np.float16]:
    """Unit-norm embeddings (float16) of ``texts``, in input order."""
    cfg = cfg or load_news_config().embed
    m = model if model is not None else _model(cfg)
    if not texts:
        return np.zeros((0, cfg.dim), dtype=np.float16)
    vecs = m.encode(
        texts,
        batch_size=cfg.batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vecs, dtype=np.float32).astype(np.float16)


def to_table(ids: pd.Series, shas: pd.Series, vecs: npt.NDArray[np.float16]) -> pa.Table:
    """id, text_sha and a fixed-size list<float16> embedding column (no pandas metadata)."""
    dim = vecs.shape[1]
    arr = pa.FixedSizeListArray.from_arrays(pa.array(vecs.reshape(-1), type=pa.float16()), dim)
    return pa.table(
        {
            "id": pa.array(ids.astype("str").to_numpy(), type=pa.large_string()),
            "text_sha": pa.array(shas.astype("str").to_numpy(), type=pa.large_string()),
            "embedding": arr,
        }
    )


def write_embeddings(
    ids: pd.Series, shas: pd.Series, vecs: npt.NDArray[np.float16], *, layout: Layout | None = None
) -> dict[str, Any]:
    """Write EMBEDDINGS with pyarrow (atomically) and register it in the manifest.

    ``io.write_parquet`` goes through pandas, whose metadata for a fixed-size-list extension column cannot
    be read back by pandas; this file has no pandas metadata, so ``io.read_parquet`` of the other columns
    works.
    """
    lay = resolve_layout(layout)
    cfg = load_news_config().embed
    path = lay.work / EMBEDDINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        pq.write_table(to_table(ids, shas, vecs), tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return io.register_file(
        EMBEDDINGS,
        producer=PRODUCER,
        description=f"NA-02 S6: {cfg.model}@{cfg.revision} on title_clean + '. ' + snippet_clean, "
        f"normalized, computed in {cfg.compute_dtype} on {cfg.device}, stored float16; one row per member "
        "article id",
        layout=lay,
    )


@dataclass(frozen=True)
class Embeddings:
    """Rows of work/news/embeddings_ts.parquet: ids, text hashes and the (n, dim) float16 matrix."""

    ids: pd.Series
    text_sha: pd.Series
    vecs: npt.NDArray[np.float16]

    def matrix_for(self, ids: pd.Series) -> npt.NDArray[np.float16]:
        """float16 rows in the order of ``ids`` (no copy when the order already matches)."""
        want = ids.astype("str").to_numpy()
        have = self.ids.astype("str").to_numpy()
        if len(want) == len(have) and bool(np.array_equal(want, have)):
            return self.vecs
        pos = pd.Series(np.arange(len(have)), index=have)
        if pos.index.has_duplicates:
            raise ValueError("embeddings have duplicate ids")
        idx = pos.reindex(want)
        if bool(idx.isna().any()):
            raise ValueError(f"{int(idx.isna().sum())} article ids have no embedding")
        return np.asarray(self.vecs[idx.to_numpy(dtype=np.int64)], dtype=np.float16)


def _fixed_list_matrix(col: pa.ChunkedArray | pa.Array) -> npt.NDArray[np.float16]:
    arr = col.combine_chunks() if isinstance(col, pa.ChunkedArray) else col
    size = arr.type.list_size
    return np.asarray(arr.flatten().to_numpy(zero_copy_only=False), dtype=np.float16).reshape(-1, size)


def read_embeddings(*, layout: Layout | None = None) -> Embeddings:
    """EMBEDDINGS after the manifest hash check (``io.read_parquet``); the matrix is read with pyarrow."""
    lay = resolve_layout(layout)
    meta = io.read_parquet(EMBEDDINGS, columns=["id", "text_sha"], layout=lay)
    table = pq.read_table(lay.work / EMBEDDINGS, columns=["embedding"])
    vecs = _fixed_list_matrix(table.column("embedding"))
    if len(vecs) != len(meta):
        raise ValueError("embedding matrix and id column differ in length")
    return Embeddings(meta["id"].astype("str"), meta["text_sha"].astype("str"), vecs)


def embed_articles(arts: pd.DataFrame, *, layout: Layout | None = None, chunk: int = 50_000) -> Embeddings:
    """Embed every article (reusing unchanged rows of an existing file) and write EMBEDDINGS."""
    lay = resolve_layout(layout)
    cfg = load_news_config().embed
    texts = embed_text(arts["title_clean"], arts["snippet_clean"])
    want = pd.DataFrame({"id": arts["id"].astype("str").to_numpy(), "text_sha": text_sha(texts).to_numpy()})
    vecs = np.zeros((len(want), cfg.dim), dtype=np.float16)
    done = np.zeros(len(want), dtype=bool)
    if (lay.work / EMBEDDINGS).is_file():
        old = read_embeddings(layout=lay)
        prev = pd.DataFrame(
            {"id": old.ids.to_numpy(), "text_sha": old.text_sha.to_numpy(), "src": np.arange(len(old.ids))}
        )
        hit = want.reset_index().merge(prev, on=["id", "text_sha"])
        vecs[hit["index"].to_numpy()] = old.vecs[hit["src"].to_numpy()]
        done[hit["index"].to_numpy()] = True
    todo = np.flatnonzero(~done)
    print(f"embed: {len(want):,} texts, {int(done.sum()):,} reused, {len(todo):,} to encode", flush=True)
    if len(todo):
        model = _model(cfg)
        t0 = time.time()
        for start in range(0, len(todo), chunk):
            part = todo[start : start + chunk]
            vecs[part] = encode(texts.iloc[part].tolist(), cfg, model=model)
            rate = (start + len(part)) / max(time.time() - t0, 1e-9)
            print(f"embed: {start + len(part):,}/{len(todo):,} texts, {rate:,.0f}/s", flush=True)
        print(f"embed: {len(todo):,} texts in {time.time() - t0:,.0f}s on {cfg.device}", flush=True)
    write_embeddings(want["id"], want["text_sha"], vecs, layout=lay)
    return Embeddings(want["id"], want["text_sha"], vecs)
