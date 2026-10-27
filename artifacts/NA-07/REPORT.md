# NA-07 REPORT — encoding ("numbers as words") and anchoring study

Date: 2026-10-27 · Branch `feat/NA-07-encoding` (worktree `NewsAction-NA05`, cut from `main` @ `7bc114b`; NA-08,
NA-09 and NA-10 ran in parallel in their own worktrees) · Decisions: `docs/decisions/NA-07.md` · Artifacts:
`artifacts/NA-07/` (`encoding_ic.csv`, `encoding_daily_ic.csv`, `encoding_check.csv`, `numeracy.csv`,
`numeracy_series.csv`, `anchoring.csv`, `selection.json`, `dry_run.json`, `key_usage.json`, `spend.json`,
`cache_audit.json`, `summary.json`).

**The chosen encoding is E3. NA-08's E3 training stands; no retrain is needed.**

**Model set.** liquid/d1-ultra, respan/span-02 and nace-ai/drex-v2.0. These are the operator's three: the
stage-2 models with the highest stage-2 Call A IC (PREREG §15 row of 2026-10-27). All three **fail NA-06's
screens**, so every number below is model-specific (§1.3).

## Result

- **Encoding: E3** (`frozen.yaml` `encoding.chosen`).
  - **Val-A search (S1).** By the PREREG §8.4 rule (mean rank over the three models), the best encoding is
    **E1** (σ-numbers, "+2.3σ"): mean ranks E1 1.67, E0 3.0, E4 3.0, E2 3.67, E3 3.67. The differences are
    small next to their noise: ICs 0.063–0.085, bootstrap SEs 0.023–0.036. Each model prefers a different
    encoding (d1-ultra E1, span-02 E2, drex-v2.0 E0).
  - **Val-B check (S2).** E1 is worse than E3 by more than 1 SE: Δ = IC(E1) − IC(E3) = **−0.0110**, bootstrap
    SE 0.0046 (t −2.33, 59 sessions). The rule therefore returns **E3**. E1 is worse for all three models on
    val-B (−0.005, −0.014, −0.014).
- **Numeracy (S3, E3): fails for every model.** The monotone shares are **0.17** (d1-ultra, the leading model),
  0.08 (span-02) and 0.07 (drex-v2.0), against the 0.90 target.
  - On average the models do read the size: mean P(too large) rises and P(too small) falls with |z|, and
    Spearman(J, |z|) runs from −0.42 to −0.89.
  - Single series are not monotone. 65–80% of adjacent steps are in order, and the 6 → 9 step (both
    "extreme") breaks 53–72% of series.
  - E3 is kept: it is the val-B rule's result, and also PRD S3's fallback. The numeracy gate (PREREG §15 NA-07
    row) applies only to a non-E3 encoding.
- **Anchoring (S4): present → `calls_per_event = 2`** (N̂ from Call A).
  - respan/span-02 anchors on both counts: slope of N̂_B on G (N̂_A control) **0.349** ≥ 0.30, and
    corr(N̂_A, N̂_B) **0.651** < 0.70.
  - d1-ultra (slope 0.166, corr 0.747) and drex-v2.0 (0.090, 0.855) do not cross the thresholds.
  - Every slope is far from 0 (session-clustered SEs 0.008–0.017), so all three move N̂ toward the reaction
    they are shown; only span-02 moves it past the pre-registered threshold.
  - The pre-registered combination is "any model", so anchoring is present.
- **Spend:**
  - NA-07 spent **$1.240485** of its $2.00 cap.
  - Actual / projected = 0.902; every part is within ±20% (0.90–0.91).
  - The ledger equals Σ cache cost (difference 4e-15).
  - Account credit fell from $11.37 to **$10.13**.
