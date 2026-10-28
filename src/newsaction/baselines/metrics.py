"""Val-A metrics of the baselines (PRD NA-09 S8): ``artifacts/NA-09/baseline_val_metrics.csv``.

**Val-A only.** ``evaluation_rows`` keeps the tuning split's rows outside the embargo and refuses any other
split: NA-09 stores val-B (and test) predictions and computes no metric on them (PRD S8; NA-11 evaluates
val-B). Targets are joined from ``panel_public``, which has no test session.

Per baseline and call, overall and by tier (PREREG §3.3):
- **call A** (D0 events): the mean daily Spearman IC of N_hat with z_cc,t and with e5 (PREREG §11.1;
  ``tournament.metrics``: ≥ 5 events a day, Newey–West t with 5 lags), the out-of-sample R² of e5 against a
  zero forecast; for mag_hat the R² of |z_cc| against the train mean of |z_cc| and against zero, and its daily
  IC with |z_cc|. A diagnostic beside them: N_hat's IC with the gap z_on,t and with the open→close z_id,t (a
  signal known before the open should show in the gap; a strong z_id IC would point at information from after
  the decision, PREREG H1 and the NA-02 leakage audit);
- **call B** (D2 events): Laya's N_hat with z_cc,t and e5, J and C with y2 (``extra``); price-only D2's
  y_hat with y2 (IC, R² against zero).

The LLM's 2,000 events are val-B: it has no val-A metric here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.baselines import BaselineError, BaselinesConfig, log_trial
from newsaction.baselines.fitting import r2
from newsaction.config import SplitName
from newsaction.paths import Layout, resolve_layout
from newsaction.tournament.metrics import daily_ic, ic_stats

PANEL: Final = "panel/panel_public.parquet"
METRIC_COLUMNS: Final = (
    "model",
    "call",
    "signal",
    "target",
    "metric",
    "tier",
    "value",
    "t",
    "se",
    "n_days",
    "n_events",
)


def evaluation_rows(pred: pd.DataFrame, cfg: BaselinesConfig, split: SplitName | None = None) -> pd.DataFrame:
    """The rows NA-09 may evaluate: the tuning split (val-A), outside the embargo. Any other split raises."""
    split = cfg.tune_split if split is None else split
    if split != cfg.tune_split:
        raise BaselineError(f"NA-09 computes no metric on {split}: only on {cfg.tune_split} (PRD NA-09 S8)")
    return pred.loc[pred["split"] == split]


def targets(layout: Layout | None = None) -> pd.DataFrame:
    """(session, symbol_id) → e5, z_cc, z_on, z_id, |z_cc|, y2 (panel_public; the event's symbol, as in
    ``data``)."""
    cols = ["session", "symbol_id", "e5", "z_cc", "z_on", "z_id", "y2", "split"]
    p = io.read_parquet(PANEL, columns=cols, layout=layout)
    p["abs_z_cc"] = p["z_cc"].abs()
    return p


def _ic_rows(
    d: pd.DataFrame,
    signal: str,
    target: str,
    cfg: BaselinesConfig,
    base: dict[str, Any],
    tiers: Sequence[str],
) -> list[dict[str, Any]]:
    out = []
    for tier in ("all", *tiers):
        g = d if tier == "all" else d.loc[d["tier"] == tier]
        g = g[["session", signal, target]].dropna()
        st = ic_stats(daily_ic(g, signal, target, cfg.metric.min_names_per_day), cfg.metric.nw_lags)
        out.append(
            {**base, "signal": signal, "target": target, "metric": "ic", "tier": tier, "value": st.mean,
             "t": st.t, "se": st.se, "n_days": st.n_days, "n_events": len(g)}
        )  # fmt: skip
    return out


def _r2_rows(
    d: pd.DataFrame,
    signal: str,
    target: str,
    reference: float,
    name: str,
    base: dict[str, Any],
    tiers: Sequence[str],
) -> list[dict[str, Any]]:
    out = []
    for tier in ("all", *tiers):
        g = d if tier == "all" else d.loc[d["tier"] == tier]
        g = g[[signal, target]].dropna()
        out.append(
            {**base, "signal": signal, "target": target, "metric": name, "tier": tier,
             "value": r2(g[signal], g[target], reference), "t": np.nan, "se": np.nan, "n_days": np.nan,
             "n_events": len(g)}
        )  # fmt: skip
    return out


def model_metrics(
    pred: pd.DataFrame, tg: pd.DataFrame, cfg: BaselinesConfig, train_abs_z_cc: float
) -> list[dict[str, Any]]:
    """Every metric of one model's predictions (all calls) on val-A outside the embargo."""
    rows = evaluation_rows(pred, cfg)
    d = rows.merge(tg.drop(columns=["split"]), on=["session", "symbol_id"], how="left", validate="m:1")
    out: list[dict[str, Any]] = []
    tiers = cfg.metric.tiers
    for call, g in d.groupby("call", sort=True):
        g = g.loc[~g["embargo"].astype(bool)] if cfg.metric.exclude_embargo else g
        base = {"model": str(g["model"].iloc[0]), "call": str(call)}
        if g["N_hat"].notna().any():
            out += _ic_rows(g, "N_hat", "z_cc", cfg, base, tiers)
            out += _ic_rows(g, "N_hat", "e5", cfg, base, tiers)
            out += _r2_rows(g, "N_hat", "e5", 0.0, "r2_vs_zero", base, tiers)
            if call == "A":  # where a D0 signal's information lands: the gap or after the open (PREREG H1)
                out += _ic_rows(g, "N_hat", "z_on", cfg, base, tiers)
                out += _ic_rows(g, "N_hat", "z_id", cfg, base, tiers)
        if g["mag_hat"].notna().any():
            out += _r2_rows(g, "mag_hat", "abs_z_cc", train_abs_z_cc, "r2_vs_train_mean", base, tiers)
            out += _r2_rows(g, "mag_hat", "abs_z_cc", 0.0, "r2_vs_zero", base, tiers)
            out += _ic_rows(g, "mag_hat", "abs_z_cc", cfg, base, tiers)
        if g["y_hat"].notna().any():
            out += _ic_rows(g, "y_hat", "y2", cfg, base, tiers)
            out += _r2_rows(g, "y_hat", "y2", 0.0, "r2_vs_zero", base, tiers)
        extra = g["extra"].map(json.loads)
        for key, target in (("j", "y2"), ("c", "y2")):
            vals = extra.map(lambda e, k=key: e.get(k))
            if vals.notna().any():
                g = g.assign(**{key: vals.astype(float)})
                out += _ic_rows(g, key, target, cfg, base, tiers)
    return out


