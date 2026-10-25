# NA-04 REPORT — states: context, codebook, masking, question battery v1

Date: 2026-10-25 · Branch `feat/NA-04-states` (cut from `main` @ `45b3da0`) · Decisions: `docs/decisions/NA-04.md` ·
Artifacts: `artifacts/NA-04/{token_stats.csv, leak_scan.csv, examples.md, summary.json, build_states.json}`.

**Result.** Every decision-model input of the paper now exists as canonical JSON: Call A on D0 (48,096 states,
all splits including test, inputs only), Call A on D2 (62,281, PREREG A3.1), Call B on D2 (42,362, train / val-A /
val-B only), 595 optional A3.5 market states, the NA-07 encoding samples (3,000 events × E0–E4) and a 1,000-event
unmasked twin for NA-06.

- **Masking.** On val-A, residual company-name / ticker hits are in 0 of 9,079 D0 states and 1 of 11,252 D2 states
  (target < 0.5%). Year / date hits are in 0 states. The unmasked twin, scanned the same way, has hits in 90.5% /
  92.3% of states, which shows the scanner finds names and dates when they are there.
- **Availability.** Every block is checked with `pit.check_inputs` at its decision point, plus a call rule:
  only Call B's `reaction_so_far` may read the D2 reaction, and only `d2_reaction` columns.
- **Tokens.** p95(state, Call A, E3) = 819 ≤ 900. One tightening was needed (§3.4): with it, every Call A and
  Call B state plus its longest core question fits Laya's 1,024 tokens (p95 954 / 1,007).
- **Questions.** `configs/questions_v1.yaml` is frozen (sha256 in `configs/frozen.yaml`). It uses every PREREG §7 /
  A2.2–A2.3 string verbatim and has no `noul`.

