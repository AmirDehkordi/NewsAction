"""Exploratory: where the D0 signal lives (operator request after unblinding; no hypothesis, outside every
family, no claim; no frozen file, function or family changes).

    uv run python -m newsaction.analysis.exploratory

Signals: N̂_W0 of Laya-Fin, d1-ultra, span-02, drex-v2.0 and Laya zero-shot on their own D0 events, and NA-09's
vendor-sentiment and tags-GBM ``N_hat`` on the Call A D0 events (``run_all._baseline_frame``; retrospective
labels, CLAUDE.md A6). Splits: val-A, val-B and test outside the embargo (``spec.eval_sample``). Every IC is
the frozen daily IC (``spec.daily``: >= 5 names a session, IC 0 on a constant session) and every t the frozen
Newey–West t of a daily series (``metrics.nw_t``, ``cfg.metrics.nw_lags``); ``spec.ic_targets`` adds the
frozen block-bootstrap CI.

1. ``earnings``: IC with z_cc, z_on and z_id on earnings-day events (the frame's ``earnings`` flag) and on the
   rest, and the daily difference on the sessions that have both.
2. ``tier``: IC with z_cc, z_on and z_id by size tier.
3. ``monthly``: the mean daily IC with z_cc per calendar month; a one-way F test of month effects on the
   daily ICs; the implied standard error of one month's mean IC, √(MS_within / mean days per month), and its
   Newey–West counterpart √(long-run variance / mean days per month).
4. ``company`` (test only): Spearman of the signal with z_cc within each company with >= 15 events; the SD of
   those correlations against a null that shuffles the signal within each company (200 draws, seed 2026).
5. ``market_state``: the daily IC with z_cc by terciles of the split's sessions of |SPY's close-to-close
   return| and of the cross-sectional SD of z_cc over covered member-days (``frames.member_days``).

Writes ``artifacts/NA-12/results/exploratory_d0_signal.json``.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats  # type: ignore[import-untyped, unused-ignore]

from newsaction.analysis import frames, run_all, spec
from newsaction.analysis import metrics as mx
from newsaction.paths import Layout, resolve_layout

RESULT: Final = "exploratory_d0_signal"
SIGNAL: Final = "a0_n_hat"
MODELS: Final = ("laya_fin", "d1_ultra", "span_02", "drex_v2", "laya_zs")
BASELINES: Final = ("sentiment", "tags_gbm")
SPLITS: Final = ("val_a", "val_b", "test")
TARGETS: Final = ("z_cc", "z_on", "z_id")
TIERS: Final = ("top100", "mid", "rest")
COMPANY_SPLIT: Final = "test"
COMPANY_MIN_EVENTS: Final = 15
NULL_DRAWS: Final = 200
NULL_SEED: Final = 2026
TERCILES: Final = ("low", "mid", "high")

Signals = dict[str, tuple[pd.DataFrame, str]]


class ExploratoryError(RuntimeError):
    """The inputs are not ready (the section follows the unblinding)."""


def signals(ctx: run_all.Ctx) -> Signals:
    """Each signal's D0 frame and column."""
    out: Signals = {k: (ctx.d0[k], SIGNAL) for k in MODELS}
    base, _ = run_all._baseline_frame(ctx)
    out |= {k: (base, f"bl_{k}") for k in BASELINES}
    return out


def daily_ic(frame: pd.DataFrame, split: str, col: str, target: str, cfg: spec.AnalysisConfig) -> pd.Series:
    s = spec.eval_sample(frame, split, cfg).dropna(subset=[col, target])
    return spec.daily(s, col, target, cfg)


