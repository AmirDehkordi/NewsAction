"""Event frames shared by the fitted baselines (PRD NA-09 S2–S5).

- **Events.** The D0 baselines predict every event with a Call A D0 state (``state_files.call_a``), the D2
  price-only model every event with a Call B state (``state_files.call_b``), so every baseline answers on
  the same events as the decision models (PRD AC2).
- **The state's articles** (``state_articles``). A D0 state carries the first ``n_articles`` of its event's
  listed W0 articles (``events_d0.news_w0``, by rank) that NA-04 did not leave out (move explainers,
  TradingView reposts, non-English articles, running market stories) and that kept any text after masking;
  ``states.build.fit_news`` drops articles only from the end. The ids are rebuilt that way and checked
  against every state: article i's masked headline and snippet equal the state's news item i (the first
  item may be cut by words). The news baselines read the articles a decision model reads, no more.
- **Inputs** (``check_inputs``): every source column is checked with the availability registry
  (``pit``) at its decision point: D0 for the news baselines and price-only D0, D2 for price-only D2. Vendor
  fields are ``selection_only`` (CLAUDE.md A6); PREREG §10.1 and §10.3 pre-register them as baseline
  signals (PRD NA-09: produced live, day by day), so ``vendor=True`` admits exactly ``VENDOR_SIGNALS`` and
  nothing else of that kind.
- **Targets** (``post``) come from ``panel_public`` (purged within each split, PREREG §4.1): e5, z_cc,
  |z_cc| at D0 and y2 at D2. Test sessions have no row there, so no 2026 target is ever joined.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction import calendar, io, pit
from newsaction.baselines import BaselineError, BaselinesConfig, baselines_config
from newsaction.events import EVENTS_D0
from newsaction.news import ARTICLES
from newsaction.paths import Layout, resolve_layout
from newsaction.states import CONTEXT_COMPANY
from newsaction.states.build import REACTION_D2

PANEL: Final = "panel/panel_public.parquet"
STATE_ARTICLES: Final = "baselines/state_articles.parquet"

VENDOR_SIGNALS: Final = frozenset(
    {
        "sentiment_direction",
        "sentiment_intensity",
        "tag_type",
        "tag_scheduled",
        "tag_forward_looking",
        "tag_primary_source",
        "tag_quantified",
        "tag_rumor",
    }
)
TAG_TYPES: Final = (
    "earnings_results",
    "guidance_outlook",
    "analyst_action",
    "ma_deal",
    "legal_regulatory",
    "financing_dilution",
    "capital_returns",
    "leadership_governance",
    "operations_supply",
    "partnership_customer",
    "product_launch",
    "competition",
    "insider_ownership",
    "macro_sector",
    "other_corporate",
)
FLAGS: Final = ("tag_scheduled", "tag_forward_looking", "tag_primary_source", "tag_quantified", "tag_rumor")
INTENSITIES: Final = ("Immediate", "Short-Term", "Medium-Term", "Long-Term")
SOURCE_CLASSES: Final = (
    "press_wire_primary",
    "major_outlet",
    "retail_analysis",
    "aggregator",
    "auto_generated",
    "other",
)
ATTENTION: Final = ("n_articles_w0", "n_stories_w0", "n_dup_w0", "attention_ratio_w0", "attention_mean_w0")
EVENT_KEYS: Final = ("event_id", "company_id", "symbol_id", "session", "split", "tier", "month", "embargo")
ARTICLE_COLUMNS: Final = (
    "id",
    "sentiment_direction",
    "sentiment_intensity",
    "tag_type",
    *FLAGS,
    "source_class_domain",
    "novelty",
    "dup_count_w0",
)
Point = Literal["D0", "D2"]


def check_inputs(columns: Iterable[str], point: Point, *, vendor: bool = False) -> None:
    """``pit.check_inputs`` at ``point``; with ``vendor`` the pre-registered vendor signals pass too."""
    cols = list(columns)
    reg = pit.default_registry()
    allowed = {c for c in cols if vendor and c in VENDOR_SIGNALS and reg.kind(c) == "selection_only"}
    pit.check_inputs([c for c in cols if c not in allowed], point, reg)


# --- events -------------------------------------------------------------------------------------------


def state_rows(cfg: BaselinesConfig, call: str, layout: Layout | None = None) -> pd.DataFrame:
    rel = cfg.state_files.call_a if call == "A" else cfg.state_files.call_b
    cols = ["event_id", "company_id", "session", "split", "n_articles", "state_json"]
    return io.read_parquet(rel, columns=cols, layout=layout)


def d0_events(cfg: BaselinesConfig, layout: Layout | None = None, *, with_news: bool = False) -> pd.DataFrame:
    """Every event with a Call A D0 state: the keys, the W0 attention block and (``with_news``) the listed
    articles and the state JSON."""
    lay = resolve_layout(layout)
    states = state_rows(cfg, "A", lay)
    cols = ["event_id", "symbol_id", "tier", "month", "embargo", *ATTENTION]
    cols += ["news_w0"] if with_news else []
    ev = io.read_parquet(EVENTS_D0, columns=cols, layout=lay)
    out = states.merge(ev, on="event_id", how="left", validate="one_to_one")
    if bool(out["symbol_id"].isna().any()):
        raise BaselineError("a Call A state has no D0 event")
    if not with_news:
        out = out.drop(columns=["state_json"])
    return out.sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


# --- the state's articles ---------------------------------------------------------------------------------


def rebuild_state_articles(layout: Layout | None = None) -> pd.DataFrame:
    """(event_id, article_id, rank) of every Call A D0 state, rebuilt and checked (module docstring)."""
    from newsaction.states.build import load_inputs, skipped

    lay = resolve_layout(layout)
    cfg = baselines_config(lay)
    ev = d0_events(cfg, lay, with_news=True)
    inp = load_inputs(lay)
    skip = skipped(inp, "W0")
    rows: list[dict[str, Any]] = []
    bad: list[str] = []
    for rec in ev[["event_id", "n_articles", "news_w0", "state_json"]].to_dict("records"):
        cands = []
        for a in rec["news_w0"]:
            aid = str(a["id"])
            if aid in skip:
                continue
            title, snippet = inp.masked[aid]
            if title or snippet:
                cands.append((aid, title, snippet))
        n = int(rec["n_articles"])
        news = json.loads(rec["state_json"])["news"]
        if len(cands) < n or len(news) != n or not _same_news(cands[:n], news):
            bad.append(str(rec["event_id"]))
            continue
        eid = rec["event_id"]
        rows += [{"event_id": eid, "article_id": c[0], "rank": i} for i, c in enumerate(cands[:n])]
    if bad:
        raise BaselineError(f"{len(bad)} states do not match their rebuilt articles, e.g. {bad[:5]}")
    return pd.DataFrame(rows, columns=["event_id", "article_id", "rank"]).astype({"rank": "int64"})


def _same_news(cands: Sequence[tuple[str, str, str]], news: Sequence[dict[str, str]]) -> bool:
    for i, ((_, title, snippet), item) in enumerate(zip(cands, news, strict=True)):
        if i == 0:  # fit_news may cut the first article's snippet, then its headline, by words
            if not (_word_prefix(item["snippet"], snippet) and _word_prefix(item["headline"], title)):
                return False
        elif item["headline"] != title or item["snippet"] != snippet:
            return False
    return True


def _word_prefix(short: str, full: str) -> bool:
    a, b = short.split(), full.split()
    return a == b[: len(a)]


def state_articles(layout: Layout | None = None) -> pd.DataFrame:
    return io.read_parquet(STATE_ARTICLES, layout=layout)


# --- features -----------------------------------------------------------------------------------------------


def article_features(cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    """One row per Call A D0 state: aggregates of its articles' vendor sentiment, intensity, tags, flags,
    source classes, novelty and duplicates (PRD S2, S4)."""
    lay = resolve_layout(layout)
    sa = state_articles(lay)
    check_inputs([c for c in ARTICLE_COLUMNS if c != "id"], "D0", vendor=True)
    arts = io.read_parquet(ARTICLES, columns=list(ARTICLE_COLUMNS), layout=lay)
    a = sa.merge(arts, left_on="article_id", right_on="id", how="left", validate="many_to_one")
    if bool(a["id"].isna().any()):
        raise BaselineError("a state article is missing from articles_clean")
    scale = cfg.sentiment.scale
    unknown = set(a["sentiment_direction"].dropna()) - set(scale)
    if unknown:
        raise BaselineError(f"unknown sentiment labels {sorted(unknown)}")
    a["sent"] = a["sentiment_direction"].map(scale).astype("float64")
    a["nonneutral"] = (a["sent"] != 0).astype("float64").where(a["sent"].notna())
    a["timely"] = a["sentiment_intensity"].isin(list(cfg.sentiment.timely)).astype("float64")
    for name in INTENSITIES:
        a[f"int_{name}"] = (a["sentiment_intensity"] == name).astype("float64")
    a["int_missing"] = a["sentiment_intensity"].isna().astype("float64")
    for t in TAG_TYPES:
        a[f"tag_{t}"] = (a["tag_type"] == t).astype("float64")
    for f in FLAGS:
        a[f] = a[f].astype("float64")
    for s in SOURCE_CLASSES:
        a[f"src_{s}"] = (a["source_class_domain"] == s).astype("float64")
    g = a.groupby("event_id", sort=False)
    out = pd.DataFrame(
        {
            "n_state_articles": g.size(),
            "sent_mean": g["sent"].mean(),
            "sent_min": g["sent"].min(),
            "sent_max": g["sent"].max(),
            "share_nonneutral": g["nonneutral"].mean(),
            "share_timely": g["timely"].mean(),
            "novelty_max": g["novelty"].max(),
            "novelty_mean": g["novelty"].mean(),
            "dup_w0_sum": g["dup_count_w0"].sum(),
        }
    )
    for c in [f"int_{n}" for n in INTENSITIES] + ["int_missing"] + list(FLAGS):
        out[f"share_{c}"] = g[c].mean()
    for c in [f"tag_{t}" for t in TAG_TYPES] + [f"src_{s}" for s in SOURCE_CLASSES]:
        out[f"n_{c}"] = g[c].sum()
    return out.reset_index()


def prev_sessions(sessions: Iterable[Any]) -> dict[Any, Any]:
    return {s: calendar.prev_session(s) for s in sorted(set(sessions))}


def price_features(keys: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    """t−1 price features of (session, symbol_id): momentum z_m5 / z_m20 / z_m60, the σ regime (σ_cc
    percentile vs its own 252 sessions), sector, and z_vol of the previous session (``z_vol_lag1``; known at
    D0). Test sessions get the context columns (NA-04 built them from t−1 data) and no ``z_vol_lag1``
    (a 2026 volume, never read here)."""
    lay = resolve_layout(layout)
    check_inputs(["z_m5", "z_m20", "z_m60", "ctx_sigma_cc_pct", "sector", "z_vol_lag1"], "D0")
    ctx = io.read_parquet(
        CONTEXT_COMPANY,
        columns=["session", "symbol_id", "z_m5", "z_m20", "z_m60", "ctx_sigma_cc_pct", "sector"],
        layout=lay,
    )
    out = keys[["session", "symbol_id"]].merge(ctx, on=["session", "symbol_id"], how="left", validate="m:1")
    vol = io.read_parquet(PANEL, columns=["session", "symbol_id", "z_vol"], layout=lay)
    prev = prev_sessions(out["session"])
    out["prev_session"] = out["session"].map(prev)
    vol = vol.rename(columns={"session": "prev_session", "z_vol": "z_vol_lag1"})
    out = out.merge(vol, on=["prev_session", "symbol_id"], how="left", validate="m:1")
    return out.drop(columns=["prev_session"])


def d0_targets(keys: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    """e5, z_cc, |z_cc| and z_on of (session, symbol_id) from panel_public (NaN where purged or test)."""
    p = io.read_parquet(PANEL, columns=["session", "symbol_id", "e5", "z_cc", "z_on"], layout=layout)
    out = keys[["session", "symbol_id"]].merge(p, on=["session", "symbol_id"], how="left", validate="m:1")
    out["abs_z_cc"] = out["z_cc"].abs()
    return out


def d2_frame(cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    """Every event with a Call B state (train / val): keys, the D0 price features, the D2 reaction
    (G = z_cc,t, z_on,t, z_vol,t) and the target y2."""
    lay = resolve_layout(layout)
    states = state_rows(cfg, "B", lay).drop(columns=["state_json", "n_articles"])
    if bool((states["split"] == "test").any()):
        raise BaselineError("a Call B state in the test period (NA-04 builds none before the freeze)")
    ev = io.read_parquet(
        "events/events_d2.parquet", columns=["event_id", "symbol_id", "tier", "month", "embargo"], layout=lay
    )
    out = states.merge(ev, on="event_id", how="left", validate="one_to_one")
    check_inputs(["g_d2", "react_z_vol", "react_z_on"], "D2")
    rx = io.read_parquet(REACTION_D2, columns=["session", "symbol_id", "g_d2", "react_z_vol"], layout=lay)
    out = out.merge(rx, on=["session", "symbol_id"], how="left", validate="m:1")
    p = io.read_parquet(PANEL, columns=["session", "symbol_id", "z_on", "y2"], layout=lay)
    p = p.rename(columns={"z_on": "react_z_on"})
    out = out.merge(p, on=["session", "symbol_id"], how="left", validate="m:1")
    pf = price_features(out, lay)
    out = pd.concat([out.reset_index(drop=True), pf.drop(columns=["session", "symbol_id"])], axis=1)
    return out.sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def d0_frame(cfg: BaselinesConfig, layout: Layout | None = None) -> pd.DataFrame:
    """Every event with a Call A D0 state: keys, attention, article aggregates, price features, targets."""
    lay = resolve_layout(layout)
    check_inputs(["tier", "month", "embargo", *ATTENTION], "D0")
    ev = d0_events(cfg, lay)
    af = article_features(cfg, lay)
    out = ev.merge(af, on="event_id", how="left", validate="one_to_one")
    if bool(out["n_state_articles"].isna().any()):
        raise BaselineError("a Call A state has no rebuilt articles")
    pf = price_features(out, lay).drop(columns=["session", "symbol_id"])
    tg = d0_targets(out, lay).drop(columns=["session", "symbol_id"])
    return pd.concat([out.reset_index(drop=True), pf, tg], axis=1)


# --- embeddings -----------------------------------------------------------------------------------------


def event_embeddings(events: pd.DataFrame, layout: Layout | None = None) -> npt.NDArray[np.float32]:
    """Mean of the bge-small vectors of each event's state articles (rows aligned with ``events``)."""
    from newsaction.news.embed import read_embeddings

    lay = resolve_layout(layout)
    check_inputs(["embedding"], "D0")
    sa = state_articles(lay)
    sa = sa.loc[sa["event_id"].isin(set(events["event_id"]))]
    emb = read_embeddings(layout=lay)
    vecs = emb.matrix_for(sa["article_id"].astype("str")).astype(np.float32)
    pos = pd.Series(np.arange(len(events)), index=events["event_id"].to_numpy())
    row = pos.reindex(sa["event_id"].to_numpy()).to_numpy()
    if np.isnan(row.astype(float)).any():
        raise BaselineError("state articles of an unknown event")
    out = np.zeros((len(events), vecs.shape[1]), dtype=np.float64)
    np.add.at(out, row.astype(np.int64), vecs)
    counts = np.bincount(row.astype(np.int64), minlength=len(events)).astype(np.float64)
    if (counts == 0).any():
        raise BaselineError(f"{int((counts == 0).sum())} events have no state article")
    return (out / counts[:, None]).astype(np.float32)
