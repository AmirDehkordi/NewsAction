# NA-14 figure captions

Rendered from `captions.yaml` by `python -m newsaction.figures.captions`; every number is a table cell (`tables/keys.json`); notation is LaTeX math. Figures 1–7 are the paper's; A1–A19 the appendix's. Section numbers follow `docs/paper_outline.md`.

## fig1_validation_test: Every validation IC that is positive falls on test

*Section 1. Files: `figures/fig1_validation_test.pdf`, `figures/fig1_validation_test.png`, data `figures/fig1_validation_test.csv`.*

Daily IC of the pre-open news reading $\hat N$ with the close-to-close move $z_{cc}$, on val-B (hollow) and on the test period (filled), each with its 95% interval ($\pm$1.96 Newey–West SE), for the instruments and the baselines (NA-12). Laya-Fin, the primary instrument, falls from 0.065 to 0.020; d1-ultra, the API comparator, from 0.097 to 0.039; span-02 and drex-v2.0 alike. The API models fail the §8.3 contamination screens, so their results are model-specific (§1.3). The clean benchmarks are about zero in both periods: price-only −0.003 and bge-ridge 0.004 on test; the LLM baseline, on a 2,000-event subsample, 0.001. The highest test ICs belong to the vendor-label baselines ($\dagger$: tags-GBM 0.055, vendor sentiment 0.047), whose labels were produced retrospectively: a possibly look-ahead-contaminated upper bound, not the benchmark. The anchor is uninformative (near-constant outputs); its ICs are in the appendix's model comparison. $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15, post-freeze NA-11 row).

## fig2_priced_at_open: The API models' signal is priced at the open; no model predicts the move after it

*Section 3. Files: `figures/fig2_priced_at_open.pdf`, `figures/fig2_priced_at_open.png`, data `figures/fig2_priced_at_open.csv`.*

(a) Daily IC of $\hat N$ with the overnight move $z_{on}$ (previous close to open, filled) and with the move after the open $z_{id}$ (open to close, hollow), test period, with 95% bootstrap intervals (NA-12). (b) H1, their difference, with its bootstrap interval. The API models' IC is all overnight: d1-ultra 0.074 with $z_{on}$ and −0.001 with $z_{id}$, H1 = 0.075 (p <0.001), model-specific (§1.3); Laya zero-shot's H1 is 0.054. For Laya-Fin, the primary instrument, both ICs are small (0.015 and 0.010): H1 is not supported (Holm p 0.853) and so is H1b, the IC with $z_{id}$ (Holm p 0.853), although on val-B its IC with $z_{id}$ had been 0.054 (t 2.89; Table 2). The anchor is uninformative (near-constant outputs) and is in Table 1. $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## fig3_convergence: Prices move part of the way to the model's value on day t, then partly fade

*Section 4. Files: `figures/fig3_convergence.pdf`, `figures/fig3_convergence.png`, data `figures/fig3_convergence.csv`.*

Convergence to the news-implied value $V$ (PREREG A1), test period. Event time is not to scale: $O_t$ is the open, 10:00 the D1 decision point, $C_t$ the close of day $t$ and $+k$ the close of session $t+k$. (a) d1-ultra's top and bottom deciles of $V$: $\mathrm{CAR}^{\mathrm{lvl}}$, the abnormal return from the previous close in typical daily moves, with SE bands ($\pm$1.96 event-level SE; descriptive), against each decile's mean $V$ (dashed). The top decile (mean $V$ 0.77) stands at +0.45 at the open, +0.52 at the close and +0.36 at t+20; the bottom decile (mean $V$ −0.64) at −0.40, −0.43 and −0.33. Before the event prices drift in $V$'s direction (not drawn): five sessions earlier the top decile stood −1.19 and the bottom decile +1.54 from the previous close, so part of $V$ reflects momentum. The other deciles, and Laya-Fin's, are in Appendix Figure A7. (b) The convergence ladder $\kappa_h$, the slope of $\mathrm{CAR}^{\mathrm{lvl}}_h$ on $V$ with day $\times$ tier fixed effects, with 95% intervals from two-way clustered SEs, against full convergence at $\kappa_h = 1$. $\kappa_h$ peaks on day $t$ or just after and is far from one: Laya-Fin 0.36 at the close and 0.38 at t+2, d1-ultra 0.61 at 10:00; it fades by t+10 (0.21 and 0.25). Laya-Fin's increase from the open to t+20 is +0.02 (p 0.467). The half-life of the gap $U = V - G^{\mathrm{lvl}}$, the first rung at which $\lambda_h$ reaches 0.5, is not reached within t+20 for any model (∞; Table 4). The convergence tests (H2-C) are not supported after Benjamini–Hochberg. The anchor is uninformative (near-constant outputs) and appears in Figure A7. d1-ultra fails the §8.3 screens and is model-specific (§1.3).

