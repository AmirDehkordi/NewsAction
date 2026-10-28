"""NA-04 build: ``uv run python -m newsaction.states.build --stage <stage>`` (PRD NA-04 S5).

Stages, one process each, in this order (schemas in docs/DATA_CONTRACT.md):
1. ``context``: work/states/context_company.parquet, context_market.parquet, reaction_d2.parquet;
2. ``mask``: work/states/articles_masked.parquet (spaCy; a process pool, so run it as a module);
3. ``states``: work/states/{callA_d0_E3, callA_d2_E3, callB_d2_E3, market_E3}.parquet and
   work/states/samples/{callA_d0_E0..E4, unmasked}.parquet;
4. ``report``: artifacts/NA-04/{token_stats.csv, leak_scan.csv, examples.md, summary.json} and the
   question / codebook hashes in configs/frozen.yaml (``states.report``).

**A state** is canonical JSON (``questions.canonical_json``: sorted keys, compact separators, UTF-8) with the
fixed top-level keys ``company``, ``market``, ``attention``, ``news`` and, for Call B only,
``reaction_so_far``; the optional A3.5 market state has ``market`` and ``news``. A news item is
{``headline``, ``snippet``, ``source_type``, ``timing``}; the text is NA-02's scrubbed title and snippet
(``title_clean`` / ``snippet_clean``, as capped in the NA-03 event list), masked unless the spec says
otherwise. The summary variant is not built here (vendor summaries are text of the §11.6 ablation only).
Move explainers ("Why … Stock Is Up Today", StockStory's "What Happened? Shares of …") and TradingView
reposts (``excluded_ids``) are in no state, in any window: the explainers' text explains the session's move,
and both are often stamped before their content (PREREG §15 NA-04 row 6). Non-English articles are in no
state either (``non_english``; operator decision B, row 8): the masker and the price-talk scrubbers are
English-only. Running market stories (live blogs, running market reports; ``running_story_ids``, row 10) keep
their first stamp while their text is the latest version, so they are in no W0 state: there they carry the
session's own cash-market outcome; W2 ends at the close, so its states keep them. The NA-03 lists are not
refilled; an event left with no article gets no state.

**Availability.** A ``StateSpec`` lists, per block, every input column it reads (``context.block_columns``).
``validate_spec`` calls ``pit.check_inputs`` on each block at the decision point (D0 for W0, D2 for W2)
and adds the call rule: no block of a Call A or market state, and no block but ``reaction_so_far`` of a
Call B state, may read a ``d1`` or ``d2_reaction`` column; ``reaction_so_far`` reads only ``d2_reaction``
columns. Renderers see only the declared columns (``context.Row``).

**Calls built here.** Call A on D0 (W0 news) and on D2 (W2 news, A3.1) for every split, test included
(inputs only); Call B on D2 for train, val-A and val-B; and (stage ``d1``, NA-10) Call B on D1: W0 news with
the reaction by 10:00, for train, val-A and val-B (``reaction_so_far`` at D1 reads ``d1`` columns only).
No Call B state of the test period exists before the NA-11 freeze: ``build_call_b`` refuses test-period
events, and the D2 and D1 reactions come from ``panel.reactions.build_reactions(period="public")``, which
refuses test rows.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import resource
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, cast
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from newsaction import calendar, io, pit
from newsaction.config import load_project, load_splits
from newsaction.events import EVENTS_D0, EVENTS_D2, load_events_config, tokens
from newsaction.news import ARTICLES
from newsaction.paths import Layout, resolve_layout
from newsaction.states import (
    ARTICLES_MASKED,
    CONTEXT_COMPANY,
    CONTEXT_MARKET,
    ENCODINGS,
    PRODUCER,
    SAMPLES_DIR,
    STATES_DIR,
    Call,
    Encoding,
    NonEnglishConfig,
    RunningStoryConfig,
    StatesConfig,
    StateWindow,
    load_states_config,
)
from newsaction.states import context as ctx
from newsaction.states.codebook import Codebook, Horizon, Move, load_codebook
from newsaction.states.macro import cpi_release_dates, load_macro, session_flags
from newsaction.states.mask import (
    SURNAME_MIN_COUNT,
    Masker,
    build_aliases,
    cjk_company_names,
    lowercase_vocabulary,
    normalize_ticker,
)
from newsaction.states.questions import Battery, canonical_json, load_battery

REACTION_D2: Final = f"{STATES_DIR}/reaction_d2.parquet"
REACTION_D1: Final = f"{STATES_DIR}/reaction_d1.parquet"
CALL_B_D1: Final = f"{STATES_DIR}/callB_d1_E3.parquet"
PRODUCER_D1: Final = "newsaction.states.build --stage d1 (NA-10 S6)"
PERSON_SURNAMES: Final = f"{STATES_DIR}/person_surnames.parquet"
COMPANY_CJK_NAMES: Final = f"{STATES_DIR}/company_cjk_names.parquet"
MARKET_NEWS: Final = "news/market_articles.parquet"
OUTPUT_COLUMNS: Final = (
    "event_id",
    "company_id",
    "session",
    "split",
    "window",
    "call",
    "encoding",
    "masked",
    "state_json",
    "state_sha256",
    "n_tokens_state",
    "n_tokens_with_questions",
    "n_articles",
    "third_party_ok_all",
)
PANEL_T1: Final = (
    "session",
    "symbol_id",
    "company_id",
    "sector",
    "beta_m",
    "sigma_cc",
    "z_m5",
    "z_m20",
    "z_m60",
    "logv_mad60",
)
REACTION_INPUTS: Final = ("ar_cc", "r_cc", "r_spy_cc", "z_vol", "z_cc", "adj_close")
NO_REACTION_KINDS: Final = frozenset({"d1", "d2_reaction"})
B_SPLITS: Final = ("train", "val_a", "val_b")
SOURCE_ORDER: Final = (
    "press_wire_primary",
    "major_outlet",
    "aggregator",
    "retail_analysis",
    "other",
    "auto_generated",
)


class StatesError(ValueError):
    """A state cannot be built as specified (availability, call rule, governance or schema)."""


# --- specs and availability ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateSpec:
    """What one state file contains: the call, the window, the encoding, masking, and per-block inputs."""

    name: str
    call: Call
    window: StateWindow
    encoding: Encoding
    masked: bool
    blocks: Mapping[str, tuple[str, ...]]

    @property
    def decision_point(self) -> pit.DecisionPoint:
        """D0 for W0, D2 for W2; Call B on W0 news is the D1 state (10:00; PREREG §2.5, NA-10)."""
        if self.window == "W0":
            return "D1" if self.call == "B" else "D0"
        return "D2"


def make_spec(
    name: str, call: Call, window: StateWindow, encoding: Encoding, masked: bool, cfg: StatesConfig
) -> StateSpec:
    if call == "M":
        names: tuple[ctx.Block, ...] = ("market", "news")
    elif call == "A":
        names = ("company", "market", "attention", "news")
    else:
        names = ("company", "market", "attention", "news", "reaction_so_far")
    blocks: dict[str, tuple[str, ...]] = {
        b: tuple(ctx.block_columns(b, window, encoding, cfg)) for b in names
    }
    if call == "M":
        blocks["news"] = (
            "market_news_w2",
            "title_masked",
            "snippet_masked",
            "t_avail",
            "source_class_domain",
        )
    if not masked:
        sfx = window.lower()
        blocks["news"] = (f"news_{sfx}", "title_clean", "snippet_clean", "t_avail", "source_class_domain")
    return StateSpec(name, call, window, encoding, masked, blocks)


def validate_spec(spec: StateSpec, registry: pit.AvailabilityRegistry | None = None) -> None:
    """``pit.check_inputs`` for every block, then the call rule (module docstring). Raises ``PITError``."""
    reg = pit.default_registry() if registry is None else registry
    for block, cols in spec.blocks.items():
        reg.check_inputs(cols, spec.decision_point)
        kinds = {c: reg.kind(c) for c in cols}
        if block == "reaction_so_far":
            if spec.call != "B":
                raise pit.PITError(f"{spec.name}: only Call B states have reaction_so_far")
            want = "d1" if spec.decision_point == "D1" else "d2_reaction"
            wrong = {c: k for c, k in kinds.items() if k != want}
            if spec.decision_point not in ("D1", "D2") or wrong:
                raise pit.PITError(
                    f"{spec.name}: reaction_so_far at {spec.decision_point} accepts {want} columns only: "
                    f"{wrong}"
                )
        else:
            late = {c: k for c, k in kinds.items() if k in NO_REACTION_KINDS}
            if late:
                raise pit.PITError(f"{spec.name}: block {block!r} may not read reaction columns {late}")


# --- context stage ------------------------------------------------------------------------------------


def _event_keys(lay: Layout) -> pd.DataFrame:
    cols = ["event_id", "company_id", "session", "symbol_id", "split", "tier"]
    d0 = io.read_parquet(EVENTS_D0, columns=cols, layout=lay)
    d2 = io.read_parquet(EVENTS_D2, columns=cols, layout=lay)
    return pd.concat([d0, d2], ignore_index=True)


def ticker_companies(lay: Layout) -> dict[str, int]:
    """Normalized ticker → company_id from ATOM tickers, price symbols, ATOM symbol_tickers, the NA-02 vendor
    aliases and the curated tickers (``extra_tickers``); ambiguous tickers are dropped."""
    comp = io.read_parquet("panel/companies.parquet", layout=lay)
    pairs: list[tuple[str, int]] = []
    for col in ("ticker", "price_symbol"):
        pairs += [
            (normalize_ticker(str(t)), int(c))
            for t, c in zip(comp[col], comp["company_id"], strict=True)
            if isinstance(t, str)
        ]
    pairs += [(normalize_ticker(t), c) for c, t in extra_tickers(lay)]
    seen: dict[str, set[int]] = {}
    for t, c in pairs:
        seen.setdefault(t, set()).add(c)
    return {t: next(iter(cs)) for t, cs in seen.items() if len(cs) == 1}


def extra_tickers(lay: Layout) -> list[tuple[int, str]]:
    """(company_id, ticker) from ATOM ref.symbol_ticker and the NA-02 vendor aliases (configs/news.yaml)."""
    from newsaction.news import load_news_config

    comp = io.read_parquet("panel/companies.parquet", columns=["symbol_id", "company_id"], layout=lay)
    sym_comp = dict(zip(comp["symbol_id"], comp["company_id"], strict=True))
    st = io.read_parquet("snapshot/symbol_tickers.parquet", columns=["symbol_id", "ticker"], layout=lay)
    out = [
        (int(sym_comp[s]), str(t))
        for s, t in zip(st["symbol_id"], st["ticker"], strict=True)
        if s in sym_comp
    ]
    for a in load_news_config().mapping.aliases:
        if a.symbol_id in sym_comp:
            out.append((int(sym_comp[a.symbol_id]), a.ticker))
    return out


def context_span() -> tuple[date, date]:
    """First and last session of any state: robustness start .. test end (``configs/splits.yaml``)."""
    sp = load_splits().splits
    return sp["robustness"].start, sp["test"].end


def compute_context(lay: Layout, keys: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(company context, market context, D2 reaction) for event ``keys`` (event_id, company_id, session,
    symbol_id, split). Results depend only on each key's own symbol history, so a subset of keys gives the
    same rows as the full build (the determinism check relies on this)."""
    cfg, cb = load_states_config(), load_codebook()
    first, last = context_span()
    grid = ctx.session_grid(first, last, cfg.context.history_sessions)
    symbols = set(keys["symbol_id"].astype("int64"))
    pub = io.read_parquet("panel/panel_public.parquet", columns=[*PANEL_T1, *REACTION_INPUTS], layout=lay)
    pub = pub.loc[pub["symbol_id"].isin(symbols)].reset_index(drop=True)
    test = io.read_parquet("panel/panel_test_inputs.parquet", columns=list(PANEL_T1), layout=lay)
    test = test.loc[test["symbol_id"].isin(symbols)]
    t1 = pd.concat([pub[list(PANEL_T1)], test], ignore_index=True)
    ev_keys = keys[["session", "symbol_id", "company_id"]].drop_duplicates()
    company = ctx.company_context(
        t1.merge(ev_keys[["symbol_id"]].drop_duplicates(), on="symbol_id"),
        pub[["session", "symbol_id", "adj_close"]],
        grid,
        cfg,
    )
    company = ev_keys.merge(company, on=["session", "symbol_id"], how="left")
    company = company.merge(t1.drop(columns=["company_id"]), on=["session", "symbol_id"], how="left")
    est = io.read_parquet("snapshot/estimates_fy1.parquet", layout=lay)
    comp = io.read_parquet(
        "panel/companies.parquet", columns=["symbol_id", "company_id", "sector"], layout=lay
    )
    est = _one_symbol_per_company(est.merge(comp[["symbol_id", "company_id"]], on="symbol_id", how="inner"))
    company = company.merge(
        ctx.eps_revision(ev_keys, est, cfg.context.revision_days, cb),
        on=["company_id", "session"],
        how="left",
    )
    earn = io.read_parquet("market/earnings_dates.parquet", layout=lay)
    flags = ctx.earnings_flags(ev_keys, earn, ticker_companies(lay), load_project().timezone)
    company = company.merge(flags, on=["company_id", "session"], how="left")
    sector = comp.drop_duplicates("company_id").set_index("company_id")["sector"]
    company["sector"] = company["sector"].fillna(company["company_id"].map(sector))
    company = company.sort_values(["session", "company_id", "symbol_id"], kind="mergesort")

    mp = io.read_parquet("market/market_prices.parquet", layout=lay)
    fred = io.read_parquet("market/fred_daily.parquet", layout=lay)
    levels = ctx.series_levels(mp, fred, grid, cfg)
    market = ctx.market_context(levels, grid, cfg)
    cpi = io.read_parquet("market/cpi_vintages.parquet", layout=lay)
    macro = load_macro()
    market = market.merge(session_flags(grid, cpi_release_dates(cpi, macro.cpi_series), macro), on="session")
    market = market.loc[[first <= d <= last for d in market["session"]]]
    reaction = reaction_frame(pub, keys, levels["stock_market"], grid, cfg, lay)
    return company.reset_index(drop=True), market.reset_index(drop=True), reaction


