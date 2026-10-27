# NA-06 REPORT — zero-shot decision-model tournament and contamination probes

Date: 2026-10-26 · Branch `feat/NA-06-tournament` (worktree `NewsAction-NA05`, cut from `main` @ `dd40ca6`; NA-08
ran in parallel in its own worktree) · Decisions: `docs/decisions/NA-06.md` · Artifacts: `artifacts/NA-06/`
(`leaderboard.csv`, `fig3_data.csv`, `probe_details.csv`, `reading_validity.csv`, `stage1_daily_ic.csv`,
`mcs.json`, `dry_run.json`, `spend.json`, `cache_audit.json`, `summary.json`, `counterfactual_edits.jsonl`).

**Result.**
- **Stage 1.** 21 eligible models (19 API + local Laya typed-decisions and base) answered the 700 stage-1 val-A
  D0 states: 14,699 of 14,700 requests.
  - The highest mean daily IC of N̂ with z_cc,t was inception/mercury-decide at 0.099 (t 2.18). Every other model
    had t < 2.
  - **The Model Confidence Set kept all 21 models** (T_R; the first elimination test already has p = 0.61).
  - T_max keeps all 21 too. With 57 sessions of about 12 events each, the daily ICs cannot separate the models.
- **Stage 2** (PREREG §8.3: the 6 highest stage-1 ICs) ran mercury-decide, respan/span-02, liquid/d1-ultra,
  cloudflare/clef, openai/gpt-6-luna-decisions and nace-ai/drex-v2.0 on 3,000 events. The probes ran for the same
  six.
  - On 3,000 events the Call A ICs fall to 0.037–0.071 (t 1.5–2.8). The stage-1 ranking was mostly noise: the
    top 6 of 21 noisy estimates regress toward the mean.
  - IC(J, y2) is negative for all six (−0.018 to −0.037, |t| ≤ 1.4).
  - Call B's N̂ tracks the observed reaction it is shown (IC 0.28–0.63 with z_cc).
- **Screens (PREREG §8.3, applied mechanically): no stage-2 model passes all four.**
  - Company identification fails for all six: 0.63–0.72 of 400 masked states are identified among 4 same-sector,
    same-tier candidates, against the ≤ 0.40 bar.
  - The counterfactual flip rate fails for five (0.53–0.68 < 0.70); drex-v2.0 passes at 0.71.
  - Masked vs unmasked passes for all six. Unmasking lowers the IC for five of them.
  - Shuffled news passes for all six (|t| ≤ 1.3).
  - `configs/frozen.yaml` `tournament.stage2_survivors_passing` is therefore `[]`.
- **Contamination vs skill** (AC5), over the six stage-2 models:
  - contamination score (company-ID accuracy − 0.25) 0.38–0.47;
  - Spearman with the stage-2 IC +0.09 (exact p 0.92); with the stage-1 IC −0.49 (p 0.36).
  - Skill does not track identifiability here, but n = 6.
- **Reading validity** (A2.5, report only; liquid/d1-ultra, the top stage-2 IC, since no model passes).
  Agreement with the references:

  | Label | Agreement | Note |
  |---|---|---|
  | event type vs vendor tag | 0.57 | |
  | quantified | 0.49 | |
  | scheduled vs earnings calendar | 0.55 | all 27 calendar reports found, plus 224 other "scheduled" |
  | rumor vs `tag_rumor` | 0.99 | uninformative: 4 vendor rumors in 500, none called a rumor |

- **Spend:** NA-06 **$3.526622** of the $4.00 cap; cumulative $3.630544 of $30.
  - The ledger equals Σ usage.cost in the cache (difference −2.7e-14) and the key's own usage ($3.63054404).
  - Dry runs projected $3.7675; actual / projected = 0.936 (stage 1 0.923, stage 2 0.940, validity 0.891).
- **Val-B is open:** `allow_val_b: true` was set after every NA-06 call, for NA-07's confirmation and NA-11's
  selection only.

**Owner decisions needed** (§11 below):
1. Every stage-2 model fails the company-identification screen and five fail the flip screen. So NA-07's input
   (PRD NA-07 S1: "the top-3 stage-2 survivors that passed the screens") is empty. NA-11's PREREG §8.5
   candidates shrink to Laya zero-shot, Laya-Fin and the anchor.
