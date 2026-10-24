"""Targets, the convergence ladder, purge, reactions and placebo (PREREG §4.1, §5.5-5.8, A1.2;
PRD NA-01 S6, AC7, AC9)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.config import load_splits
from newsaction.panel import reactions, targets

SEED = 2026


def _synthetic_panel(days: list[date], n_sym: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for sid in range(1, n_sym + 1):
        for d in days:
            rows.append(
                {
                    "session": d,
                    "symbol_id": sid,
                    "ar_cc": rng.normal(0, 0.01),
                    "ar_on": rng.normal(0, 0.005),
                    "ar_id": rng.normal(0, 0.008),
                    "sigma_cc": 0.01,
                    "sigma_on": 0.005,
                    "sigma_id": 0.008,
                    "z_id": 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_ladder_identities_and_purge_synthetic() -> None:
    split_end = load_splits().splits["val_a"].end
    days = calendar.sessions(date(2025, 6, 2), date(2025, 10, 31))
    p = _synthetic_panel(days)
    out = targets.compute_targets(p, days).set_index(["session", "symbol_id"])
    g = p.set_index(["session", "symbol_id"])
    t = days[days.index(date(2025, 7, 15))]
    i = days.index(t)
    ar = [g.at[(days[i + j], 1), "ar_cc"] for j in range(0, 21)]
    row = out.loc[(t, 1)]
    assert row["car_lvl_c5"] == pytest.approx(sum(ar[:6]) / 0.01, abs=1e-12)
    assert row["e5_lvl"] == pytest.approx(sum(ar[:5]) / 0.01, abs=1e-12)
    assert row["car_lvl_o0"] == pytest.approx(g.at[(t, 1), "ar_on"] / 0.01, abs=1e-12)
    assert row["e5"] == pytest.approx(sum(ar[:5]) / (0.01 * np.sqrt(5)), abs=1e-12)
    y2 = g.at[(days[i + 1], 1), "ar_id"] + sum(ar[2:6])
    assert row["y2"] == pytest.approx(y2 / np.sqrt(0.008**2 + 4 * 0.01**2), abs=1e-12)
    assert row["ar_c0_o1"] == pytest.approx(g.at[(days[i + 1], 1), "ar_on"], abs=1e-15)
    assert row["fwd_lvl_o1_c5"] == pytest.approx(y2 / 0.01, abs=1e-12)
    assert row["split"] == "val_a"
    # purge: horizons crossing the end of val-A are NaN within val-A
    last = (
        days.index(split_end) if split_end in days else max(j for j, d in enumerate(days) if d <= split_end)
    )
    near = out.loc[(days[last - 3], 1)]
    assert np.isnan(near["car_lvl_c5"]) and np.isfinite(near["car_lvl_c2"]) and np.isnan(near["y2"])
    assert np.isfinite(out.loc[(days[last], 1), "car_lvl_c0"]) and np.isnan(
        out.loc[(days[last], 1), "car_lvl_c1"]
    )


def test_delisting_holds_the_last_price() -> None:
    days = calendar.sessions(date(2025, 1, 2), date(2025, 3, 31))
    p = _synthetic_panel(days, n_sym=2)
    stop = days[30]
    p.loc[(p["symbol_id"] == 2) & (p["session"] > stop), ["ar_cc", "ar_on", "ar_id"]] = np.nan
    out = targets.compute_targets(p, days).set_index(["session", "symbol_id"])
    g = p.set_index(["session", "symbol_id"])
    t = days[27]
    expect = sum(g.at[(days[j], 2), "ar_cc"] for j in range(27, 31)) / 0.01  # t .. last traded session
    assert out.loc[(t, 2), "car_lvl_c5"] == pytest.approx(expect, abs=1e-12)
    assert bool(out.loc[(t, 2), "delist_within_c20"]) and not bool(out.loc[(t, 1), "delist_within_c20"])


def test_gap_inside_a_horizon_is_nan_not_zero() -> None:
    days = calendar.sessions(date(2025, 1, 2), date(2025, 3, 31))
    p = _synthetic_panel(days)
    p.loc[(p["symbol_id"] == 1) & (p["session"] == days[12]), "ar_cc"] = np.nan  # a halt, not a delisting
    out = targets.compute_targets(p, days).set_index(["session", "symbol_id"])
    assert np.isnan(out.loc[(days[10], 1), "car_lvl_c5"]) and np.isfinite(
        out.loc[(days[13], 1), "car_lvl_c5"]
    )


def test_build_targets_selects_the_requested_split() -> None:
    days = calendar.sessions(date(2025, 6, 2), date(2025, 7, 31))
    out = targets.build_targets(_synthetic_panel(days), "val_a")
    assert set(out["split"]) == {"val_a"} and min(out["session"]) == date(2025, 7, 1)
    with pytest.raises(ValueError, match="unknown period"):
        targets.build_targets(_synthetic_panel(days), "val_c")


def test_d2_reaction_is_z_cc_and_its_level_version() -> None:
    p = pd.DataFrame(
        {
            "session": [date(2025, 3, 3)] * 2,
            "symbol_id": [1, 2],
            "ar_cc": [0.03, 0.2],
            "sigma_cc": [0.01, 0.01],
            "r_cc": [0.04, 0.21],
            "r_spy_cc": [0.01, 0.01],
            "z_vol": [1.0, 2.0],
        }
    )
    g = reactions.build_reactions(p, "public", "D2")
    assert g["g_d2_lvl"].tolist() == pytest.approx([3.0, 20.0])
    assert g["g_d2"].tolist() == pytest.approx([3.0, 10.0])  # clipped like z_cc


def test_placebo_helper() -> None:
    ev = pd.DataFrame({"c": [True, False, False, False, False, False, False]})
    assert targets.no_event_window(ev, lookback=5)["c"].tolist() == [False] * 6 + [True]
    df = pd.DataFrame({"session": [date(2025, 3, 3)] * 3, "tier": ["mid"] * 3, "y": [1.0, 2.0, 9.0]})
    means = targets.placebo_means(df, ["y"], pd.Series([True, True, False]))
    adj = targets.placebo_adjust(df, ["y"], means)
    assert adj["y_placebo"].tolist() == [1.5] * 3 and adj["y_adj"].tolist() == [-0.5, 0.5, 7.5]


# --- integration (AC9, AC7) --------------------------------------------------------------------------


def test_ac9_convergence_ladder_on_20_random_public_events(panel_public: pd.DataFrame) -> None:
    p = panel_public.set_index(["symbol_id", "session"]).sort_index()
    cand = panel_public[panel_public["member"] & panel_public["car_lvl_c5"].notna()]
    events = cand.sample(20, random_state=SEED)
    for rec in events.to_dict("records"):
        sid, t = rec["symbol_id"], rec["session"]
        nxt = calendar.sessions(t, calendar.next_session(calendar.next_session(t)))
        horizon = [t]
        while len(horizon) < 6:
            horizon.append(calendar.next_session(horizon[-1]))
        ar = [float(p.at[(sid, d), "ar_cc"]) for d in horizon]
        assert rec["car_lvl_c5"] == pytest.approx(sum(ar) / rec["sigma_cc"], abs=1e-9)
        assert rec["car_lvl_o0"] == pytest.approx(rec["ar_on"] / rec["sigma_cc"], abs=1e-9)
        assert len(nxt) == 3


def test_ac9_c20_rung_is_nan_when_t_plus_20_crosses_the_split_end(panel_public: pd.DataFrame) -> None:
    splits = load_splits().splits
    for name in ("train", "val_a", "val_b"):
        end = splits[name].end
        days = calendar.sessions(splits[name].start, end)
        late = set(days[-20:])
        rows = panel_public[panel_public["session"].isin(late)]
        assert rows["car_lvl_c20"].isna().all(), name
        early = panel_public[panel_public["session"] == days[-21]]
        assert early["car_lvl_c20"].notna().any(), name


def test_ac7_median_r2_in_band(panel_public: pd.DataFrame) -> None:
    p = panel_public[(panel_public["session"] >= date(2024, 7, 1)) & panel_public["member"]]
    r2 = []
    for _, g in p.groupby("symbol_id"):
        g = g.dropna(subset=["r_cc", "r_spy_cc", "r_sec_cc"])
        if len(g) < 120:
            continue
        x = np.column_stack([np.ones(len(g)), g["r_spy_cc"], g["r_sec_cc"] - g["r_spy_cc"]])
        y = g["r_cc"].to_numpy()
        e = y - x @ np.linalg.lstsq(x, y, rcond=None)[0]
        r2.append(1 - e.var() / y.var())
    med = float(np.median(r2))
    assert 0.30 <= med <= 0.40, med
