# NA-03 REPORT — material labels, importance filters, events

Date: 2026-10-25 · Branch `feat/NA-03-filters` (cut from `main` @ `176cf8d`) · Decisions: `docs/decisions/NA-03.md` ·
Tables: `artifacts/NA-03/{filter_comparison,frontier,call_projection,selection_by_split,sensitivity_rule_ranking}.csv`,
`summary.json` (`scripts/na03_report.py`).

**Result.** The PREREG §6.8 rule, applied mechanically on val-A, chooses **F5** (logistic regression on the bge
embedding) at threshold 0.44954. It selects 30.0% of the val-A evaluation days and captures **43.5%** of material
ticker-days and **36.5%** of delayed-reaction days. Among those days, abnormal variance is 1.78× its average.

- **Runner-up.** F6 (LightGBM) is 0.92 pp better on recall. That is a tie under the 1 pp rule, and ties go to
  fewer inputs.
- **Rule filters.** F1–F4 are close to "a random day with news" at this budget.
- **Underreaction constraint.** The delayed-recall constraint excludes F2 and F3 but does not bind on the
  choice.
- **Events.** 48,103 D0 and 62,285 D2 events cover 2024-01-02 … 2026-07-31.
  *Update 2026-10-26:* after operator decision A (`parsing_allowed` None articles are third-party OK), the
  `events` and `project` stages were rebuilt with the frozen F5 unchanged. Now 55,485 D0 and 71,540 D2 events;
  robustness 2,894 / 3,940 and train 22,936 / 29,485, while val-A, val-B, test and the NA-11 cost projection are
  unchanged. Only 3 selected train days per window lack a third-party-OK article (PREREG §15, NA-02 row of
  2026-10-26; `selection_by_split.csv`).
- **NA-11 cost.** The NA-11 plan fits its $18 cap at $0.042/M ($4.03 minimal, $8.32 full). At $0.10/M the
  minimal plan fits ($9.59), but the full plan does not ($18.43).