2. Credit: $5 − $3.63 = **$1.37 left**, less than NA-07's $2 cap. Please top up before NA-07.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 samples | done | `tournament/sample.py`; `work/dm/tournament/samples.parquet` (3,061 rows), `counterfactual.parquet` (200). Pool: 8,376 val-A D0 events with a Call A state after the embargo (2025-07-09 … 09-30). Stage 1 700 ⊂ stage 2 3,000 (tier × month, seed 2026, NA-04's procedure; nesting asserted). Probe samples: identification 400, reading validity 500, the 1,000 probe events = NA-04's unmasked twins (asserted), counterfactual 200 (139 in stage 2). D2 twins: 3,000 / 3,000 |
| S2 stage 1 | done | 19 API models + 2 local Laya × 700 Call A E3 masked states; dry run $0.8630 (< $1.5); daily IC with z_cc,t and e5, Newey–West t; MCS (`tournament/mcs.py`, HLN T_R, α 0.10, stationary bootstrap over days, block 5, 10,000 reps, seed 2026); every model logged as a trial |
| S3 stage 2 | done | 6 models × (3,000 Call A + 3,000 Call B): IC(N̂_A, z_cc), IC(N̂_A, e5), IC(J, y2), IC(N̂_B, z_cc), ECE (3 classes at ±0.5), cost per 1,000, p50 / p95 latency, invalid rate |
| S4 probes | done | `tournament/probes.py`, `tournament/edits.py`: a company ID (400), b month ID (400), c counterfactual edits (200 pairs), d masked vs unmasked (1,000 twins), e shuffled news (1,000), f reading validity (500, extended battery); screens applied mechanically from `configs/tournament.yaml` (= PREREG §8.3) |
| S5 leaderboard | done | `artifacts/NA-06/leaderboard.csv` (21 models, 87 columns), `fig3_data.csv`, `probe_details.csv`; rank vs contamination in `summary.json` |
| S6 hand-off | done | `configs/frozen.yaml` `tournament` {stage1_survivors (21), stage2_models (6), stage2_survivors_passing ([]), leaderboard_file, leaderboard_sha `a7d1abd8…bf89`, mcs_statistic R}; `allow_val_b: true` written by the `handoff` stage after the last call |

