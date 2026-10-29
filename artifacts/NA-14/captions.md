# NA-14 figure captions

Rendered from `captions.yaml` by `python -m newsaction.figures.captions`; every number is a table cell (`tables/keys.json`). Figures 1–8 are the paper's; A1–A7 the appendix's. Section numbers follow `docs/paper_outline.md`.

## fig1_convergence: Prices move part of the way to the model's value on day t, then partly fade

*Section 4. Files: `figures/fig1_convergence.pdf`, `figures/fig1_convergence.png`, data `figures/fig1_convergence.csv`.*

Convergence to the news-implied value (PREREG A1), test period. (a, b) Mean CAR^lvl, the cumulative abnormal return in typical daily moves from the previous close, of the D0 events by decile of the decision model's value V, against each decile's mean V (dashed): Laya-Fin, the primary instrument, and d1-ultra, the API comparator, which fails the §8.3 screens and is model-specific (§1.3). Prices reach part of each decile's target by the open and the close of day t, then partly fade: d1-ultra's top decile (mean V 0.77) stands at +0.45 at the open, +0.52 at the close and +0.36 at t+20; its bottom decile (mean V −0.64) at −0.40, −0.43 and −0.33. Laya-Fin's deciles are ordered the same way but smaller. Before the event the prices drift in V's direction (not drawn): five sessions earlier d1-ultra's top decile stood −1.19 and its bottom decile +1.54 from the previous close; the states describe the company's recent performance in words, so part of V reflects momentum. Bands: ±1.96 event-level SE (deciles 1 and 10; descriptive). (c) The convergence ladder κ_h, the slope of CAR^lvl_h on V with day × tier fixed effects, and its 95% interval from the two-way clustered SE, against full convergence at κ = 1. κ peaks on day t or just after and is far from one: Laya-Fin 0.36 to 0.38 from the close of t to t+2, d1-ultra 0.59 to 0.61 at 10:00 and the close. It fades by t+10 (0.21 and 0.25); Laya-Fin's increase from the open to t+20 is +0.02 (p 0.467). The half-life of the gap U = V − G, the first horizon at which λ_h reaches 0.5, is not reached within t+20 for any model (∞ in t7). The anchor is uninformative (near-constant outputs). (d) d1-ultra's D2 events by RG class, signed in the news' direction, against each class's mean signed V: the 5,021 "Under" events move against the news on day t (−0.95) and never catch up (−1.04 at t+20); the 1,783 "Over" events give back part of their move, from +3.16 at the close to +2.82 at t+20. Laya-Fin has only 146 D2 events with |N̂| ≥ 0.5, so its class paths are not drawn. Decision points: D0 at the open, D1 at 10:00, D2 at the close. The convergence tests (H2-C) are not supported after Benjamini–Hochberg, and H2, the primary test of over- and under-reaction, is not supported for Laya-Fin (Holm p 0.853).

## fig2_drift_vs_move: Large moves reverse slightly in every news-strength tercile; smaller moves do not

*Section 4. Files: `figures/fig2_drift_vs_move.pdf`, `figures/fig2_drift_vs_move.png`, data `figures/fig2_drift_vs_move.csv`.*

