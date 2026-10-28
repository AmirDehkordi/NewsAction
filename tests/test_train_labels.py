"""H-react / H-mag / H-cont labels (PREREG §9.1; PRD NA-08 S1, AC2): bins, the cont rule, purge, dates."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from newsaction import calendar
from newsaction.events.labels import LabelError
from newsaction.paths import ROOT
from newsaction.train import load_training_config
from newsaction.train.labels import (
    TrainLabelError,
    build_labels,
    check_purge,
    cont_labels,
    event_keys,
    horizon_end,
    mag_levels,
    react_levels,
)

EDGES = load_training_config().labels.edges
ORDER = ["reverse", "stall", "continue"]


@pytest.mark.parametrize(
    ("e5", "level"),
    [
        (-10.0, 0),
        (-3.0, 0),
        (-2.999, 1),
        (-2.0, 1),
        (-1.999, 2),
        (-1.0, 2),
        (-0.999, 3),
        (-0.5, 3),
        (-0.4999, 4),
        (0.0, 4),
        (0.4999, 4),
        (0.5, 5),
        (0.999, 5),
        (1.0, 6),
        (1.999, 6),
        (2.0, 7),
        (2.999, 7),
        (3.0, 8),
        (12.0, 8),
    ],
)
def test_react_levels_are_q1_bins(e5: float, level: int) -> None:
    assert react_levels(pd.Series([e5]), EDGES).iloc[0] == level


def test_react_level_missing_and_symmetric() -> None:
    assert react_levels(pd.Series([np.nan]), EDGES).isna().all()
    x = pd.Series(np.linspace(-6, 6, 241))
    lv = react_levels(x, EDGES).astype(int).to_numpy()
    assert (lv + react_levels(-x, EDGES).astype(int).to_numpy() == 8).all()  # mirror image around level 4


@pytest.mark.parametrize(
    ("z", "level"),
    [(0.0, 0), (0.4999, 0), (0.5, 1), (-0.7, 1), (1.0, 2), (-1.5, 2), (2.0, 3), (3.0, 4), (-9.0, 4)],
)
def test_mag_levels(z: float, level: int) -> None:
    assert mag_levels(pd.Series([z]), EDGES).iloc[0] == level


def test_mag_level_missing() -> None:
    assert mag_levels(pd.Series([np.nan]), EDGES).isna().all()


@pytest.mark.parametrize(
    ("g", "y2", "label"),
    [
        (0.5, 0.5, 2),  # continue: x = 0.5
        (1.0, 0.49, 1),  # stall
        (1.0, -0.5, 0),  # reverse: x = -0.5
        (-1.0, 0.6, 0),  # a fall followed by a rise reverses
        (-2.0, -3.0, 2),  # a fall that keeps falling continues
        (-0.6, 0.0, 1),
    ],
)
def test_cont_rule(g: float, y2: float, label: int) -> None:
    x, lab = cont_labels(pd.Series([g]), pd.Series([y2]), min_abs_g=0.5, band=0.5, order=ORDER)
    assert lab.iloc[0] == label
    assert x.iloc[0] == pytest.approx(np.sign(g) * y2)


@pytest.mark.parametrize(("g", "y2"), [(0.49, 2.0), (-0.3, -2.0), (0.0, 1.0), (np.nan, 1.0), (1.0, np.nan)])
def test_cont_needs_a_reaction_of_half_a_sigma(g: float, y2: float) -> None:
    _, lab = cont_labels(pd.Series([g]), pd.Series([y2]), min_abs_g=0.5, band=0.5, order=ORDER)
    assert lab.isna().all()


def test_cont_refuses_another_option_order() -> None:
    with pytest.raises(TrainLabelError):
        cont_labels(
            pd.Series([1.0]),
            pd.Series([1.0]),
            min_abs_g=0.5,
            band=0.5,
            order=["continue", "stall", "reverse"],
        )


def test_horizon_end_counts_sessions() -> None:
    s = pd.Series([date(2025, 6, 24), date(2025, 6, 23), date(2025, 7, 3)])
    assert list(horizon_end(s, 4)) == [
        date(2025, 6, 30),
        date(2025, 6, 27),
        date(2025, 7, 10),
    ]  # 07-04 holiday
    assert list(horizon_end(s, 0)) == list(s)


def _keys(sessions: list[date], split: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_id": range(len(sessions)),
            "symbol_id": range(len(sessions)),
            "session": sessions,
            "split": split,
            "embargo": False,
        }
    )


def test_check_purge_refuses_a_label_past_the_split_end() -> None:
    lab = pd.DataFrame(
        {
            "session": [date(2025, 6, 24), date(2025, 6, 25)],
            "split": "train",
            "react_label": pd.array([3, 3], dtype="Int8"),
            "mag_label": pd.array([1, 1], dtype="Int8"),
            "cont_label": pd.array([pd.NA, pd.NA], dtype="Int8"),
        }
    )
    lab["react_horizon_end"] = horizon_end(lab["session"], 4)
    lab["cont_horizon_end"] = horizon_end(lab["session"], 5)
    with pytest.raises(TrainLabelError, match="react_label"):
        check_purge(lab)
    check_purge(lab.iloc[:1])  # 06-24 + 4 sessions = 06-30, the last train session


def test_build_labels_refuses_sessions_after_val_b() -> None:
    panel = pd.DataFrame(
        {
            "session": [date(2026, 1, 5)],
            "symbol_id": [1],
            "split": ["test"],
            "e5": [1.0],
            "z_cc": [1.0],
            "g_d2": [1.0],
            "y2": [1.0],
        }
    )
    keys = _keys([date(2025, 7, 1)], "val_a")
    with pytest.raises(LabelError):
        build_labels(panel, keys, keys)


def test_event_keys_merge_d0_and_d2_and_refuse_conflicts() -> None:
    d0 = _keys([date(2025, 7, 1)], "val_a")
    d2 = pd.concat(
        [d0, _keys([date(2025, 7, 2)], "val_a").assign(company_id=9, symbol_id=9)], ignore_index=True
    )
    k = event_keys(d0, d2, ["val_a"])
    assert len(k) == 2 and k["in_d2"].all() and k["in_d0"].sum() == 1
    bad = d2.copy()
    bad.loc[0, "symbol_id"] = 77
    with pytest.raises(TrainLabelError):
        event_keys(d0, bad, ["val_a"])


def test_build_labels_on_a_synthetic_panel_purges_at_the_split_end() -> None:
    days = calendar.sessions(date(2025, 6, 16), date(2025, 6, 30))
    panel = pd.DataFrame(
        {"session": days, "symbol_id": 1, "split": "train", "z_cc": 1.2, "g_d2": 1.2, "e5": 2.5, "y2": 0.7}
    )
    late4 = [horizon_end(pd.Series([d]), 4).iloc[0] > date(2025, 6, 30) for d in days]
    late5 = [horizon_end(pd.Series([d]), 5).iloc[0] > date(2025, 6, 30) for d in days]
    purged = panel.copy()
    purged.loc[late4, "e5"] = np.nan  # the panel's own purge (NA-01 target code)
    purged.loc[late5, "y2"] = np.nan
    keys = pd.DataFrame(
        {"company_id": 1, "symbol_id": 1, "session": days, "split": "train", "embargo": False}
    )
    out = build_labels(purged, keys, keys)
    first, last = out.iloc[0], out.iloc[-1]
    assert (first["react_label"], first["mag_label"], first["cont_label"]) == (7, 2, 2)
    assert pd.isna(last["react_label"]) and pd.isna(last["cont_label"]) and last["mag_label"] == 2
    with pytest.raises(TrainLabelError):  # a panel without the purge is refused
        build_labels(panel, keys, keys)


# --- the built file (integration; skipped before the NA-08 labels stage has run) ---------------------


@pytest.fixture(scope="module")
def labels() -> pd.DataFrame:
    from newsaction import io

    if not (ROOT / "work" / "kaggle" / "labels.parquet").is_file():
        pytest.skip("work/kaggle/labels.parquet is absent (run the NA-08 labels stage)")
    return io.read_parquet("kaggle/labels.parquet")


def test_built_labels_are_public_and_purged(labels: pd.DataFrame) -> None:
    assert set(labels["split"]) == {"train", "val_a", "val_b"}
    assert max(labels["session"]) <= date(2025, 12, 31)
    check_purge(labels)
    tr = labels[labels["split"] == "train"]
    assert max(tr.loc[tr["react_label"].notna(), "react_horizon_end"]) <= date(2025, 6, 30)
    assert max(tr.loc[tr["cont_label"].notna(), "cont_horizon_end"]) <= date(2025, 6, 30)
    assert labels.duplicated(["company_id", "session"]).sum() == 0


def test_thirty_random_train_labels_recomputed_from_the_panel(
    labels: pd.DataFrame, panel_public: pd.DataFrame
) -> None:
    """e5 re-summed from AR_cc over t..t+4, z_cc and y2 read, then binned by hand."""
    tr = labels[(labels["split"] == "train") & labels["react_label"].notna() & labels["cont_label"].notna()]
    sample = tr.sample(30, random_state=2026)
    p = panel_public[["session", "symbol_id", "ar_cc", "sigma_cc", "z_cc", "g_d2", "y2"]]
    by_sym = {s: g.set_index("session").sort_index() for s, g in p.groupby("symbol_id")}
    edges = [0.5, 1.0, 2.0, 3.0]
    for row in sample.itertuples():
        g = by_sym[row.symbol_id]
        days = [row.session, *[horizon_end(pd.Series([row.session]), k).iloc[0] for k in (1, 2, 3, 4)]]
        ar = g["ar_cc"].reindex(days).fillna(0.0)  # AR_cc is 0 after a last trade (NA-01)
        e5 = ar.sum() / (g.loc[row.session, "sigma_cc"] * np.sqrt(5))
        assert e5 == pytest.approx(row.e5, abs=1e-9)
        b = sum(abs(e5) >= e for e in edges)
        assert row.react_label == 4 + int(np.sign(e5)) * b
        assert row.mag_label == sum(abs(g.loc[row.session, "z_cc"]) >= e for e in edges)
        x = np.sign(g.loc[row.session, "g_d2"]) * g.loc[row.session, "y2"]
        assert row.cont_label == (0 if x <= -0.5 else 2 if x >= 0.5 else 1)
