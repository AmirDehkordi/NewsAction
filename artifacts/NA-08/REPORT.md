# NA-08 REPORT — trained decision models on Kaggle: Laya-Fin (primary) and the ModernBERT-large anchor

Date: 2026-10-26 · Branch `feat/NA-08-trained-dm` (worktree `NewsAction-NA08`, cut from `main` @ `214108f`) ·
Decisions: `docs/decisions/NA-08.md` · Config: `configs/training.yaml`.

**Status: the local half is complete and verified; the Kaggle half has not started.** Labels, the private
dataset, the notebook, the nine kernel directories, the import, the controls and the model cards are built
and tested end to end, the notebook on Laya's real weights and the whole chain on a tiny model. Nothing has
been uploaded to Kaggle. Per the PRD the operator uploads and runs (§4 runbook). The measured throughput (S4),
the controls (S5), the imported predictions (S7) and the model cards' numbers (S8) wait for those runs; this
report is updated when they come back. Three owner decisions are open (§8); the first two are needed before
the upload.

**Result so far.**
- **Labels (S1).** 48,649 event keys of train, val-A and val-B. The train labels end on 2025-06-30, purge
  asserted: react 29,026, mag 29,456, cont 19,115 (|G| ≥ 0.5). Train react levels are roughly symmetric, the
  middle level holding 30%; cont is about a third per class.
- **Dataset (S2).** 4 files and 140 MB. Train: 174,320 examples, 83,749 distinct states. Val-A: 62,404, labels
  where not purged. Val-B: 43,382 and test: 65,204 (Call A only), both **without any label column**
  (schema-tested; mutations RED). Every state is NA-04's masked, third-party-OK E3 state byte for byte, or a
  block-dropout copy of a train state. `isPrivate: true`. sha256 manifest written. A rerun is byte-identical.
- **Notebook (S3).** Adapted from Laya's official 2×T4 notebook. It switches on `INIT` ∈ {laya, modernbert}
  (the same `DecisionModel` head, fresh and seeded for the anchor) and checks the dataset's and the weights'
  sha256 on Kaggle. It runs DDP on both GPUs with fp16, gradient checkpointing and the official RLCD loss.
  It stops early on val-A loss and fits val-A temperatures per head (ECE before and after). A time budget
  keeps the 12-hour limit. There is **no Hub push** (grep-tested). A smoke run on Laya's real
  typed-decisions weights (MPS, 16 train / 300 val-A rows) went through every cell and wrote every output.
- **Head length (operator decision on NA-04 owner decision 2).** 143 tokens, the longest trained question in
  Laya's rendering (react). **Finding:** at MAX_LEN 1,024 this still cuts 5 Call A D0 states (4 train, 1
  val-A; none in val-B or test) by 4–12 tokens, because NA-04 sized the D0 budget on Q1 as canonical JSON (132
  tokens), not Laya's 146-token head. → owner decision 1.
- **Block dropout finding.** A Call B state without its reaction block is byte-identical to the event's Call
  A D2 state (48,197 of 48,197). So the PRD's p = 0.3 reaction-dropout copies only re-weight existing Call A
  D2 examples. Together with identical D0 / D2 twins, 10.5% of train examples are exact duplicates. Kept as
  specified → owner decision 3.

**Blinding.** No return of a session ≥ 2026-01-02 was read, joined or summarized. The labels come from
`panel_public`, which ends on 2025-12-31 (asserted). Test-period rows are Call A states only, without labels.
No `newsaction.train` module imports `panel.targets` or the lock. `ledgers/test_access.jsonl` is unchanged
(2 NA-01 entries). No val-B statistic of any return or model was computed: metrics refuse non-val-A rows
(`train.metrics.require_val_a`, mutation RED). The only val-B numbers in this chunk are row and state counts.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 labels | done | `src/newsaction/train/labels.py`; `work/kaggle/labels.parquet` |
| S2 export | done | `src/newsaction/train/kaggle_export.py`; `work/kaggle/dataset/{train,val_a,val_b,test_callA}.parquet`, `dataset_info.json`, `sha256_manifest.json`, `dataset-metadata.json` |
| S3 notebook | done | `src/newsaction/train/notebook/newsaction_laya_fin.ipynb` (built by `train/nbbuild.py` from `notebook/train_ddp.py`) |
| S4 throughput pilot | code done; **not run** | pilot kernel `work/kaggle/kernels/pilot`; `train/plan.py` → `artifacts/NA-08/throughput.json` after the pilot |
| S5 controls | code done; **not run** | kernels `shuffle-s13`, `repro-s13`; `train/cards.py` → `artifacts/NA-08/controls.json` |
| S6 runbook | done | §4 below; `work/kaggle/kernels/<run>/` (9 kernels) |
| S7 import | code done; **no run to import** | `train/import_preds.py` → `work/kaggle/predictions/` |
| S8 model cards | code done; **no numbers yet** | `train/cards.py` → `artifacts/NA-08/model_card_{laya_fin,anchor}.md` |

