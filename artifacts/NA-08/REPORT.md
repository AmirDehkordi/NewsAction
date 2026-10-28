# NA-08 REPORT — trained decision models on Kaggle: Laya-Fin (primary) and the ModernBERT-large anchor

Date: 2026-10-26 … 2026-10-27 · Branch `feat/NA-08-trained-dm` (worktree `NewsAction-NA08`, cut from `main` @
`214108f`) · Decisions: `docs/decisions/NA-08.md` · Config: `configs/training.yaml`.

**Status: complete for one seed per model; one control deferred.** The operator decided on 2026-10-27 to finish
within this week's Kaggle quota with one seed per model. NA-08 delivers both trained models, each as its seed-13
run (PREREG §15 NA-08 row 2). The steps:

1. A private Kaggle dataset, byte-identical to the local export.
2. A throughput pilot.
3. The shuffled-label control.
4. Laya-Fin (`laya-s13`) and the anchor (`anchor-s13`): 1 epoch each on 2×T4, verified, imported in the common
   prediction schema for val-A, val-B and test Call A, with model cards and controls.

The reproducibility rerun `repro-s13` is the operator-approved deferral under AC3; it does not block NA-11. Seeds 17
and 23 of both models are deferred too, and join without a code change.

**Val-A results** (first 5 sessions excluded; daily Spearman IC, Newey–West t, block-bootstrap 95% CI):

