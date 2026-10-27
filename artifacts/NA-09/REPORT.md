# NA-09 REPORT — the pre-registered baselines in one prediction schema

Date: 2026-10-27 · Branch `feat/NA-09-baselines` (worktree `NewsAction-NA09`, cut from `main` @ `7bc114b`;
NA-07, NA-08 and NA-10 ran in parallel in their own worktrees) · Decisions: `docs/decisions/NA-09.md` ·
Artifacts: `artifacts/NA-09/{baseline_val_metrics.csv, llm_catalog.json, llm_dry_run.json, llm_summary.json,
key_usage.json, summary.json}` · Work files: `work/baselines/*.parquet`, `work/baselines/models/*.json`.

**Status.** Interim (2026-10-27 11:45 UTC). Everything is done except S6: the Laya zero-shot run is in progress (detached; val-A Call A 5,500 / 8,906 at 11:38 UTC; about 17 h left at ~0.73 s per request), so the Laya prediction file, its val-A metrics, AC5 and the full `make verify` (whose live Laya test contends with the run for the GPU) follow when it ends. This report is then updated.

**Result.**
- **One prediction schema** (`newsaction.baselines.schema`): {event_id, model, call, split, session, company_id,
  N_hat, P_up, P_down, mag_hat, y_hat, extra}. Every file is validated before it is written: events match the
  states, there are no duplicates, no D2 test row, and test rows only for the baselines that need no 2026
  price.
- **Fitted baselines**, all fit on train (2024-07-01 … 2025-06-30) and tuned and calibrated on val-A outside the
  embargo (2025-07-09 … 09-30):
  - vendor sentiment (§10.1);
  - bge + ridge (§10.2);
  - vendor tags + LightGBM (§10.3);
  - price-only D0 and D2 (§10.4).

  Each stores a fit record that is checked before writing.
- **Val-A** (8,376 events, 59 sessions). Mean daily IC of N̂ with z_cc,t (t):

  | Baseline | IC | t |
  |---|---|---|
  | tags + GBM | 0.068 | 5.3 |
  | sentiment | 0.049 | 4.2 |
  | bge + ridge | 0.004 | 0.4 |
  | price-only | −0.006 | −0.4 |

  - For comparison, NA-06's stage-2 decision models had Call A IC 0.037–0.071 on their 3,000-event sample.
  - The vendor signals' information lands in the overnight gap: IC with z_on 0.074 / 0.076 (t 7.5 / 8.1),
    with the post-decision open→close z_id 0.006 / 0.022 (t 0.5 / 1.7).
  - Magnitude: the tags model explains R² 0.28 of |z_cc| beyond the train mean.
- **Laya zero-shot (S6).** Local `laya-typed-decisions`, core battery, on every non-test Call A D0 state and every Call B D2 state (88,552 requests, 720 cached by NA-05/06). The operator chose all splits after the >8 h projection. The run is in progress (§4).
- **Generative LLM (S7).** mistralai/mistral-nemo, picked by a rule fixed before any call: matched cost, knowledge cutoff 2024-04-30, before the train start. It answered Q1 as a strict JSON object on 2,000 val-B D0 events: 1,978 valid (234 renormalized), $0.0389 in total, **$0.0194 per 1,000 decisions** against $0.019–0.18 for the API decision models (median $0.042). No val-B metric is computed here.
- **Spend.** NA-09 $0.038884 of the $2.00 cap: 2,000 chat calls; Laya is local, $0. Cumulative in this worktree's ledger $3.669428 of $30 (NA-05 0.1039, NA-06 3.5266, NA-09 0.0389). The ledger minus Σ cache cost for NA-09 = 0.0.
- **No val-B or test metric** was computed. `test_access.jsonl` is unchanged (2 NA-01 lines). No D2 or D1 test
  prediction exists.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 schema | done | `baselines/schema.py`: `PREDICTION_COLUMNS`, `frame`, `validate`; `FitRecord`, `check_fit_record`. `run.write_predictions` validates every file before writing it |