Also: `train/metrics.py` (val-A IC, NW t, block bootstrap, ECE, temperature), `train/build.py` (CLI),
`configs/training.yaml`.

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 no val-B / test labels; private; uploaded = local | `tests/test_train_export_schema.py`. On the code path, `split_files` gives val-B and test files with exactly `EVAL_COLUMNS` and no label-like name; the built files' parquet schemas are the same. `dataset-metadata.json` has `isPrivate: true`, and the runbook creates without `--public`. **Mutations** (verifier step 8): `label_index` in the test export, and separately in the val-B export, both **RED**. **Uploaded hash:** pending the upload. On Kaggle the notebook checks every file against `sha256_manifest.json` and records them in each run record, and `import_preds.verify_record` requires them to equal the local manifest. The runbook also downloads the dataset back (`python -m newsaction.train.kaggle_export verify <dir>`). | PASS locally; upload pending |
| AC2 date hygiene | Train sessions 2024-07-01 … 2025-06-30. Last train label horizon 2025-06-30 (react 06-24 + 4, cont 06-23 + 5; `check_purge`; `dataset_info.json` `dates`; tests on the built files). Early stopping and temperatures use val-A only, labelled rows outside the first 5 sessions: the program's `fit_mask` / `calibrate(frames["val_a"])` and the run record (`early_stopping`, `temperature_fit`, `labels_read`), which `import_preds` requires. **Mutations:** purge check off, temperatures on val-B, the program reading val-B labels: all **RED** | PASS (run records pending) |
| AC3 controls | Kernels `shuffle-s13` (Laya, seed 13, 1 epoch, labels permuted within split and question) and `repro-s13`. `cards.controls` applies \|t\| < 2 (D0 N̂ vs e5) and \|Δ IC\| ≤ 0.003 (D0 N̂ vs z_cc,t and vs e5) | pending runs |
| AC4 import | `import_preds.run`. Event ids are mapped back and must match the state files. Every expected example is present exactly once, with probabilities summing to 1 (±1e-4) and equal to softmax(logits / T). Tested end to end on a tiny model (`tests/test_train_import.py`: 21 tests, both inits through every notebook cell). | code PASS; real runs pending |
| AC5 calibration reported, no val-B metric | Cards: val-A ECE (15 bins) and NLL before / after per head and seed, and the ensemble's. `cards` evaluates val-A rows only (`require_val_a`; mutation RED). The tiny-model card has no val-B or test row in its results or calibration tables (test). This REPORT has no val-B metric. | code PASS; numbers pending |
| AC6 no Hub push | `tests/test_train_notebook.py` greps the notebook and the program for every Hub or upload call (`push_to_hub`, `upload_folder`, `create_repo`, `HfApi`, `HF_TOKEN`, Kaggle secrets, …): none. Every run record writes `hub_push: false`, the summary cell re-checks it, and `import_preds` refuses anything else. **Mutation** (a `push_to_hub` call in the program): RED | PASS (run records pending) |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK (64 artifacts, 10 inputs) | PASS |
| GAC3 | `tests/test_blinding.py` passes (it caught and removed four "2026-10-26" decision-date strings from `src/`); access ledger unchanged | PASS |
| GAC4 | No OpenRouter call (no `.env`); `ledgers/spend.jsonl` untouched; $0 | PASS |
| GAC5 | 8 `work/kaggle/` artifacts in `docs/DATA_CONTRACT.md` with the manifest's sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte for byte
(asserted). Afterwards `git status` showed only the author's changes. 16 of 16 were RED:

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

Train react levels 0–8: 1,186 / 1,391 / 3,743 / 3,577 / 8,926 / 3,604 / 4,049 / 1,415 / 1,135. Mag 0–4:
10,024 / 7,511 / 7,219 / 2,394 / 2,308. Cont reverse / stall / continue: 6,601 / 5,998 / 6,516.

