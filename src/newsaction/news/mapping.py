"""PRD NA-02 S2: news ticker -> ATOM symbol -> company -> S&P 500 member (PREREG §3.1–3.2, §6.2).

1. ``parse_tickers``: ``EXCH:SYM`` -> exchange, normalized symbol and a class: ``us_equity`` (exchange
   in ``mapping.us_exchanges``), ``non_equity`` (indices, FX, crypto, macro series: the configured
   prefixes, or no exchange code at all) or ``other`` (non-US exchanges, OTC, futures exchanges).
   Normalization: upper case, ``.``, ``/`` and spaces -> ``-`` (BRK.B, BRK/B -> BRK-B).
2. ``ticker_map``: (ticker, symbol_id, [valid_from, valid_to)) from ATOM's current tickers
   (``symbols.parquet``, open-ended), ATOM's ticker history (``symbol_tickers.parquet``) and the curated
   ``mapping.aliases`` of ``configs/news.yaml`` (renames, extra share classes, and ``restrict`` rows that
   narrow an ATOM ticker's validity). ``check_collisions`` refuses a table in which one ticker maps to two
   symbols over overlapping intervals.
3. ``resolve``: the symbol whose interval contains t_avail; raises ``MappingError`` if an article
   matches two symbols (zero many-to-one collisions, PRD S2).
4. ``attach_company`` / ``member_mask``: company_id from ``companies.parquet``; an article is kept when its
   company is an index member (any class) at ``session_w2`` (``members_by_session.parquet``).
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction.news import MappingConfig, load_news_config

US_EQUITY: Final = "us_equity"
NON_EQUITY: Final = "non_equity"
OTHER: Final = "other"
_OPEN_START: Final = pd.Timestamp("1900-01-01", tz="UTC")
_OPEN_END: Final = pd.Timestamp("2200-01-01", tz="UTC")


class MappingError(ValueError):
    """Ambiguous ticker history (a many-to-one collision) or an inconsistent alias."""


def normalize_symbol(sym: pd.Series) -> pd.Series:
    """Upper case; ``.``, ``/`` and whitespace become ``-`` (BRK.B, BRK/B, BRK B -> BRK-B)."""
    s = sym.astype("str").str.strip().str.upper()
    return s.str.replace(r"[./\s]+", "-", regex=True).str.strip("-")


def parse_tickers(raw: pd.Series, cfg: MappingConfig | None = None) -> pd.DataFrame:
    """Columns ``exchange``, ``ticker_norm`` and ``ticker_class`` aligned with ``raw``."""
    cfg = cfg or load_news_config().mapping
    raw = raw.astype("str").str.strip()
    parts = raw.str.partition(":")
    has_exch = parts[1] == ":"
    exch = parts[0].where(has_exch, "").str.upper()
    sym = parts[2].where(has_exch, raw)
    prefixes = tuple(p.upper() for p in cfg.non_equity_prefixes)
    non_eq = (
        ~has_exch
        | exch.str.startswith(prefixes)
        | sym.str.upper().str.startswith(prefixes)
        | raw.str.upper().str.startswith(prefixes)
    )
    us = has_exch & exch.isin(set(cfg.us_exchanges)) & ~non_eq
    cls = np.select([us.to_numpy(), non_eq.to_numpy()], [US_EQUITY, NON_EQUITY], default=OTHER)
    return pd.DataFrame(
        {"exchange": exch, "ticker_norm": normalize_symbol(sym), "ticker_class": cls}, index=raw.index
    )


def _utc(d: Any, default: pd.Timestamp) -> pd.Timestamp:
    if d is None or (isinstance(d, float) and np.isnan(d)) or d is pd.NaT:
        return default
    t = pd.Timestamp(d)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def ticker_map(
    symbols: pd.DataFrame, symbol_tickers: pd.DataFrame, cfg: MappingConfig | None = None
) -> pd.DataFrame:
    """The point-in-time ticker table: ticker, symbol_id, valid_from, valid_to (UTC), source."""
    cfg = cfg or load_news_config().mapping
    rows: list[dict[str, object]] = []
    for sid, tic in zip(symbols["symbol_id"].tolist(), symbols["ticker"].tolist(), strict=True):
        rows.append(
            {
                "ticker": tic,
                "symbol_id": int(sid),
                "valid_from": _OPEN_START,
                "valid_to": _OPEN_END,
                "source": "atom_symbol",
            }
        )
    hist = symbol_tickers[["symbol_id", "ticker", "valid_from", "valid_to"]]
    for sid, tic, vf, vt in zip(*(hist[c].tolist() for c in hist.columns), strict=True):
        rows.append(
            {
                "ticker": tic,
                "symbol_id": int(sid),
                "valid_from": _utc(vf, _OPEN_START),
                "valid_to": _utc(vt, _OPEN_END),
                "source": "atom_history",
            }
        )
    known = set(symbols["symbol_id"].astype(int))
    for a in cfg.aliases:
        if a.symbol_id not in known:
            raise MappingError(f"alias {a.ticker}: symbol_id {a.symbol_id} is not in symbols.parquet")
        if a.kind == "restrict":
            continue
        rows.append(
            {
                "ticker": a.ticker,
                "symbol_id": a.symbol_id,
                "valid_from": _utc(a.valid_from, _OPEN_START),
                "valid_to": _utc(a.valid_to, _OPEN_END),
                "source": f"alias_{a.kind}",
            }
        )
    tmap = pd.DataFrame(rows)
    tmap["ticker"] = normalize_symbol(tmap["ticker"])
    # one interval per (ticker, symbol): the union of the sources' intervals (all are open or nested)
    tmap = (
        tmap.groupby(["ticker", "symbol_id"], as_index=False)
        .agg(valid_from=("valid_from", "min"), valid_to=("valid_to", "max"), source=("source", "first"))
        .sort_values(["ticker", "valid_from", "symbol_id"], kind="stable")
    )
    for a in cfg.aliases:
        if a.kind != "restrict":
            continue
        sel = (tmap["ticker"] == normalize_symbol(pd.Series([a.ticker])).iloc[0]) & (
            tmap["symbol_id"] == a.symbol_id
        )
        if not sel.any():
            raise MappingError(f"restrict alias {a.ticker}->{a.symbol_id} matches no ATOM ticker")
        tmap.loc[sel, "valid_from"] = _utc(a.valid_from, _OPEN_START)
        tmap.loc[sel, "valid_to"] = _utc(a.valid_to, _OPEN_END)
        tmap.loc[sel, "source"] = "atom_restricted"
    tmap = tmap.reset_index(drop=True)
    check_collisions(tmap)
    return tmap


def check_collisions(tmap: pd.DataFrame) -> None:
    """Raise if one ticker maps to two symbols over overlapping [valid_from, valid_to) intervals."""
    bad: list[str] = []
    for ticker, g in tmap.groupby("ticker", sort=False):
        if g["symbol_id"].nunique() < 2:
            continue
        g = g.sort_values("valid_from")
        starts, ends, ids = g["valid_from"].tolist(), g["valid_to"].tolist(), g["symbol_id"].tolist()
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if ids[i] != ids[j] and starts[j] < ends[i] and starts[i] < ends[j]:
                    bad.append(f"{ticker}: {ids[i]} and {ids[j]}")
    if bad:
        raise MappingError(f"many-to-one ticker collisions: {bad}")


def resolve(ticker_norm: pd.Series, t_avail: pd.Series, tmap: pd.DataFrame) -> pd.Series:
    """symbol_id (Int64, NA if unmapped) whose validity interval contains t_avail.

    Raises MappingError if any (ticker, t_avail) matches more than one symbol.
    """
    left = pd.DataFrame(
        {"row": np.arange(len(ticker_norm)), "ticker": ticker_norm.to_numpy(), "t": t_avail.to_numpy()}
    )
    m = left.merge(tmap[["ticker", "symbol_id", "valid_from", "valid_to"]], on="ticker", how="inner")
    m = m.loc[(m["valid_from"] <= m["t"]) & (m["t"] < m["valid_to"])]
    counts = m.groupby("row")["symbol_id"].nunique()
    if bool((counts > 1).any()):
        rows = counts.index[counts > 1][:5].tolist()
        raise MappingError(f"{int((counts > 1).sum())} articles match two symbols, e.g. rows {rows}")
    out = pd.Series(pd.NA, index=np.arange(len(ticker_norm)), dtype="Int64")
    first = m.drop_duplicates("row")
    out.iloc[first["row"].to_numpy()] = first["symbol_id"].to_numpy()
    out.index = ticker_norm.index
    return out


def attach_company(symbol_id: pd.Series, companies: pd.DataFrame) -> pd.Series:
    """company_id (Int64) of each symbol_id via ``companies.parquet``."""
    lookup = companies.set_index("symbol_id")["company_id"]
    return symbol_id.map(lookup).astype("Int64")


def member_companies(members: pd.DataFrame, companies: pd.DataFrame) -> pd.DataFrame:
    """Distinct (session, company_id) pairs with at least one member class at open(session)."""
    m = members[["session", "symbol_id"]].merge(companies[["symbol_id", "company_id"]], on="symbol_id")
    m["session"] = pd.to_datetime(m["session"]).dt.date
    return m[["session", "company_id"]].drop_duplicates().reset_index(drop=True)


def member_mask(session_w2: pd.Series, company_id: pd.Series, member_pairs: pd.DataFrame) -> pd.Series:
    """True where ``company_id`` is an index member at ``session_w2`` (False if either is missing)."""
    keys = set(zip(member_pairs["session"], member_pairs["company_id"].astype(int), strict=True))
    vals = [
        (s, int(c)) in keys if s is not None and not pd.isna(c) else False
        for s, c in zip(session_w2.tolist(), company_id.tolist(), strict=True)
    ]
    return pd.Series(vals, index=session_w2.index, dtype=bool)
