"""The PREREG §11.3 regression engine (``analysis.inference``) against statsmodels on the same rows with
explicit day × tier dummies: estimates, two-way clustered (CRV1) and Driscoll–Kraay covariances, t / F
inference with df_t, and the day moments of the §11.4 bootstrap."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from newsaction.analysis.inference import (
    OLSResult,
    beta_from_moments,
    counts_from_indices,
    day_moments,
    ols_fe,
    wald,
)

FE = ("session", "tier")
X = ["n_hat", "g"]
B_TRUE, C_TRUE = 0.3, -0.2  # H2: y = a + b·N̂ + c·G + day × tier FE + ε, b > 0, c < 0

Fitted = tuple[pd.DataFrame, OLSResult, Any, Any, slice]


def make_panel(
    seed: int, n_days: int = 90, firms_per_tier: int = 45, nan_share: float = 0.01
) -> pd.DataFrame:
    """Unbalanced panel (70% of firm-days) with day × tier effects, firm effects and firm-specific loadings on
    day shocks in x and in the error (so both clusterings matter and the day × tier FE do not absorb them),
    three singleton day × tier groups, and NaNs in y, x, tier and company_id. Fewer days than firms, as in
    the pre-registered panels."""
    rng = np.random.default_rng(seed)
    n_firms = 3 * firms_per_tier
    day, firm = np.divmod(np.arange(n_days * n_firms), n_firms)
    keep = rng.random(day.size) < 0.7
    day, firm = day[keep], firm[keep]
    tier = firm // firms_per_tier + 1
    n = day.size
    load = rng.normal(1.0, 0.7, n_firms)
    shock_x, shock_e = rng.normal(size=n_days), rng.normal(size=n_days)
    firm_x, firm_e = rng.normal(size=n_firms), rng.normal(size=n_firms)
    n_hat = rng.normal(size=n) + 0.5 * firm_x[firm] + 0.8 * load[firm] * shock_x[day]
    g = 0.4 * n_hat + rng.normal(size=n) + 0.5 * load[firm] * shock_x[day]
    eps = rng.normal(size=n) + 0.6 * firm_e[firm] + 0.8 * load[firm] * shock_e[day]
    cell = rng.normal(size=(n_days, 4))[day, tier]
    sessions = pd.bdate_range("2025-07-01", periods=n_days)
    df = pd.DataFrame(
        {
            "session": sessions[day],
            "company_id": [f"F{f:03d}" for f in firm],
            "tier": tier.astype(float),
            "n_hat": n_hat,
            "g": g,
            "y": B_TRUE * n_hat + C_TRUE * g + cell + eps,
        }
    )
    for d, t in ((5, 1), (17, 2), (40 % n_days, 3)):  # singleton day × tier groups
        df = df.drop(df.index[(df["session"] == sessions[d]) & (df["tier"] == t)][1:])
    for col in ("y", "n_hat", "g", "tier", "company_id"):
        df.loc[rng.random(len(df)) < nan_share, col] = np.nan
    return df.reset_index(drop=True)


def sm_fits(df: pd.DataFrame, xs: list[str], fe: tuple[str, ...] | None) -> tuple[Any, Any, slice]:
    """statsmodels OLS on the complete rows with explicit FE dummies: (two-way cluster fit, Driscoll–Kraay
    fit, slice of the x coefficients). ``use_t=True`` (statsmodels' robust default is the normal). The rows
    are in descending session order because statsmodels' nw-groupsum df is the number of descents of ``time``
    in row order: T − 1 here, which is df_t since there are fewer sessions than firms."""
    d = df.dropna(subset=["y", *xs, *(fe or ()), "session", "company_id"])
    d = d.sort_values(["session", "company_id"], ascending=[False, True])
    parts = [np.ones((len(d), 1)), d[xs].to_numpy(dtype=float)]
    if fe:
        cell = d[list(fe)].astype(str).agg("|".join, axis=1)
        parts.append(pd.get_dummies(cell, drop_first=True, dtype=float).to_numpy())
    model = sm.OLS(d["y"].to_numpy(dtype=float), np.column_stack(parts))
    groups = np.column_stack([pd.factorize(d["session"])[0], pd.factorize(d["company_id"])[0]])
    time = pd.factorize(d["session"], sort=True)[0]  # codes 0..T−1 of the sorted sessions
    cl = model.fit(cov_type="cluster", cov_kwds={"groups": groups}, use_t=True)
    dk = model.fit(cov_type="nw-groupsum", cov_kwds={"time": time, "maxlags": 5}, use_t=True)
    return cl, dk, slice(1, 1 + len(xs))


@pytest.fixture(scope="module")
def fitted() -> Fitted:
    df = make_panel(0)
    cl, dk, sl = sm_fits(df, X, FE)
    return df, ols_fe(df, "y", X, fe=FE), cl, dk, sl


# statsmodels' bse takes the square root of every dummy's two-way variance too, and some are negative (CGM's
# V₀ + V₁ − V₀₁ need not be positive semi-definite).
@pytest.mark.filterwarnings("ignore:invalid value encountered in sqrt:RuntimeWarning")
def test_matches_statsmodels_with_day_tier_dummies(fitted: Fitted) -> None:
    df, res, cl, dk, sl = fitted
    rows = df.dropna(subset=["y", *X, *FE, "company_id"])
    sizes = rows.groupby(list(FE)).size()
    assert (sizes == 1).sum() >= 3  # singleton FE groups stay in
    assert res.names == tuple(X)
    assert res.nobs == len(rows) == cl.nobs
    assert res.k_fe == len(sizes) == cl.params.size - len(X)  # const + (k_fe − 1) dummies
    assert res.n_clusters == (rows["session"].nunique(), rows["company_id"].nunique()) == tuple(cl.n_groups)
    assert res.df_t == cl.df_resid_inference == dk.df_resid_inference == rows["session"].nunique() - 1
    np.testing.assert_allclose(res.params, cl.params[sl], rtol=1e-8)
    for kind, cov, ref in (("cluster", res.cov, cl), ("dk", res.cov_dk, dk)):
        ref_cov = ref.cov_params()[sl, sl]
        np.testing.assert_allclose(cov, ref_cov, rtol=1e-8, atol=1e-8 * np.abs(ref_cov).max())
        np.testing.assert_allclose(res.se(kind), ref.bse[sl], rtol=1e-8)
        np.testing.assert_allclose(res.t(kind), ref.tvalues[sl], rtol=1e-8)
        np.testing.assert_allclose(res.p_two(kind), ref.pvalues[sl], rtol=1e-6)
    demeaned = rows["y"] - rows.groupby(list(FE))["y"].transform("mean")
    assert res.r2_within == pytest.approx(1 - cl.ssr / float((demeaned**2).sum()), rel=1e-8)


def test_no_fixed_effects_has_const_and_matches_plain_ols() -> None:
    df = make_panel(1, n_days=40, firms_per_tier=20)
    res = ols_fe(df, "y", X, fe=None)
    cl, dk, _ = sm_fits(df, X, None)
    assert res.names == ("const", *X)
    assert res.k_fe == 0
    assert res.nobs == cl.nobs
    np.testing.assert_allclose(res.params, cl.params, rtol=1e-8)
    for kind, ref in (("cluster", cl), ("dk", dk)):
        np.testing.assert_allclose(res.se(kind), ref.bse, rtol=1e-8)
        np.testing.assert_allclose(res.p_two(kind), ref.pvalues, rtol=1e-6)
    assert res.r2_within == pytest.approx(cl.rsquared, rel=1e-8)


def test_recovers_planted_signs_one_sided() -> None:
    res = ols_fe(make_panel(2), "y", X, fe=FE)
    b, c = res.coef("n_hat"), res.coef("g")
    se = dict(zip(res.names, res.se(), strict=True))
    assert b > 0 > c
    assert abs(b - B_TRUE) < 4 * se["n_hat"]
    assert abs(c - C_TRUE) < 4 * se["g"]
    for kind in ("cluster", "dk"):
        assert res.p_one("n_hat", "greater", kind) < 0.01
        assert res.p_one("g", "less", kind) < 0.01
    assert res.p_one("n_hat", "less") > 0.99
    assert res.p_one("n_hat", "greater") == pytest.approx(res.p_two()[0] / 2, rel=1e-9)
    table = res.table()
    assert list(table.columns) == ["coef", "se", "t", "p_two", "se_dk", "t_dk", "p_two_dk"]
    assert list(table.index) == X
    assert table.loc["g", "coef"] == c
    assert table.loc["g", "se_dk"] == res.se("dk")[1]


def test_common_daily_shock_inflates_clustered_se() -> None:
    rng = np.random.default_rng(3)
    n_days, n_firms = 60, 80
    day, firm = np.divmod(np.arange(n_days * n_firms), n_firms)
    x = rng.normal(size=n_days)[day] + rng.normal(size=day.size)
    y = 0.1 * x + rng.normal(size=n_days)[day] + rng.normal(size=day.size)
    df = pd.DataFrame({"session": day, "company_id": firm, "x": x, "y": y})
    res = ols_fe(df, "y", ["x"], fe=None)
    iid = sm.OLS(y, sm.add_constant(x)).fit().bse[1]
    assert res.se("cluster")[1] > 2 * iid
    assert res.se("dk")[1] > 2 * iid


def test_wald_matches_statsmodels_f_test(fitted: Fitted) -> None:
    _, res, cl, dk, sl = fitted
    r = np.zeros((2, cl.params.size))
    r[0, sl.start] = r[1, sl.start + 1] = 1.0
    for kind, ref in (("cluster", cl), ("dk", dk)):
        f, q, p = wald(res, X, kind)
        ft = ref.f_test(r)
        assert (q, ft.df_num, ft.df_denom) == (2, 2, res.df_t)
        assert f == pytest.approx(float(np.squeeze(ft.fvalue)), rel=1e-8)
        assert p == pytest.approx(float(np.squeeze(ft.pvalue)), rel=1e-6)
    f1, q1, p1 = wald(res, ["g"])  # one restriction: F = t², same p as the two-sided t test
    assert q1 == 1
    assert f1 == pytest.approx(res.t()[1] ** 2, rel=1e-12)
    assert p1 == pytest.approx(res.p_two()[1], rel=1e-9)


def test_day_moments_reproduce_ols_fe_and_duplicated_days() -> None:
    df = make_panel(4, n_days=40, firms_per_tier=20).dropna()  # ols_fe also drops rows missing company_id
    res = ols_fe(df, "y", X, fe=FE)
    days, a, b = day_moments(df, "y", X, fe=FE)
    assert list(days) == sorted(df["session"].unique())
    assert a.shape == (len(days), 2, 2)
    assert b.shape == (len(days), 2)
    np.testing.assert_allclose(beta_from_moments(a, b, np.ones((1, len(days))))[0], res.params, rtol=1e-10)

    idx = np.random.default_rng(5).integers(0, len(days), size=(4, len(days)))
    counts = counts_from_indices(idx, len(days))
    assert counts.shape == (4, len(days))
    assert (counts.sum(axis=1) == len(days)).all()
    assert all((counts[r] == np.bincount(idx[r], minlength=len(days))).all() for r in range(4))
    betas = beta_from_moments(a, b, counts)
    by_day = dict(list(df.groupby("session")))
    for draw, beta in zip(idx, betas, strict=True):
        dup = pd.concat([by_day[days[j]] for j in draw], ignore_index=True)  # whole days, duplicated
        np.testing.assert_allclose(beta, ols_fe(dup, "y", X, fe=FE).params, rtol=1e-9)

    some = beta_from_moments(a, b, np.vstack([np.zeros(len(days)), np.ones(len(days))]))
    assert np.isnan(some[0]).all()  # no day drawn: singular
    np.testing.assert_allclose(some[1], res.params, rtol=1e-10)


def test_statsmodels_dk_df_depends_on_row_order() -> None:
    """Why the Driscoll–Kraay p-values use df_t: statsmodels' nw-groupsum df counts the descents of ``time``
    in row order (0, so p = NaN, for rows in time order; T − 1 in descending time order)."""
    df = make_panel(7, n_days=30, firms_per_tier=15).dropna()
    time = pd.factorize(df["session"], sort=True)[0]
    exog = sm.add_constant(df[X].to_numpy(dtype=float))
    fits = {}
    for name, order in (("asc", np.argsort(time, kind="stable")), ("desc", np.argsort(-time, kind="stable"))):
        kwds = {"time": time[order], "maxlags": 5}
        model = sm.OLS(df["y"].to_numpy(dtype=float)[order], exog[order])
        fits[name] = model.fit(cov_type="nw-groupsum", cov_kwds=kwds, use_t=True)
    assert fits["asc"].df_resid_inference == 0
    assert np.isnan(fits["asc"].pvalues).all()
    assert fits["desc"].df_resid_inference == 30 - 1
    np.testing.assert_allclose(fits["asc"].bse, fits["desc"].bse, rtol=1e-10)
    np.testing.assert_allclose(ols_fe(df, "y", X, fe=None).se("dk"), fits["desc"].bse, rtol=1e-8)


def test_guards() -> None:
    df = make_panel(6, n_days=20, firms_per_tier=10)
    with pytest.raises(KeyError, match="nope"):
        ols_fe(df, "y", ["n_hat", "nope"], fe=FE)
    with pytest.raises(KeyError, match="firm"):
        ols_fe(df, "y", X, fe=FE, cluster=("session", "firm"))
    with pytest.raises(ValueError, match="span"):
        day_moments(df, "y", X, fe="tier")  # a tier group spans every day
    df["day_mean_g"] = df.groupby("session")["g"].transform("mean")
    with pytest.raises(ValueError, match="no variation"):
        ols_fe(df, "y", ["n_hat", "day_mean_g"], fe=FE)  # constant within day × tier: absorbed
    with pytest.raises(ValueError, match="clusters"):
        ols_fe(df[df["session"] == df["session"].iloc[0]], "y", X, fe="tier")
    res = ols_fe(df, "y", X, fe=FE)
    with pytest.raises(KeyError):
        res.coef("nope")
    with pytest.raises(ValueError, match="alternative"):
        res.p_one("g", "two-sided")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="kind"):
        res.se("hac")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="distinct"):
        wald(res, ["g", "g"])
    with pytest.raises(ValueError):
        counts_from_indices(np.array([[0, 3]]), 3)
    with pytest.raises(ValueError):
        beta_from_moments(np.zeros((3, 2, 2)), np.zeros((3, 2)), np.ones((1, 4)))
