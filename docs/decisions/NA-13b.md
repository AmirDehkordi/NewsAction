# NA-13b decisions — when does the signal work? (exploratory, post hoc)

Date: 2026-10-29. Branch: `feat/NA-13b-selective` (main checkout, cut from main @ c3351ed, after NA-14's merge).
Self-audit: `artifacts/NA-13b/REPORT.md`. Code: `newsaction.selective`. PREREG: §15 row 65, written and committed
(d587293) with the validation selection (e451062) before the one test run. Test-period data: no lock read — 2026
outcomes from NA-12's frames and `work/analysis/targets_test.parquet`, 2026 market returns from NA-13's
`work/strategy/market_test.parquet` (its one logged lock sequence), and the ^VIX close of t−1 from NA-00's registered
copy of `Data/market` (the operator's decision below). The operator's prompt is the chunk's specification; it is not
in the PRD.

## Order of work

- **The disclosures first.** The operator's assistant's three looks (the |N̂| bands, the D1 statistics, the
  conditioning preview) were found in its session transcript and reproduced exactly: first with its own code, then
  through this chunk's code (`tests/test_selective_data.py` pins every printed digit). The (c) and (d) disclosures
  include test values the prompt already printed; reproducing them is the only test-period computation before the
  selection was frozen.
- **Code before data** (1e2b0db): the readings, the coverage curves, the D1 statistics, the conditions, the
  statistics and the rule, the books, the trials and the stages, with their tests. Every development run used val-A
  and val-B (the books on val-B, the curves' timing on validation).
- **The validation selection, checked three ways before it was frozen.** Two agents re-implemented the statistics
  from a written specification without reading this chunk's code; both reproduced all 221 statistics and the 8
  selected pairs bit for bit. A third agent compared the operationalization with the prompt (below). The operator
  then decided two definitions (VIX, payrolls); a fourth check reproduced the two changed conditions and confirmed
  that nothing else moved.
- **Then the commits** of the selection (e451062) and its §15 row (d587293), and only then `run test` (once, on
  d587293, 17:07:57 UTC; it refuses to run unless the selection is committed and unchanged and the val-A cut points
  are equal), `run trials` and `run dsr`, and the paper wiring.

## Choices the prompt leaves open (all in §15 row 65)

1. **Readings.** Call A on W0 news. Laya-Fin and d1-ultra from NA-12's frames and NA-11's production; span-02 and
   drex-v2.0 from production on val-B and the test, and on val-A from NA-06's stage-2 sample (3,000 events: their only
   val-A readings, and the sample their frozen maps and gates were fit on); Laya zero-shot from NA-09 (validation)
   and NA-11 (test). *Why:* the frozen pipeline's own readings; no re-call (no API).
2. **Stated confidence = Q1's three-class confidence 1 − H/log 3**, the frozen gates' measure. Its val-A 70th
   percentile reproduces every frozen D0 gate exactly (Laya-Fin 0.0097724, span-02, drex-v2.0, Laya zero-shot),
   except d1-ultra's, whose gate was fit on the stage-2 sample (production 0.22699 against 0.22725). The gate is
   marked at 30% coverage. *Note:* Laya-Fin's |N̂| and its stated confidence rank events differently (Spearman 0.11
   on val-A; d1-ultra 0.68), which is why the prompt's two rankings differ for it.
3. **Coverage curves.** Coverage c keeps the events at or above the val-A quantile at 1 − c of the score (c = 100%
   keeps all). Hit rate and mean signed move are pooled over events (the band check's statistic); the IC is the
   frozen daily IC (≥ 5 names a session; ≥ 10 sessions to report). CIs: the frozen stationary bootstrap, one draw
   set per split on its evaluation sessions (common random numbers), the pooled means from per-session sums.
4. **D1** exactly as the assistant computed it (z-scores over the split's events outside the embargo, the
   frozen daily IC with ≥ 10 sessions, Newey–West t with 5 lags, day-clustered t for the two means; an event
   without a first bar has no y1 either). The figure's 95% intervals are mean ± 1.96·SE, SE = |mean/t|.
5. **The conditions** (each binary; thresholds and medians from val-A events or sessions outside the embargo):
   - *Missing inputs.* An event whose attribute input is missing (a vendor field, attention, momentum) counts as
     outside: the assistant's convention, which its disclosed numbers depend on. An event without a model reading
     the condition needs is in neither group (`conditions.READINGS`; the critic's point). On validation and on the
     test no model reading is missing, so the second rule changed nothing.
   - *E1 earnings day* is the earnings-calendar flag (a scheduled release in W0), not the vendor tag, as in the
     preview; it is [seen on test].
   - *E2 novelty "new" vs known:* "known" = known + partly_known (the preview's `== "new"`).
   - *E3 04:00–08:00 vs 08:00–09:15* leaves out events whose latest article precedes 04:00 (31% of val-A).
   - *E4 busy news day* is two conditions: the event's own W0 attention ratio ≥ 1.5 (event level; the codebook's
     "busy", the stock's articles against its 60-session mean — not Hirshleifer–Lim–Teoh's market-wide count), and
     the session's number of D0 events above its val-A median (day level; a count of firms with news, in the spirit
     of Hirshleifer et al.'s count of same-day announcements, not their measure). 10 of 11 val-A Mondays are busy
     days by the second, since their W0 spans the weekend.
   - *E4 macro day* = an FOMC, CPI or payroll release day (see the operator decisions).
   - *E4 VIX at t−1* = the ^VIX close of the previous session, above its val-A median (15.70).
   - *E4 |SPY overnight|*: (1 + r_cc)/(1 + r_id) − 1 of NA-13's market files, which is O_t/C_{t−1} − 1. It is known
     only at the open, after the 09:15 decision: reported, and a book on it would fail the timing guard.
   - *E5 dollar-volume tier* = the tier 251–500 by dollar volume (mirrors the size condition); *low usual coverage*
     = attention_mean below its val-A median (event-weighted, not within session and tier as PREREG cut 7).
   - *E6 conviction top 30%* ranks |N̂| at its val-A 70th percentile (the gate's percentile, not the gate's measure);
     [seen on test]. *Laya-Fin's H-mag* is `a0_mag_mean`.
   - *E7 rank average* is the one E item without a threshold, so it is a combined signal, not a subset: the sign of
     the mean of sign(N̂)·F(|N̂|) over Laya-Fin and d1-ultra (F each model's val-A distribution), compared with each
     model's own sign on the same events (a paired difference). It departs from "every condition is binary"; it
     differs from a model only where the two disagree (about a third of events), so it overlaps E7's agreement.
   - *E7 three-model agreement* runs on val-B and the test (no val-A production run), selected at t ≥ 2.5 on val-B.
   - *E8* uses each model's frozen V (|V|·σ_cc > 0.40%); *E9* is Laya-Fin's direction only.
6. **Statistics.** Event level: the mean of daily inside-minus-outside differences, day-clustered t (the SD over the
   same series of days holding both groups). Day level: the difference of the inside and outside sessions' means,
   Welch's t. Pooled validation: the val-A and val-B daily differences together (day level: Welch on the pooled
   sessions; the pooled difference is mean(pooled inside) − mean(pooled outside)). p two-sided (Student t, days − 1;
   Welch–Satterthwaite).
7. **The test family.** Every pair on the primary outcome sign(N̂)·z_id, BH at q = 0.10 over all 75 pairs (the
   prompt), and beside it over the 69 pairs that are not [seen on test] (the critic's point: the seen conditions'
   small test p-values would otherwise help the rest). The secondary (open → C_{t+1}) and descriptive (z_on)
   outcomes are reported, outside the family.
8. **Tradable versions.** The selected pairs, E8 (both models) and E9: on each session, long the inside events whose
   direction is up and short those down, equal weight within each side; a session missing one side holds cash
   (`portfolios.tier_weights`; a long–short book needs both sides). NA-13's engine for everything else (β-hedge,
   entry at the open, exits at the close and C_{t+1}, costs on both legs and the hedge, capacity, Sharpe over the
   window). Placebo: a coin flip per event (seeds 2027–2126; NA-13's MA-cross convention, since sign books have no
   quantile sides). Timing: every input must be known by 09:15, the val-A cut points included; on the test the
   selection (which read val-B outcomes) must precede the decision; val-B books are in-sample. A condition on SPY's
   overnight move (known at the open) or on a vendor label the PIT registry keeps for selection only
   (`tag_quantified`, `source_class`) gets no valid instant, so its book is refused; neither was selected.
9. **Forward-test candidates**: SELECTED, the same sign on the test with BH q < 0.10, and a test book (exit at the
   close: the primary outcome is the open → close move) whose gross Sharpe is above its placebo's 90th percentile;
   if more than three qualified, the three with the largest pooled-validation t (a validation quantity).
10. **Trials.** One ledger row per variant and split (NA-13's convention), kind "exploratory", chunk "NA-13b": 330
    coverage rows (5 models × 2 rankings × 11 coverages × 3 splits, metric the mean signed z_id), 36 D1 rows, 669
    condition rows (75 pairs × 3 outcomes × 3 splits, less E7's missing val-A), 40 book rows (net Sharpe at 10 bp).
    The ledger's chunk pattern now admits one letter after the number (`^NA-\d{2}[a-z]?$`, with a test).

## The operator's decisions in this session (2026-10-29)

1. **VIX: read the t−1 close.** The prompt's lock route does not exist (the sealed snapshot holds ATOM's raw OHLC and
   the 30-minute bars, no VIX), and the 2026 ^VIX closes are only in `Data/market` and NA-00's registered copy
   `work/market/market_prices.parquet`, which the prompt's rule against reading 2026 prices from `Data/` covers. The
   operator chose to read the closes up to t−1 from that copy: a t−1 input the frozen 2026 states already used, not an
   outcome. (The first stand-in, the state's t−1 VIX percentile against its trailing year, drifts: 29 of 59 val-A
   sessions above its val-A median against 47 of 59 in val-B.)
2. **Payrolls: add verified BLS dates.** `Data/market/fred_releases.pkl` holds only CPI (CPIAUCSL, CPILFESL); the
   repository has no Employment Situation dates. Two independent web checks against bls.gov (each release's archived
   news release and the BLS revised-release-dates table) agreed on all 12 release days from 2025-07-03 to 2026-07-02,
   including the moves by the 2025 lapse in appropriations (September data on 2025-11-20; October payrolls and
   November data on 2025-12-16) and by the 2026 lapse (January data on 2026-02-11). They are in
   `artifacts/NA-13b/inputs/payrolls.yaml`, outside `configs/` (the freeze hash covers `configs/*.yaml`) and `src/`
   (no test-period date literals).

## The payroll file and the selection record

`payrolls.yaml` was written after the two web checks and before the validation run (17:02 UTC), which read it; it
was committed with the run's result in e451062. The selection record names the code commit (1e2b0db), which predates
the file; the file's content is the one the run read (its sha256 is in the manifest and the data contract).

## The critic's review of the operationalization (before the selection was frozen)

No blocking issue. Its should-change items were applied (payrolls, VIX, the neither-group rule for missing model
readings, a BH family without the seen conditions, the selection committed before the test with the test stage
checking it); its documentation items are the notes in "Choices" above. It confirmed that no test information
reaches the cut points or the selection (`cuts` reads val-A; `select` reads val-A, val-B and pooled validation).

## What was visible before the selection was frozen

The operator's own disclosures (the band check and the D1 statistics, which include test values) and their exact
reproduction. No coverage-curve, conditioning or book statistic on the test existed before `run test` (the curves'
runtime was measured on validation only). The validation results were visible when the operator chose the VIX and
payroll definitions; the choices follow the prompt's text, and neither changed the selected set.

## Reference checks (CLAUDE.md: verify before citing)

All 14 verified against primary bibliographic records (Crossref, RePEc/IDEAS, OpenAlex, the publishers, arXiv,
proceedings.neurips.cc, PubMed); none dropped.

| Reference | Verified record | Note |
|---|---|---|
| DellaVigna & Pollet (2009) | J. Finance 64(2): 709–749, doi 10.1111/j.1540-6261.2009.01447.x, "Investor Inattention and Friday Earnings Announcements" | Friday announcements: lower immediate response, more drift |
| Hirshleifer, Lim & Teoh (2009) | J. Finance 64(5): 2289–2325, doi 10.1111/j.1540-6261.2009.01501.x, "Driven to Distraction: Extraneous Events and Underreaction to Earnings News" | busy days measured by other firms' announcements |
| Da, Engelberg & Gao (2011) | J. Finance 66(5): 1461–1499, doi 10.1111/j.1540-6261.2011.01679.x, "In Search of Attention" | attention via Google search volume (not our measure) |
| Hong, Lim & Stein (2000) | J. Finance 55(1): 265–295, doi 10.1111/0022-1082.00206, "Bad News Travels Slowly: Size, Analyst Coverage, and the Profitability of Momentum Strategies" | slow diffusion in small, low-coverage stocks |
| Tetlock (2011) | Rev. Financ. Stud. 24(5): 1481–1512, doi 10.1093/rfs/hhq141, "All the News That's Fit to Reprint: Do Investors React to Stale Information?" | stale news: smaller reaction, later reversal |
| Fedyk & Hodson (2023) | J. Financ. Econ. 149(1): 92–113, doi 10.1016/j.jfineco.2023.04.008, "When can the market identify old news?" | recombined old news over-moves prices |
| Chan (2003) | J. Financ. Econ. 70(2): 223–260, doi 10.1016/S0304-405X(03)00146-6, "Stock price reaction to news and no-news: drift and reversal after headlines" | drift after news, reversal without |
| Bernard & Thomas (1989) | J. Account. Res. 27 (Suppl.): 1–36, doi 10.2307/2491062, "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?" | PEAD as delayed response |
| Boudoukh, Feldman, Kogan & Richardson (2019) | Rev. Financ. Stud. 32(3): 992–1033, doi 10.1093/rfs/hhy083, "Information, Trading, and Volatility: Evidence from Firm-Specific News" | the title has no "identified"; the identified/unidentified terms are the authors' NBER WP 18725 |
| Jiang, Li & Wang (2021) | J. Financ. Econ. 141(2): 573–599, doi 10.1016/j.jfineco.2021.04.003, "Pervasive underreaction: Evidence from high-frequency data" | drift after news, no reversal |
| Savor & Wilson (2013) | J. Financ. Quant. Anal. 48(2): 343–375, doi 10.1017/S002210901300015X, "How Much Do Investors Care About Macroeconomic Risk? Evidence from Scheduled Economic Announcements" | inflation, employment and FOMC days |
| Schoenegger, Tuminauskaite, Park, Bastos & Tetlock (2024) | Sci. Adv. 10(45): eadp1528, doi 10.1126/sciadv.adp1528, "Wisdom of the silicon crowd: LLM ensemble prediction capabilities rival human crowd accuracy" | the prompt's title is a paraphrase; five authors |
| Geifman & El-Yaniv (2017) | NeurIPS 30 (NIPS 2017): 4878–4887, arXiv 1705.08500, "Selective Classification for Deep Neural Networks" | risk–coverage curves |
| Kargarzadeh, N. Khaledian, Parvini, Ghatak & A. Khaledian (2026) | arXiv 2608.14014 (v1 14 Aug 2026, v2 18 Oct 2026; AI4F 2026 at ICAIF), "Buy the Rumor, Sell the News: When Is News Priced In?" | abstract: "markets underreact to numbers and overreact to stories" |

*Process note:* one verifying agent sent three Crossref API requests with an e-mail address in the User-Agent
(Crossref's "polite pool" convention) without authorization; it stopped there and disclosed it, and the
operator is told in the session's summary.

## The independent review of the branch (after the test)

An adversarial review (four lenses — statistics, protocol and look-ahead, paper wiring, report accuracy — and a
skeptic for every finding) confirmed 28 findings and refuted 5. None changed a number, a selection or a conclusion.
Fixed: the coverage curves' IC result was understated (Laya-Fin's IC with z_id at its frozen confidence gate is
positive in all three periods; now reported with the multiplicity caveat); "the 10:00 reading never beats the pre-open
reading" was false for d1-ultra on val-A; the paper's A16/A17 captions and the t36/t37/t43 notes said "the test was
evaluated once" where the operator's assistant's earlier looks at the test shaped them (now disclosed, with the
caveat of 36 statistics); the data contract lacked the VIX source and the payroll file; the timing map, `committed()`
and the selection's hash check had no test (now tested; 12 guard mutations turn a test red); a book on a
`selection_only` vendor label would have passed the timing guard (now refused); two break-even values were rounded
twice; t22 still called the live ledger count "the DSR's N". The refuted findings (E8's sign, the scope of the 2026
VIX read, A19's axes, a REPORT phrase) were checked and left as they are.

## Findings that shaped the reporting

- The validation selection did not hold on the test (REPORT §7): the paper may say where the signal lived on
  validation and that none of it held out of sample; no forward-test candidate exists.
- For Laya-Fin, d1-ultra's "material" and "P(no material effect) low" conditions moved the overnight gap on the test
  (z_on differences +0.17, t 2.9 and +0.13, t 2.6), not the move after the open: descriptive, outside the family.
- The family's smallest test p is the unselected d1-ultra × VIX(t−1) high (+0.135, t 3.1, q 0.79), with 129 of 138
  test sessions inside and 9 outside: a contrast against nine days, flagged as fragile.

## Owner decisions (REPORT §11)

1. The forward-test row: no NA-13b candidate qualifies, so nothing is added to §15 for NA-15 (the F3 conviction book
   already pre-registered stays as it is). *Recommendation:* add nothing.
2. Whether NA-16 shows the NA-13b figures in the exploratory section of the main text or the appendix. *Recommendation:*
   the appendix (figA16–figA19), with one paragraph in the exploratory section.

## Not done (by decision)

- No new lock read (NA-13's market file already holds the 2026 returns and SPY's legs).
- NA-13's tables and DSRs are not recomputed (the prompt); the paper now states their N (545) from NA-13's table,
  next to NA-13b's own N (1,620).
- No figure for the tradable versions' paths (the table carries them; the books' daily series are in
  `work/selective/books_daily.parquet`).
