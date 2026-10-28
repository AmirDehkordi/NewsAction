# NA-12 REPORT — unblinding and the pre-registered analyses

Date: 2026-10-28 · Branch `feat/NA-12-analysis` (main checkout, cut from main @ 6215740) · Decisions:
`docs/decisions/NA-12.md` · PREREG: two §15 rows, one written before unblinding (the operationalization) and one
after (figure data and code fixes) · Numbers: `artifacts/NA-12/results/*.json`, `tables/*`, `figure_data/*`.

**Unblinded once.** `NA_UNBLIND=1 python -m newsaction.analysis.unblind run` ran once, with the variable set for
that command only. `lock.require_unblind` passed: the freeze hash `523e7589…` equals `artifacts/NA-11/freeze.json`
and the Deviations log was an unchanged prefix. `ledgers/test_access.jsonl` holds one "targets" sequence: 8 reads
from 19:18:32 to 19:19:17 UTC, followed by 5 "reactions" reads, all allowed and all after the freeze (10:38:58
UTC). The outcomes went to `work/analysis/targets_test.parquet` (73,498 rows, 145 test sessions); everything
after reads 2026 outcomes from that file only. The price-only D2 test predictions came first, after reproducing
NA-09's validation predictions exactly.

**Bottom line (test split, 2026-01-02 → 2026-07-31).**
- **Primary hypotheses.** None is supported for the primary instrument, Laya-Fin. The Holm-adjusted p of H1,
  H1b, H2, H3 and H4 are 0.85, 0.85, 0.85, 0.27 and 0.85; the §1.3 verdict is "not supported" for all five.
- **Laya-Fin's IC.** Its daily IC of N̂_W0 with z_cc fell to +0.020 (t 1.7) on test, from +0.065 (t 3.6) on val-B.
- **The anchor.** Its readings are uninformative (near-constant N̂, a uniform continuation head). It is reported
  next to every primary result but cannot confirm or refute one.
- **The screen-failing API models** (model-specific, §1.3). d1-ultra, span-02 and drex-v2.0 price the news
  at the open: H1 = +0.075 (p 0.0001 each). That comes from IC with z_on ≈ +0.075 against IC with z_id ≈ 0.
  Their H1b, H2, H3 and H4 are all null.
- **Secondary.** Laya-Fin's H5 holds (BH q 0.058): its W2 news explains 0.25% of stock-specific daily variance
  out of sample. Its H7, H2-C tests and every heterogeneity cut are null. For d1-ultra, H5 holds (q 0.0007);
  H6, θ (A3.4) and H2-C fail BH.
- **Convergence (A1).** The price moves part of the way to V by the close of day t and no further: κ is 0.36
  (Laya-Fin) and 0.59 (d1-ultra) at C_t, then fades. λ ≈ 0, the half-life is "never within t+20", and the
  tracking error is no better than a naive 0.
- **The highest test ICs** belong to two vendor-label baselines: tags-GBM +0.055 and vendor sentiment +0.047.
  The vendor labels were produced retrospectively (CLAUDE.md A6), so these two ICs may carry look-ahead (§10).
- **Exploratory, requested after unblinding, no claim (§13).**
  - *Earnings days.* Every signal's D0 IC is concentrated on earnings-day events (8% of test events). There it
    held from validation to test: Laya-Fin +0.13 and d1-ultra +0.22 on test.
  - *The val→test decline.* It is off earnings days and is common to every signal, the vendor baselines
    included.
  - *Months.* No signal shows a month effect (F test p ≥ 0.16), so the June–July dip of §10.5 is consistent
    with chance.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| Pre-unblinding: operationalization row, code, rehearsal | done | PREREG §15 NA-12 row "before unblinding"; `src/newsaction/analysis/{unblind,slot_path,price_only_d2,run_all,figdata,tables,contract}.py`, `frames.py` (extended); rehearsal `artifacts/NA-12/unblind_rehearsal.json` |
