"""NA-12's entries in ``work/MANIFEST.json`` and ``docs/DATA_CONTRACT.md`` (GAC5), regenerated as a whole.

    uv run python -m newsaction.analysis.contract

``write`` registers every existing NA-12 artifact (``io.register_artifact``; the work files are registered by
``io.write_parquet`` when written) and rewrites the "NA-12" section of the contract with the current sha256
of each file: the fixed entries below, and one entry per results JSON, figure CSV and table file found on
disk. Run it after each step so a commit never leaves a registered file without its contract entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from newsaction import io
from newsaction.analysis.unblind import ARTIFACTS, CHUNK
from newsaction.paths import Layout, resolve_layout

HEADING: Final = "## NA-12 — unblinding and the pre-registered analyses (`newsaction.analysis`)"
OUTCOMES: Final = "the test period's outcomes, after unblinding (NA-12 S1)"


@dataclass(frozen=True)
class Entry:
    path: str
    producer: str
    inputs: str
    schema: str
    key: str
    rows: str
    availability: str


FIXED: Final = (
    Entry(
        "work/analysis/targets_test.parquet",
        "`newsaction.analysis.unblind.run` (once, `NA_UNBLIND=1`)",
        '`panel.targets.build_targets` and `build_d1_targets` ("test"), `panel.reactions.build_reactions` '
        "(D2, D1) and `panel.build.test_returns_panel`, all on the blinded files through `newsaction.lock` "
        "(purposes targets and reactions, logged in `ledgers/test_access.jsonl`); `analysis.slot_path`",
        "ids (`session`, `symbol_id`, `split`, `company_id`, `member`, `is_rep`, `sector`, `half_day`); "
        "same-day `r_cc`, `r_spy_cc`, `ar_*`, `sigma_*`, `z_cc`, `z_on`, `z_id`, `z_vol`; `targets.py`'s "
        "columns (`y0`, `y2`, `e5`, `e5_lvl`, `car_lvl_*`, `fwd_lvl_*`, `ar_o*`, `z_o*`, …); `g_d2`, "
        "`g_d2_lvl`; D1 `y1`, `fwd_lvl_10_*`, `g_d1`, `g_d1_lvl`, `car_lvl_10`; the 30-minute path "
        "`car_lvl_b0` … `car_lvl_b11`",
        "(`session`, `symbol_id`) unique",
        "every test-period row of the test returns panel (members and the post-exit rows)",
        f"{OUTCOMES}; the only file 2026 outcomes are read from afterwards",
    ),
    Entry(
        "work/analysis/price_only_d2_test.parquet",
        "`newsaction.analysis.price_only_d2.run`",
        "NA-09's `work/baselines/models/price_only_y2.json`; `work/states/callB_d2_E3_test.parquet`, "
        "`work/events/events_d2.parquet`, `work/states/context_company.parquet`, `work/panel/panel_public."
        "parquet`, `work/analysis/targets_test.parquet` (G, z_on, z_vol of t)",
        "NA-09's common prediction schema (call B, `y_hat`)",
        "`event_id` unique",
        "the price-only baseline's D2 test predictions for every test Call B D2 state; the same code first "
        "reproduces NA-09's val-A and val-B D2 predictions exactly",
        f"D2 (after close(t)); built from {OUTCOMES}",
    ),
    Entry(
        "work/analysis/h3_predictions.parquet",
        "`newsaction.analysis.run_all.shapley`",
        "the D2 analysis frames; `spec.ridge_protocol` per coalition (fit val-B, λ val-A)",
        "`event_id`, `session`, `company_id`, `tier`, `y2`, `pred_<coalition>` (7), `model`",
        "(`model`, `event_id`) unique",
        "H3's seven coalition predictions of y2 per test D2 event for Laya-Fin, the anchor and d1-ultra; "
        "`spec.shapley_tables` on them reproduces H3's tables (checked)",
        f"test predictions; y2 from {OUTCOMES}",
    ),
    *[
        Entry(
            f"work/analysis/frame_{pt}_{m}.parquet",
            "`newsaction.analysis.run_all.write_frames`",
            "`analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the "
            "frozen V / Ñ maps",
            "the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) "
            "dropped",
            "`event_id` unique",
            f"the {pt.upper()} analysis frame of {m} on val-A, val-B and test, for the verifier's "
            "recomputation (PRD NA-12 verification 3, 4b)",
            f"val rows public; test outcomes from {OUTCOMES}",
        )
        for m in ("laya_fin", "anchor", "d1_ultra")
        for pt in ("d0", "d2")
    ],
    Entry(
        f"{ARTIFACTS}/unblind.json",
        "`newsaction.analysis.unblind.run`",
        "the unblinding run",
        "the freeze hash at unblinding, the run's \"targets\" ledger entries, the output's sha256, counts",
        "one record",
        "the evidence of the one access sequence (AC1); counts only",
        "after unblinding",
    ),
    Entry(
        f"{ARTIFACTS}/unblind_rehearsal.json",
        "`newsaction.analysis.unblind.rehearse`",
        "`work/panel/panel_public.parquet`, `work/panel/intraday_public.parquet`, the public bars",
        "the consistency gaps, the largest difference against the public panels, counts",
        "one record",
        "the val-B rehearsal of the unblinding's assembly (59 columns reproduced)",
        "public (val-B); written before unblinding",
    ),
)


def _dynamic(lay: Layout) -> list[Entry]:
    """One entry per results JSON, figure CSV and table file on disk."""
    root = lay.root / ARTIFACTS
    out = []
    for p in sorted((root / "results").glob("*.json")):
        out.append(
            Entry(
                f"{ARTIFACTS}/results/{p.name}",
                f"`newsaction.analysis.run_all.{p.stem}`",
                "the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)",
                "the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)",
                "nested by model and test",
                f"S2 section `{p.stem}` on the test split",
                f"test; outcomes from {OUTCOMES}",
            )
        )
    for p in sorted((root / "figure_data").glob("*.csv")):
        out.append(
            Entry(
                f"{ARTIFACTS}/figure_data/{p.name}",
                "`newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`",
                "the analysis frames and the S2 results",
                "long CSV (the plotted values with their group, point, mean, se, n)",
                "one row per plotted value",
                f"figure data `{p.stem}`",
                f"test (Figure 4: val-A, val-B, test); outcomes from {OUTCOMES}",
            )
        )
    for p in sorted((root / "tables").glob("*")):
        if p.suffix not in (".csv", ".tex", ".json"):
            continue
        out.append(
            Entry(
                f"{ARTIFACTS}/tables/{p.name}",
                "`newsaction.analysis.tables.write`",
                "`artifacts/NA-12/results/*.json`",
                {
                    ".csv": "a `key` column (unique) and the table's columns",
                    ".tex": "booktabs tabular; title and notes as comments",
                    ".json": 'keys.json: "table/key/column" → value; index.json: tables, columns, notes',
                }[p.suffix],
                "`key`" if p.suffix == ".csv" else "one file",
                f"table file `{p.name}`",
                f"test; outcomes from {OUTCOMES}",
            )
        )
    return out


def _block(e: Entry, sha: str) -> str:
    return (
        f"### `{e.path}`\n- **Producer:** {e.producer}\n- **Inputs:** {e.inputs}\n- **Schema:** {e.schema}\n"
        f"- **Key:** {e.key}\n- **Rows / coverage:** {e.rows}\n- **Availability:** {e.availability}\n"
        f"- **sha256:** `{sha}`\n"
    )


def write(layout: Layout | None = None) -> list[str]:
    """Register the existing NA-12 artifacts and rewrite the NA-12 contract section; returns the paths."""
    lay = resolve_layout(layout)
    done = []
    blocks = []
    for e in (*FIXED, *_dynamic(lay)):
        path = lay.root / e.path
        if not path.is_file():
            continue
        if e.path.startswith("artifacts/"):
            io.register_artifact(e.path, producer=CHUNK, description=e.rows, layout=lay)
        blocks.append(_block(e, io.sha256_file(path)))
        done.append(e.path)
    contract = lay.root / "docs" / "DATA_CONTRACT.md"
    text = contract.read_text(encoding="utf-8")
    section = HEADING + "\n\n" + "\n".join(blocks)
    if HEADING in text:
        start = text.index(HEADING)
        nxt = text.find("\n## ", start + len(HEADING))
        text = text[:start] + section + (text[nxt:] if nxt >= 0 else "")
    else:
        text = text.rstrip("\n") + "\n\n" + section
    io.atomic_write_bytes(contract, text.encode("utf-8"))
    return done


def main() -> int:
    print("\n".join(write()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
