# NA-13 REPORT — strategies and economic significance

Date: 2026-10-28 · Branch `feat/NA-13-strategies` (main checkout, cut from main @ 661aa4d) · Decisions:
`docs/decisions/NA-13.md` · PREREG: one §15 row, written before any test-period strategy return (commit 7a84e4b) ·
Numbers: `artifacts/NA-13/strategy_table.csv`, `results/*.json`, `fig7_data.csv`; daily series and positions in
`work/strategy/`.

**Bottom line (test split, 2026-01-02 → 2026-07-31; every pre-registered book reported, nulls included).**
- **No pre-registered strategy is profitable after costs.** At 10 bp per side every S-CONV, S-D0, S-D1 and S-D2
  book of the primary instrument (Laya-Fin) and of the API comparator (d1-ultra) has a negative net Sharpe. The
  only positive net Sharpes come from Laya-Fin's RG books, which traded on 3–6 test sessions with one name a
  side (|N̂| ≥ 0.5 is rare for it), and the anchor's gated S-D2 J at t+20 (+0.51).
- **Deflated Sharpe ≈ 0 everywhere.** With n_trials = 545 (the whole trials ledger) and about 138 trading days, the
  deflation benchmark SR0 is 0.26–0.30 per day (4.1–4.8 annualized); the largest DSR probability of any test book
  is 0.024.
- **S-CONV (A1.6, the primary strategy) is the price-only gap fade.** Ranking by U = V − G^lvl buys the day's
  losers and sells its winners because V is small next to G^lvl (NA-12: U ≈ −G^lvl). On test, Laya-Fin's S-CONV
  at D2 / t+5 shares 92% of its positions with the gap fade (99.8% on the same side); the daily returns correlate
  0.96. The anchor, whose V is uninformative, does as well (0.98).
- **Gross, nothing clears the placebo.** No test book's gross Sharpe reaches the 95th percentile of its 100
  random-signal books; the highest are Laya-Fin's gated S-D0 (90th and 93rd percentiles; gross Sharpe 1.18 and
  1.88; break-even cost 3.7 and 8.3 bp per side) and its RG books (90th–92nd).
- **Costs decide the sign.** One-day books trade about 4.6 dollars a day per dollar of capital (both legs, the
  hedge, entry and exit), five-day books 0.8, twenty-day books 0.19. Break-even costs are at most 8.3 bp per side
  (gated S-D0, t+1) and 5.1 bp for S-CONV (D1, t+5).
- **Capacity** at 1% of the 20-session ADV (median over decisions): about $20M for one-day books, $40M for
  two-day, $100–120M for five- and six-day, $390–420M for twenty-day books.
- **Exploratory add-on (operator item 9; after unblinding, no claim).** The MA20/MA50-cross analysis
  reproduces the operator's validation numbers exactly (none −41.1 bp at 5 days, NW t −2.08). On test the 5-day
  no-news effect is −14.4 bp (t −0.69); the tradable no-news fade nets −0.46 Sharpe at 10 bp (gross 0.98; 81st
  gross placebo percentile; DSR 0.0003), after +1.83 on validation, where its design was chosen.