## fig4_over_under: No small-move underreaction; large moves reverse slightly

*Section 4. Files: `figures/fig4_over_under.pdf`, `figures/fig4_over_under.png`, data `figures/fig4_over_under.csv`.*

Over- and under-reaction, test period (NA-12 figure data). (a) d1-ultra's D2 events by RG class, pooled over the tiers and signed in the news' direction ($\mathrm{sign}(\hat N)\cdot\mathrm{CAR}^{\mathrm{lvl}}$), with SE bands ($\pm$1.96 event-level SE), against each class's mean signed $V$ ($\bar V$ in the labels; dashed in the class's colour, dotted for Under, short dashes for Fair and long dashes for Over, since the three lie close). The 5,021 Under events moved against the news on day $t$ (−0.95) and never catch up (−1.04 at t+20, against a target of 0.38); the 1,783 Over events give back part of their move, from +3.16 at the close to +2.82. Laya-Fin has only 146 D2 events with $|\hat N| \geq 0.5$, too few to draw. (b) d1-ultra's drift after the close, $\mathrm{sign}(G)\,y_2$ (next open to the close of t+5, in the direction of the day's move $G$), by bin of $|G|$, one line per tercile of news strength, with 95% intervals. The terciles are on $|V|$, Call A's value on the day's news (NA-12's figure data), not on $|\hat N|$. Moves with $|G| \geq 3$ reverse slightly in every tercile (strong −0.14, medium −0.18, weak −0.09); below that the means are small and of both signs, except the strong tercile, which also reverses slightly at 0.5 to 2 (−0.08 and −0.08). There is no small-move underreaction. Laya-Fin's panel is Appendix Figure A8. The pre-registered regression H2 finds, for Laya-Fin, b = −0.04 (p 0.616) and c = −0.015 (p 0.110): not supported (Table 3). d1-ultra is model-specific (§1.3).

## fig5_explaining_moves: The news explains little of a stock's own move; reading the move explains more

*Section 5. Files: `figures/fig5_explaining_moves.pdf`, `figures/fig5_explaining_moves.png`, data `figures/fig5_explaining_moves.csv`.*

Explaining realized moves at the firm level (PREREG A3, after Kelly–Su–Zhang), test period (NA-12), as out-of-sample $R^2$ in % of the stock-specific variance. (a) d1-ultra's $R^2$ of the stock-specific move $z_{cc}$ by cut, stacked by step in the order of the legend: the ex-ante (D0) news, + the same-day news (Call A), + the explanation (Call B reads the realized move, so this step is not a prediction). The total stands above each bar with its 95% bootstrap interval: 15.8% of all covered member-days and 37.5% of event days. The two news steps are too thin to read, so their values stand beside each bar after a swatch of their colour: the ex-ante step's $R^2$, then the same-day step's increment. For comparison, the market and the sector, Roll's first step, explain 25.3% of total daily variance, a different base. (b) The news steps on their own scale, the zoom that makes them readable: the $R^2$ after the ex-ante and after the same-day news, with 95% bootstrap intervals. Laya-Fin's same-day news explains 0.25% of the stock-specific variance, the only secondary test that survives Benjamini–Hochberg (H5, q 0.058), and 0.13% was knowable before the open; d1-ultra's steps reach 0.82% and 0.28%. The trained models give no explanation answer; the anchor is uninformative (near-constant outputs; Table 5). d1-ultra is model-specific (§1.3).

## fig6_strategies: No pre-registered book survives costs and the deflated Sharpe; S-CONV is effectively the gap fade

*Section 6. Files: `figures/fig6_strategies.pdf`, `figures/fig6_strategies.png`, data `figures/fig6_strategies.csv`.*

Strategies on the test period (NA-13). (a, b) Annualized Sharpe ratio of each main book, gross and net of 10 bp per side on both legs and the SPY hedge, at the exit of its hypothesis' horizon; the gray box is the 5th to 95th percentile of the book's 100 random-signal books; (b) has its own scale. Gross, every book lies inside its placebo range (S-CONV's: −2.12 to +2.23); net, every one is negative (Laya-Fin's S-CONV −1.98, gross +0.61; S-D0 −6.03; S-D1 $J$ −9.70). The one-day books lose most to costs: they turn over 4.36 times their capital a day against 0.90 for S-CONV. (c) S-CONV's cumulative net return at 10 bp against the price-only gap fade, with the placebo's 5th to 95th percentile band. S-CONV is effectively the gap fade, because $V$ is small next to $G$ ($U \approx -G^{\mathrm{lvl}}$): the two share 92% of their positions, 99.8% of them on the same side, and their daily returns correlate 0.96. The only books positive net are Laya-Fin's RG books, with 6 to 12 positions over the whole test period, and the anchor's gated S-D2 $J$ held to t+20 (the anchor is uninformative, with near-constant outputs); none clears its placebo or the deflated Sharpe. The highest gross Sharpe, the gated S-D0 held to the close of t+1 (1.88), reaches placebo percentile 93; with the 545 trials in the ledger when NA-13 computed it, the largest deflated-Sharpe probability of any test book is 0.024. Every book is in the appendix's strategy table, the other books' paths and the tier sub-books in Figure A12. Borrow costs are not modelled.

## fig7_memorisation: The API models identify the masked company; Laya zero-shot hardly does

*Section 7. Files: `figures/fig7_memorisation.pdf`, `figures/fig7_memorisation.png`, data `figures/fig7_memorisation.csv`.*

Company identification on masked val-A states with activity-matched distractors (NA-11; the §8.3 screen): the share of states in which each model names the company among four candidates, as a bar, sorted, with its Wilson 95% interval and its value at the bar's end, against the matched baseline (a no-reading guess, 28%; solid) and the screening threshold (40%; dashed). The production comparators (d1-ultra, span-02, drex-v2.0) are in the comparator colour, the other API models and Laya zero-shot in gray. The API models name it in 62% to 74% of states, so they fail the screen and are model-specific (§1.3); Laya zero-shot, Laya-Fin's base, names it in 32%. Every model was released after the sample, which ends on 2026-07-31: Laya's open weights on 2026-09-18 (49 days later; the operator's date) and the API models between 2026-10-12 and 2026-10-16 (NA-05 catalog). Identifying a company is not the same as remembering its returns, and the test does not settle that. $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA1_tournament: The zero-shot tournament

