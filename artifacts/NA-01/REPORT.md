# NA-01 REPORT — ATOM snapshot, adjusted daily panel, tiers, sealed 2026

Date: 2026-10-24 · Branch `feat/NA-01-panel` (cut from `feat/NA-00-scaffold` @ `56e03af`; merged into
`main` together with NA-00 on 2026-10-24) · Decisions: `docs/decisions/NA-01.md` · Tables:
`artifacts/NA-01/*.csv`, `summary.json` (written by `scripts/na01_report.py`).

**Revision 3 (after verification round 2, PASS on the ACs).** The verifier found F3: ATOM's raw volume
for the 20 sessions before the ORLY, NOW and TPL splits was already on the post-split basis, which put
fake abnormal volume on 60 days. HON's volume was doubled like its price is halved. Fixed by
`adjust.volume_basis_check` and traded-level dollar volume (§3.2); only volume-derived columns changed.

**Revision 2 (after verification round 1, FAIL).** The verifier found two defects the written ACs did
not catch: F1, corrupt CIQ share counts (MRSH, BNY, JNPR), and F2, HON's ATOM raw price at half the
traded level. Both are fixed by general checks, not per-name patches (§3.1). A systematic review found
the share problem in 23 companies, not 3, and tiers were rebuilt. AC3(c) remains an owner decision.