**Blinding.** No return of a session ≥ 2026-01-02 was read, joined or summarized. Test-period events come from
articles, frozen models, article counts and t−1 tiers only. Only `events/labels.py` reads `panel_public`, and it
asserts sessions ≤ 2025-12-31. No `events` module imports `panel.targets` or the lock.
`ledgers/test_access.jsonl` is unchanged (2 NA-01 `write` entries). Val-B: label rows are stored for later
chunks, but no val-B statistic of returns was computed. The selection counts per split below are article counts.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 labels | done | `src/newsaction/events/labels.py`; `work/events/labels_public.parquet` (186,002 covered member company-days of train, val-A, val-B) |
| S2 candidates | done | `events/filters.py` (F0–F4 article scores, eligibility, ticker-day max + counts, budget selection, tie-breaker), `events/scores.py`; `work/events/{article_scores,ticker_days}.parquet` |
| S3 learned filters | done | `events/learned.py`; `work/events/models/{f5_logreg.model.json, f5_logreg.meta.json, f6_lgbm.model.txt, f6_lgbm.prep.json, f6_lgbm.meta.json}`; 12 grid points in `ledgers/trials.jsonl` |
| S4 comparison | done | `events/select.py` (`assert_val_a`, `compare`, `apply_rule`, `rule_trace`, `write_frozen_filter`); `artifacts/NA-03/filter_comparison.csv`, `frontier.csv`; `configs/frozen.yaml` `filter:` |
| S5 events | done | `events/aggregate.py`, `events/tokens.py`, `events/attention.py`, `events/clean_window.py`; `work/events/{window_counts,events_d0,events_d2}.parquet` |
| S6 projection | done | `events/projection.py`; `artifacts/NA-03/call_projection.csv` |
| CLI / config | done | `events/build.py` (7 stages, one process each); `configs/events.yaml` (constants checked against PREREG/PRD); `events/trials.py` (idempotent trial log) |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 dates | **Stored metadata**, F5 and F6 (`*.meta.json`): fit range 2024-07-01 … 2025-03-31, used sessions 2024-07-01 … **2025-03-24**, max label horizon **2025-03-31** (purged so t+5 ≤ window end); tune 2025-04-01 … 2025-06-23, max horizon **2025-06-30**. Model files' sha256 in the meta equal the manifest. **Tests:** `tests/test_events_dates.py` (stored dates; synthetic purge: the last fit session is 2025-03-24; `assert_val_a` refuses 2025-06-30, 2025-10-01 and 2026-01-05; `compare` refuses a sample with a val-B or train session; source check that `run_compare` filters to val-A). **Mutations:** config fit end → 2025-06-30, window purge removed, `assert_val_a` disabled: all **RED** | PASS |
| AC2 rule mechanical | `test_frozen_choice_recomputed_from_csv`: `apply_rule(filter_comparison.csv)` = **F5** = `frozen.yaml` id; the CSV sha256 = `comparison_sha` (`6ca1b192…1326`); threshold and tie_u_max match the chosen row; exactly one `chosen` row. **Mutation (drop the delayed-recall constraint):** `test_constraint_binds` (a planted table where the best-recall filter fails the constraint) turns **RED**. On the real table the constraint **does not bind**: `rule_trace` gives F5 with and without it, and it excludes F2 and F3. This is recorded as `constraint_binding: false` in `frozen.yaml` and as the CSV's `constraint_ok`. So the test detects the mutation; the real data shows the binding status | PASS |
| AC3 underreaction kept | Delayed recall reported for all 6 candidates and 4 natural-rate references. Chosen F5: **0.3645** ≥ F1 **0.2861** (`test_underreaction_kept`) | PASS |
| AC4 no test outcomes | `tests/test_events_no_test_outcomes.py`: AST scan of every `events/*.py` (no import of `newsaction.panel.targets` / `panel.reactions` / `newsaction.lock`, no "sealed"); the event builders reference neither `panel_public` nor the labels; only `labels.py` reads `panel_public`; the access ledger has no NA-03 entry (still 2 entries). **Mutations** "aggregate references panel_public" and "scores imports panel.targets": **RED** | PASS |
| AC5 event constraints | D0: 48,103 events, `n_list` 1…6 (mean 3.90), news tokens ≤ **598**. D2: 62,285, 1…6 (mean 4.28), ≤ **599**. event_id unique. All 453,761 listed article slots (D0 187,459 + D2 266,302) are `keep` ∧ `third_party_ok` articles of their event's company. On 200 sampled events per window, every t_avail is inside W0/W2 (`calendar.window_*`). 300 sampled events per window re-tokenize to the stored count, and lists are ordered by (score, t_avail) (`tests/test_events_constraints.py`). Also asserted at build time (`aggregate.check_events`). **Mutations** "third-party exclusion removed" and "token cap removed": **RED** | PASS |
| AC6 projection | `call_projection.csv` present (events, components, plans); §5 states the cap status at $0.042/M and $0.10/M (`tests/test_events_projection.py`) | PASS |
| AC7 clean-window flags | `clean_1, 2, 5, 10, 20` on every D0 and D2 event (nullable; NA only when t+h runs past 2026-07-31). Planted second D2 event 3 sessions later: clean_1 = clean_2 = True, clean_5 = clean_10 = clean_20 = False. Boundary tests: an event exactly at t+k gives clean_k False. 300 random events per file recomputed by hand from `events_d2`. `clean_window.py` imports only `newsaction.calendar`. **Mutation** `gap <= h` → `gap < h`: **RED** (after a boundary test was added; the first mutation round caught this gap) | PASS |
| GAC1 | `make verify` exit 0 (§7) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (10 inputs) | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal in `src/`; dates come from `configs/`); access ledger unchanged | PASS |
| GAC4 | No API call; `ledgers/spend.jsonl` empty; $0 | PASS |
| GAC5 | 11 new `work/events/` artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

`scratchpad` script: apply a mutation, run the named test file, restore the file byte-for-byte (asserted).
`git status` afterwards showed only the author's changes.

| Mutation | File | Result |
|---|---|---|
| delayed-recall constraint dropped | select.py | RED |
| 1 pp tie rule removed | select.py | RED |
| material = \|z_cc,t\| ≥ 2 only (verifier 7a) | labels.py | RED |
| delayed without \|z_on\| < 1 | labels.py | RED |
| fit window through 2025-06-30 (verifier 7b, config) | configs/events.yaml | RED |
| fit window not purged (code) | learned.py | RED |
| `assert_val_a` disabled | select.py | RED |
| aggregate references panel_public | aggregate.py | RED |
| scores imports panel.targets | scores.py | RED |
| third-party exclusion removed | aggregate.py | RED |
| token cap removed | tokens.py | RED |
| clean window `gap < h` | clean_window.py | RED (with the boundary test) |
| budget selection ignores eligibility | filters.py | RED |
| attention mean includes day t | attention.py | RED |

