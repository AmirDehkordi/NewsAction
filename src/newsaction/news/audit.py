"""PRD NA-02 S3 (timing audit), S10 (leakage audit, PREREG §6.4) and S13 (re-derived §14 diagnostics).

Every statistic that touches a return uses **public sessions only** (≤ the end of val-B, 2025-12-31).
``public_targets`` reads panel_public (which ends there) and ``assert_public`` refuses any later session;
articles are restricted to public sessions **before** they are joined to returns. 2026 articles are never
joined to anything here.

Daily IC: for each session, the cross-sectional Spearman correlation between a ticker-day signal and a
target over ticker-days (at least ``audit.min_names_per_day``); reported as the mean with a Newey–West
t-statistic (``audit.nw_lags`` lags, PREREG §11.1).

Leakage rule (PREREG §6.4): a cell is LEAKY when the vendor sentiment of its W0 (pre-open) articles has an
open→close IC at least as large as its gap IC, with t(IC with z_id) > ``audit.leak_t``. The t of the paired
difference IC(z_id) − IC(z_on) is reported alongside.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.config import load_splits
from newsaction.news import ARTICLES, clean, load_news_config
from newsaction.paths import CONFIGS, ROOT, Layout

PUBLIC_END: Final[date] = load_splits().splits["val_b"].end
TARGETS: Final = ("z_on", "z_id")


class AuditError(ValueError):
    """A return-based audit was given a session after the public period (blinding, CLAUDE.md B8)."""


def assert_public(sessions: pd.Series | Iterable[date], what: str = "sessions") -> None:
    """Raise unless every non-missing session is <= PUBLIC_END (the end of val-B)."""
    vals = [
        s
        for s in pd.Series(list(sessions) if not isinstance(sessions, pd.Series) else sessions)
        if s is not None and not pd.isna(s)
    ]
    if vals:
        latest = max(pd.Timestamp(v).date() for v in vals)
        if latest > PUBLIC_END:
            raise AuditError(f"{what}: session {latest} is after the public period (ends {PUBLIC_END})")


def public_only(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Rows with a session in ``col`` on or before PUBLIC_END (missing sessions dropped)."""
    s = df[col]
    ok = s.notna() & (pd.to_datetime(s.where(s.notna(), None)).dt.date <= PUBLIC_END)
    return df.loc[ok.to_numpy()]


def public_targets(layout: Layout | None = None, extra: Sequence[str] = ()) -> pd.DataFrame:
    """Member, representative-class rows of panel_public: session, company_id and targets (≤ val-B end)."""
    cols = [
        "session",
        "symbol_id",
        "company_id",
        "member",
        "is_rep",
        "z_on",
        "z_id",
        "z_cc",
        "ar_on",
        "ar_id",
        "ar_cc",
        "sigma_cc",
        "split",
        *extra,
    ]
    p = io.read_parquet("panel/panel_public.parquet", columns=list(dict.fromkeys(cols)), layout=layout)
    assert_public(p["session"], "panel_public")
    return p.loc[p["member"] & p["is_rep"]].reset_index(drop=True)


def forward_targets(panel: pd.DataFrame) -> pd.DataFrame:
    """Add z_next (z_cc at t+1) and z_5d (Σ AR_cc t+1..t+5 / (σ_cc,t+1 √5)) per symbol; NaN past the data."""
    p = panel.sort_values(["symbol_id", "session"]).copy()
    g = p.groupby("symbol_id", sort=False)
    p["z_next"] = g["z_cc"].shift(-1)
    fwd = sum(g["ar_cc"].shift(-k) for k in range(1, 6))
    p["z_5d"] = fwd / (g["sigma_cc"].shift(-1) * np.sqrt(5))
    return p


# --- statistics -------------------------------------------------------------------------------------


def nw_t(x: pd.Series | np.ndarray, lags: int) -> tuple[float, float, int]:
    """(mean, Newey–West t, n) of a series (NaN dropped)."""
    v = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(v)
    if n < 3:
        return (float(v.mean()) if n else np.nan, np.nan, n)
    e = v - v.mean()
    s = float(e @ e) / n
    for k in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / n
    se = np.sqrt(s / n) if s > 0 else np.nan
    return float(v.mean()), float(v.mean() / se) if se and se > 0 else np.nan, n


def daily_ic(df: pd.DataFrame, signal: str, target: str, min_names: int) -> pd.Series:
    """Per session: Spearman(signal, target) across ticker-days with both present (≥ min_names)."""
    d = df[["session", signal, target]].dropna()
    counts = d.groupby("session")[signal].transform("size")
    d = d[counts >= min_names]
    if d.empty:
        return pd.Series(dtype=float)
    r = d.groupby("session")[[signal, target]].rank()
    r["session"] = d["session"].to_numpy()
    ics = {s: float(g[signal].corr(g[target])) for s, g in r.groupby("session", sort=True)}
    return pd.Series(ics, dtype=float).dropna()


