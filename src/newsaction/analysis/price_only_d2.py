"""NA-12's first step after unblinding: the price-only baseline's D2 test predictions (PREREG §10.4; the
post-freeze PREREG §15 NA-11 row on timing; NA-11 REPORT §7.1 item 1).

NA-09's booster ``work/baselines/models/price_only_y2.json`` and ``baselines.price_only.D2_FEATURES`` (the D0
features plus G = z_cc,t ``g_d2``, ``react_z_on`` = z_on,t and ``react_z_vol`` = z_vol,t) are fixed. One
feature builder serves both steps:

- ``check`` re-predicts NA-09's val-A and val-B D2 rows (the Call B states; the reaction file and the public
  panel's z_on, as NA-09's ``d2_frame``) and must reproduce ``work/baselines/price_only.parquet`` exactly,
  as ``production.price_only_test.check`` does at D0;
- ``run`` (after a passing check) predicts the test Call B D2 events with g_d2, z_on and z_vol of session t
  from ``work/analysis/targets_test.parquet`` (the unblinded outcomes) and z_vol of the previous session from
  the public panel (for the first test session) or the same file.

The other features are NA-04's t−1 context (``states/context_company.parquet``) and the event's tier.
Output: ``work/analysis/price_only_d2_test.parquet`` in NA-09's common schema (call B, ``y_hat``). Run it in
its own process: LightGBM is imported only inside ``_model`` (it and torch segfault in one process, NA-09).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import pandas as pd

from newsaction import io, lock
from newsaction.analysis.unblind import CHUNK
from newsaction.analysis.unblind import OUT as TARGETS_TEST
from newsaction.baselines import schema as bs
from newsaction.baselines.data import PANEL, prev_sessions
from newsaction.baselines.gbm import matrix
from newsaction.baselines.price_only import D2_FEATURES
from newsaction.events import EVENTS_D2
from newsaction.paths import Layout, resolve_layout
from newsaction.states import CONTEXT_COMPANY
from newsaction.states.build import REACTION_D2

if TYPE_CHECKING:
    import lightgbm as lgb

OUT: Final = "analysis/price_only_d2_test.parquet"
STATES_VAL: Final = "states/callB_d2_E3.parquet"
STATES_TEST: Final = "states/callB_d2_E3_test.parquet"
NA09_PREDICTIONS: Final = "baselines/price_only.parquet"
MODEL: Final = "baselines/models/price_only_y2.json"
CHECK_TOL: Final = 1e-9
KEYS: Final = ["session", "symbol_id"]


class PriceOnlyError(RuntimeError):
    """NA-09's predictions are not reproduced, or an input is missing."""


def _dates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["session"] = pd.to_datetime(out["session"]).dt.date
    return out


def features(
    states: pd.DataFrame, reaction: pd.DataFrame, volume: pd.DataFrame, layout: Layout | None = None
) -> pd.DataFrame:
    """D2_FEATURES of the Call B ``states`` (event_id, company_id, session, split): the event's tier, the t−1
    context, ``reaction`` (session, symbol_id, g_d2, react_z_on, react_z_vol of session t) and ``volume``
    (session, symbol_id, z_vol) at the previous session (``z_vol_lag1``)."""
    lay = resolve_layout(layout)
    ev = io.read_parquet(EVENTS_D2, columns=["event_id", "symbol_id", "tier"], layout=lay)
    out = _dates(states[["event_id", "company_id", "session", "split"]]).merge(
        ev, on="event_id", how="left", validate="one_to_one"
    )
    if bool(out["symbol_id"].isna().any()):
        raise PriceOnlyError("a Call B state has no D2 event")
    out = out.merge(_dates(reaction), on=KEYS, how="left", validate="m:1")
    ctx = io.read_parquet(
        CONTEXT_COMPANY,
        columns=["session", "symbol_id", "z_m5", "z_m20", "z_m60", "ctx_sigma_cc_pct", "sector"],
        layout=lay,
    )
    out = out.merge(_dates(ctx), on=KEYS, how="left", validate="m:1")
    out["prev_session"] = out["session"].map(prev_sessions(out["session"]))
    vol = _dates(volume).rename(columns={"session": "prev_session", "z_vol": "z_vol_lag1"})
    out = out.merge(vol, on=["prev_session", "symbol_id"], how="left", validate="m:1")
    return out.drop(columns=["prev_session"])


