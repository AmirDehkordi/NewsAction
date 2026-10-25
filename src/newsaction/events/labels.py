"""Material and delayed-reaction ticker-day labels (PREREG §6.7, §6.8; PRD NA-03 S1).

For every covered member company × session in train, val-A and val-B (representative class of
``panel_public``; coverage per PREREG §3.4):

- material = |z_on,t| ≥ 2  or  |Σ_{j=0..5} AR_cc,t+j| / (σ_cc·√6) ≥ 2  or  z_vol,t ≥ 2;
- delayed  = |z_on,t| < 1  and |Σ_{j=1..5} AR_cc,t+j| / (σ_cc·√5) ≥ 2.

The six-day CAR is the panel's ``car6_z`` (NA-01 target code: σ_cc of row t, AR_cc held at 0 after a
symbol's last trade, NaN when the horizon leaves the split). The delayed five-day CAR is derived from
it: Σ_{j=1..5} AR_cc,t+j = car6_z·σ_cc·√6 − AR_cc,t, so both labels share one purge and one delisting
rule. Purge (§4.1): a label whose t+5 horizon ends after its split's last session is missing
(``purged``), as is any label with a missing input (``label_ok`` False); missing labels are never
counted as "not material".

Public sessions only: ``assert_public`` refuses any session after the end of val-B, and this module
never imports ``newsaction.panel.targets`` (the panel file already holds the purged targets).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Final

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.config import SplitName, load_splits
from newsaction.events import LABELS, PRODUCER, LabelConfig, load_events_config
from newsaction.news import COVERAGE
from newsaction.paths import Layout

LABEL_SPLITS: Final[tuple[SplitName, ...]] = ("train", "val_a", "val_b")
EMBARGO_SPLITS: Final[tuple[SplitName, ...]] = ("val_a", "val_b", "test")  # PREREG §4.2
PANEL: Final = "panel/panel_public.parquet"
PANEL_COLUMNS: Final = (
    "session",
    "symbol_id",
    "company_id",
    "member",
    "is_rep",
    "split",
    "tier",
    "z_on",
    "z_cc",
    "z_vol",
    "ar_cc",
    "sigma_cc",
    "car6_z",
)


class LabelError(ValueError):
    """A label was asked for a session outside the public period or with an inconsistent config."""


def public_end() -> date:
    """Last public session date: the end of val-B (PREREG §4)."""
    return load_splits().splits["val_b"].end


def assert_public(sessions: pd.Series, what: str = "sessions") -> None:
    """Raise LabelError if any non-missing session is after the end of val-B."""
    s = pd.to_datetime(sessions.dropna())
    if len(s) and s.max().date() > public_end():
        raise LabelError(f"{what}: session {s.max().date()} is after the public period (ends {public_end()})")


def compute_labels(df: pd.DataFrame, cfg: LabelConfig) -> pd.DataFrame:
    """Label columns for rows with z_on, z_vol, ar_cc, sigma_cc and car6_z (pure; no I/O).

    Returns ``car_delayed_z``, ``label_ok``, the three material components, ``material`` and
    ``delayed`` (nullable booleans, NA where ``label_ok`` is False).
    """
    if cfg.material_car_days != 6 or cfg.delayed_car_days != cfg.material_car_days - 1:
        raise LabelError("labels derive the t+1..t+5 CAR from the panel's six-day car6_z (PREREG §6.7-6.8)")
    sig = df["sigma_cc"].astype("float64")
    car6 = df["car6_z"].astype("float64")
    z_on = df["z_on"].astype("float64")
    z_vol = df["z_vol"].astype("float64")
    ar_cc = df["ar_cc"].astype("float64")
    car_delayed = (car6 * sig * math.sqrt(cfg.material_car_days) - ar_cc) / (
        sig * math.sqrt(cfg.delayed_car_days)
    )
    ok = np.isfinite(z_on) & np.isfinite(z_vol) & np.isfinite(car6) & np.isfinite(car_delayed) & (sig > 0)
    on = z_on.abs() >= cfg.material_on_z
    car = car6.abs() >= cfg.material_car_z
    vol = z_vol >= cfg.material_vol_z
    delayed = (z_on.abs() < cfg.delayed_on_max) & (car_delayed.abs() >= cfg.delayed_car_z)
    out = pd.DataFrame(index=df.index)
    out["car_delayed_z"] = car_delayed.where(ok)
    out["label_ok"] = ok.astype(bool)
    for name, flag in (
        ("material_on", on),
        ("material_car", car),
        ("material_vol", vol),
        ("material", on | car | vol),
        ("delayed", delayed),
    ):
        out[name] = flag.astype("boolean").mask(~ok)
    return out


def _horizon_end(sessions: pd.Series, k: int) -> pd.Series:
    """The k-th session after each session (calendar), as datetime64."""
    uniq = sorted(set(sessions))
    ends = {d: d for d in uniq}
    for d in uniq:
        e = d
        for _ in range(k):
            e = calendar.next_session(e)
        ends[d] = e
    return sessions.map(ends)


def split_last_session(name: SplitName) -> date:
    end = load_splits().splits[name].end
    return calendar.prev_session(calendar.next_session(end))


def embargo_flags(sessions: pd.Series, splits: pd.Series, n: int | None = None) -> pd.Series:
    """True for the first ``embargo_sessions`` sessions of val-A, val-B and test (PREREG §4.2)."""
    cfg = load_splits()
    n = cfg.embargo_sessions if n is None else n
    first: dict[str, set[date]] = {}
    for name in EMBARGO_SPLITS:
        rng = cfg.splits[name]
        first[name] = set(calendar.sessions(rng.start, rng.end)[:n])
    vals = [s in first.get(str(sp), set()) for s, sp in zip(sessions, splits, strict=True)]
    return pd.Series(vals, index=sessions.index, dtype=bool)


def covered_member_days(panel: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    """Representative-class member rows whose (month, company) is covered (PREREG §3.4)."""
    p = panel[panel["member"].astype(bool) & panel["is_rep"].astype(bool)].copy()
    p["month"] = pd.to_datetime(p["session"]).dt.strftime("%Y-%m")
    cov = coverage.loc[coverage["covered"].astype(bool), ["month", "company_id"]]
    out = p.merge(cov, on=["month", "company_id"], how="inner")
    if out.duplicated(["company_id", "session"]).any():
        raise LabelError("more than one representative row per company-session")
    return out


def build_labels(panel: pd.DataFrame, coverage: pd.DataFrame, cfg: LabelConfig | None = None) -> pd.DataFrame:
    """Labels for covered member company-days of train, val-A and val-B (sorted by session, company)."""
    cfg = load_events_config().label if cfg is None else cfg
    p = panel[panel["split"].isin(LABEL_SPLITS)]
    assert_public(p["session"], "panel")
    days = covered_member_days(p, coverage)
    lab = compute_labels(days, cfg)
    out = pd.concat([days.drop(columns=["member", "is_rep"]), lab], axis=1)
    ends = {name: split_last_session(name) for name in LABEL_SPLITS}
    hz = _horizon_end(out["session"], cfg.material_car_days - 1)
    out["horizon_end"] = hz
    out["purged"] = [h > ends[s] for h, s in zip(hz, out["split"], strict=True)]
    out["embargo"] = embargo_flags(out["session"], out["split"])
    cols = [
        "session",
        "company_id",
        "symbol_id",
        "split",
        "month",
        "tier",
        "embargo",
        "purged",
        "horizon_end",
        "z_on",
        "z_cc",
        "z_vol",
        "ar_cc",
        "sigma_cc",
        "car6_z",
        "car_delayed_z",
        "label_ok",
        "material_on",
        "material_car",
        "material_vol",
        "material",
        "delayed",
    ]
    return out[cols].sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def run(layout: Layout | None = None) -> pd.DataFrame:
    """Build and write work/events/labels_public.parquet."""
    panel = io.read_parquet(PANEL, columns=list(PANEL_COLUMNS), layout=layout)
    coverage = io.read_parquet(COVERAGE, layout=layout)
    out = build_labels(panel, coverage)
    if bool((out["purged"] & out["label_ok"]).any()):
        raise LabelError("a purged row has a label: the panel's car6_z is not purged at the split end")
    io.write_parquet(
        out,
        LABELS,
        producer=PRODUCER,
        description="NA-03 S1: material / delayed-reaction labels (PREREG §6.7-6.8) for covered member "
        "company-days of train, val-A and val-B; purged at split ends (§4.1); post (never a model input)",
        layout=layout,
    )
    return out
