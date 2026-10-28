"""NA-11 S2: the final selection on val-B (PREREG §8.5) and the selections frozen with it (PRD NA-11 S2).

**Candidates** (PREREG §15, NA-06 operator row): Laya zero-shot (``local/laya-typed-decisions``), Laya-Fin
(``laya_fin``) and the anchor (``anchor``); the trained models are their frozen seed-13 runs
(``TRAINED_RUNS``, operator preamble item 3). No stage-2 API model passed the §8.3 screens, so §8.5's API
candidates are none; the
three screen-failing comparators are listed for information (NA-07's 1,500-event val-B sample) and never
selected.

**Metric** (§8.5, §11.1): the mean daily Spearman IC of Call A D0 N̂ with z_cc,t (``spec.ic``: >= 5 events a
session, a constant session counts 0, Newey–West t, block-bootstrap CI) on the val-B D0 events outside the
embargo that every candidate answered.

**Rule** (``choose``): the highest IC; when the runner-up is within 0.005, the higher IC of J with y2 (val-B
D2
events outside the embargo; a trained model's J is its H-cont C, NA-08's J analogue), then the lower cost per
1,000 decisions, then the higher IC.

**Also frozen** in ``configs/frozen.yaml``:
- ``selection``: the primary instrument, the candidates, the comparators, the trained runs, the table sha256;
- ``thresholds``: the RG band (the PRD's δ) and |N̂| floor (§7), the §11.2 bands, the explanation and
  half-life thresholds (A1.5, A3.3), the confidence-gate percentile (§12);
- ``calibration``: per model and source, Ñ = isotonic N̂ → e5 and V = isotonic N̂ → E5^lvl (§7, A1.3), fit on
  val-A outside the embargo with the fit range; the val-A 70th percentile of the Q1 three-class confidence
  (1 − H/log 3; the gate of §12) for D0 (Call A, W0) and D2 (Call B); the trained models' NA-08 temperatures;
  the price-only V map (A1.4's benchmark);
- ``strategy``: PREREG §12 and A1.6 (NA-13 implements them).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from newsaction import io
from newsaction.analysis import frames, spec
from newsaction.analysis import metrics as mx
from newsaction.config import load_frozen
from newsaction.paths import Layout, resolve_layout
from newsaction.production import ProductionError, artifacts_dir, log_trial

TRAINED_RUNS: Final = {"laya_fin": ("laya-s13",), "anchor": ("anchor-s13",)}  # operator preamble NA-11 item 3
ZERO_SHOT: Final = "local/laya-typed-decisions"
CANDIDATES: Final = ("laya_fin", "anchor", ZERO_SHOT)
TIE_IC: Final = 0.005  # PREREG §8.5
GATE_PERCENTILE: Final = 0.70  # PREREG §12
MAP_DECIMALS: Final = 6
TABLE: Final = "final_selection.csv"
STAGE2: Final = "dm/tournament/stage2.parquet"
ANCHORING: Final = "dm/encoding/anchoring.parquet"
CONFIRM: Final = "dm/encoding/confirm.parquet"


# --- readings of the candidates and the comparators -------------------------------------------------------


def candidate_readings(model: str, splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    if model == ZERO_SHOT:
        return frames.readings_zeroshot(splits, layout)
    return frames.readings_trained(model, splits, layout)


def comparator_readings(model: str, layout: Layout | None = None) -> pd.DataFrame:
    """A screen-failing comparator's val-A readings from NA-06 stage 2 (Call A on W0, Call B on D2; 3,000
    events) and NA-07's anchoring sample (Call A on W2; 1,500 events), core battery."""
    s2 = io.read_parquet(STAGE2, layout=layout)
    s2 = s2.loc[(s2["model"] == model) & s2["valid"].astype(bool)]
    parts = []
    for tag, p in (("s2a", "a0_"), ("s2b", "b2_")):
        g = s2.loc[s2["tag"] == tag].set_index("event_id")
        f = pd.DataFrame({f"{p}n_hat": g["n_hat"]})
        f[f"{p}conf3"] = mx.entropy_confidence(g[["p_fall", "p_flat", "p_rise"]].to_numpy(dtype=float))
        if p == "b2_":
            for k in ("j", "w", "c"):
                f[f"{p}{k}"] = g[k]
        parts.append(f)
    an = io.read_parquet(ANCHORING, layout=layout)
    an = an.loc[(an["model"] == model) & an["valid_a"].astype(bool)].set_index("event_id")
    parts.append(pd.DataFrame({"a2_n_hat": an["n_hat_a"]}))
    out = pd.concat(parts, axis=1, join="outer")
    out.index.name = "event_id"
    return out.reset_index()


