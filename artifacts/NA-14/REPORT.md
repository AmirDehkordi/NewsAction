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
  `make paper-preview` compiles it with tectonic: no error, no overfull box, every font embedded, 82 pages
  (`artifacts/NA-14/paper_preview.pdf`, sha256 `e09b89df0c24812ae93ba99583abe68ac03fc4b7514d26374416b257c065cb15`,
  reported, not enforced; §12).
- **Every plotted value traces to its upstream cell** (`tests/test_figures_trace.py`, all 22 figure CSVs); the two
  aggregations of stored files (placebo Sharpe quantiles, break-even costs) and the Wilson intervals are recomputed
  by tests.
- **Exploratory material appears only in the appendix:** Figures A6, A13, A14, A15 and the tables t17, t24, t25,
  t31. No main figure and no main table cites exploratory material (`figures.guard`, which `make paper` enforces;
  `tests/test_figures_exploratory.py`, which plants a citation in a caption, a table and a figure's data). This
  fixes operator check 5e of the first verification; the fix pass of §12 closes the routes the re-verification
  found open (t35's MA-cross row, upstream rows in a figure's data).
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

## 11. Polish pass (operator, 2026-10-29, on top of 49a2fbe)

Three charts the operator liked at 5cccde1 are back in their layout and the new style; panels that show one quantity
on one scale share their axis; no label touches a mark; the tables are polished. No API call, no Kaggle run,
nothing touches `newsaction.lock`; the ledgers are byte-identical; no new analysis (every figure row traces to its
upstream cell, every caption and table number is a cell of `tables/keys.json`). Decisions 29–38 in
`docs/decisions/NA-14.md`.

### 11.1 The restored charts

- **Figure 5, explaining moves.** (a) is the old Figure 8 (a): d1-ultra's out-of-sample $R^2$ of $z_{cc}$ as stacked
  bars for all days, event days, Top 100, 101–250 and 251–500, the steps ex-ante news (D0), + same-day news and
  + explanation stacked in the legend's order, in the muted component palette, each total (15.8, 37.5, 19.9, 15.6,
  14.0) above its bootstrap whisker. No text over the bars: the news steps, a point or two tall, have their values
  beside the bar after a swatch of their colour, and Roll's market and sector $R^2$ (25.3%) is in the caption.
  (b) is the former (a), the news steps of Laya-Fin and d1-ultra on their own scale. The former (b) is dropped.
- **Figure 7, memorisation.** The old A3 (a): sorted horizontal bars of the share of masked states whose company was
  identified, the value ("74%") at each bar's end past its Wilson whisker, a solid line at the 28% matched baseline
  and a dashed one at the 40% screening threshold (renamed from "screen bar"), both labelled above the axis; the
  production comparators d1-ultra, span-02‡ and drex-v2.0 in the comparator colour, the other API models and Laya
  zero-shot in grey.
- **Appendix A9, Shapley.** The old six panels (a)–(f): rows out-of-sample $R^2$ and IC, columns Laya-Fin, d1-ultra
  and "anchor, uninformative"; grouped $R$, $N$, $J$ bars for all, Top 100, 101–250 and 251–500 with the total
  $R + N + J$ as a diamond; values in units of $10^{-3}$; one y-axis per row, so the zero lines line up; the muted
  component palette (no saturated green) and one legend at the top. The caption now says that every $R^2$ total is
  negative in every tier and that the IC totals have both signs (−0.029 to 0.013).
- **The muted component palette** (new): the reference hues of slots 7, 5 and 4 at chroma 0.11 and lightness
  0.46 / 0.64 / 0.76; the validator passes them on all pairs against white (CVD ΔE 15.5, normal vision 18.5).

### 11.2 Axes, alignment and details

