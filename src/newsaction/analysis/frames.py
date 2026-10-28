"""Analysis frames: the rows ``spec`` reads (NA-11 S1–S2 on the public splits; NA-12 adds the test targets).

Not hash-locked (PREREG §15 NA-11 row): this module joins registered work files and renames columns; it
computes no statistic, and ``spec`` applies every pre-registered sample rule (split, embargo, purge) itself.

- **Events.** Every event with a Call A state: D0 (``events_d0`` ∩ ``callA_d0_E3``; D1's Call B shares the
  D0 event id) and D2 (``events_d2`` ∩ ``callA_d2_E3``; Call B D2 shares the D2 event id). Keys, tier, split,
  embargo and the clean-window flags come from NA-03's events.
- **Readings** (``readings_*``): one model's answers per source, prefixed ``a0_`` (Call A, W0), ``a2_``
  (Call A, W2), ``b2_`` (Call B, D2), ``b1_`` (Call B, D1), with ``dm.parse``'s names (``n_hat``,
  ``abs_n_hat``, ``m``, ``surprise``, ``tone``, ``j``, ``w``, ``c``, …), Q1's nine probabilities ``q1``
  (a list) and ``conf_q1`` (normalized entropy confidence). The trained instruments are read only through
  ``train.import_preds.read_instrument`` (the frozen seed-13 runs).
- **Targets** (``public_targets``): ``panel_public`` (sessions before the test start) and, for D1,
  ``intraday_public``, on the event's (session, symbol_id). Test targets come from NA-12's unblinding.
- **Attributes.** From the state's own articles (NA-09's ``baselines/state_articles.parquet`` for W0, the
  same reconstruction for W2 in ``state_articles_w2``): the first news item's vendor ``tag_type``,
  ``tag_quantified`` and ``source_class``; ``imprecise`` (a date-only or hour stamp); ``latest_et``. From the
  state JSON: ``price_move_text`` and ``live_format`` (``spec``'s frozen patterns). NA-03's W0 window
  counts give ``attention_mean`` / ``attention_ratio`` (operator row (7)–(8)) for D0 and D2 events alike;
  ``context_company`` gives the earnings flag.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.analysis import metrics as mx
from newsaction.analysis import spec
from newsaction.config import load_splits
from newsaction.paths import Layout, resolve_layout

PRODUCER: Final = "NA-11"
EVENTS: Final = {"D0": "events/events_d0.parquet", "D2": "events/events_d2.parquet"}
STATES: Final = {"D0": "states/callA_d0_E3.parquet", "D2": "states/callA_d2_E3.parquet"}
WINDOW: Final = {"D0": "W0", "D2": "W2"}
SOURCES: Final = {("A", "W0"): "a0_", ("A", "W2"): "a2_", ("B", "W2"): "b2_", ("B", "W0"): "b1_"}
STATE_ARTICLES_W0: Final = "baselines/state_articles.parquet"
STATE_ARTICLES_W2: Final = "analysis/state_articles_w2.parquet"
LAYA_ZEROSHOT: Final = "baselines/laya_zeroshot.parquet"
PRICE_ONLY: Final = "baselines/price_only.parquet"
PANEL_COLUMNS: Final = (
    "session",
    "symbol_id",
    "sector",
    "half_day",
    "dv_tier",
    "r_cc",
    "r_spy_cc",
    "ar_cc",
    "ar_on",
    "ar_id",
    "z_cc",
    "z_on",
    "z_id",
    "z_vol",
    "z_m5",
    "z_m20",
    "z_m60",
    "sigma_cc",
    "y2",
    "e5",
    "e5_lvl",
    "car_lvl_o0",
    "car_lvl_c0",
    "car_lvl_c1",
    "car_lvl_c2",
    "car_lvl_c5",
    "car_lvl_c10",
    "car_lvl_c20",
    "car_lvl_c60",
    "fwd_lvl_o1_c1",
    "fwd_lvl_o1_c5",
    "fwd_lvl_o1_c20",
    "ar_o1_c5",
    "g_d2",
    "g_d2_lvl",
    "delist_within_c20",
)
INTRADAY_COLUMNS: Final = (
    "session",
    "symbol_id",
    "g_d1",
    "g_d1_lvl",
    "car_lvl_10",
    "y1",
    "fwd_lvl_10_c0",
    "fwd_lvl_10_c1",
    "fwd_lvl_10_c5",
    "fwd_lvl_10_c20",
)
EVENT_COLUMNS: Final = (
    "event_id",
    "company_id",
    "session",
    "symbol_id",
    "tier",
    "split",
    "embargo",
    "clean_1",
    "clean_2",
    "clean_5",
    "clean_10",
    "clean_20",
)
ARTICLE_META: Final = ("id", "precision", "t_avail", "source_class", "tag_type", "tag_quantified")


class FrameError(ValueError):
    """Inputs that do not join as the frames require."""


# --- readings ----------------------------------------------------------------------------------------------


def _q1_conf(probs: Iterable[Any]) -> np.ndarray:
    arr = np.stack([np.asarray(p, dtype=float) for p in probs]) if probs is not None else np.zeros((0, 9))
    return mx.entropy_confidence(arr) if len(arr) else np.zeros(0)


def readings_trained(model: str, splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """A frozen trained instrument's readings, one row per event (``read_instrument``: the pinned runs)."""
    from newsaction.train.import_preds import read_instrument

    parts = [read_instrument(model, s, layout) for s in splits]
    df = pd.concat(parts, ignore_index=True)
    out: dict[str, pd.DataFrame] = {}
    for (call, window), g in df.groupby(["call", "window"]):
        p = SOURCES[(str(call), str(window))]
        cols: dict[str, pd.Series] = {}
        react = g[g["question"] == "react"].set_index("event_id")
        if len(react):
            cols[f"{p}n_hat"] = react["n_hat"]
            cols[f"{p}abs_n_hat"] = react["e_abs_n"]
            cols[f"{p}q1"] = react["probabilities"]
            cols[f"{p}conf_q1"] = pd.Series(_q1_conf(react["probabilities"]), index=react.index)
        mag = g[g["question"] == "mag"].set_index("event_id")
        if len(mag):
            cols[f"{p}mag_mean"] = mag["mag_mean"]
            cols[f"{p}p_mag_ge1"] = mag["p_mag_ge1"]
        cont = g[g["question"] == "cont"].set_index("event_id")
        if len(cont):
            cols[f"{p}c"] = cont["c_cont"]
            cols[f"{p}w"] = cont["w_cont"]
            cols[f"{p}j"] = cont["j_cont"]
            cols[f"{p}conf_cont"] = pd.Series(_q1_conf(cont["probabilities"]), index=cont.index)
        out[p] = pd.DataFrame(cols)
    return _stack(out)