def run_context(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    company, market, reaction = compute_context(lay, _event_keys(lay))
    for frame, rel, desc in (
        (company, CONTEXT_COMPANY, "NA-04 S2: company context through t-1 for every D0/D2 event key"),
        (
            market,
            CONTEXT_MARKET,
            "NA-04 S2: market context through t-1 and scheduled macro releases per session",
        ),
        (
            reaction,
            REACTION_D2,
            "NA-04 S5: D2 reaction inputs of Call B (train, val-A, val-B D2 events only)",
        ),
    ):
        io.write_parquet(frame, rel, producer=PRODUCER, layout=lay, description=desc)
    return {
        "company_rows": len(company),
        "market_rows": len(market),
        "reaction_rows": len(reaction),
        "earnings_w0": int(company["ctx_earnings_w0"].sum()),
        "eps_revision_ok": int(company["ctx_eps_revision"].notna().sum()),
    }


def _one_symbol_per_company(est: pd.DataFrame) -> pd.DataFrame:
    n = est.groupby(["company_id", "symbol_id"]).size().rename("n").reset_index()
    n = n.sort_values(["company_id", "n", "symbol_id"], ascending=[True, False, True]).drop_duplicates(
        "company_id"
    )
    return est.merge(n[["company_id", "symbol_id"]], on=["company_id", "symbol_id"], how="inner")


def reaction_frame(
    pub: pd.DataFrame,
    keys: pd.DataFrame,
    spy_level: np.ndarray,
    grid: Sequence[date],
    cfg: StatesConfig,
    lay: Layout,
) -> pd.DataFrame:
    """D2 reaction inputs for the train / val-A / val-B D2 event keys (never the test period)."""
    from newsaction.panel.reactions import build_reactions

    d2 = keys.loc[
        keys["event_id"].str.startswith("W2:") & keys["split"].isin(B_SPLITS), ["session", "symbol_id"]
    ]
    d2 = d2.drop_duplicates()
    test_start = load_splits().splits["test"].start
    if bool((d2["session"] >= test_start).any()):
        raise StatesError("Call B reactions requested for a test-period session")
    react = build_reactions(pub, "public", "D2", layout=lay)
    react = d2.merge(react, on=["session", "symbol_id"], how="left")
    spy_change = ctx.daily_change(spy_level, "return", 1.0)
    out = ctx.reaction_d2(react, pub[["session", "symbol_id", "z_cc", "logv_mad60"]], spy_change, grid, cfg)
    return out.sort_values(["session", "symbol_id"], kind="mergesort").reset_index(drop=True)


# --- mask stage ---------------------------------------------------------------------------------------


def _text(x: object) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)