- **Data scope:** search on val-A; val-B used only for the S2 check (9,000 requests, the only val-B rows). No
  test state and no 2026 value.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 encoding study (val-A) | done | 3 models × E0–E4 × NA-04's 1,500 val-A sample (Call A, core battery, masked): 22,500 requests (4,500 E3 answers from NA-06's cache, 18,000 sent). Mean daily IC of N̂ vs z_cc,t with Newey–West t and stationary block-bootstrap SE / 95% CI (block 5, 10,000 reps, seed 2026). Rule: lowest mean rank, ties → E3 (`encoding/study.py`; `encoding_ic.csv`, `encoding_daily_ic.csv`, `selection.json`) |
| S2 confirmation (val-B) | done | The same 3 models on the 1,500 val-B sample in {E1, E3}: 9,000 requests. Pooled Δ with bootstrap SE; rule "keep best unless worse than E3 by > 1 SE" → E3 (`encoding_check.csv`) |
| S3 numeracy probe | done | `encoding/numeracy.py`: 30 real masked val-A Call B states (company, market, attention and news blocks kept) × synthetic `reaction_so_far` at 7 magnitudes (±0.3 … ±9, NA-05's grid) × 2 directions, in E3: 1,260 requests. Monotone share per model (`numeracy.csv`, `numeracy_series.csv`) |
| S4 anchoring | done | `encoding/anchoring.py`: the 1,500 val-A D2 twins; Call A on D2 (W2 news only, 3,756 sent, 744 cached) vs Call B (NA-06's cached answers). The two states differ only in `reaction_so_far` (asserted). OLS slope with N̂_A control, HC1 and clustered SEs; corr (`anchoring.csv`) |
| S5 hand-off | done | `configs/frozen.yaml`: `encoding` {chosen E3, by_model, val_a_best E1, val_a_table_sha, val_b_check, val_b_kept, numeracy_gate, models, model_specific}; `anchoring` {present true, slope 0.3487, corr 0.6506, calls_per_event 2, by_model, table_sha}. Trials: 21 encoding + 3 numeracy + 3 anchoring |

Also:
- `configs/encoding.yaml` (new);
- two PREREG §15 rows (NA-07), the first written before any NA-07 answer was read and the second before any
  val-B or numeracy answer;
- a README guard row;
- the DATA_CONTRACT NA-07 section and the cache entry.

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 numeracy | `numeracy.csv`: d1-ultra (leading) 0.167, span-02 0.083, drex-v2.0 0.067 in E3, the chosen encoding; target 0.90. Reported per model. The REPORT documents why E3 is kept (Result; §5): the val-B rule chose E3; numeracy fails in E3 as NA-05's pilot predicted; and PRD S3's rule for a failing model is "prefer E3", which E3 already is. `tests/test_numeracy_scoring.py` re-scores every series and recomputes the shares | PASS (via the documented-E3 branch) |
| AC2 rules mechanical | `tests/test_encoding_rule.py::test_encoding_choice_recomputed_from_the_csvs_matches_frozen` recomputes the val-A choice (E1), the val-B check (E3) and the numeracy gate from the CSVs with PREREG-parsed numbers, then matches `frozen.yaml` and the table sha. `tests/test_anchoring_rule.py::test_anchoring_csv_recomputed_matches_frozen` does the same for anchoring (present, 2). Mutations (scratch copy): anchoring slope threshold 0.9 in code → `test_rule_boundaries[0.3-0.95-True]` RED; `slope_min: 0.90` in the config → `test_rule_thresholds_are_prereg` RED; corr threshold 0.9 in code → `test_rule_boundaries[0.1-0.8-False]` RED | PASS |
| AC3 data scope | `cache_audit.json`: 32,016 NA-07 cache rows (s1 18,000 val-A, s2 9,000 val-B, s3 1,260 val-A, s4 3,756 val-A) and 41,760 used requests (NA-06-paid included), 0 outside their part's split and session range (val-A 2025-07-09 … 09-30, val-B 2025-10-08 … 12-31). `run.targets` refuses val-B targets unless `allow_val_b` and the val-A best ≠ E3 (`tests/test_encoding_run.py`). `ledgers/test_access.jsonl` unchanged | PASS |
| AC4 budget | NA-07 $1.240485 ≤ $2.00. Dry run vs actual: S1 0.900, S2 0.906, S3 0.914, S4 0.899, total 0.902 (all within ±20%). Ledger − Σ cache cost = 4.4e-15. The key's usage rose $1.242716 over NA-07 ($0.002231 more than the ledger, not NA-07's: §7) | PASS |
| AC5 trials | `ledgers/trials.jsonl` NA-07: `na07_encoding` 21 = 3 models × (5 encodings × val-A + 2 encodings × val-B); `na07_numeracy` 3 (3 models × E3 × val-A); `na07_anchoring` 3 (3 models × E3 × val-A) | PASS |

`make verify`: ruff and format clean, `mypy --strict` clean (77 files), **1,478 passed, 1 xfailed**, manifest OK
(94 artifacts), ledgers OK.

## 3. S1 — encoding search (val-A, 1,500 events, 59 sessions)

Mean daily IC of N̂ vs z_cc,t (t) [bootstrap 95% CI]; rank within the model.

| Model | E0 | E1 | E2 | E3 | E4 |
|---|---|---|---|---|---|
| liquid/d1-ultra | 0.076 (2.29) [0.003, 0.141] · 4 | **0.081** (3.11) [0.024, 0.131] · 1 | 0.066 (2.14) [−0.001, 0.127] · 5 | 0.080 (2.68) [0.014, 0.138] · 2 | 0.079 (2.64) [0.012, 0.139] · 3 |
| respan/span-02 | 0.065 (2.56) [0.013, 0.113] · 4 | 0.069 (2.72) [0.017, 0.116] · 2 | **0.069** (2.71) [0.016, 0.120] · 1 | 0.063 (2.79) [0.017, 0.108] · 5 | 0.068 (2.61) [0.013, 0.118] · 3 |
| nace-ai/drex-v2.0 | **0.085** (3.65) [0.037, 0.131] · 1 | 0.074 (3.07) [0.024, 0.122] · 2 | 0.070 (3.07) [0.023, 0.115] · 5 | 0.071 (2.66) [0.017, 0.123] · 4 | 0.073 (2.46) [0.016, 0.127] · 3 |
| **mean rank** | 3.00 | **1.67** | 3.67 | 3.67 | 3.00 |
| mean IC | 0.075 | 0.074 | 0.068 | 0.071 | 0.073 |

- Every answer is valid (1,500 / 1,500 per cell).
- The E3 cells are NA-06's cached answers on the same states.
- The within-model spreads (0.007–0.015) are well below one bootstrap SE (0.023–0.036). On val-A the encodings
  cannot be told apart; the rule still has to pick one, and it picked E1 with no tie.

## 4. S2 — confirmation (val-B, 1,500 events, 59 sessions)

| Model | IC E1 (t) | IC E3 (t) | Δ = E1 − E3 | boot SE | 95% CI |
|---|---|---|---|---|---|
| liquid/d1-ultra | 0.058 (2.53) | 0.063 (3.14) | −0.0048 | 0.0090 | [−0.020, 0.014] |
| respan/span-02 | 0.063 (2.58) | 0.077 (3.25) | −0.0145 | 0.0081 | [−0.030, 0.002] |
| nace-ai/drex-v2.0 | 0.030 (1.01) | 0.044 (1.55) | −0.0138 | 0.0096 | [−0.033, 0.005] |
| **pooled** (per-session mean over models) | | | **−0.0110** | **0.0046** | [−0.020, −0.002] |

- **Rule:** keep E1 iff Δ ≥ −1·SE = −0.0046. Δ = −0.0110, so **E3** (`encoding_check.csv`).
- Pooling three models' paired daily differences halves the SE relative to a single model.
- Val-A's preference for E1 does not replicate: E3 is ahead for every model on val-B.

## 5. S3 — numeracy (outcome-free, E3)

60 series per model (30 real val-A news blocks × rise / fall), each over 7 magnitudes (0.3, 0.7, 1.5, 2.5, 4, 6,
9 typical daily moves: negligible … extreme).

| Model | monotone share | L non-decreasing | S non-increasing | step rate (exploratory) | share without the 6 → 9 step (exploratory) |
|---|---|---|---|---|---|
| liquid/d1-ultra (leading) | **0.167** | 0.467 | 0.217 | 0.800 | 0.483 |
| respan/span-02 | **0.083** | 0.317 | 0.117 | 0.703 | 0.183 |
| nace-ai/drex-v2.0 | **0.067** | 0.150 | 0.067 | 0.653 | 0.233 |

- **All three are below the 0.90 target.** By PRD S3 the models mis-read the reaction words: their Q5
  probabilities do not move monotonically with the stated size, event by event.
- **What the average shows** (descriptive, `work/dm/encoding/numeracy.parquet`):
  - **d1-ultra:** mean P(too large) rises from 0.04–0.07 at |z| 0.3 to 0.67–0.75 at 9, and mean
    P(too small) falls from 0.38–0.42 to 0.02–0.04. Its J tracks size (Spearman(J, |z|) −0.87 / −0.89).
  - **span-02:** similar in size, with a large P(wrong direction) for falls (0.25–0.44 from |z| 0.7 up).
  - **drex-v2.0:** nearly flat. P(too small) stays at 0.39–0.57 even for an "extreme" move.
- **Reading:** the failures come from event-level noise and saturation at the top of the scale (the 6 → 9 step
  breaks 53–72% of series), and for drex from a weak response to size. Large moves are not read as small ones
  on average.
- **Consequence for NA-11:** J from these comparators is a noisy event-level signal. This is a property of the
  models, not of E3: NA-05's pilot found no model monotone, and no other encoding was probed (the gate applies
  only to a non-E3 encoding).
