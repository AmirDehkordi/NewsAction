"""Material / delayed-reaction labels (PREREG §6.7-6.8; PRD NA-03 S1)."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.events import load_events_config
from newsaction.events.labels import LabelError, assert_public, compute_labels, embargo_flags
from newsaction.paths import ROOT

CFG = load_events_config().label
SIG = 0.02


def _rows(**cols: list[float]) -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    base = {
        "z_on": [0.0] * n,
        "z_vol": [0.0] * n,
        "ar_cc": [0.0] * n,
        "sigma_cc": [SIG] * n,
        "car6_z": [0.0] * n,
    }
    base.update(cols)
    return pd.DataFrame(base)


def _car6_for(ar_t: float, later_sum: float) -> float:
    return (ar_t + later_sum) / (SIG * math.sqrt(6))


def test_material_components() -> None:
    df = _rows(
        z_on=[2.5, -2.0, 0.2, 0.1, 0.3, 1.9],
        car6_z=[0.0, 0.0, 2.1, -2.0, 0.0, 1.99],
        z_vol=[0.0, 0.0, 0.0, 0.0, 2.0, 1.99],
    )
    lab = compute_labels(df, CFG)
    assert lab["material"].tolist() == [True, True, True, True, True, False]
    assert lab["material_on"].tolist() == [True, True, False, False, False, False]
    assert lab["material_car"].tolist() == [False, False, True, True, False, False]
    assert lab["material_vol"].tolist() == [False, False, False, False, True, False]


def test_same_day_close_to_close_move_alone_is_not_material() -> None:
    """|z_cc,t| ≥ 2 is NOT a material criterion; the six-day CAR is (PREREG §6.7)."""
    # a +3σ close-to-close move whose overnight part is small and that fully reverses by t+5
    ar_t = 3 * SIG
    df = _rows(z_on=[0.5], ar_cc=[ar_t], car6_z=[_car6_for(ar_t, -ar_t)], z_vol=[1.0])
    df["z_cc"] = 3.0
    lab = compute_labels(df, CFG)
    assert lab["material"].tolist() == [False]


def test_delayed_reaction() -> None:
    later = 2.1 * SIG * math.sqrt(5)  # |Σ_{j=1..5} AR| / (σ√5) = 2.1
    df = _rows(
        z_on=[0.5, 0.99, 1.0, 0.5, -0.2],
        ar_cc=[0.001, 0.0, 0.0, 0.0, -0.002],
        car6_z=[
            _car6_for(0.001, later),
            _car6_for(0.0, -later),
            _car6_for(0.0, later),
            _car6_for(0.0, 1.9 * SIG * math.sqrt(5)),
            _car6_for(-0.002, later),
        ],
    )
    lab = compute_labels(df, CFG)
    assert lab["car_delayed_z"].round(9).tolist()[0] == pytest.approx(2.1)
    assert lab["delayed"].tolist() == [True, True, False, False, True]
    # √6 vs √5 scaling: a 2.1σ delayed move is only 1.94σ over six days, so not every delayed day is
    # material; a 2.5σ one is (2.28σ over six days)
    assert not bool(lab["material"].iloc[0])
    big = 2.5 * SIG * math.sqrt(5)
    lab2 = compute_labels(_rows(z_on=[0.5], ar_cc=[0.001], car6_z=[_car6_for(0.001, big)]), CFG)
    assert bool(lab2["delayed"].iloc[0]) and bool(lab2["material"].iloc[0])


def test_missing_inputs_give_missing_labels() -> None:
    df = _rows(z_on=[3.0, 0.0], car6_z=[np.nan, 0.0], z_vol=[0.0, np.nan])
    lab = compute_labels(df, CFG)
    assert lab["label_ok"].tolist() == [False, False]
    assert lab["material"].isna().all() and lab["delayed"].isna().all()


def test_assert_public_refuses_test_period() -> None:
    assert_public(pd.Series([date(2025, 12, 31), None]))
    with pytest.raises(LabelError):
        assert_public(pd.Series([date(2025, 12, 31), date(2026, 1, 2)]))


def test_embargo_first_five_sessions() -> None:
    sess = calendar.sessions(date(2025, 7, 1), date(2025, 7, 15))
    flags = embargo_flags(pd.Series(sess), pd.Series(["val_a"] * len(sess)))
    assert flags.tolist() == [True] * 5 + [False] * (len(sess) - 5)


# --- real labels (skip until the labels stage has run) ----------------------------------------------


@pytest.fixture(scope="module")
def labels() -> pd.DataFrame:
    if not (ROOT / "work" / "events" / "labels_public.parquet").is_file():
        pytest.skip("labels not built")
    from newsaction import io

    return io.read_parquet("events/labels_public.parquet")


def test_real_labels_public_and_purged(labels: pd.DataFrame) -> None:
    assert set(labels["split"]) == {"train", "val_a", "val_b"}
    assert max(labels["session"]) <= date(2025, 12, 31)
    assert not labels.duplicated(["company_id", "session"]).any()
    # the last 5 sessions of each split are purged and unlabelled
    for split, end in (("train", date(2025, 6, 30)), ("val_a", date(2025, 9, 30))):
        last5 = calendar.sessions(date(2025, 1, 1), end)[-5:]
        rows = labels.loc[(labels["split"] == split) & labels["session"].isin(last5)]
        assert len(rows) and rows["purged"].all() and not rows["label_ok"].any()
        assert rows["material"].isna().all()
    assert not (labels["purged"] & labels["label_ok"]).any()


def test_real_delayed_car_equals_direct_forward_sum(labels: pd.DataFrame) -> None:
    """Σ_{j=1..5} AR_cc,t+j summed directly from panel_public equals the derived delayed CAR."""
    from newsaction import io

    panel = io.read_parquet("panel/panel_public.parquet", columns=["session", "symbol_id", "ar_cc"])
    ar = panel.set_index(["symbol_id", "session"])["ar_cc"]
    sample = labels.loc[(labels["split"] == "val_a") & labels["label_ok"]].sample(60, random_state=2026)
    for r in sample.itertuples(index=False):
        s, total = r.session, 0.0
        for _ in range(5):
            s = calendar.next_session(s)
            total += float(ar.loc[(r.symbol_id, s)])
        assert total / (r.sigma_cc * math.sqrt(5)) == pytest.approx(r.car_delayed_z, abs=1e-9)
        direct = (r.ar_cc + total) / (r.sigma_cc * math.sqrt(6))
        assert direct == pytest.approx(r.car6_z, abs=1e-9)
        material = abs(r.z_on) >= 2 or abs(direct) >= 2 or r.z_vol >= 2
        delayed = abs(r.z_on) < 1 and abs(total / (r.sigma_cc * math.sqrt(5))) >= 2
        assert (bool(r.material), bool(r.delayed)) == (material, delayed)
