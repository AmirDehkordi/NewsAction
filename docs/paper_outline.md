# Paper outline: sections → figures and tables

NA-14 (2026-10-29; revision pass the same day). Structure only: no new analysis. The manuscript is an arXiv
preprint in LaTeX (article, 11 pt, US letter, 1-inch margins, one column; text width 6.5 in). Every figure lives
in `artifacts/NA-14/figures/` (PDF, PNG and the CSV of its plotted values), drawn at 6.5 in or 3.15 in and placed
at 100%; every table in `artifacts/NA-14/tables/` (the keyed CSV, and its LaTeX). The captions, with every number
cited from a table, are in `artifacts/NA-14/captions.md`, and `artifacts/NA-14/paper_preview.tex` sets every figure
and table in this order (`make paper-preview` compiles it). Results are stated as found in the NA-12 and NA-13
REPORTs; under PREREG §1.3 every primary hypothesis is **not supported** for the primary instrument, Laya-Fin.

Labels used throughout: the anchor is *uninformative (near-constant outputs)* and stays out of the main figures
(it appears in the appendix and in the main tables beside the primary); the vendor-label baselines (tags-GBM,
vendor sentiment) carry † and are a *possibly look-ahead-contaminated upper bound*, and the clean benchmarks are
bge-ridge, price-only, the LLM baseline and the placebo; span-02 carries ‡ and its S5 STOP footnote (PREREG §15,
post-freeze NA-11 row); the API models fail the §8.3 screens and are model-specific (§1.3).