- **Shared axes:** A12 (a, b) and (d)–(f), with (c) on its own scale (the caption says so); A7 (a, b); A9 by row;
  A13 (a, b); A5 (a) and (d), both H1; Figure 2 (a, b) on one IC range. Constrained layout aligns zero lines, panel
  tops and bottoms across a row and the x-axes down a column (checked on the axes' positions). Where panels of one
  quantity keep their own scales the caption says so: Figure 5 (b), Figure 6 (b), A5 (b, c), A14 (a, b), A15 (a, b).
- **A7:** every rung labelled as in Figure 3; the three panels in one row could not hold the labels, so (c) moved to
  a row of its own.
- **A6:** the y-range is the data's with a margin; the after-sample area is gone and the release dates are in the
  caption; every label is horizontal.
- **Figure 6:** (b) runs to −15.5, so S-D1's placebo range (from −14.04) is not clipped; one legend above the
  panels replaces (c)'s, which sat on d1-ultra's path.
- **Figure 4 (a):** Under, Fair and Over in d1-ultra's re-stepped ramp (normal-vision ΔE 19.2 between neighbours,
  was 7.7 between Under and Fair), and the dashed mean-$V$ lines dotted, short-dashed and long-dashed.
- **A2:** F6 mid-grey beside F5 black. **A14:** a small legend under each panel.
- **No label on a mark:** `style.overlaps`, enforced by `render.check`, finds no text or legend touching a line, a
  whisker, a marker, a bar, a spine, another label or a gridline without a knockout, in any of the 22 figures (2 s
  for all). It caught Figure 3's "$\kappa_h = 1$" and top "mean $V$" labels on their dashed lines, now moved clear,
  and Figure 6 (c)'s legend. Labels inside a plot and legends sit on a knockout of the surface.

### 11.3 Tables

- **Table 2:** the API models' val-B $z_{on}$ and $z_{id}$ cells (and their $t$ rows) show "—", as the note says.
- **Table 5:** "<0.001" sits on the decimal column with no space after "<"; the share knowable before the open sits
  in the $R^2$ columns with their two decimals (53.17, 34.78, 35.63), aligned with the rows above.
- **Every table:** an empty cell shows "—" and the notes say what it means (`latex.render` refuses a table
  otherwise); one decimal convention per column, or the reason in the notes (Tables 1, 2, 4, 5); t22's counts are
  whole numbers; text in S columns is in braces, the "<" of a bound included; raw keys left the appendix row labels
  (t16's robustness variants now carry Figure A5's names), and gpt-6-luna is named as in the figures; t9 is
  portrait, since its 36 rows overflowed a landscape page.
- **Each table on its own:** a standalone article with the preview's preamble, `tectonic --keep-logs`, then
  `sips -s format png` (and a 3× QuickLook render to check the alignment): 40 tables, no error, no overfull box, no
  float taller than the page; each looked at.

### 11.4 Checks

| Check | Result |
|---|---|
| `make paper` | "outputs": "all equal" (110), "figures": "all equal" (44), 37 inputs, "ledgers_unchanged": true, "forbidden_imports": [] |
| captions | `python -m newsaction.figures.captions`: 0 problems |
| trace, 5e guard | `tests/test_figures_trace.py` (22 figure CSVs) and `tests/test_figures_exploratory.py` pass; `figures.guard`: no violation |
| new tests | the overlap guard on every figure and a planted overlap; the palette's derivation; the restored layouts and shared axes; empty cells, dash notes and a planted undocumented dash; "<" against its number; Table 5's share; the preview's float and undefined-reference checks |
| `make paper-preview` | `tectonic --keep-logs`; `paper_preview.log`: 0 Overfull, 0 Underfull, 0 undefined references, 0 errors, 0 LaTeX warnings; 81 pages; 65 fonts, all embedded; PDF sha256 `0e6a1f493d26f6bda44a9f562f45ccb5e040c5409f0319d326751d77b7eb5d49` (reported, not enforced) |
| `make verify` | exit 0, with no other NewsAction pytest running: ruff check and format (302 files), mypy --strict (168 files), pytest 2130 passed, 3 skipped, 2 xfailed in 243 s, manifest OK (444 artifacts), ledgers OK (test_access 29, trials 545); peak RSS 9.6 GB. An earlier run failed `test_calendar`'s no-clock-literal guard on a "09:30" label key in `latex.py`; the cutoff labels are now derived by pattern (the LaTeX is byte-identical) |

