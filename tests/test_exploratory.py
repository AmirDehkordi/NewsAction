"""NA-12, exploratory "where the D0 signal lives" (operator request after unblinding; no hypothesis).

- the section waits for the unblinding;
- every analysis uses the frozen sample (the embargo is left out) and daily IC;
- the earnings split follows the frame's ``earnings`` flag, the tier split the ``tier`` column;
- the month F test is the one-way ANOVA of the daily ICs on calendar month, with the implied monthly SE;
- the per-company null shuffles the signal within each company, keeps companies with >= 15 events, and is
  reproducible from its seed;
- the market-state terciles split the split's sessions outside the embargo.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from scipy import stats  # type: ignore[import-untyped, unused-ignore]

from newsaction.analysis import exploratory as ex
from newsaction.analysis import spec
from newsaction.paths import Layout

CFG = spec.load_config()


def _frame(n_sessions: int = 30, per_day: int = 12, seed: int = 0) -> pd.DataFrame:
    """A D0 frame: on earnings rows the signal is z_cc, on the rest −z_cc; the embargo rows the reverse."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_sessions):
        for j in range(per_day):
            z = float(rng.normal())
            rows.append(
                {
                    "event_id": f"e{d}_{j}",
                    "company_id": j,
                    "session": date(2026, 1, 5) + timedelta(days=d),
                    "split": "test",
                    "embargo": d < 5,
                    "earnings": float(j % 2),
                    "tier": ("top100", "mid", "rest")[j % 3],
                    "z_cc": z,
                    "z_on": z,
                    "z_id": float(rng.normal()),
                }
            )
    f = pd.DataFrame(rows)
    sign = np.where(f["earnings"] == 1, 1.0, -1.0) * np.where(f["embargo"], -1.0, 1.0)
    f["sig"] = sign * f["z_cc"]
    return f


def test_the_section_waits_for_the_unblinding(tmp_layout: Layout) -> None:
    with pytest.raises(ex.ExploratoryError, match="unblinding"):
        ex.run(tmp_layout)


def test_earnings_follows_the_flag_outside_the_embargo() -> None:
    r = ex.earnings(_frame(), "test", "sig", CFG)
    assert r["earnings"]["ic_z_cc"] == pytest.approx(1.0)
    assert r["rest"]["ic_z_cc"] == pytest.approx(-1.0)
    assert r["earnings"]["ic_z_cc_days"] == 25  # the 5 embargo sessions are left out
    assert r["difference"]["z_cc"]["mean"] == pytest.approx(2.0)
    assert r["difference"]["z_cc"]["n_days"] == 25


def test_tier_follows_the_tier_column() -> None:
    f = _frame(per_day=15)  # 5 a tier: the frozen minimum of names a session
    f["sig"] = np.where(f["tier"] == "mid", f["z_cc"], -f["z_cc"])
    r = ex.tier(f, "test", "sig", CFG)
    assert r["mid"]["ic_z_cc"] == pytest.approx(1.0)
    assert r["top100"]["ic_z_cc"] == pytest.approx(-1.0)
    assert r["rest"]["ic_z_cc"] == pytest.approx(-1.0)


def test_month_effects_is_the_one_way_anova_of_the_daily_ics() -> None:
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2026-01-05", "2026-04-30")
    daily = pd.Series(rng.normal(0.02, 0.2, len(days)), index=[d.date() for d in days])
    daily[[d.month == 3 for d in daily.index]] += 0.3
    r = ex.month_effects(daily, CFG)
    groups = [g.to_numpy() for _, g in daily.groupby([d.month for d in daily.index])]
    f, p = stats.f_oneway(*groups)
    assert r["f"] == pytest.approx(f) and r["p"] == pytest.approx(p) and r["p"] < 0.01
    ms_within = sum(((g - g.mean()) ** 2).sum() for g in groups) / (len(daily) - len(groups))
    assert r["se_month_iid"] == pytest.approx(math.sqrt(ms_within / (len(daily) / len(groups))))
    assert [m["month"] for m in r["months"]] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert r["df"] == [3, len(daily) - 4]


def test_the_company_null_shuffles_within_company_and_is_seeded() -> None:
    f = _frame()
    f["sig"] = f["z_cc"]  # every company's correlation is 1 outside the embargo
    f.loc[f["embargo"], "sig"] = -f["z_cc"]
    small = f.loc[f["company_id"] == 0].head(10).assign(company_id=99, sig=lambda d: -d["z_cc"])
    g = pd.concat([f, small.assign(embargo=False)], ignore_index=True)
    r = ex.company_spread(g, "sig", CFG, split="test", draws=50)
    assert r["n_companies"] == 12  # company 99 has 10 events (< 15)
    assert r["mean"] == pytest.approx(1.0) and r["sd"] == pytest.approx(0.0, abs=1e-12)
    assert r["null_sd_mean"] > 0.1
    assert r == ex.company_spread(g, "sig", CFG, split="test", draws=50)
    other = ex.company_spread(g, "sig", CFG, split="test", draws=50, seed=7)
    assert other["null_sd_mean"] != r["null_sd_mean"]


def test_market_terciles_split_the_sessions_outside_the_embargo() -> None:
    sessions = [date(2026, 1, 5) + timedelta(days=d) for d in range(12)]
    days = pd.DataFrame(
        [
            {"session": s, "split": "test", "embargo": i < 3, "z_cc": z * (1 + i)}
            for i, s in enumerate(sessions)
            for z in (-1.0, 0.0, 1.0)
        ]
    )
    panel = pd.DataFrame({"session": sessions, "r_spy_cc": [(-1) ** i * 0.001 * i for i in range(12)]})
    st = ex.day_states(days, panel, "test")
    assert len(st) == 9 and set(st["sd_z_cc_tercile"]) == {"low", "mid", "high"}
    assert (
        st.loc[sessions[11], "sd_z_cc_tercile"] == "high" and st.loc[sessions[3], "abs_spy_tercile"] == "low"
    )
    daily = pd.Series([0.0] * 3 + [0.1] * 3 + [0.2] * 3 + [0.5] * 3, index=sessions)
    r = ex.by_tercile(daily, st, CFG)
    assert r["sd_z_cc"]["high"]["mean"] == pytest.approx(0.5)
    assert r["sd_z_cc"]["low"]["n_days"] == 3