Drift after the close against the size of the day's move, test period (NA-12 figure data). Mean sign(G)·y2, the abnormal return from the next open to the close of t+5 in the direction of the day's move G, in typical daily moves, by bin of |G| within terciles of news strength |V| (Call A on the day's news): (a) weak, (b) medium, (c) strong news; 95% intervals of ±1.96 event-level SE. Moves with |G| ≥ 3 reverse slightly in every tercile: Laya-Fin −0.10, −0.18 and −0.15; d1-ultra −0.09, −0.18 and −0.14. Below |G| = 3 the means are small and of both signs; the one exception is d1-ultra's strong-news tercile, which also reverses slightly for moves of 0.5 to 2 (−0.08 and −0.08). No bin below |G| = 1 has a positive mean outside its interval: there is no small-move underreaction. The pre-registered regression H2 (y2 = a + b·N̂ + c·G with day × tier fixed effects at D2) finds b = −0.04 (p 0.616) and c = −0.015 (p 0.110) for Laya-Fin: not supported. The anchor is uninformative (near-constant outputs).

## fig3_tournament: Zero-shot API models price the open gap, and every positive validation IC falls on test

*Section 3. Files: `figures/fig3_tournament.pdf`, `figures/fig3_tournament.png`, data `figures/fig3_tournament.csv`.*

(a) The zero-shot tournament on NA-06's val-A stage-1 sample: daily IC of Call A's N̂ with z_cc and its 95% bootstrap interval against the cost per 1,000 decisions (log scale; the two local Laya models cost nothing). Every model is in the model confidence set. The six models that ran the stage-2 contamination screens (squares) all failed them: on masked states they still name the company in 62% to 74% of cases against a matched baseline of 28% (Appendix Figure A3), so the API comparators are model-specific (§1.3). (b) Val-B (hollow) and test (filled) daily ICs on each model's D0 events, with 95% intervals of ±1.96 Newey–West SE, and the cost per 1,000 decisions. Every IC that is positive on val-B falls on test: Laya-Fin 0.065 to 0.020, d1-ultra 0.097 to 0.039 (at 0.063 USD per 1,000 decisions); the anchor, bge-ridge and price-only are about zero in both. The highest test ICs belong to the vendor-label baselines (†: tags-GBM 0.055, vendor sentiment 0.047), whose labels were produced retrospectively: a possibly look-ahead-contaminated upper bound, not the benchmark. The clean benchmarks are bge-ridge (0.004), price-only (−0.003), the LLM baseline (0.001) and the placebo. The API models' signal is the open gap (H1 = 0.075 for d1-ultra, p <0.001); for Laya-Fin H1 is not supported (0.005, Holm p 0.853) and so is H1b (Holm p 0.853). The anchor is uninformative (near-constant outputs). ‡ span-02: the S5 canary fired a STOP after the freeze and the operator chose to proceed (PREREG §15, post-freeze NA-11 row).

## fig4_monthly_ic: Every decision model was released after the sample, so no contamination cliff can show in it

*Section 3. Files: `figures/fig4_monthly_ic.pdf`, `figures/fig4_monthly_ic.png`, data `figures/fig4_monthly_ic.csv`.*

Monthly mean of the daily IC of Call A's N̂_W0 with z_cc over val-A, val-B and the test period (NA-12) for Laya-Fin, the three API comparators (‡ span-02: S5 STOP after the freeze, the operator proceeded; PREREG §15) and the anchor (uninformative, near-constant outputs). The test period ends on 2026-07-31. Laya's open weights, the base of Laya-Fin, were released on 2026-09-18 (49 days later; date supplied by the operator) and the API models between 2026-10-12 and 2026-10-16 (NA-05 catalog): every release lies after the sample (gray region), so a contamination cliff at a release would fall outside the data. The API models' ICs fall toward zero late in the test period as Laya-Fin's do, while the anchor's scatter around zero throughout; a common decline is consistent with no contamination advantage but is not a test of it. In the last two test months the ICs are about zero for every model (Laya-Fin −0.02 and −0.01, d1-ultra +0.00 and +0.01). Exploratory (post hoc): a one-way test of the daily ICs on the calendar month finds no month effect (test p 0.72 for Laya-Fin and 0.44 for d1-ultra), so the dip is within month-to-month noise.

## fig5_shapley: The value of information at the close is about zero for every feature group

*Section 4. Files: `figures/fig5_shapley.pdf`, `figures/fig5_shapley.png`, data `figures/fig5_shapley.csv`.*

Exact Shapley values of the test-period out-of-sample R² (a–c) and mean daily IC (d–f) of y2 at D2 over the feature groups R (price and reaction: G, the open gap, momentum, volume, tier), N (news, Call A: N̂, materiality, surprise, tone) and J (judgments, Call B: J, C, W), by tier, from the H3 ridge fits (§11.5; fit on val-B or on train, λ on val-A, evaluated on test). The diamonds are the full model's totals: R² −0.0017 for Laya-Fin, −0.0019 for d1-ultra and −0.0013 for the anchor (uninformative, near-constant outputs). Every total is about zero or negative, so the shares in t13 are shares of nothing and are not drawn. H3, that J adds out-of-sample IC beyond R and N, is not supported for Laya-Fin (0.0038, Holm p 0.269). Only D2 is shown: the ridge protocol is fit at the one decision point H3 tests.

## fig6_filters: An embedding filter selects material news better than rule filters

*Section 2. Files: `figures/fig6_filters.pdf`, `figures/fig6_filters.png`, data `figures/fig6_filters.csv`.*

Material recall against the share of val-A eval days selected, per candidate importance filter (NA-03 frontier, budgets from 5% to 50% of days). The frozen filter F5, a logistic regression on bge-small embeddings, selects 30% of days at its budget with material recall 0.435. F6 (LightGBM) reaches 0.444 at the same budget, a tie within one point that goes to the filter with fewer inputs (§6.8). The rule filters F1–F4 recall 0.309 to 0.335 there, close to random selection (the diagonal); F0 keeps every clean article.

## fig7_strategies: No pre-registered book survives costs and the deflated Sharpe; S-CONV is effectively the price-only gap fade

*Section 6. Files: `figures/fig7_strategies.pdf`, `figures/fig7_strategies.png`, data `figures/fig7_strategies.csv`.*

Cumulative net returns at 10 bp per side, charged on both legs and the SPY hedge, over the test period (NA-13). (a) S-CONV, the primary strategy: rank D2 events by the gap U = V − G, enter at the next open, exit at t+5. (b) S-D0: rank by Ñ before the open, hold from the open to the close (light blue: the confidence-gated variant). (c) S-D1 J: 10:00 to the close. (d) S-D2 J: the next open to t+5. Each panel shows the benchmarks and the 5th–95th percentile band of 100 random-signal books on Laya-Fin's events. At 10 bp every S-CONV, S-D0 and J book of Laya-Fin and of d1-ultra is negative net (annualized Sharpe of the drawn books: S-CONV −1.98, gross +0.61; S-D0 −6.03; S-D1 J −9.70; S-D2 J −6.45). The only books positive net are Laya-Fin's RG books, with 6 to 12 positions over the whole test period (|N̂| ≥ 0.5 is rare for it), and the anchor's gated S-D2 J held to t+20; none of them clears its placebo or the deflated Sharpe. S-CONV is effectively the price-only gap fade, because V is small next to G (U ≈ −G): the two books share 92% of their positions, 99.8% of them on the same side, and their daily returns correlate 0.96. The anchor's S-CONV, built on an uninformative V (near-constant outputs), overlaps the gap fade even more (96%). No test book's gross Sharpe reaches the 95th placebo percentile; the highest is the gated S-D0 held to the close of t+1, not drawn (1.88 gross, placebo percentile 93). With 545 trials in the ledger, the largest deflated-Sharpe probability of any test book is 0.024. (e–g) Laya-Fin's S-CONV book and the gap fade by tier: descriptive sub-books of a null book, not separate tests. Vendor sentiment (†) is a possibly look-ahead-contaminated upper bound. Borrow costs are not modelled.

## fig8_explain_move: The news explains little of a stock's own move; reading the move explains more but does not predict persistence

*Section 5. Files: `figures/fig8_explain_move.pdf`, `figures/fig8_explain_move.png`, data `figures/fig8_explain_move.csv`.*

Explaining realized moves at the firm level (PREREG A3, after Kelly–Su–Zhang), test period. (a) d1-ultra's out-of-sample R² of the stock-specific daily move z_cc, stacked by step: ex-ante news (the D0 readings), plus ex-post news (Call A on the day's news), plus the explanation features (Call B, which sees the move), by cut, with the final step's 95% bootstrap interval. Market and sector (Roll's step one) explain 0.25 of the total daily variance; for the stock-specific part, ex-ante news reaches 0.0028, ex-post news 0.0082 and the explanation step 0.158 (0.375 on event days). The explanation step is not a prediction: Call B reads the realized move. (b) The news-only steps of the three instruments, in thousandths, with 95% bootstrap intervals. Laya-Fin's same-day news explains 0.0025 of the stock-specific variance, the only secondary test that survives Benjamini–Hochberg (H5, q 0.058), and 0.0013 of it was knowable before the open. The anchor is uninformative (near-constant outputs). (c) Persistence after D2 by d1-ultra's move_reason, with 95% intervals: no reason persists significantly. θ, the D2 regression of persistence on being explained, is −0.06 (SE 0.038, p 0.946): explained moves do not persist more. Days that d1-ultra judges explained are 16% of event days and carry 41% of their Σz²_cc.