**Blinding.** No return of a session ≥ 2026-01-02 was read, joined or summarized. Test-period rows exist only
for Call A and carry t−1 context words. Those words come from the NA-01 test inputs and the `Data/` closes, which
PREREG §15 (NA-00 row 2) allows for t−1 features. The D2 reaction comes from
`panel.reactions.build_reactions(period="public")`, which refuses test rows. No module in `newsaction.states`
reads the sealed directory or calls the lock. `ledgers/test_access.jsonl` is unchanged: 2 NA-01 `write` entries.
No val-B statistic of any return was computed; val-B states exist for later chunks.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 codebook | done | `configs/codebook_v1.yaml`, `src/newsaction/states/codebook.py`: PREREG §6.11 scales + encoders E0–E4; NA-04 additions marked in the YAML (PREREG §15 row 2) |
| S2 context | done | `states/context.py` (company, market, attention, reaction blocks), `states/macro.py` + `configs/macro_calendar.yaml` (CPI from vintages; FOMC from federalreserve.gov, URL cited); `configs/states.yaml`; 45 columns registered in `configs/availability.yaml`; `work/states/{context_company, context_market, reaction_d2}.parquet` |
| S3 masking | done | `states/mask.py`, `states/scan.py`, `configs/aliases.yaml` (curated names / tickers for the 196 companies ranked ≤ 150 in any month since 2024-01, plus renamed companies); spaCy `en_core_web_sm` 3.8.0 pinned; `work/states/articles_masked.parquet` |
| S4 questions | done | `configs/questions_v1.yaml` (groups core / extended / explain), `states/questions.py` (loader for any group combination, `noul` refused, request shape); sha256 in `configs/frozen.yaml` |
| S5 build | done | `states/build.py` (specs, availability checks, canonical JSON, budget, samples, CLI); `work/states/{callA_d0_E3, callA_d2_E3, callB_d2_E3, market_E3}.parquet`, `work/states/samples/{callA_d0_E0…E4, unmasked}.parquet` |
| S6 token budget | done | `artifacts/NA-04/token_stats.csv`; tightening documented (§3.4) |
| S7 leak scan | done | `artifacts/NA-04/leak_scan.csv` (every val-A state of the three masked E3 files + the unmasked twin); `artifacts/NA-04/examples.md` (3 Call A, 2 Call B, val-A, seed 2026) |
| report stage | done | `states/report.py` (`--stage report`) |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 determinism | **Test.** `tests/test_states_determinism.py` takes 2,000 rows from seven state files (400 each of the three main files; 200 each of E0, E4, unmasked and market). It rebuilds them from the registered inputs: context recomputed for the sampled keys (and compared with the stored rows: equal), every article re-masked by a fresh in-process masker, states re-rendered. **2,000 / 2,000 sha256 identical.** **Reruns.** A full rerun of `context`, `mask` and `states` on the final code reproduced all 14 work/states sha256s (14 / 14) | PASS |
| AC2 masking | **Rates.** `leak_scan.csv`, val-A, per file (states with ≥ 1 hit). Name/ticker: callA_d0 **0 / 9,079**, callA_d2 **1 / 11,252 (0.009%)**, callB_d2 1 / 11,252. Year/date: **0** in all three. Target < 0.5% (`test_val_a_leak_rates_below_target`). **Positive control.** Unmasked twin: 90.5% / 92.3%. **Mutation** "empty the alias list" (`companies: {}`): **RED** (`test_curated_and_derived_names`) | PASS |
| AC3 availability | **Tests.** `tests/test_states_pit.py`: z_id, z_cc, z_on, y0, e5, r_cc, adj_close (`post`), every `w2` / `d2_reaction` column, vendor `selection_only` columns, `material` and `clean_5`. Added to any block of a D0 Call A spec, each raises `PITError` (84 cases). Call B's `reaction_so_far` accepts `d2_reaction` columns only (z_cc, y2, e5, ar_cc, g_d1, raw_close refused). Reaction columns refused in every other block, and Call A has no reaction block. Planted shocks: a +50% SPY day / stock close at t changes no market / company context dated ≤ t, and does change t+1. **Mutation** z_cc registered `t_minus_1`: **RED** | PASS |
| AC4 encodings | **Tests.** `tests/test_states_codebook.py`: every bin edge of move, percentile, β, attention and revision (value − ε, the edge, + ε); the PREREG examples of E0–E4 reproduced exactly; E2 words carry no digit, E3 only inside "≈k.k×", for every horizon. **Built files.** `tests/test_states_outputs.py`: every E2 sample state's company / market / attention blocks have no digit; E3 (sample, Call B incl. `reaction_so_far`, market) has digits only inside "≈k.k×", with the three fixed PREREG tier phrases ("one of the 100 largest US companies", "… rank 101–250", "… 251–500") removed first, since they are labels, not values. **Mutation** move edge 2.0 → 2.5: **RED** | PASS (tier phrases: note) |
| AC5 tokens | `token_stats.csv`. **Call A E3:** p95 state **819** (≤ 900), p95 state + longest core question + 3 special tokens **954**, max 1,024. **Call A D2:** 780 / 915 / 930. **Call B:** 858 / **1,007** / 1,024. **Tightening.** Before it, Call B was 913 / 1,062 (fail); the documented cut is in §3.4. Stored counts re-tokenize exactly on 200 states per file (`tests/test_states_tokens.py`) | PASS (after documented tightening) |
| AC6 no 2026 Call B | No state file has a Call B row with split test or session ≥ 2026-01-02. `reaction_d2.parquet` has no test session. `build_event_states` refuses Call B events outside train / val-A / val-B (test + mutation RED). `ledgers/test_access.jsonl` has 2 lines, both NA-01 (`test_access_ledger_has_no_na04_entry`) | PASS |
| AC7 questions frozen | `tests/test_states_questions_prereg.py` parses the PREREG §7 / A2.2–A2.3 table rows and compares: ids, types and level counts; option keys; every quoted description; the 8 verbatim instructions; Q1's levels; the Q3 / Q4 / Q14 end points; Q17 = Q8's nine company categories + 2. Groups: core A = Q1–Q4, core B = Q1, Q5, Q6, extended = Q7–Q15, explain = Q16–Q17. `questions_v1_sha256` = `e602c6c0…0c85a` = file sha. No `noul`, and the loader refuses one. **Mutations** (one word of Q3; `noul` check removed): **RED** | PASS |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (54 artifacts, 10 inputs) | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal in `src/`; dates come from configs); access ledger unchanged | PASS |
| GAC4 | No API call; `ledgers/spend.jsonl` empty; $0 | PASS |
| GAC5 | 14 new `work/states/` artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte-for-byte (asserted).
`git status` afterwards showed only the author's changes.