def readings_zeroshot(splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """Laya zero-shot (NA-09 S6): Call A on W0, Call B on D2 (every non-test state; test Call A after the
    freeze), with M, surprise, tone or J, W, C and Q1's probabilities from ``extra``."""
    df = io.read_parquet(LAYA_ZEROSHOT, layout=layout)
    df = df.loc[df["split"].isin(list(splits))]
    extra = [json.loads(e) if isinstance(e, str) else dict(e) for e in df["extra"]]
    out: dict[str, pd.DataFrame] = {}
    for call, window, keys in (("A", "W0", ("m", "surprise", "tone")), ("B", "W2", ("j", "w", "c"))):
        mask = ((df["call"] == call) & df["event_id"].str.startswith(f"{window}:")).to_numpy()
        g = df.loc[mask]
        ex = [e for e, m in zip(extra, mask, strict=True) if m]
        p = SOURCES[(call, window)]
        frame = pd.DataFrame(index=g["event_id"].to_numpy())
        frame[f"{p}n_hat"] = g["N_hat"].to_numpy()
        frame[f"{p}abs_n_hat"] = g["mag_hat"].to_numpy()
        for k in keys:
            frame[f"{p}{k}"] = [e.get(k, np.nan) for e in ex]
        frame[f"{p}q1"] = [e["q1_probs"] for e in ex]
        frame[f"{p}conf_q1"] = _q1_conf(frame[f"{p}q1"])
        out[p] = frame
    return _stack(out)


def readings_api(path_rel: str, layout: Layout | None = None) -> pd.DataFrame:
    """An API model's production readings (``production.run`` output: one row per event and source with
    ``dm.parse`` names and ``source`` = the prefix without the underscore)."""
    df = io.read_parquet(path_rel, layout=layout)
    out: dict[str, pd.DataFrame] = {}
    for src, g in df.groupby("source"):
        p = f"{src}_"
        g = g.set_index("event_id").drop(columns=["source"])
        out[p] = g.add_prefix(p)
    return _stack(out)


def _stack(parts: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Event-level frame: one row per event id with every source's columns (outer join on the event id)."""
    frames = [f for f in parts.values() if len(f)]
    if not frames:
        return pd.DataFrame(columns=["event_id"])
    out = pd.concat(frames, axis=1, join="outer")
    out.index.name = "event_id"
    return out.reset_index()


# --- events, targets, attributes ---------------------------------------------------------------------------


def events(point: str, layout: Layout | None = None) -> pd.DataFrame:
    """The events of ``point`` (D0 or D2) that have a Call A state."""
    ev = io.read_parquet(EVENTS[point], columns=list(EVENT_COLUMNS), layout=layout)
    st = io.read_parquet(STATES[point], columns=["event_id"], layout=layout)
    return ev.loc[ev["event_id"].isin(set(st["event_id"]))].reset_index(drop=True)


def public_targets(layout: Layout | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(panel rows, intraday rows) of the public sessions with the columns the spec reads."""
    panel = io.read_parquet("panel/panel_public.parquet", columns=list(PANEL_COLUMNS), layout=layout)
    intraday = io.read_parquet("panel/intraday_public.parquet", columns=list(INTRADAY_COLUMNS), layout=layout)
    test_start = load_splits().splits["test"].start
    for f in (panel, intraday):
        if bool((pd.to_datetime(f["session"]) >= pd.Timestamp(test_start)).any()):
            raise FrameError("public targets hold a test-period session")
    return panel, intraday


def state_articles_w2(layout: Layout | None = None) -> pd.DataFrame:
    """(event_id, article_id, rank) of every Call A D2 state, rebuilt as NA-09 rebuilt the D0 ones (the first
    ``n_articles`` listed W2 articles NA-04 kept with text) and checked against each state's news block."""
    from newsaction.baselines.data import _same_news
    from newsaction.states.build import load_inputs, skipped

    lay = resolve_layout(layout)
    ev = io.read_parquet(EVENTS["D2"], columns=["event_id", "news_w2"], layout=lay)
    st = io.read_parquet(STATES["D2"], columns=["event_id", "n_articles", "state_json"], layout=lay)
    ev = ev.merge(st, on="event_id", how="inner")
    inp = load_inputs(lay)
    skip = skipped(inp, "W2")
    rows: list[dict[str, Any]] = []
    bad: list[str] = []
    for rec in ev.to_dict("records"):
        cands = []
        for a in rec["news_w2"]:
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
        rows += [
            {"event_id": rec["event_id"], "article_id": c[0], "rank": i} for i, c in enumerate(cands[:n])
        ]
    if bad:
        raise FrameError(f"{len(bad)} D2 states do not match their rebuilt articles, e.g. {bad[:5]}")
    return pd.DataFrame(rows, columns=["event_id", "article_id", "rank"]).astype({"rank": "int64"})


def write_state_articles_w2(layout: Layout | None = None) -> dict[str, Any]:
    df = state_articles_w2(layout)
    return io.write_parquet(
        df,
        STATE_ARTICLES_W2,
        producer=PRODUCER,
        description="NA-11: (event_id, article_id, rank) of every Call A D2 state (W2), rebuilt from "
        "events_d2 "
        "news_w2 with NA-04's exclusions and checked against each state's news block",
        layout=layout,
    )


def article_attributes(point: str, sessions: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    """Per event: the first news item's vendor tag type, quantified flag and source class; ``imprecise``;
    ``latest_et`` (minutes after ET midnight of the session, negative before it)."""
    rel = STATE_ARTICLES_W0 if point == "D0" else STATE_ARTICLES_W2
    sa = io.read_parquet(rel, layout=layout)
    meta = io.read_parquet("news/articles_clean.parquet", columns=list(ARTICLE_META), layout=layout)
    meta = meta.loc[meta["id"].isin(set(sa["article_id"]))].rename(columns={"id": "article_id"})
    a = sa.merge(meta, on="article_id", how="left", validate="many_to_one")
    if bool(a["precision"].isna().any()):
        raise FrameError("state articles without metadata")
    first = a.loc[a["rank"] == 0].set_index("event_id")
    cfg = spec.load_config()
    a["imprecise"] = a["precision"].isin(list(cfg.robustness.date_only_hour_precision))
    agg = a.groupby("event_id").agg(imprecise=("imprecise", "any"), latest=("t_avail", "max"))
    out = pd.DataFrame(index=agg.index)
    out["vendor_event_type"] = first["tag_type"].reindex(out.index)
    out["vendor_quantified"] = first["tag_quantified"].reindex(out.index)
    out["press_wire"] = first["source_class"].reindex(out.index) == "press_wire_primary"
    out["imprecise"] = agg["imprecise"]
    sess = sessions.set_index("event_id")["session"].reindex(out.index)
    latest = pd.to_datetime(agg["latest"], utc=True).dt.tz_convert("America/New_York")
    midnight = pd.to_datetime(sess.astype(str)).dt.tz_localize("America/New_York")
    out["latest_et"] = (latest - midnight).dt.total_seconds() / 60.0
    return out.reset_index()


def text_flags(point: str, layout: Layout | None = None) -> pd.DataFrame:
    """``price_move_text`` and ``live_format`` of each Call A state (operator row (a); the residue count)."""
    st = io.read_parquet(STATES[point], columns=["event_id", "state_json"], layout=layout)
    cfg = spec.load_config()
    return pd.DataFrame(
        {
            "event_id": st["event_id"],
            "price_move_text": [spec.price_move_text(s, cfg) for s in st["state_json"]],
            "live_format": [spec.live_format(s, cfg) for s in st["state_json"]],
        }
    )


def attention(layout: Layout | None = None) -> pd.DataFrame:
    w = io.read_parquet(
        "events/window_counts.parquet",
        columns=["session", "company_id", "attention_mean_w0", "attention_ratio_w0"],
        layout=layout,
    )
    return w.rename(columns={"attention_mean_w0": "attention_mean", "attention_ratio_w0": "attention_ratio"})


def earnings(point: str, layout: Layout | None = None) -> pd.DataFrame:
    col = "ctx_earnings_w0" if point == "D0" else "ctx_earnings_w2"
    c = io.read_parquet(
        "states/context_company.parquet", columns=["session", "symbol_id", col], layout=layout
    )
    return c.rename(columns={col: "earnings"}).assign(earnings=lambda d: d["earnings"].astype(float))


# --- assembly ---------------------------------------------------------------------------------------------


def base(
    point: str,
    *,
    splits: Sequence[str],
    layout: Layout | None = None,
    targets: tuple[pd.DataFrame, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """The model-independent part of ``point``'s frame on ``splits``: events, targets, attributes, HAR and the
    price-only reading (``po_n_hat``, D0). ``targets``: (panel, intraday) rows (default: the public ones)."""
    lay = resolve_layout(layout)
    ev = events(point, lay)
    df = ev.loc[ev["split"].isin(list(splits))].copy()
    panel, intraday = targets if targets is not None else public_targets(lay)
    for f in (panel, intraday):
        f["session"] = pd.to_datetime(f["session"]).dt.date
    df["session"] = pd.to_datetime(df["session"]).dt.date
    df = df.merge(panel, on=["session", "symbol_id"], how="left", validate="many_to_one")
    if point == "D0":
        df = df.merge(intraday, on=["session", "symbol_id"], how="left", validate="many_to_one")
    df = df.merge(
        attention(lay).assign(session=lambda d: pd.to_datetime(d["session"]).dt.date),
        on=["session", "company_id"],
        how="left",
        validate="many_to_one",
    )
    df = df.merge(
        earnings(point, lay).assign(session=lambda d: pd.to_datetime(d["session"]).dt.date),
        on=["session", "symbol_id"],
        how="left",
        validate="many_to_one",
    )
    df = df.merge(
        article_attributes(point, df[["event_id", "session"]], lay),
        on="event_id",
        how="left",
        validate="one_to_one",
    )
    df = df.merge(text_flags(point, lay), on="event_id", how="left", validate="one_to_one")
    har = spec.har_features(panel[["session", "symbol_id", "z_cc"]], spec.load_config())
    df = df.merge(har, on=["session", "symbol_id"], how="left", validate="many_to_one")
    df["abs_z_cc"] = df["z_cc"].abs()
    if point == "D0":
        po = io.read_parquet(PRICE_ONLY, columns=["event_id", "call", "N_hat"], layout=lay)
        po = po.loc[po["call"] == "A", ["event_id", "N_hat"]].rename(columns={"N_hat": "po_n_hat"})
        df = df.merge(po, on="event_id", how="left", validate="one_to_one")
    return df


def build(
    frame: pd.DataFrame,
    readings: pd.DataFrame,
    *,
    maps: Mapping[str, Mapping[str, Any]] | None = None,
    price_value_map: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """``base`` joined with one model's ``readings``; ``maps``: the model's frozen V / Ñ maps by source prefix
    (``spec.add_calibrated``); ``price_value_map``: the price-only V map (A1.4 benchmark, D0)."""
    df = frame.merge(readings, on="event_id", how="left", validate="one_to_one")
    if maps:
        df = spec.add_calibrated(df, maps)
    if price_value_map is not None and "po_n_hat" in df.columns:
        df["po_v"] = mx.apply_map(df["po_n_hat"].to_numpy(dtype=float), price_value_map)
    return df


# --- covered member-days (A3.2 ladder, §5.7 placebo) -------------------------------------------------------


def member_days(splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """Covered member company-days of ``splits`` (PREREG §3.4, A3.2): the representative class's public panel
    row
    of each member company-session in a covered company-month, with the split's embargo (its first sessions,
    §4.2), the session's D0 and D2 event ids (events with a Call A state) and ``placebo_eligible`` (no
    selected
    D2 event of the company in the session or the previous 5 sessions, §5.7)."""
    lay = resolve_layout(layout)
    cols = [
        "session",
        "symbol_id",
        "company_id",
        "member",
        "is_rep",
        "tier",
        "split",
        "z_cc",
        "ar_cc",
        "r_cc",
        "y2",
        "z_on",
        "z_id",
    ]
    p = io.read_parquet("panel/panel_public.parquet", columns=cols, layout=lay)
    p = p.loc[p["member"].astype(bool) & p["is_rep"].astype(bool) & p["split"].isin(list(splits))]
    p = p.drop(columns=["member", "is_rep"])
    p["session"] = pd.to_datetime(p["session"]).dt.date
    p["month"] = pd.to_datetime(p["session"]).dt.strftime("%Y-%m")
    cov = io.read_parquet(
        "news/coverage_member_month.parquet", columns=["month", "company_id", "covered"], layout=lay
    )
    p = p.merge(
        cov.loc[cov["covered"].astype(bool), ["month", "company_id"]], on=["month", "company_id"], how="inner"
    )
    n_emb = load_splits().embargo_sessions
    first = {s: set(sorted(g["session"].unique())[:n_emb]) for s, g in p.groupby("split")}
    p["embargo"] = [d in first[s] for d, s in zip(p["session"], p["split"], strict=True)]
    for point, col in (("D0", "event_id_d0"), ("D2", "event_id_d2")):
        ev = events(point, lay)[["event_id", "company_id", "session"]]
        ev["session"] = pd.to_datetime(ev["session"]).dt.date
        p = p.merge(
            ev.rename(columns={"event_id": col}),
            on=["company_id", "session"],
            how="left",
            validate="one_to_one",
        )
    sel = io.read_parquet(EVENTS["D2"], columns=["company_id", "session"], layout=lay)
    sel["session"] = pd.to_datetime(sel["session"]).dt.date
    grid = sorted(set(p["session"]) | set(sel["session"]))
    pos = {d: i for i, d in enumerate(grid)}
    hits: dict[int, list[int]] = {}
    for cid, d in zip(sel["company_id"], sel["session"], strict=True):
        hits.setdefault(int(cid), []).append(pos[d])
    for v in hits.values():
        v.sort()
    lookback = 5

    def eligible(cid: int, d: Any) -> bool:
        h = hits.get(cid)
        if not h:
            return True
        i = pos[d]
        j = int(np.searchsorted(h, i, side="right"))  # events at or before day i
        return j == 0 or h[j - 1] < i - lookback

    p["placebo_eligible"] = [eligible(int(c), d) for c, d in zip(p["company_id"], p["session"], strict=True)]
    return p.reset_index(drop=True)


def with_day_readings(days: pd.DataFrame, readings: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    """``days`` with a model's readings: ``a0_*`` through the D0 event, ``a2_*`` / ``b2_*`` through the D2
    event;
    ``has_d0`` / ``has_d2`` flags; ``features`` are 0 on days without the event (A3.2: kept, as in Roll)."""
    r = readings.set_index("event_id")
    out = days.copy()
    out["has_d0"] = out["event_id_d0"].notna().astype(float)
    out["has_d2"] = out["event_id_d2"].notna().astype(float)
    for f in features:
        if f in ("has_d0", "has_d2"):
            continue
        key, flag = ("event_id_d0", "has_d0") if f.startswith("a0_") else ("event_id_d2", "has_d2")
        if f not in r.columns:
            raise FrameError(f"the readings lack {f}")
        out[f] = out[key].map(r[f])
        out.loc[out[flag] == 0.0, f] = 0.0
    return out
