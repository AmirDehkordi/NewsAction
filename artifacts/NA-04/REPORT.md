# NA-04 REPORT — states: context, codebook, masking, question battery v1

Date: 2026-10-25 · Branch `feat/NA-04-states` (cut from `main` @ `45b3da0`) · Decisions: `docs/decisions/NA-04.md` ·
Artifacts: `artifacts/NA-04/{token_stats.csv, leak_scan.csv, examples.md, summary.json, build_states.json}`.

**Result.** Every decision-model input of the paper now exists as canonical JSON:
- Call A on D0: 48,085 states, all splits including test (inputs only).
- Call A on D2: 62,274 states (PREREG A3.1).
- Call B on D2: 42,359 states, train / val-A / val-B only.
- 595 optional A3.5 market states.
- The NA-07 encoding samples (3,000 events × E0–E4) and a 1,000-event unmasked twin for NA-06.

Main results:
- **Masking.** On val-A, the independent scanner finds company-name or ticker hits in 9 of 9,073 D0 states (0.10%)
  and 8 of 11,249 D2 states (0.07%), and no year or date (target < 0.5% each). Five / four of those hits are "IT
  spending" in Gartner's texts, kept on purpose (§3.3); the rest are other entities. On the unmasked twin the same
  scanner has hits in 90.5% / 94.1% of states. The verifier's own scripts of the second verification find the
  company's own ticker only as that "IT", and no year.
- **Availability.** Every block is checked with `pit.check_inputs` at its decision point. A call rule adds that only
  Call B's `reaction_so_far` may read the D2 reaction, and only `d2_reaction` columns.
