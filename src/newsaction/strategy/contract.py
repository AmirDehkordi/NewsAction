"""NA-13's entries in ``work/MANIFEST.json`` and ``docs/DATA_CONTRACT.md`` (GAC5), regenerated as a whole.

    uv run python -m newsaction.strategy.contract

Registers every existing NA-13 artifact (``io.register_artifact``; the work files are registered when written)
and rewrites the "NA-13" section of the contract with each file's current sha256. Run it last.
"""

from __future__ import annotations

from typing import Final

from newsaction import io
from newsaction.analysis.contract import Entry
from newsaction.paths import Layout, resolve_layout
from newsaction.strategy import ma_cross as ma
from newsaction.strategy import market as mk
from newsaction.strategy import run
from newsaction.strategy import tables as tb

HEADING: Final = "## NA-13 — strategies and economic significance (`newsaction.strategy`)"
TEST_NOTE: Final = "test-period returns from `work/strategy/market_test.parquet` (after unblinding)"
RUN: Final = "`newsaction.strategy.run`"


def _split_entries() -> list[Entry]:
    out = []
    for split in run.SPLITS:
        avail = TEST_NOTE if split == "test" else "val-B (reference; the maps and gates were fit on val-A)"
        out += [
            Entry(
                f"work/{run.OUT_DAILY.format(split=split)}",
                f"{RUN} `{split}`",
                "`work/analysis/frame_{d0,d2}_{laya_fin,d1_ultra,anchor}.parquet`, `work/baselines/sentiment."
                "parquet`, the market panel, `configs/frozen.yaml` (`strategy`, maps, gates)",
                "`rule`, `split`, `tier` (all / top100 / mid / rest), `session`, `gross`, `turnover`, "
                "`active`, "
                "`net_5`, `net_10`, `net_20`",
                "(`rule`, `tier`, `session`) unique",
                "every non-empty book's daily series over its window (first entry to last exit)",
                avail,
            ),
            Entry(
                f"work/{run.OUT_POSITIONS.format(split=split)}",
                f"{RUN} `{split}`",
                "as the books",
                "`rule`, `event_id`, `session`, `symbol_id`, `tier`, `cohort`, `beta`, `adv20`, "
                "`decision_utc`, "
                "`entry_utc`, `exit_utc`, the inputs' instants (`news_utc`, `reaction_utc`, `tier_utc`, "
                "`risk_utc`, `calibration_utc`), `side`, `weight`, `score`, `group`",
                "(`rule`, `event_id`) unique",
                "every position of every book",
                avail,
            ),
            Entry(
                f"work/{run.OUT_PLACEBO.format(split=split)}",
                f"{RUN} `{split}`",
                "the books' universes",
                "`universe`, `seed`, `sharpe_gross`, `sharpe_net_{5,10,20}`, `ann_return_gross`, "
                "`ann_return_net_{5,10,20}`",
                "(`universe`, `seed`) unique",
                "100 random-signal books (seeds 2027–2126) per universe",
                avail,
            ),
            Entry(
                f"work/{run.OUT_PLACEBO_PATHS.format(split=split)}",
                f"{RUN} `{split}`",
                "the placebo books",
                "`universe`, `session`, `cum_net_10_q05`, `cum_net_10_q50`, `cum_net_10_q95`",
                "(`universe`, `session`) unique",
                "the placebo's percentile paths of the cumulative net return at 10 bp",
                avail,
            ),
            Entry(
                f"{run.RESULTS}/books_{split}.json",
                f"{RUN} `{split}`",
                "as the books",
                "per rule: the rule, counts (events, purged, β fallbacks, zero-return days), metrics, "
                "capacity, "
                "placebo percentiles",
                "one file",
                "every pre-registered book and benchmark, empty ones included",
                avail,
            ),
        ]
    return out