| Mutation | File | Result |
|---|---|---|
| alias list emptied (verifier 6a) | configs/aliases.yaml | RED |
| z_cc registered `t_minus_1` (verifier 6b) | configs/availability.yaml | RED |
| move edge 2.0 → 2.5 (verifier 6c) | configs/codebook_v1.yaml | RED |
| `check_inputs` removed from `validate_spec` | states/build.py | RED |
| reaction "d2_reaction only" rule removed | states/build.py | RED |
| Call B test-period refusal removed | states/build.py | RED |
| third-party check removed | states/build.py | RED (after a test was added; first round GREEN) |
| E3 multiple rounded instead of truncated | states/codebook.py | RED |
| trailing history includes the scored value | states/context.py | RED |
| market context not shifted (day t used) | states/context.py | RED |
| earnings stamp at the close kept in W2(s) | states/context.py | RED |
| bare-year rule removed | states/mask.py | RED (after a test was added; first round GREEN) |
| person masking disabled | states/mask.py | RED |
| loader accepts `noul` | states/questions.py | RED (message assertion tightened; first round GREEN, as the type check still refused it) |
| one word of Q3 edited | configs/questions_v1.yaml | RED |

## 3. Numbers

### 3.1 States

| File | robustness | train | val-A | val-B | test | total | mean articles |
|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 689 | 17,759 | 9,079 | 6,147 | 14,422 | 48,096 | 3.88 |
| callA_d2_E3 | 971 | 23,199 | 11,252 | 7,911 | 18,948 | 62,281 | 4.16 |
| callB_d2_E3 | — | 23,199 | 11,252 | 7,911 | — | 42,362 | 4.44 |
| market_E3 (A3.5) | 119 | 203 | 64 | 64 | 145 | 595 | 5.14 |

- **Samples.** NA-07: 1,500 val-A + 1,500 val-B D0 events in each of E0–E4, the same events in every encoding.
  The E3 sample states are byte-identical to the main E3 states. NA-06: an unmasked twin of 1,000 val-A D0 events
  (Call A E3); the masked twin is the same `event_id` in `callA_d0_E3`.
- **D0 vs D2 Call A.** 10,621 of the 48,096 D0 events have a byte-identical D2 Call A state, so NA-11 gets those
  from the cache (NA-03 counted 18,656 identical W0/W2 lists). The rest differ in the W2 attention words, the
  W2 earnings flag, or the D2 budget cut (§3.4).
- **Events without text** (`build_states.json`). 7 D0, 4 D2 and 1 Call B event have no state, because every
  listed article lost its text: price-path sentences that NA-02's scrubber missed and the second scrub after
  masking removed ("Shares of eBay declined on Thursday after…"). 9 of the 11 Call A cases are val-B or test.
  PREREG §15 row 5 (e).

### 3.2 Masking

- **Replacements** in the 296,082 event articles (title + snippet):
  - 345,253 company names;
  - 166,294 ticker forms;
  - 249,536 date / year / fiscal-period phrases (incl. datelines and ISINs);
  - 84,952 person names.
- **Shares.** 61.5% of articles had a name masked and 18.2% a person. 251 articles have no text left. The 3,062
  market articles had 2,027 dates and 829 people masked.
- **Iterations** (each re-scanned all 296K masked articles):

  | Masker version | Articles with a residual company-name hit |
  |---|---|
  | first (case-sensitive phrases) | 12,235 |
  | case-insensitive phrases + distinctive words, hyphen / en-dash variants (DexCom, GE Healthcare, Smucker, Mettler-Toledo) | 37 |
  | HTML entities decoded (`Microsoft&nbsp;`) | 4 |

  A vocabulary rule removed spaCy's title-case misfires ("Balance Sheet", "Buy", "Soar" as PERSON). It cut person
  replacements from 138,924 to 84,952 while still catching surnames that NER missed ("Elon Musk … Musk added").
