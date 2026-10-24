"""NA-01 S8: numbers and tables for artifacts/NA-01/REPORT.md.

    uv run python scripts/na01_report.py

Reads the registered NA-01 artifacts and public inputs; writes small CSV tables to artifacts/NA-01/
and prints a summary. Every return statistic is restricted to sessions <= the end of val-B; for
test-period sessions only counts are reported (membership, tier sizes, close sources).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.config import load_splits
from newsaction.panel import PANEL_START, adjust, build, tiers
from newsaction.paths import ARTIFACTS

OUT = ARTIFACTS / "NA-01"
PUBLIC_END = load_splits().splits["val_b"].end
R2_START = date(2024, 7, 1)
HOLDOUT_ANCHOR = pd.Timestamp("2025-06-30")


def _csv(df: pd.DataFrame, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, float_format="%.6g")


def universe(members: pd.DataFrame, companies: pd.DataFrame) -> dict[str, Any]:
    m = members.merge(companies[["symbol_id", "company_id"]], on="symbol_id")
    m["session"] = [pd.Timestamp(d).date() for d in m["session"]]
    per = m.groupby("session")["company_id"].nunique()
    sym = m.groupby("session")["symbol_id"].nunique()
    out = {}
    for name, sel in (
        ("panel_public", (per.index >= PANEL_START) & (per.index <= PUBLIC_END)),
        ("all", per.index == per.index),
    ):
        out[name] = {
            "companies": [int(per[sel].min()), float(per[sel].median()), int(per[sel].max())],
            "symbols": [int(sym[sel].min()), float(sym[sel].median()), int(sym[sel].max())],
            "sessions": int(sel.sum()),
        }
    return out


def tier_sizes(tm: pd.DataFrame) -> pd.DataFrame:
    t = (
        tm.groupby(["month", "tier_source", "tier"], dropna=False)
        .size()
        .unstack(["tier_source", "tier"], fill_value=0)
    )
    t.columns = [f"{a}:{b}" for a, b in t.columns]
    t["fallback_dv"] = tm[tm["tier_source"] == "ranked"].groupby("month")["fallback_dv"].sum()
    t["close_source_reconstructed"] = tm[tm["close_source"] == "reconstructed"].groupby("month").size()
    t["close_source_stale_public"] = tm[tm["close_source"] == "stale_public"].groupby("month").size()
    return t.fillna(0).astype(int).reset_index()


def risk_quantiles(p: pd.DataFrame) -> pd.DataFrame:
    q = [0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99]
    sel = p[p["member"] & (p["session"] >= R2_START)]
    cols = ["beta_m", "beta_s", "sigma_cc", "sigma_on", "sigma_id", "z_vol", "z_cc", "z_on", "z_id"]
    rows = [
        {
            "column": c,
            "n": int(sel[c].notna().sum()),
            **{f"q{int(x * 100):02d}": sel[c].quantile(x) for x in q},
        }
        for c in cols
    ]
    return pd.DataFrame(rows)


def r2_sanity(p: pd.DataFrame) -> dict[str, Any]:
    sel = p[(p["session"] >= R2_START) & p["member"]]
    r2 = []
    for _, g in sel.groupby("symbol_id"):
        g = g.dropna(subset=["r_cc", "r_spy_cc", "r_sec_cc"])
        if len(g) < 120:
            continue
        x = np.column_stack([np.ones(len(g)), g["r_spy_cc"], g["r_sec_cc"] - g["r_spy_cc"]])
        y = g["r_cc"].to_numpy()
        e = y - x @ np.linalg.lstsq(x, y, rcond=None)[0]
        r2.append(1 - e.var() / y.var())
    a = np.array(r2)
    return {
        "median": float(np.median(a)),
        "q25": float(np.quantile(a, 0.25)),
        "q75": float(np.quantile(a, 0.75)),
        "n_stocks": len(a),
    }


def qc_tables(qc: pd.DataFrame, p: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    mem = p[["session", "symbol_id", "member"]]
    q = qc.merge(mem, on=["session", "symbol_id"], how="left")
    q["member"] = q["member"].fillna(False).astype(bool)
    q["in_panel_period"] = [d >= PANEL_START for d in q["session"]]
    counts = q.groupby(["reason", "member"]).size().unstack("member", fill_value=0).reset_index()
    q["severity"] = np.maximum(q["diff_bp"].abs().fillna(0) / 1e4, q["r_on"].abs().fillna(0))
    top = q[q["member"]].sort_values("severity", ascending=False).head(30)
    return counts, top.drop(columns=["severity"])


def goldens(p: pd.DataFrame, tm: pd.DataFrame, companies: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ge = p[(p["ticker"] == "GE") & (p["session"] == date(2024, 4, 2))].iloc[0]
    out["GE_2024-04-02"] = {
        "r_on": float(ge["r_on"]),
        "r_cc": float(ge["r_cc"]),
        "r_id": float(ge["r_id"]),
        "raw_gap": float(ge["raw_open"] / 175.24 - 1),
    }
    for t, months in {
        "NVDA": ("2024-05", "2024-06", "2024-07", "2024-08"),
        "CMG": ("2024-05", "2024-06", "2024-07", "2024-08"),
        "AVGO": ("2024-06", "2024-07", "2024-08", "2024-09"),
        "WMT": ("2024-01", "2024-02", "2024-03", "2024-04"),
        "GE": ("2024-03", "2024-04", "2024-05"),
    }.items():
        cid = int(companies.loc[companies["ticker"] == t, "company_id"].item())
        g = tm[(tm["company_id"] == cid) & tm["month"].isin(months)].sort_values("month")
        out[t] = [
            {
                "month": r["month"],
                "ranking_session": str(r["ranking_session"]),
                "cap_bn": round(r["cap_usd"] / 1e9, 1),
                "rank": int(r["rank"]),
                "tier": r["tier"],
            }
            for r in g.to_dict("records")
        ]
    return out


def leavers(companies: pd.DataFrame, symbols: pd.DataFrame, last_member: date) -> pd.DataFrame:
    c = companies.merge(symbols[["symbol_id", "delisting_date", "is_active"]], on="symbol_id", how="left")
    c = c[c["last_member_session"].notna()]
    out = c[[d < last_member for d in c["last_member_session"]]]
    return out[
        [
            "symbol_id",
            "ticker",
            "name",
            "first_member_session",
            "last_member_session",
            "delisting_date",
            "is_active",
            "adj_source",
        ]
    ].sort_values("last_member_session")


def split_classification(
    actions: pd.DataFrame, symbols: pd.DataFrame, basis_book_check: pd.DataFrame
) -> pd.DataFrame:
    a = actions[(actions["action_type"] == "split") & (actions["ex_session"] >= pd.Timestamp("2022-01-01"))]
    a = a.merge(symbols[["symbol_id", "ticker"]], on="symbol_id")
    a = a.merge(
        basis_book_check[["symbol_id", "ex_session", "value_ratio", "restated"]],
        on=["symbol_id", "ex_session"],
        how="left",
    )
    return a[["ticker", "ex_date", "split_ratio", "kind", "value_ratio", "restated"]].sort_values("ex_date")


def reconstruction_holdout(inp: build.Inputs, asm: build.Assembled) -> tuple[dict[str, Any], pd.DataFrame]:
    """Reconstruct raw closes for 2025-H2 from a 2025-06-30 anchor (as done for the test months) and
    compare closes and tiers with the exact ATOM raw-close versions (public data only)."""
    f = asm.frames
    end = pd.Timestamp(PUBLIC_END)
    mapped = [
        s
        for s, src in zip(asm.static["symbol_id"], asm.static["adj_source"], strict=True)
        if src == "data_prices"
    ]
    level = asm.mapping.set_index("symbol_id")["level_factor"].reindex(mapped).fillna(1.0)
    ac = f["adj_close"].loc[:end, mapped]
    rc = f["raw_close"].loc[:end, mapped] * level  # raw close on the traded level, as in the build
    f_anchor = f["adj_factor"].loc[HOLDOUT_ANCHOR, mapped] / level
    hat = adjust.reconstruct_raw_close(ac, f_anchor, HOLDOUT_ANCHOR, inp.actions)
    later = hat.index[hat.index > HOLDOUT_ANCHOR]
    err = (hat / rc - 1).loc[later].where(f["member"].loc[later, mapped])
    e = err.stack().dropna().abs()
    worst = err.abs().max().sort_values(ascending=False).head(5)
    ticker = asm.static.set_index("symbol_id")["ticker"]
    stats = {
        "daily_abs_rel_err": {
            "median": float(e.median()),
            "p99": float(e.quantile(0.99)),
            "max": float(e.max()),
            "n": len(e),
        },
        "worst": {str(ticker[s]): round(float(v), 4) for s, v in worst.items()},
    }
    # tiers with the reconstructed closes for months 2025-08 .. 2026-01 vs exact
    months = ["2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01"]
    exact = asm.tiers_monthly[asm.tiers_monthly["month"].isin(months)]
    ranking = tiers.month_ranking_sessions(asm.sessions)
    rs = pd.DatetimeIndex([ranking[m] for m in months])
    full_level = (
        asm.mapping.set_index("symbol_id")["level_factor"].reindex(f["raw_close"].columns).fillna(1.0)
    )
    close = f["raw_close"].loc[rs] * full_level  # exact closes on the traded level ...
    unflagged = [s for s in mapped if level[s] == 1.0]
    close[unflagged] = hat.loc[
        rs, unflagged
    ]  # ... replaced by reconstructions where the build would use them
    members = f["member"]
    mbm = {}
    for mo in months:
        at_m = members.loc[ranking[mo]]
        during = members.loc[[tiers.month_key(t) == mo for t in members.index]].any(axis=0)
        mbm[mo] = (
            {int(c) for c in at_m.index[at_m.to_numpy(dtype=bool)]},
            {int(c) for c in during.index[during.to_numpy(dtype=bool)]},
        )
    company = {
        int(a): int(b) for a, b in zip(asm.companies["symbol_id"], asm.companies["company_id"], strict=True)
    }
    dv = f["raw_close"] * full_level * f["raw_volume"]
    adv = dv.rolling(63, min_periods=40).mean().loc[rs]
    src = pd.DataFrame("reconstructed", index=rs, columns=close.columns)
    alt = tiers.monthly_tiers(
        months,
        ranking,
        close,
        src,
        adv,
        mbm,
        company,
        tiers.share_book(inp.shares, inp.actions),
        {m: calendar.close_utc(m.date()) for m in rs},
        yahoo=build._yahoo_shares(inp, asm.mapping, asm.symbols),
    )
    j = exact.merge(alt, on=["month", "company_id"], suffixes=("", "_hat"))
    j = j[j["tier_source"] == "ranked"]
    agree = (
        j.groupby("month")
        .apply(
            lambda g: pd.Series(
                {
                    "companies": len(g),
                    "tier_agree": float((g["tier"] == g["tier_hat"]).mean()),
                    "max_abs_rank_change": float((g["rank"] - g["rank_hat"]).abs().max()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    return stats, agree


def ex_dividend(p: pd.DataFrame, actions: pd.DataFrame) -> dict[str, Any]:
    div = actions.loc[actions["action_type"] == "cash_dividend", ["symbol_id", "ex_date", "cash_amount"]]
    div = div.groupby(["symbol_id", "ex_date"], as_index=False)["cash_amount"].sum()
    q = p[p["member"]][["session", "symbol_id", "ar_on", "raw_close", "adj_factor"]].sort_values(
        ["symbol_id", "session"]
    )
    q = q.assign(
        prev_close=q.groupby("symbol_id")["raw_close"].shift(1),
        prev_f=q.groupby("symbol_id")["adj_factor"].shift(1),
    )
    q = q.merge(div, left_on=["symbol_id", "session"], right_on=["symbol_id", "ex_date"], how="left").dropna(
        subset=["ar_on"]
    )
    ex, other = q[q["cash_amount"].notna()].dropna(subset=["prev_close"]), q[q["cash_amount"].isna()]
    dy = ex["cash_amount"] / ex["prev_close"]
    return {
        "n_ex_days": len(ex),
        "mean_ar_on_ex_bp": 1e4 * float(ex["ar_on"].mean()),
        "mean_ar_on_other_bp": 1e4 * float(other["ar_on"].mean()),
        "diff_bp": 1e4 * float(ex["ar_on"].mean() - other["ar_on"].mean()),
        "median_ar_on_ex_bp": 1e4 * float(ex["ar_on"].median()),
        "mean_dividend_yield_bp": 1e4 * float(dy.mean()),
        "mean_factor_jump_bp": 1e4 * float((ex["adj_factor"] / ex["prev_f"] - 1).mean()),
        "slope_ar_on_on_yield": float(np.polyfit(dy.to_numpy(), ex["ar_on"].to_numpy(), 1)[0]),
        "by_yield_quintile_bp": (1e4 * ex.groupby(pd.qcut(dy, 5, labels=False))["ar_on"].mean())
        .round(2)
        .tolist(),
    }


def main() -> int:
    p = io.read_parquet("panel/panel_public.parquet")
    tm = io.read_parquet("panel/tiers_monthly.parquet")
    companies = io.read_parquet("panel/companies.parquet")
    qc = io.read_parquet("panel/qc_flags.parquet")
    mp = io.read_parquet("panel/mapping.parquet")
    members = io.read_parquet("snapshot/members_by_session.parquet")
    symbols = io.read_parquet("snapshot/symbols.parquet")
    inp = build.load_inputs()
    inp_public = replace(
        inp,
        dp=inp.dp[inp.dp["date"] <= pd.Timestamp(PUBLIC_END)],
        spy_close=inp.spy_close[inp.spy_close.index <= pd.Timestamp(PUBLIC_END)],
    )
    asm = build.assemble(inp_public)  # public data only: the holdout never touches the test period
    basis = tiers.share_basis(inp.shares, inp.actions[inp.actions["kind"] == "split"])

    summary: dict[str, Any] = {"universe": universe(members, companies)}
    _csv(tier_sizes(tm), "tier_sizes_by_month.csv")
    rq = risk_quantiles(p)
    _csv(rq, "beta_sigma_quantiles_2024H2_2025.csv")
    summary["r2"] = r2_sanity(p)
    counts, top = qc_tables(qc, p)
    _csv(counts, "qc_reason_counts.csv")
    _csv(top, "qc_top30_member_days.csv")
    summary["qc_rows"] = len(qc)
    summary["goldens"] = goldens(p, tm, companies)
    lv = leavers(companies, symbols, max(pd.Timestamp(d).date() for d in members["session"]))
    _csv(lv, "leavers.csv")
    _csv(mp[mp["status"] != "mapped"], "mapping_failures.csv")
    summary["mapping"] = mp["status"].value_counts().to_dict()
    summary["mapping_lowest_pearson"] = mp.nsmallest(5, "corr_pearson")[
        ["atom_ticker", "corr_pearson", "corr_spearman"]
    ].to_dict("records")
    _csv(split_classification(inp.actions, symbols, basis), "split_classification.csv")
    summary["share_basis"] = {
        "restated": int(basis["restated"].sum()),
        "as_reported_or_after_pull": int((~basis["restated"]).sum()),
    }
    stats, agree = reconstruction_holdout(inp_public, asm)
    summary["reconstruction_holdout"] = stats
    _csv(agree, "reconstruction_holdout_tiers.csv")
    summary["ex_dividend"] = ex_dividend(p, inp.actions)
    ranked = tm[tm["tier_source"] == "ranked"]
    summary["tiers"] = {
        "months": int(tm["month"].nunique()),
        "fallback_dv_company_months": int(ranked["fallback_dv"].sum()),
        "fallback_dv_per_month_max": int(ranked.groupby("month")["fallback_dv"].sum().max()),
        "no_data_company_months": int((tm["tier_source"] == "no_data").sum()),
        "joiner_company_months": int((tm["tier_source"] == "joiner_threshold").sum()),
        "close_source_counts": tm["close_source"].value_counts(dropna=False).to_dict(),
    }
    comp1 = companies.drop_duplicates("company_id")[["company_id", "ticker"]]
    subs = tm[tm["shares_source"].str.startswith("yahoo")].merge(comp1, on="company_id")
    subs = subs.groupby(["ticker", "shares_source"]).agg(
        months=("month", "size"),
        ciq_shares_mn=("ciq_shares_mn", "median"),
        yahoo_shares_mn=("yahoo_shares_mn", "median"),
        first=("month", "min"),
        last=("month", "max"),
    )
    _csv(subs.reset_index(), "share_substitutions.csv")
    summary["shares_source_counts"] = tm["shares_source"].value_counts().to_dict()
    lvl = mp[["symbol_id", "atom_ticker", "level_n", "level_rho", "level_iqr", "level_factor"]]
    _csv(lvl[lvl["level_n"] > 0].sort_values("level_rho"), "raw_level_check.csv")
    checked = lvl[lvl["level_n"] >= adjust.LEVEL_MIN_EX_DATES]
    summary["raw_level_check"] = {
        "symbols_checked": len(checked),
        "rho_quantiles": checked["level_rho"].quantile([0.01, 0.05, 0.5, 0.95, 0.99]).round(4).to_dict(),
        "flagged": lvl.loc[lvl["level_factor"] != 1.0, ["atom_ticker", "level_rho", "level_n"]].to_dict(
            "records"
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(rq.round(4).to_string(index=False))
    print(agree.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
