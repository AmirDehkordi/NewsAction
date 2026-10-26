# NA-04 REPORT — states: context, codebook, masking, question battery v1

Date: 2026-10-25, revision 4 on 2026-10-26 · Branch `feat/NA-04-states` (cut from `main` @ `45b3da0`) · Decisions:
`docs/decisions/NA-04.md` · Artifacts: `artifacts/NA-04/{token_stats.csv, leak_scan.csv, examples.md, summary.json,
build_states.json}`.

**Result.** Every decision-model input of the paper now exists as canonical JSON:
- Call A on D0: 47,125 states, all splits including test (inputs only).
- Call A on D2: 61,405 states (PREREG A3.1).
- Call B on D2: 41,852 states, train / val-A / val-B only.
- 595 optional A3.5 market states.
- The NA-07 encoding samples (3,000 events × E0–E4) and a 1,000-event unmasked twin for NA-06.

Main results:
- **Masking.** On val-A the independent scanner finds:
  - company-name or ticker hits in 8 of 8,923 D0 states (0.09%) and 8 of 11,148 D2 states (0.07%);
  - no year or date (target < 0.5% each);
  - price talk (moves, quotes or levels) in 0 D0 states and 5 D2 states (0.04%); the bar is the same 0.5%
    (revision 4);
  - on the unmasked twin, name / ticker hits in 89.1% of states and year / date hits in 92.0%.

  The third verification labelled residues by hand. Its date residue fell from 3.86% to 0.13% of D0 states
  (revision 3). Its company name / ticker residue is 1.29% of D0 and 1.00% of D2 states of the revision-2 build
  (1.26% / 0.97% on the revision-3 build, plus about 30 D0 states with the name in Korean or Japanese). This
  residue is accepted (PREREG §15 NA-04 row 7); NA-06's identification probe measures what remains
  identifiable. The fourth verification found price talk in 2.52% of D0 and 3.25% of D2 states by its own
  scripts. On the revision-4 build those scripts find nothing real, and a full listing of the cents amounts left
  finds about 0.01% (§ Revision 4).
