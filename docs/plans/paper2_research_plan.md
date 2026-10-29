# Research plan: Paper 2, the companion to "The Market Reads the News First"

*Written 2026-10-29, after NA-12 to NA-14 (the 2026 test is unblinded and analysed). Status: plan only; nothing is run yet.*
*Repository: `/Users/amir/Research/NewsAction`. Paper 1 is written in NA-16 (prompt in the session notes).*

---

## 1. The idea in one paragraph

Paper 1 asks a finance question: can AI decision models anticipate how prices react to news, or tell when the market has
over- or under-reacted? The answer, from a pre-registered, blinded 2026 test, is no. The market prices pre-open news at
the open. Paper 2 asks the evaluation question that AI researchers care about: **when an AI model seems to predict
markets, did it read the news, or does it remember what happened?** It adds evidence that paper 1 does not have:
- a **forward test** on news published after every model's release date;
- a **company-identification probe** across all commercial decision models, released as a reusable tool;
- a systematic look at calibration, selective prediction and over-updating.

**Working title:** *Did the Model Read It or Remember It? Evaluating AI Decision Models on Financial News*

Alternatives:
- *Memorisation, Overconfidence and Decay: A Pre-Registered Evaluation of AI Decision Models in Finance*
- *How to Test an AI Trading Signal Without Fooling Yourself*

**Audience:** AI/ML evaluation and benchmarking (an ML evaluation workshop or a datasets-and-benchmarks track) and
finance-ML researchers. arXiv: cs.LG or cs.AI primary, with q-fin.ST and cs.CL.

**Authors (same as paper 1):** Amir Dehkordi, Arman Khaledian, Alireza Kargarzadeh, Nariman Khaledian, Navid Parvini.

---

## 2. Why it is a separate paper, not a slice of paper 1

- **New data.** The forward window (news after 2026-10-21) did not exist when paper 1 was written.
- **New analyses.** The probe on all 19 commercial models (paper 1 covers 6); forward-versus-test comparisons; a
  released tool.
- **A different question and audience.** Paper 1 is about markets; paper 2 is about how to evaluate AI models.
- **Overlap is limited to the shared design.** Paper 2 cites paper 1 for the design and the 2026 results, and does not
  re-report them as new.

---

## 3. Findings already in hand (from paper 1's data; inputs to paper 2)

| Finding | Numbers (2026 test unless stated) | Where |
|---|---|---|
| Validation-to-test decay | Laya-Fin IC 0.055 (val-A) → 0.065 (val-B, t 3.6) → 0.020 (test, t 1.7); API models about halved | NA-12 |
| Memorisation signal | API models identify masked firms 62–74% vs a 28% matched baseline; Laya zero-shot 32% | NA-11 |
| Overconfidence | API models' ECE 0.21–0.36 (stated 70% calls right ~35%); Laya-Fin ECE 0.06 | NA-12/14 (appendix reliability) |
| Selective prediction (exploratory) | Signal concentrated in the top 10% of conviction: d1-ultra signed z_cc 0.80 / 0.75 / 0.59 (val-A / val-B / test), the bottom 50% ≈ 0 | operator's assistant, NA-13b |
| Over-updating (exploratory) | Revisions after the first 30-minute bar have IC ≤ 0 on val-B and test (−0.027 / −0.036 Laya-Fin; −0.043 / −0.011 d1-ultra) | operator's assistant, NA-13b |
| Gating helps gross, not net | The confidence gate lifts gross Sharpe (Laya-Fin 0.35 → 1.18; d1-ultra 0.10 → 1.15); still negative net at 10 bp | NA-13 |
| Silent model updates | The canary STOP on span-02 (judged noise); the rule's design flaw is documented | NA-11 |
| Cost vs accuracy | 19 commercial decision models in the tournament; cheap models as good as expensive ones (val-A) | NA-06 / NA-14 A1 |
| Reversal probes | API models follow reversed news strongly (1.2–1.8 SD); Laya-Fin weakly (0.2 SD) | NA-11 probes |

---

## 4. Hypotheses to pre-register BEFORE any forward data is exported

> **Critical:** write these into `docs/PREREG.md` §15 as one operator row **before** the news after 2026-10-21 is
> exported to `Data/`. Otherwise the forward test is not clean. (Proposed to be added at the NA-14 merge.)

**F1, memorisation via the forward drop (primary).** For each commercial model *m*, compare the daily IC of N̂ with
z_cc on the forward window against the 2026 test, net of the same change for the clean baselines (price-only, bge-ridge):

  D_m = [IC_m(forward) − IC_m(test)] − [IC_clean(forward) − IC_clean(test)].

Memorisation predicts D_m < 0. The test is one-sided, with a block bootstrap over sessions; Holm across the three
production API models.

**F2, entity versus event knowledge.** The company-identification accuracy on masked forward states, against masked
2026-test states and against the 28% matched baseline:
- if it stays high on forward news, the models know companies (entity knowledge, not leakage of outcomes);
- if it falls, the 2026 identification reflected memorised events.