def with_conf3(readings: pd.DataFrame) -> pd.DataFrame:
    """Add each source's Q1 three-class confidence (``<p>conf3``) from its nine probabilities (``<p>q1``)."""
    out = readings.copy()
    for col in [f"{s}q1" for s in frames.SOURCES.values() if f"{s}q1" in readings.columns]:
        p = col[: -len("q1")]
        have = out[col].notna()
        conf = np.full(len(out), np.nan)
        if have.any():
            q = np.stack([np.asarray(v, dtype=float) for v in out.loc[have, col]])
            conf[have.to_numpy()] = mx.entropy_confidence(mx.three_class(q))
        out[f"{p}conf3"] = conf
    return out


# --- the val-B table and the rule (§8.5) --------------------------------------------------------------------


def _wide(base: pd.DataFrame, readings: Mapping[str, pd.DataFrame], col: str) -> pd.DataFrame:
    df = base.copy()
    for model, r in readings.items():
        if col in r.columns:
            df = df.merge(
                r[["event_id", col]].rename(columns={col: f"{col}__{model}"}),
                on="event_id",
                how="left",
                validate="one_to_one",
            )
    return df


def selection_table(
    d0: pd.DataFrame, d2: pd.DataFrame, readings: Mapping[str, pd.DataFrame], cfg: spec.AnalysisConfig
) -> pd.DataFrame:
    """One row per candidate: val-B IC of N̂ with z_cc on the common events, and the tie-break IC(J, y2)."""
    w0 = _wide(d0, readings, "a0_n_hat")
    cols = [f"a0_n_hat__{m}" for m in readings]
    common = w0.dropna(subset=[*cols, "z_cc"])
    w2 = _wide(d2, readings, "b2_j")
    rows = []
    for m in readings:
        e = spec.ic(common, "val_b", f"a0_n_hat__{m}", "z_cc", cfg)
        j = spec.ic(w2, "val_b", f"b2_j__{m}", "y2", cfg) if f"b2_j__{m}" in w2.columns else None
        rows.append(
            {
                "model": m,
                "role": "candidate",
                "runs": ",".join(TRAINED_RUNS.get(m, ("zero-shot",))),
                "n_events": e.n_obs,
                "n_days": e.n_days,
                "ic": e.value,
                "nw_t": e.nw_t,
                "boot_se": e.boot_se,
                "ci_low": e.ci_low,
                "ci_high": e.ci_high,
                "p_one_sided": e.p,
                "ic_j_y2": None if j is None else j.value,
                "ic_j_y2_t": None if j is None else j.nw_t,
                "ic_j_y2_days": None if j is None else j.n_days,
                "cost_per_1000": 0.0,
            }
        )
    return pd.DataFrame(rows)


def choose(table: pd.DataFrame, tie: float = TIE_IC) -> tuple[str, str]:
    """PREREG §8.5 on the candidates' rows: (winner, the reason)."""
    t = table.loc[table["role"] == "candidate"].sort_values("ic", ascending=False, kind="mergesort")
    if t.empty or not np.isfinite(t["ic"].to_numpy(dtype=float)).any():
        raise ProductionError("no candidate has a val-B IC")
    first, second = t.iloc[0], (t.iloc[1] if len(t) > 1 else None)
    if second is None or float(first["ic"]) - float(second["ic"]) >= tie:
        return str(first["model"]), "highest val-B IC"
    pair = t.iloc[:2].copy()
    j = pair["ic_j_y2"].astype(float)
    if j.notna().all() and j.iloc[0] != j.iloc[1]:
        return str(pair["model"].iloc[int(np.argmax(j.to_numpy()))]), f"IC within {tie}: the higher IC(J, y2)"
    c = pair["cost_per_1000"].astype(float)
    if c.iloc[0] != c.iloc[1]:
        return str(
            pair["model"].iloc[int(np.argmin(c.to_numpy()))]
        ), f"IC within {tie}, IC(J, y2) tied: the lower cost per 1,000"
    return str(first["model"]), f"IC within {tie}, IC(J, y2) and cost tied: the higher IC"