*Section appendix. Files: `figures/figA1_tournament.pdf`, `figures/figA1_tournament.png`, data `figures/figA1_tournament.csv`.*

The zero-shot tournament on NA-06's val-A stage-1 sample: (a) the daily IC of Call A's $\hat N$ with $z_{cc}$ and its 95% bootstrap interval, models sorted by IC; (b) the cost per 1,000 decisions (log scale; the local Laya models cost nothing). Every model is in the model confidence set; the highest IC is mercury-decide's (0.099) and d1-ultra's is 0.085. The six models that ran the stage-2 screens (squares) all failed them (Figure 7). $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA2_filters: An embedding filter selects material news better than rule filters

*Section appendix. Files: `figures/figA2_filters.pdf`, `figures/figA2_filters.png`, data `figures/figA2_filters.csv`.*

Material recall against the share of val-A days selected, per candidate importance filter (NA-03 frontier, budgets from 5% to 50% of days). The frozen filter F5, a logistic regression on bge-small embeddings, selects 30% of days at its budget with material recall 0.435. F6 (gradient boosting) reaches 0.444 at the same budget, a tie within one point that goes to the filter with fewer inputs (§6.8). The rule filters F1 to F4 recall 0.309 to 0.335 there, close to random selection (dashed); F0 keeps every clean article.

## figA3_encoding: How numbers are written in the state hardly matters

*Section appendix. Files: `figures/figA3_encoding.pdf`, `figures/figA3_encoding.png`, data `figures/figA3_encoding.csv`.*

