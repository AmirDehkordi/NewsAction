# NA-13b REPORT — When does the signal work? (exploratory, post hoc)

Date: 2026-10-29 · Branch `feat/NA-13b-selective` (main checkout, cut from main @ c3351ed after NA-14's merge) ·
Decisions: `docs/decisions/NA-13b.md` · PREREG: §15 row 65 (d587293, committed with the validation selection
e451062 before the test run) · Numbers: `artifacts/NA-13b/tables/*.csv` and `results/*.json` · Code:
`newsaction.selective` · Paper: NA-14 appendix tables t36–t43 and Figures A16–A19 (exploratory section).

**Everything in this report is exploratory (post hoc):** requested by the operator after unblinding, outside every
pre-registered family, no claim. Conditions were selected on validation only, by the operator's rule, and the 2026
test was evaluated once.

**Bottom line (test split 2026-01-02 → 2026-07-31; validation val-A 2025-Q3, val-B 2025-Q4).**
- **Selective prediction concentrates the signal where it is priced: at the open.** d1-ultra's top 10% by
  conviction |N̂|: signed z_on 1.52 / 1.16 / 0.93 and z_cc 0.80 / 0.75 / 0.59 (val-A / val-B / test), against
  0.22 / 0.26 / 0.21 and 0.13 / 0.16 / 0.10 for all events. After the open (z_id, the tradable move) the top 10% gives
  0.004 / 0.140 / 0.101 (d1-ultra) and 0.106 / 0.123 / 0.068 (Laya-Fin); every 95% interval at 10% coverage includes
  zero on the test.
- **Calibrated but compressed against overconfident.** Laya-Fin's N̂ has SD 0.11–0.12 and a median stated confidence
  of 0.006–0.007 (three-class probabilities near uniform; NA-12's test ECE 0.057); the API models' N̂ is wide and skewed
  positive (d1-ultra SD ≈ 0.61, 73–77% positive; span-02 SD ≈ 0.9) and their stated confidence overstates the hit rate
  (ECE 0.21–0.36).
- **The 10:00 reading never beats the pre-open reading** for y1 (10:00 → close), the model's revision after the first
  bar has IC ≤ 0 on val-B and the test (Laya-Fin −0.027 / −0.036, d1-ultra −0.043 / −0.011: over-updating toward the
  first bar), and no first-bar momentum or reversal holds across periods.
- **The conditioning study's validation choices did not hold.** 8 of 75 (model, condition) pairs were SELECTED on
  validation (pooled t 2.3–3.5). On the test five changed sign and three are small and positive (t ≤ 1.0); the
  smallest BH q among them is 0.94 and the smallest in the whole family 0.79. Their tradable versions, gross Sharpe
  4.6–6.8 (Laya-Fin) and 1.7–2.3 (d1-ultra) on val-B (in-sample), are −0.73 to +0.67 on the test, all below their
  placebo's 90th percentile and all net-negative at 10 bp. **No forward-test candidate qualifies.**
- No lock read, no API call ($0); 1,075 exploratory trials logged (ledger 545 → 1,620).

## 1. Scope

| Item (operator prompt §2) | Status | Where |
|---|---|---|
| (a) coverage curves, 5 models × 2 rankings × 11 coverages × 3 splits × 3 targets, bootstrap CIs, gate marked | done | `tables/coverage.csv`; t36; Figure A16 |
| (b) output distributions next to the reliability diagrams | done | `tables/histograms.csv`, `output_summary.csv`; t41, t42; Figure A19 |
| (c) the band disclosure reproduced exactly | done | `tables/bands.csv`; t43; `tests/test_selective_data.py` |
| (d) the D1 statistics, reproduced exactly, next to the pre-registered D1 results | done | `tables/watch_open.csv`; t37; Figure A17 |
| (e) conditioning study E1–E9: references, validation selection, one test, BH, tradable versions | done | `tables/{cuts,selection_validation,conditioning,selection,books}.csv`; t38–t40; Figure A18 |
| (f) every variant logged as an exploratory trial | done | `ledgers/trials.jsonl` (1,075 rows, chunk NA-13b) |
| Outputs wired into `make paper` (digests, trace, captions, contract) | done | NA-14 tables t36–t43 (LaTeX for t36–t39, t43), Figures A16–A19, `make paper` and `make paper-preview` |
| REPORT, decisions, self-audit, `make verify` | done | this file; `docs/decisions/NA-13b.md` |

## 2. Self-audit

| Check | Evidence | Result |
|---|---|---|
| C1 The three disclosures reproduce exactly | the assistant's transcript code rerun, then this chunk's code: (c) every band number, (d) the 24 ICs, (e) the preview's baselines, four pairs and the low-uncertainty row (`tests/test_selective_data.py`, every printed digit) | PASS |
| C2 Selection on validation only, fixed before the test | `validation` cuts the study to val-A/val-B before any statistic (test `test_the_validation_stage_passes_no_test_row_to_the_statistics`); the selection committed at e451062 (17:07:29 UTC) and §15 row 65 at d587293 (17:07:29), the test run at 17:07:57 on d587293 (`results/test_run.json`) | PASS |
| C3 The test is evaluated once | `run test` refuses an uncommitted or changed selection and changed val-A cut points (tests); one `test_run.json`; the trials ledger refuses a re-logged row with another value | PASS |
| C4 The selection is computed right | two independent re-implementations from a written specification reproduced all 221 validation statistics and the 8 pairs bit for bit; a third reproduced the two E4 conditions the operator's decisions changed | PASS |
| C5 No look-ahead in the books | every input's instant ≤ the 09:15 decision (`portfolios.check_timing`), the val-A cut points and, on the test, the validation selection included; a condition known only at the open is refused (tests) | PASS |
| C6 BH over the whole family | `selection.csv` `bh_q` over 75 pairs, `bh_q_unseen` over the 69 not [seen on test] | PASS |
| C7 Trials logged | 1,075 rows (330 + 36 + 669 + 40), kind "exploratory", `make ledgers` OK | PASS |
| C8 References verified | 14 of 14 against primary records (decisions file) | PASS |
| GAC1 `make verify` | exit 0: ruff and format clean, mypy --strict 179 files, 2,192 passed / 3 skipped / 2 xfailed (the expected strict ones), manifest 483 artifacts OK, ledgers OK; `make paper` "paper: OK" (all equal); `make paper-preview` 0 overfull, 0 undefined | PASS |
| GAC2 `Data/` untouched | `git status --porcelain Data/` empty; `Data/` is read-only | PASS |
| GAC3 2026 data only through the allowed routes | NA-12's frames, `analysis/targets_test`, NA-13's `strategy/market_test` (its one logged lock sequence) and, by the operator's decision, the ^VIX closes up to t−1 from NA-00's `work/market/market_prices.parquet`; `ledgers/test_access.jsonl` unchanged at 29 lines; `tests/test_blinding.py` passes | PASS |
| GAC4 No API call | spend ledger unchanged; NA-13b $0.00, cumulative $15.73 | PASS |
| GAC5 Data contract | `## NA-13b` section in `docs/DATA_CONTRACT.md` (14 entries), sha256 equal to the manifest (`make manifest` OK) | PASS |

## 3. (a) Selective prediction

Coverage c keeps the events whose score is at or above the val-A quantile at 1 − c (thresholds from val-A only;
span-02's and drex-v2.0's val-A is NA-06's 3,000-event stage-2 sample). Mean signed move = the mean of sign(N̂)·z over
covered events (typical daily moves); 95% CIs from the frozen stationary bootstrap over sessions.

**Mean signed move, conviction |N̂| (val-A / val-B / test):**

| Model | Coverage | z_cc | z_on | z_id |
|---|---|---|---|---|
| Laya-Fin | 100% | 0.088 / 0.083 / 0.043 | 0.064 / 0.093 / 0.063 | 0.058 / 0.037 / 0.016 |
| Laya-Fin | 30% | 0.231 / 0.183 / 0.083 | 0.265 / 0.137 / 0.136 | 0.086 / 0.114 / 0.024 |
| Laya-Fin | 10% | 0.459 / 0.351 / 0.172 | 0.569 / 0.332 / 0.191 | 0.106 / 0.123 / 0.068 |
| d1-ultra | 100% | 0.133 / 0.155 / 0.102 | 0.223 / 0.259 / 0.212 | 0.025 / 0.022 / 0.005 |
| d1-ultra | 30% | 0.366 / 0.369 / 0.273 | 0.677 / 0.604 / 0.508 | 0.034 / 0.053 / 0.025 |
| d1-ultra | 10% | 0.799 / 0.754 / 0.592 | 1.516 / 1.157 / 0.930 | 0.004 / 0.140 / 0.101 |

- On the test, d1-ultra's top-10% z_on is 0.930 [0.680, 1.135] and z_cc 0.592 [0.410, 0.759]; its z_id 0.101
  [−0.021, 0.241]. Laya-Fin's top-10% z_id is 0.068 [−0.036, 0.168]. span-02's and drex-v2.0's curves have the same
  shape (top-10% test z_on 0.72 and 0.77); Laya zero-shot's is flat.
- **Ranking by the stated confidence** (the frozen gate's measure) gives the same picture for d1-ultra; for
  Laya-Fin its top 10% had the largest validation z_id (0.214 [0.083, 0.372] / 0.164 [0.050, 0.346]) and 0.072
  [−0.025, 0.167] on the test. At the frozen gate (30% coverage by confidence) the test z_id is 0.048 (Laya-Fin) and
  0.025 (d1-ultra).
- Hit rates move little: d1-ultra's top 10% hits z_cc's sign 0.587 / 0.566 / 0.556 of the time, 0.506 for all events
  on the test.
- The mean daily IC inside the covered set is noisy (sessions with ≥ 5 covered names thin out below 30% coverage).

## 4. (b) Output distributions

| Model (test) | N̂ mean | N̂ SD | share N̂ > 0 | stated confidence median | q95 | ECE e5 (NA-12, test) |
|---|---|---|---|---|---|---|
| Laya-Fin | −0.008 | 0.115 | 0.58 | 0.006 | 0.073 | 0.057 |
| d1-ultra | 0.305 | 0.612 | 0.77 | 0.167 | 0.489 | 0.260 |
| span-02 ‡ | 0.246 | 0.907 | 0.68 | 0.314 | 0.739 | 0.361 |
| drex-v2.0 | 0.261 | 0.660 | 0.67 | 0.109 | 0.457 | 0.209 |
| Laya zero-shot | −0.205 | 0.281 | 0.20 | 0.157 | 0.220 | 0.176 |

- The distributions are stable across splits (val-A / val-B rows in `output_summary.csv`), except that the API models'
  share of positive readings rises from val-A to the test (d1-ultra 0.73 → 0.77) and Laya zero-shot drifts negative
  (share positive 0.35 → 0.20).
- The reliability diagrams (Figure A19 (c), NA-12's test bins) use the top-label class probability (§11.2's ECE),
  not the entropy confidence the histograms show. ‡ span-02: the S5 canary STOP, judged noise (PREREG §15).

## 5. (c) The disclosure (the operator's assistant's first look; it shaped this chunk)

Before this chunk, the operator's assistant split each split's events into val-A |N̂| bands (bottom 50%, 50–70%,
70–90%, top 10%; cut points Laya-Fin 0.032 / 0.054 / 0.133, d1-ultra 0.419 / 0.648 / 1.079). Its numbers reproduce
exactly (`tables/bands.csv`): d1-ultra top 10% hit rate 0.587 / 0.566 / 0.556, signed z_cc 0.80 / 0.75 / 0.59, z_on
1.52 / 1.16 / 0.93, z_id 0.004 / 0.140 / 0.101; Laya-Fin top 10% hit rate 0.562 / 0.542 / 0.526, z_cc 0.46 / 0.35 /
0.17, z_id 0.106 / 0.123 / 0.068; the bottom 50% is about 0 everywhere (|signed z_cc| and |z_id| ≤ 0.044). This look,
which used the test, is why the coverage curves were asked for; they are reported as a whole, with no chosen threshold.

## 6. (d) Watching the open

y1 = AR(10:00 → C_t)/σ_rest. Daily IC with y1 (Newey–West t) and the mean of sign(N̂_D0)·y1 by whether the first bar
moved against or with the pre-open view (day-clustered t); val-A / val-B / test:

| Model | Statistic | val-A | val-B | test |
|---|---|---|---|---|
| Laya-Fin | IC pre-open N̂_D0 | +0.047 (3.9) | +0.008 (0.5) | +0.026 (2.1) |
| Laya-Fin | IC 10:00 N̂_D1 | +0.034 (1.7) | −0.024 (−1.5) | −0.013 (−0.9) |
| Laya-Fin | IC revision | +0.001 (0.1) | −0.027 (−1.4) | −0.036 (−2.3) |
| Laya-Fin | IC first bar G_D1 | +0.030 (1.5) | −0.034 (−1.6) | −0.016 (−1.0) |
| Laya-Fin | mean, bar against | −0.010 (−0.3) | −0.000 (−0.0) | +0.045 (1.7) |
| Laya-Fin | mean, bar with | +0.111 (3.7) | −0.037 (−1.2) | −0.001 (−0.0) |
| d1-ultra | IC pre-open N̂_D0 | +0.014 (0.9) | +0.019 (1.6) | −0.004 (−0.3) |
| d1-ultra | IC 10:00 N̂_D1 | +0.029 (1.4) | −0.020 (−1.5) | −0.014 (−1.1) |
| d1-ultra | IC revision | +0.018 (1.2) | −0.043 (−2.7) | −0.011 (−0.8) |
| d1-ultra | IC first bar G_D1 | +0.030 (1.5) | −0.034 (−1.6) | −0.016 (−1.0) |
| d1-ultra | mean, bar against | −0.039 (−1.5) | +0.039 (1.3) | +0.008 (0.4) |
| d1-ultra | mean, bar with | +0.078 (3.1) | −0.013 (−0.4) | −0.036 (−1.5) |

The operator's assistant computed the four ICs first; they reproduce exactly. **Pre-registered D1 results, for
reference** (NA-12, NA-13; test): H2 at D1 (y1 on N̂_W0 and G) b = +0.229 (p 0.062) and c = +0.013 (Laya-Fin), b =
−0.018 (d1-ultra); κ at 10:00 = 0.273 (Laya-Fin) and 0.610 (d1-ultra); λ from the D1 entry to C_t ≈ −0.01 (both;
the 10:00 gap does not close); S-D1 J gross Sharpe +0.76 / −0.28 and S-CONV at D1 +1.61 (83rd placebo pct) / +0.03,
all net-negative at 10 bp.

**Reading.** The 10:00 reading never beats the pre-open reading. The revision after the first bar is zero or
negative on val-B and the test, which points to over-updating toward the first bar (the frozen forward test F5 asks
this question two-sided). No first-bar momentum or reversal holds across periods: the first-bar IC and the
against/with means change sign between splits. **Multiple comparisons:** 36 statistics (6 × 2 models × 3 splits;
the first-bar IC is the same for both models, so 33 distinct); about two with |t| > 2 are expected by chance, and
six appear (three on val-A, one on val-B, two on the test), none of them consistent across the three periods.

## 7. (e) The conditioning study

**Design** (the operator's, fixed before the chunk ran; operationalization in §15 row 65 and the decisions file).
Outcome: sign(N̂_D0)·z_id (primary), open → C_{t+1} (secondary), z_on (descriptive). E1 vendor fields; E2 d1-ultra's
own labels (A2); E3 timing; E4 day (Friday, Monday, the event's busy news day, the day's news count, earnings
intensity, FOMC/CPI/payroll days, VIX at t−1, |SPY overnight|); E5 stock; E6 model internals; E7 combinations; E8 the
cost-aware rule; E9 Laya-Fin's direction on d1-ultra's "numbers" and "material". 75 (model, condition) pairs.
Research basis: verified references in the decisions file.

**Validation selection** (positive with t ≥ 1 in val-A and val-B, pooled t ≥ 2; [seen on test] never selected):

| Pair | val-A diff (t) | val-B diff (t) | pooled t | test diff (t) | test p | BH q |
|---|---|---|---|---|---|---|
| Laya-Fin × d1 "numbers" | +0.061 (1.6) | +0.150 (3.0) | 3.34 | −0.040 (−1.0) | 0.33 | 0.94 |
| Laya-Fin × d1 "material" | +0.074 (2.3) | +0.088 (2.5) | 3.40 | −0.016 (−0.5) | 0.63 | 0.94 |
| Laya-Fin × d1 P(no effect) low | +0.073 (2.6) | +0.079 (2.0) | 3.17 | −0.037 (−1.2) | 0.23 | 0.94 |
| Laya-Fin × busy news day (event) | +0.046 (1.2) | +0.191 (2.5) | 2.75 | +0.014 (0.4) | 0.69 | 0.94 |
| Laya-Fin × own H-mag high | +0.057 (1.7) | +0.120 (2.8) | 3.22 | −0.016 (−0.5) | 0.63 | 0.94 |
| Laya-Fin × E9 (numbers and material) | +0.074 (1.4) | +0.208 (3.4) | 3.51 | −0.058 (−1.0) | 0.32 | 0.94 |
| d1-ultra × the day's news count high | +0.042 (1.1) | +0.102 (1.8) | 2.31 | +0.021 (0.7) | 0.52 | 0.94 |
| d1-ultra × agrees with Laya-Fin | +0.101 (2.0) | +0.073 (1.4) | 2.46 | +0.039 (1.0) | 0.32 | 0.94 |

(The day's news count is day level: Welch t. BH q over the 69 pairs not [seen on test]: 0.92 for each.) The secondary
outcome agrees: the selected pairs' test differences on open → C_{t+1} are −0.123 to +0.047 (E9 −0.123, t −2.2).

**The rest of the family on the test.** The smallest p is d1-ultra × VIX(t−1) high, +0.135 (t 3.1, p 0.011, q 0.79):
not selected (val-A +0.016, val-B −0.024), and its inside group holds 129 of 138 test sessions, so it contrasts them
with nine low-VIX days. The [seen on test] conditions: earnings day Laya-Fin −0.330 (t −1.6), d1-ultra +0.268 (t 1.3);
latest article before 08:00 +0.018 / +0.029; conviction top 30% +0.004 / +0.023. Descriptively, for Laya-Fin the
"material" and "P(no effect) low" conditions moved the overnight gap on the test (z_on +0.172, t 2.9; +0.133, t 2.6),
not the move after the open.

**Tradable versions** (exit at the close; val-B is in-sample for the selection; 5 and 10 bp per side on both legs and
the hedge; placebo 100 coin-flip sign assignments of the same events; DSR at N = 1,620):

| Book | val-B gross (pct) | test gross (pct) | test net 5 / 10 | break-even (bp) | names long / short | DSR 10 bp |
|---|---|---|---|---|---|---|
| Laya-Fin × "numbers" | 5.43 (100) | −0.73 (41) | −3.15 / −5.54 | −1.5 | 17.4 / 14.1 | 0.000 |
| Laya-Fin × "material" | 5.50 (100) | 0.19 (66) | −3.24 / −6.63 | 0.3 | 22.7 / 19.9 | 0.000 |
| Laya-Fin × P(no effect) low | 4.60 (98) | −0.57 (38) | −3.93 / −7.27 | −0.9 | 30.3 / 24.7 | 0.000 |
| Laya-Fin × busy news day | 5.99 (100) | 0.35 (64) | −2.77 / −5.88 | 0.6 | 30.2 / 23.7 | 0.000 |
| Laya-Fin × own H-mag high | 5.56 (100) | 0.67 (67) | −2.75 / −6.15 | 1.0 | 33.0 / 28.6 | 0.000 |
| Laya-Fin × E9 | 6.78 (100) | −0.71 (31) | −2.45 / −4.18 | −2.0 | 10.7 / 11.2 | 0.000 |
| Laya-Fin × E8 (cost hurdle) | 1.28 (76) | 0.88 (73) | −0.38 / −1.63 | 3.5 | 4.9 / 7.3 | 0.000 |
| d1-ultra × the day's news count high | 2.25 (78) | 0.36 (60) | −2.81 / −5.25 | 0.6 | 133.9 / 37.4 | 0.000 |
| d1-ultra × agrees with Laya-Fin | 1.69 (78) | 0.62 (66) | −2.84 / −6.32 | 0.9 | 48.2 / 14.7 | 0.000 |
| d1-ultra × E8 (cost hurdle) | 2.92 (95) | 0.05 (54) | −1.66 / −3.36 | 0.2 | 11.8 / 8.2 | 0.000 |

At C_{t+1} every test book is also net-negative at 10 bp except Laya-Fin × E8 (+0.01; gross 1.47, 85th placebo pct).
The largest DSR probability is 0.0045 (10 bp) and 0.079 (5 bp). Capacity medians $10–80M.

**Forward-test candidates** (SELECTED; the same sign on the test with BH q < 0.10; a test book above its placebo's
90th percentile): **none.**

## 8. (f) Trials

1,075 rows, kind "exploratory", chunk "NA-13b" (the ledger's chunk pattern now admits a letter): 330 coverage (model
× ranking × coverage × split; metric the mean signed z_id), 36 D1 (model × statistic × split), 669 conditions (pair ×
outcome × split; metric the difference), 40 books (book × exit × split; net Sharpe at 10 bp). The ledger holds 1,620
rows (`results/dsr.json` lists them by kind); NA-13's tables and DSRs (N = 545) are not recomputed, and the paper now
states that N from NA-13's table.

## 9. What NA-13b may conclude

- **Where the signal lives.** By conviction: in the most confident readings, and mostly in the overnight gap (priced
  at the open); after the open the gain from selectivity is small and imprecise on the test. By news type, day,
  stock and model combination: on validation, Laya-Fin's after-open signal looked concentrated in d1-ultra's
  "numbers" and "material" news, on busy news days and in its own high predicted magnitude; **none of these held on
  the 2026 test** (five reversed, none significant, every q ≥ 0.79).
- **The 10:00 reading and the revision add nothing** over the pre-open reading; the revisions lean the wrong way.
- **No candidate for the pre-registered forward test.** The forward test's F3 (the 90th-percentile conviction book)
  and F5 (over-updating) are already pre-registered; NA-13b adds nothing to §15 for NA-15.
- It claims no profitable strategy, chooses no threshold or condition from test results, and presents no [seen on
  test] condition as confirmed.

## 10. Limitations

- Multiple testing is large: 75 pairs × 3 outcomes × 3 splits, 110 coverage variants, 36 D1 statistics (1,075 trial
  rows). Validation t's of 2–3.5 were not enough to survive the test.
- Selection on two validation quarters (59 sessions each) is thin; the test (138–140 sessions) is longer.
- Vendor fields (E1) are retrospective labels (CLAUDE.md A6); d1-ultra's labels (E2) are contemporaneous but
  screen-failing-model readings (PREREG §8.3).
- The VIX, macro and busy-day conditions are day level with few days on one side (macro 7 + 6 validation sessions;
  VIX's test contrast has 9 outside days).
- SPY's overnight move is known only at the open; no book was built on it.
- Books carry NA-13's limitations (no borrow cost, sector exposure unhedged, the last two test sessions without an
  open).

## 11. Spend, look-ahead self-check, deviations, STOPs, owner decisions

- **Spend:** NA-13b $0.00 (no API call); cumulative $15.73 (spend ledger). FMP requests 0. Kaggle 0.
- **Look-ahead self-check:**

  | Input | Available at | ≤ the decision (09:15 of t) |
  |---|---|---|
  | Call A readings on W0 news (all models) | the latest W0 article (≤ 09:15) | yes |
  | Event attributes (vendor fields, timing, attention, tier, σ, z_m20) | W0 / t−1 (PIT registry) | yes |
  | val-A thresholds, medians, the rank-average distribution | close of val-A's last session | yes (val-B, test) |
  | Frozen V maps (E8) | the model's calibration instant | yes |
  | Day counts (D0 events, earnings events) | 09:15 of t | yes |
  | FOMC / CPI / payroll calendar | scheduled in advance | yes |
  | ^VIX close of t−1 | close of t−1 | yes |
  | SPY's overnight move | the open of t | **no** — reported only, no book |
  | The validation selection (test books) | close of val-B's last session | yes |
- **Deviations from the PREREG:** none to a frozen file, family or verdict. From the operator's prompt, by the
  operator's decisions: VIX at t−1 read from NA-00's copy of `Data/market` (the sealed snapshot has no VIX); payroll
  days added from bls.gov (`fred_releases.pkl` holds CPI only); no lock read was needed for SPY's overnight move
  (NA-13's market file holds SPY's legs). All in §15 row 65.
- **STOP conditions:** none fired (no spend, no lock read, no frozen file changed).
- **Owner decisions:** (1) the forward-test row: no candidate, *recommendation:* add nothing to §15 for NA-15;
  (2) NA-16's placement of Figures A16–A19, *recommendation:* the appendix with one paragraph in the exploratory
  section.

## 12. Files and `make verify`

- **Code (new):** `src/newsaction/selective/` (`data`, `coverage`, `watch`, `distributions`, `conditions`,
  `conditioning`, `books`, `trials`, `run`, `contract`). **Changed:** `src/newsaction/ledger.py` (chunk pattern);
  the paper build `src/newsaction/figures/` (`sources`, `tables`, `latex`, `data`, `appendix`, `render`,
  `captions`, `keys`, `guard`, `preview`, `paper`, `contract`): the NA-13b tables and figures, the guard extended to
  any NA-13b row in a main figure, the caption identifiers `NA-13b` and `y1`, and NA-13's DSR N cited from its
  stored `n_trials` (545) instead of the live ledger count.
- **Tests (new):** `tests/test_selective_{books,conditioning,data,run,trials}.py`; changed: `tests/test_ledger.py`,
  `tests/test_figures_{captions,exploratory,keys,paper,style,tables}.py`.
- **Data:** `work/selective/books_daily.parquet` (registered). **Artifacts:** `artifacts/NA-13b/` (inputs, results,
  tables, this REPORT). **Ledgers:** `trials.jsonl` +1,075. **Docs:** PREREG §15 row 65, `docs/DATA_CONTRACT.md`
  (NA-13b section; the NA-14 section regenerated), `docs/decisions/NA-13b.md`, `docs/REPLICATION.md` and
  `docs/paper_outline.md` (the new outputs, their digests and counts). **NA-14 artifacts:** `captions.yaml` (four
  captions; Figure 6's N), `inputs/prereg_deviations.yaml` (rows 64–65), the regenerated tables, keys, digests and
  preview.

```
ruff check src tests scripts      All checks passed!
ruff format --check               318 files already formatted
mypy --strict src/                Success: no issues found in 179 source files
pytest -q -m "not network"         2192 passed, 3 skipped, 2 xfailed in 233.02s
manifest                          483 artifacts, 10 inputs checked: OK
ledgers                           OK (trials.jsonl=1620, test_access.jsonl=29)
peak RSS                          9.7 GB
```
