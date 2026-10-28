"""NA-11 S8: the price-only baseline's test predictions at D0 (PREREG §10.4; ``configs/production.yaml``
``price_only``) with NA-09's saved boosters (``work/baselines/models/price_only_{e5,abs_z_cc}.json``; the
category lists are part of the model strings).

- **Features** at D0 of session t (NA-09's ``D0_FEATURES``): the context NA-04 built from t−1 data
  (``states/context_company.parquet``: z_m5, z_m20, z_m60, the σ regime, sector), the tier, and
  ``z_vol_lag1`` = z_vol of the previous session, from the public panel for 2025-12-31 and, for a 2026
  session, ``react_z_vol`` of ``reactions.build_reactions(..., "test", "D2")`` (through the lock: a reaction
  known at the previous close).
- **Predictions**: N_hat (e5 booster), mag_hat = max(|z_cc| booster, 0), P_up / P_down from NA-09's val-A
  isotonic maps of N_hat. ``check`` first re-predicts NA-09's val-A and val-B rows from the same features
  and compares them with ``work/baselines/price_only.parquet``.
- **D2** is not produced here: its ``react_z_on`` (z_on,t) is not among the frozen reactions' columns
  (operator decision pending).

Output: ``work/dm/production/price_only_test.parquet`` (NA-09's common schema). Run it in its own process:
LightGBM is imported only inside ``_model`` (it and torch segfault in one process, NA-09).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction import io, lock
from newsaction.baselines import schema as bs
from newsaction.baselines.data import PANEL, prev_sessions
from newsaction.baselines.gbm import matrix
from newsaction.baselines.price_only import D0_FEATURES
from newsaction.dm.runner import load_states
from newsaction.events import EVENTS_D0
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError
from newsaction.production.plan import load_plan
from newsaction.production.run import PRODUCTION_DIR
from newsaction.states import CONTEXT_COMPANY

if TYPE_CHECKING:
    import lightgbm as lgb

OUT: Final = f"{PRODUCTION_DIR}/price_only_test.parquet"
NA09_PREDICTIONS: Final = "baselines/price_only.parquet"
CHECK_TOL: Final = 1e-9


def _dates(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.date


def frame(splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """The D0 features of the Call A D0 states of ``splits`` (module docstring)."""
    lay = resolve_layout(layout)
    states = load_states(load_plan().states["A_D0"], splits=splits, layout=lay)
    out = states[["event_id", "session", "split"]].merge(
        io.read_parquet(EVENTS_D0, columns=["event_id", "company_id", "symbol_id", "tier"], layout=lay),
        on="event_id",
        how="left",
        validate="one_to_one",
    )
    out["session"] = _dates(out["session"])
    ctx = io.read_parquet(
        CONTEXT_COMPANY,
        columns=["session", "symbol_id", "z_m5", "z_m20", "z_m60", "ctx_sigma_cc_pct", "sector"],
        layout=lay,
    )
    ctx["session"] = _dates(ctx["session"])
    out = out.merge(ctx, on=["session", "symbol_id"], how="left", validate="m:1")
    vol = io.read_parquet(PANEL, columns=["session", "symbol_id", "z_vol"], layout=lay)
    if "test" in splits:
        from newsaction.panel import reactions

        rx = reactions.build_reactions(pd.DataFrame(), "test", "D2", layout=lay)  # through the lock
        vol = pd.concat(
            [vol, rx[["session", "symbol_id", "react_z_vol"]].rename(columns={"react_z_vol": "z_vol"})],
            ignore_index=True,
        )
    vol["session"] = _dates(vol["session"])
    out["prev_session"] = out["session"].map(prev_sessions(out["session"]))
    vol = vol.rename(columns={"session": "prev_session", "z_vol": "z_vol_lag1"})
    out = out.merge(vol, on=["prev_session", "symbol_id"], how="left", validate="m:1")
    return out.drop(columns=["prev_session"])


def _model(target: str, layout: Layout | None = None) -> tuple[lgb.Booster, dict[str, Any]]:
    import lightgbm as lgb  # never at import time: LightGBM and torch segfault in one process (NA-09)

    path = resolve_layout(layout).work / f"baselines/models/price_only_{target}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    if list(doc["record"]["features"]) != list(D0_FEATURES):
        raise ProductionError(f"price_only_{target}: features {doc['record']['features']} != {D0_FEATURES}")
    return lgb.Booster(model_str=doc["model"]["lightgbm"]), doc


def _iso(x: npt.NDArray[np.float64], m: dict[str, Any]) -> npt.NDArray[np.float64]:
    """An isotonic map with ``out_of_bounds="clip"`` from its thresholds (sklearn's predict)."""
    return np.asarray(np.interp(x, np.asarray(m["x"], float), np.asarray(m["y"], float)), dtype=np.float64)


def predict(df: pd.DataFrame, layout: Layout | None = None) -> pd.DataFrame:
    n_model, n_doc = _model("e5", layout)
    mag_model, _ = _model("abs_z_cc", layout)
    x = matrix(df, D0_FEATURES)
    n_hat = np.asarray(n_model.predict(x), dtype=np.float64)
    maps = n_doc["prob_maps"]
    up, down = _iso(n_hat, maps["up"]), _iso(n_hat, maps["down"])
    total = up + down
    scale = np.where(total > 1.0, 1.0 / np.where(total > 0, total, 1.0), 1.0)
    return pd.DataFrame(
        {
            "event_id": df["event_id"].to_numpy(),
            "model": "price_only",
            "call": "A",
            "split": df["split"].to_numpy(),
            "session": df["session"].to_numpy(),
            "company_id": df["company_id"].to_numpy(),
            "N_hat": n_hat,
            "P_up": up * scale,
            "P_down": down * scale,
            "mag_hat": np.maximum(np.asarray(mag_model.predict(x), dtype=np.float64), 0.0),
            "extra": json.dumps({}),
        }
    )


def check(layout: Layout | None = None) -> dict[str, Any]:
    """Re-predict NA-09's val-A and val-B D0 rows; every column must equal NA-09's stored predictions."""
    lay = resolve_layout(layout)
    got = predict(frame(["val_a", "val_b"], lay), lay)
    ref = io.read_parquet(NA09_PREDICTIONS, layout=lay)
    ref = ref.loc[(ref["call"] == "A") & ref["split"].isin(["val_a", "val_b"])]
    m = got.merge(ref, on="event_id", suffixes=("", "_na09"), validate="one_to_one")
    diff = {
        c: float(np.nanmax(np.abs(m[c] - m[f"{c}_na09"]))) for c in ("N_hat", "P_up", "P_down", "mag_hat")
    }
    if len(m) != len(ref) or max(diff.values()) > CHECK_TOL:
        raise ProductionError(f"NA-09's val predictions are not reproduced: rows {len(m)}/{len(ref)}, {diff}")
    return {"rows": len(m), "max_abs_diff": diff}


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if not lock.is_frozen(lay):
        raise ProductionError("the test predictions follow the freeze")
    out: dict[str, Any] = {"check": check(lay)}
    df = frame(["test"], lay)
    pred = bs.frame(predict(df, lay))
    io.write_parquet(
        pred,
        OUT,
        producer=CHUNK,
        layout=lay,
        description="NA-11 S8: the price-only baseline's test predictions at D0 (NA-09's saved models)",
    )
    out |= {
        "rows": len(pred),
        "features_missing": {c: int(df[c].isna().sum()) for c in D0_FEATURES},
    }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    print(json.dumps(check() if args[:1] == ["check"] else run(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
