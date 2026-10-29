"""NA-13b (e): the conditions of the conditioning study (E1–E9), fixed in the operator's prompt before this
chunk ran. Every condition is binary, inside against outside; thresholds and medians come from val-A only
(events or sessions of val-A outside the embargo). An event whose attribute input is missing (a vendor
field, attention, momentum) counts as outside (the operator's assistant's convention: ``fillna(False)``); an
event without a model reading a condition needs (another model's N̂, d1-ultra's labels or confidence,
Laya-Fin's magnitude, V) is in neither group (``READINGS``); and where a condition names its outside group
(E3's 04:00–08:00 against 08:00–09:15) the rest is in neither.

Levels (the selection rule's statistic):

- ``event``: inside and outside are events of the same session; the statistic is the mean of daily
  differences of the two groups' daily means, with a day-clustered t;
- ``day``: decided at the session level; the statistic is the difference of the inside and outside
  sessions' daily means (every event of the session), with Welch's t;
- ``paired``: E7's rank average, an alternative signal on the same events; the statistic is the mean of
  daily differences between the daily mean of sign(ensemble)·z and that of sign(N̂_model)·z.

Inputs (``data.study_frame``): vendor fields of the rank-0 news item (retrospective labels, CLAUDE.md A6;
marked ``vendor``), d1-ultra's own A2 reading of the same W0 news, the latest W0 article's availability time,
the session calendar (FOMC and CPI days from the frozen state's context; payroll days hand-checked on
bls.gov, ``data.PAYROLLS``), VIX's close of t−1 (NA-00's copy of ``Data/market``; operator decision), SPY's
overnight move (known at the open, after the 09:15 decision), the model readings and V (the frozen val-A map,
PREREG A1.3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np
import pandas as pd

from newsaction.selective import data as sd

Level = Literal["event", "day", "paired"]
COST_HURDLE: Final = 2 * 10e-4 * 2  # E8: 2 × 10 bp per side × 2 legs (0.40%)
BUSY_RATIO: Final = 1.5  # PREREG §15 operator row (8): the codebook's "busy" or heavier
GATE_PCT: Final = 0.7  # E6: the frozen gate's percentile, applied to conviction |N̂|
MINUTES: Final = {"04:00": 240, "08:00": 480, "09:15": 555}


@dataclass(frozen=True)
class Condition:
    key: str
    group: str
    label: str
    level: Level = "event"
    seen_on_test: bool = False
    models: tuple[str, ...] = sd.MAIN
    splits: tuple[str, ...] = sd.SPLITS
    val_b_only: bool = False  # E7's three-model agreement: selected on val-B alone (t >= 2.5)
    vendor: bool = False
    note: str = ""


CONDITIONS: Final[tuple[Condition, ...]] = (
    Condition("e1_earnings", "E1", "earnings day", seen_on_test=True,
              note="the earnings-calendar flag (a scheduled release in W0), not the vendor tag"),
    Condition("e1_vendor_quantified", "E1", "vendor: quantified", vendor=True),
    Condition("e1_press_wire", "E1", "press wire", vendor=True),
    Condition("e1_imprecise", "E1", "imprecise timestamp", vendor=True,
              note="a state article stamped to the date or the hour"),
    Condition("e2_new", "E2", "d1: new (not known)"),
    Condition("e2_numbers", "E2", "d1: numbers (not narrative)"),
    Condition("e2_scheduled", "E2", "d1: scheduled"),
    Condition("e2_company", "E2", "d1: company-specific"),
    Condition("e2_confirmed", "E2", "d1: confirmed"),
    Condition("e2_long_horizon", "E2", "d1: impact horizon > median"),
    Condition("e2_low_uncertainty", "E2", "d1: uncertainty < median"),
    Condition("e2_few_mixed", "E2", "d1: mixed signals < median"),
    Condition("e2_material", "E2", "d1: materiality > median"),
    Condition("e2_effect", "E2", "d1: P(no material effect) < median"),
    Condition("e3_before_0800", "E3", "latest article before 08:00", seen_on_test=True),
    Condition("e3_0400_0800", "E3", "04:00-08:00 vs 08:00-09:15",
              note="events whose latest article precedes 04:00 are left out of this comparison"),
    Condition("e4_friday", "E4", "Friday", level="day"),
    Condition("e4_monday", "E4", "Monday", level="day"),
    Condition("e4_busy_event", "E4", "busy news day (ratio >= 1.5)",
              note="the event's own W0 attention ratio (event level)"),
    Condition("e4_busy_day", "E4", "day's news count > median", level="day"),
    Condition("e4_earnings_season", "E4", "day's earnings count > median", level="day"),
    Condition("e4_macro", "E4", "macro day (FOMC, CPI or payrolls)", level="day",
              note="FOMC and CPI from the frozen calendar; payrolls hand-checked on bls.gov"),
    Condition("e4_vix", "E4", "VIX(t-1) > median", level="day",
              note="the ^VIX close of the session before (NA-00's copy of Data/market)"),
    Condition("e4_spy_gap", "E4", "|SPY overnight| > median", level="day",
              note="known at the open, after the 09:15 decision"),
    Condition("e5_tier", "E5", "size tier 251-500"),
    Condition("e5_dv_tier", "E5", "dollar-volume tier 251-500"),
    Condition("e5_low_coverage", "E5", "low usual coverage"),
    Condition("e5_high_sigma", "E5", "sigma > median"),
    Condition("e5_momentum", "E5", "direction agrees with z_m20"),
    Condition("e5_price_text", "E5", "price-move text"),
    Condition("e6_conviction", "E6", "conviction top 30%", seen_on_test=True,
              note="|N̂| at or above its val-A 70th percentile (the gate's percentile; the frozen gate "
              "itself ranks by the stated confidence)"),
    Condition("e6_lf_mag", "E6", "Laya-Fin H-mag > median"),
    Condition("e6_d1_conf", "E6", "d1 stated confidence > median"),
    Condition("e7_agree", "E7", "Laya-Fin and d1-ultra agree"),
    Condition("e7_api3", "E7", "three API models agree", splits=("val_b", "test"), val_b_only=True,
              note="span-02 and drex-v2.0 have no val-A production run"),
    Condition("e7_rank_avg", "E7", "rank average of Laya-Fin and d1-ultra", level="paired",
              note="sign of the mean of sign(N̂)·F(|N̂|), F each model's val-A distribution of |N̂|; "
              "against the model's own sign on the same events"),
    Condition("e8_cost", "E8", "|V| x sigma > cost hurdle", note="|V|·σ_cc > 2 × 10 bp × 2 legs"),
    Condition("e9_division", "E9", "d1 numbers and material (Laya-Fin direction)", models=("laya_fin",)),
)  # fmt: skip
BY_KEY: Final = {c.key: c for c in CONDITIONS}
_D1: Final = ("n_d1_ultra",)
# The model readings each condition needs; an event lacking one is in neither group (not "outside").
READINGS: Final[dict[str, tuple[str, ...]]] = {
    **{k: _D1 for k in ("e2_new", "e2_numbers", "e2_scheduled", "e2_company", "e2_confirmed",
                        "e2_long_horizon", "e2_low_uncertainty", "e2_few_mixed", "e2_material", "e2_effect",
                        "e6_d1_conf", "e9_division")},
    "e6_lf_mag": ("lf_mag",),
    "e7_agree": ("n_laya_fin", "n_d1_ultra"),
    "e7_api3": ("n_d1_ultra", "n_span_02", "n_drex_v2"),
    "e8_cost": ("v_{model}",),
}  # fmt: skip


def pairs(conditions: Sequence[Condition] = CONDITIONS) -> list[tuple[str, Condition]]:
    """Every (model, condition) pair of the family."""
    return [(m, c) for c in conditions for m in c.models]


# --- val-A cut points ---------------------------------------------------------------------------------------

EVENT_MEDIANS: Final = (
    "a0_h",
    "a0_u_unc",
    "a0_p_mixed",
    "a0_m",
    "a0_p_no_material_effect",
    "attention_mean",
    "sigma_cc",
    "lf_mag",
    "d1_conf",
)
DAY_MEDIANS: Final = ("n_events", "n_earnings", "vix_prev", "abs_spy_on")


def cuts(study: pd.DataFrame) -> dict[str, Any]:
    """Every threshold, from val-A outside the embargo: event medians, session medians, the 70th percentile
    of each model's |N̂| and each model's sorted val-A |N̂| (the rank average's distribution)."""
    va = sd.eval_rows(study, "val_a")
    out: dict[str, Any] = {f"median_{c}": float(va[c].median()) for c in EVENT_MEDIANS}
    d = day_frame(va)
    out |= {f"day_median_{c}": float(d[c].median()) for c in DAY_MEDIANS}
    for m in sd.MAIN:
        a = va[f"n_{m}"].abs().dropna()
        out[f"q70_abs_{m}"] = float(a.quantile(GATE_PCT))
        out[f"sorted_abs_{m}"] = np.sort(a.to_numpy(dtype=float))
    return out


def day_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """The session attributes of the rows' sessions (one row per session)."""
    cols = ["session", "n_events", "n_earnings", "vix_prev", "macro_cpi_today", "macro_fomc_today",
            "macro_payrolls_today", "r_spy_on", "weekday"]  # fmt: skip
    d = rows[cols].drop_duplicates("session").copy()
    d["abs_spy_on"] = d["r_spy_on"].abs()
    return d.set_index("session")


def ecdf(sorted_ref: np.ndarray, x: np.ndarray) -> np.ndarray:
    """F(x): the share of the reference values <= x."""
    return np.searchsorted(sorted_ref, x, side="right") / max(len(sorted_ref), 1)


def ensemble(study: pd.DataFrame, c: Mapping[str, Any]) -> pd.Series:
    """E7's rank average: the mean of sign(N̂)·F(|N̂|) over Laya-Fin and d1-ultra (F from val-A)."""
    parts = []
    for m in sd.MAIN:
        n = study[f"n_{m}"].to_numpy(dtype=float)
        parts.append(np.sign(n) * ecdf(c[f"sorted_abs_{m}"], np.abs(n)))
    return pd.Series((parts[0] + parts[1]) / 2.0, index=study.index)


# --- inside / outside -----------------------------------------------------------------------------------


def _true(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(bool)


def event_inside(study: pd.DataFrame, model: str, cond: Condition, c: Mapping[str, Any]) -> pd.Series:
    """The event-level (or day-level, broadcast to events) inside flag; NaN where the event is in neither
    group of the comparison."""
    f = study
    n = f[f"n_{model}"]
    k = cond.key

    def med(col: str) -> float:
        return float(c[f"median_{col}"])

    if k == "e1_earnings":
        m = f["earnings"] == 1
    elif k == "e1_vendor_quantified":
        m = f["vendor_quantified"] == True  # noqa: E712
    elif k == "e1_press_wire":
        m = f["press_wire"] == True  # noqa: E712
    elif k == "e1_imprecise":
        m = f["imprecise"] == True  # noqa: E712
    elif k == "e2_new":
        m = f["a0_label_novelty"] == "new"
    elif k == "e2_numbers":
        m = f["a0_label_quantified"] == "numbers"
    elif k == "e2_scheduled":
        m = f["a0_label_scheduled"] == "scheduled"
    elif k == "e2_company":
        m = f["a0_label_scope"] == "company_specific"
    elif k == "e2_confirmed":
        m = f["a0_label_credibility"] == "confirmed"
    elif k == "e2_long_horizon":
        m = f["a0_h"] > med("a0_h")
    elif k == "e2_low_uncertainty":
        m = f["a0_u_unc"] < med("a0_u_unc")
    elif k == "e2_few_mixed":
        m = f["a0_p_mixed"] < med("a0_p_mixed")
    elif k == "e2_material":
        m = f["a0_m"] > med("a0_m")
    elif k == "e2_effect":
        m = f["a0_p_no_material_effect"] < med("a0_p_no_material_effect")
    elif k == "e3_before_0800":
        m = f["latest_et"] < MINUTES["08:00"]
    elif k == "e3_0400_0800":
        t = f["latest_et"]
        inside = (t >= MINUTES["04:00"]) & (t < MINUTES["08:00"])
        outside = (t >= MINUTES["08:00"]) & (t <= MINUTES["09:15"])
        return inside.astype(float).where(inside | outside)
    elif k == "e4_busy_event":
        m = f["attention_ratio"] >= BUSY_RATIO
    elif k == "e5_tier":
        m = f["tier"] == "rest"
    elif k == "e5_dv_tier":
        m = f["dv_tier"] == "rest"
    elif k == "e5_low_coverage":
        m = f["attention_mean"] < med("attention_mean")
    elif k == "e5_high_sigma":
        m = f["sigma_cc"] > med("sigma_cc")
    elif k == "e5_momentum":
        m = np.sign(n) == np.sign(f["z_m20"])
    elif k == "e5_price_text":
        m = f["price_move_text"] == True  # noqa: E712
    elif k == "e6_conviction":
        m = n.abs() >= c[f"q70_abs_{model}"]
    elif k == "e6_lf_mag":
        m = f["lf_mag"] > med("lf_mag")
    elif k == "e6_d1_conf":
        m = f["d1_conf"] > med("d1_conf")
    elif k == "e7_agree":
        m = np.sign(f["n_laya_fin"]) == np.sign(f["n_d1_ultra"])
    elif k == "e7_api3":
        s = np.sign(f["n_d1_ultra"])
        m = (s == np.sign(f["n_span_02"])) & (s == np.sign(f["n_drex_v2"]))
    elif k == "e8_cost":
        m = (f[f"v_{model}"].abs() * f["sigma_cc"]) > COST_HURDLE
    elif k == "e9_division":
        m = (f["a0_label_quantified"] == "numbers") & (f["a0_m"] > med("a0_m"))
    elif cond.level == "day":
        return day_inside(f, cond, c).astype(float)
    elif cond.level == "paired":  # every event with both readings; the comparison is between two signals
        return pd.Series(1.0, index=f.index).where(f["n_laya_fin"].notna() & f["n_d1_ultra"].notna())
    else:
        raise KeyError(f"no event rule for {k!r}")
    flag = _true(pd.Series(m, index=f.index)).astype(float)
    need = [col.format(model=model) for col in READINGS.get(k, ())]
    return flag.where(f[need].notna().all(axis=1)) if need else flag


def day_inside(rows: pd.DataFrame, cond: Condition, c: Mapping[str, Any]) -> pd.Series:
    """A day-level condition, evaluated per session and broadcast to the rows."""
    k = cond.key
    if k == "e4_friday":
        m = rows["weekday"] == 4
    elif k == "e4_monday":
        m = rows["weekday"] == 0
    elif k == "e4_busy_day":
        m = rows["n_events"] > c["day_median_n_events"]
    elif k == "e4_earnings_season":
        m = rows["n_earnings"] > c["day_median_n_earnings"]
    elif k == "e4_macro":
        m = (
            _true(rows["macro_cpi_today"])
            | _true(rows["macro_fomc_today"])
            | _true(rows["macro_payrolls_today"])
        )
    elif k == "e4_vix":
        m = rows["vix_prev"] > c["day_median_vix_prev"]
    elif k == "e4_spy_gap":
        m = rows["r_spy_on"].abs() > c["day_median_abs_spy_on"]
    else:
        raise KeyError(f"no day rule for {k!r}")
    return _true(pd.Series(m, index=rows.index))