**Blinding.** No statistic, print or plot of any test-period (≥ 2026-01-02) return appears in this
report or was looked at. For test months, only counts are shown: membership, tier sizes, close sources.
The blinded files were written by the export, registered by hash, and never opened.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 export | done | `scripts/export_atom_snapshot.py` (ATOM venv; one `REPEATABLE READ, READ ONLY` transaction); `scripts/register_snapshot.py`; `work/snapshot/*.parquet` (10), `work/snapshot/sealed/{prices_raw,total_return_check}_2026.parquet`, `MANIFEST_snapshot.json` |
| S2 mapping + adjustment | done | `src/newsaction/panel/{mapping,adjust}.py`; `work/panel/{mapping,qc_flags}.parquet` |
| S3 sector | done | `src/newsaction/panel/sector.py` (GICS level 1, leave-one-company-out, ≥ 5 others) |
| S4 risk | done | `src/newsaction/panel/risk.py` (every rolling statistic ends at t−1 via an explicit `.shift(1)`) |
| S5 companies + tiers | done | `src/newsaction/panel/tiers.py`; `work/panel/{companies,tiers_monthly}.parquet` |
| S6 targets + reactions + placebo | done | `src/newsaction/panel/{targets,reactions}.py` (the A1.2 ladder included; the test period goes only through `newsaction.lock`) |
| S7 build | done | `src/newsaction/panel/build.py` (`uv run python -m newsaction.panel.build`); `work/panel/{panel_public,panel_test_inputs}.parquet`; every column registered in `configs/availability.yaml` |
| S8 QC report | done | this file + `scripts/na01_report.py` |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 read-only export | `MANIFEST_snapshot.json`: `transaction_read_only` = **on**, statement `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`. `count(*)` before = in-snapshot = after: md.price_eod **2,016,915**, uni.member **1,551**. Price rows ≥ 2026-01-02 only in `sealed/` (78,131 + 78,131); public price files max `trade_date` = 2025-12-31, checked from row-group statistics. `tests/test_export_snapshot.py` (9) | PASS |
| AC2 PIT rolling stats | `tests/test_panel_pit.py`. Real data: a +50σ AR_cc (ratio measured 50.0) plus 100× volume planted on (AAPL, 2025-03-14) in a copy of the public inputs. Every t−1 column of **every** symbol dated ≤ 2025-03-14 is unchanged. β_m, β_s, ADV63, car_m5 and logv_mad60 dated 2025-03-17 change. Every March 2025 tier is unchanged; April's ranking input (ADV63) moves. Synthetic version covers the median/MAD statistics deterministically. Mutations (drop any of the 5 shifts) are **RED** (§2.1). Note: AC2's "tier … for 2025-03-17 change" cannot hold under PREREG §3.3 (March tiers use the February ranking); the test checks the PIT property | PASS |
| AC3 adjustment | (a) r_on(GE, 2024-04-02) = **+0.41%** (raw gap −19.8%). (b) Every public member-day with \|r_on\| > 25% has a qc_flags entry (0 missing). (c) Mean AR_on on cash-dividend ex-dates − other days = **+5.85 bp** (bound 3 bp; 4,045 ex-days). The adjustment is exact: factor jump 60.67 bp vs D/P 60.50 bp. The slope of AR_on on D/P is **0.013**; an adjustment error gives −1 or +1. By yield quintile: 5.8 / 6.2 / 3.7 / 7.1 / 5.7 bp, flat. This is an ex-date return pattern, not a dividend error. `tests/test_panel_adjust.py`: the slope test passes; the literal 3 bp test is a strict xfail | (a) (b) PASS · (c) **FAIL as written** (owner decision 2) |
| AC4 calendar equality | `tests/test_panel_calendar_equality.py`: 1,207 sessions 2022-01-03 … 2026-10-23, all open/close instants equal `calendar_atom`; 2025-01-09 absent; the half days are equal | PASS |
| AC5 tiers | Each of 37 months (2023-07 … 2026-07) has exactly **100** Top-100 and **150** Mid ranked companies (ties by company_id). NVDA Top-100 (rank 3) in 2024-06/07/08. AVGO (Top-100, ranks 9/8), CMG (Mid, ranks 106/107) and WMT (Top-100, 14/13) keep their tiers across their splits. Caps are continuous across splits: NVDA 2,707 → 3,042 bn, CMG 85.9 → 86.0 bn, AVGO 745.8 → 746.4 bn, WMT 444.9 → 473.5 bn. Golden caps are recomputed through the share code (NVDA, CMG, AVGO, WMT, GE before its spin-off). Mutation "no split adjustment of shares" is **RED**. **Revision 2 goldens** (verifier F1/F2): HON Top-100 in all 31 public months (rank 53–93; cap 2025-09 **$140.0bn**, verifier $136.6bn). MRSH Top-100 / Mid (was Rest). BNY Mid in all months (rank 135–231). CTRA Rest (was Top-100, rank 8). V (ranks 9–14) and BRK-B (7–9) Top-100 in all months. Share goldens are recomputed through the cross-check code. Fallback (DV-imputed cap): **54** company-months, ≤ 2 per month (was 553 before the cross-check) | PASS |
| AC6 universe | Companies per session **500 / 500 / 502** (min / median / max), 897 sessions 2023-01-03 … 2026-07-31; symbols 503 / 503 / 505. WBA last member session 2025-08-26 and absent from 2025-08-27. COIN first 2025-05-19 and present through 2025-12-31. HOOD and APP first 2025-09-22 (absent 2025-09-19). `tests/test_panel_universe.py` (6) | PASS |
| AC7 sanity | Median per-stock R² of r_cc on [SPY, sector − SPY], member days 2024-07-01 … 2025-12-31: **0.399** (IQR 0.275–0.532, 510 stocks). Inside [0.30, 0.40] but near the top: the equal-weighted leave-one-out sector factor fits better than the exploratory 0.34 | PASS |
| AC8 sealing | panel_public max session 2025-12-31. panel_test_inputs: 29 columns, kinds {static, t_minus_1} only (`check_inputs(…, "D0")` passes), sessions 2026-01-02 … 2026-07-31. `build_targets(…, "test")` and `build_reactions(…, "test", "D2"/"D1")` raise `LockError` and log `allowed: false` (temporary ledger). Public routes and the placebo helper refuse test-period rows. The post-freeze / post-unblinding route reads through `lock.read_sealed` (tested with a real freeze record in a throwaway repo). Mutations "targets / reactions skip the lock" are **RED**. `tests/test_panel_sealing.py` (12) | PASS |
| AC9 ladder | 20 random public events (seed 2026): CAR^lvl at C_{t+5} = Σ_{j=0..5} AR_cc,t+j / σ_cc,t and CAR^lvl at O_t = AR_on,t / σ_cc,t to 1e-9. The C_{t+20} rung is NaN for every session within 20 of the train / val-A / val-B ends and finite 21 sessions before. Synthetic tests cover e5, E5^lvl, y2, the forward pieces, purge, the delisting hold and gaps. Mutation "no purge" is **RED** | PASS |
| GAC1 | `make verify` exit 0 (§7) | PASS |
| GAC2 | `git status --porcelain Data/` empty; nothing written under Data/; `make manifest` checks the inputs | PASS |
| GAC3 | Blinding scan of `src/` (no test-period literals; "sealed" only in lock API calls); `ledgers/test_access.jsonl` has 2 entries, both `write` (snapshot registration), no read | PASS |
| GAC4 | No API call; spend $0 | PASS |
| GAC5 | All 19 new artifacts are in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A session-local script applied each mutation, ran `pytest`, and restored the file; `src/` was
byte-identical afterwards.

