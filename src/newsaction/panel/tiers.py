"""Companies, representative share class, market caps and monthly size tiers (PREREG §3.2-3.3; NA-01 S5).

- **Companies.** Symbols with the same CIK are one company. ATOM fills ``ref.symbol.cik`` for 6 of
  1,615 symbols, so symbols without a CIK are grouped by issuer name with the share-class designation
  removed ("Alphabet Inc. (Class A)" ~ "(Class C)"); PREREG §15. ``company_id`` = the smallest
  symbol_id of the group.
- **Representative class** of a company for month M: the class with the higher 63-session average
  dollar volume ending at the last session of M-1.
- **Market cap** at a ranking session m (last session of M-1, applied to every session of M):
  raw close of the representative class x shares_basic. CIQ ``shares_basic`` is a company-level
  count (GOOGL and GOOG carry the same value) restated to the share basis of the CIQ pull (the
  rows' ``ingested_at`` date), so the company cap is not a sum over classes, and the share count is
  brought back to m's basis by dividing by the true splits with m < ex_date <= that date. Spin-off
  pseudo-splits do not change share counts and are ignored. ``share_basis`` checks the restatement
  per split; a split whose shares were not restated is handled as-reported. The share row is the
  latest with ``known_from`` <= close(m). (PREREG §15.)
- **Share cross-check.** CIQ's count is compared with an independent one: the Yahoo share count of
  the same class (work/market/shares.parquet; the latest observation dated at least 45 days before m,
  at most 400 days, brought to m's basis through the true splits in between). If CIQ is missing or
  differs by more than ``SHARE_TOLERANCE``x, the Yahoo count is used (``shares_source`` =
  ``yahoo_ciq_missing`` / ``yahoo_ciq_rejected``); both counts are kept for review. ATOM's CIQ rows
  are corrupt for some names (MRSH 1.07M shares, BNY's interleaved off-quarter rows, CBRE, CTRA,
  ...): PREREG §15.
- **Stale closes.** A ``stale_public`` close (test months, no usable test-period close) is paired
  with shares on the basis of the session it comes from (``stale_basis``), so a split after it
  cannot halve or double the cap.
- **Fallback.** A company with neither count gets the cap of the company with the nearest
  63-session dollar volume and is flagged.
- **Tiers.** Companies that are index members at m are ranked by cap (ties: smaller company_id
  first): Top-100 (ranks 1-100), Mid (101-250), Rest (251+). Companies joining during M are not
  ranked; their tier compares their cap at m with the rank-100 / rank-250 caps. DV tiers rank the
  company's summed 63-session dollar volume the same way (PREREG §3.3 robustness).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any, Final, cast

import numpy as np
import pandas as pd

TOP: Final = "top100"
MID: Final = "mid"
REST: Final = "rest"
TOP_N: Final = 100
SHARE_TOLERANCE: Final = 1.5
YAHOO_LAG_DAYS: Final = 45
YAHOO_MAX_AGE_DAYS: Final = 400
YAHOO_SPLIT_SETTLE_DAYS: Final = 30
MID_N: Final = 250


def normalize_issuer(name: str | None) -> str:
    n = (name or "").lower()
    n = re.sub(r"\(.*?class.*?\)", " ", n)
    n = re.sub(r"\bclass [a-z]\b", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(n.split())


def companies(symbols: pd.DataFrame) -> pd.DataFrame:
    """symbol_id -> company_id, with the grouping key and how it was formed (cik / name)."""
    df = symbols[["symbol_id", "ticker", "name", "cik"]].copy()
    has_cik = df["cik"].notna() & (df["cik"].astype(str).str.strip() != "")
    df["group_key"] = np.where(
        has_cik, "cik:" + df["cik"].astype(str), "name:" + df["name"].map(normalize_issuer)
    )
    df["grouping"] = np.where(has_cik, "cik", "name")
    df["company_id"] = df.groupby("group_key")["symbol_id"].transform("min").astype("int64")
    df["n_classes"] = df.groupby("company_id")["symbol_id"].transform("count").astype("int64")
    return df[["symbol_id", "ticker", "name", "cik", "company_id", "n_classes", "grouping", "group_key"]]


def month_key(ts: pd.Timestamp) -> str:
    return f"{ts.year:04d}-{ts.month:02d}"


def next_month(key: str) -> str:
    y, m = (int(x) for x in key.split("-"))
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def month_ranking_sessions(sessions: pd.DatetimeIndex) -> dict[str, pd.Timestamp]:
    """Applied month ("YYYY-MM") -> ranking session: the last session of the previous month."""
    last: dict[str, pd.Timestamp] = {}
    for ts in sessions:
        last[month_key(ts)] = pd.Timestamp(ts)  # ascending: the last write is the month's last session
    return {next_month(k): v for k, v in last.items()}


def representative(adv_at_m: pd.DataFrame, company: pd.Series) -> pd.DataFrame:
    """Representative symbol per (ranking session, company): the higher DV, ties -> smaller symbol_id.

    ``adv_at_m``: rows = ranking sessions, columns = symbol_id, 63-session average dollar volume.
    """
    frame = adv_at_m.rename_axis(index="ranking_session", columns="symbol_id").reset_index()
    long = frame.melt(id_vars="ranking_session", var_name="symbol_id", value_name="adv")
    long["company_id"] = long["symbol_id"].map(company)
    long["adv_key"] = long["adv"].fillna(-1.0)
    long = long.sort_values(
        ["ranking_session", "company_id", "adv_key", "symbol_id"], ascending=[True, True, False, True]
    )
    rep = long.drop_duplicates(["ranking_session", "company_id"])
    return rep[["ranking_session", "company_id", "symbol_id"]].rename(columns={"symbol_id": "rep_symbol_id"})


def share_basis(shares: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Per (symbol, true split): were shares_basic values restated to the post-split basis?

    Compares the last value with period_end < ex_date and the first with period_end >= ex_date:
    a ratio near 1 means restated, near the split ratio means as-reported. Undecidable -> restated
    (the CIQ convention observed in this snapshot).
    """
    rows = []
    q = shares[shares["period_type"] == "Q"].sort_values(["symbol_id", "period_end"])
    q = q.assign(pe=pd.to_datetime(q["period_end"]), ing=pd.to_datetime(q["ingested_at"]).dt.tz_convert(None))
    for rec in splits.to_dict("records"):
        ex, r = pd.Timestamp(rec["ex_session"]), float(rec["split_ratio"])
        s = q[q["symbol_id"] == rec["symbol_id"]]
        before = s.loc[s["pe"] < ex, "value"].to_numpy(dtype="float64")
        after = s.loc[s["pe"] >= ex, "value"].to_numpy(dtype="float64")
        restated, ratio = True, float("nan")
        if len(before) and len(after) and before[-1] > 0:
            ratio = float(after[0] / before[-1])
            restated = bool(abs(np.log(ratio)) < abs(np.log(ratio) - np.log(r)))
        if len(s) and ex > pd.Timestamp(s["ing"].max()):
            restated = False  # a split after the pull cannot be in the values
        rows.append((int(rec["symbol_id"]), ex, r, ratio, restated))
    return pd.DataFrame(rows, columns=["symbol_id", "ex_session", "split_ratio", "value_ratio", "restated"])


