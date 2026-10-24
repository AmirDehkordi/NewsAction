"""NA-02 build: ``uv run python -m newsaction.news.build [--stage all|embed|articles|coverage]``.

Stages (each reads only registered files and Data/news; schemas in docs/DATA_CONTRACT.md). Run them one
process at a time to bound memory (``--stage prepare``, then ``embed``, ``articles``, ``coverage``):
1. ``prepare``: load (S1), time (S3), map + membership (S2), clean flags (S4), detectors and scrub (S5),
   source classes (S9) -> work/news/articles_stage1.parquet; market-index articles ->
   work/news/market_articles.parquet (S14); mapping statistics -> artifacts/NA-02/.
2. ``embed`` (S6): work/news/embeddings_ts.parquet, one row per mapped member article id; rows whose
   embedded text is unchanged are reused from an existing file (``text_sha``).
3. ``articles`` (S7, S8, S12): near-duplicate groups and PIT novelty over the clean articles; writes
   work/news/articles_clean.parquet.
4. ``coverage`` (S11): work/news/coverage_member_month.parquet.

No return or price is read here; the ≤ 2025 audits are in ``newsaction.news.audit``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Final

import pandas as pd

from newsaction import io
from newsaction.news import (
    ARTICLES,
    MARKET_ARTICLES,
    STAGE1,
    clean,
    coverage,
    dedupe,
    detect,
    embed,
    load,
    load_news_config,
    mapping,
    novelty,
    sources,
)
from newsaction.paths import Layout, resolve_layout

PRODUCER: Final = "newsaction.news.build (NA-02)"
VENDOR_FIELDS: Final = (
    "sentiment_direction",
    "sentiment_intensity",
    "tag_type",
    "tag_type2",
    *load.VENDOR_FLAGS,
    "tag_source",
    "event_id",
    "event_age_days",
)
FLAG_COLUMNS: Final = ("non_news", "junk_tag", "is_13f", "is_form4", "after_fact", "premarket_talk")
OUTPUT_COLUMNS: Final = (
    "id",
    "company_id",
    "symbol_id",
    "ticker_raw",
    "ts_pub_utc",
    "precision",
    "t_avail",
    "session_w0",
    "session_w2",
    "domain",
    "source_class",
    "source_class_domain",
    "title",
    "snippet",
    "title_clean",
    "snippet_clean",
    "summary_present",
    *FLAG_COLUMNS,
    "has_clean_text",
    "non_english_hint",
    "third_party_ok",
    "parsing_allowed",
    *VENDOR_FIELDS,
    "dup_group",
    "dup_count",
    "dup_count_w0",
    "dup_count_w2",
    "is_representative",
    "novelty",
    "keep",
)


@dataclass
class Prepared:
    articles: pd.DataFrame
    market: pd.DataFrame
    stats: dict[str, Any] = field(default_factory=dict)
    unmapped: pd.DataFrame = field(default_factory=pd.DataFrame)
    timings: dict[str, float] = field(default_factory=dict)


def _reference(layout: Layout) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    symbols = io.read_parquet("snapshot/symbols.parquet", layout=layout)
    history = io.read_parquet("snapshot/symbol_tickers.parquet", layout=layout)
    members = io.read_parquet("snapshot/members_by_session.parquet", layout=layout)
    companies = io.read_parquet("panel/companies.parquet", layout=layout)
    tmap = mapping.ticker_map(symbols, history)
    pairs = mapping.member_companies(members, companies)
    return tmap, pairs, companies


def _text_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cleaning flags, detector flags, scrubbed text and source classes for ``df`` (in place)."""
    flags = clean.clean_flags(df)
    for c in flags.columns:
        df[c] = flags[c].to_numpy()
    det = detect.detect_articles(df["title"], df["snippet"])
    for c in det.columns:
        df[c] = det[c].to_numpy()
    df["source_class_domain"] = sources.source_class_domain(df["domain"])
    df["source_class"] = sources.source_class(df["domain"], df["tag_primary_source"])
    return df


def _with_text(year: int, df: pd.DataFrame, layout: Layout) -> pd.DataFrame:
    """``df`` (rows of one news file) with title, snippet and summary_present, then text features."""
    df = df.sort_values("row").reset_index(drop=True)
    text = load.read_text(year, df["row"].to_numpy(), layout=layout)
    for c in text.columns:
        df[c] = text[c].to_numpy()
    return _text_features(df.drop(columns=["row", "exchange", "ticker_norm", "ticker_class", "member"]))