| S1 unblind | done | `analysis/unblind.py`; `work/analysis/targets_test.parquet`; `artifacts/NA-12/unblind.json`; `ledgers/test_access.jsonl` (+13 lines) |
| Price-only D2 test predictions (operator item 4) | done | `analysis/price_only_d2.py`; `work/analysis/price_only_d2_test.parquet` |
| S2 run all | done | `analysis/run_all.py` (13 sections); `artifacts/NA-12/results/*.json` (13), `figure_data/*.csv` (7); `work/analysis/{frame_d0,frame_d2}_{laya_fin,anchor,d1_ultra}.parquet`, `h3_predictions.parquet` |
| S3 tables | done | `analysis/tables.py`; `artifacts/NA-12/tables/` (20 tables × CSV + LaTeX, `keys.json`, `index.json`) |
| S4 report | done | this file; `docs/decisions/NA-12.md`; `docs/DATA_CONTRACT.md` (NA-12 section, `analysis/contract.py`) |
| Tests | done | `tests/test_unblind_lock.py`, `test_run_all_params.py`, `test_tables_keys.py` (the PRD's three), `test_price_only_d2.py` |
| Exploratory: where the D0 signal lives (operator request after unblinding) | done | `analysis/exploratory.py`; `artifacts/NA-12/results/exploratory_d0_signal.json`; `tests/test_exploratory.py`; §13 |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 lock | `artifacts/NA-12/unblind.json`: `freeze_hash` 523e7589… = the record; `ledgers/test_access.jsonl`: one "targets" sequence of 8 entries (19:18:32–19:19:17 UTC, callers `targets.build_targets`, `targets.build_d1_targets`, `analysis.unblind.run`), all after the freeze (10:38:58 UTC); `unblind check` now reports `targets_entries: 8, ready: false` (a second run refuses) | PASS |
| AC2 verbatim | `git diff prereg-freeze HEAD -- docs/PREREG.md configs src/newsaction/panel/{targets,reactions}.py src/newsaction/analysis/{spec,inference,shapley,metrics}.py`: PREREG +5 rows in §15 only (3 earlier post-freeze rows, NA-12's two); the freeze hash recomputed equals the record. `run_all` calls `spec`'s functions; the two places that rebuild a spec intermediate (H3's coalition predictions for storage, the plateau rows) are checked to reproduce the spec's own output exactly | PASS |
| AC3 inference | `tests/test_run_all_params.py`: the test run's configuration is `spec.load_config()` itself with PREREG's numbers; spies on `inference.ols_fe` (FE session × tier, clusters session and company, Driscoll–Kraay 5 lags), `metrics.Bootstrap.draw` (10,000 reps, block 5, seed 2026) and `metrics.holm` (H1, H1b, H2, H3, H4); BH q 0.10 for the secondary and heterogeneity families | PASS |
| AC4 completeness | `python -m newsaction.analysis.tables`: 20 tables, 10,509 keys, `missing: []` against `tables.required()` (each primary and secondary test, all 8 cuts, every κ_h rung in three variants plus the plateau, every λ rung at D1 and D2 with and without clean windows, the half-lives, tracking ratios per rung, the cuts by tier, quantified flag and \|G\| bin, the A2.5, A3.2–A3.5 rows, the robustness items not run). `tests/test_tables_keys.py` checks every key against its CSV cell | PASS |
| AC5 headline rule | `t1_primary` carries the anchor's estimate, CI and p next to Laya-Fin's in every row; §3 below states both for each hypothesis | PASS |
| GAC1 | `make verify` exit 0 (§16) | PASS |
| GAC2 | `git status --porcelain Data/` empty | PASS |
| GAC3 | one "targets" sequence; `tests/test_blinding.py` passes (no 2026 literal or sealed-path use in `src/` outside `lock.py`) | PASS |
| GAC4 | no API call: `ledgers/spend.jsonl`, `trials.jsonl`, `fmp_requests.jsonl` unchanged against main; NA-12 spend $0 | PASS |
| GAC5 | `docs/DATA_CONTRACT.md` NA-12 section (74 files, with §13's results file) with sha256 equal to `work/MANIFEST.json`; `python -m newsaction.io check` OK | PASS |

### 2.1 Mutations

A session script applied each mutation, cleared `__pycache__`, ran the guard's test and restored the file (sha256
checked; `git status` clean afterwards). All 14 RED: `run` skips `require_unblind`; `run` skips the
one-sequence guard; `assemble` ignores inconsistent outcomes; the test run uses the rehearsal configuration; Holm
runs on the anchor's p; `run_all.run` does not wait for the unblinding; H7 leaves Laya-Fin's secondary family;
`check_models` accepts other roles; `test_targets` accepts member rows missing from the test inputs; tables accept
duplicate keys; `cite` renders unknown keys; the price-only D2 check tolerates any difference; the D2 step imports
LightGBM at import time; `required()` forgets the gap rungs.

## 3. S1 unblinding and the price-only D2 step

**Unblinding.** `targets.build_targets` and `targets.build_d1_targets` for "test" gave the outcomes;
`reactions.build_reactions` at D2 and D1 gave G and the 10:00 rung, the routes the NA-11 Call B states used. The
same-day columns came from `panel.build.test_returns_panel` on the blinded prices (read with purpose "targets").
z_cc and z_on came from `panel.risk.zscore`, the function NA-01 used (the panel exposes AR, σ and z_id only). The
day-t 30-minute path (figure data) is NA-10's D1 arithmetic with the 10:00 price replaced by each bar's close.

Before any sealed read, a rehearsal on val-B through the public routes ran the same assembly. It reproduced 59
columns of `panel_public` / `intraday_public` (largest difference 6.6e-14), and the path's first point equalled
the frozen 10:00 rung exactly. On test, the three consistency gaps (y0 = z_id, g_d2 = z_cc, path point 0 = the
10:00 rung) are 0. The run took 106 s, peak 5.0 GB. The test-period rows of the returns panel (members and
post-exit rows): 73,498 rows, 145 sessions, 519 symbols.

**Price-only D2** (post-freeze §15 row; NA-11 REPORT §7.1 item 1). NA-09's y2 booster and `D2_FEATURES` were used
unchanged. The same feature code first reproduced NA-09's 18,976 val-A and val-B D2 predictions exactly (largest
|Δ| 0.0). It then predicted the 18,625 test Call B D2 events, with G, z_on and z_vol of t taken from
`targets_test`. Missing inputs take LightGBM's missing branch, as at D0: z_on 390, the σ regime 334, momentum
154, z_vol 4. Test IC of y_hat with y2: +0.012 (t 1.2, p 0.13).

## 4. Primary hypotheses (Holm over H1, H1b, H2, H3, H4 at 0.05; §1.3 headline rule)

Test split outside the embargo; one-sided p. Laya-Fin is the primary instrument (laya-s13); the anchor is
anchor-s13. **The anchor's readings are uninformative** (NA-11 REPORT §7.1 item 4): its val-A Call A N̂ has an SD of
0.006 against Laya-Fin's 0.105, and its continuation head is uniform (temperature at NA-08's bound of 20). Its
direction, H2 and continuation numbers below are reported as uninformative, not as nulls. §1.3 is still applied
as frozen; since no Laya-Fin p survives Holm, the anchor decides no verdict.

| Hypothesis | Laya-Fin | p | Holm p | Anchor | anchor p | Verdict (§1.3) |
|---|---|---|---|---|---|---|
| H1 | +0.0046 [−0.035, +0.041] | 0.41 | 0.85 | +0.0036 [−0.027, +0.034] | 0.41 | **not supported** |
| H1b | +0.0105 [−0.014, +0.037] | 0.21 | 0.85 | +0.0020 [−0.019, +0.022] | 0.43 | **not supported** |
| H2 (D2) | b −0.044, c −0.0149 | 0.62 | 0.85 | b +0.75, c −0.0150 | 0.29 | **not supported** |
| H3 | +0.0038 [−0.0008, +0.0085] | 0.054 | 0.27 | +0.0013 [+0.0002, +0.0024] | 0.017 | **not supported** |
| H4 | +0.0012 [−0.0017, +0.0042] | 0.22 | 0.85 | −0.0004 [−0.0016, +0.0007] | 0.77 | **not supported** |

### 4.1 H1 — priced at the open

*Pre-registered:* for D0 events, mean daily IC(N̂_W0, z_on) − IC(N̂_W0, z_id) > 0 (stationary block bootstrap over
sessions).
*Result:* Laya-Fin +0.0046 (95% CI −0.035 to +0.041; NW t 0.23; 138 sessions, 13,748 events): IC with z_on
+0.015 (t 1.1), with z_id +0.010 (t 0.8). Anchor +0.0036 (p 0.41).
*Verdict:* **not supported** (Holm p 0.85). Model-specific comparators (screen-failing): d1-ultra +0.075 (CI
+0.041 to +0.109, p 0.0001), span-02 +0.075 (p 0.0001), drex-v2.0 +0.075 (p 0.0001), Laya zero-shot +0.054 (p
0.001). For each API model, IC with z_on is about +0.075 (t 4.5–5.3) and IC with z_id about 0; their quintile
spreads of z_on are 0.76–0.81σ a day (t 5.6–6.2).

### 4.2 H1b — not fully priced at the open

*Pre-registered:* mean daily IC(N̂_W0, z_id) > 0 on H1's sample and draws.
*Result:* Laya-Fin +0.0105 (CI −0.014 to +0.037; t 0.82). Anchor +0.0020 (p 0.43). Comparators: d1-ultra −0.0007,
span-02 −0.0005, drex-v2.0 +0.0019, Laya zero-shot −0.017 (none significant).
*Verdict:* **not supported** (Holm p 0.85). No model's N̂ predicts the open-to-close move. The S-D0 strategy
(NA-13), which enters at the open, has no pre-registered support here.

### 4.3 H2 — explained moves persist, unexplained moves reverse (central)

*Pre-registered:* y2 = a + b·N̂_W2 + c·G + day × tier FE at D2, b > 0 and c < 0 one-sided, two-way clustered SEs; p =
max(p_b, p_c).
*Result:* Laya-Fin b = −0.044 (SE 0.149; p 0.62; Driscoll–Kraay p 0.62), c = −0.0149 (SE 0.012; p 0.11; DK p
0.12); 17,188 events, 135 sessions, 500 firms. Anchor b +0.75 (SE 1.38; uninformative scale: its N̂ barely varies),
c −0.0150. d1-ultra b −0.076 (SE 0.031; p 0.99), c −0.0115 (p 0.17).
*Reported, not in the family:* at D1, Laya-Fin b +0.23 (p 0.062), c +0.013 (p 0.86); at D0 (y0 = z_id), b +0.28 (p
0.096). Within |G| bins (< 1, 1–2, > 2) no b or c is significant for any model (`t2_h2_over_under`).
*Verdict:* **not supported** (Holm p 0.85). The reversal coefficient c has the predicted sign for every model but
is not significant (p 0.11–0.17).

### 4.4 H3 — complementarity of the judgments J

*Pre-registered:* ΔIC = IC(R+N+J) − IC(R+N) for y2 > 0, ridge with the §11.5 protocol (fit val-B 2025-10-08 …
2025-12-23, λ on val-A, evaluated on test).
*Result:* Laya-Fin +0.0038 (CI −0.0008 to +0.0085; p 0.054; 135 sessions, 17,044 events). Anchor +0.0013 (CI
+0.0002 to +0.0024; p 0.017) — its J features come from a uniform continuation head (probabilities within 0.0008 of
1/3), so this is uninformative. d1-ultra +0.0007 (p 0.29). The protocol chose λ = 10⁴ (the grid's largest) for
every coalition of every model, and the full model's out-of-sample R² of y2 is about −0.002 for all three models.
*Verdict:* **not supported** (Holm p 0.27).

### 4.5 H4 — width (materiality and surprise predict |z_cc|)

*Pre-registered:* out-of-sample ΔR² of the news readings for |z_cc,t| over HAR + earnings + tier > 0. **R²
reference** (operator item 6): Σ(y − ȳ)² around the mean |z_cc| of the val-B events (1.245), as the frozen spec
fixes; NA-09's table used the mean over all train ticker-days (0.957) and its grid the train event days (1.289).
*Result:* Laya-Fin (E|N̂| and the H-mag expected level) +0.0012 (CI −0.0017 to +0.0042; p 0.22; 140 sessions); the
HAR benchmark's R² is 0.284. Anchor −0.0004 (p 0.77). d1-ultra (materiality, surprise, E|N̂|) +0.0004 (p 0.35);
A2.5's U_unc and P(no_material_effect) add +0.0001 (p 0.25). Laya zero-shot −0.0013 (p 0.99).
*Verdict:* **not supported** (Holm p 0.85). The magnitude readings rank |z_cc| (AUC for |z_cc| ≥ 1: Laya-Fin's
H-mag 0.60) but add nothing beyond realized volatility.

## 5. Secondary hypotheses (BH q = 0.10 within each instrument)

The families are those of the §15 NA-12 row written before unblinding. H6 needs tone and A3.4 needs the
explanation answer (Q16), which the trained models do not give: "not available" for them.

| Test | Laya-Fin | p | q | d1-ultra (model-specific) | p | q |
|---|---|---|---|---|---|---|
| H5 (ex-post W2 news step, OOS R² > 0) | +0.0025 | 0.010 | **0.058** | +0.0082 | 0.0001 | **0.0007** |
| H6 (tone × sign(N̂) < 0 in H2) | n/a | | | d = +0.010 (SE 0.019) | 0.70 | 0.95 |
| H7 (ΔIC Laya-Fin − Laya zero-shot) | +0.0146 [−0.007, +0.036] | 0.097 | 0.24 | n/a | | |
| H2-C κ_t+20 > 0 | +0.26 (SE 0.23) | 0.13 | 0.24 | +0.37 (SE 0.22) | 0.047 | 0.16 |
| H2-C κ_t+20 − κ_O_t > 0 | +0.02 [−0.36, +0.49] | 0.47 | 0.56 | −0.18 [−0.53, +0.22] | 0.83 | 0.95 |
| H2-C λ_t+5 > 0 (D2) | +0.026 (SE 0.026) | 0.16 | 0.24 | +0.022 (SE 0.026) | 0.21 | 0.48 |
| H2-C tracking ratio vs naive < 1 (t+20) | 1.001 | 0.87 | 0.87 | 1.000 | 0.78 | 0.95 |
| A3.4 θ > 0 (D2) | n/a | | | −0.062 (SE 0.038) | 0.95 | 0.95 |

- **Pooled sensitivity family** (Laya-Fin's six plus d1-ultra's H6 and A3.4): Laya-Fin's H5 q 0.078; nothing else
  below 0.10.
- **The anchor's family**: H5 +0.0003 (q 0.36); every H2-C test q ≥ 0.39 (uninformative).
- **H7 on val-B** (reported): Laya-Fin − zero-shot +0.035 (p 0.040); the anchor − zero-shot −0.049 on val-B and
  +0.002 on test.
- **H7's calibration (ECE before and after temperature)** is in §10.3.

**H5 verdict: supported for Laya-Fin** (the only secondary test that survives BH). The share is small: news
published up to the close explains 0.25% of the stock-specific daily variance of covered member-days out of
sample, 0.13% of it already before the open. **H6, H7, H2-C, A3.4: not supported.**

## 6. Heterogeneity (8 cuts; one BH family for Laya-Fin)

Wald test of N̂·1[cut] and G·1[cut] added to H2 at D2 (`t5_heterogeneity`). Laya-Fin: no cut differs (p 0.16–0.90,
q ≥ 0.74). The tier cuts are Top-100 (4,516 events), Mid (5,121) and Rest (7,551); quantified (15,030 in), \|G\| < 1
(9,795), press wire (9,655), low usual coverage (8,387) and busy day (7,805). Within-cut b and c are reported in
the table. The anchor (q ≥ 0.47) and d1-ultra (smallest p 0.038 for the Rest tier, q 0.30) are reported, not
claimed.

## 7. Convergence to the news-implied value (A1, H2-C)

V = the frozen val-A isotonic map of N̂ to E[E5^lvl]; CAR^lvl in typical-daily-move units (`t6`–`t9`).

| κ_h (CAR^lvl_h on V, day × tier FE) | O_t | 10:00 | C_t | t+1 | t+2 | t+5 | t+10 | t+20 | plateau t+16..20 |
|---|---|---|---|---|---|---|---|---|---|
| Laya-Fin | 0.24*** | 0.27*** | 0.36*** | 0.36*** | 0.38*** | 0.26* | 0.21 | 0.26 | 0.27 |
| d1-ultra (model-specific) | 0.55*** | 0.61*** | 0.59*** | 0.54*** | 0.47*** | 0.36** | 0.25 | 0.37* | 0.37* |
| anchor (uninformative) | 0.08 | −0.02 | −0.04 | −0.04 | −0.03 | −0.06 | −0.03 | 0.08 | 0.08 |

One-sided p: *** < 0.001, ** < 0.01, * < 0.05.

**Answer to "does the price converge to the model's value, how fast, how completely?"**
- **Laya-Fin.** The price moves toward V on day t and no further. About a quarter of V is in the price at the open
  and a third by the close; after day t, κ falls back, and the increase from the open to t+20 is +0.02 (p 0.47).
- **d1-ultra.** It has the same shape, larger: 55% at the open, 61% at 10:00 and 59% at the close, then a partial
  give-back to 36–37% at t+5…t+20.
- **Gap closure.** U = V − G^lvl closes by λ ≈ 0 at D2 (Laya-Fin λ_t+1 −0.007, λ_t+5 +0.026, λ_t+20 +0.050; all p ≥
  0.16) and at D1 (all λ ≤ 0). The half-life is "never within t+20" for every model, CI included. The λ are almost
  the same for every model, because V is small next to G^lvl: U ≈ −G^lvl, and λ measures the reversal of the day's
  move, not convergence to V.
- **ψ_h\*.** ψ_t+20 is −0.24 (two-sided p 0.21) for Laya-Fin and −0.13 (p 0.42) for d1-ultra (outside every
  family).
- **Tracking error.** RMSE(CAR^lvl_h − V) relative to a naive 0 is 1.00–1.02 at every rung for Laya-Fin
  (0.995–1.002 for d1-ultra), and about 1.00 relative to the price-only V.
- **Robustness.**
  - *Clean windows:* the short rungs hold (Laya-Fin κ_C_t+1 0.33, p 0.03). The long rungs have too few clean
    events (t+20: 205) to say anything.
  - *h\* = t+10:* the increase from the open to t+10 is −0.03 (p 0.58).
  - *Plateau:* as above (0.27, p 0.11).
- **By cut.**
  - *Tier:* Laya-Fin's κ_C_t is 0.75 for Top-100 against about 0.25 for Mid and Rest.
  - *Quantified vs story:* d1-ultra's own "numbers" label gives κ_t+20 = 0.78 (p 0.002) against −0.04 for
    "narrative". The vendor flag points the same way (0.39 vs 0.26).
  - *\|G\| bins:* no λ is significant.

**H2-C verdict: not supported** for Laya-Fin (q ≥ 0.24) and, after BH, for d1-ultra.

**Figures 1–2** (`figure_data/fig1_*`, `fig2_drift_vs_g.csv`; descriptive):
- *d1-ultra's top V decile* (mean V 0.77): +0.45 at the open, +0.55 at 10:00, +0.51 at 15:30, +0.53 at the close,
  +0.37 at t+5, +0.36 at t+20.
- *d1-ultra's bottom decile* (mean V −0.64): −0.40 at the open, −0.43 at the close, −0.13 at t+5, −0.33 at t+20.
- *Laya-Fin's deciles* are ordered the same way but at about a quarter of the size.
- *Pre-event drift* runs in the direction of V: d1-ultra's bottom decile lost 1.5 typical moves from t−5 to t−1.
  The states carry the company's recent abnormal performance in words, so part of N̂ reflects momentum.
- *Signed RG classes* (D2, d1-ultra; sign(N̂)·CAR): "Under" events (5,021) moved against the news on day t (−0.95)
  and stay there through t+20 (−1.04). "Over" events (1,783) gave back 0.33 of +3.16 by t+20. "Fair" (2,113) stay
  near +0.7. Laya-Fin has only 146 events with |N̂| ≥ 0.5.
- *Figure 2:* moves with |G| ≥ 3 reverse in every news-strength tercile (mean sign(G)·y2 −0.10 to −0.18); smaller
  moves do not.

## 8. Explaining realized moves (A3, Kelly–Su–Zhang style)

Covered member-days of the test split; out-of-sample shares of stock-specific daily variance (z_cc) by cumulative
step (`t10`, `t11`, `fig8_explanation_ladder.csv`). Step 1, market + sector (Roll's baseline): R² 0.25 of total
daily variance.

| Step (OOS R² of z_cc) | Laya-Fin | anchor | d1-ultra (model-specific) |
|---|---|---|---|
| + ex-ante news (D0) | 0.0013 | 0.0001 | 0.0028 |
| + ex-post news (W2, Call A) | 0.0025 (H5) | 0.0003 | 0.0082 (H5) |
| + explanation (X, X·N̂_W2, reason × N̂_W2; Call B sees the move) | — | — | 0.158 |
| share knowable before the open (ex-ante ÷ ex-post) | 53% | 36% | 35% |

- **By cut.** d1-ultra's explanation step reaches 0.375 on event days (non-event days: no news by construction)
  and 0.14–0.20 by tier. By its own event type it is 0.40 for earnings, 0.43 for analyst actions and 0.38 for
  deals; guidance and legal / regulatory overfit (negative OOS).
- **Explained share** (A3.3). Days judged explained (X ≥ 0.5) are 16% of events but carry 41% of event-day Σz_cc²
  (Top-100 41%, Mid 42%, Rest 40%). By reason: earnings carries 57% of the variance and 54% of it falls on
  explained days; "no identifiable news" carries 14%, with 2% explained.
- **θ** (A3.4: explanation → persistence). −0.062 at D2 (SE 0.038, p 0.95) and −0.040 at D1 (p 0.87): explained
  moves do not persist more; the sign points to slightly more reversal. Persistence by move_reason: no reason
  shows positive persistence (sign(G)·y2 between −0.17 and +0.06; none significant).
- **Market replication** (A3.5, exploratory). SPY's daily return on d1-ultra's market reading, fit on 127 val
  sessions: OOS R² +2.1% (CI −6.6% to +10.7%, p 0.31) on 144 test sessions.

The ex-post explanation step is not a prediction: Call B reads the realized move. It measures how much of the move
the model can attribute to the day's news, which is Kelly–Su–Zhang's quantity at the firm level.

## 9. Question battery v2 (A2.5; d1-ultra's extended answers)

- **Mechanism cuts** (`t12`). H2's b is not significant within any model or vendor event type, nor within either
  quantified label. The ladder by d1-ultra's own labels is in §7: numbers 0.78 vs narrative −0.04 at t+20.
- **Horizon validity.** Spearman(H, share of the t+20 move realized by C_t) = −0.068 (CI −0.093 to −0.040, p <
  0.001; 9,683 events with |CAR^lvl_t+20| ≥ 1). As predicted: a longer expected horizon means less of the move
  on day t.
- **H4 width.** U_unc and P(no_material_effect) add ΔR² +0.0001 (p 0.25).
- **Reading validity** (NA-06, val-A, 500 events, reported only). d1-ultra agrees with the vendor's event type 57%
  of the time (45% with the raw tag), with the quantified flag 49%, with the earnings calendar on "scheduled" 55%,
  and with `tag_rumor` on credibility 99%.

## 10. Model comparison, probes, Shapley, monthly IC, calibration

### 10.1 Model comparison (`t14_model_comparison`)

Daily IC of N̂_W0 with z_cc on each model's events; on test, every decision model answered the same 13,748 events.

| Model | Role | IC val-B (t) | IC test (t) | Cost / 1,000 | Latency p50 / p95 |
|---|---|---|---|---|---|
| Laya-Fin | primary (laya-s13) | +0.065 (3.6) | +0.020 (1.7) | $0 (Kaggle free tier) | batch |
| anchor | clean anchor | −0.020 (−1.5) | +0.008 (0.8) | $0 | batch |
| Laya zero-shot | §10.5 | +0.029 (1.9) | +0.005 (0.4) | $0 (local) | 536 / 758 ms |
| d1-ultra | best API comparator | +0.097 (5.4) | +0.039 (3.2) | $0.064 | 288 / 427 ms |
| span-02 ¹ | core comparator | +0.099 (5.8) | +0.041 (3.1) | $0.028 | 2,262 / 2,459 ms |
| drex-v2.0 | core comparator | +0.075 (4.1) | +0.044 (3.7) | $0.045 | 680 / 1,115 ms |
| vendor sentiment ² | baseline §10.1 | +0.087 (4.4) | +0.047 (3.4) | $0 | — |
| bge-small ridge | baseline §10.2 | +0.002 (0.1) | +0.004 (0.4) | $0 | — |
| vendor tags GBM ² | baseline §10.3 | +0.108 (6.0) | +0.055 (3.9) | $0 | — |
| price-only (D0) | baseline §10.4 | +0.004 (0.3) | −0.003 (−0.3) | $0 | — |
| mistral-nemo (2,000-event subsample) | baseline §10.7 | +0.052 (1.9) | +0.001 (0.0) | $0.020 | — |

- **Notes to the table.**
  - The API models' val-B ICs here use all 5,506 val-B D0 events. NA-11's §8.5 table used NA-07's 1,500-event
    sample.
  - On the LLM's 1,977 test events, Laya-Fin's IC is −0.012 (t −0.4).
  - The price-only D2 reading's IC with y2 is +0.012 (t 1.2).
  - Costs include answers paid by earlier chunks.
  - ¹ span-02: S5's canary fired a STOP; the operator chose to proceed (PREREG §15, post-freeze NA-11 row).
  - ² The vendor labels were produced retrospectively (CLAUDE.md A6; NewsWitch's `_ts` lags publication by about
    17 h). The two vendor-label baselines may therefore carry look-ahead that the masked decision-model states
    cannot. Their ICs are an upper bound, not a fair benchmark.
- **The API models' H1 holds in every robustness variant** (§11), and unmasking does not raise d1-ultra's IC
  (§11.2). Their test ICs are about half their val-B ICs.

### 10.2 Disclosed val-A probes (NA-11; not hypotheses)

`t18_probes_val_a` reproduces NA-11's `probes_val_a.csv` next to the comparison. The API models fail the frozen
§8.3 screens: company identification 0.62–0.74 (0.66–0.74 for the three comparators run here, against a bar
of 0.40), and flip rates below 0.70 for d1-ultra (0.68) and span-02 (0.65); drex-v2.0's is 0.71. Laya-Fin's right_way share is 0.80, its edit shift 0.20 of its own SD (t 7.3), and its real
minus shuffled IC +0.019 (t 0.5, inconclusive). The anchor's right_way share is 0.435 (chance).

### 10.3 Calibration (§11.2; `t15_calibration`, appendix `appendix_reliability.csv`)

Q1's three classes (fall / no move / rise at ±0.5) against e5, with val-A climatology:

| Model | ECE | log-loss skill | Brier skill | AUC (\|z_cc\| ≥ 1) | H7: temperature, ECE before → after |
|---|---|---|---|---|---|
| Laya-Fin | 0.057 | +0.001 | −0.000 | 0.60 (H-mag) | NA-08 T = 1.002: 0.058 → 0.057 |
| anchor | 0.048 | +0.002 | +0.001 | 0.58 (H-mag) | NA-08 T = 0.966: 0.011 → 0.048 |
| Laya zero-shot | 0.176 | −0.156 | −0.110 | 0.52 | val-A T = 6.33: 0.176 → 0.110 |
| d1-ultra | 0.260 | −0.194 | −0.194 | 0.58 | val-A T = 1.95: 0.260 → 0.155 |
| span-02 | 0.361 | −0.460 | −0.361 | 0.56 | no val-A reading |
| drex-v2.0 | 0.209 | −0.135 | −0.138 | 0.57 | no val-A reading |

- **The trained models are calibrated but barely informative** (skill ≈ 0).
- **The zero-shot and API models are overconfident** (negative skill). A single val-A temperature roughly halves
  their ECE.
- **The anchor's ECE rises under its temperature of 0.966.** That is not an error: the file's probabilities
  equal softmax(logits / T) to 1.5e-8. With confidences near 1/3, the 15-bin ECE is sensitive to slight
  sharpening.

### 10.4 Shapley (§11.5; `t13_shapley`, `fig5_shapley_shares.csv`)

The shares of R² and IC over {R, N, J} are reported as computed (Laya-Fin R², R 0.64 / N 0.17 / J 0.19), but they
are shares of a total that is about zero: the full model's OOS R² of y2 is −0.0017 (Laya-Fin), −0.0013 (anchor)
and −0.0019 (d1-ultra), and its mean daily IC −0.001 to −0.005. They carry no information. `work/analysis/
h3_predictions.parquet` holds the seven coalition predictions per test event; the Shapley tables recomputed from
it equal H3's.

### 10.5 Monthly IC (`fig4_monthly_ic.csv`; Figure 4)

The mean daily IC of N̂_W0 with z_cc is positive in most months of 2025 and early 2026 for every model, then about
0 or negative in June and July 2026 for all of them: d1-ultra +0.003 / +0.008, span-02 −0.001 / −0.007, Laya-Fin
−0.023 / −0.006.
- **Release dates.** The API models were released 2026-10-12 to 2026-10-16 (NA-05 catalog), after the whole test
  period. The anchor's checkpoint is from 2024-12.
- **No contamination signature.** Contamination would show as uniformly high test-period IC; the API models show
  the same decline as the clean-period anchor and Laya-Fin. That is consistent with no contamination advantage,
  but it is not a test of it.
- **The June–July drop** is unexplained here and worth a data check (event counts and sources by month) before
  NA-13.
  - *Month effects (§13.3, exploratory).* A one-way F test of the daily ICs on month finds none: test p 0.72
    for Laya-Fin, 0.44 for d1-ultra and 0.16–0.71 for the others. One month's mean IC has an implied SE of about
    0.03, so the June–July dip is within month-to-month noise.

## 11. Robustness (§11.6 and the operator rows (a)–(b); every variant raw and placebo-adjusted; `t16`)

| Variant | Laya-Fin H1 / H1b / IC(z_cc) | Laya-Fin H2 b (p) / c (p) | d1-ultra H1 (p) |
|---|---|---|---|
| main | +0.005 (0.41) / +0.010 (0.21) / +0.020 | −0.044 (0.62) / −0.015 (0.11) | +0.075 (0.0001) |
| dollar-volume tiers | +0.005 / +0.010 / +0.020 | −0.038 (0.60) / −0.014 (0.11) | +0.075 (<0.001) |
| no date-only / hour-stamped article | −0.004 / +0.019 (0.09) / +0.026 | −0.011 (0.53) / −0.018 (0.07) | +0.083 (<0.001) |
| no half day | identical (no test half day in the sample) | identical | +0.075 |
| non-overlapping (≥ 5 sessions) | −0.005 / +0.020 (0.08) / +0.028 | −0.012 (0.53) / +0.005 (0.64) | +0.062 (0.01) |
| no delisting flag | +0.004 / +0.011 / +0.020 | −0.050 (0.63) / −0.015 (0.11) | +0.074 (<0.001) |
| (a) without price-move text | +0.000 / +0.009 / +0.014 | (D0 only) | +0.064 (<0.001) |
| 08:00 W0 cutoff, approximated | +0.002 / +0.007 / +0.018 | (D0 only) | +0.045 (<0.001) |
| (b) latest article before 04:00 | +0.008 / −0.005 / +0.006 | (D0 only) | +0.022 (0.17) |
| (b) latest article 04:00–08:00 | +0.027 / +0.016 / +0.025 | (D0 only) | +0.057 (<0.001) |
| (b) latest article 08:00–09:15 | +0.024 / +0.014 / +0.025 | (D0 only) | +0.122 (<0.001) |
| placebo-adjusted (§5.7) | +0.006 (0.38) / +0.009 (0.25) | −0.044 (0.62) / −0.015 (0.11) | +0.076 (<0.001) |
| σ = 60-session SD | +0.007 (0.37) / +0.009 (0.24) | −0.032 (0.61) / −0.013 (0.11) | +0.075 (<0.001) |
| 2024-H1 (robustness split) | +0.028 (0.24) / +0.024 (0.11) / +0.041 | +0.079 (0.34) / +0.004 (0.61) | +0.153 (0.001) |

Every variant is also run placebo-adjusted (`variants_*_placebo`); no conclusion changes. The anchor's variants are
in `t16` (uninformative).

### 11.1 Ablations (d1-ultra, S8; on the same test events)

- **Unmasked Call A.** On 5,923 events, IC with z_cc is +0.026 masked and +0.029 unmasked; H1 is +0.063 and +0.074.
  Unmasking adds nothing material.
- **Call B without news** (6,086 events). IC of J with y2: −0.020 real, −0.012 without news.
- **Call B with shuffled news** (6,088). IC of J with y2: −0.021 real, −0.001 shuffled. Call B's judgments carry no
  positive information about y2 with or without the news.

### 11.2 Not run

- §11.6's summary-text variant, vendor tags in text and the 09:30 W0 cutoff: not run (§15 NA-11 operator
  decision; they need new states and calls). The 08:00 cutoff is approximated above.
- Gated S-D1: not run (no frozen gate; NA-13).
- The trained models' unmasked and shuffled checks exist on val-A only (§10.2).
- S8's 210 rate-limited ablation requests were not retried (operator); they are missing, which is unrelated to
  content.

## 12. Exploratory (outside every family; no claim)

- **Sector ICs** (`t17_sector_exploratory`).
  - *Laya-Fin:* the IC by GICS sector ranges from −0.046 (Energy) to +0.100 (Real Estate); none has |t| > 2.2.
    Leave-one-sector-out ICs are +0.011 to +0.030, so no single sector drives the main IC.
  - *d1-ultra:* from −0.084 (Utilities) to +0.120 (Energy); leave-one-out ICs +0.030 to +0.043.
- **The day-t 30-minute path** (figure data). d1-ultra's top V decile is +0.45 at the open, +0.55 at 10:00, +0.51
  at 12:30, +0.51 at 15:30 and +0.53 at the close; the bottom decile is about −0.42 all day. The intraday drift
  after 10:00 is flat: the move happens overnight and in the first half hour.
- **Figure-data definitions after unblinding** (§15 NA-12 row "after unblinding"). V deciles rank by N̂, which
  breaks the isotonic V's ties; the RG paths are also given signed. Both are descriptive, and every results JSON
  is unchanged.

## 13. Exploratory: where the D0 signal lives (operator request after unblinding; no hypothesis, no claim)

**How this section was made.**
- **When.** The operator asked for it after the results above had been read. It adds no hypothesis and changes
  no frozen file, definition or family. Every number is exploratory and outside every family.
- **Code.** `src/newsaction/analysis/exploratory.py` writes `results/exploratory_d0_signal.json`
  (byte-identical on a rerun). It calls the frozen `spec` functions: the sample outside the embargo, the daily
  IC (≥ 5 names a session, IC 0 on a constant session), the Newey–West t with 5 lags, and the block-bootstrap
  CIs in the JSON.
- **Signals.** N̂_W0 of Laya-Fin, d1-ultra, span-02, drex-v2.0 and Laya zero-shot, each on its own D0 events, and
  the vendor sentiment and tags-GBM baselines. The vendor labels are retrospective (§10.1, note ²). span-02 and
  drex-v2.0 have no val-A reading.
- **Cross-check.** The operator's assistant had computed several of these numbers independently. This code
  reproduces every one: the earnings z_cc ICs, the test month-effect p (0.72 and 0.44) and the per-company SDs
  (0.214 and 0.199 against a null of 0.197).

### 13.1 Earnings-day events vs the rest

The frame's `earnings` flag marks 482 val-A, 447 val-B and 1,128 test events, out of 8,376, 5,506 and 13,748.
Sessions with at least 5 earnings events: 19, 21 and 56.

Daily IC of the signal with z_cc. Columns: val-A / val-B / test; the t is for test.

| Signal | Earnings days | Other events | Test difference, earnings − other (t) |
|---|---|---|---|
| Laya-Fin | +0.125 / +0.106 / +0.134 (t 3.2) | +0.048 / +0.049 / +0.013 (t 1.0) | +0.138 (2.8) |
| d1-ultra | +0.304 / +0.237 / +0.223 (t 8.1) | +0.057 / +0.062 / +0.018 (t 1.4) | +0.223 (6.1) |
| span-02 | — / +0.201 / +0.235 (t 8.1) | — / +0.066 / +0.019 (t 1.5) | +0.235 (6.2) |
| drex-v2.0 | — / +0.240 / +0.241 (t 9.8) | — / +0.043 / +0.026 (t 2.2) | +0.223 (6.6) |
| Laya zero-shot | +0.093 / +0.102 / +0.103 (t 3.7) | +0.025 / +0.009 / −0.003 (t −0.2) | +0.121 (3.6) |
| vendor sentiment | +0.294 / +0.249 / +0.285 (t 9.5) | +0.039 / +0.058 / +0.022 (t 1.6) | +0.289 (7.9) |
| tags-GBM | +0.277 / +0.255 / +0.304 (t 12.3) | +0.047 / +0.071 / +0.022 (t 1.7) | +0.294 (9.2) |

On test, where the earnings-day signal sits (IC, t):

| Signal | z_on: earnings / other | z_id: earnings / other |
|---|---|---|
| Laya-Fin | +0.069 (1.5) / +0.016 (1.1) | +0.091 (1.6) / +0.008 (0.7) |
| d1-ultra | +0.238 (8.9) / +0.060 (4.5) | +0.034 (0.8) / −0.011 (−0.9) |
| span-02 | +0.264 (9.8) / +0.058 (4.1) | +0.047 (1.1) / −0.010 (−0.8) |
| drex-v2.0 | +0.241 (10.4) / +0.065 (5.3) | +0.057 (1.6) / −0.008 (−0.7) |
| Laya zero-shot | +0.104 (4.4) / +0.033 (2.8) | −0.003 (−0.1) / −0.020 (−1.4) |
| vendor sentiment | +0.327 (8.6) / +0.034 (2.4) | −0.004 (−0.1) / +0.005 (0.4) |
| tags-GBM | +0.295 (6.9) / +0.037 (2.6) | +0.068 (1.8) / +0.006 (0.4) |

- **Earnings days carry the signal, and it is stable there.** For every signal the earnings-day IC is 2–11 times
  the IC on other events on validation and 9–14 times on test (Laya zero-shot's other-event test IC is about 0).
  It did not fall from val-B to test: the changes are −0.014 to +0.049.
- **The val→test decline is off earnings days, for every signal.** On the other events the IC fell from
  0.04–0.07 on validation (Laya zero-shot 0.01–0.03) to −0.003…+0.026 on test, for the vendor baselines too. Laya-Fin's drop from +0.065
  (val-B) to +0.020 (test, §10.1) is this pattern: its earnings-day IC held, and its other-event IC went from
  +0.049 to +0.013.
- **Laya-Fin's validation z_id signal was off earnings days.** It was +0.042 (t 3.2) on val-A and +0.033 (t 1.8)
  on val-B, and +0.008 (t 0.7) on test. This is the signal H1b was added for (§4.2).
- **The API models price earnings news at the open** (z_on +0.24–0.26, z_id not significant). Off earnings days
  they keep a smaller open-gap IC (z_on about +0.06, t 4.1–5.3).
- **Caveat.** Validation has only about 20 earnings sessions per split, so the validation earnings ICs have wide
  CIs (in the JSON).

### 13.2 Size tier

Test daily IC (t); validation in the JSON:

| Signal | Top-100: z_cc / z_on | Mid (101–250): z_cc / z_on | Rest (251–500): z_cc / z_on |
|---|---|---|---|
| Laya-Fin | +0.037 (1.7) / +0.014 (0.6) | −0.001 (−0.0) / −0.006 (−0.2) | +0.027 (1.5) / +0.027 (1.4) |
| d1-ultra | +0.015 (0.6) / +0.015 (0.6) | +0.033 (2.2) / +0.082 (4.0) | +0.060 (3.7) / +0.096 (4.6) |
| span-02 | +0.033 (1.3) / +0.029 (1.1) | +0.018 (1.2) / +0.086 (3.7) | +0.058 (3.4) / +0.091 (4.3) |
| drex-v2.0 | +0.031 (1.2) / +0.038 (1.6) | +0.036 (2.1) / +0.085 (4.2) | +0.062 (3.5) / +0.084 (4.0) |
| Laya zero-shot | +0.027 (1.2) / +0.029 (1.5) | −0.025 (−1.0) / +0.036 (2.0) | +0.010 (0.6) / +0.042 (2.2) |
| vendor sentiment | +0.053 (2.1) / +0.037 (1.3) | +0.029 (1.5) / +0.046 (2.2) | +0.058 (2.9) / +0.070 (3.8) |
| tags-GBM | +0.041 (1.7) / +0.047 (1.8) | +0.053 (3.0) / +0.068 (3.2) | +0.062 (3.0) / +0.075 (4.4) |

- **API models.** On test, their open-gap signal sits in the Mid and Rest tiers (z_on +0.08 to +0.10, t
  3.7–4.6) and is weak in the Top-100 (t ≤ 1.6). On val-B it was present in the Top-100 too (z_on +0.125 to
  +0.141, t 3.3–3.9).
- **Laya-Fin.** No tier stands out on test (the largest is +0.037, t 1.7, in the Top-100). On validation, every
  tier was positive.
- **z_id** is about 0 in every tier for every signal on test (|t| ≤ 1.7).

### 13.3 Month effects

One-way F test of the daily ICs (with z_cc) on calendar month. Degrees of freedom: (2, 56) on val-A and val-B,
(6, 133) on test. The implied SE of one month's mean IC is √(MS_within ÷ mean days a month) (iid), or the
long-run variance of the daily ICs over the mean days a month (Newey–West).

| Signal | F test p: val-A / val-B / test | Implied monthly SE, test: iid / NW | SD of the 7 test monthly means | June / July 2026 IC |
|---|---|---|---|---|
| Laya-Fin | 0.71 / 0.25 / 0.72 | 0.037 / 0.031 | 0.029 | −0.023 / −0.006 |
| d1-ultra | 0.25 / 0.40 / 0.44 | 0.030 / 0.032 | 0.030 | +0.003 / +0.008 |
| span-02 | — / 0.60 / 0.24 | 0.033 / 0.035 | 0.037 | −0.001 / −0.007 |
| drex-v2.0 | — / 0.38 / 0.20 | 0.028 / 0.032 | 0.034 | +0.007 / +0.019 |
| Laya zero-shot | 0.30 / 0.71 / 0.16 | 0.033 / 0.038 | 0.040 | −0.055 / −0.021 |
| vendor sentiment | 0.81 / 0.81 / 0.56 | 0.034 / 0.037 | 0.030 | +0.025 / −0.001 |
| tags-GBM | 0.77 / 0.79 / 0.71 | 0.034 / 0.037 | 0.026 | +0.060 / +0.021 |

- **No signal shows a month effect** on any split (every p ≥ 0.16).
- **The monthly means scatter as noise would.** On test, the SD of the seven monthly means (0.026–0.040) matches
  the implied SE of one month's mean (0.028–0.038). By chance alone, a month's mean IC can sit ±0.06 (2 SE)
  from the period's mean.
- **June–July 2026 (§10.5).** Laya-Fin's June (−0.023) is 1.2–1.4 implied SEs below its test mean (+0.020), and
  d1-ultra's (+0.003 against +0.039) 1.1–1.2. tags-GBM did not dip in June (+0.060).

### 13.4 Per-company rank correlations (test)

Setup:
- For each company with ≥ 15 test events: the Spearman correlation of the signal with z_cc over its events.
  That covers 427 companies and 13,026 events for every signal.
- The null shuffles the signal within each company: 200 draws, seed 2026, the same draws for every signal.
- p = (1 + the number of null SDs ≥ the observed SD) ÷ 201.

| Signal | Mean ρ | SD of ρ | Null SD: mean [2.5%, 97.5%] | p |
|---|---|---|---|---|
| Laya-Fin | +0.016 | 0.214 | 0.197 [0.186, 0.212] | 0.015 |
| d1-ultra | +0.042 | 0.199 | 0.197 [0.183, 0.213] | 0.38 |
| span-02 | +0.040 | 0.204 | 0.197 [0.183, 0.211] | 0.15 |
| drex-v2.0 | +0.050 | 0.201 | 0.196 [0.184, 0.208] | 0.25 |
| Laya zero-shot | +0.009 | 0.189 | 0.197 [0.184, 0.208] | 0.88 |
| vendor sentiment | +0.030 | 0.189 | 0.197 [0.183, 0.211] | 0.86 |
| tags-GBM | +0.057 | 0.211 | 0.197 [0.182, 0.209] | 0.015 |

- **Laya-Fin and tags-GBM.** Their per-company correlations spread more than a within-company shuffle produces;
  each observed SD lies above the null's 97.5th percentile.
  - For Laya-Fin the excess implies a between-company SD of about √(0.214² − 0.197²) ≈ 0.08 around a mean of
    +0.016: its reading tracks z_cc for some companies and runs against it for others.
  - The test cannot tell company-specific skill from company-specific noise in the reading.
  - Seven signals were tested, with no correction.
- **The API models, Laya zero-shot and vendor sentiment.** Their spread is what chance gives (p 0.15–0.88), so
  their signal is spread evenly across companies.

### 13.5 Market state

Days are split into terciles over each split's sessions outside the embargo (test: 47, 46 and 47 sessions).
- **|SPY| close-to-close.** On test, below 0.31% and above 0.79%.
- **Cross-sectional SD of z_cc** over covered member-days. On test, 0.81–1.28 for the low tercile and 1.51–2.94
  for the high one.

Test daily IC with z_cc (t is for high − low):

| Signal | SD of z_cc: low / mid / high | High − low (t) | \|SPY\|: high − low (t) |
|---|---|---|---|
| Laya-Fin | +0.011 / +0.029 / +0.020 | +0.008 (0.3) | +0.011 (0.4) |
| d1-ultra | +0.012 / +0.036 / +0.070 | +0.059 (2.7) | +0.012 (0.5) |
| span-02 | +0.015 / +0.036 / +0.070 | +0.055 (2.2) | +0.004 (0.2) |
| drex-v2.0 | +0.018 / +0.041 / +0.073 | +0.055 (2.5) | +0.021 (0.9) |
| Laya zero-shot | +0.007 / +0.009 / −0.000 | −0.008 (−0.3) | +0.024 (0.8) |
| vendor sentiment | +0.036 / +0.045 / +0.059 | +0.023 (0.8) | +0.004 (0.2) |
| tags-GBM | +0.031 / +0.042 / +0.092 | +0.061 (2.2) | +0.012 (0.4) |

- **Dispersion, on test.** The API models' and tags-GBM's IC rises with the day's cross-sectional dispersion of
  z_cc: +0.07–0.09 on the most dispersed third of days against +0.01–0.03 on the least (t 2.2–2.7). Laya-Fin,
  Laya zero-shot and sentiment show no such gradient.
- **Dispersion, on validation.** No signal has a gradient with |t| > 2 (the largest is tags-GBM on val-A, −0.058,
  t −1.9). So the test gradient is not stable across splits.
- **|SPY|.** There is no gradient on test (|t| ≤ 0.9).
  - On val-B, the API models, Laya zero-shot and both vendor baselines had a higher IC on high-|SPY| days (+0.05
    to +0.08, t 1.7–3.0).
  - On val-A they did not, and sentiment reversed (−0.057, t −2.8).
- **Overlap with §13.1.** The dispersion terciles may overlap the earnings calendar. This section does not
  separate the two.

## 14. Deviations and corrections (in PREREG §15 unless noted)

1. **Before unblinding** (NA-12 row). The operationalization of NA-12's calls of the frozen spec:
   - the unblinding routes and the rehearsal;
   - the price-only D2 step;
   - the primary, secondary and heterogeneity families, per instrument with a pooled sensitivity family (the
     NA-11 verification had found the secondary family unfixed);
   - which model answers which test, and the A3.2 explanation features (X·N̂_W2; one column per Q17 reason ×
     N̂_W2);
   - the descriptive choices: calibration targets, the H7 temperatures, robustness raw and placebo-adjusted, the
     convergence cuts, the figure definitions.
2. **After unblinding** (NA-12 row). Figure 1's data, and three code fixes found when the code first met the test
   rows. The code fixes:
   - the test frame's tier guard (two June-2026 spin-off joiners without a tier, as in the public panel; no event
     falls on them);
   - the trained models' temperatures shown in the calibration table;
   - the tables keep a half-life of ∞.

   No pre-registered number changed, and every results JSON is byte-identical before and after.
3. **Within the frozen plan, reported here.** The anchor is reported as uninformative, not null (operator item 5).
   span-02 carries its footnote. H4 states its R² reference (operator item 6).
4. **Exploratory section after unblinding (§13; operator request).** New code and one new results file only. No
   frozen file, definition, hypothesis or family changed; every other results JSON is untouched. No PREREG
   row (owner decision 4).

## 15. Spend, look-ahead, STOPs, owner decisions

- **Spend.** NA-12 $0. No API call, no Kaggle run, no FMP request (the spend, trials and FMP ledgers are
  unchanged). Cumulative spend stays at $15.73.
- **Look-ahead self-check.** 2026 outcomes were read only after the unblinding, from `targets_test.parquet`.
  Model readings are those NA-11 produced before any outcome was read. Maps, gates and temperatures are NA-11's
  frozen val-A fits; ridge fits use val-B, with λ chosen on val-A. The only new fits are the descriptive H7
  temperatures for Laya zero-shot and d1-ultra, on val-A, recorded before unblinding. No input of a test-period
  decision uses data after its decision time.
- **STOP conditions.**
  - Hash check at unblinding: passed.
  - A failure after the first logged access: none (exit 0, one sequence).
  - Anything needing an API call: no.
  - None fired.
- **Owner decisions.**
  1. **Vendor-label baselines.** Present tags-GBM and sentiment as possibly look-ahead-contaminated upper bounds in
     NA-14, not as the benchmark. *Recommendation: yes; footnote both, and benchmark against bge-ridge, price-only
     and the LLM.*
  2. **June–July 2026 IC collapse** across all models. *Recommendation:* a descriptive data check (events, sources
     and coverage by month) before NA-13. It needs no new hypothesis and no outcome-driven change.
     *Update after §13.3:* no signal shows a month effect (F test p ≥ 0.16), and the dip is within about 1.2
     implied monthly SEs. The check is now optional.
  3. **Anchor robustness runs** after 2026-10-31 (your §15 row). They decide whether the Laya-Fin–anchor contrast
     reflects training. *Recommendation: run them as planned;* they do not affect any verdict above.
  4. **The §13 exploratory section.** It was requested after unblinding, and the REPORT labels it so.
     *Recommendation:* add a one-line PREREG §15 "after unblinding, exploratory" row, so the paper trail dates
     it. Any NA-14 use goes in an exploratory section as post hoc, with no test.

## 16. Files and `make verify`

**Code (new).** `src/newsaction/analysis/`:
- `unblind.py`, `slot_path.py`, `price_only_d2.py`;
- `run_all.py`, `figdata.py`;
- `tables.py`, `contract.py`;
- `exploratory.py` (§13).

**Code (changed).**
- `analysis/frames.py`: the test targets, the S7 readings under the pin, the price-only test reading,
  member-days from given rows.
- `analysis/contract.py`: §13's results file has its own contract entry.

**Tests (new).** `test_unblind_lock.py`, `test_run_all_params.py`, `test_tables_keys.py`, `test_price_only_d2.py`,
`test_exploratory.py` (6 tests: the unblinding precondition, the embargo, the earnings and tier splits, the month
F test, the seeded within-company shuffle, the terciles).

**Docs.**
- `docs/PREREG.md` (two §15 rows);
- `docs/DATA_CONTRACT.md` (NA-12 section, 74 files);
- `docs/decisions/NA-12.md`;
- this report.

**Artifacts** (`artifacts/NA-12/`).
- `unblind.json`, `unblind_rehearsal.json`;
- `results/*.json` (14, with §13's `exploratory_d0_signal.json`);
- `figure_data/*.csv` (7);
- `tables/` (20 × CSV + LaTeX, `keys.json`, `index.json`).

**Work files** (registered).
- `work/analysis/targets_test.parquet`, `price_only_d2_test.parquet`, `h3_predictions.parquet`;
- `frame_{d0,d2}_{laya_fin,anchor,d1_ultra}.parquet`.

**Ledgers.** `ledgers/test_access.jsonl` (+13 lines).

`make verify`, run after the last code change (§13 included; no other NewsAction pytest running), exit 0:

```
ruff check src tests scripts       All checks passed!
ruff format --check                257 files already formatted
mypy --strict src/                 Success: no issues found in 137 source files
pytest -q -m "not network"         1906 passed, 3 skipped, 2 xfailed in 213.19s
manifest                           267 artifacts, 10 inputs checked (size+mtime): OK
ledgers                            OK (test_access.jsonl 26 lines, unchanged by §13)
peak RSS                           9.4 GB
```

Before §13 the same run gave 1,900 passed and 266 artifacts (peak 10.5 GB).
