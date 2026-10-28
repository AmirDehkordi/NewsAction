"""NA-12 S3: every table of the analysis as CSV and LaTeX (booktabs), with a machine-readable key (PRD NA-12).

    uv run python -m newsaction.analysis.tables

Reads ``artifacts/NA-12/results/*.json`` (``run_all``) and writes ``artifacts/NA-12/tables/<name>.{csv,tex}``
plus two files:
- ``keys.json``: "<table>/<key>/<column>" → value for every non-empty cell. A caption cites a number as
  ``{{t1_primary/H1/primary_p}}``; ``cite`` renders it with the tables' formatting and fails on an unknown
  key, so NA-14's captions can be tested against the tables (``tests/test_tables_keys.py``);
- ``index.json``: each table's title, columns, notes and files.

Every table has a ``key`` column, unique within the table. ``required`` lists the keys that every
pre-registered test must have (PRD NA-12 AC4: nulls, "not available" and failed robustness rows included);
``missing`` reports those absent, and ``main`` fails when any is.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from newsaction.analysis import spec
from newsaction.analysis.run_all import ANCHOR, API, FOCUS, MODELS, PRIMARY, RESULTS, TESTS
from newsaction.analysis.unblind import ARTIFACTS
from newsaction.paths import Layout, resolve_layout

TABLES: Final = "tables"
CITE: Final = re.compile(r"\{\{([^{}]+)\}\}")
P_COLUMNS: Final = re.compile(r"(^|_)(p|q)(_|$)|p_holm|p_two|p_dk")
COUNTS: Final = re.compile(r"^(n|nobs.*|n_.*|.*_n|df_t|rows)$")
SECONDARY_TESTS: Final = (
    "H5",
    "H6",
    "H7",
    "H2C_kappa_hstar",
    "H2C_kappa_increase",
    "H2C_lambda_t5",
    "H2C_tracking_naive",
    "A3.4",
)
STATEMENTS: Final = {
    "H1": "IC(N̂_W0, z_on) − IC(N̂_W0, z_id) > 0 (priced at the open)",
    "H1b": "IC(N̂_W0, z_id) > 0 (not fully priced at the open)",
    "H2": "y2 = a + b·N̂_W2 + c·G + FE: b > 0 and c < 0",
    "H3": "ΔIC(R+N+J vs R+N) for y2 > 0",
    "H4": "ΔR² of the news readings for |z_cc| over HAR + earnings + tier > 0",
}


@dataclass(frozen=True)
class Table:
    name: str
    title: str
    frame: pd.DataFrame
    notes: tuple[str, ...] = ()


def _num(x: Any) -> float:
    if isinstance(x, str) and x in (
        "inf",
        "-inf",
    ):  # the results JSON stores ±∞ as strings (a half-life "never")
        return float(x)
    if x is None or isinstance(x, str | bool):
        return math.nan
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _est(r: Any) -> dict[str, Any]:
    """value, CI, NW t, p and sizes of a spec ``Estimate`` dict ("available": False otherwise)."""
    if not isinstance(r, Mapping) or r.get("available") is False:
        return {"available": False}
    return {
        "estimate": _num(r.get("value", r.get("estimate"))),
        "ci_low": _num(r.get("ci_low")),
        "ci_high": _num(r.get("ci_high")),
        "nw_t": _num(r.get("nw_t")),
        "p": _num(r.get("p")),
        "n_days": r.get("n_days"),
        "n_obs": r.get("n_obs"),
        "available": True,
    }


def _frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if "key" not in df.columns:
        raise ValueError("a table needs a key column")
    dup = df.loc[df["key"].duplicated(), "key"].tolist()
    if dup:
        raise ValueError(f"duplicate keys: {dup[:5]}")
    slash = [k for k in df["key"].astype(str) if "/" in k]
    if slash:
        raise ValueError(f"a key may not hold '/' (keys.json separates table/key/column): {slash[:5]}")
    return df[["key", *[c for c in df.columns if c != "key"]]]


# --- primary ---------------------------------------------------------------------------------------------


def t1_primary(r: Mapping[str, Any]) -> Table:
    pr = r["primary"]
    m = pr["models"]
    rows = []
    for t in TESTS:
        p, a = _est(m[PRIMARY][t]), _est(m[ANCHOR][t])
        dp, da = pr["directional"]["primary"].get(t, {}), pr["directional"]["anchor"].get(t, {})
        rows.append(
            {
                "key": t,
                "hypothesis": t,
                "statement": STATEMENTS[t],
                "primary_estimate": _num(dp.get("estimate")),
                "primary_ci_low": p.get("ci_low"),
                "primary_ci_high": p.get("ci_high"),
                "primary_p": _num(dp.get("p")),
                "primary_p_holm": _num(pr["holm"].get(t)),
                "anchor_estimate": _num(da.get("estimate")),
                "anchor_ci_low": a.get("ci_low"),
                "anchor_ci_high": a.get("ci_high"),
                "anchor_p": _num(da.get("p")),
                "verdict": pr["headline"][t],
            }
        )
    return Table(
        "t1_primary",
        "Primary hypotheses (Holm over H1, H1b, H2, H3, H4; §1.3 headline rule): Laya-Fin and the anchor",
        _frame(rows),
        (
            "Estimates in each hypothesis' direction (H2: min(b, −c)); p one-sided; the anchor's p is its "
            "own (§1.3), not Holm-adjusted. H2's CI is in t2 (b and c separately).",
            "The anchor's direction, H2 and continuation readings are uninformative (NA-11 REPORT §7.1).",
        ),
    )


def t1b_by_model(r: Mapping[str, Any]) -> Table:
    pr = r["primary"]["models"]
    rows = []
    for mod in MODELS:
        res = pr[mod.key]
        for t in TESTS:
            e = _est(res[t])
            row: dict[str, Any] = {"key": f"{mod.key}:{t}", "model": mod.key, "test": t, "role": mod.role}
            if e["available"]:
                d = spec.directional({**res[t], "test": t})
                row |= {**e, "estimate": d["estimate"], "p": d["p"]}
                row["p_holm_within_model"] = res["holm_within_model"][t]
            else:
                row |= {"available": False, "reason": res[t].get("reason")}
            row["footnote"] = mod.footnote
            rows.append(row)
    return Table(
        "t1b_primary_by_model",
        "H1–H4 for every decision model (the API models screen-failing and model-specific)",
        _frame(rows),
        ("Holm within each model is descriptive; only Laya-Fin's Holm enters the headline rule.",),
    )


H2_COLS: Final = (
    "b",
    "b_se",
    "b_t",
    "b_p",
    "b_se_dk",
    "b_p_dk",
    "c",
    "c_se",
    "c_t",
    "c_p",
    "c_se_dk",
    "c_p_dk",
)


def _h2_row(key: str, model: str, label: str, h: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"key": key, "model": model, "variant": label}
    if h.get("available") is False:
        return row | {"available": False, "reason": h.get("reason")}
    row |= {"available": True, **{c: _num(h.get(c)) for c in H2_COLS}}
    row |= {c: h.get(c) for c in ("p", "p_dk", "nobs", "n_sessions", "n_firms", "df_t", "r2_within")}
    return row


def t2_h2(r: Mapping[str, Any]) -> Table:
    rows = []
    for mod in MODELS:
        res = r["primary"]["models"][mod.key]
        for pt, name in (("D2", "H2"), ("D1", "H2_D1"), ("D0", "H2_D0")):
            rows.append(_h2_row(f"{mod.key}:{pt}", mod.key, pt, res[name]))
        if isinstance(res["H2_by_abs_g"], list):
            for h in res["H2_by_abs_g"]:
                b = h["abs_g_bin"]
                rows.append(_h2_row(f"{mod.key}:D2:absG{b}", mod.key, f"D2, |G| in {b}", h))
    return Table(
        "t2_h2_over_under",
        "Over/under regression y = a + b·N̂ + c·G + day × tier FE by decision point and within |G| bins",
        _frame(rows),
        (
            "Two-way clustered (session, firm) SEs; Driscoll–Kraay (5 lags) SEs and p in the _dk columns.",
            "D2: y2, G = z_cc,t, N̂ from Call A on W2; D1: y1, G at 10:00, N̂_W0; D0: y0 = z_id, no G.",
        ),
    )


def t3_ic(r: Mapping[str, Any]) -> Table:
    rows = []
    for mod in MODELS:
        res = r["primary"]["models"][mod.key]
        ic, qs = res.get("ic", {}), res.get("quintiles", {})
        for tgt in ("z_cc", "z_on", "z_id"):
            if f"ic_{tgt}" not in ic:
                continue
            q = _est(qs.get(tgt, {}))
            rows.append(
                {
                    "key": f"{mod.key}:{tgt}",
                    "model": mod.key,
                    "target": tgt,
                    "ic": _num(ic[f"ic_{tgt}"]),
                    "ic_t": _num(ic[f"ic_{tgt}_t"]),
                    "ic_ci_low": _num(ic[f"ic_{tgt}_ci_low"]),
                    "ic_ci_high": _num(ic[f"ic_{tgt}_ci_high"]),
                    "n_days": ic[f"ic_{tgt}_days"],
                    "n_obs": ic[f"ic_{tgt}_n"],
                    "qspread": q.get("estimate"),
                    "qspread_t": q.get("nw_t"),
                    "qspread_p": q.get("p"),
                }
            )
    return Table(
        "t3_ic", "Daily IC of N̂_W0 with z_cc, z_on and z_id, and quintile spreads (§11.1)", _frame(rows)
    )


# --- secondary and heterogeneity --------------------------------------------------------------------------


def _secondary_estimate(name: str, t: Mapping[str, Any], conv: Mapping[str, Any]) -> dict[str, Any]:
    if name == "H5":
        return {"estimate": _num(t.get("estimate"))}
    if name in ("H6", "A3.4"):
        lab = "d" if name == "H6" else "theta"
        return {"estimate": _num(t.get(lab)), "se": _num(t.get(f"{lab}_se")), "nobs": t.get("nobs")}
    if name == "H7":
        return {
            "estimate": _num(t.get("value")),
            "ci_low": _num(t.get("ci_low")),
            "ci_high": _num(t.get("ci_high")),
        }
    lad, gap, te = conv["ladder"], conv["gap_d2"], conv["tracking"]
    if name == "H2C_kappa_hstar":
        k = lad["rungs"].get("C_t+20", {})
        return {"estimate": _num(k.get("kappa")), "se": _num(k.get("kappa_se")), "nobs": k.get("nobs")}
    if name == "H2C_kappa_increase":
        inc = lad.get("increase", {})
        return {
            "estimate": _num(inc.get("value")),
            "ci_low": _num(inc.get("ci_low")),
            "ci_high": _num(inc.get("ci_high")),
        }
    if name == "H2C_lambda_t5":
        g = gap["rungs"].get("C_t+5", {})
        return {"estimate": _num(g.get("lambda")), "se": _num(g.get("lambda_se")), "nobs": g.get("nobs")}
    n = te["rungs"].get("C_t+20", {}).get("naive", {})
    return {
        "estimate": _num(n.get("ratio")),
        "ci_low": _num(n.get("ci_low")),
        "ci_high": _num(n.get("ci_high")),
    }


def t4_secondary(r: Mapping[str, Any]) -> Table:
    sec = r["secondary"]
    conv = r["convergence"]["models"]
    pooled = sec["families"]["pooled_sensitivity"]["q"]
    rows = []
    for key in FOCUS:
        fam, tests = sec["families"][key], sec["tests"][key]
        for name in SECONDARY_TESTS:
            t = tests.get(name, {"available": False, "reason": "not run"})
            row: dict[str, Any] = {"key": f"{key}:{name}", "model": key, "test": name}
            if t.get("available") is False:
                rows.append(row | {"available": False, "reason": t.get("reason")})
                continue
            row |= {"available": True, **_secondary_estimate(name, t, conv[key]), "p": _num(t.get("p"))}
            row |= {"in_family": name in fam["tests"], "q": _num(fam["q"].get(name))}
            row["q_pooled"] = _num(pooled.get(f"{key}:{name}"))
            rows.append(row)
    return Table(
        "t4_secondary",
        "Secondary hypotheses (BH, q = 0.10, within each instrument; pooled sensitivity family)",
        _frame(rows),
        (
            "H6 and A3.4 need tone and the explanation answer (Q16), which the trained models do not give.",
            "The pooled family adds d1-ultra's H6 and A3.4 to Laya-Fin's six (PREREG §15 NA-12 row).",
        ),
    )


def t5_heterogeneity(r: Mapping[str, Any]) -> Table:
    rows = []
    for key, cuts in r["heterogeneity"]["models"].items():
        for c in cuts:
            rows.append(
                {"key": f"{key}:{c['cut']}", "model": key, **{k: v for k, v in c.items() if k != "split"}}
            )
    return Table(
        "t5_heterogeneity",
        "Heterogeneity cuts on H2 at D2: Wald test of N̂·1[cut] and G·1[cut], BH over each model's eight cuts",
        _frame(rows),
        ("Laya-Fin's eight cuts are the family; the anchor's and d1-ultra's are reported.",),
    )


# --- convergence (A1) -------------------------------------------------------------------------------------

KAPPA_COLS: Final = ("kappa", "kappa_se", "kappa_t", "kappa_p", "kappa_se_dk", "kappa_p_dk")
GAP_COLS: Final = ("lambda", "lambda_se", "lambda_p", "lambda_p_dk", "psi", "psi_se", "psi_p_two")


def t6_ladder(r: Mapping[str, Any]) -> Table:
    rows: list[dict[str, Any]] = []
    for key, res in r["convergence"]["models"].items():
        for variant in ("ladder", "ladder_clean", "ladder_h10", "ladder_plateau"):
            lad = res[variant]
            share = lad.get("share_h_star_robust" if variant == "ladder_h10" else "share_h_star", {})
            for rung, k in lad["rungs"].items():
                row: dict[str, Any] = {"key": f"{key}:{variant}:{rung}", "model": key, "variant": variant}
                row["rung"] = rung
                if not k.get("available", False):
                    rows.append(row | {"available": False, "nobs": k.get("nobs")})
                    continue
                row |= {"available": True, **{c: _num(k.get(c)) for c in KAPPA_COLS}}
                rows.append(row | {"share_of_h_star": _num(share.get(rung)), "nobs": k.get("nobs")})
            inc = lad.get("increase")
            if inc:
                rows.append(
                    {
                        "key": f"{key}:{variant}:increase",
                        "model": key,
                        "variant": variant,
                        "rung": f"{inc['from']} → {inc['to']}",
                        "available": True,
                        "kappa": _num(inc["value"]),
                        "ci_low": _num(inc["ci_low"]),
                        "ci_high": _num(inc["ci_high"]),
                        "kappa_p": _num(inc["p"]),
                    }
                )
    return Table(
        "t6_convergence_ladder",
        "A1 convergence ladder: κ_h of CAR^lvl_h on V (D0 events, day × tier FE) and the shares κ_h / κ_h*",
        _frame(rows),
        (
            "ladder_clean: each rung on its clean-window events; ladder_h10: h* = t+10; ladder_plateau: the "
            "mean CAR^lvl over t+16..t+20. The C_t+60 rung is exploratory.",
        ),
    )


def t7_gap(r: Mapping[str, Any]) -> Table:
    rows: list[dict[str, Any]] = []
    for key, res in r["convergence"]["models"].items():
        for point in ("D2", "D1"):
            gp = res[f"gap_{point.lower()}"]
            for variant, rungs in (("all", gp["rungs"]), ("clean", res[f"gap_{point.lower()}_clean"])):
                for rung, g in rungs.items():
                    row: dict[str, Any] = {
                        "key": f"{key}:{point}:{variant}:{rung}",
                        "model": key,
                        "point": point,
                    }
                    row |= {"variant": variant, "rung": rung}
                    if not g.get("available", False):
                        rows.append(row | {"available": False})
                        continue
                    row |= {"available": True, **{c: _num(g.get(c)) for c in GAP_COLS}}
                    rows.append(row | {"nobs": g.get("nobs")})
            rows.append(
                {
                    "key": f"{key}:{point}:all:half_life",
                    "model": key,
                    "point": point,
                    "variant": "all",
                    "rung": "half-life (sessions)",
                    "available": True,
                    "lambda": _num(gp["half_life_sessions"]),
                    "ci_low": _num(gp["half_life_ci"][0]),
                    "ci_high": _num(gp["half_life_ci"][1]),
                }
            )
    return Table(
        "t7_gap_closure",
        "A1 gap closure AR(τ→h)/σ = a + λ_h·U_τ + ψ_h·V (+ FE) at D2 and D1; half-life (first λ_h >= 0.5)",
        _frame(rows),
        ("ψ carries its two-sided p (ψ_h* = 0, outside every family); a half-life of ∞ is beyond t+20.",),
    )


def t8_tracking(r: Mapping[str, Any]) -> Table:
    rows = []
    for key, res in r["convergence"]["models"].items():
        for rung, t in res["tracking"]["rungs"].items():
            row: dict[str, Any] = {
                "key": f"{key}:{rung}",
                "model": key,
                "rung": rung,
                "rmse": _num(t.get("rmse")),
            }
            row["nobs"] = t.get("nobs")
            for b in ("naive", "price_only"):
                x = t.get(b, {})
                for c in ("ratio", "ci_low", "ci_high", "p"):
                    row[f"{b}_{c}"] = _num(x.get(c))
            rows.append(row)
    return Table(
        "t8_tracking_error",
        "A1 tracking error RMSE(CAR^lvl_h − V) relative to the naive 0 and to the price-only V",
        _frame(rows),
    )


def _cut_row(key: str, cut: str, level: str, lad: Any, gap: Any, te: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"key": f"{key}:{cut}:{level}", "model": key, "cut": cut, "level": level}
    if isinstance(lad, Mapping) and "rungs" in lad:
        k, k0 = lad["rungs"].get("C_t+20", {}), lad["rungs"].get("C_t", {})
        row |= {
            "kappa_t20": _num(k.get("kappa")),
            "kappa_t20_p": _num(k.get("kappa_p")),
            "nobs_d0": k.get("nobs"),
        }
        row |= {"kappa_ct": _num(k0.get("kappa")), "kappa_ct_p": _num(k0.get("kappa_p"))}
    if isinstance(gap, Mapping) and "rungs" in gap:
        g = gap["rungs"].get("C_t+5", {})
        row |= {"lambda_t5": _num(g.get("lambda")), "lambda_t5_p": _num(g.get("lambda_p"))}
        row |= {
            "psi_t5": _num(g.get("psi")),
            "half_life": _num(gap.get("half_life_sessions")),
            "nobs_gap": g.get("nobs"),
        }
    if isinstance(te, Mapping) and "rungs" in te:
        t = te["rungs"].get("C_t+20", {}).get("naive", {})
        row |= {"tracking_naive_t20": _num(t.get("ratio")), "tracking_naive_t20_p": _num(t.get("p"))}
    return row


def t9_conv_cuts(r: Mapping[str, Any]) -> Table:
    rows = []
    for key, res in r["convergence"]["models"].items():
        for tier, x in res["by_tier"].items():
            rows.append(_cut_row(key, "tier", tier, x.get("ladder"), x.get("gap_d2"), x.get("tracking")))
        for name, x in res["by_quantified"].items():
            for lev in sorted(set(x["ladder"]) | set(x["gap_d2"])):
                rows.append(_cut_row(key, name, lev, x["ladder"].get(lev), x["gap_d2"].get(lev), None))
        for point in ("gap_d2", "gap_d1"):
            for b, g in res["by_abs_g"][point].items():
                rows.append(_cut_row(key, f"abs_g_{point}", b, None, g, None))
    return Table(
        "t9_convergence_cuts",
        "A1 by tier, quantified vs story (vendor; d1-ultra's own label) and |G| bin",
        _frame(rows),
        ("|G| bins apply to gap closure only (the D0 ladder has no G); PREREG §15 NA-12 row.",),
    )


# --- explanation (A3) and the question battery (A2.5) ------------------------------------------------------


def t10_explanation(r: Mapping[str, Any]) -> Table:
    ex = r["explanation"]
    roll = ex["roll_r2"]
    rows: list[dict[str, Any]] = [
        {
            "key": "roll_r2",
            "model": "all",
            "cut": "all",
            "step": "market+sector",
            "r2": _num(roll["r2"]),
            "n": roll["n"],
        }
    ]
    for key, res in ex["models"].items():
        cuts: dict[str, Any] = {"all": res["ladder"], "event_days": res["event_days"]}
        cuts["non_event_days"] = res["non_event_days"]
        cuts |= {f"tier:{t}": v for t, v in res["by_tier"].items()}
        cuts |= {f"event_type:{t}": v for t, v in res.get("by_event_type", {}).items()}
        for cut, lad in cuts.items():
            if not isinstance(lad, Mapping) or "steps" not in lad:
                rows.append({"key": f"{key}:{cut}", "model": key, "cut": cut, "available": False})
                continue
            for step, s in lad["steps"].items():
                inc = s.get("increment", {})
                rows.append(
                    {
                        "key": f"{key}:{cut}:{step}",
                        "model": key,
                        "cut": cut,
                        "step": step,
                        "r2": _num(s["value"]),
                        "r2_ci_low": _num(s["ci_low"]),
                        "r2_ci_high": _num(s["ci_high"]),
                        "r2_p": _num(s["p"]),
                        "increment": _num(inc.get("value")),
                        "increment_p": _num(inc.get("p")),
                        "n": s.get("n_obs"),
                        "lambda": _num(s.get("lambda")),
                    }
                )
            if "knowable_before_open" in lad:
                rows.append(
                    {
                        "key": f"{key}:{cut}:knowable",
                        "model": key,
                        "cut": cut,
                        "step": "ex-ante ÷ ex-post (increment: ex-post − ex-ante)",
                        "r2": _num(lad["knowable_before_open"]),
                        "increment": _num(lad["arrived_during_day"]),
                    }
                )
    return Table(
        "t10_explanation_ladder",
        "A3.2 explanation ladder: out-of-sample share of stock-specific daily variance (z_cc) by step",
        _frame(rows),
        (
            "Ridge fit on val-B, λ on val-A, evaluated on test (§11.5); news features are 0 on days without "
            "an event.",
        ),
    )


def t11_explanation_more(r: Mapping[str, Any]) -> Table:
    ex = r["explanation"]
    es = ex["explained_share"]
    rows: list[dict[str, Any]] = [
        {
            "key": "share:all",
            "item": "share of Σz_cc² on days judged explained (X >= 0.5)",
            "value": _num(es["share_explained"]),
            "events_share": _num(es["share_events_explained"]),
            "n": es["n"],
        }
    ]
    rows += [
        {"key": f"share:tier:{t}", "item": f"explained share, {t}", "value": _num(v)}
        for t, v in es["by_tier"].items()
    ]
    for reason, v in es.get("by_reason", {}).items():
        rows.append(
            {
                "key": f"share:reason:{reason}",
                "item": f"explained share, reason {reason}",
                "value": _num(v["share_explained"]),
                "variance_share": _num(v["share_of_variance"]),
                "n": v["n"],
            }
        )
    for pt in ("d2", "d1"):
        th = ex[f"theta_{pt}"]
        row: dict[str, Any] = {"key": f"theta:{pt}", "item": f"θ at {pt.upper()} (explanation → persistence)"}
        if th.get("available") is False:
            rows.append(row | {"available": False})
        else:
            rows.append(
                row
                | {
                    "value": _num(th["theta"]),
                    "se": _num(th["theta_se"]),
                    "p": _num(th["theta_p"]),
                    "n": th["nobs"],
                }
            )
    for reason, v in ex["persistence_by_reason"].items():
        e = _est(v)
        rows.append(
            {
                "key": f"persistence:{reason}",
                "item": f"mean sign(G)·y2, reason {reason}",
                "value": e.get("estimate"),
                "ci_low": e.get("ci_low"),
                "ci_high": e.get("ci_high"),
                "p": e.get("p"),
                "n": e.get("n_obs"),
            }
        )
    mk = ex["market_replication"]
    rows.append(
        {
            "key": "market:r2",
            "item": "A3.5 market replication, OOS R² of SPY's r_cc (exploratory)",
            "value": _num(mk.get("r2_value")),
            "ci_low": _num(mk.get("r2_ci_low")),
            "ci_high": _num(mk.get("r2_ci_high")),
            "p": _num(mk.get("r2_p")),
            "n": mk.get("r2_n_obs"),
            "available": mk.get("available"),
        }
    )
    return Table(
        "t11_explanation_share_theta",
        "A3.3–A3.5 (d1-ultra, model-specific): explained share, θ, persistence by reason, the market",
        _frame(rows),
    )


def t12_battery(r: Mapping[str, Any]) -> Table:
    b = r["battery"]
    rows: list[dict[str, Any]] = []
    for key, mech in b["mechanism"].items():
        for analysis, by_col in mech.items():
            for col, levels in by_col.items():
                for lev, res in levels.items():
                    row: dict[str, Any] = {"key": f"{key}:{analysis}:{col}:{lev}", "model": key}
                    row |= {"analysis": analysis, "label": col, "level": lev}
                    if "error" in res:
                        rows.append(row | {"available": False})
                    elif analysis == "h2_d2":
                        row |= {
                            "b": _num(res["b"]),
                            "b_p": _num(res["b_p"]),
                            "c": _num(res["c"]),
                            "c_p": _num(res["c_p"]),
                        }
                        rows.append(row | {"nobs": res["nobs"]})
                    else:
                        k = res["rungs"].get("C_t+20", {})
                        row |= {"kappa_t20": _num(k.get("kappa")), "kappa_t20_p": _num(k.get("kappa_p"))}
                        rows.append(row | {"nobs": k.get("nobs")})
    hv = b["horizon_validity"]
    rows.append(
        {
            "key": "horizon_validity",
            "model": API,
            "analysis": "horizon validity: Spearman(H, share of the t+20 move by C_t)",
            "rho": _num(hv["rho"]),
            "ci_low": _num(hv["ci_low"]),
            "ci_high": _num(hv["ci_high"]),
            "p": _num(hv["p"]),
            "nobs": hv["n"],
        }
    )
    w = r["primary"]["models"][API]["H4"].get("a2_width", {})
    rows.append(
        {
            "key": "h4_width_a2",
            "model": API,
            "analysis": "H4 width: ΔR² of U_unc and P(no_material_effect)",
            "delta_r2": _num(w.get("value")),
            "ci_low": _num(w.get("ci_low")),
            "ci_high": _num(w.get("ci_high")),
            "p": _num(w.get("p")),
        }
    )
    for x in b["reading_validity_na06"]:
        rows.append(
            {
                "key": f"reading:{str(x['model']).replace('/', '_')}:{x['comparison']}",
                "model": x["model"],
                "analysis": f"reading validity (NA-06, val-A): {x['comparison']}",
                "agreement": _num(x["agreement"]),
                "nobs": x["n"],
            }
        )
    return Table(
        "t12_question_battery",
        "A2.5: mechanism cuts (own labels and vendor tags), horizon validity, H4 width, reading validity",
        _frame(rows),
    )


# --- Shapley, model comparison, calibration, robustness, exploratory ---------------------------------------


def t13_shapley(r: Mapping[str, Any]) -> Table:
    rows = []
    for key, res in r["shapley"]["models"].items():
        for part, row in res["shapley"].items():
            for metric in ("r2", "ic"):
                x = row[metric]
                for g in ("R", "N", "J"):
                    rows.append(
                        {
                            "key": f"{key}:{part}:{metric}:{g}",
                            "model": key,
                            "tier": part,
                            "metric": metric,
                            "group": g,
                            "shapley": _num(x["shapley"].get(g)),
                            "share": _num(x["shares"].get(g)),
                            "n": row["n"],
                        }
                    )
                rows.append(
                    {
                        "key": f"{key}:{part}:{metric}:total",
                        "model": key,
                        "tier": part,
                        "metric": metric,
                        "group": "R+N+J",
                        "shapley": _num(x["values"].get("R+N+J")),
                        "n": row["n"],
                    }
                )
    return Table(
        "t13_shapley",
        "§11.5 Shapley decomposition of the test OOS R² and mean daily IC over {R, N, J}, pooled and by tier",
        _frame(rows),
    )


def _ic_cols(r: Mapping[str, Any], label: str) -> dict[str, Any]:
    e = _est(r or {})
    return {f"ic_{label}": e.get("estimate"), f"ic_{label}_t": e.get("nw_t"), f"ic_{label}_n": e.get("n_obs")}


def t14_comparison(r: Mapping[str, Any]) -> Table:
    c = r["comparison"]
    rows = []
    for m in c["models"]:
        row = {"key": m["model"], "model": m["model"], "name": m["name"], "role": m["role"]}
        for s, lab in (("ic_val_b", "val_b"), ("ic_test", "test"), ("ic_common", "common")):
            row |= _ic_cols(m.get(s) or {}, lab)
        row |= {k: m.get(k) for k in ("cost_per_1000", "latency_p50_ms", "latency_p95_ms", "coverage")}
        rows.append(row | {"footnote": m["footnote"]})
    for b in c["baselines"]:
        row = {"key": f"baseline:{b['baseline']}", "model": b["baseline"], "role": "baseline (PREREG §10)"}
        for s, lab in (("ic_val_b", "val_b"), ("ic_test", "test")):
            row |= _ic_cols(b.get(s) or {}, lab)
        rows.append(row)
    llm = c["llm_subsample"]
    for who in ("laya_fin", "llm"):
        row = {"key": f"llm_subsample:{who}", "model": who, "role": "the LLM baseline's test subsample"}
        rows.append(row | _ic_cols(llm.get(who) or {}, "test"))
    po = c["price_only_d2"]
    row = {"key": "baseline:price_only_d2", "model": "price_only (D2, y2)", "role": "baseline (PREREG §10.4)"}
    rows.append(row | _ic_cols(po.get("ic_y2") or {}, "test"))
    return Table(
        "t14_model_comparison",
        "Model comparison: daily IC of N̂_W0 with z_cc (val-B, test, common test events), cost, latency",
        _frame(rows),
        (
            "The API models are screen-failing and model-specific (§15 NA-06 row). span-02: the S5 canary "
            "fired a STOP and the operator chose to proceed (PREREG §15, post-freeze NA-11 row).",
            "Costs per 1,000 decisions include answers paid by earlier chunks; the price-only D2 row is IC "
            "with y2.",
        ),
    )


def t15_calibration(r: Mapping[str, Any]) -> Table:
    rows: list[dict[str, Any]] = []
    for key, res in r["calibration"]["models"].items():
        for tgt in ("e5", "z_cc"):
            x = res[tgt]
            row = {"key": f"{key}:{tgt}", "model": key, "target": tgt}
            row |= {k: _num(x[k]) for k in ("ece", "log_loss", "brier", "log_loss_skill", "brier_skill")}
            rows.append(row | {"n": x["n"]})
        auc = res["auc_abs_z_ge_1"]
        rows.append({"key": f"{key}:auc", "model": key, "target": "|z_cc| >= 1", "auc": _num(auc["auc"])})
        t = res.get("temperature_h7")
        if isinstance(t, Mapping) and "before" in t:
            rows.append(
                {
                    "key": f"{key}:temperature",
                    "model": key,
                    "target": "e5",
                    "temperature": _num(t["temperature"]),
                    "ece_before": _num(t["before"]["ece"]),
                    "ece_after": _num(t["after"]["ece"]),
                    "source": t["source"],
                }
            )
    return Table(
        "t15_calibration",
        "§11.2 calibration of Q1's three classes (ECE; log-loss and Brier skill vs val-A climatology); H7",
        _frame(rows),
    )


def _rob_row(key: str, model: str, point: str, name: str, adj: str, v: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"key": key, "model": model, "point": point, "variant": name, "adjustment": adj}
    for t in ("H1", "H1b"):
        if t in v:
            e = _est(v[t])
            row |= {t: e.get("estimate"), f"{t}_t": e.get("nw_t"), f"{t}_p": e.get("p"), "n": e.get("n_obs")}
    ic = v.get("ic", {})
    for tgt in ("z_cc", "z_on", "z_id"):
        if f"ic_{tgt}" in ic:
            row |= {f"ic_{tgt}": _num(ic[f"ic_{tgt}"]), f"ic_{tgt}_t": _num(ic[f"ic_{tgt}_t"])}
    h = v.get("H2")
    if isinstance(h, Mapping) and "b" in h:
        row |= {"b": _num(h["b"]), "b_p": _num(h["b_p"]), "c": _num(h.get("c")), "c_p": _num(h.get("c_p"))}
        row |= {"H2_p": _num(h["p"]), "nobs": h["nobs"]}
    return row


def t16_robustness(r: Mapping[str, Any]) -> Table:
    rob = r["robustness"]
    rows: list[dict[str, Any]] = []
    for key, res in rob["models"].items():
        for adj in ("raw", "placebo"):
            for pt in ("D0", "D2"):
                for name, v in res[f"variants_{pt.lower()}_{adj}"].items():
                    rows.append(_rob_row(f"{key}:{pt}:{name}:{adj}", key, pt, name, adj, v))
        rows.append(
            _rob_row(
                f"{key}:all:placebo_adjusted",
                key,
                "D0+D2",
                "placebo-adjusted",
                "placebo",
                res["placebo_adjusted"],
            )
        )
        rows.append(_rob_row(f"{key}:all:sigma60", key, "D0+D2", "σ = 60-session SD", "raw", res["sigma60"]))
        for nm in ("h1_2024h1_raw", "h1_2024h1_placebo", "h2_2024h1_raw", "h2_2024h1_placebo"):
            if nm in res:
                v = res[nm] if nm.startswith("h1") else {"H2": res[nm]}
                pt = "D0" if nm.startswith("h1") else "D2"
                rows.append(_rob_row(f"{key}:2024H1:{nm}", key, pt, "2024-H1", nm.rsplit("_", 1)[1], v))
    ab = rob["ablations_d1_ultra"]
    for side in ("masked", "unmasked"):
        v = ab["a0_unmasked"][side]
        rows.append(
            _rob_row(f"{API}:D0:a0_unmasked:{side}", API, "D0", f"unmasked twins: {side} reading", "raw", v)
        )
    for name in ("b2_no_news", "b2_shuffled"):
        for col in ("j", "c", "n_hat"):
            for side in ("real", "ablated"):
                e = _est(ab[name][f"{side}_{col}"])
                row = {"key": f"{API}:D2:{name}:{col}:{side}", "model": API, "point": "D2"}
                row |= {"variant": f"{name}: IC of b2_{col} with y2 ({side})", "adjustment": "raw"}
                rows.append(row | {"ic_y2": e.get("estimate"), "ic_y2_t": e.get("nw_t"), "n": e.get("n_obs")})
    for name, why in rob["not_run"].items():
        rows.append(
            {"key": f"not_run:{name}", "model": "all", "variant": name, "adjustment": "not run", "note": why}
        )
    return Table(
        "t16_robustness",
        "§11.6 and operator rows (a)–(b): every robustness variant, raw and placebo-adjusted",
        _frame(rows),
        ("At D0 each variant re-runs H1, H1b and the ICs; at D2, H2 (§15 NA-11 row (xii)).",),
    )


def t17_sector(r: Mapping[str, Any]) -> Table:
    rows = []
    for key, res in r["exploratory"]["sector"].items():
        for kind in ("by_sector", "leave_one_out"):
            for sec, x in res[kind].items():
                row: dict[str, Any] = {
                    "key": f"{key}:{kind}:{sec}",
                    "model": key,
                    "kind": kind,
                    "sector": sec,
                }
                for tgt in ("z_cc", "z_on", "z_id"):
                    for suffix in ("", "_t", "_ci_low", "_ci_high", "_n"):
                        row[f"ic_{tgt}{suffix}"] = _num(x.get(f"ic_{tgt}{suffix}"))
                rows.append(row)
    return Table(
        "t17_sector_exploratory",
        "Exploratory (outside every family, no claim): IC of N̂_W0 by GICS sector and leave-one-sector-out",
        _frame(rows),
    )


def t18_probes(r: Mapping[str, Any]) -> Table:
    rows = [{"key": str(x.get("model")).replace("/", "_"), **x} for x in r["comparison"]["probes_val_a"]]
    return Table(
        "t18_probes_val_a",
        "Disclosed val-A probes (NA-11; not hypotheses), next to the model comparison",
        _frame(rows),
    )


def t19_monthly(r: Mapping[str, Any]) -> Table:
    rows = [{"key": f"{x['model']}:{x['month']}", **x} for x in r["monthly_ic"]["rows"]]
    notes = tuple(f"{k}: {v['date']} ({v['source']})" for k, v in r["monthly_ic"]["release"].items())
    return Table(
        "t19_monthly_ic", "Monthly mean daily IC of N̂_W0 with z_cc (val-A, val-B, test)", _frame(rows), notes
    )


BUILDERS: Final[tuple[Callable[[Mapping[str, Any]], Table], ...]] = (
    t1_primary,
    t1b_by_model,
    t2_h2,
    t3_ic,
    t4_secondary,
    t5_heterogeneity,
    t6_ladder,
    t7_gap,
    t8_tracking,
    t9_conv_cuts,
    t10_explanation,
    t11_explanation_more,
    t12_battery,
    t13_shapley,
    t14_comparison,
    t15_calibration,
    t16_robustness,
    t17_sector,
    t18_probes,
    t19_monthly,
)


# --- formatting, keys and output ---------------------------------------------------------------------------


def fmt(value: Any, column: str) -> str:
    """A cell for LaTeX and captions: p and q to 3 decimals ("<0.001"), counts as integers, other numbers to
    3 decimals (scientific below 0.001)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if math.isinf(value):
            return "∞" if value > 0 else "−∞"
        if P_COLUMNS.search(column):
            return "<0.001" if value < 0.001 else f"{value:.3f}"
        if COUNTS.match(column) and value.is_integer():
            return f"{int(value):,}"
        return f"{value:.3f}" if abs(value) >= 0.001 or value == 0 else f"{value:.2e}"
    return str(value)