def prepare(*, layout: Layout | None = None, years: tuple[int, ...] | None = None) -> Prepared:
    """Stage 1: every member-mapped article with timing, flags and clean text; market articles.

    Year by year: map on the light columns, then read text for member and market rows only.
    """
    lay = resolve_layout(layout)
    cfg = load_news_config()
    tmap, pairs, companies = _reference(lay)
    ident = tmap.merge(companies[["symbol_id", "company_id"]], on="symbol_id")
    ident_company = ident.drop_duplicates("ticker").set_index("ticker")["company_id"]
    kept: list[pd.DataFrame] = []
    market: list[pd.DataFrame] = []
    unmapped: list[pd.Series] = []
    stats: dict[str, Any] = {"by_year": {}}
    timings: dict[str, float] = {}
    for year in years or cfg.load.years:
        t0 = time.time()
        df = load.load_year_light(year, layout=lay)
        parsed = mapping.parse_tickers(df["ticker"])
        df = pd.concat([df, parsed], axis=1)
        us = df["ticker_class"] == mapping.US_EQUITY
        df["symbol_id"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
        df.loc[us, "symbol_id"] = mapping.resolve(df.loc[us, "ticker_norm"], df.loc[us, "t_avail"], tmap)
        df["company_id"] = mapping.attach_company(df["symbol_id"], companies)
        df["member"] = mapping.member_mask(df["session_w2"], df["company_id"], pairs)
        # reference for the mapped share: a member identifier on a member-day of that company,
        # ignoring validity ranges (PRD S2 "member-day article volume")
        ref_company = df["ticker_norm"].map(ident_company).astype("Int64")
        ref = us & mapping.member_mask(df["session_w2"], ref_company, pairs)
        stats["by_year"][year] = {
            "rows_in_range": len(df),
            "ticker_class": {str(k): int(v) for k, v in df["ticker_class"].value_counts().items()},
            "us_mapped": int(df["symbol_id"].notna().sum()),
            "member": int(df["member"].sum()),
            "reference_member_day": int(ref.sum()),
            "reference_mapped_member": int((ref & df["member"]).sum()),
        }
        unmapped.append(df.loc[us & df["symbol_id"].isna(), "ticker"].value_counts())
        timings[f"map_{year}"] = time.time() - t0
        t0 = time.time()
        mkt = df.loc[df["ticker"].isin(cfg.market_tickers)]
        if len(mkt):
            market.append(_with_text(year, mkt.copy(), lay))
        kept.append(_with_text(year, df.loc[df["member"]].copy(), lay))
        timings[f"text_{year}"] = time.time() - t0
        del df, parsed, mkt
        print(f"news.build: {year}: {stats['by_year'][year]['member']:,} member articles", flush=True)
    arts = pd.concat(kept, ignore_index=True)
    del kept
    dup = arts["id"].duplicated(keep="first")
    stats["duplicate_ids_dropped"] = int(dup.sum())
    arts = arts.loc[~dup].reset_index(drop=True)
    mkt_df = pd.concat(market, ignore_index=True) if market else pd.DataFrame()
    top = pd.concat(unmapped).groupby(level=0).sum().sort_values(ascending=False)
    top_df = top.rename("n").rename_axis("ticker").reset_index()
    return Prepared(arts, mkt_df, stats, top_df, timings)


def market_output(mkt: pd.DataFrame) -> pd.DataFrame:
    """S14: cleaned, scrubbed market-index articles (no company mapping; same third-party rule)."""
    keep = clean.passes_clean(mkt)
    cols = [
        "id",
        "ticker",
        "ts_pub_utc",
        "precision",
        "t_avail",
        "session_w0",
        "session_w2",
        "domain",
        "source_class_domain",
        "title",
        "snippet",
        "title_clean",
        "snippet_clean",
        "summary_present",
        "non_news",
        "junk_tag",
        "is_13f",
        "after_fact",
        "premarket_talk",
        "third_party_ok",
    ]
    out = mkt.loc[keep, cols].rename(columns={"ticker": "ticker_raw"})
    out = out.drop_duplicates("id").sort_values(["t_avail", "id"], kind="stable")
    return out.reset_index(drop=True)


def write_market(prep: Prepared, *, layout: Layout | None = None) -> dict[str, Any]:
    return io.write_parquet(
        market_output(prep.market),
        MARKET_ARTICLES,
        producer=PRODUCER,
        description="NA-02 S14: cleaned, scrubbed market-index articles (^GSPC, ^VIX, DX-Y.NYB)",
        layout=layout,
    )


def write_stage1(prep: Prepared, *, layout: Layout | None = None) -> None:
    """Stage 1 outputs: work/news/articles_stage1.parquet, market articles, mapping statistics."""
    lay = resolve_layout(layout)
    arts = prep.articles.sort_values(["t_avail", "id"], kind="stable").reset_index(drop=True)
    io.write_parquet(
        arts.drop(columns=["file_year"]),
        STAGE1,
        producer=PRODUCER,
        description="NA-02 stage 1: member-mapped articles with timing, flags and scrubbed text (pre-dedupe)",
        layout=lay,
    )
    write_market(prep, layout=lay)
    out = lay.artifacts / "NA-02"
    out.mkdir(parents=True, exist_ok=True)
    stats = {**prep.stats, "timings_s": {k: round(v, 1) for k, v in prep.timings.items()}}
    (out / "mapping_stats.json").write_text(json.dumps(stats, indent=2, default=str) + "\n", encoding="utf-8")
    prep.unmapped.head(100).to_csv(out / "unmapped_top100.csv", index=False)


def finalize(arts: pd.DataFrame, emb: embed.Embeddings) -> pd.DataFrame:
    """Stage 3: dedupe + novelty over clean articles with clean text; ``keep``; output column order."""
    cfg = load_news_config()
    arts = arts.rename(columns={"ticker": "ticker_raw"})
    arts["has_clean_text"] = embed.embed_text(arts["title_clean"], arts["snippet_clean"]) != ""
    arts["non_english_hint"] = detect.non_english_hint(arts["title"], arts["snippet"]).to_numpy()
    usable = (clean.passes_clean(arts) & arts["has_clean_text"]).to_numpy()
    vecs = emb.matrix_for(arts["id"])
    groups = dedupe.near_duplicate_groups(
        arts, vecs, mask=usable, cosine=cfg.dedupe.cosine, window=pd.Timedelta(hours=cfg.dedupe.window_hours)
    )
    for c in groups.columns:
        arts[c] = groups[c].to_numpy()
    arts["novelty"] = novelty.pit_novelty(
        arts, vecs, mask=usable, window=pd.Timedelta(days=cfg.novelty.window_days)
    ).to_numpy()
    arts["keep"] = usable & arts["is_representative"].to_numpy(dtype=bool)
    arts = arts.sort_values(["t_avail", "id"], kind="stable").reset_index(drop=True)
    return arts[list(OUTPUT_COLUMNS)]


def main(argv: list[str] | None = None) -> int:
    """Run one stage per process (``all`` runs them in order); each stage reads the previous one's file."""
    parser = argparse.ArgumentParser(prog="python -m newsaction.news.build")
    parser.add_argument("--stage", choices=["all", "prepare", "embed", "articles", "coverage"], default="all")
    args = parser.parse_args(argv)
    if args.stage in ("all", "prepare"):
        prep = prepare()
        for k, v in prep.timings.items():
            print(f"news.build: {k} {v:.1f}s", flush=True)
        write_stage1(prep)
        print(
            f"news.build: {len(prep.articles):,} member, {len(prep.market):,} market-index articles",
            flush=True,
        )
        del prep
    if args.stage in ("all", "embed"):
        embed.embed_articles(io.read_parquet(STAGE1, columns=["id", "title_clean", "snippet_clean"]))
    if args.stage in ("all", "articles"):
        arts = finalize(io.read_parquet(STAGE1), embed.read_embeddings())
        io.write_parquet(
            arts,
            ARTICLES,
            producer=PRODUCER,
            description="NA-02 S12: cleaned, timed, member-mapped articles with flags, dedupe, PIT novelty",
        )
        print(
            f"news.build: wrote {ARTICLES} ({len(arts):,} rows, keep {int(arts['keep'].sum()):,})", flush=True
        )
        del arts
    if args.stage in ("all", "coverage"):
        coverage.write_coverage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