## 3. Numbers

### 3.1 Labels (S1)

- **Coverage.** Covered member company-days are train 122,734 (120,005 labelled) and val-A 31,694 (29,215). The last
  5 sessions of each split are purged.
- **Base rates** (labelled days):

  | Split | Material | Delayed | \|z_on\| ≥ 2 | six-day CAR ≥ 2 | z_vol ≥ 2 |
  |---|---|---|---|---|---|
  | train | 26.0% | 7.31% | 12.1% | 12.6% | 7.7% |
  | val-A | 20.6% | 7.03% | 7.5% | 10.9% | 7.5% |

- **Delayed vs material.** Some delayed days are not material: with √5 vs √6 scaling, a 2.1σ drift over
  t+1…t+5 is 1.94σ over six days. The delayed constraint is therefore a separate guard.

### 3.2 F5 / F6 fit and tune (S3)

- **Fit window.** 89,253 ticker-days (26.6% material) and 359,302 kept W0 articles.
- **Tune window.** 28,272 ticker-days (24.5% material) and 172,145 articles.
- **Tuning metric.** Ticker-day material recall at the 30% budget on the tune window.

| Model | Grid (tune recall) | Frozen |
|---|---|---|
| F5 | C = 0.001: 0.3933 · 0.01: 0.3944 · **0.1: 0.3946** · 1.0: 0.3943 | C = 0.1 |
| F6 | 15 leaves: 0.4190 / 0.4199 / **0.4212** / 0.4191; 63 leaves: 0.4173 / 0.4181 / 0.4205 / 0.4142 (min_child_samples 100, 100, 400, 400 × rounds 200, 600, 200, 600) | 15 leaves, min_child 400, 200 rounds |

### 3.3 Val-A comparison (S4; `filter_comparison.csv`)

- **Sample.** 26,738 covered member-days of val-A, labelled, with the first 5 sessions excluded (embargo). Of
  these, 21.1% are material and 7.2% delayed.
- **Budget.** 8,021 days (30%).

| Filter | Role | Eligible | Selected | Material recall | Delayed recall | Precision | Var ratio | Top-100 / Mid / Rest selected |
|---|---|---|---|---|---|---|---|---|
| F0 clean | natural | 81.2% | 81.2% | 0.859 | 0.831 | 0.223 | 1.09 | 94% / 84% / 75% |
| F1 material rules | natural | 46.1% | 46.1% | 0.506 | 0.462 | 0.232 | 1.20 | 67% / 47% / 37% |
| F1 | candidate (thinned) | 46.1% | 30.0% | 0.322 | **0.286** | 0.227 | 1.19 | 44% / 30% / 24% |
| F2 hard + timely | candidate = natural | 25.5% | 25.5% | 0.309 | 0.267 ✗ | 0.255 | 1.48 | 37% / 25% / 22% |
| F3 source quality | natural | 52.0% | 52.0% | 0.585 | 0.493 | 0.237 | 1.31 | 73% / 53% / 43% |
| F3 | candidate (thinned) | 52.0% | 30.0% | 0.335 | 0.270 ✗ | 0.236 | 1.33 | 42% / 30% / 25% |
| F4 novelty | candidate | 81.2% | 30.0% | 0.333 | 0.327 | 0.234 | 1.34 | 38% / 31% / 26% |
| **F5 embedding LR** | **candidate, chosen** | 81.2% | 30.0% | **0.435** | **0.365** | 0.306 | 1.78 | 45% / 29% / 25% |
| F6 LightGBM | candidate | 81.2% | 30.0% | 0.444 | 0.367 | 0.313 | 1.81 | 41% / 29% / 26% |

✗ = delayed recall below F1's (excluded by the rule).

- **Rule trace.** Among feasible filters (F1, F4, F5, F6) the best recall is F6's 0.4444. F5 (0.4352) is within
  1 pp (a tie) and comes earlier in the order F1 < … < F6. Without the constraint the choice is the same.
