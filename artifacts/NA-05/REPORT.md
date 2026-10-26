# NA-05 REPORT — decision-model client, cache, budget guard, catalog, canary, local Laya, pilot

Date: 2026-10-26 · Branch `feat/NA-05-client-pilot` (worktree `NewsAction-NA05`, cut from `main` @ `214108f`;
NA-08 ran in parallel in its own worktree) · Decisions: `docs/decisions/NA-05.md` · Artifacts:
`artifacts/NA-05/{catalog.json, canary_v1.jsonl, canary_baseline.parquet, pilot.json, key_usage.json}`.

**Result.** `newsaction.dm` is the single path to a decision model. It provides:
- typed requests whose provider object can only say `data_collection: deny`;
- a strict parser that records problems and repairs nothing;
- a sha256 response cache;
- the refusal rules (a)–(f), checked before any cache read or send;
- a projection check plus a per-call reservation in the spend ledger;
- retries and an asyncio semaphore;
- an offline mode;
- local Laya behind the same response shape.

The pilot spent **$0.103922** of the $0.20 cap (cumulative $0.103922 of $30) on 1,949 answered API calls. All
other calls were either free or not billed: 278 local Laya calls and 65 failed attempts. The spend ledger matches
both the cache (Σ usage.cost, difference 1e-16) and the key's own usage on OpenRouter (difference 1e-16).

**STOP (PREREG §13), operator decision needed before NA-06.** The five pilot models bill the state once per
request. But the smoke test of the rest of the catalog found **six models that bill the state once per question**,
exactly 4.00 state copies with 4 questions:
- perplexity/pplx-decider-flash-v1.2
- respan/span-02
- scaledown/classify-1
- togethercomputer/tev1-4b-experimental
- upstage/solar-decide
- upstage/solar-decide-flash

The consequences and the reduced plan are in §8. Nothing in NA-05 depends on them, and no further spending was
done.

**Operator decisions (2026-10-26), applied** (§9):
- (a) the per-question models stay in NA-06 with the core battery;
- rounded probabilities within one step (|Σp − 1| ≤ 0.0105) are renormalized and flagged (a change to PRD S1),
  and the pilot numbers were recomputed from the cache with no API call;
- the NA-11 canary rule is recorded in `configs/dm.yaml` `canary`;
- classify-1's `state_as_text` is confirmed.

Pilot answers (`pilot.json` `items`):

| # | Question | Answer |
|---|---|---|
| 1 | Billing basis | **Once per request** for all 5 pilot models. Median state copies with 2 / 4 / 13 questions = 1.00 (mercury 1.01). Smoke test: 10 models once, **6 per question**, 2 never answered |
| 2 | usage.cost vs price × input_tokens; failed calls billed? | Ratio **1.000** for every call of every model (min 1.0, max 1.0). **Failed calls are not billed**: 65 failed attempts (61 × 400, 3 × 429, 1 × 502), and the key's usage changed by exactly the ledger's spend. Mercury bills some repeated identical requests far below their size (5 of 361, a prompt cache) |
| 3 | Truncation (sentinel at the end of 2K / 4K / 8K-token states) | **Read to the end at every length by all 5** (P(mentioned) ≥ 0.9988; start and no-sentinel controls right). Smoke at 2K: both solar models miss the end sentinel (0.18 / 0.32; start 0.85 / 0.91): silent truncation, excluded. Laya typed-decisions reports its own truncation beyond 1,024 tokens |
| 4 | Repeat variance (20 states × 5 repeats) | **luna and pplx deterministic** (100% identical). Jev mean / max \|Δp\| 0.011 / 0.10 (\|ΔN̂\| 0.048 / 0.21). mercury 0.013 / 0.21. d1 0.026 / 0.37 (\|ΔN̂\| 0.13 / 0.62). `seed` is accepted by all and **changes nothing** (seed 1 vs 2 ≈ two calls with one seed). Laya identical |
| 5 | Question interaction (mean \|ΔN̂\|: Q1 alone vs in core; core + extended vs core) | Jev 0.048 / 0.065 against repeat noise 0.048. luna 0 / 0. mercury 0.062 / 0.048 (noise 0.048). d1 0.126 / 0.120 (noise 0.130). **pplx-decider 0.212 / 0.169 against noise 0**: its answers depend on the other questions of the call. Laya 0 / 0 |
| 6 | Latency p50 / p95 (ms) at concurrency 1 / 4 / 8 / 16; errors; rate limits | p50 Jev 218–242, luna 311–427, mercury 509–630, d1 312–346, pplx 298–345; p95 0.3–1.8 s. **No error** in 800 latency calls (one 429 retried, pplx at c = 1); no rate-limit header is returned |
| 7 | Response format | Legends present and matching 100%. Choice = argmax 100%. luna, mercury, d1, pplx: Σp = 1 to 1e-15 and score = Σ i·p_i exactly. **Jev 1.14: probabilities on a 0.01 grid**, so 19 of 1,509 answers sum to 0.99 / 1.01; since the operator's decision they are renormalized and flagged (all 1,509 valid). Its score differs from Σ i·p_i by 0.013 on average (max 0.08) |
| 8 | Numeracy (fixed positive news; reaction at 7 magnitudes × 2 directions): is reaction_adequacy monotone? | **No, for every model.** J is not non-increasing in the rise for any model; Spearman ρ(J, rise) runs from −0.68 (luna, the expected sign) to +0.89 (mercury). After clearly positive news, a fall gets "much_too_large" and P(wrong_direction) ≈ 0 (mean 0.000–0.009), while large rises draw P(wrong_direction) 0.20–0.56 |
| 9 | data_collection = deny accepted? | **Yes, by every model that answered** (21 catalog models). None refused for data policy. Respan span-01 / span-01-lite refuse our requests for format reasons, so it is not determined for them |
| 10 | Build ids; catalog hash | jev-1.14-20261014, gpt-6-luna-decisions-20261006, mercury-decide-20260930, d1-20260930, pplx-decider-v1.2-20261016: one build per model for all 361 calls. Catalog snapshot sha256 `205464ea…58d4d` (30 models, 2026-10-26 17:47 UTC) |

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 schemas | done | `src/newsaction/dm/schemas.py`: `DecisionRequest`, `QuestionSpec` (choice / score; noul refused), `Provider` (deny only), `ChoiceAnswer`, `ScoreAnswer`, `Usage`, `DecisionResponse`, `parse_response` (problems vs notes; the raw answer is never altered; a sum within one rounding step is renormalized and flagged, operator decision) |
| S2 cache | done | `dm/cache.py`: `cache/decisions.sqlite`, tables `responses` and `attempts`; key over {model, state, ordered questions, provider, params, repeat_idx} |
| S3 client | done | `dm/client.py`: refusals (a)–(f) + pilot period; `dry_run`; projection check + per-call `reserve` / `record` / `release`; tenacity retries (429 / 5xx / transport, 5 attempts, jitter, Retry-After); asyncio semaphore; `offline=True`; `state_as_text`; `key_usage`, `get_json`; `reconcile` |
| S3 cost model | done | `dm/costmodel.py`: catalog prices, billed bytes, defaults, per-model calibration (two rates, robust fit; written to `configs/dm.yaml`) |
| S4 catalog + eligibility | done | `dm/catalog.py`; `artifacts/NA-05/catalog.json`; `configs/frozen.yaml` `eligible_models` (32 rows) and `free_model_approvals: {}` |
| S5 local Laya | done | `dm/laya_local.py`: `local/laya-typed-decisions` and `local/laya-base` @ `55cf4c4e`, weights sha256-verified, MPS → CPU, max_len 1024, fp32, exact float64 probabilities |
| S6 parse | done | `dm/parse.py`: PREREG §7 (N̂, E\|N̂\|, M, J, W, C, RG) and A2.4 (H, X, labels, U_unc, mixed), confidence summaries |
| S7 canary | done | `dm/canary.py`; `artifacts/NA-05/canary_v1.jsonl` (50 states with sha256s), `canary_baseline.parquet` (7 models) |
| S8 pilot | done | `dm/pilot.py` (stages catalog → billing → calibrate → measure → smoke → laya → report); `artifacts/NA-05/pilot.json`; `dm/runner.py` (state files → requests → frames, for NA-06 on) |

