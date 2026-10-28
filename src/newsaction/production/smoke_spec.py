"""NA-11 S1 / AC2: the analysis spec end to end on val-B (the smoke run).

Runs every spec function whose inputs exist before production on val-B: Laya-Fin as the primary instrument,
the anchor for the headline rule, Laya zero-shot for H7. The A2/A3 functions that need the extended or explain
answers (horizon validity, H6, A3.3–A3.5) have no such answers before production; their synthetic tests cover
them (``tests/test_spec_functions.py``).

The ridge protocol's splits are shifted for the smoke run (fit and λ on val-A, evaluation on val-B), since the
frozen protocol fits on val-B and evaluates on test. The numbers are a code check, not pre-registered
estimates.
The spec was final before this ran; any later change to it is listed in the REPORT.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.analysis import frames, spec
from newsaction.config import load_frozen, load_splits
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, artifacts_dir
from newsaction.production.select_final import ZERO_SHOT, candidate_readings

SPLIT: Final = "val_b"
OUT: Final = "spec_smoke_val_b.json"


def maps_for(model: str, frozen: Any) -> dict[str, dict[str, Any]]:
    cal = frozen.calibration[model]
    return {f"{src}_": cal[src] for src in ("a0", "a2") if src in cal}


def smoke_config() -> spec.AnalysisConfig:
    cfg = spec.load_config()
    ridge = cfg.ridge.model_copy(update={"fit_split": "val_a", "lambda_split": "val_a", "eval_split": SPLIT})
    return cfg.model_copy(update={"ridge": ridge})


def _jsonable(x: Any) -> Any:
    if isinstance(x, Mapping):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.generic):
        return _jsonable(x.item())
    if isinstance(x, float) and not math.isfinite(x):
        return None if math.isnan(x) else ("inf" if x > 0 else "-inf")
    return x


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    frozen = load_frozen(lay.configs / "frozen.yaml")
    cfg = smoke_config()
    t0 = time.time()
    splits = ["val_a", "val_b"]
    d0b, d2b = frames.base("D0", splits=splits, layout=lay), frames.base("D2", splits=splits, layout=lay)
    po_map = frozen.calibration["price_only"]["a0"]["v"]
    read = {m: candidate_readings(m, splits, lay) for m in ("laya_fin", "anchor", ZERO_SHOT)}
    d0 = {m: frames.build(d0b, r, maps=maps_for(m, frozen), price_value_map=po_map) for m, r in read.items()}
    d2 = {m: frames.build(d2b, r, maps=maps_for(m, frozen)) for m, r in read.items()}
    out: dict[str, Any] = {"split": SPLIT, "primary": "laya_fin", "steps": {}}

    def step(name: str, fn: Callable[[], Any]) -> None:
        s = time.time()
        out["steps"][name] = {"result": _jsonable(fn()), "seconds": round(time.time() - s, 1)}

    p = d0["laya_fin"]
    step("h1_h1b", lambda: {m: spec.primary_d0(d0[m], SPLIT, cfg) for m in ("laya_fin", "anchor")})
    step("ic_targets", lambda: {m: spec.ic_targets(d0[m], SPLIT, cfg) for m in d0})
    step("h2_d2", lambda: {m: spec.h2(d2[m], SPLIT, cfg, "D2") for m in ("laya_fin", "anchor")})
    step("h2_d1", lambda: spec.h2(p, SPLIT, cfg, "D1"))
    step("h2_d0", lambda: spec.h2(p, SPLIT, cfg, "D0"))
    step("h2_by_abs_g", lambda: spec.h2_by_abs_g(d2["laya_fin"], SPLIT, cfg, "D2"))
    trained_groups = {
        "R": list(cfg.groups.R),
        "N": list(cfg.groups.N_trained),
        "J": list(cfg.groups.J_trained),
    }
    step("h3", lambda: spec.h3(d2["laya_fin"], cfg, trained_groups))
    step("h4", lambda: spec.h4(p, cfg, list(cfg.groups.h4_news_trained)))
    prim_d0 = out["steps"]["h1_h1b"]["result"]["laya_fin"]
    anch_d0 = out["steps"]["h1_h1b"]["result"]["anchor"]
    prim = {k: spec.directional(prim_d0[k] | {"test": k}) for k in ("H1", "H1b")}
    prim["H2"] = spec.directional(spec.h2(d2["laya_fin"], SPLIT, cfg, "D2"))
    anch = {k: spec.directional(anch_d0[k] | {"test": k}) for k in ("H1", "H1b")}
    anch["H2"] = spec.directional(spec.h2(d2["anchor"], SPLIT, cfg))
    adj = spec.primary_family({k: v["p"] for k, v in prim.items()}, cfg)
    step("headline", lambda: {"adjusted": adj, "verdicts": spec.headline(prim, anch, adj, cfg)})
    step("heterogeneity", lambda: spec.heterogeneity(d2["laya_fin"], SPLIT, cfg))
    step("ladder", lambda: spec.ladder(p, SPLIT, cfg))
    step("ladder_clean", lambda: spec.ladder(p, SPLIT, cfg, clean=True))
    step("gap_d2", lambda: spec.gap_closure(d2["laya_fin"], SPLIT, cfg, "D2"))
    step("gap_d1", lambda: spec.gap_closure(p, SPLIT, cfg, "D1"))
    step("tracking_error", lambda: spec.tracking_error(p, SPLIT, cfg))
    step(
        "h2c",
        lambda: spec.h2c_tests(
            out["steps"]["ladder"]["result"],
            out["steps"]["gap_d2"]["result"],
            out["steps"]["tracking_error"]["result"],
            cfg,
        ),
    )
    step(
        "h7",
        lambda: spec.h7(
            p.merge(
                d0[ZERO_SHOT][["event_id", "a0_n_hat"]].rename(columns={"a0_n_hat": "zs_n_hat"}),
                on="event_id",
            ),
            SPLIT,
            cfg,
            "a0_n_hat",
            "zs_n_hat",
        ),
    )
    ref = spec.eval_sample(p, "val_a", cfg)
    s = spec.eval_sample(p, SPLIT, cfg).dropna(subset=["a0_q1", "z_cc"])
    step(
        "calibration",
        lambda: spec.calibration(
            np.stack(s["a0_q1"].map(np.asarray).to_list()), s["z_cc"], ref["z_cc"].dropna(), cfg
        ),
    )
    step("auc_large", lambda: spec.auc_large(s["a0_mag_mean"], s["z_cc"], cfg))
    days = frames.member_days(splits, lay)
    feats = [f for v in cfg.explanation.ladder_steps_trained.values() for f in v]
    dd = frames.with_day_readings(days, read["laya_fin"], feats)
    step("roll_r2", lambda: spec.roll_r2(dd, SPLIT, cfg))
    step("h5_ladder", lambda: spec.h5(dd, cfg, cfg.explanation.ladder_steps_trained))
    step("sector", lambda: spec.sector_ic(p, SPLIT, cfg))
    sessions = sorted(d2b["session"].unique())
    step("robustness_d0", lambda: spec.robustness(p, SPLIT, cfg, sessions, "D0"))
    step("robustness_d2", lambda: spec.robustness(d2["laya_fin"], SPLIT, cfg, sessions, "D2"))
    means = spec.placebo_means(days, ["y2", "z_on", "z_id"])
    step("placebo_h2", lambda: spec.h2(spec.placebo_adjust(d2["laya_fin"], means, ["y2"]), SPLIT, cfg, "D2"))
    step(
        "placebo_h1_h1b", lambda: spec.primary_d0(spec.placebo_adjust(p, means, ["z_on", "z_id"]), SPLIT, cfg)
    )
    step(
        "mechanism_vendor",
        lambda: spec.mechanism_cuts(
            d2["laya_fin"], SPLIT, cfg, lambda f: spec.h2(f, SPLIT, cfg, "D2"), "a2_"
        ),
    )
    panel = io.read_parquet(
        "panel/panel_public.parquet",
        columns=["session", "symbol_id", "ar_cc", "ar_on", "ar_id", "sigma_cc"],
        layout=lay,
    )
    s60 = spec.sigma60(panel, cfg)
    nxt = s60.copy()
    nxt["session"] = nxt.groupby("symbol_id")["session"].shift(1)
    nxt = nxt.dropna(subset=["session"]).rename(columns={"s60_cc": "s60_cc_next", "s60_id": "s60_id_next"})
    pp = io.read_parquet(
        "panel/panel_public.parquet",
        columns=["session", "symbol_id", "ar_cc", "ar_on", "ar_id", "ar_o1_c5"],
        layout=lay,
    )
    pp["session"] = pd.to_datetime(pp["session"]).dt.date
    d2s = d2["laya_fin"].drop(columns=["ar_cc", "ar_on", "ar_id", "ar_o1_c5"], errors="ignore")
    d2s = d2s.merge(pp, on=["session", "symbol_id"], how="left").merge(
        s60, on=["session", "symbol_id"], how="left"
    )
    d2s = d2s.merge(
        nxt[["session", "symbol_id", "s60_cc_next", "s60_id_next"]], on=["session", "symbol_id"], how="left"
    )
    step("sigma60_h2", lambda: spec.h2(spec.sigma60_rescale(d2s), SPLIT, cfg, "D2"))
    ends: dict[str, date] = {str(k): v.end for k, v in load_splits().splits.items() if k in splits}
    rows = spec.eval_sample(p, SPLIT, cfg)[["event_id", "session", "symbol_id", "split"]]
    plat = spec.plateau_rungs(panel, rows, ends, cfg).assign(event_id=rows["event_id"].to_numpy())
    both = (
        plat[["event_id", "car_lvl_c20"]]
        .merge(p[["event_id", "car_lvl_c20"]], on="event_id", suffixes=("_helper", "_targets"))
        .dropna()
    )
    gap = float((both["car_lvl_c20_helper"] - both["car_lvl_c20_targets"]).abs().max())
    if not gap < 1e-9:  # the frozen plateau helper must agree with panel/targets.py on the shared rung
        raise ValueError(f"plateau_rungs' t+20 differs from targets.py's car_lvl_c20 by {gap}")
    out["plateau_check"] = {"rows": len(both), "max_abs_diff_c20": gap}
    lo, hi = cfg.convergence.plateau
    add = plat[["event_id", *[f"car_lvl_c{k}" for k in range(lo, hi)]]]
    pl = p.merge(add, on="event_id", how="left", validate="one_to_one")
    pl["car_lvl_plateau"] = spec.plateau(pl, cfg)
    step("ladder_plateau", lambda: spec.ladder(pl, SPLIT, cfg, rungs={"plateau": "car_lvl_plateau"}))
    residue = {pt: int(spec.eval_sample(f, SPLIT, cfg)["live_format"].sum()) for pt, f in (("D0", p),)}
    out["live_format_states_val_b"] = residue
    out["seconds"] = round(time.time() - t0, 1)
    path = artifacts_dir(lay) / OUT
    path.write_text(json.dumps(_jsonable(out), indent=1, sort_keys=False) + "\n", encoding="utf-8")
    return out


def main() -> int:
    out = run()
    print(json.dumps({k: v["seconds"] for k, v in out["steps"].items()}, indent=1))
    print(f"{CHUNK} smoke run on {SPLIT}: {len(out['steps'])} steps, {out['seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