def ic_row(df: pd.DataFrame, signal: str, targets: Sequence[str] = TARGETS) -> dict[str, float]:
    """Mean daily IC and NW t per target, plus the paired difference of the first two targets."""
    cfg = load_news_config().audit
    out: dict[str, float] = {"ticker_days": float(df[signal].notna().sum())}
    ics = {}
    for t in targets:
        ic = daily_ic(df, signal, t, cfg.min_names_per_day)
        ics[t] = ic
        m, tt, n = nw_t(ic, cfg.nw_lags)
        out[f"ic_{t}"], out[f"t_{t}"], out[f"days_{t}"] = m, tt, float(n)
    if len(targets) >= 2:
        a, b = ics[targets[1]], ics[targets[0]]
        both = pd.concat([a, b], axis=1, join="inner")
        m, tt, n = nw_t(both.iloc[:, 0] - both.iloc[:, 1], cfg.nw_lags) if len(both) else (np.nan, np.nan, 0)
        out[f"diff_{targets[1]}_minus_{targets[0]}"], out["t_diff"] = m, tt
    return out


def is_leaky(row: dict[str, float] | pd.Series, t_threshold: float | None = None) -> bool:
    """PREREG §6.4: IC(z_id) ≥ IC(z_on) with t(IC(z_id)) > threshold."""
    thr = load_news_config().audit.leak_t if t_threshold is None else t_threshold
    ic_id, ic_on, t_id = row["ic_z_id"], row["ic_z_on"], row["t_z_id"]
    if any(pd.isna(v) for v in (ic_id, ic_on, t_id)):
        return False
    return bool(ic_id >= ic_on and t_id > thr)


# --- ticker-day signals ------------------------------------------------------------------------------


def sentiment_score(direction: pd.Series) -> pd.Series:
    return direction.map(load_news_config().sentiment_scale).astype("float")


def ticker_day(arts: pd.DataFrame, session_col: str, by: Sequence[str] = ()) -> pd.DataFrame:
    """Mean vendor sentiment per (company_id, session[, by...]) of ``arts`` (sessions ≤ PUBLIC_END)."""
    a = public_only(arts, session_col)
    a = a.assign(
        session=pd.to_datetime(a[session_col]).dt.date, sent=sentiment_score(a["sentiment_direction"])
    )
    keys = ["company_id", "session", *by]
    return a.groupby(keys, as_index=False, dropna=False).agg(sent=("sent", "mean"), n_articles=("id", "size"))


