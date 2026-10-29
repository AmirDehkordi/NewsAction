"""NA-13b on the real files: the readings, the frozen gates' confidence and the operator's three disclosures.

The disclosures (operator prompt NA-13b, items 2(c), 2(d) and 2(e)) were computed by the operator's assistant
before this chunk; the chunk's code must reproduce every printed digit.
"""

from __future__ import annotations

import pytest

from newsaction.analysis import spec
from newsaction.config import load_yaml
from newsaction.paths import CONFIGS, ROOT
from newsaction.selective import conditioning as cg
from newsaction.selective import conditions as cd
from newsaction.selective import coverage as cv
from newsaction.selective import data as sd
from newsaction.selective import watch as wt

pytestmark = pytest.mark.skipif(
    not (ROOT / "work" / "analysis" / "frame_d0_laya_fin.parquet").is_file(), reason="needs NA-12's frames"
)


@pytest.fixture(scope="module")
def events() -> object:
    return sd.events()


def test_every_model_reads_every_event_and_the_gates_reproduce(events: object) -> None:
    gates = load_yaml(CONFIGS / "frozen.yaml")["calibration"]
    for m in sd.MODELS:
        f = sd.model_frame(m, events)  # type: ignore[arg-type]
        n = {s: len(sd.eval_rows(f, s)) for s in sd.SPLITS}
        assert n == {"val_a": 3000 if m in sd.STAGE2_MODEL else 8376, "val_b": 5506, "test": 13748}
        q70 = float(sd.eval_rows(f, "val_a")["conf"].quantile(0.7))
        gate = gates[sd.CALIBRATION_KEY[m]]["gates"]["D0"]["value"]
        if m == "d1_ultra":  # the frozen gate was fit on NA-06's 3,000-event sample, not production
            assert q70 == pytest.approx(gate, abs=5e-4)
        else:
            assert q70 == pytest.approx(gate, abs=1e-15)


def test_the_band_disclosure_reproduces() -> None:
    want = {
        "d1_ultra": {"cuts": (0.419, 0.648, 1.079), "hit_cc": (0.587, 0.566, 0.556), "cc": (0.80, 0.75, 0.59),
                     "on": (1.52, 1.16, 0.93), "id": (0.004, 0.140, 0.101)},
        "laya_fin": {"cuts": (0.032, 0.054, 0.133), "hit_cc": (0.562, 0.542, 0.526), "cc": (0.46, 0.35, 0.17),
                     "id": (0.106, 0.123, 0.068)},
    }  # fmt: skip
    for m, w in want.items():
        q, g = cv.bands(sd.frame(m, ["event_id", "split", "embargo", "a0_n_hat", "z_cc", "z_on", "z_id"]))
        assert tuple(round(v, 3) for v in q) == w["cuts"]
        top = g.loc[g["band"] == "top 10%"].set_index("split")
        for col, vals in w.items():
            if col == "cuts":
                continue
            dec = 3 if col in ("hit_cc", "id") else 2
            assert tuple(round(float(top.at[s, col]), dec) for s in sd.SPLITS) == vals, (m, col)
        bottom = g.loc[g["band"] == "bottom 50%"]
        assert bottom[["cc", "id"]].abs().max().max() < 0.05  # "about 0 everywhere"


def test_the_d1_disclosure_reproduces() -> None:
    want = {  # pre-open / 10:00 / revision / first-bar IC with y1, val-A ; val-B ; test
        "laya_fin": (
            (0.047, 0.034, 0.001, 0.030),
            (0.008, -0.024, -0.027, -0.034),
            (0.026, -0.013, -0.036, -0.016),
        ),
        "d1_ultra": (
            (0.014, 0.029, 0.018, 0.030),
            (0.019, -0.020, -0.043, -0.034),
            (-0.004, -0.014, -0.011, -0.016),
        ),
    }
    got = wt.run(spec.load_config()).set_index(["model", "split", "statistic"])["value"]
    for m, rows in want.items():
        for split, vals in zip(sd.SPLITS, rows, strict=True):
            ics = tuple(round(float(got[(m, split, s)]), 3) for s in wt.IC_STATS)
            assert ics == vals, (m, split)


def test_the_conditioning_preview_reproduces() -> None:
    study = sd.study_frame()
    study = study.loc[study["split"].isin(cg.VAL)].reset_index(drop=True)
    c = cd.cuts(study)
    conds = [
        cd.BY_KEY[k] for k in ("e2_numbers", "e2_material", "e4_busy_event", "e7_agree", "e2_low_uncertainty")
    ]
    v = cg.evaluate(study, c, list(cg.VAL), outcomes=["z_id"], conditions=conds).set_index(
        ["model", "condition", "split"]
    )

    def row(m: str, k: str, s: str) -> tuple[float, float, float, float]:
        r = v.loc[(m, k, s)]
        return (round(r["inside"], 3), round(r["inside_t"], 1), round(r["diff"], 3), round(r["diff_t"], 1))

    assert row("laya_fin", "e2_numbers", "val_a") == (0.087, 2.3, 0.061, 1.6)
    assert row("laya_fin", "e2_numbers", "val_b") == (0.145, 3.3, 0.150, 3.0)
    assert row("laya_fin", "e2_material", "val_a") == (0.088, 2.8, 0.074, 2.3)
    assert row("laya_fin", "e2_material", "val_b") == (0.082, 2.6, 0.088, 2.5)
    assert row("laya_fin", "e4_busy_event", "val_a") == (0.081, 2.0, 0.046, 1.2)
    assert row("laya_fin", "e4_busy_event", "val_b") == (0.196, 2.6, 0.191, 2.5)
    assert row("d1_ultra", "e7_agree", "val_a") == (0.052, 2.1, 0.101, 2.0)
    assert row("d1_ultra", "e7_agree", "val_b") == (0.022, 0.8, 0.073, 1.4)
    r = v.loc[("laya_fin", "e2_low_uncertainty", "val_b")]
    assert (round(r["diff"], 3), round(r["diff_t"], 1)) == (-0.139, -3.4)
    for m, base in (("laya_fin", (0.047, 0.031)), ("d1_ultra", (0.017, -0.004))):
        f = cg.frame_for(study, m, "z_id")
        got = tuple(round(float(sd.eval_rows(f, s).groupby("session")["y"].mean().mean()), 3) for s in cg.VAL)
        assert got == base