- **Look-ahead and pre-market talk.** Three kinds of article are in no state:
  - move explainers ("Why … Stock Is Up Today", "Why Micron Technology Rallied Today", StockStory's "What
    Happened? Shares of …");
  - TradingView reposts, whose vendor timestamps often precede their content (revision 3);
  - non-English articles (revision 4, operator decision B), because masking and the price scrubbers are
    English-only.

  The third verification found DGX's 2025-07-22 earnings jump and its earnings summary in the 07-21 pre-open
  state. The fourth found about 9 val-A D0 states with the company's own pre-market move, in Portuguese or
  Spanish ("dispararam mais de 27% ... pré-mercado"). 978 D0 events (2.03%) have no state:
  - 871 have every listed article excluded (PREREG §15 NA-04 rows 6 and 8);
  - 107 lost all their text to the price-talk scrub.
- **Availability.** Every block is checked with `pit.check_inputs` at its decision point. A call rule adds that only
  Call B's `reaction_so_far` may read the D2 reaction, and only `d2_reaction` columns.
- **Tokens.** p95(state, Call A, E3) = 766 ≤ 900. With the documented tightening (§3.4), every Call A and Call B state
  plus its longest core question fits Laya's 1,024 tokens.
- **Questions.** `configs/questions_v1.yaml` is frozen (sha256 in `configs/frozen.yaml`). It uses every PREREG §7 /
  A2.2–A2.3 string verbatim and has no `noul`.

**Blinding.**
- No return of a session ≥ 2026-01-02 was read, joined or summarized.
- Test-period rows exist only for Call A and carry t−1 context words, from the NA-01 test inputs and the `Data/` closes
  that PREREG §15 (NA-00 row 2) allows for t−1 features.
- The D2 reaction comes from `panel.reactions.build_reactions(period="public")`, which refuses test rows.
- No module in `newsaction.states` reads the sealed directory or calls the lock.
- `ledgers/test_access.jsonl` is unchanged (2 NA-01 `write` entries).
- No val-B statistic of any return was computed.

## Revision 4 — after the fourth verification's price-talk finding (2026-10-26)

The fourth verification passed AC1–AC7 and GAC1–GAC5. It found price talk that AC2's metrics do not measure.
PREREG §6.3 removes share-price levels and percent moves, §6.4 strips pre-market price talk from Call A, and the
PRD bars raw prices. Its independent scripts found (val-A, revision-3 build, about 90–95% precision on hand
checks):

| Price talk | D0 | D2 / Call B | Scanner reported |
|---|---|---|---|
| share-price levels ("shares closed yesterday at $242.66", "Das Papier kostete zuletzt 72,99 US-Dollar") | 1.12% | 1.61% | 0.01% |
| price targets not written "$X" ("at USD 220", "38,36 € / share") | 0.62% | 0.69% | — |
| percent moves (incl. MarketBeat's "Trading 2.4% Higher", 0.54% of D0, rises only) | 1.10% | 1.36% | 0.09% |
| any of these | **2.52%** | **3.25%** | |

- About 9 val-A D0 states carried the company's own pre-market or after-hours move. These were in Portuguese or
  Spanish, and NA-02's language hint had not flagged them. That move is the D0 overnight target: DAY 2025-08-18
  read "dispararam mais de 27% ... pré-mercado" against an overnight return of +24.7%, and GPN 2025-07-16 read
  "+6% en las operaciones previas al mercado" against +6.0%.
- No look-ahead: every timed hit was pre-market before 09:15 ET or about a past session.
- NA-02 scrubs "Trading Down 3.1%", "Shares Up 2%" and "Stock Price Down 1.7%", but not "Trading 2.4% Higher".
  That form exists only for rises, so the residue was sign-dependent.

**Operator decisions (2026-10-26).** Fix it now, before any API spend, because states are cached by their sha256.
Apply decision B of 2026-10-25 (drop non-English articles) at the states step. Recorded in PREREG §15 NA-04
row 8.

**What changed, first pass** (commits `940668d`, `c03a704`):
- **Non-English articles** are in no state (`build.non_english`, `configs/states.yaml`
  `news_exclusion.non_english`; Decisions → States). The rule looks at:
  - non-Latin script;
  - distinct function words of 13 languages against English ones (lower case or capitalized only, so DE is not
    "de");
  - words with non-English letters.

  It flags 22,960 of 296,082 event articles (7.75%); NA-02's hint flagged 5.0%. It finds 98–100% of each
  non-English residue class (the hint: 51–98%), and 205 sampled flags were all non-English.
- **Move explainers.** The title rule now also takes "Why Micron Technology Rallied Today", "Why CoreWeave
  Rocketed as High as 26% Today" and "Why Airline Stocks Are Flying High Today": a move word between "why" and
  "today". The old rule needed the singular "stock" or "shares", so 188 event articles had escaped. "Here's Why
  We Think F5 Might Deserve Your Attention Today" is kept. Corpus explainers: 8,760 (7,535 before).
- **Masker, English price talk:**
  - share-price levels after a verb (`_LEVEL`);
  - a currency amount after a share word unless it is per share, a size, a total or a fundamental
    (`_SHARE_LEVEL`; possessive amounts);
  - the direction after the number ("Trading 2.4% Higher", "Moves 22.8% Higher", "closing 1% lower");
  - moves as nouns ("1.95% Stock Rise", "closed at a 1.13% decline");
  - price targets in any notation ("from GBX 420 to GBX 500" → "raised by about 19%");
  - "$210/Share" deal prices.
- **Scanner:** the same classes with its own rules.

**What changed, second pass** (commits `8bdf5bc`, `dd11b87`, `36f597d`, `5e764ec`, `e62f9dc`, `3680bd2`).

The first rebuild passed the verification's scripts and the scanner. A broader check then listed every
cents-precision amount left in val-A states and read the ones that were not EPS or dividends. It found forms
that no rule (masker, scanner or the verification's scripts) had seen:
- price targets after an abbreviation ("JPMorgan Chase & Co. from $104.00 to $96.00", "Citigroup Inc.");
- MarketBeat's "The company traded as high as $155.51";
- "Receives $645.36 Consensus Price Target";
- "a one-year high of $66.44";
- insider prices ("sold 2,500 shares at a price of $251.12");
- "rallies to $202.34 as … ad revenue";
- "current price ($246.03)";
- quote widgets ("GE VernovaGEV $554.00 (-3.11%)");
- "shares saw an increase of 2.4% during after-hours trading";
- options-flow chatter ("lifted the $0.37 offer … 9/12 weekly 20 puts");
- "Sep-25" and "Jun-12-2025".

Pattern lists kept missing phrasings, so the masker now ends with a structural pass. After the price-target
rewrites, it drops a sentence that holds:
- a cents-precision amount (sizes such as "$9.05 Billion" or "$6.16 bln" are not), unless a per-share
  fundamental word (EPS, earnings, per share, dividend, distribution, FFO, consensus, estimate, guidance, …) is
  in the sentence and no price word or move verb stands just before the amount;
- any cents amount in a sentence with a price-target label;
- a quoted price.

Also:
- the price-target window crosses abbreviation periods (Co., Inc., Corp., Ltd., one capital, ".com");
- "of N%" and "added N%" moves, with a guard for "per share, an increase of 16%";
- options-flow sentences;
- month-year and month-day-year dates;
- deal prices with words before "a share" ("$47.50 in cash a share", "cash + CVR per share"), where "pay" is a
  deal word unless a dividend is on either side.

The scanner learned each class in its own wording, with abbreviation-aware sentence breaks.

**Tests:**
- non-English golden cases in 11 languages, and English look-alikes ("Los Angeles", "DuPont de Nemours", DE /
  EL / DAN);
- no built state carries two non-Latin script characters (exact);
- 50 revision-4 removal cases and 23 fundamentals that must stay (EPS, dividends, market sizes, "EPS rose to
  $1.44");
- the scanner sees every removal case and counts none of the fundamentals (levels, moves, quotes);
- val-A price talk under 0.5% per file (`test_val_a_price_talk_below_target`);
- events without text bounded at 0.3%.

**After the rebuild** (val-A unless stated):

| Check | Before (revision 3) | After (revision 4) |
|---|---|---|
| verification's price-talk scripts, D0 / D2 | 2.52% / 3.25% | 0.02% / 0.05% of states hit, all false positives (deal or revenue sizes next to "price target") |
| every cents amount left, read by hand where not EPS / dividend / revenue / market size | — | D0: 2 market-size headlines cut before "Billion", a structured note quoting Dell's price, a deal's "$22.50" CVR (other companies); one offering range ("$141.85 and $143.35") and one "reaching as low as $28.83" (D2) are the remaining share prices: about 0.01% |
| scanner price talk (moves, quotes, levels; its revision-4 rules), D0 / D2 | 5.47% on the revision-3 build | **0.00% / 0.04%** (D2: another company's insider price, "20,200 Shares at $1.02/Share", and four false positives) |
| scanner name / ticker, D0 / D2 | 0.10% / 0.08% | 0.09% / 0.07% |
| scanner year / date | 0.00% | 0.00% |
| verification's date residue, D0 | 0.13% | 0.02% (a lower-case "july 14th"; a one-line Dutch title) |
| D0 states / events without a state | 47,489 / 614 (1.28%) | 47,125 / 978 (2.03%): 871 all excluded (254 all non-English), 107 without text |
| p95 state, Call A D0 / Call B | 809 / 855 | 766 / 840 |
| share of states ≤ 768 tokens (Laya), Call A D0 / Call B | 87% / 53% | 95% / 71% |

The 107 D0 events without text carried only price talk ("Lockheed Martin (NYSE:LMT) Trading 0.8% Higher - Here's
What Happened", "Cencora, Inc. shares rise 2.42% after-hours …", "Expeditors … Receives $115.40 Average T…"). By
split: test 65, val-B 18, train 12, val-A 12. The structural pass drops a few product and commodity prices too
("a $19.99 per month subscription", silver prices); about 0.7% of event articles lose a sentence to it.

## Revision 3 — after the third verification FAIL on AC2, and its look-ahead finding (2026-10-25)

The third verification passed AC1 and AC3–AC7, and failed AC2. It read every val-A state with its own regexes and
labelled the hits by hand:

| Residue (val-A, revision-2 build) | D0 | D2 / Call B | Scanner reported |
|---|---|---|---|
| the company's own name or ticker | 1.29% | 1.00% | 0.10% / 0.07% |
| a date or period label | 3.86% | 3.64% | 0.00% |
| of which written-out ordinal quarters in other languages ("deuxième trimestre", "zweiten Quartal") | 2.14% | 2.04% | 0 |

**Look-ahead.** It also found future price information in pre-open inputs:
- DGX's D0 state for 2025-07-21 read "Quest Diagnostics DGXjumped 6.4% in the morning session after the company
  reported strong second-quarter" results, a move of 07-22 (z +4.84).
- The vendor timestamps of these move explainers ("Why Quest (DGX) Stock Is Up Today") can precede their content.
  Of 204 pre-open-stamped explainers about the company itself (2024-01 … 2025-09), 29 describe a move after their
  stamp.
- The price-move filter missed the sentence because the ticker is glued to the verb.

During the fix, the same DGX state turned out to hold Reuters' earnings summary of 07-22, reposted on TradingView
under the same stamp. 128 of 511 TradingView earnings summaries are stamped before the release they report, against
0–7% for other outlets (previews included).

**Operator decisions (2026-10-25).**
1. Fix the look-ahead and the cheap date forms now, before any API spend: states are cached by their sha256.
2. Exclude TradingView reposts as well.
3. Accept the name residue as a logged deviation (PREREG §15 NA-04 row 7).
4. This revision was implemented by the session that ran the third verification (the operator waived the
   independence of this round). Its re-check is mechanical: the verification's own scripts plus the tests below.

**What changed** (commit `314efd2`):
- **Exclusion** (`configs/states.yaml` `news_exclusion`, `states.build.excluded_ids`; PREREG §15 NA-04 row 6):
  - move explainers (raw title "Why … stock/shares … today", or StockStory's raw snippet "What Happened? Shares of / A
    number of …") and every TradingView domain are in no state, in any window or call (both twins and the samples
    included);
  - the NA-03 lists are not refilled;
  - `build_states.json` counts the excluded articles and the events left without any (`events_all_excluded`)
    apart from `events_without_text`.
- **Price-move filter:** a move verb glued to an upper-case ticker ("DGXjumped 6.4%") is a move. "Slower 6%" and
  "GROUP" are not.
- **Dates (masker, and the scanner with its own patterns):**
  - written-out ordinal quarters and halves (FR, ES, IT, PT, DE, NL); "3T25"; a bare T1–T4 after a period word;
  - Korean 분기 / 반기;
  - two-digit years after any apostrophe ("'25", "FY’25", "Q1 ‘25");
  - a lone "Aug."; bare H1 / 2H (not hydrogen);
  - glued yyyymmdd; day-first dd/mm; "domingo".
- **Tests:**
  - `tests/test_states_exclusion.py` (rule golden cases, `news_items`, built files);
  - revision-3 masker and scanner cases in `tests/test_states_mask.py`;
  - the determinism test keeps `Inputs.excluded`;
  - `test_splits_and_counts` accounts for the emptied events.

**After the rebuild** (val-A unless stated):

| Check | Before | After |
|---|---|---|
| verification's date residue, D0 / D2 | 3.86% / 3.64% | **0.13% / 0.11%** |
| verification's own name / ticker residue, D0 / D2 (accepted) | 1.29% / 1.00% | 1.26% / 0.97%, plus about 30 D0 states in Korean / Japanese |
| scanner name / ticker, D0 / D2 | 0.10% / 0.07% | 0.10% / 0.08% |
| scanner year / date | 0.00% | 0.00% (now also counting the new forms) |
| glued move sentences, every file and split | 16 val-A D0 states | **0** |
| "N% in the morning / afternoon session" in a D0 state, every split | 39 val-A states | **0** |
| DGX `W0:420:2025-07-21` | the 07-22 jump and results | no state (every listed article excluded) |
| events without any article: D0 / D2 / Call B | — | 596 / 503 / 224 |
| events without text after masking | 18 / 11 / 4 | 18 / 10 / 4 |

What is left of the date residue (12 D0 states): "saison T2", "1º semestre", German compounds ("ersten
Quartalszahlen"), "Investopedia22/08", option expiries ("9/12 weekly puts") and a software version
"2025.001.20744".

## Revision 2 — after the second verification FAIL on AC2 (2026-10-25)

The second verification passed every AC except AC2. It measured, on val-A Call A D0 states:

| Leak | Share of states | Scanner reported |
|---|---|---|
| the company's own ticker written in capitals, a ticker that is an English word ("MET earnings per share", "View the latest DASH revenue", "MS.N") | 2.07% | 0 |
| name or ticker, all forms | 2.40% | 0.33% |
| a year glued to letters or CJK ("the quarter CY2025", "2025年第二季度") | 3.0% | 0.00% |
| CJK months / days / weekdays, "recently-18", "the yearQ2", option codes | 0.5–0.7% each | 0 |
| a percent quote after "the company" ("· IP. -0.58%") | 1.75% | not counted |

**Root cause.** The scanner still shared the masker's blind spots: its list of English-word tickers was a copy of
the masker's stoplist, its year pattern refused a year after a letter or a CJK character, and it had no CJK patterns.

**What changed:**
- **Scanner** (`states/scan.py`). It has no English-word ticker list any more:
  - every bare ticker in capitals counts in a text that is not mostly in capitals; a clock time ("4:30 PM") is the
    only exception, and in a text mostly in capitals a ticker counts unless it is an ordinary word of the corpus;
  - its own forms for "（紐交所：DE）", "紐交所:CTRA", "HOOD US", "COIN.US", option codes, "WMT/TGT", "Inc.ANET",
    "ABBV19";
  - years after letters or CJK; Chinese / Japanese / Korean dates; glued period labels ("yearQ2", "quarter-25");
    option expiries; masked day-range remnants;
  - CJK company names by its own rule (`harvest_cjk_names`: every 2–6 character ending of the CJK word before the
    ticker, seen twice); names glued to the previous word or written without spaces;
  - quote widgets, "Price: … Change: …" lines, Chinese transliterated person names;
  - it scans one headline or snippet at a time.
- **Masker** (`states/mask.py`, `configs/aliases.yaml`):
  - **tickers:** a stoplisted ticker in capitals is the company unless the text is mostly in capitals (a sample
    of 40 such uses was 40 ticker uses); kept are a clock time ("4:30 PM", Philip Morris) and IT before an IT noun
    ("IT spending", Gartner); in a text mostly in capitals, a ticker that is not an ordinary word, in a list of
    tickers, before a period label or right after the company's name is masked too. Also CJK and venue forms,
    Reuters exchange letters (AAPL-Q, NKE-N), drug codes (ABBV-400), tickers with digits ("ABBV19"), in pairs and
    lists ("Omnicom-IPG", "WMT/TGT/TJX"), and glued after a masked name ("Inc.ANET"); option codes are removed
    with their expiry and strike;
  - **dates:** years glued to letters or CJK, year + period in any order ("2025Q2", "FY2025Q2", "Q2-25", "Q1
    CY2025"), day ranges ("July 17-18"), slashed dates (2025/08/08), Chinese / Japanese / Korean dates, weekdays,
    quarters and halves; remnants of a masked range lose their number; period rules use ASCII boundaries (CJK
    characters are word characters);
  - **names:** 572 Chinese / Japanese / Korean names of 254 companies harvested from the event texts (the CJK words
    right before the company's own ticker in parentheses; `work/states/company_cjk_names.parquet`); names glued
    to the previous word or a number ("Key TakeawaysHumana", "2025Principal Financial Group"), written without
    spaces ("MolsonCoors"), or cut at the end of a snippet ("for Warner..."); about 15 more curated names
    (Principal Finl Gr, HP Enterprise, NY Mellon, Smith AO, Norwegian, Caribbean, Campbell, PMČR, …); "Fargo"
    alone for Wells Fargo;
  - **people:** Chinese transliterations of Western names ("薩姆·阿爾特曼") → "a person"; "Leyen" added to the
    public figures;
  - **price talk:** quote widgets are removed before the company step (they split names: "Constellation · CEG.
    +3.58%. Energy's"); "Price: 152.75, Change: -15.87" lines (1% of D2 states before the fix) and share-price
    level sentences ("boosts stock to $102.89") go;
  - **config:** `ON` is quoted (YAML read it as true, so ON Semiconductor's curated names were ignored); the
    loader refuses a non-string entry.
- **The verifier's scripts** (`stoptick.py`, `years.py`, `residues.py`, re-run read-only on the final states): own
  tickers in capitals 5 / 9,073 D0 states (0.06%) and 4 / 11,249 D2 states (0.04%), all Gartner's "IT spending";
  years 0; date residues 1 state (a clock time, "8:30 CEST").
- **Rebuilt** with all earlier mutations plus 15 new ones RED (§2.1).

## Revision 1 — after the first verification FAIL on AC2 (2026-10-25)

The first scanner imported the masker's aliases, exchange list, stoplist and English-only date patterns and reported
0%; independent scans of val-A D0 states found the own ticker in 3.4%, its name in ≥ 1.8%, quarter / half labels in
title case in 10.3%, non-English months / weekdays in 7.9%, price-move sentences in 2.2%, dollar price targets in
13.4% and one-word public figures in 10.3%.

**Operator decisions (2026-10-25).**
1. Price-target and deal-price amounts: drop the amount, keep the action.
2. Non-English dates: mask them too.
3. Person names: mask all of them, including surnames used alone.

All three are in PREREG §15 row 4, which amends NA-02's rule that kept price targets. The scanner was made
independent of the masker's code and alias file; the masker gained every exchange code, class suffixes,
possessives, ticker lists, about 90 curated names, quarter labels in any case, seven languages' dates, numeric m/d
dates, corpus surnames and a public-figure list, the price-move sentence filter and the price-target rewrite.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 codebook | done | `configs/codebook_v1.yaml`, `src/newsaction/states/codebook.py`: PREREG §6.11 scales + encoders E0–E4; NA-04 additions marked in the YAML (PREREG §15 row 2) |
| S2 context | done | `states/context.py` (company, market, attention, reaction blocks), `states/macro.py` + `configs/macro_calendar.yaml` (CPI from vintages; FOMC from federalreserve.gov, URL cited); `configs/states.yaml`; 45 columns registered in `configs/availability.yaml`; `work/states/{context_company, context_market, reaction_d2}.parquet` |
| S3 masking | done | `states/mask.py`, `states/scan.py` (independent), `configs/aliases.yaml`; spaCy `en_core_web_sm` 3.8.0 pinned; `work/states/{articles_masked, person_surnames, company_cjk_names}.parquet` |
| S4 questions | done | `configs/questions_v1.yaml` (groups core / extended / explain), `states/questions.py` (loader for any group combination, `noul` refused, request shape); sha256 in `configs/frozen.yaml` |
| S5 build | done | `states/build.py` (specs, availability checks, canonical JSON, budget, samples, CLI); `work/states/{callA_d0_E3, callA_d2_E3, callB_d2_E3, market_E3}.parquet`, `work/states/samples/{callA_d0_E0…E4, unmasked}.parquet` |
| S6 token budget | done | `artifacts/NA-04/token_stats.csv`; tightening documented (§3.4) |
| S7 leak scan | done | `artifacts/NA-04/leak_scan.csv` (every val-A state of the three masked E3 files + the unmasked twin); `artifacts/NA-04/examples.md` (3 Call A, 2 Call B, val-A, seed 2026) |
| report stage | done | `states/report.py` (`--stage report`) |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 determinism | **Test.** `tests/test_states_determinism.py` takes 2,000 rows from seven state files (400 each of the three main files; 200 each of E0, E4, unmasked and market). It rebuilds them from the registered inputs: context recomputed for the sampled keys (and compared with the stored rows: equal), every article re-masked by a fresh in-process masker with the stored corpus surname list (the CJK names are derived again from the event texts), states re-rendered. **2,000 / 2,000 sha256 identical** (the test keeps the excluded articles, revision 3, and the non-English ones, revision 4). **Rerun.** Revision 4: the states were built from `36f597d` (report from `5e764ec`); a full rerun of `mask`, `states` and `report` from `3680bd2` reproduced all 13 `work/states` files of the stages and the 5 report artifacts byte for byte (22 of 22 outputs incl. the context files and `configs/frozen.yaml`) (§9) | PASS |
| AC2 masking | **Independent scanner** (`leak_scan.csv`, val-A, states with ≥ 1 hit). Name/ticker: callA_d0 **8 / 8,923 (0.09%)**, callA_d2 **8 / 11,148 (0.07%)**, callB_d2 8 / 11,148. Year/date: **0** in all three, with the revision-3 forms counted. Target < 0.5% (`test_val_a_leak_rates_below_target`). **Price talk** (revision 4; moves, quotes or levels, the scanner's new rules): 0 D0, 5 D2 / Call B states (0.04%), target < 0.5% (`test_val_a_price_talk_below_target`); the fourth verification's scripts find no real hit, and a full listing of the cents amounts left finds about 0.01% (Revision 4). **Positive control.** Unmasked twin: 89.1% name / ticker, 92.0% year / date, 24.9% price talk. **Hand-labelled (third verification, revision-3 build).** Own name / ticker 1.26% D0 / 0.97% D2, plus about 30 D0 states in Korean / Japanese: above the target, **accepted by the operator** (PREREG §15 NA-04 row 7); date residue 0.13% / 0.11%. **Independence.** No import from the masker (`test_scanner_is_independent_of_the_masker`); every stoplisted ATOM ticker counts in capitals (`test_scanner_counts_every_stoplisted_ticker`); mutations "scanner imports the masker", "scanner skips English-word tickers", "scanner refuses years after letters / CJK", "scanner revision-3 date forms removed": RED. **Cross-check.** The second verification's scripts: own ticker 5 / 4 states (Gartner "IT spending"), years 0 (Revision 2). **Mutation** "empty the alias list": RED | PASS on the scanner; names: accepted deviation (row 7) |
| AC3 availability | **Tests.** `tests/test_states_pit.py`, 84 cases: z_id, z_cc, z_on, y0, e5, r_cc, adj_close (`post`), every `w2` / `d2_reaction` column, vendor `selection_only` columns, `material` and `clean_5`, each added to any block of a D0 Call A spec, raise `PITError`. Call B's `reaction_so_far` accepts `d2_reaction` columns only (z_cc, y2, e5, ar_cc, g_d1, raw_close refused). Reaction columns are refused in every other block, and Call A has no reaction block. **Planted shocks.** A +50% SPY day or stock close at t changes no market or company context dated ≤ t, and does change t+1. **Mutation** z_cc registered `t_minus_1`: **RED** | PASS |
| AC4 encodings | **Tests.** `tests/test_states_codebook.py`: every bin edge of move, percentile, β, attention and revision (value − ε, the edge, + ε); the PREREG examples of E0–E4 reproduced exactly; E2 words carry no digit, E3 only inside "≈k.k×", for every horizon. **Built files.** `tests/test_states_outputs.py`: no digit in the company / market / attention blocks of any E2 sample state; E3 (sample, Call B incl. `reaction_so_far`, market) has digits only inside "≈k.k×". The three fixed PREREG tier phrases ("one of the 100 largest US companies", "… rank 101–250", "… 251–500") are removed first: they are labels, not values. **Mutation** move edge 2.0 → 2.5: **RED** | PASS (tier phrases: note) |
| AC5 tokens | `token_stats.csv`. **Call A E3:** p95 state **766** (≤ 900), p95 state + longest core question + 3 special tokens **901**, max 1,021. **Call A D2:** 761 / 896 / 930. **Call B:** 840 / **989** / 1,023 (revision 4). **Before the tightening:** Call B was 913 / 1,062 (fail); §3.4. Stored counts re-tokenize exactly on 200 states per file (`tests/test_states_tokens.py`) | PASS (after documented tightening) |
| AC6 no 2026 Call B | No state file has a Call B row with split test or session ≥ 2026-01-02. `reaction_d2.parquet` has no test session. `build_event_states` refuses Call B events outside train / val-A / val-B (test + mutation RED). `ledgers/test_access.jsonl` has 2 lines, both NA-01 (`test_access_ledger_has_no_na04_entry`) | PASS |
| AC7 questions frozen | `tests/test_states_questions_prereg.py` parses the PREREG §7 / A2.2–A2.3 table rows and compares: ids, types and level counts; option keys; every quoted description; the 8 verbatim instructions; Q1's levels; the Q3 / Q4 / Q14 end points; Q17 = Q8's nine company categories + 2. Groups: core A = Q1–Q4, core B = Q1, Q5, Q6, extended = Q7–Q15, explain = Q16–Q17. `questions_v1_sha256` = `e602c6c0…0c85a` = file sha. No `noul`, and the loader refuses one. **Mutations** (one word of Q3; `noul` check removed): **RED** | PASS |
| GAC1 | `make verify` exit 0: 947 passed, 1 xfailed; manifest and ledgers OK (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal in `src/`; dates come from configs); access ledger unchanged | PASS |
| GAC4 | No API call; `ledgers/spend.jsonl` empty; $0 | PASS |
| GAC5 | 16 `work/states/` artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte-for-byte (asserted).
`git status` afterwards showed only the author's changes. All 100 turn the tests RED: 41 through revision 2, 22 in
revision 3 and 37 in revision 4. In revision 4, four first survived and needed a test, because another rule
caught every golden case or the test did not look at the counted column:
- the verb-level price rule (a case with a fundamental word in the stretch, `c03a704`);
- the options-flow rule (a case with no cents amount, `3680bd2`);
- the scanner's quote guard (the kept-text check now includes quotes, `3680bd2`);
- the scanner's abbreviation-aware sentence breaks (an "EPS …, vs. FactSet Est of …" line, `3680bd2`).

The verifier's (a)–(c) were re-run on the final code: RED.

| Mutation | File |
|---|---|
| alias list emptied (verifier 6a) | configs/aliases.yaml |
| z_cc registered `t_minus_1` (verifier 6b) | configs/availability.yaml |
| move edge 2.0 → 2.5 (verifier 6c) | configs/codebook_v1.yaml |
| `check_inputs` removed from `validate_spec`; reaction "d2_reaction only" rule removed; Call B test-period refusal removed; third-party check removed | states/build.py |
| E3 multiple rounded instead of truncated | states/codebook.py |
| trailing history includes the scored value; market context not shifted; earnings stamp at the close kept in W2(s) | states/context.py |
| loader accepts `noul`; one word of Q3 edited | states/questions.py, configs/questions_v1.yaml |
| **revision 1:** bare-year rule removed; person masking disabled; public-figure list emptied; any-exchange-code rule removed (BOATS:NEE); ticker quotes kept; quarter labels case-sensitive; non-English weekday rule removed; zero-padded m/d rule removed; price-move sentence filter disabled; price-target amounts kept; scanner imports the masker | states/mask.py, states/scan.py, configs/aliases.yaml |
| **revision 2:** upper-case stoplisted ticker rule removed; stoplisted tickers in a text in capitals kept even when not a word; full-width / venue ticker forms removed; option codes kept; years glued to letters / CJK kept; CJK weekday rule removed; CJK company names not masked; CJK person names kept; YAML boolean guard removed; glued names kept; truncated names kept; quote widgets removed only after the company step; share-price level sentences kept; bare tickers only after a non-word character; names need a space between words; scanner skips English-word tickers; scanner refuses years after letters / CJK | states/mask.py, states/scan.py |
| **revision 4, second pass:** cents-level pass off; options-flow sentences kept; per-share fundamental before the amount not exempt; price word before the amount ignored; price-target label not a level; quoted price not a level; abbreviation periods end the price-target window; "of N%" / "added N%" moves off; "per share" guard off; Mon-DD-YYYY dates off; Mon-YY dates off; "pay" not a deal word; scanner cents levels and options off; scanner price word before the amount ignored; scanner "of N%" moves off; scanner verb-level levels off; scanner sentence breaks after abbreviations; scanner share-amount levels off | states/mask.py, states/scan.py |
| **revision 4:** non-English rule dropped from `excluded_ids`; script rule off; foreign-word rule off; diacritic rule off; words in capitals count (DE = "de"); place names not removed; explainer title rule back to revision 3; broad share-level rule off; verb-level price-level alternatives removed; direction after the number off; moves as nouns off; price targets in other notations off; their relative change off; "/share" deal prices off; possessive amounts reverted; broad-rule cues emptied; scanner new price levels off; scanner new price moves off; scanner fundamental after the number ignored; scanner fundamental acronyms counted as quotes | configs/states.yaml, states/build.py, states/mask.py, states/scan.py |
| **revision 3:** exclusion skip removed from `news_items`; TradingView domain pattern never matches; explainer patterns never match; `market_selection` keeps excluded articles (determinism test RED); determinism test rebuilds `Inputs` by hand and drops `excluded` (RED); glued-verb alternative removed; each new date rule removed, one at a time (ordinal quarters, ordinal halves, "3T25", bare T after a period word, Korean quarters, Korean halves, glued d/m/y, day-first dd/mm, glued yyyymmdd, bare half-year, apostrophe year, curly apostrophes, lone month abbreviation, "recent’25" remnant, "domingo"); scanner revision-3 date forms removed | configs/states.yaml, states/build.py, states/mask.py, states/scan.py, tests/test_states_determinism.py |

The revision-1 mutation "ODFL back in the stoplist" no longer applies: a stoplisted ticker that is not an ordinary
word is masked in capitals anyway, which the revision-2 mutation on the vocabulary check covers.

## 3. Numbers

### 3.1 States

| File | robustness | train | val-A | val-B | test | total | mean articles |
|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 650 | 17,490 | 8,923 | 6,048 | 14,014 | 47,125 | 3.46 |
| callA_d2_E3 | 920 | 22,862 | 11,148 | 7,842 | 18,633 | 61,405 | 3.78 |
| callB_d2_E3 | — | 22,862 | 11,148 | 7,842 | — | 41,852 | 3.95 |
| market_E3 (A3.5) | 119 | 203 | 64 | 64 | 145 | 595 | 5.13 |

- **Samples.**
  - NA-07: 1,500 val-A + 1,500 val-B D0 events in each of E0–E4, the same events in every encoding. The E3 sample
    states are byte-identical to the main E3 states.
  - NA-06: an unmasked twin of 1,000 val-A D0 events (Call A E3). The masked twin is the same `event_id` in
    `callA_d0_E3`.
- **D0 vs D2 Call A.** 10,937 of the 47,125 D0 events have a byte-identical D2 Call A state (NA-03 counted 18,656
  identical W0/W2 lists). The rest differ in the W2 attention words, the W2 earnings flag, or the D2 budget cut.
- **Events with every listed article excluded** (revisions 3 and 4; `build_states.json` `events_all_excluded`).
  These are move explainers, TradingView reposts or non-English articles, so the event gets no state:
  - 871 D0 events (test 348, train 257, val-A 144, val-B 83, robustness 39; 254 of them only non-English), 814 D2
    and 480 Call B (revision 3: 596 / 503 / 224);
  - 22,648 D0 and 30,585 D2 listed articles are left out, of which 14,897 and 19,642 are non-English;
  - of the 296,082 event articles, 34,735 (11.7%) are excluded: 22,960 non-English (7.75%) and 11,775 explainers or
    TradingView reposts (corpus: 8,760 explainers, 38,135 TradingView articles);
  - PREREG §15 NA-04 rows 6 and 8.
- **Events without text** (`build_states.json`). 107 D0, 66 D2 and 31 Call B events have no state, because every
  listed article lost its text to the price-path scrub, the price-move filter or the revision-4 price rules
  ("Lockheed Martin (NYSE:LMT) Trading 0.8% Higher - Here's What Happened", "Shares of eBay declined on Thursday
  after…"). D0: test 65, val-B 18, train 12, val-A 12 (revision 3: 18 / 10 / 4). PREREG §15 row 5 (e).

### 3.2 Masking

- **Replacements** in the 296,082 event articles (title + snippet):
  - 353,348 company names;
  - 168,938 ticker forms;
  - 266,174 date / year / fiscal-period phrases (incl. datelines, ISINs and option codes; 263,311 before revision 3,
    266,161 before revision 4's month-year forms);
  - 94,232 person names.
- **Shares.** 63.3% of articles had a name masked and 19.9% a person. 2,852 articles have no text left (807 before
  revision 4's price rules). The 3,055 market articles (TradingView reposts, explainers and non-English articles left
  out) had 1,990 dates and 1,177 people masked.
- **Lexicons.** 1,777 corpus surnames (last words of multi-word PERSON names seen ≥ 3 times in English texts,
  capitalized ASCII, not an ordinary or company-alias word, not tagged inside an organization or place at least half
  as often) plus 49 listed public figures; 572 CJK names of 254 companies.
- **Not masked by design** (PRD risks; NA-06 measures them): products and subsidiaries (Zepbound, Firefly, Apple Watch
  → "the company Watch"), other companies' names, fundamental figures, "IT" before an IT noun in Gartner's texts, a
  CJK name never written before the company's ticker.
- **Non-English.** 7.75% of event articles are non-English by the revision-4 rule (NA-02's hint: 5.0%), 1% CJK. They
  are still masked (dates, harvested CJK names), but since revision 4 they are in no state (PREREG §15 NA-04 row 8):
  the masker's price rules and NA-02's scrubber are English-only.

### 3.3 Leak scan (val-A; `leak_scan.csv`, independent scanner)

| File | States | Name/ticker | Year/date | Price moves | Quotes | Price levels | Public figures |
|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 8,923 | 0.09% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| callA_d2_E3 | 11,148 | 0.07% | 0.00% | 0.02% | 0.00% | 0.03% | 0.00% |
| callB_d2_E3 | 11,148 | 0.07% | 0.00% | 0.02% | 0.00% | 0.03% | 0.00% |
| unmasked twin (control) | 1,000 | 89.1% | 92.0% | 2.4% | 3.1% | 21.2% | 13.7% |

Since revision 4 the price columns use the scanner's broader rules (amounts after a share word, targets in any
notation, the direction after the number, noun forms); the revision-3 build scored 5.47% of D0 states on them. The
5 D2 states: another company's insider price ("20,200 Shares at $1.02/Share"), and four false positives (an
offering's 2.0% agent fee, Mexico's index "closed more than 1% higher", a preferred redemption "at $1,000 per…", a
$100,000 visa fee).

Revision 2 read its 9 D0 name/ticker states one by one:
- 5 were Gartner's "IT spending" / "IT services", kept on purpose; the scanner counts them conservatively.
- 4 were other entities: Citizens Holding Company, Morgan Stanley in Kinder Morgan's texts, Carnegie Mellon
  University, "visits to Vegas".

The revision-3 and revision-4 hits (9 / 8 D0, 9 / 8 D2) were not re-read one by one. **The scanner undercounts names.** The third
verification's hand count is 1.26% D0 / 0.97% D2 own names or tickers, plus about 30 D0 states in Korean /
Japanese. The forms it cannot see are one-word names that are ordinary words, glued or inflected names, slug
tickers, preferred / venue tickers and CJK transliterations. This residue is accepted (PREREG §15 NA-04 row 7).

### 3.4 Tokens and the tightening (S6, AC5)

- **Question tokens** (canonical JSON):

  | | Core battery | Longest single core question | Core + extended / explain |
  |---|---|---|---|
  | Call A | 302 | 132 (Q1) | 976 |
  | Call B | 355 | 146 (Q5) | 663 |

- **Before the tightening:**
  - Call A E3: p95 state 824 and p95 state + longest + 3 = 959 (pass).
  - Call B: p95 state 913 and p95 with the question 1,062; 12% of Call B states over 1,024 (fail).
- **Tightening** (`build.fit_news`; PREREG §15 row 5 (d)).
  - The lowest-ranked articles of a state are dropped (at least one stays) until state + longest core question
    + 3 ≤ 1,024. The caps are 889 state tokens at D0 and 875 at D2.
  - The D2 count reserves the longest possible E3 `reaction_so_far`. So Call A on D2 and Call B keep the same
    articles (tested), and the cut never depends on the observed reaction.
  - The samples and the unmasked twin reuse the D0 cut.
  - No text was cut.
  - Articles dropped by the budget or masking (excluded articles not counted): 1,434 from 1,393 D0 states (3.0%);
    3,492 from 3,385 D2 Call A states (5.5%); 2,654 from 2,563 Call B states (6.1%). Revision 3: 762 / 5,689 / 5,451;
    the revision-4 exclusions shortened the states, so fewer articles hit the cap, while more lost their text.
- **After** (`token_stats.csv`):

  | File | p50 state | p95 state | max | p95 + longest question | max + longest | share ≤ 768 |
  |---|---|---|---|---|---|---|
  | callA_d0_E3 | 558 | 766 | 886 | 901 | 1,021 | 95% |
  | callA_d2_E3 | 599 | 761 | 795 | 896 | 930 | 97% |
  | callB_d2_E3 | 694 | 840 | 874 | 989 | 1,023 | 71% |
  | samples E0 / E1 / E2 / E3 / E4 | 512 / 486 / 471 / 589 / 566 | 699 / 673 / 657 / 775 / 753 | ≤ 873 | ≤ 910 | ≤ 1,008 | 94–100% |
  | unmasked twin | 654 | 836 | 923 | 971 | 1,058 | 78% |

  Revision 4 (non-English articles out) shortened the states: Call A D0 p95 809 → 766, Call B 855 → 840. The unmasked
  twin is an API probe (NA-06) with the masked twin's articles; 0.5% of it exceeds 1,024 with a question (3.3% before).
- **Laya.** The model card's `head_max_len = 256` leaves about 768 tokens for the state. 29% of Call B states and 5% of
  Call A D0 states are longer (47% / 13% before revision 4; owner decision 2, NA-08's decision C).
- **Cost.** Mean request tokens (state + core questions, val + test) exceed NA-03's assumption (news + 250 + 350):

  | Call | Actual | NA-03 assumed | Difference |
  |---|---|---|---|
  | Call A D0 | 866 | 803 | +8% |
  | Call A D2 | 892 | 826 | +8% |
  | Call B | 1,046 | 857 | +22% |

  The NA-11 full plan is dearer than NA-03 projected. Scaling the revision-3 estimate (requests 2–3% shorter, states
  0.7% fewer): roughly $9.5 at $0.042/M (fits $18) and $20.5–21.5 at $0.10/M (owner decision 3).

### 3.5 Context checks

- **Missing values** ("not available"), share of event keys:
  - σ / momentum percentiles: 1.5–4.5% (short history after index entry);
  - FY1 revision: 3–5%;
  - E0 raw returns: 0.1–3% outside test (test E0 states are never built);
  - HY OAS z: 18.5% of robustness sessions (FRED history starts 2023-08).
- **Macro.** 30 CPI release dates 2024-01 … 2026-07 match the BLS schedule, including the shutdown-delayed 2025-10-24
  and 2025-12-18 releases. 24 FOMC statement dates.
- **Earnings.** A scheduled report falls in W0 for 4.3% of val-A event keys.

## 4. Questions (S4)

- **Shape.** Call A asks core {justified_move (score, 9), materiality (choice, 2 neutral keys), surprise (score, 5),
  tone (score, 5)}; Call B asks {justified_move, reaction_adequacy (choice, 6), continuation (choice, 3)}. The extended
  group is Q7–Q15 (Call A), the explain group Q16–Q17 (Call B). All PREREG-verbatim strings are used as written.
- **Text written by NA-04** (PREREG §15 row 5 (c)):
  - instructions of Q2, Q5, Q6, Q9–Q13, Q15, each referencing `news` and/or `reaction_so_far` in backticks;
  - the middle levels of Q3 / Q4 / Q14;
  - option descriptions where PREREG gives keys only;
  - Q1's rise ranges, mirrored from the falls.
- **Empirical-finding self-check** (`test_authored_text_references_state_fields_and_states_no_finding`).
  - Every instruction and option is scanned for tends / usually / typically / historically / on average / often /
    more or less likely / research / studies / evidence / underreact / overreact / drift / momentum / revert:
    **no match**.
  - Backticked fields must be `news` or `reaction_so_far`.
  - Read by hand as well: no option states what a kind of news usually does. Q5's options are relative to "what the
    news justifies"; Q6's are directional only.

## 5. Spend, network

- **Spend.** OpenRouter $0.00 this chunk and cumulative (`ledgers/spend.jsonl` empty). FMP requests: 0. Kaggle: none.
- **Network:**
  - one download of the spaCy `en_core_web_sm` 3.8.0 wheel from GitHub, pinned in `pyproject.toml` / `uv.lock`;
  - three page reads: the OpenRouter Jev guide, the Laya model card and the Fed FOMC calendar.
- No article text or derived data left the machine.

## 6. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| panel `sector`, `tier` (events), `beta_m`, `sigma_cc`, `z_m{5,20,60}`, `logv_mad60` (panel_public ∪ panel_test_inputs) | company block; volume multiple | `static` / `t_minus_1` (NA-01, through close(t−1)) |
| `ctx_sigma_cc_pct`, `ctx_z_m{k}_pct` | volatility regime; E4 | `t_minus_1`: the value at t (already through t−1) vs the symbol's 252 previous values; shock tests |
| panel `adj_close` (public) | `ctx_ret_m{k}` (E0 samples, val only) | shifted one session: AdjClose(t−1) / AdjClose(t−1−k) |
| estimates_fy1 | FY1 revision | snapshots dated before the session (and 30 days earlier); a snapshot dated on the session is not used (test) |
| earnings_dates | earnings flag | [close(prev s), 09:15 ET] (`w0`) / [close(prev s), close s) (`w2`); retrospective calendar, read as a pre-announced schedule |
| market_prices (SPY, VIX, DXY, oil), DGS10 | market block | last observation dated ≤ prev(s); σ / percentiles from the 252 changes before it |
| BAMLH0A0HYM2 | HY spread change | the change of t−2 (publication lag) |
| cpi_vintages, macro_calendar.yaml | scheduled releases today | `static` (published schedules) |
| window_counts via events (`attention_ratio_*`, `n_stories_*`) | attention block | `w0` / `w2` counts; 60-session mean `t_minus_1` (NA-03) |
| events news lists (title_clean / snippet_clean, t_avail, source_class_domain) | news block | `w0` / `w2` (NA-03 / NA-02); vendor `source_class` not used (only the domain class) |
| corpus surnames, CJK company names, ordinary-word vocabularies | masking, scanning | lexicons of the article texts (no return); the same for every split |
| articles_clean `third_party_ok` | governance check | `selection_only`; read only to refuse non-OK articles |
| `build_reactions(public)`: g_d2, react_r_cc, react_r_spy_cc, react_z_vol; z_cc history; SPY history | Call B `reaction_so_far` | `d2_reaction` (the reaction of s); E4 / σ histories through t−1; never in Call A (call rule + tests) |

## 7. Deviations from PREREG

Eight rows were appended to the §15 Deviations log (2026-10-25 and 2026-10-26, NA-04), all before the freeze. As in earlier chunks,
they are **in the working tree, not committed**, for the operator to commit on main.

1. **§6.10 industry.** Sector only; ATOM has GICS level 1 only.
2. **§6.10–§6.11 codebook additions:**
   - multi-day and market-series moves;
   - revision, count, volume, timing, time-label and source-type words;
   - "not available";
   - only moves vary with the encoding.
3. **§6.10 availability.** Publication lags (HY OAS at t−2), the CPI and FOMC calendars, the earnings windows.
4. **§6.3 / §6.4 masking**, revised after both verifications:
   - "the quarter" instead of "the latest quarter";
   - non-English dates, including Chinese, Japanese and Korean;
   - person names, including surnames used alone and Chinese transliterations;
   - price-target and deal-price amounts removed, which amends NA-02's rule;
   - price-move and share-price-level sentences and quote lines dropped;
   - every ticker form, including stoplisted tickers in capitals;
   - CJK company names harvested from the corpus.

   The operator decided the three marked policies.
5. **§6.4 / §6.10 / §7:**
   - (a) no pre-market talk in Call B;
   - (b) D2 Call A attention from W2;
   - (c) the question text written by NA-04;
   - (d) the token budget;
   - (e) no state for events without text.
6. **§2 / §6.4 / §6.9 / A3.1 / A3.5 excluded articles** (revision 3): move explainers and TradingView reposts are in
   no state. The NA-03 lists are not refilled. 596 D0 / 503 D2 / 224 Call B events are left without any article.
   Operator decision 2026-10-25.
7. **§6.3 residual target / AC2** (revision 3): the hand-labelled name / ticker residue (1.26% D0, 0.97% D2) is
   above 0.5% and accepted, and the revision-3 date forms are listed. Operator decision 2026-10-25.
8. **§6.3 / §6.4 / §6.9 / A3.1 / A3.5 price talk and non-English articles** (revision 4): non-English articles are
   in no state (operator decision B); the explainer title rule takes any move word; the masker drops the remaining
   English share-price levels, moves and price targets (two passes; a structural cents-amount rule last). 871 D0 /
   814 D2 / 480 Call B events are left without any article, 107 / 66 / 31 without text. Operator decision
   2026-10-26.

PRD-level choices that need no PREREG change are in `docs/decisions/NA-04.md`.

## 8. STOP conditions and owner decisions

No STOP condition fired: no API call, no budget, no 2026 outcome, no new third party. The three masking policies the
first verification raised were decided by the operator on 2026-10-25 (Revision 1); the second verification raised
no new policy question. The third raised three, which the operator decided on 2026-10-25 (Revision 3): exclude the
explainers, exclude TradingView, accept the name residue. The fourth found price talk outside AC2's metrics; the
operator decided on 2026-10-26 to fix it before any API spend and to apply decision B (drop non-English articles)
at the states step (Revision 4).

Owner decisions:

1. **Confirm the eight NA-04 rows in PREREG §15.** Especially:
   - row 4: masking, including the change to NA-02's price-target rule;
   - row 5 (d): the token budget drops the last articles of 5.5% of D2 lists;
   - rows 6–7 (revision 3) and row 8 (revision 4).
2. **Laya's state budget.** Every state fits PREREG §9.1's max length 1,024 together with its longest question. If
   NA-08 keeps the released checkpoint's `head_max_len = 256` (≈ 768 for the state), 29% of Call B and 5% of Call A
   D0 states would be cut at the end of the news list (47% / 13% before revision 4). NA-08 should either set the head length to the question's
   actual length (≤ 146 tokens) or ask for a tighter state budget, which is one constant in `configs/states.yaml`.
3. **Cost projection.** Requests are 8–22% larger than NA-03 assumed (§3.4). At $0.10/M the full NA-11 plan is about
   $20.5–21.5 against the $18 cap. NA-05's pilot should re-project with the real states.
4. **Non-English articles** (NA-02 decision 4): decided (operator decision B, 2026-10-25) and applied here in
   revision 4, at the states step and not at NA-02's `keep` (which feeds the frozen F5 filter).
5. **`parsing_allowed == None`** (NA-02 decision 1): the operator allowed these articles (decision A, 2026-10-25).
   Applying it needs the NA-02 → NA-03 → NA-04 rebuild path, which NA-04 has not run. States use only the current
   third-party-OK articles; the rebuild should re-run the leak checks on the added 2024 states.
6. **Identifiability.** Product names, distinctive facts and the accepted name residue remain (row 7). NA-06's
   company-identification probe will measure it on the masked / unmasked twins.
7. **NA-02 timestamps (revision 3).** Revision 3 found vendor timestamps that precede their content. They occur for
   TradingView reposts and pre-open-stamped move explainers, both now left out of the states. NA-02's `t_avail`
   and the NA-03 lists still contain them, so a later chunk that reads articles directly (for example the NA-10
   bars or NA-12 analyses of news timing) should apply the same `news_exclusion` rule.
8. **Language detection downstream (revision 4).** NA-02's `non_english_hint` misses about a third of non-English
   texts. A later chunk that needs English-only text should use `states.build.non_english` (configured in
   `configs/states.yaml`), not the hint.

## 9. Files

- **Added — code.** `src/newsaction/states/{__init__, codebook, context, macro, mask, scan, questions, build, report}.py`.
- **Added — configs.** `configs/{codebook_v1, questions_v1, aliases, macro_calendar, states}.yaml`.
- **Added — docs and artifacts.** `docs/decisions/NA-04.md`; `artifacts/NA-04/{REPORT.md, token_stats.csv,
  leak_scan.csv, examples.md, summary.json, build_states.json}`.
- **Changed.**
  - `configs/availability.yaml`: 45 NA-04 columns.
  - `configs/frozen.yaml`: `questions_v1_sha256`, `codebook_v1_sha256`.
  - `docs/DATA_CONTRACT.md`: the NA-04 section, 16 artifacts.
  - `pyproject.toml` / `uv.lock`: `en-core-web-sm` 3.8.0 in the `embed` extra.
- **Changed, uncommitted.** `docs/PREREG.md` (§15 rows).
- **Tests.** 8 files: `test_states_codebook`, `test_states_pit`, `test_states_mask`, `test_states_questions_prereg`,
  `test_states_outputs`, `test_states_tokens`, `test_states_determinism`, `test_states_exclusion` (revision 3): 373
  tests (17 / 130 / 187 / 13 / 19 / 7 / 1 / 26; 300 before revision 4).
- **Derived (gitignored).** `work/states/*` (16 files); `work/MANIFEST.json`.
- **Peak RSS per stage (GB).** context 0.7, mask 1.8–2.3 (spaCy, 4 workers), states 3.2–4.3 (5.7–5.8 since revision
  4: the language rule reads every listed article's raw text), report 1.5.
- **Reproducibility.**
  - Revision 2: the final code was built (`mask`, `states`, `report`), then `mask` and `states` were run again,
    each in a new process. All 16 `work/states/` sha256s were identical (16 of 16). Mask stage 783 / 818 s, states
    328 / 341 s.
  - Revision 3: the uncommitted fix was built (mask 660 s, states 328 s, report 54 s), then the three stages were
    run again from the fix commit `314efd2` (mask 872 s, states 327 s, report 54 s). All 13 rebuilt `work/states`
    files and the 5 report artifacts came out byte for byte identical (18 of 18). The manifest records `314efd2`.
  - Revision 4: uncommitted builds while the rules were tuned on val-A, then builds from each fix commit
    (mask 550–595 s, states 219–226 s, report 36–42 s). The final states come from `36f597d`, the report from
    `5e764ec`. A full rerun from `3680bd2` (mask 595 s, states 225 s, report 42 s) reproduced all 22 outputs byte
    for byte (13 rebuilt `work/states` files, 5 report artifacts, the 3 context files, `configs/frozen.yaml`). The
    manifest records `3680bd2`.
- **`make verify`** (revision 4, final: exit 0, 135 s, peak RSS 10.8 GB; pytest **947 passed, 1 xfailed**; manifest
  56 artifacts OK; ledgers OK). Revision 3, for reference (exit 0, 208 s, peak RSS 10.8 GB):
  - ruff check "All checks passed!"; ruff format "110 files already formatted"; mypy --strict "no issues found
    in 54 source files";
  - pytest **847 passed, 1 xfailed** (798 + 1 after revision 2);
  - manifest 56 artifacts OK; ledgers OK (fmp 0, spend 0, test_access 2, trials 94).
