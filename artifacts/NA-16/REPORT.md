# NA-16 REPORT — the manuscript

Date: 2026-10-29 · Branch `feat/NA-16-paper` (main checkout, cut from main @ 8371696; not merged) · Decisions:
`docs/decisions/NA-16.md` (choices, NA-14 generator changes, corrections, the reference log) · PDF:
`artifacts/NA-16/paper.pdf` · Spend: $0 (no API call, no Kaggle run, nothing reads `newsaction.lock`).

**Bottom line.**
- **An arXiv preprint in LaTeX**, 41 pages: a title page; 24 pages of main text (Sections 1–12, pp. 2–25) with 8
  figures, 6 tables and 9 numbered equations; 4 pages of references (66 entries, every one verified); a
  12-page appendix (pp. 30–41) with 3 figures, 6 tables and the deflated-Sharpe equation.
- **Every result number enters through a macro** (`\res{name}`, 270 names) generated from NA-14's table keys by
  `make paper-text`; a test fails on any hand-typed result number, an unregistered or unused macro, a non-ASCII
  line or an unlabelled exploratory sentence. The only keys added are counts in NA-14's derived table (t30).
- **`make paper-pdf`** (tectonic, `--keep-logs`): no error, no overfull box, no undefined reference or citation,
  no oversized float, every font embedded, figures and tables numbered in order of first mention with no gap.
  Every page was rendered to PNG (PDFKit) and looked at.
- **NA-14's tables and Figure 5 were changed in NA-14's generator**, never by hand: pipeline names out of the
  notes the paper prints, numbers in each caption's first sentence, Table 6's trial counts, Table 5 and Figure 5
  without "Call A/Call B", the deviations table by stage. `make paper` reproduces every digest; `make
  paper-preview` passes.