def share_book(shares: pd.DataFrame, actions: pd.DataFrame) -> ShareBook:
    """The ShareBook of the snapshot: share bases follow true splits only (``kind == "split"``).

    Spin-offs are stored by ATOM as split rows with a price ratio; they do not change share counts.
    """
    return ShareBook(shares, share_basis(shares, actions[actions["kind"] == "split"]))


class ShareBook:
    """shares_basic rows and split-basis records per symbol, for fast point-in-time lookups."""

    def __init__(self, shares: pd.DataFrame, basis: pd.DataFrame) -> None:
        ok = shares[shares["value"].notna()].sort_values(["symbol_id", "period_end", "known_from"])
        self._rows = {int(cast(int, k)): g for k, g in ok.groupby("symbol_id")}
        self._basis: dict[int, list[tuple[pd.Timestamp, float, bool]]] = {}
        for rec in basis.to_dict("records"):
            entry = (pd.Timestamp(rec["ex_session"]), float(rec["split_ratio"]), bool(rec["restated"]))
            self._basis.setdefault(int(rec["symbol_id"]), []).append(entry)

    def at(
        self, symbol_id: int, m: pd.Timestamp, known_by: pd.Timestamp
    ) -> tuple[float, pd.Timestamp | None]:
        """Shares (millions) of ``symbol_id`` on session m's share basis; NaN if none known by ``known_by``.

        The row is the one with the latest period_end among rows with known_from <= known_by.
        """
        g = self._rows.get(int(symbol_id))
        if g is None:
            return float("nan"), None
        known = g[g["known_from"] <= known_by]
        if known.empty:
            return float("nan"), None
        row = known.iloc[-1]
        pe = pd.Timestamp(row["period_end"])
        value = float(row["value"])
        for ex, ratio, restated in self._basis.get(int(symbol_id), []):
            post_basis = restated or pe >= ex
            need_post = ex <= m
            if need_post and not post_basis:
                value *= ratio
            elif post_basis and not need_post:
                value /= ratio
        return value, pe