def nw(daily: pd.Series, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    """Mean, Newey–West t and SE (mean / t) of a daily series."""
    mean, t, n = mx.nw_t(daily, cfg.metrics.nw_lags)
    se = abs(mean / t) if math.isfinite(t) and t != 0 else math.nan
    return {"mean": mean, "nw_t": t, "se": se, "n_days": n}


# --- 1–2: IC by group --------------------------------------------------------------------------------------


def by_group(
    frame: pd.DataFrame, split: str, col: str, groups: Mapping[str, pd.Series], cfg: spec.AnalysisConfig
) -> dict[str, Any]:
    """``spec.ic_targets`` of the signal with z_cc, z_on and z_id on each group's rows."""
    return {g: spec.ic_targets(frame.loc[mask], split, cfg, col, TARGETS) for g, mask in groups.items()}


def earnings(frame: pd.DataFrame, split: str, col: str, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    """IC on earnings-day events and on the rest, and the daily difference on the sessions with both."""
    groups = {"earnings": frame["earnings"] == 1, "rest": frame["earnings"] == 0}
    out = by_group(frame, split, col, groups, cfg)
    out["difference"] = {}
    for t in TARGETS:
        a, b = (daily_ic(frame.loc[m], split, col, t, cfg) for m in groups.values())
        out["difference"][t] = nw((a - b).dropna(), cfg)
    return out


def tier(frame: pd.DataFrame, split: str, col: str, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    return by_group(frame, split, col, {t: frame["tier"] == t for t in TIERS}, cfg)


# --- 3: month effects --------------------------------------------------------------------------------------


def month_effects(daily: pd.Series, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    """One-way ANOVA of the daily ICs on calendar month, the per-month means and the implied standard error of
    one month's mean IC (iid: √(MS_within / n̄); Newey–West: √(long-run variance / n̄), n̄ the mean days per
    month)."""
    months = pd.Index(pd.to_datetime(pd.Index(daily.index)).strftime("%Y-%m"))
    groups = {str(m): g.to_numpy(dtype=float) for m, g in daily.groupby(months)}
    rows = [
        {"month": m, "ic": float(v.mean()), "n_days": len(v),
         "se": float(v.std(ddof=1) / math.sqrt(len(v))) if len(v) > 1 else math.nan}
        for m, v in groups.items()
    ]  # fmt: skip
    k, n = len(groups), len(daily)
    out: dict[str, Any] = {"months": rows, "n_months": k, "n_days": n}
    if k < 2 or n <= k:
        return out | {"f": math.nan, "p": math.nan}
    f, p = stats.f_oneway(*groups.values())
    ms_within = sum(float(((v - v.mean()) ** 2).sum()) for v in groups.values()) / (n - k)
    n_bar = n / k
    se_all = nw(daily, cfg)["se"]
    return out | {
        "f": float(f),
        "p": float(p),
        "df": [k - 1, n - k],
        "ms_within": ms_within,
        "mean_days_per_month": n_bar,
        "se_month_iid": math.sqrt(ms_within / n_bar),
        "se_month_nw": se_all * math.sqrt(n / n_bar),
        "sd_month_means": float(np.std([r["ic"] for r in rows], ddof=1)),
    }


# --- 4: per-company correlations against a within-company shuffle ------------------------------------------


def _row_corr(
    x: npt.NDArray[np.floating[Any]], y: npt.NDArray[np.floating[Any]], constant: float
) -> npt.NDArray[np.floating[Any]]:
    """Pearson correlation of each row of ``x`` with ``y`` (``constant`` where either side is constant)."""
    xc = x - x.mean(axis=1, keepdims=True)
    yc = y - y.mean()
    den = np.sqrt((xc**2).sum(axis=1) * float(yc @ yc))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (xc @ yc) / den
    return np.where(den > 0, r, constant)


def company_spread(
    frame: pd.DataFrame,
    col: str,
    cfg: spec.AnalysisConfig,
    *,
    split: str = COMPANY_SPLIT,
    min_events: int = COMPANY_MIN_EVENTS,
    draws: int = NULL_DRAWS,
    seed: int = NULL_SEED,
) -> dict[str, Any]:
    """Spearman of the signal with z_cc within each company with >= ``min_events`` events; the SD across
    companies against ``draws`` within-company shuffles of the signal (one generator, companies in id
    order)."""
    s = spec.eval_sample(frame, split, cfg).dropna(subset=[col, "z_cc"])
    s = s.loc[s.groupby("company_id")["z_cc"].transform("size") >= min_events]
    s = s.sort_values(["company_id", "session", "event_id"])
    rng = np.random.default_rng(seed)
    const = cfg.sample.constant_day_ic
    obs: list[float] = []
    null = np.empty((draws, s["company_id"].nunique()))
    for i, (_, g) in enumerate(s.groupby("company_id", sort=True)):
        x = g[col].rank().to_numpy(dtype=np.float64)
        y = g["z_cc"].rank().to_numpy(dtype=np.float64)
        obs.append(float(_row_corr(x[None, :], y, const)[0]))
        null[:, i] = _row_corr(rng.permuted(np.tile(x, (draws, 1)), axis=1), y, const)
    if len(obs) < 2:
        return {"split": split, "n_companies": len(obs), "n_events": len(s)}
    sd = float(np.std(obs, ddof=1))
    null_sd = null.std(axis=1, ddof=1)
    return {
        "split": split,
        "n_companies": len(obs),
        "n_events": len(s),
        "mean": float(np.mean(obs)),
        "sd": sd,
        "null_sd_mean": float(null_sd.mean()),
        "null_sd_p2_5": float(np.quantile(null_sd, 0.025)),
        "null_sd_p97_5": float(np.quantile(null_sd, 0.975)),
        "p": float((1 + (null_sd >= sd).sum()) / (1 + draws)),
    }


# --- 5: market state ---------------------------------------------------------------------------------------


def day_states(days: pd.DataFrame, daily_panel: pd.DataFrame, split: str) -> pd.DataFrame:
    """Per session of the split outside the embargo: |SPY's close-to-close return|, the cross-sectional SD of
    z_cc over covered member-days, and their terciles over the split's sessions."""
    d = days.loc[(days["split"] == split) & ~days["embargo"].astype(bool)]
    out = d.groupby("session")["z_cc"].std().rename("sd_z_cc").to_frame()
    spy = daily_panel.dropna(subset=["r_spy_cc"]).groupby("session")["r_spy_cc"].first().abs()
    out["abs_spy"] = out.index.map(spy.to_dict())
    for c in ("abs_spy", "sd_z_cc"):
        out[f"{c}_tercile"] = pd.qcut(out[c], 3, labels=list(TERCILES)).astype(str)
    return out


def by_tercile(daily: pd.Series, states: pd.DataFrame, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in ("abs_spy", "sd_z_cc"):
        lab = daily.index.map(states[f"{c}_tercile"].to_dict())
        row = {t: nw(daily[lab == t], cfg) for t in TERCILES}
        hi, lo = row["high"], row["low"]
        diff = hi["mean"] - lo["mean"]
        se = math.sqrt(hi["se"] ** 2 + lo["se"] ** 2)
        row["high_minus_low"] = {"mean": diff, "se": se, "t": diff / se if se > 0 else math.nan}
        out[c] = row
    return out


def cutoffs(states: pd.DataFrame) -> dict[str, Any]:
    return {
        c: {t: [float(g[c].min()), float(g[c].max()), len(g)] for t, g in states.groupby(f"{c}_tercile")}
        for c in ("abs_spy", "sd_z_cc")
    }


# --- run ---------------------------------------------------------------------------------------------------


def compute(ctx: run_all.Ctx, splits: Sequence[str] = SPLITS) -> dict[str, Any]:
    cfg = ctx.cfg
    sig = signals(ctx)
    states = {s: day_states(ctx.days, ctx.daily, s) for s in splits}
    out: dict[str, Any] = {
        "exploratory": True,
        "requested": "operator, after unblinding; no hypothesis, outside every family, no claim",
        "splits": list(splits),
        "signals": {k: col for k, (_, col) in sig.items()},
        "settings": {
            "min_names_per_day": cfg.sample.min_names_per_day,
            "constant_day_ic": cfg.sample.constant_day_ic,
            "nw_lags": cfg.metrics.nw_lags,
            "bootstrap": cfg.bootstrap.model_dump(),
            "embargo": cfg.sample.embargo,
            "company": {
                "split": COMPANY_SPLIT,
                "min_events": COMPANY_MIN_EVENTS,
                "draws": NULL_DRAWS,
                "seed": NULL_SEED,
            },
        },
        "earnings": {},
        "tier": {},
        "monthly": {},
        "company": {},
        "market_state": {"cutoffs": {s: cutoffs(st) for s, st in states.items()}},
    }
    for k, (frame, col) in sig.items():
        have = [s for s in splits if run_all.answers(frame, [col], [s])]
        missing = {s: run_all.na("no reading on this split") for s in splits if s not in have}
        out["earnings"][k] = {s: earnings(frame, s, col, cfg) for s in have} | missing
        out["tier"][k] = {s: tier(frame, s, col, cfg) for s in have} | missing
        daily = {s: daily_ic(frame, s, col, "z_cc", cfg) for s in have}
        out["monthly"][k] = {s: month_effects(d, cfg) for s, d in daily.items()} | missing
        out["company"][k] = company_spread(frame, col, cfg)
        out["market_state"][k] = {s: by_tercile(d, states[s], cfg) for s, d in daily.items()} | missing
    return out


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if not (lay.work / frames.TARGETS_TEST).exists():
        raise ExploratoryError(
            "the exploratory section follows the unblinding (work/analysis/targets_test.parquet)"
        )
    ctx = run_all.build_ctx(lay)
    res = compute(ctx)
    path = run_all.out_dir(ctx) / f"{RESULT}.json"
    path.write_text(json.dumps(run_all.jsonable(res), indent=1) + "\n", encoding="utf-8")
    return {"path": str(path.relative_to(lay.root)), "signals": list(res["signals"])}


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    print(json.dumps(run(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