| Reading | Laya-Fin (laya-s13) | Anchor (anchor-s13) | Shuffled labels (control) |
|---|---|---|---|
| D0 Call A, N̂ vs z_cc,t (PREREG §8.5's metric) | **+0.055**, t 4.30, [0.030, 0.078] | **+0.024**, t 1.86, [−0.001, 0.049] | +0.001, t 0.06 |
| D0 Call A, N̂ vs e5 (the training target) | +0.027, t 1.02 | +0.009, t 0.65 | −0.007, t −0.48 (**PASS**) |
| D2 Call A, N̂ vs e5 | +0.036, t 1.56 | −0.001, t −0.11 | −0.007, t −0.44 |
| D2 Call B, N̂ vs e5 (sees the day's reaction) | +0.448, t 30.9 | +0.003, t 0.30 | +0.011, t 1.16 |
| D0 H-mag, E[level] vs \|z_cc,t\| | +0.172, t 6.85 | +0.169, t 6.32 | −0.044, t −2.39 |
| D2 Call B H-cont, C vs sign(G)·y2 (\|G\| ≥ 0.5) | +0.023, t 1.61 | −0.027, t −2.19 | +0.020, t 1.49 |

**What the table shows:**
- Both models read the size of a day's move from pre-open news (H-mag, t > 6).
- Laya-Fin also has a significant direction signal (N̂ vs z_cc,t, t 4.3); the anchor's is weaker and not
  significant.
- Laya-Fin's Call B react head uses the reaction block; the anchor's does not after one epoch.
- Neither cont head learned much. Laya-Fin's is near uniform (IC +0.023, t 1.61). The anchor's is uniform after
  its temperature (T 20), yet its ranking is negative (IC −0.027, t −2.19). Like the control's H-mag reading
  (t −2.39), it falls under no pre-registered rule, and it is one of 18 readings in the table.
- **Calibration** (val-A, 15-bin ECE): Laya-Fin react 0.018 and mag 0.017 at temperatures ≈ 1.00, cont 0.0004
  at T 2.36. For the anchor, the NLL-optimal temperatures (0.97, 0.90) lower NLL slightly but raise ECE (react
  0.004 → 0.012, mag 0.003 → 0.022), and its cont head is uniform (T on the bound 20).

**Blinding.** No return of a session ≥ 2026-01-02 was read, joined or summarized:
- The labels come from `panel_public`, which ends on 2025-12-31 (asserted).
- Test-period rows are Call A states without any label column, and their predictions are stored, not
  evaluated.
- No `newsaction.train` module imports `panel.targets` or the lock.
- `ledgers/test_access.jsonl` is unchanged (2 NA-01 entries).
- **No val-B statistic** of any return or model was computed: the metrics refuse non-val-A rows
  (`train.metrics.require_val_a`, mutation RED). The only val-B numbers here are row and state counts.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 labels | done | `src/newsaction/train/labels.py`; `work/kaggle/labels.parquet` |
| S2 export | done | `train/kaggle_export.py`; `work/kaggle/dataset/{train,val_a,val_b,test_callA}.parquet`, `dataset_info.json`, `sha256_manifest.json`, `dataset-metadata.json`; uploaded as the private `amirdehkordi98/newsaction-na08-states` |
| S3 notebook | done | `train/notebook/newsaction_laya_fin.ipynb`, built by `train/nbbuild.py` from `train/notebook/train_ddp.py` |
| S4 throughput pilot and plan | done | kernel `newsaction-na08-pilot`; `train/plan.py` → `artifacts/NA-08/throughput.json` |
| S5 controls | done; the reproducibility rerun is deferred (operator-approved, AC3) | kernel `newsaction-na08-shuffle-s13`; `train/cards.py` → `artifacts/NA-08/controls.json`; `repro-s13` planned, `deferred: true` |
| S6 runbook | done | §4; `work/kaggle/kernels/<run>/` (9 kernel directories) |
| S7 import | done | `train/import_preds.py` → `work/kaggle/predictions/runs/{shuffle-s13,laya-s13,anchor-s13}.parquet`, `work/kaggle/predictions/{laya_fin,anchor}_{val_a,val_b,test_callA}.parquet` |
| S8 model cards | done | `artifacts/NA-08/model_card_{laya_fin,anchor}.md` |

Also: `train/metrics.py` (val-A IC, NW t, block bootstrap, ECE, temperature), `train/build.py` (CLI), and
`configs/training.yaml`, which holds every constant with its PREREG / PRD source.

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 no val-B / test labels; private; uploaded = local | `tests/test_train_export_schema.py` checks the code path: `split_files` gives val-B and test files with exactly `EVAL_COLUMNS` and no label-like name; the built files' parquet schemas are the same. `dataset-metadata.json` has `isPrivate: true`; the dataset was created without `--public`, and Kaggle's metadata says `isPrivate: true`. **Mutations** (verifier step 8): `label_index` in the test export, and separately in the val-B export, both **RED**. **Uploaded = local:** the dataset, downloaded back file by file, passes `python -m newsaction.train.kaggle_export verify` on all 5 manifest files, and `sha256_manifest.json` is identical (`2bafd1de…`). On Kaggle every run re-checked every file and recorded the sha256s, and `import_preds.verify_record` found them equal to the local manifest for the pilot, shuffle-s13, laya-s13 and anchor-s13. | PASS |
| AC2 date hygiene | Train sessions 2024-07-01 … 2025-06-30. The last train label horizon is 2025-06-30 (react 06-24 + 4, cont 06-23 + 5; `check_purge`, `dataset_info.json` `dates`, tests on the built files). Early stopping and temperatures used val-A only (labelled rows outside the first 5 sessions): the program's `fit_mask` and `calibrate(frames["val_a"])`. Every run record says so (`early_stopping.split`, `temperature_fit.split` = val_a, `labels_read` val_b / test false), and `import_preds` refuses anything else. Fit sessions in the records: 2025-07-09 … 2025-09-30. **Mutations:** purge check off, temperatures on val-B, the program reading val-B labels: all **RED** | PASS |
| AC3 controls | **Shuffled labels** (`shuffle-s13`: Laya init, seed 13, 1 epoch, labels permuted within split and question): val-A D0 N̂ vs e5 IC −0.0072, NW t −0.48, \|t\| < 2: **PASS**. Every head's IC is in `controls.json`; H-mag reads −0.044, t −2.39, which is not part of the rule. **Reproducibility** (`repro-s13`): **deferred**, the operator-approved deferral under AC3 (2026-10-27). The remaining weekly quota is kept for NA-11, and it does not block NA-11 (`controls.json` `reproducibility.status`). | PASS (shuffled labels); reproducibility deferred with operator approval |
| AC4 import | Laya-Fin and the anchor each have val-A (62,404 rows), val-B (43,382) and test Call A (65,204) predictions in the common schema. `import_preds` checks, before writing: every expected example present exactly once; option counts as the questions'; probabilities summing to 1 (±1e-4) and equal to softmax(logits / T) (±2e-4); every event id in the state files (`common_schema` refuses others). Also tested end to end on a tiny model through every notebook cell (`tests/test_train_import.py`, 23 tests). | PASS |
| AC5 calibration reported; no val-B metric | Both cards report val-A ECE (15 bins) and NLL before and after the per-head temperature (react, mag, cont). `cards` evaluates val-A rows only (`require_val_a`; mutation RED). The cards, `controls.json` and this REPORT carry no val-B or test metric (the val-B and test files are named, never evaluated), and the run logs print only val-A losses. | PASS |
| AC6 no Hub push | `tests/test_train_notebook.py` greps the notebook and the program for every Hub or upload call (`push_to_hub`, `upload_folder`, `create_repo`, `HfApi`, `HF_TOKEN`, Kaggle secrets, …): none. Every run record (pilot, shuffle-s13, laya-s13, anchor-s13) says `hub_push: false`; the summary cell re-checks it and `import_preds` refuses anything else. **Mutation** (a `push_to_hub` call in the program): RED | PASS |
| GAC1 | `make verify` exit 0 (§10) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (73 artifacts, 10 inputs) | PASS |
| GAC3 | `tests/test_blinding.py` passes (during the chunk it flagged four "2026-10-26" decision-date strings in `src/`, since reworded); `ledgers/test_access.jsonl` unchanged (2 NA-01 entries) | PASS |
| GAC4 | No OpenRouter call (no `.env`); `ledgers/spend.jsonl` untouched; $0 | PASS |
| GAC5 | 17 `work/kaggle/` artifacts in `docs/DATA_CONTRACT.md` with the manifest's sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte for byte
(asserted); `git status` afterwards showed only the author's changes. 16 of 16 were RED:

| Mutation | File | Test |
|---|---|---|
| `label_index` in the test export | kaggle_export.py | test_train_export_schema |
| `label_index` in the val-B export | kaggle_export.py | test_train_export_schema |
| third-party check off; masked check off; test-period Call B refusal off | kaggle_export.py | test_train_export_schema |
| val-A guard off | metrics.py | test_train_metrics |
| bins closed on the right; purge check off; cont stall band widened | labels.py | test_train_labels |
| `push_to_hub` in the program; temperatures fit on val-B; val-B labels read | notebook/train_ddp.py | test_train_notebook |
| import accepts another dataset; import accepts a Hub push | import_preds.py | test_train_import |
| N̂ midpoints changed; reaction dropout p changed | configs/training.yaml | test_train_config |

## 3. Numbers

### 3.1 Labels (`work/kaggle/labels.parquet`; train and val-A shown, no val-B statistic)

| Split | Keys | react labelled | mag labelled | cont labelled (\|G\| ≥ 0.5) |
|---|---|---|---|---|
| train | 29,485 | 29,026 | 29,456 | 19,115 |
| val-A | 11,252 | 10,692 | 11,250 | 6,667 |
| val-B | 7,912 | (stored for NA-11) | | |

- Train react levels 0–8: 1,186 / 1,391 / 3,743 / 3,577 / 8,926 / 3,604 / 4,049 / 1,415 / 1,135.
- Mag 0–4: 10,024 / 7,511 / 7,219 / 2,394 / 2,308.
- Cont reverse / stall / continue: 6,601 / 5,998 / 6,516.
- Bins: [0, 0.5) [0.5, 1) [1, 2) [2, 3) [3, ∞), the codebook's move words.
- 30 random train labels are recomputed by hand from `panel_public` in a test (e5 re-summed from AR_cc).

### 3.2 Dataset (`work/kaggle/dataset`; Kaggle `amirdehkordi98/newsaction-na08-states`, private)

| File | Examples | Distinct states | Labels | Size |
|---|---|---|---|---|
| train | 174,320 | 83,749 | all labelled | 69.9 MB |
| val_a | 62,404 | 29,687 | 56,323 labelled; 3,828 embargo rows | 27.9 MB |
| val_b | 43,382 | 20,327 | **no column** | 16.9 MB |
| test_callA | 65,204 | 29,237 | **no column** (Call A D0 13,977 + D2 18,625 states) | 22.8 MB |

- **Train by source and question:** Call A D0 react 22,267, mag 22,598; Call A D2 react 28,766, mag 29,192;
  Call B react 28,766, cont 18,946.
- **Block-dropout copies** (PREREG §9.1): `no_reaction` 8,680; `no_context` 15,105.
- **Finding: exact duplicates in train.** 18,344 (10.5%):
  - the 8,680 `no_reaction` copies, because a Call B state without its reaction block is byte-identical to the
    event's Call A D2 state (48,197 of 48,197);
  - 9,481 Call A D2 examples identical to their D0 twin;
  - 183 others.

  Kept as specified (operator decision).
- **Tokens per train sequence** (state + head + 4 special tokens): mean 711, p50 733, p95 925; 124 M per epoch.
- **Heads in Laya's rendering** (question tokens, no specials): react 143, mag 77, cont 64. Head length 143;
  max length **1,036** (PREREG §15 NA-08 row 1). Room for the state: react 889, mag 955, cont 968. The longest
  D0 state has 889 tokens, so **no state is cut** (every run record: `states_cut` empty).
  - **Why 1,036:** at the PRD's 1,024 the react room would be 877, and 5 states would have been cut by up to 12
    tokens (4 train, 1 val-A). NA-04 sized the D0 budget on Q1 as canonical JSON (132 tokens), not on Laya's
    146-token head.
- **Tokenizer:** Laya's typed-decisions tokenizer and NA-04's ModernBERT-large tokenizer give identical ids on
  4,500 sampled states. Every run re-checked every state's token count on Kaggle.

### 3.3 Throughput pilot and the plan (S4; `artifacts/NA-08/throughput.json`)

The pilot was one kernel with three launches on Kaggle's GPU T4 x2 (Python 3.13.15, torch 2.11.0+cu128,
transformers 5.20.2, laya 0.4.14). Each trained 200 micro-batches per GPU on a 5% subsample of train, then
rehearsed the output path on 2,000 / 500 / 500 val-A / val-B / test rows.

| Launch | Training (seq/s, 2 GPUs) | Inference (seq/s) | Peak GPU | Result |
|---|---|---|---|---|
| Laya, checkpointing on, micro-batch 8 × accum. 4 | 8.24 | 31.9 | 10.5 GB | ok, rehearsal verified |
| Laya, checkpointing off, micro-batch 4 × accum. 8 | – | – | > 14.5 GB | out of memory once AdamW's states exist (probe alone 10.1 GB) |
| Anchor, checkpointing on, micro-batch 8 × accum. 4 | 8.21 | 32.0 | 10.5 GB | ok, rehearsal verified |

- **Projection:** an epoch takes 5.87 h, the val-A evaluation 0.54 h and the val-B + test inference 0.94 h. A
  1-epoch run is therefore 7.44 h (6.49 h for a control, which predicts val-A only), and 2 epochs (13.8 h) do
  not fit the 11.25 h budget of a 12-hour session.
- **Every run trains 1 epoch**, within PREREG §9.1's ≤ 3; the cosine schedule spans that epoch (2,724 updates),
  and early stopping has one epoch to choose.
- **Options** (GPU-hours over 30 h weekly quotas):
  - full, 58.3 h (2 weeks);
  - anchor seeds → 1, 43.4 h (2 weeks);
  - MAX_LEN 768 is excluded by the no-cut rule;
  - 2 epochs do not fit a session.
- **Plans:**
  - 2026-10-26: the full plan, hedged;
  - 2026-10-27: replaced by one seed per model within this week's quota (PREREG §15 NA-08 row 2);
  - 2026-10-27, evening: repro-s13 deferred and no new pushes (§8).

### 3.4 Kaggle runs (each downloaded with `--file-pattern na08_` and verified by `import_preds verify`)

| Run | Pushed (UTC) | Session h | Epochs | Train seq/s | Val-A loss | T react / mag / cont | Quota before push | Verified |
|---|---|---|---|---|---|---|---|---|
| pilot (3 launches) | 10-26 20:22 | 0.35 | (200 steps) | 8.24 / 8.21 | – | (rehearsal) | 30 h left | yes (`plan`) |
| shuffle-s13 | 10-26 20:55 | 6.76 | 1 | 7.89 | 1.6421 (shuffled labels) | 0.95 / 0.85 / 20.0 | – | yes |
| laya-s13 | 10-27 05:04 | 7.59 | 1 | 7.94 | 1.5761 | 1.00 / 1.00 / 2.36 | – | yes |
| anchor-s13 | 10-27 12:41 | 8.11 | 1 | 7.41 | 1.6136 | 0.97 / 0.90 / 20.0 | 15.30 h left; needs 8.18 (7.44 + 10%) | yes |
| repro-s13 | 10-27 20:56 | ≈ 0.57, stopped | – | – | – | – | 7.19 h left; needs 7.14 (6.49 + 10%) | not imported: **deferred** |

- **repro-s13:** the operator's decision to defer it ("the rest is kept for NA-11") crossed with its push: it
  had been pushed at 20:56 under the earlier rule, as a val-A-only run projected at 6.49 h. The CLI cannot cancel
  a session (the SDK's cancel needs a session id that no API call returns). The operator stopped it on Kaggle
  about 35 minutes in. Kaggle's status query no longer finds the kernel, the quota has stayed at 23.38 h used
  since, and nothing was downloaded.
- **Quota after:** 23.38 h used of 30, 6.62 h left until the reset at 2026-10-31 00:00 UTC.
- **Kaggle GPU time in NA-08:** pilot 0.35 + shuffle 6.76 + laya 7.59 + anchor 8.11 + stopped repro 0.57 =
  23.38 h, equal to `kaggle quota`.
- **For NA-11:** the laya-s13 and anchor-s13 kernels keep their fp32 checkpoints in their outputs (`ckpt/`,
  config with `na08_temperatures`). Attach them as kernel inputs for the test Call B inference.

## 4. Operator runbook (S6)

Run from the repository root (`/Users/amir/Research/NewsAction-NA08`, or the main repository after the merge).
Steps 1–3 and the runs above are done. The commands also cover the deferred runs.

```bash
# 0. Environment, once. kaggle is an *extra* (not a group); `make sync` would remove the extras.
uv sync --locked --all-extras
ls -l ~/.kaggle/kaggle.json         # must be -rw------- (chmod 600); never print its content
uv run --locked kaggle quota        # GPU hours used / remaining in the weekly window, and its reset

# 1. Local build (deterministic). Rerun only if the NA-04 states or configs/training.yaml change.
uv run --locked python -m newsaction.train.build --stage labels
uv run --locked python -m newsaction.train.build --stage export
uv run --locked python -m newsaction.train.build --stage kernels
make manifest

# 2. Upload the dataset: private (no --public), parquet kept as is. ~140 MB.
uv run --locked kaggle datasets create -p work/kaggle/dataset --keep-tabular
uv run --locked kaggle datasets status amirdehkordi98/newsaction-na08-states       # until "ready"
#    AC1: download it back and compare with the local sha256 manifest (the bundle download can come back
#    empty right after creation; per-file downloads work).
rm -rf /tmp/na08-dataset-check && mkdir -p /tmp/na08-dataset-check
for f in train.parquet val_a.parquet val_b.parquet test_callA.parquet dataset_info.json sha256_manifest.json; do
  uv run --locked kaggle datasets download amirdehkordi98/newsaction-na08-states -f $f -p /tmp/na08-dataset-check --force
done
uv run --locked python -m newsaction.train.kaggle_export verify /tmp/na08-dataset-check

# 3. Throughput pilot: one kernel, three launches (~21 min). `push` uploads the notebook and runs it.
uv run --locked kaggle kernels push -p work/kaggle/kernels/pilot --accelerator NvidiaTeslaT4
uv run --locked kaggle kernels status amirdehkordi98/newsaction-na08-pilot         # until "complete"
uv run --locked kaggle kernels output amirdehkordi98/newsaction-na08-pilot \
    -p work/kaggle/predictions/pilot --file-pattern na08_
uv run --locked python -m newsaction.train.build --stage plan     # verifies the pilot → throughput.json

# 4. A training run (1 epoch, ~7.4 h; ~6.5 h for a control). Before each push: `kaggle quota` must leave the
#    run's projection + 10%. A deferred run (repro-s13, laya-s17/23, anchor-s17/23) is first set to
#    `deferred: false` in configs/training.yaml (then --stage kernels).
RUN=repro-s13
uv run --locked kaggle kernels push -p work/kaggle/kernels/$RUN --accelerator NvidiaTeslaT4
uv run --locked kaggle kernels status amirdehkordi98/newsaction-na08-$RUN           # until "complete"
uv run --locked kaggle kernels output amirdehkordi98/newsaction-na08-$RUN \
    -p work/kaggle/predictions/$RUN --file-pattern na08_
uv run --locked python -m newsaction.train.import_preds verify $RUN      # checks the download, writes nothing
#    --file-pattern na08_ skips the 1.7 GB fp32 checkpoint (ckpt/), which stays in the kernel's output.

# 5. Import, controls, model cards (each verifies what it reads); a new seed joins its model's ensemble.
uv run --locked python -m newsaction.train.build --stage import
uv run --locked python -m newsaction.train.build --stage cards
make verify
```

If a kernel fails, `kaggle kernels output` still returns its log (without `--file-pattern`). Fixing the code
means a commit, `--stage notebook` and `--stage kernels`, then pushing again: `import_preds` refuses outputs of
a program whose sha256 is not the committed `train_ddp.py`.

## 5. Spend, network

- **OpenRouter:** $0.00 this chunk (no `.env`, no call). Cumulative: this branch's `ledgers/spend.jsonl` is
  empty (the branch was cut before any spend), so NA-08 adds $0 to the total on main.
- **FMP:** 0 requests (`ledgers/fmp_requests.jsonl` unchanged).
- **Kaggle (free tier):** 23.38 GPU-hours of the 30-hour weekly quota (§3.4).
- **Uploads, operator-approved:** the private dataset (masked, third-party-OK states; train and val-A labels
  only) and five notebooks. Kernels are private, GPU T4 ×2, with internet on to download the pinned models.
  Nothing was pushed to the Hugging Face Hub.
- **Downloads:**
  - the official Laya notebook (GitHub raw);
  - Hugging Face model metadata and configs (`convaiinnovations/laya`, `convaiinnovations/laya-typed-decisions`,
    `answerdotai/ModernBERT-large`);
  - the runs' outputs from Kaggle.

  Laya's weights were already in the local Hugging Face cache (sha256 checked); the smoke run used an APFS clone.
- No article text left the machine except as the masked states in the private Kaggle dataset (CLAUDE.md
  D15–D16).

## 6. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| `panel_public` e5, z_cc, g_d2, y2 (sessions ≤ 2025-12-31) | labels (train / val-A on Kaggle; val-B local) | `post`; purged per split (§4.1, asserted) |
| NA-04 state files (masked E3, third-party OK) | model inputs, byte for byte | their decision points (NA-04); Call B only train / val-A / val-B |
| events_d0 / events_d2 keys, split, embargo | label keys; the val-A embargo | static (calendar) |
| `configs/questions_v1.yaml` Q1, Q6; the H-mag question | question text | static |
| Laya @ 55cf4c4e (typed-decisions), ModernBERT-large @ 45bb4654 | initialisation | static; Laya's training data is undisclosed, hence the anchor |
| val-A labels outside the first 5 sessions | early stopping, temperatures, every metric | `post`; val-A only (the val-B gate is closed) |

## 7. Deviations from PREREG

Two rows were appended to the §15 Deviations log (NA-08, before the freeze). The operator committed them on the
branch (`24978f6`), and they reached main with the merge. `tests/test_train_config.py` checks both rows.

1. **§9.1 max length 1024 → 1,036** for the trained models. The head is the longest trained question in Laya's
   rendering (143 + 3 tokens), and at 1,024 five Call A D0 states would be cut. Operator decision 2026-10-26.
2. **§9.1–9.2 seeds {13, 17, 23} → one seed (13) per model for now.** The other seeds are deferred and the
   reported model is the single seed; this also departs from the PRD's seed targets and reduction order. Every
   run trains 1 epoch (within ≤ 3). The reproducibility rerun is deferred, and the stopped session is
   recorded. Operator decisions 2026-10-27.

PRD-level choices are in `docs/decisions/NA-08.md`:
- H-mag on Call A D2;
- block dropout as copies, with the context block = attention + company + market;
- the embargo applied to fitting;
- the warm-up and the frozen act head;
- the fp32 checkpoint;
- val-A-only calibration reporting (the PRD's S3 also names val-B, which AC5 and the val-B gate exclude);
- the controls predicting val-A only;
- the corrected runbook commands.

## 8. STOP conditions and owner decisions

No STOP condition fired: no OpenRouter budget, no 2026 outcome, no new third party (Kaggle was approved, the
dataset is private), no FMP. The Kaggle quota bounded the plan; the operator decided each reduction.

Owner decisions, all taken during the chunk:
1. **2026-10-26: MAX_LEN 1,036.** No state is cut (PREREG §15 NA-08 row 1).
2. **2026-10-26: the Kaggle steps run from this session.** Upload, pushes and downloads, each with its quota
   check.
3. **2026-10-26: keep the block-dropout copies** as specified, though they duplicate Call A D2 examples.
4. **The run plan:**
   - full, hedged (2026-10-26);
   - replaced by one seed per model within this week's quota (2026-10-27);
   - then "defer repro-s13, no new pushes; the remaining quota is kept for NA-11" (2026-10-27, evening). The
     session already pushed was stopped by the operator.

Open for the operator:
5. **Commit the two PREREG §15 rows** with the merge.
6. **Deferred runs.** repro-s13 (AC3) and seeds 17 / 23 of both models are planned with `deferred: true`. Each
   can run after a quota reset (§4 step 4). Then rerun `--stage import` and `--stage cards`: a seed joins its
   model's ensemble, and the repro rerun fills `controls.json`.
7. **Ledger merge.** NA-08 appended 4 trial records (`ledgers/trials.jsonl`, now 98 lines: laya_fin and anchor,
   each as its seed and as its 1-seed "ensemble", on val-A D0 N̂ vs z_cc,t). Other chunks append to the same
   ledger on their branches (NA-05 runs in parallel). The ledger is hash-chained (`prev` = sha256 of the
   previous line), so the merge needs NA-08's 4 lines re-chained onto main's tip.
8. **If NA-07 picks an encoding other than E3:** NA-04 must first build the full state files in it; then
   `configs/training.yaml` `encoding` / `states`, the export and a retraining (PREREG §9.1).

## 9. Files

- **Added — code.**
  - `src/newsaction/train/{__init__, labels, kaggle_export, nbbuild, import_preds, metrics, plan, cards, build}.py`;
  - `src/newsaction/train/notebook/{train_ddp.py, newsaction_laya_fin.ipynb}`.
- **Added — config and docs.**
  - `configs/training.yaml`; `docs/decisions/NA-08.md`;
  - `artifacts/NA-08/{REPORT.md, throughput.json, controls.json, model_card_laya_fin.md, model_card_anchor.md}`.
- **Changed.**
  - `docs/DATA_CONTRACT.md`: the NA-08 section, 17 artifacts;
  - `pyproject.toml`: `laya.*` in mypy's missing-import overrides; the notebook directory excluded from mypy (its
    program runs on Kaggle's stack); the generated notebook excluded from `ruff format` (still linted);
  - `ledgers/trials.jsonl`: +4 NA-08 trials.
- **Committed by the operator.** `docs/PREREG.md` (§15, two NA-08 rows; `24978f6`).
- **Tests.** 6 files, 121 tests: `test_train_config` (9), `test_train_labels` (49), `test_train_export_schema`
  (19), `test_train_notebook` (13), `test_train_metrics` (8), `test_train_import` (23). `test_train_import`
  includes the tiny-model end-to-end runs (both inits, the shuffle control and the pilot, through every
  notebook cell).
- **Derived (gitignored).**
  - `work/kaggle/labels.parquet`, `work/kaggle/dataset/*`, `work/kaggle/predictions/runs/*.parquet` and
    `work/kaggle/predictions/{laya_fin,anchor}_*.parquet`, all registered;
  - the downloaded run outputs `work/kaggle/predictions/<run>/na08_*` (checked by sha256);
  - `work/kaggle/kernels/<run>/` (9 kernel directories).
- **Peak RSS:** labels 0.3 GB, export 6.3 GB, import 1.0 GB, cards 0.6 GB (final rerun, 17 s, outputs
  byte-identical), `make verify` 6.7 GB (§10).

## 10. `make verify`

Final run 2026-10-27, 23:25–23:30 UTC: **exit 0**, 296 s, peak RSS 6.7 GB (`/usr/bin/time -l`).
`pgrep -fl pytest` first showed other sessions' test runs (ATOM; load average ≈ 105), so the run waited 1 h 44 min
until no test run had been active for 60 s (load average 10 at the start). An earlier run in this chunk had
overlapped with NA-05's `make test`; this one started with no other test run active.

| Step | Result |
|---|---|
| `ruff check src tests scripts` | All checks passed |
| `ruff format --check src tests scripts` | 126 files already formatted |
| `mypy --strict src/` | no issues in 63 source files |
| `pytest -q -m "not network"` | 1343 passed, 1 xfailed, 4 min 47 s. The xfail is a pre-existing strict one in `tests/test_panel_adjust.py` (the documented ex-dividend AR_on bound), not an NA-08 test |
| `python -m newsaction.io check` | manifest OK: 73 artifacts, 10 inputs |
| `python -m newsaction.ledger check` | hash chains OK: fmp_requests 0, spend 0, test_access 2, trials 98 |