**Exploratory material appears only in the appendix:** Appendix Figures A6 (the monthly IC with its exploratory
±1 SE bands), A13 (the probes' descriptive columns), A14 and A15 (post hoc), and the appendix tables t17, t24, t25
and t31. No main figure (1–7) and no main table (1–6) cites an exploratory table or row: not in a caption, not in a
LaTeX cell, not in a figure's data (`figures.guard`, `tests/test_figures_exploratory.py`). The CSVs of t11 and t20
keep their exploratory rows; their LaTeX leaves them out and points to t31, t25 and Figure A15.

## 1. Question and decision models

Can a decision model read pre-open company news and anticipate the reaction, and can it judge over- and
under-reaction once part of the move is visible?

- **Figure 1** (`fig1_validation_test`, half width): validation against test, the daily IC with $z_{cc}$ on val-B
  and test per instrument, grouped (trained, zero-shot, API models, baselines); every positive validation IC falls.
- Appendix: Figure A1 (the zero-shot tournament), the model comparison (t14) and the tournament table (t27).

## 2. Design: pre-registration, freeze, blinding, masking, ledgers

- No main figure or table. Appendix: Figure A2 (the importance filters; t28), Figure A3 (the encodings; t29), the
  spend and requests (t22) and the one-page summary of the pre-registration deviations (t34, PREREG §15).

## 3. Reading the news: priced at the open (H1, H1b)

- **Figure 2** (`fig2_priced_at_open`): the IC with $z_{on}$ beside the IC with $z_{id}$ per model, and H1.
- **Table 1** (`tab1_primary`): the primary hypotheses H1, H1b, H2, H3, H4 (estimate, 95% CI, p, Holm p, §1.3
  verdict) with the anchor beside the primary.
- **Table 2** (`tab2_ic_by_target`): the IC with $z_{cc}$, $z_{on}$, $z_{id}$ on val-B and test.
- Appendix: Figures A4 (reliability; t15), A5 (robustness; t16), A6 (monthly IC, exploratory); tables t1b, t3,
  t32, t15, t16, t19.

## 4. Over- and under-reaction, and convergence to the news-implied value (H2, A1)

- **Figure 3** (`fig3_convergence`): d1-ultra's extreme $V$ deciles against their targets, and $\kappa_h$ with the
  half-life not reached within $t{+}20$.
- **Figure 4** (`fig4_over_under`): d1-ultra's Under / Fair / Over paths, and the drift after the close by $|G|$ per
  news-strength tercile (terciles of $|V|$, NA-12's split). No small-move underreaction; large moves reverse slightly.
- **Table 3** (`tab3_over_under`): the over/under regression, b and c with SEs by decision point.
- **Table 4** (`tab4_convergence`): $\kappa_h$ by rung, $\lambda_h$ and the half-life.
- Appendix: Figures A7 (every decile, the anchor's $\kappa_h$), A8 (Figure 4 b for Laya-Fin), A9 (Shapley by
  instrument and tier), A10 (Call B ablations); tables t2, t4, t5, t6, t7, t8, t9, t13, t30.

## 5. Explaining realized moves (A3, H5)

- **Figure 5** (`fig5_explaining_moves`): d1-ultra's $R^2$ by cut, stacked by step (ex-ante news, same-day news,
  the explanation), with each total and its interval; then the news steps on their own scale, for Laya-Fin and
  d1-ultra.
- **Table 5** (`tab5_explaining_moves`): the ladder's increments and H5, the only secondary test that survives BH.
- Appendix: Figure A11 (persistence by move reason, $\theta$); tables t10, t11, t12.

## 6. Economic significance (strategies)

- **Figure 6** (`fig6_strategies`): gross and net Sharpe of the main books against the placebo range, and
  S-CONV's cumulative net return against the gap fade.
- **Table 6** (`tab6_strategies`): gross and net Sharpe, turnover, break-even cost, placebo percentile, DSR.
- Appendix: Figure A12 (the other books' paths, S-CONV by tier); tables t20, t26, t33, t35.

## 7. Memorisation and validation-to-test decay

- **Figure 7** (`fig7_memorisation`, half width): company identification on masked states, sorted bars with
  Wilson intervals, against the matched baseline and the screening threshold; every release after the sample.
- Appendix: Figure A13 (the probes, exploratory); tables t21, t23, t18.

## 8. Limitations

S&P 500 members only; a daily horizon (plus one 10:00 decision point from 30-minute bars); a seven-month test
period; one training seed for the trained instruments (the anchor's robustness runs are pending); the anchor after
one epoch is uninformative; no borrow costs; the vendor-label baselines may carry look-ahead.

## 9. The forward test (NA-15), pending

Post-release news (2026-08-01 onward), run after the operator exports the news (NA-15).

## Appendix

The appendix figures and tables, in the order of the sections above; exploratory material appears only here.

- A1 the tournament; A2 the filters; A3 the encodings; A4 reliability; A5 robustness; A6 the monthly IC
  (exploratory: ±1 implied SE of a month's mean, NA-12 §13); A7 convergence in detail and the anchor; A8 the drift
  for Laya-Fin; A9 Shapley by instrument and tier; A10 Call B ablations; A11 persistence by move reason; A12 the other books and S-CONV
  by tier; A13 the probes' descriptive columns (exploratory); A14 where the D0 signal lives (exploratory, post
  hoc, with the month-effect test); A15 news and a moving-average cross (exploratory, post hoc).
- Exploratory tables: t17 (sectors), t24 (NA-12 §13), t25 (NA-13 §9), t31 (the A3.5 market replication,
  pre-registered as exploratory).

## Figure index

| Figure | File stem | Section | Data |
|---|---|---|---|
| 1 | `fig1_validation_test` | 1 | NA-12 t14 |
| 2 | `fig2_priced_at_open` | 3 | NA-12 t3, t1b |
| 3 | `fig3_convergence` | 4 | NA-12 figure data, t6, t7 |
| 4 | `fig4_over_under` | 4 | NA-12 figure data |
| 5 | `fig5_explaining_moves` | 5 | NA-12 t10 |
| 6 | `fig6_strategies` | 6 | NA-13 strategy table and Figure 7 data, t33 |
| 7 | `fig7_memorisation` | 7 | NA-11 company identification (Wilson intervals) |
| A1 | `figA1_tournament` | appendix (1) | NA-06 |
| A2 | `figA2_filters` | appendix (2) | NA-03 |
| A3 | `figA3_encoding` | appendix (2) | NA-07 |
| A4 | `figA4_reliability` | appendix (3) | NA-12 figure data, t15 |
| A5 | `figA5_robustness` | appendix (3) | t16, t1b, t3 |
| A6 | `figA6_monthly_ic` | appendix (3), exploratory | t24 (NA-12 §13); the release dates (t21) in its caption |
| A7 | `figA7_convergence_detail` | appendix (4) | NA-12 figure data, t6, t7 |
| A8 | `figA8_drift_laya_fin` | appendix (4) | NA-12 figure data |
| A9 | `figA9_shapley` | appendix (4) | t13 |
| A10 | `figA10_ablations` | appendix (4) | t16 |
| A11 | `figA11_persistence` | appendix (5) | t11 |
| A12 | `figA12_strategy_paths` | appendix (6) | NA-13 Figure 7 data |
| A13 | `figA13_probes` | appendix (7), exploratory | NA-11 probes |
| A14 | `figA14_exploratory_d0` | appendix, exploratory | t24 (NA-12 §13) |
| A15 | `figA15_exploratory_ma_cross` | appendix, exploratory | t25 (NA-13 §9), NA-13 Figure 7 data |

## Table index

Every CSV table and its section, as `artifacts/NA-14/tables/index.json` records it (`tests/test_figures_tables.py`
checks that the two agree). t1–t19 are NA-12's (copied unchanged), t20 is NA-13's strategy table, t21–t35 are
NA-14's records, flattened results and aggregations, and the f-tables are figure data (no LaTeX).

| Table | Section | Source |
|---|---|---|
| `t1_primary` | 3 | NA-12 |
| `t1b_primary_by_model` | 3 | NA-12 |
| `t2_h2_over_under` | 4 | NA-12 |
| `t3_ic` | 3 | NA-12 |
| `t4_secondary` | 4 | NA-12 |
| `t5_heterogeneity` | 4 | NA-12 |
| `t6_convergence_ladder` | 4 | NA-12 |
| `t7_gap_closure` | 4 | NA-12 |
| `t8_tracking_error` | 4 | NA-12 |
| `t9_convergence_cuts` | 4 | NA-12 |
| `t10_explanation_ladder` | 5 | NA-12 |
| `t11_explanation_share_theta` | 5 | NA-12 (its LaTeX leaves out the A3.5 market row) |
| `t12_question_battery` | 5 | NA-12 |
| `t13_shapley` | 4 | NA-12 |
| `t14_model_comparison` | 1 | NA-12 (the LaTeX marks the vendor-label rows †) |
| `t15_calibration` | appendix | NA-12 |
| `t16_robustness` | appendix | NA-12 |
| `t17_sector_exploratory` | appendix | NA-12; exploratory |
| `t18_probes_val_a` | appendix | NA-12 |
| `t19_monthly_ic` | appendix | NA-12 |
| `t20_strategies` | 6 | NA-13 (its LaTeX leaves out the exploratory MA-cross rows) |
| `t21_release_dates` | 7 | NA-05 catalog; Laya's date from the operator |
| `t22_spend` | 2 | the ledgers; NA-08 and NA-11 REPORTs |
| `t23_company_identification` | 7 | NA-11 |
| `t24_exploratory_d0_signal` | appendix | NA-12 §13; exploratory (post hoc) |
| `t25_ma_cross` | appendix | NA-13 §9; exploratory (post hoc) |
| `t26_sconv_overlap` | 6 | NA-13's stored positions and books |
| `t27_tournament` | 1 | NA-06 |
| `t28_filter_frontier` | 2 | NA-03 |
| `t29_encoding` | appendix | NA-07 |
| `t30_derived` | 4 | NA-12 figure data (a sum a caption cites) |
| `t31_market_replication` | appendix | NA-12 t11, row market:r2; exploratory (pre-registered as such) |
| `t32_val_b_ic` | 3 | NA-11's val-B run of the frozen spec |
| `t33_placebo_sharpe` | 6 | NA-13's stored placebo books (quantiles) |
| `t34_prereg_deviations` | appendix | PREREG §15 and NA-14's one-line summaries |
| `t35_break_even` | 6 | NA-13 strategy table (gross mean ÷ turnover) |
| `f1_rg_class_paths` | 4 | NA-12 figure data |
| `f1_v_decile_paths` | 4 | NA-12 figure data |
| `f2_drift_vs_g` | 4 | NA-12 figure data |
| `f4_monthly_ic` | appendix | NA-12 figure data |
| `f5_shapley_shares` | appendix | NA-12 figure data |
| `f8_explanation_ladder` | 5 | NA-12 figure data |
| `fa_reliability` | appendix | NA-12 figure data |

The LaTeX tables (`artifacts/NA-14/tables/latex.json`): six main tables, then one appendix table per CSV the paper
shows. Cells: the keyed cells each prints.

| LaTeX file | Where | Draws on | Cells |
|---|---|---|---|
| `tab1_primary.tex` | main | t1_primary | 38 |
| `tab2_ic_by_target.tex` | main | t3_ic, t14_model_comparison, t32_val_b_ic | 60 |
| `tab3_over_under.tex` | main | t2_h2_over_under | 54 |
| `tab4_convergence.tex` | main | t6_convergence_ladder, t7_gap_closure | 96 |
| `tab5_explaining_moves.tex` | main | t10_explanation_ladder, t4_secondary | 24 |
| `tab6_strategies.tex` | main | t20_strategies, t35_break_even | 73 |
| `t14_model_comparison.tex` | appendix | t14_model_comparison | 74 |
| `t27_tournament.tex` | appendix | t27_tournament | 84 |
| `t21_release_dates.tex` | appendix | t21_release_dates | 5 |
| `t22_spend.tex` | appendix | t22_spend | 15 |
| `t28_filter_frontier.tex` | appendix | t28_filter_frontier | 350 |
| `t29_encoding.tex` | appendix | t29_encoding | 126 |
| `t1b_primary_by_model.tex` | appendix | t1b_primary_by_model | 138 |
| `t3_ic.tex` | appendix | t3_ic | 126 |
| `t32_val_b_ic.tex` | appendix | t32_val_b_ic | 21 |
| `t15_calibration.tex` | appendix | t15_calibration | 54 |
| `t16_robustness.tex` | appendix | t16_robustness | 541 |
| `t2_h2_over_under.tex` | appendix | t2_h2_over_under | 192 |
| `t4_secondary.tex` | appendix | t4_secondary | 72 |
| `t5_heterogeneity.tex` | appendix | t5_heterogeneity | 192 |
| `t6_convergence_ladder.tex` | appendix | t6_convergence_ladder | 393 |
| `t7_gap_closure.tex` | appendix | t7_gap_closure | 258 |
| `t8_tracking_error.tex` | appendix | t8_tracking_error | 144 |
| `t9_convergence_cuts.tex` | appendix | t9_convergence_cuts | 155 |
| `t13_shapley.tex` | appendix | t13_shapley | 264 |
| `t10_explanation_ladder.tex` | appendix | t10_explanation_ladder | 472 |
| `t11_explanation_share_theta.tex` | appendix | t11_explanation_share_theta | 69 |
| `t12_question_battery.tex` | appendix | t12_question_battery | 430 |
| `t20_strategies.tex` | appendix | t20_strategies | 1567 |
| `t26_sconv_overlap.tex` | appendix | t26_sconv_overlap | 16 |
| `t33_placebo_sharpe.tex` | appendix | t33_placebo_sharpe | 315 |
| `t35_break_even.tex` | appendix | t35_break_even | 264 |
| `t23_company_identification.tex` | appendix | t23_company_identification | 28 |
| `t18_probes_val_a.tex` | appendix | t18_probes_val_a | 58 |
| `t19_monthly_ic.tex` | appendix | t19_monthly_ic | 144 |
| `t17_sector_exploratory.tex` | appendix | t17_sector_exploratory | 330 |
| `t25_ma_cross.tex` | appendix | t25_ma_cross | 78 |
| `t31_market_replication.tex` | appendix | t31_market_replication | 3 |
| `t30_derived.tex` | appendix | t30_derived | 1 |
| `t34_prereg_deviations.tex` | appendix | t34_prereg_deviations | 315 |