class YahooShares:
    """Independent share counts per symbol (Yahoo, as-of dated; millions on a requested basis)."""

    def __init__(
        self,
        shares: pd.DataFrame,
        tickers: dict[int, list[str]],
        splits: dict[int, list[tuple[pd.Timestamp, float]]],
    ) -> None:
        by_ticker = {str(t): g for t, g in shares.groupby("ticker")}
        self._series: dict[int, tuple[str, pd.Series]] = {}
        for sid, candidates in tickers.items():
            for t in candidates:
                g = by_ticker.get(t)
                if g is not None and len(g):
                    s = pd.Series(
                        g["shares"].to_numpy(dtype="float64") / 1e6, index=pd.DatetimeIndex(g["date"])
                    )
                    self._series[sid] = (t, s.sort_index())
                    break
        self._splits = splits

    def ticker(self, symbol_id: int) -> str | None:
        hit = self._series.get(int(symbol_id))
        return None if hit is None else hit[0]

    def at(self, symbol_id: int, m: pd.Timestamp, basis: pd.Timestamp) -> tuple[float, pd.Timestamp | None]:
        """Latest count dated in [m - 400d, m - 45d], expressed on ``basis``'s share basis.

        Only observations at least 30 days after the last true split up to the basis session are
        used (Yahoo's series is sometimes restated before an ex-date and updated late after it).
        NaN when the count cannot be trusted as a reference: a true split still lies between the
        observation and the basis session, or the count is off by more than SHARE_TOLERANCE x from
        the median of the symbol's own observations over the previous year (a transient vendor
        error, e.g. HST 2024-Q4).
        """
        hit = self._series.get(int(symbol_id))
        if hit is None:
            return float("nan"), None
        s = hit[1]
        splits = self._splits.get(int(symbol_id), [])
        lo, hi = m - pd.Timedelta(days=YAHOO_MAX_AGE_DAYS), m - pd.Timedelta(days=YAHOO_LAG_DAYS)
        settled = sorted(ex + pd.Timedelta(days=YAHOO_SPLIT_SETTLE_DAYS) for ex, _ in splits if ex <= basis)
        lo = max([lo, *settled])  # observations on the basis session's side of every split
        w = s[(s.index >= lo) & (s.index <= hi)]
        if w.empty:
            return float("nan"), None
        obs, value = pd.Timestamp(w.index[-1]), float(w.iloc[-1])
        if any(min(obs, basis) < ex <= max(obs, basis) for ex, _ in splits):
            return float("nan"), obs
        trail = s[(s.index > max([obs - pd.Timedelta(days=365), *settled[-1:]])) & (s.index <= obs)]
        med = float(trail.median())
        if not 1 / SHARE_TOLERANCE <= value / med <= SHARE_TOLERANCE:
            return float("nan"), obs
        return value, obs


