"""NA-04 report stage (PRD NA-04 S4, S6, S7): token budget, leak scan, examples, frozen hashes.

Writes, from the registered state files only (no return is read):
- ``artifacts/NA-04/token_stats.csv``: p50 / p95 / max of the state tokens, the state with the call's core
  questions (the request), the state with its longest single core question plus special tokens (the Laya
  input, AC5), and the state with core + extended / explain questions, per file, call and encoding; the
  share of states within the 900-token target and within Laya's 768-token state budget;
- ``artifacts/NA-04/leak_scan.csv``: the independent scanner (``scan.LeakScanner``; ``scanner``) on every
  val-A state of the masked E3 files and the unmasked twin (the positive control); ``post_open`` (revision 6)
  counts post-open text, meaningful for the W0 files (W2 news runs to the close);
- ``artifacts/NA-04/examples.md``: three masked Call A (D0) and two Call B states of val-A, seed 2026;
- ``artifacts/NA-04/summary.json``; ``configs/frozen.yaml`` ``questions_v1_sha256`` / ``codebook_v1_sha256``.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Final
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.config import load_project
from newsaction.events import load_events_config, tokens
from newsaction.paths import Layout, resolve_layout
from newsaction.states import SAMPLES_DIR, STATES_DIR, load_states_config
from newsaction.states.build import event_articles, extra_tickers
from newsaction.states.questions import load_battery, write_frozen_hashes
from newsaction.states.scan import LeakScanner, harvest_cjk_names, harvest_names, ordinary_words

ARTIFACT_DIR: Final = "NA-04"
MAIN_FILES: Final = ("callA_d0_E3", "callA_d2_E3", "callB_d2_E3", "market_E3")
SAMPLE_FILES: Final = ("callA_d0_E0", "callA_d0_E1", "callA_d0_E2", "callA_d0_E3", "callA_d0_E4", "unmasked")
SCAN_FILES: Final = ("callA_d0_E3", "callA_d2_E3", "callB_d2_E3")


def state_files() -> list[tuple[str, str]]:
    """(label, work-relative path) of every state file."""
    out = [(n, f"{STATES_DIR}/{n}.parquet") for n in MAIN_FILES]
    out += [(f"samples/{n}", f"{SAMPLES_DIR}/{n}.parquet") for n in SAMPLE_FILES]
    return out


def _q(x: pd.Series, q: float) -> float:
    return float(np.quantile(x.to_numpy(dtype=np.float64), q)) if len(x) else float("nan")


def token_stats(lay: Layout) -> pd.DataFrame:
    cfg = load_states_config()
    from newsaction.states.build import question_tokens

    tok = tokens.tokenizer(load_events_config().events)
    qtok = question_tokens(load_battery(), tok)
    rows = []
    for label, rel in state_files():
        df = io.read_parquet(
            rel, columns=["call", "encoding", "masked", "split", "n_tokens_state"], layout=lay
        )
        for (call_key, enc, masked), g in df.groupby(["call", "encoding", "masked"], sort=True):
            call = str(call_key)
            st = g["n_tokens_state"]
            longest = st + qtok[call]["longest_core"] + cfg.tokens.special_tokens
            rows.append(
                {
                    "file": label,
                    "call": call,
                    "encoding": enc,
                    "masked": bool(masked),
                    "n_states": len(g),
                    "state_p50": _q(st, 0.5),
                    "state_p95": _q(st, 0.95),
                    "state_max": int(st.max()),
                    "with_core_p50": _q(st + qtok[call]["core"], 0.5),
                    "with_core_p95": _q(st + qtok[call]["core"], 0.95),
                    "with_core_max": int((st + qtok[call]["core"]).max()),
                    "with_longest_q_p50": _q(longest, 0.5),
                    "with_longest_q_p95": _q(longest, 0.95),
                    "with_longest_q_max": int(longest.max()),
                    "with_all_groups_p95": _q(st + qtok[call]["all"], 0.95),
                    "share_state_le_900": float((st <= cfg.tokens.state_p95_max).mean()),
                    "share_state_le_768": float((st <= cfg.tokens.laya_state_budget).mean()),
                    "share_longest_q_le_1024": float((longest <= cfg.tokens.total_max).mean()),
                    "q_core_tokens": qtok[call]["core"],
                    "q_longest_core_tokens": qtok[call]["longest_core"],
                    "q_all_groups_tokens": qtok[call]["all"],
                }
            )
    return pd.DataFrame(rows)


def scanner(lay: Layout) -> LeakScanner:
    """The independent scanner: ATOM names and tickers, ATOM / vendor former tickers, and the names
    harvested from the unmasked event texts (``scan.harvest_names``, ``scan.harvest_cjk_names``); nothing
    from the masker or configs/aliases.yaml."""
    comp = io.read_parquet("panel/companies.parquet", columns=["company_id", "ticker", "name"], layout=lay)
    extra = extra_tickers(lay)
    tick: dict[int, set[str]] = {}
    for cid, t in [*zip(comp["company_id"], comp["ticker"], strict=True), *extra]:
        tick.setdefault(int(cid), set()).add(str(t))
    arts = event_articles(lay)
    by_company = {c: sorted(t) for c, t in tick.items()}
    harvested = harvest_names(arts, by_company)
    cjk = harvest_cjk_names(arts, by_company)
    return LeakScanner(comp, extra, harvested, ordinary_words([*arts["title"], *arts["snippet"]]), cjk)


def open_minutes(session: date) -> int:
    """The session's open in minutes after local midnight (the scanner's post-open live entries)."""
    opens = calendar.open_utc(session).tz_convert(ZoneInfo(load_project().timezone))
    return opens.hour * 60 + opens.minute


def leak_scan(lay: Layout) -> pd.DataFrame:
    sc = scanner(lay)
    parts = []
    files = [(n, f"{STATES_DIR}/{n}.parquet") for n in SCAN_FILES] + [
        ("samples/unmasked", f"{SAMPLES_DIR}/unmasked.parquet")
    ]
    for label, rel in files:
        df = io.read_parquet(
            rel, columns=["event_id", "company_id", "session", "split", "masked", "state_json"], layout=lay
        )
        df = df.loc[df["split"] == "val_a"]
        opens = {s: open_minutes(s) for s in set(df["session"])}
        counts = [
            sc.residual_leaks(js, int(c), opens[s]).as_dict()
            for js, c, s in zip(df["state_json"], df["company_id"], df["session"], strict=True)
        ]
        out = pd.concat(
            [df.drop(columns=["state_json"]).reset_index(drop=True), pd.DataFrame(counts)], axis=1
        )
        out.insert(0, "file", label)
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


def leak_rates(scan: pd.DataFrame) -> pd.DataFrame:
    g = scan.assign(
        name_or_ticker=(scan["names"] + scan["tickers"]) > 0, year_or_date=(scan["years"] + scan["dates"]) > 0
    ).groupby("file", sort=True)
    flags = {
        c: (c, lambda x: float((x > 0).mean()))
        for c in ("price_moves", "quotes", "price_levels", "people", "post_open")
    }
    return g.agg(
        states=("event_id", "size"),
        name_or_ticker_rate=("name_or_ticker", "mean"),
        year_or_date_rate=("year_or_date", "mean"),
        names=("names", "sum"),
        tickers=("tickers", "sum"),
        years=("years", "sum"),
        dates=("dates", "sum"),
        **{f"{c}_rate": v for c, v in flags.items()},
    ).reset_index()


def examples(lay: Layout, seed: int) -> str:
    a = io.read_parquet(f"{STATES_DIR}/callA_d0_E3.parquet", layout=lay)
    b = io.read_parquet(f"{STATES_DIR}/callB_d2_E3.parquet", layout=lay)
    a, b = a.loc[a["split"] == "val_a"], b.loc[b["split"] == "val_a"]
    rng = np.random.default_rng(seed)
    pick_a = a.iloc[np.sort(rng.choice(len(a), 3, replace=False))]
    pick_b = b.iloc[np.sort(rng.choice(len(b), 2, replace=False))]
    lines = [
        "# NA-04 example states (val-A, masked, E3)",
        "",
        "Three Call A (D0) and two Call B (D2) states, drawn with seed "
        f"{seed} (`newsaction.states.report.examples`), for human review of the masking and the codebook. "
        "Each block is the exact `state_json` sent to a decision model, pretty-printed (the stored form is "
        "compact). Event ids and token counts are shown outside the state; they are not part of it.",
        "",
    ]
    for title, frame in (("Call A, D0", pick_a), ("Call B, D2", pick_b)):
        for rec in frame.to_dict("records"):
            lines += [
                f"## {title}: `{rec['event_id']}`",
                "",
                f"{rec['n_articles']} articles · {rec['n_tokens_state']} state tokens · "
                f"{rec['n_tokens_with_questions']} with the core questions",
                "",
                "```json",
                json.dumps(json.loads(rec["state_json"]), indent=2, sort_keys=True, ensure_ascii=False),
                "```",
                "",
            ]
    return "\n".join(lines)


def run_report(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    out_dir = lay.artifacts / ARTIFACT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = token_stats(lay)
    ts.to_csv(out_dir / "token_stats.csv", index=False, float_format="%.4f")
    scan = leak_scan(lay)
    scan.to_csv(out_dir / "leak_scan.csv", index=False)
    rates = leak_rates(scan)
    (out_dir / "examples.md").write_text(examples(lay, load_states_config().samples.seed), encoding="utf-8")
    hashes = write_frozen_hashes()
    summary = {
        "token_stats": ts.to_dict("records"),
        "leak_rates": rates.to_dict("records"),
        "frozen_hashes": hashes,
        "rows": {
            label: len(io.read_parquet(rel, columns=["event_id"], layout=lay)) for label, rel in state_files()
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return {"leak_rates": rates.to_dict("records"), "hashes": hashes}