The test is a two-proportion test per model.

**F3, the conviction strategy (from the selective-prediction lead).** The pre-open book (S-D0) on events above each
model's **val-A 90th percentile of |N̂|**:
- open to close, and to the next close;
- at 5 and 10 bp per side, β-hedged;
- net Sharpe > 0, with the placebo percentile and a DSR counting every trial.

The threshold is fixed now from val-A. It must not be changed.

**F4, priced at the open, replicated.** The frozen H1 / H1b on the forward window, as in the PRD's NA-15.

**F5, over-updating.** The IC of the revision z(N̂_D1) − z(N̂_D0) with y1 is ≤ 0 (one-sided test of > 0 rejected,
or a two-sided estimate reported).

**Decision rules:**
- Report every hypothesis, including nulls.
- The forward window is short, so state the power (minimum detectable IC) in the plan before the data arrives.

---

## 5. Data, models and budget

- **Forward window:** the first session after 2026-10-21 → the last session with complete t+5 targets.
  - Aim for at least 3 months, including the Jan–Feb 2027 earnings season (the signal concentrates in earnings news).
  - That points to a news export around **late February 2027**.
- **Data needed:**
  - a NewsWitch export from 2026-08-01 to the latest date (new `Data/news_2026b*.parquet`);
  - a fresh ATOM snapshot (sealed after 2026-10-21 until the forward freeze record exists).
- **Models (all frozen; same ids):**
  - Laya-Fin (laya-s13) and the anchor (Kaggle inference only);
  - Laya zero-shot (local);
  - d1-ultra, span-02, drex-v2.0;
  - baselines (price-only, bge-ridge, LLM baseline; vendor labels only as an upper bound).
- **The all-model probe:** company identification for all 19 tournament API models.
  - On val-A masked states, any time: no forward data needed, about 400 calls per model.
  - On forward masked states, after export.
- **Canary first:** re-run the canary and the drift check before any forward call. Record any build change.
- **Budget:**
  - OpenRouter: $15.73 of $30 used. The forward production for 3 models is ≈ $1–2; the 19-model probe ≈ $0.3–0.5.
    The PRD's NA-15 cap is $2, so it may need an operator-approved increase, recorded in §15.
  - Kaggle: ≈ 1–2 GPU-hours.

---

## 6. The tool to release (what gets cited)

A small open-source package (working name `maskprobe`):
- **Masked-company identification:** matched distractors (same sector and size), accuracy against the matched
  baseline, Wilson intervals.
- **The silent-update canary:** baseline repeats and a drift check against cached answers. Fix the threshold to
  "above the largest baseline repeat", not "above the mean", the flaw found in NA-11.
- **A pre-registration helper:** freeze-hash and append-only deviations log, ledger chaining, one-shot unblinding.
- **A checklist:** "Before you trust an AI backtest", 10 items.

The license is the operator's decision. No proprietary NewsWitch text is released; examples use synthetic or licensed
text.

---

## 7. Chunks (same workflow: a power prompt, then an independent verification, then a merge)

| Chunk | What | When |
|---|---|---|
| (now) §15 row | Pre-register F1–F5, the window rule, the 90th-percentile threshold and the power statement | At the NA-14 merge, before any forward export |
| NA-15 | The frozen forward test (PRD prompt) plus F1–F5 | After the forward export (≈ late Feb 2027) |
| NA-17 | Paper-2 analyses: the all-model probe (val-A anytime; forward after NA-15); forward-versus-test comparisons; calibration, selective prediction and over-updating across all models; package the tool | After NA-15 |
| NA-18 | Write paper 2 (same rules as NA-16: traceable numbers, verified references, ASCII and pdflatex-safe source, nothing hidden) | After NA-17 |

The anchor robustness runs (§15 row of 2026-10-28: seeds 17 and 23 plus a longer run) can join NA-17 if the "does
decision training matter" question is kept; otherwise report them as not run.

---

## 8. Risks

- **A short forward window means low power.** State the minimum detectable effect in advance. A null is still
  informative if the confidence interval excludes the 2026 effect size.
- **A regime change confounds the forward drop.** That is why F1 nets out the clean baselines' change
  (difference-in-differences).
- **Silent model updates or deprecations.** The canary goes first. If a model id disappears, record it and report
  without it.
- **Vendor labels are retrospective**, so they cannot serve as a clean benchmark in either period.
- **Paper 1's referees may ask for the forward test.** Point them to this pre-registered plan, with its commit date as
  proof.

---

## 9. Checklist for when you come back

1. Is the §15 forward-test row committed, and dated before the forward export? If not, do that first.
2. Is the news export ready, covering at least 3 months after 2026-10-21 including the earnings season?
3. Is the OpenRouter balance enough, and is the NA-15 cap raised if needed (recorded)?
4. Is the Kaggle quota available, about 2 GPU-hours?
5. Run NA-15, then NA-17, then NA-18, each followed by an independent verification.
