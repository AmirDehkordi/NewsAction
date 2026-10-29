"""NA-13b inputs: one D0 frame per model (PREREG §2.5, §5.6; NA-12's frames and NA-11's readings).

**Events.** NA-12's D0 frames (``work/analysis/frame_d0_<model>.parquet``) hold every D0 event of val-A, val-B
and the test with its embargo flag, its targets (z_cc, z_on, z_id and y1; the 2026 rows from
``analysis/targets_test``) and the event attributes the conditions use. The secondary outcome
``z_o0_c1`` = AR(O_t → C_{t+1}) / (σ_id² + σ_cc²)^½ (``panel.targets``) is joined by (session, symbol_id) from
``panel/panel_public`` (validation) and ``analysis/targets_test`` (2026). The conditioning study's session
inputs add the ^VIX close of t−1 (NA-00's registered copy of ``Data/market``, a t−1 input the frozen states
used; the operator's decision in this session), the payroll release days (``PAYROLLS``, hand-checked on
bls.gov) and SPY's overnight move from NA-13's market files (no lock read).

**Readings** (Call A on W0 news, ``a0_``):

- Laya-Fin and d1-ultra: N̂ from their frames; Laya-Fin's Q1 probabilities from its pinned predictions
  (``frames.readings_trained``).
- span-02 and drex-v2.0: NA-11's production readings (val-B and test; there is no production val-A run) and,
  for val-A, NA-06's stage-2 sample (3,000 val-A events, Call A, core battery): the sample their frozen maps
  and gates were fit on (PREREG §15, NA-11 row (v)–(vi)).
- Laya zero-shot: NA-09's validation run and NA-11's test run.

**Stated confidence** ``conf`` = Q1's three-class confidence 1 − H(fall, no move, rise)/log 3, the measure of
the frozen gates (``configs/frozen.yaml`` thresholds.confidence); its val-A 70th percentile reproduces every
model's frozen D0 gate (``tests/test_selective_data.py``).
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from datetime import date
from typing import Final

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.analysis import frames
from newsaction.analysis import metrics as mx
from newsaction.config import load_yaml
from newsaction.paths import Layout, resolve_layout

MODELS: Final = ("laya_fin", "d1_ultra", "span_02", "drex_v2", "laya_zs")
MAIN: Final = ("laya_fin", "d1_ultra")
SPLITS: Final = ("val_a", "val_b", "test")
TARGETS: Final = ("z_cc", "z_on", "z_id")
SECONDARY: Final = "z_o0_c1"
FRAME: Final = "analysis/frame_d0_{model}.parquet"
PANEL_PUBLIC: Final = "panel/panel_public.parquet"
STAGE2: Final = "dm/tournament/stage2.parquet"
PRODUCTION: Final = {
    "span_02": "dm/production/respan_span_02_api_comparators_market.parquet",
    "drex_v2": "dm/production/nace_ai_drex_v2_0_api_comparators_market.parquet",
    "laya_zs": "dm/production/local_laya_typed_decisions_test.parquet",
}
STAGE2_MODEL: Final = {"span_02": "respan/span-02", "drex_v2": "nace-ai/drex-v2.0"}
CALIBRATION_KEY: Final = {
    "laya_fin": "laya_fin",
    "d1_ultra": "liquid/d1-ultra",
    "span_02": "respan/span-02",
    "drex_v2": "nace-ai/drex-v2.0",
    "laya_zs": "local/laya-typed-decisions",
}
LABEL: Final = {
    "laya_fin": "Laya-Fin",
    "d1_ultra": "d1-ultra",
    "span_02": "span-02",
    "drex_v2": "drex-v2.0",
    "laya_zs": "Laya zero-shot",
}
EVENT_COLUMNS: Final = (
    "event_id",
    "session",
    "symbol_id",
    "company_id",
    "split",
    "embargo",
    "tier",
    "dv_tier",
    "z_cc",
    "z_on",
    "z_id",
    "y1",
    "g_d1",
    "sigma_cc",
    "z_m20",
    "attention_mean",
    "attention_ratio",
    "earnings",
    "vendor_quantified",
    "press_wire",
    "imprecise",
    "latest_et",
    "price_move_text",
)
# d1-ultra's own A2 reading of the same W0 news (PREREG A2.2, A2.4)
D1_LABELS: Final = (
    "a0_label_novelty",
    "a0_label_quantified",
    "a0_label_scheduled",
    "a0_label_scope",
    "a0_label_credibility",
    "a0_h",
    "a0_u_unc",
    "a0_p_mixed",
    "a0_m",
    "a0_p_no_material_effect",
    "a0_conf3",
)


class DataError(ValueError):
    """The inputs do not join as NA-13b needs."""


def _dates(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.date


def frame(model: str, columns: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """Columns of NA-12's D0 frame of ``model`` (Laya-Fin, d1-ultra or the anchor)."""
    df = io.read_parquet(FRAME.format(model=model), columns=list(dict.fromkeys(columns)), layout=layout)
    if "session" in df.columns:
        df["session"] = _dates(df["session"])
    return df