Also: `configs/tournament.yaml` (new); a PREREG §15 row (NA-06, before any answer was read); a README guard row;
DATA_CONTRACT entries for the 5 work files and 11 committed artifacts; the NA-05 cache entry updated.

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 val-A only | `artifacts/NA-06/cache_audit.json`: 65,289 cache rows with `chunk = NA-06`, every one a state-file row (`source = states`, `split = val_a`), sessions **2025-07-09 … 2025-09-30** (after the embargo's last session 2025-07-08), 0 violations; probe rows tagged (company 2,395, month 2,400, counterfactual 1,200, unmasked twin 5,940, shuffled 5,992, reading validity 500); shuffle donors also val-A after the embargo. `tests/test_tournament_audit.py` reads the cache independently (an immutable copy) and checks every row. The client refused val-B and test throughout (`allow_val_b` stayed false until the hand-off) | PASS |
| AC2 leaderboard complete | `leaderboard.csv`: 21 rows = every `include: true` id of `eligible_models`, each with `ic1_z_cc` ± se, t, days, `mcs_pvalue`, `mcs_member`. `tests/test_tournament_mcs.py`: synthetic losses with a known best model → MCS = {best} (R and max); equal models all kept; the best always kept; p-values monotone; identical models indistinguishable; **identical p-values to `arch.bootstrap.MCS` given arch's bootstrap indices** (R and max, 1e-12); the recorded MCS reproduces from `stage1_daily_ic.csv` | PASS |
| AC3 screens mechanical | `tests/test_tournament_screens.py` parses the thresholds out of PREREG §8.3's table, checks `configs/tournament.yaml` against them, tests `probes.screens` at every boundary (0.40 passes, 0.4025 fails; 0.70 / 0.6975; 0.02 or \|t\| < 2; \|t\| 1.99 / 2.0; None and NaN fail), and **recomputes every pass/fail of `probe_details.csv` independently and matches the leaderboard** (6 models × 4 screens + all). Mutation "company-ID threshold 0.90 in code" and "in the config": RED | PASS |
| AC4 budget | Dry runs before every sending stage (`dry_run.json`): stage 1 $0.8630 → actual $0.7968 (0.923); stage 2 + probes $2.8671 → $2.6965 (0.940); validity $0.0374 → $0.0334 (0.891); total $3.7675 → $3.5266 (**0.936**, within ±20%). Per model all within ±20% except cloudflare/clef in stage 1 (1.216; stage 2 1.142): its providers bill above the catalog price (§8). Spend $3.526622 ≤ $4.00; ledger − Σ cache cost = −2.7e-14; key usage = ledger total | PASS |
| AC5 contamination reported | Per-model company-ID accuracy (§6) and Spearman(rank, contamination): stage-2 IC +0.086 (exact p 0.92), stage-1 IC −0.486 (p 0.36), n = 6 (`summary.json`) | PASS |
| AC6 trials | 106 NA-06 lines in `ledgers/trials.jsonl`: stage 1 21 × {ic1_z_cc, ic1_e5}; stage 2 6 × {ic2_a_z_cc, ic2_a_e5, ic2_j_y2, ic2_b_z_cc, ece2_a_z_cc}; probes 6 × {company_id_acc, month_id_acc, flip_rate, unmasked_minus_masked, ic_shuffled}; reading validity 4 agreements. `tests/test_tournament_audit.py::test_one_trial_per_model_stage_metric`: exactly one per (kind, model, metric); a rerun of the report appends none | PASS |
| GAC1 | `make verify` exit 0: ruff "All checks passed!", "148 files already formatted"; mypy --strict "no issues found in 72 source files"; pytest **1,432 passed, 1 xfailed** (213 s); manifest "77 artifacts … OK"; ledgers OK (spend 131,870, trials 200, test_access 2, fmp 0) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (inputs size + mtime); sha256 of `Data/market/earnings_dates.pkl` and `fred_releases.pkl` re-hashed = manifest | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal, no sealed path in `src/`); `ledgers/test_access.jsonl` unchanged (2 NA-01 lines); no test-period state was built, read or sent | PASS |
| GAC4 | NA-06 ledger $3.526621699 vs Σ `responses.cost` (chunk NA-06) $3.526621699: difference −2.7e-14; chunk ≤ $4.00; total $3.630544 ≤ $30 | PASS |
| GAC5 | 16 new manifest entries (5 under `work/dm/tournament/`, 11 under `artifacts/NA-06/`) each with a DATA_CONTRACT entry and the same sha256 (`make manifest`: 77 artifacts OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, cleared `__pycache__` (stale bytecode can hide an equal-length
mutation), ran the named test file and restored the file byte for byte (asserted). **17 / 17 RED**; `git status` was
unchanged afterwards.

| Area | Mutations |
|---|---|
| screens | company threshold hard-coded 0.90 (the verifier's); `company_id_max: 0.90` in the config; shuffled \|t\| ≤ instead of <; a missing value passes; flip threshold ignored |
| MCS | no running maximum of the p-values; block length ignored; the better model of the pair eliminated |
| samples | embargo kept; NA-04 twin check off |
| edits | subject rule off; forward-looking rule off; mixed directions allowed |
| metrics | minimum names per day ignored |
| run | hand-off without the tournament; ties to the dearer model; trials logged twice |

The first pass found one survivor ("a missing value passes": NaN compares false anyway); a test with None values
now kills it.

## 3. Stage 1 (700 val-A D0 events; Call A, core battery, E3, masked)

Mean daily Spearman IC (57 sessions with ≥ 5 events), Newey–West t (5 lags). Cost is the realized USD per 1,000
Call A requests; latency is per request at concurrency 16 (Laya: local, sequential, MPS shared with NA-08).

| # | Model | $/M | billing | IC z_cc ± se | t | IC e5 | t | MCS p | $/1,000 A | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | inception/mercury-decide **(S2)** | 0.020 | once | 0.099 ± 0.046 | 2.18 | 0.083 | 2.35 | 1.000 | 0.0234 | 408 / 747 |
| 2 | respan/span-02 **(S2)** | 0.010 | per_question | 0.091 ± 0.052 | 1.74 | 0.087 | 2.17 | 0.986 | 0.0311 | 2178 / 2329 |
| 3 | liquid/d1-ultra **(S2)** | 0.042 | once | 0.085 ± 0.052 | 1.65 | 0.107 | 2.31 | 0.986 | 0.0422 | 234 / 343 |
| 4 | cloudflare/clef **(S2)** | 0.042 | once | 0.082 ± 0.042 | 1.93 | 0.064 | 1.93 | 0.986 | 0.0676 | 347 / 549 |
| 5 | openai/gpt-6-luna-decisions **(S2)** | 0.100 | once | 0.081 ± 0.050 | 1.64 | 0.083 | 1.82 | 0.986 | 0.1142 | 203 / 386 |
| 6 | nace-ai/drex-v2.0 **(S2)** | 0.060 | once | 0.080 ± 0.053 | 1.51 | 0.066 | 1.40 | 0.986 | 0.0491 | 741 / 1299 |
| 7 | perplexity/pplx-decider-v1.2 | 0.020 | once | 0.070 ± 0.046 | 1.53 | 0.108 | 2.76 | 0.986 | 0.0191 | 262 / 517 |
| 8 | cloudflare/clef-omni | 0.150 | once | 0.062 ± 0.037 | 1.69 | 0.055 | 1.71 | 0.946 | 0.1796 | 220 / 372 |
| 9 | microsoft/microsoft-decision-1 | 0.042 | once | 0.062 ± 0.039 | 1.58 | 0.070 | 1.63 | 0.946 | 0.0338 | 352 / 478 |
| 10 | cloudflare/clef-flash | 0.019 | once | 0.059 ± 0.045 | 1.33 | 0.053 | 1.30 | 0.946 | 0.0263 | 300 / 844 |
| 11 | nace-ai/drex-max | 0.060 | once | 0.057 ± 0.037 | 1.55 | 0.105 | 3.35 | 0.954 | 0.0677 | 533 / 899 |
| 12 | perplexity/pplx-decider-flash-v1.2 | 0.010 | per_question | 0.057 ± 0.041 | 1.37 | 0.066 | 1.63 | 0.908 | 0.0289 | 227 / 372 |
| 13 | liquid/d1 | 0.020 | once | 0.054 ± 0.046 | 1.16 | 0.064 | 1.98 | 0.772 | 0.0201 | 302 / 423 |
| 14 | typesafe/jev-1.14 | 0.042 | once | 0.050 ± 0.039 | 1.28 | 0.100 | 2.69 | 0.837 | 0.0573 | 185 / 261 |
| 15 | typesafe/jev-1.13 | 0.042 | once | 0.043 ± 0.040 | 1.08 | 0.102 | 2.59 | 0.682 | 0.0573 | 184 / 245 |
| 16 | local/laya-base | 0.000 | local | 0.042 ± 0.030 | 1.37 | -0.008 | -0.21 | 0.946 | 0.0000 | 921 / 1199 |
| 17 | local/laya-typed-decisions | 0.000 | local | 0.037 ± 0.043 | 0.86 | 0.026 | 0.72 | 0.953 | 0.0000 | 898 / 1175 |
| 18 | togethercomputer/tev1-4b-experimental | 0.042 | per_question | 0.034 ± 0.053 | 0.65 | 0.025 | 0.49 | 0.885 | 0.1157 | 736 / 908 |
| 19 | jaredpalmer/kev-4b | 0.042 | once | 0.034 ± 0.050 | 0.68 | 0.048 | 1.11 | 0.642 | 0.0344 | 658 / 1193 |
| 20 | nace-ai/drex-v1.5 | 0.040 | once | 0.021 ± 0.054 | 0.39 | 0.057 | 1.23 | 0.777 | 0.0328 | 327 / 946 |
| 21 | scaledown/classify-1 | 0.040 | per_question | 0.014 ± 0.032 | 0.43 | 0.055 | 1.57 | 0.612 | 0.1377 | 1206 / 2884 |

- Every answer of the chunk parsed as valid (0 invalid of 65,289). One luna request was refused for good in stage 1
  ("OpenAI refused to answer question justified_move", HTTP 502 on 5 attempts × 3 passes); it is missing, not
  imputed.
- One build per model throughout (e.g. mercury-decide-20260930, d1-ultra-20261015, gpt-6-luna-decisions-20261006;
  clef and clef-flash report no dated build). clef was served by three providers (PrimeIntellect 8,405, DeepInfra
  388, Cloudflare 257 calls), clef-flash by three and kev-4b by two: their answers are not from one deployment.
- Both Laya checkpoints rank 16–17, as expected zero-shot; their value comes from NA-08's fine-tuning.

## 4. Model Confidence Set

- **Configuration:** T_R on loss = −daily IC, over the 57 sessions every model has; stationary bootstrap (block 5,
  10,000 reps, seed 2026).
- **Result: no model is eliminated.** The first test (all 21 models) has p = 0.612, so the MCS p-values run from
  0.612 (classify-1) to 1.000 (mercury-decide). T_max also keeps all 21 (`mcs.json` `robustness_other_statistic`).
- **Stage-2 choice:** with 21 survivors, stage 2 took the six highest stage-1 ICs (PREREG §8.3). No exact tie
  arose. The 6th, drex-v2.0 (0.0799), and the 7th, pplx-decider-v1.2 (0.0704), are 0.2 se apart.
- **Verifier rerun:** `python -m newsaction.tournament.mcs --seed 7` reruns the MCS from
  `stage1_daily_ic.csv` with another seed.

## 5. Stage 2 (3,000 val-A D0 events; Call B on their 3,000 D2 twins)

| Model | IC(N̂_A, z_cc) | IC(N̂_A, e5) | IC(J, y2) | IC(N̂_B, z_cc) | ECE z_cc / E5^lvl | $/1,000 A / B | p50 / p95 ms | failed |
|---|---|---|---|---|---|---|---|---|
| inception/mercury-decide | 0.050 (t 2.33) | 0.043 (t 1.22) | −0.021 (t −1.09) | 0.276 (t 11.4) | 0.336 / 0.305 | 0.0236 / 0.0250 | 422 / 729 | 0 |
| respan/span-02 | 0.063 (t 2.53) | 0.037 (t 1.58) | −0.020 (t −0.96) | 0.629 (t 27.9) | 0.330 / 0.354 | 0.0315 / 0.0278 | 2157 / 2295 | 0 |
| liquid/d1-ultra | 0.071 (t 2.83) | 0.036 (t 1.81) | −0.029 (t −1.21) | 0.591 (t 40.0) | 0.230 / 0.226 | 0.0426 / 0.0479 | 243 / 453 | 0 |
| cloudflare/clef | 0.037 (t 1.52) | 0.024 (t 0.90) | −0.018 (t −0.88) | 0.539 (t 31.4) | 0.241 / 0.222 | 0.0667 / 0.0683 | 345 / 464 | 0 |
| openai/gpt-6-luna-decisions | 0.045 (t 2.28) | 0.035 (t 1.35) | −0.037 (t −1.38) | 0.633 (t 41.6) | 0.289 / 0.366 | 0.1150 / 0.1199 | 204 / 390 | 4 |
| nace-ai/drex-v2.0 | 0.062 (t 2.64) | 0.024 (t 1.37) | −0.024 (t −1.24) | 0.345 (t 12.8) | 0.217 / 0.162 | 0.0497 / 0.0583 | 691 / 1039 | 0 |

- Daily ICs over the 59 stage-2 sessions; e5 misses the last 4 val-A sessions and y2 the last 5 (purged by the
  panel, so no val-B return is read).
- **ECE** is the top-label ECE (15 bins) of Q1 collapsed to fall / no move / rise against the realized class at
  ±0.5: z_cc,t, or E5^lvl, the horizon Q1 names. Before any temperature fitting.
- **IC(N̂_B, z_cc):** Call B's N̂ is strongly tied to the reaction it is shown. That is NA-07's anchoring question
  (PREREG §8.4).
- **Failures:** luna's 4 failed Call A / B requests (and 7 of its probe requests) are the same stable OpenAI
  refusal. No answer of any model was invalid.
- **Cost:** per 1,000 decisions (Call A, core battery), cheapest first among the six: mercury $0.024, span-02
  $0.032 (per-question billing), d1-ultra $0.043, drex-v2.0 $0.050, clef $0.067, luna $0.115.

## 6. Probes and screens (PREREG §8.3; `probe_details.csv`)

| Model | company ID (P true) | month ID | flip rate (pairs; mean shift) | IC masked / unmasked | unmasked − masked (t) | shuffled IC (t) | screens a / c / d / e | all |
|---|---|---|---|---|---|---|---|---|
| inception/mercury-decide | 0.627 (0.60) | 0.200 | 0.562 (169; +1.14) | 0.061 / 0.045 | −0.016 (−1.01) | −0.044 (−1.28) | **fail** / **fail** / pass / pass | **fail** |
| respan/span-02 | 0.660 (0.62) | 0.113 | 0.645 (169; +1.36) | 0.054 / 0.039 | −0.015 (−0.80) | −0.002 (−0.06) | **fail** / **fail** / pass / pass | **fail** |
| liquid/d1-ultra | 0.720 (0.66) | 0.595 | 0.678 (177; +1.09) | 0.072 / 0.063 | −0.009 (−0.43) | +0.021 (0.60) | **fail** / **fail** / pass / pass | **fail** |
| cloudflare/clef | 0.690 (0.60) | 0.470 | 0.529 (155; +0.80) | 0.025 / 0.010 | −0.015 (−1.07) | −0.022 (−0.70) | **fail** / **fail** / pass / pass | **fail** |
| openai/gpt-6-luna-decisions | 0.704 (0.65) | 0.507 | 0.568 (148; +0.92) | 0.076 / 0.051 | −0.025 (−0.98) | +0.021 (0.82) | **fail** / **fail** / pass / pass | **fail** |
| nace-ai/drex-v2.0 | 0.667 (0.54) | 0.188 | 0.710 (162; +1.02) | 0.065 / 0.074 | +0.008 (0.48) | −0.000 (−0.01) | **fail** / pass / pass / pass | **fail** |

- **a. Company identification** (400 events; chance 0.25; contamination score = accuracy − 0.25 = 0.38–0.47).
  - **Not a design artifact:**
    - the true candidate's position is spread evenly (87 / 106 / 100 / 107 over the four keys);
    - models lean a little toward `candidate_1`;
    - accuracy is high in every tier: 0.57–0.71 Mid, 0.61–0.70 Rest, 0.68–0.76 Top-100.
  - **Distractors:** 394 events drew all three from the same sector and tier, and 6 by nearest size rank.
  - **Reading:** masked states describe products, deals, customers and executives' roles. NA-04's verifier judged
    about half of states identifiable by content. Every model picks the right company among same-sector,
    same-tier peers about two times in three.
  - **Not outcome recall:** probes d and e show no sign of it. Unmasking the names lowers the IC for five of six,
    and news from another event gives an IC of zero.
- **b. Month identification** (report only; chance 0.25): 0.11–0.60.
  - d1-ultra, luna and clef pick a val-A month (Jul–Sep 2025) for 84%, 67% and 67% of the states. Masked states
    carry no dates, so this is timing from content or knowledge.
  - mercury, span-02 and drex-v2.0 are below chance: they favour 2024 months.
- **c. Counterfactual edits** (200 pairs; 148–177 with |N̂_orig| ≥ 0.25).
  - Every model moves N̂ the right way on average: +0.80 to +1.36 typical daily moves against the original
    direction.
  - Only 53–71% of the pairs change sign. The rule edits only the outcome phrase; other cues ("strong demand",
    "record performance") remain by design.
  - Edit families in the 200 pairs: beat 168 edits, rating 77 (+ 37 ladders), guidance 29, price-target
    companions 22, expectations 4. Polarity: 157 positive, 43 negative originals.
- **d. Masked vs unmasked** (1,000 twins, 59 sessions): unmasked − masked is −0.025 to +0.008, every |t| < 1.1.
  All pass.
- **e. Shuffled news** (1,000 events): mean daily IC −0.044 to +0.021, |t| ≤ 1.28. All pass. The news carries the
  stage-2 signal; the context blocks alone do not.

## 7. Reading validity (probe f; PREREG A2.5, report only)

liquid/d1-ultra (the highest stage-2 Call A IC; no model passed the screens) answered core + extended on the 500
events in one request each. The main article was matched for 500 / 500. Confusion tables are in
`reading_validity.csv`.

- **Event type vs vendor `tag_type`** (mapped): agreement 0.572.
  - Earnings results agree best: 161 of the 272 earnings-tagged items.
  - Most of the rest of the earnings-tagged items are called "other" (45), "analyst action" (22) or "sector or
    macro" (20). The vendor's earnings tag also covers previews and commentary.
- **Quantified vs `tag_quantified`:** 0.494. The model calls 233 of the 382 vendor-"numbers" items narrative.
- **Scheduled vs NA-04's earnings-in-W0 flag:** 0.552. Recall is 27 of 27, but the model calls 251 items
  scheduled: earnings coverage outside the W0 report window too.
- **Credibility = rumor vs `tag_rumor`:** 0.990, a base-rate number. 4 vendor rumors, none called a rumor; one
  rumor call, not a vendor rumor.

## 8. Spend, projections and realized cost ratios

| Stage | projected | actual | actual / projected |
|---|---|---|---|
| stage 1 (19 API models × 700; Laya free) | $0.8630 | $0.7968 | 0.923 |
| stage 2 + probes a–e (6 models; 50,101 requests) | $2.8671 | $2.6965 | 0.940 |
| reading validity (d1-ultra, 500) | $0.0374 | $0.0334 | 0.891 |
| **total** | **$3.7675** | **$3.5266** | **0.936** |

Realized cost ratio = Σ usage.cost ÷ Σ (catalog price × input tokens) per model:
- **1.000 for every model except two:**
  - cloudflare/clef: **1.284**, and one call at 5.71× the catalog price;
  - cloudflare/clef-flash: **1.152**, max 2.00×.
- **Consequence for clef:** its actual cost was 1.22× (stage 1) and 1.14× (stage 2) its projection, against
  about 0.90× for the others. The cost model's 1.1 safety factor, with ratio 1.0, under-projects clef.
- **This is the NA-05 verifier's routing finding, now measured** on 9,050 clef and 700 clef-flash calls (§3
  lists the providers). `configs/dm.yaml` was not changed. A later chunk that projects clef should use a ratio
  ≥ 1.3.

By model: luna $1.018, clef $0.581, drex-v2.0 $0.467, d1-ultra $0.427, span-02 $0.256, mercury $0.210; the 13
stage-1-only API models together $0.567. Retries: 916 × 429 (drex-v2.0 on DeepInfra), 198 × 502 (luna 180,
mercury 17, span-02 1), 1 × 503; all retried except luna's 12 refusals. Failed attempts are not billed (NA-05): the
key's usage equals the ledger.

## 9. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| `work/states/callA_d0_E3.parquet` val-A rows (sessions 2025-07-09 … 09-30) | stage 1/2 Call A; probes a, b, c (edited), e (recipient and donor news); f | D0 states: W0 news (≤ 09:15 ET of the session), t−1 context; masked; third-party OK (all) |
| `work/states/callB_d2_E3.parquet` val-A rows | stage 2 Call B | D2 states: W2 news + the session's own reaction (after close(s)); used only at D2 |
| `work/states/samples/unmasked.parquet` (1,000 val-A) | probe d | as Call A D0, unmasked, sent only under `unmasked_twin` |
| `work/events/events_d0.parquet` (keys, tier, month, embargo; `news_w0` ids for probe f) | samples, main-article match | `w0` / t−1 tier; ids only |
| `work/panel/panel_public.parquet` val-A rows: sector, tier, rank (members of the session) | probe a candidates | `static` sector, `t_minus_1` tier and rank |
| `work/panel/panel_public.parquet` val-A rows: z_cc, e5, e5_lvl, y2 | evaluation targets only, never a model input | `post` (targets; purged by split, so no val-B return enters) |
| `work/news/articles_clean.parquet` `tag_type`, `tag_quantified`, `tag_rumor`; `work/states/articles_masked.parquet` | probe f references only | `selection_only` vendor labels (CLAUDE.md A6): compared with the answers, never sent |
| `work/states/context_company.parquet` `ctx_earnings_w0` | probe f reference | `w0` |
| `work/panel/companies.parquet` names | probe a option texts | `static` (the names are in the question, the state stays masked) |

No val-B or test state was sent, and no val-B or test return was read. `allow_val_b` was false for every NA-06
call and the client would have refused one. No sealed file was opened, and `ledgers/test_access.jsonl` is
unchanged.

## 10. Deviations from PREREG

One row appended to §15 (2026-10-26, NA-06, "Before"; written before any NA-06 answer was read). It records the
operationalizations §8.2–8.3, §11.1–11.2 and A2.5 leave open:
- the sample procedure;
- the daily-IC minimum of 5 events and constant days = 0;
- the MCS statistic and set rule;
- same-sector, same-tier company candidates (GICS industry is unavailable);
- the edit rules (PRD's raised↔lowered and PREREG's raise↔cut both used);
- the shuffled-news design, the ECE definition and the reading-validity references.

No earlier section was edited.

## 11. STOP conditions and owner decisions

**STOP conditions (PREREG §13).**
- "Any projection exceeds the remaining budget": **not fired**.
  - Stage 1 projected $0.863 < the $1.5 limit (PRD S2) and < the $4.00 left.
  - Stage 2 projected $2.867 < $3.203 left.
  - Validity projected $0.037 < $0.507 left.
- "Billed per question": the known NA-05 STOP. respan/span-02 (per question) reached stage 2 under the operator's
  decision (a). If it ever becomes the primary instrument, §13's reduced battery applies.
- "Winner priced above $0.12/M": for NA-11.

**Owner decisions.**
1. **No stage-2 model passes the screens.**
   - **What failed:** company identification fails for all six (0.63–0.72 vs ≤ 0.40), and the flip rate for five
     (0.53–0.68 vs ≥ 0.70).
   - **What it blocks:** PREREG §8.5's candidates for NA-11 become Laya zero-shot + Laya-Fin + the anchor, and
     NA-07's model set (PRD NA-07 S1, "top-3 stage-2 survivors that passed the screens") is empty.
   - **What NA-06 did:** applied the screens mechanically and changed nothing.
   - **What the evidence says:** probes d and e give no sign of outcome memorisation. Unmasking does not help and
     shuffled news gives nothing. Company identification measures how identifiable the masked content is (NA-04
     accepted residue, PREREG §15 rows of 2026-10-25/26).
   - **Options (any change to §8.3 or §8.5 is a PREREG deviation before the freeze):**
     - **(a)** Keep the result: no zero-shot API model is a headline instrument; the paper's API results are
       reported as model-specific (§1.3), and NA-07 runs on Laya only, or not at all.
     - **(b)** Run NA-07 and NA-11 with the top-3 stage-2 models by IC, labelled "screen-failing". Every claim
       from them is then model-specific (§1.3), with the anchor and Laya-Fin as the clean comparators.
     - **(c)** Amend the identification screen before the freeze (for example, require the identification to
       predict returns, or tighten the distractors), and rerun probe a only (about $0.1).
2. **Top-up:** $1.37 credit is left, less than NA-07's $2 cap.
3. **clef's cost:** routing makes clef 1.28× its catalog price (max 5.7× per call). Any later projection of clef
   should carry a cost ratio ≥ 1.3, or clef should be dropped from paid runs.
4. **luna's refusals:** OpenAI refuses `justified_move` for 12 of 9,051 luna requests (0.13%), for good. They are
   missing answers. If luna is ever used in production, these states need a rule (missing or Laya fallback).
5. **Ledger size (information):** `ledgers/spend.jsonl` grew from 4,020 to 131,870 lines (46 MB). The client
   writes one reserve and one spend line per call.
   - NA-11's roughly 140,000 calls would take the file past GitHub's 100 MB per-file limit, if the repository is
     ever pushed.
   - Options: batch-level reservations in `dm.client`, or git LFS for `ledgers/`.
   - NA-06 did not change the ledger protocol.

## 12. Files, tests and run records

**Code (new):** `src/newsaction/tournament/{__init__, sample, metrics, mcs, edits, probes, run}.py`.

**Config (new):** `configs/tournament.yaml`. **Changed:**
- `configs/frozen.yaml`: `tournament`, `allow_val_b: true`;
- `docs/PREREG.md`: one §15 row;
- `docs/DATA_CONTRACT.md`: the NA-06 section and the cache entry;
- `README.md`: guard row;
- `ledgers/{spend,trials}.jsonl`;
- `tests/test_configs_match_prereg.py`: the frozen skeleton now allows NA-06's section, with val-B open only once
  it is recorded;
- `tests/test_dm_refusals.py`: the val-B refusal test sets the gate closed itself, since the repository's gate is
  now open.

**Tests (new, 9 files, 94 tests):** `tests/test_tournament_{config, sample, metrics, mcs, edits, probes, screens,
audit, run}.py`.

**Work files:** `work/dm/tournament/{samples, counterfactual, stage1, stage2, probes}.parquet`. The full
counterfactual states (masked NewsWitch text) stay in `work/`; the committed jsonl has no article text.

**Run records** (one stage per process):

| Stage | Wall time | Peak RSS |
|---|---|---|
| samples | 5 s | 0.64 GB |
| stage 1 | 1,788 s (Laya 2 × 645 s on MPS shared with NA-08) | 3.10 GB |
| select | — | 0.77 GB |
| stage 2 | 2,169 s | 1.79 GB |
| validity | 12 s | 1.13 GB |
| report | 20 s | 2.36 GB |
| `make verify` | 220 s | 10.7 GB |

- **Reproducibility:** the report reproduces every registered file byte for byte on a rerun and appends no trial.
- **Verification commands:** `python -m newsaction.tournament.run --stage report` rebuilds everything offline;
  `python -m newsaction.tournament.mcs --seed N` reruns the MCS.