def val_metrics(
    preds: Sequence[pd.DataFrame], events: pd.DataFrame, cfg: BaselinesConfig, layout: Layout | None = None
) -> pd.DataFrame:
    """The metrics table of every prediction frame. ``events`` maps event_id → symbol_id, tier, embargo."""
    tg = targets(layout)
    train = tg.loc[tg["split"] == cfg.fit_split, "abs_z_cc"].dropna()
    rows: list[dict[str, Any]] = []
    for pred in preds:
        p = pred.merge(events, on="event_id", how="left", validate="m:1")
        if bool(p["tier"].isna().any()):
            raise BaselineError("a prediction without its event's tier")
        rows += model_metrics(p, tg, cfg, float(train.mean()))
    return pd.DataFrame(rows, columns=list(METRIC_COLUMNS))


def log_metrics(table: pd.DataFrame, layout: Layout | None = None) -> int:
    """One trial per (model, call, signal, target, metric) over all tiers (CLAUDE.md B10)."""
    n = 0
    for r in table.loc[table["tier"] == "all"].to_dict("records"):
        params = {"model": r["model"], "call": r["call"], "signal": r["signal"], "target": r["target"]}
        name = f"{r['model']}:{r['call']}:{r['signal']}"
        n += log_trial(
            "baseline", name, params, "val_a", f"{r['metric']}_{r['target']}", r["value"], layout=layout
        )
    return n


def write(table: pd.DataFrame, layout: Layout | None = None) -> str:
    from newsaction.baselines import ARTIFACTS, PRODUCER

    lay = resolve_layout(layout)
    rel = f"{ARTIFACTS}/baseline_val_metrics.csv"
    path = lay.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    io.atomic_write_bytes(path, table.to_csv(index=False, float_format="%.6g").encode("utf-8"))
    io.register_artifact(
        rel, producer=PRODUCER, description="NA-09 S8 val-A metrics of the baselines", layout=lay
    )
    return rel
