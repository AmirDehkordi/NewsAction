"""NA-12 S2: the frozen analysis spec on the test split (PRD NA-12 S2; PREREG §1, §11, A1.3–A1.6, A2.4–A2.5,
A3.2–A3.5; the PREREG §15 NA-11 rows and NA-12's row written before unblinding).

    uv run python -m newsaction.analysis.run_all [section ...]   # every section by default
    uv run python -m newsaction.analysis.run_all --rehearse --out DIR   # val-B as the evaluation split

Every statistic is a ``spec`` function called with the frozen configuration (``spec.load_config()``). This
module builds the frames (``analysis.frames``; the test outcomes from ``work/analysis/targets_test.parquet``),
decides which model answers which test (a model without the reading gets "not available", never a null),
and writes ``artifacts/NA-12/results/<section>.json`` and ``artifacts/NA-12/figure_data/*.csv``; the
analysis frames of the primary instrument, the anchor and the API comparator, and the H3 coalition
predictions, go to ``work/analysis/`` for the verifier.

**Models** (``configs/frozen.yaml`` selection, ``configs/production.yaml``; ``MODELS``): the primary
instrument Laya-Fin (laya-s13), the clean anchor (anchor-s13), Laya zero-shot, the best API comparator
d1-ultra (core + extended + explain) and the core comparators span-02 and drex-v2.0 (Call A D0 only). Every
API result is screen-failing and model-specific (§15 NA-06 row); span-02 carries the S5 footnote.

**Families** (§15 NA-12 row): Holm over Laya-Fin's H1, H1b, H2, H3, H4; §1.3 by ``spec.headline`` with the
anchor's one-sided p. Secondary BH per instrument over the tests it answers (``SECONDARY``), with a pooled
sensitivity family; heterogeneity BH over Laya-Fin's eight cuts. Other models' p are reported with a Holm
within the model, outside every claim.

**Rehearsal** (``--rehearse``, before unblinding): NA-11's smoke configuration (ridge fit and λ on val-A,
evaluation on val-B; the market fit on val-A) and no test file.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.analysis import figdata, frames, slot_path, spec
from newsaction.analysis.unblind import ARTIFACTS, CHUNK
from newsaction.config import load_frozen, load_splits
from newsaction.paths import Layout, resolve_layout

Kind = Literal["trained", "zero_shot", "api"]
PRODUCTION: Final = "dm/production"
RESULTS: Final = "results"
FIGURES: Final = "figure_data"
SPLITS: Final = ("val_a", "val_b", "robustness")
TESTS: Final = ("H1", "H1b", "H2", "H3", "H4")
DAILY: Final = ("session", "symbol_id", "ar_cc", "ar_on", "ar_id", "sigma_cc", "r_spy_cc", "z_cc", "ar_o1_c5")
PLACEBO_TARGETS: Final = ("y2", "z_on", "z_id", "z_cc")


@dataclass(frozen=True)
class ModelSpec:
    key: str
    name: str  # configs/frozen.yaml calibration key
    kind: Kind
    role: str
    readings: str | None = None
    full: bool = False  # the extended + explain battery (the best API comparator, PREREG A2.1)
    footnote: str = ""


MODELS: Final = (
    ModelSpec("laya_fin", "laya_fin", "trained", "primary instrument (laya-s13)"),
    ModelSpec("anchor", "anchor", "trained", "clean anchor (anchor-s13)"),
    ModelSpec(
        "laya_zs",
        "local/laya-typed-decisions",
        "zero_shot",
        "Laya zero-shot (PREREG §10.5)",
        f"{PRODUCTION}/local_laya_typed_decisions_test.parquet",
    ),
    ModelSpec(
        "d1_ultra",
        "liquid/d1-ultra",
        "api",
        "best API comparator; screen-failing, model-specific",
        f"{PRODUCTION}/liquid_d1_ultra_api_comparators_market.parquet",
        full=True,
    ),
    ModelSpec(
        "span_02",
        "respan/span-02",
        "api",
        "core comparator; screen-failing, model-specific",
        f"{PRODUCTION}/respan_span_02_api_comparators_market.parquet",
        footnote="S5 canary STOP, operator: proceed (PREREG §15, post-freeze NA-11 row)",
    ),
    ModelSpec(
        "drex_v2",
        "nace-ai/drex-v2.0",
        "api",
        "core comparator; screen-failing, model-specific",
        f"{PRODUCTION}/nace_ai_drex_v2_0_api_comparators_market.parquet",
    ),
)
PRIMARY: Final = "laya_fin"
ANCHOR: Final = "anchor"
API: Final = "d1_ultra"
ZERO_SHOT: Final = "laya_zs"
FOCUS: Final = (PRIMARY, ANCHOR, API)  # every A1 / A3 / robustness analysis runs for these three
SECONDARY: Final = {
    PRIMARY: ("H5", "H7", "H2C_kappa_hstar", "H2C_kappa_increase", "H2C_lambda_t5", "H2C_tracking_naive"),
    ANCHOR: ("H5", "H2C_kappa_hstar", "H2C_kappa_increase", "H2C_lambda_t5", "H2C_tracking_naive"),
    API: ("H5", "H6", "H2C_kappa_hstar", "H2C_kappa_increase", "H2C_lambda_t5", "H2C_tracking_naive", "A3.4"),
}
POOLED_FROM_API: Final = ("H6", "A3.4")  # the pooled sensitivity family adds these to the primary's
BASELINES: Final = {  # PREREG §10: D0 signals (N_hat) on the Call A D0 events
    "sentiment": ("baselines/sentiment.parquet", None),
    "embed_ridge": ("baselines/embed_ridge.parquet", None),
    "tags_gbm": ("baselines/tags_gbm.parquet", None),
    "llm": ("baselines/llm.parquet", f"{PRODUCTION}/llm_test.parquet"),
}
# Figure 4's release dates: the anchor's checkpoint (PREREG §9.2); the API models' from the NA-05 catalog
RELEASES: Final = {
    "anchor": ("2024-12", "answerdotai/ModernBERT-large Dec-2024 checkpoint (PREREG §9.2)"),
}


class RunAllError(RuntimeError):
    """The inputs or the configuration do not match the frozen plan."""


def check_models(layout: Layout | None = None) -> None:
    """The model roles must be the frozen ones (``configs/frozen.yaml`` selection, ``production.yaml``)."""
    from newsaction.production.plan import load_plan

    lay = resolve_layout(layout)
    sel = load_frozen(lay.configs / "frozen.yaml").selection
    plan = load_plan(lay.configs / "production.yaml")
    by_key = {m.key: m for m in MODELS}
    got = {
        "primary": sel["primary_instrument"] == by_key[PRIMARY].name,
        "anchor": sel["anchor"] == by_key[ANCHOR].name,
        "comparators": list(sel["comparators"]) == [m.name for m in MODELS if m.kind == "api"],
        "api": plan.api.model == by_key[API].name,
        "core": [c.model for c in plan.comparators_core] == ["respan/span-02", "nace-ai/drex-v2.0"],
        "zero_shot": plan.laya_zero_shot.model == by_key[ZERO_SHOT].name,
    }
    bad = [k for k, ok in got.items() if not ok]
    if bad:
        raise RunAllError(f"model roles differ from the frozen selection: {bad}")


# --- context ------------------------------------------------------------------------------------------------


@dataclass
class Ctx:
    lay: Layout
    cfg: spec.AnalysisConfig
    rehearsal: bool
    d0: dict[str, pd.DataFrame]
    d2: dict[str, pd.DataFrame]
    readings: dict[str, pd.DataFrame]
    days: pd.DataFrame
    daily: pd.DataFrame
    sessions: list[date]
    frozen: Any
    out_root: Path
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def split(self) -> str:
        return self.cfg.ridge.eval_split

    @property
    def fit_splits(self) -> list[str]:
        r = self.cfg.ridge
        return list(dict.fromkeys([r.fit_split, r.lambda_split, r.eval_split]))


def rehearsal_config() -> spec.AnalysisConfig:
    """NA-11's smoke configuration: ridge fit and λ on val-A, evaluation on val-B (the A3.5 fit on val-A)."""
    cfg = spec.load_config()
    ridge = cfg.ridge.model_copy(
        update={"fit_split": "val_a", "lambda_split": "val_a", "eval_split": "val_b"}
    )
    market = cfg.market.model_copy(update={"fit_splits": ("val_a",), "eval_split": "val_b"})
    return cfg.model_copy(update={"ridge": ridge, "market": market})