- **Not masked by design** (PRD risks; NA-06 measures them):
  - products and subsidiaries (Zepbound, Firefly, Apple Watch → "the company Watch");
  - other companies' names;
  - fundamental figures.
- **Non-English.** About 5% of articles are non-English (NA-03). The masker is English-only; in a text the
  detector flags as non-English, only multi-word capitalized names count as persons. Some foreign words are
  still masked as "a person" (`examples.md`, the French headline).

### 3.3 Leak scan (val-A; `leak_scan.csv`)

| File | States | Name/ticker states | Year/date states |
|---|---|---|---|
| callA_d0_E3 | 9,079 | 0 (0.000%) | 0 |
| callA_d2_E3 | 11,252 | 1 (0.009%) | 0 |
| callB_d2_E3 | 11,252 | 1 (0.009%) | 0 |
| unmasked twin (control) | 1,000 | 905 (90.5%) | 923 (92.3%) |

The one remaining hit is a run-together market-research name list in the company's own article ("… What
Investors Must Know | StanleyBlack&Decker, NucorFastener, …"), which the word-boundary patterns cannot split.
The verifier's manual read of 10 states (PRD step 2) is the check on alias completeness: the scanner uses the
masker's own name definition.

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
  - Cost: 627 D0 states lost 659 articles; 6,389 D2 states lost 7,111. No text was cut.
- **After** (`token_stats.csv`):

  | File | p50 state | p95 state | max | p95 + longest question | max + longest | share ≤ 768 |
  |---|---|---|---|---|---|---|
  | callA_d0_E3 | 616 | 819 | 889 | 954 | 1,024 | 83% |
  | callA_d2_E3 | 671 | 780 | 795 | 915 | 930 | 90% |
  | callB_d2_E3 | 783 | 858 | 875 | 1,007 | 1,024 | 45% |
  | samples E0 / E1 / E2 / E3 / E4 | 589 / 562 / 546 / 664 / 643 | 751 / 724 / 709 / 827 / 805 | ≤ 888 | ≤ 962 | ≤ 1,023 | 80–100% |
  | unmasked twin | 757 | 880 | 951 | 1,015 | 1,086 | 53% |

  The unmasked twin is an API probe (NA-06) with the masked twin's articles; 3.7% of it exceeds 1,024 with a
  question.
- **Laya.** The model card's `head_max_len = 256` leaves about 768 tokens for the state. 45% of Call B states and
  17% of Call A D0 states are longer (owner decision 2).
- **Cost.** Mean request tokens (state + core questions, val + test) exceed NA-03's assumption (news + 250 +
  350): Call A D0 898 vs 803 (+12%), Call A D2 923 vs 826 (+12%), Call B 1,090 vs 857 (+27%). The NA-11 full plan
  is therefore about 15–20% dearer than NA-03 projected: roughly $9.7 instead of $8.32 at $0.042/M (fits $18),
  and $21–22 instead of $18.43 at $0.10/M (owner decision 3).

### 3.5 Context checks

- **Missing values** (state words "not available"), share of event keys:
  - σ / momentum percentiles: 1.5–4.5% (short history after index entry);
  - FY1 revision: 3–5%;
  - E0 raw returns: 0.1–3% outside test (test: never built);
  - market series: 0%, except the HY OAS z in 18.5% of robustness sessions (FRED history starts 2023-08).
- **Macro.** 30 CPI release dates 2024-01 … 2026-07 match the BLS schedule, including the shutdown-delayed
  2025-10-24 and 2025-12-18 releases and no October 2025 release. 24 FOMC statement dates.
- **Earnings.** A scheduled report falls in W0 for 4.3% of val-A event keys.

## 4. Questions (S4)

- **Shape.** Call A asks core {justified_move (score, 9), materiality (choice, 2 neutral keys), surprise
  (score, 5), tone (score, 5)}; Call B asks {justified_move, reaction_adequacy (choice, 6), continuation
  (choice, 3)}. The extended group is Q7–Q15 (Call A), the explain group Q16–Q17 (Call B).