## figA1_reliability: Reliability of the three-class forecasts

*Section appendix. Files: `figures/figA1_reliability.pdf`, `figures/figA1_reliability.png`, data `figures/figA1_reliability.csv`.*

Reliability of Q1's three classes (fall, no move or rise, split at ±0.5 typical moves) against e5 on the test period: the hit rate of the top class by bin of its confidence (15 bins; dot area proportional to the events in the bin; NA-12). The trained models are calibrated but barely informative: ECE 0.057 for Laya-Fin and 0.048 for the anchor (uninformative, near-constant outputs), with log-loss skill 0.001 for Laya-Fin. The zero-shot and API models are overconfident: ECE 0.176 for Laya zero-shot, 0.260 for d1-ultra, 0.361 for span-02 (‡: S5 STOP after the freeze, the operator proceeded) and 0.209 for drex-v2.0.

## figA2_encoding: How numbers are written in the state hardly matters

*Section appendix. Files: `figures/figA2_encoding.pdf`, `figures/figA2_encoding.png`, data `figures/figA2_encoding.csv`.*

The encoding of numbers in states (NA-07; PREREG §8.4): daily IC of N̂ with z_cc by encoding E0 to E4 on NA-07's val-A sample (filled, 95% bootstrap intervals) and the val-B confirmation of E1 and E3 (hollow), for the three API comparators (‡ span-02: S5 STOP after the freeze, the operator proceeded). E1 had the best mean val-A rank across the three models (1.67) and was selected there, but on val-B it fell short of E3 by more than one standard error, so NA-07's rule kept E3, the frozen encoding (d1-ultra on val-B: 0.058 with E1, 0.063 with E3). On val-A the differences between encodings lie well inside the intervals.