def event_articles(lay: Layout) -> pd.DataFrame:
    """Unique (id, company_id, title, snippet) of every listed article of every D0 / D2 event."""
    rows: list[tuple[str, int, str, str]] = []
    for rel, col in ((EVENTS_D0, "news_w0"), (EVENTS_D2, "news_w2")):
        ev = io.read_parquet(rel, columns=["company_id", col], layout=lay)
        for cid, items in zip(ev["company_id"], ev[col], strict=True):
            rows += [(str(a["id"]), int(cid), _text(a["title"]), _text(a["snippet"])) for a in items]
    out = pd.DataFrame(rows, columns=["id", "company_id", "title", "snippet"]).drop_duplicates()
    if out["id"].duplicated().any():
        raise StatesError("an article appears with two different texts or companies across event lists")
    return out.sort_values("id", kind="mergesort").reset_index(drop=True)


@dataclass(frozen=True)
class LanguageRule:
    """``configs/states.yaml`` ``news_exclusion.non_english``, compiled (``non_english``)."""

    script: re.Pattern[str]
    min_script_chars: int
    foreign: re.Pattern[str]
    english: re.Pattern[str]
    min_foreign: int
    diacritic_word: re.Pattern[str]
    min_diacritic_words: int
    max_english_with_diacritics: int
    place_names: re.Pattern[str]


def _word_forms(words: str) -> str:
    """Each word in lower case or capitalized (not in capitals: a ticker such as DE is not "de")."""
    forms = {f for w in words.split() for f in (w, w[:1].upper() + w[1:])}
    return "|".join(re.escape(f).replace("'", "['’]") for f in sorted(forms, key=len, reverse=True))


@functools.cache
def language_rule(cfg: NonEnglishConfig) -> LanguageRule:
    word = r"(?<![\w'’-])(?:{})(?![\w'’-])"
    return LanguageRule(
        script=re.compile(cfg.script),
        min_script_chars=cfg.min_script_chars,
        foreign=re.compile(word.format(_word_forms(cfg.foreign_words))),
        english=re.compile(word.format(_word_forms(cfg.english_words))),
        min_foreign=cfg.min_foreign,
        diacritic_word=re.compile(rf"(?<!\w)\w*[{re.escape(cfg.diacritics)}]\w*(?!\w)"),
        min_diacritic_words=cfg.min_diacritic_words,
        max_english_with_diacritics=cfg.max_english_with_diacritics,
        place_names=re.compile(cfg.place_names),
    )


def non_english(text: str, cfg: NonEnglishConfig) -> bool:
    """Operator decision B (PREREG §15 NA-04 row 8): the masker and the price-talk scrubbers are English-only,
    so a non-English article is in no state. The rule is in ``configs/states.yaml``."""
    r = language_rule(cfg)
    if len(r.script.findall(text)) >= r.min_script_chars:
        return True
    text = r.place_names.sub(" ", text)
    foreign = {w.lower().replace("’", "'") for w in r.foreign.findall(text)}
    english = {w.lower() for w in r.english.findall(text)}
    if len(foreign) >= r.min_foreign and len(foreign) > len(english):
        return True
    if len(foreign) >= r.min_foreign - 1 and not english:
        return True
    marked = {w.lower() for w in r.diacritic_word.findall(text)}
    return len(marked) >= r.min_diacritic_words and len(english) <= r.max_english_with_diacritics


def non_english_ids(articles: pd.DataFrame, cfg: StatesConfig) -> frozenset[str]:
    """Ids of the non-English articles (``non_english`` on NA-02's raw title + snippet)."""
    rule = cfg.news_exclusion.non_english
    texts = articles["title"].fillna("").astype(str) + " " + articles["snippet"].fillna("").astype(str)
    hit = [non_english(t, rule) for t in texts]
    return frozenset(articles.loc[hit, "id"].astype(str))


def excluded_ids(articles: pd.DataFrame, cfg: StatesConfig) -> frozenset[str]:
    """Ids of the articles left out of every state (``configs/states.yaml`` ``news_exclusion``): move
    explainers ("Why … Stock Is Up Today", StockStory's "What Happened? Shares of …") and TradingView reposts
    (PREREG §15 NA-04 row 6), and non-English articles (row 8). ``articles``: id, ``domain`` and NA-02's raw
    ``title`` and ``snippet``."""
    ex = cfg.news_exclusion
    hit = articles["title"].fillna("").astype(str).str.contains(ex.title, regex=True)
    hit |= articles["snippet"].fillna("").astype(str).str.contains(ex.snippet, regex=True)
    hit |= articles["domain"].fillna("").astype(str).str.contains(ex.domain, regex=True)
    return frozenset(articles.loc[hit, "id"].astype(str)) | non_english_ids(articles, cfg)


# --- running market stories: W0 states only (PREREG §15 NA-04 row 10, revision 6) -----------------------

SNIPPET_LEAD: Final = 40  # characters of a snippet where an overseas market would be its subject
WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_STORY_SENTENCES: Final = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'“‘(])|\n+")
_EXCHANGE_TICKER: Final = re.compile(  # "(NASDAQ:NDAQ)", "NYSE: DOW", "(DOW)" are tickers, not the index
    r"\((?:NASDAQ|NYSE|NYSEAMERICAN|NYSEARCA|AMEX|ARCA|OTC\w*)[^)]*\)"
    r"|\b(?:NASDAQ|NYSE|Nasdaq|NYSEAMERICAN|NYSEARCA)\s?:\s?[A-Z][A-Z.]*|\([A-Z][A-Z.\-]{0,6}\)"
)
# a ticker becomes this mark, not a space: "Nasdaq (NASDAQ:NDAQ) Trading 2% Higher" keeps the "(" that tells
# the company from the index
TICKER_MARK: Final = " (T) "


@dataclass(frozen=True)
class StoryRule:
    """``configs/states.yaml`` ``news_exclusion.running_story``, compiled (``running_story``)."""

    live_title: re.Pattern[str]
    live_snippet: re.Pattern[str]
    clock: re.Pattern[str]
    clock_before: re.Pattern[str]
    clock_after: re.Pattern[str]
    foreign_zone: re.Pattern[str]
    european: re.Pattern[str]
    market_subject: re.Pattern[str]
    close_verb: re.Pattern[str]
    premarket: re.Pattern[str]
    forecast: re.Pattern[str]
    wire: re.Pattern[str]
    schedule: re.Pattern[str]
    asia: re.Pattern[str]
    overseas: re.Pattern[str]
    intraday: re.Pattern[str]
    wrap_title: re.Pattern[str]
    wrap_veto: re.Pattern[str]


@functools.cache
def story_rule(cfg: RunningStoryConfig) -> StoryRule:
    return StoryRule(**{name: re.compile(getattr(cfg, name)) for name in cfg.patterns})


_WEEKDAY: Final = re.compile(rf"\b({'|'.join(WEEKDAYS)})\b")


def live_format(title: str, snippet: str, r: StoryRule) -> bool:
    """Rule 1: a live blog or a running page ("Stock market today: …", "Markets News, July 16, 2025: …",
    "Live Updates Live Coverage …"), whatever its stamp."""
    return r.live_title.search(title) is not None or r.live_snippet.search(snippet) is not None