def config_for(rehearsal: bool) -> spec.AnalysisConfig:
    """The test run uses the frozen configuration itself; the rehearsal moves only the fitting splits."""
    return rehearsal_config() if rehearsal else spec.load_config()


def maps_for(name: str, frozen: Any) -> dict[str, dict[str, Any]]:
    cal = frozen.calibration.get(name, {})
    return {f"{src}_": cal[src] for src in ("a0", "a2") if src in cal}


def load_readings(m: ModelSpec, splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """One model's readings, one row per event, every source (``analysis.frames``)."""
    if m.kind == "trained":
        return frames.readings_trained(m.name, splits, layout, s7=True)
    assert m.readings is not None
    if m.kind == "zero_shot":
        parts = [frames.readings_zeroshot([s for s in splits if s != "test"], layout)]
        if "test" in splits:
            parts.append(frames.readings_api(m.readings, layout, valid_only=True))
        return pd.concat(parts, ignore_index=True)
    return frames.readings_api(m.readings, layout, valid_only=True)


def explanation_features(readings: pd.DataFrame) -> pd.DataFrame:
    """A3.2's explanation step for a model that answers Q16–Q17 (the config's ``b2_x_n_hat`` and
    ``reason_n_hat``): X·N̂_W2 and, for each Q17 reason, 1[argmax reason = r]·N̂_W2 (§15 NA-12 row)."""
    out = readings.copy()
    out["b2_x_n_hat"] = out["b2_x"] * out["a2_n_hat"]
    lab = out["b2_label_move_reason"]
    for lev in sorted(str(v) for v in lab.dropna().unique()):
        out[f"reason__{lev}__n_hat"] = ((lab == lev).astype(float) * out["a2_n_hat"]).where(lab.notna())
    return out


def reason_columns(frame: pd.DataFrame) -> list[str]:
    return sorted(c for c in frame.columns if c.startswith("reason__") and c.endswith("__n_hat"))


def build_ctx(layout: Layout | None = None, *, rehearsal: bool = False, out_root: Path | None = None) -> Ctx:
    lay = resolve_layout(layout)
    check_models(lay)
    cfg = config_for(rehearsal)
    frozen = load_frozen(lay.configs / "frozen.yaml")
    splits = [*SPLITS, *([] if rehearsal else ["test"])]
    pub_p, pub_i = frames.public_targets(lay)
    pub_days = frames.member_days(list(SPLITS), lay)
    if rehearsal:
        panel, intraday, days, daily = pub_p, pub_i, pub_days, pub_p[list(DAILY)].copy()
    else:
        tp, ti, tm = frames.test_targets(lay)
        panel = pd.concat([pub_p, tp], ignore_index=True)
        intraday = pd.concat([pub_i, ti], ignore_index=True)
        days = pd.concat([pub_days, frames.member_days(["test"], lay, panel=tm)], ignore_index=True)
        daily = pd.concat([pub_p[list(DAILY)], tp[list(DAILY)]], ignore_index=True)
    daily["session"] = pd.to_datetime(daily["session"]).dt.date
    d0b = frames.base("D0", splits=splits, layout=lay, targets=(panel, intraday))
    d2b = frames.base("D2", splits=splits, layout=lay, targets=(panel, intraday))
    if not rehearsal:
        slots = tm[["session", "symbol_id", *slot_path.POINT_COLUMNS]].copy()
        slots["session"] = pd.to_datetime(slots["session"]).dt.date
        d0b = d0b.merge(slots, on=["session", "symbol_id"], how="left", validate="many_to_one")
    po_map = frozen.calibration["price_only"]["a0"]["v"]
    d0: dict[str, pd.DataFrame] = {}
    d2: dict[str, pd.DataFrame] = {}
    readings: dict[str, pd.DataFrame] = {}
    for m in MODELS:
        r = load_readings(m, splits, lay)
        if m.full:
            r = explanation_features(r)
        readings[m.key] = r
        d0[m.key] = frames.build(d0b, r, maps=maps_for(m.name, frozen), price_value_map=po_map)
        d2[m.key] = frames.build(d2b, r, maps=maps_for(m.name, frozen))
    sessions = calendar.sessions(min(daily["session"]), max(daily["session"]))
    root = out_root if out_root is not None else lay.root / ARTIFACTS
    return Ctx(lay, cfg, rehearsal, d0, d2, readings, days, daily, sessions, frozen, root)


# --- helpers ------------------------------------------------------------------------------------------------


def jsonable(x: Any) -> Any:
    if isinstance(x, Mapping):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set | frozenset):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return [jsonable(v) for v in x.tolist()]
    if isinstance(x, np.generic):
        return jsonable(x.item())
    if isinstance(x, float) and not math.isfinite(x):
        return None if math.isnan(x) else ("inf" if x > 0 else "-inf")
    if isinstance(x, date):
        return str(x)
    return x


def na(reason: str) -> dict[str, Any]:
    """A test the model cannot answer: no p, not counted as a null (§15 NA-11 row (xii))."""
    return {"available": False, "reason": reason}


def answers(frame: pd.DataFrame, cols: Sequence[str], splits: Sequence[str]) -> bool:
    """Every column exists and has values on each split."""
    if any(c not in frame.columns for c in cols):
        return False
    return all(bool(frame.loc[frame["split"] == s, list(cols)].notna().all(axis=1).any()) for s in splits)


def model(key: str) -> ModelSpec:
    return next(m for m in MODELS if m.key == key)


def groups_for(m: ModelSpec, cfg: spec.AnalysisConfig) -> dict[str, list[str]] | None:
    """§11.5's feature groups the model answers (trained: Q1 and H-cont; the full API battery: all)."""
    g = cfg.groups
    if m.kind == "trained":
        return {"R": list(g.R), "N": list(g.N_trained), "J": list(g.J_trained)}
    if m.full:
        return {"R": list(g.R), "N": list(g.N), "J": list(g.J)}
    return None


def h4_news(m: ModelSpec, cfg: spec.AnalysisConfig) -> list[str]:
    return list(cfg.groups.h4_news_trained if m.kind == "trained" else cfg.groups.h4_news)


def h4_extra(m: ModelSpec, cfg: spec.AnalysisConfig) -> list[str]:
    return list(cfg.groups.h4_a2) if m.full else []