- **Verbatim text.** All PREREG-verbatim strings are used as written.
- **Text written by NA-04** (PREREG §15 row 5 (c)): instructions of Q2, Q5, Q6, Q9–Q13, Q15, each referencing
  `news` and/or `reaction_so_far` in backticks; the middle levels of Q3 / Q4 / Q14; option descriptions where
  PREREG gives keys only; Q1's rise ranges mirrored from the falls.
- **Empirical-finding self-check** (`test_authored_text_references_state_fields_and_states_no_finding`):
  - every instruction and option is scanned for tends / usually / typically / historically / on average /
    often / more or less likely / research / studies / evidence / underreact / overreact / drift / momentum /
    revert: **no match**;
  - backticked fields must be `news` or `reaction_so_far`;
  - read by hand as well: no option states what a kind of news usually does ("legal news tends to continue"
    style). Q5's six options are relative to "what the news justifies"; Q6's are directional only.

## 5. Spend, network

- **Spend.** OpenRouter $0.00 this chunk and cumulative (`ledgers/spend.jsonl` empty). FMP requests: 0. Kaggle:
  none.
- **Network:**
  - one download of the spaCy `en_core_web_sm` 3.8.0 wheel from GitHub (explosion/spacy-models), pinned in
    `pyproject.toml` / `uv.lock`;
  - three page reads: the OpenRouter Jev guide, the Laya model card and the Fed FOMC calendar.
- No article text or derived data left the machine.

## 6. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| panel `sector`, `tier` (events), `beta_m`, `sigma_cc`, `z_m{5,20,60}`, `logv_mad60` (panel_public ∪ panel_test_inputs) | company block; volume multiple | `static` / `t_minus_1` (NA-01, through close(t−1)) |
| `ctx_sigma_cc_pct`, `ctx_z_m{k}_pct` | volatility regime; E4 | `t_minus_1`: the value at t (already through t−1) vs the symbol's 252 previous values; shock tests |
| panel `adj_close` (public) | `ctx_ret_m{k}` (E0 samples, val only) | shifted one session: AdjClose(t−1) / AdjClose(t−1−k) |
| estimates_fy1 | FY1 revision | snapshots dated before the session (and 30 days earlier); test: snapshot on the session not used |
| earnings_dates | earnings flag | [close(prev s), 09:15 ET] (`w0`) / [close(prev s), close s) (`w2`); retrospective calendar, read as a pre-announced schedule |
| market_prices (SPY, VIX, DXY, oil), DGS10 | market block | last observation dated ≤ prev(s); σ / percentiles from the 252 changes before it |
| BAMLH0A0HYM2 | HY spread change | the change of t−2 (publication lag) |
| cpi_vintages, macro_calendar.yaml | scheduled releases today | `static` (published schedules) |
| window_counts via events (`attention_ratio_*`, `n_stories_*`) | attention block | `w0` / `w2` counts; 60-session mean `t_minus_1` (NA-03) |
| events news lists (title_clean / snippet_clean, t_avail, source_class_domain) | news block | `w0` / `w2` (NA-03 / NA-02); vendor `source_class` not used (only the domain class) |
| articles_clean `third_party_ok` | governance check | `selection_only`; read only to refuse non-OK articles |
| `build_reactions(public)`: g_d2, react_r_cc, react_r_spy_cc, react_z_vol; z_cc history; SPY history | Call B `reaction_so_far` | `d2_reaction` (the reaction of s); E4 / σ histories through t−1; never in Call A (call rule + tests) |

## 7. Deviations from PREREG

Five rows were appended to the §15 Deviations log (2026-10-25, NA-04), all before the freeze. As in earlier
chunks they are **in the working tree, not committed**, for the operator to commit on main.

1. **§6.10 industry.** Sector only, because ATOM has GICS level 1 only.
2. **§6.10–§6.11 codebook additions:**
   - multi-day and market-series moves;
   - revision, count, volume, timing, time-label and source-type words;
   - "not available";
   - only moves vary with the encoding.
