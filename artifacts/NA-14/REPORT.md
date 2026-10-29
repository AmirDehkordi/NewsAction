# NA-14 REPORT — paper figures, tables and replication package

Date: 2026-10-29 · Branch `feat/NA-14-paper-figures` (main checkout, cut from main @ b10b4f1) · Decisions:
`docs/decisions/NA-14.md` · PREREG: unchanged · Spend: $0 (no API call, no Kaggle run, no FMP request; nothing
reads `newsaction.lock`).

**Bottom line.**
- **Eight figures and seven appendix figures**, each a vector PDF and a 300-dpi PNG drawn only from its own CSV,
  at one or two column widths, no text below 7 pt, in the dataviz skill's validated palette.
- **4,558 plotted values trace to their upstream cells** of NA-03, NA-06, NA-07, NA-11, NA-12 and NA-13 (or the
  NA-14 tables that copy them), intervals included (`tests/test_figures_trace.py`).
- **38 paper tables** (CSV; LaTeX for 30) with 39,867 keys, and **15 captions** citing **153 numbers**, every one
  checked against its table cell (`tests/test_figures_captions.py`).
- **`make paper`** rebuilds all of it offline in about 7 seconds and reproduces every digest (87 text outputs
  enforced, 30 PDF/PNG files reported equal); it writes no ledger and imports neither the decision-model client
  nor the lock.
- **Captions state the results as found.** Every primary hypothesis is "not supported" for Laya-Fin under §1.3.
  Prices move part of the way to V by the close of day t and then partly fade, the gap's half-life is never
  reached within t+20, there is no small-move underreaction, and no book survives costs and the deflated Sharpe.
  The operator's summary needed one correction: Laya-Fin's tiny RG books and the anchor's gated S-D2 J at t+20 are
  positive net at 10 bp (owner decision 1).

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 style | done | `src/newsaction/figures/style.py` (palette, inks, sizes, fonts, interval helpers, byte-stable export) |
| S2 figures 1–8 | done | `figures/fig1_hero_car.py` … `fig8_explain_move.py`; data `figures/data.py`, provenance `figures/sources.py`, drawing `figures/render.py`; `artifacts/NA-14/figures/fig1…fig8.{csv,pdf,png}` |
| S2 appendix | done | `figures/appendix.py`: A1 reliability, A2 encoding, A3 masking / identifiability, A4 ablations (news removed, shuffled), A5 robustness forest, A6 and A7 exploratory (post hoc) |
| S3 tables | done | `figures/tables.py`; `artifacts/NA-14/tables/` (38 CSV, 30 LaTeX, `keys.json`, `index.json`, `paper_tables.tex`) |
| S4 captions | done | `artifacts/NA-14/captions.yaml` (templates), `captions.md` (rendered); `figures/captions.py`, `figures/keys.py` |
| S5 replication | done | `make paper` (`figures/paper.py`), `artifacts/NA-14/digests.json`, `docs/REPLICATION.md`, `docs/paper_outline.md`; contract `figures/contract.py` |
| Operator item 7 (PNG paths of Figures 1 and 7) | done | reported as soon as they existed, before the other figures |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 `make paper` offline, digests | `make paper`: "outputs": "all equal" (87), "figures": "all equal" (30), "ledgers_unchanged": true, "forbidden_imports": []. `tests/test_figures_paper.py` runs the full build in a scratch copy (NA-03 … NA-13 artifacts and the ledgers linked) and checks every output byte against the committed one, every `ledgers/*.jsonl` byte-identical, a changed input stopping the run and a ledger write failing it | PASS |
| AC2 captions match tables | `python -m newsaction.figures.captions`: 0 problems; 153 citations, each equal to its table cell and, for an NA-12 copy, to NA-12's CSV; no uncited number (`tests/test_figures_captions.py`, 22 tests, three of them planted failures) | PASS |
| AC3 CSV, palette, fonts | each of the 15 figures has its CSV; `tests/test_figures_style.py`: width 3.3 or 6.9 in, smallest text ≥ 7 pt in every figure, the palette equals the reference instance, figure modules read no file, drawing reads only the figure's CSV, a rebuild writes the committed PDF and PNG bytes. Palette validation in `docs/decisions/NA-14.md` item 16 | PASS |
| AC4 no new analysis | `tests/test_figures_trace.py`: all 4,558 rows of the 15 figure CSVs equal their upstream cells (values and intervals), each CSV equals a fresh build, and a changed value, interval or key is caught; NA-12 copies byte-identical, keyed copies equal their sources, flattened JSON copied (`tests/test_figures_tables.py`). The one recomputation, t26, reproduces numbers NA-13's REPORT states (§3) | PASS |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal in `src/`; Laya's date lives in `artifacts/NA-14/inputs/operator.yaml`); `ledgers/test_access.jsonl` still 29 lines | PASS |
| GAC4 | no API call; `ledgers/spend.jsonl` unchanged (sha256 before and after every run); NA-14 spend $0 | PASS |
| GAC5 | `docs/DATA_CONTRACT.md` NA-14 section, 120 entries with sha256 equal to `work/MANIFEST.json`; `python -m newsaction.io check`: 406 artifacts OK | PASS |

