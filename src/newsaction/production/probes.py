"""NA-11: the operator's disclosed val-A probes (not hypotheses; ``configs/production.yaml`` ``probes``), next
to the API models' NA-06 screens (PREREG §8.3): ``artifacts/NA-11/probes_val_a.csv``.

- **API models** (NA-06 stage 2): NA-06's leaderboard values (``artifacts/NA-06/leaderboard.csv``).
- **Laya zero-shot** (local): NA-06's three probes on its own readings (``laya_local.probe_table``): the flip
  rate on the 200 counterfactual edit pairs, masked vs unmasked on the 1,000 val-A twins, shuffled news.
- **Laya-Fin and the anchor** (S7 on Kaggle, masked states only): the flip rate (the edited states predicted
  on Kaggle, the originals from NA-08's val-A predictions) and shuffled news; no unmasked probe (unmasked
  states never leave this machine).

Each value sits beside NA-06's screen threshold (``screen`` columns); none of it is a test.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, Final

import pandas as pd

from newsaction import io
from newsaction.paths import Layout, resolve_layout
from newsaction.production import artifacts_dir
from newsaction.production.laya_local import MODEL as LAYA_ZS
from newsaction.production.laya_local import PROBE_FILE, probe_table
from newsaction.train import PREDICTIONS_DIR
from newsaction.train.import_preds import read_instrument

TABLE: Final = "probes_val_a.csv"
NA06_LEADERBOARD: Final = "artifacts/NA-06/leaderboard.csv"
NA06_COLUMNS: Final = (
    "flip_rate",
    "flip_n",
    "flip_pairs_valid",
    "edit_mean_shift",
    "ic_masked",
    "ic_masked_t",
    "ic_unmasked",
    "ic_unmasked_t",
    "unmasked_minus_masked",
    "unmasked_minus_masked_t",
    "ic_shuffled",
    "ic_shuffled_t",
)
TRAINED: Final = ("laya_fin", "anchor")


def api_rows(layout: Layout | None = None) -> list[dict[str, Any]]:
    lb = pd.read_csv(resolve_layout(layout).root / NA06_LEADERBOARD)
    lb = lb.loc[lb["stage2"].astype(bool)]
    out = []
    for rec in lb.to_dict("records"):
        row = {"model": rec["model"], "kind": "api (NA-06 stage 2)"} | {c: rec[c] for c in NA06_COLUMNS}
        row["flip_pairs"] = row.pop("flip_n")
        out.append(row)
    return out


def trained_readings(model: str, layout: Layout | None = None) -> pd.DataFrame | None:
    """(probe, event_id, n_hat) of a trained instrument: S7's flip_edit and shuffled states, and NA-08's val-A
    Call A D0 predictions of the edited events' original states (``flip_orig``)."""
    rel = f"{PREDICTIONS_DIR}/{model}_probes.parquet"
    if not (resolve_layout(layout).work / rel).is_file():
        return None
    p = io.read_parquet(rel, layout=layout)
    p = p.loc[p["question"] == "react", ["variant", "event_id", "n_hat"]].rename(columns={"variant": "probe"})
    va = read_instrument(model, "val_a", layout)
    va = va.loc[(va["call"] == "A") & (va["window"] == "W0") & (va["question"] == "react")]
    edited = set(p.loc[p["probe"] == "flip_edit", "event_id"])
    orig = va.loc[va["event_id"].isin(edited), ["event_id", "n_hat"]].assign(probe="flip_orig")
    return pd.concat([p, orig], ignore_index=True)


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    rows = api_rows(lay)
    local = io.read_parquet(PROBE_FILE, layout=lay)
    rows.append(probe_table(local, LAYA_ZS, lay) | {"kind": "local zero-shot"})
    for m in TRAINED:
        r = trained_readings(m, lay)
        if r is not None:
            rows.append(probe_table(r, m, lay) | {"kind": "trained (S7)"})
    table = pd.DataFrame(rows)
    table.to_csv(artifacts_dir(lay) / TABLE, index=False)
    return {"rows": table.to_dict("records")}


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    print(json.dumps(run(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