| S2 sentiment | done | `baselines/sentiment.py`. Mean vendor sentiment (−2 … +2) of the state's articles → isotonic N_hat (train); OLS mag_hat on the shares of non-neutral and Immediate / Short-Term articles (train); val-A P maps |
| S3 embed + ridge | done | `baselines/embed_ridge.py`. Mean bge-small vector of the state's articles + log1p attention (5) → ridge for e5 and \|z_cc\|; λ ∈ {1e−2 … 1e6} on val-A, each a trial. Chosen λ: e5 10, \|z_cc\| 1e4 |
| S4 tags + GBM | done | `baselines/tags_gbm.py`, `gbm.py`. 47 features (tag counts, flags, sentiment, intensity, source classes, novelty, duplicates, attention, tier, sector); 8-point grid on val-A, each a trial |
| S5 price-only | done | `baselines/price_only.py`. D0: z_m5/20/60, z_vol(t−1), σ regime, tier, sector → e5, \|z_cc\|. D2: + G, z_on,t, z_vol,t → y2. No test prediction (NA-11, after the freeze, with the saved models) |
| S6 Laya zero-shot | running | `baselines/laya_zeroshot.py`; `run --stage laya` (detached, log `work/baselines/laya_run.log`); predictions `work/baselines/laya_zeroshot.parquet` |
| S7 generative LLM | done | `dm/client.py` `chat_json` / `chat_json_batch` (every guard); `baselines/llm_baseline.py`; mistralai/mistral-nemo on 2,000 val-B D0 events; `llm_summary.json` |
| S8 val metrics | done for the fitted baselines; Laya rows follow | `artifacts/NA-09/baseline_val_metrics.csv` (val-A only; by tier); trials logged |