The encoding of numbers in states (NA-07; §8.4): daily IC of $\hat N$ with $z_{cc}$ by encoding E0 to E4 on NA-07's val-A sample (filled, 95% bootstrap intervals) and the val-B confirmation of E1 and E3 (hollow), for the three API comparators; the gray column is the frozen encoding. E1 had the best mean val-A rank (1.67) but fell short of E3 on val-B by more than one standard error, so NA-07's rule kept E3 (d1-ultra on val-B: 0.058 with E1, 0.063 with E3). $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA4_reliability: Reliability of the three-class forecasts

*Section appendix. Files: `figures/figA4_reliability.pdf`, `figures/figA4_reliability.png`, data `figures/figA4_reliability.csv`.*

Reliability of Q1's three classes (fall, no move or rise at $\pm$0.5 typical moves) against $e_5$ on the test period: the hit rate of the top class by bin of its confidence (15 bins; dot area grows with the events in the bin; the diagonal is perfect calibration; NA-12). The trained models are calibrated but barely informative: ECE 0.057 for Laya-Fin and 0.048 for the anchor (uninformative, near-constant outputs), with log-loss skill 0.001 for Laya-Fin. The zero-shot and API models are overconfident: ECE 0.176 for Laya zero-shot, 0.260 for d1-ultra, 0.361 for span-02 and 0.209 for drex-v2.0. $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA5_robustness: No robustness variant changes a conclusion

*Section appendix. Files: `figures/figA5_robustness.pdf`, `figures/figA5_robustness.png`, data `figures/figA5_robustness.csv`.*

Robustness of the D0 results (§11.6): Laya-Fin's H1, H1b and IC of $\hat N$ with $z_{cc}$, and d1-ultra's H1, in each variant raw (filled) and placebo-adjusted (hollow), below the main estimate (diamond; stationary block bootstrap) with 95% intervals ($\pm$1.96 Newey–West SE for the variants). (a) and (d), both H1, share a scale; (b) and (c) have their own. Laya-Fin's H1 and H1b stay within their intervals of zero in every variant. d1-ultra's H1 stays positive in every variant, from 0.022 when the latest article precedes 04:00 to 0.122 when it falls between 08:00 and 09:15; it is model-specific (§1.3).

## figA6_monthly_ic: Exploratory: the monthly IC, with the implied standard error of a month's mean

*Section appendix. Files: `figures/figA6_monthly_ic.pdf`, `figures/figA6_monthly_ic.png`, data `figures/figA6_monthly_ic.csv`.*

Exploratory (post hoc): the bands come from NA-12 §13, requested after unblinding; no hypothesis, no claim. The monthly mean of the daily IC of $\hat N$ with $z_{cc}$ over val-A, val-B and the test period for Laya-Fin and d1-ultra (model-specific), with $\pm$1 implied standard error of a month's mean (iid; on test 0.037 for Laya-Fin). In the last two test months the ICs are about zero (Laya-Fin −0.02 and −0.01, d1-ultra +0.00 and +0.01), within about one standard error of a month's mean. Every release lies after the sample, where the time axis stops, which ends on 2026-07-31: Laya on 2026-09-18, the API models from 2026-10-12; a contamination cliff at a release would fall outside the data. The anchor (uninformative, near-constant outputs) has no implied SE; its monthly ICs are in the appendix's monthly table. $\ddagger$ span-02, whose release closes the API models' range: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA7_convergence_detail: Convergence in detail, every decile and the anchor

*Section appendix. Files: `figures/figA7_convergence_detail.pdf`, `figures/figA7_convergence_detail.png`, data `figures/figA7_convergence_detail.csv`.*

(a, b) $\mathrm{CAR}^{\mathrm{lvl}}$ of every decile of $V$ for Laya-Fin and d1-ultra (gray: deciles 2 to 9; the extreme deciles with SE bands and their mean $V$ dashed), on one scale. Laya-Fin's deciles are ordered like d1-ultra's but smaller and noisier: its top decile (mean $V$ 0.33) stands at +0.12 at the close. (c) The ladder $\kappa_h$ with the anchor, whose readings are uninformative (near-constant outputs): its $\kappa_h$ is about zero throughout (−0.04 at the close). Event time is not to scale; d1-ultra is model-specific (§1.3).

## figA8_drift_laya_fin: Laya-Fin's drift after the close by the size of the move