- **Tokens.** p95(state, Call A, E3) = 814 ≤ 900. With the documented tightening (§3.4), every Call A and Call B state
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
| AC1 determinism | **Test.** `tests/test_states_determinism.py` takes 2,000 rows from seven state files (400 each of the three main files; 200 each of E0, E4, unmasked and market). It rebuilds them from the registered inputs: context recomputed for the sampled keys (and compared with the stored rows: equal), every article re-masked by a fresh in-process masker with the stored corpus surname list (the CJK names are derived again from the event texts), states re-rendered. **2,000 / 2,000 sha256 identical.** **Rerun.** A full rerun of `mask` and `states` on the final code: §9 | PASS |
| AC2 masking | **Independent scanner** (`leak_scan.csv`, val-A, states with ≥ 1 hit). Name/ticker: callA_d0 **9 / 9,073 (0.10%)**, callA_d2 **8 / 11,249 (0.07%)**, callB_d2 8 / 11,249. Year/date: **0** in all three. Target < 0.5% (`test_val_a_leak_rates_below_target`). **Positive control.** Unmasked twin: 90.5% / 94.1%. **Independence.** No import from the masker (`test_scanner_is_independent_of_the_masker`); every stoplisted ATOM ticker counts in capitals (`test_scanner_counts_every_stoplisted_ticker`); mutations "scanner imports the masker", "scanner skips English-word tickers", "scanner refuses years after letters / CJK": RED. **Cross-check.** The second verification's scripts: own ticker 5 / 4 states (Gartner "IT spending"), years 0 (Revision 2). **Mutation** "empty the alias list": RED | PASS |
| AC3 availability | **Tests.** `tests/test_states_pit.py`, 84 cases: z_id, z_cc, z_on, y0, e5, r_cc, adj_close (`post`), every `w2` / `d2_reaction` column, vendor `selection_only` columns, `material` and `clean_5`, each added to any block of a D0 Call A spec, raise `PITError`. Call B's `reaction_so_far` accepts `d2_reaction` columns only (z_cc, y2, e5, ar_cc, g_d1, raw_close refused). Reaction columns are refused in every other block, and Call A has no reaction block. **Planted shocks.** A +50% SPY day or stock close at t changes no market or company context dated ≤ t, and does change t+1. **Mutation** z_cc registered `t_minus_1`: **RED** | PASS |
| AC4 encodings | **Tests.** `tests/test_states_codebook.py`: every bin edge of move, percentile, β, attention and revision (value − ε, the edge, + ε); the PREREG examples of E0–E4 reproduced exactly; E2 words carry no digit, E3 only inside "≈k.k×", for every horizon. **Built files.** `tests/test_states_outputs.py`: no digit in the company / market / attention blocks of any E2 sample state; E3 (sample, Call B incl. `reaction_so_far`, market) has digits only inside "≈k.k×". The three fixed PREREG tier phrases ("one of the 100 largest US companies", "… rank 101–250", "… 251–500") are removed first: they are labels, not values. **Mutation** move edge 2.0 → 2.5: **RED** | PASS (tier phrases: note) |
| AC5 tokens | `token_stats.csv`. **Call A E3:** p95 state **814** (≤ 900), p95 state + longest core question + 3 special tokens **949**, max 1,024. **Call A D2:** 778 / 913 / 930. **Call B:** 857 / **1,006** / 1,024. **Before the tightening:** Call B was 913 / 1,062 (fail); §3.4. Stored counts re-tokenize exactly on 200 states per file (`tests/test_states_tokens.py`) | PASS (after documented tightening) |
| AC6 no 2026 Call B | No state file has a Call B row with split test or session ≥ 2026-01-02. `reaction_d2.parquet` has no test session. `build_event_states` refuses Call B events outside train / val-A / val-B (test + mutation RED). `ledgers/test_access.jsonl` has 2 lines, both NA-01 (`test_access_ledger_has_no_na04_entry`) | PASS |
| AC7 questions frozen | `tests/test_states_questions_prereg.py` parses the PREREG §7 / A2.2–A2.3 table rows and compares: ids, types and level counts; option keys; every quoted description; the 8 verbatim instructions; Q1's levels; the Q3 / Q4 / Q14 end points; Q17 = Q8's nine company categories + 2. Groups: core A = Q1–Q4, core B = Q1, Q5, Q6, extended = Q7–Q15, explain = Q16–Q17. `questions_v1_sha256` = `e602c6c0…0c85a` = file sha. No `noul`, and the loader refuses one. **Mutations** (one word of Q3; `noul` check removed): **RED** | PASS |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal in `src/`; dates come from configs); access ledger unchanged | PASS |
| GAC4 | No API call; `ledgers/spend.jsonl` empty; $0 | PASS |
| GAC5 | 16 `work/states/` artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte-for-byte (asserted).
`git status` afterwards showed only the author's changes. All 41 turn the tests RED.

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

The revision-1 mutation "ODFL back in the stoplist" no longer applies: a stoplisted ticker that is not an ordinary
word is masked in capitals anyway, which the revision-2 mutation on the vocabulary check covers.

## 3. Numbers

### 3.1 States

| File | robustness | train | val-A | val-B | test | total | mean articles |
|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 689 | 17,759 | 9,073 | 6,145 | 14,419 | 48,085 | 3.88 |
| callA_d2_E3 | 971 | 23,199 | 11,249 | 7,911 | 18,944 | 62,274 | 4.17 |
| callB_d2_E3 | — | 23,199 | 11,249 | 7,911 | — | 42,359 | 4.45 |
| market_E3 (A3.5) | 119 | 203 | 64 | 64 | 145 | 595 | 5.14 |

- **Samples.**
  - NA-07: 1,500 val-A + 1,500 val-B D0 events in each of E0–E4, the same events in every encoding. The E3 sample
    states are byte-identical to the main E3 states.
  - NA-06: an unmasked twin of 1,000 val-A D0 events (Call A E3). The masked twin is the same `event_id` in
    `callA_d0_E3`.
- **D0 vs D2 Call A.** 10,684 of the 48,085 D0 events have a byte-identical D2 Call A state (NA-03 counted 18,656
  identical W0/W2 lists). The rest differ in the W2 attention words, the W2 earnings flag, or the D2 budget cut.
