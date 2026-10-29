"""NA-13b's entries in ``work/MANIFEST.json`` and ``docs/DATA_CONTRACT.md`` (GAC5), regenerated as a whole.

    uv run python -m newsaction.selective.contract

Registers every existing NA-13b artifact (``io.register_artifact``; the work file is registered when written)
and rewrites the "NA-13b" section of the contract with each file's current sha256. Run it last.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from newsaction import io
from newsaction.paths import Layout, resolve_layout
from newsaction.selective import run

HEADING: Final = "## NA-13b — when does the signal work? (`newsaction.selective`, exploratory)"
RUN: Final = "`newsaction.selective.run`"
FRAMES: Final = "`work/analysis/frame_d0_{laya_fin,d1_ultra}.parquet`"
EXPLORATORY: Final = "exploratory (post hoc); "
TEST_NOTE: Final = (
    f"{EXPLORATORY}test-period outcomes from NA-12's frames and `work/analysis/targets_test.parquet`, test "
    "market returns from NA-13's `work/strategy/market_test.parquet` (no lock read)"
)


@dataclass(frozen=True)
class Entry:
    path: str
    producer: str
    inputs: str
    schema: str
    key: str
    rows: str
    availability: str


def _t(name: str) -> str:
    return f"{run.TABLES}/{run.FILES[name]}"


ENTRIES: Final = (
    Entry(
        run.SELECTION_JSON,
        f"{RUN} `validation`",
        f"{FRAMES}, NA-11's span-02 / drex-v2.0 production readings, `work/states/context_market.parquet`, "
        "`work/strategy/market_public.parquet`, `work/panel/panel_public.parquet`",
        "the selection rule, the selected (model, condition) pairs, the val-A cut points, each condition's "
        "definition, the sha256 of the two validation tables, git sha",
        "one object",
        "the validation selection, committed before the test stage ran",
        f"{EXPLORATORY}val-A and val-B only (no test row read)",
    ),
    Entry(
        _t("cuts"),
        f"{RUN} `validation`",
        "as the selection",
        "`key`, `name`, `value`",
        "`key` unique",
        "every val-A threshold of the conditions (medians, the 70th percentile of |N̂|)",
        f"{EXPLORATORY}val-A only",
    ),
    Entry(
        _t("selection_validation"),
        f"{RUN} `validation`",
        "as the selection",
        "`key`, `model`, `condition`, `group`, `label`, `level`, `seen_on_test`, `val_b_only`, `diff_val_a`, "
        "`t_val_a`, `diff_val_b`, `t_val_b`, `t_pooled`, `selected`, `rule`",
        "`key` = model|condition unique",
        "every (model, condition) pair of E1–E9 on the primary outcome sign(N̂)·z_id",
        f"{EXPLORATORY}val-A and val-B only",
    ),
    Entry(
        _t("conditioning"),
        f"{RUN} `test`",
        f"as the selection, and the test rows of {FRAMES} and `work/analysis/targets_test.parquet`",
        "`key`, `model`, `condition`, `group`, `label`, `level`, `seen_on_test`, `vendor`, `outcome`, "
        "`role`, `split`, `n_in`, `n_out`, `days_in`, `days_out`, `df`, `inside`, `inside_t`, `outside`, "
        "`outside_t`, `diff`, `diff_t`, `diff_p`, `diff_days`",
        "`key` = model|condition|outcome|split unique",
        "every pair × outcome (z_id, z_o0_c1, z_on) × split (val-A, val-B, pooled validation, test)",
        TEST_NOTE,
    ),
    Entry(
        _t("selection"),
        f"{RUN} `test`",
        "the conditioning table and the books",
        "the test rows of the primary outcome, `bh_q` (Benjamini–Hochberg over the family), `selected`, "
        "`same_sign`, `confirmed`, the test book's gross Sharpe and placebo 90th percentile, `eligible`, "
        "`t_pooled_val`, `candidate`",
        "`key` = model|condition unique",
        "every pair of the family on the test",
        TEST_NOTE,
    ),
    Entry(
        _t("books"),
        f"{RUN} `test`, then `dsr`",
        "the conditions, NA-13's market files, `configs/frozen.yaml` (V maps), `ledgers/trials.jsonl` (DSR)",
        "`key`, `book_key`, `book`, `model`, `condition`, `split`, `exit`, `holding`, NA-13's counts and "
        "`portfolios.summary` columns, `n_positions`, `names_long`, `names_short`, `break_even_bp`, placebo "
        "percentiles and quantiles, capacity, `dsr_prob_net_{5,10}`, `dsr_sr0_net_{5,10}`, `n_trials`",
        "`key` = book|exit|split unique",
        "the tradable versions (the selected pairs, E8, E9) on val-B (in-sample) and the test",
        TEST_NOTE,
    ),
    Entry(
        f"work/{run.BOOKS_DAILY}",
        f"{RUN} `test`",
        "as the books",
        "`session`, `gross`, `turnover`, `active`, `net_5`, `net_10`, `book`, `model`, `condition`, `split`, "
        "`exit`",
        "(`book`, `split`, `exit`, `session`) unique",
        "every book's daily series over its window",
        TEST_NOTE,
    ),
    Entry(
        _t("coverage"),
        f"{RUN} `test`",
        f"{FRAMES}, NA-11's and NA-09's readings, NA-06's stage-2 sample (span-02, drex-v2.0 val-A), "
        "`work/panel/panel_public.parquet`, `work/analysis/targets_test.parquet`",
        "`key`, `model`, `ranking`, `coverage`, `split`, `target`, `threshold`, `sample`, `n`, `n_days`, "
        "`hit`, `hit_ci_low`, `hit_ci_high`, `signed`, `signed_ci_low`, `signed_ci_high`, `ic`, `ic_t`, "
        "`ic_ci_low`, `ic_ci_high`, `ic_days`",
        "`key` = model|ranking|coverage|split|target unique",
        "the risk–coverage curves: 5 models × 2 rankings × 11 coverages × 3 splits × 3 targets",
        TEST_NOTE,
    ),
    Entry(
        _t("histograms"),
        f"{RUN} `test`",
        "as the coverage curves",
        "`key`, `bin`, `lo`, `hi`, `mid`, `n`, `share`, `model`, `measure`, `split`",
        "`key` = model|measure|split|bin unique",
        "40-bin histograms of N̂ and of the stated confidence per model and split",
        TEST_NOTE,
    ),
    Entry(
        _t("output_summary"),
        f"{RUN} `test`",
        "as the coverage curves",
        "`key`, `model`, `measure`, `split`, `sample`, `n`, `mean`, `sd`, `clipped_low`, `clipped_high`, "
        "`q05`, `q25`, `q50`, `q75`, `q95`, `share_positive`",
        "`key` = model|measure|split unique",
        "the outputs' moments and quantiles",
        TEST_NOTE,
    ),
    Entry(
        _t("bands"),
        f"{RUN} `test`",
        FRAMES,
        "`key`, `split`, `band`, `n`, `hit_cc`, `cc`, `on`, `id`, `model`, `cut_50`, `cut_70`, `cut_90`",
        "`key` = model|split|band unique",
        "the operator's assistant's band check, reproduced (disclosure)",
        TEST_NOTE,
    ),
    Entry(
        _t("watch_open"),
        f"{RUN} `test`",
        FRAMES,
        "`key`, `model`, `split`, `statistic`, `kind`, `value`, `t`, `ci_low`, `ci_high`, `n_days`, `n_obs`",
        "`key` = model|split|statistic unique",
        "the D1 (10:00) against D0 statistics: four daily ICs with y1 and two conditional means",
        TEST_NOTE,
    ),
    Entry(
        f"{run.RESULTS}/test_run.json",
        f"{RUN} `test`",
        "the selection record",
        "the selected pairs, the books, the forward-test candidates, git sha, lock reads (0)",
        "one object",
        "the record of the one test run",
        TEST_NOTE,
    ),
    Entry(
        f"{run.RESULTS}/dsr.json",
        f"{RUN} `dsr`",
        "`ledgers/trials.jsonl`",
        "`n_trials`, `parts` (rows by kind), git sha",
        "one object",
        "the trial count the books' DSR used",
        f"{EXPLORATORY}after the NA-13b trials were logged",
    ),
)


def _block(e: Entry, sha: str) -> str:
    return (
        f"### `{e.path}`\n- **Producer:** {e.producer}\n- **Inputs:** {e.inputs}\n- **Schema:** {e.schema}\n"
        f"- **Key:** {e.key}\n- **Rows / coverage:** {e.rows}\n- **Availability:** {e.availability}\n"
        f"- **sha256:** `{sha}`\n"
    )


def write(layout: Layout | None = None) -> list[str]:
    """Register the existing NA-13b artifacts and rewrite the NA-13b contract section; returns the paths."""
    lay = resolve_layout(layout)
    done, blocks = [], []
    for e in ENTRIES:
        path = lay.root / e.path
        if not path.is_file():
            continue
        if e.path.startswith("artifacts/"):
            io.register_artifact(e.path, producer=run.CHUNK, description=e.rows, layout=lay)
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