**Mutations (7, all RED).** A session script applied each, cleared `__pycache__`, ran the guard's test and restored
the file (sha256 checked; `make paper` still "all equal" afterwards): the trace accepts every row; the caption
check skips bare numbers; it skips the value comparison; the paper run ignores a ledger change; it ignores a changed
input; the 7 pt floor is off; the vendor-label note is dropped from the LaTeX.

## 3. What the figures show (as found)

- **Figure 1 (convergence, A1).** d1-ultra's top V decile (mean V 0.77) stands at +0.45 at the open, +0.52 at the
  close and +0.36 at t+20; κ peaks on day t or just after (Laya-Fin 0.36–0.38 from the close to t+2, d1-ultra
  0.59–0.61 at 10:00 and the close) and fades by t+10; the gap's half-life is ∞ (not reached within t+20).
  d1-ultra's "Under" events never catch up (−0.95 → −1.04), its "Over" events give back part of their move
  (+3.16 → +2.82). Laya-Fin's 146 RG events are too few to draw.
- **Figure 2.** Moves with |G| ≥ 3 reverse slightly in every news-strength tercile (Laya-Fin −0.10 / −0.18 /
  −0.15); below 3 the means are small and of both signs, except d1-ultra's strong-news tercile (−0.08 at 0.5–2);
  no small-move underreaction. H2 not supported.
- **Figure 3.** Every IC that is positive on val-B falls on test (Laya-Fin 0.065 → 0.020, d1-ultra 0.097 →
  0.039); the vendor-label baselines lead the test (tags-GBM 0.055) as a possibly look-ahead-contaminated upper
  bound.
- **Figure 4.** Every release (Laya 2026-09-18, the API models 2026-10-12 to 10-16) falls after the sample, which
  ends on 2026-07-31.
- **Figure 5.** The Shapley totals of OOS R² are negative (−0.0017 Laya-Fin); shares are not drawn.
- **Figure 6.** F5 selects 30% of days with material recall 0.435; F6 0.444; rule filters 0.309–0.335.
- **Figure 7.** At 10 bp, S-CONV −1.98, S-D0 −6.03, S-D1 J −9.70, S-D2 J −6.45 (Laya-Fin, annualized). S-CONV
  shares 92% of its positions with the gap fade (99.8% on the same side; return correlation 0.96). Largest DSR
  probability 0.024 with 545 trials.
- **Figure 8.** d1-ultra: ex-ante news 0.0028, ex-post 0.0082, explanation 0.158 of stock-specific variance;
  Laya-Fin's H5 share 0.0025 (q 0.058); θ = −0.06 (p 0.95).

## 4. Deviations

- **PREREG:** none. NA-14 changes no definition, estimate or family; no §15 row (owner decision 4).
- **From the PRD's figure descriptions** (data or "no new analysis" decide; `docs/decisions/NA-14.md` items 5–13):
  Figure 1's bands are ±1.96 event-level SE, not bootstrap; its RG classes are pooled over tiers (the figure data
  have no tier split) and drawn for d1-ultra only; Figure 3 has a second panel because Laya-Fin and the anchor are
  not in NA-06's tournament sample; Figure 5 shows values, not shares, at D2 only; Figure 8 stacks d1-ultra only and
  annotates Roll's step one instead of stacking it.
- **Operator item 3, Figure 7:** "every pre-registered book is negative net at 10 bp" is not what NA-13 found
  (above); the caption states NA-13's result.
- **NA-12 open item (t14 vendor footnote):** resolved in the NA-14 copy of t14 (LaTeX note and † marks); NA-12's
  own artifact is unchanged.

## 5. Spend, look-ahead self-check, STOPs

