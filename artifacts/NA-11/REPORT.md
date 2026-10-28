# NA-11 REPORT — final selection, freeze, production

Date: 2026-10-28 · Branch `feat/NA-11-freeze-production` (main checkout) · Decisions: `docs/decisions/NA-11.md`
· PREREG: §15 holds ten NA-11 rows written before the freeze and two after it (the S5 STOP decision; the
price-only D2 timing) · Numbers: the `artifacts/NA-11/*.csv|json` files named below.

**Frozen.** `artifacts/NA-11/freeze.json`: hash `523e7589d1bd551c715d03b2c285a4875a4770050f75712a585db7decae73a7c`
at 2026-10-28T10:38:58Z over PREREG before its Deviations log, every `configs/*.yaml`, `panel/targets.py`,
`panel/reactions.py` and `analysis/{spec,inference,shapley,metrics}.py`. Annotated tag `prereg-freeze` →
`3751d8e` (the freeze commit). The hash is unchanged at the end of the chunk.

**Primary instrument: Laya-Fin** (`laya-s13`), selected on val-B (§8.5): daily IC 0.0647 (NW t 3.64) against
Laya zero-shot 0.0295 and the anchor −0.0199. d1-ultra (the "best API comparator"), span-02 and drex-v2.0 ran
as screen-failing, model-specific comparators (§1.3).

**STOPs.** S5's canary fired for respan/span-02 (0.0366 against its repeat noise 0.0344); the operator decided to
proceed (post-freeze §15 row, with the evidence and the end-of-S6 rule). At the end of S6 the canary fired for
d1-ultra and span-02 and the drift check for neither, every build unchanged: noise under the recorded rule, no
STOP (§3.4). Both S7 kernels completed; each reloaded checkpoint reproduces NA-08's val-A predictions exactly.

