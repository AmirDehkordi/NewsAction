# NA-14 REPORT — paper figures, tables and replication package

Date: 2026-10-29 (author session, fix pass and revision pass the same day) · Branch `feat/NA-14-paper-figures`
(main checkout, cut from main @ b10b4f1) · Decisions: `docs/decisions/NA-14.md` · PREREG: unchanged · Spend: $0 (no
API call, no Kaggle run, no FMP request; nothing reads `newsaction.lock`).

**Bottom line.**
- **Seven main figures and fifteen appendix figures** for an arXiv LaTeX preprint: drawn at 6.5 in or 3.15 in and
  placed at 100%, in Computer Modern at 8 pt (nothing below 7 pt), vector PDF and 300-dpi PNG, each from its own
  CSV, in the dataviz skill's validated palette with one colour per model.
- **Six main tables and thirty-four appendix tables in LaTeX** (booktabs, threeparttable notes, siunitx S columns,
  captions above with a takeaway), every number a cited cell of `tables/keys.json`, plus a one-page summary of the
  63 pre-registration deviations.
- **`artifacts/NA-14/paper_preview.tex`** sets every figure and table in outline order with its caption;
  `make paper-preview` compiles it with tectonic: no error, no overfull box, every font embedded, 81 pages
  (`artifacts/NA-14/paper_preview.pdf`, sha256 `74aff6d22c8489130a91cc8305b478c034cdbd8cebbe6cb4d7ef2f8ce3a88d7a`,
  reported, not enforced).
- **Every plotted value traces to its upstream cell** (`tests/test_figures_trace.py`, all 22 figure CSVs); the two
  aggregations of stored files (placebo Sharpe quantiles, break-even costs) and the Wilson intervals are recomputed
  by tests.
- **Exploratory material appears only in the appendix:** Figures A6, A13, A14, A15 and the tables t17, t24, t25,
  t31. No main figure and no main table cites exploratory material (`figures.guard`, which `make paper` enforces;
  `tests/test_figures_exploratory.py`, which plants a citation in a caption, a table and a figure's data). This
  fixes operator check 5e of the first verification.
- **`make paper`** rebuilds all of it offline in about 12 seconds and reproduces every digest (110 text outputs
  enforced, 44 PDF/PNG files reported equal); it writes no ledger and imports neither the decision-model client
  nor the lock.
- **Captions state the results as found**: every primary hypothesis is "not supported" for Laya-Fin; the API models
  price the news at the open; prices move part of the way to $V$ on day $t$ and then partly fade, with the gap's
  half-life never reached within $t+20$; there is no small-move underreaction; no book survives costs and the
  deflated Sharpe.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 style | done (revised) | `src/newsaction/figures/style.py`: widths, Computer Modern, marks, palette and ordinal ramps, plain-text guard, byte-stable export |
| S2 main figures | done (redesigned) | `figures/fig1_validation_test.py` … `fig7_memorisation.py`; data `figures/data.py`, provenance `figures/sources.py`, drawing `figures/render.py` |
| S2 appendix | done (redesigned) | `figures/appendix.py`: A1–A15 |
| S3 tables | done (LaTeX rebuilt) | `figures/tables.py` (CSV, keys, index), `figures/latex.py` (the LaTeX and `latex.json`) |
| S4 captions | done (rewritten) | `artifacts/NA-14/captions.yaml`, `captions.md`; `figures/captions.py`, `figures/keys.py` |
| S5 replication | done | `make paper` (`figures/paper.py`), `make paper-preview` (`figures/preview.py`), `digests.json`, `docs/REPLICATION.md`, `docs/paper_outline.md`, contract `figures/contract.py` |
| Operator check 5e | done | `figures/guard.py`, `tests/test_figures_exploratory.py` |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 `make paper` offline, digests | `make paper`: "outputs": "all equal" (110), "figures": "all equal" (44), "ledgers_unchanged": true, "forbidden_imports": []; `tests/test_figures_paper.py` rebuilds in a scratch copy and checks every byte, the ledgers, a changed input and a ledger write | PASS |
| AC2 captions match tables | `python -m newsaction.figures.captions`: 0 problems; every cited number equals its cell; no uncited number in text or math (`tests/test_figures_captions.py`, planted failures included) | PASS |
| AC3 CSV, palette, fonts | each of the 22 figures has its CSV; `tests/test_figures_style.py`: width 6.5 or 3.15 in, text ≥ 7 pt, Computer Modern, no unprintable text, the reference palette and the validated ramps, figure modules read no file, a rebuild writes the committed bytes | PASS |
| AC4 no new analysis | `tests/test_figures_trace.py`: every row of the 22 figure CSVs equals its upstream cell (values and intervals); t33 and t35 recomputed from NA-13's stored files and equal to NA-13's REPORT §6–§7; Wilson intervals from stored counts; NA-12 copies byte-identical | PASS |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty | PASS |
| GAC3 | `tests/test_blinding.py` passes (no test-year literal in `src/`); `ledgers/test_access.jsonl` still 29 lines | PASS |
| GAC4 | no API call; every `ledgers/*.jsonl` sha256 unchanged; NA-14 spend $0 | PASS |
| GAC5 | `docs/DATA_CONTRACT.md` NA-14 section regenerated (158 entries) with sha256 equal to `work/MANIFEST.json` and the files; stale entries of renamed files dropped; `python -m newsaction.io check`: OK | PASS |

## 3. What the figures show (as found)

- **Figure 1 (validation against test).** Every IC that is positive on val-B falls on test: Laya-Fin 0.065 → 0.020,
  d1-ultra 0.097 → 0.039; the clean benchmarks are about zero; the vendor-label baselines (†) lead on test as a
  possibly look-ahead-contaminated upper bound (tags-GBM 0.055).
- **Figure 2 (priced at the open).** The API models' IC is all overnight (d1-ultra 0.074 with $z_{on}$, −0.001 with
  $z_{id}$; H1 0.075, p < 0.001); Laya-Fin's is small either way (H1 and H1b not supported, Holm p 0.853), although
  on val-B its IC with $z_{id}$ had been 0.054 (t 2.89).