def post_open_clock(text: str, open_minutes: int, shift: int, r: StoryRule) -> bool:
    """Rule 2 (an article stamped on the calendar date of s): a live entry or an update at or after the open
    ("4:15pm: Muted close", "10:54 am by …", "Updated at 10:28 AM EST"). ``open_minutes``: the open of s in
    minutes after local midnight; ``shift``: minutes the text's clock runs ahead of New York (London's for an
    article about a European market: "12.30pm" on a FTSE page is 07:30 ET)."""
    if r.schedule.search(text):
        return False
    for m in r.clock.finditer(text):
        hour, minute = int(m.group(1)), int(m.group(2))
        if not 1 <= hour <= 12 or minute > 59:
            continue
        local = (hour % 12 + (12 if m.group(3).lower() == "p" else 0)) * 60 + minute - shift
        after = text[m.end() :]
        if local < open_minutes or r.foreign_zone.match(after):
            continue
        if r.clock_after.match(after) or r.clock_before.search(text[: m.start()]):
            return True
    return False


def closed_on(text: str, weekday: str, r: StoryRule) -> bool:
    """Rule 3: in one sentence, a market subject and a close verb whose nearest weekday is that of s ("The
    S&P 500 ended Tuesday's choppy session", "closed modestly higher on Wednesday"), or "<weekday> close";
    not pre-market, a schedule or an Asian market, which closes before the US open."""
    noun = re.compile(rf"\b{weekday}(?:['’]s)?\s+close\b", re.IGNORECASE)
    for sentence in _STORY_SENTENCES.split(_EXCHANGE_TICKER.sub(TICKER_MARK, text)):
        if (
            r.market_subject.search(sentence) is None
            or r.premarket.search(sentence)
            or r.schedule.search(sentence)
            or r.asia.search(sentence)
        ):
            continue
        if noun.search(sentence):
            return True
        for v in r.close_verb.finditer(sentence):
            near = [
                (d.start() - v.end(), d.group(1)) for d in _WEEKDAY.finditer(sentence, v.end(), v.end() + 75)
            ]
            near += [
                (v.start() - d.end(), d.group(1))
                for d in _WEEKDAY.finditer(sentence, max(0, v.start() - 45), v.start())
            ]
            if near and min(near)[1] == weekday:
                return True
    return False


def intraday(text: str, weekday: str, same_day: bool, r: StoryRule) -> bool:
    """Rule 4: running intraday wording about the market ("U.S. stocks are drifting", "Wall Street … in early
    trading", "opened lower") in an article stamped on the calendar date of s or naming its weekday: a market
    subject in the sentence, or a Reuters text (its style keeps "premarket" for before the open). Not with
    pre-market words or another weekday in the sentence, nor a forecast or an overseas market before the
    phrase ("stocks may show a lack of direction in early trading"; "European stock indexes opened lower":
    overseas markets trade before the US open). A company's "shares rose in early trading" before the open is
    mostly pre-market and does not count."""
    wire = r.wire.search(text) is not None
    for sentence in _STORY_SENTENCES.split(_EXCHANGE_TICKER.sub(TICKER_MARK, text)):
        phrase = r.intraday.search(sentence)
        if phrase is None or r.premarket.search(sentence):
            continue
        if not wire and r.market_subject.search(sentence) is None:
            continue
        before = sentence[: phrase.start()]
        if r.forecast.search(before) or r.overseas.search(before):
            continue
        days = set(_WEEKDAY.findall(sentence))
        if days - {weekday}:
            continue
        if same_day or weekday in days:
            return True
    return False


def morning_wrap(title: str, snippet: str, same_day: bool, r: StoryRule) -> bool:
    """Rule 5 (an article stamped on the calendar date of s): a title opening, or opening a clause, with a
    US-market subject and a move or close word ("Dow Swings To Drop 224 Points; Nasdaq Ekes Out A Gain" at
    08:07 ET). Not with futures, pre-market or question words in the title, a forecast or an overseas word up
    to the move word ("RBC sees S&P 500 …"), pre-market words in the snippet, or an overseas market opening
    its first sentence ("EU mid-market update: Stocks open higher")."""
    if not same_day or r.wrap_veto.search(title):
        return False
    bare = _EXCHANGE_TICKER.sub(TICKER_MARK, title)
    m = r.wrap_title.search(bare)
    if m is None or r.forecast.search(bare[: m.end()]) or r.overseas.search(bare[: m.end()]):
        return False
    first = _STORY_SENTENCES.split(snippet, maxsplit=1)[0]
    return not (r.premarket.search(snippet) or r.overseas.search(first[:SNIPPET_LEAD]))


def running_story(title: str, snippet: str, t_avail: pd.Timestamp, cfg: RunningStoryConfig) -> bool:
    """A running market story in W0 of its session (PREREG §15 NA-04 row 10): live blogs and running market
    reports keep their first stamp while their text is the latest version, so in W0 they carry the session's
    own cash-market outcome. Rules 1–5 are in ``configs/states.yaml``. False outside every W0."""
    s = calendar.session_of_w0(t_avail)
    if s is None:
        return False
    r = story_rule(cfg)
    tz = ZoneInfo(load_project().timezone)
    opens = calendar.open_utc(s).tz_convert(tz)
    weekday = WEEKDAYS[s.weekday()]
    same_day = t_avail.tz_convert(tz).date() == s
    london = opens.tz_convert(ZoneInfo(cfg.european_zone))
    european = r.european.search(f"{title} {snippet}") is not None
    shift = (london.hour - opens.hour) * 60 + london.minute - opens.minute if european else 0
    texts = (title, snippet)
    return (
        live_format(title, snippet, r)
        or (same_day and any(post_open_clock(t, opens.hour * 60 + opens.minute, shift, r) for t in texts))
        or any(closed_on(t, weekday, r) or intraday(t, weekday, same_day, r) for t in texts)
        or morning_wrap(title, snippet, same_day, r)
    )


def running_story_ids(articles: pd.DataFrame, cfg: StatesConfig) -> frozenset[str]:
    """Ids of the running market stories (``running_story``), left out of W0 states only: W2 ends at the
    close, so there the same text is inside the window. ``articles``: id, ``t_avail`` and NA-02's raw
    ``title`` and ``snippet``. Chunks that read W0 articles directly should leave these out too."""
    rule = cfg.news_exclusion.running_story
    t_avail = pd.to_datetime(articles["t_avail"], utc=True)
    hit = [
        running_story(_text(t), _text(s), ts, rule)
        for t, s, ts in zip(articles["title"], articles["snippet"], t_avail, strict=True)
    ]
    return frozenset(articles.loc[hit, "id"].astype(str))


def market_selection(lay: Layout, cfg: StatesConfig) -> pd.DataFrame:
    """A3.5 market-state articles: per W2 session, third-party-OK market-index articles with text, excluded
    articles left out (``excluded_ids``), near-identical titles dropped, ordered by source class then t_avail,
    at most ``max_articles`` and ``max_news_tokens``."""
    m = io.read_parquet(MARKET_NEWS, layout=lay)
    sp = load_splits()
    keep = m["third_party_ok"].astype(bool) & m["session_w2"].notna()
    keep &= (m["title_clean"].fillna("").str.len() + m["snippet_clean"].fillna("").str.len()) > 0
    keep &= ~m["id"].astype(str).isin(excluded_ids(m, cfg))
    m = m.loc[keep].copy()
    m["split"] = m["session_w2"].map(lambda d: sp.split_of(d) or "")
    m = m.loc[m["split"].isin(cfg.market_states.splits)]
    rank = {c: i for i, c in enumerate(SOURCE_ORDER)}
    m["src_rank"] = m["source_class_domain"].map(lambda c: rank.get(c, len(rank)))
    m["title_key"] = m["title_clean"].fillna("").str.lower().str.replace(r"\W+", " ", regex=True).str.strip()
    m = m.sort_values(["session_w2", "src_rank", "t_avail", "id"], kind="mergesort")
    m = m.drop_duplicates(["session_w2", "title_key"])
    m = m.groupby("session_w2", sort=True).head(cfg.market_states.max_articles)
    tok = tokens.tokenizer(load_events_config().events)
    enc, off = tokens.hf_encode(tok), tokens.hf_offsets(tok)
    kept = []
    for _, g in m.groupby("session_w2", sort=True):
        arts = [
            tokens.ArticleText(_text(t), _text(s))
            for t, s in zip(g["title_clean"], g["snippet_clean"], strict=True)
        ]
        capped = tokens.cap_articles(arts, cfg.market_states.max_news_tokens, enc, off)
        sub = g.iloc[: len(capped.articles)].copy()
        sub["title"] = [a.title for a in capped.articles]
        sub["snippet"] = [a.snippet for a in capped.articles]
        kept.append(sub)
    out = pd.concat(kept, ignore_index=True)
    return out[
        ["id", "session_w2", "split", "t_avail", "source_class_domain", "title", "snippet", "third_party_ok"]
    ]