### 3.2 Dataset (`work/kaggle/dataset`)

| File | Examples | Distinct states | Labels | Size |
|---|---|---|---|---|
| train | 174,320 | 83,749 | all labelled | 69.9 MB |
| val_a | 62,404 | 29,687 | 56,323 labelled; 3,828 embargo rows | 27.9 MB |
| val_b | 43,382 | 20,327 | **no column** | 16.9 MB |
| test_callA | 65,204 | 29,237 | **no column** (Call A D0 13,977 + D2 18,625 states) | 22.8 MB |

- **Train by source and question:** Call A D0 react 22,267, mag 22,598; Call A D2 react 28,766, mag 29,192;
  Call B react 28,766, cont 18,946.
- **Train copies:** `no_reaction` 8,680; `no_context` 15,105.
- **Exact duplicates in train:** 18,344 (10.5%): the 8,680 `no_reaction` copies (= Call A D2), 9,481 Call A D2
  examples identical to their D0 twin, and 183 others.
- **Tokens per train sequence** (state + head + 4 special): mean 711, p50 733, p95 925; 124 M tokens per epoch.
- **Heads in Laya's rendering** (question tokens, no specials): react 143, mag 77, cont 64. Head length
  143, max length 1,024. Room for the state: react 877, mag 943, cont 956.
- **States over the room:** 5 react examples (`W0:1001:2025-04-10`, `W0:1581:2025-04-15`, `W0:243:2025-04-03`,
  `W0:520:2025-06-13` in train; `W0:59:2025-07-18` in val-A), by up to 12 tokens. No cut at 1,036.
- **Tokenizer:** Laya's typed-decisions tokenizer and NA-04's ModernBERT-large tokenizer give identical ids
  on 4,500 sampled states. The notebook re-checks every count on Kaggle.

### 3.3 Compute (before the pilot; a projection, not a measurement)

- **Rough estimate:** at ~3 GFLOP per token (forward, backward, recomputation) and ~18 TFLOP/s effective
  per T4, one epoch takes ~3–4.5 h on 2×T4. A 3-epoch run with val-A evaluation and the final inference may
  not fit a 12-hour session; the time budget then ends the run at its best epoch.
- **Plan size:** with ~9–11 h per training run, the plan of 8 training runs plus the pilot is ~70–90
  GPU-hours, i.e. about 3 weeks of a 30 h weekly quota.
- **Reductions:** the PRD's order is anchor seeds → 1 (saves 2 runs); MAX_LEN 768, which the no-cut rule
  excludes; then epochs 2. Even reduced, the plan is ~40–55 GPU-hours.
- **The pilot measures it:** `plan.py` writes the options with GPU-hours and weeks for the operator to choose
  from (owner decision 4).

## 4. Operator runbook (S6)

Run from the repository root (`/Users/amir/Research/NewsAction-NA08`, or the main repository after the merge).
Every command is idempotent except `create` and `push`.

