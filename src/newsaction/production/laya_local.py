"""NA-11: local Laya zero-shot (``local/laya-typed-decisions``, core battery; nothing leaves the machine).

- **Test Call A on D0** (PREREG §10.5; ``configs/production.yaml`` ``laya_zero_shot``): every test D0 state,
  after the freeze (the client refuses test states before it).
- **Disclosed val-A probes** (``configs/production.yaml`` ``probes``; the operator's addition, not
  hypotheses):
  NA-06's own probe states, built by ``tournament.run``'s spec builders for this model: the 200 counterfactual
  edit pairs (edited states; the originals are its cached Call A answers), the 1,000 unmasked val-A twins
  (probe tag ``unmasked_twin``) with their masked twins, and the 1,000 shuffled-news states. Their metrics
  follow NA-06's screens (``tournament.probes`` / ``tournament.metrics``) in ``probe_table``.

Outputs: ``work/dm/production/local_laya_typed_decisions_test.parquet`` and ``…_probes.parquet`` (the
``production.run.readings`` schema plus ``probe``).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io, lock
from newsaction.dm.client import CallSpec, DecisionClient
from newsaction.dm.runner import load_states, state_specs
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK, ProductionError
from newsaction.production.run import PRODUCTION_DIR, readings, slug

MODEL: Final = "local/laya-typed-decisions"
TEST_FILE: Final = f"{PRODUCTION_DIR}/{slug(MODEL)}_test.parquet"
PROBE_FILE: Final = f"{PRODUCTION_DIR}/{slug(MODEL)}_probes.parquet"
STATES_A: Final = "states/callA_d0_E3.parquet"


def test_specs(layout: Layout | None = None) -> list[CallSpec]:
    if not lock.is_frozen(layout):
        raise ProductionError("the test-period Laya run follows the freeze")
    rows = load_states(STATES_A, splits=["test"], layout=layout)
    return state_specs(rows, STATES_A, MODEL, call="A", groups=("core",), tag="na11_laya_zs_test")


def probe_specs(layout: Layout | None = None) -> dict[str, list[CallSpec]]:
    """NA-06's probe states for this model (``tournament.run`` builders)."""
    from newsaction.tournament import run as tr

    ctx = tr.Ctx.load(layout)
    edited, _ = tr.counterfactual_specs(ctx, MODEL)
    cf_ids = ctx.counterfactual()["event_id"].astype(str).tolist()
    twins = ctx.ids("unmasked_twin")
    return {
        "flip_edit": edited,
        "flip_orig": tr.call_a_specs(ctx, MODEL, cf_ids, "na11_probe_cf_orig"),
        "unmasked": tr.unmasked_specs(ctx, MODEL),
        "masked_twin": tr.call_a_specs(ctx, MODEL, twins, "na11_probe_masked"),
        "shuffled": tr.shuffled_specs(ctx, MODEL),
    }