- **Limitation:** short-sale borrow costs are not modelled (S&P 500 names are general collateral).

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 portfolios: S-CONV (D2, D1), S-D0, S-D1, S-D2, gated variants | done | `src/newsaction/strategy/portfolios.py` (timing, sides, engine), `run.py` (rules, signals, inputs) |
| S2 costs and capacity | done | `strategy/costs.py`, `strategy/capacity.py` |
| S3 DSR, golden test against ATOM, n_trials | done | `strategy/dsr.py`; `tests/golden/dsr_atom.json` (computed once by `scripts/na13_dsr_golden.py` under ATOM's venv) |
| S4 benchmarks: gap fade, vendor sentiment, 100-seed placebo | done | `strategy/run.py` (`rules`, `placebo`) |
| S5 outputs: strategy table (val-B reference and test), Figure 7 data | done | `artifacts/NA-13/strategy_table.{csv,tex}`, `fig7_data.csv` (`strategy/tables.py`) |
| Test-period returns (operator item 3) | done | `strategy/market.py`; `work/strategy/market_test.parquet`; `artifacts/NA-13/market_test.json` |
| Exploratory MA-cross add-on (operator item 9) | done | `strategy/ma_cross.py`; `results/ma_cross.json` |
| Trials, contract | done | `ledgers/trials.jsonl` (+200 rows); `strategy/contract.py`; `docs/DATA_CONTRACT.md` NA-13 section |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 timing | `tests/test_strategy_timing.py`: entry > decision for D0 / D1 / D2 on full, half and DST-edge days; every stored position of both splits has entry > decision and each input instant (latest article, reaction, tier ranking close, β/ADV close, the frozen fits) ≤ decision (`positions_{val_b,test}.parquet`); the guard refuses a close entry at the decision and a previous-close entry. **Mutations RED:** S-D2 entered at the day-t close; S-D2 at the open of t; S-D0 at the previous close; the D1 fill without its lag; the guard removed; missing instants accepted | PASS |
| AC2 costs | `tests/test_strategy_costs.py`: a toy book (2 longs, 2 shorts, betas 1.2 / 0.8 / 1.0 / 1.5, SPY +1%) reproduces gross 3.00% − 2 × (2 + 0.25) × 10 bp = net 2.55% exactly; the hedge's 0.25 is charged; calendar-time turnover and capacity by hand. **Mutations RED:** hedge left out, exit side left out | PASS |
| AC3 DSR | `tests/test_strategy_dsr_golden.py`: 11 golden cases from ATOM's `deflated_sharpe_ratio` (normal, skewed, fat-tailed, given trial variance, benchmark SR, degenerate) agree to 0.0 (≤ 1e-6 required); n_trials = 545 = every ledger row (`results/strategy_summary.json`: 345 selection trials + 200 "strategy" rows). **Mutation RED:** Mertens correction dropped | PASS |
| AC4 placebo | 100 random-signal books per universe (51 universes a split), `work/strategy/placebo_{split}.parquet`; percentiles of every book's gross and net Sharpe in the table (§7) | PASS |
| AC5 frozen files, registration | `git diff 661aa4d -- configs src/newsaction/panel/{targets,reactions}.py src/newsaction/analysis/{spec,inference,shapley,metrics}.py` empty; PREREG +1 row in §15 only; freeze hash 523e7589… unchanged; every NA-13 file in `work/MANIFEST.json` and `docs/DATA_CONTRACT.md` (`python -m newsaction.io check`: OK) | PASS |
| AC6 S-CONV first, ranks rebuilt | S-CONV is the first family in every table and here; D2 and D1, every exit; U = V − G^lvl with V from the frozen maps. `test_ac6_rebuild_one_day_of_s_conv_d2_ranks` rebuilds the busiest test day's D2 longs and shorts from Laya-Fin's stored N̂, the frozen V map and `targets_test`'s G^lvl with the pooling rule written out, and matches the stored positions and scores; `test_signal_definitions` pins U, J, RG, the gap fade and Ñ. **Mutations RED:** V instead of U; unsigned J; RG without the \|N̂\| cut; pooling at 5 | PASS |
| GAC1 | `make verify` exit 0: 1,960 passed, 3 skipped, 2 xfailed (§12) | PASS |
| GAC2 | `git status --porcelain Data/` empty | PASS |
| GAC3 | 2026 data only through the lock (§3); `tests/test_blinding.py` passes | PASS |
| GAC4 | no API call; `ledgers/spend.jsonl` unchanged; NA-13 spend $0 | PASS |
| GAC5 | NA-13 section in `docs/DATA_CONTRACT.md` (19 files), sha256 = manifest | PASS |

**Mutations (13, all RED).** A session script (scratchpad `na13/mutate.py`) applied each, cleared `__pycache__`, ran
the guard's tests and restored the file (sha256 checked; `git status` unchanged afterwards).

## 3. Test-period data (operator item 3)

`targets_test.parquet` lacks the raw open → close return, SPY's open, the volumes for the ADV and the 10:00 legs.
They were read once through the lock: `NA_UNBLIND=1 python -m newsaction.strategy.market test`.

| ts (UTC) | name | purpose | caller |
|---|---|---|---|
| 2026-10-28 22:54:21.649 | prices_raw_2026 | targets | `strategy/market.py:test_panel` |
| 2026-10-28 22:54:21.695 | total_return_check_2026 | targets | `strategy/market.py:test_panel` |
| 2026-10-28 22:54:21.719 | bars30_2026 | targets | `strategy/market.py:test_panel` |

- `lock.require_unblind` passed (freeze hash 523e7589… equals the record; the Deviations log an unchanged prefix).
- The frames were assembled with NA-01's own grid (`panel.build.assemble`, as `test_returns_panel` does) and
  NA-10's intraday route (`bars.derive.test_intraday_panel`).
- Before the read, `market rehearse` ran the same route with empty blinded frames; its val-B rows equalled the
  public build on all 17 columns (largest difference 0.0).
- After the read the test build refuses to write unless its val-B rows equal the public build (17 columns, 0.0)
  and its test `r_cc`, `r_spy_cc`, `ar_cc` equal `targets_test` (0.0). Output: 73,498 rows, 145 sessions — the
  rows of `targets_test`.
- **Last two sessions.** The blinded raw prices end on 2026-07-29, so 2026-07-30 and 07-31 have no official open;
  D0 events of those days and D2 entries on them have no fill and are dropped (up to 419 events a book; also
  Dayforce's three sessions after its February 2026 acquisition). Holding days on 07-30 and 07-31 earn the
  adjusted close → close return.

## 4. S-CONV — the primary strategy (A1.6)

Rank by U = V − G^lvl; long the top 20% (price below value), short the bottom 20%; within tier or pooled;
β-hedged with SPY; calendar time. Test split; Sharpe annualized; in brackets the percentile among 100
random-signal books on the same events.

| Instrument | Point | Exit | SR gross [pct] | SR 5 bp [pct] | SR 10 bp [pct] | SR 20 bp [pct] | DSR 10 bp | Turnover / day | Capacity |
|---|---|---|---|---|---|---|---|---|---|
| Laya-Fin | D2 | t+1 | −3.15 [0] | −6.89 [16] | −10.64 [51] | −18.10 [95] | 0.000 | 4.65 | $28M |
| Laya-Fin | D2 | t+5 | +0.61 [68] | −0.69 [87] | −1.98 [95] | −4.58 [99] | 0.000 | 0.90 | $138M |
| Laya-Fin | D2 | t+20 | +0.22 [58] | −0.36 [66] | −0.94 [76] | −2.11 [87] | 0.000 | 0.20 | $531M |
| Laya-Fin | D1 | C_t | +1.61 [83] | −2.56 [98] | −6.74 [100] | −15.08 [100] | 0.000 | 4.68 | $20M |
| Laya-Fin | D1 | t+1 | −0.97 [20] | −3.48 [41] | −5.99 [55] | −10.99 [77] | 0.000 | 2.32 | $40M |
| Laya-Fin | D1 | t+5 | +1.23 [84] | +0.02 [88] | −1.19 [89] | −3.62 [95] | 0.000 | 0.75 | $120M |
| Laya-Fin | D1 | t+20 | −0.67 [36] | −1.22 [40] | −1.77 [45] | −2.87 [54] | 0.000 | 0.19 | $418M |
| d1-ultra | D2 | t+1 / t+5 / t+20 | −3.48 / −0.09 / +0.02 | −7.22 / −1.40 / −0.62 | −10.97 / −2.72 / −1.26 | −18.47 / −5.35 / −2.54 | 0.000 | | |
| d1-ultra | D1 | C_t / t+1 / t+5 / t+20 | +0.03 / −2.26 / +0.32 / −0.88 | −4.19 / −4.81 / −0.98 / −1.43 | −8.42 / −7.35 / −2.27 / −1.98 | −16.80 / −12.41 / −4.87 / −3.08 | 0.000 | | |
| anchor (uninformative) | D2 | t+1 / t+5 / t+20 | −2.91 / +0.71 / +0.13 | | −10.04 / −1.72 / −0.92 | | 0.000 | | |
| anchor (uninformative) | D1 | C_t / t+1 / t+5 / t+20 | +1.10 / −1.38 / +0.90 / −0.68 | | −7.45 / −6.54 / −1.64 / −1.79 | | 0.000 | | |
| *gap fade (price-only, V = 0)* | D2 | t+1 / t+5 / t+20 | −3.52 / +0.44 / −0.09 | −7.19 / −0.78 / −0.61 | −10.87 / −2.01 / −1.13 | −18.24 / −4.45 / −2.16 | 0.000 | | |
| *gap fade* | D1 | C_t / t+1 / t+5 / t+20 | +0.78 / −1.57 / +0.40 / −0.98 | −3.44 / −4.13 / −0.84 / −1.54 | −7.66 / −6.69 / −2.08 / −2.10 | −16.06 / −11.79 / −4.57 / −3.22 | 0.000 | | |

**Reading.**
- *The value adds little to the price.* V is small next to the day's move, so U ≈ −G^lvl and S-CONV is close to
  the gap fade: positions overlap 92% (Laya-Fin, D2 / t+5; 89% at D1 / C_t; 90% for d1-ultra), with the same
  side 99.8% of the time, and the daily returns correlate 0.96 (0.93; 0.94).
- *Adding V tilts the fade a little, and not because of the news.* Laya-Fin's gross Sharpe is above the gap
  fade's at all seven rungs, by 0.2–0.8 (D2 t+5 0.61 vs 0.44; D1 C_t 1.61 vs 0.78; D1 t+5 1.23 vs 0.40). The
  anchor's V is uninformative, yet it beats the gap fade at all seven rungs by similar margins (0.71, 1.10,
  0.90). So the tilt is no evidence that V carries value; no difference is tested. d1-ultra's larger V (κ 0.59
  at C_t in NA-12) lowers the gross Sharpe at four of the seven rungs.