FIXED: Final = (
    Entry(
        f"work/{mk.PUBLIC_OUT}",
        "`newsaction.strategy.market public`",
        "`panel.build.assemble` on the public inputs; `work/panel/intraday_public.parquet`",
        "`session`, `symbol_id`, `company_id`, `split`, `member`, `is_rep`, `raw_open`, `raw_close`, "
        "`adj_close`, `r_cc`, `r_id`, `r_spy_cc`, `r_spy_id`, `beta_m`, `ar_cc`, `adv20`, `ma20`, `ma50`, "
        "`ma20_prev`, `ma50_prev`, `p10`, `r_10c`, `r_spy_10c`",
        "(`session`, `symbol_id`) unique",
        "val-A and val-B member and post-exit rows; equal to `panel_public` on the shared columns",
        "returns of session t are known at its close; `beta_m`, `adv20` end at t−1",
    ),
    Entry(
        f"work/{mk.TEST_OUT}",
        "`newsaction.strategy.market test` (once, `NA_UNBLIND=1`)",
        '`lock.read_sealed(…, "targets")` of the blinded prices, total-return check and 30-minute bars '
        "(logged in `ledgers/test_access.jsonl`), assembled as `panel.build.test_returns_panel` and "
        "`bars.derive.test_intraday_panel` do",
        "as `market_public`",
        "(`session`, `symbol_id`) unique",
        "the test period's member and post-exit rows (73,498, as `targets_test`); its val-B rows equal the "
        "public build and its `r_cc`, `r_spy_cc`, `ar_cc` equal `targets_test` (`artifacts/NA-13/"
        "market_test.json`)",
        "test-period returns, after unblinding; `beta_m`, `adv20` end at t−1",
    ),
    Entry(
        f"work/{ma.OUT_BOOKS}",
        "`newsaction.strategy.ma_cross`",
        "`work/panel/panel_public.parquet`, the market panels, the D0 frames",
        "`period`, `session`, `gross`, `turnover`, `active`, `net_5`, `net_10`, `net_20`",
        "(`period`, `session`) unique",
        "the exploratory no-news MA-cross fade (operator item 9), validation and test",
        "exploratory, after unblinding",
    ),
    Entry(
        f"{run.ARTIFACTS}/market_test.json",
        "`newsaction.strategy.market test`",
        "the test build",
        "output path and sha256, sessions, the lock reads, the consistency gaps",
        "one file",
        "the record of the one NA-13 access sequence",
        "after unblinding",
    ),
    Entry(
        f"{run.RESULTS}/{ma.RESULT}",
        "`newsaction.strategy.ma_cross`",
        "as its books",
        "per period: crosses, the group statistics (mean bp, Newey–West t, days, crosses), the fade book",
        "one file",
        "validation (reproduces the operator's numbers) and test",
        "exploratory, after unblinding",
    ),
    Entry(
        tb.TABLE_CSV,
        "`newsaction.strategy.tables`",
        "the books, the placebo, the trials ledger (n_trials for the DSR)",
        "`order`, `split`, `family`, `model`, `point`, `signal`, `exit`, `gated`, `role`, `rule`, "
        "`universe`, "
        "the metrics, `dsr_*_net_{5,10,20}`, `capacity_*`, `note`, `n_trials`",
        "(`split`, `rule`) unique",
        "every book on test and val-B, S-CONV first; the exploratory fade last",
        "test and val-B (reference)",
    ),
    Entry(
        tb.TABLE_TEX,
        "`newsaction.strategy.tables`",
        "`strategy_table.csv`",
        "booktabs tabular; title and notes as comments",
        "one file",
        "the test books",
        "test",
    ),
    Entry(
        tb.FIG7,
        "`newsaction.strategy.tables`",
        "the test books, the placebo paths, the exploratory fade",
        "`rule`, `tier`, `session`, `cum_net_10`, `series` (book / placebo_band), `cum_net_10_q05/_q50/_q95`",
        "(`rule`, `tier`, `session`) unique",
        "Figure 7: cumulative net returns at 10 bp by tier, with the benchmarks and the placebo band",
        "test",
    ),
    Entry(
        f"{run.RESULTS}/{tb.SUMMARY}",
        "`newsaction.strategy.tables`",
        "the trials ledger, `market_test.json`",
        "n_trials and its parts, the DSR settings, the lock reads, row counts",
        "one file",
        "the DSR's trial count",
        "after unblinding",
    ),
)


def _block(e: Entry, sha: str) -> str:
    return (
        f"### `{e.path}`\n- **Producer:** {e.producer}\n- **Inputs:** {e.inputs}\n- **Schema:** {e.schema}\n"
        f"- **Key:** {e.key}\n- **Rows / coverage:** {e.rows}\n- **Availability:** {e.availability}\n"
        f"- **sha256:** `{sha}`\n"
    )


def write(layout: Layout | None = None) -> list[str]:
    """Register the existing NA-13 artifacts and rewrite the NA-13 contract section; returns the paths."""
    lay = resolve_layout(layout)
    done, blocks = [], []
    for e in (*FIXED[:3], *_split_entries(), *FIXED[3:]):
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