```bash
# 0. Environment, once. kaggle is an *extra* (not a group); `make sync` would remove the extras.
uv sync --locked --all-extras
ls -l ~/.kaggle/kaggle.json         # must be -rw------- (chmod 600); never print its content

# 1. Local build (done; deterministic). Rerun only if the NA-04 states or configs/training.yaml change.
uv run --locked python -m newsaction.train.build --stage labels
uv run --locked python -m newsaction.train.build --stage export
uv run --locked python -m newsaction.train.build --stage kernels
make manifest

# 2. Upload the dataset: private (no --public), parquet kept as is. ~140 MB.
uv run --locked kaggle datasets create -p work/kaggle/dataset --keep-tabular
uv run --locked kaggle datasets status amirdehkordi98/newsaction-na08-states       # until "ready"
#    AC1: download it back and compare with the local sha256 manifest.
rm -rf /tmp/na08-dataset-check && mkdir -p /tmp/na08-dataset-check
uv run --locked kaggle datasets download amirdehkordi98/newsaction-na08-states -p /tmp/na08-dataset-check --unzip
uv run --locked python -m newsaction.train.kaggle_export verify /tmp/na08-dataset-check
#    The dataset page on kaggle.com must show "Private".

# 3. Throughput pilot: one kernel, three launches (~45 min). `push` uploads the notebook and runs it.
uv run --locked kaggle kernels push -p work/kaggle/kernels/pilot --accelerator NvidiaTeslaT4
uv run --locked kaggle kernels status amirdehkordi98/newsaction-na08-pilot         # every ~10 min, until "complete"
uv run --locked kaggle kernels output amirdehkordi98/newsaction-na08-pilot \
    -p work/kaggle/predictions/pilot --file-pattern na08_
uv run --locked python -m newsaction.train.build --stage plan     # verifies the pilot → artifacts/NA-08/throughput.json
#    Then choose the plan (owner decision 4); configs/training.yaml `kaggle.runs` / `model.max_epochs` are
#    edited to it and `--stage kernels` is rerun before step 4.

# 4. Training runs, one at a time, in this order (each ends within 11.25 h):
#    shuffle-s13, laya-s13, laya-s17, laya-s23, anchor-s13, anchor-s17, anchor-s23, repro-s13
RUN=shuffle-s13
uv run --locked kaggle kernels push -p work/kaggle/kernels/$RUN --accelerator NvidiaTeslaT4
uv run --locked kaggle kernels status amirdehkordi98/newsaction-na08-$RUN           # until "complete"
uv run --locked kaggle kernels output amirdehkordi98/newsaction-na08-$RUN \
    -p work/kaggle/predictions/$RUN --file-pattern na08_
#    --file-pattern na08_ skips the 1.7 GB fp32 checkpoint (ckpt/), which stays in the kernel's output on
#    Kaggle for NA-11's test Call B inference (attach the kernel's output as an input).

# 5. Import, controls, model cards (after the runs; each verifies what it reads).
uv run --locked python -m newsaction.train.build --stage import
uv run --locked python -m newsaction.train.build --stage cards
make verify
```

If a kernel fails, `kaggle kernels output` still returns its log (`*.log`, without `--file-pattern`). Fixing
the code means a commit, `--stage notebook` and `--stage kernels`, then pushing again: `import_preds` refuses
outputs of a program whose sha256 is not the committed `train_ddp.py`.

## 5. Spend, network

- **Spend:** OpenRouter $0.00 (no `.env`, no call); FMP 0; Kaggle: nothing uploaded or run.
- **Network (downloads only, nothing sent):**
  - the official notebook from GitHub (raw file, read);
  - the Hugging Face model card and API metadata of `convaiinnovations/laya`,
    `convaiinnovations/laya-typed-decisions` and `answerdotai/ModernBERT-large` (revisions, file oids);
  - the `typed-decisions/rl_agent_config.json` and `encoder/config.json` at the pinned revision.

  The Laya weights were already in the local Hugging Face cache (sha256 checked); the smoke run used an APFS
  clone of them, so the shared cache was not touched.
- No article text or derived data left the machine.