### 11.5 Files whose digest changed (against 49a2fbe's `digests.json`)

- **Inputs (37):** `captions.yaml`.
- **Text outputs (110, none added or removed; 33 changed):** `captions.md`, `paper_preview.tex`; the figure CSVs
  `fig5_explaining_moves.csv`, `figA6_monthly_ic.csv`, `figA9_shapley.csv`; the LaTeX of the six main tables
  `tab1` … `tab6` and of t1b, t2, t3, t4, t5, t6, t7, t9, t10, t11, t12, t13, t14, t15, t16, t18, t20, t21, t22,
  t23, t25 and t27. No table CSV, `keys.json` or `index.json` changed.
- **Figures (44, reported; 37 changed):** every PDF and PNG except `fig1_validation_test.png`, `figA3_encoding.png`,
  `figA4_reliability.png`, `figA10_ablations.png`, `figA11_persistence.{pdf,png}` and
  `figA15_exploratory_ma_cross.png` (the PDFs of fig1, A3, A4, A10 and A15 differ only by the knockouts, white on
  white).
- **Not enforced:** `paper_preview.pdf` (sha256 above).
- **Other files:** code `figures/style.py`, `data.py`, `render.py`, `fig2_priced_at_open.py` …
  `fig7_memorisation.py`, `appendix.py`, `latex.py`, `preview.py`, `contract.py`; tests `test_figures_style.py`,
  `test_figures_tables.py`, `test_figures_preview.py`; docs `REPLICATION.md` (the three CSV digests, the preview
  checks), `paper_outline.md`, `decisions/NA-14.md`, `DATA_CONTRACT.md` (NA-14 section regenerated, 158 entries);
  `.gitignore` (the preview log).

## 12. Fix pass after the re-verification (operator, 2026-10-29, on top of 1bbc5f9)

The re-verification at 1bbc5f9 passed every check except operator check 5 (appendix LaTeX tables), and found two
routes left open in the 5e guard. This pass changes the LaTeX of 13 tables, marks one more exploratory row in
`index.json`, and extends the guard and its tests. No table CSV, `keys.json` value, figure or caption changes, so
AC1–AC4 hold as before. Decisions 39–44 in `docs/decisions/NA-14.md`.

### 12.1 Check 5: the appendix tables

- **Marks with their notes.** t21's ‡ and t33's † get their notes. The strategy tables (Table 6, t20, t33, t35) carry
  a vendor note about books, not ICs. `latex.render` now refuses a † or ‡ without a note.
- **No key as a label.**
  - t35's rows are named as t20's ("S-CONV, Laya-Fin, D2 $U$, to $t+1$"). Its exploratory MA-cross row leaves its
    LaTeX, which points to Table A33 and Figure A15.
  - t12's mechanism cuts read "own event type (Call A, pre-open news)" and similar. Its two analysis names are
    typeset.
  - t5 reads "low usual coverage". t21 drops "(created)". Vendor sentiment's books no longer repeat its name.
- **Numbers that were missing or mislabelled.**
  - t12 prints the five reading-validity agreements (0.990, 0.572, 0.454, 0.494, 0.552).
  - t4 prints the 95% CI of each test whose uncertainty NA-12 states as a CI, and says why the anchor's H7 has no
    $q$.
  - t3 sets the quintile spread and its $p$ under one header.
  - t9 prints both event counts ($\kappa$ and $\lambda$). t10's "Days" are "Member-days".
- **Captions.**
  - t29: "E1 ranked best in the val-A search but fell short of E3 on val-B, so E3 was kept".
  - t21: "every decision model came out after the sample; only the anchor's checkpoint predates it".
- **No repeated label.**
  - t33 names a universe's model where its events are that model's alone.
  - t15's temperature rows read "…, $e_5$, temperature scaling".
  - t20 is one longtable per period, so every page says "continued (test)" or "continued (val-B)".
  - `latex.render` now refuses a row label repeated within a panel.