def cross_check(ciq: float, yahoo: float) -> tuple[float, str]:
    """(shares used, source): CIQ unless it is missing or off by more than SHARE_TOLERANCE x."""
    if np.isfinite(ciq) and np.isfinite(yahoo) and yahoo > 0:
        ratio = ciq / yahoo
        if 1 / SHARE_TOLERANCE <= ratio <= SHARE_TOLERANCE:
            return ciq, "ciq"
        return yahoo, "yahoo_ciq_rejected"
    if np.isfinite(ciq):
        return ciq, "ciq_unchecked"
    if np.isfinite(yahoo):
        return yahoo, "yahoo_ciq_missing"
    return float("nan"), "missing"


def assign_ranks(values: pd.Series, company_ids: Iterable[int]) -> pd.Series:
    """Dense 1..n ranks by value descending, ties by smaller company_id; NaN values unranked."""
    df = pd.DataFrame({"v": values, "cid": list(company_ids)}).dropna(subset=["v"])
    df = df.sort_values(["v", "cid"], ascending=[False, True])
    ranks = pd.Series(np.arange(1, len(df) + 1), index=df.index, dtype="float64")
    return ranks.reindex(values.index)


def tier_of_rank(rank: pd.Series) -> pd.Series:
    out = pd.Series(REST, index=rank.index, dtype=object)
    out[rank <= MID_N] = MID
    out[rank <= TOP_N] = TOP
    out[rank.isna()] = None
    return out


def tier_of_value(value: pd.Series, top_cut: float, mid_cut: float) -> pd.Series:
    out = pd.Series(REST, index=value.index, dtype=object)
    out[value >= mid_cut] = MID
    out[value >= top_cut] = TOP
    out[value.isna()] = None
    return out


def impute_cap_from_dv(cap: pd.Series, adv: pd.Series) -> pd.Series:
    """Cap of the company with the nearest log dollar volume, for companies without a cap."""
    have = cap.notna() & adv.gt(0)
    need = cap.isna() & adv.gt(0)
    if not have.any() or not need.any():
        return cap.copy()
    ref = pd.DataFrame({"lv": np.log(adv[have]), "cap": cap[have]}).sort_values("lv")
    lv, caps = ref["lv"].to_numpy(), ref["cap"].to_numpy()
    x = np.log(adv[need].to_numpy(dtype="float64"))
    hi = np.clip(np.searchsorted(lv, x), 0, len(lv) - 1)
    lo = np.clip(hi - 1, 0, len(lv) - 1)
    nearest = np.where(np.abs(lv[lo] - x) <= np.abs(lv[hi] - x), lo, hi)
    out = cap.copy()
    out[need] = caps[nearest]
    return out