- **Spend.** NA-14 $0. Cumulative (t22): OpenRouter $15.73 of the $30 cap; Kaggle 25.38 GPU-hours (NA-08 23.38,
  NA-11 2.00); FMP 15,858 of 17,000 requests. `tectonic`, used once to check that the LaTeX compiles, fetched TeX
  fonts from its bundle server; it is not part of `make paper`, and no project data was sent.
- **Look-ahead self-check.** NA-14 makes no decision, so no input has a decision time. Its inputs are committed
  outputs of NA-03 … NA-13 (test-period numbers only from NA-12's and NA-13's post-unblinding artifacts), NA-13's
  registered `work/strategy` positions and books, two configs, the operator's release date and the ledgers (read
  only). Nothing reads `work/snapshot`, the lock, `load_targets` or `build_reactions`; the paper run checks that
  none of those modules is imported.
- **STOP conditions.** Anything needing an API call: no. A lock read: no. None fired.

## 6. Owner decisions

1. **Figure 7 wording.** Your summary said every pre-registered book is negative net at 10 bp. NA-13 found that
   Laya-Fin's four RG books (6 to 12 positions over the test period) and the anchor's gated S-D2 J at t+20 are
   positive net, though none clears the placebo or the deflated Sharpe. *Recommendation:* keep the caption as it
   is (it states NA-13's result).
2. **Laya's release date** (2026-09-18) is yours; no artifact records it. *Recommendation:* keep it in
   `artifacts/NA-14/inputs/operator.yaml` with its source, or point me to a citable source to add.
3. **NA-12's own t14** still lacks the vendor footnote; the paper's copy has it. *Recommendation:* leave NA-12's
   verified artifact unchanged.
4. **A PREREG §15 row for NA-14.** *Recommendation:* none; NA-14 changes nothing pre-registered, and its
   presentation choices are in the decisions file.
5. **Figure 1's "bootstrap bands" and "by tier" RG paths.** Both need event-level data that NA-12 did not store.
   *Recommendation:* accept the SE bands and pooled classes; a tier split would need an NA-12 figure-data addendum.

## 7. Files

- **Code (new).** `src/newsaction/figures/`: `__init__`, `style`, `sources`, `data`, `render`, `fig1_hero_car`,
  `fig2_drift_vs_move`, `fig3_tournament`, `fig4_monthly_ic`, `fig5_shapley`, `fig6_filters`, `fig7_strategies`,
  `fig8_explain_move`, `appendix`, `keys`, `tables`, `captions`, `paper`, `contract`.
- **Tests (new, 116).** `tests/test_figures_trace.py`, `test_figures_captions.py`, `test_figures_keys.py`,
  `test_figures_style.py`, `test_figures_tables.py`, `test_figures_paper.py`.
- **Artifacts.** `artifacts/NA-14/figures/` (15 × CSV, PDF, PNG), `tables/` (38 CSV, 30 TeX, `keys.json`,
  `index.json`, `paper_tables.tex`), `captions.yaml`, `captions.md`, `digests.json`, `inputs/operator.yaml`.
- **Docs.** `docs/REPLICATION.md`, `docs/paper_outline.md`, `docs/decisions/NA-14.md`, `docs/DATA_CONTRACT.md`
  (NA-14 section, 120 entries). **Makefile:** `paper` target.
- **Ledgers:** unchanged.

## 8. Figure files

`artifacts/NA-14/figures/`: `fig1_convergence`, `fig2_drift_vs_move`, `fig3_tournament`, `fig4_monthly_ic`,
`fig5_shapley`, `fig6_filters`, `fig7_strategies`, `fig8_explain_move`, `figA1_reliability`, `figA2_encoding`,
`figA3_identifiability`, `figA4_ablations`, `figA5_robustness`, `figA6_exploratory_d0`,
`figA7_exploratory_ma_cross` (each `.pdf`, `.png`, `.csv`).

## 9. `make verify`

Run on the final commit (53c2fee), with no other NewsAction pytest running and 71% of memory free; exit 0:

```
ruff check src tests scripts       All checks passed!
ruff format --check                298 files already formatted
mypy --strict src/                 Success: no issues found in 166 source files
pytest -q -m "not network"         2076 passed, 3 skipped, 2 xfailed in 373.79s
manifest                           406 artifacts, 10 inputs checked (size+mtime): OK
ledgers                            OK (fmp_requests 31,716, spend 624,248, test_access 29, trials 545 lines)
peak RSS                           6.5 GB (9.6 GB in an earlier run of the same suite)
```