- **AC1:** E3 is kept, and this table documents why. The "prefer E3 for that model" rule (PRD S3) is already
  satisfied for all three; `frozen.yaml` `encoding.by_model` is E3 for every model.
- **Design note:** the non-reaction blocks of the 30 states keep their real E3 words, since NA-04 built Call B
  in E3 only. Only `reaction_so_far` is synthetic: S&P 500 +0.1, volume "busy", "by the close" (NA-05's canary
  values).

## 6. S4 — anchoring (val-A D2, 1,500 events per model)

| Model | slope b (HC1 SE; clustered SE) | c (N̂_A) | R² | corr(N̂_A, N̂_B) | Spearman | slope without control | anchors? |
|---|---|---|---|---|---|---|---|
| liquid/d1-ultra | 0.166 (0.009; 0.009) | 0.609 | 0.845 | 0.747 | 0.739 | 0.198 | no |
| respan/span-02 | **0.349** (0.016; 0.017) | 0.648 | 0.824 | **0.651** | 0.675 | 0.392 | **yes** (both conditions) |
| nace-ai/drex-v2.0 | 0.090 (0.008; 0.008) | 0.766 | 0.801 | 0.855 | 0.849 | 0.132 | no |
| **all** (largest slope, smallest corr) | 0.349 | | | 0.651 | | | **present → 2 calls per event** |

