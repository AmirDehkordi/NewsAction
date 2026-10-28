"""NA-11: the operator's disclosed val-A probes (not hypotheses; ``configs/production.yaml`` ``probes``), next
to the API models' NA-06 screens (PREREG §8.3): ``artifacts/NA-11/probes_val_a.csv``.

Every row comes from ``laya_local.probe_table`` on the model's own readings:

- **API models** (NA-06 stage 2): NA-06's probe readings (``work/dm/tournament/probes.parquet``) and, for the
  real news of the shuffled-probe events and the N̂ scale, their stage-2 Call A readings
  (``stage2.parquet``, tag ``s2a``). The recomputed NA-06 values must equal NA-06's leaderboard, and the
  frozen screen verdicts are copied from it (``screen_*``).
- **Laya zero-shot** (local): NA-06's three probes on its own readings (``laya_local``); the real news and
  the N̂ scale from NA-09's val-A file (``work/baselines/laya_zeroshot.parquet``).
- **Laya-Fin and the anchor** (S7 on Kaggle, masked states only): the edit pairs and shuffled news; the
  originals, the real news and the N̂ scale from NA-08's val-A predictions; no unmasked probe (unmasked
  states never leave this machine).

The operator's descriptive additions (after the freeze; the frozen screen verdicts stay as computed):
``right_way``, ``shift_sd``, ``ic_real_same_events`` and ``real_minus_shuffled`` (``probe_table``). NA-06's
flip screen counts only pairs with |N̂_orig| ≥ 0.25, which a model with a narrow N̂ scale rarely reaches.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io
from newsaction.paths import Layout, resolve_layout
from newsaction.production import ProductionError, artifacts_dir
from newsaction.production.laya_local import MODEL as LAYA_ZS
from newsaction.production.laya_local import PROBE_FILE, probe_table
from newsaction.train import PREDICTIONS_DIR
from newsaction.train.import_preds import read_instrument

TABLE: Final = "probes_val_a.csv"
NA06_LEADERBOARD: Final = "artifacts/NA-06/leaderboard.csv"
NA06_PROBES: Final = "dm/tournament/probes.parquet"
NA06_STAGE2: Final = "dm/tournament/stage2.parquet"
NA09_LAYA: Final = "baselines/laya_zeroshot.parquet"
NA06_NAMES: Final = {
    "counterfactual_orig": "flip_orig",
    "counterfactual_edit": "flip_edit",
    "masked": "masked_twin",
    "unmasked": "unmasked",
    "shuffled": "shuffled",
}
CHECKED: Final = ("flip_rate", "edit_mean_shift", "ic_masked", "ic_unmasked", "ic_shuffled")
CHECK_TOL: Final = 1e-9
TRAINED: Final = ("laya_fin", "anchor")


def _real(values: pd.DataFrame, readings: pd.DataFrame) -> pd.DataFrame:
    """``values`` (event_id, n_hat) of the shuffled-probe events, as probe ``real``."""
    ids = set(readings.loc[readings["probe"] == "shuffled", "event_id"])
    return values.loc[values["event_id"].isin(ids), ["event_id", "n_hat"]].assign(probe="real")


def _sd(n_hat: pd.Series) -> float:
    v = n_hat.astype(float)
    return float(v[np.isfinite(v)].std())


def api_rows(layout: Layout | None = None) -> list[dict[str, Any]]:
    lay = resolve_layout(layout)
    lb = pd.read_csv(lay.root / NA06_LEADERBOARD).set_index("model")
    lb = lb.loc[lb["stage2"].astype(bool)]
    pr = io.read_parquet(NA06_PROBES, columns=["model", "event_id", "probe", "n_hat", "valid"], layout=lay)
    s2 = io.read_parquet(NA06_STAGE2, columns=["model", "event_id", "tag", "n_hat", "valid"], layout=lay)
    out = []
    for model in lb.index:
        r = pr.loc[(pr["model"] == model) & pr["probe"].isin(list(NA06_NAMES)) & pr["valid"].astype(bool)]
        r = r.assign(probe=r["probe"].map(NA06_NAMES))[["probe", "event_id", "n_hat"]]
        a = s2.loc[(s2["model"] == model) & (s2["tag"] == "s2a") & s2["valid"].astype(bool)]
        r = pd.concat([r, _real(a, r)], ignore_index=True)
        row = probe_table(r, str(model), lay, _sd(a["n_hat"])) | {"kind": "api (NA-06 stage 2)"}
        diff = {c: abs(float(row[c]) - float(lb.loc[model, c])) for c in CHECKED}
        if max(diff.values()) > CHECK_TOL:
            raise ProductionError(f"{model}: the recomputed NA-06 probe values differ from NA-06's: {diff}")
        screens = [c for c in lb.columns if c.startswith("screen_")]
        out.append(row | {c: lb.loc[model, c] for c in screens})
    return out


def local_row(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    r = io.read_parquet(PROBE_FILE, layout=lay)[["probe", "event_id", "n_hat"]]
    nb = io.read_parquet(NA09_LAYA, columns=["event_id", "split", "call", "N_hat"], layout=lay)
    nb = nb.loc[(nb["split"] == "val_a") & (nb["call"] == "A")].rename(columns={"N_hat": "n_hat"})
    r = pd.concat([r, _real(nb, r)], ignore_index=True)
    return probe_table(r, LAYA_ZS, lay, _sd(nb["n_hat"])) | {"kind": "local zero-shot"}


def trained_readings(model: str, layout: Layout | None = None) -> tuple[pd.DataFrame, float] | None:
    """(probe, event_id, n_hat) of a trained instrument and its val-A N̂ SD: S7's flip_edit and shuffled
    states; NA-08's val-A Call A D0 predictions of the edited events' originals (``flip_orig``) and of the
    shuffled events with their real news (``real``)."""
    rel = f"{PREDICTIONS_DIR}/{model}_probes.parquet"
    if not (resolve_layout(layout).work / rel).is_file():
        return None
    p = io.read_parquet(rel, layout=layout)
    p = p.loc[p["question"] == "react", ["variant", "event_id", "n_hat"]].rename(columns={"variant": "probe"})
    va = read_instrument(model, "val_a", layout)
    va = va.loc[(va["call"] == "A") & (va["window"] == "W0") & (va["question"] == "react")]
    edited = set(p.loc[p["probe"] == "flip_edit", "event_id"])
    orig = va.loc[va["event_id"].isin(edited), ["event_id", "n_hat"]].assign(probe="flip_orig")
    return pd.concat([p, orig, _real(va, p)], ignore_index=True), _sd(va["n_hat"])


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    rows = [*api_rows(lay), local_row(lay)]
    for m in TRAINED:
        got = trained_readings(m, lay)
        if got is not None:
            rows.append(probe_table(got[0], m, lay, got[1]) | {"kind": "trained (S7)"})
    table = pd.DataFrame(rows)
    table.to_csv(artifacts_dir(lay) / TABLE, index=False)
    return {"rows": table.to_dict("records")}


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    print(json.dumps(run(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