def frame_val(layout: Layout | None = None) -> pd.DataFrame:
    """NA-09's D2 inputs for val-A and val-B: the reaction file's G and z_vol, the public panel's z_on."""
    lay = resolve_layout(layout)
    states = io.read_parquet(STATES_VAL, columns=["event_id", "company_id", "session", "split"], layout=lay)
    states = states.loc[states["split"].isin(["val_a", "val_b"])]
    rx = io.read_parquet(REACTION_D2, columns=[*KEYS, "g_d2", "react_z_vol"], layout=lay)
    panel = io.read_parquet(PANEL, columns=[*KEYS, "z_on", "z_vol"], layout=lay)
    rx = _dates(rx).merge(
        _dates(panel[[*KEYS, "z_on"]]).rename(columns={"z_on": "react_z_on"}), on=KEYS, how="left"
    )
    return features(states, rx, panel[[*KEYS, "z_vol"]], lay)


def frame_test(layout: Layout | None = None) -> pd.DataFrame:
    """The test Call B D2 events with session t's outcomes from ``targets_test`` (after unblinding)."""
    lay = resolve_layout(layout)
    states = io.read_parquet(STATES_TEST, columns=["event_id", "company_id", "session", "split"], layout=lay)
    tt = io.read_parquet(TARGETS_TEST, columns=[*KEYS, "g_d2", "z_on", "z_vol"], layout=lay)
    rx = tt.rename(columns={"z_on": "react_z_on", "z_vol": "react_z_vol"})
    public = io.read_parquet(PANEL, columns=[*KEYS, "z_vol"], layout=lay)
    volume = pd.concat([_dates(public), _dates(tt[[*KEYS, "z_vol"]])], ignore_index=True)
    return features(states, rx, volume, lay)


def _model(layout: Layout | None = None) -> lgb.Booster:
    import lightgbm as lgb  # never at import time: LightGBM and torch segfault in one process (NA-09)

    doc = json.loads((resolve_layout(layout).work / MODEL).read_text(encoding="utf-8"))
    if list(doc["record"]["features"]) != list(D2_FEATURES) or doc["record"]["target"] != "y2":
        raise PriceOnlyError(f"{MODEL}: features {doc['record']['features']} != {list(D2_FEATURES)}")
    return lgb.Booster(model_str=doc["model"]["lightgbm"])


def predict(df: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    y_hat = np.asarray(_model(layout).predict(matrix(df, D2_FEATURES)), dtype=np.float64)
    return pd.DataFrame(
        {
            "event_id": df["event_id"].to_numpy(),
            "model": "price_only",
            "call": "B",
            "split": df["split"].to_numpy(),
            "session": df["session"].to_numpy(),
            "company_id": df["company_id"].to_numpy(),
            "y_hat": y_hat,
            "extra": json.dumps({}),
        }
    )


def check(layout: Layout | None = None) -> dict[str, Any]:
    """Re-predict NA-09's val-A and val-B D2 rows; ``y_hat`` must equal NA-09's stored predictions."""
    lay = resolve_layout(layout)
    got = predict(frame_val(lay), lay)
    ref = io.read_parquet(NA09_PREDICTIONS, layout=lay)
    ref = ref.loc[(ref["call"] == "B") & ref["split"].isin(["val_a", "val_b"])]
    m = got.merge(ref, on="event_id", suffixes=("", "_na09"), validate="one_to_one")
    diff = float(np.nanmax(np.abs(m["y_hat"] - m["y_hat_na09"]))) if len(m) else float("nan")
    nan_mismatch = int((m["y_hat"].isna() != m["y_hat_na09"].isna()).sum())
    if len(m) != len(ref) or len(got) != len(ref) or nan_mismatch or not diff <= CHECK_TOL:
        raise PriceOnlyError(
            f"NA-09's val D2 predictions are not reproduced: rows {len(m)}/{len(ref)}, max |Δ| {diff}, "
            f"{nan_mismatch} NaN mismatches"
        )
    return {"rows": len(m), "by_split": m["split"].value_counts().to_dict(), "max_abs_diff_y_hat": diff}


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if not lock.is_frozen(lay) or not (lay.work / TARGETS_TEST).exists():
        raise PriceOnlyError("the D2 test predictions follow the freeze and the unblinding")
    out: dict[str, Any] = {"check": check(lay)}
    df = frame_test(lay)
    pred = bs.frame(predict(df, lay))
    io.write_parquet(
        pred,
        OUT,
        producer=CHUNK,
        layout=lay,
        description="NA-12: the price-only baseline's D2 test predictions (NA-09's saved y2 booster; G, z_on "
        "and z_vol of session t from targets_test)",
    )
    out |= {
        "rows": len(pred),
        "features_missing": {c: int(df[c].isna().sum()) for c in D2_FEATURES},
    }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    print(json.dumps(check() if args[:1] == ["check"] else run(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