*Section appendix. Files: `figures/figA8_drift_laya_fin.pdf`, `figures/figA8_drift_laya_fin.png`, data `figures/figA8_drift_laya_fin.csv`.*

Figure 4 (b) for Laya-Fin: $\mathrm{sign}(G)\,y_2$ by bin of $|G|$, one line per tercile of news strength $|V|$, with 95% intervals. Moves with $|G| \geq 3$ reverse slightly in every tercile (strong −0.15, medium −0.18, weak −0.10); smaller moves do not drift.

## figA9_shapley: The value of information at the close is about zero for every feature group

*Section appendix. Files: `figures/figA9_shapley.pdf`, `figures/figA9_shapley.png`, data `figures/figA9_shapley.csv`.*

Exact Shapley values of the test-period out-of-sample $R^2$ (a to c) and mean daily IC (d to f) of $y_2$ at D2 over the feature groups $R$ (price and reaction), $N$ (news, Call A) and $J$ (judgements, Call B), for all member-days and by size tier, with the full model's total $R + N + J$ (diamond), from the H3 ridge fits (§11.5); values in units of $10^{-3}$, and each row on one scale. One column per instrument: Laya-Fin, d1-ultra (model-specific) and the anchor (uninformative, near-constant outputs). Every $R^2$ total is negative, in every tier; for all member-days it is −0.0017 for Laya-Fin, −0.0019 for d1-ultra and −0.0013 for the anchor, so the Shapley shares are shares of nothing and are not drawn. The IC totals are small and of both signs, from −0.029 (Laya-Fin, 101 to 250) to 0.013 (Laya-Fin, Top-100). H3 is not supported for Laya-Fin (Holm p 0.269).

## figA10_ablations: Call B's judgments carry no information about the drift, with or without the news

*Section appendix. Files: `figures/figA10_ablations.pdf`, `figures/figA10_ablations.png`, data `figures/figA10_ablations.csv`.*

Call B ablations for d1-ultra (S8, on the same test events): the IC of $J$, $C$ and $\hat N$ with $y_2$, real news (filled) against (a) the news removed and (b) shuffled news (hollow), with 95% intervals ($\pm$1.96 Newey–West SE). $J$'s IC is −0.02 with the news and −0.01 without it, and −0.02 against −0.00 with shuffled news. d1-ultra is model-specific (§1.3).

## figA11_persistence: Explained moves do not persist more

*Section appendix. Files: `figures/figA11_persistence.pdf`, `figures/figA11_persistence.png`, data `figures/figA11_persistence.csv`.*

Persistence after D2, the mean of $\mathrm{sign}(G)\,y_2$, by d1-ultra's reason for the move (95% intervals), and $\theta$, the D2 regression of persistence on being explained: −0.06 (SE 0.038, p 0.946). No reason persists significantly. Days that d1-ultra judges explained are 16% of event days and carry 41% of their squared moves. d1-ultra is model-specific (§1.3).

## figA12_strategy_paths: The other books, and S-CONV by tier

*Section appendix. Files: `figures/figA12_strategy_paths.pdf`, `figures/figA12_strategy_paths.png`, data `figures/figA12_strategy_paths.csv`.*

Cumulative net returns at 10 bp per side over the test period (NA-13). (a) S-D0 from the open to the close, with vendor sentiment ($\dagger$: a possibly look-ahead-contaminated upper bound, not the benchmark); (b) S-D1 $J$ from 10:00 to the close; (c) S-D2 $J$ from the next open to t+5, each against the gap fade where it applies and the placebo's 5th to 95th percentile band of Laya-Fin's universe. The steep declines of the one-day books are mostly costs (net Sharpe −6.03 and −9.70, gross +0.35 and +0.76). (d to f) Laya-Fin's S-CONV and the gap fade by tier: descriptive sub-books of a null book, not separate tests. (a) and (b) share a scale, as do (d) to (f); (c) has its own, since S-D2 loses far less. d1-ultra is model-specific (§1.3).

## figA13_probes: Exploratory: the probes' descriptive columns

*Section appendix. Files: `figures/figA13_probes.pdf`, `figures/figA13_probes.png`, data `figures/figA13_probes.csv`.*

