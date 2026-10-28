"""The pre-registered analysis specification (PREREG §1, §11, A1.3–A1.6, A2.4–A2.5, A3.2–A3.5; PREREG §15 rows
"operator, before NA-11" and NA-11). **Hash-locked at the NA-11 freeze** (PREREG §4.4, with ``inference.py``,
``shapley.py``, ``metrics.py`` and ``configs/*.yaml``); NA-12 calls these functions verbatim on the test
split.

Every function is pure: it takes analysis frames, a split name and the frozen configuration, and returns
numbers. Nothing here reads a file, so nothing here can reach a blinded target; the caller builds the frames
(``analysis.frames`` for the public splits; NA-12 after unblinding for the test split).

**Frames.** One row per event, with the event's keys (``event_id``, ``company_id``, ``session``, ``split``,
``embargo``, ``tier``, ``dv_tier``, ``sector``, ``half_day``), the model's readings and the targets:
- readings carry the prefix of their source: ``a0_`` Call A on W0 news (D0), ``a2_`` Call A on W2 news (D2,
  A3.1), ``b2_`` Call B at D2, ``b1_`` Call B at D1, ``m_`` the A3.5 market state. Names follow ``dm.parse``:
  ``n_hat``, ``abs_n_hat``, ``m``, ``surprise``, ``tone``, ``j``, ``w``, ``c``, ``h``,
  ``p_no_material_effect``,
  ``u_unc``, ``x``, ``label_event_type``, ``label_quantified``, ``label_move_reason``; trained models add
  ``mag_mean``; ``v`` (A1.3) and ``n_tilde`` (§7) come from the frozen val-A maps (``add_calibrated``);
- targets and reactions use the names of ``panel/targets.py`` and ``panel/reactions.py`` (``z_cc``, ``z_on``,
  ``z_id``, ``y2``, ``y1``, ``e5``, ``e5_lvl``, ``car_lvl_*``, ``fwd_lvl_*``, ``g_d2``, ``g_d2_lvl``,
  ``g_d1``,
  ``g_d1_lvl``), plus ``z_vol``, ``z_m5``/``z_m20``/``z_m60`` (t−1) and ``har_d``/``har_w``/``har_m``
  (``har_features``);
- event attributes: ``vendor_quantified``, ``vendor_event_type`` and ``press_wire`` (the state's first news
  item), ``attention_mean`` / ``attention_ratio`` (NA-03's W0 window counts, operator row (7)–(8), for D0 and
  D2 events alike), ``earnings``, ``imprecise`` (a date-only or hour-stamped article in the state),
  ``latest_et`` (ET minutes after midnight of the session of the state's latest article, negative before
  midnight), ``price_move_text`` (operator row (a)), ``clean_1``…``clean_20`` and ``delist_within_c20``.

**Sample** (``eval_sample``): the rows of the split outside the embargo (§4.2); purged targets are NaN
(§4.1) and drop out of each analysis that needs them.

**Primary (§1.1 and H1b, Holm at 0.05 over H1, H1b, H2, H3, H4).**
- **H1** (``h1``): D0 events. Daily IC(N̂_W0, z_on) − daily IC(N̂_W0, z_id) on the sessions with both; H1:
  mean > 0; stationary block bootstrap over sessions (centred one-sided p, ``metrics``).
- **H1b** (``h1b``; PREREG §15 NA-11 row): D0 events. Mean daily IC(N̂_W0, z_id) > 0 (not fully priced at
  the open), on H1's sample and bootstrap draws. ``primary_d0`` runs H1 and H1b together, and every
  robustness re-run of H1 re-runs H1b (``robustness``).
- **H2** (``h2``): y = a + b·N̂ + c·G + day × tier FE (``inference.ols_fe``), two-way clustered (session,
  company). D2 is primary (y = y2, G = z_cc,t, N̂ from Call A on W2 news since anchoring is present, §8.4);
  D1 (y1, G_D1, N̂_W0) and D0 (y0 = z_id, no G) are reported. H2's p is the intersection–union p
  max(p_b, p_c) of the one-sided tests b > 0 and c < 0: H2 holds only if both do.
- **H3** (``h3``): ridge with the §11.5 protocol on the 7 coalitions of {R, N, J} at D2 (target y2);
  ΔIC = mean daily IC(R+N+J) − IC(R+N) on the evaluation split; H1: ΔIC > 0, paired day bootstrap.
  Exact Shapley shares of OOS R² and of IC, pooled and by tier (``shapley``).
- **H4** (``h4``): D0 events, target |z_cc,t|. Benchmark: HAR (|z_cc| of t−1, means over t−5..t−1 and
  t−22..t−1), the earnings flag and tier; full: plus the model's materiality, surprise and E|N̂| (trained
  models:
  E|N̂| and the H-mag expected level). ΔR² = Σ(SSE_bench − SSE_full) / Σ(y − ȳ_fit)², ȳ_fit the fit split's
  mean; H1: ΔR² > 0, day bootstrap of the per-session sums. A2.5 adds U_unc and P(no_material_effect).
- **Ridge protocol** (§11.5; PREREG §15 NA-11 row): features z-scored with the fit split's moments, intercept
  unpenalized; fit on val-B; λ is the grid value whose val-B fit has the lowest mean squared error on val-A
  (ties to the larger λ); predictions on the evaluation split. Rows missing a feature of the coalition's
  full feature set are left out, so every coalition of an analysis uses the same rows.
- **Headline rule** (§1.3, ``headline``): "general" iff the primary instrument's Holm-adjusted p < 0.05 and
  the
  anchor's estimate has the same sign with p < 0.05 (pooled); "model-specific" iff only the primary's holds;
  else "not supported".

**Secondary (§1.2, A1.4, A3.4; BH at q = 0.10).** H5 (OOS R² of the ex-post news step > 0), H6 (tone ×
sign(N̂) < 0 in the augmented H2), H7 (ΔIC trained − zero-shot > 0 on common D0 events), H2-C (κ_{h*} > 0;
κ_{h*} − κ_{O_t} > 0; λ_{t+5} > 0 at D2; tracking-error ratio vs the naive benchmark < 1 at h*) and A3.4
(θ > 0 at D2). The heterogeneity cuts form their own BH family (operator row: one family of <= 8 cuts):
for each cut, the Wald F of (N̂·1[cut], G·1[cut]) = 0 in H2 at D2.

**Convergence (A1.3–A1.5).** ``ladder``: CAR^lvl_h = α_h + κ_h·V + day × tier FE for the rungs O_t, 10:00,
C_t … C_{t+20} on D0 events (V from W0 news); shares κ_h/κ_{h*}. ``gap_closure``: AR(τ→h)/σ_cc = a +
λ_h·U_τ + ψ_h·V with U_τ = V − G^lvl_τ at τ = D2 (V from W2 news) and D1 (V from W0 news); the half-life is
the first rung with λ_h >= 0.5, its bootstrap distribution over rungs gives the CI ("never" = beyond t+20).
``tracking_error``: RMSE(CAR^lvl_h − V) over RMSE of the naive 0 and of the price-only value.

**Exploratory, outside every family**: sector ICs and leave-one-sector-out (operator row), A3.5.
"""

from __future__ import annotations

import functools
import itertools
import json
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from pydantic import BaseModel, ConfigDict

from newsaction.analysis import inference as inf
from newsaction.analysis import metrics as mx
from newsaction.analysis import shapley as sh
from newsaction.config import load_yaml
from newsaction.paths import CONFIGS

FloatArray = npt.NDArray[np.float64]
Point = Literal["D0", "D1", "D2"]
ANALYSIS_CONFIG: Final = CONFIGS / "analysis.yaml"
TIER_DUMMIES: Final = {"tier_top100": "top100", "tier_mid": "mid"}
NEVER: Final = math.inf


# --- configuration -----------------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SampleCfg(_Strict):
    embargo: bool
    min_names_per_day: int
    constant_day_ic: float


class MetricsCfg(_Strict):
    nw_lags: int
    quintiles: int
    class_band: float
    ece_bins: int
    auc_abs_z: float
    q1_large_levels: tuple[int, ...]


class BootCfg(_Strict):
    block: float
    reps: int
    seed: int
    ci: float


class InferenceCfg(_Strict):
    fe: tuple[str, ...]
    cluster: tuple[str, str]
    dk_lags: int


class FamilyCfg(_Strict):
    method: Literal["holm", "bh"]
    alpha: float | None = None
    q: float | None = None
    tests: tuple[str, ...] = ()


class MultipleCfg(_Strict):
    primary: FamilyCfg
    secondary: FamilyCfg
    heterogeneity: FamilyCfg


class H1Cfg(_Strict):
    signal: str
    gap: str
    after_open: str


class H1bCfg(_Strict):
    signal: str
    target: str


class PointCfg(_Strict):
    y: str
    g: str | None
    n_hat: str


class H2Cfg(_Strict):
    primary_point: Point
    points: dict[Point, PointCfg]
    abs_g_bins: tuple[float, ...]


class H3Cfg(_Strict):
    point: Point
    target: str


class H4Cfg(_Strict):
    target: str
    har_lags: tuple[int, int, int]
    har_min_obs: tuple[int, int, int]
    r2_mean: Literal["fit"]


class GroupsCfg(_Strict):
    R: tuple[str, ...]
    N: tuple[str, ...]
    J: tuple[str, ...]
    N_trained: tuple[str, ...]
    J_trained: tuple[str, ...]
    h4_bench: tuple[str, ...]
    h4_news: tuple[str, ...]
    h4_news_trained: tuple[str, ...]
    h4_a2: tuple[str, ...]