- **Figure 3 (convergence).** d1-ultra's top decile (mean $V$ 0.77) stands at +0.45 at the open, +0.52 at the close
  and +0.36 at $t+20$; $\kappa_h$ peaks on day $t$ or just after, far from one (Laya-Fin 0.36 at the close and
  0.38 at $t+2$, d1-ultra 0.61 at 10:00), and fades by $t+10$; the half-life is not reached within $t+20$.
- **Figure 4 (over- and under-reaction).** d1-ultra's Under events never catch up (−0.95 → −1.04), its Over events
  give back part of their move (+3.16 → +2.82); moves with $|G| \geq 3$ reverse slightly in every news-strength
  tercile of $|V|$; there is no small-move underreaction; H2 not supported.
- **Figure 5 (explaining moves).** Laya-Fin's same-day news explains 0.25% of the stock-specific variance (H5,
  q 0.058), d1-ultra's 0.82%; reading the move explains 15.8% (37.5% on event days).
- **Figure 6 (strategies).** Gross, every main book lies inside its placebo range; net of 10 bp every one is
  negative (S-CONV −1.98); S-CONV shares 92% of its positions with the gap fade (correlation 0.96); the largest
  DSR probability is 0.024 with 545 trials.
- **Figure 7 (memorisation).** The API models name the masked company in 62% to 74% of states against a matched
  baseline of 28%; Laya zero-shot in 32%; every model was released after the sample.

## 4. Deviations