def monthly_tiers(
    applied: Sequence[str],
    ranking: dict[str, pd.Timestamp],
    close_at: pd.DataFrame,
    close_source: pd.DataFrame,
    adv_at: pd.DataFrame,
    members_by_month: dict[str, tuple[set[int], set[int]]],
    company: dict[int, int],
    book: ShareBook,
    known_by: dict[pd.Timestamp, pd.Timestamp],
    yahoo: YahooShares | None = None,
    stale_basis: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """tiers_monthly: one row per (applied month, company) of companies that are members in it.

    ``close_at`` / ``close_source`` / ``adv_at``: rows = ranking sessions, columns = symbol_id (raw
    close, its source, 63-session average dollar volume ending at the ranking session).
    ``members_by_month[M]`` = (symbol_ids that are members at the ranking session, symbol_ids that
    are members on any session of M). ``known_by[m]`` = the close(m) instant.
    """
    rep = representative(adv_at, pd.Series(company))
    classes_of: dict[int, list[int]] = {}
    for sid, cid in sorted(company.items()):
        classes_of.setdefault(cid, []).append(sid)
    out = []
    for month in applied:
        m = ranking[month]
        at_m, during = members_by_month[month]
        comp_m = {company[s] for s in at_m if s in company}
        comp_any = {company[s] for s in at_m | during if s in company}
        rep_m = dict(
            rep.loc[rep["ranking_session"] == m, ["company_id", "rep_symbol_id"]].to_numpy().tolist()
        )
        close_m: dict[Any, Any] = close_at.loc[m].to_dict()
        source_m: dict[Any, Any] = close_source.loc[m].to_dict()
        adv_m: dict[Any, Any] = adv_at.loc[m].to_dict()
        recs = []
        for cid in sorted(comp_any):
            classes = classes_of[cid]
            rep_sid = int(rep_m.get(cid, classes[0]))
            source = source_m.get(rep_sid)
            basis = stale_basis if source == "stale_public" and stale_basis is not None else m
            ciq, pe, y, y_obs = float("nan"), None, float("nan"), None
            for sid in [rep_sid, *(c for c in classes if c != rep_sid)]:  # company-level counts
                if not np.isfinite(ciq):
                    ciq, pe = book.at(sid, basis, known_by[m])
                if yahoo is not None and not np.isfinite(y):
                    y, y_obs = yahoo.at(sid, m, basis)
            value, share_src = cross_check(ciq, y)
            price = float(close_m.get(rep_sid, np.nan))
            cap = price * value * 1e6 if np.isfinite(value) else np.nan  # shares_basic is in millions
            advs = [float(adv_m.get(c, np.nan)) for c in classes]
            adv = float(np.nansum(advs)) if np.isfinite(advs).any() else np.nan
            recs.append(
                {
                    "month": month,
                    "ranking_session": m,
                    "company_id": cid,
                    "rep_symbol_id": rep_sid,
                    "member_at_ranking": cid in comp_m,
                    "raw_close": price,
                    "close_source": source,
                    "shares_mn": value,
                    "shares_source": share_src,
                    "ciq_shares_mn": ciq,
                    "ciq_period_end": pe,
                    "yahoo_shares_mn": y,
                    "yahoo_obs_date": y_obs,
                    "cap_usd": cap,
                    "adv63_usd": adv,
                }
            )
        out.append(_rank_month(pd.DataFrame(recs)))
    return pd.concat(out, ignore_index=True)


def _cut(values: pd.Series, n: int) -> float:
    """The n-th largest value (-inf when fewer than n are ranked, so every joiner clears it)."""
    v = np.sort(values.dropna().to_numpy(dtype="float64"))[::-1]
    return float(v[n - 1]) if len(v) >= n else float("-inf")


def _rank_month(df: pd.DataFrame) -> pd.DataFrame:
    """Ranks and tiers of one month (ranked = members at the ranking session; joiners by threshold)."""
    ranked = df["member_at_ranking"].to_numpy(dtype=bool)
    joiners = ~ranked
    df["fallback_dv"] = df["cap_usd"].isna() & df["adv63_usd"].notna()
    df["cap_rank_value"] = impute_cap_from_dv(df["cap_usd"].where(ranked), df["adv63_usd"].where(ranked))
    df["rank"] = assign_ranks(df["cap_rank_value"].where(ranked), df["company_id"])
    df["dv_rank"] = assign_ranks(df["adv63_usd"].where(ranked), df["company_id"])
    df["tier"] = tier_of_rank(df["rank"])
    df["dv_tier"] = tier_of_rank(df["dv_rank"])
    df["tier_source"] = np.where(
        ranked, np.where(df["rank"].notna(), "ranked", "no_data"), "joiner_threshold"
    )
    if joiners.any():
        top_cut, mid_cut = (_cut(df.loc[ranked, "cap_rank_value"], n) for n in (TOP_N, MID_N))
        dv_top, dv_mid = (_cut(df.loc[ranked, "adv63_usd"], n) for n in (TOP_N, MID_N))
        j_cap = impute_cap_from_dv(df["cap_usd"], df["adv63_usd"]).where(joiners)
        df.loc[joiners, "cap_rank_value"] = j_cap[joiners]
        df.loc[joiners, "tier"] = tier_of_value(j_cap[joiners], top_cut, mid_cut)
        df.loc[joiners, "dv_tier"] = tier_of_value(df.loc[joiners, "adv63_usd"], dv_top, dv_mid)
    return df
