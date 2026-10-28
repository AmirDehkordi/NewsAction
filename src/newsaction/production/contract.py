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
        "work/states/callB_d2_E3_test.parquet",
        "`newsaction.production.states_test` (S4, after the freeze)",
        "`work/events/events_d2.parquet`, `work/analysis/state_articles_w2.parquet`, NA-04's inputs; the "
        "test "
        'reactions from `panel.reactions.build_reactions(..., "test", "D2")` through `newsaction.lock` '
        "(purpose reactions, logged)",
        "NA-04's state schema (`event_id`, `company_id`, `session`, `split`, `window`, `call`, `encoding`, "
        "`masked`, `state_json`, `state_sha256`, `n_tokens_state`, `n_tokens_with_questions`, `n_articles`, "
        "`third_party_ok_all`)",
        "`event_id` unique",
        "Call B on D2 for the 18,625 test D2 events with a Call A D2 state; each equals its Call A D2 twin "
        "except `reaction_so_far` (asserted)",
        "D2 (after close(s)); built only after the freeze (PREREG §4.4 step 5)",
    ),
    Entry(
        "work/states/callB_d1_E3_test.parquet",
        "`newsaction.production.states_test` (S4, after the freeze)",
        "`work/events/events_d0.parquet`, NA-04's inputs; the test D1 reactions from "
        '`panel.reactions.build_reactions(..., "test", "D1")` and `bars.derive.test_intraday_panel` on the '
        "blinded bars and prices, all through `newsaction.lock` (purpose reactions, logged)",
        "NA-04's state schema",
        "`event_id` unique",
        "Call B on D1 (W0 news + the reaction by 10:00) for the test D0 events with text (13,977); NA-10's "
        "budget (the longest possible reaction block)",
        "D1 (10:00 ET); built only after the freeze",
    ),
    Entry(
        "work/dm/production/local_laya_typed_decisions_probes.parquet",
        '`newsaction.production.laya_local.run("probes")`',
        "NA-06's probe builders (`tournament.run`: counterfactual edits, unmasked twins, shuffled news) on "
        "`work/states/callA_d0_E3.parquet` and `work/states/samples/*.parquet`; `cache/decisions.sqlite`",
        "`newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, "
        "`tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, "
        "`tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `probe`)",
        "(`probe`, `event_id`) unique",
        "the operator's disclosed val-A probes for Laya zero-shot: flip_edit 200, flip_orig 200, unmasked "
        "1,000, masked_twin 1,000, shuffled 1,000 (3,400 rows)",
        "val-A D0; run locally (the unmasked states never leave this machine); probes, not hypotheses",
    ),
    Entry(
        "work/dm/production/local_laya_typed_decisions_test.parquet",
        '`newsaction.production.laya_local.run("test")`',
        "`work/states/callA_d0_E3.parquet` (test rows, after the freeze); `cache/decisions.sqlite`",
        "`newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, "
        "`tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, "
        "`tone`, confidences; plus `q1`, `conf3`, `source`, `split`)",
        "`event_id` unique",
        "Laya zero-shot's test Call A at D0, core battery (PREREG §10.5 comparator)",
        "D0 (09:15 ET); local model, nothing sent to a third party",
    ),
    Entry(
        "work/dm/production/liquid_d1_ultra_api_comparators_market.parquet",
        '`newsaction.production.run.run(["api", "comparators", "market"])` (S6)',
        "the state files of `configs/production.yaml` `states`; `cache/decisions.sqlite` (chunk NA-11)",
        "`newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, "
        "`tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, "
        "`tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `component`; market rows: `n_hat`, "
        "`label_market_reason`, "
        "`plabel_market_reason`)",
        "(`component`, `event_id`) unique",
        "liquid/d1-ultra: the full plan: Call A D0/D2 (core + extended), Call B D2 (core) and D1 (core + "
        "explain), the 2024-H1 A0/A2 core, the A3.5 market states",
        "the readings' window (`source`: a0 = W0, a2 = W2, b2 = D2, b1 = D1, m = market); test rows sent "
        "after the freeze",
    ),
    Entry(
        "work/dm/production/respan_span_02_api_comparators_market.parquet",
        '`newsaction.production.run.run(["api", "comparators", "market"])` (S6)',
        "the state files of `configs/production.yaml` `states`; `cache/decisions.sqlite` (chunk NA-11)",
        "`newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, "
        "`tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, "
        "`tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `component`; market rows: `n_hat`, "
        "`label_market_reason`, "
        "`plabel_market_reason`)",
        "(`component`, `event_id`) unique",
        "respan/span-02: core Call A D0 on val-B and test (comparator; screen-failing, model-specific)",
        "the readings' window (`source`: a0 = W0, a2 = W2, b2 = D2, b1 = D1, m = market); test rows sent "
        "after the freeze",
    ),
    Entry(
        "work/dm/production/nace_ai_drex_v2_0_api_comparators_market.parquet",
        '`newsaction.production.run.run(["api", "comparators", "market"])` (S6)',
        "the state files of `configs/production.yaml` `states`; `cache/decisions.sqlite` (chunk NA-11)",
        "`newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, "
        "`tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, "
        "`tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `component`; market rows: `n_hat`, "
        "`label_market_reason`, "
        "`plabel_market_reason`)",
        "(`component`, `event_id`) unique",
        "nace-ai/drex-v2.0: core Call A D0 on val-B and test (comparator; screen-failing, model-specific)",
        "the readings' window (`source`: a0 = W0, a2 = W2, b2 = D2, b1 = D1, m = market); test rows sent "
        "after the freeze",
    ),
    Entry(
        "work/kaggle/dataset_na11/test_callB.parquet",
        "`newsaction.production.kaggle_infer.export` (S7)",
        "NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` "
        "questions (Laya's input format)",
        "NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, "
        "`question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column",
        "`example_id` unique",
        "test Call B at D2 (18,625 states) and D1 (13,977), questions react and cont",
        "masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset "
        "`amirdehkordi98/newsaction-na11-infer`",
    ),
    Entry(
        "work/kaggle/dataset_na11/val_callB_d1.parquet",
        "`newsaction.production.kaggle_infer.export` (S7)",
        "NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` "
        "questions (Laya's input format)",
        "NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, "
        "`question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column",
        "`example_id` unique",
        "val-A and val-B Call B at D1 (14,941 states), react and cont",
        "masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset "
        "`amirdehkordi98/newsaction-na11-infer`",
    ),
    Entry(
        "work/kaggle/dataset_na11/robustness_callA.parquet",
        "`newsaction.production.kaggle_infer.export` (S7)",
        "NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` "
        "questions (Laya's input format)",
        "NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, "
        "`question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column",
        "`example_id` unique",
        "Call A at D0 (2,793) and D2 (3,887) of the robustness split, react and mag",
        "masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset "
        "`amirdehkordi98/newsaction-na11-infer`",
    ),
    Entry(
        "work/kaggle/dataset_na11/probes.parquet",
        "`newsaction.production.kaggle_infer.export` (S7)",
        "NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` "
        "questions (Laya's input format)",
        "NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, "
        "`question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column",
        "`example_id` unique",
        "NA-06's 200 counterfactual edits (flip_edit) and 1,000 shuffled-news states (shuffled), react",
        "masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset "
        "`amirdehkordi98/newsaction-na11-infer`",
    ),
    Entry(
        "work/kaggle/dataset_na11/check_val_a.parquet",
        "`newsaction.production.kaggle_infer.export` (S7)",
        "NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` "
        "questions (Laya's input format)",
        "NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, "
        "`question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column",
        "`example_id` unique",
        "500 val-A D0 react examples of NA-08's export, re-predicted to check the checkpoint",
        "masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset "
        "`amirdehkordi98/newsaction-na11-infer`",
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
        "artifacts/NA-11/canary_baseline_na11.parquet",
        "`newsaction.production.canary_check.run`",
        "`artifacts/NA-05/canary_v1.jsonl`; `cache/decisions.sqlite` (chunk NA-11)",
        "`model`, `model_build`, `canary_id`, `question`, `option`, `p`, `renormalized`, `key`, `repeat_idx` "
        "(NA-05's `canary_baseline.parquet` format)",
        "(`model`, `canary_id`, `question`, `option`, `repeat_idx`) unique",
        "canary baselines of d1-ultra, span-02 and drex-v2.0 (no NA-05 baseline): repeat 0 of all 50 items "
        "and "
        "repeats 1–4 of the 20 train Call A items",
        "train and synthetic canary states; no target",
    ),
    Entry(
        "artifacts/NA-11/canary_drift_na06.csv",
        "`newsaction.production.canary_check.run`",
        "`artifacts/NA-11/canary_baseline_na11.parquet`, `work/dm/tournament/stage2.parquet`, "
        "`cache/decisions.sqlite` (NA-06 and NA-11 rows)",
        "`model`, `canary_noise_mean_abs_dp`, `canary_noise_per_repeat`, `drift_mean_abs_dp_vs_na06`, "
        "`drift_pairs`, `same_state_noise_mean_abs_dp`, `builds_na06`, `builds_now`, `stop`",
        "`model` unique",
        "repeat noise of the new baselines and the drift of 100 NA-06 stage-2 answers per model (operator "
        "rule: "
        "STOP if the drift exceeds the noise)",
        "val-A states; no target",
    ),
    Entry(
        "work/dm/production/ablation_sample.parquet",
        "`newsaction.production.ablations.write_sample` (S8)",
        "`work/states/{callB_d2_E3,callB_d2_E3_test,callA_d0_E3}.parquet`, "
        "`work/events/{events_d0,events_d2}.parquet` (tier, month, embargo)",
        "`event_id`, `base` (`B_D2` / `A_D0`), `split`, `session`, `company_id`, `tier`, `month`, `donor` "
        "(the shuffled-news donor of a `B_D2` event)",
        "`event_id` unique",
        "12,000 events per base outside the embargo, split × tier × month, the smallest "
        "u = sha256('2026:ablation:<event_id>') per stratum (24,000 rows)",
        "keys only",
    ),
    Entry(
        "work/states/samples/unmasked_robustness.parquet",
        "`newsaction.production.ablations.build_unmasked` (S8)",
        "NA-04's builder inputs (`states.build.load_inputs`), `work/baselines/state_articles.parquet` (the "
        "articles each masked D0 state kept), `work/dm/production/ablation_sample.parquet`",
        "NA-04's state columns (`event_id`, …, `masked` false, `state_json`, `state_sha256`, tokens, "
        "`third_party_ok_all`)",
        "`event_id` unique",
        "the unmasked twins of the 12,000 sampled Call A D0 events; the masked rebuild equals NA-04's state "
        "for every one and the 439 NA-04 twins in the sample are unchanged",
        "D0 (09:15 ET); unmasked: sent only under the registered probe tag `unmasked_robustness` "
        "(PREREG §11.6), third-party-OK articles only",
    ),
    Entry(
        "work/dm/production/liquid_d1_ultra_ablations.parquet",
        "`newsaction.production.ablations.run` (S8)",
        "`work/dm/production/ablation_sample.parquet`, the Call B D2 states, "
        "`work/states/samples/unmasked_robustness.parquet`; `cache/decisions.sqlite` (chunk NA-11)",
        "`newsaction.production.run.readings` plus `ablation` (`b2_no_news`, `b2_shuffled`, `a0_unmasked`) "
        "and `donor`",
        "(`ablation`, `event_id`) unique",
        "d1-ultra, core battery: 12,000 events per ablation (36,000 rows)",
        "D2 (Call B) / D0 (Call A); probes, compared with the S6 readings of the same events",
    ),
    Entry(
        "work/dm/production/llm_sample_test.parquet",
        "`newsaction.production.llm_test.write_sample` (S8)",
        "`work/states/callA_d0_E3.parquet`, `work/events/events_d0.parquet` (NA-09's `d0_events`)",
        "`event_id`, `tier`, `month` and the client's state columns",
        "`event_id` unique",
        "2,000 test D0 events outside the embargo, tier × month, seed 2026 (NA-09's val-B rule, "
        "PREREG §10.7)",
        "D0 (09:15 ET), masked",
    ),
    Entry(
        "work/dm/production/llm_test.parquet",
        "`newsaction.production.llm_test.run` (S8)",
        "`work/dm/production/llm_sample_test.parquet`; NA-09's prompt and settings; `cache/decisions.sqlite`",
        "NA-09's common prediction schema (`baselines.schema`)",
        "`event_id` unique",
        "mistralai/mistral-nemo's valid answers on the 2,000 test events (invalid ones counted in "
        "`artifacts/NA-11/llm_test.json`)",
        "D0 (09:15 ET)",
    ),
    Entry(
        "work/dm/production/price_only_test.parquet",
        "`newsaction.production.price_only_test.run` (S8)",
        "`work/baselines/models/price_only_{e5,abs_z_cc}.json` (NA-09), "
        "`work/states/context_company.parquet`, "
        "`work/panel/panel_public.parquet`, the 2026 `react_z_vol` of `reactions.build_reactions` (lock)",
        "NA-09's common prediction schema (`baselines.schema`)",
        "`event_id` unique",
        "every test Call A D0 event (13,977); the same code reproduces NA-09's val-A/val-B rows exactly",
        "D0 (09:15 ET): t−1 context, z_vol of the previous session",
    ),
    Entry(
        "artifacts/NA-11/ablation_runs.json",
        "`newsaction.production.ablations.run` (S8)",
        "`work/dm/production/liquid_d1_ultra_ablations.parquet`",
        "list of {ablation, requests, ok, valid, cost}",
        "one entry per ablation",
        "the S8 ablation batches",
        "counts and cost only",
    ),
    Entry(
        "artifacts/NA-11/llm_test.json",
        "`newsaction.production.llm_test.run` (S8)",
        "`work/dm/production/llm_test.parquet`",
        "{model, requests, send, projected_usd, cap_usd, budget_left_usd, answered, valid, invalid, "
        "spent_usd}",
        "one object",
        "the LLM baseline's test batch",
        "counts and cost only",
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