def run(part: str, layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    with DecisionClient(CHUNK, layout=lay) as cl:
        if part == "test":
            res = cl.decide(test_specs(lay))
            df = readings(res, "a0")
            io.write_parquet(
                df,
                TEST_FILE,
                producer=CHUNK,
                layout=lay,
                description="NA-11: Laya zero-shot test Call A on D0 (local, core battery)",
            )
            return {"rows": len(df), "valid": int(df["valid"].sum())}
        if part == "probes":
            parts = []
            for name, specs in probe_specs(lay).items():
                res = cl.decide(specs)
                parts.append(readings(res, "a0").assign(probe=name))
            df = pd.concat(parts, ignore_index=True)
            io.write_parquet(
                df,
                PROBE_FILE,
                producer=CHUNK,
                layout=lay,
                description="NA-11: Laya zero-shot on NA-06's probe states (flip, masked/unmasked, "
                "shuffled; local)",
            )
            return {"rows": len(df), "by_probe": df.groupby("probe").size().to_dict()}
    raise ProductionError(f"unknown part {part!r} (test | probes)")


def probe_table(
    readings_by_probe: pd.DataFrame,
    model: str,
    layout: Layout | None = None,
    n_hat_sd: float | None = None,
) -> dict[str, Any]:
    """NA-06's screen metrics on a model's probe readings (``probe``: flip_edit, flip_orig, unmasked,
    masked_twin, shuffled, real; ``event_id``, ``n_hat``): flip rate, masked − unmasked paired daily IC with
    z_cc, shuffled-news daily IC (Newey–West), each with NA-06's threshold beside it. Descriptive additions
    (the operator's, after the freeze; the frozen screens stay as computed): ``right_way``, the share of the
    edit pairs whose N̂ moves the way the edit points; ``shift_sd``, ``edit_mean_shift`` over ``n_hat_sd``
    (the SD of the model's own val-A Call A D0 N̂); and, when ``real`` holds the model's readings of the
    shuffled-probe events with their real news, ``ic_real_same_events`` and the paired real − shuffled
    difference."""
    from newsaction.tournament import metrics as tmx
    from newsaction.tournament import probes as pr
    from newsaction.tournament import tournament_config
    from newsaction.tournament.run import COUNTERFACTUAL

    cfg = tournament_config(layout)
    sc, mc = cfg.screens, cfg.metric
    r = readings_by_probe
    panel = io.read_parquet(
        "panel/panel_public.parquet", columns=["session", "symbol_id", "z_cc"], layout=layout
    )
    ev = io.read_parquet(
        "events/events_d0.parquet", columns=["event_id", "session", "symbol_id"], layout=layout
    )
    tgt = ev.merge(panel, on=["session", "symbol_id"], how="left")[["event_id", "session", "z_cc"]]
    out: dict[str, Any] = {"model": model}
    e = r.loc[r["probe"] == "flip_edit"].set_index("event_id")["n_hat"]
    o = r.loc[r["probe"] == "flip_orig"].set_index("event_id")["n_hat"]
    both = pd.concat([o.rename("o"), e.rename("e")], axis=1, join="inner").dropna()
    if len(both):
        rate, n = pr.flip_rate(both["o"].to_numpy(), both["e"].to_numpy(), sc.flip_min_abs_n_hat)
        cf = io.read_parquet(COUNTERFACTUAL, columns=["event_id", "polarity"], layout=layout)
        pol = cf.set_index("event_id")["polarity"].reindex(both.index).astype(float).to_numpy()
        out |= {
            "flip_rate": rate,
            "flip_pairs": n,
            "flip_screen": sc.flip_rate_min,
            # beside NA-06's metric, two that do not depend on the model's N̂ scale reaching 0.25:
            # NA-06's edit_mean_shift (positive = N̂ moves the way the edit points) and the sign flips of
            # every valid pair
            "edit_mean_shift": float(np.mean((both["e"].to_numpy() - both["o"].to_numpy()) * -pol)),
            "flip_rate_all_pairs": float((np.sign(both["e"]) != np.sign(both["o"])).mean()),
            "flip_pairs_valid": len(both),
            "right_way": float(np.mean((both["e"].to_numpy() - both["o"].to_numpy()) * -pol > 0)),
        }
        if n_hat_sd:
            out["n_hat_sd_val_a"] = n_hat_sd
            out["shift_sd"] = out["edit_mean_shift"] / n_hat_sd

    def ic_of(name: str, ids: set[str] | None = None) -> pd.Series:
        f = r.loc[r["probe"] == name, ["event_id", "n_hat"]]
        if ids is not None:
            f = f.loc[f["event_id"].isin(ids)]
        f = f.merge(tgt, on="event_id", how="inner")
        return tmx.daily_ic(f, "n_hat", "z_cc", mc.min_names_per_day)

    if (r["probe"] == "unmasked").any():
        um, ma = ic_of("unmasked"), ic_of("masked_twin")
        st = tmx.paired(um, ma, mc.nw_lags)
        su, sm = tmx.ic_stats(um, mc.nw_lags), tmx.ic_stats(ma, mc.nw_lags)
        out |= {
            "ic_masked": sm.mean,
            "ic_masked_t": sm.t,
            "ic_unmasked": su.mean,
            "ic_unmasked_t": su.t,
            "unmasked_minus_masked": st.mean,
            "unmasked_minus_masked_t": st.t,
            "masked_screen": sc.unmasked_minus_masked_max,
        }
    if (r["probe"] == "shuffled").any():
        sh = ic_of("shuffled")
        st = tmx.ic_stats(sh, mc.nw_lags)
        out |= {"ic_shuffled": st.mean, "ic_shuffled_t": st.t, "shuffled_screen_t": sc.shuffled_t}
        if (r["probe"] == "real").any():
            shuffled_ids = set(r.loc[r["probe"] == "shuffled", "event_id"])
            real_ids = set(r.loc[r["probe"] == "real", "event_id"])
            if real_ids - shuffled_ids:
                raise ProductionError(f"{model}: real-news readings outside the shuffled-probe events")
            ids = shuffled_ids & real_ids  # events with both readings valid
            real, same = ic_of("real", ids), ic_of("shuffled", ids)
            sr, sd = tmx.ic_stats(real, mc.nw_lags), tmx.paired(real, same, mc.nw_lags)
            out |= {
                "ic_real_same_events": sr.mean,
                "ic_real_same_events_t": sr.t,
                "real_minus_shuffled": sd.mean,
                "real_minus_shuffled_t": sd.t,
                "real_shuffled_events": len(ids),
            }
    return {k: (float(v) if isinstance(v, np.floating) else v) for k, v in out.items()}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    for part in args or ["probes", "test"]:
        print(json.dumps({part: run(part)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