| Mutation | File | Result |
|---|---|---|
| beta moments not lagged | risk.py | RED |
| sigma (MAD) not lagged | risk.py | RED |
| volume baseline not lagged | risk.py | RED |
| momentum not lagged | risk.py | RED |
| ADV not lagged | risk.py | RED |
| no split adjustment of shares | tiers.py | RED |
| ranking at the current month end | tiers.py | RED |
| spin-off pseudo-splits scale shares | tiers.py | RED (GREEN on the first run; the GE golden was added) |
| test-period targets skip the lock | targets.py | RED |
| test-period reactions skip the lock | reactions.py | RED |
| no purge | targets.py | RED |
| public targets accept test rows | targets.py | RED |
| adjusted open uses no factor | adjust.py | RED |
| own company left in the sector factor | sector.py | RED (GREEN on the first run; LOO unit tests added) |
| minimum of 5 other companies dropped | sector.py | RED |
| no share cross-check (CIQ always kept) | tiers.py | RED (revision 2) |
| Yahoo reference without the 45-day lag | tiers.py | RED (revision 2) |
| Yahoo stability guard removed | tiers.py | RED (revision 2) |
| raw price-level factor never applied | adjust.py | RED (revision 2) |
| no volume basis check | adjust.py | RED (revision 3) |
| dollar volume without the traded-level volume | build.py | RED (revision 3) |

## 3. Numbers (public period unless stated)

### 3.1 Revision 2: verification findings F1 and F2

**F1, share counts.** ATOM's CIQ `shares_basic` is corrupt for some large names and missing for others.
`tiers.YahooShares` / `tiers.cross_check` compares the CIQ count with Yahoo's count for the same class
(`work/market/shares.parquet`). The Yahoo observation must be 45–400 days old, at least 30 days after the
last split, and within 1.5× of its own trailing-year median. Yahoo replaces CIQ when CIQ is missing or
more than 1.5× off (`share_substitutions.csv`). Of 18,557 company-months:

| shares_source | company-months |
|---|---|
| ciq (cross-checked) | 17,383 |
| ciq_unchecked (no usable Yahoo count) | 290 |
| yahoo_ciq_rejected | 325 |
| yahoo_ciq_missing | 499 |
| missing → DV fallback | 60 |

The rejected CIQ counts (median CIQ vs Yahoo, millions):
- **Corrupt in CIQ:** MRSH 1.07 vs 492, BNY 38 vs 733, CBRE 43 vs 305, CTRA 18,536 vs 757, HES 18 vs
  308, JNPR 14 vs 325, CTLT 24 vs 181, SEE 4,156 vs 144, WRK 1,272 vs 256, MRO 1,347 vs 585, CMA 44 vs
  132, IPG 103 vs 377.
- **Class A vs all classes:** BX 769 vs 1,218, IBKR 444 vs 1,700, ARES 219 vs 330, CVNA 138 vs 217,
  SATS 528 vs 289.
- **Yahoo-side errors that change no tier:** DOC (before 2024-03), UDR (2023), PSKY (2026).

CIQ is missing entirely for single-letter and class tickers: V, T, C, F, D, O, A, J, K, L, CB, BRK-B, BF-B.