class RidgeCfg(_Strict):
    fit_split: str
    lambda_split: str
    lambdas: tuple[float, ...]
    standardize: bool
    eval_split: str


class ShapleyCfg(_Strict):
    groups: tuple[str, ...]


class GapCfg(_Strict):
    value: str
    g_lvl: str
    rungs: dict[str, str]


class ConvergenceCfg(_Strict):
    value: str
    ladder: dict[str, str]
    exploratory_rungs: dict[str, str]
    h_star: str
    h_short: str
    h_star_robust: str
    plateau: tuple[int, int]
    gap: dict[Point, GapCfg]
    rung_sessions: dict[str, int]
    half_life_lambda: float
    clean_flags: dict[str, str]
    benchmarks: tuple[str, ...]


class CutCfg(_Strict):
    column: str
    equals: str | bool | None = None
    below: float | None = None
    at_least: float | None = None
    below_median_by: tuple[str, ...] | None = None


class CutsCfg(_Strict):
    statistic: Literal["h2_interaction"]
    list: dict[str, CutCfg]


class MechanismCfg(_Strict):
    model_labels: tuple[str, ...]
    vendor: tuple[str, ...]


class HorizonCfg(_Strict):
    min_abs_car20: float


class PersistCfg(_Strict):
    y: str
    g: str
    x: str
    n_hat: str
    event_type: str


class ExplanationCfg(_Strict):
    explained_x: float
    ladder_target: str
    ladder_steps: dict[str, tuple[str, ...]]
    ladder_steps_trained: dict[str, tuple[str, ...]]
    persistence: dict[Point, PersistCfg]


class MarketCfg(_Strict):
    fit_splits: tuple[str, ...]
    eval_split: str
    target: str
    features: tuple[str, ...]


class SectorCfg(_Strict):
    signal: str
    targets: tuple[str, ...]


class Sigma60Cfg(_Strict):
    window: int
    min_obs: int


class RobustnessCfg(_Strict):
    date_only_hour_precision: tuple[str, ...]
    non_overlap_sessions: int
    sigma60: Sigma60Cfg
    timing_strata_et: tuple[str, str, str]
    cutoff_approx_et: str
    price_move_text: str
    live_format: str


class AnalysisConfig(_Strict):
    version: int
    sample: SampleCfg
    metrics: MetricsCfg
    bootstrap: BootCfg
    inference: InferenceCfg
    multiple_testing: MultipleCfg
    h1: H1Cfg
    h1b: H1bCfg
    h2: H2Cfg
    h3: H3Cfg
    h4: H4Cfg
    groups: GroupsCfg
    ridge: RidgeCfg
    shapley: ShapleyCfg
    convergence: ConvergenceCfg
    cuts: CutsCfg
    mechanism: MechanismCfg
    horizon_validity: HorizonCfg
    explanation: ExplanationCfg
    market: MarketCfg
    sector: SectorCfg
    robustness: RobustnessCfg


@functools.cache
def _load(path: Path, mtime_ns: int) -> AnalysisConfig:
    return AnalysisConfig.model_validate(load_yaml(path))


def load_config(path: Path = ANALYSIS_CONFIG) -> AnalysisConfig:
    return _load(path, path.stat().st_mtime_ns)


# --- sample, bootstrap, small helpers ---------------------------------------------------------------------


def eval_sample(frame: pd.DataFrame, split: str, cfg: AnalysisConfig) -> pd.DataFrame:
    """The rows of ``split`` outside the embargo (§4.1–4.2)."""
    keep = frame["split"] == split
    if cfg.sample.embargo and "embargo" in frame.columns:
        keep &= ~frame["embargo"].fillna(False).astype(bool)
    return frame.loc[keep].copy()


def bootstrap_for(sample: pd.DataFrame, cfg: AnalysisConfig) -> mx.Bootstrap:
    """The §11.4 draws on the sample's session grid (one seed for every analysis: common random numbers)."""
    b = cfg.bootstrap
    return mx.Bootstrap.draw(sample["session"].unique().tolist(), b.reps, b.block, b.seed)


def _need(frame: pd.DataFrame, cols: Sequence[str]) -> None:
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise KeyError(f"the analysis frame lacks {missing}")