_TEX: Final = str.maketrans(
    {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "\\": r"\textbackslash{}",
    }
)


def to_latex(t: Table) -> str:
    """A booktabs tabular; the title and notes as leading comments."""
    cols = list(t.frame.columns)
    head = " & ".join(c.translate(_TEX) for c in cols) + r" \\"
    body = [
        " & ".join(fmt(v, c).translate(_TEX) for c, v in zip(cols, row, strict=True)) + r" \\"
        for row in t.frame.itertuples(index=False)
    ]
    lines = [f"% {t.name}: {t.title}", *[f"% {n}" for n in t.notes]]
    lines += [f"\\begin{{tabular}}{{{'l' * len(cols)}}}", r"\toprule", head, r"\midrule", *body]
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def _plain(x: Any) -> Any:
    if isinstance(x, float) and math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return x.item() if hasattr(x, "item") else x


def keys_of(t: Table) -> dict[str, Any]:
    """ "<table>/<key>/<column>" → value for every non-empty cell."""
    out: dict[str, Any] = {}
    for row in t.frame.to_dict("records"):
        for c, v in row.items():
            if c == "key" or v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
                continue
            out[f"{t.name}/{row['key']}/{c}"] = _plain(v)
    return out


def cite(text: str, keys: Mapping[str, Any]) -> str:
    """Replace each {{table/key/column}} with its formatted value; an unknown key raises KeyError."""

    def one(m: re.Match[str]) -> str:
        k = m.group(1).strip()
        if k not in keys:
            raise KeyError(f"unknown table key {k!r}")
        v = keys[k]
        if v in ("inf", "-inf"):
            v = float(v)
        return fmt(v, k.rsplit("/", 1)[1])

    return CITE.sub(one, text)


