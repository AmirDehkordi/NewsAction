"""D0 and D2 events with the frozen filter, for every period (PREREG §6.9, A1.2; PRD NA-03 S5).

One event per (window, company, session) whose ticker-day the frozen filter selects
(``configs/frozen.yaml`` ``filter:``; ``filters.apply_threshold``):
- **D0 events** use W0 = (close(prev s), 09:15 ET of s];
- **D2 events** use W2 = (close(prev s), close s] with the same filter and threshold;
- **sessions** run from the start of the robustness split to the end of the test split.

The news list (``news_w0`` / ``news_w2``):
- **Order.** Up to 6 kept articles, ordered by the filter's article score (high first), then t_avail,
  then id.
- **Third parties.** Articles with ``third_party_ok`` False are left out but counted
  (``n_not_third_party_*``). A selected ticker-day with no third-party-OK article has no event and is
  counted in the build summary.
- **Tokens.** The list is capped at 600 ModernBERT-large tokens (``tokens.cap_articles``).

Each event also carries:
- the attention counts of ``attention`` (articles, distinct stories, duplicates, ratio vs the previous 60
  member sessions);
- the t−1 tier and representative class (``panel/tiers_monthly.parquet``);
- the split and the §4.2 embargo flag;
- the A1.2 clean-window flags (``clean_window``, from the D2 events).

Inputs are articles, frozen models' scores, counts and t−1 tiers only. This module reads no price,
return or target and imports neither ``newsaction.panel.targets`` nor ``newsaction.lock``, so building
test-period events touches no outcome (PRD NA-03 AC4).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from newsaction import calendar, io
from newsaction.config import SPLIT_ORDER, load_frozen, load_splits
from newsaction.events import (
    ARTICLE_SCORES,
    COUNTS,
    EVENTS_D0,
    EVENTS_D2,
    FILTER_IDS,
    PRODUCER,
    TICKER_DAYS,
    EventsConfig,
    FilterId,
    Window,
    clean_window,
    load_events_config,
    tokens,
)
from newsaction.events.filters import SCORE_COLUMN, apply_threshold, eligible
from newsaction.news import ARTICLES
from newsaction.paths import Layout, resolve_layout

TEXT_COLUMNS: Final = (
    "id",
    "keep",
    "third_party_ok",
    "precision",
    "source_class",
    "source_class_domain",
    "non_english_hint",
    "novelty",
    "dup_count_w0",
    "dup_count_w2",
    "title_clean",
    "snippet_clean",
)
TIER_COLUMNS: Final = ("month", "company_id", "rep_symbol_id", "tier")
NEWS_STRUCT: Final = pa.struct(
    [
        ("id", pa.string()),
        ("rank", pa.int32()),
        ("score", pa.float64()),
        ("t_avail", pa.timestamp("us", tz="UTC")),
        ("precision", pa.string()),
        ("source_class", pa.string()),
        ("source_class_domain", pa.string()),
        ("non_english_hint", pa.bool_()),
        ("novelty", pa.float64()),
        ("dup_count", pa.float64()),
        ("title", pa.string()),
        ("snippet", pa.string()),
        ("title_truncated", pa.bool_()),
        ("snippet_truncated", pa.bool_()),
    ]
)


class EventsError(ValueError):
    """The frozen filter is missing or malformed, or an event breaks a PREREG §6.9 constraint."""


def frozen_filter(layout: Layout | None = None) -> dict[str, Any]:
    ff = load_frozen(resolve_layout(layout).configs / "frozen.yaml").filter
    if not isinstance(ff, dict) or ff.get("id") not in FILTER_IDS:
        raise EventsError("configs/frozen.yaml has no NA-03 filter section; run the compare stage first")
    for key in ("threshold", "tie_u_max", "tie_seed", "budget_share", "rule_version", "comparison_sha"):
        if key not in ff:
            raise EventsError(f"frozen filter lacks {key!r}")
    return dict(ff)


def article_score_column(fid: FilterId, window: Window) -> str:
    col = SCORE_COLUMN[fid]
    return f"{col}_{window.lower()}" if fid == "F6" else col


def event_span() -> tuple[date, date]:
    """First and last session of the event build: robustness start .. test end (configs/splits.yaml)."""
    sp = load_splits().splits
    first, last = sp[SPLIT_ORDER[0]].start, sp[SPLIT_ORDER[-1]].end
    return calendar.next_session(calendar.prev_session(first)), calendar.prev_session(
        calendar.next_session(last)
    )


def select_ticker_days(td: pd.DataFrame, ff: Mapping[str, Any]) -> pd.DataFrame:
    """Ticker-days of ``td`` (one window) selected by the frozen filter."""
    fid = ff["id"]
    score = td[SCORE_COLUMN[fid]].to_numpy(dtype=np.float64)
    mask = apply_threshold(
        score,
        eligible(td, fid),
        td["tie_u"].to_numpy(dtype=np.float64),
        float(ff["threshold"]),
        float(ff["tie_u_max"]),
    )
    out = td.loc[mask, ["company_id", "session", SCORE_COLUMN[fid], "n_kept"]]
    return out.rename(columns={SCORE_COLUMN[fid]: "filter_score"}).reset_index(drop=True)


def _text(x: object) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)


def _news_array(rows: list[list[dict[str, Any]]]) -> pa.Array:
    return pa.array(rows, type=pa.list_(NEWS_STRUCT))


def build_window(
    window: Window,
    sel: pd.DataFrame,
    arts: pd.DataFrame,
    cfg: EventsConfig,
    tok: Any,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Events of one window from the selected ticker-days and their kept articles.

    ``arts``: kept articles of the window (company_id, session, score, t_avail, id, third_party_ok,
    text and descriptive fields). Returns the event frame (without counts, tiers or flags) and counts
    of dropped ticker-days.
    """
    sfx = window.lower()
    a = arts.merge(sel[["company_id", "session"]], on=["company_id", "session"], how="inner")
    a = a.sort_values(
        ["company_id", "session", "score", "t_avail", "id"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    )
    not_ok = a.loc[~a["third_party_ok"].astype(bool)].groupby(["company_id", "session"]).size()
    ok = a.loc[a["third_party_ok"].astype(bool)]
    n_ok = ok.groupby(["company_id", "session"]).size()
    head = ok.groupby(["company_id", "session"], sort=False).head(cfg.max_articles)
    groups = list(head.groupby(["company_id", "session"], sort=True))
    texts = [
        [
            tokens.ArticleText(_text(t), _text(s))
            for t, s in zip(g["title_clean"], g["snippet_clean"], strict=True)
        ]
        for _, g in groups
    ]
    counts = []
    blocks = [tokens.render_block(t) for t in texts]
    for i in range(0, len(blocks), 20_000):
        counts += tokens.count_batch(tok, blocks[i : i + 20_000])
    encode, offsets = tokens.hf_encode(tok), tokens.hf_offsets(tok)
    rows: list[dict[str, Any]] = []
    news: list[list[dict[str, Any]]] = []
    for ((company, session), g), arts_text, n_tok in zip(groups, texts, counts, strict=True):
        capped = (
            tokens.Capped(arts_text, n_tok, 0)
            if n_tok <= cfg.max_news_tokens
            else tokens.cap_articles(arts_text, cfg.max_news_tokens, encode, offsets)
        )
        k = len(capped.articles)
        sub = g.iloc[:k]
        items: list[dict[str, Any]] = []
        for rank, (rec, txt) in enumerate(zip(sub.to_dict("records"), capped.articles, strict=True), start=1):
            items.append(
                {
                    "id": str(rec["id"]),
                    "rank": rank,
                    "score": float(rec["score"]),
                    "t_avail": rec["t_avail"],
                    "precision": rec["precision"],
                    "source_class": rec["source_class"],
                    "source_class_domain": rec["source_class_domain"],
                    "non_english_hint": bool(rec["non_english_hint"]),
                    "novelty": float(rec["novelty"]),
                    "dup_count": float(rec[f"dup_count_{sfx}"]),
                    "title": txt.title,
                    "snippet": txt.snippet,
                    "title_truncated": txt.title_truncated,
                    "snippet_truncated": txt.snippet_truncated,
                }
            )
        news.append(items)
        rows.append(
            {
                "company_id": company,
                "session": session,
                f"n_list_{sfx}": k,
                f"n_ok_{sfx}": int(n_ok.get((company, session), 0)),
                f"n_not_third_party_{sfx}": int(not_ok.get((company, session), 0)),
                f"n_dropped_cap_{sfx}": capped.n_dropped,
                f"news_tokens_{sfx}": capped.n_tokens,
                f"n_non_english_{sfx}": int(sum(i["non_english_hint"] for i in items)),
            }
        )
    ev = pd.DataFrame(rows)
    ev[f"news_{sfx}"] = pd.arrays.ArrowExtensionArray(_news_array(news))
    have = set(zip(ev["company_id"], ev["session"], strict=True)) if len(ev) else set()
    dropped = sel.loc[[(c, s) not in have for c, s in zip(sel["company_id"], sel["session"], strict=True)]]
    stats = {"selected": len(sel), "events": len(ev), "dropped_no_third_party": len(dropped)}
    return ev, stats


def load_window_articles(
    scores: pd.DataFrame, text: pd.DataFrame, fid: FilterId, window: Window
) -> pd.DataFrame:
    sfx = window.lower()
    s = scores.loc[
        scores[f"session_{sfx}"].notna(),
        ["id", "company_id", f"session_{sfx}", "t_avail", article_score_column(fid, window)],
    ]
    s = s.rename(columns={f"session_{sfx}": "session", article_score_column(fid, window): "score"})
    return s.merge(text, on="id", how="left", validate="one_to_one")


def attach_context(
    ev: pd.DataFrame, sel: pd.DataFrame, counts: pd.DataFrame, tiers: pd.DataFrame, window: Window
) -> pd.DataFrame:
    sfx = window.lower()
    out = ev.merge(sel[["company_id", "session", "filter_score"]], on=["company_id", "session"], how="left")
    out = out.rename(columns={"filter_score": f"filter_score_{sfx}"})
    ccols = [c for c in counts.columns if c.endswith(f"_{sfx}")]
    out = out.merge(counts[["company_id", "session", *ccols]], on=["company_id", "session"], how="left")
    out["month"] = pd.to_datetime(out["session"]).dt.strftime("%Y-%m")
    out = out.merge(tiers[list(TIER_COLUMNS)], on=["month", "company_id"], how="left")
    out = out.rename(columns={"rep_symbol_id": "symbol_id"})
    sp = load_splits()
    out["split"] = out["session"].map(lambda d: sp.split_of(d) or "")
    first = {
        name: set(calendar.sessions(sp.splits[name].start, sp.splits[name].end)[: sp.embargo_sessions])
        for name in ("val_a", "val_b", "test")
    }
    out["embargo"] = [d in first.get(s, set()) for d, s in zip(out["session"], out["split"], strict=True)]
    out.insert(
        0,
        "event_id",
        [f"{window}:{c}:{d.isoformat()}" for c, d in zip(out["company_id"], out["session"], strict=True)],
    )
    out.insert(1, "window", window)
    out.insert(2, "decision_point", "D0" if window == "W0" else "D2")
    return out


def run_events(layout: Layout | None = None) -> dict[str, Any]:
    """Build and write work/events/events_d0.parquet and events_d2.parquet."""
    lay = resolve_layout(layout)
    cfg = load_events_config()
    ff = frozen_filter(lay)
    fid: FilterId = ff["id"]
    first, last = event_span()
    td = io.read_parquet(TICKER_DAYS, layout=lay)
    td = td.loc[[first <= d <= last for d in td["session"]]]
    scores = io.read_parquet(ARTICLE_SCORES, layout=lay)
    text = io.read_parquet(ARTICLES, columns=list(TEXT_COLUMNS), layout=lay)
    text = text.loc[text["keep"].astype(bool)].drop(columns=["keep"]).reset_index(drop=True)
    counts = io.read_parquet(COUNTS, layout=lay)
    tiers = io.read_parquet("panel/tiers_monthly.parquet", columns=list(TIER_COLUMNS), layout=lay)
    tok = tokens.tokenizer(cfg.events)
    built: dict[str, pd.DataFrame] = {}
    stats: dict[str, Any] = {"filter": ff}
    windows: tuple[Window, ...] = ("W0", "W2")
    for window in windows:
        t0 = time.time()
        sel = select_ticker_days(td.loc[td["window"] == window], ff)
        arts = load_window_articles(scores, text, fid, window)
        ev, st = build_window(window, sel, arts, cfg.events, tok)
        ev = attach_context(ev, sel, counts, tiers, window)
        built[window] = ev
        stats[window] = {**st, "seconds": round(time.time() - t0, 1)}
        print(f"events {window}: {st}", flush=True)
    d2_keys = built["W2"][["company_id", "session"]]
    horizons = cfg.events.clean_horizons
    outputs: tuple[tuple[Window, str], ...] = (("W0", EVENTS_D0), ("W2", EVENTS_D2))
    for window, rel in outputs:
        ev = built[window]
        flags = clean_window.clean_flags(ev[["company_id", "session"]], d2_keys, horizons, last)
        ev = (
            pd.concat([ev, flags], axis=1)
            .sort_values(["session", "company_id"], kind="mergesort")
            .reset_index(drop=True)
        )
        check_events(ev, window, cfg.events)
        write_events(
            ev,
            rel,
            window,
            f"NA-03 S5: {'D0' if window == 'W0' else 'D2'} events ({window} news), frozen filter {fid}, "
            f"sessions {first}..{last}; <= {cfg.events.max_articles} third-party-OK articles, "
            f"<= {cfg.events.max_news_tokens} ModernBERT-large tokens; attention counts; A1.2 clean flags",
            lay,
        )
    return stats


def write_events(ev: pd.DataFrame, rel: str, window: Window, description: str, layout: Layout) -> None:
    """Write an event table with pyarrow and register it (``io.register_file``).

    The ``news_*`` list<struct> column is written with its explicit Arrow type and without pandas
    metadata (pandas cannot rebuild a nested ArrowDtype from its metadata string). ``pd.read_parquet``
    returns it as an object column of arrays of dicts, with ``t_avail`` as tz-aware datetimes; the other
    columns keep their pandas dtypes.
    """
    col = f"news_{window.lower()}"
    table = pa.Table.from_pandas(ev.drop(columns=[col]), preserve_index=False)
    news = pa.array(ev[col].array, type=pa.list_(NEWS_STRUCT))
    table = table.append_column(col, news)
    path = layout.work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        pq.write_table(table, tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    io.register_file(rel, producer=PRODUCER, description=description, layout=layout)


def check_events(ev: pd.DataFrame, window: Window, cfg: EventsConfig) -> None:
    """PRD NA-03 AC5 on a built table: 1–6 articles, ≤ cap tokens, unique event ids."""
    sfx = window.lower()
    n = ev[f"n_list_{sfx}"]
    if bool(((n < 1) | (n > cfg.max_articles)).any()):
        raise EventsError(f"{window}: an event has {int(n.min())}..{int(n.max())} articles")
    if bool((ev[f"news_tokens_{sfx}"] > cfg.max_news_tokens).any()):
        raise EventsError(f"{window}: an event exceeds {cfg.max_news_tokens} news tokens")
    if ev["event_id"].duplicated().any():
        raise EventsError(f"{window}: duplicate event ids")
    lengths = ev[f"news_{sfx}"].list.len().to_numpy()
    if not np.array_equal(lengths, n.to_numpy()):
        raise EventsError(f"{window}: news list lengths differ from n_list")