Also: `io.register_artifact` (committed outputs in the manifest), `configs/dm.yaml` (new), a README guard row.

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 budget guard | `tests/test_dm_budget.py` (mock transport). (1) A 5-call batch projected above a $1e-6 chunk cap raises `BudgetExceeded` with 0 transport calls and an empty ledger. (2) An open hold of someone else's batch leaves too little: raises, 0 calls; after `release` it is sent. (3) 4 calls at concurrency 2: each spend line has a reserve line earlier in the ledger with the same rid; `reconcile() == 0`; nothing left held. (4) HTTP 400 → reserve + release, no spend. (5) 429 then 200 → 2 attempts, one spend. (6) usage without cost → computed price × tokens recorded, still reconciles. **Mutations** "skip reserve()" and "projection check off": **RED**. Live: NA-05 ledger $0.103922341 = Σ cache cost (reconcile 9.7e-17) | PASS |
| AC2 cache | `tests/test_dm_cache.py`: a repeated request is a hit with no transport call and no ledger line; one character of the state (object or string), a question, an option's order, the question order, the model, a param, the repeat index each give another key; the session id does not; duplicates in a batch are sent once; offline serves hits and raises `CacheMiss` on a miss with 0 calls; a key is written once. **Mutations** "questions not keyed" (the PRD's), "repeat_idx not keyed", "option order not keyed", "cache read off", "offline check off": **RED** | PASS |
| AC3 refusals | `tests/test_dm_refusals.py`, each online and offline, 0 transport calls: (a) third party (API only; local allowed), (b) test period by session or split label, API and local, allowed after a freeze record, (c) val-B by session or label (API; local allowed; allowed after `allow_val_b: true`), (d) unmasked without a registered probe (`unmasked_twin` allowed), (e) not in `eligible_models` (pilot lifts it), (f) `:free` without approval (pilot does not lift it), pilot period (val-A / val-B states refused with `pilot=True`), a batch with one bad request sends nothing, `Provider(data_collection="allow")` impossible. **Mutations** "2026 guard removed" (the PRD's) and (a), (c), (d), (e), (f), pilot period, split-label-only test check, refusals moved after the cache, provider not deny-only: **RED** | PASS |
| AC4 pilot | `pilot.json` `items` has a numeric / boolean answer for each of the 10 items (table above). Spend $0.103922 ≤ $0.20 (ledger). Sessions of every state sent, read from the cache's `meta_json`: 1,976 train-split states, latest **2025-06-30**, and 251 synthetic; no val-A, val-B or test state; refused by the client otherwise (`pilot_period`) | PASS |
| AC5 local Laya | typed-decisions on the 50 canary states: 50 / 50 valid `DecisionResponse`s, \|Σp − 1\| ≤ 2.2e-16 (float64 recomputation; laya's own 4-decimal values kept and checked). Base checkpoint: 50 / 50. `tests/test_dm_laya_local.py` checks 20 canary states from the cache (AC5) and runs 3 states live (slow). **Mutation** "drift check off": RED | PASS |
| AC6 canary | `canary_v1.jsonl`: 50 lines C01–C50 with `state_sha256` / `questions_sha256` (`load_canary` refuses a tampered line, tested); `build_canary` reproduces the file byte for byte (sha256 `783aa96c…`). `canary_baseline.parquet`: 6,846 rows for the 5 pilot models and both Laya checkpoints, 978 rows each; 19 rows (Jev: C19 tone, C31 tone, C49 Q1) are `renormalized` | PASS |
| AC7 eligibility | `configs/frozen.yaml` `eligible_models`: all 30 catalog ids + 2 local ids, each with `include` and a reason (`tests/test_dm_catalog.py::test_frozen_lists_every_catalog_id_with_a_reason`). 21 included, 11 excluded (§4) | PASS |
| GAC1 | `make verify` exit 0 (after the operator's decisions): ruff "All checks passed!", "132 files already formatted"; mypy --strict "no issues found in 65 source files"; pytest **1,338 passed, 1 xfailed** (139 s); manifest 61 artifacts OK; ledgers OK (spend 4,020, test_access 2, trials 94) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (inputs size + mtime) | PASS |
| GAC3 | `tests/test_blinding.py` passes: no 2026 literal in `src/` (the client reads the test start from `configs/splits.yaml`); no sealed-path use; `ledgers/test_access.jsonl` unchanged (2 NA-01 lines) | PASS |
| GAC4 | NA-05 ledger $0.103922341 vs Σ `responses.cost` (chunk NA-05) $0.103922341: difference 9.7e-17; chunk ≤ $0.20; total $0.103922 ≤ $30 | PASS |
| GAC5 | 5 new artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest`: 61 artifacts OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte for byte
(asserted). It cleared `__pycache__` before every run, because two mutations of equal length written within
the same second can leave a stale `.pyc` that hides the second mutation; the first run of the script showed
exactly that for (a). **30 / 30 RED** (after the operator's decisions; 27 / 27 before them):

| Area | Mutations |
|---|---|
| budget | skip reserve(); projection check off |
| cache | questions not keyed; repeat_idx not keyed; option order not keyed; cache read off; offline check off |
| refusals | (a) third party; (b) 2026 guard; (b) split label only; (c) val-B; (d) unmasked; (e) eligibility; (f) `:free`; pilot period; refusals after the cache; provider not deny-only |
| schema | sum bound off (everything renormalized); bound widened to 0.02; `renormalized` flag not set; rounded sums not rescaled; missing type accepted; legend check off |
| Laya | drift check off |
| parse | N̂ midpoint changed; J's sign term dropped |
| canary | hash check off |
| cost / eligibility | billing basis by max (the mercury anomaly flips it); renormalized answers counted as a failure; alias kept |

`git status` afterwards showed only the author's changes.

## 3. The pilot in detail

**Models.** The PRD's five (typesafe/jev-1.14, openai/gpt-6-luna-decisions, inception/mercury-decide, liquid/d1,
perplexity/pplx-decider-v1.2) plus local Laya. **States:** the canary (20 train Call A, 10 train Call B, 6
synthetic Call A, 14 numeracy Call B), 160 more train Call A states for latency, and synthetic sentinel states.

| Stage (calls by the stage that first sent the request) | Calls | USD |
|---|---|---|
| billing (2 states × Q1 / Q1+Q2 / core / core + extended) | 40 | 0.00202 |
| canary, repeat 0 = the baseline (10 more are billing's core calls) | 240 | 0.01100 |
| repeats 1–4 of the 20 Call A canary states | 400 | 0.01849 |
| seeds (5 states × seed 1 / 2 × 2 calls, incl. the 5 probes) | 100 | 0.00431 |
| interaction, Q1 alone and core + extended (20 more are billing calls) | 180 | 0.01118 |
| truncation 2K / 4K / 8K × end / start / none (+ kev-4b's probe, refused) | 45 | 0.00907 |
| latency, concurrency 1 / 4 / 8 / 16 × 40 distinct states | 800 | 0.03692 |
| smoke: 16 answering models × 9 calls (2 canary, 3 at 2K, 4 billing check) | 144 | 0.01094 |
| total (1,949 answered calls; plus 65 failed attempts, not billed) | 1,949 | **0.103922** |

By model: luna $0.0454, Jev 1.14 $0.0227, mercury $0.0091, d1 $0.0081, pplx $0.0077 (pilot models $0.0930); the 16
smoke models $0.0109.

**Item 1, billing.** The number of state copies billed with n questions is k_n = (tokens(n, long state) −
tokens(n, short state)) / (tokens(1, long) − tokens(1, short)), using C16 (386 ModernBERT tokens) and C17 (748).
- Jev, luna, d1 and pplx: k_2 = k_4 = k_13 = 1.00.
- mercury: 0.93 / 1.01 / 6.22. The 6.22 comes from one response that reported 161 input tokens for a request of
  about 2,000. Its other 13-question call billed 2,357 tokens, which is once-per-request. Four more mercury calls
  (identical requests sent again) billed about 250 tokens: a provider prompt cache. My first billing rule took
  the maximum over n and flagged mercury as per question. The rule now takes the median, and the decisions doc
  records the change.
- Smoke models (Q1 alone vs core): 10 at k_4 = 1.00 and 6 at k_4 = 4.00 (the STOP).

**Item 2, cost and failures.**
- usage.cost / (catalog price × input_tokens) = 1.000 for all 1,949 calls. No request price, no discount.
- input_tokens include a per-request overhead (calibration: Jev 349, d1 136, pplx 156, mercury 177, luna 85
  tokens), and states and questions tokenize at different rates (§7).
- Failed attempts: 61 × 400 (respan and scaledown format refusals, re-sent by the smoke reruns; kev-4b's
  12,288-token probe over its 8,192 context), 3 × 429 and 1 × 502 (all retried successfully).
- Key usage: $0.00006174 before billing → $0.103922341 at the report. That is exactly the ledger, so failed calls
  are not billed. The key's counter lags a call by up to about a minute.

**Item 3, truncation.** States of 2,048 / 4,096 / 8,192 ModernBERT tokens of neutral filler, with the sentinel
"a purple giraffe named Zephyrine" last, first or absent; one choice question.
- **The 5 pilot models:** P(mentioned) at the end ≥ 0.9988 at every length; controls right; their own token counts
  were 1,967–2,745 / 3,836–5,203 / 7,546–10,053.
- **Smoke at 2K:**
  - 14 models read to the end;
  - both solar models do not (§4);
  - classify-1 reads to the end with the state as text.
- **Laya typed-decisions** reports truncation (`usage.truncated`) at every length, since its window is 1,024. The
  base checkpoint cannot do the task (start sentinel 0.41–0.45), so its result is inconclusive.

**Item 4, repeats.**

| Model | identical | mean \|Δp\| | max \|Δp\| | mean \|ΔN̂\| | max \|ΔN̂\| | seed 1 vs 2 / same seed twice |
|---|---|---|---|---|---|---|
| jev-1.14 | 0% | 0.011 | 0.10 | 0.048 | 0.21 | 0.014 / 0.013 |
| luna | 100% | 0 | 0 | 0 | 0 | 0 / 0 |
| mercury | 12.5% | 0.013 | 0.21 | 0.048 | 0.14 | 0.013 / 0.010 |
| d1 | 0% | 0.026 | 0.37 | 0.130 | 0.62 | 0.029 / 0.034 |
| pplx-decider | 100% | 0 | 0 | 0 | 0 | 0 / 0 |
| Laya (both) | 100% | 0 | 0 | 0 | 0 | — |

Every model accepts a top-level `seed` (HTTP 200), and it changes nothing: the difference between seeds equals the
difference between two calls with the same seed.

**Item 5, interaction.** Mean |ΔN̂| over the 20 Call A canary states:

| Model | Q1 alone vs in core | core + extended vs core | repeat noise | other core questions, \|Δp\| core + ext vs core |
|---|---|---|---|---|
| jev-1.14 | 0.048 | 0.065 | 0.048 | 0.014 |
| luna | 0 | 0 | 0 | 0 |
| mercury | 0.062 | 0.048 | 0.048 | 0.012 |
| d1 | 0.126 | 0.120 | 0.130 | 0.030 |
| pplx-decider | **0.212** | **0.169** | 0 | 0.031 |

PREREG A2 assumes that "decision models answer every question in a request independently (the NA-05 pilot
verifies this)". That holds within noise for Jev, luna, mercury and d1, and exactly for Laya. **It does not hold
for pplx-decider-v1.2,** which is deterministic and still moves N̂ by about 0.2 (on the ±3.5 scale) when other
questions share the call (owner decision 4).

**Item 6, latency.**

| Model | p50 / p95 ms at c = 1 | c = 4 | c = 8 | c = 16 |
|---|---|---|---|---|
| jev-1.14 | 218 / 1,755 | 222 / 311 | 238 / 1,056 | 242 / 854 |
| luna | 311 / 484 | 397 / 504 | 364 / 1,198 | 427 / 1,416 |
| mercury | 509 / 1,090 | 559 / 1,195 | 612 / 1,215 | 630 / 1,378 |
| d1 | 337 / 530 | 312 / 599 | 345 / 480 | 346 / 1,283 |
| pplx-decider | 298 / 529 | 339 / 1,105 | 328 / 674 | 345 / 522 |

- **Errors:** 800 / 800 answered. One 429 (pplx, c = 1), retried.
- **Throughput:** a batch of 40 at c = 16 takes 1.7–3 s.
- **Rate limits:** no `x-ratelimit-*` or `retry-after` header was ever returned, so no limit was observed up to
  c = 16. At c = 16 and ~0.35 s per call that is about 45 calls/s for one model, and NA-11's ~140,000 calls take
  under an hour per model at that rate.

**Item 7, format.**
- mercury, d1 and pplx: full-precision probabilities summing to 1 within 1e-15. luna: probabilities on a 0.01 grid
  that always sum to exactly 1. For all four, score = Σ i·p_i exactly, legends present, choice = argmax.
- Jev 1.14 (and 1.13) also use a 0.01 grid, but Jev's sums are off by one step in 1.3% of answers (19 of 1,509;
  in the canary: C19 tone, C31 tone, C49 Q1). Its score is the unrounded position (mean gap 0.013).
- Five smoke models (clef, clef-flash, kev-4b, drex-v1.5, drex-v2.0) round to 4 decimals, and 2–4 of their 10
  answers sum to 0.9998–1.0001; clef-omni also rounds to 4 decimals, without an off sum. solar-decide rounds to 6
  (one answer at 0.999999).
- Under the PRD's original 1e-6 rule all of these answers were invalid. Since the operator's decision (owner
  decision 2) every one of them is renormalized and flagged: no answer of any model is left invalid by its sum.

**Item 8, numeracy.** The positive news (beat, raised guidance, buyback) is read correctly: N̂ +1.7 to +2.3 in
Call A, and every model gets all six synthetic Call A directions right (miss, downgrade and investigation
negative; approval positive; conference ≈ 0 with materiality ≤ 0.03). In Call B:

| Model | J by rise z = 0.3 / 0.7 / 1.5 / 2.5 / 4 / 6 / 9 | argmax at 2.5–9 | mean W after falls / rises |
|---|---|---|---|
| jev-1.14 | 0.70 / 0.29 / −0.08 / 0.07 / 0.28 / 0.52 / 0.64 | wrong_direction, too_small | 0.00 / 0.20 |
| luna | 1.00 / 0.90 / 0.64 / 0.11 / 0.04 / 0.14 / 0.28 | wrong_direction | 0.00 / 0.36 |
| mercury | −0.89 / −0.96 / −0.92 / −0.00 / 0.00 / 0.01 / 0.01 | wrong_direction | 0.00 / 0.56 |
| d1 | −0.18 / −0.49 / −0.33 / 0.06 / −0.03 / 0.06 / 0.18 | wrong_direction, about_right | 0.01 / 0.23 |
| pplx-decider | 0.19 / −0.44 / −0.34 / −0.09 / 0.00 / 0.04 / 0.06 | wrong_direction | 0.00 / 0.49 |

None is monotone. A fall after this news, which is the wrong direction, gets "much_too_large" from every model
(J ≈ −0.9, W ≈ 0). Large rises get W 0.2–0.56. N̂ in Call B also moves with the reaction: mercury's N̂ falls from
+2.1 to +0.2 as the rise grows, and rises to +3.2 as the fall grows. These are inputs for NA-07's anchoring and
encoding study (owner decision 5).

**Item 9, data policy.** Every request of the chunk carried `provider: {"data_collection": "deny"}`: the schema
allows nothing else, and all 1,949 cached request bodies were checked. No model refused it.

**Item 10, builds.** One build per model throughout. Smoke builds are listed in `pilot.json` (clef and clef-flash
return their id without a date).

## 4. Eligibility (PREREG §8.1; `configs/frozen.yaml` `eligible_models`)

**Included (21).**
- The five pilot models, each with 341 / 341 well-formed calls answered.
- cloudflare/clef, clef-flash, clef-omni; jaredpalmer/kev-4b; liquid/d1-ultra; microsoft/microsoft-decision-1;
  nace-ai/drex-max, drex-v1.5, drex-v2.0; typesafe/jev-1.13: each 5 / 5 calls answered, the 2K sentinel read, the
  state billed once.
- perplexity/pplx-decider-flash-v1.2, respan/span-02, scaledown/classify-1 (state sent as text),
  togethercomputer/tev1-4b-experimental: 5 / 5 answered and the 2K sentinel read, but the state is **billed per
  question**.
- local/laya-typed-decisions and local/laya-base.

Each reason states the billing basis and, where it applies, the probability rounding (for example "probabilities to
4 decimals (40% of answers off 1 by a rounding step)").

**Excluded (11):**

| Model(s) | Reason |
|---|---|
| ~typesafe/jev-latest, ~perplexity/pplx-decider-latest, ~perplexity/pplx-decider-flash-latest | aliases |
| inception/mercury-decide:free, respan/span-01-lite:free | `:free` duplicates |
| baseten/elephant-1:free, baseten/mammoth-1:free | `:free` without operator approval (CLAUDE.md C13) |
| respan/span-01, respan/span-01-lite | refuse every request: our state object ("Respan state must be a string or … input … output"), and with the state as text every question that is not a `noul` ("Respan only accepts noul questions…"), which PREREG §7 forbids |
| upstage/solar-decide, solar-decide-flash | silent truncation: the 2K end sentinel is missed (P 0.18 / 0.32) while the start sentinel is found (0.85 / 0.91) and nothing reports a cut; they also bill per question |

**How the rules were settled.** The first eligibility pass also excluded clef, clef-flash, kev-4b, drex-v1.5 and
drex-v2.0. The reason given was that more than 10% of their answers "fail the strict schema". Every one of those
failures is a sum of 0.9998–1.0001 from 4-decimal rounding. PREREG §8.1 excludes missing probabilities, not rounded
ones, so the rule was corrected (`Outcome.rounded_share`; mutation-tested). The smoke evidence is thin (5 calls per
model), so NA-06's first calls are effectively their real test.

## 5. Local Laya

| | typed-decisions | base (root) |
|---|---|---|
| build | `local/laya-typed-decisions@55cf4c4e…` | `local/laya-base@55cf4c4e…` |
| device, load | MPS, 0.7–2.8 s | MPS, 0.6 s |
| canary | 50 / 50 valid; median 411 ms per call (4 question rows), p95 616 | 50 / 50; 441 / 627 ms |
| repeats, interaction | identical; 0 / 0 | identical; 0 / 0 |
| synthetic Call A N̂ (beat / miss / downgrade / approval / investigation / conference) | +0.68 / −0.96 / −0.56 / +0.01 / −0.18 / +0.10; M 0.63–0.72 everywhere | −0.72 / −1.14 / −0.97 / −0.44 / −0.65 / −0.50 |
| truncation (window 1,024) | reported (`usage.truncated`) at 2K / 4K / 8K | sentinel task not solved (inconclusive) |
| numeracy | not monotone (ρ +0.75) | not monotone (ρ +0.21) |

Zero-shot, typed-decisions reads the direction of clear earnings and analyst news, and gives the same materiality to
everything. Base reads everything as negative. This matches the model card ("near chance zero-shot").
`input_tokens` counts the state once per question row (C01: 3,056 = 4 × ~764), and the state's 685 ModernBERT
tokens equal NA-04's count. laya clamps the shipped choice:11+ temperature 0.10 → 0.5 (Q17 only).

## 6. Canary

- **States:** canary_v1 has 50 states (§1). The 30 train states run 2024-08-13 … 2025-06-23 and are
  tier-stratified (10 Top-100, 8 Mid, 12 Rest).
- **Baseline:** repeat 0 of every pilot model and both Laya checkpoints, 6,846 rows (19 `renormalized`).
- **For NA-11 S5** ("STOP if any probability moved ≥ 0.02 vs the NA-05 baseline"): the repeat noise of Jev (max
  |Δp| 0.10), mercury (0.21) and d1 (0.37) exceeds 0.02 with nothing changed, so that rule would fire on noise for
  those three models. **Operator decision:** deterministic models (luna, pplx-decider, both Laya checkpoints) keep
  max |Δp| ≥ 0.02; any other model compares the canary's mean |Δp| with its own 5-repeat noise (Jev 0.0112,
  mercury 0.0125, d1 0.0255). Recorded in `configs/dm.yaml` `canary`; NA-11 implements it.

## 7. Cost model and projections

**Calibration** (`configs/dm.yaml` `costmodel.models`; 21 models): tokens = overhead + state bytes / r_state +
question bytes / r_question, with the state counted once per question for per-question models.
- **Pilot models (all ~338 calls each):**

  | Model | r_state | r_question | overhead |
  |---|---|---|---|
  | Jev 1.14 | 3.54 | 3.29 | 349 |
  | luna | 4.77 | 2.20 | 85 |
  | mercury | 4.39 | 2.71 | 177 |
  | d1 | 3.64 | 5.04 | 136 |
  | pplx | 4.24 | 4.59 | 156 |

- **Fit quality:** median absolute error 0.8–1.6%, 90th percentile ≤ 4.5%, 13-question requests ≤ 1.2%.
- **Smoke models:** calibrated from their 6 JSON calls.
- **Projections:** safety 1.1 when calibrated; uncalibrated models use per-question billing, 3 bytes / token and
  × 1.5.

**NA-06 stage 1** (PREREG §8.2: 700 val-A D0 events × Call A core per eligible API model; mean request 3,536
bytes): **$0.79** for all 19 API models, against NA-06's $4 cap.
- Dearest: clef-omni $0.127, classify-1 $0.098 (per question; $0.030 with Q1 alone), tev1-4b $0.082 ($0.024 with
  Q1 alone), luna $0.080.
- The five pilot models together $0.16.

**NA-11** (NA-03's call counts × real state sizes × each model's tokenizer and price; cap $18):

| Model | minimal | full | full + D1 + A3.5 |
|---|---|---|---|
| pplx-decider, d1, mercury | 2.0–2.7 | 4.8–6.1 | 5.6–7.1 |
| jev-1.14 / jev-1.13 | 5.8 / 5.7 | 12.3 / 12.1 | 14.7 / 14.5 |
| kev-4b, drex-v1.5, microsoft, clef-flash | 2.8–3.5 | 6.2–7.8 | 7.3–9.2 |
| d1-ultra, drex-v2.0, clef | 4.2–6.1 | 9.2–12.5 | 10.9–14.9 |
| drex-max | 8.0 | 16.1 | **19.2** |
| **luna** ($0.10/M) | 14.4 | **27.9** | **33.5** |
| **clef-omni** ($0.15/M) | **21.7** | **41.9** | **50.3** |
| per question: pplx-flash, span-02 | 4.4–4.9 | 9.2–10.1 | 10.6–11.6 |
| per question: **tev1-4b**, **classify-1** | **17.7 / 22.1** | **33.9 / 41.6** | **39.5 / 48.8** |
| … with §13's reduced battery (Q1, + Q5 for Call B) | 0.9–4.8 | 2.9–10.8 | — |

NA-04's owner decision 3 estimated $20.5–21.5 for the full plan at $0.10/M. With luna's real tokenizer, which
counts 2.2 bytes per question token, it is $27.9. PREREG §13's projection STOP applies at NA-11 against the
winner: if luna, clef-omni or drex-max wins, A2.6's cuts are needed; clef-omni (> $0.12/M) also triggers §13's
"Call A + one Call B" rule.

## 8. STOP conditions

- **PREREG §13, "the pilot shows the state is billed per question": FIRED for 6 catalog models.** None of them is
  a pilot model.

  | Model | State copies (4 q) | Price ($/M) | Eligible |
  |---|---|---|---|
  | perplexity/pplx-decider-flash-v1.2 | 4.0 | 0.01 | yes |
  | respan/span-02 | 4.0 | 0.01 | yes |
  | scaledown/classify-1 | 4.0 | 0.04 | yes (state as text) |
  | togethercomputer/tev1-4b-experimental | 4.0 | 0.042 | yes |
  | upstage/solar-decide / solar-decide-flash | 4.0 | 0.05 | no (silent truncation) |

  **Consequence.**
  - For these models each question re-bills the whole state: Call A core costs ~4× a once-billed call, Call B core
    ~3×, core + extended ~13×.
  - In NA-06 stage 1 they cost $0.02–0.10 each with the core battery ($0.006–0.03 with Q1 alone).
  - If one of them won NA-11, the full plan would be $9–42 instead of $3–11.

  **Reduced plan (§13).**
  - If such a model is the primary instrument: production asks Q1 (+ Q5 for Call B), re-projected at $2.9–10.8 for
    the full plan, and the extended battery (A2) is not asked of it (A2.6's cutting order).
  - For NA-06 stage 1 the options are:
    - (a) keep them with the core battery (projected $0.79 for all models, within the $4 cap);
    - (b) ask them Q1 only (stage 1 ranks on N̂ alone), at the cost of a different question set (item 5 shows
      that this can matter);
    - (c) exclude them from the tournament.

  **Not done in NA-05:** no plan was changed and nothing was spent on them beyond the smoke test.

  **Operator decision (2026-10-26): (a).** They stay in the NA-06 tournament with the full core battery, the same
  questions every model gets. If one becomes the primary instrument, §13's reduced battery applies (Q1, + Q5 for
  Call B; no extended battery).
- **PREREG §13, "winner priced above $0.12/M":** not evaluated before NA-11; clef-omni ($0.15/M) is the only
  eligible model above it.
- **PREREG §13, "any projection exceeds the remaining budget":** no projection of NA-05 did (largest $0.119 for
  the measurement stage, against $0.198 left). The NA-11 projections above exceed $18 only for luna, clef-omni,
  drex-max (with D1 + A3.5) and the per-question tev1-4b / classify-1.
- Budget: the chunk cap ($0.20) and the total cap were never approached; the per-call reservations never refused.

## 9. Owner decisions and the operator's answers (2026-10-26)

| # | Question | Operator's decision | Applied |
|---|---|---|---|
| 1 | Per-question billing (STOP, §8): (a) keep with the core battery, (b) Q1 only, (c) exclude | **(a)**. Keep them in NA-06 with the full core battery; if one becomes the primary instrument, §13's reduced battery (Q1, + Q5 for Call B; no extended battery) | Nothing to change: `eligible_models` includes them, and the cost model prices them per question (`configs/dm.yaml` calibration). Recorded in `docs/decisions/NA-05.md` |
| 2 | Rounded probabilities under the strict 1e-6 sum rule | **Accept \|Σp − 1\| ≤ 0.0105 (one rounding step), renormalize, flag `renormalized: true`**; beyond the bound, invalid | Yes; details below |
| 3 | The canary threshold of NA-11 S5 | **Mean \|Δp\| vs the model's own repeat noise (5 repeats); 0.02 on max \|Δp\| only for deterministic models** | Recorded as `configs/dm.yaml` `canary` (validated by `DmConfig.canary`): noise_repeats 5, deterministic_max_abs_dp 0.02, noisy_rule mean_abs_dp_vs_repeat_noise, and the deterministic models of the pilot (luna, pplx-decider, both Laya checkpoints). NA-11 implements the comparison |
| 4 | pplx-decider-v1.2's question interaction | No decision now; revisit only if it wins | — |
| 5 | Numeracy / Q5 | Noted for NA-07; no change | — |
| 6 | `state_as_text` for scaledown/classify-1 | **Confirmed** | Unchanged |
| 7 | Merging with parallel worktrees (the cache) | — (information) | `cache/decisions.sqlite` (2,227 responses) and the five `work/MANIFEST.json` entries for `artifacts/NA-05/*` exist only in this worktree; the verifier needs the cache here or copied |
| 8 | Laya head length | — (information) | Unchanged; NA-04's owner decision 2 applies to NA-08 / NA-09 |

**Decision 2 in detail: a change to PRD NA-05 S1.** S1 said "probabilities that do not sum to 1 ± 1e-6 (record as
invalid, not silently fixed)".
- **Rule** (`dm/schemas.py` `_probabilities`):
  - a sum off 1 by at most 1e-6 is accepted as is;
  - a sum off by more than 1e-6 and at most `RENORM_TOL` = 0.0105 is renormalized (p_k / Σp), and the parsed
    answer carries `renormalized = True` and the original `raw_sum`;
  - a larger deviation, or any probability outside [0, 1], stays invalid.
- **Where the flag goes.** The provider's answer is never altered (the cache keeps it raw). The flag travels with
  every materialized answer:
  - `ParsedAnswer.renormalized`;
  - the `renormalized` column of `runner.answers_frame` and of `canary_baseline.parquet`;
  - `runner.derived_frame` `n_renormalized`;
  - the counts in `pilot.json`.
- **Tests:** both sides of the bound (0.0104 / 0.0106 and ±), the flag, the raw sum, the unaltered raw answer, a
  value outside [0, 1], a Jev-style score on a 0.01 grid. Mutations (bound off, bound widened, flag dropped, no
  rescaling) are RED.
- **Recomputed from the cache with no API call** (`python -m newsaction.dm.pilot --stage report --offline`, which
  also skips the key-usage GET; `key_usage.json` is unchanged):
  - Jev 1.14: 19 of 1,509 answers renormalized (1.26%); valid share 98.7% → 100%. Repeat noise mean |Δp| 0.0112,
    mean |ΔN̂| 0.0480 (0.0485 before; 1,680 cells instead of 1,627). Seed 1 vs 2 / the same seed twice 0.0142 /
    0.0128 (0.0148 / 0.0135). Core-question |Δp| with the extended battery 0.0136 (0.0130).
  - Canary baseline: 6,846 rows (6,827), 19 flagged.
  - Smoke models: every rounded answer renormalized (clef 2, clef-flash 4, kev-4b 4, drex-v1.5 2, drex-v2.0 2,
    solar-decide 1 of 10); no invalid answer left in any model.
  - Unchanged: eligibility (only the reasons' wording: "x% of answers renormalized"), the cost calibration, the
    projections, the billing finding, the spend.
- **The cache's `valid` / `problems_json` columns** keep the verdict of the parser that wrote the row (a row is
  written once); every read re-parses with the current parser.

## 10. Spend, look-ahead, deviations, files

**Spend.**
- OpenRouter this chunk $0.103922341; cumulative $0.103922341 (`ledgers/spend.jsonl`, 4,020 lines: one reserve
  and one spend or release per sent call).
- The key's usage at the report was $0.103922341, the same as the ledger (the first snapshot, $0.00006174, is the
  one exploratory Jev call made before the billing stage, which the ledger also holds).
- FMP 0. Kaggle none.
- Network:
  - the catalog and key endpoints (no spend);
  - the Laya checkpoints (~1.7 GB, Hugging Face);
  - Hub metadata reads;
  - three documentation pages (OpenRouter Decisions API reference and Jev guide; the Laya model card).

**Look-ahead self-check.**

| Input | Use | Availability |
|---|---|---|
| `work/states/callA_d0_E3.parquet` train rows (canary 20, billing 2 of them, latency 160) | API and Laya requests | D0 states (W0 news, t−1 context), sessions 2024-07-01 … 2025-06-30; masked; third-party OK |
| `work/states/callB_d2_E3.parquet` train rows (canary 10) | requests | D2 states (W2 news + the session's own reaction), train only |
| synthetic states (codebook words; hand-written news; filler) | requests | no date, no company, no return |
| all state files' sizes (val-A / val-B / test rows: byte counts only) | NA-06 / NA-11 cost projections | the text is not read beyond its length; no return of any period |
| `artifacts/NA-03/call_projection.csv` | call counts | NA-03 projection (no outcome) |

No return, target, label or reaction of any period was read; no val-B or test state was sent anywhere; no sealed
file was opened; `ledgers/test_access.jsonl` is unchanged. Val-B and test rows of the state files were counted for
their byte length only, never sent and never summarized.

**Deviations from PREREG.** None; §15 is unchanged. The operator's decision 2 changes PRD NA-05 S1 (the
probability-sum rule), not PREREG; it is recorded in `docs/decisions/NA-05.md`.

**Files.**
- **Added — code:** `src/newsaction/dm/{__init__, schemas, cache, costmodel, client, catalog, laya_local, parse,
  canary, runner, pilot}.py`.
- **Added — config:** `configs/dm.yaml` (with the operator's `canary` rule).
- **Added — docs:** `docs/decisions/NA-05.md`; `artifacts/NA-05/*` (REPORT, catalog.json, canary_v1.jsonl,
  canary_baseline.parquet, pilot.json, key_usage.json).
- **Changed:**
  - `src/newsaction/io.py`: `register_artifact`;
  - `configs/frozen.yaml`: `free_model_approvals`, `eligible_models`;
  - `docs/DATA_CONTRACT.md`: NA-05 section;
  - `pyproject.toml`: mypy override for `laya.*`;
  - `README.md`: guard row;
  - `ledgers/spend.jsonl`.
- **Tests (10 files, 116 tests):** `tests/test_dm_{schemas, cache, budget, refusals, parse, costmodel, catalog,
  canary, laya_local, runner}.py`, with the shared fakes in `tests/dm_fakes.py`. The slow Laya test loads the
  cached checkpoint; nothing is downloaded in tests.
- **Peak RSS:** billing 0.50 GB, measure 0.99 GB (249 s), smoke 0.51 GB, laya 3.49 GB (181 s), report 1.45 GB.

**`make verify`** (2026-10-26, after the operator's decisions; run when no other pytest was active): exit 0 in
143 s, peak RSS 9.8 GB.
- ruff check "All checks passed!"; ruff format "132 files already formatted";
- mypy --strict "Success: no issues found in 65 source files";
- pytest **1,338 passed, 1 xfailed**: 1,339 collected, of which 116 are the new `test_dm_*` tests and 1,223 main's
  at `214108f`;
- `make manifest` "61 artifacts, 10 inputs checked … OK"; `make ledgers` OK (fmp 0, spend 4,020, test_access 2,
  trials 94).

The first verify after the decisions failed one test: `tests/test_blinding.py` flags any `2026-` month string in
`src/`, docstrings included, and three new docstrings cited the decision's date. They now point to
`docs/decisions/NA-05.md`. The earlier verify (before the decisions) passed with 1,329 tests.