- **`make verify`** exit 0: 2,208 passed, 3 skipped, 2 xfailed; manifest OK (487 artifacts); ledgers unchanged.
- **Open:** affiliations, e-mail, the data and code statement and URL, the title choice, the AI-use statement,
  and a final pdflatex check (Docker's TeX Live image) that needs your approval before any image is pulled.

## 1. Scope

| Item (prompt section) | Status | Where |
|---|---|---|
| 0 Branch, memory rules, no API/Kaggle/lock | done | `feat/NA-16-paper` from 8371696; `pgrep` and `memory_pressure` before `make verify` (59% free, no other run) |
| 1 Read first | done | CLAUDE.md, PREREG with §15 (both forward-test rows), the REPORTs of NA-03, 06, 08, 11, 12, 13, 13b, 14, NA-13b's decisions, the outline, NA-14's captions/tables/figures/preview, REPLICATION.md, the earlier paper's verified abstract |
| 2 What the paper says | done | Sections 4–11; corrections to the summary in the decisions file |
| 2a The usefulness rule | done | §4 below: every NA-14 and NA-13b table and figure placed, with a reason |
| 3 Structure | done | `paper/main.tex`, `paper/sections/*.tex` (title page, 12 sections, appendix A–F) |
| 3b Equations | done | §5 below |
| 4 Title, authors, abstract | done | title page; `arxiv/abstract.txt` (221 words); alternatives in §3 |
| 5 Findability | done | terms in title, abstract, keywords and headings; hyperref metadata; T1 + lmodern + glyphtounicode; `arxiv/abstract.txt`, `arxiv/metadata.md`, `CITATION.cff`; nothing hidden |
| 6 References | done | `paper/references.bib` (66); log in `docs/decisions/NA-16.md` |
| 7 Traceable numbers | done | `paper/numbers.yaml`, `paper/generated/numbers.tex`, `paper/allowlist.yaml`, `tests/test_paper_text.py` |
| 8 Build and checks | done (pdflatex pending your approval) | `make paper-text`, `make paper-pdf`, `newsaction.paper.{numbers,build,contract}` |
| 9 REPORT, decisions | done | this file; `docs/decisions/NA-16.md` |

## 2. Self-audit

| Check | Evidence | Result |
|---|---|---|
| No new analysis | every number is a cell of `artifacts/NA-14/tables/keys.json`; the only new keys are counts of existing rows (t30: tournament models 21 and stage-2 6, conditioning pairs 75, selected 8, reversed 5, positive 3, failed ablation requests 210), each with its formula and source | PASS |
| No claim beyond the REPORTs | the resolved text of every section was read against the keys and the REPORTs; five places where the prompt's summary differs from the REPORTs are written as the REPORTs have them (decisions file) | PASS |
| Numbers through macros | `make paper-text`: 270 numbers, 0 problems; `tests/test_paper_text.py` (11 tests) plants a typed number in text and in math, an unknown and an unused macro, a non-ASCII line, an unlabelled exploratory sentence and an allowlist entry without a reason, and each is caught | PASS |
| ASCII, pdflatex-safe sources | the check covers `paper/*.tex|.bib|.yaml`, the sections, the generated macros and `arxiv/*`; no `fontspec`; standard packages only (§9) | PASS |
| Compile | `make paper-pdf`: tectonic exit 0; errors 0; overfull 0 (max 0.0 pt); undefined 0; float too large 0; LaTeX warnings 0; float order []; 67 fonts, all embedded; 41 pages | PASS |
| Visual check | every page rendered (PDFKit, `swiftc`), looked at as contact sheets and singly: title block, floats near first mention, no orphaned heading (a `needspace` before "Key findings"; no empty appendix heading), captions readable | PASS |
| NA-14 unchanged except as listed | `make paper` all outputs equal after `--write-digests`; `figures.captions` 0 problems; `make paper-preview` 0 overfull, 0 undefined; NA-14 tests 207 passed | PASS |
| Data contract | `newsaction.figures.contract` (183 NA-14 entries) and `newsaction.paper.contract` (3 NA-16 entries); `python -m newsaction.io check`: OK | PASS |
| `make verify` | exit 0: ruff and format clean (323 files), mypy --strict clean (183 files), pytest 2,208 passed / 3 skipped / 2 xfailed in 272 s, manifest OK (487 artifacts), ledgers OK (trials 1,620, test access 29, unchanged); peak RSS about 8.0 GB | PASS |
| Spend and access | no API call, no Kaggle run, no FMP request, no lock read; `ledgers/*` byte-identical; web requests only to verify references, with no e-mail or identifying header | PASS |

## 3. The paper

- **Title (working):** "The Market Reads the News First: A Pre-Registered, Look-Ahead-Free Test of AI Decision
  Models on Stock-Price Reactions". **Alternatives for your choice:**
  1. "Priced at the Open: A Pre-Registered Test of Whether AI Decision Models Can Read Financial News Before the
     Market";
  2. "Clean Validation, Null Test: AI Decision Models, Financial News and Stock-Price Reactions in a
     Pre-Registered, Look-Ahead-Free Design".
- **Authors** (operator, 2026-10-29: these three for now): Amir Dehkordi (corresponding), Arman Khaledian,
  Nariman Khaledian; affiliations and e-mail are red placeholders.
- **Abstract:** 221 words, from the prompt's draft with every number checked and four edits: "return
  probabilities" (not "calibrated probabilities", since the commercial models are overconfident); "where the
  models predict anything, it is the overnight gap" (Laya-Fin's test ICs are small on both sides); "survives
  transaction costs and a deflated Sharpe ratio"; and the exploratory sentence (in-sample Sharpe ratios up to
  6.8). The plain-text version is `arxiv/abstract.txt`, generated from the LaTeX so the two cannot differ.
- **Keywords, JEL, categories** as in the prompt; the categories (cs.AI primary; q-fin.ST, cs.LG, cs.CL) are a
  footnote on the title, as is a placeholder for the data and code statement.
- **Sections:** 1 Introduction (question, decision models, look-ahead and memorization, design, seven key
  findings, contributions); 2 Related work (six paragraphs, the earlier paper last); 3 Data and design; 4 Clean
  validation did not survive the blinded test; 5 Pre-open news is priced at the open; 6 The models cannot tell
  over- from under-reaction (the regression, the convergence ladder, what it identifies, gap closure, the
  classes); 7 News explains little of a stock's own move; the commercial models are overconfident; 8 What the
  models know about masked firms; 9 Economic significance; 10 Exploratory analyses (post hoc): where the signal
  lives; 11 Limitations and the forward test; 12 Conclusion; acknowledgments and statements (placeholders).
  Appendix: A Pre-registration and deviations; B Notation; C The deflated Sharpe ratio; D Additional
  pre-registered results; E Exploratory: the conditioning study; F The replication package.

## 4. The usefulness rule: where every table and figure went

Figures (PDF numbering follows first mention):