- *After costs, every rung loses.* The best S-CONV book breaks even at 5.1 bp per side (Laya-Fin D1 / t+5).
- *By tier (descriptive sub-books, not separate trials).* The Top-100 sub-book of Laya-Fin's D2 / t+5 book has a
  gross Sharpe of 2.49 and +0.90 net at 10 bp, against −0.19 / −0.68 gross for Mid and Rest. The price-only gap
  fade shows the same Top-100 pattern (2.00 gross, +0.40 net). This agrees with NA-12's larger κ for Top-100, but
  it is a cut of a null book, not a finding.
- *The placebo's net percentiles need care.* When costs dominate the mean, the net Sharpe (μ − c)/σ is less
  negative for more volatile books, so a book can rank high among random books net of costs without any skill
  (D1 / C_t: 83rd gross, 100th at 10 bp). The gross percentile is the comparison of signal quality; the table also
  gives the percentile of the mean net return (`placebo_pct_mean_net_10`, a descriptive supplement added after
  seeing this, no claim).

**Validation reference (val-B, 54–59 sessions; the maps and gates were fit on val-A, so val-B is out of sample).**
Laya-Fin S-CONV gross: D2 t+1 / t+5 / t+20 = −4.53 / −1.43 / +2.20; D1 C_t / t+1 / t+5 / t+20 = +2.41 / +0.19 /
−1.45 / +1.16; at 10 bp all negative (−0.11 to −15.89). The gap fade on val-B: −4.79 / −2.02 / +1.47 at D2.