3. **§6.10 availability.** Publication lags (HY OAS at t−2), CPI and FOMC calendars, the earnings windows.
4. **§6.3 masking tokens and rules.** "The quarter" instead of "the latest quarter", years and fiscal years,
   datelines and ISINs, the person rules, case-insensitive matching.
5. **§6.4 / §6.10 / §7:**
   - (a) no pre-market talk in Call B;
   - (b) D2 Call A attention from W2;
   - (c) the question text written by NA-04;
   - (d) the token budget;
   - (e) no state for events without text.

PRD-level choices that need no PREREG change are in `docs/decisions/NA-04.md`.

## 8. STOP conditions and owner decisions

No STOP condition fired: no API call, no budget, no 2026 outcome, no new third party.

Owner decisions:

1. **Confirm the five NA-04 rows in PREREG §15**, especially row 4 ("the quarter" for "the latest quarter")
   and row 5 (d) (the token budget drops 10% of D2 lists' last articles).
2. **Laya's state budget.** PREREG §9.1 trains Laya-Fin with max length 1,024, and every state fits that with its
   longest question. If NA-08 keeps the released checkpoint's `head_max_len = 256` (≈ 768 for the state), 45% of
   Call B and 17% of Call A D0 states would be cut at the end, inside the news list. NA-08 should either set the
   head length to the question's actual length (≤ 146 tokens) or ask for a tighter state budget, which is one
   constant in `configs/states.yaml`.
3. **Cost projection.** Requests are 12–27% larger than NA-03 assumed (§3.4). At $0.10/M the full NA-11 plan is
   about $21–22 against the $18 cap; A2.6's cuts or §13's Call A + one Call B rule would apply. NA-05's pilot
   should re-project with the real states.
4. **Non-English articles** (NA-02 decision 4, still open): masking is English-only.
5. **`parsing_allowed == None`** (NA-02 decision 1, still open): states use only third-party-OK articles, as the
   NA-03 events do.
6. **Identifiability.** Product names and distinctive facts remain. NA-06's company-identification probe will
   measure it on the masked / unmasked twins.

## 9. Files

- **Added — code.** `src/newsaction/states/{__init__, codebook, context, macro, mask, scan, questions, build, report}.py`.
- **Added — configs.** `configs/{codebook_v1, questions_v1, aliases, macro_calendar, states}.yaml`.
- **Added — docs and artifacts.** `docs/decisions/NA-04.md`; `artifacts/NA-04/{REPORT.md, token_stats.csv,
  leak_scan.csv, examples.md, summary.json, build_states.json}`.
- **Changed.**
  - `configs/availability.yaml`: 45 NA-04 columns.
  - `configs/frozen.yaml`: `questions_v1_sha256`, `codebook_v1_sha256`.
  - `docs/DATA_CONTRACT.md`: the NA-04 section, 14 artifacts.
  - `pyproject.toml` / `uv.lock`: `en-core-web-sm` 3.8.0 in the `embed` extra.
- **Changed, uncommitted.** `docs/PREREG.md` (§15 rows).
- **Tests added: 7 files, 206 tests.**
  - `test_states_codebook` 17, `test_states_pit` 130, `test_states_mask` 19, `test_states_questions_prereg` 13;
  - `test_states_outputs` 19, `test_states_tokens` 7, `test_states_determinism` 1.
- **Derived (gitignored).** `work/states/*` (14 files); `work/MANIFEST.json`.
- **Peak RSS per stage (GB).** context 0.7, mask 2.1 (spaCy, 4 workers), states 4.2, report 1.4.
- **`make verify`:** exit 0.
  - ruff: all checks passed; 109 files formatted.
  - mypy --strict: no issues in 54 source files.
  - pytest: **753 passed** (547 before NA-04 + 206 new), **1 xfailed** (NA-01's literal AC3(c) bound); 179 s.
    Peak RSS of the whole `make verify` 9.6 GB (the full suite; NA-03 reported 9.3 GB).
  - manifest OK (54 artifacts, 10 inputs); ledgers OK (trials 94, test_access 2, spend 0, fmp 0).