def required() -> list[str]:
    """The keys that every pre-registered test must have (PRD NA-12 AC4), from the frozen configuration."""
    cfg = spec.load_config()
    cv = cfg.convergence
    req = [f"t1_primary/{t}/verdict" for t in TESTS]
    req += [f"t1b_primary_by_model/{m.key}:{t}/test" for m in MODELS for t in TESTS]
    req += [f"t2_h2_over_under/{k}:{p}/variant" for k in FOCUS for p in ("D2", "D1", "D0")]
    req += [f"t3_ic/{k}:{t}/ic" for k in FOCUS for t in ("z_cc", "z_on", "z_id")]
    req += [f"t4_secondary/{k}:{t}/test" for k in FOCUS for t in SECONDARY_TESTS]
    req += [f"t5_heterogeneity/{k}:{c}/cut" for k in FOCUS for c in cfg.cuts.list]
    for k in FOCUS:
        for v in ("ladder", "ladder_clean", "ladder_h10"):
            req += [f"t6_convergence_ladder/{k}:{v}:{rung}/rung" for rung in cv.ladder]
        req += [f"t6_convergence_ladder/{k}:ladder_plateau:plateau/rung"]
        for pt in ("D2", "D1"):
            req += [
                f"t7_gap_closure/{k}:{pt}:{v}:{rung}/rung"
                for v in ("all", "clean")
                for rung in cv.gap[pt].rungs
            ]
            req += [f"t7_gap_closure/{k}:{pt}:all:half_life/rung"]
        req += [f"t8_tracking_error/{k}:{rung}/rung" for rung in cv.ladder]
        req += [f"t9_convergence_cuts/{k}:tier:{t}/cut" for t in ("top100", "mid", "rest")]
        req += [f"t10_explanation_ladder/{k}:all:ex_post/step"]
        req += [f"t16_robustness/{k}:all:sigma60/variant", f"t16_robustness/{k}:all:placebo_adjusted/variant"]
    req += [
        "t10_explanation_ladder/roll_r2/step",
        "t11_explanation_share_theta/share:all/item",
        "t11_explanation_share_theta/theta:d2/item",
        "t11_explanation_share_theta/theta:d1/item",
        "t11_explanation_share_theta/market:r2/item",
        "t12_question_battery/horizon_validity/analysis",
        "t12_question_battery/h4_width_a2/analysis",
    ]
    req += [
        f"t16_robustness/not_run:{n}/note"
        for n in ("summary_text_variant", "vendor_tags_in_text", "w0_cutoff_09:30")
    ]
    req += ["t16_robustness/not_run:gated_s_d1/note"]
    return req


