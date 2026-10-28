"""NA-11's entries in ``work/MANIFEST.json`` and ``docs/DATA_CONTRACT.md`` (GAC5), regenerated as a whole.

``ENTRIES`` describes every NA-11 file; ``write`` registers the ones that exist (``io.register_artifact`` for
``artifacts/``; work files are registered by ``io.write_parquet`` when written) and rewrites the "NA-11"
section of the contract with their current sha256, so a file that changes later (``key_usage.json``) is
re-documented by running it again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from newsaction import io
from newsaction.paths import Layout, resolve_layout
from newsaction.production import CHUNK

HEADING: Final = (
    "## NA-11 — final selection, freeze, production (`newsaction.analysis`, `newsaction.production`)"
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


ENTRIES: Final = (
    Entry(
        "work/analysis/state_articles_w2.parquet",
        "`newsaction.analysis.frames.write_state_articles_w2`",
        "`work/events/events_d2.parquet` (`news_w2`), `work/states/callA_d2_E3.parquet`, "
        "`work/states/articles_masked.parquet`, `work/news/articles_clean.parquet` (NA-04 exclusions)",
        "`event_id`, `article_id`, `rank` (int64, 0 = the state's first news item)",
        "(`event_id`, `rank`) unique",
        "every Call A D2 state's articles, rebuilt as NA-09 rebuilt the D0 ones and checked against each "
        "state's news block (274,944 rows)",
        "D2 (`w2`); article ids only",
    ),
    Entry(
        "work/dm/production/company_id_matched.parquet",
        "`newsaction.production.company_id.run`",
        "`work/dm/tournament/samples.parquet` (NA-06's 400 identification events), "
        "`work/states/callA_d0_E3.parquet`,"
        " `work/events/{events_d0,window_counts}.parquet`, `work/panel/{panel_public,companies}.parquet`, "
        "`cache/decisions.sqlite` (chunk NA-11)",
        "`model`, `event_id`, `key`, `ok`, `valid`, `true_key`, `argmax_key`, `p_true`, `cost`, `correct`",
        "(`model`, `event_id`) unique",
        "PREREG §15 NA-06 row option (iv): company identification with activity-matched distractors, six "
        "stage-2 API models and local Laya zero-shot × 400 val-A events (2,800 rows)",
        "val-A D0 states (masked); a probe, no target",
    ),
    Entry(
        "artifacts/NA-11/final_selection.csv",
        "`newsaction.production.select_final`",
        "`work/kaggle/predictions/{laya_fin,anchor}_{val_a,val_b}.parquet` (the frozen runs), "
        "`work/baselines/laya_zeroshot.parquet`, `work/dm/encoding/confirm.parquet`, "
        "`work/panel/panel_public.parquet`",
        "`model`, `role`, `runs`, `n_events`, `n_days`, `ic`, `nw_t`, `boot_se`, `ci_low`, `ci_high`, "
        "`p_one_sided`, `ic_j_y2`, `ic_j_y2_t`, `ic_j_y2_days`, `cost_per_1000`, `selected`, `rank`, `rule`",
        "`model` unique",
        "PREREG §8.5 on val-B: three candidates (common events) and three screen-failing comparators "
        "(NA-07's "
        "val-B sample, information only); its sha256 is `configs/frozen.yaml` `selection.ic_table_sha`",
        "val-B targets (`allow_val_b: true`); no test row",
    ),
    Entry(
        "artifacts/NA-11/company_id_matched.csv",
        "`newsaction.production.company_id.run`",
        "`work/dm/production/company_id_matched.parquet`, `work/dm/tournament/probes.parquet`",
        "`model`, `n`, `valid`, `accuracy`, `mean_p_true`, `cost`, `accuracy_na06_design`, "
        "`baseline_matched`, "
        "`baseline_na06_design`, `screen_threshold`",
        "`model` unique",
        "accuracy per model beside NA-06's and the no-reading baselines of both designs",
        "val-A; a probe",
    ),
    Entry(
        "artifacts/NA-11/spec_smoke_val_b.json",
        "`newsaction.production.smoke_spec`",
        "the val-A / val-B analysis frames (`newsaction.analysis.frames`) of Laya-Fin, the anchor and Laya "
        "zero-shot; `configs/frozen.yaml` calibration",
        "{split, primary, steps: {name: {result, seconds}}, plateau_check, live_format_states_val_b, "
        "seconds}",
        "one JSON object",
        "PRD NA-11 AC2: the spec end to end on val-B (29 steps; the ridge protocol's splits shifted)",
        "val-A / val-B targets; no test row",
    ),
    Entry(
        "artifacts/NA-11/key_usage.json",
        "`newsaction.production.record_key_usage`",
        "OpenRouter GET /api/v1/key and /api/v1/credits; `ledgers/spend.jsonl`",
        "list of {label, ts, usage, usage_daily, limit, limit_remaining, is_free_tier, total_credits, "
        "total_usage, remaining, ledger_chunk_usd}",
        "one entry per check, in time order",
        "the key's usage before and after each NA-11 paid batch (operator preamble item 6)",
        "account metadata; no data",
    ),
)


def _block(e: Entry, sha: str) -> str:
    return (
        f"### `{e.path}`\n- **Producer:** {e.producer}\n- **Inputs:** {e.inputs}\n- **Schema:** {e.schema}\n"
        f"- **Key:** {e.key}\n- **Rows / coverage:** {e.rows}\n- **Availability:** {e.availability}\n"
        f"- **sha256:** `{sha}`\n"
    )


def write(layout: Layout | None = None) -> list[str]:
    """Register the existing NA-11 artifacts and rewrite the NA-11 contract section; returns the paths."""
    lay = resolve_layout(layout)
    done = []
    blocks = []
    for e in ENTRIES:
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


if __name__ == "__main__":
    print("\n".join(write()))