| NA-14 file | Paper | Reason |
|---|---|---|
| `fig1_validation_test` | Figure 1 | finding 1 |
| `fig2_priced_at_open` | Figure 2 | finding 2 |
| `fig3_convergence` | Figure 3 | finding 3 (the ladder and its fade) |
| `fig4_over_under` | Figure 4 | finding 3 (Under never catches up; only large moves reverse) |
| `fig5_explaining_moves` | Figure 5 | finding 5 (redrawn: legend without "Call A/B") |
| `fig7_memorisation` | Figure 6 | finding 4 (Section 8 comes before Section 9) |
| `fig6_strategies` | Figure 7 | finding 7 |
| `figA16_selective_coverage` | Figure 8 (exploratory section) | the exploratory selective-prediction result |
| `figA5_robustness` | Figure A1 | needed to judge findings 1–2: no variant changes a conclusion |
| `figA4_reliability` | Figure A2 | finding 6 (pre-registered calibration) |
| `figA18_conditioning_map` | Figure A3 | the decay result: all 75 pairs, the 8 selected and their collapse at a glance (chosen over t39, whose numbers the text cites) |
| `figA1_tournament`, `figA2_filters`, `figA3_encoding` | left out | design details; the text gives the counts and the filter's recall |
| `figA6_monthly_ic`, `figA14_exploratory_d0` | left out | no month effect; the earnings split is stated in the text with its numbers |
| `figA7_convergence_detail`, `figA8_drift_laya_fin` | left out | Figure 3, Figure 4 and Table 4 carry the result; the anchor is uninformative and Laya-Fin has too few classified events |
| `figA9_shapley` | left out | shares of a total that is about zero; one sentence |
| `figA10_ablations`, `figA11_persistence`, `figA13_probes` | left out | one sentence each (unmasking; θ; the flip screen) |
| `figA12_strategy_paths`, `figA15_exploratory_ma_cross` | left out | Figure 7 (c) shows the convergence path; the MA-cross result is one sentence |
| `figA17_watch_open` | left out | one sentence with the ICs and t; the figure adds only intervals |
| `figA19_output_histograms` | left out | Figure A2 and the skill numbers carry finding 6; the histograms are exploratory |

Tables:

| NA-14 table | Paper | Reason |
|---|---|---|
| `tab1_primary` … `tab6_strategies` | Tables 1–6 | the primary hypotheses (required), the IC by target, H2, the ladder, the explanation ladder and H5, the strategies |
| `t34_prereg_deviations` | Table A1 | honesty: every deviation (required) |
| (new) notation | Table A2 | the prompt |
| `t14_model_comparison` | Table A3 | every model's val-B and test IC and cost (H7's cost part; judges finding 1) |
| `t5_heterogeneity` | Table A4 | pre-registered secondary cuts (every secondary test in a summary table) |
| `t4_secondary` | Table A5 | every secondary hypothesis (required) |
| `t15_calibration` | Table A6 | finding 6; H7's calibration part |
| `t1_primary`, `t3_ic`, `t32_val_b_ic`, `t2_h2_over_under`, `t6_convergence_ladder`, `t7_gap_closure`, `t10_explanation_ladder`, `t35_break_even` | covered | their cells are in Tables 1–6; the full tables are in the replication package |
| `t1b_primary_by_model` | left out | per-model H1 in Figure 2 and the text |
| `t8`, `t9`, `t11`, `t12`, `t13`, `t16`, `t21`, `t22`, `t23`, `t24`, `t25`, `t26`, `t27`, `t28`, `t30` | left out | the numbers the text needs are cited from their keys |
| `t17`, `t18`, `t19`, `t29`, `t31`, `t33` | left out | sectors, probes, monthly ICs, encodings, the exploratory market replication, placebo quantiles (Figure 7 shows them) |
| `t20_strategies` | left out | Table 6 summarizes; every book is in the replication package |
| `t36`, `t37`, `t38`, `t39` | left out | Figure 8, Figure A3 and the text's numbers carry them |
| `t40`, `t41`, `t42` | left out | the operator's recommendation |
| `t43_band_disclosure` | replaced | by the disclosure sentence (Section 10, Figure 8 and Figure A3 captions) |

The appendix ends with one pointer: "Further tables and figures are in the replication package."

## 5. Equations