def run_mask(layout: Layout | None = None, n_process: int = 4) -> dict[str, Any]:
    lay = resolve_layout(layout)
    arts = event_articles(lay)
    market = market_selection(lay, load_states_config())
    mk = masker(lay, vocabulary=True)
    masked = mask_frame(arts, market, lay, n_process=n_process, mk=mk)
    io.write_parquet(
        pd.DataFrame({"surname": sorted(mk.surnames)}),
        PERSON_SURNAMES,
        producer=PRODUCER,
        layout=lay,
        description="NA-04 S3: corpus surnames masked wherever they appear (last words of multi-word PERSON "
        f"names seen >= {SURNAME_MIN_COUNT} times in the event and market articles)",
    )
    io.write_parquet(
        pd.DataFrame(
            [(cid, n) for cid, names in sorted(mk.cjk_names.items()) for n in names],
            columns=["company_id", "name"],
        ).astype({"company_id": "int64"}),
        COMPANY_CJK_NAMES,
        producer=PRODUCER,
        layout=lay,
        description="NA-04 S3: Chinese / Japanese / Korean company names masked in the company's texts "
        "(the CJK words right before its own ticker in parentheses in the event articles)",
    )
    io.write_parquet(
        masked,
        ARTICLES_MASKED,
        producer=PRODUCER,
        layout=lay,
        description="NA-04 S3: masked title / snippet of every event article and A3.5 market article",
    )
    return {
        "articles": int((masked["kind"] == "company").sum()),
        "market_articles": int((masked["kind"] == "market").sum()),
        "names": int(masked["n_names"].sum()),
        "tickers": int(masked["n_tickers"].sum()),
        "dates": int(masked["n_dates"].sum()),
        "persons": int(masked["n_persons"].sum()),
        "corpus_surnames": len(mk.surnames),
        "cjk_names": sum(len(v) for v in mk.cjk_names.values()),
        "cjk_name_companies": len(mk.cjk_names),
    }


VOCAB_MIN_COUNT: Final = 20


def load_surnames(lay: Layout) -> frozenset[str]:
    """The corpus surnames the mask stage derived (``person_surnames.parquet``)."""
    return frozenset(io.read_parquet(PERSON_SURNAMES, layout=lay)["surname"].astype(str))


def masker(lay: Layout, *, vocabulary: bool = False, surnames: frozenset[str] | None = None) -> Masker:
    """The masker of every company in ``panel/companies.parquet``. ``vocabulary``: also derive the ordinary
    lower-case words from the text of every event article (needed for person names) and the companies'
    Chinese, Japanese and Korean names (``cjk_company_names``). ``surnames``: the corpus surnames; None
    derives them from the texts the masker is given (the mask stage)."""
    comp = io.read_parquet(
        "panel/companies.parquet", columns=["symbol_id", "company_id", "ticker", "name"], layout=lay
    )
    aliases = build_aliases(comp, extra_tickers(lay))
    vocab: frozenset[str] = frozenset()
    cjk: dict[int, tuple[str, ...]] = {}
    if vocabulary:
        arts = event_articles(lay)
        vocab = lowercase_vocabulary([*arts["title"], *arts["snippet"]], VOCAB_MIN_COUNT)
        cjk = cjk_company_names(arts, aliases)
    return Masker(aliases, vocabulary=vocab, surnames=surnames, cjk_names=cjk)