**Blinding.** No 2026 outcome statistic was computed, printed or looked at. Every 2026 price or bar was read
through `newsaction.lock` with purpose "reactions", after the freeze (10 entries, all allowed; no "targets"
entry). No numeric 2026 reaction is written to disk: the S4 states carry reactions as codebook words, and the
price-only D0 predictions use z_vol(t−1) as a model input only. Every probe and selection number here is val-A or
val-B.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 analysis spec | done | `src/newsaction/analysis/{spec,inference,shapley,metrics,frames}.py`, `configs/analysis.yaml`; synthetic tests; val-B smoke `artifacts/NA-11/spec_smoke_val_b.json` |
| S2 final selection | done | `production/select_final.py`; `artifacts/NA-11/final_selection.csv`; `configs/frozen.yaml` `selection`, `thresholds`, `calibration`, `strategy` |
| S3 freeze | done | `production/freeze.py`, `lock.freeze`; `artifacts/NA-11/freeze.json`; commit `3751d8e`, tag `prereg-freeze` |
| S4 2026 reaction states | done | `production/states_test.py`; `work/states/callB_{d2,d1}_E3_test.parquet` |
| S5 canary | done (STOP for span-02; operator: proceed) | `production/canary_check.py`; `artifacts/NA-11/canary_{baseline_na11.parquet,drift_na06.csv,check.csv}` |
| S6 production | done (one retry pass of transient failures, operator) | `production/run.py`; `work/dm/production/*_api_comparators_market.parquet`; `production_runs_api_comparators_market.json`, `production_retry.json`; end of S6: `canary_end_s6.json`, `canary_drift_check.csv` |
| S7 trained-model inference | done (2 kernels, 2.00 GPU-h of the 2.39 projected) | `production/kaggle_infer.py`, `train/notebook/infer_ddp.py`, `train/infer_nbbuild.py`, `notebook/newsaction_infer.ipynb`; private dataset `amirdehkordi98/newsaction-na11-infer`; `work/kaggle/predictions/{laya_fin,anchor}_{test_callB,val_callB_d1,robustness_callA,probes}.parquet`; `kaggle_import_*.json` |
| S8 ablations, LLM baseline, price-only | done; price-only D2 moved to NA-12 (operator; §15 row) | `production/{ablations,llm_test,price_only_test}.py`; `ablation_runs.json`, `llm_test.json` |
| S9 summary | done | `production/summary.py`; `artifacts/NA-11/production_summary.csv`, `production_spend.csv` |
| Operator additions | done | option (iv) company identification (`company_id.py`); H1b; the val-A probes and their descriptive additions (`probes.py`, `probes_val_a.csv`); the live-format residue count; the canary design |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 order | `python -m newsaction.production.freeze evidence`: the freeze (10:38:58.45Z) precedes the first cache row with a 2026 state (11:12:01Z, local Laya test) and the first "reactions" entry of `ledgers/test_access.jsonl` (10:43:59Z); `spec.py` and `targets.py` (with `reactions.py`, `inference.py`, `shapley.py`, `metrics.py`) are hashed; `prereg-freeze` is an annotated tag on `3751d8e`; `hash_now` equals the record. `tests/test_freeze_order.py` | PASS |
| AC2 spec tested | `tests/test_spec_synthetic.py`: planted b > 0 and c < 0 recovered (H2); a planted Shapley interaction (`test_shapley.py`); a convergence path with κ_h rising to 1 and a known half-life; H1 and H1b planted effects recovered, null rejection near 5% (20 replications). The val-B smoke run passes, A1 ladder included (plateau equal to `targets.py`'s `car_lvl_c20`, max difference 0). `configs/frozen.yaml` holds the A1.3 V maps (val-A fit range 2025-07-09…2025-09-24) and the A1.6 S-CONV parameters, written before the freeze | PASS |
| AC3 coverage | `production_summary.csv`: Laya-Fin has valid outputs for **100%** of its eligible events on every call and split (Call A D0 and D2, Call B D2 and D1; val-A, val-B, test, 2024-H1). The API comparators reach 100% after the retry pass (market 271 of 273) | PASS |
| AC4 canary | Pre-production (S5, repeat 10): d1-ultra 0.0176 < 0.0203; drex-v2.0 max \|Δp\| 0 < 0.02; **span-02 0.0366 > 0.0344: STOP recorded**, operator decision in the post-freeze §15 row | STOP recorded, resolved by the operator |
| AC5 budget | NA-11 spend **$10.82** ≤ $18; cumulative **$15.73** ≤ $30 (`ledgers/spend.jsonl`); `reconcile` 5e-13 after S6 and after the end-of-S6 canary. Dry runs: S6 $10.852 projected, $9.229 spent (−15%, the retry pass included); ablations $1.548 / $1.412 (−9%); the LLM baseline $0.153 / $0.040 (NA-09's chat cost model prices every answer at `max_tokens`, on purpose) | PASS |
| AC6 no targets | `ledgers/test_access.jsonl`: 0 "targets" entries; `load_targets` is never called in `src/newsaction/production` (grep) | PASS |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; nothing written under `Data/` | PASS |
| GAC3 | Only "reactions" accesses, all after the freeze (10 entries; §3.2); `tests/test_blinding.py` passes | PASS |
| GAC4 | Every API call through `dm.client` (cache, ledger, caps, `data_collection: deny`); spend in §4 | PASS |
| GAC5 | 47 NA-11 files in `docs/DATA_CONTRACT.md` with their sha256 (the freeze record included); `python -m newsaction.io check` OK | PASS |

### 2.1 Mutations

A session script applied each mutation, cleared `__pycache__`, ran the guard's tests, restored the file and
checked its sha256 (`git status` clean afterwards; the freeze hash unchanged).

| Mutation | File | Result |
|---|---|---|
| the freeze hash leaves out `metrics.py` | lock.py | RED |
| `read_instrument` accepts any runs | train/import_preds.py | RED |
| Call B admits test events without `allow_test` | states/build.py | RED |
| the freeze check ignores cached test states | production/freeze.py | RED |
| H1b tests the wrong direction | analysis/spec.py | RED |
| the ablation rebuild check ignores differences | production/ablations.py | RED |
| the LLM test sends above its cap | production/llm_test.py | RED |
| end-of-S6 judge: one firing check counts as an update | production/canary_check.py | RED |
| `price_only_test` imports LightGBM at import time | production/price_only_test.py | RED |
| the inference program reads a label column | train/notebook/infer_ddp.py | RED |

## 3. Numbers

### 3.1 Final selection (S2)

5,506 val-B D0 events that every candidate answered, 59 sessions (`final_selection.csv`):

| Model | Daily IC | NW t | 95% CI | Role |
|---|---|---|---|---|
| Laya-Fin (`laya-s13`) | 0.0647 | 3.64 | 0.030 – 0.100 | **primary** |
| Laya zero-shot | 0.0295 | 1.94 | 0.001 – 0.056 | candidate |
| anchor (`anchor-s13`) | −0.0199 | −1.52 | −0.044 – 0.003 | candidate |
| d1-ultra (NA-07's 1,500-event sample) | 0.0630 | 3.14 | | comparator |
| span-02 (NA-07's sample) | 0.0773 | 3.25 | | comparator |
| drex-v2.0 (NA-07's sample) | 0.0439 | 1.55 | | comparator |

Company identification with activity-matched distractors (option (iv); `company_id_matched.csv`): no-reading
baseline 0.283 (NA-06's design 0.359); d1-ultra 0.74, drex-v2.0 0.68, luna 0.68, span-02 0.66, clef 0.66,
mercury 0.62; Laya zero-shot 0.32.

### 3.2 Freeze and order (S3)

| Event | Time (UTC) |
|---|---|
| freeze record (`freeze.json`, `git_sha` f8f3b4c), commit `3751d8e`, tag `prereg-freeze` | 10:38:58 |
| first "reactions" access (S4: `prices_raw_2026`, `total_return_check_2026`) | 10:43:59 |
| first cache row with a 2026 state (local Laya, test Call A) | 11:12:01 |
| S6 start | 11:33 |

The 10 accesses: S4 at D2 (2), S4 at D1 (6: `bars30_2026`, prices and the total-return check, twice), the
price-only D0 step (2). All purpose "reactions", all allowed.

### 3.3 2026 reaction states (S4)

`callB_d2_E3_test`: 18,625 states, each equal to its Call A D2 twin except `reaction_so_far` (asserted).
`callB_d1_E3_test`: 13,977 states; 593 have no D1 reaction (rendered "not available"). Longest state 874 tokens,
as in the validation builds. Live-format residue (`spec.live_format`) in the test Call A D0 states: 24 of
13,977, all "… Stock Market Today" titles (train 3, val-A 8, val-B 5).

### 3.4 Canary (S5 and the end of S6)

| Model | Repeat noise (4 baseline repeats) | S5 canary (r10) | End-of-S6 canary (r11) | Drift vs NA-06, pre-freeze / end of S6 | Builds | End-of-S6 verdict |
|---|---|---|---|---|---|---|
| d1-ultra | 0.0203 (0.0198–0.0209) | 0.0176 | **0.0212 (fires)** | 0.0191 / 0.0194 | d1-ultra-20261015 throughout | noise |
| span-02 | 0.0344 (0.0305–0.0386) | **0.0366 (fires: STOP)** | **0.0399 (fires)** | 0.0224 / 0.0250 | span-02-20261015 throughout | noise |
| drex-v2.0 (deterministic) | 0 | 0 | 0 | 0 / 0 | drex-v2.0-20261009 throughout | pass |

The rule (post-freeze §15 row, recorded before the end-of-S6 run): a noisy model counts as updated only if its
build string changed or both checks fire; otherwise a firing is noise and the results stand; a deterministic
firing or an update is a STOP. Every S6 answer carries the pre-freeze builds. Both end-of-S6 canary values sit
slightly above their own four baseline repeats; the drift checks stay at their pre-freeze levels. As recorded, a
noisy model passes a mean-noise threshold only about half the time. span-02's results carry a footnote to the
post-freeze §15 row in every model-comparison table.

### 3.5 Production (S6)

d1-ultra on the full plan (core + extended on Call A, core + explain on Call B), span-02 and drex-v2.0 on core
Call A D0; 13,188 s at concurrency 16. 1,226 requests failed on the first pass: 1,223 with 429, one with 502
and the 2 market rows without a recorded status; no refusal and no invalid answer. The one retry pass (operator
decision) re-sent the 1,224 transient ones at concurrency 8: all answered and valid (73 through the cache,
identical states of another component).

| Model | Reading | val-A | val-B | test | 2024-H1 | Valid | Cost of the answers |
|---|---|---|---|---|---|---|---|
| d1-ultra | a0 (Call A D0) | 8,906 | 6,035 | 13,977 | | 100% | $1.88 |
| d1-ultra | a2 (Call A D2) | 11,148 | 7,828 | 18,625 | | 100% | $2.50 |
| d1-ultra | b2 (Call B D2) | 11,148 | 7,828 | 18,625 | | 100% | $2.09 |
| d1-ultra | b1 (Call B D1) | 8,906 | 6,035 | 13,977 | | 100% | $1.57 |
| d1-ultra | a0 / a2 2024-H1 | | | | 2,793 / 3,887 | 100% | $0.11 / $0.16 |
| d1-ultra | market (A3.5) | 64 | 64 | 145 | | 271 of 273 | $0.01 |
| span-02 | a0 | | 6,035 | 13,977 | | 100% | $0.57 |
| drex-v2.0 | a0 | | 6,035 | 13,977 | | 100% | $0.91 |

The 2 market failures were not re-sent: the S6 run's market rows carry no HTTP status (`market_readings`
records it since). Costs include cached answers paid by earlier chunks; the spend is in §4.

### 3.6 Trained models on Kaggle (S7)

Private dataset `amirdehkordi98/newsaction-na11-infer` (5 files, 110,146 rows per model, masked third-party-OK
states, no label column), downloaded back and equal to the local manifest byte for byte. Two private
inference-only kernels on GPU T4 ×2 (the training kernel's `ckpt/` as source, NA-08's `train_ddp.py` unchanged):

| Run | Rows | GPU time | Record | val-A check (500 rows) |
|---|---|---|---|---|
| laya-s13 (Laya-Fin) | 110,146 | 3,793 s (projected 1.20 h) | trained false, hub_push false, labels_read false, no state cut, temperatures = NA-08's | max \|Δp\| **0.0** |
| anchor-s13 (anchor) | 110,146 | 3,265 s (projected 1.20 h) | the same flags; temperatures = NA-08's (`cont` at NA-08's cap of 20) | max \|Δp\| **0.0** |

The import (`kaggle_infer.import_run`) verified each output's sha256, the record, the program and dataset
sha256s and probabilities = softmax(logits / T). Kaggle GPU quota: 23.38 h used before S7, 25.38 h after (30 h,
reset 2026-10-31): S7 used 2.00 GPU-h.

### 3.7 Laya zero-shot (local) and the val-A probes

Test Call A D0, core battery: 13,977 readings, all valid (2.57 h on this machine; nothing sent anywhere).

The operator's disclosed val-A probes (`probes_val_a.csv`; not hypotheses; the descriptive columns right_way,
shift_sd and the real-news IC were added after the freeze, and the frozen screen verdicts stay as computed).
Every row is computed from the model's own readings; for the API models the recomputed NA-06 values equal
NA-06's leaderboard (to 1e-9) and the screen verdicts are copied from it.

| Model | Flip rate (pairs) | right_way | shift_sd (t) | IC real, same events (t) | IC shuffled (t) | Real − shuffled (t) | Unmasked − masked (t) |
|---|---|---|---|---|---|---|---|
| mercury-decide | 0.562 (169) | 0.995 | 1.40 (19.0) | 0.061 (2.07) | −0.044 (−1.28) | 0.106 (2.81) | −0.016 (−1.01) |
| span-02 | 0.645 (169) | 0.990 | 1.61 (20.8) | 0.054 (1.21) | −0.002 (−0.06) | 0.056 (0.98) | −0.015 (−0.80) |
| d1-ultra | 0.678 (177) | 0.985 | 1.83 (21.6) | 0.072 (1.69) | 0.021 (0.60) | 0.051 (1.03) | −0.009 (−0.43) |
| clef | 0.529 (155) | 0.980 | 1.24 (19.7) | 0.025 (0.71) | −0.022 (−0.70) | 0.047 (1.09) | −0.015 (−1.07) |
| gpt-6-luna | 0.568 (148) | 0.950 | 1.47 (17.6) | 0.076 (2.31)¹ | 0.021 (0.82) | 0.056 (1.46) | −0.025 (−0.98) |
| drex-v2.0 | 0.710 (162) | 0.985 | 1.59 (22.2) | 0.065 (1.45) | −0.000 (−0.01) | 0.066 (1.16) | 0.008 (0.48) |
| Laya zero-shot | 0.043 (92) | 0.940 | 0.41 (11.2) | 0.051 (1.52) | 0.002 (0.05) | 0.048 (1.29) | −0.013 (−0.51) |
| **Laya-Fin** | 0.000 (8) | 0.800 | 0.20 (7.35) | 0.050 (1.60) | 0.031 (0.90) | 0.019 (0.47) | — |
| anchor | — (0)² | 0.435 | 0.0002 (0.18) | 0.055 (1.44) | 0.043 (1.05) | 0.011 (0.94) | — |

¹ 997 events (three real-news readings invalid); every other row uses the 1,000 events.
² The anchor's val-A N̂ has an SD of 0.006: no original reaches 0.25, and its N̂ moves by 1.2e-6 on average
under the edits (no sign changes).
right_way: the share of the 200 edit pairs whose N̂ moves the way the edit points (NA-06's polarity).
shift_sd: NA-06's edit_mean_shift over the SD of the model's own val-A Call A D0 N̂ (API: NA-06 stage 2; Laya
zero-shot: NA-09's val-A file; Laya-Fin and the anchor: NA-08's val-A predictions); t: one-sample t of the
signed per-pair shift over the 200 pairs. NA-06's screens: flip rate
≥ 0.70, unmasked − masked ≤ 0.02, shuffled-news t < 2. **The frozen flip screen counts only pairs with
|N̂_orig| ≥ 0.25, which is 2.4 SD of Laya-Fin's N̂ (SD 0.105), so 8 of its 200 pairs qualify**; on every pair
its N̂ moves the way the edit points 80% of the time, against 95–99.5% for the API models.

### 3.8 Ablations, LLM baseline and price-only (S8)

- **Ablations** (d1-ultra, core battery; `ablation_runs.json`, `work/dm/production/liquid_d1_ultra_ablations.parquet`).
  12,000 events per base, split × tier × month, the smallest u = sha256("2026:ablation:<id>") per stratum, outside
  the embargo: Call B D2 (val-A 3,497, val-B 2,385, test 6,118) and Call A D0 (3,639 / 2,390 / 5,971). The
  unmasked twins come from NA-04's builder on the articles each masked state kept: the masked rebuild equals
  NA-04's state for all 12,000, and the 439 sampled NA-04 twins come out unchanged.

  | Ablation | Valid | Failed (all 429) | Cost |
  |---|---|---|---|
  | b2_no_news (Call B D2 without `news`) | 11,965 | 35 | $0.39 |
  | b2_shuffled (another event's `news`, same split, another company) | 11,882 | 118 | $0.54 |
  | a0_unmasked (probe tag `unmasked_robustness`) | 11,943 | 57 | $0.50 |

  The 210 failed requests were not retried (the retry decision covered S6).
- **LLM baseline** (mistralai/mistral-nemo, NA-09's prompt and settings; 2,000 test D0 events, tier × month):
  2,000 answered, **1,977 valid** (23 invalid), $0.040.
- **Price-only D0** (NA-09's saved boosters): 13,977 test events; the same code reproduces NA-09's 14,941
  val-A and val-B D0 predictions exactly (max difference 0). Missing features (LightGBM's missing branch):
  momentum 110, σ regime 246, z_vol(t−1) 3.
- **Price-only D2: moved to NA-12** (operator; post-freeze §15 row, timing only); §7.1.

### 3.9 Summary (S9)

`production_summary.csv` (61 rows): every model, reading and split with eligible events, answers, validity,
coverage, invalid rate, latency and cost. Coverage: Laya-Fin and the anchor 100% everywhere; d1-ultra, span-02
and drex-v2.0 100% after the retry (market 99.3%); Laya zero-shot test 100%; LLM baseline 98.9% valid of 2,000;
price-only D0 100%; ablations 97.2–99.96% per split. No API answer was invalid; the LLM baseline's 23 invalid
answers are its only invalid rate (1.15%). Latency p50/p95 per API reading are in the file.

## 4. Spend

OpenRouter (`ledgers/spend.jsonl`; `production_spend.csv` per model and purpose): **NA-11 $10.82** — production
(S6 with its retry) $9.229 (d1-ultra $7.855, drex-v2.0 $0.843, span-02 $0.530), ablations $1.412, company
identification $0.076, canary and drift checks $0.064, LLM baseline $0.040. **Cumulative $15.73** (NA-05 $0.10,
NA-06 $3.53, NA-07 $1.24, NA-09 $0.04, NA-11 $10.82) of the $30 cap. The account was read before and after every
paid batch (`key_usage.json`). FMP: none. Kaggle: 2.00 GPU-h of the 2.39 projected (laya-s13 1.05 h, anchor-s13
0.91 h, plus setup).

## 5. Look-ahead self-check

| Input | Availability |
|---|---|
| Call A D0 states (NA-04): W0 news, context of t−1 | 09:15 ET of session t |
| Call A D2 states (NA-04): W2 news | after close(t), before open(t+1) |
| Call B D2 test states (S4): `reaction_so_far` from the lock's D2 reactions | after close(t) |
| Call B D1 test states (S4): the first 30-minute bar | 10:00 ET of t |
| Market states (A3.5) | after close(t) |
| Ablation states: Call B D2 without news or with another event's news (same split); unmasked Call A D0 | as their bases |
| Price-only D0: context of t−1; z_vol of session t−1 (`react_z_vol` of t−1 through the lock) | close(t−1) |
| LLM baseline: Call A D0 states | 09:15 ET |
| Trained-model inference: the same states, NA-08's frozen checkpoints and val-A temperatures | as the states |
| Canary items (train period), drift states (val-A), probes (val-A) | before 2026 |
| Calibration maps (val-A fit, range stored), confidence gates (val-A 70th percentile), selection (val-B) | before the freeze |

No 2026 target was read (no "targets" access).

## 6. Deviations from PREREG

All in §15 (Deviations log), each with its reason:

- Before the freeze (10 rows): the spec's operationalization; the extended freeze hash; the seed-13 pin; the
  final selection and the frozen sections; option (iv); the live-format residue count; H1b; the production plan
  (best API comparator, question groups, gated S-D1 not run, the probes); the §11.6 items not run (the 08:00
  cutoff approximated); the canary design.
- After the freeze (2 rows): the S5 STOP decision for span-02 with the end-of-S6 rule; the price-only D2 test
  predictions moved to NA-12 (timing only).
- Within the frozen plan, reported here: the one retry pass of S6's transient failures (operator); the probe
  table's descriptive additions (operator).

## 7. STOP conditions and owner decisions

| Condition | Fired | Decision |
|---|---|---|
| S5 canary | span-02 | operator: proceed (post-freeze §15 row) |
| End-of-S6 canary and drift re-check | canary for d1-ultra and span-02, drift for none, builds unchanged | noise under the recorded rule; results stand |
| A projection above the cap or the balance | no (largest: S6 $10.85 against $17.88 left) | — |
| Kaggle GPU-hours | no: 2.00 h used of 2.39 projected; 4.62 h left before the reset | operator approved the push |
| A kernel fails | no | — |

Owner decision open: a retry pass for the S8 ablations' 210 rate-limited requests (≈ $0.01).

### 7.1 Hand-off to NA-12

1. **First step after unblinding, before any analysis: the price-only D2 test predictions** (post-freeze §15
   row). NA-09's booster `work/baselines/models/price_only_y2.json` and `baselines.price_only.D2_FEATURES` are
   fixed; the code must first reproduce NA-09's val-A and val-B D2 predictions exactly, as
   `production.price_only_test.check` does at D0.
2. span-02's results carry a footnote to the post-freeze §15 row (the S5 STOP and the decision).
3. The trained instruments are the seed-13 pins; seeds 17/23 and repro-s13 after the 2026-10-31 reset are seed
   robustness only (separate `*_seeds_*` files).
4. **The anchor's readings are uninformative; report them as such, not as a null.** Its direction outputs are
   nearly constant: Call A N̂ SD 0.006 on val-A (Laya-Fin 0.105), Call B react N̂ SD 0.005–0.009 on val-A and
   val-B at D2 and D1 (Laya-Fin 0.65–0.76); its cont head is uniform (temperature at NA-08's bound 20; every
   probability within 0.0008 of 1/3). Its direction, H2 and continuation readings therefore carry almost no
   information, and its edits barely move N̂ (right_way 0.435, mean shift 1.2e-6, t 0.18).
5. The API readings, the trained instruments' NA-11 files, Laya zero-shot's test file, the S8 files and the
   probe table are in `docs/DATA_CONTRACT.md` (NA-11 section); `analysis.frames` joins them.

## 8. Files

**Code (new).** `src/newsaction/analysis/` — `spec.py`, `inference.py`, `shapley.py`, `metrics.py` (hashed),
`frames.py`; `src/newsaction/production/` — `select_final.py`, `smoke_spec.py`, `company_id.py`, `freeze.py`,
`plan.py`, `states_test.py`, `canary_check.py`, `run.py`, `laya_local.py`, `kaggle_infer.py`, `ablations.py`,
`llm_test.py`, `price_only_test.py`, `probes.py`, `summary.py`, `contract.py`; `src/newsaction/train/infer_nbbuild.py`,
`src/newsaction/train/notebook/{infer_ddp.py,newsaction_infer.ipynb}`.
**Code (changed).** `lock.py` (FREEZE_FILES), `train/import_preds.py` (the pin), `train/cards.py`,
`states/build.py` (`allow_test`; a purpose-tagged sampler seed).
**Configs.** `configs/analysis.yaml`, `configs/production.yaml` (new, hashed); `configs/frozen.yaml` (selection,
thresholds, calibration, strategy, frozen); `configs/dm.yaml` (drex-v2.0 deterministic).
**Docs.** `docs/PREREG.md` (12 §15 rows), `docs/DATA_CONTRACT.md` (NA-11 section, 47 files),
`docs/decisions/NA-11.md`, this report.
**Artifacts** (`artifacts/NA-11/`). `final_selection.csv`, `company_id_matched.csv`, `spec_smoke_val_b.json`,
`freeze.json`, `canary_baseline_na11.parquet`, `canary_drift_na06.csv`, `canary_check.csv`,
`canary_drift_check.csv`, `canary_end_s6.json`, `production_runs_api_comparators_market.json`,
`production_retry.json`, `kaggle_import_{laya-s13,anchor-s13}.json`, `ablation_runs.json`, `llm_test.json`,
`probes_val_a.csv`, `production_summary.csv`, `production_spend.csv`, `key_usage.json`.
**Work files** (registered). `work/analysis/state_articles_w2.parquet`; `work/states/callB_{d2,d1}_E3_test.parquet`,
`work/states/samples/unmasked_robustness.parquet`; `work/dm/production/` (the S6 readings per model, Laya
zero-shot test and probes, company identification, the S8 files); `work/kaggle/dataset_na11/*`,
`work/kaggle/predictions/{laya_fin,anchor}_{test_callB,val_callB_d1,robustness_callA,probes}.parquet`.
**Ledgers.** `ledgers/spend.jsonl`, `test_access.jsonl` (10 "reactions" entries), `trials.jsonl`.
**Tests (new).** `test_analysis_config`, `test_analysis_metrics`, `test_inference`, `test_shapley`,
`test_spec_functions`, `test_spec_synthetic` (with `spec_fakes.py`), `test_select_final_rule`,
`test_company_id_matched`, `test_freeze_order`, `test_frozen_instruments`, `test_kaggle_infer`,
`test_production_s8`. **Changed:** `conftest.py` (pre-freeze throwaway layouts), `test_lock`,
`test_configs_match_prereg`, `test_states_outputs`.

## 9. `make verify`

Run after the last change (no other NewsAction pytest running; 76% memory free), exit 0:

```
ruff check src tests scripts       All checks passed!
ruff format --check                244 files already formatted
mypy --strict src/                 Success: no issues found in 129 source files
pytest -q -m "not network"         1876 passed, 3 skipped, 2 xfailed in 286.03s
manifest                           193 artifacts, 10 inputs checked: OK
```

Two problems the suite caught during the chunk, both fixed: the S8 tests loaded LightGBM into the pytest
process, which then segfaulted in the live Laya test (torch; NA-09's known conflict), and the lock's tests broke
after the real freeze because their throwaway repository copied a frozen `configs/frozen.yaml`.
`tests/test_blinding.py` also caught a 2026 date in a contract description (the freeze time), reworded.