- **PREREG:** none. NA-14 changes no definition, estimate or family; no §15 row (owner decision 4).
- **From the PRD's figure descriptions** (data or "no new analysis" decide; `docs/decisions/NA-14.md` items 12,
  14, 18–21): SE bands, not bootstrap bands; RG classes pooled over tiers and drawn for d1-ultra only; Shapley
  values, not shares; the news-strength terciles of Figure 4 are on $|V|$ (NA-12's `a2_v`), not the PRD's $|\hat N|$;
  the API models' val-B ICs with $z_{on}$ and $z_{id}$ are "not computed" in Table 2.
- **From the operator's revision list:** Figures 5–7 are numbered in the order the paper shows them (explaining
  moves, strategies, memorisation), since the outline puts §5 explaining moves before §6 strategies, as the tables
  do (decision 7); Table 1 moves the tests' statements to its notes and Table 6 leaves out the position counts, to
  fit 6.5 in (decision 13); long tables set their notes after the table, not with threeparttablex (decision 13).
- **NA-12 open item (t14 vendor footnote):** resolved in the paper's tables (†); NA-12's own artifact unchanged.

## 5. Spend, look-ahead self-check, STOPs

- **Spend.** NA-14 $0. Cumulative (t22): OpenRouter $15.73 of the $30 cap; Kaggle 25.38 GPU-hours (NA-08 23.38,
  NA-11 2.00); FMP 15,858 of 17,000 requests. `tectonic` compiles the preview from its cached TeX bundle; no project
  data is sent anywhere.
- **Look-ahead self-check.** NA-14 makes no decision, so no input has a decision time. Its inputs are committed
  outputs of NA-03 … NA-13 (test-period numbers only from NA-12's and NA-13's post-unblinding artifacts), NA-11's
  pre-freeze val-B run, NA-13's registered positions, books and placebo books, PREREG §15, two configs, the
  operator's inputs and the ledgers (read only). Nothing reads `work/snapshot`, the lock, `load_targets` or
  `build_reactions`; the paper run checks that none of those modules is imported.
- **STOP conditions.** Anything needing an API call: no. A lock read: no. None fired.

## 6. Owner decisions

All five were decided on 2026-10-29 as recommended (operator, revision pass item F; `docs/decisions/NA-14.md`).

1. **Figure 6's wording** (formerly Figure 7) stays: it states NA-13's result, that Laya-Fin's RG books (6 to 12
   positions) and the anchor's gated S-D2 J at $t+20$ are positive net at 10 bp and none clears the placebo or the
   deflated Sharpe.
2. **Laya's release date** (2026-09-18) stays in `artifacts/NA-14/inputs/operator.yaml`, with the source "operator,
   from Convai's Laya release (weights at huggingface.co/convaiinnovations/laya)".
3. **NA-12's own t14** stays unchanged; the paper's table carries the †.
4. **A PREREG §15 row for NA-14:** there is none.
5. **SE bands and pooled classes:** kept; the captions say "SE bands" and "pooled over the tiers".

## 7. Files

- **Code.** `src/newsaction/figures/`: `__init__`, `style`, `sources`, `data`, `render`, `fig1_validation_test`,
  `fig2_priced_at_open`, `fig3_convergence`, `fig4_over_under`, `fig5_explaining_moves`, `fig6_strategies`,
  `fig7_memorisation`, `appendix`, `keys`, `tables`, `latex`, `preview`, `guard`, `captions`, `paper`, `contract`.
  Removed: `fig1_hero_car`, `fig2_drift_vs_move`, `fig3_tournament`, `fig4_monthly_ic`, `fig5_shapley`,
  `fig6_filters`, `fig7_strategies`, `fig8_explain_move`. **Makefile:** `paper`, `paper-preview`.
- **Tests.** `tests/test_figures_trace.py`, `test_figures_captions.py`, `test_figures_keys.py`,
  `test_figures_style.py`, `test_figures_tables.py`, `test_figures_paper.py`, `test_figures_exploratory.py`,
  `test_figures_preview.py` (new).
- **Artifacts.** `artifacts/NA-14/figures/` (22 × CSV, PDF, PNG), `tables/` (43 CSV, 40 LaTeX, `keys.json`,
  `index.json`, `latex.json`), `captions.yaml`, `captions.md`, `paper_preview.tex`, `paper_preview.pdf`,
  `digests.json`, `inputs/operator.yaml`, `inputs/prereg_deviations.yaml`.