**F2, raw price level.** `adjust.raw_level_check` takes Yahoo's dividend factor jump at each ex-date,
which equals D / traded close, so D / jump gives the traded price level and can be compared with ATOM's
raw close (`raw_level_check.csv`). Across 434 names with at least 4 usable ex-dates the ratio is
1.000 (median; 1% / 99% quantiles 0.993 / 1.012). Only **HON** is flagged, at **2.000** over 16 ex-dates
(IQR 0.0003). Its factor rescales the price levels used for caps and dollar volume; returns are ratios
and unchanged. In test months HON keeps its last public close, with shares on that session's basis.

**Impact on tiers** (`tier_changes_vs_first_build.csv`). 404 public company-months in 102 companies
change tier. In 23 companies the company's own data changed: HON, CTRA, CB, HES, F, MRSH, D, CBRE, WRK,
MRO, O, BNY, A, T, K, SEE, IBKR, C, BF-B, V and others. The other 79 crossed the rank-100 / 250
boundaries because of those.

The verifier's suggested check, Yahoo adjusted close × Yahoo shares, was not used as the rule: it also
fires on NVDA, CMG, DD and AMCR around their splits, whose ATOM data are right.

**Side note fixed.** `tiers_monthly` keeps no reconstructed test-period price levels: `raw_close`,
`cap_usd`, `cap_rank_value` and `adv63_usd` are NaN for the 6 test months. Ranks and tiers remain.

**Verifier note, Step 8.** HON's Solstice spin-off and CMCSA's Versant spin-off are dated 2025-10-01 and
2025-12-08 in both vendors; the real ex-dates were 2025-10-30 and 2026-01-05. No real move was erased.
Check CMCSA around 2026-01-05 after unblinding.

**Mapping** (`mapping_failures.csv`): 525 of 565 ids map to Data/prices (Spearman ≥ 0.99 on ≥ 120 non-event
days). Lowest Pearson: GNRC 0.981 (Spearman 0.994; one bad ATOM print), HON 0.991, CMCSA 0.993 (spin-offs
missing in ATOM).

The 40 unmapped ids fall back to ATOM total-return closes: AMTM ANSS ATVI BNY CBOE CMA CRH CTLT CTRA DAY
DELL DFS DISH ERIE FDXF FISV FLEX FRC HES HOLX HONA IPG JNPR K MRO MRSH PSKY PXD Q SATS SBNY SEDG SEE SIVB
SNDK SOLS SW WBA WRK XYZ. Where both series exist, ATOM total and Data/prices r_cc differ by > 50 bp on 47
of 524,907 symbol-days.

**β / σ distributions**, member-days 2024-07 … 2025-12 (`beta_sigma_quantiles_2024H2_2025.csv`):

| | q01 | q10 | q50 | q90 | q99 |
|---|---|---|---|---|---|
| β_m | 0.12 | 0.53 | 0.95 | 1.51 | 2.15 |
| β_s | −0.38 | 0.29 | 0.90 | 1.40 | 2.22 |
| σ_cc | 0.63% | 0.69% | 0.99% | 1.58% | 2.80% |
| σ_on | 0.23% | 0.26% | 0.38% | 0.60% | 1.14% |
| σ_id | 0.61% | 0.66% | 0.92% | 1.44% | 2.39% |

z_cc, z_on and z_id have median ≈ 0 and q10/q90 ≈ ±1.4. z_on has the fattest tails (q01 / q99 = −5.1 / +5.4).

**Tier sizes** (`tier_sizes_by_month.csv`): 100 / 150 / 250 ranked in every month except 2026-07
(100 / 150 / 248 plus 2 `no_data`). Joiners tiered by threshold: 56 company-months. Ranking-session closes:
15,544 ATOM raw, 2,914 reconstructed (test months), 93 stale public (ids without Data/prices, plus HON;
test months), 6 missing.

**Raw-close reconstruction** (test-month ranking sessions; PREREG §15), validated on public data with
anchor 2025-06-30. Daily absolute error: median 0.0000, p99 0.22%, max 6.8%. The worst cases are CMCSA
(6.8%) and HON (6.1%), the two spin-offs ATOM lacks, then AMCR (3.0%). Tiers rebuilt with reconstructed
closes, the same share cross-check and the same level factor agree **100%** with the exact tiers in
2025-08 … 2026-01; the largest rank change is 4 (`reconstruction_holdout_tiers.csv`).

