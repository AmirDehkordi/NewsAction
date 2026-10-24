"""PRD NA-02 S11: member-month coverage (PREREG §3.4) and the leaver check.

``coverage_member_month``: one row per (month, company) with at least one member session in the month, for
the months of the news load range (``load`` in configs/news.yaml);
articles are counted by the month of their ``session_w2`` (a member session by construction).
``covered`` = at least one cleaned article (``keep``, PREREG §6.2). Uncovered member-months are
*missing*, never "no news" (§3.4).

``leaver_check``: for each company that leaves the index, articles per member-day (``keep``) over its
last 60 member sessions, against stayers with the same tier (at the leaver's last member month) and
sector, measured over the same sessions. Counts only: no price is read.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.news import ARTICLES, COVERAGE, load_news_config
from newsaction.news.mapping import member_companies
from newsaction.paths import Layout, resolve_layout

PRODUCER: Final = "newsaction.news.coverage (NA-02 S11)"
LEAVER_WINDOW: Final = 60


def _month(d: pd.Series) -> pd.Series:
    return pd.to_datetime(d).dt.strftime("%Y-%m")


def member_month_counts(arts: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Coverage table from articles (company_id, session_w2, keep, passes) and member (session, company)."""
    cfg = load_news_config().load
    lo, hi = cfg.t_avail_start.strftime("%Y-%m"), cfg.t_avail_end.strftime("%Y-%m")
    mm = pairs.assign(month=_month(pairs["session"]))
    mm = mm[(mm["month"] >= lo) & (mm["month"] <= hi)]  # months the news corpus is loaded for
    base = mm.groupby(["month", "company_id"], as_index=False).agg(member_sessions=("session", "nunique"))
    a = arts.assign(month=_month(arts["session_w2"]))
    w0 = a["session_w0"].notna()
    counts = (
        a.assign(keep_w0=a["keep"] & w0)
        .groupby(["month", "company_id"], as_index=False)
        .agg(
            n_mapped=("id", "size"),
            n_clean=("passes_clean", "sum"),
            n_keep=("keep", "sum"),
            n_keep_w0=("keep_w0", "sum"),
        )
    )
    out = base.merge(counts, on=["month", "company_id"], how="left")
    for c in ("n_mapped", "n_clean", "n_keep", "n_keep_w0"):
        out[c] = out[c].fillna(0).astype("int64")
    out["covered"] = out["n_keep"] >= 1
    return out.sort_values(["month", "company_id"]).reset_index(drop=True)


def write_coverage(*, layout: Layout | None = None) -> pd.DataFrame:
    lay = resolve_layout(layout)
    arts = io.read_parquet(
        ARTICLES,
        columns=[
            "id",
            "company_id",
            "session_w0",
            "session_w2",
            "keep",
            "non_news",
            "junk_tag",
            "is_13f",
            "is_form4",
        ],
        layout=lay,
    )
    arts["passes_clean"] = ~arts[["non_news", "junk_tag", "is_13f", "is_form4"]].any(axis=1)
    members = io.read_parquet("snapshot/members_by_session.parquet", layout=lay)
    companies = io.read_parquet("panel/companies.parquet", layout=lay)
    cov = member_month_counts(arts, member_companies(members, companies))
    io.write_parquet(
        cov,
        COVERAGE,
        producer=PRODUCER,
        description="NA-02 S11: member-month article counts after cleaning; covered = >= 1 kept article",
        layout=lay,
    )
    return cov


def _rate(per_day: pd.Series, company: int, window: list[object]) -> float:
    """Kept articles per member session of ``company`` over ``window`` (sessions)."""
    if company not in per_day.index.get_level_values(0):
        return 0.0
    s = per_day.loc[company]
    return float(s[s.index.isin(window)].sum()) / len(window)


def leaver_check(
    arts: pd.DataFrame, pairs: pd.DataFrame, tiers: pd.DataFrame, sectors: pd.Series
) -> pd.DataFrame:
    """Per leaver: kept articles per member-day in its last 60 member sessions vs matched stayers."""
    sessions = sorted(pairs["session"].unique())
    last = pairs.groupby("company_id")["session"].max()
    leavers = last[last < sessions[-1]]
    keep = arts.loc[arts["keep"], ["company_id", "session_w2"]]
    per_day = keep.groupby(["company_id", "session_w2"]).size()
    member_sets = pairs.groupby("company_id")["session"].agg(set)
    rows = []
    for cid, end in leavers.items():
        mine = sorted(member_sets[cid])
        window = [s for s in mine if s <= end][-LEAVER_WINDOW:]
        if len(window) < LEAVER_WINDOW // 2:
            continue
        month = pd.Timestamp(end).strftime("%Y-%m")
        tier_row = tiers[(tiers["month"] == month) & (tiers["company_id"] == cid)]
        tier = tier_row["tier"].iloc[0] if len(tier_row) else None
        wset = set(window)
        cand = tiers[(tiers["month"] == month) & (tiers["tier"] == tier) & (tiers["company_id"] != cid)]
        stayers = [
            int(c)
            for c in cand["company_id"]
            if sectors.get(c) == sectors.get(cid)
            and last.get(c, sessions[0]) > end
            and wset <= member_sets[c]
        ]

        stay = [_rate(per_day, c, window) for c in stayers]
        rows.append(
            {
                "company_id": int(cid),
                "last_member_session": end,
                "tier": tier,
                "sector": sectors.get(cid),
                "window_sessions": len(window),
                "leaver_rate": _rate(per_day, int(cid), window),
                "n_stayers": len(stayers),
                "stayer_rate_mean": float(np.mean(stay)) if stay else np.nan,
                "stayer_rate_median": float(np.median(stay)) if stay else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    if len(out):
        out["ratio"] = out["leaver_rate"] / out["stayer_rate_mean"].replace(0, np.nan)
    return out