def join_targets(td: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    assert_public(td["session"], "ticker-days")
    cols = ["company_id", "session", *[c for c in panel.columns if c.startswith(("z_", "ar_"))]]
    p = panel[cols].copy()
    p["session"] = pd.to_datetime(p["session"]).dt.date
    return td.merge(p, on=["company_id", "session"], how="inner")


def ic_table(td: pd.DataFrame, cells: str | None, targets: Sequence[str] = TARGETS) -> pd.DataFrame:
    """One ic_row per value of ``cells`` (or one row for all) on a joined ticker-day frame."""
    rows = []
    groups: Iterable[tuple[object, pd.DataFrame]] = [("all", td)] if cells is None else td.groupby(cells)
    for value, g in groups:
        row: dict[str, object] = {"cell": cells or "all", "value": value, **ic_row(g, "sent", targets)}
        rows.append(row)
    return pd.DataFrame(rows)


# --- S10 leakage audit -------------------------------------------------------------------------------

LEAKAGE_CELLS: Final = ("summary_present", "source_class", "precision", "after_fact")


def leakage_audit(arts: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """W0 kept articles; IC of vendor sentiment with z_on and z_id per cell; the §6.4 LEAKY flag."""
    w0 = arts.loc[arts["keep"] & arts["session_w0"].notna()]
    parts = [ic_table(join_targets(ticker_day(w0, "session_w0"), panel), None)]
    for cell in LEAKAGE_CELLS:
        td = join_targets(ticker_day(w0, "session_w0", by=[cell]), panel)
        parts.append(ic_table(td, cell))
    out = pd.concat(parts, ignore_index=True)
    out["leaky"] = [is_leaky(r) for _, r in out.iterrows()]
    out["value"] = out["value"].astype("str")
    return out


def frozen_news_section(leak: pd.DataFrame, leak_csv: Path) -> dict[str, object]:
    """The ``news:`` block of configs/frozen.yaml implied by the leakage table (PRD NA-02 S10)."""
    summary = leak[(leak["cell"] == "summary_present") & (leak["value"] == "True")]
    allowed = bool(len(summary) == 1 and not bool(summary["leaky"].iloc[0]))
    excluded = sorted(leak.loc[(leak["cell"] == "source_class") & leak["leaky"], "value"].astype(str))
    return {
        "summary_variant_allowed": allowed,
        "excluded_sources": excluded,
        "leakage_audit_sha": hashlib.sha256(leak_csv.read_bytes()).hexdigest(),
        "leakage_audit_file": "artifacts/NA-02/leakage_ic.csv",
        "parsing_allowed_none": clean.none_policy(),  # the operator's decision survives a re-run
    }


def write_frozen_news(section: dict[str, object], path: Path = CONFIGS / "frozen.yaml") -> None:
    """Replace the ``news:`` entry of frozen.yaml in place, keeping every other line and comment."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln.startswith("news:"))
    end = start + 1
    while end < len(lines) and lines[end].startswith((" ", "\t")):
        end += 1

    def scalar(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, list):
            return "[" + ", ".join(str(x) for x in v) + "]"
        return str(v)

    block = ["news:                # NA-02 (PRD S10): leakage audit, PREREG §6.4; §6.1 None policy\n"]
    block += [f"  {k}: {scalar(v)}\n" for k, v in section.items()]
    path.write_text("".join(lines[:start] + block + lines[end:]), encoding="utf-8")


# --- S3 timing audit ---------------------------------------------------------------------------------


def same_session(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise equality of two session columns; two missing sessions are equal."""
    na, nb = a.isna().to_numpy(), b.isna().to_numpy()
    da = pd.to_datetime(a.where(~na, None)).dt.date.to_numpy()
    db = pd.to_datetime(b.where(~nb, None)).dt.date.to_numpy()
    return pd.Series((na & nb) | (~na & ~nb & (da == db)), index=a.index)


def affected_share(arts: pd.DataFrame) -> pd.DataFrame:
    """Per t_avail year and precision class: share of articles whose W0 / W2 session differs from naive."""
    a = arts.assign(year=arts["t_avail"].dt.year)
    a["w0_changed"] = ~same_session(a["session_w0"], a["session_w0_naive"])
    a["w2_changed"] = ~same_session(a["session_w2"], a["session_w2_naive"])
    return (
        a.groupby(["year", "precision"])
        .agg(articles=("id", "size"), w0_changed=("w0_changed", "mean"), w2_changed=("w2_changed", "mean"))
        .reset_index()
    )


def d0_ticker_day_change(arts: pd.DataFrame) -> pd.DataFrame:
    """Per t_avail year: D0 ticker-days (company, session with ≥ 1 W0 article), naive vs PREREG rule."""
    rows = []
    for year, g in arts.groupby(arts["t_avail"].dt.year):
        p = g.loc[g["session_w0"].notna()]
        n = g.loc[g["session_w0_naive"].notna()]
        ps = p.groupby(["company_id", "session_w0"])["id"].agg(frozenset).rename("p")
        ns = n.groupby(["company_id", "session_w0_naive"])["id"].agg(frozenset).rename("n")
        ns.index = ns.index.set_names(ps.index.names)
        both = pd.concat([ps, ns], axis=1, join="outer")
        in_p, in_n = both["p"].notna(), both["n"].notna()
        changed = [a != b for a, b in zip(both["p"], both["n"], strict=True)]
        rows.append(
            {
                "year": int(year),
                "d0_ticker_days_naive": int(in_n.sum()),
                "d0_ticker_days_prereg": int(in_p.sum()),
                "naive_not_in_prereg": float((in_n & ~in_p).sum() / max(int(in_n.sum()), 1)),
                "prereg_not_in_naive": float((in_p & ~in_n).sum() / max(int(in_p.sum()), 1)),
                "article_set_changed": float(np.mean(changed)) if changed else np.nan,
            }
        )
    return pd.DataFrame(rows)


def leak_signature(arts: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """W0 articles by precision class: sentiment IC with z_on / z_id under the naive vs the PREREG rule."""
    parts = []
    for rule, col in (("naive", "session_w0_naive"), ("prereg", "session_w0")):
        w0 = arts.loc[arts[col].notna()]
        td = join_targets(ticker_day(w0, col, by=["precision"]), panel)
        t = ic_table(td, "precision")
        t.insert(0, "rule", rule)
        parts.append(t)
        t_all = ic_table(join_targets(ticker_day(w0, col), panel), None)
        t_all.insert(0, "rule", rule)
        parts.append(t_all)
    return pd.concat(parts, ignore_index=True)


# --- S13 re-derived diagnostics ----------------------------------------------------------------------


def news_status(arts: pd.DataFrame, panel: pd.DataFrame, covered: pd.DataFrame) -> pd.DataFrame:
    """Covered member-days (rep class) labelled no_news / intraday_only / pre_open / pre_open_earnings."""
    k = public_only(arts.loc[arts["keep"]], "session_w2")
    w2 = set(zip(k["company_id"], pd.to_datetime(k["session_w2"]).dt.date, strict=True))
    k0 = k.loc[k["session_w0"].notna()]
    w0 = set(zip(k0["company_id"], pd.to_datetime(k0["session_w0"]).dt.date, strict=True))
    earn = k0.loc[k0["tag_type"] == "earnings_results"]
    w0e = set(zip(earn["company_id"], pd.to_datetime(earn["session_w0"]).dt.date, strict=True))
    p = panel.copy()
    p["session"] = pd.to_datetime(p["session"]).dt.date
    p["month"] = pd.to_datetime(p["session"]).dt.strftime("%Y-%m")
    p = p.merge(covered.loc[covered["covered"], ["month", "company_id"]], on=["month", "company_id"])
    key = list(zip(p["company_id"], p["session"], strict=True))
    p["status"] = np.select(
        [[x in w0e for x in key], [x in w0 for x in key], [x in w2 for x in key]],
        ["pre_open_earnings", "pre_open", "intraday_only"],
        default="no_news",
    )
    return p


def variance_shares(p: pd.DataFrame) -> pd.DataFrame:
    """Overnight share of stock-specific variance, Σ AR_on² / (Σ AR_on² + Σ AR_id²), by news status."""
    d = p.dropna(subset=["ar_on", "ar_id"])
    rows = []
    for status, x in d.groupby("status", sort=True):
        on2, id2 = float((x["ar_on"] ** 2).sum()), float((x["ar_id"] ** 2).sum())
        rows.append(
            {
                "status": status,
                "member_days": len(x),
                "overnight_share": on2 / (on2 + id2),
                "mean_abs_z_on": float(x["z_on"].abs().mean()),
                "mean_abs_z_id": float(x["z_id"].abs().mean()),
            }
        )
    return pd.DataFrame(rows)


def fama_macbeth_bp(td: pd.DataFrame, target: str, lags: int) -> tuple[float, float]:
    """Mean daily OLS slope (bp of AR per sentiment unit) and its NW t."""
    slopes = []
    for _, g in td[["session", "sent", target]].dropna().groupby("session"):
        if len(g) >= 10 and g["sent"].std() > 0:
            slopes.append(np.polyfit(g["sent"], g[target], 1)[0] * 1e4)
    m, t, _ = nw_t(pd.Series(slopes), lags)
    return m, t


def continuation(td: pd.DataFrame, by: str) -> pd.DataFrame:
    """After |z_on| > 2: sign(z_on)·z_id and sign(z_on)·z_5d, mean / t / n per ``by``."""
    big = td.loc[td["z_on"].abs() > 2].copy()
    s = np.sign(big["z_on"])
    big["cont_id"], big["cont_5d"] = s * big["z_id"], s * big["z_5d"]
    rows = []
    for value, g in big.groupby(by, dropna=False):
        row: dict[str, object] = {by: value, "events": len(g)}
        for c in ("cont_id", "cont_5d"):
            x = g[c].dropna()
            row[f"{c}_mean"] = float(x.mean()) if len(x) else np.nan
            row[f"{c}_t"] = float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("events", ascending=False)


def top_tag(arts: pd.DataFrame, session_col: str) -> pd.DataFrame:
    """The most frequent vendor tag among a ticker-day's articles (ties: earliest article's tag)."""
    a = public_only(arts, session_col).sort_values(["t_avail", "id"])
    a = a.assign(session=pd.to_datetime(a[session_col]).dt.date)
    counts = a.groupby(["company_id", "session", "tag_type"], sort=False).size().rename("n").reset_index()
    counts = counts.sort_values(["company_id", "session", "n"], ascending=[True, True, False], kind="stable")
    return counts.drop_duplicates(["company_id", "session"])[["company_id", "session", "tag_type"]]


# --- CLI: python -m newsaction.news.audit (PRD NA-02 S10) ---------------------------------------------

LEAKAGE_CSV: Final = "artifacts/NA-02/leakage_ic.csv"


def main(argv: list[str] | None = None) -> int:
    """Write artifacts/NA-02/leakage_ic.csv and the ``news:`` section of configs/frozen.yaml."""
    cols = ["id", "company_id", "session_w0", "keep", "sentiment_direction", *LEAKAGE_CELLS]
    arts = io.read_parquet(ARTICLES, columns=cols)
    leak = leakage_audit(arts, public_targets())
    path = ROOT / LEAKAGE_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    leak.to_csv(path, index=False, float_format="%.6g")
    section = frozen_news_section(pd.read_csv(path, dtype={"value": str}), path)
    write_frozen_news(section)
    print(leak.to_string(index=False))
    print(f"news.audit: frozen.yaml news = {section}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