- **Events without text** (`build_states.json`). 18 D0, 11 D2 and 4 Call B events have no state, because every
  listed article lost its text to the price-path scrub or the price-move sentence filter ("Shares of eBay declined
  on Thursday after…"). D0: test 8, val-A 6, val-B 4. PREREG §15 row 5 (e).

### 3.2 Masking

- **Replacements** in the 296,082 event articles (title + snippet):
  - 353,348 company names;
  - 168,938 ticker forms;
  - 263,311 date / year / fiscal-period phrases (incl. datelines, ISINs and option codes);
  - 94,358 person names.
- **Shares.** 62.7% of articles had a name masked and 20.0% a person. 797 articles have no text left. The 3,062 market
  articles had 2,055 dates and 1,150 people masked.
- **Lexicons.** 1,777 corpus surnames (last words of multi-word PERSON names seen ≥ 3 times in English texts,
  capitalized ASCII, not an ordinary or company-alias word, not tagged inside an organization or place at least half
  as often) plus 49 listed public figures; 572 CJK names of 254 companies.
- **Not masked by design** (PRD risks; NA-06 measures them): products and subsidiaries (Zepbound, Firefly, Apple Watch
  → "the company Watch"), other companies' names, fundamental figures, "IT" before an IT noun in Gartner's texts, a
  CJK name never written before the company's ticker.
- **Non-English.** About 5% of articles are non-English (NA-03), 1% CJK. Their dates are masked, and CJK names as
  harvested. Persons count only as multi-word capitalized names, known surnames or Chinese transliterations.

### 3.3 Leak scan (val-A; `leak_scan.csv`, independent scanner)

| File | States | Name/ticker | Year/date | Price moves | Quotes | Price levels | Public figures |
|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 9,073 | 0.10% | 0.00% | 0.14% | 0.07% | 0.01% | 0.00% |
| callA_d2_E3 | 11,249 | 0.07% | 0.00% | 0.17% | 0.07% | 0.01% | 0.00% |
| callB_d2_E3 | 11,249 | 0.07% | 0.00% | 0.17% | 0.07% | 0.01% | 0.00% |
| unmasked twin (control) | 1,000 | 90.5% | 94.1% | 2.6% | 3.3% | 17.5% | 16.7% |

The 9 D0 name/ticker states are read one by one:
- 5 are Gartner's "IT spending" / "IT services", kept on purpose; the scanner counts them conservatively.
- 4 are other entities: Citizens Holding Company, Morgan Stanley in Kinder Morgan's texts, Carnegie Mellon
  University, "visits to Vegas".

The 8 D2 states are 4 of the same Gartner texts, Citizens Holding Company, Morgan Stanley in Kinder Morgan's and
Stanley Black & Decker's texts, and "the Mexican market" (Chipotle). The verifier's manual
read of 10 states (PRD step 2) remains the check on what a scanner cannot see.

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
  - Articles dropped: 854 from 818 D0 states (1.7%); 6,653 from 6,035 D2 Call A states (9.7%); 6,347 from 5,737
    Call B states (13.5%).
- **After** (`token_stats.csv`):

  | File | p50 state | p95 state | max | p95 + longest question | max + longest | share ≤ 768 |
  |---|---|---|---|---|---|---|
  | callA_d0_E3 | 613 | 814 | 889 | 949 | 1,024 | 85% |
  | callA_d2_E3 | 666 | 778 | 795 | 913 | 930 | 91% |
  | callB_d2_E3 | 779 | 857 | 875 | 1,006 | 1,024 | 47% |
  | samples E0 / E1 / E2 / E3 / E4 | 584 / 558 / 543 / 661 / 638 | 745 / 718 / 701 / 819 / 799 | ≤ 888 | ≤ 954 | ≤ 1,023 | 82–100% |
  | unmasked twin | 756 | 880 | 951 | 1,015 | 1,086 | 53% |

  The unmasked twin is an API probe (NA-06) with the masked twin's articles; 3.9% of it exceeds 1,024 with a question.
- **Laya.** The model card's `head_max_len = 256` leaves about 768 tokens for the state. 53% of Call B states and 15% of
  Call A D0 states are longer (owner decision 2).
- **Cost.** Mean request tokens (state + core questions, val + test) exceed NA-03's assumption (news + 250 + 350):

  | Call | Actual | NA-03 assumed | Difference |
  |---|---|---|---|
  | Call A D0 | 895 | 803 | +11% |
  | Call A D2 | 919 | 826 | +11% |
  | Call B | 1,086 | 857 | +27% |

  The NA-11 full plan is about 15–20% dearer than projected: roughly $9.7 at $0.042/M (fits $18) and $21–22 at
  $0.10/M (owner decision 3).

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

Five rows were appended to the §15 Deviations log (2026-10-25, NA-04), all before the freeze. As in earlier chunks,
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

PRD-level choices that need no PREREG change are in `docs/decisions/NA-04.md`.

## 8. STOP conditions and owner decisions

No STOP condition fired: no API call, no budget, no 2026 outcome, no new third party. The three masking policies the
first verification raised were decided by the operator on 2026-10-25 (Revision 1); the second verification raised
no new policy question.

Owner decisions:

1. **Confirm the five NA-04 rows in PREREG §15.** Especially:
   - row 4: masking, including the change to NA-02's price-target rule;
   - row 5 (d): the token budget drops the last articles of 10% of D2 lists.
2. **Laya's state budget.** Every state fits PREREG §9.1's max length 1,024 together with its longest question. If
   NA-08 keeps the released checkpoint's `head_max_len = 256` (≈ 768 for the state), 53% of Call B and 15% of Call A
   D0 states would be cut at the end of the news list. NA-08 should either set the head length to the question's
   actual length (≤ 146 tokens) or ask for a tighter state budget, which is one constant in `configs/states.yaml`.
3. **Cost projection.** Requests are 11–27% larger than NA-03 assumed (§3.4). At $0.10/M the full NA-11 plan is about
   $21–22 against the $18 cap. NA-05's pilot should re-project with the real states.
4. **Non-English articles** (NA-02 decision 4, still open). Their dates are masked and CJK names harvested; a CJK
   name never written before the company's ticker is not known, so excluding CJK articles (1%) stays an option.
5. **`parsing_allowed == None`** (NA-02 decision 1, still open). States use only third-party-OK articles.
6. **Identifiability.** Product names and distinctive facts remain. NA-06's company-identification probe will measure
   it on the masked / unmasked twins.

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
- **Tests.** 7 files: `test_states_codebook`, `test_states_pit`, `test_states_mask`, `test_states_questions_prereg`,
  `test_states_outputs`, `test_states_tokens`, `test_states_determinism`: 251 tests (17 / 130 / 64 / 13 / 19 / 7 / 1).
- **Derived (gitignored).** `work/states/*` (16 files); `work/MANIFEST.json`.
- **Peak RSS per stage (GB).** context 0.7, mask 1.8–2.3 (spaCy, 4 workers), states 4.0–4.3, report 1.5.
- **Reproducibility.** The final code was built (`mask`, `states`, `report`), then `mask` and `states` were run
  again, each in a new process: all 16 `work/states/` sha256s identical (16 of 16). Mask stage 783 / 818 s, states
  328 / 341 s.
- **`make verify`** (exit 0, 196 s, peak RSS 10.8 GB): ruff check "All checks passed!"; ruff format "109 files
  already formatted"; mypy --strict "no issues found in 54 source files"; pytest **798 passed, 1 xfailed** (774 + 1
  after revision 1); manifest 56 artifacts OK; ledgers OK (fmp 0, spend 0, test_access 2, trials 94).