Main text: (1) the return split and the z-scores; (2) the daily IC; (3) H1 and H1b; (4) the over/under
regression; (5) the convergence ladder; (6) attenuation under classical measurement error, κ̂_h → θ_V κ*_h, with
the level and shape consequences, labelled an interpretation; (7) gap closure and the half-life; (8) the
out-of-sample R² and ΔR²; (9) the memorization accuracy and its excess over the matched baseline. The news-implied
move N̂ = Σ p_k m_k is an unnumbered display. Appendix: (A1) the deflated Sharpe ratio as `strategy.dsr` computes
it (Mertens denominator, analytic trial variance, expected maximum Sharpe SR0). Each equation is followed by one
sentence on what it measures and how the results read it.

## 6. Numbers and claims

- 270 macros (`paper/numbers.yaml` → `paper/generated/numbers.tex`), each a cell of NA-14's keys; the allowlist
  holds dates, names and pre-registered design constants, each with its reason (decisions file).
- Exploratory claims say "exploratory" or "post hoc" in the same sentence (checked mechanically for Section 10).
- Deviations summarized in the text (Sections 3, 11) and listed in Appendix A: H1b before the freeze; the canary
  STOP and its rule; the price-only post-close timing; the 210 rate-limited ablation requests; the items not run;
  the exploratory study's VIX source and payroll dates; plus the masking rounds, the screen-failing comparators,
  one seed and one epoch, the matched-distractor re-run and the forward test.
- Trial counts agree in the text (Sections 3, 9, 10), Table 6's note and Appendix C: the pre-registered
  strategies' DSR used N = 545; the ledger holds 1,620 after the exploratory study, which deflated its own books
  with 1,620.

## 7. References

66 entries, all cited, all verified against a primary record (log in the decisions file). Changes from the
starting list: Kim, Muhn and Nikolaev not cited (withdrawn); Lopez-Lira and Tang, He et al. (JFE 2026),
Glasserman and Lin (JFDS 2024), ModernBERT (ACL 2025) and C-Pack (SIGIR 2024) cited in their published versions;
Ke, Kelly and Xiu cited as the NBER working paper; the Laya weights cited as their Hugging Face page. The earlier
paper (arXiv 2608.14014, v2) is summarized from its verified abstract.

## 8. Build and the look at every page

`make paper-text` then `make paper-pdf` (about 30 s). The build copies `main.bbl` to `paper/generated/` for arXiv.
PDF sha256 `393c734cf8fce69025025e704b3cc04902bf8c6c74c0b46c3c27607126030d72` (after §13's changes) (tectonic's bundle decides the bytes; reported, not enforced). Every page was rendered at
72 and 115 dpi and inspected. Fixes made from the look: the two title footnote marks overlapped (now separated);
an inline list of level midpoints ran into the margin (now a display); "Key findings" sat alone at a page foot
(`needspace`); three tables sat alone on half-empty float pages (float fractions loosened); the notation table
floated away from its heading (now a longtable in the flow); empty appendix headings (a paragraph and a float
barrier); the bibliography in small type.

## 9. pdflatex compatibility