def missing(keys: Mapping[str, Any]) -> list[str]:
    return [k for k in required() if k not in keys]


def load_results(root: Path) -> dict[str, Any]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.json"))}


def write(
    layout: Layout | None = None, results: Path | None = None, out: Path | None = None
) -> dict[str, Any]:
    """Every table from ``results`` (default ``artifacts/NA-12/results``) into ``out`` (default
    ``artifacts/NA-12/tables``)."""
    lay = resolve_layout(layout)
    res = load_results(results or lay.root / ARTIFACTS / RESULTS)
    d = out or lay.root / ARTIFACTS / TABLES
    d.mkdir(parents=True, exist_ok=True)
    keys: dict[str, Any] = {}
    index = []
    for t in (b(res) for b in BUILDERS):
        t.frame.to_csv(d / f"{t.name}.csv", index=False, float_format="%.10g")
        (d / f"{t.name}.tex").write_text(to_latex(t), encoding="utf-8")
        keys |= keys_of(t)
        index.append(
            {
                "name": t.name,
                "title": t.title,
                "columns": list(t.frame.columns),
                "rows": len(t.frame),
                "notes": list(t.notes),
                "files": [f"{t.name}.csv", f"{t.name}.tex"],
            }
        )
    (d / "keys.json").write_text(json.dumps(keys, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (d / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return {"tables": len(index), "keys": len(keys), "missing": missing(keys)}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv or [])
    results = Path(args[args.index("--results") + 1]) if "--results" in args else None
    out_dir = Path(args[args.index("--out") + 1]) if "--out" in args else None
    out = write(results=results, out=out_dir)
    print(json.dumps(out, indent=1))
    return 1 if out["missing"] else 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