- **Docs.** `docs/REPLICATION.md`, `docs/paper_outline.md`, `docs/decisions/NA-14.md`, `docs/DATA_CONTRACT.md`
  (NA-14 section, 158 entries).
- **Ledgers:** unchanged.

## 8. Figure and table files

Main: `fig1_validation_test`, `fig2_priced_at_open`, `fig3_convergence`, `fig4_over_under`,
`fig5_explaining_moves`, `fig6_strategies`, `fig7_memorisation`; tables `tab1_primary`, `tab2_ic_by_target`,
`tab3_over_under`, `tab4_convergence`, `tab5_explaining_moves`, `tab6_strategies`. Appendix: `figA1_tournament`,
`figA2_filters`, `figA3_encoding`, `figA4_reliability`, `figA5_robustness`, `figA6_monthly_ic`,
`figA7_convergence_detail`, `figA8_drift_laya_fin`, `figA9_shapley`, `figA10_ablations`, `figA11_persistence`,
`figA12_strategy_paths`, `figA13_probes`, `figA14_exploratory_d0`, `figA15_exploratory_ma_cross`; the appendix
tables are the `tN_*.tex` files (`docs/paper_outline.md` maps all of them).

## 9. `make verify`

Run on the final tree, with no other NewsAction pytest running; exit 0:

```
ruff check: All checks passed!
ruff format --check: 302 files already formatted
mypy --strict src/: Success: no issues found in 168 source files
pytest -q -m "not network": 2125 passed, 3 skipped, 2 xfailed in 241.55s
newsaction.io check: manifest: 444 artifacts, 10 inputs checked (size+mtime); manifest: OK
newsaction.ledger check: ledgers: OK fmp_requests.jsonl=31716, spend.jsonl=624248, test_access.jsonl=29, trials.jsonl=545
```

## 10. Revision pass (operator, 2026-10-29)

The first verification (at 5cccde1) passed AC1–AC4 and GAC1–GAC5 and failed operator check 5e. An interrupted fix
pass had left uncommitted edits (the 5e fix, the outline mapping, the |V| note); the revision pass kept those that
still apply and replaced the figures, the LaTeX and the captions.

### 10.1 Main and appendix mapping