def comparator_rows(d0: pd.DataFrame, cfg: spec.AnalysisConfig, layout: Layout | None = None) -> pd.DataFrame:
    """The screen-failing comparators on NA-07's val-B sample (E3, Call A D0, 1,500 events): information."""
    c = io.read_parquet(CONFIRM, layout=layout)
    c = c.loc[(c["encoding"] == "E3") & c["valid"].astype(bool)]
    lb = pd.read_csv(resolve_layout(layout).root / "artifacts/NA-06/leaderboard.csv").set_index("model")
    rows = []
    for m, g in c.groupby("model"):
        f = d0.merge(g[["event_id", "n_hat"]], on="event_id", how="inner")
        e = spec.ic(f, "val_b", "n_hat", "z_cc", cfg)
        rows.append(
            {
                "model": str(m),
                "role": "comparator (screen-failing; NA-07 val-B sample)",
                "runs": "api",
                "n_events": e.n_obs,
                "n_days": e.n_days,
                "ic": e.value,
                "nw_t": e.nw_t,
                "boot_se": e.boot_se,
                "ci_low": e.ci_low,
                "ci_high": e.ci_high,
                "p_one_sided": e.p,
                "cost_per_1000": float(lb["cost_per_1000_a2"].astype(float).loc[str(m)]),
            }
        )
    return pd.DataFrame(rows)


# --- val-A maps, gates, temperatures -----------------------------------------------------------------------