Exploratory (post hoc): the probes' descriptive columns (NA-11, val-A), not hypotheses. (a) ICs on masked and unmasked states: unmasking does not raise them materially (d1-ultra 0.072 masked and 0.063 unmasked; the largest rise, drex-v2.0's, is +0.01, t 0.48). Both panels share the IC scale. (b) ICs on real against shuffled news on the same events (Laya-Fin 0.050 and 0.031, inconclusive); the anchor is uninformative (near-constant outputs). $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA14_exploratory_d0: Exploratory (post hoc): where the D0 signal lives

*Section appendix. Files: `figures/figA14_exploratory_d0.pdf`, `figures/figA14_exploratory_d0.png`, data `figures/figA14_exploratory_d0.csv`.*

Exploratory (post hoc): requested after unblinding (NA-12 §13); no hypothesis, no claim. (a) Every signal's IC sits on earnings-day events (squares), and there it held from val-B (hollow) to test (filled): Laya-Fin 0.11 and 0.13, d1-ultra 0.24 and 0.22. On other events (circles) it fell, for Laya-Fin from 0.049 to 0.013, and for every other signal too. (b) By size tier on test the API models' IC sits in the two smaller tiers (d1-ultra 0.015 in the Top-100 against 0.060 in the 251–500 tier). The earnings-day ICs of (a) are several times the tier ICs of (b), so the two panels have their own scales. (c) The spread of the per-company rank correlations against a within-company shuffle (gray: its 95% range): Laya-Fin's (0.214, p 0.015) and tags-GBM's exceed it, the others' do not; the test cannot tell company-specific skill from company-specific noise. Not drawn: a one-way test of the daily ICs on the calendar month finds no month effect on test (p 0.72 for Laya-Fin and 0.44 for d1-ultra). $\dagger$ Vendor-label baselines: a possibly look-ahead-contaminated upper bound. $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA15_exploratory_ma_cross: Exploratory (post hoc): news and a moving-average cross

*Section appendix. Files: `figures/figA15_exploratory_ma_cross.pdf`, `figures/figA15_exploratory_ma_cross.png`, data `figures/figA15_exploratory_ma_cross.csv`.*

Exploratory (post hoc): the operator's MA20/MA50 cross add-on (NA-13 §9), designed on validation and run once on test; no claim. (a, b) Mean signed abnormal return over 5 and 20 days after a cross, by group (95% intervals, $\pm$1.96 Newey–West SE), validation (hollow) against test (filled); the two panels have their own scales, since 20-day returns spread wider than 5-day ones. The validation reversal of crosses without news (−41.1 bp, t −2.08) did not replicate on test (−14.4 bp, t −0.69). (c) The tradable no-news fade on test, cumulative net at 10 bp: net Sharpe −0.46 (gross 0.98, after 3.85 on validation, where its design was chosen).

## figA16_selective_coverage: Exploratory (post hoc): risk-coverage curves of the pre-open reading

*Section appendix. Files: `figures/figA16_selective_coverage.pdf`, `figures/figA16_selective_coverage.png`, data `figures/figA16_selective_coverage.csv`.*

Exploratory (post hoc): NA-13b, requested after unblinding; no hypothesis, no claim. Its thresholds and medians come from val-A, and the test was evaluated once. Each model's D0 events are ranked by its conviction $|\hat N|$ (solid lines) or, for Laya-Fin and d1-ultra, by its stated confidence (thin lines, hollow dots); a coverage keeps the events at or above the val-A quantile of the ranking. Rows: (a) the mean signed overnight move $\mathrm{sign}(\hat N)\,z_{on}$, (b) the mean signed move after the open $\mathrm{sign}(\hat N)\,z_{id}$, (c) the hit rate against $z_{cc}$; columns val-A, val-B and test; bands are 95% bootstrap intervals; the dashed line is the frozen confidence gates' coverage (their val-A 70th percentile). Conviction concentrates the overnight move, which the open prices: d1-ultra's surest 10% carry 0.93 typical moves on the test against 0.21 for all its events. After the open little is left: 0.10 (95% interval −0.02 to 0.24) for d1-ultra's surest 10% and 0.07 for Laya-Fin's; neither model's test interval excludes zero at any coverage. span-02's and drex-v2.0's val-A points come from NA-06's 3,000-event stage-2 sample. d1-ultra is model-specific (§1.3). $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).

## figA17_watch_open: Exploratory (post hoc): the 10:00 reading against the pre-open one