def _complete(frame: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    _need(frame, cols)
    return frame.dropna(subset=list(dict.fromkeys(cols))).copy()


def add_tier_dummies(frame: pd.DataFrame, tier: str = "tier") -> pd.DataFrame:
    out = frame.copy()
    for col, value in TIER_DUMMIES.items():
        out[col] = (out[tier] == value).astype(float).where(out[tier].notna())
    return out


def daily(sample: pd.DataFrame, signal: str, target: str, cfg: AnalysisConfig) -> pd.Series:
    return mx.daily_ic(sample, signal, target, cfg.sample.min_names_per_day)


def ic(
    frame: pd.DataFrame,
    split: str,
    signal: str,
    target: str,
    cfg: AnalysisConfig,
    alternative: mx.Alternative = "greater",
) -> mx.Estimate:
    """Mean daily IC (§11.1) of ``signal`` with ``target`` on the split's sample, NW t and bootstrap CI."""
    s = _complete(eval_sample(frame, split, cfg), [signal, target])
    boot = bootstrap_for(s, cfg)
    return mx.daily_mean_estimate(
        daily(s, signal, target, cfg), boot, cfg.metrics.nw_lags, cfg.bootstrap.ci, alternative, len(s)
    )


def _reg(sample: pd.DataFrame, y: str, x: Sequence[str], cfg: AnalysisConfig) -> inf.OLSResult:
    ic_ = cfg.inference
    return inf.ols_fe(
        sample, y, list(x), fe=list(ic_.fe), cluster=ic_.cluster, time="session", dk_lags=ic_.dk_lags
    )


def _coef_row(
    res: inf.OLSResult, name: str, label: str, alternative: mx.Alternative | None
) -> dict[str, Any]:
    i = res.names.index(name)
    row = {
        f"{label}": float(res.params[i]),
        f"{label}_se": float(res.se("cluster")[i]),
        f"{label}_t": float(res.t("cluster")[i]),
        f"{label}_se_dk": float(res.se("dk")[i]),
        f"{label}_p_two": float(res.p_two("cluster")[i]),
    }
    if alternative is not None:
        row[f"{label}_p"] = float(res.p_one(name, alternative, "cluster"))
        row[f"{label}_p_dk"] = float(res.p_one(name, alternative, "dk"))
    return row


def _sign(x: pd.Series) -> pd.Series:
    return pd.Series(np.sign(x.to_numpy(dtype=float)), index=x.index)


# --- calibrated readings (§7, A1.3) -----------------------------------------------------------------------


def add_calibrated(frame: pd.DataFrame, maps: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """``<p>v`` and ``<p>n_tilde`` for each source prefix ``p`` with frozen val-A maps.

    ``maps``: {prefix: {"v": {x, y}, "n_tilde": {x, y}}} of one model (``configs/frozen.yaml``
    calibration)."""
    out = frame.copy()
    for prefix, m in maps.items():
        col = f"{prefix}n_hat"
        if col not in out.columns:
            continue
        for name in ("v", "n_tilde"):
            if name in m:
                out[f"{prefix}{name}"] = mx.apply_map(out[col].to_numpy(dtype=float), m[name])
    return out


def rg_class(n_hat: npt.ArrayLike, g: npt.ArrayLike, min_abs: float, band: float) -> npt.NDArray[np.object_]:
    """PREREG §7 RG classes: Under (RG > band), Over (RG < −band), Fair; None where |N̂| < min_abs."""
    n = np.asarray(n_hat, dtype=float)
    gg = np.asarray(g, dtype=float)
    rg = (n - gg) * np.sign(n)
    out = np.where(rg > band, "Under", np.where(rg < -band, "Over", "Fair")).astype(object)
    out[~(np.isfinite(n) & np.isfinite(gg)) | (np.abs(n) < min_abs)] = None
    return out


# --- frozen helpers on the daily panel (HAR, σ60, plateau) -------------------------------------------------


def _by_symbol(daily_panel: pd.DataFrame, col: str) -> pd.DataFrame:
    d = daily_panel[["session", "symbol_id", col]].copy()
    d["session"] = pd.to_datetime(d["session"])
    return d.pivot_table(index="session", columns="symbol_id", values=col, aggfunc="first").sort_index()


def har_features(daily_panel: pd.DataFrame, cfg: AnalysisConfig) -> pd.DataFrame:
    """HAR inputs of H4 from data through t−1: |z_cc| of the previous session, and the means of |z_cc| over
    the
    previous 5 and 22 sessions (at least 1 / 4 / 16 values present). Rows: (session, symbol_id)."""
    lags, mins = cfg.h4.har_lags, cfg.h4.har_min_obs
    a = _by_symbol(daily_panel, "z_cc").abs().shift(1)
    out = {
        "har_d": a.rolling(lags[0], min_periods=mins[0]).mean(),
        "har_w": a.rolling(lags[1], min_periods=mins[1]).mean(),
        "har_m": a.rolling(lags[2], min_periods=mins[2]).mean(),
    }
    long = pd.concat({k: v.stack() for k, v in out.items()}, axis=1).reset_index()
    long.columns = ["session", "symbol_id", *out.keys()]
    long["session"] = long["session"].dt.date
    return long


def sigma60(daily_panel: pd.DataFrame, cfg: AnalysisConfig) -> pd.DataFrame:
    """§11.6 robustness: the standard deviation of AR_cc, AR_on and AR_id over the 60 rows ending t−1 (at
    least ``min_obs``). Rows: (session, symbol_id) with ``s60_cc``, ``s60_on``, ``s60_id``."""
    w, m = cfg.robustness.sigma60.window, cfg.robustness.sigma60.min_obs
    parts = {}
    for name in ("cc", "on", "id"):
        g = _by_symbol(daily_panel, f"ar_{name}")
        parts[f"s60_{name}"] = g.shift(1).rolling(w, min_periods=m).std(ddof=1)
    long = pd.concat({k: v.stack() for k, v in parts.items()}, axis=1).reset_index()
    long.columns = ["session", "symbol_id", *parts.keys()]
    long["session"] = long["session"].dt.date
    return long


def sigma60_rescale(frame: pd.DataFrame) -> pd.DataFrame:
    """Rescale the H1/H2 z's with the σ60 columns of the same row (t) and, for y2, of row t+1
    (``s60_*_next``):
    z_on, z_id, z_cc and G = AR_x / σ60_x (clipped at ±10 like the same-day z); y2 = ar_o1_c5 /
    (σ60_id,t+1² + 4·σ60_cc,t+1²)^½ (unclipped, as y2)."""
    _need(
        frame,
        ["ar_on", "ar_id", "ar_cc", "ar_o1_c5", "s60_cc", "s60_on", "s60_id", "s60_cc_next", "s60_id_next"],
    )
    out = frame.copy()
    out["z_on"] = (out["ar_on"] / out["s60_on"]).clip(-10, 10)
    out["z_id"] = (out["ar_id"] / out["s60_id"]).clip(-10, 10)
    out["z_cc"] = (out["ar_cc"] / out["s60_cc"]).clip(-10, 10)
    out["g_d2"] = out["z_cc"]
    out["y2"] = out["ar_o1_c5"] / np.sqrt(out["s60_id_next"] ** 2 + 4 * out["s60_cc_next"] ** 2)
    return out


def plateau(frame: pd.DataFrame, cfg: AnalysisConfig) -> pd.Series:
    """A1.5 plateau equilibrium: the mean of CAR^lvl over t+k for k in the configured range (``car_lvl_c<k>``
    columns, purged like every rung: NaN if any is missing)."""
    lo, hi = cfg.convergence.plateau
    cols = [f"car_lvl_c{k}" for k in range(lo, hi + 1)]
    _need(frame, cols)
    return frame[cols].mean(axis=1, skipna=False)


def plateau_rungs(
    daily_panel: pd.DataFrame, rows: pd.DataFrame, split_end: Mapping[str, date], cfg: AnalysisConfig
) -> pd.DataFrame:
    """CAR^lvl_{t+k} = Σ_{j=0..k} AR_cc,t+j / σ_cc,t for the plateau's k (A1.2 level units, no √h), on the
    ``rows`` (session, symbol_id, split); NaN where t+k leaves the row's split (purge, §4.1) or a term is
    missing. AR_cc after a symbol's last traded row counts as 0 as in ``panel/targets.py``."""
    lo, hi = cfg.convergence.plateau
    ar = _by_symbol(daily_panel, "ar_cc")
    sig = _by_symbol(daily_panel, "sigma_cc")
    last = ar.notna()[::-1].idxmax()  # last traded session per symbol
    held = ar.copy()
    for sym in held.columns:
        held.loc[held.index > last[sym], sym] = 0.0
    csum = held.fillna(0.0).cumsum()
    bad = held.isna().astype(float).cumsum()
    idx = held.index
    out = rows[["session", "symbol_id", "split"]].copy()
    r_pos = idx.get_indexer(pd.Index(pd.to_datetime(out["session"])))
    c_pos = held.columns.get_indexer(pd.Index(out["symbol_id"]))
    ends = {k: idx.searchsorted(pd.Timestamp(v), side="right") - 1 for k, v in split_end.items()}
    end_pos = out["split"].map(ends).to_numpy()
    c = csum.to_numpy()
    b = bad.to_numpy()
    s = sig.reindex(index=idx, columns=held.columns).to_numpy()
    for k in range(lo, hi + 1):
        hi_pos = r_pos + k
        ok = (r_pos >= 0) & (c_pos >= 0) & (hi_pos <= end_pos) & (hi_pos < len(idx))
        hp = np.where(ok, hi_pos, 0)
        lo_pos = np.where(r_pos > 0, r_pos - 1, 0)
        total = c[hp, c_pos] - np.where(r_pos > 0, c[lo_pos, c_pos], 0.0)
        nbad = b[hp, c_pos] - np.where(r_pos > 0, b[lo_pos, c_pos], 0.0)
        val = total / s[np.where(r_pos >= 0, r_pos, 0), c_pos]
        out[f"car_lvl_c{k}"] = np.where(ok & (nbad == 0), val, np.nan)
    return out


# --- H1 (§1.1) ---------------------------------------------------------------------------------------------


def h1(frame_d0: pd.DataFrame, split: str, cfg: AnalysisConfig, signal: str | None = None) -> dict[str, Any]:
    """H1: daily IC(N̂, z_on) − daily IC(N̂, z_id) > 0 on D0 events (paired, day bootstrap)."""
    c = cfg.h1
    sig = signal or c.signal
    s = _complete(eval_sample(frame_d0, split, cfg), [sig])
    boot = bootstrap_for(s, cfg)
    ic_on = daily(s, sig, c.gap, cfg)
    ic_id = daily(s, sig, c.after_open, cfg)
    both = pd.concat([ic_on.rename("on"), ic_id.rename("id")], axis=1, join="inner").dropna()
    est = mx.daily_mean_estimate(
        both["on"] - both["id"], boot, cfg.metrics.nw_lags, cfg.bootstrap.ci, "greater", len(s)
    )
    out: dict[str, Any] = {"test": "H1", "split": split, "signal": sig, **est.as_dict()}
    for name, series in (("ic_on", ic_on), ("ic_id", ic_id)):
        e = mx.daily_mean_estimate(series, boot, cfg.metrics.nw_lags, cfg.bootstrap.ci, "greater", len(s))
        out |= {
            f"{name}": e.value,
            f"{name}_t": e.nw_t,
            f"{name}_ci_low": e.ci_low,
            f"{name}_ci_high": e.ci_high,
        }
    return out


def h1b(frame_d0: pd.DataFrame, split: str, cfg: AnalysisConfig, signal: str | None = None) -> dict[str, Any]:
    """H1b (PREREG §15 NA-11 row): not fully priced at the open. Mean daily IC(N̂_W0, z_id) > 0 on D0 events,
    one-sided, on H1's sample and bootstrap draws."""
    c = cfg.h1b
    sig = signal or c.signal
    s = _complete(eval_sample(frame_d0, split, cfg), [sig])
    boot = bootstrap_for(s, cfg)
    est = mx.daily_mean_estimate(
        daily(s, sig, c.target, cfg), boot, cfg.metrics.nw_lags, cfg.bootstrap.ci, "greater", len(s)
    )
    return {"test": "H1b", "split": split, "signal": sig, "target": c.target, **est.as_dict()}


def primary_d0(
    frame_d0: pd.DataFrame, split: str, cfg: AnalysisConfig, signal: str | None = None
) -> dict[str, dict[str, Any]]:
    """H1 and H1b together: every analysis that re-runs H1 re-runs H1b (PREREG §15 NA-11 row)."""
    return {"H1": h1(frame_d0, split, cfg, signal), "H1b": h1b(frame_d0, split, cfg, signal)}


def ic_targets(
    frame_d0: pd.DataFrame,
    split: str,
    cfg: AnalysisConfig,
    signal: str | None = None,
    targets: Sequence[str] = ("z_cc", "z_on", "z_id"),
) -> dict[str, Any]:
    """Mean daily IC of the signal with each target (§11.1; the robustness and sector tables)."""
    sig = signal or cfg.h1.signal
    out: dict[str, Any] = {"split": split, "signal": sig}
    for t in targets:
        e = ic(frame_d0, split, sig, t, cfg)
        out |= {
            f"ic_{t}": e.value,
            f"ic_{t}_t": e.nw_t,
            f"ic_{t}_ci_low": e.ci_low,
            f"ic_{t}_ci_high": e.ci_high,
            f"ic_{t}_days": e.n_days,
            f"ic_{t}_n": e.n_obs,
        }
    return out


# --- H2 (§1.1) ---------------------------------------------------------------------------------------------


def h2(
    frame: pd.DataFrame, split: str, cfg: AnalysisConfig, point: Point | None = None, n_hat: str | None = None
) -> dict[str, Any]:
    """H2: y = a + b·N̂ + c·G + day × tier FE; b > 0 and c < 0 one-sided; p = max(p_b, p_c)."""
    pt = point or cfg.h2.primary_point
    pc = cfg.h2.points[pt]
    n = n_hat or pc.n_hat
    x = [n] if pc.g is None else [n, pc.g]
    s = _complete(eval_sample(frame, split, cfg), [pc.y, *x, *cfg.inference.fe, *cfg.inference.cluster])
    res = _reg(s, pc.y, x, cfg)
    out: dict[str, Any] = {
        "test": "H2",
        "split": split,
        "point": pt,
        "y": pc.y,
        "n_hat": n,
        "g": pc.g,
        "nobs": res.nobs,
        "n_sessions": res.n_clusters[0],
        "n_firms": res.n_clusters[1],
        "df_t": res.df_t,
        "r2_within": res.r2_within,
    }
    out |= _coef_row(res, n, "b", "greater")
    if pc.g is not None:
        out |= _coef_row(res, pc.g, "c", "less")
        out["p"] = max(out["b_p"], out["c_p"])
        out["p_dk"] = max(out["b_p_dk"], out["c_p_dk"])
    else:
        out["p"], out["p_dk"] = out["b_p"], out["b_p_dk"]
    return out


def h2_by_abs_g(
    frame: pd.DataFrame, split: str, cfg: AnalysisConfig, point: Point | None = None
) -> list[dict[str, Any]]:
    """H2 re-estimated within |G| bins (< 1, 1–2, > 2; PRD NA-12 S2)."""
    pt = point or cfg.h2.primary_point
    g = cfg.h2.points[pt].g
    if g is None:
        raise ValueError(f"{pt} has no observed reaction G")
    edges = [0.0, *cfg.h2.abs_g_bins, math.inf]
    out = []
    for lo, hi in itertools.pairwise(edges):
        a = frame[g].abs()
        sub = frame.loc[(a >= lo) & (a < hi)] if math.isfinite(hi) else frame.loc[a >= lo]
        row = h2(sub, split, cfg, pt)
        row["abs_g_bin"] = f"[{lo:g}, {hi:g})"
        out.append(row)
    return out


# --- ridge protocol (§11.5) --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RidgeFit:
    features: tuple[str, ...]
    target: str
    lam: float
    mean: tuple[float, ...]
    sd: tuple[float, ...]
    coef: tuple[float, ...]
    intercept: float
    n_fit: int
    fit_first: str
    fit_last: str
    lambda_scores: dict[str, float]

    def predict(self, frame: pd.DataFrame) -> FloatArray:
        x = frame[list(self.features)].to_numpy(dtype=float)
        z = (x - np.asarray(self.mean)) / np.asarray(self.sd)
        return np.asarray(z @ np.asarray(self.coef) + self.intercept, dtype=float)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def fit_ridge(
    frame: pd.DataFrame, features: Sequence[str], target: str, lam: float, standardize: bool = True
) -> RidgeFit:
    """Ridge on z-scored features (the fit rows' mean and SD; SD 0 → 1), unpenalized intercept."""
    d = _complete(frame, [*features, target])
    if len(d) <= len(features):
        raise ValueError(f"ridge needs more rows than features ({len(d)} rows)")
    x = d[list(features)].to_numpy(dtype=float)
    y = d[target].to_numpy(dtype=float)
    mu = x.mean(axis=0) if standardize else np.zeros(x.shape[1])
    sd = x.std(axis=0, ddof=0) if standardize else np.ones(x.shape[1])
    sd = np.where(sd > 0, sd, 1.0)
    z = (x - mu) / sd
    zc = z - z.mean(axis=0)
    coef = np.linalg.solve(zc.T @ zc + lam * np.eye(z.shape[1]), zc.T @ (y - y.mean()))
    intercept = float(y.mean() - z.mean(axis=0) @ coef)
    sessions = pd.to_datetime(d["session"]) if "session" in d.columns else pd.Series(dtype="datetime64[ns]")
    return RidgeFit(
        tuple(features),
        target,
        float(lam),
        tuple(mu.tolist()),
        tuple(sd.tolist()),
        tuple(coef.tolist()),
        intercept,
        len(d),
        str(sessions.min().date()) if len(sessions) else "",
        str(sessions.max().date()) if len(sessions) else "",
        {},
    )


def ridge_protocol(
    frame: pd.DataFrame, features: Sequence[str], target: str, cfg: AnalysisConfig
) -> RidgeFit:
    """§11.5 (PREREG §15 NA-11 row): fit on the fit split; λ = the grid value whose fit-split fit has the
    lowest
    mean squared error on the λ split (ties to the larger λ)."""
    r = cfg.ridge
    fit = _complete(eval_sample(frame, r.fit_split, cfg), [*features, target])
    val = _complete(eval_sample(frame, r.lambda_split, cfg), [*features, target])
    scores: dict[str, float] = {}
    best: tuple[float, float] | None = None
    for lam in r.lambdas:
        m = fit_ridge(fit, features, target, lam, r.standardize)
        mse = float(np.mean((val[target].to_numpy(dtype=float) - m.predict(val)) ** 2))
        scores[f"{lam:g}"] = mse
        if best is None or mse < best[1] - 1e-15 or (abs(mse - best[1]) <= 1e-15 and lam > best[0]):
            best = (lam, mse)
    assert best is not None
    final = fit_ridge(fit, features, target, best[0], r.standardize)
    return RidgeFit(**{**asdict(final), "lambda_scores": scores})


def _coalition_features(groups: Mapping[str, Sequence[str]], coalition: frozenset[str]) -> list[str]:
    return [f for g, feats in groups.items() if g in coalition for f in feats]


# --- H3 and Shapley (§1.1, §11.5) -------------------------------------------------------------------------


def h3(
    frame_d2: pd.DataFrame, cfg: AnalysisConfig, groups: Mapping[str, Sequence[str]], split: str | None = None
) -> dict[str, Any]:
    """H3 and the §11.5 Shapley table. ``groups``: {R, N, J} → the features the model answers."""
    ev = split or cfg.ridge.eval_split
    target = cfg.h3.target
    frame = add_tier_dummies(frame_d2)
    feats = [f for g in cfg.shapley.groups for f in groups[g]]
    data = _complete(frame, [*feats, target])
    fits: dict[frozenset[str], RidgeFit] = {}
    for co in sh.coalitions(cfg.shapley.groups):
        fits[co] = ridge_protocol(data, _coalition_features(groups, co), target, cfg)
    s = eval_sample(data, ev, cfg)
    boot = bootstrap_for(s, cfg)
    preds = {co: fit.predict(s) for co, fit in fits.items()}
    for co, p in preds.items():
        s[f"pred_{sh.label(co, cfg.shapley.groups)}"] = p
    full = frozenset(cfg.shapley.groups)
    rn = frozenset(("R", "N"))
    d_full = daily(s, f"pred_{sh.label(full)}", target, cfg)
    d_rn = daily(s, f"pred_{sh.label(rn)}", target, cfg)
    both = pd.concat([d_full.rename("f"), d_rn.rename("r")], axis=1, join="inner").dropna()
    est = mx.daily_mean_estimate(
        both["f"] - both["r"], boot, cfg.metrics.nw_lags, cfg.bootstrap.ci, "greater", len(s)
    )
    out: dict[str, Any] = {
        "test": "H3",
        "split": ev,
        "target": target,
        **est.as_dict(),
        "lambdas": {sh.label(c): f.lam for c, f in fits.items()},
        "fit_range": [fits[full].fit_first, fits[full].fit_last],
    }
    out["shapley"] = shapley_tables(s, preds, target, cfg)
    return out


def shapley_tables(
    s: pd.DataFrame, preds: Mapping[frozenset[str], FloatArray], target: str, cfg: AnalysisConfig
) -> dict[str, dict[str, Any]]:
    """Exact Shapley values and shares of OOS R² (zero forecast) and mean daily IC, pooled and by tier."""
    out: dict[str, dict[str, Any]] = {}
    for name, mask in [
        ("all", np.ones(len(s), dtype=bool)),
        *[(t, (s["tier"] == t).to_numpy()) for t in ("top100", "mid", "rest")],
    ]:
        sub = s.loc[mask]
        v_r2 = {co: mx.oos_r2(sub[target], p[mask]) for co, p in preds.items()}
        v_ic = {}
        for co in preds:
            col = f"pred_{sh.label(co, cfg.shapley.groups)}"
            series = daily(sub, col, target, cfg)
            v_ic[co] = float(series.mean()) if len(series) else math.nan
        row: dict[str, Any] = {"n": int(mask.sum())}
        for metric, v in (("r2", v_r2), ("ic", v_ic)):
            phi = sh.shapley(v, cfg.shapley.groups)
            row[metric] = {
                "values": {sh.label(c, cfg.shapley.groups): x for c, x in v.items()},
                "shapley": phi,
                "shares": sh.shares(phi),
                "interactions": sh.interactions(v, cfg.shapley.groups),
            }
        out[name] = row
    return out


# --- H4 (§1.1, A2.5) ---------------------------------------------------------------------------------------


def _delta_r2(
    s: pd.DataFrame,
    bench: RidgeFit,
    full: RidgeFit,
    target: str,
    ybar: float,
    boot: mx.Bootstrap,
    cfg: AnalysisConfig,
) -> mx.Estimate:
    y = s[target].to_numpy(dtype=float)
    e_b = (y - bench.predict(s)) ** 2
    e_f = (y - full.predict(s)) ** 2
    t = (y - ybar) ** 2
    per = pd.DataFrame({"session": s["session"].to_numpy(), "num": e_b - e_f, "den": t})
    g = per.groupby("session").sum()
    return mx.ratio_estimate(g["num"], g["den"], boot, cfg.bootstrap.ci, "greater", len(s))


def h4(
    frame_d0: pd.DataFrame,
    cfg: AnalysisConfig,
    news: Sequence[str],
    extra: Sequence[str] = (),
    split: str | None = None,
) -> dict[str, Any]:
    """H4: ΔR² of the news features over HAR + earnings + tier for |z_cc,t| (and A2.5's additions)."""
    ev = split or cfg.ridge.eval_split
    target = cfg.h4.target
    frame = add_tier_dummies(frame_d0)
    if target not in frame.columns:
        frame[target] = frame["z_cc"].abs()
    bench_f = list(cfg.groups.h4_bench)
    cols = [*bench_f, *news, *extra, target]
    data = _complete(frame, cols)
    bench = ridge_protocol(data, bench_f, target, cfg)
    full = ridge_protocol(data, [*bench_f, *news], target, cfg)
    ybar = float(eval_sample(data, cfg.ridge.fit_split, cfg)[target].mean())
    s = eval_sample(data, ev, cfg)
    boot = bootstrap_for(s, cfg)
    est = _delta_r2(s, bench, full, target, ybar, boot, cfg)
    out: dict[str, Any] = {
        "test": "H4",
        "split": ev,
        "target": target,
        "r2_reference_mean": ybar,
        "r2_reference": f"mean of {target} over {cfg.ridge.fit_split} events",
        **est.as_dict(),
        "r2_bench": 1
        - float(((s[target] - bench.predict(s)) ** 2).sum()) / float(((s[target] - ybar) ** 2).sum()),
        "lambda_bench": bench.lam,
        "lambda_full": full.lam,
    }
    if extra:
        wide = ridge_protocol(data, [*bench_f, *news, *extra], target, cfg)
        a2 = _delta_r2(s, full, wide, target, ybar, boot, cfg)
        out["a2_width"] = a2.as_dict()
    return out


# --- primary family and the headline rule (§1.1, §1.3) ------------------------------------------------------


def primary_family(p: Mapping[str, float], cfg: AnalysisConfig) -> dict[str, float]:
    """Holm-adjusted p of H1–H4."""
    fam = cfg.multiple_testing.primary
    return mx.holm({t: p.get(t, math.nan) for t in fam.tests})


def headline(
    primary: Mapping[str, Mapping[str, Any]],
    anchor: Mapping[str, Mapping[str, Any]],
    adjusted: Mapping[str, float],
    cfg: AnalysisConfig,
) -> dict[str, str]:
    """§1.3 for each primary hypothesis: general / model-specific / not supported.

    ``primary``/``anchor``: {test: {"estimate": signed value in the hypothesis' direction, "p": raw p}};
    for H2
    the estimate is min(b, −c) (both must be positive in H2's direction)."""
    alpha = cfg.multiple_testing.primary.alpha or 0.05
    out = {}
    for t in cfg.multiple_testing.primary.tests:
        pa = adjusted.get(t, math.nan)
        ok_primary = math.isfinite(pa) and pa < alpha and primary[t]["estimate"] > 0
        an = anchor.get(t, {})
        ok_anchor = bool(an) and an.get("estimate", math.nan) > 0 and an.get("p", math.nan) < alpha
        out[t] = (
            "general" if ok_primary and ok_anchor else "model-specific" if ok_primary else "not supported"
        )
    return out


def directional(result: Mapping[str, Any]) -> dict[str, float]:
    """{estimate, p} of a primary result in its hypothesis' direction (for ``headline``)."""
    if result["test"] == "H2" and "c" in result:
        return {"estimate": min(float(result["b"]), -float(result["c"])), "p": float(result["p"])}
    if result["test"] == "H2":
        return {"estimate": float(result["b"]), "p": float(result["p"])}
    return {"estimate": float(result["value"]), "p": float(result["p"])}


# --- secondary: H5 / A3.2, H6, H7 ---------------------------------------------------------------------------


def roll_r2(days: pd.DataFrame, split: str, cfg: AnalysisConfig) -> dict[str, Any]:
    """A3.2 step 1 (descriptive): 1 − Σ AR_cc² / Σ r_cc² over the split's covered member-days."""
    s = _complete(eval_sample(days, split, cfg), ["ar_cc", "r_cc"])
    return {
        "step": "market+sector",
        "r2": 1 - float((s["ar_cc"] ** 2).sum()) / float((s["r_cc"] ** 2).sum()),
        "n": len(s),
    }


def explanation_ladder(
    days: pd.DataFrame,
    cfg: AnalysisConfig,
    steps: Mapping[str, Sequence[str]] | None = None,
    split: str | None = None,
) -> dict[str, Any]:
    """A3.2 / H5: OOS share of stock-specific daily variance (z_cc, zero forecast) by cumulative feature steps
    on covered member-days (news features 0 on days without an event). ``steps`` defaults to the config's;
    a model without the explanation group passes its first two steps only."""
    ev = split or cfg.ridge.eval_split
    target = cfg.explanation.ladder_target
    st = dict(steps or cfg.explanation.ladder_steps)
    feats: list[str] = []
    data = _complete(days, [target, *[f for v in st.values() for f in v]])
    s = eval_sample(data, ev, cfg)
    boot = bootstrap_for(s, cfg)
    out: dict[str, Any] = {"split": ev, "target": target, "steps": {}}
    sst = pd.Series(s[target].to_numpy(dtype=float) ** 2).groupby(s["session"].to_numpy()).sum()
    prev: FloatArray | None = None
    for name, add in st.items():
        feats = [*feats, *add]
        fit = ridge_protocol(data, feats, target, cfg)
        pred = fit.predict(s)
        sse = pd.Series((s[target].to_numpy(dtype=float) - pred) ** 2).groupby(s["session"].to_numpy()).sum()
        est = mx.ratio_estimate(sst - sse, sst, boot, cfg.bootstrap.ci, "greater", len(s))
        row: dict[str, Any] = {**est.as_dict(), "lambda": fit.lam, "features": list(feats)}
        if prev is not None:
            sse_prev = (
                pd.Series((s[target].to_numpy(dtype=float) - prev) ** 2)
                .groupby(s["session"].to_numpy())
                .sum()
            )
            inc = mx.ratio_estimate(sse_prev - sse, sst, boot, cfg.bootstrap.ci, "greater", len(s))
            row["increment"] = inc.as_dict()
        out["steps"][name] = row
        prev = pred
    names = list(st)
    if len(names) >= 2:
        r2a, r2p = out["steps"][names[0]]["value"], out["steps"][names[1]]["value"]
        out["knowable_before_open"] = r2a / r2p if r2p else math.nan  # step 2 ÷ step 3 (A3.2)
        out["arrived_during_day"] = r2p - r2a  # step 3 − step 2
    return out


def h5(
    days: pd.DataFrame,
    cfg: AnalysisConfig,
    steps: Mapping[str, Sequence[str]] | None = None,
    split: str | None = None,
) -> dict[str, Any]:
    """H5 (BH): the ladder; the test is the ex-post step's OOS R² > 0."""
    lad = explanation_ladder(days, cfg, steps, split)
    names = list(lad["steps"])
    key = names[1] if len(names) > 1 else names[0]
    return {"test": "H5", "estimate": lad["steps"][key]["value"], "p": lad["steps"][key]["p"], "ladder": lad}


def _one_hot(
    frame: pd.DataFrame, col: str, min_share: float = 0.01, prefix: str | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Dummies of a categorical (the most frequent level is the base; levels under ``min_share`` pooled)."""
    v = frame[col].astype("string").fillna("missing")
    share = v.value_counts(normalize=True)
    keep = share[share >= min_share].index.tolist()
    v = v.where(v.isin(keep), "other_pooled")
    levels = v.value_counts().index.tolist()
    names = []
    out = frame.copy()
    for lev in levels[1:]:
        name = f"{prefix or col}__{re.sub(r'[^0-9A-Za-z_]+', '_', str(lev))}"
        out[name] = (v == lev).astype(float)
        names.append(name)
    return out, names


def h6(frame_d2: pd.DataFrame, split: str, cfg: AnalysisConfig, prefix: str = "a2_") -> dict[str, Any]:
    """H6: in H2 at D2 with content controls (vendor event type, vendor quantified, materiality) and tone,
    the coefficient on tone × sign(N̂) is < 0."""
    pc = cfg.h2.points["D2"]
    n, tone, m = f"{prefix}n_hat", f"{prefix}tone", f"{prefix}m"
    s = _complete(
        eval_sample(frame_d2, split, cfg),
        [pc.y, n, str(pc.g), tone, m, "vendor_quantified", "vendor_event_type"],
    )
    s["tone_x_sign"] = s[tone] * _sign(s[n])
    s["vendor_quantified_f"] = s["vendor_quantified"].astype(float)
    s, dummies = _one_hot(s, "vendor_event_type")
    x = [n, str(pc.g), "tone_x_sign", tone, m, "vendor_quantified_f", *dummies]
    res = _reg(s, pc.y, x, cfg)
    return {
        "test": "H6",
        "split": split,
        "nobs": res.nobs,
        **_coef_row(res, "tone_x_sign", "d", "less"),
        "estimate": -float(res.coef("tone_x_sign")),
        "p": float(res.p_one("tone_x_sign", "less")),
    }


def h7(
    frame_d0: pd.DataFrame, split: str, cfg: AnalysisConfig, trained: str, zero_shot: str
) -> dict[str, Any]:
    """H7: daily IC(trained N̂) − daily IC(zero-shot N̂) with z_cc,t on their common D0 events > 0."""
    s = _complete(eval_sample(frame_d0, split, cfg), [trained, zero_shot, "z_cc"])
    boot = bootstrap_for(s, cfg)
    a, b = daily(s, trained, "z_cc", cfg), daily(s, zero_shot, "z_cc", cfg)
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    est = mx.daily_mean_estimate(
        both["a"] - both["b"], boot, cfg.metrics.nw_lags, cfg.bootstrap.ci, "greater", len(s)
    )
    return {
        "test": "H7",
        "split": split,
        "trained": trained,
        "zero_shot": zero_shot,
        **est.as_dict(),
        "estimate": est.value,
    }


def calibration(
    probs: npt.ArrayLike, target: npt.ArrayLike, reference_target: npt.ArrayLike, cfg: AnalysisConfig
) -> dict[str, float]:
    """§11.2 on Q1's three classes: ECE, log-loss and Brier with their skill vs the reference climatology."""
    p3 = mx.three_class(probs)
    y = mx.realized_class(target, cfg.metrics.class_band)
    clim = mx.climatology(mx.realized_class(reference_target, cfg.metrics.class_band))
    pc = np.tile(clim, (len(p3), 1))
    ll, bs = mx.log_loss(p3, y), mx.brier(p3, y)
    return {
        "ece": mx.ece(p3, y, cfg.metrics.ece_bins),
        "log_loss": ll,
        "brier": bs,
        "log_loss_skill": mx.skill(ll, mx.log_loss(pc, y)),
        "brier_skill": mx.skill(bs, mx.brier(pc, y)),
        "n": int((y >= 0).sum()),
    }


def auc_large(score: npt.ArrayLike, target: npt.ArrayLike, cfg: AnalysisConfig) -> float:
    """§11.2 AUC of a magnitude score for |z| >= 1."""
    t = np.asarray(target, dtype=float)
    lab = np.where(np.isfinite(t), (np.abs(t) >= cfg.metrics.auc_abs_z).astype(float), np.nan)
    return mx.auc(score, lab)


# --- heterogeneity cuts (§1.2, operator rows (7)–(8)) -------------------------------------------------------


def cut_indicator(frame: pd.DataFrame, cut: CutCfg) -> pd.Series:
    """1.0 inside the cut, 0.0 outside, NaN where the cut is undefined (e.g. no usual-coverage mean)."""
    v = frame[cut.column]
    if cut.equals is not None:
        if isinstance(cut.equals, bool):
            return v.map(lambda z: np.nan if pd.isna(z) else float(bool(z) == cut.equals)).astype(float)
        return v.map(lambda z: np.nan if pd.isna(z) else float(str(z) == cut.equals)).astype(float)
    num = pd.to_numeric(v, errors="coerce")
    if cut.below is not None:
        return (num < cut.below).astype(float).where(num.notna())
    if cut.at_least is not None:
        return (num >= cut.at_least).astype(float).where(num.notna())
    if cut.below_median_by is not None:
        med = num.groupby([frame[c] for c in cut.below_median_by]).transform("median")
        return (num < med).astype(float).where(num.notna())
    raise ValueError(f"cut on {cut.column} has no rule")


def heterogeneity(frame_d2: pd.DataFrame, split: str, cfg: AnalysisConfig) -> list[dict[str, Any]]:
    """The cuts' Wald tests (one BH family) with the within-cut b and c."""
    pc = cfg.h2.points["D2"]
    g, n = str(pc.g), pc.n_hat
    base = eval_sample(frame_d2, split, cfg)
    base["abs_g"] = base[g].abs()
    rows = []
    for name, cut in cfg.cuts.list.items():
        s = base.copy()
        s["_in"] = cut_indicator(s, cut)
        s = _complete(s, [pc.y, n, g, "_in", *cfg.inference.fe, *cfg.inference.cluster])
        s["n_x_cut"] = s[n] * s["_in"]
        s["g_x_cut"] = s[g] * s["_in"]
        row: dict[str, Any] = {
            "cut": name,
            "split": split,
            "n_in": int(s["_in"].sum()),
            "n_out": int((1 - s["_in"]).sum()),
        }
        try:
            res = _reg(s, pc.y, [n, g, "n_x_cut", "g_x_cut"], cfg)
            f, q, p = inf.wald(res, ["n_x_cut", "g_x_cut"])
            row |= {
                "wald_f": f,
                "wald_q": q,
                "p": p,
                **_coef_row(res, "n_x_cut", "b_diff", None),
                **_coef_row(res, "g_x_cut", "c_diff", None),
            }
        except (ValueError, np.linalg.LinAlgError) as exc:
            row |= {"wald_f": math.nan, "wald_q": 2, "p": math.nan, "error": str(exc)}
        for side, val in (("in", 1.0), ("out", 0.0)):
            sub = s.loc[s["_in"] == val]
            try:
                r = h2(sub.assign(split=split, embargo=False), split, cfg, "D2")
                row |= {
                    f"b_{side}": r["b"],
                    f"b_{side}_se": r["b_se"],
                    f"c_{side}": r["c"],
                    f"c_{side}_se": r["c_se"],
                }
            except (ValueError, np.linalg.LinAlgError):
                row |= {f"b_{side}": math.nan, f"c_{side}": math.nan}
        rows.append(row)
    qv = mx.bh({row["cut"]: row["p"] for row in rows})
    for row in rows:
        row["q"] = qv[row["cut"]]
    return rows


def secondary_family(p: Mapping[str, float]) -> dict[str, float]:
    """BH q-values of the secondary family (H5, H6, H7, H2-C, A3.4)."""
    return mx.bh(dict(p))


# --- convergence (A1.3–A1.5) --------------------------------------------------------------------------------


def _boot_betas(
    s: pd.DataFrame, y: str, x: Sequence[str], boot: mx.Bootstrap, cfg: AnalysisConfig
) -> FloatArray:
    """Bootstrap slope draws (reps, k) from per-session moments (FE groups nest in sessions)."""
    days, a, b = inf.day_moments(s, y, list(x), fe=list(cfg.inference.fe), day="session")
    pos = pd.Index(list(boot.grid)).get_indexer(pd.Index(days))
    w = boot.counts[:, pos]
    return inf.beta_from_moments(a, b, w)


def ladder(
    frame_d0: pd.DataFrame,
    split: str,
    cfg: AnalysisConfig,
    value: str | None = None,
    rungs: Mapping[str, str] | None = None,
    clean: bool = False,
) -> dict[str, Any]:
    """A1.5 ladder: κ_h of CAR^lvl_h on V with day × tier FE; shares κ_h/κ_{h*} and κ_h/κ_{t+5}; κ_{h*} > 0
    and κ_{h*} − κ_{O_t} > 0 (bootstrap). ``clean``: each rung on its clean-window events only."""
    cv = cfg.convergence
    v = value or f"a0_{cv.value}"
    rg = dict(rungs or cv.ladder)
    s0 = _complete(eval_sample(frame_d0, split, cfg), [v, *cfg.inference.fe, *cfg.inference.cluster])
    boot = bootstrap_for(s0, cfg)
    rows: dict[str, dict[str, Any]] = {}
    draws: dict[str, FloatArray] = {}
    for name, col in rg.items():
        if col not in s0.columns:
            rows[name] = {"available": False}
            continue
        s = s0
        if clean and name in cv.clean_flags:
            s = s0.loc[s0[cv.clean_flags[name]].fillna(False).astype(bool)]
        s = _complete(s, [col])
        if len(s) < 10:
            rows[name] = {"available": False, "nobs": len(s)}
            continue
        res = _reg(s, col, [v], cfg)
        rows[name] = {"available": True, "nobs": res.nobs, **_coef_row(res, v, "kappa", "greater")}
        draws[name] = _boot_betas(s, col, [v], boot, cfg)[:, 0]
    out: dict[str, Any] = {"split": split, "value": v, "clean": clean, "rungs": rows}
    for ref_name, ref in (
        ("h_star", cv.h_star),
        ("h_short", cv.h_short),
        ("h_star_robust", cv.h_star_robust),
    ):
        k_ref = rows.get(ref, {}).get("kappa", math.nan)
        out[f"share_{ref_name}"] = {
            n: r.get("kappa", math.nan) / k_ref if k_ref else math.nan for n, r in rows.items()
        }
    first = next(iter(rg))
    if cv.h_star in draws and first in draws:
        k_star = rows[cv.h_star]["kappa"]
        diff = k_star - rows[first]["kappa"]
        bd = draws[cv.h_star] - draws[first]
        lo, hi = mx.percentile_ci(bd, cfg.bootstrap.ci)
        out["increase"] = {
            "from": first,
            "to": cv.h_star,
            "value": diff,
            "ci_low": lo,
            "ci_high": hi,
            "p": mx.boot_p(bd, diff, "greater"),
        }
        out["kappa_h_star_p"] = rows[cv.h_star]["kappa_p"]
    return out


def gap_closure(
    frame: pd.DataFrame,
    split: str,
    cfg: AnalysisConfig,
    point: Literal["D1", "D2"] = "D2",
    value: str | None = None,
) -> dict[str, Any]:
    """A1.5 gap closure: AR(τ→h)/σ_cc = a + λ_h·U_τ + ψ_h·V (+ day × tier FE); half-life with its bootstrap
    distribution over the rungs (first rung with λ_h >= threshold; "never" beyond the last rung)."""
    cv = cfg.convergence
    gp = cv.gap[point]
    v = value or gp.value
    base = _complete(eval_sample(frame, split, cfg), [v, gp.g_lvl, *cfg.inference.fe, *cfg.inference.cluster])
    base["u_gap"] = base[v] - base[gp.g_lvl]
    boot = bootstrap_for(base, cfg)
    rows: dict[str, dict[str, Any]] = {}
    lam_draws: dict[str, FloatArray] = {}
    for name, col in gp.rungs.items():
        if col not in base.columns:
            rows[name] = {"available": False}
            continue
        s = _complete(base, [col])
        res = _reg(s, col, ["u_gap", v], cfg)
        rows[name] = {
            "available": True,
            "nobs": res.nobs,
            **_coef_row(res, "u_gap", "lambda", "greater"),
            **_coef_row(res, v, "psi", None),
        }
        lam_draws[name] = _boot_betas(s, col, ["u_gap", v], boot, cfg)[:, 0]
    order = [n for n in gp.rungs if rows.get(n, {}).get("available")]
    sessions = [cv.rung_sessions[n] for n in order]
    thr = cv.half_life_lambda
    est = next((cv.rung_sessions[n] for n in order if rows[n]["lambda"] >= thr), NEVER)
    if order:
        mat = np.column_stack([lam_draws[n] for n in order])
        hit = mat >= thr
        first = np.where(hit.any(axis=1), np.asarray(sessions, dtype=float)[hit.argmax(axis=1)], NEVER)
        first = first[np.isfinite(mat).all(axis=1)]
        dist = {
            str(int(k)) if math.isfinite(k) else "never": float(np.mean(first == k))
            for k in [*sessions, NEVER]
        }
        # percentile CI over the ordered categories (the rungs, then "never"): quantiles of category codes
        cats = np.asarray([*sessions, NEVER], dtype=float)
        codes = np.searchsorted(cats, first)
        if len(codes):
            level = cfg.bootstrap.ci
            q = np.quantile(codes, [(1 - level) / 2, 1 - (1 - level) / 2], method="inverted_cdf")
            lo, hi = float(cats[int(q[0])]), float(cats[int(q[1])])
        else:
            lo, hi = math.nan, math.nan
    else:
        dist, lo, hi = {}, math.nan, math.nan
    return {
        "split": split,
        "point": point,
        "value": v,
        "rungs": rows,
        "half_life_sessions": est,
        "half_life_ci": [float(lo), float(hi)],
        "half_life_distribution": dist,
    }


def tracking_error(
    frame_d0: pd.DataFrame,
    split: str,
    cfg: AnalysisConfig,
    value: str | None = None,
    price_value: str = "po_v",
    rungs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """A1.4: RMSE(CAR^lvl_h − V) relative to the naive 0 and to the price-only value (ratios < 1 favour V)."""
    cv = cfg.convergence
    v = value or f"a0_{cv.value}"
    rg = dict(rungs or cv.ladder)
    out: dict[str, Any] = {"split": split, "value": v, "rungs": {}}
    for name, col in rg.items():
        cols = [v, col] + ([price_value] if price_value in frame_d0.columns else [])
        if col not in frame_d0.columns:
            continue
        s = _complete(eval_sample(frame_d0, split, cfg), cols)
        if len(s) < 10:
            continue
        boot = bootstrap_for(s, cfg)
        sess = s["session"].to_numpy()
        e_v = pd.Series((s[col] - s[v]).to_numpy() ** 2).groupby(sess).sum()
        row: dict[str, Any] = {"nobs": len(s), "rmse": math.sqrt(float(e_v.sum()) / len(s))}
        bench = {"naive": pd.Series(s[col].to_numpy() ** 2).groupby(sess).sum()}
        if price_value in s.columns:
            bench["price_only"] = pd.Series((s[col] - s[price_value]).to_numpy() ** 2).groupby(sess).sum()
        for bn, e_b in bench.items():
            ratio = math.sqrt(float(e_v.sum()) / float(e_b.sum()))
            with np.errstate(divide="ignore", invalid="ignore"):
                br = np.sqrt(boot.sums(e_v) / boot.sums(e_b))
            lo, hi = mx.percentile_ci(br, cfg.bootstrap.ci)
            row[bn] = {
                "ratio": ratio,
                "ci_low": lo,
                "ci_high": hi,
                "p": mx.boot_p(br - 1.0, ratio - 1.0, "less"),
            }
        out["rungs"][name] = row
    return out


def h2c_tests(
    lad: Mapping[str, Any], gap_d2: Mapping[str, Any], te: Mapping[str, Any], cfg: AnalysisConfig
) -> dict[str, float]:
    """The H2-C p-values that enter the secondary BH family."""
    cv = cfg.convergence
    out = {
        "H2C_kappa_hstar": float(lad.get("kappa_h_star_p", math.nan)),
        "H2C_kappa_increase": float(lad.get("increase", {}).get("p", math.nan)),
        "H2C_lambda_t5": float(gap_d2["rungs"].get(cv.h_short, {}).get("lambda_p", math.nan)),
        "H2C_tracking_naive": float(te["rungs"].get(cv.h_star, {}).get("naive", {}).get("p", math.nan)),
    }
    return out


# --- A2.5 ---------------------------------------------------------------------------------------------------


def by_category(
    frame: pd.DataFrame, column: str, fn: Callable[[pd.DataFrame], dict[str, Any]], min_rows: int = 30
) -> dict[str, dict[str, Any]]:
    """``fn`` on each level of a categorical (levels with fewer than ``min_rows`` rows are skipped)."""
    out: dict[str, dict[str, Any]] = {}
    for lev, sub in frame.groupby(frame[column].astype("string"), dropna=True):
        if len(sub) < min_rows:
            continue
        try:
            out[str(lev)] = fn(sub)
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            out[str(lev)] = {"error": str(exc)}
    return out


def mechanism_cuts(
    frame: pd.DataFrame,
    split: str,
    cfg: AnalysisConfig,
    fn: Callable[[pd.DataFrame], dict[str, Any]],
    prefix: str,
) -> dict[str, Any]:
    """A2.5: ``fn`` (H2 or the ladder) by the model's own event type / quantified label and the vendor's."""
    s = eval_sample(frame, split, cfg)
    out: dict[str, Any] = {}
    for col in [f"{prefix}{c}" for c in cfg.mechanism.model_labels] + list(cfg.mechanism.vendor):
        if col in s.columns:
            out[col] = by_category(s, col, fn)
    return out


def horizon_validity(
    frame_d0: pd.DataFrame, split: str, cfg: AnalysisConfig, h: str = "a0_h"
) -> dict[str, Any]:
    """A2.5: Spearman(H, CAR^lvl_{C_t} / CAR^lvl_{t+20}) over events with |CAR^lvl_{t+20}| >= the minimum;
    expected < 0; CI and p from the day bootstrap (events resampled with their sessions)."""
    s = _complete(eval_sample(frame_d0, split, cfg), [h, "car_lvl_c0", "car_lvl_c20"])
    s = s.loc[s["car_lvl_c20"].abs() >= cfg.horizon_validity.min_abs_car20].copy()
    s["speed"] = s["car_lvl_c0"] / s["car_lvl_c20"]
    rho = mx.spearman(s[h], s["speed"])
    boot = bootstrap_for(s, cfg)
    rows_by_day = s.groupby("session").indices
    grid_rows = [rows_by_day.get(d, np.array([], dtype=np.int64)) for d in boot.grid]
    hv, sp = s[h].to_numpy(dtype=float), s["speed"].to_numpy(dtype=float)
    reps = min(len(boot.idx), 2000)  # rank correlations per draw: 2,000 draws suffice for a CI
    draws = np.empty(reps)
    for b in range(reps):
        take = np.concatenate([grid_rows[i] for i in boot.idx[b]])
        draws[b] = mx.spearman(hv[take], sp[take]) if len(take) >= 3 else np.nan
    lo, hi = mx.percentile_ci(draws, cfg.bootstrap.ci)
    return {
        "split": split,
        "rho": rho,
        "ci_low": lo,
        "ci_high": hi,
        "p": mx.boot_p(draws, rho, "less"),
        "n": len(s),
        "reps": reps,
    }


# --- A3.3–A3.5 ----------------------------------------------------------------------------------------------


def explained_share(
    frame_d2: pd.DataFrame,
    split: str,
    cfg: AnalysisConfig,
    x: str = "b2_x",
    reason: str = "b2_label_move_reason",
) -> dict[str, Any]:
    """A3.3: the share of Σ z_cc² on event days judged explained (X >= threshold), by tier and by reason."""
    s = _complete(eval_sample(frame_d2, split, cfg), [x, "z_cc"])
    s["sq"] = s["z_cc"] ** 2
    s["explained"] = s[x] >= cfg.explanation.explained_x
    tot = float(s["sq"].sum())
    out: dict[str, Any] = {
        "split": split,
        "n": len(s),
        "share_explained": float(s.loc[s["explained"], "sq"].sum()) / tot if tot else math.nan,
        "share_events_explained": float(s["explained"].mean()),
    }
    out["by_tier"] = {
        str(t): float(g.loc[g["explained"], "sq"].sum() / g["sq"].sum())
        for t, g in s.groupby("tier")
        if g["sq"].sum() > 0
    }
    if reason in s.columns:
        out["by_reason"] = {
            str(r): {
                "share_of_variance": float(g["sq"].sum() / tot),
                "n": len(g),
                "share_explained": float(g.loc[g["explained"], "sq"].sum() / g["sq"].sum())
                if g["sq"].sum() > 0
                else math.nan,
            }
            for r, g in s.groupby(reason)
        }
    return out


def persistence(
    frame: pd.DataFrame, split: str, cfg: AnalysisConfig, point: Literal["D1", "D2"] = "D2"
) -> dict[str, Any]:
    """A3.4: sign(G)·y = a + θ·X + |G| + N̂ + event type + day × tier FE; θ > 0 one-sided."""
    pc = cfg.explanation.persistence[point]
    s = _complete(eval_sample(frame, split, cfg), [pc.y, pc.g, pc.x, pc.n_hat, pc.event_type])
    s["signed_y"] = _sign(s[pc.g]) * s[pc.y]
    s["abs_g"] = s[pc.g].abs()
    s, dummies = _one_hot(s, pc.event_type, prefix="etype")
    res = _reg(s, "signed_y", [pc.x, "abs_g", pc.n_hat, *dummies], cfg)
    return {
        "test": "A3.4",
        "split": split,
        "point": point,
        "nobs": res.nobs,
        **_coef_row(res, pc.x, "theta", "greater"),
        "estimate": float(res.coef(pc.x)),
        "p": float(res.p_one(pc.x, "greater")),
    }


def persistence_by_reason(
    frame_d2: pd.DataFrame, split: str, cfg: AnalysisConfig, reason: str = "b2_label_move_reason"
) -> dict[str, Any]:
    """A3.4 by ``move_reason``: mean sign(G)·y2 with day-bootstrap CIs (descriptive)."""
    pc = cfg.explanation.persistence["D2"]
    s = _complete(eval_sample(frame_d2, split, cfg), [pc.y, pc.g, reason])
    s["signed_y"] = _sign(s[pc.g]) * s[pc.y]
    out: dict[str, Any] = {}
    for r, g in s.groupby(reason):
        if len(g) < 30:
            continue
        boot = bootstrap_for(g, cfg)
        per = g.groupby("session")["signed_y"].agg(["sum", "count"])
        est = mx.ratio_estimate(per["sum"], per["count"], boot, cfg.bootstrap.ci, "greater", len(g))
        out[str(r)] = est.as_dict()
    return out


def market_replication(frame_m: pd.DataFrame, cfg: AnalysisConfig) -> dict[str, Any]:
    """A3.5 (exploratory): OLS of the market target on the market readings, fit on the validation sessions,
    OOS
    R² (zero forecast) on the evaluation sessions with a session bootstrap."""
    mc = cfg.market
    d = _complete(frame_m, [mc.target, *mc.features])
    fit = d.loc[d["split"].isin(list(mc.fit_splits))]
    ev = d.loc[d["split"] == mc.eval_split]
    if len(fit) <= len(mc.features) + 1 or not len(ev):
        return {"available": False, "n_fit": len(fit), "n_eval": len(ev)}
    x = np.column_stack([np.ones(len(fit)), fit[list(mc.features)].to_numpy(dtype=float)])
    beta = np.linalg.lstsq(x, fit[mc.target].to_numpy(dtype=float), rcond=None)[0]
    xe = np.column_stack([np.ones(len(ev)), ev[list(mc.features)].to_numpy(dtype=float)])
    pred = xe @ beta
    y = ev[mc.target].to_numpy(dtype=float)
    per = pd.DataFrame({"session": ev["session"].to_numpy(), "num": y**2 - (y - pred) ** 2, "den": y**2})
    g = per.groupby("session").sum()
    boot = bootstrap_for(ev, cfg)
    est = mx.ratio_estimate(g["num"], g["den"], boot, cfg.bootstrap.ci, "greater", len(ev))
    return {"available": True, "beta": beta.tolist(), "n_fit": len(fit), **est.as_dict(prefix="r2_")}


# --- exploratory: sectors (operator row) ----------------------------------------------------------------


def sector_ic(
    frame_d0: pd.DataFrame, split: str, cfg: AnalysisConfig, signal: str | None = None
) -> dict[str, Any]:
    """IC of N̂ by GICS sector (block-bootstrap CIs) and the main ICs with each sector left out."""
    sig = signal or cfg.sector.signal
    s = eval_sample(frame_d0, split, cfg)
    out: dict[str, Any] = {"split": split, "signal": sig, "by_sector": {}, "leave_one_out": {}}
    for sec, g in s.groupby("sector"):
        out["by_sector"][str(sec)] = ic_targets(g, split, cfg, sig, cfg.sector.targets)
    for sec in sorted(s["sector"].dropna().unique()):
        out["leave_one_out"][str(sec)] = ic_targets(
            s.loc[s["sector"] != sec], split, cfg, sig, cfg.sector.targets
        )
    return out


# --- robustness (§11.6, operator rows (a)–(b)) -----------------------------------------------------------


@functools.cache
def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def news_text(state_json: str) -> str:
    """The headlines and snippets of a state's ``news`` block (the only free text of a state)."""
    items = json.loads(state_json).get("news", [])
    return "\n".join(f"{it.get('headline', '')}\n{it.get('snippet', '')}" for it in items)


def price_move_text(state_json: str, cfg: AnalysisConfig) -> bool:
    """Operator row (a): the state's news text matches ``price_move_text``."""
    return _rx(cfg.robustness.price_move_text).search(news_text(state_json)) is not None


def live_format(state_json: str, cfg: AnalysisConfig) -> bool:
    """Operator row residue: a live format in a news headline. NA-04 left out every title that opens with one,
    so a remaining one sits behind a prefix or ends the title ("…: Stock Market Today")."""
    rx = _rx(cfg.robustness.live_format)
    return any(rx.search(it.get("headline", "")) for it in json.loads(state_json).get("news", []))


def timing_stratum(latest_et: npt.ArrayLike, cfg: AnalysisConfig) -> npt.NDArray[np.object_]:
    """Operator row (b): the latest W0 article before 04:00, 04:00–08:00 or 08:00–09:15 ET of the session
    (``latest_et`` in minutes after midnight; earlier days are negative and fall in the first stratum)."""
    edges = [int(h) * 60 + int(m) for h, m in (e.split(":") for e in cfg.robustness.timing_strata_et)]
    v = np.asarray(latest_et, dtype=float)
    names = [
        f"before_{cfg.robustness.timing_strata_et[0]}",
        f"{cfg.robustness.timing_strata_et[0]}_{cfg.robustness.timing_strata_et[1]}",
        f"{cfg.robustness.timing_strata_et[1]}_{cfg.robustness.timing_strata_et[2]}",
    ]
    out = np.full(len(v), None, dtype=object)
    ok = np.isfinite(v)
    out[ok & (v < edges[0])] = names[0]
    out[ok & (v >= edges[0]) & (v < edges[1])] = names[1]
    out[ok & (v >= edges[1]) & (v <= edges[2])] = names[2]
    return out


def non_overlapping(frame: pd.DataFrame, sessions: Sequence[date], gap: int) -> pd.DataFrame:
    """§11.6: the first event per company per ``gap`` sessions (greedy in time: an event is kept when the
    company's last kept event is at least ``gap`` sessions earlier)."""
    pos = {pd.Timestamp(d): i for i, d in enumerate(sorted(sessions))}
    f = frame.assign(_pos=pd.to_datetime(frame["session"]).map(pos)).sort_values(["company_id", "_pos"])
    keep = []
    last: dict[Any, int] = {}
    for idx, cid, p in zip(f.index, f["company_id"], f["_pos"], strict=True):
        if pd.isna(p):
            continue
        if cid not in last or p - last[cid] >= gap:
            keep.append(idx)
            last[cid] = int(p)
    return frame.loc[sorted(keep)]


def placebo_adjust(
    frame: pd.DataFrame, means: pd.DataFrame, targets: Sequence[str], by: Sequence[str] = ("session", "tier")
) -> pd.DataFrame:
    """§5.7: ``target`` minus its (day, tier) placebo mean; the raw columns are replaced, the placebo means
    kept
    as ``<target>_placebo``. ``means`` comes from covered member-days without a selected event in W2 of the
    same or the previous 5 sessions (``placebo_means``)."""
    out = frame.merge(means, on=list(by), how="left", validate="many_to_one")
    for t in targets:
        out[t] = out[t] - out[f"{t}_placebo"]
    return out


def placebo_means(
    days: pd.DataFrame, targets: Sequence[str], by: Sequence[str] = ("session", "tier")
) -> pd.DataFrame:
    """Mean of each target over the eligible member-days (``days.placebo_eligible``) per (day, tier)."""
    sub = days.loc[days["placebo_eligible"].fillna(False).astype(bool), [*by, *targets]]
    return sub.groupby(list(by), dropna=False)[list(targets)].mean().add_suffix("_placebo").reset_index()


def robustness_variants(
    frame: pd.DataFrame, cfg: AnalysisConfig, sessions: Sequence[date], point: Point = "D0"
) -> Iterator[tuple[str, pd.DataFrame]]:
    """The §11.6 / operator variants that need no new model call (each re-runs H1 at D0 or H2 at D2 on the
    frame it yields). The operator's (a) price-move text and (b) timing strata are D0 only (IC and H1 on the
    Call A D0 state). Variants that need other inputs (σ60, placebo, 2024-H1, the ablation and unmasked calls)
    are run by the caller with the helpers above."""
    yield "dollar_volume_tiers", frame.assign(tier=frame["dv_tier"])
    if "imprecise" in frame.columns:
        yield "exclude_date_only_hour", frame.loc[~frame["imprecise"].fillna(False).astype(bool)]
    yield "exclude_half_days", frame.loc[~frame["half_day"].fillna(False).astype(bool)]
    yield "non_overlapping", non_overlapping(frame, sessions, cfg.robustness.non_overlap_sessions)
    if "delist_within_c20" in frame.columns:
        yield "exclude_delisting_flag", frame.loc[~frame["delist_within_c20"].fillna(False).astype(bool)]
    if point != "D0":  # the operator's (a) and (b) are defined on the Call A D0 state (IC and H1)
        return
    if "price_move_text" in frame.columns:
        yield "without_price_move_text", frame.loc[~frame["price_move_text"].fillna(False).astype(bool)]
    if "latest_et" in frame.columns:
        h, m = (int(x) for x in cfg.robustness.cutoff_approx_et.split(":"))
        early = frame["latest_et"].to_numpy(dtype=float) < h * 60 + m
        yield f"w0_cutoff_{cfg.robustness.cutoff_approx_et}_approx", frame.loc[early]
        st = timing_stratum(frame["latest_et"].to_numpy(dtype=float), cfg)
        for name in sorted({x for x in st if x is not None}):
            yield f"timing_{name}", frame.loc[st == name]


def robustness(
    frame: pd.DataFrame, split: str, cfg: AnalysisConfig, sessions: Sequence[date], point: Point = "D0"
) -> dict[str, dict[str, Any]]:
    """Every ``robustness_variants`` frame re-run: at D0, H1 and H1b and the ICs of N̂ with z_cc, z_on and z_id
    (the operator row's report for (a) and (b)); at D2, H2."""
    out: dict[str, dict[str, Any]] = {}
    for name, f in robustness_variants(frame, cfg, sessions, point):
        if point == "D0":
            out[name] = {**primary_d0(f, split, cfg), "ic": ic_targets(f, split, cfg)}
        else:
            out[name] = {"H2": h2(f, split, cfg, point)}
    return out