## 5. S-D0, S-D1, S-D2

Test split, Laya-Fin unless noted; all books' rows are in `strategy_table.csv`.

| Book | Exit | SR gross [pct] | SR 5 / 10 / 20 bp | DSR 10 bp | Names a side |
|---|---|---|---|---|---|
| S-D0 Ñ | C_t | +0.35 [64] | −2.85 / −6.03 / −12.35 | 0.000 | 19.0 |
| S-D0 Ñ | C_{t+1} | −0.95 [22] | −2.77 / −4.58 / −8.19 | 0.000 | 19.0 |
| S-D0 Ñ gated | C_t | +1.18 [90] | −0.43 / −2.03 / −5.23 | 0.000 | 4.8 |
| S-D0 Ñ gated | C_{t+1} | +1.88 [93] | +0.75 / −0.38 / −2.65 | 0.000 | 4.8 |
| S-D1 J | C_t / t+1 / t+5 | +0.76 / −0.15 / −2.35 [6] | −9.70 / −6.03 / −5.63 at 10 bp | 0.000 | 18.6 |
| S-D1 RG | C_t / t+1 / t+5 | +0.02 / −0.04 / +1.12 | −0.32 / −0.33 / +1.02 at 10 bp | ≤ 0.008 | 1.0 |
| S-D2 J | t+1 / t+5 / t+20 | −1.14 / −2.69 [3] / −1.77 | −10.61 / −6.45 / −3.55 at 10 bp | 0.000 | 24.9 |
| S-D2 J gated | t+1 / t+5 / t+20 | −1.52 / −0.90 / −1.01 | −6.14 / −2.91 / −2.01 at 10 bp | 0.000 | 8.0 |
| S-D2 RG | t+1 / t+5 / t+20 | +1.87 [90] / +1.69 [92] / −0.55 | +1.61 / +1.50 / −0.64 at 10 bp | ≤ 0.024 | 1.0 |
| S-D2 RG gated | t+1 / t+5 / t+20 | +0.24 / +0.29 / −0.83 | −0.11 / +0.19 / −0.88 at 10 bp | ≤ 0.002 | 1.0 |
| d1-ultra S-D0 Ñ (gated) | C_t / t+1 | +0.10 / −1.05 (+1.15 / +0.20) | −6.41 / −4.93 (−2.52 / −2.30) at 10 bp | 0.000 | 19.0 (6.2) |
| d1-ultra S-D2 J / RG | t+5 | +0.39 / +0.15 | −2.37 / −1.98 at 10 bp | 0.000 | 24.9 / 12.0 |
| vendor sentiment (D0; possible look-ahead upper bound) | C_t / t+1 | +0.27 [62] / −1.36 [11] | −6.24 / −5.32 at 10 bp | 0.000 | 19.0 |