def secondary_outcome(layout: Layout | None = None) -> pd.DataFrame:
    """(session, symbol_id, z_o0_c1) for validation (``panel_public``) and the test (``targets_test``)."""
    cols = ["session", "symbol_id", SECONDARY]
    parts = [io.read_parquet(PANEL_PUBLIC, columns=cols, layout=layout)]
    parts.append(io.read_parquet(frames.TARGETS_TEST, columns=cols, layout=layout))
    out = pd.concat(parts, ignore_index=True)
    out["session"] = _dates(out["session"])
    out = out.dropna(subset=[SECONDARY]).drop_duplicates(["session", "symbol_id"], keep="last")
    return out.reset_index(drop=True)


def events(layout: Layout | None = None) -> pd.DataFrame:
    """Every D0 event of val-A, val-B and the test: attributes, targets and the secondary outcome."""
    ev = frame("laya_fin", EVENT_COLUMNS, layout)
    if ev["event_id"].duplicated().any():
        raise DataError("duplicate D0 event ids in the frame")
    ev["embargo"] = ev["embargo"].fillna(False).astype(bool)
    sec = secondary_outcome(layout)
    ev = ev.merge(sec, on=["session", "symbol_id"], how="left", validate="many_to_one")
    ev["weekday"] = pd.to_datetime(ev["session"]).dt.day_of_week
    return ev


def conf3(q1: pd.Series) -> np.ndarray:
    """Q1's three-class confidence of each reading (NaN where Q1 is missing)."""
    out = np.full(len(q1), np.nan)
    ok = q1.notna().to_numpy()
    if ok.any():
        probs = np.stack([np.asarray(p, dtype=float) for p in q1.to_numpy()[ok]])
        out[ok] = mx.entropy_confidence(mx.three_class(probs))
    return out


def _indexed(r: pd.DataFrame) -> pd.DataFrame:
    return r if "event_id" in r.columns else r.rename_axis("event_id").reset_index()


def _stage2(model: str, layout: Layout | None = None) -> pd.DataFrame:
    """An API model's NA-06 stage-2 val-A Call A readings (n_hat and the three-class confidence)."""
    cols = ["model", "event_id", "call", "part", "valid", "n_hat", "p_fall", "p_flat", "p_rise"]
    s2 = io.read_parquet(STAGE2, columns=cols, layout=layout)
    s2 = s2.loc[(s2["model"] == STAGE2_MODEL[model]) & (s2["call"] == "A") & s2["valid"].astype(bool)]
    p3 = s2[["p_fall", "p_flat", "p_rise"]].to_numpy(dtype=float)
    return pd.DataFrame(
        {"event_id": s2["event_id"].to_numpy(), "n_hat": s2["n_hat"].to_numpy(dtype=float),
         "conf": mx.entropy_confidence(p3), "sample": "stage2"}
    )  # fmt: skip


