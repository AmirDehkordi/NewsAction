"""NA-13b (a) and (c): risk–coverage curves of the D0 reading (selective prediction; Geifman and El-Yaniv,
2017) and the operator's assistant's band check, reproduced.

**(a) Curves.** Each model's D0 events are ranked by its conviction |N̂| and, separately, by its stated
confidence (Q1's three-class confidence, the frozen gate's measure; ``data``). A coverage c keeps the events
whose score is at or above the val-A quantile at 1 − c of that score (thresholds from val-A only; c = 100%
keeps every event). For each split (val-A, val-B, test), target (z_cc, z_on, z_id) and coverage:

- the hit rate, the share of covered events with sign(N̂) = sign(z);
- the mean signed move, the mean of sign(N̂)·z over covered events (typical daily moves);
- the mean daily IC of N̂ with z over the covered events (the frozen daily IC: sessions with >= 5 such
  events; IC 0 on a constant session) with its Newey–West t (5 lags).

Events of the split outside the embargo with N̂ and the target. 95% CIs: the frozen stationary block bootstrap
over the split's sessions (block 5, 10,000 draws, seed 2026; ``metrics.Bootstrap``), one draw set per split
shared by every model, ranking, coverage and target (common random numbers); the pooled means are bootstrapped
from per-session sums (``metrics.ratio_estimate``), the IC from its daily series. span-02's and drex-v2.0's
val-A points and thresholds come from NA-06's 3,000-event stage-2 sample (``data``).

**(c) Bands** (disclosure, the operator's assistant's first look): |N̂| bands at the val-A 50th, 70th and
90th percentiles (bottom 50%, 50–70%, 70–90%, top 10%), the hit rate against z_cc and the mean signed z_cc,
z_on and z_id per split, pooled over events; events outside the embargo with N̂ and z_cc. The code is the
assistant's, line for line, so the numbers in the operator's prompt reproduce exactly.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction.analysis import metrics as mx
from newsaction.analysis import spec
from newsaction.selective import data as sd

COVERAGES: Final = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05)
RANKINGS: Final = ("conviction", "confidence")
GATE_COVERAGE: Final = 0.3  # the frozen gate: the val-A 70th percentile of the stated confidence
BAND_EDGES: Final = (0.5, 0.7, 0.9)
BANDS: Final = ("bottom 50%", "50-70%", "70-90%", "top 10%")
MIN_IC_DAYS: Final = 10


def score(df: pd.DataFrame, ranking: str) -> pd.Series:
    if ranking == "conviction":
        return df["n_hat"].abs()
    if ranking == "confidence":
        return df["conf"]
    raise ValueError(f"unknown ranking {ranking!r}")


def thresholds(
    frame: pd.DataFrame, ranking: str, coverages: Sequence[float] = COVERAGES
) -> dict[float, float]:
    """The val-A quantile of the score at 1 − c for each coverage c (−inf at c = 1)."""
    va = score(sd.eval_rows(frame, "val_a"), ranking).dropna()
    if va.empty:
        raise sd.DataError("no val-A readings to set the thresholds")
    return {c: (-math.inf if c >= 1.0 else float(va.quantile(1.0 - c))) for c in coverages}


def gate_coverage(frame: pd.DataFrame, gate: float) -> float:
    """The share of val-A events at or above the frozen gate (0.30 by construction on the gate's sample)."""
    return float((sd.eval_rows(frame, "val_a")["conf"] >= gate).mean())


def _ci(boot: np.ndarray, level: float) -> tuple[float, float]:
    return mx.percentile_ci(boot, level)


def point(covered: pd.DataFrame, target: str, boot: mx.Bootstrap, cfg: spec.AnalysisConfig) -> dict[str, Any]:
    """Hit rate, mean signed move and mean daily IC over the covered events, with bootstrap CIs."""
    level = cfg.bootstrap.ci
    s = np.sign(covered["n_hat"].to_numpy(dtype=float))
    z = covered[target].to_numpy(dtype=float)
    d = pd.DataFrame(
        {"session": covered["session"].to_numpy(), "hit": (s == np.sign(z)).astype(float), "signed": s * z}
    )
    per = d.groupby("session").agg(n=("hit", "size"), hit=("hit", "sum"), signed=("signed", "sum"))
    out: dict[str, Any] = {"n": len(d), "n_days": len(per)}
    for k in ("hit", "signed"):
        value = float(d[k].mean()) if len(d) else math.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            bs = boot.sums(per[k]) / boot.sums(per["n"])
        lo, hi = _ci(bs, level)
        out |= {k: value, f"{k}_ci_low": lo, f"{k}_ci_high": hi}
    daily = spec.daily(covered, "n_hat", target, cfg)
    if len(daily) >= MIN_IC_DAYS:
        mean, t, n = mx.nw_t(daily, cfg.metrics.nw_lags)
        lo, hi = _ci(boot.means(daily), level)
        out |= {"ic": mean, "ic_t": t, "ic_ci_low": lo, "ic_ci_high": hi, "ic_days": n}
    else:
        out |= {"ic": math.nan, "ic_t": math.nan, "ic_ci_low": math.nan, "ic_ci_high": math.nan}
        out["ic_days"] = len(daily)
    return out


def boots(ev: pd.DataFrame, cfg: spec.AnalysisConfig, splits: Sequence[str] = sd.SPLITS) -> dict[str, Any]:
    """One §11.4 draw set per split on the sessions of its evaluation sample (every event outside the
    embargo)."""
    b = cfg.bootstrap
    return {
        s: mx.Bootstrap.draw(sd.eval_rows(ev, s)["session"].unique().tolist(), b.reps, b.block, b.seed)
        for s in splits
    }


def curves(
    frames_by_model: Mapping[str, pd.DataFrame],
    boot: Mapping[str, mx.Bootstrap],
    cfg: spec.AnalysisConfig,
    splits: Sequence[str] = sd.SPLITS,
    targets: Sequence[str] = sd.TARGETS,
    coverages: Sequence[float] = COVERAGES,
) -> pd.DataFrame:
    """Every (model, ranking, coverage, split, target) point of the risk–coverage curves."""
    rows: list[dict[str, Any]] = []
    for model, f in frames_by_model.items():
        for ranking in RANKINGS:
            thr = thresholds(f, ranking, coverages)
            for split in splits:
                base = sd.eval_rows(f, split)
                if base.empty:
                    continue
                sc = score(base, ranking)
                sample = str(base["sample"].iloc[0]) if base["sample"].nunique() == 1 else "mixed"
                for c in coverages:
                    cov = base.loc[sc >= thr[c]]
                    for target in targets:
                        x = cov.dropna(subset=["n_hat", target])
                        rows.append(
                            {"model": model, "ranking": ranking, "coverage": c, "split": split,
                             "target": target, "threshold": thr[c], "sample": sample,
                             **point(x, target, boot[split], cfg)}
                        )  # fmt: skip
    return pd.DataFrame(rows)


# --- (c) the disclosure: the operator's assistant's band check, verbatim ----------------------------------


def bands(model_frame: pd.DataFrame) -> tuple[list[float], pd.DataFrame]:
    """The assistant's code: ``frame_d0_<model>`` outside the embargo, rows with N̂ and z_cc, |N̂| bands at
    the val-A 50/70/90% quantiles; per split and band the count, the hit rate against z_cc and the mean
    signed z_cc, z_on and z_id (pooled over events)."""
    f = model_frame.loc[~model_frame["embargo"]].dropna(subset=["a0_n_hat", "z_cc"]).copy()
    a = f["a0_n_hat"].abs()
    q = a[f["split"] == "val_a"].quantile(list(BAND_EDGES)).to_numpy()
    f["band"] = np.select([a < q[0], a < q[1], a < q[2]], list(BANDS[:3]), BANDS[3])
    s = np.sign(f["a0_n_hat"])
    for k in sd.TARGETS:
        f["s_" + k] = s * f[k]
    f["hit"] = (s == np.sign(f["z_cc"])).astype(float)
    g = f.groupby(["split", "band"]).agg(
        n=("hit", "size"),
        hit_cc=("hit", "mean"),
        cc=("s_z_cc", "mean"),
        on=("s_z_on", "mean"),
        id=("s_z_id", "mean"),
    )
    return [float(v) for v in q], g.reset_index()