ASCII-only sources (tested); no `fontspec`; `fontenc` T1 with `lmodern`; `inputenc` and `glyphtounicode` only under
pdfTeX (`iftex`); packages all in TeX Live (geometry, amsmath, amssymb, graphicx, booktabs, array, longtable,
threeparttable, threeparttablex, pdflscape, siunitx, caption, enumitem, needspace, placeins, xcolor, natbib,
microtype, hyperref); figures are PDF; the `.bbl` is shipped, since arXiv does not run BibTeX; the figure and table
paths are two macros (`\figdir`, `\tabdir`) that an arXiv bundle sets to its own folders (`arxiv/metadata.md`).
NA-14's tables use siunitx v3 options (TeX Live 2021 or later). **Not yet run: a real pdflatex compile.** It needs
a TeX Live image (for example Docker's `texlive/texlive`); the prompt asks for your approval before any pull.

## 10. Open placeholders

Affiliations of the three authors; the corresponding author's e-mail; the data and code statement
and the replication-package URL (title footnote, Appendix F, `arxiv/metadata.md`, `CITATION.cff`); the data
availability statement; acknowledgments, funding and conflicts; the AI-use statement (suggested wording in the
paper, to confirm); the license and the arXiv identifier (`CITATION.cff`); the title choice (§3).

## 11. Spend, look-ahead, deviations, STOPs, owner decisions

- **Spend:** $0; cumulative $15.73. No FMP request, no Kaggle run.
- **Look-ahead self-check:** NA-16 makes no decision and reads no data: its inputs are NA-14's committed keys,
  tables and figures, the pre-registration and the REPORTs.
- **Deviations from the PREREG:** none. The NA-14 generator changes are listed in the decisions file.
- **STOP conditions:** none fired (no spend, no lock read, no frozen file changed; the freeze hash is unchanged).
- **Owner decisions:**
  1. The title (working title or one of the two alternatives). *Recommendation:* the working title.
  2. A final pdflatex check in a TeX Live container before submission (pulls an image of several GB).
     *Recommendation:* yes, once, with the bundle described in `arxiv/metadata.md`.
  3. The AI-use statement's wording. *Recommendation:* keep a short statement; many venues ask for one.
  4. Whether to name the news vendor in the data statement. *Recommendation:* decide with the license terms.

## 12. Files and `make verify`

- **Code (new):** `src/newsaction/paper/{__init__,numbers,build,contract}.py`; `tests/test_paper_text.py`.
  **Changed:** `src/newsaction/io.py` (`COMMITTED_ROOTS`), `src/newsaction/figures/{latex,tables,paper,
  fig5_explaining_moves}.py`, `tests/test_figures_{tables,exploratory}.py`, `Makefile` (`paper-text`, `paper-pdf`),
  `.gitignore` (the build log).
- **Manuscript:** `paper/main.tex`, `paper/sections/*.tex` (14 files), `paper/references.bib`,
  `paper/numbers.yaml`, `paper/allowlist.yaml`, `paper/generated/{numbers.tex,main.bbl}`; `arxiv/abstract.txt`,
  `arxiv/metadata.md`; `CITATION.cff`; `artifacts/NA-16/paper.pdf`.
- **NA-14 artifacts regenerated:** `digests.json`, `captions.{yaml,md}`, `inputs/prereg_deviations.yaml`, Figure 5,
  `tables/{keys,index,latex}.json`, `t30` and `t34` (CSV and LaTeX), the LaTeX of the tables carrying the shared
  notes, `paper_preview.{tex,pdf}`.
- **Docs:** `docs/DATA_CONTRACT.md` (NA-14 section regenerated, NA-16 section new), `docs/REPLICATION.md` (two CSV
  digests; the manuscript's build), `docs/decisions/NA-16.md`, this REPORT.

```
ruff check src tests scripts      All checks passed!
ruff format --check               323 files already formatted
mypy --strict src/                Success: no issues found in 183 source files
pytest -q -m "not network"         2208 passed, 3 skipped, 2 xfailed in 272.28s
manifest                          487 artifacts, 10 inputs checked: OK
ledgers                           OK (trials.jsonl=1620, test_access.jsonl=29)
peak RSS                          about 8.0 GB
```

## 13. Operator changes after the session (2026-10-29)

- **Figures 1 and 2 redrawn** in NA-14's generator (`figures/fig1_validation_test.py`, `fig2_priced_at_open.py`):
  the val-B and test points (Figure 1) and the overnight and after-the-open points (Figure 2) were offset above
  and below each model's row, so the dots did not line up with the labels. Each quantity now has its own panel,
  with one dot per model exactly on its row and one shared scale: Figure 1 (a) val-B, (b) test, now full width;
  Figure 2 (a) overnight, (b) after the open, (c) H1. The plotted numbers are unchanged; only the CSVs' `panel`
  column changed (Figure 1: val-B a, test b; Figure 2: z_on a, z_id b, H1 c). Captions in
  `artifacts/NA-14/captions.yaml` and the manuscript no longer say "hollow" or "filled".
- **Authors:** Amir Dehkordi, Arman Khaledian and Nariman Khaledian, for now (`paper/main.tex`, `CITATION.cff`,
  `arxiv/metadata.md`).
- **Findability:** keywords widened (LLMs, stock return prediction, data contamination, backtest overfitting,
  deflated Sharpe ratio, overnight returns, calibration) in the paper, the PDF metadata, `arxiv/metadata.md` and
  `CITATION.cff`; the abstract now says "predict", "non-generative language models" and "look-ahead bias in
  backtests of large language models (LLMs)" (227 words, 1,466 characters). No number or claim changed.
- Rebuilt: `make paper` (all digests equal after `--write-digests`), `figures.contract`, the two figure-CSV
  digests in `docs/REPLICATION.md`, `make paper-preview`, `make paper-pdf` (0 errors, 0 overfull, 41 pages),
  `paper.contract`; `make verify` exit 0 (2,208 passed, 3 skipped, 2 xfailed; manifest and ledgers OK).