def readings(model: str, layout: Layout | None = None) -> pd.DataFrame:
    """(event_id, n_hat, conf, sample) of a model's Call A D0 readings on every split it answered."""
    if model == "laya_fin":
        f = frame(model, ["event_id", "a0_n_hat"], layout)
        q = _indexed(frames.readings_trained("laya_fin", list(SPLITS), layout))[["event_id", "a0_q1"]]
        f = f.merge(q, on="event_id", how="left", validate="one_to_one")
        out = pd.DataFrame({"event_id": f["event_id"], "n_hat": f["a0_n_hat"], "conf": conf3(f["a0_q1"])})
    elif model == "d1_ultra":
        f = frame(model, ["event_id", "a0_n_hat", "a0_conf3"], layout)
        out = pd.DataFrame({"event_id": f["event_id"], "n_hat": f["a0_n_hat"], "conf": f["a0_conf3"]})
    elif model in ("span_02", "drex_v2"):
        r = _indexed(frames.readings_api(PRODUCTION[model], layout, valid_only=True))
        prod = pd.DataFrame({"event_id": r["event_id"], "n_hat": r["a0_n_hat"], "conf": r["a0_conf3"]})
        out = pd.concat([prod.assign(sample="production"), _stage2(model, layout)], ignore_index=True)
    elif model == "laya_zs":
        z = _indexed(frames.readings_zeroshot(["val_a", "val_b"], layout))
        val = pd.DataFrame({"event_id": z["event_id"], "n_hat": z["a0_n_hat"], "conf": conf3(z["a0_q1"])})
        r = _indexed(frames.readings_api(PRODUCTION[model], layout, valid_only=True))
        test = pd.DataFrame({"event_id": r["event_id"], "n_hat": r["a0_n_hat"], "conf": r["a0_conf3"]})
        out = pd.concat([val, test], ignore_index=True)
    else:
        raise DataError(f"unknown model {model!r}")
    if "sample" not in out.columns:
        out["sample"] = "production"
    out = out.loc[out["event_id"].astype(str).str.startswith("W0:")].dropna(subset=["n_hat"])
    if out["event_id"].duplicated().any():
        raise DataError(f"{model}: more than one D0 reading of an event")
    return out.reset_index(drop=True)


def model_frame(model: str, ev: pd.DataFrame | None = None, layout: Layout | None = None) -> pd.DataFrame:
    """The model's D0 events (inner join of ``events`` and ``readings``)."""
    lay = resolve_layout(layout)
    base = events(lay) if ev is None else ev
    r = readings(model, lay)
    out = base.merge(r, on="event_id", how="inner", validate="one_to_one")
    out["model"] = model
    return out


def eval_rows(df: pd.DataFrame, split: str) -> pd.DataFrame:
    """The split's rows outside the embargo (PREREG §4.2; ``spec.eval_sample``)."""
    return df.loc[(df["split"] == split) & ~df["embargo"]]


# --- the conditioning study's frame -------------------------------------------------------------------------

CONTEXT_MARKET: Final = "states/context_market.parquet"
MARKET: Final = {"public": "strategy/market_public.parquet", "test": "strategy/market_test.parquet"}
MARKET_PRICES: Final = "market/market_prices.parquet"  # NA-00's registered copy of Data/market
VIX: Final = "^VIX"
PAYROLLS: Final = "artifacts/NA-13b/inputs/payrolls.yaml"


def payroll_dates(layout: Layout | None = None) -> frozenset[date]:
    """The BLS Employment Situation release days (08:30 ET), hand-checked on bls.gov (``PAYROLLS``)."""
    rows = load_yaml(resolve_layout(layout).root / PAYROLLS)["releases"]
    return frozenset(date.fromisoformat(str(r["date"])) for r in rows)


def vix_prev(sessions: Sequence[date], layout: Layout | None = None) -> pd.Series:
    """The ^VIX close of the latest day on or before t−1 (the previous NYSE session) for each session t: a
    t−1 input (operator decision of the NA-13b session; the frozen states used the same closes)."""
    m = io.read_parquet(MARKET_PRICES, columns=["symbol", "date", "close"], layout=layout)
    v = m.loc[m["symbol"] == VIX].dropna(subset=["close"])
    s = pd.Series(v["close"].to_numpy(dtype=float), index=_dates(v["date"]).to_numpy()).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    days_ = list(s.index)
    out = {}
    for t in sessions:
        i = bisect.bisect_right(days_, calendar.prev_session(t)) - 1
        out[t] = float(s.iloc[i]) if i >= 0 else np.nan
    return pd.Series(out, name="vix_prev", dtype=float)


