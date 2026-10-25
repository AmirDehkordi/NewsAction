"""Learned filters F5 and F6: fit, tune, freeze, store and load (PREREG §6.6, §6.8; PRD NA-03 S3).

- **Sample.** Kept W0 articles of covered member company-days with a valid material label. The article
  inherits its ticker-day's label (PREREG §6.7), and the ticker-day score is the max over articles
  (``filters``).
- **Windows.** Fit on 2024-07-01 → 2025-03-31 and tune on 2025-04-01 → 2025-06-30 (``configs/events.yaml``).
  Each window is purged (§4.1): a ticker-day enters only if its label horizon (t+5) ends inside the
  window. So the fit labels end by 2025-03-31, the tune labels by 2025-06-30, and the two never overlap.
- **F5.** Standardized bge-small embedding → L2 logistic regression; grid over C.
- **F6.** LightGBM on the vendor tag, the five tag flags, sentiment (−2…2), intensity, source class,
  novelty, 16 principal components of the embedding (PCA fit on the fit window) and the W attention
  ratio; grid over leaves / min_child_samples / rounds.
- **Tuning.** Each grid point is fit on the fit window and scored on the tune window by the
  ticker-day material recall at the 30% budget (the protocol's target). Each point is logged in
  ``ledgers/trials.jsonl``. The best point (ties: first in grid order) is the frozen model; it is
  **not** refit on the tune window.

Stored under ``work/events/models/`` as JSON / LightGBM text (deterministic bytes, no pickle), each
with a ``*.meta.json`` holding {fit_range, tune_range, features, params, sha256}.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from newsaction import io
from newsaction.events import (
    COUNTS,
    LABELS,
    MODELS_DIR,
    PRODUCER,
    DateWindow,
    NA03Config,
    load_events_config,
)
from newsaction.events.filters import VENDOR_COLUMNS, budget_select, tie_u
from newsaction.events.trials import log_trial
from newsaction.news import ARTICLES, EMBEDDINGS, load_news_config
from newsaction.paths import Layout, resolve_layout

F5_MODEL: Final = f"{MODELS_DIR}/f5_logreg.model.json"
F5_META: Final = f"{MODELS_DIR}/f5_logreg.meta.json"
F6_MODEL: Final = f"{MODELS_DIR}/f6_lgbm.model.txt"
F6_PREP: Final = f"{MODELS_DIR}/f6_lgbm.prep.json"
F6_META: Final = f"{MODELS_DIR}/f6_lgbm.meta.json"
TUNE_METRIC: Final = "tune_material_recall_at_budget"

FLAGS: Final = ("tag_scheduled", "tag_forward_looking", "tag_primary_source", "tag_quantified", "tag_rumor")
CATEGORICAL: Final = ("tag_type", "sentiment_intensity", "source_class")
ARTICLE_COLUMNS: Final = (
    "id",
    "company_id",
    "t_avail",
    "session_w0",
    "session_w2",
    "keep",
    "novelty",
    *VENDOR_COLUMNS,
)

FloatArray = npt.NDArray[np.float64]


# --- articles and embeddings ----------------------------------------------------------------------


def load_kept_articles(layout: Layout | None = None) -> pd.DataFrame:
    """Kept articles with vendor fields, novelty and ``pos`` (their row in articles_clean / embeddings)."""
    lay = resolve_layout(layout)
    # io.read_parquet checks the file's sha256; the filtered pyarrow read below then reads the same file
    keep = io.read_parquet(ARTICLES, columns=["keep"], layout=lay)["keep"].to_numpy(dtype=bool)
    cols = [c for c in ARTICLE_COLUMNS if c != "keep"]
    table = pq.read_table(lay.work / ARTICLES, columns=cols, filters=[("keep", "==", True)])
    a: pd.DataFrame = table.to_pandas()
    if len(a) != int(keep.sum()):
        raise ValueError("filtered read of kept articles differs from the keep column")
    a["pos"] = np.flatnonzero(keep).astype(np.int64)
    a["company_id"] = a["company_id"].astype("int64")
    return a


def check_embedding_alignment(arts: pd.DataFrame, layout: Layout | None = None) -> None:
    """Embeddings rows are in articles_clean order (both sorted by t_avail, id); verify for ``arts``."""
    ids = io.read_parquet(EMBEDDINGS, columns=["id"], layout=layout)["id"].astype("str").to_numpy()
    got = ids[arts["pos"].to_numpy()]
    if not np.array_equal(got, arts["id"].astype("str").to_numpy()):
        raise ValueError("embeddings_ts rows are not aligned with articles_clean rows")


def _fixed_list(col: pa.ChunkedArray | pa.Array) -> npt.NDArray[np.float16]:
    arr = col.combine_chunks() if isinstance(col, pa.ChunkedArray) else col
    return np.asarray(arr.flatten().to_numpy(zero_copy_only=False), dtype=np.float16).reshape(
        -1, arr.type.list_size
    )


def map_embeddings(
    positions: npt.NDArray[np.int64],
    fn: Callable[[npt.NDArray[np.float16]], npt.NDArray[Any]],
    *,
    layout: Layout | None = None,
    batch_rows: int = 131_072,
) -> npt.NDArray[Any]:
    """``fn`` applied to the embedding rows at ``positions``, streamed batch by batch (bounded memory).

    Returns the stacked outputs in the order of ``positions``. Call ``check_embedding_alignment`` (or
    ``io.read_parquet`` of the file) first: this reader streams the registered file directly.
    """
    lay = resolve_layout(layout)
    order = np.argsort(positions, kind="stable")
    sp = positions[order]
    parts: list[npt.NDArray[Any]] = []
    offset, j = 0, 0
    for batch in pq.ParquetFile(lay.work / EMBEDDINGS).iter_batches(
        batch_size=batch_rows, columns=["embedding"]
    ):
        n = batch.num_rows
        hi = int(np.searchsorted(sp, offset + n, side="left"))
        if hi > j:
            parts.append(fn(_fixed_list(batch.column(0))[sp[j:hi] - offset]))
        j, offset = hi, offset + n
    if j != len(sp):
        raise ValueError("positions beyond the embeddings file")
    stacked = np.concatenate(parts) if parts else np.empty((0,))
    out = np.empty_like(stacked)
    out[order] = stacked
    return out


# --- models ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Pca:
    mean: FloatArray
    components: FloatArray  # (k, d)

    def transform(self, x: npt.NDArray[Any]) -> npt.NDArray[np.float32]:
        return np.asarray((x.astype(np.float64) - self.mean) @ self.components.T, dtype=np.float32)

    def to_json(self) -> dict[str, Any]:
        return {"mean": self.mean.tolist(), "components": self.components.tolist()}

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Pca:
        return cls(np.asarray(d["mean"], dtype=np.float64), np.asarray(d["components"], dtype=np.float64))


def fit_pca(x: npt.NDArray[Any], k: int, chunk: int = 65_536) -> Pca:
    """Top-k principal axes of ``x`` (eigendecomposition of the covariance; deterministic signs)."""
    n, d = x.shape
    mean = np.zeros(d)
    for s in range(0, n, chunk):
        mean += x[s : s + chunk].astype(np.float64).sum(axis=0)
    mean /= n
    cov = np.zeros((d, d))
    for s in range(0, n, chunk):
        c = x[s : s + chunk].astype(np.float64) - mean
        cov += c.T @ c
    cov /= max(n - 1, 1)
    vals, vecs = np.linalg.eigh(cov)
    top = vecs[:, np.argsort(vals)[::-1][:k]].T
    signs = np.sign(top[np.arange(k), np.abs(top).argmax(axis=1)])
    return Pca(mean, top * signs[:, None])


@dataclass(frozen=True)
class LogReg:
    """F5: p = σ(((x − mean) / scale) · coef + intercept)."""

    mean: FloatArray
    scale: FloatArray
    coef: FloatArray
    intercept: float

    def predict(self, x: npt.NDArray[Any]) -> FloatArray:
        z = ((x.astype(np.float64) - self.mean) / self.scale) @ self.coef + self.intercept
        return np.asarray(1.0 / (1.0 + np.exp(-z)), dtype=np.float64)

    def to_json(self) -> dict[str, Any]:
        return {
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "coef": self.coef.tolist(),
            "intercept": self.intercept,
        }

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> LogReg:
        return cls(
            np.asarray(d["mean"], dtype=np.float64),
            np.asarray(d["scale"], dtype=np.float64),
            np.asarray(d["coef"], dtype=np.float64),
            float(d["intercept"]),
        )


def fit_logreg(x: npt.NDArray[Any], y: npt.NDArray[np.bool_], c: float, max_iter: int) -> LogReg:
    from sklearn.linear_model import LogisticRegression

    xf = x.astype(np.float64)
    mean = xf.mean(axis=0)
    scale = xf.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    xf -= mean
    xf /= scale
    m = LogisticRegression(C=c, max_iter=max_iter, solver="lbfgs")
    m.fit(xf, y.astype(np.int64))
    return LogReg(mean, scale, np.asarray(m.coef_[0], dtype=np.float64), float(m.intercept_[0]))


@dataclass(frozen=True)
class F6Prep:
    """Everything F6 needs besides the booster: feature order, category vocabularies, PCA."""

    features: tuple[str, ...]
    vocab: dict[str, tuple[str, ...]]
    sentiment_scale: dict[str, int]
    pca: Pca

    def to_json(self) -> dict[str, Any]:
        return {
            "features": list(self.features),
            "vocab": {k: list(v) for k, v in self.vocab.items()},
            "sentiment_scale": dict(self.sentiment_scale),
            "pca": self.pca.to_json(),
        }

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> F6Prep:
        return cls(
            tuple(d["features"]),
            {k: tuple(v) for k, v in d["vocab"].items()},
            {k: int(v) for k, v in d["sentiment_scale"].items()},
            Pca.from_json(d["pca"]),
        )


def f6_feature_names(k: int) -> tuple[str, ...]:
    return (
        *CATEGORICAL,
        *FLAGS,
        "sentiment",
        "novelty",
        *(f"pc{i + 1}" for i in range(k)),
        "attention_ratio",
    )


def make_prep(arts: pd.DataFrame, pca: Pca) -> F6Prep:
    vocab = {c: tuple(sorted(str(v) for v in arts[c].dropna().unique())) for c in CATEGORICAL}
    return F6Prep(
        f6_feature_names(pca.components.shape[0]), vocab, dict(load_news_config().sentiment_scale), pca
    )


def f6_frame(
    arts: pd.DataFrame, pcs: npt.NDArray[Any], attention_ratio: npt.NDArray[Any], prep: F6Prep
) -> pd.DataFrame:
    """The F6 feature matrix (float64; categories as codes, unknown or missing → NaN)."""
    out: dict[str, Any] = {}
    for c in CATEGORICAL:
        codes = {v: float(i) for i, v in enumerate(prep.vocab[c])}
        out[c] = arts[c].map(codes).to_numpy(dtype=np.float64, na_value=np.nan)
    for c in FLAGS:
        out[c] = arts[c].astype("boolean").to_numpy(dtype=np.float64, na_value=np.nan)
    out["sentiment"] = arts["sentiment_direction"].map(prep.sentiment_scale).to_numpy(dtype=np.float64)
    out["novelty"] = arts["novelty"].to_numpy(dtype=np.float64)
    for i in range(pcs.shape[1]):
        out[f"pc{i + 1}"] = np.asarray(pcs[:, i], dtype=np.float64)
    out["attention_ratio"] = np.asarray(attention_ratio, dtype=np.float64)
    frame = pd.DataFrame(out)
    return frame[list(prep.features)]


def lgb_params(fixed: Mapping[str, float | int], point: Mapping[str, int], seed: int) -> dict[str, Any]:
    return {
        "objective": "binary",
        "verbosity": -1,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        **fixed,
        **{k: v for k, v in point.items() if k != "n_estimators"},
    }


def fit_lgbm(frame: pd.DataFrame, y: npt.NDArray[np.bool_], params: Mapping[str, Any], rounds: int) -> Any:
    import lightgbm as lgb

    ds = lgb.Dataset(
        frame, label=y.astype(np.int64), categorical_feature=list(CATEGORICAL), free_raw_data=True
    )
    return lgb.train(dict(params), ds, num_boost_round=rounds)


def load_booster(text: str) -> Any:
    import lightgbm as lgb

    return lgb.Booster(model_str=text)


# --- windows and the tuning metric ----------------------------------------------------------------


def window_ticker_days(labels: pd.DataFrame, window: DateWindow) -> pd.DataFrame:
    """Labelled covered member-days of ``window`` whose label horizon ends inside it (purge, §4.1)."""
    s = pd.to_datetime(labels["session"]).dt.date
    h = pd.to_datetime(labels["horizon_end"]).dt.date
    ok = labels["label_ok"].astype(bool) & (s >= window.start) & (s <= window.end) & (h <= window.end)
    return labels.loc[ok.to_numpy()].reset_index(drop=True)


def attach_w0(arts: pd.DataFrame, td: pd.DataFrame) -> pd.DataFrame:
    """Kept W0 articles of the ticker-days in ``td``, with ``td_row`` (their ticker-day) and ``y``."""
    key = td[["company_id", "session"]].assign(
        td_row=np.arange(len(td)), y=td["material"].astype(bool).to_numpy()
    )
    a = arts.loc[arts["session_w0"].notna()].merge(
        key, left_on=["company_id", "session_w0"], right_on=["company_id", "session"], how="inner"
    )
    return a.drop(columns=["session"]).sort_values("pos", kind="mergesort").reset_index(drop=True)


def recall_at_budget(
    art_scores: npt.NDArray[np.float64],
    td_row: npt.NDArray[np.int64],
    td: pd.DataFrame,
    budget: float,
    seed: int,
) -> float:
    """Ticker-day material recall when the top ``budget`` share of ``td`` is selected by max score."""
    n = len(td)
    best = np.full(n, -np.inf)
    np.maximum.at(best, td_row, art_scores)
    ok = np.isfinite(best)
    u = tie_u(td["company_id"], td["session"], seed)
    sel = budget_select(best, ok, u, math.floor(budget * n)).mask
    mat = td["material"].astype(bool).to_numpy()
    return int((sel & mat).sum()) / max(int(mat.sum()), 1)


def attention_for(arts: pd.DataFrame, counts: pd.DataFrame, window: str) -> npt.NDArray[np.float64]:
    """The ticker-day attention ratio of window ``W0`` / ``W2`` for each article (NaN when unknown)."""
    sfx = window.lower()
    col = f"session_{sfx}"
    c = counts[["company_id", "session", f"attention_ratio_{sfx}"]].rename(columns={"session": col})
    m = arts[["company_id", col]].merge(c, on=["company_id", col], how="left")
    return m[f"attention_ratio_{sfx}"].to_numpy(dtype=np.float64)


# --- persistence ----------------------------------------------------------------------------------


def _write_json(rel: str, payload: Mapping[str, Any], description: str, layout: Layout | None) -> str:
    lay = resolve_layout(layout)
    path = lay.work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(path, (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode())
    return str(
        io.register_file(rel, producer=PRODUCER, description=description, inspect_parquet=False, layout=lay)[
            "sha256"
        ]
    )


def _write_text(rel: str, text: str, description: str, layout: Layout | None) -> str:
    lay = resolve_layout(layout)
    path = lay.work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(path, text.encode())
    return str(
        io.register_file(rel, producer=PRODUCER, description=description, inspect_parquet=False, layout=lay)[
            "sha256"
        ]
    )


def _read_registered(rel: str, layout: Layout | None) -> bytes:
    """Bytes of a registered work/ file after the manifest sha256 check."""
    lay = resolve_layout(layout)
    path = lay.work / rel
    entry = io.load_manifest(lay)["artifacts"].get(lay.rel(path))
    if entry is None:
        raise io.ManifestError(f"{rel} is not registered")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise io.ManifestError(f"{rel}: sha256 differs from the manifest")
    return data


def load_f5(layout: Layout | None = None) -> LogReg:
    return LogReg.from_json(json.loads(_read_registered(F5_MODEL, layout)))


def load_f6(layout: Layout | None = None) -> tuple[Any, F6Prep]:
    booster = load_booster(_read_registered(F6_MODEL, layout).decode())
    prep = F6Prep.from_json(json.loads(_read_registered(F6_PREP, layout)))
    return booster, prep


def load_meta(fid: str, layout: Layout | None = None) -> dict[str, Any]:
    rel = F5_META if fid == "F5" else F6_META
    out: dict[str, Any] = json.loads(_read_registered(rel, layout))
    return out


def _range_meta(td: pd.DataFrame, window: DateWindow) -> dict[str, Any]:
    s = pd.to_datetime(td["session"]).dt.date
    h = pd.to_datetime(td["horizon_end"]).dt.date
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "min_session": min(s).isoformat(),
        "max_session": max(s).isoformat(),
        "max_horizon_end": max(h).isoformat(),
        "ticker_days": len(td),
        "material_ticker_days": int(td["material"].astype(bool).sum()),
    }


def _grid(grid: Mapping[str, tuple[Any, ...]]) -> list[dict[str, Any]]:
    keys = list(grid)
    return [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*(grid[k] for k in keys))]


# --- the fit stage --------------------------------------------------------------------------------


def run_fit(layout: Layout | None = None, cfg: NA03Config | None = None) -> dict[str, Any]:
    """Fit, tune and freeze F5 and F6; write the model files and their metadata."""
    cfg = load_events_config() if cfg is None else cfg
    lc = cfg.learned
    budget = cfg.compare.budget_share
    labels = io.read_parquet(LABELS, layout=layout)
    fit_td, tune_td = window_ticker_days(labels, lc.fit), window_ticker_days(labels, lc.tune)
    if max(pd.to_datetime(fit_td["horizon_end"]).dt.date) > lc.fit.end:
        raise ValueError("fit labels end after the fit window")
    if max(pd.to_datetime(tune_td["horizon_end"]).dt.date) > lc.tune.end:
        raise ValueError("tune labels end after the tune window")
    arts = load_kept_articles(layout)
    check_embedding_alignment(arts, layout)
    counts = io.read_parquet(COUNTS, layout=layout)
    fit_a, tune_a = attach_w0(arts, fit_td), attach_w0(arts, tune_td)
    n_fit, n_tune = f"{len(fit_td):,} / {len(fit_a):,}", f"{len(tune_td):,} / {len(tune_a):,}"
    print(f"ticker-days / articles: fit {n_fit}, tune {n_tune}", flush=True)

    def as32(x: npt.NDArray[np.float16]) -> npt.NDArray[np.float32]:
        return x.astype(np.float32)

    x_fit = map_embeddings(fit_a["pos"].to_numpy(), as32, layout=layout)
    x_tune = map_embeddings(tune_a["pos"].to_numpy(), as32, layout=layout)
    y_fit = fit_a["y"].to_numpy(bool)
    tune_rows = tune_a["td_row"].to_numpy(np.int64)
    common = {
        "fit_range": _range_meta(fit_td, lc.fit),
        "tune_range": _range_meta(tune_td, lc.tune),
        "fit_articles": len(fit_a),
        "tune_articles": len(tune_a),
        "label": "material ticker-day (PREREG §6.7) of the article's W0 ticker-day",
        "tuning_metric": f"{TUNE_METRIC} (budget {budget}, ticker-day max score, tie seed {lc.seed})",
        "seed": lc.seed,
        "embedding": f"{load_news_config().embed.model}@{load_news_config().embed.revision}",
        "events_config_sha256": io.sha256_file(resolve_layout(layout).configs / "events.yaml"),
    }

    # F5
    f5_grid = []
    best5: tuple[float, dict[str, Any], LogReg] | None = None
    for point in _grid(lc.f5.grid):
        model = fit_logreg(x_fit, y_fit, float(point["C"]), lc.f5.max_iter)
        r = recall_at_budget(model.predict(x_tune), tune_rows, tune_td, budget, lc.seed)
        params = {"filter": "F5", **point, "max_iter": lc.f5.max_iter}
        log_trial("filter_hparam", f"F5 {point}", params, "train", TUNE_METRIC, r, layout=layout)
        f5_grid.append({"params": point, TUNE_METRIC: r})
        print(f"F5 {point}: tune recall {r:.4f}", flush=True)
        if best5 is None or r > best5[0]:
            best5 = (r, point, model)
    assert best5 is not None
    sha5 = _write_json(
        F5_MODEL,
        best5[2].to_json(),
        "NA-03 S3: frozen F5 logistic regression (mean, scale, coef, intercept)",
        layout,
    )
    meta5 = {
        **common,
        "filter": "F5",
        "model_file": F5_MODEL,
        "features": "bge-small embedding of title_clean + '. ' + snippet_clean (384), standardized",
        "params": {**best5[1], "max_iter": lc.f5.max_iter, "penalty": "l2", "solver": "lbfgs"},
        "grid": f5_grid,
        "sha256": {F5_MODEL: sha5},
    }
    _write_json(
        F5_META, meta5, "NA-03 S3: F5 fit metadata {fit_range, tune_range, features, params, sha256}", layout
    )
    del x_tune

    # F6
    pca = fit_pca(x_fit, cfg.filters.pca_components)
    p_fit = pca.transform(x_fit)
    del x_fit
    p_tune = map_embeddings(tune_a["pos"].to_numpy(), pca.transform, layout=layout)
    prep = make_prep(fit_a, pca)
    f_fit = f6_frame(fit_a, p_fit, attention_for(fit_a, counts, "W0"), prep)
    f_tune = f6_frame(tune_a, p_tune, attention_for(tune_a, counts, "W0"), prep)
    f6_grid = []
    best6: tuple[float, dict[str, Any], Any] | None = None
    for point in _grid(lc.f6.grid):
        params = lgb_params(lc.f6.fixed, point, lc.seed)
        booster = fit_lgbm(f_fit, y_fit, params, int(point["n_estimators"]))
        r = recall_at_budget(
            np.asarray(booster.predict(f_tune), dtype=np.float64), tune_rows, tune_td, budget, lc.seed
        )
        log_trial(
            "filter_hparam",
            f"F6 {point}",
            {"filter": "F6", **params, "n_estimators": point["n_estimators"]},
            "train",
            TUNE_METRIC,
            r,
            layout=layout,
        )
        f6_grid.append({"params": point, TUNE_METRIC: r})
        print(f"F6 {point}: tune recall {r:.4f}", flush=True)
        if best6 is None or r > best6[0]:
            best6 = (r, point, booster)
    assert best6 is not None
    sha6 = _write_text(
        F6_MODEL, best6[2].model_to_string(), "NA-03 S3: frozen F6 LightGBM booster (text)", layout
    )
    sha6p = _write_json(
        F6_PREP,
        prep.to_json(),
        "NA-03 S3: F6 feature order, category vocabularies and PCA (fit window)",
        layout,
    )
    meta6 = {
        **common,
        "filter": "F6",
        "model_file": F6_MODEL,
        "prep_file": F6_PREP,
        "features": list(prep.features),
        "categorical": list(CATEGORICAL),
        "params": {**lgb_params(lc.f6.fixed, best6[1], lc.seed), "n_estimators": best6[1]["n_estimators"]},
        "grid": f6_grid,
        "pca": {"components": cfg.filters.pca_components, "fit_on": "fit-window articles"},
        "sha256": {F6_MODEL: sha6, F6_PREP: sha6p},
    }
    _write_json(
        F6_META, meta6, "NA-03 S3: F6 fit metadata {fit_range, tune_range, features, params, sha256}", layout
    )
    return {"F5": meta5, "F6": meta6}
