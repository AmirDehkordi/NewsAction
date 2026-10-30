# NewsAction — decision models × financial news (research repository)

## What this project is

NewsAction is a research project for an **AI-first, look-ahead-free paper**. The paper asks whether **decision models** can do two things:

- read pre-open company news and anticipate the market's reaction;
- judge, once part of the reaction is visible, whether the market over- or under-reacted. This includes important news that produced only a small move.

A decision model is a non-generative model: it takes a `state` plus typed questions (`choice` / `score` / two-option yes/no) and returns calibrated probabilities. Examples are TypeSafe Jev, Convai Laya and OpenAI's Decisions API.

It follows the team's AI4F'26 paper "Buy the Rumor, Sell the News" (arXiv 2608.14014). Other inspirations:
- Kelly–Su–Zhang (2026), "Explaining Realized Returns: Roll's R² 40 Years Later".
- JevAgentHarness (arXiv 2610.21412).
- Wegmann et al.'s survey on representing linguistic style.
- Chen–Kelly–Xiu, "Expected Returns and LLMs".

The work is delivered as chunks NA-00…NA-15 in `NewsAction PRD.md`:
- Each chunk is one session: run its **power prompt**, then its **verification prompt** in a separate, independent session.
- `docs/PREREG.md` is the pre-registration. Every definition, constant, split, hypothesis and selection rule lives there; read it before changing anything substantive.
- Its §15 holds **operative amendments**. Read §15 in full in every chunk. Currently:
  - **A1 — convergence to the news-implied value:** the model's value V, the price–value gap, the open→t+20 ladder, the S-CONV trade.
  - **A2 — question battery v2:** core / extended / explain question groups.
  - **A3 — explaining realized moves:** the firm-level Kelly–Su–Zhang-style analysis.

## Quick facts

- **Root:** `/Users/amir/Research/NewsAction`. Python 3.12, a `uv` project named `newsaction` (code in `src/newsaction/`), with its own environment (needs pandas ≥ 3).
- **Raw data (READ-ONLY):** `Data/`. See `Data/README.md`.
  - `news_YYYY.parquet`: NewsWitch, 4.69M articles, 2020-01..2026-07-31.
  - `embeddings/` (bge-small, 384-d).
  - `prices/`: adjusted close + volume, 2,638 symbols; rolling betas.
  - `market/`: SPY/sector ETF/VIX/DXY/oil closes, FRED pickles, earnings dates, shares.
- **ATOM** (`/Users/amir/GitHub/Atom`, Postgres in docker `atom_postgres`) is **read-only** for us. NA-01 exports one hashed snapshot to `work/snapshot/` using ATOM's own venv (`/Users/amir/GitHub/Atom/.venv/bin/python`) and its PIT accessors. No other chunk touches ATOM.
- **Universe:** S&P 500 point-in-time members (`uni.member`, code `sp500`), in tiers Top-100 / 101–250 / 251–500 by prior-month-end market cap.
- **Splits** (PREREG §4): train 2024-07-01→2025-06-30 · val-A 2025-07-01→2025-09-30 · val-B 2025-10-01→2025-12-31 · **test 2026-01-02→2026-07-31 (blinded)**.
- **Budgets:**
  - OpenRouter: **hard cap $30 total**, plus per-chunk caps from the PRD.
  - FMP: ≤ 17,000 requests (raised from 3,000 by the operator; PREREG §15, NA-10 rows), and only in NA-10.
  - Kaggle: free 2×T4 (NA-08).