- **S-D0** has no pre-registered support (NA-12: H1b failed). Its ungated book is null gross. The gated book
  keeps about a quarter of the events (Laya-Fin's val-A 70th percentile of Q1 confidence). It has the highest
  gross Sharpes on test (1.18 at C_t, 1.88 at C_{t+1}; 90th and 93rd placebo percentiles) and breaks even at
  3.7 and 8.3 bp per side. With 545 trials its DSR is 0.000.
- **S-D1 and S-D2 (J).** J is signed by the move: J > 0 (too small) continues the move, J < 0 reverses it.
  Neither model's J has a positive gross Sharpe at t+5; Laya-Fin's S-D2 J at t+5 is at the 3rd placebo
  percentile. This matches NA-12: IC(J, y2) was negative for d1-ultra and Call B's judgements carried no
  information about y2.
- **RG books are tiny.** Laya-Fin's |N̂| reaches 0.5 on 82 test D0 events (the D1 RG universe) and 129 D2 events;
  a session needs 5 of them for one name a side (k = ⌊0.2·n⌋), so its RG books traded on 3–6 sessions of the test.
  Their positive net Sharpes come from a handful of two-stock days in an otherwise flat series; DSR ≤ 0.024. The anchor's |N̂| never reaches 0.5: its RG books are empty and not logged as trials. d1-ultra's
  RG books (8–12 names a side) are null.
- **Pooling.** With k = ⌊0.2·n⌋ ≥ 10 needing 50 events in a tier, most test sessions pool small tiers. Of
  Laya-Fin's ungated positions, 31% were ranked within their own tier, 55% in the session's pool of small tiers
  and 14% with the whole session.

## 6. Costs, turnover and capacity

- **Costs.** 5 / 10 / 20 bp per side on every traded dollar: both legs and the SPY hedge, at entry and at exit,
  with no netting across cohorts.
- **Turnover** (median over test books by holding length L, dollars traded a day per dollar of capital): 4.61
  (L = 1), 2.27 (L = 2), 0.89 (L = 5), 0.75 (L = 6), 0.20 (L = 20), 0.19 (L = 21). At 10 bp a one-day book
  pays about 1.16 a year in costs per dollar, a five-day book 0.22, a twenty-day book 0.05.
- **Break-even cost** (gross mean ÷ turnover; test). Gated S-D0 8.3 bp (t+1) and 3.7 bp (C_t); S-CONV Laya-Fin
  D1 / t+5 5.1 bp, D2 / t+5 2.4 bp, D1 / C_t 1.9 bp; gap fade D2 / t+5 1.8 bp; vendor sentiment D0 / C_t 0.4 bp.
- **Capacity.** The median over decisions of the capital at which the most constrained trade reaches 1% of the
  20-session ADV; the 10th percentile is in the CSV.
  - By holding length: L = 1 $20M; L = 2 $40M; L = 5 $102M; L = 6 $118M; L = 20 $393M; L = 21 $418M.
  - Gated S-D0 books are smaller ($7–17M), because their few names carry larger weights.

## 7. Benchmarks and the placebo

- **Gap fade** (price-only; −G^lvl). It is the S-CONV rank with V = 0, at the same points, exits and costs (§4).
- **Vendor sentiment** (NA-09's `N_hat` at D0). Gross +0.27 at C_t and −1.36 at C_{t+1}, and −6.24 / −5.32 net
  at 10 bp. Its labels were produced retrospectively (CLAUDE.md A6; NA-12 owner decision 1), so it is a possibly
  look-ahead-contaminated **upper bound**, not the benchmark. Even so it trades no better than the models; its
  daily returns correlate 0.35 with Laya-Fin's S-D0.
- **Random-signal placebo.** 100 uniform signals (seeds 2027–2126) per rule's own events, the same sides, hedge
  and costs. Typical spread on test: S-CONV D2 / t+5 gross Sharpe 5th / 50th / 95th percentiles −2.12 / −0.04 /
  2.23 (net 10 bp −6.25 / −4.05 / −1.99); S-D0 / C_t −1.99 / −0.29 / 2.35. No test book's gross Sharpe reaches the
  95th percentile of its placebo; four reach the 90th (Laya-Fin's gated S-D0 at both exits, its S-D2 RG at t+1
  and t+5). Placebo bands are in `fig7_data.csv` (`series = placebo_band`).

## 8. Deflated Sharpe and the trial count (PRD S3, operator item 6)

- **n_trials = 545** = every row of `ledgers/trials.jsonl` when the DSR was computed:
  - **345 selection trials** of NA-03…NA-11:
    - filters 94 (filter 10, frontier 70, hyperparameters 12, sensitivity 2);
    - models 166 (tournament stage 1 42, stage 2 30, probes 30, reading validity 4, trained 4, final selection 6,
      baselines 50 and their grids 58 — the selection of the benchmark models);
    - encoding 27 (encoding 21, anchoring 3, numeracy 3).
  - **200 "strategy" rows of NA-13:**
    - 174 pre-registered: 87 non-empty books × {val-B, test};
    - 26 exploratory: the add-on's 12 group statistics and its tradable book, × {validation, test}.
  - Cost levels and placebo seeds are not separate rows; the 9 empty anchor RG books are not rows.
- **DSR.**
  - Method: ATOM's formula (golden-tested), on each book's daily net series at 5 / 10 / 20 bp.
  - Trial variance: the analytic (1 + SR²/2)/(T − 1), because the ledger's other trials are ICs, recalls and
    losses, not Sharpes.
  - Benchmark: SR0 = 0.26–0.30 per day (4.1–4.8 annualized). No book comes near it; the largest test DSR
    probability is 0.024 (Laya-Fin S-D2 RG, t+5) and every other is ≤ 0.008.
  - Sensitivity: SR0 is 0.263 per day at N = 545 and T = 138, against 0.251 at N = 345 (selection trials only);
    no conclusion changes.

## 9. Exploratory: news and a moving-average cross (operator item 9; requested after unblinding; no claim)

Design fixed by the operator before any test result (PREREG §15 NA-13 row (xiii); `strategy/ma_cross.py`):
- MA20 / MA50 crosses of the adjusted close, on the long panel's rows, for members at t.
- Signed Σ ar_cc over t+1..t+5 and t+1..t+20.
- Groups by the symbol's latest D0 event in t−2..t, by the sign of Laya-Fin's and d1-ultra's N̂.
- Day means, then their mean, with a Newey–West t at k − 1 lags.

**Reproduction.** On validation (2025-07-01 … 2025-12-31) the code reproduces the operator's numbers to the
reported precision: all −15.8 bp (NW t −0.94), none −41.1 bp (t −2.08). The cross count is 1,345 against the
operator's 1,347; the two-cross difference is unexplained and moves no reported number. Reproducing it fixed
three details the brief left open:
- the moving averages run over the panel's rows, not the full grid;
- members only;
- events matched by symbol.

| Group | Validation 5 d | Validation 20 d | Test 5 d | Test 20 d |
|---|---|---|---|---|
| all | −15.8 bp (t −0.94; 1,293) | −13.9 (−0.58) | −5.6 (−0.34; 1,580) | −42.9 (−1.45) |
| none (no D0 event in t−2..t) | −41.1 (−2.08; 686) | −15.8 (−0.52) | −14.4 (−0.69; 919) | −76.7 (−2.55) |
| agree, Laya-Fin | +1.1 (0.04) | −51.3 (−1.34) | −23.1 (−0.63) | −4.3 (−0.04) |
| disagree, Laya-Fin | −26.3 (−0.74) | −31.9 (−0.47) | −9.8 (−0.38) | −178.8 (−2.23) |
| agree, d1-ultra | −10.3 (−0.35) | −25.6 (−0.87) | −4.4 (−0.12) | +20.9 (0.19) |
| disagree, d1-ultra | −3.3 (−0.13) | −56.1 (−1.17) | −24.3 (−0.71) | −188.7 (−2.35) |

- **The validation result does not replicate at its own horizon.** The 5-day no-news fade is −14.4 bp on test
  (t −0.69), about a third of validation's.
- At 20 days the test shows a no-news effect (−76.7 bp, t −2.55) and large "disagree" effects (−179 / −189 bp,
  t −2.2 / −2.4). Those are 3 of the add-on's 24 test statistics, on 103–123 cross days, with no correction:
  noise until shown otherwise.
- **Tradable no-news fade** (short up-crosses, buy down-crosses; next open → C_{t+5}; β-hedged).

  | | Validation | Test |
  |---|---|---|
  | Positions | 686 | 920 |
  | Gross Sharpe | +3.85 | +0.98 |
  | Net Sharpe 5 / 10 / 20 bp | +2.84 / +1.83 / −0.20 | +0.26 / −0.46 / −1.91 |
  | Placebo pct, gross / 10 bp | 99th / 100th | 81st / 90th |
  | DSR, 10 bp | 0.035 | 0.0003 |
  | Capacity (median) | $34M | $47M |

  The validation numbers are in-sample for the design.

## 10. Limitations

1. **No borrow costs.** Short-sale borrow costs are not modelled (S&P 500 names are general collateral).
2. **The D1 fill.** It is the 10:00 bar's closing price, stamped one second after the decision (PREREG §2.5);
   the first trades after 10:00 may differ. FMP's first bar starts at the first trade, not the auction (NA-10).
3. **No impact term; no netting.** Costs are flat per side; cohorts exiting and entering the same name on one day
   are not netted (conservative).
4. **Equal weights are restored daily** within a cohort (the usual calendar-time convention). That rebalancing is
   not charged.
5. **The SPY hedge removes market beta only;** the sector component of the abnormal return is not hedged (no
   tradeable sector instruments at the open, NA-01).
6. **The last two test sessions** have no official open (§3).
7. **Pooling.** Most test sessions pool small tiers, so the books are only partly tier-neutral (§5).
8. **The API comparators.** Their contamination caveat applies (NA-12 §10.5): released after the test period,
   with no contamination signature.

## 11. Spend, look-ahead self-check, deviations, STOPs, owner decisions

- **Spend.** $0. No API call, no Kaggle run, no FMP request (spend and FMP ledgers unchanged); cumulative
  $15.73. ATOM's venv ran once to produce `tests/golden/dsr_atom.json`, with `PYTHONDONTWRITEBYTECODE=1`; ATOM's
  `git status` was empty before and after. Nothing was written to ATOM's database or repository.
- **Look-ahead self-check** (every input of every position; `positions_*.parquet`, checked by the tests):

  | Input | Available at | ≤ decision |
  |---|---|---|
  | news: the state's latest article | `latest_et` (max t_avail) | D0/D1 ≤ 09:15 of t; D2 ≤ close(t) |
  | reaction G, G^lvl | the 10:00 bar end (D1), close(t) (D2) | = decision |
  | tier | close of the prior month's ranking session | yes |
  | β_m, ADV20 | close of the session before entry | D0/D1 close(t−1); D2 close(t) |
  | V, Ñ maps and gates | close of 2025-09-30 (val-A fits; e5 to t+4) | val-B and test only |
  | outcomes | the market panels (test through the lock, §3) | not inputs |

  Val-A strategies were not run because the maps and gates read val-A.
- **Deviations.** None from a definition. The operationalization is the §15 NA-13 row, written before any
  test-period strategy return. The add-on is labelled exploratory. The supplementary mean-return percentile
  (§4) was added after seeing the net-Sharpe percentiles' behaviour; it is descriptive.
- **STOP conditions.** Freeze-hash check: passed. Any API call needed: no. None fired.
- **Owner decisions.**
  1. **The direction of J and RG.** §7 defines both relative to a direction, so the books trade sign(G)·J and
     N̂ − G (§15 NA-13 row (iv)). *Recommendation: keep;* the unsigned version buys "too small" rises and "too
     small" falls alike. If you want the unsigned books reported as well, they are cheap but add trials.
  2. **Report the gross placebo percentile as the headline comparison** (§4, the net-Sharpe percentile caveat).
     *Recommendation: yes,* with the net percentiles in the appendix table.
  3. **The Top-100 S-CONV sub-book** (+0.90 net at 10 bp) is a descriptive cut. *Recommendation: mention it in
     NA-14 only as such,* next to the gap fade's +0.40; it is not a test.
  4. **The add-on's 20-day test statistics** (no-news and disagree reversals). *Recommendation: exploratory
     footnote at most;* the pre-specified 5-day effect did not replicate.

## 12. Files and `make verify`

- **Code (new).** `src/newsaction/strategy/`: `__init__.py`, `market.py`, `portfolios.py`, `costs.py`,
  `capacity.py`, `dsr.py`, `run.py`, `tables.py`, `contract.py`, `ma_cross.py`; `scripts/na13_dsr_golden.py`.
- **Tests (new).** `tests/test_strategy_timing.py`, `test_strategy_costs.py`, `test_strategy_dsr_golden.py`
  (the PRD's three), `test_strategy_portfolios.py`, `test_strategy_ma_cross_trials.py`;
  `tests/golden/dsr_atom.json`.
- **Data (`work/strategy/`, registered).** `market_public`, `market_test`, `books_{val_b,test}`,
  `positions_{val_b,test}`, `placebo_{val_b,test}`, `placebo_paths_{val_b,test}`, `ma_cross_books`.
- **Artifacts.** `artifacts/NA-13/`: `REPORT.md`, `strategy_table.{csv,tex}`, `fig7_data.csv`,
  `market_test.json`, `results/{books_val_b,books_test,ma_cross,strategy_summary}.json`.
- **Ledgers.** `trials.jsonl` +200 rows (hash chain verified); `test_access.jsonl` +3 rows (§3).
- **Docs.** `docs/PREREG.md` §15 +1 row; `docs/DATA_CONTRACT.md` NA-13 section; `docs/decisions/NA-13.md`.
- **`make verify`.** Exit 0.
  - Lint and format clean; `mypy --strict` clean on 147 source files.
  - pytest: 1,960 passed, 3 skipped, 2 xfailed (NA-10's strict ones).
  - Manifest: 286 artifacts OK. Ledgers OK (trials 545, test_access 29).
  - Peak RSS 7.8 GB.
  - The first run failed one test: `tests/test_blinding.py` caught a contract string containing "read_sealed";
    reworded, then re-run.
