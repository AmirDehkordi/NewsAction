"""Leave-one-company-out sector returns (PREREG §5.2; PRD NA-01 S3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from newsaction.panel import sector

IDX = pd.DatetimeIndex(pd.bdate_range("2025-01-02", periods=2), name="session")


def _setup(n_companies: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Companies 1..n in one sector (company 1 has two classes: symbols 1 and 101) + one other sector."""
    syms = [*range(1, n_companies + 1), 101, 900]
    r = pd.DataFrame([[0.01 * s if s < 900 else 0.5 for s in syms]] * 2, index=IDX, columns=syms)
    r.loc[IDX[0], 101] = 0.02  # the second class of company 1 moves with it
    sec = pd.DataFrame([["IT"] * (n_companies + 1) + ["Energy"]] * 2, index=IDX, columns=syms)
    pool = pd.DataFrame(True, index=IDX, columns=syms)
    pool[101] = False  # only the representative class enters the pool
    company = pd.Series({**{s: s for s in range(1, n_companies + 1)}, 101: 1, 900: 900})
    return r, sec, pool, company


def test_loo_excludes_the_own_company_and_counts_companies_once() -> None:
    r, sec, pool, company = _setup(7)
    loo, n = sector.loo_sector_return(r, sec, pool, company)
    others = [0.01 * s for s in range(2, 8)]
    assert loo.loc[IDX[0], 1] == pytest.approx(np.mean(others))
    assert loo.loc[IDX[0], 101] == pytest.approx(np.mean(others))  # same company -> same factor
    assert loo.loc[IDX[0], 3] == pytest.approx(np.mean([0.01 * s for s in (1, 2, 4, 5, 6, 7)]))
    assert n.loc[IDX[0], 1] == 6 and n.loc[IDX[0], 3] == 6
    assert np.isnan(loo.loc[IDX[0], 900])  # no other company in its sector


def test_loo_needs_five_other_companies() -> None:
    r, sec, pool, company = _setup(5)  # four others
    loo, n = sector.loo_sector_return(r, sec, pool, company)
    assert n.loc[IDX[0], 1] == 4 and np.isnan(loo.loc[IDX[0], 1])
    r6, sec6, pool6, company6 = _setup(6)
    assert np.isfinite(sector.loo_sector_return(r6, sec6, pool6, company6)[0].loc[IDX[0], 1])


def test_missing_returns_do_not_count() -> None:
    r, sec, pool, company = _setup(7)
    r.loc[IDX[0], 7] = np.nan
    loo, n = sector.loo_sector_return(r, sec, pool, company)
    assert n.loc[IDX[0], 1] == 5 and loo.loc[IDX[0], 1] == pytest.approx(
        np.mean([0.01 * s for s in range(2, 7)])
    )