def spy_overnight(layout: Layout | None = None) -> pd.DataFrame:
    """SPY's close(t−1) → open(t) return per session, (1 + r_cc)/(1 + r_id) − 1 of NA-13's market files
    (validation: the public build; 2026: NA-13's one logged lock sequence; no new read). Known at the open,
    after the 09:15 decision (``configs/availability.yaml``: ``post`` at D0)."""
    parts = []
    for rel in MARKET.values():
        m = io.read_parquet(rel, columns=["session", "r_spy_cc", "r_spy_id"], layout=layout)
        parts.append(m.groupby("session", as_index=False)[["r_spy_cc", "r_spy_id"]].first())
    s = pd.concat(parts, ignore_index=True)
    s["session"] = _dates(s["session"])
    s = s.drop_duplicates("session", keep="last")
    s["r_spy_on"] = (1.0 + s["r_spy_cc"]) / (1.0 + s["r_spy_id"]) - 1.0
    return s[["session", "r_spy_on"]].reset_index(drop=True)


def days(ev: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    """One row per session: its D0 event count, earnings-event count and weekday (from every D0 event of the
    session), the FOMC and CPI flags and the state's t−1 VIX level percentile (``context_market``), the
    payroll flag, the t−1 VIX close and SPY's overnight move."""
    g = ev.groupby("session")
    out = pd.DataFrame(
        {"n_events": g.size(), "n_earnings": g["earnings"].sum(min_count=1).fillna(0.0)}
    ).reset_index()
    out["weekday"] = pd.to_datetime(out["session"]).dt.day_of_week
    cm = io.read_parquet(
        CONTEXT_MARKET, columns=["session", "mkt_vix_level_pct", "macro_cpi_today", "macro_fomc_today"],
        layout=layout,
    )  # fmt: skip
    cm["session"] = _dates(cm["session"])
    out = out.merge(cm, on="session", how="left", validate="one_to_one")
    out["macro_payrolls_today"] = out["session"].isin(payroll_dates(layout))
    out["vix_prev"] = out["session"].map(vix_prev(list(out["session"]), layout))
    out = out.merge(spy_overnight(layout), on="session", how="left", validate="one_to_one")
    return out


def study_frame(layout: Layout | None = None) -> pd.DataFrame:
    """Every D0 event with the readings the conditions use: Laya-Fin's and d1-ultra's N̂, value V and the
    conditions' inputs (d1-ultra's A2 labels, Laya-Fin's predicted magnitude), span-02's and drex-v2.0's N̂
    (val-B and test), and the session attributes of ``days``."""
    lay = resolve_layout(layout)
    ev = events(lay)
    lf = frame("laya_fin", ["event_id", "a0_n_hat", "a0_v", "a0_mag_mean"], lay)
    lf = lf.rename(columns={"a0_n_hat": "n_laya_fin", "a0_v": "v_laya_fin", "a0_mag_mean": "lf_mag"})
    d1 = frame("d1_ultra", ["event_id", "a0_n_hat", "a0_v", *D1_LABELS], lay)
    d1 = d1.rename(columns={"a0_n_hat": "n_d1_ultra", "a0_v": "v_d1_ultra", "a0_conf3": "d1_conf"})
    out = ev.merge(lf, on="event_id", how="left", validate="one_to_one")
    out = out.merge(d1, on="event_id", how="left", validate="one_to_one")
    for m in ("span_02", "drex_v2"):
        r = readings(m, lay)
        r = r.loc[r["sample"] == "production", ["event_id", "n_hat"]].rename(columns={"n_hat": f"n_{m}"})
        out = out.merge(r, on="event_id", how="left", validate="one_to_one")
    out = out.merge(days(ev, lay).drop(columns=["weekday"]), on="session", how="left", validate="many_to_one")
    return out