def ladder_steps(m: ModelSpec, cfg: spec.AnalysisConfig, frame: pd.DataFrame) -> dict[str, list[str]] | None:
    """A3.2's steps: trained models the config's trained steps; the full battery adds the explanation step
    with X, X·N̂_W2 and each reason × N̂_W2 (``explanation_features``)."""
    e = cfg.explanation
    if m.kind == "trained":
        return {k: list(v) for k, v in e.ladder_steps_trained.items()}
    if m.full:
        steps = {k: list(v) for k, v in e.ladder_steps.items()}
        steps["explanation"] = ["b2_x", "b2_x_n_hat", *reason_columns(frame)]
        return steps
    return None


def p_of(result: Mapping[str, Any]) -> float:
    return float(result["p"]) if "p" in result and result.get("available", True) else math.nan


def has_p(result: Mapping[str, Any]) -> bool:
    return not math.isnan(p_of(result))


def _with(frame: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    return frame.loc[mask.fillna(False).astype(bool).to_numpy()]


# --- S2 sections --------------------------------------------------------------------------------------------


def primary(ctx: Ctx) -> dict[str, Any]:
    """H1, H1b, H2 (D2), H3, H4 per model; H2 at D1 and D0 and within |G| bins (reported); Holm and §1.3."""
    cfg, ev = ctx.cfg, ctx.split
    out: dict[str, Any] = {"split": ev, "models": {}}
    for m in MODELS:
        d0, d2 = ctx.d0[m.key], ctx.d2[m.key]
        r: dict[str, Any] = {}
        a0 = answers(d0, ["a0_n_hat"], [ev])
        a2 = answers(d2, ["a2_n_hat"], [ev])
        if a0:
            r |= spec.primary_d0(d0, ev, cfg)
        else:
            r["H1"] = r["H1b"] = na("no Call A D0 reading")
        r["H2"] = spec.h2(d2, ev, cfg, "D2") if a2 else na("no Call A W2 reading")
        groups = groups_for(m, cfg)
        reads = [f for k in ("N", "J") for f in (groups or {}).get(k, [])]
        if groups and answers(d2, reads, ctx.fit_splits):
            r["H3"] = spec.h3(d2, cfg, groups, ev)
            ctx.cache[f"h3:{m.key}"] = (groups, r["H3"])
        else:
            r["H3"] = na("no Call A W2 / Call B readings on the fit, λ and test splits")
        news, extra = h4_news(m, cfg), h4_extra(m, cfg)
        if answers(d0, [*news, *extra], ctx.fit_splits):
            r["H4"] = spec.h4(d0, cfg, news, extra, ev)
        else:
            r["H4"] = na("no D0 readings on the fit and λ splits (the ridge protocol needs val-A and val-B)")
        r["H2_D1"] = spec.h2(d0, ev, cfg, "D1") if a0 and answers(d0, ["g_d1", "y1"], [ev]) else na("no D1 G")
        r["H2_D0"] = spec.h2(d0, ev, cfg, "D0") if a0 else na("no Call A D0 reading")
        r["H2_by_abs_g"] = spec.h2_by_abs_g(d2, ev, cfg, "D2") if a2 else na("no Call A W2 reading")
        r["holm_within_model"] = spec.primary_family({t: p_of(r[t]) for t in TESTS}, cfg)
        out["models"][m.key] = r
    prim = out["models"][PRIMARY]
    anch = out["models"][ANCHOR]
    d_prim = {t: spec.directional(prim[t]) for t in TESTS if has_p(prim[t])}
    d_anch = {t: spec.directional(anch[t]) for t in TESTS if has_p(anch[t])}
    adjusted = spec.primary_family({t: v["p"] for t, v in d_prim.items()}, cfg)
    out["family"] = {
        "tests": list(cfg.multiple_testing.primary.tests),
        "alpha": cfg.multiple_testing.primary.alpha,
    }
    out["holm"] = adjusted
    out["directional"] = {"primary": d_prim, "anchor": d_anch}
    out["headline"] = spec.headline(d_prim, d_anch, adjusted, cfg)
    return out


def _plateau_frame(ctx: Ctx, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The frame with ``car_lvl_plateau`` (A1.5): the frozen helper's t+16…t+19 with targets.py's t+20,
    after checking the helper's t+20 against targets.py's."""
    cfg, ev = ctx.cfg, ctx.split
    rows = spec.eval_sample(frame, ev, cfg)[["event_id", "session", "symbol_id", "split"]]
    ends = {str(k): v.end for k, v in load_splits().splits.items() if k == ev}
    plat = spec.plateau_rungs(ctx.daily, rows, ends, cfg).assign(event_id=rows["event_id"].to_numpy())
    both = (
        plat[["event_id", "car_lvl_c20"]]
        .merge(frame[["event_id", "car_lvl_c20"]], on="event_id", suffixes=("_helper", "_targets"))
        .dropna()
    )
    gap = float((both["car_lvl_c20_helper"] - both["car_lvl_c20_targets"]).abs().max()) if len(both) else 0.0
    if not gap < 1e-9:
        raise RunAllError(f"plateau_rungs' t+20 differs from targets.py's car_lvl_c20 by {gap}")
    lo, hi = cfg.convergence.plateau
    add = plat[["event_id", *[f"car_lvl_c{k}" for k in range(lo, hi)]]]
    pl = frame.merge(add, on="event_id", how="left", validate="one_to_one")
    pl["car_lvl_plateau"] = spec.plateau(pl, cfg)
    return pl, {"rows": len(both), "max_abs_diff_c20": gap}


def _gap_clean(ctx: Ctx, frame: pd.DataFrame, point: Literal["D1", "D2"]) -> dict[str, Any]:
    """Gap closure on clean-window events: each rung on the events clean over its own horizon."""
    cv = ctx.cfg.convergence
    out: dict[str, Any] = {}
    for rung in cv.gap[point].rungs:
        flag = cv.clean_flags.get(rung)
        sub = frame if flag is None else _with(frame, frame[flag])
        out[rung] = spec.gap_closure(sub, ctx.split, ctx.cfg, point)["rungs"].get(rung, na("rung missing"))
    return out


def _by_values(frame: pd.DataFrame, col: str, fn: Callable[[pd.DataFrame], Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if col not in frame.columns:
        return out
    for lev in sorted(str(v) for v in frame[col].dropna().unique()):
        sub = frame.loc[frame[col].astype("string") == lev]
        try:
            out[lev] = fn(sub)
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            out[lev] = {"available": False, "error": str(exc)}
    return out


def _abs_bins(
    frame: pd.DataFrame, g: str, edges: Sequence[float], fn: Callable[[pd.DataFrame], Any]
) -> dict[str, Any]:
    cuts = [0.0, *edges, math.inf]
    out: dict[str, Any] = {}
    for lo, hi in itertools.pairwise(cuts):
        a = frame[g].abs()
        sub = frame.loc[(a >= lo) & (a < hi)]
        try:
            out[f"[{lo:g}, {hi:g})"] = fn(sub)
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            out[f"[{lo:g}, {hi:g})"] = {"available": False, "error": str(exc)}
    return out


def convergence(ctx: Ctx) -> dict[str, Any]:
    """A1.4–A1.5 for the primary instrument, the anchor and d1-ultra: ladder (with clean-window, plateau and
    h* = t+10 robustness), gap closure at D2 and D1 (half-life, ψ; clean windows), tracking error, the H2-C
    tests, each by tier, quantified vs story and |G| bin."""
    cfg, ev = ctx.cfg, ctx.split
    cv = cfg.convergence
    cfg10 = cfg.model_copy(update={"convergence": cv.model_copy(update={"h_star": cv.h_star_robust})})
    edges = list(cfg.h2.abs_g_bins)
    out: dict[str, Any] = {"split": ev, "models": {}}
    for key in FOCUS:
        d0, d2 = ctx.d0[key], ctx.d2[key]
        r: dict[str, Any] = {}
        r["ladder"] = lad = spec.ladder(d0, ev, cfg)
        r["ladder_clean"] = spec.ladder(d0, ev, cfg, clean=True)
        r["ladder_h10"] = spec.ladder(d0, ev, cfg10)
        pl, check = _plateau_frame(ctx, d0)
        r["ladder_plateau"] = spec.ladder(pl, ev, cfg, rungs={"plateau": "car_lvl_plateau"})
        r["plateau_check"] = check
        r["gap_d2"] = gap2 = spec.gap_closure(d2, ev, cfg, "D2")
        r["gap_d1"] = spec.gap_closure(d0, ev, cfg, "D1")
        r["gap_d2_clean"] = _gap_clean(ctx, d2, "D2")
        r["gap_d1_clean"] = _gap_clean(ctx, d0, "D1")
        r["tracking"] = te = spec.tracking_error(d0, ev, cfg)
        r["h2c"] = spec.h2c_tests(lad, gap2, te, cfg)
        r["by_tier"] = {
            t: {
                "ladder": spec.ladder(d0.loc[d0["tier"] == t], ev, cfg),
                "gap_d2": spec.gap_closure(d2.loc[d2["tier"] == t], ev, cfg, "D2"),
                "tracking": spec.tracking_error(d0.loc[d0["tier"] == t], ev, cfg),
            }
            for t in ("top100", "mid", "rest")
        }
        quant = {"vendor_quantified": ("vendor_quantified", "vendor_quantified")}
        if model(key).full:
            quant["model_quantified"] = ("a0_label_quantified", "a2_label_quantified")
        r["by_quantified"] = {
            name: {
                "ladder": _by_values(d0, c0, lambda f: spec.ladder(f, ev, cfg)),
                "gap_d2": _by_values(d2, c2, lambda f: spec.gap_closure(f, ev, cfg, "D2")),
            }
            for name, (c0, c2) in quant.items()
        }
        r["by_abs_g"] = {
            "gap_d2": _abs_bins(d2, "g_d2", edges, lambda f: spec.gap_closure(f, ev, cfg, "D2")),
            "gap_d1": _abs_bins(d0, "g_d1", edges, lambda f: spec.gap_closure(f, ev, cfg, "D1")),
        }
        out["models"][key] = r
    ctx.cache["convergence"] = out
    return out


def _days_for(ctx: Ctx, key: str) -> tuple[pd.DataFrame, dict[str, list[str]] | None]:
    m = model(key)
    steps = ladder_steps(m, ctx.cfg, ctx.readings[key])
    if steps is None:
        return ctx.days, None
    feats = list(dict.fromkeys(f for v in steps.values() for f in v))
    dd = frames.with_day_readings(ctx.days, ctx.readings[key], feats)
    if m.full:
        lab = ctx.readings[key].set_index("event_id")["a2_label_event_type"]
        dd["a2_label_event_type"] = dd["event_id_d2"].map(lab)
    return dd, steps


def secondary(ctx: Ctx) -> dict[str, Any]:
    """H5, H6, H7, H2-C and A3.4 with BH per instrument (``SECONDARY``) and the pooled sensitivity family."""
    cfg, ev = ctx.cfg, ctx.split
    conv = ctx.cache.get("convergence") or convergence(ctx)
    out: dict[str, Any] = {"split": ev, "tests": {}, "families": {}}
    zs = ctx.d0[ZERO_SHOT][["event_id", "a0_n_hat"]].rename(columns={"a0_n_hat": "zs_n_hat"})
    for key in FOCUS:
        t: dict[str, Any] = {}
        dd, steps = _days_for(ctx, key)
        if steps is not None and answers(
            dd.loc[dd["has_d2"] == 1.0], [f for v in steps.values() for f in v], ctx.fit_splits
        ):
            t["H5"] = h5 = spec.h5(dd, cfg, steps, ev)
            ctx.cache[f"h5:{key}"] = h5
        else:
            t["H5"] = na("no ex-post (W2) reading on the fit, λ and test splits")
        d2 = ctx.d2[key]
        tone_cols = ["a2_tone", "a2_m"]
        t["H6"] = (
            spec.h6(d2, ev, cfg) if answers(d2, tone_cols, [ev]) else na("no tone or materiality (Q3–Q4)")
        )
        if key in (PRIMARY, ANCHOR):
            f = ctx.d0[key].merge(zs, on="event_id", how="left")
            t["H7"] = spec.h7(f, ev, cfg, "a0_n_hat", "zs_n_hat")
            t["H7_val_b"] = spec.h7(f, "val_b", cfg, "a0_n_hat", "zs_n_hat")
        else:
            t["H7"] = na("H7 compares a trained model with Laya zero-shot")
        t |= {k: {"p": v} for k, v in conv["models"][key]["h2c"].items()}
        ok_x = answers(d2, ["b2_x", "a2_label_event_type"], [ev])
        t["A3.4"] = spec.persistence(d2, ev, cfg, "D2") if ok_x else na("no explanation answer X (Q16)")
        out["tests"][key] = t
        fam = {name: p_of(t[name]) for name in SECONDARY[key]}
        out["families"][key] = {"tests": list(SECONDARY[key]), "p": fam, "q": spec.secondary_family(fam)}
    pooled = {f"{PRIMARY}:{n}": p_of(out["tests"][PRIMARY][n]) for n in SECONDARY[PRIMARY]}
    pooled |= {f"{API}:{n}": p_of(out["tests"][API][n]) for n in POOLED_FROM_API}
    out["families"]["pooled_sensitivity"] = {
        "tests": list(pooled),
        "p": pooled,
        "q": spec.secondary_family(pooled),
    }
    ctx.cache["secondary"] = out
    return out


def heterogeneity(ctx: Ctx) -> dict[str, Any]:
    """The eight cuts (one BH family for the primary instrument; the others reported)."""
    return {
        "split": ctx.split,
        "models": {k: spec.heterogeneity(ctx.d2[k], ctx.split, ctx.cfg) for k in FOCUS},
    }


def market_frame(ctx: Ctx) -> pd.DataFrame:
    """A3.5: one row per session with the market reading and SPY's close-to-close return."""
    r = ctx.readings[API]
    m = r.loc[r["event_id"].astype(str).str.startswith("M:"), ["event_id", "m_n_hat"]].copy()
    m["session"] = pd.to_datetime(m["event_id"].str[2:]).dt.date
    spy = ctx.daily.groupby("session")["r_spy_cc"].first().rename("r_spy_cc").reset_index()
    m = m.merge(spy, on="session", how="left")
    sp = load_splits()
    m["split"] = [sp.split_of(d) for d in m["session"]]
    return m.dropna(subset=["split"])


def explanation(ctx: Ctx) -> dict[str, Any]:
    """A3.2–A3.5: the ladder by tier, event vs non-event days and the model's event type; the explained share;
    θ at D2 and D1; persistence by move_reason; the market-level replication."""
    cfg, ev = ctx.cfg, ctx.split
    out: dict[str, Any] = {"split": ev, "roll_r2": spec.roll_r2(ctx.days, ev, cfg), "models": {}}
    for key in FOCUS:
        dd, steps = _days_for(ctx, key)
        if steps is None:
            continue
        lad = ctx.cache.get(f"h5:{key}", {}).get("ladder") or spec.explanation_ladder(dd, cfg, steps, ev)
        event = (dd["has_d0"] == 1.0) | (dd["has_d2"] == 1.0)

        def run(f: pd.DataFrame, s: dict[str, list[str]] = steps) -> dict[str, Any]:
            return spec.explanation_ladder(f, cfg, s, ev)

        r: dict[str, Any] = {
            "ladder": lad,
            "by_tier": {t: run(dd.loc[dd["tier"] == t]) for t in ("top100", "mid", "rest")},
            "event_days": run(dd.loc[event]),
            "non_event_days": run(dd.loc[~event], {k: v for k, v in steps.items() if k == "ex_ante"}),
        }
        if model(key).full:
            r["by_event_type"] = spec.by_category(dd.loc[dd["has_d2"] == 1.0], "a2_label_event_type", run)
        out["models"][key] = r
    d0, d2 = ctx.d0[API], ctx.d2[API]
    out["explained_share"] = spec.explained_share(d2, ev, cfg)
    out["theta_d2"] = spec.persistence(d2, ev, cfg, "D2")
    out["theta_d1"] = (
        spec.persistence(d0, ev, cfg, "D1")
        if answers(d0, ["b1_x", "a0_label_event_type", "g_d1", "y1"], [ev])
        else na("no D1 explanation answer")
    )
    out["persistence_by_reason"] = spec.persistence_by_reason(d2, ev, cfg)
    out["market_replication"] = spec.market_replication(market_frame(ctx), cfg)
    out["market_replication"]["exploratory"] = True
    return out


def battery(ctx: Ctx) -> dict[str, Any]:
    """A2.5: mechanism cuts (H2 at D2 and the A1 ladder by the model's own labels next to the vendor tags),
    horizon validity, the H4 width additions, and NA-06's reading-validity table."""
    cfg, ev = ctx.cfg, ctx.split
    out: dict[str, Any] = {"split": ev, "mechanism": {}}
    for key in FOCUS:
        out["mechanism"][key] = {
            "h2_d2": spec.mechanism_cuts(ctx.d2[key], ev, cfg, lambda f: spec.h2(f, ev, cfg, "D2"), "a2_"),
            "ladder": spec.mechanism_cuts(ctx.d0[key], ev, cfg, lambda f: spec.ladder(f, ev, cfg), "a0_"),
        }
    out["horizon_validity"] = spec.horizon_validity(ctx.d0[API], ev, cfg, "a0_h")
    rv = pd.read_csv(ctx.lay.root / "artifacts/NA-06/reading_validity.csv")
    rv["n_agree"] = rv["n"] * (rv["label"].astype(str) == rv["reference"].astype(str))
    agg = rv.groupby(["model", "comparison"], as_index=False)[["n", "n_agree"]].sum()
    agg["agreement"] = agg["n_agree"] / agg["n"]
    out["reading_validity_na06"] = agg.to_dict("records")
    return out


def shapley(ctx: Ctx) -> dict[str, Any]:
    """§11.5 Shapley shares (from ``spec.h3``) and the coalition predictions behind them, re-derived with the
    same ``ridge_protocol`` calls and checked to give the same tables (``work/analysis/h3_predictions``)."""
    cfg, ev = ctx.cfg, ctx.split
    out: dict[str, Any] = {"split": ev, "models": {}}
    parts = []
    for key in FOCUS:
        if f"h3:{key}" not in ctx.cache:
            continue
        groups, h3 = ctx.cache[f"h3:{key}"]
        target = cfg.h3.target
        feats = [f for g in cfg.shapley.groups for f in groups[g]]
        data = spec.add_tier_dummies(ctx.d2[key]).dropna(subset=list(dict.fromkeys([*feats, target])))
        from newsaction.analysis import shapley as sh

        s = spec.eval_sample(data, ev, cfg)
        preds = {}
        for co in sh.coalitions(cfg.shapley.groups):
            cols = [f for g, fs in groups.items() if g in co for f in fs]
            preds[co] = spec.ridge_protocol(data, cols, target, cfg).predict(s)
            s[f"pred_{sh.label(co, cfg.shapley.groups)}"] = preds[co]
        again = spec.shapley_tables(s, preds, target, cfg)
        if jsonable(again) != jsonable(h3["shapley"]):
            raise RunAllError(f"{key}: the stored predictions do not reproduce H3's Shapley table")
        out["models"][key] = {"shapley": h3["shapley"], "lambdas": h3["lambdas"], "n": len(s)}
        keep = [
            "event_id",
            "session",
            "company_id",
            "tier",
            target,
            *[c for c in s.columns if c.startswith("pred_")],
        ]
        parts.append(s[keep].assign(model=key))
    if parts and not ctx.rehearsal:
        pred = pd.concat(parts, ignore_index=True)
        io.write_parquet(
            pred,
            "analysis/h3_predictions.parquet",
            producer=CHUNK,
            description="NA-12 S2: H3's seven coalition predictions of y2 per test D2 event (ridge protocol, "
            "§11.5) for the primary instrument, the anchor and d1-ultra",
            layout=ctx.lay,
        )
    return out


def monthly_ic(ctx: Ctx) -> dict[str, Any]:
    """Figure 4: the monthly mean daily IC of N̂_W0 with z_cc per model over val-A, val-B and the evaluation
    split, with the models' release dates."""
    cfg = ctx.cfg
    catalog = json.loads((ctx.lay.root / "artifacts/NA-05/catalog.json").read_text())
    created = {m["id"]: m.get("created") for m in catalog["models"]}
    rows = []
    for m in MODELS:
        d0 = ctx.d0[m.key]
        for s in dict.fromkeys(["val_a", "val_b", ctx.split]):
            smp = spec.eval_sample(d0, s, cfg).dropna(subset=["a0_n_hat", "z_cc"])
            if smp.empty:
                continue
            daily = spec.daily(smp, "a0_n_hat", "z_cc", cfg)
            months = pd.Series(pd.to_datetime(pd.Index(daily.index)).strftime("%Y-%m"), index=daily.index)
            for mon, v in daily.groupby(months):
                rows.append(
                    {"model": m.key, "split": s, "month": mon, "ic": float(v.mean()), "n_days": len(v)}
                )
    release = {}
    for m in MODELS:
        if m.kind == "api" and created.get(m.name):
            d = datetime.fromtimestamp(int(created[m.name]), UTC).date()
            release[m.key] = {"date": str(d), "source": "NA-05 catalog created"}
        elif m.key in RELEASES:
            release[m.key] = {"date": RELEASES[m.key][0], "source": RELEASES[m.key][1]}
    write_figure(ctx, "fig4_monthly_ic", pd.DataFrame(rows))
    return {"split": ctx.split, "rows": rows, "release": release}


def _temperature(ctx: Ctx, key: str) -> dict[str, Any]:
    """H7's ECE before and after temperature fitting on Q1 (§11.2's three classes against e5 on the evaluation
    split). Trained models: T = 1 on NA-08's logits vs NA-08's val-A temperature (the files' probabilities).
    Laya zero-shot and d1-ultra: one temperature fit on val-A by NA-08's rule
    (``train.metrics.fit_temperature`` on log-probabilities against Q1's e5 level), applied to the evaluation
    split."""
    from newsaction.train.labels import react_levels
    from newsaction.train.metrics import fit_temperature, softmax

    cfg, ev = ctx.cfg, ctx.split
    d0 = ctx.d0[key]
    edges = (0.5, 1.0, 2.0, 3.0)
    ref = spec.eval_sample(d0, "val_a", cfg).dropna(subset=["e5"])
    s = spec.eval_sample(d0, ev, cfg).dropna(subset=["a0_q1", "e5"])
    if s.empty or "a0_q1" not in d0.columns:
        return na("no Q1 probabilities")
    after = np.stack(s["a0_q1"].map(np.asarray).to_list())
    if model(key).kind == "trained":
        from newsaction.train import PREDICTIONS_DIR

        (run,) = ctx.frozen.selection["trained_runs"][key]  # the seed-13 pin (§15 NA-11 row)
        runs = io.read_parquet(f"{PREDICTIONS_DIR}/runs/{run}.parquet", layout=ctx.lay)
        sel = (runs["call"] == "A") & (runs["window"] == "W0") & (runs["question_id"] == "react")
        logit_of = runs.loc[sel].drop_duplicates("event_id").set_index("event_id")["logits"]
        logits = np.stack(s["event_id"].map(logit_of).map(np.asarray).to_list())
        before = softmax(logits)
        t = float("nan")
        source = "NA-08 val-A temperature (the files' probabilities) vs T = 1 on the logits"
    else:
        r = ref.dropna(subset=["a0_q1"])
        lab = react_levels(r["e5"], edges).to_numpy(dtype=float)
        logp = np.log(np.clip(np.stack(r["a0_q1"].map(np.asarray).to_list()), 1e-12, None))
        t = fit_temperature(logp, lab.astype(int))
        before = after
        after = softmax(np.log(np.clip(before, 1e-12, None)), t)
        source = "one Q1 temperature fit on val-A (NA-08's rule), applied to the evaluation split"
    reft = ref["e5"]
    return {
        "temperature": t,
        "source": source,
        "before": spec.calibration(before, s["e5"], reft, cfg),
        "after": spec.calibration(after, s["e5"], reft, cfg),
    }


def calibration(ctx: Ctx) -> dict[str, Any]:
    """§11.2 for every decision model: Q1's three classes against e5 and z_cc (ECE, log-loss and Brier skill),
    AUC of the magnitude reading for |z_cc| >= 1, reliability bins (appendix), and H7's before / after."""
    cfg, ev = ctx.cfg, ctx.split
    out: dict[str, Any] = {"split": ev, "models": {}}
    bins = []
    for m in MODELS:
        d0 = ctx.d0[m.key]
        if "a0_q1" not in d0.columns:
            continue
        s = spec.eval_sample(d0, ev, cfg).dropna(subset=["a0_q1"])
        ref = spec.eval_sample(d0, "val_a", cfg)
        if s.empty:
            continue
        probs = np.stack(s["a0_q1"].map(np.asarray).to_list())
        r: dict[str, Any] = {}
        for target in ("e5", "z_cc"):
            ok = s[target].notna().to_numpy()
            r[target] = spec.calibration(probs[ok], s.loc[ok, target], ref[target].dropna(), cfg)
            for b in figdata.reliability(probs[ok], s.loc[ok, target], cfg):
                bins.append({"model": m.key, "target": target, **b})
        score = "a0_mag_mean" if m.kind == "trained" else "a0_abs_n_hat"
        r["auc_abs_z_ge_1"] = {"score": score, "auc": spec.auc_large(s[score], s["z_cc"], cfg)}
        if m.key in (PRIMARY, ANCHOR, ZERO_SHOT, API):
            r["temperature_h7"] = _temperature(ctx, m.key)
        out["models"][m.key] = r
    write_figure(ctx, "appendix_reliability", pd.DataFrame(bins))
    return out


def _sigma60_frames(ctx: Ctx, key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D0 and D2 frames with the σ60 columns of row t and, for y2, of row t+1 (§11.6; NA-11's smoke run)."""
    cfg = ctx.cfg
    s60 = spec.sigma60(ctx.daily, cfg)
    s60["session"] = pd.to_datetime(s60["session"]).dt.date
    nxt = s60.copy()
    nxt["session"] = nxt.groupby("symbol_id")["session"].shift(1)
    nxt = nxt.dropna(subset=["session"]).rename(columns={"s60_cc": "s60_cc_next", "s60_id": "s60_id_next"})
    out = []
    for f in (ctx.d0[key], ctx.d2[key]):
        g = f.merge(s60, on=["session", "symbol_id"], how="left", validate="many_to_one")
        g = g.merge(
            nxt[["session", "symbol_id", "s60_cc_next", "s60_id_next"]],
            on=["session", "symbol_id"],
            how="left",
            validate="many_to_one",
        )
        out.append(g)
    return out[0], out[1]


def _ablation(ctx: Ctx) -> dict[str, Any]:
    """§11.6 with d1-ultra's S8 ablations on the evaluation split: unmasked Call A D0, Call B without news,
    Call B with shuffled news, each against the same events' real readings."""
    cfg, ev = ctx.cfg, ctx.split
    ab = io.read_parquet(f"{PRODUCTION}/liquid_d1_ultra_ablations.parquet", layout=ctx.lay)
    ab = ab.loc[ab["valid"].astype(bool)]
    out: dict[str, Any] = {}
    um = ab.loc[ab["ablation"].astype(str).str.contains("unmasked")].set_index("event_id")
    d0 = ctx.d0[API]
    f = d0.loc[d0["event_id"].isin(um.index)].copy()
    f["unmasked_n_hat"] = f["event_id"].map(um["n_hat"])
    out["a0_unmasked"] = {
        "n_events": int(spec.eval_sample(f, ev, cfg)["unmasked_n_hat"].notna().sum()),
        "masked": {**spec.primary_d0(f, ev, cfg), "ic": spec.ic_targets(f, ev, cfg)},
        "unmasked": {
            **spec.primary_d0(f, ev, cfg, "unmasked_n_hat"),
            "ic": spec.ic_targets(f, ev, cfg, "unmasked_n_hat"),
        },
    }
    d2 = ctx.d2[API]
    for name in ("no_news", "shuffled"):
        b = ab.loc[ab["ablation"].astype(str).str.contains(name)].set_index("event_id")
        g = d2.loc[d2["event_id"].isin(b.index)].copy()
        r: dict[str, Any] = {"n_events": int(spec.eval_sample(g, ev, cfg)["event_id"].isin(b.index).sum())}
        for col in ("j", "c", "n_hat"):
            g[f"abl_{col}"] = g["event_id"].map(b[col])
            r[f"real_{col}"] = spec.ic(g, ev, f"b2_{col}", "y2", cfg).as_dict()
            r[f"ablated_{col}"] = spec.ic(g, ev, f"abl_{col}", "y2", cfg).as_dict()
        out[f"b2_{name}"] = r
    return out


def robustness(ctx: Ctx) -> dict[str, Any]:
    """§11.6 and the operator rows' (a)–(b): every ``spec.robustness`` variant at D0 (H1, H1b, ICs) and D2
    (H2), raw and placebo-adjusted; σ60; 2024-H1; d1-ultra's ablations; the items not run."""
    cfg, ev = ctx.cfg, ctx.split
    means = spec.placebo_means(ctx.days, list(PLACEBO_TARGETS))
    out: dict[str, Any] = {"split": ev, "models": {}}
    for key in FOCUS:
        d0, d2 = ctx.d0[key], ctx.d2[key]
        a0 = spec.placebo_adjust(d0, means, ["z_on", "z_id", "z_cc"])
        a2 = spec.placebo_adjust(d2, means, ["y2"])
        s0, s2 = _sigma60_frames(ctx, key)
        r: dict[str, Any] = {
            "variants_d0_raw": spec.robustness(d0, ev, cfg, ctx.sessions, "D0"),
            "variants_d0_placebo": spec.robustness(a0, ev, cfg, ctx.sessions, "D0"),
            "variants_d2_raw": spec.robustness(d2, ev, cfg, ctx.sessions, "D2"),
            "variants_d2_placebo": spec.robustness(a2, ev, cfg, ctx.sessions, "D2"),
            "placebo_adjusted": {**spec.primary_d0(a0, ev, cfg), "H2": spec.h2(a2, ev, cfg, "D2")},
            "sigma60": {
                **spec.primary_d0(spec.sigma60_rescale(s0), ev, cfg),
                "H2": spec.h2(spec.sigma60_rescale(s2), ev, cfg, "D2"),
            },
        }
        if answers(d0, ["a0_n_hat"], ["robustness"]):
            r["h1_2024h1_raw"] = {
                **spec.primary_d0(d0, "robustness", cfg),
                "ic": spec.ic_targets(d0, "robustness", cfg),
            }
            r["h1_2024h1_placebo"] = spec.primary_d0(a0, "robustness", cfg)
        if answers(d2, ["a2_n_hat"], ["robustness"]):
            r["h2_2024h1_raw"] = spec.h2(d2, "robustness", cfg, "D2")
            r["h2_2024h1_placebo"] = spec.h2(a2, "robustness", cfg, "D2")
        out["models"][key] = r
    out["ablations_d1_ultra"] = _ablation(ctx)
    out["not_run"] = {
        "summary_text_variant": "§15 NA-11 row: needs new state builds and calls; not run (operator)",
        "vendor_tags_in_text": "§15 NA-11 row: needs new state builds and calls; not run (operator)",
        "w0_cutoff_09:30": "§15 NA-11 row: needs new states; not run (operator); 08:00 approximated",
        "gated_s_d1": "§15 NA-11 row (vii): no frozen gate; not run",
        "unmasked_trained_models": "the trained models' unmasked and shuffled probes are val-A only (NA-11)",
    }
    return out


def _baseline_frame(ctx: Ctx) -> tuple[pd.DataFrame, list[str]]:
    """The primary's D0 frame with each baseline's N_hat as ``bl_<name>`` (and the price-only D0 reading)."""
    f = ctx.d0[PRIMARY].copy()
    names = []
    for name, (rel, test_rel) in BASELINES.items():
        parts = [io.read_parquet(rel, columns=["event_id", "call", "N_hat"], layout=ctx.lay)]
        if test_rel and not ctx.rehearsal:
            parts.append(io.read_parquet(test_rel, columns=["event_id", "call", "N_hat"], layout=ctx.lay))
        b = pd.concat(parts, ignore_index=True)
        n_hat = b.loc[b["call"] == "A"].drop_duplicates("event_id").set_index("event_id")["N_hat"]
        f[f"bl_{name}"] = f["event_id"].map(n_hat)
        names.append(f"bl_{name}")
    f["bl_price_only"] = f["po_n_hat"]
    return f, [*names, "bl_price_only"]


def comparison(ctx: Ctx) -> dict[str, Any]:
    """The model comparison: val-B and test IC of N̂_W0 with z_cc (own events and the events every decision
    model answered), cost per 1,000 decisions and latency; the baselines' ICs, H1 and H1b; the price-only
    D2 reading's IC with y2; Laya-Fin on the LLM baseline's test subsample."""
    cfg, ev = ctx.cfg, ctx.split
    summ = pd.read_csv(ctx.lay.root / "artifacts/NA-11/production_summary.csv")
    common = None
    for m in MODELS:
        ids = set(spec.eval_sample(ctx.d0[m.key], ev, cfg).dropna(subset=["a0_n_hat"])["event_id"])
        common = ids if common is None else common & ids
    rows = []
    for m in MODELS:
        d0 = ctx.d0[m.key]
        row: dict[str, Any] = {"model": m.key, "name": m.name, "role": m.role, "footnote": m.footnote}
        for s in ("val_b", ev):
            if answers(d0, ["a0_n_hat"], [s]):
                row[f"ic_{s}"] = spec.ic(d0, s, "a0_n_hat", "z_cc", cfg).as_dict()
        sub = d0.loc[d0["event_id"].isin(common or set())]
        row["ic_common"] = spec.ic(sub, ev, "a0_n_hat", "z_cc", cfg).as_dict() if common else None
        sm = summ.loc[
            (summ["model"].isin([m.name, m.key])) & (summ["source"] == "a0") & (summ["split"] == "test")
        ]
        if len(sm):
            x = sm.iloc[0]
            row["cost_per_1000"] = (
                float(x["cost_usd"]) / float(x["answered"]) * 1000 if x["answered"] else None
            )
            row["latency_p50_ms"] = None if pd.isna(x["latency_p50_ms"]) else float(x["latency_p50_ms"])
            row["latency_p95_ms"] = None if pd.isna(x["latency_p95_ms"]) else float(x["latency_p95_ms"])
            row["coverage"] = float(x["coverage"])
        rows.append(row)
    f, names = _baseline_frame(ctx)
    base_rows = []
    for name in names:
        r: dict[str, Any] = {"baseline": name.removeprefix("bl_")}
        for s in ("val_b", ev):
            if answers(f, [name], [s]):
                r[f"ic_{s}"] = spec.ic(f, s, name, "z_cc", cfg).as_dict()
        if answers(f, [name], [ev]):
            r |= {
                "primary_d0": spec.primary_d0(f, ev, cfg, name),
                "ic_targets": spec.ic_targets(f, ev, cfg, name),
            }
        base_rows.append(r)
    llm_ids = set(f.loc[f["bl_llm"].notna() & (f["split"] == ev), "event_id"])
    sub = f.loc[f["event_id"].isin(llm_ids)]
    llm_pair = {
        "n_events": len(llm_ids),
        "laya_fin": spec.ic(sub, ev, "a0_n_hat", "z_cc", cfg).as_dict() if llm_ids else None,
        "llm": spec.ic(sub, ev, "bl_llm", "z_cc", cfg).as_dict() if llm_ids else None,
    }
    po_d2: dict[str, Any] = na("the price-only D2 test predictions run after unblinding")
    if not ctx.rehearsal:
        po = io.read_parquet(
            "analysis/price_only_d2_test.parquet", columns=["event_id", "y_hat"], layout=ctx.lay
        )
        g = ctx.d2[PRIMARY].merge(po, on="event_id", how="left")
        po_d2 = {"ic_y2": spec.ic(g, ev, "y_hat", "y2", cfg).as_dict(), "n_predictions": len(po)}
    return {
        "split": ev,
        "n_common_events": len(common or set()),
        "models": rows,
        "baselines": base_rows,
        "llm_subsample": llm_pair,
        "price_only_d2": po_d2,
        "probes_val_a": pd.read_csv(ctx.lay.root / "artifacts/NA-11/probes_val_a.csv").to_dict("records"),
    }


def figures(ctx: Ctx) -> dict[str, Any]:
    """Figure 1 (V-decile and RG-class CAR^lvl paths, the day-t 30-minute path) and Figure 2 (drift vs |G| by
    news-strength terciles); Figures 4–5 and 8 come from their sections."""
    cfg, ev = ctx.cfg, ctx.split
    ends = {str(k): v.end for k, v in load_splits().splits.items() if k == ev}
    fig1, fig2, fig1_rg = [], [], []
    for key in FOCUS:
        d0 = spec.eval_sample(ctx.d0[key], ev, cfg).dropna(subset=["a0_v"])
        p0 = figdata.event_paths(ctx.daily, d0[["event_id", "session", "symbol_id", "split"]], ends, cfg)
        f0 = d0.merge(p0[["event_id", *figdata.PATH_COLUMNS]], on="event_id", how="left")
        f0["v_decile"] = figdata.deciles(f0["a0_v"])
        cols = [*figdata.PATH_COLUMNS, *[c for c in figdata.SLOT_POINTS if c in f0.columns]]
        fig1 += [{"model": key, **r} for r in figdata.group_paths(f0, "v_decile", "a0_v", cols, "v_decile")]
        d2 = spec.eval_sample(ctx.d2[key], ev, cfg).dropna(subset=["a2_n_hat", "g_d2"])
        p2 = figdata.event_paths(ctx.daily, d2[["event_id", "session", "symbol_id", "split"]], ends, cfg)
        f2 = d2.merge(p2[["event_id", *figdata.PATH_COLUMNS]], on="event_id", how="left")
        rg = ctx.frozen.thresholds["rg"]  # PREREG §7 RG (configs/frozen.yaml thresholds.rg)
        f2["rg"] = spec.rg_class(f2["a2_n_hat"], f2["g_d2"], rg["min_abs_n_hat"], rg["band"])
        fig1_rg += [
            {"model": key, **r}
            for r in figdata.group_paths(f2, "rg", "a2_v", list(figdata.PATH_COLUMNS), "rg_class")
        ]
        fig2 += [{"model": key, **r} for r in figdata.drift_by_g(f2, "g_d2", "y2", "a2_v", "drift_vs_g")]
    write_figure(ctx, "fig1_v_decile_paths", pd.DataFrame(fig1))
    write_figure(ctx, "fig1_rg_class_paths", pd.DataFrame(fig1_rg))
    write_figure(ctx, "fig2_drift_vs_g", pd.DataFrame(fig2))
    sh_rows = []
    for key, r in ctx.cache.get("shapley", {}).get("models", {}).items():
        for part, row in r["shapley"].items():
            for metric in ("r2", "ic"):
                for grp, share in row[metric]["shares"].items():
                    value = row[metric]["shapley"][grp]
                    sh_rows.append(
                        {"model": key, "tier": part, "metric": metric, "group": grp, "share": share,
                         "value": value, "n": row["n"]}
                    )  # fmt: skip
    write_figure(ctx, "fig5_shapley_shares", pd.DataFrame(sh_rows))
    lad_rows = []
    for key in FOCUS:
        h5 = ctx.cache.get(f"h5:{key}")
        if not h5:
            continue
        for step, row in h5["ladder"]["steps"].items():
            lad_rows.append({"model": key, "step": step, "r2": row["value"], "ci_low": row["ci_low"],
                             "ci_high": row["ci_high"], "p": row["p"]})  # fmt: skip
    write_figure(ctx, "fig8_explanation_ladder", pd.DataFrame(lad_rows))
    return {"split": ev, "files": sorted(p.name for p in figure_dir(ctx).glob("*.csv"))}


SECTIONS: Final[dict[str, Callable[[Ctx], dict[str, Any]]]] = {
    "primary": primary,
    "convergence": convergence,
    "secondary": secondary,
    "heterogeneity": heterogeneity,
    "explanation": explanation,
    "battery": battery,
    "shapley": shapley,
    "monthly_ic": monthly_ic,
    "calibration": calibration,
    "robustness": robustness,
    "comparison": comparison,
    "figures": figures,
}


# --- output -------------------------------------------------------------------------------------------------


def out_dir(ctx: Ctx) -> Path:
    path = ctx.out_root / RESULTS
    path.mkdir(parents=True, exist_ok=True)
    return path


def figure_dir(ctx: Ctx) -> Path:
    path = ctx.out_root / FIGURES
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_figure(ctx: Ctx, name: str, df: pd.DataFrame) -> None:
    df.to_csv(figure_dir(ctx) / f"{name}.csv", index=False, float_format="%.10g")


def write_frames(ctx: Ctx) -> list[str]:
    """The analysis frames of the primary instrument, the anchor and d1-ultra (evaluation, fit and λ splits),
    for the verifier's recomputation (PRD NA-12 verification 3 and 4b)."""
    done = []
    for key in FOCUS:
        for point, f in (("d0", ctx.d0[key]), ("d2", ctx.d2[key])):
            keep = [c for c in f.columns if not c.endswith("q1")]
            sub = f.loc[f["split"].isin(ctx.fit_splits), keep].reset_index(drop=True)
            for c in sub.columns:
                if sub[c].dtype == object and sub[c].map(lambda v: isinstance(v, list | np.ndarray)).any():
                    sub = sub.drop(columns=[c])
            rel = f"analysis/frame_{point}_{key}.parquet"
            io.write_parquet(
                sub,
                rel,
                producer=CHUNK,
                description=f"NA-12 S2: the {point.upper()} analysis frame of {key} (val-A, val-B, test): "
                "events, test outcomes from targets_test, readings, V and Ñ from the frozen maps",
                layout=ctx.lay,
            )
            done.append(rel)
    return done


def run(
    sections: Sequence[str] | None = None,
    *,
    rehearsal: bool = False,
    out_root: Path | None = None,
    layout: Layout | None = None,
) -> dict[str, Any]:
    """Run ``sections`` (all by default). A rehearsal needs ``out_root`` outside the repository's artifacts:
    its val-B numbers are a code check, never read as results."""
    lay = resolve_layout(layout)
    if rehearsal and (out_root is None or lay.root in out_root.resolve().parents):
        raise RunAllError("a rehearsal writes outside the repository (pass --out <dir>)")
    if not rehearsal and not (lay.work / frames.TARGETS_TEST).exists():
        raise RunAllError("the test analysis follows the unblinding (work/analysis/targets_test.parquet)")
    if not rehearsal and not (lay.work / "analysis/price_only_d2_test.parquet").exists():
        raise RunAllError("the price-only D2 test predictions come first (operator preamble NA-12, item 4)")
    t0 = time.time()
    ctx = build_ctx(lay, rehearsal=rehearsal, out_root=out_root)
    names = list(sections or SECTIONS)
    timings: dict[str, float] = {"build": round(time.time() - t0, 1)}
    for name in names:
        s = time.time()
        res = SECTIONS[name](ctx)
        ctx.cache[name] = res
        (out_dir(ctx) / f"{name}.json").write_text(
            json.dumps(jsonable(res), indent=1) + "\n", encoding="utf-8"
        )
        timings[name] = round(time.time() - s, 1)
    if not rehearsal and set(names) == set(SECTIONS):
        timings["frames"] = len(write_frames(ctx))
    return {"split": ctx.split, "rehearsal": rehearsal, "seconds": timings}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    rehearsal = "--rehearse" in args
    out_root = Path(args[args.index("--out") + 1]) if "--out" in args else None
    names = [a for a in args if not a.startswith("--") and (out_root is None or a != str(out_root))]
    unknown = [n for n in names if n not in SECTIONS]
    if unknown:
        print(f"unknown sections {unknown}; choose from {list(SECTIONS)}", file=sys.stderr)
        return 2
    print(json.dumps(run(names or None, rehearsal=rehearsal, out_root=out_root), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
