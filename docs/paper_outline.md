# Paper outline: sections → figures and tables

NA-14 (2026-10-29). Structure only: no new analysis. Every figure lives in `artifacts/NA-14/figures/` (PDF, PNG and
the CSV of its plotted values) and every table in `artifacts/NA-14/tables/` (CSV, and LaTeX for the paper tables).
The captions, with every number cited from a table, are in `artifacts/NA-14/captions.md`. Results are stated as
found in the NA-12 and NA-13 REPORTs; under PREREG §1.3 every primary hypothesis is **not supported** for the
primary instrument, Laya-Fin.

Labels used throughout: the anchor is *uninformative (near-constant outputs)*; the vendor-label baselines
(tags-GBM, vendor sentiment) are a *possibly look-ahead-contaminated upper bound*, and the clean benchmarks are
bge-ridge, price-only, the LLM baseline and the placebo; span-02 carries its S5 STOP footnote (PREREG §15,
post-freeze NA-11 row). Exploratory material is labelled *Exploratory (post hoc)*.

## 1. Question and decision models

Can a decision model read pre-open company news and anticipate the reaction, and can it judge over- and
under-reaction once part of the move is visible?

- Decision models, the trained instrument (Laya-Fin), the clean anchor and the zero-shot API models.
- Figure 3 (a): the zero-shot tournament, IC against cost.
- Tables: t14 (model comparison: IC on val-B and test, cost, latency), t27 (the tournament), t21 (release dates
  against the sample).

## 2. Design: pre-registration, freeze, blinding, masking, ledgers

- The pre-registration (PREREG v0.2 with amendments A1–A3), the NA-11 freeze, the test period's lock and its one
  access sequence per unblinding chunk, masking of names and numbers, the ledgers.
- Figure 6: the importance filters (selection share against material recall); t28.
- Appendix A2: the encoding of numbers in states (NA-07); t29.
- Appendix A3 (a): company identification on masked states (the §8.3 screen); t23.
- t22: spend and requests from the ledgers.

## 3. Reading the news: priced at the open (H1, H1b)

- The API models price the news at the open (H1 positive, model-specific); nothing predicts the open-to-close move
  (H1b); Laya-Fin's H1 and H1b are not supported.
- Figure 3 (b): val-B and test ICs of the final instruments and baselines.
- Figure 4: monthly IC across validation and test, against the release dates (all after the sample).
- Tables: t1 (primary, with the anchor next to Laya-Fin), t1b (by model), t3 (ICs with z_cc, z_on, z_id),
  t19 (monthly IC).
- Appendix A1 (calibration, t15), A5 (robustness of the D0 results, t16).

## 4. Over- and under-reaction: the H2 null; convergence by the close, then fade

- H2 is null; the reversal coefficient has the predicted sign but is not significant.
- Prices move part of the way to the model's value V by the open and the close of day t, then partly fade; κ peaks
  on day t or just after; the half-life of the gap is not reached within t+20.
- Large moves (|G| ≥ 3) reverse slightly in every news-strength tercile; smaller moves do not; there is no
  small-move underreaction.
- Figure 1 (hero): convergence; Figure 2: drift against the size of the move; Figure 5: Shapley value of
  information at D2 (H3, about zero).
- Tables: t2 (H2 by decision point and |G| bin), t6 (ladder κ_h), t7 (gap closure λ_h, half-life), t8 (tracking
  error), t9 (convergence cuts), t13 (Shapley), t4 (secondary family), t5 (heterogeneity).
- Appendix A4: Call B with the news removed or shuffled (t16).

## 5. Explaining moves: the A3 ladder and the small H5 share

- Same-day news explains a small share of the stock-specific variance out of sample (H5, the only secondary test
  that survives BH); reading the move (Call B) explains more but does not predict persistence (θ ≤ 0).
- Figure 8; tables t10 (the explanation ladder), t11 (explained share, θ, persistence by reason), t12 (question
  battery v2).

## 6. Economic significance: no book survives costs or the deflated Sharpe

- Every S-CONV, S-D0 and J book is negative net at 10 bp; Laya-Fin's RG books (6 to 12 positions) and the anchor's
  gated S-D2 J at t+20 are positive net but clear neither the placebo nor the deflated Sharpe; S-CONV is
  effectively the price-only gap fade.
- Figure 7; tables t20 (every book, val-B and test), t26 (the S-CONV / gap-fade overlap).

## 7. Memorisation and validation-to-test decay

- Company identification on masked states (API models far above the matched baseline; Laya zero-shot near it).
- The val-B → test drop of every positive IC (Figure 3 b); no contamination signature in the monthly ICs, which is
  not a test of contamination (Figure 4).
- Appendix A3 (a: t23; b, c: the probes' descriptive columns, exploratory), t18.

## 8. Exploratory (post hoc)

Requested after unblinding; no hypothesis, no claim.

- Where the D0 signal lives: earnings days against other events, size tiers, month effects, per-company spread
  (Appendix A6; t24, from NA-12 §13).
- News and a moving-average cross: the validation result did not replicate on test (Appendix A7; t25, from NA-13
  §9).
- Sector ICs (t17).

## 9. Limitations

S&P 500 members only; a daily horizon (plus one 10:00 decision point from 30-minute bars); a seven-month test
period; one training seed for the trained instruments (the anchor's robustness runs are pending); the anchor
after one epoch is uninformative; no borrow costs; the vendor-label baselines may carry look-ahead.

## 10. The forward test (NA-15), pending

Post-release news (2026-08-01 onward), run after the operator exports the news (NA-15).

## Figure and table index

| Figure | File stem | Section | Data |
|---|---|---|---|
| 1 | `fig1_convergence` | 4 | NA-12 figure data, t6, t7 |
| 2 | `fig2_drift_vs_move` | 4 | NA-12 figure data |
| 3 | `fig3_tournament` | 1, 3, 7 | NA-06 tournament, t14 |
| 4 | `fig4_monthly_ic` | 3, 7 | NA-12 figure data, t21 |
| 5 | `fig5_shapley` | 4 | t13 |
| 6 | `fig6_filters` | 2 | NA-03 frontier, NA-03 summary |
| 7 | `fig7_strategies` | 6 | NA-13 Figure 7 data, strategy table |
| 8 | `fig8_explain_move` | 5 | t10, t11 |
| A1 | `figA1_reliability` | appendix | NA-12 reliability bins, t15 |
| A2 | `figA2_encoding` | appendix (2) | NA-07 |
| A3 | `figA3_identifiability` | appendix (2, 7) | NA-11 |
| A4 | `figA4_ablations` | appendix (4) | t16 |
| A5 | `figA5_robustness` | appendix (3) | t16, t1b, t3 |
| A6 | `figA6_exploratory_d0` | 8 | t24 (NA-12 §13) |
| A7 | `figA7_exploratory_ma_cross` | 8 | t25 (NA-13 §9), NA-13 Figure 7 data |

Tables t1–t19 are NA-12's (copied unchanged), t20 is NA-13's strategy table, and t21–t30 are NA-14's records and
flattened results; `artifacts/NA-14/tables/index.json` lists each with its source.