- **Frontier** (`frontier.csv`, Figure 6 data; material recall at a 10/20/30/40/50% share):
  - F0 (random among days with news): 0.10 / 0.21 / 0.30 / 0.41 / 0.52;
  - F1: 0.11 / 0.21 / 0.32 / 0.44 / 0.51;
  - F4: 0.12 / 0.23 / 0.33 / 0.44 / 0.55;
  - F5: 0.20 / 0.33 / 0.44 / 0.53 / 0.62;
  - F6: 0.22 / 0.34 / 0.44 / 0.54 / 0.63.

  At 30%, F1, F3 and F4 add 2–3 pp of recall over random (F0), and F2 adds 5.6 pp at its own 25.5% share.
  The learned filters add 13–14 pp.
- **Sensitivity of the tie-break deviation** (`sensitivity_rule_ranking.csv`; 2 trials logged).
  - Ranking F1 / F3 by their count of qualifying articles, instead of thinning at random, gives F1 0.345 /
    0.295 (material / delayed recall) and F3 0.387 / 0.277.
  - The rule still chooses F5. The constraint still excludes F2 and F3 and does not bind.

### 3.4 Events (S5; `selection_by_split.csv`)

| Window | Split | Covered days | With a kept article | Selected | Selected share | Events | Dropped (no third-party-OK article) |
|---|---|---|---|---|---|---|---|
| W0 (D0) | robustness | 57,514 | 29,129 | 2,894 | 5.0% | 689 | 2,205 |
| | train | 122,734 | 84,970 | 22,939 | 18.7% | 17,759 | 5,180 |
| | val-A | 31,694 | 25,635 | 9,079 | 28.7% | 9,079 | 0 |
| | val-B | 31,574 | 22,346 | 6,149 | 19.5% | 6,149 | 0 |
| | test | 71,237 | 49,431 | 14,427 | 20.3% | 14,427 | 0 |
| W2 (D2) | robustness | 57,514 | 33,651 | 3,940 | 6.9% | 971 | 2,969 |
| | train | 122,734 | 93,675 | 29,488 | 24.0% | 23,199 | 6,289 |
| | val-A | 31,694 | 27,722 | 11,252 | 35.5% | 11,252 | 0 |
| | val-B | 31,574 | 25,869 | 7,912 | 25.1% | 7,912 | 0 |
| | test | 71,237 | 58,264 | 18,951 | 26.6% | 18,951 | 0 |

- **Selection shares.** The frozen threshold selects fewer days outside val-A: val-A has more news per day,
  with 81% of covered days carrying a kept W0 article against 69–71% in train, val-B and test.
- **Robustness split.** The 2024-H1 split is thin. Coverage is sparse, and §6.1's `parsing_allowed` None policy
  (pending, treated as not OK) removes 76% of its selected days and 23% of train's. Nothing is removed from
  2025 on.
- **By tier** (D0, val-A / val-B / test): Top-100 2,774 / 1,766 / 3,683; Mid 2,635 / 1,715 / 4,264; Rest
  3,670 / 2,668 / 6,480.
- **List and tokens.**
  - Mean list length 3.90 (D0) / 4.28 (D2).
  - Mean news tokens 212.5 / 230.6, max 598 / 599.
  - The cap dropped articles in 25 / 31 events and never truncated a snippet.
  - 5.2% / 4.8% of listed articles carry `non_english_hint`.
- **Clean-window flags** (D0): the shares of events with clean_1 / 2 / 5 / 10 / 20 are 52% / 36% / 17% / 8% /
  3% (D2 is similar). Most big-company news days are followed by more news within a week, so the A1.5
  clean-window robustness sample will be small at h ≥ 10.

## 4. Spend

OpenRouter $0.00 this chunk, $0.00 cumulative (`ledgers/spend.jsonl` empty). FMP requests: 0. Kaggle: none.

