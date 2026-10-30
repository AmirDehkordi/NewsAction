# NewsAction

Research code for a look-ahead-free paper on **decision models × financial news**: can a decision
model read pre-open company news and anticipate the market's reaction, and once part of the
reaction is visible, judge whether the market over- or under-reacted?

- Rules that bind every session: [`CLAUDE.md`](CLAUDE.md)
- Pre-registration (definitions, splits, hypotheses; frozen in NA-11): [`docs/PREREG.md`](docs/PREREG.md)
- Work plan, chunks NA-00 … NA-15 with power and verification prompts: [`NewsAction PRD.md`](NewsAction%20PRD.md)
- Every derived file and its sha256: [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md)
- Per-chunk decisions and self-audits: `docs/decisions/NA-xx.md`, `artifacts/NA-xx/REPORT.md`

## Setup

Python 3.12 and [uv](https://docs.astral.sh/uv/). `Data/` (raw, read-only, gitignored) must sit at
the repository root; see `Data/README.md`.

```bash
make sync                               # uv sync --locked (runtime + dev tools)
cp .env.example .env                    # only the keys the current chunk needs; never commit .env
uv run python scripts/convert_pickles.py   # NA-00: rebuild work/market/*.parquet from Data/market
make verify
```

Optional dependency groups are declared but not installed by default: `uv sync --extra embed`
(NA-02), `--extra laya` (NA-05), `--extra kaggle` (NA-08).

## Working from the GitHub copy

The private GitHub repository holds the code, configs, docs, ledgers, committed artifacts and the paper sources.
It does **not** hold any data. These stay on the operator's machine:

- `Data/`: NewsWitch news, prices and market files (raw, licensed);
- `work/`: derived data;
- `cache/`: decision-model responses;
- `.env`: API keys;
- `artifacts/NA-02/{spam_judgments,detector_eval}.csv`: judged NewsWitch titles and sentences (gitignored).

```bash
brew install git-lfs tectonic && git lfs install   # once per machine; ledgers/spend.jsonl (210 MB) is in Git LFS
git clone https://github.com/AmirDehkordi/NewsAction.git && cd NewsAction
uv sync --locked --all-extras                      # the extras (spacy, torch) are needed for `make type`
```

**Works without the data:**
- `make lint`, `make type`, `make test` (tests that need `work/` skip) and `make ledgers`;
- `make paper-text` and `make paper-pdf`.

To edit the paper, change `paper/sections/*.tex`. Every result number is a `\res{name}` macro, defined in
`paper/numbers.yaml` and generated from `artifacts/NA-14`; do not type result numbers by hand.

**Needs the data (operator's machine):**
- `make paper`, which regenerates the figures and tables;
- `make manifest`;
- any chunk run;
- any decision-model API call.

**Making changes:**
- Work on a branch (`feat/<topic>` or `fix/<topic>`) and open a pull request into `main`. The operator merges.
- Never edit or append to `ledgers/*.jsonl` by hand. They are hash-chained and written only by the operator's runs.
- After the NA-11 freeze, `docs/PREREG.md`, `configs/` and the analysis spec and targets code do not change. A
  deviation is appended to the PREREG §15 log (CLAUDE.md rule 11).
- The history was rewritten for the upload on 2026-10-30. Commit hashes cited in older documents and in the ledgers'
  `git_sha` fields are the pre-upload ones; `docs/COMMIT_MAP.tsv` maps them to the current commits.

## Running a chunk

1. Start from an up-to-date `main` and a **fresh** Claude Code session in this directory.
2. Paste the chunk's *Power prompt* from the PRD. It works on branch `feat/NA-xx-<slug>`, commits
   there (Conventional Commits) and ends with a self-audit in `artifacts/NA-xx/REPORT.md`.
3. In **another fresh session**, paste the chunk's *Verification prompt*. Verifiers are read-only,
   restore any mutation they make and spend nothing.
4. The operator merges the branch into `main` only after the verifier's PASS.

## Make targets

| Target | What it does |
|---|---|
| `make sync` | `uv sync --locked` |
| `make lint` | `ruff check` + `ruff format --check` on `src/`, `tests/`, `scripts/` |
| `make format` | apply `ruff format` and safe `ruff check --fix` |
| `make type` | `mypy --strict src/` |
| `make test` | `pytest -q -m "not network"` (warnings are errors) |
| `make manifest` | re-hash every artifact in `work/MANIFEST.json`, check `Data/` inputs (size + mtime), flag unregistered parquet files, compare each sha256 with `docs/DATA_CONTRACT.md` |
| `make manifest-deep` | as `manifest`, and re-hash every `Data/` input |
| `make ledgers` | verify the hash chain of every `ledgers/*.jsonl` |
| `make verify` | lint + type + test + manifest + ledgers |

## Guards (`src/newsaction/`)

| Module | Guard |
|---|---|
| `calendar` | XNYS sessions, open/close instants (half days, DST) and the decision windows W0 = (close(prev), 09:15 ET], W2 = (close(prev), close]; scalar and vectorized `session_of_w0/w2` (PREREG §2.4) |
| `timeutil` | timestamp precision class and availability time t_avail (PREREG §2.2–2.3) |
| `pit` | availability registry (`configs/availability.yaml`): `check_inputs(columns, "D0"/"D1"/"D2")`, `assert_visible` |
| `lock` | blinding of 2026 data: `sealed_path` / `read_sealed` (logged in `ledgers/test_access.jsonl`), `freeze` (NA-11), `require_unblind` (NA-12) |
| `ledger` | append-only, hash-chained ledgers: spend with hard caps (PREREG §13), trials, test access, FMP requests |
| `io` | hashed parquet I/O, `work/MANIFEST.json`, fingerprints of every `Data/` input read; `register_artifact` for committed outputs under `artifacts/` |
| `dm.client` | the only path to a decision model (OpenRouter Decisions API or local Laya): refusals (third-party, test period before the freeze, val-B gate, unmasked states, eligibility, `:free`), the sha256 response cache (`cache/decisions.sqlite`), dry runs and the spend ledger with hard caps, retries, `data_collection: deny`, offline mode for verifiers (CLAUDE.md C12–C14); `chat_json` (NA-09) sends chat completions with a strict JSON schema through the same refusals, cache, budget and offline mode, to `frozen.yaml` `chat_models` only |
| `tournament` | PREREG §8.2–8.3 model selection on val-A only: nested seeded samples without the embargo, the Model Confidence Set (stationary bootstrap over days), mechanical screens whose thresholds come from `configs/tournament.yaml` (= PREREG §8.3), rule-based counterfactual edits; `allow_val_b` is set only after every NA-06 call (CLAUDE.md B9, C13) |
| `encoding` | PREREG §8.4 encoding and anchoring rules: search on val-A only, val-B read only for the confirmation check and only when the val-A best is not E3 (`run.targets` refuses otherwise); thresholds from `configs/encoding.yaml` (= PREREG §8.4, parsed from its text by the tests); the numeracy probe is outcome-free (synthetic reaction blocks) |
| `baselines` | PREREG §10 baselines in one validated prediction schema: fit on train only and tuned on val-A only (fit records checked before anything is written), inputs checked with the availability registry (vendor fields only as the pre-registered signals), metrics on val-A only, no D2 or price-only test prediction before the freeze (CLAUDE.md A5–A6, B8–B9) |

Each guard has tests that fail when the guard is removed (`tests/`).