| Was (5cccde1) | Now | Where |
|---|---|---|
| Fig 3 (b) val-B → test | Figure 1, a grouped dumbbell (half width) | main §1 |
| — (t3, t1b) | Figure 2, priced at the open | main §3 |
| Fig 1 (a–c) convergence | Figure 3 (d1-ultra's extreme deciles; $\kappa_h$); every decile and the anchor in A7 | main §4; A7 |
| Fig 1 (d) RG classes; Fig 2 drift | Figure 4 (d1-ultra's classes; drift by $|G|$ per tercile); Laya-Fin's drift in A8 | main §4; A8 |
| Fig 8 (a, b) ladder | Figure 5, news steps on their own scale | main §5 |
| Fig 7 (a–d) books | Figure 6 (gross and net Sharpe against the placebo; S-CONV and the gap fade); other books and tiers in A12 | main §6; A12 |
| A3 (a) company identification | Figure 7 with Wilson intervals (half width) | main §7 |
| Fig 3 (a) tournament | A1, rows sorted by IC with cost beside | appendix |
| Fig 6 filters | A2 | appendix |
| A2 encoding | A3 | appendix |
| A1 reliability | A4 | appendix |
| A5 robustness | A5 | appendix |
| Fig 4 monthly IC | A6, with ±1 implied SE bands (exploratory) | appendix |
| Fig 5 Shapley | A9, one compact dot plot | appendix |
| A4 ablations | A10 | appendix |
| Fig 8 (c) persistence | A11 | appendix |
| A3 (b, c) probes | A13 (exploratory) | appendix |
| A6, A7 | A14, A15 (exploratory, post hoc) | appendix |
| t1, t3 + t14 + t32, t2, t6 + t7, t10 + t4, t20 + t35 | Tables 1–6 (`tab1` … `tab6`) | main §3–§6 |
| every other LaTeX table | an appendix table per CSV, plus t31–t35 | appendix |

### 10.2 Changes per figure

- **All figures:** Computer Modern 8 pt, 6.5 / 3.15 in, notation as math, short panel titles, no sentence in a plot
  area, thin intervals and small markers, horizontal gridlines only, one colour per model, the anchor out of the
  main set, footnotes and tags moved to the captions.
- **Figure 1:** a new dumbbell grouped by kind (trained, zero-shot, API, baselines), † on the vendor labels.
- **Figure 2:** new; IC with $z_{on}$ and $z_{id}$ per model, and H1 with its bootstrap interval.
- **Figure 3:** d1-ultra's top and bottom deciles only, with dashed targets labelled "mean $V$"; $\kappa_h$ of
  Laya-Fin and d1-ultra with the line at 1 and "half-life: not reached within $t+20$"; axes say "not to scale".
- **Figure 4:** the classes and terciles in d1-ultra's validated orange ramp; each class labelled with its mean
  $V$; the drift with thin 95% intervals and a legend "news strength (tercile of $|V|$)".
- **Figure 5:** the news steps in their own panel and scale (percent); the explanation step by cut in another.
- **Figure 6:** gross and net Sharpe with each book's placebo 5th–95th range (t33); the cumulative path with the
  placebo band.
- **Figure 7:** Wilson 95% intervals from the stored shares and valid answers; the matched baseline and the screen
  bar as reference lines.
- **Appendix:** A1 sorted rows (no overlapping labels); A2 a legend instead of colliding end labels; A6 exploratory
  ±1 SE bands; A7 sparse event-time labels; A9 pooled dot plot; the rest restyled.

### 10.3 Changes per table

- **New main tables** (`tab1_primary` … `tab6_strategies`), as decided in item 13; T2's val-B columns use t32,
  T6's break-even column uses t35.
- **Appendix tables:** every LaTeX table rebuilt with human headers, model names as in the figures, siunitx
  alignment, threeparttable notes (long tables: notes after), the †/‡/anchor/API notes, captions above with a
  takeaway and labels `tab:a-…`. t11 and t20 leave out their exploratory rows and point to t31, t25 and A15.
  t1's LaTeX is now Table 1 (`tab1_primary.tex`); `paper_tables.tex` is replaced by `paper_preview.tex`.
- **New CSV tables (documented additions):** t31 (the A3.5 market row; fix pass), t32 (val-B ICs by target,
  NA-11), t33 (placebo Sharpe quantiles, NA-13), t34 (the 63 deviations, one line each), t35 (break-even costs).
  Every other CSV is byte-identical to 5cccde1 except t21, whose Laya source text is owner decision 2;
  `keys.json` gains only the new tables' keys and that one changed cell.

### 10.4 Files whose digest changed (against 5cccde1's `digests.json`)

- **Inputs:** changed `captions.yaml`, `inputs/operator.yaml`; added `inputs/prereg_deviations.yaml`,
  `docs/PREREG.md`, `artifacts/NA-11/spec_smoke_val_b.json`, `work/strategy/placebo_test.parquet` (33 → 37).
- **Text outputs (87 → 110):** removed the 14 old figure CSVs (all but `figA5_robustness.csv`, unchanged),
  `tables/t1_primary.tex` and `tables/paper_tables.tex`; added the 21 new figure CSVs, `paper_preview.tex`,
  `tables/latex.json`, the six `tab*.tex`, and t31–t35 (CSV and LaTeX); changed `captions.md`, `tables/index.json`,
  `tables/keys.json`, `tables/t21_release_dates.csv` and every remaining `tables/t*.tex` (29 files).
- **Figures (30 → 44):** every PDF and PNG is new or redrawn; `figA5_robustness.{pdf,png}` changed in place.
- **Not enforced:** `paper_preview.pdf` (sha256 above).