- Call A (D2) and Call B see the same W2 news and context; only `reaction_so_far` differs. The differences
  between N̂_A and N̂_B are therefore the reaction's effect, plus the models' own answer noise.
- The verdict rests on span-02. Under the pre-registered "any" combination, present.
- Even the two models below the thresholds shift N̂ toward G with a clustered t of 11–19.
- **For production (NA-11):** N̂ always comes from Call A, with two calls per event; NA-11's budget already
  assumes this. The primary instrument will be a Laya model (§8.5 after NA-06's screens), whose anchoring
  NA-07 did not measure. Two calls is the conservative default for it as well.

## 7. Spend, projections and credit

| Part | requests sent (cached) | projected | actual | actual / projected |
|---|---|---|---|---|
| S1 search (val-A) | 18,000 (4,500) | $0.7709 | $0.6940 | 0.900 |
| S4 anchoring (val-A) | 3,756 (5,244) | $0.1807 | $0.1625 | 0.899 |
| S2 confirm (val-B) | 9,000 (0) | $0.3602 | $0.3263 | 0.906 |
| S3 numeracy | 1,260 (0) | $0.0630 | $0.0576 | 0.914 |
| **total** | **32,016** | **$1.3748** | **$1.2405** | **0.902** |

- **Plan:**
  - the `dryrun` stage projected $1.4026 for the worst case (S2 and S3 at their most expensive encoding),
    under the $2.00 cap and the $11.37 credit;
  - each paid stage repeated the projection and checked the account's credit (`/api/v1/credits`) before its
    first call: not fired.
- **By model:** drex-v2.0 $0.499, d1-ultra $0.433, span-02 $0.308. The cost ratio (usage.cost ÷ catalog price ×
  tokens) is 1.000 for all three. span-02's per-question billing is in the cost model.
- **Retries:** 1,284 × 429 from drex-v2.0 on DeepInfra, all retried. One S2 request exhausted its 5 attempts
  ("Model busy") and was sent again in pass 2.
- **Ledger** (this worktree): NA-07 $1.240485; cumulative $4.871029 of $30 (NA-05 $0.103922, NA-06 $3.526622,
  NA-07 $1.240485).
- **Key usage:**
  - The account's usage rose $1.242716 between the dry run and the final snapshot. That is $0.002231 more than
    NA-07's ledger, while NA-07's cache holds every NA-07 cost (difference 4e-15). The excess is presumably
    NA-09's, since it shares the key.
  - Earlier snapshots lagged the ledger by $0.01–0.04, because the key endpoint updates with a delay.
  - Credit left: **$10.13 of $15.00**.
- **FMP:** 0 requests.

## 8. Look-ahead self-check

| Input | Available at | Used for |
|---|---|---|
| Call A D0 states E0–E4 (NA-04 samples; W0 news to 09:15 ET, context through t−1) | 09:15 ET of `session` | S1, S2 requests |
| Call A D2 states (`callA_d2_E3`; W2 news to close(s), context through t−1) | close of `session` | S4 Call A |
| Call B D2 states (`callB_d2_E3`; the same plus the D2 reaction: z_cc,t words, S&P 500 move, volume) | after close of `session` | S4 Call B; S3 non-reaction blocks |
| Synthetic `reaction_so_far` (codebook words of fixed z) | n/a (no data) | S3 |
| z_cc,t (panel_public; σ_cc through t−1) | close of `session` | evaluation only (IC targets; G of S4, the value Call B was shown) |
| NA-06 leaderboard (val-A) | NA-06 | the model choice |

- No input is later than its decision point, and no target enters a state.
- Every session is in val-A (2025-07-09 … 09-30) or val-B (2025-10-08 … 12-31). No 2026 session was read or
  sent, and `ledgers/test_access.jsonl` is unchanged.
- Val-B targets were read only by the S2 check, after the val-A selection was written (`selection.json`, 10:55
  UTC; the first val-B call came at 10:56).

## 9. Deviations from PREREG (all logged in §15, "Before")

1. **NA-07 operationalization,** written before any NA-07 answer was read:
   - the models;
   - the pooled mean-rank rule and its tie order;
   - the pooled val-B Δ and its bootstrap SE;
   - the numeracy design (NA-05's grid; synthetic reaction block; strict monotonicity, tolerance 1e-9);
   - anchoring on D2 Call A vs Call B, combined over models by "any";
   - the trial records.
2. **Numeracy gate and E3 reference,** written after the val-A selection (E1) and before any val-B or numeracy
   answer:
   - a non-E3 encoding is kept for a model only if its monotone share is ≥ 0.90;
   - `chosen` follows the leading model (PRD AC1);
   - an E3 reference run is added, report-only.

   It did not apply: the val-B check kept E3.
3. **PRD S1 "survivors that passed the screens" → the operator's three screen-failing models:** the operator's
   §15 row of 2026-10-27, already on main.

## 10. STOP conditions and owner decisions

**STOP conditions.**
- "Any projection exceeds the remaining budget" (PREREG §13): not fired. The worst case was $1.40 against $2.00
  and $11.37 of credit; each stage was checked again before its first call.
- "Billed per question": span-02, the known NA-05 STOP under decision (a). It is included in every projection.
- "The chosen encoding is not E3" (preamble 5): not fired (E3).

**Owner decisions / information.**
1. **Numeracy fails for all three models in E3** (0.07–0.17 vs 0.90). Nothing in §8.4 changes: E3 is kept.
   - Any H2 / RG / J result from these comparators should carry the caveat that their reaction-adequacy
     answers are not monotone in the stated size at the event level, even though they are on average.
   - Probing Laya zero-shot and Laya-Fin the same way (local, $0) before NA-11 would show whether the primary
     instrument reads the words better. This is not in NA-07's scope.
2. **Anchoring is decided by respan/span-02 alone** under the pre-registered "any" rule; d1-ultra alone would
   have allowed one call. `calls_per_event = 2` holds for production. NA-07 did not measure Laya's anchoring.
3. **Key usage vs ledger:** the account's usage exceeds NA-07's ledger by $0.002231, presumably NA-09 on the
   shared key. This is for the merge-time reconciliation across worktrees.
4. **Ledger size:** `ledgers/spend.jsonl` is 68.8 MB (195,904 lines, +64,034 in NA-07). NA-11's ~140,000 calls
   would take it past GitHub's 100 MB per-file limit (NA-06 owner decision 5).

## 11. Files, tests and run records

**Code (new):** `src/newsaction/encoding/{__init__, study, numeracy, anchoring, run}.py`.
**Code (changed):** `src/newsaction/tournament/__init__.py` (`log_trial` takes `chunk=`; NA-06's calls are
unchanged).
**Config:** `configs/encoding.yaml` (new); `configs/frozen.yaml` (`encoding`, `anchoring`).
**Docs:**
- `docs/PREREG.md` (two §15 rows);
- `docs/DATA_CONTRACT.md` (the NA-07 section and the cache entry);
- `docs/decisions/NA-07.md`;
- `README.md` (guard row).

**Tests (new, 5 files, 46 tests):**
- `tests/test_encoding_config.py` (PREREG / PRD numbers, the operator's models, NA-05's grid);
- `tests/test_encoding_rule.py` (pooling, ties, val-B boundary, bootstrap, model choice; recomputation vs
  `frozen.yaml`);
- `tests/test_numeracy_scoring.py` (monotonicity, synthetic blocks in E0–E4, the gate; recomputation);
- `tests/test_anchoring_rule.py` (PREREG thresholds at the boundaries, combination, OLS vs lstsq;
  recomputation);
- `tests/test_encoding_run.py` (val-B target refusal, parts and splits, the frozen writer, sample and twin
  invariants, numeracy states, the audit, no targets in work files).

**Tests (changed):** `tests/test_configs_match_prereg.py` (the frozen skeleton accepts NA-07's sections).

**Work files** (`work/dm/encoding/`): `samples.parquet` (3,000), `search.parquet` (22,500), `confirm.parquet`
(9,000), `numeracy.parquet` (1,260), `anchoring.parquet` (4,500).

**Runs** (peak RSS):

| Stage | Duration | Peak RSS |
|---|---|---|
| samples | — | 727 MB |
| dryrun | — | 1,042 MB |
| search | 21 min | 761 MB |
| anchoring | 5 min | 1,017 MB |
| select | — | 314 MB |
| confirm | 11 min | 633 MB |
| numeracy | 1.5 min | 1,029 MB |
| report | — | 1,016–1,161 MB |

Verifier: `uv run python -m newsaction.encoding.run --stage report` rebuilds everything from the cache offline
($0). It needs `cache/decisions.sqlite` and `work/` from this worktree.
