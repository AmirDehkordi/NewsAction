"""Pooled OLS with absorbed fixed effects, two-way clustered and Driscoll–Kraay covariances (PREREG §1.2 H2,
§11.3–11.4; §15 A1.5, A3).

§11.3: pooled OLS with day × tier fixed effects; standard errors two-way clustered (date, firm);
Driscoll–Kraay (5 lags) as robustness. ``ols_fe`` returns what statsmodels' ``OLS`` gives on the same rows
with explicit FE dummies, ``cov_type="cluster"`` with a two-column ``groups`` array and
``cov_type="nw-groupsum"`` with ``time`` and ``maxlags`` (statsmodels' defaults otherwise). It absorbs the
fixed effects instead of estimating them, so a 20,000-row frame with 450 groups fits in milliseconds.
tests/test_inference.py checks every formula below against statsmodels.

**Sample.** Rows missing y, an x, an FE, cluster or time value are dropped; N counts the rest. Singleton FE
groups stay in: they demean to zero, as their dummy would fit them exactly.

**Estimator** (Frisch–Waugh–Lovell). g(i) is row i's FE group, one per observed combination of the ``fe``
columns; ỹ_i = y_i − ȳ_g(i) and x̃_i = x_i − x̄_g(i); β̂ = (X̃'X̃)⁻¹X̃'ỹ, and e = ỹ − X̃β̂ are the dummy
regression's residuals. With ``fe=None`` the design is [1, X] ("const" first), not demeaned. K = k + k_fe
(k + 1 with ``fe=None``) is the dummy design's column count, the K of statsmodels' corrections.
r2_within = 1 − e'e / ỹ'ỹ (with ``fe=None``, 1 − e'e / Σ(y − ȳ)², statsmodels' R²).

**Sandwich.** B = (X̃'X̃)⁻¹. For a partition P of the rows, S_P = Σ_{p∈P} u_p u_p' with u_p = Σ_{i∈p} x̃_i e_i.
The β block of statsmodels' dummy-design sandwich is exactly B S_P B, because the β rows of (Z'Z)⁻¹Z' are
B X̃' (FWL); absorbing changes only the K in the corrections.

**Two-way clustered** (``cov``; Cameron–Gelbach–Miller; statsmodels ``cov_cluster_2groups``, CRV1):

    V = c(G₀) B S₀ B + c(G₁) B S₁ B − c(G₀₁) B S₀₁ B,    c(G) = G/(G − 1) · (N − 1)/(N − K),

where S₀ and S₁ cluster on ``cluster[0]`` and ``cluster[1]`` and S₀₁ on their intersection (one cell per
observed pair). Each term has its own G; G₀₁ is the number of observed pairs. There is no eigenvalue fix: V
need not be positive semi-definite, and a negative variance gives se = NaN (as statsmodels' ``bse``).

**Driscoll–Kraay** (``cov_dk``; statsmodels ``cov_nw_groupsum``, default ``use_correction="cluster"``). The T
periods are the sorted distinct ``time`` values of the kept rows, so a lag counts observed periods, not
calendar days. h_t = Σ_{i: time_i = t} x̃_i e_i, Γ_ℓ = Σ_{t>ℓ} h_t h_{t−ℓ}', w_ℓ = 1 − ℓ/(L + 1) (Bartlett,
L = ``dk_lags``):

    V_DK = T/(T − 1) · (N − 1)/(N − K) · B [Γ₀ + Σ_{ℓ=1..L} w_ℓ (Γ_ℓ + Γ_ℓ')] B.

statsmodels gives the same with ``time`` = the integer codes 0..T−1 of the sorted periods (its group sums put
period c in row c).

**Inference.** t = β̂/se, and p comes from Student t with df_t = min(G₀, G₁) − 1. That is statsmodels'
``df_resid_inference`` for two-way clustering, but statsmodels uses it only with ``use_t=True``; its default
for robust covariances is the normal. The p-values here equal statsmodels' with ``use_t=True``.
The Driscoll–Kraay p-values use the same df_t. statsmodels' ``nw-groupsum`` sets ``df_resid_inference`` to the
number of descents of ``time`` in row order (it counts stacked panel units), so it depends on how the rows are
sorted: 0 (p = NaN) for rows in time order, T − 1 for rows in descending time order. df_t is T − 1 whenever
time is the smaller cluster dimension, as in the pre-registered panels (fewer sessions than firms).
``wald``: W = β̂_R' V_RR⁻¹ β̂_R, F = W/q, p from F(q, df_t): statsmodels' ``f_test`` with the same covariance.

**Day bootstrap** (§11.4 resamples days). When every FE group lies within one day, the within transformation
of a resample of whole days equals the original one. So β̂* = (Σ_d w_d A_d)⁻¹ Σ_d w_d b_d, with
A_d = X̃_d'X̃_d, b_d = X̃_d'ỹ_d and w_d the number of draws of day d (``day_moments``, ``counts_from_indices``,
``beta_from_moments``). This equals ``ols_fe`` on the duplicated rows; all-ones weights give ``ols_fe``'s β̂.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats  # type: ignore[import-untyped, unused-ignore]

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
ObjectArray = npt.NDArray[np.object_]
Kind = Literal["cluster", "dk"]

CONST: Final = "const"
CLUSTER: Final = ("session", "company_id")  # §11.3: two-way clustered (date, firm)
DK_LAGS: Final = 5  # §11.3: Driscoll–Kraay (5 lags)
ABSORBED_RTOL: Final = 1e-9  # a regressor whose within norm is below this share of its norm is absorbed
_SIDES: Final = {"greater": 1.0, "less": -1.0}


# --- result ----------------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class OLSResult:
    """One ``ols_fe`` fit. ``cov`` is two-way clustered, ``cov_dk`` Driscoll–Kraay (module docstring); t and p
    use Student t with ``df_t`` degrees of freedom."""

    names: tuple[str, ...]
    params: FloatArray
    cov: FloatArray
    cov_dk: FloatArray
    nobs: int
    k_fe: int
    n_clusters: tuple[int, int]
    df_t: int
    r2_within: float

    def se(self, kind: Kind = "cluster") -> FloatArray:
        """Standard errors; NaN where a (two-way, not necessarily positive) variance is negative."""
        var = np.diag(self._cov(kind))
        out = np.full(var.shape, np.nan)
        ok = var >= 0
        out[ok] = np.sqrt(var[ok])
        return out

    def t(self, kind: Kind = "cluster") -> FloatArray:
        with np.errstate(divide="ignore", invalid="ignore"):
            return self.params / self.se(kind)

    def p_two(self, kind: Kind = "cluster") -> FloatArray:
        """Two-sided p of H0: β = 0."""
        return np.asarray(2.0 * stats.t.sf(np.abs(self.t(kind)), self.df_t), dtype=np.float64)

    def coef(self, name: str) -> float:
        return float(self.params[self._index(name)])

    def p_one(self, name: str, alternative: Literal["greater", "less"], kind: Kind = "cluster") -> float:
        """One-sided p of H0: β = 0 against β > 0 (``"greater"``) or β < 0 (``"less"``)."""
        sign = _SIDES.get(alternative)
        if sign is None:
            raise ValueError(f"alternative must be 'greater' or 'less', got {alternative!r}")
        return float(stats.t.sf(sign * self.t(kind)[self._index(name)], self.df_t))

    def table(self) -> pd.DataFrame:
        """One row per regressor: coef with the clustered se, t, p_two and the Driscoll–Kraay ones."""
        return pd.DataFrame(
            {
                "coef": self.params,
                "se": self.se("cluster"),
                "t": self.t("cluster"),
                "p_two": self.p_two("cluster"),
                "se_dk": self.se("dk"),
                "t_dk": self.t("dk"),
                "p_two_dk": self.p_two("dk"),
            },
            index=pd.Index(self.names, name="term"),
        )

    def _cov(self, kind: str) -> FloatArray:
        cov = {"cluster": self.cov, "dk": self.cov_dk}.get(kind)
        if cov is None:
            raise ValueError(f"kind must be 'cluster' or 'dk', got {kind!r}")
        return cov

    def _index(self, name: str) -> int:
        if name not in self.names:
            raise KeyError(f"{name!r} is not a regressor of this fit: {list(self.names)}")
        return self.names.index(name)


# --- estimation ------------------------------------------------------------------------------------------


def ols_fe(
    frame: pd.DataFrame,
    y: str,
    x: Sequence[str],
    *,
    fe: str | Sequence[str] | None,
    cluster: tuple[str, str] = CLUSTER,
    time: str = "session",
    dk_lags: int = DK_LAGS,
) -> OLSResult:
    """Pooled OLS of ``y`` on ``x``, absorbing one set of FE groups (the observed combinations of the ``fe``
    columns; ``None``: a constant instead), with the two-way clustered (``cluster``) and Driscoll–Kraay
    (``time``, ``dk_lags``) covariances of the module docstring."""
    if len(cluster) != 2:
        raise ValueError(f"cluster must name two columns, got {cluster!r}")
    if dk_lags < 0:
        raise ValueError(f"dk_lags must be >= 0, got {dk_lags}")
    w = _within(frame, y, x, fe, [*cluster, time])
    n, k = w.x.shape
    n_params = k + w.k_fe
    if n <= n_params:
        raise ValueError(f"{n} rows leave no residual degrees of freedom for {n_params} parameters")
    xtx = w.x.T @ w.x
    beta = _solve(xtx[None], (w.x.T @ w.y)[None])[0]
    if not np.isfinite(beta).all():
        raise ValueError(f"X'X of {list(w.names)} is numerically singular")
    resid = w.y - w.x @ beta
    scores = w.x * resid[:, None]
    bread = _inverse(xtx)
    small = (n - 1) / (n - n_params)

    c0, g0 = _codes(w.rows, [cluster[0]])
    c1, g1 = _codes(w.rows, [cluster[1]])
    if min(g0, g1) < 2:
        raise ValueError(f"two-way clustering needs >= 2 clusters in each dimension, got {g0} and {g1}")
    c01, g01 = _codes(w.rows, list(cluster))
    meat = _crv1(scores, c0, g0) + _crv1(scores, c1, g1) - _crv1(scores, c01, g01)

    tc, periods = _sorted_codes(w.rows[time])
    if len(periods) < 2:
        raise ValueError(f"Driscoll–Kraay needs >= 2 values of {time!r}, got {len(periods)}")
    meat_dk = _driscoll_kraay(scores, tc, len(periods), dk_lags)

    return OLSResult(
        names=w.names,
        params=beta,
        cov=small * _sandwich(bread, meat),
        cov_dk=small * _sandwich(bread, meat_dk),
        nobs=n,
        k_fe=w.k_fe,
        n_clusters=(g0, g1),
        df_t=min(g0, g1) - 1,
        r2_within=1.0 - float(resid @ resid) / w.sst if w.sst > 0 else math.nan,
    )


def wald(res: OLSResult, names: Sequence[str], kind: Kind = "cluster") -> tuple[float, int, float]:
    """Joint H0: the coefficients ``names`` are all 0. Returns (F = W/q, q, p) with p from F(q, df_t)."""
    idx = [res._index(name) for name in ([names] if isinstance(names, str) else names)]
    if not idx or len(set(idx)) != len(idx):
        raise ValueError(f"names must be distinct regressors, got {names!r}")
    b = res.params[idx]
    try:
        w = float(b @ np.linalg.solve(res._cov(kind)[np.ix_(idx, idx)], b))
    except np.linalg.LinAlgError:
        raise ValueError(f"the {kind} covariance of {list(names)} is singular") from None
    q = len(idx)
    return w / q, q, float(stats.f.sf(w / q, q, res.df_t))


# --- day bootstrap (§11.4) -------------------------------------------------------------------------------


def day_moments(
    frame: pd.DataFrame, y: str, x: Sequence[str], *, fe: str | Sequence[str], day: str = "session"
) -> tuple[ObjectArray, FloatArray, FloatArray]:
    """Per value of ``day`` (sorted): A_d = X̃_d'X̃_d (k × k) and b_d = X̃_d'ỹ_d (k) of ``ols_fe``'s within
    transformation (rows missing y, an x, an FE or ``day`` value are dropped). Every FE group must lie within
    one day, so that resampling whole days keeps the groups intact. Returns (days, A, b)."""
    w = _within(frame, y, x, fe, [day])
    codes, days = _sorted_codes(w.rows[day])
    if (pd.Series(codes).groupby(w.fe_codes).nunique() > 1).any():
        raise ValueError(f"fixed-effect groups of {fe!r} span several values of {day!r}")
    order = np.argsort(codes, kind="stable")
    starts = np.searchsorted(codes[order], np.arange(len(days)))
    xo, yo = w.x[order], w.y[order]
    a = np.add.reduceat(xo[:, :, None] * xo[:, None, :], starts, axis=0)
    b = np.add.reduceat(xo * yo[:, None], starts, axis=0)
    return days, np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)


def beta_from_moments(a: npt.ArrayLike, b: npt.ArrayLike, weights: npt.ArrayLike) -> FloatArray:
    """(reps, k) β̂* = solve(Σ_d w_rd A_d, Σ_d w_rd b_d) for ``weights`` (reps, n_days), e.g. the day counts
    of bootstrap draws; NaN rows where the summed matrix is singular."""
    am = np.asarray(a, dtype=np.float64)
    bm = np.asarray(b, dtype=np.float64)
    wm = np.asarray(weights, dtype=np.float64)
    if bm.ndim != 2 or am.shape != (*bm.shape, bm.shape[1]) or wm.ndim != 2 or wm.shape[1] != bm.shape[0]:
        raise ValueError(
            f"expected A (n_days, k, k), b (n_days, k), weights (reps, n_days); got {am.shape}, {bm.shape}, "
            f"{wm.shape}"
        )
    n_days, k = bm.shape
    sa = (wm @ am.reshape(n_days, k * k)).reshape(-1, k, k)
    return _solve(sa, wm @ bm)


def counts_from_indices(idx: npt.ArrayLike, n_days: int) -> IntArray:
    """(reps, n) day-index draws → (reps, n_days) counts of each day per draw."""
    ix = np.asarray(idx)
    if ix.ndim != 2 or not np.issubdtype(ix.dtype, np.integer):
        raise ValueError(f"expected a (reps, n) integer index array, got {ix.dtype} {ix.shape}")
    if ix.size and (ix.min() < 0 or ix.max() >= n_days):
        raise ValueError(f"day indices must lie in [0, {n_days})")
    reps = ix.shape[0]
    flat = (ix.astype(np.int64) + n_days * np.arange(reps, dtype=np.int64)[:, None]).ravel()
    return np.bincount(flat, minlength=reps * n_days).reshape(reps, n_days).astype(np.int64)


# --- internals -------------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _Within:
    rows: pd.DataFrame  # the complete rows (their original index)
    names: tuple[str, ...]
    y: FloatArray  # ỹ
    x: FloatArray  # X̃ (n, k)
    sst: float  # ỹ'ỹ, or Σ(y − ȳ)² without FE
    fe_codes: IntArray  # FE group of each row (all 0 without FE)
    k_fe: int


def _within(
    frame: pd.DataFrame, y: str, x: Sequence[str], fe: str | Sequence[str] | None, extra: Sequence[str]
) -> _Within:
    """The complete rows; ỹ and X̃ demeaned within the FE groups, or y and [1, X] without FE."""
    xs = [x] if isinstance(x, str) else list(x)
    fes = [] if fe is None else [fe] if isinstance(fe, str) else list(fe)
    if fe is not None and not (fes and xs):
        raise ValueError(f"fe and x must each name at least one column, got fe={fe!r}, x={xs}")
    if len(set(xs)) != len(xs) or y in xs or (fe is None and CONST in xs):
        raise ValueError(f"x must be distinct columns other than y and {CONST!r}, got {xs}")
    cols = list(dict.fromkeys([y, *xs, *fes, *extra]))
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise KeyError(f"columns not in the frame: {missing}")
    rows = frame.loc[frame[cols].notna().all(axis=1).to_numpy(dtype=bool), cols]
    n = len(rows)
    if n == 0:
        raise ValueError(f"no row has all of {cols}")
    yv = rows[y].to_numpy(dtype=np.float64)
    xv = rows[xs].to_numpy(dtype=np.float64).reshape(n, len(xs))
    if not (np.isfinite(yv).all() and np.isfinite(xv).all()):
        raise ValueError(f"{y} and {xs} must be finite")
    names: tuple[str, ...]
    if fe is None:
        names, codes, k_fe = (CONST, *xs), np.zeros(n, dtype=np.int64), 0
        yt = yv
        xt = raw = np.column_stack([np.ones(n), xv])
        sst = float(np.sum((yv - yv.mean()) ** 2))
    else:
        names, raw = tuple(xs), xv
        codes, k_fe = _codes(rows, fes)
        both = _demean(np.column_stack([yv, xv]), codes, k_fe)
        yt, xt = both[:, 0], both[:, 1:]
        sst = float(yt @ yt)
    _check_rank(xt, raw, names)
    return _Within(rows, names, yt, xt, sst, codes, k_fe)


def _check_rank(xt: FloatArray, raw: FloatArray, names: tuple[str, ...]) -> None:
    """Refuse regressors absorbed by the fixed effects (or all zero) and collinear regressors."""
    within = np.sqrt(np.sum(xt * xt, axis=0))
    scale = np.sqrt(np.sum(raw * raw, axis=0))
    gone = [nm for nm, a, s in zip(names, within, scale, strict=True) if a <= ABSORBED_RTOL * s]
    if gone:
        raise ValueError(f"no variation left in {gone} after absorbing the fixed effects")
    if np.linalg.matrix_rank(xt / within) < xt.shape[1]:
        raise ValueError(f"the regressors {list(names)} are collinear after absorbing the fixed effects")


def _codes(rows: pd.DataFrame, columns: Sequence[str]) -> tuple[IntArray, int]:
    """Dense codes 0..G−1 of the observed combinations of ``columns``, and G."""
    codes = np.zeros(len(rows), dtype=np.int64)
    n = 1
    for col in columns:
        part, uniq = pd.factorize(rows[col])
        combo, seen = pd.factorize(codes * len(uniq) + part)
        codes, n = np.asarray(combo, dtype=np.int64), len(seen)
    return codes, n


def _sorted_codes(values: pd.Series) -> tuple[IntArray, ObjectArray]:
    """Codes 0..T−1 of the sorted distinct values, and those values."""
    codes, uniq = pd.factorize(values, sort=True)
    return np.asarray(codes, dtype=np.int64), np.asarray(uniq, dtype=object)


def _sums(values: FloatArray, codes: IntArray, n_groups: int) -> FloatArray:
    """(G, m) sums of the (n, m) ``values`` within each code."""
    return np.column_stack([np.bincount(codes, weights=v, minlength=n_groups) for v in values.T])


def _demean(values: FloatArray, codes: IntArray, n_groups: int) -> FloatArray:
    """(n, m) ``values`` minus their group means."""
    counts = np.bincount(codes, minlength=n_groups).astype(np.float64)
    return values - (_sums(values, codes, n_groups) / counts[:, None])[codes]


def _crv1(scores: FloatArray, codes: IntArray, n_groups: int) -> FloatArray:
    """G/(G − 1) · S_P for the partition ``codes`` (the (N − 1)/(N − K) factor is applied once, later)."""
    u = _sums(scores, codes, n_groups)
    return n_groups / (n_groups - 1) * (u.T @ u)


def _driscoll_kraay(scores: FloatArray, codes: IntArray, n_periods: int, lags: int) -> FloatArray:
    """T/(T − 1) · Bartlett HAC of the per-period score sums (rows of ``_sums`` are the sorted periods)."""
    u = _sums(scores, codes, n_periods)
    s = u.T @ u
    for lag in range(1, min(lags, n_periods - 1) + 1):
        gamma = u[lag:].T @ u[:-lag]
        s += (1.0 - lag / (lags + 1.0)) * (gamma + gamma.T)
    return n_periods / (n_periods - 1) * s


def _sandwich(bread: FloatArray, meat: FloatArray) -> FloatArray:
    v = bread @ meat @ bread
    return (v + v.T) / 2


def _inverse(a: FloatArray) -> FloatArray:
    """Inverse of a positive definite matrix, scaled to unit diagonal first."""
    s = np.outer(1.0 / np.sqrt(np.diag(a)), 1.0 / np.sqrt(np.diag(a)))
    inv = np.linalg.inv(a * s) * s
    return (inv + inv.T) / 2


def _solve(a: FloatArray, b: FloatArray) -> FloatArray:
    """Row-wise solve(a_r, b_r) for a (r, k, k) and b (r, k), scaled to unit diagonal; NaN rows where a_r is
    singular (smallest singular value <= k·eps times the largest, numpy's ``matrix_rank`` tolerance)."""
    r, k = b.shape
    out = np.full((r, k), np.nan)
    diag = np.diagonal(a, axis1=1, axis2=2)
    pos = np.isfinite(a).all(axis=(1, 2)) & np.isfinite(b).all(axis=1) & (diag > 0).all(axis=1)
    if not pos.any():
        return out
    s = 1.0 / np.sqrt(diag[pos])
    m = a[pos] * s[:, :, None] * s[:, None, :]
    sv = np.linalg.svd(m, compute_uv=False)
    ok = sv[:, -1] > sv[:, 0] * k * np.finfo(np.float64).eps
    rows = np.flatnonzero(pos)[ok]
    if rows.size:
        out[rows] = s[ok] * np.linalg.solve(m[ok], (b[rows] * s[ok])[:, :, None])[:, :, 0]
    return out