- **GitHub:** private `origin` https://github.com/AmirDehkordi/NewsAction (2026-10-30), shared with the team.
  - It never holds `Data/`, `work/`, `cache/`, `.env` or NewsWitch text: `artifacts/NA-02/{spam_judgments,detector_eval}.csv`
    are gitignored and stay on the operator's machine.
  - `ledgers/spend.jsonl` is stored in Git LFS (it is over GitHub's 100 MB file limit).
  - The history was rewritten for the upload. Commit hashes cited before 2026-10-30 (REPORTs, decisions, commit messages,
    the ledgers' `git_sha`) are old ones; `docs/COMMIT_MAP.tsv` maps them to the current commits.
- **Secrets** live in `.env` (gitignored): `OPENROUTER_API_KEY`, `ATOM_DB_PASSWORD`, `FMP_API_KEY`. Never print, log or commit them.

## Standard commands (created in NA-00)

```bash
make sync      # uv sync
make lint      # ruff check + ruff format --check
make type      # mypy --strict src/
make test      # pytest -q (fast; no network)
make verify    # lint + type + test + snapshot/manifest check
make manifest  # recompute and compare work/MANIFEST.json hashes
```

## Repository layout

```
CLAUDE.md, NewsAction PRD.md, README.md, pyproject.toml, uv.lock, Makefile, .env.example
docs/PREREG.md          pre-registration (frozen in NA-11; deviations log at the end)
docs/DATA_CONTRACT.md   schema + sha256 of every derived artifact (each chunk appends)
docs/decisions/NA-xx.md per-chunk decisions and findings
configs/                project.yaml, splits.yaml, questions_v1.yaml, codebook_v1.yaml, frozen.yaml
src/newsaction/         paths, config, calendar, timeutil, pit, lock, ledger, io, panel/, news/, events/,
                        states/, dm/, tournament/, encoding/, train/, baselines/, bars/, production/,
                        analysis/, strategy/, figures/
scripts/                CLIs (export_atom_snapshot.py runs under ATOM's venv)
tests/                  pytest; one test per guard; golden cases
work/                   derived data (gitignored): snapshot/, market/, panel/, news/, events/, states/,
                        dm/, kaggle/, bars30/, analysis/
artifacts/NA-xx/        committed small outputs: REPORT.md, tables, figure CSVs and PDFs
ledgers/                committed append-only JSONL: spend, trials, test_access, fmp_requests
cache/                  decision-model response cache (sqlite; gitignored)
```

## Non-negotiable rules

### A. Time and look-ahead (point-in-time)

1. **Every input to a decision at time τ must have been available at or before τ.** Use `newsaction.calendar` (session open/close instants, half days, DST) and `newsaction.timeutil.availability()`. Never write literal "16:00" / "09:30" offsets.
2. **News availability** (PREREG §2):
   - Date-only timestamps (exactly 00:00:00 UTC) are available at **23:59:59 UTC of that date**.
   - Hour-rounded timestamps (mm:ss = 00:00) are available at the **end of that hour**.
   - The D0 news window for session s is (close of the previous session, **09:15 ET** of s].
3. **Rolling statistics end at t−1.** This covers β, σ, volume baselines, tiers (prior month-end), percentiles and context words. A planted +50σ return on day t must not change anything dated t.
4. **No price levels, tickers, company names, people, dates, years or fiscal-quarter labels in model states** (masking, PREREG §6.3). Every number in a state goes through the codebook (`configs/codebook_v1.yaml`).
5. **The availability registry** (`newsaction.pit`) declares, for every column, when it becomes known. State builders call `check_inputs()`. Passing a post-decision column must raise.
6. **Vendor labels** (tags, sentiment, summaries, `event_id` clusters) were produced retrospectively. Use them **only for selecting news**, never as model text, except in the pre-registered ablations.
7. Never use `Data/prices/universe.csv` `included` or vendor ticker lists as filters. **Membership comes only from `uni.member`.**

### B. Blinding and pre-registration

8. **No statistic, plot or printout of any return for sessions ≥ 2026-01-02 before the NA-11 freeze.**
   - 2026 prices live in `work/snapshot/sealed/`.
   - They are read **only** through `newsaction.lock` (`build_reactions` after the freeze; `load_targets` after unblinding with `NA_UNBLIND=1`). Every read is appended to `ledgers/test_access.jsonl`.
9. **Everything selected on validation stays on validation.**
   - Search runs on val-A.
   - Confirmation and final selection run on val-B.
   - Calibration and temperatures are fit on val-A only, with the fitted date range stored.
   - The test period is used once.
10. **Log every evaluated variant** (model, encoding, filter, threshold, strategy) in `ledgers/trials.jsonl`; the deflated Sharpe uses this count.
11. **Deviations from PREREG:** append them to the "Deviations log" in `docs/PREREG.md` with date, chunk and reason. Never edit earlier sections silently. After the freeze, a deviation is reported as a deviation.

### C. Decision-model API (OpenRouter) and budget

12. **Every API call goes through `newsaction.dm.client`.** It provides:
    - the sha256 cache (model + state + questions + params);
    - the append-only spend ledger and the hard cap;
    - retries;
    - `provider: {"data_collection": "deny"}`.

    Before any batch, run a **dry run** with the projected cost. If a call would cross the chunk cap or the $30 total, the batch must refuse (STOP and report).
13. **Restricted endpoints and dates:**
    - No `:free` endpoints or endpoints requiring data collection without the operator's written approval.
    - No test-period (2026) state is sent before the NA-11 freeze.
    - No val-B state is sent, and no val-B metric is computed, until NA-06 sets `allow_val_b: true` in `configs/frozen.yaml`.
14. **Verification sessions run the client in `offline=True` mode** (cache only). They spend $0.

### D. Data governance

15. **Articles with `parsing_allowed == False` are never sent to any third party** (OpenRouter, Kaggle) in any form. NewsWitch text is proprietary.
16. **Kaggle datasets are PRIVATE** and contain only masked states plus train and val-A labels.
    - Val-B and test labels never leave this machine.
    - Nothing is pushed to the Hugging Face Hub.

### E. External systems

17. **ATOM is read-only** (NA-01's snapshot export only). Never write to the ATOM DB or repo.
18. **FMP is used only in NA-10:**
    - 30-min bars, never 1-minute;
    - ≤ 17,000 requests total (raised from 3,000 by the operator after FMP proved to serve 30 days per
      30-minute request; PREREG §15, NA-10 rows; 15,858 used), logged in `ledgers/fmp_requests.jsonl`;
    - if more would be needed, STOP and ask.
19. **`Data/` is read-only.** All derived data goes under `work/` and is registered in `work/MANIFEST.json` and `docs/DATA_CONTRACT.md`.

### F. Reproducibility

20. Set seeds wherever randomness is used. Every derived file has a sha256 in the manifest. Configs are hashed into every run record.
21. Chunks communicate only through files listed in `docs/DATA_CONTRACT.md`. A chunk never relies on another session's memory.
22. **Charts:** before writing any chart code, invoke the `dataviz` skill. Every figure ships with the CSV of its plotted data.

### G. Code quality

23. Type hints everywhere. `mypy --strict src/`, `ruff check`, `ruff format`.
24. **Tests come with every guard:**
    - each guard has a test that fails if the guard is removed (the verification prompt mutates it);
    - golden cases for calendar and adjustment edge cases.
25. No notebooks in `src/` (the Kaggle notebook lives under `src/newsaction/train/notebook/` as an artifact and is exported, not imported).

### H. Git and workflow

26. **One chunk = one branch** `feat/NA-xx-<slug>`, cut from `main`.
    - Use Conventional Commits (`feat(NA-03): …`).
    - Commit on the branch; **do not merge to main**. The operator merges after the verification PASS.
    - No remote push unless asked.
27. **Every chunk ends with a self-audit** (below) and writes `artifacts/NA-xx/REPORT.md` and `docs/decisions/NA-xx.md`.

## Self-audit (end of every chunk)

1. Scope items S1…Sn: done or not done, with file paths.
2. Acceptance criteria table: AC id, evidence (command plus the observed number), PASS/FAIL.
3. Spend this chunk and cumulative (from `ledgers/spend.jsonl`); FMP requests used.
4. Look-ahead self-check: list every input used and its availability time.
5. Deviations from PREREG (and whether they were logged).
6. STOP conditions evaluated and which fired; owner decisions needed.
7. Files added or changed; tests added; `make verify` output summary.

## When uncertain

Ask the operator; do not guess. In particular, ask about anything that would:
- spend more than a chunk's cap;
- touch 2026 outcomes before the freeze;
- change a PREREG definition;
- send proprietary text to a new third party;
- exceed the FMP request cap.

Better one question than a contaminated result.