def fit_map(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    """Increasing isotonic map of y on x (sklearn, clipped outside the fitted range): rounded breakpoints."""
    keep = x.notna() & y.notna()
    if int(keep.sum()) < 30:
        raise ProductionError(f"a map needs >= 30 pairs, got {int(keep.sum())}")
    iso = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(
        x[keep].to_numpy(dtype=float), y[keep].to_numpy(dtype=float)
    )
    bx = np.round(np.asarray(iso.X_thresholds_, dtype=float), MAP_DECIMALS)
    by = np.round(np.asarray(iso.y_thresholds_, dtype=float), MAP_DECIMALS)
    first = np.r_[True, np.diff(bx) > 0]  # rounding may merge neighbours: keep the first of each
    return {"x": bx[first].tolist(), "y": by[first].tolist(), "n": int(keep.sum())}


def _range(frame: pd.DataFrame) -> list[str]:
    s = pd.to_datetime(frame["session"])
    return [str(s.min().date()), str(s.max().date())]


def calibration_entry(
    d0: pd.DataFrame, d2: pd.DataFrame, readings: pd.DataFrame, cfg: spec.AnalysisConfig
) -> dict[str, Any]:
    """One model's val-A maps (per source with N̂) and confidence gates."""
    out: dict[str, Any] = {}
    for prefix, base in (("a0_", d0), ("a2_", d2)):
        col = f"{prefix}n_hat"
        if col not in readings.columns:
            continue
        f = spec.eval_sample(
            base.merge(readings[["event_id", col]], on="event_id", how="inner"), "val_a", cfg
        )
        f = f.dropna(subset=[col, "e5", "e5_lvl"])  # e5 and E5^lvl share the t+4 purge: the rows of both maps
        out[prefix.rstrip("_")] = {
            "n_tilde": fit_map(f[col], f["e5"]),
            "v": fit_map(f[col], f["e5_lvl"]),
            "fit_range": _range(f),
            "split": "val_a",
        }
    gates: dict[str, Any] = {}
    for point, prefix, base in (("D0", "a0_", d0), ("D2", "b2_", d2)):
        col = f"{prefix}conf3"
        if col not in readings.columns:
            continue
        f = spec.eval_sample(
            base.merge(readings[["event_id", col]], on="event_id", how="inner"), "val_a", cfg
        )
        v = f[col].dropna()
        if len(v) >= 30:
            gates[point] = {
                "source": prefix.rstrip("_"),
                "percentile": GATE_PERCENTILE,
                "value": float(np.quantile(v.to_numpy(dtype=float), GATE_PERCENTILE)),
                "n": len(v),
                "fit_range": _range(f.loc[v.index]),
            }
    out["gates"] = gates
    return out


def trained_temperatures(layout: Layout | None = None) -> dict[str, dict[str, float]]:
    """NA-08's val-A temperatures of the frozen runs (``predictions/<run>/na08_<run>_calibration.json``)."""
    lay = resolve_layout(layout)
    out: dict[str, dict[str, float]] = {}
    for model, runs in TRAINED_RUNS.items():
        path = lay.work / "kaggle/predictions" / runs[0] / f"na08_{runs[0]}_calibration.json"
        cal = json.loads(path.read_text(encoding="utf-8"))
        out[model] = {q: float(h["temperature"]) for q, h in cal["heads"].items()}
    return out


# --- frozen.yaml sections -----------------------------------------------------------------------------------


def thresholds_entry() -> dict[str, Any]:
    cfg = spec.load_config()
    return {
        "rg": {"min_abs_n_hat": 0.5, "band": 0.5, "note": "PREREG §7 RG; the PRD's δ is this band"},
        "class_band": cfg.metrics.class_band,
        "auc_abs_z": cfg.metrics.auc_abs_z,
        "explained_x": cfg.explanation.explained_x,
        "half_life_lambda": cfg.convergence.half_life_lambda,
        "confidence_gate_percentile": GATE_PERCENTILE,
        "confidence": "Q1 three-class confidence 1 − H(fall, no move, rise)/log 3 of the signal's reading",
    }


def strategy_entry() -> dict[str, Any]:
    """PREREG §12 and A1.6 (NA-13 implements them; nothing here is fit)."""
    return {
        "quantile": 0.2,
        "within": "tier",
        "pool_if_side_below": 10,
        "weights": "equal",
        "hedge": "beta_spy",
        "s_d0": {"rank": "a0_n_tilde", "entry": "open_t", "exit": "close_t", "secondary_exit": "close_t+1"},
        "s_d1": {
            "rank": ["b1_j", "rg"],
            "entry": "10:00 bar close",
            "exits": ["close_t", "close_t+1", "close_t+5"],
        },
        "s_d2": {
            "rank": ["b2_j", "rg"],
            "entry": "open_t+1",
            "exits": ["close_t+1", "close_t+5", "close_t+20"],
            "calendar_time": True,
        },
        "s_conv": {
            "primary": True,
            "rank": "U_tau = V - G^lvl_tau (long the top: price below value)",
            "points": {
                "D1": {
                    "value": "a0_v",
                    "g_lvl": "g_d1_lvl",
                    "entry": "10:00 bar close",
                    "exits": ["close_t", "close_t+1", "close_t+5", "close_t+20"],
                },
                "D2": {
                    "value": "a2_v",
                    "g_lvl": "g_d2_lvl",
                    "entry": "open_t+1",
                    "exits": ["close_t+1", "close_t+5", "close_t+20"],
                },
            },
            "calendar_time": True,
        },
        "gating": {
            "variant": "secondary",
            "percentile": GATE_PERCENTILE,
            "values": "calibration.<model>.gates",
        },
        "costs_bp_per_side": [5, 10, 20],
        "capacity_adv_share": 0.01,
        "deflated_sharpe_trials": "ledgers/trials.jsonl",
        "benchmarks": ["gap_fade", "vendor_sentiment_rank", "random_signal_placebo"],
        "seed": 2026,
    }


def ensure_section(layout: Layout, name: str, before: str = "questions_v1_sha256") -> None:
    """Add ``name: null`` to configs/frozen.yaml (before ``before``) if the section does not exist."""
    path = layout.configs / "frozen.yaml"
    text = path.read_text(encoding="utf-8")
    if any(ln.startswith(f"{name}:") for ln in text.splitlines()):
        return
    lines = text.splitlines(keepends=True)
    at = next(i for i, ln in enumerate(lines) if ln.startswith(f"{before}:"))
    lines.insert(at, f"{name}: null\n")
    io.atomic_write_bytes(path, "".join(lines).encode("utf-8"))


def write_section(layout: Layout, name: str, comment: str, entry: Mapping[str, Any]) -> None:
    from newsaction.encoding.run import write_frozen_section

    ensure_section(layout, name)
    write_frozen_section(layout, name, comment, entry)


def pin_trained_runs(layout: Layout | None = None) -> None:
    """Write the trained instruments' pin before anything reads them (``import_preds.read_instrument``)."""
    lay = resolve_layout(layout)
    sel = load_frozen(lay.configs / "frozen.yaml").selection
    entry = dict(sel) if isinstance(sel, Mapping) else {}
    entry["trained_runs"] = {k: list(v) for k, v in TRAINED_RUNS.items()}
    write_section(lay, "selection", "NA-11: PREREG §8.5 (artifacts/NA-11/final_selection.csv)", entry)


# --- the stage ----------------------------------------------------------------------------------------------


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if not load_frozen(lay.configs / "frozen.yaml").allow_val_b:
        raise ProductionError("allow_val_b is false (CLAUDE.md C13)")
    pin_trained_runs(lay)
    cfg = spec.load_config()
    splits = ["val_a", "val_b"]
    d0 = frames.base("D0", splits=splits, layout=lay)
    d2 = frames.base("D2", splits=splits, layout=lay)
    readings = {m: with_conf3(candidate_readings(m, splits, lay)) for m in CANDIDATES}
    table = selection_table(d0, d2, readings, cfg)
    winner, reason = choose(table)
    table["selected"] = table["model"] == winner
    table["rank"] = table["ic"].rank(ascending=False, method="first").astype(int)
    table["rule"] = np.where(table["selected"], reason, "")
    comps = comparator_rows(d0, cfg, lay)
    full = pd.concat([table, comps], ignore_index=True)
    path = artifacts_dir(lay) / TABLE
    full.to_csv(path, index=False)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    for rec in table.to_dict("records"):
        params = {"model": rec["model"], "runs": rec["runs"], "metric": "§8.5 val-B D0 IC(N̂, z_cc)"}
        log_trial(
            "final_selection", str(rec["model"]), params, "val_b", "ic_z_cc", float(rec["ic"]), layout=lay
        )
        if rec["ic_j_y2"] is not None and math.isfinite(float(rec["ic_j_y2"])):
            log_trial(
                "final_selection",
                str(rec["model"]),
                params,
                "val_b",
                "ic_j_y2",
                float(rec["ic_j_y2"]),
                layout=lay,
            )
    frozen = load_frozen(lay.configs / "frozen.yaml")
    comparators = list(frozen.encoding["models"])
    calibration: dict[str, Any] = {}
    for m in CANDIDATES:
        calibration[m] = calibration_entry(d0, d2, readings[m], cfg)
    for m in comparators:
        calibration[m] = calibration_entry(d0, d2, comparator_readings(m, lay), cfg)
    temps = trained_temperatures(lay)
    for m, t in temps.items():
        calibration[m]["temperatures_na08"] = t
    po = spec.eval_sample(d0.dropna(subset=["po_n_hat", "e5", "e5_lvl"]), "val_a", cfg)
    calibration["price_only"] = {
        "a0": {
            "v": fit_map(po["po_n_hat"], po["e5_lvl"]),
            "n_tilde": fit_map(po["po_n_hat"], po["e5"]),
            "fit_range": _range(po),
            "split": "val_a",
        }
    }
    selection = {
        "rule": "prereg-8.5-v1",
        "primary_instrument": winner,
        "reason": reason,
        "candidates": list(CANDIDATES),
        "anchor": "anchor",
        "trained_runs": {k: list(v) for k, v in TRAINED_RUNS.items()},
        "comparators": comparators,
        "comparators_note": "screen-failing (PREREG §8.3); every result model-specific (§1.3, §15 NA-06 row)",
        "table_file": f"artifacts/NA-11/{TABLE}",
        "ic_table_sha": sha,
        "val_b": {"n_events": int(table["n_events"].iloc[0]), "n_days": int(table["n_days"].iloc[0])},
    }
    write_section(lay, "selection", "NA-11: PREREG §8.5 (artifacts/NA-11/final_selection.csv)", selection)
    write_section(
        lay, "thresholds", "NA-11: PREREG §7 RG (δ), §11.2, A1.5, A3.3, §12 gates", thresholds_entry()
    )
    write_section(
        lay,
        "calibration",
        "NA-11: val-A maps Ñ and V (§7, A1.3), gates (§12), NA-08 temperatures",
        calibration,
    )
    write_section(lay, "strategy", "NA-11: PREREG §12 and A1.6 S-CONV (NA-13 implements)", strategy_entry())
    return {"winner": winner, "reason": reason, "table": full.to_dict("records"), "ic_table_sha": sha}


def main() -> int:
    out = run()
    print(json.dumps({k: v for k, v in out.items() if k != "table"}, indent=1))
    print(
        pd.DataFrame(out["table"])[
            ["model", "role", "n_events", "n_days", "ic", "nw_t", "ci_low", "ci_high", "ic_j_y2"]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
