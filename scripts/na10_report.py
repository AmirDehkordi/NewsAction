"""NA-10 report tables: ``uv run python scripts/na10_report.py`` -> artifacts/NA-10/{summary.json, *.csv}.

Public sessions only (≤ val-B end). The test-period bars are counted from the FMP ledger and the manifest
(requests, rows), never opened.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.bars import (
    BARS_PUBLIC,
    BARS_QC,
    CAPABILITY,
    INTRADAY_PUBLIC,
    INTRADAY_SPY_PUBLIC,
    load_bars_config,
)
from newsaction.config import load_project, load_splits
from newsaction.ledger import FmpLedger
from newsaction.panel.targets import blinded_bars_file
from newsaction.paths import ROOT

OUT = ROOT / "artifacts" / "NA-10"
QUANTILES = (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)


def _q(x: pd.Series) -> dict[str, float]:
    x = x.dropna()
    return {f"q{int(q * 100):02d}": round(float(x.quantile(q)), 6) for q in QUANTILES} | {"n": len(x)}


def ledger_summary() -> dict[str, Any]:
    recs = FmpLedger().records()
    req = {r["n"]: r for r in recs if r["event"] == "request"}
    resp = {r["n"]: r for r in recs if r["event"] == "response"}
    by: dict[str, dict[str, int]] = {}
    for n, r in req.items():
        p = str(r["meta"]["purpose"])
        d = by.setdefault(p, {"requests": 0, "answered_200": 0, "rows": 0, "empty": 0, "retries": 0})
        d["requests"] += 1
        d["retries"] += int(r["meta"].get("attempt", 1) > 1)
        a = resp.get(n)
        if a is not None and a["status"] == 200:
            d["answered_200"] += 1
            d["rows"] += int(a["rows"] or 0)
            d["empty"] += int((a["rows"] or 0) == 0)
    statuses = Counter(str(r["status"]) for r in resp.values())
    return {
        "requests": len(req),
        "cap": load_project().fmp_request_cap,
        "by_purpose": by,
        "statuses": dict(statuses),
        "unanswered": sorted(set(req) - set(resp)),
    }


def member_sessions() -> pd.DataFrame:
    lo, hi = load_bars_config().fetch.stock_start, load_splits().splits["val_b"].end
    cols = ["session", "symbol_id", "ticker", "tier", "member", "is_rep", "raw_open"]
    pan = io.read_parquet("panel/panel_public.parquet", columns=cols)
    keep = pan["member"] & pan["is_rep"] & pan["raw_open"].notna()
    keep &= np.asarray([lo <= d <= hi for d in pan["session"]], dtype=bool)
    qc = io.read_parquet(BARS_QC)
    out = pan.loc[keep, ["session", "symbol_id", "ticker", "tier"]].merge(
        qc, on=["session", "symbol_id"], how="left"
    )
    out["half_day"] = [calendar.is_half_day(d) for d in out["session"]]
    out["basis"] = out["basis"].fillna("no_bars")
    for c in ("complete", "open_ok", "usable"):
        out[c] = out[c].fillna(False).astype(bool)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cap = json.loads((ROOT / CAPABILITY).read_text())
    m = member_sessions()
    bad = m.loc[~m["complete"] | ~m["usable"]]
    bad[
        ["ticker", "session", "n_regular", "n_expected", "basis", "phi_open", "phi_close", "level_prev"]
    ].sort_values(["ticker", "session"]).to_csv(OUT / "member_session_exceptions.csv", index=False)
    qc = io.read_parquet(BARS_QC)
    sym = io.read_parquet("snapshot/symbols.parquet", columns=["symbol_id", "ticker"]).set_index("symbol_id")[
        "ticker"
    ]
    by_sym = qc.groupby("symbol_id").agg(
        sessions=("session", "size"),
        as_traded=("basis", lambda b: int((b == "as_traded").sum())),
        rescaled=("basis", lambda b: int((b == "rescaled").sum())),
        inconsistent=("basis", lambda b: int((b == "inconsistent").sum())),
        factor_min=("factor", "min"),
        factor_max=("factor", "max"),
        first_rescaled=(
            "session",
            lambda s: min(
                (d for d, b in zip(s, qc.loc[s.index, "basis"], strict=True) if b == "rescaled"), default=None
            ),
        ),
        last_rescaled=(
            "session",
            lambda s: max(
                (d for d, b in zip(s, qc.loc[s.index, "basis"], strict=True) if b == "rescaled"), default=None
            ),
        ),
    )
    by_sym.insert(0, "ticker", by_sym.index.map(sym))
    by_sym.loc[by_sym["rescaled"] + by_sym["inconsistent"] > 0].sort_values(
        "rescaled", ascending=False
    ).to_csv(OUT / "basis_by_symbol.csv")
    intra = io.read_parquet(INTRADAY_PUBLIC)
    intra = intra.loc[intra["member"] & intra["is_rep"]]
    spy = io.read_parquet(INTRADAY_SPY_PUBLIC)
    ev = io.read_parquet("events/events_d0.parquet", columns=["session", "symbol_id", "split"])
    ev = ev.loc[ev["split"].isin(["train", "val_a", "val_b"])].merge(
        intra.drop(columns=["split"]), on=["session", "symbol_id"], how="left"
    )
    pub_bars = io.load_manifest()["artifacts"]
    sealed = {k: v for k, v in pub_bars.items() if k.endswith(f"{blinded_bars_file()}.parquet")}
    summary: dict[str, Any] = {
        "ledger": ledger_summary(),
        "capability": {k: cap[k] for k in ("facts", "decision", "projection")},
        "bars_public_rows": pub_bars[f"work/{BARS_PUBLIC}"]["rows"],
        "bars_test_rows_from_manifest": {k: v["rows"] for k, v in sealed.items()},
        "member_sessions": {
            "n": len(m),
            "complete": round(float(m["complete"].mean()), 5),
            "half_day_n": int(m["half_day"].sum()),
            "half_day_seven_bars": round(float((m.loc[m["half_day"], "n_regular"] == 7).mean()), 5),
            "usable": round(float(m["usable"].mean()), 5),
            "open_within_5bp": round(float(m["open_ok"].mean()), 5),
            "abs_open_dev_bp": _q(m["open_dev_bp"].abs()),
            "basis": m["basis"].value_counts().to_dict(),
            "exceptions": len(bad),
            "exceptions_by_kind": bad["basis"].value_counts().to_dict(),
        },
        "intraday_member_rows": {
            "n": len(intra),
            "with_p10": int(intra["p10"].notna().sum()),
            "with_p1530": int(intra["p1530"].notna().sum()),
            "with_p_pre": int(intra["p_pre"].notna().sum()),
            "with_g_d1": int(intra["g_d1"].notna().sum()),
            "with_y1": int(intra["y1"].notna().sum()),
        },
        "sigma_30": _q(intra["sigma_30"]),
        "sigma_rest": _q(intra["sigma_rest"]),
        "sigma_on_over_sigma_30": _q(intra["sigma_on"] / intra["sigma_30"]),
        "g_d1": _q(intra["g_d1"]),
        "g_d1_lvl": _q(intra["g_d1_lvl"]),
        "y1": _q(intra["y1"]),
        "corr_g_d1_lvl_vs_g_d2_lvl": None,
        "d1_events_train_val": {
            "n": len(ev),
            "with_g_d1": int(ev["g_d1"].notna().sum()),
            "by_split": ev.groupby("split")["g_d1"].apply(lambda x: int(x.notna().sum())).to_dict(),
        },
        "spy_sessions": len(spy),
    }
    pan = io.read_parquet("panel/panel_public.parquet", columns=["session", "symbol_id", "g_d2_lvl"])
    j = intra[["session", "symbol_id", "g_d1_lvl"]].merge(pan, on=["session", "symbol_id"])
    summary["corr_g_d1_lvl_vs_g_d2_lvl"] = round(
        float(j[["g_d1_lvl", "g_d2_lvl"]].corr(method="spearman").iloc[0, 1]), 4
    )
    d1 = ROOT / "artifacts" / "NA-10" / "build_states_d1.json"
    if d1.is_file():
        summary["states_d1"] = json.loads(d1.read_text())
        st = io.read_parquet(
            "states/callB_d1_E3.parquet",
            columns=["split", "n_tokens_state", "n_tokens_with_questions", "n_articles"],
        )
        summary["states_d1_tokens"] = {
            "p50": int(st["n_tokens_state"].quantile(0.5)),
            "p95": int(st["n_tokens_state"].quantile(0.95)),
            "max": int(st["n_tokens_state"].max()),
            "max_with_core_questions": int(st["n_tokens_with_questions"].max()),
            "by_split": st["split"].value_counts().to_dict(),
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