- **Fit.** The wider tables fit the text width: t9 at `\footnotesize`, a 4 pt column gap in t9 and t10, and wrapped
  label columns in t12 and t15.

### 12.2 The 5e guard

- t35's `exploratory|ma_cross|fade_no_news|close_t+5` is an exploratory row (`tables.EXPLORATORY_ROWS`,
  `index.json`), so a main caption or table citing it is refused.
- A main figure's data row is refused when it comes from an NA-12 table whose NA-14 copy marks it exploratory, or
  from any upstream file whose key names NA-13's "exploratory" family (the MA-cross path of the Figure 7 data).
- The index test reads keys as well as text. A plant of each route is caught. Removing either new render guard,
  either new guard route or t35's row turns the tests red.

### 12.3 Checks

| Check | Result |
|---|---|
| `make paper` | "outputs": "all equal" (110), "figures": "all equal" (44), 37 inputs, "ledgers_unchanged": true, "forbidden_imports": [] |
| `make paper-preview` | 82 pages; `paper_preview.log`: 0 Overfull, 0 Underfull, 0 undefined references, 0 errors, 0 LaTeX warnings; 65 fonts, all embedded; PDF sha256 `e09b89df0c24812ae93ba99583abe68ac03fc4b7514d26374416b257c065cb15` (reported, not enforced) |
| each changed table on its own | the 13 tables compiled with the preview's preamble, `tectonic --keep-logs`: 0 overfull; each rendered and looked at |
| captions, guard | `python -m newsaction.figures.captions`: 0 problems; `figures.guard`: no violation |
| `make verify` | exit 0, with no other NewsAction pytest running: ruff check and format (302 files), mypy --strict (168 files), pytest 2134 passed, 3 skipped, 2 xfailed in 248 s, manifest OK (444 artifacts), ledgers OK (test_access 29, trials 545); peak RSS 8.0 GB |

### 12.4 Files whose digest changed (against 1bbc5f9's `digests.json`)

- **Text outputs** (110; none added or removed; 15 changed): `tables/index.json`, `tables/latex.json`, and the LaTeX
  of `tab6`, t3, t4, t5, t9, t10, t12, t15, t20, t21, t29, t33 and t35.
- **Figures, inputs:** none.
- **Not enforced:** `paper_preview.pdf`.
- **Other files:**
  - code `figures/latex.py`, `tables.py`, `guard.py`;
  - tests `test_figures_tables.py`, `test_figures_exploratory.py`;
  - docs `paper_outline.md`, `decisions/NA-14.md`, `DATA_CONTRACT.md` (NA-14 section regenerated).

## 13. Negative zeros (operator, 2026-10-29, after the re-check of 54bee19)

The re-check of 54bee19 passed scope, the guard and the gates, and found one item of check 5 open: 17 cells in nine
appendix tables (t10, t13, t15, t16, t17, t18, t19, t20, t33) printed a value that rounds to zero with a minus sign
("−0.000"). The main tables had none.

- `latex.unsigned_zero` drops the sign of any formatted number that rounds to zero, in every fixed-point format and
  in confidence intervals. A value that does not round to zero keeps its sign (−0.0016 prints as −0.002).
- `latex.render` refuses a cell that still shows a negative zero (`latex.NEGATIVE_ZERO`).
- `tests/test_figures_tables.py::test_a_value_that_rounds_to_zero_shows_no_sign` covers the formats, the render
  guard and the committed LaTeX. It fails on 54bee19's LaTeX.
- The rebuild changed the LaTeX of those nine tables only. Every changed line differs only by the dropped sign (17
  cells). No CSV, `keys.json` value, figure or caption changed. `digests.json`, the preview (82 pages, sha256
  `e09b89df…`) and the data contract are regenerated.
- t12 still does not print the CIs it holds for horizon validity and H4 width. They are in its CSV. Placing them
  would need a new column in a landscape table, so the paper cites them in its text instead (operator decision).