**Share basis** (`split_classification.csv`): 46 true splits plus 17 spin-off pseudo-splits since 2022 (2026 rows included: corporate actions, no prices).
Of the 115 (symbol, true split) pairs checked against `shares_basic`, all 115 are restated, so values are
on the post-split basis of the CIQ pull.

**Leavers** (`leavers.csv`): 62 symbols whose last member session precedes 2026-07-31. Examples: SIVB/SBNY
2023-03-13, FRC 2023-05-02, ATVI 2023-10-16, PXD 2024-05-07, MRO 2024-11-22, DFS 2025-05-16, JNPR
2025-07-07, HES 2025-07-21, WBA 2025-08-26, K 2025-12-10. In panel_public, leavers keep up to 60 priced
sessions after exit for target horizons (1,842 non-member rows).

**QC flags**: 228 public symbol-days.

| Reason | Member days | Non-member days |
|---|---|---|
| genuine_large_move (\|r_on\| > 25%, factor smooth, ATOM agrees) | 19 | 162 (mostly SBNY OTC prints after its 2023 exit) |
| cash_dividend (ATOM total-return dividend handling: HON's halved raw price, which doubles its yield (F2), and AMCR) | 15 | 8 |
| adj_factor_jump_no_atom_action (spin-offs ATOM lacks: CMCSA Versant, HON Solstice) | 5 | 10 |
| raw_print_suspect (one bad ATOM raw close) | 1 | 6 |
| spinoff (LEN Millrose: Yahoo 1.067 vs ATOM 1.033) | 1 | 0 |
| other | 0 | 1 |

Top 30 member-day flags (`qc_top30_member_days.csv`; ranked by max(\|diff\|, \|r_on\|)). Values are never
changed by a flag.

| # | Session | Ticker | Rule | Reason | r_on | r_cc | ATOM total r_cc | diff (bp) |
|---|---|---|---|---|---|---|---|---|
| 1 | 2025-10-29 | FISV | abs_r_on_gt_25pct | genuine_large_move | -0.434 | -0.440 | -0.440 | +0 |
| 2 | 2024-07-26 | DXCM | abs_r_on_gt_25pct | genuine_large_move | -0.388 | -0.407 | -0.407 | +0 |
| 3 | 2023-11-01 | PAYC | abs_r_on_gt_25pct | genuine_large_move | -0.377 | -0.385 | -0.385 | -0 |
| 4 | 2025-10-06 | AMD | abs_r_on_gt_25pct | genuine_large_move | +0.375 | +0.237 | +0.237 | +0 |
| 5 | 2025-08-08 | TTD | abs_r_on_gt_25pct | genuine_large_move | -0.359 | -0.386 | -0.386 | -0 |
| 6 | 2025-07-02 | CNC | abs_r_on_gt_25pct | genuine_large_move | -0.341 | -0.404 | -0.404 | -0 |
| 7 | 2023-10-20 | SEDG | abs_r_on_gt_25pct | genuine_large_move | -0.337 | -0.273 | -0.273 | +0 |
| 8 | 2025-02-05 | FMC | abs_r_on_gt_25pct | genuine_large_move | -0.335 | -0.335 | -0.335 | -0 |
| 9 | 2025-09-10 | ORCL | abs_r_on_gt_25pct | genuine_large_move | +0.322 | +0.359 | +0.359 | -0 |
| 10 | 2025-07-31 | ALGN | abs_r_on_gt_25pct | genuine_large_move | -0.300 | -0.366 | -0.366 | -0 |
| 11 | 2025-09-10 | SNPS | abs_r_on_gt_25pct | genuine_large_move | -0.292 | -0.358 | -0.358 | +0 |
| 12 | 2024-10-30 | SMCI | abs_r_on_gt_25pct | genuine_large_move | -0.291 | -0.327 | -0.327 | +0 |
| 13 | 2025-02-06 | SWKS | abs_r_on_gt_25pct | genuine_large_move | -0.282 | -0.247 | -0.247 | -0 |
| 14 | 2025-08-05 | IT | abs_r_on_gt_25pct | genuine_large_move | -0.280 | -0.276 | -0.276 | -0 |
| 15 | 2025-09-18 | INTC | abs_r_on_gt_25pct | genuine_large_move | +0.276 | +0.228 | +0.228 | +0 |
| 16 | 2024-07-25 | EW | abs_r_on_gt_25pct | genuine_large_move | -0.264 | -0.313 | -0.313 | +0 |
| 17 | 2024-11-19 | SMCI | abs_r_on_gt_25pct | genuine_large_move | +0.259 | +0.312 | +0.312 | -0 |
| 18 | 2024-08-29 | DG | abs_r_on_gt_25pct | genuine_large_move | -0.255 | -0.321 | -0.321 | -0 |
| 19 | 2023-10-23 | FMC | abs_r_on_gt_25pct | genuine_large_move | -0.251 | -0.132 | -0.132 | +0 |
| 20 | 2025-12-08 | CMCSA | tr_diff_gt_50bp | adj_factor_jump_no_atom_action | +0.000 | -0.024 | -0.086 | +615 |
| 21 | 2025-10-01 | HON | tr_diff_gt_50bp | adj_factor_jump_no_atom_action | +0.000 | -0.002 | -0.059 | +578 |
| 22 | 2025-01-21 | LEN | tr_diff_gt_50bp | spinoff | -0.007 | -0.028 | -0.059 | +310 |
| 23 | 2025-04-23 | LVS | tr_diff_gt_50bp | raw_print_suspect | +0.027 | +0.013 | +0.021 | -80 |
| 24 | 2025-11-28 | AMCR | tr_diff_gt_50bp | cash_dividend | -0.019 | -0.012 | +0.003 | -151 |
| 25 | 2025-09-05 | AMCR | tr_diff_gt_50bp | cash_dividend | -0.011 | -0.006 | +0.009 | -153 |
| 26 | 2024-01-03 | BEN | tr_diff_gt_50bp | cash_dividend | -0.010 | -0.035 | -0.024 | -106 |
| 27 | 2024-01-02 | BEN | tr_diff_gt_50bp | adj_factor_jump_no_atom_action | -0.009 | -0.006 | -0.017 | +103 |
| 28 | 2023-07-12 | EXR | tr_diff_gt_50bp | adj_factor_jump_no_atom_action | +0.010 | +0.006 | -0.001 | +67 |
| 29 | 2025-09-03 | EG | tr_diff_gt_50bp | cash_dividend | -0.010 | +0.009 | +0.015 | -58 |
| 30 | 2024-02-29 | HON | tr_diff_gt_50bp | cash_dividend | +0.009 | +0.011 | +0.017 | -54 |

**For the verifier.**
- **Step 4 (MSFT, 2025-06-12).** σ_cc is at the cross-sectional floor: the raw 1.4826·MAD is 0.006450 and
  the stored value is 0.006759, the day's member minimum. β_m and β_s match numpy OLS to 1e-6
  (`tests/test_panel_pit.py::test_hand_recompute_msft_beta_sigma`).
- **Step 3.** "sealed" appears in `src/` only in lock API calls (`lock.read_sealed`) and in `paths.py`
  (allowed in NA-00).

### 3.2 Revision 3: verification finding F3 (volume share basis)

ATOM and Data/prices volumes agree to 0.4% on 99% of public symbol-days. They disagree by exactly a
pending split ratio on 60 days, where ATOM's raw volume is already split-adjusted but its raw close is
not (`volume_basis_check.csv`):

| Ticker | Split | Days restored | z_vol median on those days (before → after) | Days with z_vol > 4 |
|---|---|---|---|---|
| ORLY | 15:1, 2025-06-10 | 2025-05-12 … 06-09 (20) | +6.78 → −0.60 | 17 → 0 |
| NOW | 5:1, 2025-12-18 | 2025-11-19 … 12-17 (20) | +4.28 → +0.45 | 11 → 1 |
| TPL | 3:1, 2025-12-23 | 2025-11-24 … 12-22 (20) | +3.74 → +0.70 | 7 → 0 |

- ORLY is now Mid by dollar volume in every public month (it was Top-100 in 2025-06 … 09).
- HON's ATOM volume is 1.98× Data/prices, mirroring its halved raw price, so dollar volume now uses
  volume on the traded level. HON's DV rank median moves from 29 to 87; its cap tier does not change.
- Other disagreements are not touched, because no pending split explains them: DD after the Qnity
  spin-off (Data/prices volume is the odd one), BRK-B in 2024, and single-day prints on 2023-05-30.
- **What changed:** `raw_volume` (60 cells), `z_vol` / `logv_med60` / `logv_mad60` (ORLY, NOW, TPL),
  `adv63` (plus HON), and DV ranks and tiers. Returns, betas, sigmas, targets, cap ranks and tiers, the
  sector factor and the QC flags are identical to revision 2, as are `companies` and `qc_flags`.

## 4. Spend

OpenRouter $0.00 this chunk, $0.00 cumulative (`ledgers/spend.jsonl` empty). FMP requests 0. No network
use other than the local ATOM Postgres.

## 5. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| ATOM raw OHLCV (snapshot, ≤ 2025-12-31) | r_on, r_id, f, dollar volume, z_vol | bar d known at close(d); used for t−1 statistics from t+1 |
| Data/prices adjusted close / volume | r_cc; t−1 features of test sessions; reconstructed ranking closes | as above. Test-period values feed only rolling statistics ending t−1 (PREREG §15, NA-00 row 2) |
| work/market SPY close | market factor | as above |
| members_by_session | member flag, sector pool, ranking universe | membership at open(s), announced in advance (static) |
| gics | sector | current classification applied to every session (ATOM has no history). Mild look-ahead in classification only (e.g. the 2023-03 GICS changes), not in returns |
| corporate_actions | adjustment factors, true-split share bases, QC reasons | ex-date based. Splits after the ranking session are used only to undo CIQ's retroactive restatement, never as information about the future |
| shares_basic | caps | row used only if known_from ≤ close(ranking session) (synthetic 45/90-day lag) |
| work/market/shares.parquet (Yahoo share counts) | share cross-check and substitute | observation dated 45–400 days before the ranking session (its own as-of dates are retrospective, so the lag is conservative); share counts only, no prices |
| Data/prices factor jumps at ex-dates | raw price-level check | public ex-dates only; the factor rescales levels, never returns |
| β, σ, z_vol baseline, ADV, momentum | features | windows end at t−1 (explicit shift; planted-shock tests) |
| tiers, representative class | features | ranking session = last session of the previous month |
| sector factor r_sec,x,t | AR_x,t (post) | same-day peers; only enters same-day AR and t−1 betas |
| targets / g_d2 | labels / D2 reaction | `post` / `d2_reaction` in the registry; purged at split ends |
| estimates_fy1 | exported, not used in NA-01 | use as_of_date < session (NA-04) |

## 6. Deviations from PREREG

Nine rows appended to the §15 Deviations log (2026-10-24, NA-01), all before the freeze. They are
committed separately on `main` (operator instruction: PREREG / CLAUDE.md / PRD stay out of NA-01
commits). They sit in their own table at the end of §15, which is the append-only part outside the
freeze hash (NA-00 row 1).
1. §3.2: companies grouped by issuer name when there is no CIK.
2. §3.2–3.3: cap = representative close × company-level shares; shares de-split by later true splits;
   spin-off pseudo-splits ignored.
3. §3.3: reconstructed raw closes and Data/prices dollar volume for test-month ranking sessions.
4. §5.1: ATOM total-return close as AdjClose for 40 ids.
5. §5.2: one class per company in the sector pool, leave-own-company-out; 2022 pool from the first
   snapshot; GICS level 1 only.
6. §5.4–5.6 and A1.2 clarifications: z_vol minimum, floor order, mixed-window z scale, unclipped multi-day
   z, delisting hold, warmup purge.
7. §3.3, revision 2 (F1): CIQ shares cross-checked against Yahoo's share count, which replaces them when
   CIQ is missing or > 1.5× off.
8. §3.3 / §5.1, revision 2 (F2): raw price-level check from dividend factor jumps (HON × 2); test-month
   price levels dropped from `tiers_monthly`.
9. §5.4 / §3.3, revision 3 (F3): ATOM raw volume days already on a later split's basis are restored;
   dollar volume of a level-flagged id uses volume ÷ the level factor.

PRD-level choices without a PREREG change: Spearman for mapping validation; non-member panel rows capped
at 60 sessions after an exit; test inputs without σ_on / σ_id; AC2's tier clause tested as the PIT property.

## 7. STOP conditions and owner decisions

No STOP condition fired. There was no spend, no FMP, no write to ATOM (equal counts, read-only
transaction), and no read of a blinded file.

Owner decisions requested:
1. Confirm the nine PREREG §15 rows (committed on `main` at the operator's request when merging).
2. **AC3(c):** accept the yield-slope criterion (|slope| < 0.1, factor jump = D/P) in place of the 3 bp
   bound. The +5.8 bp ex-date AR_on does not scale with the dividend.
3. The 40 ids without Data/prices: accept the ATOM total-return fallback, or provide adjusted closes. For
   the 19 of them that are members in 2026, close-based t−1 features become NaN within the test period.
4. NA-04: GICS industry is unavailable (level 1 only).
5. Git: the branch is cut from `feat/NA-00-scaffold`; rebase onto `main` after the NA-00 merge.
6. `.env` was not created. The export received the password in its environment, read from ATOM's `.env`.
7. **Share sources (F1):** confirm Yahoo as the independent reference and substitute. Confirm the
   all-class count where CIQ has Class A only (BX, IBKR, ARES, CVNA, SATS), in line with PREREG §3.2's
   "sum over classes". Three known Yahoo errors (DOC before 2024-03, UDR 2023, PSKY 2026) change ranks
   but no tier.
8. **HON (F2):** confirm the price-level correction. ATOM's HON prices should also be reported to the
   ATOM owner: the raw series is halved together with a 0.5 split row on 2026-06-29.

## 8. Files

- **Added:** `scripts/{export_atom_snapshot,register_snapshot,na01_report}.py`;
  `src/newsaction/panel/{__init__,grid,mapping,adjust,sector,risk,tiers,targets,reactions,build}.py`;
  `docs/decisions/NA-01.md`; `artifacts/NA-01/{REPORT.md,summary.json,*.csv}`.
- **Tests added (124):** `test_export_snapshot` 9, `test_panel_adjust` 34, `test_panel_calendar_equality`
  2, `test_panel_mapping` 5, `test_panel_pit` 5, `test_panel_sealing` 12, `test_panel_sector` 3,
  `test_panel_targets` 9, `test_panel_tiers` 39, `test_panel_universe` 6. Revision 2 added 22: the
  level check, the cross-check rule, the Yahoo guards, share goldens through the code, verifier tier
  goldens, and blank test-month price columns.
- **Revision-2 tables:** `share_substitutions.csv`, `raw_level_check.csv`,
  `tier_changes_vs_first_build.csv` (one-off diff against the first build's tiers).
- **Revision 3:** `adjust.volume_basis_check`, traded-level dollar volume in `build._ranking_inputs`,
  `mapping.volume_basis_days`, table `volume_basis_check.csv`; 5 tests in `test_panel_adjust` (pending-
  split products, untouched non-split discrepancies, the real-data golden, traded-level dollar volume,
  the panel result).
- **Changed:** `configs/availability.yaml` (every panel column registered); `docs/DATA_CONTRACT.md` (NA-01
  sections, 19 artifacts); `tests/conftest.py` (artifact fixtures); `ledgers/test_access.jsonl` (2 `write`
  entries).
- **Changed, committed on `main` separately:** `docs/PREREG.md` (§15 rows).
- **Derived (gitignored):** `work/snapshot/` (13 files incl. 2 blinded), `work/panel/` (6 files),
  `work/MANIFEST.json`.
- **`make verify`:** exit 0. ruff "All checks passed!", 45 files formatted; mypy --strict "no issues found in
  20 source files"; pytest **347 passed, 1 xfailed** (the literal AC3(c) bound; 342 before revision 3); manifest OK (24
  artifacts, 6 inputs); ledgers OK (test_access 2).