## figA3_identifiability: The API models identify the masked company; Laya zero-shot does not

*Section 7. Files: `figures/figA3_identifiability.pdf`, `figures/figA3_identifiability.png`, data `figures/figA3_identifiability.csv`.*

(a) Company identification with activity-matched distractors on masked val-A states (NA-11; the §8.3 screen): the API models name the company in 62% to 74% of states, against a matched baseline of 28% and the screen bar of 40%; Laya zero-shot names it in 32%. The API models therefore fail the screen and are model-specific (§1.3). (b, c) Exploratory (post hoc): the probes' descriptive columns (NA-11, val-A), not hypotheses. (b) ICs on masked and unmasked states: unmasking does not raise them materially (d1-ultra 0.072 masked and 0.063 unmasked; the largest rise, drex-v2.0's, is +0.01, t 0.48). (c) ICs on real against shuffled news on the same events (Laya-Fin 0.050 and 0.031); the anchor is uninformative (near-constant outputs). ‡ span-02: S5 STOP after the freeze, the operator proceeded (PREREG §15).

## figA4_ablations: Call B's judgments carry no information about the next days' drift, with or without the news

*Section appendix. Files: `figures/figA4_ablations.pdf`, `figures/figA4_ablations.png`, data `figures/figA4_ablations.csv`.*

Call B ablations for d1-ultra (S8, on the same test events; t16): the IC of J, C and N̂ with y2, real (filled) against (a) the news removed and (b) shuffled news (hollow), with 95% intervals of ±1.96 Newey–West SE. J's IC is −0.02 with the news and −0.01 without it, and −0.02 against −0.00 with shuffled news: the judgments carry no positive information about y2 in any case.

## figA5_robustness: No robustness variant changes a conclusion

*Section appendix. Files: `figures/figA5_robustness.pdf`, `figures/figA5_robustness.png`, data `figures/figA5_robustness.csv`.*

Robustness of the D0 results (§11.6; t16): Laya-Fin's H1, H1b and IC of N̂ with z_cc, and d1-ultra's H1, in each variant raw (filled) and placebo-adjusted (hollow), with the main estimate (diamond; t1b, the IC from t3) and 95% intervals (main: stationary block bootstrap; variants: ±1.96 Newey–West SE). Laya-Fin's H1 and H1b stay within their intervals of zero in every variant. d1-ultra's H1 stays positive in every variant, from 0.022 when the latest article precedes 04:00 to 0.122 when it falls between 08:00 and 09:15.

## figA6_exploratory_d0: Exploratory (post hoc): where the D0 signal lives

*Section 8. Files: `figures/figA6_exploratory_d0.pdf`, `figures/figA6_exploratory_d0.png`, data `figures/figA6_exploratory_d0.csv`.*

Exploratory (post hoc): requested after unblinding (NA-12 §13); no hypothesis, no claim. (a) Every signal's IC sits on earnings-day events, and there it held from val-B to test: Laya-Fin 0.11 and 0.13, d1-ultra 0.24 and 0.22. On other events it fell, for Laya-Fin from 0.049 to 0.013, and for every other signal too. (b) By size tier on test the API models' IC sits in the two smaller tiers (d1-ultra 0.015 in the Top-100 against 0.060 in the 251–500 tier). (c) The spread of the per-company rank correlations against a within-company shuffle: Laya-Fin's (0.214, p 0.015) and tags-GBM's exceed it, the others' do not; the test cannot tell company-specific skill from company-specific noise. † Vendor-label baselines: possibly look-ahead-contaminated upper bound. ‡ span-02: S5 STOP after the freeze, the operator proceeded (PREREG §15).

## figA7_exploratory_ma_cross: Exploratory (post hoc): news and a moving-average cross

*Section 8. Files: `figures/figA7_exploratory_ma_cross.pdf`, `figures/figA7_exploratory_ma_cross.png`, data `figures/figA7_exploratory_ma_cross.csv`.*

Exploratory (post hoc): the operator's MA20/MA50 cross add-on (NA-13 §9), designed on validation and run once on test; no claim. (a, b) Mean signed abnormal return over 5 and 20 days after a cross, by group (95% intervals of ±1.96 Newey–West SE), validation (hollow) against test (filled). The validation reversal of crosses without news (−41.1 bp, t −2.08) did not replicate on test (−14.4 bp, t −0.69). (c) The tradable no-news fade on test, cumulative net at 10 bp: net Sharpe −0.46 (gross 0.98, after 3.85 on validation, where its design was chosen).