## 6. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| `panel_public` e5, z_cc, g_d2, y2 (sessions ≤ 2025-12-31) | labels only (train / val-A to Kaggle, val-B local) | `post`; purged per split (§4.1, asserted) |
| NA-04 state files (masked E3, third-party OK) | model inputs, byte for byte | their decision points (NA-04); Call B only train / val-A / val-B |
| events_d0 / events_d2 keys, split, embargo | label keys, the val-A embargo | static (calendar) |
| `configs/questions_v1.yaml` Q1, Q6; the H-mag question | question text | static |
| Laya weights @ 55cf4c4e / ModernBERT-large @ 45bb4654 | initialisation | static (pre-period checkpoints; Laya's data undisclosed, hence the anchor) |
| val-A labels (outside the embargo) | early stopping, temperatures, val-A metrics | `post`; val-A only (the val-B gate is closed) |

## 7. Deviations from PREREG

None so far. PRD-level choices are in `docs/decisions/NA-08.md`: H-mag on Call A D2, block dropout as copies
with the context block = attention + company + market, the embargo applied to fitting, the warm-up, the frozen
act head, the fp32 checkpoint, val-A-only calibration reporting, the corrected runbook commands. Owner
decision 1 may require one: MAX_LEN 1,036 would be a §9.1 deviation.

## 8. STOP conditions and owner decisions

**STOP, by design:** the PRD has the operator upload and run on Kaggle. Everything before that is done; the
chunk resumes at the import when the runs are downloaded. No budget, no 2026 outcome, no new third party.
Kaggle is already approved (CLAUDE.md D15–D16), and the dataset holds only third-party-OK states.

Owner decisions:

1. **The 5 states that MAX_LEN 1,024 cuts** (§3.2). Options:
   - (a) keep MAX_LEN 1,024 and cut those 5 react examples by ≤ 12 tokens (4 of 174,320 train examples,
     1 val-A prediction; val-B and test untouched);
   - (b) MAX_LEN 1,036, which cuts nothing; a PREREG §9.1 deviation ("max length 1024") logged in §15. The
     model and memory are unaffected (ModernBERT reads 8,192 positions);
   - (c) shorten NA-04's D0 budget by 12 tokens and rebuild the D0 states, which would change state hashes
     NA-05 / NA-06 already use (not recommended).

   **Recommended: (b).** It is the only option that keeps both the no-cut rule and the states NA-05 uses.
   The build currently uses (a), PREREG's 1,024. The choice is one constant in `configs/training.yaml` and
   needs no new upload.
2. **Who uploads and runs.** The PRD has the operator do it. The Kaggle CLI on this machine is authenticated
   (`amirdehkordi98`), so I can also run steps 2–5 of the runbook myself on your go-ahead: the upload, each
   kernel push and the downloads. Uploading puts the masked states on Kaggle (private).
3. **Reaction-dropout duplicates** (§3.2): keep the p = 0.3 copies (PREREG §9.1 as written; ~5% more compute),
   or drop them via `TRAIN_VARIANTS` (they duplicate Call A D2 examples), logged as a §9.1 deviation. Likewise
   the 9,481 D0 / D2 twin duplicates could be dropped (~5% compute). **Recommended:** keep both unless the
   pilot shows the plan does not fit; then drop them before cutting seeds.
4. **The quota plan** (after the pilot): the plan likely needs 2–3 weeks of quota. Choose between the full plan
   and the PRD's reductions (anchor seeds → 1; epochs 2); MAX_LEN 768 is excluded by the no-cut rule.
   `throughput.json` will list the GPU-hours and weeks of each option. Kaggle is assumed to count a T4 ×2
   session's wall-clock hours against the quota once (to be confirmed on the account page after the pilot).
5. **Ledger merge.** NA-05 runs in parallel. Both branches may append to `ledgers/trials.jsonl`, whose lines
   are hash-chained, so merging both needs a re-chain of one branch's lines. NA-08 appends trials only at the
   cards stage, after the runs.
6. **If NA-07 picks an encoding other than E3**, NA-04 must first build the full state files in that encoding;
   then `configs/training.yaml` `encoding` / `states`, the export and one retraining (PREREG §9.1).

## 9. Files

- **Added — code.**
  - `src/newsaction/train/{__init__, labels, kaggle_export, nbbuild, import_preds, metrics, plan, cards,
    build}.py`;
  - `src/newsaction/train/notebook/{train_ddp.py, newsaction_laya_fin.ipynb}`.
- **Added — config, docs.**
  - `configs/training.yaml`; `docs/decisions/NA-08.md`; `artifacts/NA-08/REPORT.md`;
  - `docs/DATA_CONTRACT.md`: the NA-08 section, 8 artifacts, and the schema of the files the import writes.
- **Changed.** `pyproject.toml`:
  - `laya.*` in mypy's missing-import overrides;
  - the notebook directory excluded from mypy (the program runs on Kaggle's stack);
  - the generated notebook excluded from `ruff format` (still linted).
- **Tests** (6 files, 104 tests): `test_train_config` (9), `test_train_labels` (49), `test_train_export_schema`
  (19), `test_train_notebook` (13), `test_train_metrics` (8), `test_train_import` (21, including the tiny-model
  end-to-end run).
- **Derived (gitignored).** `work/kaggle/labels.parquet`, `work/kaggle/dataset/*` (registered),
  `work/kaggle/kernels/<run>/` (9 kernel directories: `kernel-metadata.json` and the run's notebook; not data).
- **`make verify`:** see §10.

## 10. `make verify`

Exit 0 in 165 s, peak RSS 9.3 GB:
- ruff "All checks passed!" and "126 files already formatted";
- mypy --strict "no issues found in 63 source files";
- pytest **1,341 passed, 1 xfailed** (1,215 + 1 before NA-08; 104 NA-08 tests, plus a few more collected from
  the new parametrizations);
- manifest: 64 artifacts, 10 inputs OK;
- ledgers OK: fmp 0, spend 0, test_access 2, trials 94 (unchanged).

NA-05's own `make test` started a few seconds before this run and the two overlapped. Both fit in memory; the
next runs wait for an idle machine.