def mask_frame(
    arts: pd.DataFrame, market: pd.DataFrame, lay: Layout, *, n_process: int = 1, mk: Masker | None = None
) -> pd.DataFrame:
    """Masked texts: company articles (``arts``: id, company_id, title, snippet) and market articles."""
    mk = masker(lay, vocabulary=True) if mk is None else mk
    items: list[tuple[str, int | None, bool]] = []
    for cid, t, s in zip(arts["company_id"], arts["title"], arts["snippet"], strict=True):
        items += [(t, int(cid), True), (s, int(cid), False)]
    for t, s in zip(market["title"], market["snippet"], strict=True):
        items += [(_text(t), None, True), (_text(s), None, False)]
    groups = [i // 2 for i in range(len(items))]  # an article's title and snippet
    res = mk.mask_texts(items, groups=groups, n_process=n_process)
    titles, snippets = res[0::2], res[1::2]
    frame = pd.DataFrame(
        {
            "id": [*arts["id"], *market["id"]],
            "kind": ["company"] * len(arts) + ["market"] * len(market),
            "company_id": [*arts["company_id"].astype("int64"), *([-1] * len(market))],
            "title_masked": [t for t, _ in titles],
            "snippet_masked": [s for s, _ in snippets],
        }
    )
    for name in ("names", "tickers", "dates", "persons"):
        frame[f"n_{name}"] = [
            getattr(a, name) + getattr(b, name) for (_, a), (_, b) in zip(titles, snippets, strict=True)
        ]
    return frame


# --- states stage -------------------------------------------------------------------------------------


@dataclass
class Inputs:
    """Everything a state needs, keyed for lookup."""

    company: pd.DataFrame  # context_company (session, symbol_id)
    market: pd.DataFrame  # context_market (session)
    reaction: pd.DataFrame  # reaction_d2 (session, symbol_id)
    masked: Mapping[str, tuple[str, str]]  # article id -> (title, snippet)
    third_party: Mapping[str, bool]  # article id -> third_party_ok
    reaction_d1: pd.DataFrame | None = None  # reaction_d1 (session, symbol_id), the D1 stage only (NA-10)
    excluded: frozenset[str] = (
        frozenset()
    )  # explainers, TradingView reposts and non-English articles (``excluded_ids``), in no state
    non_english: frozenset[str] = frozenset()  # the non-English ones among them (counted apart)
    excluded_w0: frozenset[str] = frozenset()  # running market stories (``running_story_ids``): no W0 state
    cb: Codebook = field(default_factory=load_codebook)


def load_inputs(lay: Layout, masked_frame: pd.DataFrame | None = None) -> Inputs:
    """Context, reaction, masked texts and the excluded articles (in every window, and in W0 only);
    ``masked_frame`` replaces work/states/articles_masked.parquet (the determinism check rebuilds it from
    scratch)."""
    masked = (
        io.read_parquet(ARTICLES_MASKED, columns=["id", "title_masked", "snippet_masked"], layout=lay)
        if masked_frame is None
        else masked_frame
    )
    tp = io.read_parquet(
        ARTICLES, columns=["id", "third_party_ok", "domain", "title", "snippet", "t_avail"], layout=lay
    )
    tp = tp.loc[tp["id"].isin(set(masked["id"]))]
    mk = masked.set_index("id")
    cfg = load_states_config()
    return Inputs(
        company=io.read_parquet(CONTEXT_COMPANY, layout=lay),
        market=io.read_parquet(CONTEXT_MARKET, layout=lay),
        reaction=io.read_parquet(REACTION_D2, layout=lay),
        masked={
            i: (t, s) for i, t, s in zip(mk.index, mk["title_masked"], mk["snippet_masked"], strict=True)
        },
        third_party=dict(zip(tp["id"], tp["third_party_ok"].astype(bool), strict=True)),
        excluded=excluded_ids(tp, cfg),
        non_english=non_english_ids(tp, cfg),
        excluded_w0=running_story_ids(tp, cfg),
    )


def skipped(inp: Inputs, window: StateWindow) -> frozenset[str]:
    """The articles no state of ``window`` carries: ``Inputs.excluded``, and in W0 also the running market
    stories (``Inputs.excluded_w0``)."""
    return inp.excluded | inp.excluded_w0 if window == "W0" else inp.excluded


def news_items(
    items: Sequence[Mapping[str, Any]], session: date, masked: bool, inp: Inputs, window: StateWindow
) -> tuple[list[dict[str, str]], list[str]]:
    """The ``news`` block and its article ids, in list order. Raises if an article is not third-party OK
    (CLAUDE.md D15); an excluded article (``skipped``) and an article whose title and snippet are both empty
    are left out."""
    out: list[dict[str, str]] = []
    ids: list[str] = []
    skip = skipped(inp, window)
    for a in items:
        aid = str(a["id"])
        if inp.third_party.get(aid) is not True:
            raise StatesError(f"article {aid} is not third-party OK (CLAUDE.md D15)")
        if aid in skip:
            continue
        if masked:
            title, snippet = inp.masked[aid]
        else:
            title, snippet = _text(a["title"]), _text(a["snippet"])
        if not (title or snippet):
            continue
        ids.append(aid)
        out.append(
            {
                "headline": title,
                "snippet": snippet,
                "source_type": inp.cb.source_type_word(a["source_class_domain"]),
                "timing": inp.cb.timing_word(a["t_avail"], session),
            }
        )
    return out, ids


@dataclass(frozen=True)
class Budget:
    """State token budget (PRD NA-04 S6 tightening): ``cap`` = 1,024 − special tokens − the longest core
    question. ``reserve`` is a block counted but not emitted: the longest possible ``reaction_so_far``, so
    that a D2 news list fits Call B too and never depends on the observed reaction."""

    tok: Any
    cap: int
    reserve: Mapping[str, Any] | None = None

    def count(self, state: Mapping[str, Any]) -> int:
        probe = dict(state) if self.reserve is None else {**state, "reaction_so_far": self.reserve}
        return len(self.tok(canonical_json(probe), add_special_tokens=False)["input_ids"])


def fit_news(state: dict[str, Any], ids: list[str], budget: Budget) -> tuple[list[str], bool]:
    """Drop the lowest-ranked articles until the state fits ``budget`` (at least one stays); if one article
    still does not fit, cut its snippet, then its headline, by words. Returns the kept ids and whether a text
    was cut. ``state["news"]`` is changed in place."""
    news = state["news"]
    while len(news) > 1 and budget.count(state) > budget.cap:
        news.pop()
        ids = ids[:-1]
    cut = False
    for field_name in ("snippet", "headline"):
        words = news[0][field_name].split() if news else []
        while news and words and budget.count(state) > budget.cap:
            words = words[: int(len(words) * 0.9)]
            news[0][field_name] = " ".join(words)
            cut = True
    if budget.count(state) > budget.cap:
        raise StatesError(f"a state does not fit {budget.cap} tokens even with one empty article")
    return ids, cut


def budgets(
    tok: Any, qtok: Mapping[str, Mapping[str, int]], cfg: StatesConfig, cb: Codebook
) -> dict[str, Budget]:
    """The D0 budget (Call A questions) and the D2 budget (Call B questions, reaction reserved)."""
    t = cfg.tokens
    return {
        "W0": Budget(tok, t.total_max - t.special_tokens - qtok["A"]["longest_core"]),
        "W2": Budget(
            tok,
            t.total_max - t.special_tokens - max(qtok["A"]["longest_core"], qtok["B"]["longest_core"]),
            worst_reaction(tok, cb),
        ),
    }


def worst_reaction(tok: Any, cb: Codebook, point: str = "D2") -> dict[str, Any]:
    """The E3 ``reaction_so_far`` block with the longest phrase (in tokens) in every field (at D2, or at D1
    with its moves in typical close(prev) → 10:00 moves)."""
    zs = [round(x, 2) for x in np.arange(-10.0, 10.0001, 0.05)]

    def longest(phrases: Iterable[str]) -> str:
        size = {p: len(tok(json.dumps(p, ensure_ascii=False))["input_ids"]) for p in set(phrases)}
        return min(size, key=lambda p: (-size[p], p))

    horizon: Horizon = "d1" if point == "D1" else "day"
    move = longest(cb.encode_move(Move(z=z, horizon=horizon), "E3") for z in zs)
    volume = longest([*cb.attention.words, cb.missing])
    return {
        "time": cb.time_label_word("D1" if point == "D1" else "D2"),
        "stock_move_vs_market_and_sector": move,
        "stock_market_move": move,
        "volume_vs_normal": volume,
    }


def render_state(
    spec: StateSpec, values: Mapping[str, Any], news: list[dict[str, str]], inp: Inputs, cfg: StatesConfig
) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for block, cols in spec.blocks.items():
        if block == "news":
            state["news"] = news
            continue
        row = ctx.Row(values, cols)
        if block == "company":
            state["company"] = ctx.company_block(row, spec.window, spec.encoding, inp.cb, cfg)
        elif block == "market":
            state["market"] = ctx.market_block(row, spec.encoding, inp.cb, cfg, load_macro())
        elif block == "attention":
            state["attention"] = ctx.attention_block(row, spec.window, inp.cb)
        elif block == "reaction_so_far":
            state["reaction_so_far"] = ctx.reaction_block(row, spec.encoding, inp.cb, spec.decision_point)
        else:
            raise StatesError(f"unknown block {block!r}")
    return state


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(k): (None if v is pd.NA else v) for k, v in rec.items()} for rec in frame.to_dict("records")]