Also:
- `configs/baselines.yaml` (new);
- `configs/dm.yaml`: chat and credits endpoints, the chat price snapshot, the chat cost settings;
- `configs/frozen.yaml` `chat_models`;
- `configs/availability.yaml`: `z_vol_lag1`, `react_z_on`, `embedding`, `text_sha`;
- a PREREG §15 row (NA-09, before any LLM call and any Laya metric);
- a README guard row;
- DATA_CONTRACT entries.

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 fit ranges | Each of the 9 fit records (`work/baselines/models/<model>_<target>.json`) has a fit range inside train and tuning and calibration ranges inside val-A, computed from the rows used. Example: e5 fit 2024-07-01 … 06-24, 22,267 rows; val-A 2025-07-09 … 09-24, 7,970 rows; \|z_cc\| 22,598 / 8,376; y2 28,673 / 9,751. `check_fit_record` refuses anything else before writing. `tests/test_baselines_fit_ranges.py` runs every baseline on a synthetic frame and checks the recorded ranges and row counts, refuses ranges outside their split (7 cases), refuses a fit fed val-A rows (nothing written), shows that scrambling val-A targets moves no train-fitted N̂, and checks the 9 stored records. **Mutation "embed_ridge fits on train + val-A" (the PRD's) and 5 more: RED** | PASS |
| AC2 schema | `schema.validate` runs before every write. `tests/test_baselines_schema.py` checks the real files and 17 refused frames: duplicates, events that are not states, wrong company or split, P outside [0, 1], P_up + P_down > 1, negative mag_hat, infinities, neither N_hat nor y_hat, extra not an object, call-B test rows, test rows of price-only / Laya / LLM. Files: sentiment, embed_ridge, tags_gbm 54,332 rows each (every Call A state, the event set equal to the state file's); price_only 40,355 call A + 48,197 call B (every non-test state); llm 1,978. No duplicate (event_id, model, call) in any file | PASS (Laya's file follows) |
| AC3 no 2026 reactions | No call-B row in the test period; test rows only for sentiment, embed_ridge, tags_gbm (13,977 each). Price-only has no test row: D0 needs a 2026 volume, D2 the 2026 reactions. Laya has none: the client refuses test states before the freeze. `ledgers/test_access.jsonl`: 2 lines, both NA-01. Only 2026-01-02 has `z_vol_lag1` (its previous session is 2025-12-31); the price-only test rows are not made. Schema mutations "call-B test row allowed" and "any model in test": RED | PASS |
| AC4 budget | NA-09 spend $0.038884 ≤ $2.00 (projection $0.155: bytes / 3 and max_tokens 300, conservative on purpose). The ledger minus Σ `responses.cost` (chunk NA-09; 2,000 chat rows plus 0-cost Laya rows) = 0.0. The account was checked before the first paid call: $10.28 left against $0.000089 for the probe and $0.155 for the batch (`key_usage.json`). The key's own usage moved by $0.173 during S7, because NA-07 spent from the same key in parallel (operator preamble), so the reconciliation is against the cache. `tests/test_chat_json_refusals.py` (36 tests, mock transport, online and offline): every refusal (a)–(f), no local backend, a bad request in a batch sends nothing, deny-only provider, cache hit and offline `CacheMiss`, key sensitivity, projection before the first send, reserve → record order, reconcile 0, HTTP error → release, usage without cost priced, the strict parser. Mutations: 11 chat_json mutations RED | PASS |
| AC5 Laya | Run in progress (§4) | pending |
| GAC1 | `make lint` (ruff check and format: 166 files) and `make type` (mypy --strict: 85 files): clean. pytest: 1,532 passed, 1 skipped, 1 xfailed, with `test_dm_laya_local.py::test_live_typed_decisions_on_three_canary_states` deselected. That test loads Laya on MPS and segfaults while the S6 run holds the GPU (two of three combined runs crashed while loading weights; alone it passes). `make manifest` OK (99 artifacts); `make ledgers` OK. The full `make verify` is rerun when S6 ends | pending (full run after S6) |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (inputs size + mtime) | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal, no sealed path in `src/`). `test_access.jsonl` unchanged. No 2026 return, volume or reaction was read: test features come from `context_company` (NA-04's t−1 context) and the state's articles | PASS |
| GAC4 | NA-09 ledger $0.038884416 vs Σ cache cost (chunk NA-09) $0.038884416: difference 0.0. Chunk ≤ $2.00. Total in this worktree's ledger $3.669 ≤ $30; NA-07's spend sits in its own worktree's ledger (operator re-chains at merge) | PASS |
| GAC5 | 23 new manifest entries (8 `work/baselines/*.parquet`, 9 `work/baselines/models/*.json`, 6 `artifacts/NA-09/*`), each with a DATA_CONTRACT entry and the same sha256 (`make manifest`: OK); the Laya file follows | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, cleared `__pycache__`, ran the named test file and restored the file
byte for byte (asserted). **26 / 26 RED** (23 / 25 on the first pass, the two survivors below; the 26th, the chat parser's float margin, was added with the fix in §5).

| Area | Mutations |
|---|---|
| fit ranges (AC1) | embed_ridge fits on train + val-A; `fit_rows` takes val-A; `tune_rows` keeps the embargo; tags_gbm tunes on val-B; `check_fit_record` off; probability maps fit on val-B |
| metrics (S8) | any split allowed; val-B rows read |
| schema (AC2, AC3) | call-B test row allowed; any model in test; duplicates allowed; events not matched to states |
| inputs | every `selection_only` column allowed; no pit check; the Laya test split allowed |
| chat_json (AC4) | eligibility from the decision-model list; a local model allowed; test-period guard off; offline sends; no batch projection check; no reservation; cache read off; provider `allow`; key ignores the seed; sum rule off; float margin of the sum rule removed |

The two survivors of the first pass:
- "duplicates allowed": the duplicate test row also mismatched its state;
- "no batch projection check": a cap below one call is refused by the per-call reservation too.

A true-duplicate test and a cap that fits one call but not three now kill them.

## 3. Fitted baselines

### 3.1 Fit records and choices (`work/baselines/models/`)

| Model → target | Fit (train) | Tune (val-A) | Calibration (val-A) | Selected (val-A score) |
|---|---|---|---|---|
| sentiment → e5 | 2024-07-01 … 2025-06-24, 22,267 | — | 2025-07-09 … 09-24 | isotonic, increasing |
| sentiment → \|z_cc\| | … 2025-06-30, 22,598 | — | — | OLS: 0.909 − 0.114 non-neutral + 0.805 timely |
| embed_ridge → e5 | … 06-24, 22,267 | 07-09 … 09-24, 7,970 | 07-09 … 09-24 | λ 10 (IC −0.016; every λ negative, −0.016 … −0.030) |
| embed_ridge → \|z_cc\| | … 06-30, 22,598 | 07-09 … 09-30, 8,376 | — | λ 1e4 (R² 0.167) |
| tags_gbm → e5 | … 06-24 | 07-09 … 09-24 | 07-09 … 09-24 | 7 leaves, 50 min child, 200 trees (IC 0.053) |
| tags_gbm → \|z_cc\| | … 06-30 | 07-09 … 09-30 | — | 31 / 50 / 200 (R² 0.282) |
| price_only → e5 | … 06-24 | 07-09 … 09-24 | 07-09 … 09-24 | 31 / 400 / 800 (IC 0.005) |
| price_only → \|z_cc\| | … 06-30 | 07-09 … 09-30 | — | 7 / 400 / 200 (R² 0.083) |
| price_only → y2 | … 06-23, 28,673 | 07-09 … 09-23, 9,751 | — | 31 / 400 / 200 (IC 0.011) |

The ranges end where `panel_public`'s purge ends each target inside its split (e5: t+4; y2: t+5).

### 3.2 Val-A metrics (`baseline_val_metrics.csv`; mean daily IC, Newey–West t in brackets)

| Baseline | IC(N̂, z_cc) | IC(N̂, e5) | R²(e5) vs 0 | IC(N̂, z_on) | IC(N̂, z_id) | R²(\|z_cc\|) vs train mean | IC(mag, \|z_cc\|) |
|---|---|---|---|---|---|---|---|
| sentiment | 0.049 (4.2) | 0.033 (1.4) | 0.004 | 0.074 (7.5) | 0.006 (0.5) | 0.024 | 0.084 (4.2) |
| embed_ridge | 0.004 (0.4) | −0.016 (−1.2) | −0.039 | 0.017 (1.5) | −0.010 (−0.9) | 0.168 | 0.155 (6.1) |
| tags_gbm | 0.068 (5.3) | 0.053 (2.4) | 0.013 | 0.076 (8.1) | 0.022 (1.7) | 0.283 | 0.180 (6.5) |
| price_only (D0) | −0.006 (−0.4) | 0.005 (0.3) | −0.042 | −0.008 (−0.6) | −0.004 (−0.3) | 0.084 | 0.165 (7.3) |


- 59 sessions (55 for e5); 8,376 events (7,970 with e5).
- Price-only D2: IC(y_hat, y2) 0.011 (t 1.4), R² vs 0 −0.013, on 9,751 events and 54 sessions.


By tier (top100 / mid / rest), IC(N̂, z_cc) and R²(|z_cc|) against the train mean:

| Baseline | IC top100 | IC mid | IC rest | R² top100 | R² mid | R² rest |
|---|---|---|---|---|---|---|
| sentiment | 0.041 (1.5) | 0.016 (0.6) | 0.063 (3.4) | −0.042 | 0.025 | 0.049 |
| embed_ridge | −0.012 (−0.6) | 0.021 (1.4) | 0.010 (0.6) | 0.107 | 0.155 | 0.200 |
| tags_gbm | 0.055 (2.9) | 0.058 (2.6) | 0.066 (3.6) | 0.152 | 0.283 | 0.334 |
| price_only | −0.018 (−0.8) | 0.008 (0.3) | −0.014 (−0.6) | 0.048 | 0.063 | 0.111 |

**Reading.**
- **Vendor signals carry D0 information.** The sentiment map and the tags model rank D0 events as well as the
  best zero-shot decision models did in NA-06, and they are cheaper. NA-11 / NA-12 must report every decision
  model against them.
- **Where the information lands.** The gap / open→close split is what a pre-open signal should look like: almost
  all of it is in the gap z_on. Little lands after the decision, which bounds what the vendor's after-the-fact
  labelling (CLAUDE.md A6) could have leaked into these signals.
- **bge + ridge** learns magnitude (R² 0.17) but no direction: no λ gives a positive val-A IC with e5.
- **Price-only** has no directional D0 signal, as expected. Its magnitude R² (0.08) is the volatility baseline
  for H4.
- **Caveats.** Val-A P_up / P_down are in-sample for their maps, so no probability metric is reported here.
  These are val-A numbers, the split the grids were chosen on. Val-B and test are NA-11's.

## 4. Laya zero-shot (S6)

- **Scope** (operator, 2026-10-27, after the projection): `local/laya-typed-decisions` (revision `55cf4c4e`, fp32,
  max_len 1024, MPS), core battery. Call A D0: val-A 8,906, val-B 6,035, train 22,621, robustness 2,793. Call B D2:
  val-A 11,148, val-B 7,828, train 29,221. That is 88,552 requests, 720 already cached (NA-06 stage 1: 700 val-A;
  NA-05 canary: 20 train).
- **Measured before the start:**
  - one request at a time: 0.516 s per Call A, 0.582 s per Call B state (0.507 s through the client);
  - laya `predict_batch` at 4 / 8 / 16 states per pass: 0.62 / 0.68 / 0.77 s per state, with bitwise-identical
    probabilities;
  - two processes: 0.62 s per state combined.

  Batch 1 in one process is fastest. Projection: 13.4 h.
- **Run:** started 10:36 UTC, detached (`caffeinate`), log `work/baselines/laya_run.log`; peak RSS 2.98 GB. Rate
  ~0.73 s per request (the GPU is shared with the desktop and other worktrees), so it ends around 04:30 UTC on
  2026-10-28.
- **Next:** `--stage laya_predictions` (offline, from the cache), `metrics`, `report`, then the full `make verify`.

## 5. Generative LLM at matched cost (S7)

- **`chat_json`** (`dm/client.py`) shares every guard of the decision path (decisions doc, AC4). Every request
  carried `provider: {"data_collection": "deny", "require_parameters": true}`, `response_format` json_schema
  (strict), temperature 0, seed 2026 and max_tokens 300.
- **Model** (`llm_catalog.json`; rule in `configs/baselines.yaml` `llm.selection`, fixed before any call). 463
  catalog models gave 11 candidates. The reference is the median realized cost of the 19 NA-06 API decision
  models, $0.0422 per 1,000 Call A requests. Order by distance to it:

  | # | Model | Projected $/1,000 | Cutoff |
  |---|---|---|---|
  | 1 | **mistralai/mistral-nemo** | 0.034 | 2024-04-30 |
  | 2 | mistral-small-24b-instruct-2501 | 0.062 | 2023-10-31 |
  | 3 | llama-3.1-8b-instruct | 0.062 | 2023-12-31 |
  | 4 | phi-4 | 0.090 | 2024-06-30 |
  | 5 | mistral-small-3.2-24b | 0.103 | 2023-10-31 |
  | 6 | qwen-2.5-7b-instruct | 0.129 | 2024-06-30 |
  | 7 | llama-3.3-70b-instruct | 0.143 | 2023-12-31 |
  | 8 | gpt-4.1-nano | 0.153 | 2024-06-30 |
  | 9–11 | command-r-08-2024, gpt-4o-mini (×2) | | |

  The chosen model costs $0.029 / $0.03 per M input / output tokens.
- **Sample** (`work/baselines/llm_sample.parquet`): 2,000 val-B D0 events with a Call A state, outside the embargo
  (2025-10-08 … 12-31), tier × month, seed 2026.
- **Calls:** 2,000 of 2,000 answered with HTTP 200 (one probe, then 1,999 at concurrency 8). Providers: DekaLLM
  1,771, Parasail 140, DeepInfra 89, all under `data_collection: deny`; build `mistralai/mistral-nemo`. Mean
  tokens: 827 input, 116 output. Latency p50 6.8 s, p95 18.1 s.
- **Validity:**
  - 1,978 valid, of which 234 were renormalized (sums 0.95 … 1.05);
  - 22 invalid: 21 sums outside 1 ± 0.05 (0.9 … 1.6), 1 `finish_reason` "error", 1 content that was not JSON.

  Invalid answers are not in `llm.parquet`; no re-asking.

  **Disclosure.** The first parse also marked 176 answers invalid whose sums were exactly 1.05 or 0.95: in
  floating point, 0.4 + 0.4 + 0.25 is 4e-17 above 1.05. The rule as recorded ("within 0.05 of 1") includes them,
  so the parser now compares with a 1e-9 margin (`schemas.SUM_EPS`, tested; mutation RED), as the decision-model
  bound 0.0105 already does. The cache's stored `valid` flag of those 176 rows keeps the first verdict;
  predictions are always re-parsed from the raw responses.
- **Cost per 1,000 decisions:**

  | Model | $ per 1,000 | Questions per request |
  |---|---|---|
  | **mistral-nemo (LLM, Q1 only)** | **0.0194** | 1 |
  | inception/mercury-decide | 0.0234 | 4 |
  | respan/span-02 | 0.0311 | 4 |
  | liquid/d1-ultra | 0.0422 | 4 |
  | nace-ai/drex-v2.0 | 0.0491 | 4 |
  | cloudflare/clef | 0.0676 | 4 |
  | openai/gpt-6-luna-decisions | 0.1142 | 4 |
  | 19 API decision models: range / median | 0.019–0.180 / 0.042 | 4 |
  | Laya (local) | 0 | 4 |

  The decision-model figures are NA-06 stage 1 Call A, core battery. Actual / projected for the LLM = 0.25,
  because the dry run uses 3 bytes per token and max_tokens.
- **Limits.**
  - These are verbalized probabilities, not the model's token probabilities (PRD risk note).
  - Three providers served the model, so temperature 0 and the seed do not guarantee identical answers on a
    rerun; the cache keeps the ones used.
  - No val-B metric here: NA-11 evaluates the LLM on val-B and runs the test subsample after the freeze (≤ $1).

## 6. Spend

| | USD |
|---|---|
| NA-09 cap | 2.00 |
| S7 projection (dry run, before sending) | 0.155 |
| S7 actual (2,000 chat calls) | 0.038884 |
| S6 (local Laya) | 0 |
| NA-09 total (ledger) | **0.038884** |
| ledger − Σ cache cost (NA-09) | 0.0 |
| cumulative, this worktree's ledger (NA-05 + NA-06 + NA-09) | 3.669428 |
| account before S7 / after S7 (`key_usage.json`; NA-07 spent in parallel from the same key) | 10.284 / 10.091 left |

## 7. Look-ahead self-check (inputs and availability)

| Input | Source | Availability | Used by |
|---|---|---|---|
| state's articles (ids, rank) | rebuilt from `events_d0.news_w0` + NA-04 exclusions; checked against every state | `w0` (t_avail ≤ 09:15 ET of s) | sentiment, embed, tags |
| vendor sentiment, intensity, tag type, 5 flags | `articles_clean` | `selection_only`; pre-registered baseline signals (§10.1, §10.3); only these pass `check_inputs(vendor=True)` | sentiment, tags |
| source class (domain), novelty, `dup_count_w0` | `articles_clean` | `w0` (novelty and duplicates look backwards only) | tags |
| bge-small vectors | `embeddings_ts` | `w0` (the article's own scrubbed text) | embed |
| attention (articles, stories, duplicates, ratio; 60-session mean) | `events_d0` | `w0` / `t_minus_1` | embed, tags |
| tier, sector | `events_d0`, `context_company` | `t_minus_1` / static | tags, price-only |
| z_m5 / z_m20 / z_m60, σ regime | `context_company` | `t_minus_1` | price-only |
| z_vol(t−1) | `panel_public` z_vol of prev(s) | `t_minus_1` (`z_vol_lag1`); absent for 2026 sessions | price-only D0 |
| G = z_cc,t, z_vol,t | `reaction_d2` | `d2_reaction` (after close(s)); train / val only | price-only D2 |
| z_on,t | `panel_public` | `d2_reaction` as `react_z_on`; train / val only | price-only D2 |
| masked Call A / Call B states | NA-04 state files | D0 / D2 (states built with `pit.check_inputs`) | Laya, LLM |
| targets e5, z_cc, \|z_cc\|, z_on, z_id, y2 | `panel_public` (purged by split) | `post`: fitting on train, tuning on val-A, evaluation on val-A only | all |

No input dated after its decision point enters a model. No 2026 price, return, volume or reaction is read: the
test features are NA-04's t−1 context and the state's articles. The LLM's knowledge cutoff (2024-04-30) is
before the sample.

## 8. Deviations from PREREG

- **One §15 row (NA-09, "Before").** It records the §10 operationalizations: features, maps, grids, the P maps
  on val-A, the vendor exception, price-only test predictions moved to NA-11, Laya's scope, §10.6 left to NA-11,
  and the LLM rule, model, prompt and parse rule. It was written after the fitted baselines' val-A grids and
  before any LLM call and any Laya metric.
- **Column additions.** The schema adds `session`, `company_id` and `y_hat` to the PRD's nine columns
  (decisions doc).
- **z_vol,t at D2.** Price-only D2 includes z_vol,t, because PREREG §11.5's R lists z_vol; the PRD's "the same"
  list has z_vol(t−1) only.

## 9. STOP conditions and owner decisions

- **S6 runtime.** The projection was over ~8 h (13.4 h at batch 1; batching and two processes were slower). I
  asked before starting, and the operator chose all splits. The run's rate was ~0.73 s per request (GPU shared
  with the desktop and other worktrees).
- **Credit.** Checked before the first paid call: $10.32 left against a $0.155 projection. No STOP fired.
- **No PREREG §13 STOP condition applies.**

Owner decisions needed:
1. **Matched cost.** The S7 model came from a rule (matched to the NA-06 API median $/1,000, cutoff before the
   train start) rather than from name recognition. If a well-known model is wanted as well (gpt-4.1-nano,
   $0.153 per 1,000; or gpt-4o-mini), it would cost about $0.3 on the same 2,000 events. It would be a disclosed
   second comparator.
2. **NA-11.** It must produce the test predictions of price-only (D0 needs z_vol(t−1) of 2026; D2 the 2026
   reactions), Laya Call A and the LLM subsample after the freeze, with the saved models and settings.

## 10. Files, tests and run records

- **New code:** `src/newsaction/baselines/{__init__, schema, data, fitting, gbm, sentiment, embed_ridge, tags_gbm,
  price_only, laya_zeroshot, llm_baseline, metrics, run}.py`.
- **Changed code:**
  - `src/newsaction/dm/client.py`: `ChatSpec`, `ChatResult`, `chat_json`, `chat_json_batch`, `run_chat`,
    `dry_run_chat`, `chat_key`, `credits`, `account_left`; refusals shared through `check`; transport by URL and
    body;
  - `dm/schemas.py`: `ChatProvider`, `ChatMessage`, `ChatRequest`, `ChatResponse`, `ParsedChat`,
    `parse_chat_response`; `_sum_rule` shared, the decision-model rule unchanged;
  - `dm/costmodel.py`: `Price.completion`, `estimate_chat`, several price snapshots;
  - `dm/__init__.py`: `ApiConfig.chat_url`, `credits_url`, `chat_catalog`; `ChatCost`.
- **Configs:** `configs/baselines.yaml` (new); `configs/dm.yaml`; `configs/frozen.yaml` (`chat_models`);
  `configs/availability.yaml`.
- **Docs:** `docs/PREREG.md` §15 row; `docs/decisions/NA-09.md`; `docs/DATA_CONTRACT.md` (NA-09 section);
  `README.md` guard row.
- **Tests:** `tests/test_baselines_schema.py` (29), `test_baselines_fit_ranges.py` (15),
  `test_baselines_guards.py` (26), `test_chat_json_refusals.py` (36); fakes `tests/baselines_fakes.py`.
- **Ledgers:** `ledgers/spend.jsonl` (NA-09: 2,000 reserve / spend pairs); `ledgers/trials.jsonl` (NA-09: 58
  grid + the final val-A metrics); `test_access.jsonl` unchanged.
- **Run records:** `artifacts/NA-09/{llm_dry_run.json, key_usage.json, llm_summary.json, summary.json}`;
  `work/baselines/laya_run.log`.
- **Commands:**
  ```bash
  uv run python -m newsaction.baselines.run --stage articles   # state articles (rebuilt and checked)
  uv run python -m newsaction.baselines.run --stage fit        # S2–S5 (about 2 min, peak RSS 2.5 GB)
  uv run python -m newsaction.baselines.run --stage llm_sample
  uv run python -m newsaction.baselines.run --stage llm_select # catalog GET, no spend
  uv run python -m newsaction.baselines.run --stage llm_dry    # projection, no spend
  uv run python -m newsaction.baselines.run --stage llm_run    # credit check, then 2,000 calls
  uv run python -m newsaction.baselines.run --stage laya       # S6, detached (~17 h here)
  uv run python -m newsaction.baselines.run --stage laya_predictions
  uv run python -m newsaction.baselines.run --stage llm_predictions
  uv run python -m newsaction.baselines.run --stage metrics
  uv run python -m newsaction.baselines.run --stage report
  ```
- **Recompute a val-A IC** (verification step 3): join a prediction file to `panel_public` on (session,
  company_id) with `is_rep`, or through `events_d0.symbol_id`; both give the same rows (the event's symbol is
  the representative class for all 9,079 val-A events). Keep `split == "val_a"` and `embargo == False`. The daily
  Spearman IC needs ≥ 5 events a day; take the mean with a Newey–West t (5 lags).