Network:
- one download of the ModernBERT-large tokenizer files (rev `45bb4654`) from the Hugging Face Hub;
- `brew install libomp` (LightGBM's OpenMP runtime on macOS).

No article text or derived data left the machine.

## 5. Call projection (S6, AC6; `call_projection.csv`)

- **Tokens per call.** News tokens + 250 context + 350 core questions, plus 600 for the primary API
  instrument's extended / explain groups (A2).
- **Events.** Val-A, val-B and test, embargoed events included.
- **A3.1 cache hits.** Call A on D2 skips the 11,250 D2 events whose list equals their D0 list, because they
  hit the cache.

| Plan | Calls | $0.01/M | $0.02/M | **$0.042/M** | **$0.10/M** | $0.24/M |
|---|---|---|---|---|---|---|
| minimal (PRD S6: Call A D0 + Call B D2) | 67,770 | 0.96 | 1.92 | **4.03** | **9.59** | 23.03 |
| minimal + D1 (with NA-10 bars) | 97,425 | 1.38 | 2.75 | 5.78 | 13.75 | 33.01 |
| NA-11 full (S2 final selection, S6 incl. A3.1 Call A on D2, S8 ablations + $1 LLM) | 142,933 | 2.74 | 4.49 | **8.32** | **18.43** | 42.84 |
| NA-11 full + D1 + A3.5 market | 172,988 | 3.16 | 5.33 | 10.08 | 22.63 | 52.90 |

- **At $0.042/M (Jev):** every plan fits NA-11's $18 cap.
- **At $0.10/M:**
  - the minimal plan fits ($9.59);
  - the full plan exceeds the cap by $0.43, and $4.63 with D1 and A3.5.
  - A2.6's cutting order would bring it back under the cap. For example, without the extended group on the
    26,865 A3.1 Call A D2 calls alone, the full plan saves $1.61 at $0.10/M.
  - §13 also switches production to Call A + one Call B for a winner above $0.12/M.
- **Comparison with the PRD.** These event counts (val + test D0 29,655; D2 38,115) are below the PRD's
  planning numbers (~54K D0, ~69K D2). The 30% budget on a news-heavy val-A quarter yields about 20% of
  member-days elsewhere.

## 6. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| panel_public z_on, z_cc, z_vol, ar_cc, sigma_cc, car6_z | labels (S1) | `post`; sessions ≤ 2025-12-31 asserted; purged at split ends (§4.1) |
| labels_public | F5/F6 fit (≤ 2025-03-31 horizons) and tune (≤ 2025-06-30); val-A comparison | `post`; fit and tune windows purged inside train; comparison restricted to val-A (asserted twice) |
| articles_clean: company, t_avail, session_w0 / w2, novelty, dup counts, title_clean, snippet_clean, precision, source_class_domain, non_english_hint | counts, F4, events | known at t_avail (`w0` / `w2`); novelty and dup groups look only backwards (NA-02) |
| vendor tag_type, flags, sentiment, intensity, event_age_days, source_class, keep, third_party_ok | F1–F3, F6, event eligibility | `selection_only` (CLAUDE.md A6): never model text |
| embeddings_ts (bge-small) | F5, F6 PCs | function of the article's own scrubbed text (`w0`) |
| attention mean (previous 60 member sessions) | F6, events | `t_minus_1` (sessions ending t−1); the ratio's numerator is `w0` / `w2` |
| members_by_session, companies, coverage | covered member-days, attention | `static`; coverage is a sample-definition flag |
| tiers_monthly tier, rep_symbol_id | events | `t_minus_1` (ranked on the previous month end) |
| events_d2 sessions | clean_h flags | look forward by construction: registered `post`, sample selection only, never a model input |

56 NA-03 columns are registered in `configs/availability.yaml`:
- labels and `clean_*`: `post`;
- filter scores and third-party counts: `selection_only`;
- window counts, news lists and token counts: `w0` / `w2`;
- attention means: `t_minus_1`.

## 7. Deviations from PREREG

Four rows were appended to the §15 Deviations log (2026-10-25, NA-03), all before the freeze. As in NA-01 and NA-02,
they are **in the working tree, not committed**, for the operator to commit on main.

1. **§6.8 fixed budget for 0/1 rules.** Each filter has an eligibility set and a seeded hash tie-break. F1 and F3
   are thinned at random to 30%, and a selection is frozen as (threshold, tie_u_max). The count-ranked
   alternative does not change the choice (§3.3).
2. **§6.8 comparison sample.** Val-A covered member-days, purged and with the embargo applied: 26,738 days.
3. **§6.6 / §6.8 F5 and F6.** Article-level training with the ticker-day label; the window purge; the tuning
   metric; no refit; the feature details (`tag_type` only, PCA on the fit window, the member-session attention
   ratio).
4. **§6.9 / A1.2 events.**
   - D2 events use the same threshold on W2 scores.
   - A selected day without a third-party-OK article gets no event.
   - The token block format.
   - Clean flags come from events_d2 as written and are NA past the data end.

PRD-level choices that need no PREREG change are in `docs/decisions/NA-03.md`.

## 8. STOP conditions and owner decisions

No STOP condition fired. §13's projection STOP is evaluated in NA-11 against the actual winner's price; at
$0.042/M every plan fits. Owner decisions:

1. **Confirm the four NA-03 rows in PREREG §15**, especially row 1 (random thinning of F1 / F3 at the budget).
2. **`parsing_allowed == None`** (NA-02 decision 1, still pending). It now costs 2,205 of 2,894 selected
   robustness D0 days and 5,180 of 22,939 train days (D2: 2,969 / 6,289). Allowing None for local use only
   (option c) would not change the API states. It would restore Kaggle training events (NA-08) only if
   allowed there. `python -m newsaction.events.build --stage events` (then `project`) rebuilds them in about a
   minute.
3. **The projection at $0.10/M.** If the NA-06 winner is priced near $0.10/M, the full NA-11 plan needs A2.6's
   first cut. PREREG already orders the cuts; this flags it early.
4. **Non-English articles** (NA-02 decision 4). They are kept in the event lists and counted (`n_non_english_*`,
   about 5% of listed articles). NA-04 masking is English-only.
5. **Optional.** F6 lost to F5 only through the < 1 pp tie rule (0.444 vs 0.435). The chosen F5 is itself
   tag-free, so the tag-free robustness run in the PRD's NA-03 "Risks" note is now the primary analysis. A
   tag-based robustness variant (F6, or F1 at its natural rate) would be the natural complement; NA-11 decides.

## 9. Files

- **Added — code.**
  - `src/newsaction/events/{__init__,labels,attention,filters,learned,scores,select,tokens,clean_window,aggregate,projection,trials,build}.py`
  - `scripts/na03_report.py`
- **Added — config.** `configs/events.yaml`.
- **Added — docs and artifacts.**
  - `docs/decisions/NA-03.md`
  - `artifacts/NA-03/`:
    - `REPORT.md`, `summary.json`;
    - `filter_comparison.csv`, `frontier.csv`, `call_projection.csv`;
    - `selection_by_split.csv`, `sensitivity_rule_ranking.csv`.
- **Changed.**
  - `configs/frozen.yaml`: `filter:`.
  - `configs/availability.yaml`: 56 NA-03 columns.
  - `docs/DATA_CONTRACT.md`: the NA-03 section, 11 artifacts.
  - `pyproject.toml`: mypy ignores `sklearn.*` stubs.
  - `tests/test_configs_match_prereg.py`: `filter` leaves the null list; a shape test is added.
  - `ledgers/trials.jsonl`: +94 records:
    - 12 `filter_hparam` (train / tune);
    - 10 `filter` (val-A);
    - 70 `filter_frontier` (val-A);
    - 2 `filter_sensitivity` (val-A).
- **Changed, uncommitted.** `docs/PREREG.md` (§15 rows).
- **Tests added (91 in 10 new files, plus 1 in an existing file).**
  - `test_events_config` 8, `test_events_labels` 8, `test_events_dates` 7, `test_events_rule` 9,
    `test_events_constraints` 11;
  - `test_events_clean_window` 11, `test_events_no_test_outcomes` 23, `test_events_filters` 5,
    `test_events_learned` 5, `test_events_projection` 4;
  - `test_configs_match_prereg` +1.
- **Derived (gitignored).** `work/events/{labels_public,window_counts,article_scores,ticker_days,events_d0,events_d2}.parquet`,
  `work/events/models/*` (≈ 216 MB); `work/MANIFEST.json`.
- **Reproducibility.** A full rerun of the 7 stages reproduced every sha256 (11 work files, 3 CSVs,
  `frozen.yaml`) and appended no trial.
- **Peak RSS per stage (GB).** labels 0.3, counts 0.8, fit 8.9–9.2, scores 6.6, compare 0.4, events 6.4,
  project 1.1.
- **`make verify`:** exit 0.
  - ruff: all checks passed.
  - mypy --strict: no issues in 45 source files.
  - pytest: **547 passed** (455 before NA-03 + 92 new), **1 xfailed** (NA-01's literal AC3(c) bound).
  - manifest OK (40 artifacts, 10 inputs).
  - ledgers OK (trials 94, test_access 2, spend 0).