def build_event_states(
    events: pd.DataFrame,
    spec: StateSpec,
    inp: Inputs,
    cfg: StatesConfig,
    *,
    budget: Budget | None = None,
    keep: Mapping[str, Sequence[str]] | None = None,
    allow_test: bool = False,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """States of ``events`` (rows of events_d0 / events_d2) under ``spec`` (validated first), and the article
    ids each state kept. ``budget`` fits each state's news list (``fit_news``); ``keep`` instead reuses the
    ids an earlier build kept, so the same event has the same news across encodings, masking and calls. An
    event with no article text left after masking gets no state. ``allow_test`` admits test-period Call B
    events; only NA-11's post-freeze build passes it, after checking the freeze
    (``production.states_test``)."""
    validate_spec(spec)
    sfx = spec.window.lower()
    if spec.call == "B":
        allowed = (*B_SPLITS, "test") if allow_test else B_SPLITS
        bad = events.loc[~events["split"].isin(allowed)]
        if len(bad):
            raise StatesError(
                f"{spec.name}: Call B refuses {len(bad)} events outside {B_SPLITS} (no test-period Call B)"
            )
    frame = events.merge(inp.company, on=["session", "symbol_id"], how="left", suffixes=("", "_ctx"))
    frame = frame.merge(inp.market, on="session", how="left")
    if spec.call == "B":
        react = inp.reaction_d1 if spec.decision_point == "D1" else inp.reaction
        if react is None:
            raise StatesError(f"{spec.name}: no D1 reaction inputs (the d1 stage loads them)")
        frame = frame.merge(react, on=["session", "symbol_id"], how="left")
    rows, kept = [], {}
    skip = skipped(inp, spec.window)
    for rec in _records(frame):
        eid = str(rec["event_id"])
        news, ids = news_items(rec[f"news_{sfx}"], rec["session"], spec.masked, inp, spec.window)
        if keep is not None:
            want = set(keep[eid])
            news = [n for n, i in zip(news, ids, strict=True) if i in want]
            ids = [i for i in ids if i in want]
        values = {
            **rec,
            "title_masked": None,
            "snippet_masked": None,
            "title_clean": None,
            "snippet_clean": None,
            "t_avail": None,
            "source_class_domain": None,
        }
        state = render_state(spec, values, news, inp, cfg)
        cut = False
        if budget is not None:
            ids, cut = fit_news(state, ids, budget)
        kept[eid] = ids
        if not state["news"]:
            continue  # every article was price talk or empty after masking: no news, no state
        js = canonical_json(state)
        rows.append(
            {
                "event_id": eid,
                "company_id": int(rec["company_id"]),
                "session": rec["session"],
                "split": rec["split"],
                "window": spec.window,
                "call": spec.call,
                "encoding": spec.encoding,
                "masked": spec.masked,
                "state_json": js,
                "state_sha256": hashlib.sha256(js.encode("utf-8")).hexdigest(),
                "n_articles": len(state["news"]),
                "third_party_ok_all": True,
                "_cut": cut,
                "_listed": sum(str(a["id"]) not in skip for a in rec[f"news_{sfx}"]),
            }
        )
    return pd.DataFrame(rows), kept


def build_market_states(sel: pd.DataFrame, spec: StateSpec, inp: Inputs, cfg: StatesConfig) -> pd.DataFrame:
    validate_spec(spec)
    mk = inp.market.set_index("session")
    rows = []
    for key, g in sel.groupby("session_w2", sort=True):
        session = cast(date, key)
        items = g.to_dict("records")
        news = []
        for a in items:
            if not bool(a["third_party_ok"]):
                raise StatesError(f"market article {a['id']} is not third-party OK")
            title, snippet = inp.masked[str(a["id"])]
            if title or snippet:
                news.append(
                    {
                        "headline": title,
                        "snippet": snippet,
                        "source_type": inp.cb.source_type_word(a["source_class_domain"]),
                        "timing": inp.cb.timing_word(a["t_avail"], session),
                    }
                )
        if not news:
            continue  # every article lost its text (since revision 5, index wraps): no state, as for an event
        values = {
            **{str(k): v for k, v in mk.loc[session].to_dict().items()},
            "market_news_w2": None,
            "title_masked": None,
            "snippet_masked": None,
            "t_avail": None,
            "source_class_domain": None,
        }
        state = render_state(spec, values, news, inp, cfg)
        js = canonical_json(state)
        rows.append(
            {
                "event_id": f"M:{session.isoformat()}",
                "company_id": -1,
                "session": session,
                "split": g["split"].iloc[0],
                "window": spec.window,
                "call": spec.call,
                "encoding": spec.encoding,
                "masked": spec.masked,
                "state_json": js,
                "state_sha256": hashlib.sha256(js.encode("utf-8")).hexdigest(),
                "n_articles": len(news),
                "third_party_ok_all": True,
            }
        )
    return pd.DataFrame(rows)


def question_tokens(battery: Battery, tok: Any) -> dict[str, dict[str, int]]:
    """Tokens of each call's request ``questions`` object (core, core+extended/explain) and its longest single
    core question, each as canonical JSON."""
    out: dict[str, dict[str, int]] = {}
    for call, extra in (("A", "extended"), ("B", "explain")):
        core = battery.request(call, ["core"])
        single = [
            len(tok(canonical_json({k: v}), add_special_tokens=False)["input_ids"]) for k, v in core.items()
        ]
        out[call] = {
            "core": len(tok(canonical_json(core), add_special_tokens=False)["input_ids"]),
            "all": len(
                tok(canonical_json(battery.request(call, ["core", extra])), add_special_tokens=False)[
                    "input_ids"
                ]
            ),
            "longest_core": max(single),
        }
    out["M"] = out["A"]
    return out


def add_tokens(df: pd.DataFrame, tok: Any, qtok: Mapping[str, Mapping[str, int]]) -> pd.DataFrame:
    counts: list[int] = []
    texts = df["state_json"].tolist()
    for i in range(0, len(texts), 5000):
        counts += tokens.count_batch(tok, texts[i : i + 5000])
    df = df.copy()
    df["n_tokens_state"] = np.asarray(counts, dtype=np.int64)
    df["n_tokens_with_questions"] = df["n_tokens_state"] + df["call"].map(lambda c: qtok[c]["core"]).astype(
        "int64"
    )
    return df[list(OUTPUT_COLUMNS)]


def stratified_sample(events: pd.DataFrame, n: int, strata: Sequence[str], seed: int | str) -> pd.DataFrame:
    """Proportional allocation over ``strata`` (largest remainder, ties by stratum order), then the ``n_h``
    events with the smallest u = sha256("{seed}:{event_id}") in each stratum (``seed`` may carry a purpose,
    as NA-11's "2026:ablation")."""
    if n > len(events):
        raise StatesError(f"cannot sample {n} of {len(events)} events")
    ev = events.copy()
    ev["_u"] = [int(hashlib.sha256(f"{seed}:{e}".encode()).hexdigest()[:16], 16) for e in ev["event_id"]]
    size = ev.groupby(list(strata), sort=True).size()
    exact = size / size.sum() * n
    quota = (exact // 1).astype(int)
    rest = int(n - quota.sum())
    order = (exact - quota).sort_values(ascending=False, kind="mergesort").index[:rest]
    quota.loc[order] += 1
    take = {k: int(v) for k, v in zip(quota.index, quota.to_numpy(), strict=True)}
    parts = [
        g.sort_values(["_u", "event_id"], kind="mergesort").head(take[key])
        for key, g in ev.groupby(list(strata), sort=True)
    ]
    out = pd.concat(parts).drop(columns=["_u"])
    return out.sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def sample_frames(d0: pd.DataFrame, cfg: StatesConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(1,500 val-A + 1,500 val-B D0 events for E0–E4, 1,000 val-A D0 events for the unmasked twin)."""
    s = cfg.samples
    pool = d0.loc[~d0["embargo"].astype(bool)] if s.exclude_embargo else d0
    va, vb = pool.loc[pool["split"] == "val_a"], pool.loc[pool["split"] == "val_b"]
    enc = pd.concat(
        [
            stratified_sample(va, s.encodings_val_a, s.strata, s.seed),
            stratified_sample(vb, s.encodings_val_b, s.strata, s.seed),
        ],
        ignore_index=True,
    )
    twin = stratified_sample(va, s.unmasked_val_a, s.strata, s.seed)
    return enc, twin


OUTPUTS: Final = ("callA_d0_E3", "callA_d2_E3", "callB_d2_E3", "market_E3")


def write_states(
    df: pd.DataFrame, rel: str, description: str, lay: Layout, producer: str = PRODUCER
) -> dict[str, Any]:
    df = df.sort_values(["session", "company_id", "event_id"], kind="mergesort").reset_index(drop=True)
    return io.write_parquet(df, rel, producer=producer, description=description, layout=lay)


def exclusion_counts(
    events: pd.DataFrame,
    col: str,
    excluded: frozenset[str],
    non_english: frozenset[str] = frozenset(),
    running: frozenset[str] = frozenset(),
) -> tuple[int, int, int, int]:
    """(listed excluded articles, events whose every listed article is excluded, listed non-English
    articles, listed running market stories not excluded otherwise) of an event frame; ``excluded`` includes
    ``running`` for a W0 frame."""
    ids = [[str(a["id"]) for a in items] for items in events[col]]
    flags = [[i in excluded for i in row] for row in ids]
    n_foreign = sum(i in non_english for row in ids for i in row)
    n_running = sum(i in running for row in ids for i in row)
    return sum(sum(f) for f in flags), sum(bool(f) and all(f) for f in flags), n_foreign, n_running


def _budget_stats(
    df: pd.DataFrame, n_events: int, excl: tuple[int, int, int, int] = (0, 0, 0, 0)
) -> dict[str, int]:
    return {
        "rows": len(df),
        "articles_excluded": excl[0],
        "articles_excluded_non_english": excl[2],
        "articles_excluded_running": excl[3],
        "events_all_excluded": excl[1],
        "events_without_text": n_events - len(df) - excl[1],
        "states_with_dropped_articles": int((df["n_articles"] < df["_listed"]).sum()),
        "articles_dropped": int((df["_listed"] - df["n_articles"]).sum()),
        "texts_cut": int(df["_cut"].sum()),
    }


def run_states(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    cfg = load_states_config()
    tok = tokens.tokenizer(load_events_config().events)
    qtok = question_tokens(load_battery(), tok)
    inp = load_inputs(lay)
    bud = budgets(tok, qtok, cfg, inp.cb)
    d0 = io.read_parquet(EVENTS_D0, layout=lay)
    d2 = io.read_parquet(EVENTS_D2, layout=lay)
    stats: dict[str, Any] = {"caps": {w: b.cap for w, b in bud.items()}, "question_tokens": qtok}

    def emit(df: pd.DataFrame, ev: pd.DataFrame, col: str, rel: str, description: str, name: str) -> None:
        window: StateWindow = "W0" if col == "news_w0" else "W2"
        running = inp.excluded_w0 - inp.excluded if window == "W0" else frozenset()
        counts = exclusion_counts(ev, col, skipped(inp, window), inp.non_english, running)
        stats[name] = _budget_stats(df, len(ev), counts)
        write_states(add_tokens(df, tok, qtok), rel, description, lay)
        print(f"states {name}: {stats[name]}", flush=True)

    spec = make_spec("callA_d0_E3", "A", "W0", "E3", True, cfg)
    a0, keep_d0 = build_event_states(d0, spec, inp, cfg, budget=bud["W0"])
    emit(
        a0,
        d0,
        "news_w0",
        f"{STATES_DIR}/callA_d0_E3.parquet",
        "NA-04 S5: Call A on D0 (W0 news), masked, E3",
        spec.name,
    )
    spec = make_spec("callA_d2_E3", "A", "W2", "E3", True, cfg)
    a2, keep_d2 = build_event_states(d2, spec, inp, cfg, budget=bud["W2"])
    emit(
        a2,
        d2,
        "news_w2",
        f"{STATES_DIR}/callA_d2_E3.parquet",
        "NA-04 S5: Call A on D2 (W2 news, A3.1), masked, E3",
        spec.name,
    )
    b_events = d2.loc[d2["split"].isin(B_SPLITS)]
    spec = make_spec("callB_d2_E3", "B", "W2", "E3", True, cfg)
    b2, _ = build_event_states(b_events, spec, inp, cfg, keep=keep_d2)
    emit(
        b2,
        b_events,
        "news_w2",
        f"{STATES_DIR}/callB_d2_E3.parquet",
        "NA-04 S5: Call B on D2 (train, val-A, val-B), masked, E3",
        spec.name,
    )

    sel = market_selection(lay, cfg)
    dm = build_market_states(sel, make_spec("market_E3", "M", "W2", "E3", True, cfg), inp, cfg)
    write_states(
        add_tokens(dm, tok, qtok),
        f"{STATES_DIR}/market_E3.parquet",
        "NA-04 S5 (A3.5, optional): market states per session (E3)",
        lay,
    )
    stats["market_E3"] = {
        "rows": len(dm),
        "sessions_without_text": int(sel["session_w2"].nunique()) - len(dm),
    }

    with_text = d0.loc[d0["event_id"].isin(set(a0["event_id"]))]
    enc_events, twin = sample_frames(with_text, cfg)
    for e in ENCODINGS:
        spec = make_spec(f"callA_d0_{e}", "A", "W0", e, True, cfg)
        df, _ = build_event_states(enc_events, spec, inp, cfg, keep=keep_d0)
        emit(
            df,
            enc_events,
            "news_w0",
            f"{SAMPLES_DIR}/callA_d0_{e}.parquet",
            f"NA-04 S5: NA-07 encoding sample, 1,500 val-A + 1,500 val-B D0 events, Call A {e}",
            f"sample_{e}",
        )
    spec = make_spec("unmasked", "A", "W0", "E3", False, cfg)
    du, _ = build_event_states(twin, spec, inp, cfg, keep=keep_d0)
    emit(
        du,
        twin,
        "news_w0",
        f"{SAMPLES_DIR}/unmasked.parquet",
        "NA-04 S5: unmasked twin of 1,000 val-A D0 events (Call A E3; masked twin in callA_d0_E3)",
        "unmasked",
    )
    out = lay.artifacts / "NA-04" / "build_states.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, indent=2, default=str) + "\n", encoding="utf-8")
    return stats


# --- D1 stage (NA-10 S6) ------------------------------------------------------------------------------


def reaction_frame_d1(lay: Layout, cfg: StatesConfig) -> pd.DataFrame:
    """D1 reaction inputs for the train / val-A / val-B D0 event keys (never the test period), from
    ``work/panel/intraday_public.parquet`` through ``panel.reactions.build_reactions(..., "D1")``."""
    from newsaction.bars import INTRADAY_PUBLIC, INTRADAY_SPY_PUBLIC
    from newsaction.panel.reactions import D1_INPUT_COLUMNS, build_reactions

    keys = io.read_parquet(EVENTS_D0, columns=["event_id", "session", "symbol_id", "split"], layout=lay)
    d0 = keys.loc[keys["split"].isin(B_SPLITS), ["session", "symbol_id"]].drop_duplicates()
    if bool((d0["session"] >= load_splits().splits["test"].start).any()):
        raise StatesError("Call B D1 reactions requested for a test-period session")
    intra = io.read_parquet(
        INTRADAY_PUBLIC, columns=[*D1_INPUT_COLUMNS, "g_d1", "logv10_mad60"], layout=lay
    ).loc[:, lambda f: ~f.columns.duplicated()]
    react = d0.merge(
        build_reactions(intra, "public", "D1", layout=lay), on=["session", "symbol_id"], how="left"
    )
    first, last = context_span()
    grid = ctx.session_grid(first, last, cfg.context.history_sessions)
    spy = io.read_parquet(INTRADAY_SPY_PUBLIC, columns=["session", "r_spy_c10"], layout=lay)
    spy_change = spy.set_index("session")["r_spy_c10"].reindex(grid).to_numpy(dtype="float64")
    out = ctx.reaction_d1(
        react, intra[["session", "symbol_id", "g_d1", "logv10_mad60"]], spy_change, grid, cfg
    )
    return out.sort_values(["session", "symbol_id"], kind="mergesort").reset_index(drop=True)


def run_d1(layout: Layout | None = None) -> dict[str, Any]:
    """``callB_d1_E3``: Call B on W0 news with the reaction by 10:00, train / val-A / val-B (NA-10 S6).

    NA-04's builder, masking and W0 exclusions (explainers, TradingView, non-English and running market
    stories: the D1 state is decided before the close, so the W0 rule applies). The news list keeps the
    leading articles that fit 1,024 tokens with Call B's longest core question and the longest possible D1
    ``reaction_so_far`` (``worst_reaction``), so the cut never depends on the observed reaction; it can be
    shorter than the Call A D0 state's list. Writes reaction_d1 and callB_d1_E3 only."""
    lay = resolve_layout(layout)
    cfg = load_states_config()
    tok = tokens.tokenizer(load_events_config().events)
    qtok = question_tokens(load_battery(), tok)
    react = reaction_frame_d1(lay, cfg)
    io.write_parquet(
        react,
        REACTION_D1,
        producer=PRODUCER_D1,
        description="NA-10 S6: D1 reaction inputs of Call B (train, val-A, val-B D0 events only)",
        layout=lay,
    )
    inp = load_inputs(lay)
    inp.reaction_d1 = react
    t = cfg.tokens
    budget = Budget(
        tok, t.total_max - t.special_tokens - qtok["B"]["longest_core"], worst_reaction(tok, inp.cb, "D1")
    )
    d0 = io.read_parquet(EVENTS_D0, layout=lay)
    b_events = d0.loc[d0["split"].isin(B_SPLITS)]
    spec = make_spec("callB_d1_E3", "B", "W0", "E3", True, cfg)
    df, _ = build_event_states(b_events, spec, inp, cfg, budget=budget)
    running = inp.excluded_w0 - inp.excluded
    stats: dict[str, Any] = _budget_stats(
        df, len(b_events), exclusion_counts(b_events, "news_w0", skipped(inp, "W0"), inp.non_english, running)
    )
    stats["cap"] = budget.cap
    entry = write_states(
        add_tokens(df, tok, qtok),
        CALL_B_D1,
        "NA-10 S6: Call B on D1 (W0 news + reaction by 10:00), train/val-A/val-B, masked, E3",
        lay,
        PRODUCER_D1,
    )
    stats.update(rows=entry["rows"], sha256=entry["sha256"])
    stats["reaction_missing"] = int(react["g_d1"].isna().sum())
    out = lay.artifacts / "NA-10" / "build_states_d1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, indent=2, default=str) + "\n", encoding="utf-8")
    return stats


# --- CLI ----------------------------------------------------------------------------------------------

STAGES: Final = ("context", "mask", "states", "report", "d1")


def _stage(name: str) -> Callable[[Layout | None], Any]:
    if name == "context":
        return run_context
    if name == "mask":
        return run_mask
    if name == "states":
        return run_states
    if name == "d1":
        return run_d1
    from newsaction.states.report import run_report

    return run_report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="newsaction.states.build", description=__doc__)
    ap.add_argument("--stage", choices=STAGES, required=True)
    args = ap.parse_args(argv)
    t0 = time.time()
    result = _stage(args.stage)(None)
    rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS
    print(f"stage {args.stage}: {time.time() - t0:,.0f}s, peak RSS {rss_gb:.1f} GB", flush=True)
    print(json.dumps(result, default=str)[:4000], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