*Section appendix. Files: `figures/figA17_watch_open.pdf`, `figures/figA17_watch_open.png`, data `figures/figA17_watch_open.csv`.*

Exploratory (post hoc): NA-13b, requested after unblinding; no hypothesis, no claim. Its thresholds and medians come from val-A, and the test was evaluated once. The daily IC with $y_1$, the move from 10:00 to the close, of the pre-open reading $\hat N_{\mathrm{D0}}$ (circles), of the 10:00 reading $\hat N_{\mathrm{D1}}$ (Call B at D1; squares) and of their revision $z(\hat N_{\mathrm{D1}}) - z(\hat N_{\mathrm{D0}})$ (diamonds) for (a) Laya-Fin and (b) d1-ultra on val-A, val-B and the test, with 95% intervals ($\pm$1.96 Newey–West SE). Watching the open adds nothing: on val-B and the test the 10:00 reading's IC is negative for both models (test: Laya-Fin −0.013, d1-ultra −0.014), and so is the revision's (Laya-Fin on test −0.036, t −2.33); only Laya-Fin's pre-open reading keeps a positive test IC (0.026, t 2.09). The first bar, the moves after it and the pre-registered D1 results are in the appendix table on watching the open. d1-ultra is model-specific (§1.3).

## figA18_conditioning_map: Exploratory (post hoc): the conditioning study, validation against test

*Section appendix. Files: `figures/figA18_conditioning_map.pdf`, `figures/figA18_conditioning_map.png`, data `figures/figA18_conditioning_map.csv`.*

Exploratory (post hoc): NA-13b, requested after unblinding; no hypothesis, no claim. Every condition is binary, its thresholds and medians come from val-A, the selection used val-A and val-B only, by the operator's rule fixed before the test, and the test was evaluated once. Each row: the difference inside minus outside of the primary outcome, the tradable move after the open $\mathrm{sign}(\hat N)\,z_{id}$, for (a) Laya-Fin and (b) d1-ultra on val-A (hollow circles), val-B (hollow squares) and the test (filled), with 95% intervals ($\pm$1.96 $|$difference$/t|$). Shaded rows were selected on validation ($t \geq 1$ in val-A and in val-B, pooled $t \geq 2$). None held on the test: their test differences run from −0.06 (Laya-Fin's E9, the strongest on validation, pooled t 3.51) to +0.04 (d1-ultra's E7 agreement, t 1.01), every Benjamini–Hochberg q of the family is at least 0.79, and no pair is confirmed. (seen): shown by the test before the study, never selected. $\dagger$ E1's vendor fields are labels produced retrospectively, possibly look-ahead-contaminated. E7's three-model agreement has no val-A run; E9 is Laya-Fin's alone. d1-ultra is model-specific (§1.3).

## figA19_output_histograms: Exploratory (post hoc): the decision models' outputs beside their reliability

*Section appendix. Files: `figures/figA19_output_histograms.pdf`, `figures/figA19_output_histograms.png`, data `figures/figA19_output_histograms.csv`.*

Exploratory (post hoc): NA-13b, requested after unblinding; no hypothesis, no claim. Its thresholds, medians and bins come from val-A, and the test was evaluated once. For each model, the share of its D0 events in each of 40 bins of (a) $\hat N$ and (b) the stated confidence, $1 - H/\log 3$ of Q1's three classes (the measure of the frozen gates), on val-A, val-B and the test; the bins span the val-A 0.5th to 99.5th percentiles and the end bins hold the values beyond. (c) NA-12's reliability diagram on the test (Figure A4): the hit rate of Q1's top class against $e_5$ by bin of the top-class probability, the confidence of §11.2's ECE, not the entropy confidence of (b); dot area grows with the events in the bin, the dashed diagonal is perfect calibration. Laya-Fin reads small: its $\hat N$ has an SD of 0.11 on test against 0.61 for d1-ultra, and its stated confidence stays below 0.073 for 95% of its test events; it is calibrated (ECE 0.057) where d1-ultra is not (0.260). The distributions barely move from val-A to the test, except Laya zero-shot's $\hat N$ (median −0.11 on val-A, −0.21 on test). span-02's and drex-v2.0's val-A histograms come from NA-06's 3,000-event stage-2 sample. $\ddagger$ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15).
