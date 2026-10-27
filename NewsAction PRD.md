# NewsAction PRD — Decision models × financial news (chunks NA-00 … NA-15)

> **How to use this document.**
> 1. For each chunk, in the order below, open a **fresh Claude Code session** in `/Users/amir/Research/NewsAction` and paste the chunk's **Power prompt**.
> 2. When the session ends with its self-audit, open **another fresh session** and paste the **Verification prompt**.
> 3. Merge the chunk branch into `main` only after the verifier's PASS.
>
> Sessions share nothing except files: `CLAUDE.md`, `docs/PREREG.md`, `docs/DATA_CONTRACT.md`, `configs/`, `work/`, `artifacts/`, `ledgers/`.

**Owner:** operator (you). **Written:** 2026-10-24. **Rules:** `CLAUDE.md`. **Pre-registration:** `docs/PREREG.md` (v0; frozen in NA-11).

## Why this program exists

The team's AI4F'26 paper showed three things:
- news is mostly priced in before and at publication;
- markets underreact to quantified news and overreact to stories;
- news widens volatility.

This program asks whether **decision models** can turn that into calibrated, look-ahead-free judgments. A decision model is non-generative: a `state` plus typed questions go in, and probabilities come out (TypeSafe Jev, Convai Laya, OpenAI Decisions, and ~25 other models on OpenRouter). The questions are:
- **Before the open:** how will the market react to this news?
- **After part of the reaction:** was that reaction too small or too large? This includes important news that moved the stock only a little.

Paper framing:
- **AI-first:** the first use of decision models in asset pricing, plus a contamination-robust evaluation protocol and a trained, calibrated finance decision model (Laya-Fin).
- **Finance evidence:**
  - do prices **converge to the decision model's valuation of the news** (from the open to t+20), and is the price–value gap tradeable;
  - "explained moves persist, unexplained moves reverse";
  - how much of each stock's move its news can explain (Kelly–Su–Zhang's question at the firm level);
  - the value of news vs. price information;
  - size tiers.

## Execution order and budgets

```
NA-00 → NA-01 → NA-02 → NA-03 → NA-04 → NA-05 → NA-06 → NA-07 ─┐
                                    │                            ├→ NA-11 → NA-12 → NA-13 → NA-14
                                    ├→ NA-08 (Kaggle, parallel) ─┤
                                    └→ NA-09 (baselines) ────────┤
          NA-01 + NA-04 → NA-10 (30-min bars) ───────────────────┘          NA-15 (later, new data)

val-B gate: nothing reads val-B outcomes until NA-06 sets configs/frozen.yaml allow_val_b = true. NA-07, NA-09's
LLM run and NA-11 use val-B after that; NA-08 and NA-09 produce val-B predictions earlier but compute no val-B metric.
```

| ID | Chunk | Depends | OpenRouter cap | Other budget |
|---|---|---|---|---|
| NA-00 | [Chore] Scaffold, time/lock/ledger primitives, PREREG v0 | — | $0 | — |
| NA-01 | [Build] ATOM snapshot, adjusted daily panel, tiers, sealed 2026 | 00 | $0 | ATOM read-only |
| NA-02 | [Build] News timing audit, mapping, cleaning, re-embedding, novelty | 00, 01 | $0 | local MPS |
| NA-03 | [Research] Importance filters, material label, events | 01, 02 | $0 | — |
| NA-04 | [Build] States: context, codebook, masking, questions v1 | 01–03 | $0 | — |
| NA-05 | [Build] Decision-model client, cache, budget guard, catalog, canary, Laya local, pilot | 04 | $0.20 | — |
| NA-06 | [Research] Zero-shot tournament + contamination probes | 05 | $4 | — |
| NA-07 | [Research] Encoding and anchoring study | 06 | $2 | — |
| NA-08 | [Build] Trained decision models on Kaggle (Laya-Fin + ModernBERT anchor) | 04 | $0 | Kaggle free 2×T4 |
| NA-09 | [Build] Baselines (incl. generative LLM at matched cost) | 04 | $2 | — |
| NA-10 | [Build] 30-min bars (FMP, ≤ 3,000 requests), D1 inputs | 01, 04 | $0 | FMP ≤ 17,000 req (raised from 3,000; PREREG §15 NA-10) |
| NA-11 | [Run] Final selection, **freeze**, production, ablations | 06–10 | $18 | Kaggle inference |
| NA-12 | [Research] Unblinding and pre-registered analyses | 11 | $0 | — |
| NA-13 | [Research] Strategies and economic significance | 12 | $0 | — |
| NA-14 | [Paper] Charts, tables, replication package | 12, 13 | $0 | — |
| NA-15 | [Run, later] Forward test on post-release news | 14 + new data | $2 | — |

**Total OpenRouter: ≤ $28.2 + $1.8 reserve = $30 hard cap** (PREREG §13).

## Conventions shared by every chunk

- **Repository:** `/Users/amir/Research/NewsAction` (git, created in NA-00). Branch `feat/NA-xx-<slug>` cut from `main`. Conventional Commits (`feat(NA-03): …`). Commit on the branch; **never merge yourself**.
- **Read first, every chunk:** `CLAUDE.md`; the PREREG sections listed in the prompt; **PREREG §15 in full**, which holds the operative amendments (currently **A1** convergence to the news-implied value — NA-01, 03, 10, 11, 12, 13, 14; **A2** question battery v2 — NA-03, 04, 05, 06, 11, 12; **A3** explaining realized moves, Kelly–Su–Zhang style — NA-02, 04, 08, 11, 12, 14); `docs/DATA_CONTRACT.md`; and the REPORT of each dependency (`artifacts/NA-yy/REPORT.md`).
- **Outputs:**
  - Every derived file is written with `newsaction.io.write_parquet` (sha256 in `work/MANIFEST.json`) and gets a `docs/DATA_CONTRACT.md` entry: path, producer, schema, key, availability semantics, sha256.
  - Every chunk writes `artifacts/NA-xx/REPORT.md` and `docs/decisions/NA-xx.md`.
- **Ledgers** (`ledgers/`, append-only, committed): `spend.jsonl`, `trials.jsonl`, `test_access.jsonl`, `fmp_requests.jsonl`.
- **STOP conditions are findings.** When one fires, write it in the REPORT and stop; do not redesign. The operator decides.
- **Verification sessions:**
  - read-only, except temporary mutations, which must be restored (`git status` must show only the author's changes);
  - API client in `offline=True` mode (cache only, $0 spend);
  - no FMP calls, no Kaggle runs.

### Global acceptance criteria (every chunk; every verifier checks them)

- **GAC1:** `make verify` exits 0.
- **GAC2:** nothing under `Data/` changed (`git status --porcelain Data/` is empty; spot-check the sha256 of two Data files against `work/MANIFEST.json` `inputs`).
- **GAC3:** no code reads sessions ≥ 2026-01-02 outside `newsaction.lock`.
  - Test `tests/test_blinding.py` scans `src/` for date literals ≥ "2026-01" and for any read of `work/snapshot/sealed/` outside `lock.py`.
  - `ledgers/test_access.jsonl` contains no unexpected entries.
- **GAC4:** the spend ledger reconciles (Σ recorded cost = Σ `usage.cost` in the cache for this chunk's calls); chunk spend ≤ chunk cap; total ≤ $30.
- **GAC5:** every new artifact appears in `docs/DATA_CONTRACT.md` with a sha256 equal to `work/MANIFEST.json`.

### Operator checklist

| When | Action |
|---|---|
| Before NA-00 | Nothing (no keys needed). |
| Before NA-01 | ATOM stack up (`docker ps` shows `atom_postgres`). Put `ATOM_DB_PASSWORD` (the value of `POSTGRES_PASSWORD` in `~/GitHub/Atom/.env`) into `NewsAction/.env`. |
| Before NA-05 | Put `OPENROUTER_API_KEY` into `.env`; add ≥ $10 credit (top up as chunks need, within the $30 cap). Decide how `parsing_allowed == None` articles are treated (NA-02 reports the share). |
| Before NA-08 | Kaggle account with phone verification (GPU access); API token at `~/.kaggle/kaggle.json` (chmod 600). |
| Before NA-10 | Put `FMP_API_KEY` (from ATOM's `.env`) into `.env`. |
| Before NA-15 | Export NewsWitch news for 2026-08-01 → latest into `Data/` (new files; never overwrite existing ones). |

---

## NA-00 — [Chore] Repository scaffold, time / lock / ledger primitives, PREREG v0

**Category:** Phase 0 — foundation. Its deliverable is the **guards every later chunk relies on**: the calendar windows, the timestamp-availability rule, the availability registry, the blinding lock, the spend/trial/access ledgers and the hashed artifact I/O. These come with tests that fail if any guard is removed. No data analysis.

**Goal:**
- Turn the folder into a `uv`-managed, git-tracked Python 3.12 project with `make verify`.
- Implement and test `calendar`, `timeutil`, `pit`, `lock`, `ledger` and `io` exactly as PREREG §2 and §4 define them.
- Convert the `Data/market` pickles (they need pandas ≥ 3) to parquet.
- Commit CLAUDE.md, PREREG v0 and this PRD; tag `prereg-v0`.

**Dependencies:** none. Consumed by every chunk. · **Estimated time:** 1 day · **Branch:** `feat/NA-00-scaffold`

**Expected outputs:**
- **New:**
  - `pyproject.toml`, `uv.lock`, `Makefile`, `.gitignore`, `.env.example`, `README.md`.
  - `configs/project.yaml`, `configs/splits.yaml`, `configs/availability.yaml`, `configs/frozen.yaml` (skeleton).
  - `src/newsaction/{__init__,paths,config,calendar,timeutil,pit,lock,ledger,io}.py`.
  - `scripts/convert_pickles.py`; `work/market/*.parquet`; `work/MANIFEST.json`.
  - `docs/DATA_CONTRACT.md`, `docs/decisions/NA-00.md`, `artifacts/NA-00/REPORT.md`.
  - `ledgers/{spend,trials,test_access,fmp_requests}.jsonl` (empty).
  - `tests/test_calendar.py`, `test_timeutil.py`, `test_pit.py`, `test_lock.py`, `test_ledger.py`, `test_io.py`, `test_configs_match_prereg.py`, `test_blinding.py`.
- **Not touched:** `Data/`, ATOM.

**Current state (verified 2026-10-24):**
- `/Users/amir/Research/NewsAction` holds `Data/` (news 2020–2026-07, embeddings, prices, market; 13 GB), `CLAUDE.md`, `docs/PREREG.md` and this PRD. It is **not** a git repository; there is no Python project.
- The ATOM venv has pandas 2.3.3. `Data/market/fred_releases.pkl` fails there with `NotImplementedError` (datetime64[us] pickled by pandas 3) and loads with pandas 3.1.0 (`uv run --with "pandas>=3"`).
- `uv` is at `/Users/amir/.local/bin/uv`.
- No `OPENROUTER_API_KEY` in the shell; no `~/.kaggle`.
- NYSE 2024–2026 facts for the calendar golden tests:
  - half days 2024-07-03, 2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28, 2025-12-24 (close 13:00 ET);
  - unscheduled closure 2025-01-09 (national day of mourning);
  - DST starts 2024-03-10 / 2025-03-09 / 2026-03-08 and ends 2024-11-03 / 2025-11-02.

### Power prompt — NA-00

```text
You are implementing NA-00 (scaffold + guards) for the NewsAction research repo at /Users/amir/Research/NewsAction.
This chunk builds FOUNDATION ONLY: project, configs, and the tested primitives every later chunk depends on. No data
analysis, no network calls, no ATOM access, no writes under Data/.

Read first:
  - CLAUDE.md (all of it — these rules bind you)
  - docs/PREREG.md §2 (time conventions), §4 (splits, purge, embargo, blinding, freeze), §13 (budget)
  - NewsAction PRD.md → "Conventions shared by every chunk" and "Global acceptance criteria"
  - Data/README.md (what is in Data/; never modify it)

Branch: run `git init -b main` first (the folder is not yet a repo), commit the three existing docs on main as
"chore: initial docs", then create branch feat/NA-00-scaffold.

## Scope

S1. GIT + IGNORE. .gitignore must exclude: Data/, work/, cache/, .env, *.sqlite, .venv/, __pycache__/, .mypy_cache/,
    .ruff_cache/, kaggle.json, *.ckpt, *.safetensors. ledgers/ and artifacts/ ARE committed.

S2. UV PROJECT. pyproject.toml: name "newsaction", requires-python ">=3.12,<3.13", src layout (src/newsaction).
    Runtime deps: pandas>=3, pyarrow, numpy, scipy, statsmodels, scikit-learn, lightgbm, pydantic>=2, pyyaml, httpx,
    tenacity, exchange-calendars, arch, matplotlib, tqdm, filelock. Dev group: pytest, pytest-cov, hypothesis, ruff,
    mypy, pandas-stubs, types-PyYAML. Optional groups declared now but NOT installed here: "embed" (torch,
    sentence-transformers, transformers, spacy), "laya" (laya), "kaggle" (kaggle). `uv sync` must succeed.

S3. MAKEFILE targets: sync, lint (ruff check + ruff format --check), format, type (mypy --strict src/), test
    (pytest -q -m "not network"), verify (lint+type+test+manifest), manifest (verify every sha256 in
    work/MANIFEST.json).

S4. CONFIGS (values must equal PREREG; a test enforces it):
    - configs/project.yaml: timezone America/New_York; exchange XNYS; d0_cutoff "09:15"; d1_time "10:00";
      budget: total_usd 30.0 and per-chunk caps {NA-05: 0.20, NA-06: 4.0, NA-07: 2.0, NA-09: 2.0, NA-11: 18.0,
      NA-15: 2.0}; fmp_request_cap 3000; seeds {global: 2026}.
    - configs/splits.yaml: robustness 2024-01-02..2024-06-28; train 2024-07-01..2025-06-30; val_a 2025-07-01..
      2025-09-30; val_b 2025-10-01..2025-12-31; test 2026-01-02..2026-07-31; embargo_sessions 5; max_horizon 20.
    - configs/availability.yaml: the registry skeleton (S7) with kinds and a few seed entries.
    - configs/frozen.yaml: skeleton with null sections {news, filter, encoding, anchoring, tournament, selection,
      thresholds, calibration, allow_val_b: false, frozen: false}.
    - src/newsaction/config.py: pydantic models + loaders; src/newsaction/paths.py: ROOT, DATA, WORK, ARTIFACTS,
      LEDGERS, CACHE, CONFIGS, SEALED = WORK/"snapshot"/"sealed".

S5. CALENDAR — src/newsaction/calendar.py on exchange_calendars "XNYS" (pin the library version in pyproject).
    Functions (all tz-aware UTC in/out; dates are exchange-local `datetime.date`):
      sessions(start, end) -> list[date]; is_session(d); prev_session(d); next_session(d);
      open_utc(d); close_utc(d) (13:00 ET on half days); is_half_day(d);
      d0_cutoff_utc(d) (09:15 ET of d); d1_utc(d) (10:00 ET);
      window_w0(d) -> (start_exclusive=close_utc(prev_session(d)), end_inclusive=d0_cutoff_utc(d));
      window_w2(d) -> (close_utc(prev_session(d)), close_utc(d));
      session_of_w0(ts) / session_of_w2(ts) -> date | None (vectorized versions for pandas Series).
    If exchange_calendars lacks the 2025-01-09 closure, add an explicit override list in calendar.py and document it.
    Never hard-code UTC offsets; never write "16:00"/"09:30" literals outside this module.

S6. TIMEUTIL — src/newsaction/timeutil.py: precision_class(unix_seconds) -> {"date_only","hour","minute","exact"}
    and availability(unix_seconds) -> UTC timestamp per PREREG §2.2–2.3 (vectorized for pandas). date_only →
    23:59:59 UTC of that date; hour → +3599 s; minute → +59 s; exact → unchanged.

S7. PIT — src/newsaction/pit.py: class AvailabilityRegistry loaded from configs/availability.yaml mapping column
    name → kind ∈ {"static","t_minus_1","w0","w2","d1","post"}; check_inputs(columns, decision_point) raises
    PITError if any column's kind is not allowed for that decision point (D0 allows static,t_minus_1,w0; D1 adds d1;
    D2 adds w2 and "d2_reaction"; nothing allows "post"). assert_visible(df, ts_col, decision_ts_col) raises if any
    row has ts > decision ts. Unknown columns raise (registry must be explicit).

S8. LOCK — src/newsaction/lock.py:
      FREEZE_FILES = [docs/PREREG.md, configs/*.yaml, src/newsaction/panel/targets.py,
                      src/newsaction/panel/reactions.py, src/newsaction/analysis/spec.py] (missing files hash as "ABSENT");
      compute_freeze_hash(); freeze(note) (writes artifacts/NA-11/freeze.json — only callable when
      configs/frozen.yaml has frozen_requested: true; NA-11 sets it); is_frozen(); require_frozen();
      require_unblind() (frozen AND current hash == recorded hash AND os.environ.get("NA_UNBLIND") == "1");
      sealed_path(name, purpose: Literal["reactions","targets"]) → Path: purpose "reactions" requires frozen,
      "targets" requires unblind; EVERY call (allowed or refused) appends {ts, caller, name, purpose, allowed,
      git_sha} to ledgers/test_access.jsonl.

S9. LEDGERS — src/newsaction/ledger.py: append-only JSONL with filelock + fsync.
      SpendLedger(chunk_id): reserve(est_usd) raises BudgetExceeded if cumulative_total + est > total cap or
      chunk_total + est > chunk cap (caps from configs/project.yaml); record(actual_usd, meta); totals();
      reconcile(cache_costs) → difference. TrialLedger.log(record) (fields: chunk, kind, name, params_hash, split,
      metric, value). AccessLedger (used by lock). FmpLedger (count, cap).

S10. IO — src/newsaction/io.py: write_parquet(df, relpath, *, producer, description) writes under work/, computes
     sha256, rows, columns, git sha, and upserts work/MANIFEST.json; read_parquet(relpath, verify=True) re-hashes;
     manifest_check() used by `make manifest`. Also record sha256 of each Data/ input actually read in
     MANIFEST["inputs"] (path → sha256, size, mtime) the first time it is read.

S11. PICKLES — scripts/convert_pickles.py (runs in the NewsAction env, pandas>=3): Data/market/{fred_daily,
     fred_releases, earnings_dates, shares}.pkl → work/market/{fred_daily, cpi_vintages, earnings_dates,
     shares}.parquet in long format (series_id/date/value[/realtime_start]; ticker/earnings_ts; ticker/date/shares)
     via io.write_parquet; plus work/market/market_prices.parquet copied from Data/market/market_prices.parquet
     (registered as an input). Row-count equality test against the pickles.

S12. DOCS — README.md (what the repo is; how to run a chunk; make targets); docs/DATA_CONTRACT.md (template +
     entries for every NA-00 artifact); docs/decisions/NA-00.md; artifacts/NA-00/REPORT.md (self-audit).

S13. BLINDING TEST — tests/test_blinding.py: (a) scans src/ (excluding lock.py) for string literals matching
     2026-0[1-9]|2026-1[0-2] and for "sealed" path usage → must be absent; (b) asserts sealed_path raises before
     freeze for both purposes and that each attempt is logged.

S14. PREREG TAG — after all tests pass, commit on the branch; the operator will merge. Create annotated tag
     prereg-v0 on the commit that contains docs/PREREG.md v0 (on main's "chore: initial docs" commit).

## Acceptance criteria

- AC1 — `make verify` exits 0 (ruff, format check, mypy --strict src/, pytest, manifest). FAILS BEFORE: no project.
- AC2 — CALENDAR GOLDEN CASES (tests/test_calendar.py): window_w0(2024-03-11) == (2024-03-08 21:00Z,
  2024-03-11 13:15Z]; window_w0(2024-11-04) starts 2024-11-01 20:00Z (EDT) and ends 2024-11-04 14:15Z (EST);
  close_utc(2024-11-29) == 18:00Z and window_w0(2024-12-02) starts there; window_w0(2024-01-16) starts
  2024-01-12 21:00Z (MLK Monday closed); 2025-01-09 is not a session and window_w0(2025-01-10) starts
  2025-01-08 21:00Z; close_utc(2025-07-03) == 17:00Z. MUTATION: replace close_utc with a constant 21:00Z →
  RED; MUTATION: compute the 09:15 cutoff as 14:15Z fixed → RED on the EDT case.
- AC3 — AVAILABILITY: unit + hypothesis tests for every precision class (availability ≥ publication; date_only maps
  to 23:59:59Z of the same date; hour adds 3599 s). MUTATION: delete the date_only branch → RED.
- AC4 — PIT REGISTRY: check_inputs(["z_id"], "D0") raises (z_id registered as "post"); unknown column raises;
  assert_visible raises on a planted future row. MUTATION: make check_inputs a no-op → RED.
- AC5 — LOCK: before freeze, sealed_path(…, "reactions") and (…, "targets") raise LockError and each attempt
  appends a refused entry to ledgers/test_access.jsonl (test uses a temp ledger path). MUTATION: make is_frozen()
  return True → RED.
- AC6 — LEDGER: SpendLedger.reserve refuses when total or chunk cap would be exceeded; concurrent appends from 4
  processes produce valid JSONL. MUTATION: remove the chunk-cap comparison → RED.
- AC7 — CONFIGS MATCH PREREG: tests/test_configs_match_prereg.py asserts every split date, the 09:15 cutoff, the
  caps and fmp_request_cap equal the PREREG values (hard-coded in the test with a PREREG § reference).
- AC8 — PICKLES: converted row counts equal the pickles' (per series/ticker); `make manifest` verifies hashes.
- AC9 — GIT: repo on main with "chore: initial docs"; tag prereg-v0 exists and `git show prereg-v0:docs/PREREG.md`
  equals the committed v0; .gitignore excludes Data/ work/ cache/ .env (test: `git check-ignore` on each).

## Constraints

- No network (except `uv sync` for packages), no ATOM, no OpenRouter, no FMP, no Kaggle. No writes under Data/.
- Python 3.12; type hints everywhere; mypy --strict on src/; ruff; no notebooks.
- Every guard has a test that fails if the guard is removed (the verifier will mutate them).
- Do not modify docs/PREREG.md content (only commit it). If you find an inconsistency, append it to the PREREG
  Deviations log with your reasoning and flag it in the REPORT.
- Conventional Commits; commit on feat/NA-00-scaffold; do NOT merge to main.
- End with the CLAUDE.md self-audit, written to artifacts/NA-00/REPORT.md and printed.
```

### Verification prompt — NA-00

```text
Independent verifier for NA-00 at /Users/amir/Research/NewsAction (branch feat/NA-00-scaffold). READ-ONLY: you may
run commands and temporarily edit files for mutation checks, but restore everything (`git status` must show only
the author's committed state at the end) and make no commits. No network beyond what `uv sync` already cached.

The implementations most likely to ship wrong: (i) a calendar that hard-codes UTC offsets (breaks across DST and
half days), (ii) a lock that is "enforced" only by convention, (iii) ledgers that are not actually append-only.

1. STATIC GATES: `make verify` → exit 0. Report test count and mypy/ruff status.
2. CALENDAR, INDEPENDENTLY: in `uv run python`, using exchange_calendars directly (not the repo module), compute
   the close of 2024-11-29, the sessions around 2025-01-09, and the W0 windows for 2024-03-11, 2024-11-04,
   2024-12-02, 2025-07-07; compare with newsaction.calendar outputs. Any mismatch fails AC2.
3. AVAILABILITY: compute availability() for 1735689600 (2025-01-01 00:00:00Z), 1735693200 (01:00:00Z),
   1735693260, 1735693261; expected 23:59:59Z same day, +3599 s, +59 s, unchanged.
4. MUTATIONS (restore after each): (a) calendar close_utc → constant 21:00Z; (b) delete the date_only branch;
   (c) check_inputs → return None; (d) is_frozen → return True; (e) remove the chunk-cap check. Run `make test`
   after each: every one must turn RED. Any that stays green fails the corresponding AC.
5. LOCK LOGGING: call sealed_path("prices_raw_2026", "targets") in a temp-ledger context; confirm LockError and a
   refused entry with caller and git_sha.
6. CONFIGS vs PREREG: open docs/PREREG.md §2, §4, §13 and compare every number with configs/*.yaml by eye; list
   any discrepancy.
7. GIT: `git tag -n prereg-v0`; `git check-ignore Data work cache .env`; confirm Data/ is not tracked
   (`git ls-files Data | wc -l` == 0).
8. PICKLES: re-load one pickle with `uv run --with "pandas>=3"` and compare row counts with the parquet.
9. GAC1–GAC5 as applicable.

Verdict: PASS / FAIL per AC (AC1–AC9) and GAC, with the observed numbers and the mutation table. Numbers, not
"looks right".
```

**New tests to add:** `test_calendar.py` (golden windows, DST, half days, the 2025-01-09 closure), `test_timeutil.py` (property tests), `test_pit.py`, `test_lock.py`, `test_ledger.py` (cap and concurrency), `test_io.py` (manifest round trip), `test_configs_match_prereg.py`, `test_blinding.py`.

**Risks / notes:**
- `exchange_calendars` version drift can change half-day handling, so pin it and keep the golden tests.
- The lock is procedural. Its strength comes from logging plus verifier greps; that limitation is written in the REPORT.

---

## NA-01 — [Build] ATOM snapshot, adjusted daily panel, tiers, sealed 2026

**Category:** Phase 1 — data. One read-only export from ATOM (via ATOM's own venv and PIT accessors), then the daily panel every later chunk uses: adjusted returns, two-factor abnormal returns, β and σ through t−1, tiers, and targets **for sessions ≤ 2025-12-31 only**. All 2026 prices go to `work/snapshot/sealed/`.

**Goal:** a frozen, hashed snapshot and two panels:
- `work/panel/panel_public.parquet`: 2023-07-03 → 2025-12-31, features + targets.
- `work/panel/panel_test_inputs.parquet`: 2026 sessions, t−1 features only.

Both are built with code (`panel/targets.py`, `panel/reactions.py`) that refuses to touch 2026 outcomes until the NA-11 freeze.

**Dependencies:** NA-00. Consumed by NA-02 (sessions, membership), NA-03 (labels), NA-04 (context), NA-10, NA-11 (reactions), NA-12 (targets). · **Estimated time:** 1.5–2 days · **Branch:** `feat/NA-01-panel`

**Expected outputs:**
- **New:**
  - `scripts/export_atom_snapshot.py` (runs with ATOM's venv).
  - `work/snapshot/{members_by_session,symbol_tickers,symbols,gics,prices_raw,total_return_check,corporate_actions,shares_basic,estimates_fy1,calendar_atom}.parquet` and `work/snapshot/MANIFEST_snapshot.json`.
  - `work/snapshot/sealed/{prices_raw_2026,total_return_check_2026}.parquet`.
  - `src/newsaction/panel/{__init__,mapping,adjust,sector,risk,tiers,targets,reactions,build}.py`.
  - `work/panel/{panel_public,panel_test_inputs,companies,tiers_monthly,qc_flags}.parquet`.
  - `artifacts/NA-01/REPORT.md`, `docs/decisions/NA-01.md`.
  - Tests: `tests/test_panel_*.py`.
- **Not touched:** ATOM DB and repo (read-only), `Data/`.

**Current state (verified 2026-10-24):**
- ATOM Postgres runs in docker `atom_postgres` (db/user `atom`).
  - `Settings.load()` fails outside the ATOM repo: secrets are missing and `ATOM_VENDOR__EDGAR__USER_AGENT` is required. Connect with `atom_data.db.get_engine(DatabaseSettings(password=SecretStr(pw)))` and `get_session` (`packages/atom_data/src/atom_data/db.py:58,89`); `DatabaseSettings` is in `atom_core.config`.
  - Accessors import cleanly with `/Users/amir/GitHub/Atom/.venv/bin/python`.
- Accessors to use:
  - `get_universe_members(universe_code, as_of, *, session, clock=None)` (`packages/atom_research/src/atom_research/accessors.py:636`).
  - `get_prices_eod_by_id(symbol_ids, start, end, as_of, *, session, adjust="raw"|"price"|"total", clock=None)` (`:285`). Rows are capped at `as_of`; return ratios do not depend on `as_of` once `as_of ≥ t`.
  - `get_estimates(...)` (`:589`).
  - Calendar: `atom_core/calendars.py` `session_open_instant` (:90), `session_close_instant` (:113), `previous_session` (:145), `sessions_between` (:166).
  - Accessors raise `PITError` if `as_of` is more than 1 day ahead of now.
- `md.price_eod`: 716 symbols, raw OHLCV, 2014-01-02 → 2026-10-23, SPY `symbol_id` 21538.
- `md.corporate_action` since 2024: merger 12, split 42, cash_dividend 4,916, **no spin-offs**. GE raw 2024-04-01 C=175.24 → 2024-04-02 O=140.53, a fake −19.8% gap; `Data/prices` adjusted gives −2.5%.
- `fnd.financial_metric`: `shares_outstanding` has **0 rows**, so `atom_features…_common.market_cap()` (:206) returns nothing. `shares_basic` has 45,819 rows / 717 symbols; known_from = period_end + 45 days (up to 90).
- `uni.member` (sp500) matches real index changes: SMCI 2024-03-15, PLTR/DELL/ERIE 2024-09-23, WDAY 2024-12-22, DASH/TKO/WSM 2025-03-23, COIN 2025-05-18, DDOG 2025-07-08, TTD 2025-07-17, XYZ 2025-07-22, IBKR 2025-08-27 (WBA removed 2025-08-27), HOOD/APP 2025-09-21.
- `Data/prices/prices.parquet`: close (adjusted) + volume, 2,638 symbols, 2019-07-01 → 2026-07-31. `betas.parquet` is "as of day t" (includes t), so it is **not used**; β is recomputed.
- No sector-ETF opens exist anywhere, so the sector factor is leave-one-out from member stocks.
- Earlier exploratory diagnostics (scratchpad, 2026-10-24) found median market+sector R² ≈ 0.34; the AC7 sanity band is 0.30–0.40.

### Power prompt — NA-01

```text
You are implementing NA-01 for /Users/amir/Research/NewsAction: a one-time READ-ONLY export from ATOM and the daily
point-in-time panel. 2026 outcomes are SEALED: no statistic, print or plot of any 2026 return in this chunk.

Read first:
  - CLAUDE.md (rules A, B, E especially)
  - docs/PREREG.md §3 (universe, tiers), §4 (splits, purge, blinding), §5 (prices, returns, σ, targets, placebo)
  - docs/PREREG.md §15 Amendment A1 — you build the convergence-ladder targets of A1.2 (CAR^lvl rungs, E5^lvl)
  - docs/DATA_CONTRACT.md and artifacts/NA-00/REPORT.md
  - src/newsaction/{calendar,lock,io,pit,ledger}.py (use them; do not re-implement)
  - ATOM (read-only): packages/atom_research/src/atom_research/accessors.py:285 (get_prices_eod_by_id), :636
    (get_universe_members), :589 (get_estimates); packages/atom_core/src/atom_core/calendars.py:90,:113,:145,:166;
    packages/atom_data/src/atom_data/db.py:58,:89; packages/atom_features/src/atom_features/features/_common.py:206
    (market_cap — read its docstring: shares not split-adjusted; and shares_outstanding is EMPTY in this DB);
    docs/data_dictionary.md (md.price_eod raw; md.corporate_action; fnd.financial_metric; uni.member)
Branch: feat/NA-01-panel (from main after NA-00 is merged).

Operator prerequisite: ATOM stack up; ATOM_DB_PASSWORD in .env. Never print it.

## Scope

S1. EXPORT SCRIPT — scripts/export_atom_snapshot.py, executed as
    `/Users/amir/GitHub/Atom/.venv/bin/python scripts/export_atom_snapshot.py --out work/snapshot`
    (ATOM venv; pandas 2.3 there — write parquet with pyarrow; no pickles). Connect with DatabaseSettings(password=
    SecretStr(os.environ["ATOM_DB_PASSWORD"])) → get_engine → get_session. READ-ONLY: open the session, set
    `SET TRANSACTION READ ONLY` on the connection, and record `SELECT count(*)` of md.price_eod and uni.member
    before and after (must be equal). Export:
      a. members_by_session: for every XNYS session 2023-01-03..2026-07-31 call get_universe_members("sp500",
         as_of=session_open_instant("NYSE", d)) → (session, symbol_id, ticker).
      b. symbols: ref.symbol (symbol_id, ticker, name, cik, exchange, listing/delisting dates) for all member ids ∪
         SPY; symbol_tickers: ref.symbol_ticker (symbol_id, ticker, valid_from, valid_to).
      c. gics: ref.symbol_sector joined to ref.sector hierarchy (levels 1–4 names) with valid ranges.
      d. prices_raw: get_prices_eod_by_id(ids ∪ {SPY}, 2022-01-03, 2026-07-31, as_of=<export instant>,
         adjust="raw"). Rows dated ≤ 2025-12-31 → work/snapshot/prices_raw.parquet; rows ≥ 2026-01-02 →
         work/snapshot/sealed/prices_raw_2026.parquet. Same for adjust="total" → total_return_check(_2026).
      e. corporate_actions: md.corporate_action rows for those ids (action_type, announce_date, ex_date,
         split_ratio, cash_amount).
      f. shares_basic: fnd.financial_metric rows with metric code shares_basic (symbol_id, period_end, value,
         known_from = lower(knowledge_range)).
      g. estimates_fy1: get_estimates for eps_diluted, aggregation mean & count, annual periods, as_of snapshots
         2023-01..2026-07 (symbol_id, as_of_date, period_end, mean, n).
      h. calendar_atom: sessions 2022-01-03..2026-10-23 with open/close instants from atom_core.calendars.
    Write work/snapshot/MANIFEST_snapshot.json (sha256, rows, ATOM git sha `git -C ~/GitHub/Atom rev-parse HEAD`,
    export instant, accessor names, the before/after counts). Then, back in the NewsAction env, register every
    snapshot file in work/MANIFEST.json via io (sealed files registered with their hash but never read).

S2. MAPPING + ADJUSTMENT — panel/mapping.py + panel/adjust.py:
    - Map each ATOM symbol_id to the Data/prices symbol: normalize tickers (. → -), match by ticker validity range
      overlapping the price history, then VALIDATE: correlation of daily close-to-close returns (raw-close ratio vs
      Data/prices adjusted close) ≥ 0.99 over non-event days. Report unmapped / failed ids (expect a handful).
    - f_t = AdjClose_t / RawClose_t; adjusted open AO_t = RawOpen_t·f_t; r_cc = AC_t/AC_{t−1}−1;
      r_id = RawClose_t/RawOpen_t−1; r_on = (1+r_cc)/(1+r_id)−1 (PREREG §5.1). SPY identically (ATOM raw OHLC +
      Data/market/market_prices.parquet SPY close as AdjClose).
    - QC: compare r_cc with ATOM total-return close-to-close; flag |diff| > 50 bp into work/panel/qc_flags.parquet
      with a reason column; list the top 30 in the REPORT (expect spin-offs like GE 2024-04-02 and SOLV/VLTO-type
      events). Public period only.

S3. SECTOR — panel/sector.py: PIT GICS sector per (session, symbol); leave-one-out equal-weighted sector return
    for each return type with ≥ 5 other members, else NaN (flag).

S4. RISK — panel/risk.py: β_m, β_s by rolling OLS over 252 sessions ending t−1 (min 126) of r_cc on
    [r_SPY, r_sec − r_SPY]; AR_x for x∈{cc,on,id}; σ_x = 1.4826·MAD over 126 sessions ending t−1 (min 60), floored
    at the cross-sectional 10th percentile of that day; half days scale σ_id by sqrt(minutes/390); z_x clipped
    ±10; z_vol per PREREG §5.4. EVERYTHING ends at t−1 (use explicit shift and assert via a planted-shock test).

S5. COMPANIES + TIERS — panel/tiers.py: group symbols by CIK into companies; representative class = higher
    63-session dollar volume at the prior month-end; company cap = Σ classes (raw close × shares_basic latest with
    known_from ≤ ranking session × Π split ratios with ex_date in (period_end, ranking session]); rank at the last
    session of each month, applied to the next month: Top-100 (1–100), Mid (101–250), Rest (251+); fallback rank by
    dollar volume when shares are missing (flag). Also DV tiers. Outputs work/panel/companies.parquet and
    tiers_monthly.parquet.

S6. TARGETS + REACTIONS (code that NA-11/NA-12 will reuse, hashed at the freeze):
    - panel/targets.py: build_targets(panel, period) computes PREREG §5.6 targets (z_on, z_cc, z_id, AR(O_t→C_{t+k})
      for k∈{1,5}, AR(O_{t+1}→C_{t+k}) for k∈{1,5,20}, AR(C_t→O_{t+1}), e5, the CONVERGENCE LADDER (PREREG A1.2) CAR^lvl_h from
      the previous close in level units (÷ σ_cc,t, no √h) for h ∈ {O_t, C_t, C_{t+1}, C_{t+2}, C_{t+5}, C_{t+10},
      C_{t+20}} (+ C_{t+60} exploratory) and E5^lvl, material-label inputs) with purge (§4.1: horizon must end
      inside the split; else NaN). Clean-window flags need events (added in NA-03); the 10:00 rung comes in NA-10. For any session ≥ 2026-01-02 it must obtain prices ONLY
      via lock.sealed_path(..., "targets") (which raises before unblinding).
    - panel/reactions.py: build_reactions(panel, period, point) computes G for D2 (z_cc,t) and the inputs D1 needs
      later (left as a stub raising NotImplementedError until NA-10 adds bars); for 2026 it must go through
      lock.sealed_path(..., "reactions") (raises before the freeze).
    - Placebo helper (PREREG §5.7) operating on the public panel only.

S7. BUILD — panel/build.py (CLI `uv run python -m newsaction.panel.build`): writes
    work/panel/panel_public.parquet (sessions 2023-07-03..2025-12-31: ids, company_id, tier, dv_tier, member flag,
    sector, half_day, r_*/AR_*/σ_*/z_*, β, z_vol, momentum features (5/20/60-session abnormal returns through t−1),
    targets) and work/panel/panel_test_inputs.parquet (2026 sessions: ids, company_id, tier, sector, half_day, β, σ,
    volume baselines, momentum — all through t−1 — and NOTHING dated t or later). Register every column's
    availability kind in configs/availability.yaml.

S8. QC REPORT — artifacts/NA-01/REPORT.md: companies per session (min/median/max), tier sizes per month, β/σ
    distributions, the R² sanity check (2024-07..2025-12), the QC flag list, golden checks (S9), the delisting /
    leaver list, calendar equality vs calendar_atom, mapping failures. No 2026 return statistic anywhere.

## Acceptance criteria

- AC1 — READ-ONLY EXPORT: MANIFEST_snapshot.json shows equal before/after counts for md.price_eod and uni.member;
  the export used a READ ONLY transaction; rows ≥ 2026-01-02 exist only under work/snapshot/sealed/.
- AC2 — PIT ROLLING STATS: test plants a +50σ AR_cc on (AAPL, 2025-03-14) in a copy of the inputs; β, σ, z_vol
  and tier for 2025-03-14 are unchanged and those for 2025-03-17 change. MUTATION: drop the shift(1) in risk.py →
  RED.
- AC3 — ADJUSTMENT: |r_on(GE, 2024-04-02)| < 3%; no public-period member-day with |r_on| > 25% lacks a qc_flags
  entry; mean AR_on on cash-dividend ex-dates differs from other days by < 3 bp.
- AC4 — CALENDAR EQUALITY: newsaction.calendar sessions and open/close instants equal calendar_atom for
  2022-01-03..2026-10-23 (including half days and 2025-01-09).
- AC5 — TIERS: each month has exactly 100 Top-100 and 150 Mid companies (ties by company_id); NVDA (10:1 split
  2024-06-10) is Top-100 in 2024-06, 2024-07, 2024-08; AVGO (2024-07-15), CMG (50:1, 2024-06-26), WMT (3:1,
  2024-02-26) keep stable tiers across their splits; fallback count reported. MUTATION: drop the split adjustment
  of shares → the NVDA/CMG assertions RED.
- AC6 — UNIVERSE: companies per session within 495–505; WBA present through its last session before 2025-08-27
  and absent after; COIN absent before 2025-05-19 and present from it; HOOD/APP present from 2025-09-22.
- AC7 — SANITY: median per-stock R² of r_cc on [SPY, sector−SPY] over 2024-07-01..2025-12-31 in [0.30, 0.40].
- AC8 — SEALING: panel_public has no session ≥ 2026-01-02; panel_test_inputs has only columns registered as
  static or t_minus_1 (schema test against configs/availability.yaml); build_targets(…, "test") and
  build_reactions(…, "test", "D2") raise LockError and log refused attempts.
- AC9 — CONVERGENCE LADDER: for 20 random public events, CAR^lvl at C_{t+5} equals Σ_{j=0..5} AR_cc,t+j / σ_cc,t
  and CAR^lvl at O_t equals AR_on,t / σ_cc,t (tolerance 1e-9); the C_{t+20} rung is NaN whenever t+20 crosses the
  split end (purge).

## Constraints

- ATOM is READ-ONLY: no writes, no migrations, no changes in ~/GitHub/Atom. The export script lives in this repo.
- No FMP calls (ETF opens are NOT needed: sector is leave-one-out). No OpenRouter.
- Blinding: never compute, print or plot a 2026 return; the sealed files are read only via newsaction.lock (they are
  not read at all in this chunk).
- All rolling statistics end at t−1; tiers use the prior month-end only.
- Use the PIT accessors for prices and membership; raw SQL is acceptable only for tables with no accessor
  (corporate_action, shares_basic, ref tables) and must be SELECT-only inside the READ ONLY transaction.
- Register every artifact (io + DATA_CONTRACT). Conventional Commits on feat/NA-01-panel; do not merge.
- End with the self-audit (artifacts/NA-01/REPORT.md).
```

### Verification prompt — NA-01

```text
Independent verifier for NA-01 at /Users/amir/Research/NewsAction (branch feat/NA-01-panel). READ-ONLY; restore any
mutation; no commits; no ATOM writes (you may run SELECT counts); never compute or print a 2026 return.

Most likely defects: (i) β/σ/tiers computed with day t (look-ahead), (ii) spin-off gaps left in, (iii) market caps
broken by splits (shares_basic is not split-adjusted), (iv) 2026 prices leaking into public files.

1. GATES: `make verify` → 0. `make manifest` → all hashes OK.
2. ATOM UNTOUCHED: `docker exec -i atom_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select
   count(*) from md.price_eod"'` and the same for uni.member — compare with MANIFEST_snapshot.json "after".
3. SEALING: with pyarrow, read only the `date`/`session` column of work/panel/panel_public.parquet and
   work/snapshot/prices_raw.parquet → max ≤ 2025-12-31. List work/snapshot/sealed/ (do not open the files).
   Grep src/ for "sealed" outside lock.py (must be none).
4. HAND RECOMPUTE: for (MSFT, 2025-06-12) recompute β_m, β_s from the panel's r_cc over the 252 prior sessions
   with numpy OLS and σ_cc from the 126 prior AR_cc; compare (tolerance 1e-6).
5. GOLDEN CASES: GE 2024-04-02 r_on; NVDA/CMG/AVGO/WMT tiers around their splits; WBA/COIN/HOOD membership dates;
   companies-per-session range. Report the numbers.
5b. CONVERGENCE LADDER (A1.2, AC9): for 5 random public events recompute CAR^lvl at O_t, C_t, C_{t+5} and C_{t+20}
   from the AR columns and σ_cc,t by hand; confirm the C_{t+20} rung is NaN for an event within 20 sessions of a
   split end.
6. MUTATIONS (restore each): (a) remove the t−1 shift in risk.py; (b) remove split adjustment of shares in
   tiers.py; (c) make build_targets skip the lock for 2026. Run `make test`; each must turn RED.
7. SANITY: median R² band (AC7) recomputed independently on 50 random companies.
8. QC FLAGS: open the top 10 flagged days; confirm each has a plausible reason (spin-off, data error) and none is a
   silently "fixed" genuine move.
9. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC9 and GAC with numbers.
```

**New tests to add:**
- `test_panel_pit.py`: planted shock (AC2).
- `test_panel_adjust.py`: GE, the ex-dividend mean, the flag coverage.
- `test_panel_calendar_equality.py`.
- `test_panel_tiers.py`: sizes and split goldens.
- `test_panel_universe.py`.
- `test_panel_sealing.py`: schema and lock refusals.

**Risks / notes:**
- **Ticker mapping between ATOM and `Data/prices`** (renames like SQ→XYZ, share classes). The ≥ 0.99 return-correlation validation is the guard.
- **`shares_basic` known-dates are synthetic** (45 days), but adequate for monthly ranks. DV tiers are the robustness check.
- **Delisted or acquired names** may lack `Data/prices` rows near the end; flag them and use the last price (PREREG §5.8).

---

## NA-02 — [Build] News timing audit, symbol mapping, cleaning, re-embedding, PIT novelty

**Category:** Phase 1 — data. Turns the raw NewsWitch corpus into **cleaned, correctly-timed, member-mapped articles**:
- availability times (the date-only and hour-precision rules);
- after-the-fact and price-talk detection;
- near-duplicate collapse;
- re-embedding from title + snippet;
- PIT novelty;
- source classes;
- a leakage audit on ≤ 2025 data.

It also re-derives the pre-registration's exploratory diagnostics on ≤ 2025 data (PREREG §14).

**Goal:** `work/news/articles_clean.parquet`, plus embeddings, coverage, the timing audit and the leakage IC table that decide which text fields and sources are allowed.

**Dependencies:** NA-00, NA-01 (sessions, membership, symbols, panel targets for the ≤ 2025 audits). Consumed by NA-03, NA-04. · **Estimated time:** 1.5–2 days · **Branch:** `feat/NA-02-news`

**Expected outputs:**
- **New:** `src/newsaction/news/{__init__,load,mapping,clean,detect,dedupe,embed,novelty,sources,audit,coverage}.py`.
- **Configs:** `configs/sources.yaml`, `configs/patterns.yaml` (13F, Form-4 and after-the-fact regexes).
- **Work files:** `work/news/{articles_clean,embeddings_ts,coverage_member_month}.parquet`.
- **Artifacts:** `artifacts/NA-02/{REPORT.md,timing_audit.md,leakage_ic.csv,spam_judgments.csv,detector_eval.csv,rederived_diagnostics.md}`.
- **Modified:** `configs/frozen.yaml` (`news:` section).
- **Tests:** `tests/test_news_*.py`.
- **Not touched:** `Data/`, ATOM.

**Current state (verified 2026-10-24):**
- **Corpus:** `Data/news_YYYY.parquet` holds 4,685,889 rows (2024 1.35M; 2025 2.44M; 2026 Jan–Jul 0.72M). Columns:
  - `id`, `ticker` (`EXCH:SYM`), `date` (unix UTC publication);
  - `title`, `snippet`, `body`, `summary` (LLM-written, 4.8% null);
  - `sentiment_direction` (5 levels), `sentiment_intensity` (actually a horizon label), `sentiment_reason`;
  - `domain`, `url`, `non_news`, `parsing_allowed`;
  - 17-type `tag_type`, `tag_type2`, 5 boolean flags, `tag_conf`, `tag_source`;
  - `event_id`, `event_first_day`, `event_age_days` (story clustering done **offline over the whole corpus**);
  - `_ts`.
- **Embeddings:** `Data/embeddings` are bge-small vectors of **"title. summary"** (README), so they must be re-embedded from title + snippet.
- **Date-only timestamps** (exactly 00:00:00 UTC): 10.9% of 2024 (24–25% in 2024-01..06, 3.8% in 2024-07, 35.6% in 2024-08, 16.9% in 2024-09), 5.0% of 2025, 3.0% of 2026. 10,326 date-only `earnings_results` articles in 2025. Top domains among them: marketbeat, finviz, theglobeandmail, gurufocus, aol.
- **Spam:**
  - 13F holdings articles: about 15% of all articles (62.6% of `insider_ownership`) by the title regex in this session's diagnostics.
  - Form-4 pattern: 1.8% of `insider_ownership`.
  - Top domains 2024+: marketbeat.com 1.05M, finance.yahoo.com 0.38M, openpr.com 0.19M, defenseworld.net 0.19M.
- **`parsing_allowed`** across all years: True 78.5%, None 20.6%, False 0.86%.
- **2025–26 coverage:** about 1,000–1,100 tickers, including indices (`^GSPC`, `^VIX`), FX, crypto and foreign listings that must be excluded. 517 tickers map to S&P 500 members; only 16 members have no news.
- **Exploratory diagnostics from 2026-10-24** used 2026 data and ignored the availability rules (PREREG §14).

### Power prompt — NA-02

```text
You are implementing NA-02 for /Users/amir/Research/NewsAction: cleaned, correctly-timed, member-mapped news. The
leakage audits and the re-derived diagnostics use ONLY sessions ≤ 2025-12-31 (2026 targets are sealed; you may
process 2026 ARTICLES — text and timestamps are inputs — but you must not join them to any 2026 return).

Read first:
  - CLAUDE.md; docs/PREREG.md §2 (timestamps, windows), §3.4 (coverage), §6.1–6.5 (third-party rule, cleaning,
    masking context, text fields, novelty), §14 (disclosure)
  - docs/DATA_CONTRACT.md; artifacts/NA-01/REPORT.md; work/snapshot/{symbols,symbol_tickers}.parquet;
    work/panel/panel_public.parquet (targets for ≤ 2025 audits)
  - src/newsaction/{calendar,timeutil,pit,io}.py
  - Data/README.md (news + embeddings schema; embeddings are of "title. summary")
Branch: feat/NA-02-news.

## Scope

S1. LOAD — news/load.py: read Data/news_2023..2026 parquet with pyarrow, columns: id, ticker, date, title, snippet,
    summary, domain, non_news, parsing_allowed, sentiment_direction, sentiment_intensity, tag_type, tag_type2,
    tag_scheduled, tag_forward_looking, tag_primary_source, tag_quantified, tag_rumor, tag_source, event_id,
    event_age_days. Never load `body`. Keep articles with t_avail in [2023-07-01, 2026-07-31].

S2. MAP — news/mapping.py: parse EXCH:SYM; drop non-equity prefixes (^, CCC, INDEX*, DX-, FX) and non-US
    exchanges; normalize; resolve ticker → symbol_id using work/snapshot/symbol_tickers.parquet validity ranges at
    t_avail (handles SQ→XYZ, FB→META-style renames), then → company (CIK) via companies.parquet; keep only articles
    whose company is an S&P 500 member at session_of_w2(t_avail). Report: mapped share of member-day article volume,
    top 30 unmapped tickers, and assert zero many-to-one collisions (one (ticker, t) → one symbol).

S3. TIMING — apply timeutil.precision_class / availability; assign session_w0 and session_w2 via calendar
    (vectorized). TIMING AUDIT (artifacts/NA-02/timing_audit.md): precision-class shares by year and by top domains;
    share of D0 ticker-days that change under the date-only rule; LEAK SIGNATURE on ≤ 2025 only: for W0 articles,
    daily IC of vendor sentiment (−2..+2) with z_on vs z_id, split by precision class, under the naive assignment vs
    the PREREG rule. Report both.

S4. CLEAN — news/clean.py: flags non_news, junk_tag (price_commentary, promotional_content), is_13f (regex from
    configs/patterns.yaml), is_form4 (insider auto-articles: keep as metadata), unmapped; third_party_ok =
    (parsing_allowed is True); report parsing_allowed True/None/False shares for member articles 2024-07..2026-07
    (the operator decides None before NA-05 — write the decision request in the REPORT).
    SPAM JUDGMENT: sample 200 is_13f-flagged and 200 unflagged insider_ownership titles (seed 2026), judge each
    yourself (13F holdings auto-article: yes/no), save artifacts/NA-02/spam_judgments.csv, compute precision and
    recall. Iterate the regex until precision ≥ 0.95 (re-judge a fresh sample after each change).

S5. DETECT + SCRUB — news/detect.py: sentence-level detectors on title+snippet: (a) after-the-fact / price-path
    language ("shares rose|fell|jumped|slid … (today|this morning|in early/morning/afternoon trading|midday)",
    "closed (up|down|higher|lower|at)", "opened (higher|lower|at)", "as of \d{1,2}:\d{2}", "stock (is|was)
    (up|down) \d", "trading (higher|lower|up|down)"), (b) pre-market talk ("premarket|pre-market|before the
    bell|in extended trading"). scrub(text) removes flagged sentences and share-price levels ("$123.45 a share",
    "price target" stays). Build a planted evaluation set of ≥ 60 synthetic sentences (positives and hard
    negatives) → recall ≥ 0.95; judge precision on 200 sampled flagged sentences (artifacts/NA-02/
    detector_eval.csv).

S6. EMBED — news/embed.py (install the "embed" group): BAAI/bge-small-en-v1.5 via sentence-transformers on MPS,
    text = title_clean + ". " + snippet_clean, normalize_embeddings=True, float16; for all mapped member articles;
    write work/news/embeddings_ts.parquet aligned by id; log throughput and the model revision hash.

S7. DEDUPE — news/dedupe.py: within company, articles with cosine ≥ 0.93 and |Δt_avail| ≤ 72 h form a group; the
    representative is the earliest t_avail; store dup_group, dup_count, is_representative.

S8. NOVELTY — news/novelty.py: novelty = 1 − max cosine to the same company's representatives with t_avail
    STRICTLY earlier within 7 days (1.0 if none). Implement with a per-company time-ordered scan.

S9. SOURCES — news/sources.py + configs/sources.yaml: domain → class ∈ {press_wire_primary, major_outlet,
    aggregator, retail_analysis, auto_generated, other}; press_wire_primary also when tag_primary_source is True.
    Document the domain lists (top 100 domains by volume classified explicitly).

S10. LEAKAGE AUDIT (≤ 2025-12-31 ONLY) — news/audit.py → artifacts/NA-02/leakage_ic.csv: for W0 articles, the
     daily IC of vendor sentiment with z_on and z_id by (text field the sentiment was derived from is the summary —
     so test "summary present vs absent"), by source class, by precision class, by after_fact flag. Rule (PREREG
     §6.4): a field/source is LEAKY if IC(z_id) ≥ IC(z_on) with t > 2. Write configs/frozen.yaml news:
     {summary_variant_allowed: bool, excluded_sources: [...], leakage_audit_sha: ...}.

S11. COVERAGE — news/coverage.py: member-month article counts (after cleaning) → work/news/
     coverage_member_month.parquet with covered flag; leaver check: articles per member-day in the last 60 sessions
     before removal vs matched stayers (same tier/sector) — report.

S12. OUTPUT — work/news/articles_clean.parquet: id, company_id, symbol_id, ticker_raw, ts_pub_utc, precision,
     t_avail, session_w0, session_w2, domain, source_class, title, snippet, title_clean, snippet_clean,
     summary_present, flags {non_news, junk_tag, is_13f, is_form4, after_fact, premarket_talk}, third_party_ok,
     vendor fields (sentiment_direction, sentiment_intensity, tag_type, tag_type2, tag flags, event_age_days),
     dup_group, dup_count, is_representative, novelty, keep (bool: passes §6.2). Register availability kinds
     (t_avail-based "w0"/"w2" for text; vendor fields as "selection_only").

S13. RE-DERIVED DIAGNOSTICS (PREREG §14) — artifacts/NA-02/rederived_diagnostics.md on ≤ 2025-12-31 with the
     PREREG timing rules: overnight vs intraday variance shares by news status; vendor-sentiment IC on z_on, z_id,
     next-day and 5-day; continuation after |z_on| > 2 by tag. These are the versions the paper may cite.

S14. MARKET NEWS (PREREG A3.5, optional) — keep the cleaned, scrubbed market-index articles that S2 drops from the
     company set (tickers ^GSPC, ^VIX, DX-Y.NYB) with t_avail and session_w2 in work/news/market_articles.parquet (no
     company mapping; same third_party_ok rule).

## Acceptance criteria

- AC1 — TIMESTAMP RULES: (a) a date-only fixture stamped 2025-03-10 00:00:00Z becomes available 2025-03-10
  23:59:59Z → session_w0 = 2025-03-11 and session_w2 = 2025-03-11 (never 2025-03-10); (b) an hour-precision fixture
  stamped 2025-03-10 13:00:00Z (09:00 EDT) becomes available 13:59:59Z, which is after that day's 13:15Z (09:15 EDT)
  cutoff and before the 20:00Z close → session_w0 = None (not a D0 article) and session_w2 = 2025-03-10; (c) an exact
  fixture at 2025-03-10 12:30:00Z → session_w0 = session_w2 = 2025-03-10. MUTATION: remove the date_only branch → (a)
  RED; remove the hour branch → (b) RED. Affected-share table reported per year.
- AC2 — MAPPING: SQ-tagged 2024 articles and XYZ-tagged 2025 articles of Block map to the same company_id;
  BRK.B/BRK-B normalize; collisions == 0; mapped share of member-day volume ≥ 95% (report exact).
- AC3 — DETECTOR: planted-set recall ≥ 0.95; judged precision reported (no threshold, but < 0.8 must be explained).
- AC4 — NOVELTY PIT: deleting every article with t_avail > τ (τ = 2025-06-15) leaves novelty unchanged for all
  articles with t_avail ≤ τ. MUTATION: use ≤ instead of < → RED (self-similarity).
- AC5 — SPAM: 13F precision ≥ 0.95 on the final judged sample (CSV committed).
- AC6 — LEAKAGE AUDIT uses only sessions ≤ 2025-12-31 (assert in code and test); frozen.yaml news section written.
- AC7 — EMBEDDINGS: one row per kept article id; float16; L2 norm within 1 ± 1e-2.
- AC8 — THIRD-PARTY: parsing_allowed shares reported; third_party_ok column present; operator decision request
  for None written in the REPORT.
- AC9 — NO 2026 OUTCOMES: test_blinding passes; ledgers/test_access.jsonl has no NA-02 entries.

## Constraints

- Never load Data/news `body` (size; and summaries/body may contain post-publication edits).
- Vendor tags/sentiment/event clustering are selection-only (CLAUDE.md A6); store them, don't put them in text.
- Leakage audit and re-derived diagnostics: ≤ 2025-12-31 only. No 2026 return touched.
- Local compute only (MPS); no API calls. Register artifacts; Conventional Commits; do not merge.
- End with the self-audit.
```

### Verification prompt — NA-02

```text
Independent verifier for NA-02 (branch feat/NA-02-news). READ-ONLY; restore mutations; no commits; no network; never
join 2026 articles to returns.

Most likely defects: (i) date-only/hour timestamps still assigned to the wrong window, (ii) ticker renames mapped to
two companies, (iii) a "novelty" that peeks at later articles, (iv) leakage audit touching 2026.

1. GATES: `make verify`; `make manifest`.
2. TIMING: recompute precision-class shares for 2024 and 2025 directly from Data/news (pyarrow, `date` column only)
   and compare with timing_audit.md. Pick 10 random date-only articles and 10 hour-precision articles and check
   their session_w0/session_w2 by hand with newsaction.calendar.
3. MAPPING: list articles for tickers containing "SQ" or "XYZ" across 2024–2025; confirm one company_id. Count
   (ticker, t) → symbol collisions (must be 0).
4. NOVELTY: run the deletion test yourself with τ = 2025-02-03 on 20 random companies.
5. DETECTOR: write 10 NEW sentences of your own (5 after-the-fact, 5 hard negatives such as "price target raised to
   $200") and run detect; report hits.
6. SPAM: re-judge 30 random rows of spam_judgments.csv; agreement ≥ 90% with the author's labels.
7. LEAKAGE AUDIT: grep news/audit.py for the date filter; confirm max session ≤ 2025-12-31 in its inputs; check
   frozen.yaml news section is consistent with leakage_ic.csv and the PREREG §6.4 rule.
8. MUTATIONS: (a) remove the date_only rule; (b) novelty `<` → `<=`; (c) disable ticker-history mapping (map by the
   current ticker only) → the SQ/XYZ test must RED. Restore.
9. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC9 and GAC with numbers.
```

**New tests to add:**
- `test_news_timing.py`: date-only and hour cases.
- `test_news_mapping.py`: renames, collisions.
- `test_news_detect.py`: the planted set.
- `test_news_novelty.py`: deletion invariance.
- `test_news_dedupe.py`.
- `test_news_audit_dates.py`.

**Risks / notes:**
- **Snippets are short** (~150 chars), so title + snippet carries less information than summaries. That is the price of leakage safety. The summary variant is allowed only if the audit passes.
- **Embedding all member articles takes time.** About 1.5–2M short texts with bge-small on MPS should take tens of minutes; log the throughput.
- **The operator must decide `parsing_allowed == None` before NA-05.**

---

## NA-03 — [Research] Importance filters, material label, events

**Category:** Phase 1 — research design on data. It compares candidate "important news" filters under a pre-registered rule at a fixed call budget, then builds the **events** (one per company, session and window, with ≤ 6 articles) that every model scores.

**Goal:**
- Material labels: ≤ 2025 only, with the delayed reaction included.
- Learned filters F5/F6: fit ≤ 2025-03, tuned ≤ 2025-06.
- A val-A comparison with the efficiency frontier, the frozen choice, and `work/events/events_{d0,d2}.parquet` for all periods (no outcome access for the test period).
- Exact call and cost projections for later chunks.

**Dependencies:** NA-01, NA-02. Consumed by NA-04 onward. · **Estimated time:** 1 day · **Branch:** `feat/NA-03-filters`

**Expected outputs:**
- **New code:** `src/newsaction/events/{__init__,labels,filters,select,aggregate,tokens}.py`.
- **Work files:**
  - `work/events/{labels_public,article_scores,events_d0,events_d2}.parquet`;
  - `work/events/models/{f5_logreg,f6_lgbm}.*` with fit metadata.
- **Artifacts:** `artifacts/NA-03/{REPORT.md,filter_comparison.csv,frontier.csv,call_projection.csv}`.
- **Modified:** `configs/frozen.yaml` (`filter:` section).
- **Tests:** `tests/test_events_*.py`.

**Current state (verified 2026-10-24, before the timestamp fix; these are planning numbers only):**
- With rules similar to F1 (material) on S&P 500 PIT members and a 09:15 cutoff, D0 events were 39.3K (2024), 54.4K (2025) and 26.8K (2026 Jan–Jul); D2 events 48.5K / 67.0K / 34.7K.
- Mean articles per selected ticker-day was about 2.75, and news text (title + summary) about 410 tokens. With title + snippet it will be smaller.
- Rule filters showed modest lift: selecting 38% of stock-days captured 44% of |z| > 2 days.
- PREREG §6.6–6.9 defines the candidates, the label, the protocol and the rule.

### Power prompt — NA-03

```text
You are implementing NA-03 for /Users/amir/Research/NewsAction: compare candidate importance filters with the
pre-registered rule, freeze the choice, and build events for all periods. Labels/targets exist only for sessions
≤ 2025-12-31; test-period events are built from articles alone.

Read first:
  - CLAUDE.md; docs/PREREG.md §4 (splits/purge), §5.4–5.6 (z, targets), §6.6–6.9 (filters, label, protocol, rule,
    events), §13 (budget), §15 Amendment A1.2 (convergence clean-window flags you add to events)
  - docs/DATA_CONTRACT.md; artifacts/NA-02/REPORT.md; work/news/articles_clean.parquet; work/news/
    embeddings_ts.parquet; work/news/coverage_member_month.parquet; work/panel/panel_public.parquet
Branch: feat/NA-03-filters.

## Scope

S1. LABELS — events/labels.py: for every covered member company × session in train/val-A/val-B (public panel):
    material = (|z_on,t| ≥ 2) or (|Σ_{j=0..5} AR_cc,t+j| / (σ_cc·√6) ≥ 2) or (z_vol,t ≥ 2); delayed =
    (|z_on,t| < 1) and (|Σ_{j=1..5} AR_cc,t+j| / (σ_cc·√5) ≥ 2). Purge per PREREG §4.1 (horizon inside the split).
    Write work/events/labels_public.parquet. Never call build_targets for "test".

S2. CANDIDATES — events/filters.py: article-level scores for F0–F6 (PREREG §6.6) on kept, representative
    articles in W0 windows; ticker-day score = max article score; also counts. F4 uses novelty; F3 uses
    source_class; F1/F2 use vendor fields (selection only).

S3. LEARNED FILTERS: F5 = logistic regression on embeddings; F6 = LightGBM on (tag_type, tag flags, sentiment,
    intensity, source_class, novelty, 16 PCA components of embeddings fit on the fit window, attention ratio =
    articles today / 60-session mean). Fit on 2024-07-01..2025-03-31 ticker-days (label at ticker-day level; purge),
    tune hyperparameters on 2025-04-01..2025-06-30 (small grid; each grid point logged to ledgers/trials.jsonl),
    then FREEZE the model and store it with metadata {fit_range, tune_range, features, params, sha256}.

S4. COMPARISON (val-A only) — events/select.py: for each filter set its threshold so selected ticker-days ≤ 30%
    of covered member-days in val-A (F0 is reported at its natural rate as a reference); compute recall of material
    ticker-days, delayed-reaction recall, precision, abnormal variance ratio Var(z_cc | selected)/Var(z_cc | all),
    selection rate by tier. Apply the PREREG §6.8 rule MECHANICALLY (function apply_rule(df) → filter id), write
    configs/frozen.yaml filter: {id, threshold, budget_share, rule_version, comparison_sha}. Write
    artifacts/NA-03/filter_comparison.csv and frontier.csv (for each filter: selection share vs recall at 10
    thresholds — Figure 6 data).

S5. EVENTS — events/aggregate.py with the FROZEN filter for ALL periods (robustness, train, val-A, val-B, test):
    D0 events (W0) and D2 events (W2) per company×session: up to 6 representative articles ordered by score then
    t_avail; exclude third_party_ok=False from the article list but count them; news token count with the
    answerdotai/ModernBERT-large tokenizer (events/tokens.py; cap 600 tokens by dropping lowest-score articles,
    then truncating the last snippet); attention features (articles, distinct stories, dup counts); and the
    convergence clean-window flags clean_h for h ∈ {1, 2, 5, 10, 20} sessions = no other D2 event for the same
    company in sessions (t, t+h] (PREREG A1.2; built from events only — no returns, so allowed for test). Write
    work/events/events_d0.parquet and events_d2.parquet (event_id = f"{window}:{company_id}:{session}").

S6. PROJECTIONS — artifacts/NA-03/call_projection.csv: events per split × tier × window; projected calls for the
    NA-11 production plan (Call A on D0 + Call B on D2 [+ D1 if bars]) for val-A+val-B+test; estimated tokens per call
    = news tokens + 250 context + question tokens (measured from configs later; use 350 for the core battery and
    +600 for the extended battery of PREREG A2, which only the primary API instrument gets); cost at $0.01, $0.02,
    $0.042, $0.10, $0.24 per M. Flag if the $0.042 projection exceeds the NA-11 cap.

## Acceptance criteria

- AC1 — FIT/TUNE/COMPARE DATES: stored metadata shows F5/F6 fit max session ≤ 2025-03-31 (after purge), tune
  ≤ 2025-06-30; comparison uses val-A only (assert in select.py; test).
- AC2 — RULE IS MECHANICAL: a test recomputes apply_rule from filter_comparison.csv and matches frozen.yaml.
  MUTATION: drop the delayed-recall constraint → the test must detect a different choice OR the verifier shows the
  constraint binding status; report which.
- AC3 — UNDERREACTION KEPT: delayed-reaction recall reported for every candidate; the chosen filter's
  delayed-reaction recall ≥ F1's.
- AC4 — NO OUTCOMES FOR TEST: building test events reads no target (ledgers/test_access.jsonl has no NA-03
  entries; events code imports nothing from panel.targets).
- AC5 — EVENT CONSTRAINTS: every event has 1–6 articles, ≤ 600 news tokens, only third_party_ok articles in its
  list; event_id unique.
- AC6 — PROJECTION: call_projection.csv present; the REPORT states whether NA-11 fits its cap at $0.042/M and at
  $0.10/M.
- AC7 — CLEAN-WINDOW FLAGS (A1.2): clean_h exists for h ∈ {1, 2, 5, 10, 20} on every D0 and D2 event; a test plants a
  second D2 event for the same company 3 sessions later → clean_1 and clean_2 True, clean_5/10/20 False; the flag
  code reads events only (no returns, no panel targets).

## Constraints

- Labels and comparisons: ≤ 2025-12-31 only; val-B is NOT used here.
- Log every evaluated filter/threshold/hyperparameter in ledgers/trials.jsonl.
- No API calls. Register artifacts; Conventional Commits; do not merge. Self-audit at the end.
```

### Verification prompt — NA-03

```text
Independent verifier for NA-03 (branch feat/NA-03-filters). READ-ONLY; restore mutations; no commits; no API calls.

1. GATES: `make verify`, `make manifest`.
2. LABELS: for 20 random (company, session) in val-A recompute material and delayed from panel_public by hand.
3. DATES: open the F5/F6 metadata; confirm fit ≤ 2025-03-31 and tune ≤ 2025-06-30; grep select.py for the val-A
   restriction; confirm val-B absent from all NA-03 computations.
4. RULE: recompute the rule from filter_comparison.csv yourself (PREREG §6.8 text) and compare with frozen.yaml.
5. EVENTS: sample 20 test-period events; confirm ≤ 6 articles, ≤ 600 tokens (re-tokenize), all articles
   third_party_ok, all articles within the event's window (t_avail inside W0/W2 by newsaction.calendar).
5b. CLEAN FLAGS (A1.2, AC7): for 10 random events recompute clean_h from events_d2 by hand (next D2 event of the same
   company vs t+h); confirm the flag module imports nothing from panel/targets.
6. LEDGERS: test_access.jsonl has no NA-03 entries; trials.jsonl has the grid points.
7. MUTATIONS: (a) change the material label to |z_cc,t| ≥ 2 only (same-day) → delayed recall table changes and a
   test asserting the label definition turns RED; (b) let F6 fit on data through 2025-06 → the date test RED.
8. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC7 and GAC with numbers (selection shares, recalls, chosen filter).
```

**New tests to add:** `test_events_labels.py`, `test_events_dates.py`, `test_events_rule.py`, `test_events_constraints.py`, `test_events_no_test_outcomes.py`.

**Risks / notes:**
- At a 30% budget, rule filters may be indistinguishable from F6. The rule then picks the simplest, which is fine.
- Tag-based filters depend on retrospective vendor labels. F4/F5 are the tag-free alternatives, and the robustness section reports results under a tag-free filter.

---

## NA-04 — [Build] States: context, numbers-as-words codebook, masking, question battery v1

**Category:** Phase 2 — model inputs. It builds the exact JSON `state` that every decision model, trained or zero-shot, receives:
- context in words, computed through t−1;
- masked news;
- an optional reaction block (Call B).

It also writes the codebook and the question battery v1 (frozen and hashed).

**Goal:**
- `configs/codebook_v1.yaml` and `configs/questions_v1.yaml` (hashed into `frozen.yaml`).
- `src/newsaction/states/*`.
- Call A (D0) and Call B (D2) states for train, val-A and val-B, plus Call A (D0) states for test, in encoding E3 (with E0–E4 for the NA-07 sample).
- The anonymization scanner, the availability-registry checks, and token budgets that fit Laya's 1,024-token context.

**Dependencies:** NA-01, NA-02, NA-03. Consumed by NA-05 through NA-11. · **Estimated time:** 1.5 days · **Branch:** `feat/NA-04-states`

**Expected outputs:**
- **New code:** `src/newsaction/states/{__init__,codebook,context,macro,mask,questions,build,scan}.py`.
- **Configs:** `configs/codebook_v1.yaml`, `configs/questions_v1.yaml`, `configs/aliases.yaml`, `configs/macro_calendar.yaml`.
- **Work files:** `work/states/{callA_d0,callB_d2}_{E3}.parquet` and `work/states/samples/{callA_d0_E0..E4,unmasked}.parquet`.
- **Artifacts:** `artifacts/NA-04/{REPORT.md,token_stats.csv,leak_scan.csv,examples.md}`.
- **Modified:** `configs/availability.yaml`, `configs/frozen.yaml` (`questions_v1_sha256`, `codebook_v1_sha256`).

**Current state (verified 2026-10-24):**
- Laya `typed-decisions` has a 1,024-token context (ModernBERT-large). Its `noul` can follow its labels instead of the state (README issue #156), so yes/no questions are 2-option `choice` with neutral keys.
- Jev: Score ≤ 10 levels; weak at arithmetic and dates; accuracy drops with irrelevant state.
- The OpenRouter Decisions request is `{model, state, questions:{id:{type, instructions, criteria}}}`. For `choice`, `criteria` maps option → description; for `score`, `criteria` is an ordered list (lowest first).
- `work/market/cpi_vintages.parquet` (from NA-00) gives CPI release dates (`realtime_start`). FOMC dates are not in the data and come from the Fed's published calendar (2024–2026).
- PREREG §6.3 and §6.10–§7 define the masking rules, the state content, the codebook and the questions.

### Power prompt — NA-04

```text
You are implementing NA-04 for /Users/amir/Research/NewsAction: the model inputs (states) and the frozen question
battery. Every context value is computed with data through t−1; the reaction block (Call B) appears only in Call B
states and only for train/val now (2026 Call B states are built after the NA-11 freeze, through the lock).

Read first:
  - CLAUDE.md (A4, A5, A6, B9, D15); docs/PREREG.md §2.5 (decision points), §6.3 (masking), §6.9–6.11 (events,
    state content, codebook), §7 (questions, derived quantities), §8.4 (encodings), §15 Amendments A2 (question
    battery v2: core / extended / explain groups) and A3.1, A3.5 (D2 news-only states; optional market states)
  - docs/DATA_CONTRACT.md; artifacts/NA-03/REPORT.md; work/events/events_{d0,d2}.parquet; work/news/
    articles_clean.parquet; work/panel/{panel_public,panel_test_inputs}.parquet; work/market/*.parquet;
    work/snapshot/{symbols,gics,estimates_fy1}.parquet
  - Decision-model request shape: https://openrouter.ai/docs/guides/community/jev and the Laya model card
    (https://huggingface.co/convaiinnovations/laya) for criteria formats and the noul caveat
Branch: feat/NA-04-states.

## Scope

S1. CODEBOOK — states/codebook.py + configs/codebook_v1.yaml exactly per PREREG §6.11: move words (|z| bins),
    sign words, encoders E0 (raw %), E1 (σ numbers, 1 decimal), E2 (words only), E3 (words + "≈k.k× a typical
    day's move"), E4 (percentile words vs own 252-session history); percentile words; β words; attention words;
    tier words; timing words. Pure functions with unit tests at every bin edge.

S2. CONTEXT — states/context.py: company block (sector/industry names, tier words, β_m words, volatility regime =
    σ_cc percentile vs own 252 sessions, abnormal performance over 5/20/60 sessions through t−1 in move words,
    FY1 EPS consensus 30-day revision words from estimates_fy1 as-of t−1, earnings-timing words from
    work/market/earnings_dates.parquet: "a scheduled earnings report falls in this window" when an earnings
    timestamp lies in W0/W2); market block from t−1 data (SPY previous-session move, VIX level percentile and
    1-day change, 10-year yield change z vs 252 sessions, HY OAS change, dollar and oil moves); macro block from
    states/macro.py + configs/macro_calendar.yaml (CPI release dates from cpi_vintages realtime_start; FOMC
    statement dates 2024–2026 from federalreserve.gov — cite the URL in the YAML); attention block (articles in the
    window vs 60-session mean, distinct stories). Register every field in configs/availability.yaml.

S3. MASKING — states/mask.py: per-company alias set = ATOM name with legal suffixes stripped + configs/aliases.yaml
    (hand-curated common names for the top-150 companies, e.g. Alphabet/Google, Meta/Facebook) + ticker, $TICKER,
    EXCH:TICKER; spaCy en_core_web_sm PERSON entities → "an executive"; date/weekday/year/fiscal-period regexes →
    neutral words; share-price levels and percent price moves removed (reuse news.detect.scrub). Keep fundamental
    figures. states/scan.py: residual_leaks(state, company) counts remaining aliases/tickers/years/dates.

S4. QUESTIONS — states/questions.py + configs/questions_v1.yaml with EXACT text from PREREG §7: Call A {Q1
    justified_move (score, 9 levels with the level wording), Q2 materiality (choice, 2 neutral keys), Q3 surprise
    (score 5), Q4 tone (score 5)}; Call B adds the reaction block and asks {Q1, Q5 reaction_adequacy (choice 6),
    Q6 continuation (choice 3)}. No noul anywhere. Add the PREREG A2 groups with EXACT text from A2.2–A2.3: `extended` (Q7–Q15, Call A) and
    `explain` (Q16–Q17, Call B); the loader returns any combination of the groups {core, extended, explain}. Instructions reference state fields in backticks (e.g.
    `news`, `reaction_so_far`). Self-check: no option text may encode empirical findings (e.g. "legal news tends to
    continue") — list the check in the REPORT. Compute sha256 of the YAML → configs/frozen.yaml questions_v1_sha256.

S5. BUILD — states/build.py: canonical JSON (sorted keys, compact separators, UTF-8) with fixed top-level keys
    {company, market, attention, news, reaction_so_far?}; news items {headline, snippet, source_type, timing};
    text = title_clean / snippet_clean (summary variant only if frozen.yaml news.summary_variant_allowed); masked;
    encoding parameter. check_inputs(columns, decision_point) is called for every field (raise on violation).
    Build:
      - callA_d0_E3 for robustness, train, val-A, val-B, test (test allowed: inputs only);
      - callA_d2_E3 = news-only states on W2 news (PREREG A3.1) for robustness, train, val-A, val-B, test (inputs
        only; when W2 adds no news to W0 the state is identical and shares the hash, so it costs nothing extra);
      - (optional, PREREG A3.5) market_E3: one state per session from work/news/market_articles.parquet;
      - callB_d2_E3 for train, val-A, val-B (reaction_so_far = D2 reaction from panel_public: z_cc,t words + SPY
        same-day move + volume vs normal); NOT for test;
      - samples for NA-07: 1,500 val-A + 1,500 val-B D0 events (stratified tier×month, seed 2026) in E0–E4; and an
        unmasked twin of 1,000 val-A events (for NA-06 probes).
    Output columns: event_id, company_id, session, split, window, call, encoding, masked, state_json, state_sha256,
    n_tokens_state, n_tokens_with_questions (ModernBERT tokenizer), n_articles, third_party_ok_all (bool).

S6. TOKEN BUDGET — artifacts/NA-04/token_stats.csv: p50/p95/max of state tokens and state+questions tokens by call
    and encoding. Target: p95(state) ≤ 900 so state + the longest single question fits 1,024 for Laya; if not,
    tighten S5 (fewer articles / shorter snippets) and document.

S7. LEAK SCAN — artifacts/NA-04/leak_scan.csv: residual name/ticker/date/year hits per state for all val-A states.
    examples.md: 3 masked Call A and 2 Call B states (val-A) for human review.

## Acceptance criteria

- AC1 — DETERMINISM: rebuilding produces identical state_sha256 for all rows (test on a 2,000-row sample).
- AC2 — MASKING: residual name/ticker hits < 0.5% of val-A states; years/dates hits < 0.5%. MUTATION: empty the
  alias list → RED.
- AC3 — AVAILABILITY: passing z_id, z_cc or any "post"/"w2" field into a D0 Call A build raises PITError; Call B
  for D2 accepts the D2 reaction only. MUTATION: register z_cc as t_minus_1 → a Call A test RED.
- AC4 — ENCODINGS: E2 context/reaction blocks contain no digits; E3 blocks contain digits only inside "≈k.k×";
  bin-edge unit tests pass for every scale.
- AC5 — TOKENS: p95(state, Call A, E3) ≤ 900 and p95(state + longest question) ≤ 1,024 (else documented
  tightening applied).
- AC6 — NO 2026 CALL B: no callB file contains split == "test"; ledgers/test_access.jsonl has no NA-04 entries.
- AC7 — QUESTIONS FROZEN: questions_v1.yaml text equals PREREG §7 (group core) and A2.2–A2.3 (groups extended,
  explain) — the test compares key strings for every group; sha256 recorded; no noul type present.

## Constraints

- No API calls. No 2026 reactions. Third-party rule: states built only from third_party_ok articles.
- Every numeric value in a state goes through the codebook; no raw prices, tickers, names, dates or years.
- Register artifacts; Conventional Commits; do not merge. Self-audit at the end.
```

### Verification prompt — NA-04

```text
Independent verifier for NA-04 (branch feat/NA-04-states). READ-ONLY; restore mutations; no commits; no API calls.

1. GATES: `make verify`, `make manifest`.
2. READ 10 STATES (val-A, random, seed 7): for each, list anything that could identify the company or the date
   (names, products unique to one firm, people, years, prices). Report counts; compare with leak_scan.csv.
3. PIT: for 5 states, recompute 3 context values (β words, 20-session performance words, VIX percentile words)
   from panel_public/market data using only data through t−1; they must match.
4. QUESTIONS: diff configs/questions_v1.yaml against PREREG §7 wording; confirm the sha256 in frozen.yaml;
   confirm no option text encodes empirical findings.
5. TOKENS: re-tokenize 50 states with the ModernBERT tokenizer and compare with n_tokens_*.
6. MUTATIONS: (a) alias list emptied; (b) z_cc registered as t_minus_1; (c) codebook bin edge 2.0 → 2.5 (a bin-edge
   test must RED). Restore.
7. Confirm no test-period Call B state exists and no NA-04 entry in test_access.jsonl.
8. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC7 and GAC with numbers.
```

**New tests to add:** `test_states_codebook.py` (bin edges), `test_states_mask.py`, `test_states_pit.py`, `test_states_determinism.py`, `test_states_tokens.py`, `test_states_questions_prereg.py`.

**Risks / notes:**
- **Masking is imperfect by nature**: distinctive facts can still identify a company. NA-06's company-identification probe measures this, and results are reported by identifiability.
- **Fundamental figures are kept** because they are content, but they can raise identifiability.

---

## NA-05 — [Build] Decision-model client, cache, budget guard, catalog, canary set, local Laya, pilot

**Category:** Phase 2 — infrastructure plus measurements. The only sanctioned path to any decision model (OpenRouter Decisions API or local Laya):
- typed request and response schemas;
- a deterministic cache;
- the spend ledger with hard caps;
- refusal rules (third-party, blinding, val-B gate);
- `data_collection: deny`;
- an offline mode for verifiers.

Then a **≤ $0.20 pilot** that measures what PREREG §13 needs before real spending.

**Goal:** `src/newsaction/dm/*`, the catalog snapshot, `canary_v1`, and `artifacts/NA-05/pilot.json` answering the 10 pilot questions with numbers.

**Dependencies:** NA-04. Consumed by NA-06, NA-07, NA-09, NA-11, NA-15. · **Estimated time:** 1 day · **Branch:** `feat/NA-05-client-pilot`

**Expected outputs:**
- **New code:** `src/newsaction/dm/{__init__,schemas,cache,client,catalog,laya_local,canary,runner,parse,costmodel}.py`.
- **Cache:** `cache/decisions.sqlite` (gitignored).
- **Artifacts:** `artifacts/NA-05/{REPORT.md,catalog.json,pilot.json,canary_v1.jsonl,canary_baseline.parquet}`.
- **Modified:** `configs/frozen.yaml` (`eligible_models`); `ledgers/spend.jsonl`.
- **Tests:** `tests/test_dm_*.py`.

**Current state (verified 2026-10-24):**
- **Endpoint:** `POST https://openrouter.ai/api/alpha/decisions`, Bearer `OPENROUTER_API_KEY`.
  - Body: `model`, `state`, `questions` (`id → {type, instructions, criteria}`); optional `session_id`, `user`, `trace`, `provider` (routing/data policy, incl. `data_collection`, `zdr`, `max_price`).
  - Response: `id`, `model` (the exact build), `provider`, `answers` (each with `type`; `choice` → `choice`, `probabilities`, `confidence`; `score` → `score`, `legend`, `probabilities`, `confidence`; these fields are marked optional), `usage{input_tokens, output_tokens, cost}`.
  - Sources: [OpenRouter decisions skill](https://github.com/OpenRouterTeam/skills/blob/main/skills/openrouter-decisions/references/decisions-api.md); [Jev guide](https://openrouter.ai/docs/guides/community/jev).
- **Catalog:** `GET https://openrouter.ai/api/v1/models?output_modalities=decisions` returned **30 entries** on 2026-10-24 (created 2026-09-18 … 2026-10-21; input $0–0.24/M; output free):
  - typesafe/jev-1.13, jev-1.14, ~jev-latest
  - jaredpalmer/kev-4b (8K ctx)
  - respan/span-01-lite(+:free), span-01, span-02
  - upstage/solar-decide, solar-decide-flash
  - inception/mercury-decide(+:free)
  - togethercomputer/tev1-4b-experimental
  - cloudflare/clef, clef-flash, clef-omni
  - liquid/d1, d1-ultra
  - openai/gpt-6-luna-decisions ($0.10)
  - nace-ai/drex-v1.5, drex-v2.0, drex-max
  - microsoft/microsoft-decision-1
  - scaledown/classify-1
  - ~perplexity/pplx-decider-latest, ~pplx-decider-flash-latest, perplexity/pplx-decider-v1.2, pplx-decider-flash-v1.2
  - baseten/elephant-1:free, mammoth-1:free
- **Laya:** `pip install laya`; `laya.load("convaiinnovations/laya", subfolder="typed-decisions")`; `agent.predict(state, questions)` → `result["answers"][id]`.
  - Laya ships overconfident and is near chance zero-shot.
  - `act_probability` carries no signal; use `confidence`.
  - It takes about 1.7 s for a 4K-token input on Apple GPU.
- **Unknowns the pilot must measure:**
  - billing basis (state billed once per call, or per question);
  - truncation behaviour;
  - repeat variance and whether a seed exists;
  - question interaction;
  - rate limits and latency;
  - acceptance of `data_collection: deny`.

### Power prompt — NA-05

```text
You are implementing NA-05 for /Users/amir/Research/NewsAction: the single sanctioned decision-model client and a
≤ $0.20 measurement pilot. Pilot states must be train-period (≤ 2025-06-30) or synthetic — never val-A/val-B/test.

Read first:
  - CLAUDE.md (C12–C14, D15–D16, B8); docs/PREREG.md §7 (questions, derived quantities), §8.1 (eligibility),
    §13 (budget + STOP), §15 A2 (extended battery; A2.6 cutting order)
  - docs/DATA_CONTRACT.md; artifacts/NA-04/REPORT.md; configs/questions_v1.yaml; work/states/*.parquet
  - src/newsaction/{ledger,lock,io}.py
  - API reference: https://github.com/OpenRouterTeam/skills/blob/main/skills/openrouter-decisions/references/decisions-api.md
    and https://openrouter.ai/docs/guides/community/jev ; Laya: https://huggingface.co/convaiinnovations/laya
Operator prerequisite: OPENROUTER_API_KEY in .env (never print it); ≥ $1 credit.
Branch: feat/NA-05-client-pilot.

## Scope

S1. SCHEMAS — dm/schemas.py (pydantic v2): DecisionRequest {model, state (dict|str), questions (dict),
    provider = {"data_collection": "deny"}, session_id}; ChoiceAnswer, ScoreAnswer (legend, probabilities,
    confidence optional), Usage, DecisionResponse; strict parsing that rejects missing `type` and probabilities that
    do not sum to 1 ± 1e-6 (record as invalid, not silently fixed).

S2. CACHE — dm/cache.py: sqlite keyed by sha256(canonical_json({model, state, questions, provider, params,
    repeat_idx})); stores request hash parts, response JSON, model build, provider, usage, latency, created_at, chunk.
    A changed state/question/model/param MUST miss.

S3. CLIENT — dm/client.py: httpx + tenacity (retry 429/5xx with exponential backoff + jitter; max 5); asyncio
    concurrency semaphore (configurable); `offline=True` → cache only (raise on miss); dry_run(requests) → projected
    tokens and USD via dm/costmodel.py (catalog price × estimated tokens; calibrated by the pilot); SpendLedger.reserve
    before each call and record(usage.cost) after; REFUSALS (raise, never send): (a) any state with
    third_party_ok_all == False; (b) any state with session ≥ 2026-01-02 unless lock.is_frozen(); (c) any val-B state
    unless configs/frozen.yaml allow_val_b == true; (d) unmasked states unless the call is tagged as a registered
    probe; (e) any model not in configs/frozen.yaml eligible_models (except during catalog/pilot with
    explicit pilot=True); (f) `:free` model ids unless operator approval is recorded in frozen.yaml.

S4. CATALOG — dm/catalog.py: GET /api/v1/models?output_modalities=decisions → artifacts/NA-05/catalog.json
    (id, name, created, context_length, pricing); eligibility per PREREG §8.1 (drop ~aliases and :free duplicates);
    after the pilot also drop models that fail (errors, no probabilities, reject data_collection deny, silent
    truncation) → configs/frozen.yaml eligible_models with reasons for every exclusion.

S5. LOCAL LAYA — dm/laya_local.py (install group "laya"): wrapper returning the same DecisionResponse shape (usage
    cost 0; latency measured; model = "local/laya-typed-decisions@<revision>"), device mps → cpu fallback, max_len
    1024; also a `local/laya-base` variant (root checkpoint). Record revision hashes.

S6. PARSE — dm/parse.py: derived quantities exactly per PREREG §7 (N̂, E|N̂|, M, J, W, C, confidence summaries);
    unit tests with hand-made probability vectors.

S7. CANARY — dm/canary.py: 50 fixed states (30 train-period masked states + 20 synthetic) → artifacts/NA-05/
    canary_v1.jsonl (state + questions + sha256). compare(model) → max |Δp| vs baseline; baseline stored for every
    pilot model in canary_baseline.parquet.

S8. PILOT (≤ $0.20 total; models: typesafe/jev-1.14, openai/gpt-6-luna-decisions, inception/mercury-decide,
    liquid/d1, perplexity/pplx-decider-v1.2 + local Laya). Answer with numbers in artifacts/NA-05/pilot.json:
    1 billing basis: the same state with 1, 2 and 4 questions and with the full core + extended battery (PREREG
      A2) → input_tokens and cost (is state billed once?);
    2 usage.cost vs catalog price × input_tokens (ratio); are failed calls billed?;
    3 truncation: a sentinel sentence at the END of 2K/4K/8K-token synthetic states + a 2-option question "does the
      text mention <sentinel>?" → detected?;
    4 repeat variance: 20 states × 5 repeats (repeat_idx in the cache key) → mean/max |Δp|; does any `seed`
      parameter change it?;
    5 question interaction: Q1 alone vs Q1 within the core battery vs within core + extended (A2) → mean |ΔN̂|;
    6 latency p50/p95 and errors at concurrency 1/4/8/16 (≤ 40 calls each); observed rate-limit headers;
    7 response format: probabilities sum, legend present, score position consistent with probabilities;
    8 numeracy/anchoring (synthetic): fixed news; reaction words for 7 magnitudes × 2 directions in Call B → is
      reaction_adequacy monotone?;
    9 data policy: are requests with provider.data_collection = "deny" accepted per model?;
    10 model build ids returned; catalog snapshot hash.
    Update dm/costmodel.py from (1)–(2). Apply PREREG §13 STOP rules: if state is billed per question, write the
    consequence and the reduced plan in the REPORT and STOP for the operator.

## Acceptance criteria

- AC1 — BUDGET GUARD: with a mock transport, a batch whose projection exceeds the chunk cap raises before any send;
  ledger total equals Σ usage.cost (reconcile() == 0). MUTATION: skip reserve() → RED.
- AC2 — CACHE: a repeated request makes no network call and records no spend (mock); changing one character of the
  state misses. MUTATION: drop `questions` from the key → RED.
- AC3 — REFUSALS: tests for (a)–(f) each raise. MUTATION: remove the 2026 date guard → RED.
- AC4 — PILOT: every one of the 10 items has a numeric/boolean answer in pilot.json; spend ≤ $0.20 (ledger); the
  ledger shows no session ≥ 2025-07-01 among pilot states.
- AC5 — LOCAL LAYA: returns valid DecisionResponse objects for 20 canary states; probabilities sum to 1.
- AC6 — CANARY: canary_v1 has 50 states with hashes; baselines stored for each pilot model.
- AC7 — ELIGIBILITY: frozen.yaml eligible_models lists every catalog id with include/exclude and a reason.

## Constraints

- Every network call goes through dm/client.py. Never print or log the key. data_collection deny on every call.
- Pilot states: train-period or synthetic only. Spend cap $0.20 (hard).
- Register artifacts; Conventional Commits; do not merge. Self-audit at the end (include the pilot numbers).
```

### Verification prompt — NA-05

```text
Independent verifier for NA-05 (branch feat/NA-05-client-pilot). READ-ONLY; restore mutations; no commits; client in
offline=True mode ONLY ($0 spend).

1. GATES: `make verify`, `make manifest`.
2. LEDGER vs CACHE: sum usage.cost in cache/decisions.sqlite rows with chunk == "NA-05" and compare with
   ledgers/spend.jsonl NA-05 total (difference < $0.0001); total ≤ $0.20.
3. DATES: list the sessions of every state sent in NA-05 (from the cache) → all ≤ 2025-06-30 or synthetic.
4. PILOT: open pilot.json; for items 1, 2, 4, 5 recompute the reported numbers from cached rows.
5. REFUSALS: run the refusal tests; additionally construct by hand a test-period state and a third_party_ok=False
   state and call the client in offline mode with a mock transport → both must raise before any transport call.
6. MUTATIONS: (a) skip reserve(); (b) remove questions from the cache key; (c) remove the 2026 guard. Each RED.
7. Confirm no :free model was called without an approval record; confirm provider.data_collection == "deny" in
   every cached request.
8. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC7 and GAC; restate the pilot's billing-basis finding and any STOP condition.
```

**New tests to add:** `test_dm_schemas.py`, `test_dm_cache.py`, `test_dm_budget.py`, `test_dm_refusals.py`, `test_dm_parse.py`, `test_dm_laya_local.py` (marked slow), `test_dm_canary.py`.

**Risks / notes:**
- **The alpha endpoint may change fields.** The strict schemas surface this rather than hide it.
- **Some providers may reject `data_collection: deny`.** Those models are excluded; their exclusion is a reported finding.
- **Rate limits on cheap models** are measured in the pilot to size NA-11's concurrency.

---

## NA-06 — [Research] Zero-shot decision-model tournament + contamination probes

**Category:** Phase 3 — model selection (validation only). It finds the best off-the-shelf decision models on **val-A**, with the pre-registered Model Confidence Set and contamination screens. Every eligible model postdates our data, so a "best memoriser" must not win.

**Goal:**
- Stage 1: all eligible models plus local Laya × 700 val-A D0 events (Call A); MCS.
- Stage 2: ≤ 6 survivors × 3,000 val-A events (Calls A and B), plus probes: company/month identification, counterfactual edits, masked vs. unmasked, shuffled news.
- A leaderboard with screen pass/fail, the trials logged, and val-B unlocked for NA-07 and NA-11.

**Dependencies:** NA-05 (client, eligibility, cost model), NA-04 (states and samples). Consumed by NA-07, NA-11, NA-14 (Figure 3). · **Estimated time:** 1 day · **Branch:** `feat/NA-06-tournament`

**Expected outputs:**
- **New code:** `src/newsaction/tournament/{__init__,sample,metrics,mcs,probes,edits,run}.py`.
- **Work files:** `work/dm/tournament/{stage1,stage2,probes}.parquet`.
- **Artifacts:** `artifacts/NA-06/{REPORT.md,leaderboard.csv,fig3_data.csv,probe_details.csv}`.
- **Modified:** `configs/frozen.yaml` (`tournament:`, `allow_val_b: true`), `ledgers/{spend,trials}.jsonl`.
- **Tests:** `tests/test_tournament_*.py`.

**Current state (verified 2026-10-24):**
- There are 30 catalog entries, about 25 distinct after removing aliases and `:free`. The final eligibility list is NA-05's.
- Prices range $0.01–0.24/M input. Most are $0.02–0.06; `openai/gpt-6-luna-decisions` is $0.10 and `cloudflare/clef` $0.24.
- Third-party benchmarks are contested. Examples: Laya 0.766 vs Jev 0.727 argmax (vendor); a community run gave Jev 0.9065 vs Laya 0.6863; Perplexity claims 85.7% vs Jev 84.5%. None is on finance, so this tournament is the evidence.
- Laya zero-shot is near chance on typed decisions, so it is expected to do poorly zero-shot; it is still included.
- PREREG §8.2–8.3 fixes the samples, metrics, MCS and screens.

### Power prompt — NA-06

```text
You are implementing NA-06 for /Users/amir/Research/NewsAction: the zero-shot tournament of decision models on
val-A only, with contamination probes, exactly per PREREG §8.2–8.3. Spend cap: $4.00 (hard; dry-run first).

Read first:
  - CLAUDE.md (B9, B10, C12–C14); docs/PREREG.md §7 (derived quantities), §8.1–8.3, §11.1, §11.4, §15 A2.5
    (reading validity — report only)
  - docs/DATA_CONTRACT.md; artifacts/NA-05/{REPORT.md,pilot.json,catalog.json}; configs/frozen.yaml
    (eligible_models); work/states/callA_d0_E3.parquet, callB_d2_E3.parquet, samples/unmasked.parquet;
    work/events/*.parquet; work/panel/panel_public.parquet (val-A targets)
  - src/newsaction/dm/{client,parse,runner,costmodel}.py
Branch: feat/NA-06-tournament.

## Scope

S1. SAMPLES — tournament/sample.py (seed 2026): stage-1 = 700 val-A D0 events stratified by tier × month;
    stage-2 = 3,000 val-A D0 events (superset of stage-1) and their D2 twins where a D2 event exists; probe
    subsamples: 1,000 events with unmasked twins (NA-04 sample), 400 for identification, 200 editable for
    counterfactuals (S4). Events in the first 5 sessions of val-A are excluded (embargo).

S2. STAGE 1 — all eligible models + local Laya (laya-typed-decisions and laya-base) on stage-1 Call A E3 masked
    states. DRY RUN FIRST: print projected USD per model and total; abort if > $1.5 for stage 1. Metric: per model,
    daily Spearman IC between N̂ and z_cc,t (PREREG primary) and with e5 (secondary); Newey–West t on the daily
    series. MCS (tournament/mcs.py; Hansen–Lunde–Nason; α = 0.10; stationary bootstrap over days, block 5,
    10,000 reps; loss = −daily IC) → survivors. Log every model as a trial.

S3. STAGE 2 — up to 6 survivors (highest stage-1 IC; ties → cheaper) on stage-2 events: Call A (all 3,000) and
    Call B D2 (twins). Report IC(N̂_A, z_cc), IC(N̂_A, e5), IC(J, y2), IC(N̂_B, z_cc), calibration (ECE of the
    3-class sign at ±0.5σ), cost per 1,000 decisions, p50/p95 latency, invalid-response rate.

S4. PROBES (stage-2 models) — tournament/probes.py + edits.py:
    a. company identification: masked state + a 4-option choice "Which company is this news most likely about?"
       options = true company + 3 same-GICS-industry members (names) → accuracy (chance 0.25);
    b. month identification: 4 options (true month + 3 random months in 2024-07..2025-12) → accuracy (report);
    c. counterfactual edits: 200 states whose news contains an editable outcome phrase (beat↔missed,
       raised↔lowered [guidance], upgrade↔downgrade, above↔below expectations) edited by rules (documented in
       edits.py) → flip rate = share with sign(N̂_edit) ≠ sign(N̂_orig) among pairs with |N̂_orig| ≥ 0.25;
    d. masked vs unmasked: paired IC on the 1,000 twins;
    e. shuffled news: Call A states with the `news` block replaced by another random val-A event's news →
       mean daily IC with Newey–West t.
    f. reading validity (PREREG A2.5; REPORT ONLY, never a screen): the top stage-2 model answers the extended
       battery on 500 stage-2 events → agreement of event_type with the vendor tag, quantified with tag_quantified,
       scheduled with the earnings calendar, credibility = rumor with tag_rumor (confusion tables).
    Apply PREREG §8.3 screens mechanically (company-ID ≤ 0.40; flip ≥ 0.70; unmasked − masked ≤ 0.02 or paired
    |t| < 2; shuffled-news |t| < 2).

S5. LEADERBOARD — artifacts/NA-06/leaderboard.csv: every eligible model (id, price, stage-1 IC ± se, MCS member,
    stage-2 metrics, probe results, screen pass/fail, contamination score = company-ID accuracy − 0.25) and
    fig3_data.csv (price per 1,000 decisions vs IC with CI, MCS flag, screen flag). Report the Spearman correlation
    between model rank and contamination score (does skill track memorisation?).

S6. HANDOFF — configs/frozen.yaml tournament: {stage1_survivors, stage2_survivors_passing, leaderboard_sha};
    set allow_val_b: true (val-B may now be used by NA-07 confirmation and NA-11 selection — and nothing else).

## Acceptance criteria

- AC1 — VAL-A ONLY: an audit over the cache rows of this chunk shows every state session in val-A (≥ 5 sessions
  after 2025-07-01) or probe/synthetic; no val-B, no test.
- AC2 — LEADERBOARD COMPLETE: every eligible model appears with stage-1 IC and MCS membership; the MCS
  implementation passes a unit test on synthetic losses with a known best model.
- AC3 — SCREENS MECHANICAL: a test recomputes pass/fail from probe_details.csv and matches the leaderboard.
- AC4 — BUDGET: dry-run projection within ±20% of actual; spend ≤ $4.00; ledger reconciles.
- AC5 — CONTAMINATION REPORTED: rank-vs-contamination correlation and per-model company-ID accuracy in the REPORT.
- AC6 — TRIALS: one trials.jsonl entry per (model, stage, metric) evaluated.

## Constraints

- val-A only (the client refuses val-B until you set allow_val_b at the very end, after all calls are done).
- data_collection deny on every call; no :free endpoints without recorded approval.
- Do not tune prompts/questions here (they are frozen); encoding is E3; masking on (except probe d).
- Register artifacts; Conventional Commits; do not merge. Self-audit at the end.
```

### Verification prompt — NA-06

```text
Independent verifier for NA-06 (branch feat/NA-06-tournament). READ-ONLY; offline client only ($0); restore
mutations; no commits.

1. GATES: `make verify`, `make manifest`.
2. DATE AUDIT: from cache/decisions.sqlite rows with chunk == "NA-06", list min/max state session → within val-A
   (or probe/synthetic markers). Any val-B/test row fails AC1.
3. RECOMPUTE: for two models (the leader and one non-survivor), recompute stage-1 daily IC and its mean from cached
   answers + panel_public z_cc; compare with leaderboard.csv (tolerance 1e-6).
4. MCS: run tournament/mcs.py on the cached daily losses with a different seed; survivors set should be the same or
   differ only at the margin (report).
5. SCREENS: recompute pass/fail from probe_details.csv using PREREG §8.3 thresholds.
6. EDITS: read 10 counterfactual pairs; confirm each edit flips the factual outcome and changes nothing else.
7. MUTATION: change the company-ID threshold in code to 0.90 → the screen test must RED (thresholds must come from
   PREREG/config, not ad hoc).
8. LEDGER: NA-06 spend ≤ $4; reconcile; dry-run vs actual within ±20%.
9. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC6 and GAC; list the survivors and screen outcomes.
```

**New tests to add:** `test_tournament_mcs.py` (synthetic known best), `test_tournament_sample.py` (stratification, embargo), `test_tournament_screens.py`, `test_tournament_edits.py`.

**Risks / notes:**
- **A model that passes the screens can still be contaminated.** The headline-claim rule (PREREG §1.3) and the forward test (NA-15) are the backstops.
- **Laya zero-shot will likely rank low.** Its value comes from fine-tuning (NA-08).

---

## NA-07 — [Research] Encoding ("numbers as words") and anchoring study

**Category:** Phase 3 — input design (validation only). It decides two things by pre-registered rules:
- **Which numeric encoding to use** (E0–E4). An outcome-free numeracy probe checks that models read the words monotonically.
- **One call per event or two.** If a model that sees the reaction anchors its news reading on it, N̂ must come from a separate news-only call.

**Goal:** `configs/frozen.yaml` gets `encoding` and `anchoring` (`calls_per_event`), with val-A search and val-B confirmation, and the evidence in `artifacts/NA-07`.

**Dependencies:** NA-06 (survivors; `allow_val_b`). Consumed by NA-08 (retrain if the encoding changes), NA-11. · **Estimated time:** 1 day · **Branch:** `feat/NA-07-encoding`

**Expected outputs:**
- **New code:** `src/newsaction/encoding/{__init__,study,numeracy,anchoring}.py`.
- **Work files:** `work/dm/encoding/*.parquet`.
- **Artifacts:** `artifacts/NA-07/{REPORT.md,encoding_ic.csv,numeracy.csv,anchoring.csv}`.
- **Modified:** `configs/frozen.yaml`; ledgers.

**Current state (verified 2026-10-24):**
- E3 ("large rise (≈2.3× a typical day's move)") is the default (the operator liked this style).
- Jev's guidance says to compute numbers in code and hand the model the semantic part.
- NA-04 built E0–E4 samples: 1,500 val-A and 1,500 val-B D0 events.

### Power prompt — NA-07

```text
You are implementing NA-07 for /Users/amir/Research/NewsAction: the encoding and anchoring decisions per PREREG §8.4.
Spend cap: $2.00 (dry-run first).

Read first:
  - CLAUDE.md; docs/PREREG.md §6.11 (encodings), §7 (derived quantities), §8.4 (rules), §11.1
  - artifacts/NA-06/{REPORT.md,leaderboard.csv}; configs/frozen.yaml (tournament, allow_val_b);
    work/states/samples/callA_d0_E0..E4 (val-A and val-B); work/states/callB_d2_E3.parquet
  - src/newsaction/dm/*, src/newsaction/states/{codebook,build}.py
Branch: feat/NA-07-encoding.

## Scope

S1. ENCODING STUDY (val-A search) — the top-3 stage-2 survivors that passed the screens (by stage-2 Call A IC;
    ties → cheaper) × E0–E4 × the 1,500 val-A sample (Call A). Metric: mean daily IC(N̂, z_cc) with block-bootstrap
    CIs. Choose the best encoding per PREREG §8.4 (pooled across the 3 models by mean rank; ties → E3).

S2. CONFIRMATION (val-B) — the same 3 models on the 1,500 val-B sample in {best, E3}. Rule: keep best unless it is
    worse than E3 by more than 1 bootstrap SE; else E3.

S3. NUMERACY PROBE (outcome-free) — encoding/numeracy.py: 30 real masked val-A news blocks × synthetic Call B
    reaction blocks at 7 magnitudes (negligible…extreme) × 2 directions in the chosen encoding → for each model,
    share of (news, direction) series where P(too_large)+P(much_too_large) is non-decreasing in magnitude and
    P(too_small)+P(much_too_small) non-increasing (monotone). Target ≥ 0.90; report per model; < 0.90 → note in
    REPORT (the model mis-reads the words) and prefer E3 for that model.

S4. ANCHORING — encoding/anchoring.py: on 1,500 val-A D2 events, compare N̂ from Call A (news only) with N̂ from
    Call B (news + reaction) for the top-3 models: slope of N̂_B on G (OLS, with N̂_A as control) and corr(N̂_A,
    N̂_B). Rule (PREREG §8.4): anchoring present if slope ≥ 0.30 or corr < 0.70 → calls_per_event = 2 (N̂ from
    Call A); otherwise 1 is allowed.

S5. HANDOFF — configs/frozen.yaml encoding: {chosen, val_a_table_sha, val_b_check}; anchoring: {present, slope,
    corr, calls_per_event}. Log every (model, encoding, split) as a trial.

## Acceptance criteria

- AC1 — NUMERACY: per-model monotone share reported; the chosen encoding has ≥ 0.90 for the leading model (or the
  REPORT documents why E3 is kept).
- AC2 — RULES MECHANICAL: tests recompute the encoding choice (val-A + val-B check) and the anchoring decision
  from the CSVs and match frozen.yaml.
- AC3 — DATA SCOPE: val-A for search, val-B used only for the S2 check (cache audit).
- AC4 — BUDGET: ≤ $2.00; dry-run within ±20%; ledger reconciles.
- AC5 — TRIALS logged (count equals models × encodings × splits evaluated).

## Constraints

- No question changes. No test data. Register artifacts; Conventional Commits; do not merge. Self-audit.
- If the chosen encoding is not E3, write "NA-08 must retrain with <encoding>" at the top of the REPORT.
```

### Verification prompt — NA-07

```text
Independent verifier for NA-07 (branch feat/NA-07-encoding). READ-ONLY; offline client only; restore mutations.

1. GATES: `make verify`, `make manifest`.
2. CACHE AUDIT: sessions of NA-07 states: val-A for S1/S3/S4, val-B only for S2.
3. RECOMPUTE the encoding table for one model from cached answers; re-apply the rule; compare with frozen.yaml.
4. NUMERACY: re-score monotonicity for one model from cached answers.
5. ANCHORING: recompute slope and corr; re-apply the rule.
6. MUTATION: set the anchoring threshold to 0.9 in code → the rule test must RED (thresholds from PREREG/config).
7. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC5 and GAC with the chosen encoding and calls_per_event.
```

**New tests to add:** `test_encoding_rule.py`, `test_numeracy_scoring.py`, `test_anchoring_rule.py`.

**Risks / notes:**
- **Encoding differences may be small.** The rule then keeps E3, which is the expected outcome and is fine.
- **If anchoring is strong,** production needs two calls per event; NA-11's budget assumes this.

---

## NA-08 — [Build] Trained decision models on Kaggle: Laya-Fin (primary) + ModernBERT-large clean anchor

**Category:** Phase 3 — the trainable decision model chosen by the operator. Accurate on finance after training, cheap, trainable. It fine-tunes **Laya** on our finance questions with the official Kaggle 2×T4 recipe. An identical-head **ModernBERT-large** model (Dec-2024 checkpoint, no vendor distillation) is the uncontaminated anchor.

**Goal:**
- A private Kaggle dataset: masked states; train/val labels; **test Call A states without labels**.
- A parameterized notebook (`INIT ∈ {laya, modernbert}`).
- Throughput-sized runs within Kaggle quotas: shuffled-label and reproducibility controls; temperatures per (question type, option count) on val-A.
- Predictions downloaded and imported: val-A, val-B, and test Call A.
- Model cards.

**Dependencies:** NA-04 (states), NA-03 (events), NA-01 (labels ≤ 2025). Optional: NA-07 (encoding; retrain if not E3). Runs in parallel with NA-05 to NA-07. Consumed by NA-11, NA-12. · **Estimated time:** 2–3 days (mostly Kaggle wall-clock) · **Branch:** `feat/NA-08-trained-dm`

**Expected outputs:**
- **New code:** `src/newsaction/train/{__init__,labels,kaggle_export,import_preds,cards}.py`.
- **Notebook:** `src/newsaction/train/notebook/newsaction_laya_fin.ipynb`.
- **Work files:** `work/kaggle/dataset/*` (parquet + `dataset-metadata.json`) and `work/kaggle/predictions/*.parquet`.
- **Artifacts:** `artifacts/NA-08/{REPORT.md,model_card_laya_fin.md,model_card_anchor.md,throughput.json,controls.json}`.
- **Tests:** `tests/test_train_*.py`.

**Current state (verified 2026-10-24):**
- **Laya repos:** `convaiinnovations/laya` (subfolders root / `multilingual` / `typed-decisions`) and `convaiinnovations/laya-typed-decisions`.
  - Apache-2.0, last modified 2026-10-03.
  - Architecture: ModernBERT-large backbone (395M, fully fine-tuned) + a decision head trained from scratch (2 transformer layers, an option-marker scorer, an act/escalate head); 421M total; 1,024-token context.
  - Benchmarks: base near chance zero-shot (0.362 vs 0.318 random); the fine-tuned typed-decisions checkpoint reaches 0.766 (on the vendor's split).
  - Calibration: ships overconfident; a per-type temperature takes ECE 0.466 → 0.081.
  - Speed: 103–332 questions/s batched on one T4.
  - Official notebook: `https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb` (builds the dataset, trains, fits temperatures, evaluates, pushes to the Hub — **we must not push**).
- **ModernBERT-large:** `answerdotai/ModernBERT-large` (arXiv 2412.13663, Dec 2024; 2T tokens; Apache-2.0).
- **Kaggle:** free tier is 2×T4, ≤ 12 h per session, ~30 GPU-hours per week. No `~/.kaggle` token and no kaggle CLI on this machine yet.
- **Operator choice (2026-10-24):** Kaggle free GPUs.
- **Data scale:** roughly 70–90K train events (D0 + D2) after the filter. NA-03's REPORT has the exact counts.

### Power prompt — NA-08

```text
You are implementing NA-08 for /Users/amir/Research/NewsAction: fine-tune Laya on our finance questions (Laya-Fin)
and train an identical-head ModernBERT-large anchor, on Kaggle free 2×T4, with strict data hygiene. You prepare
everything locally; the OPERATOR uploads and runs on Kaggle following your exact instructions; you then import the
predictions. No test labels ever leave this machine. Nothing is pushed to the Hugging Face Hub.

Read first:
  - CLAUDE.md (D15–D16, B9); docs/PREREG.md §4 (splits/purge), §5.6 (targets), §7 (questions), §9 (trained models),
    §11.2 (calibration metrics)
  - docs/DATA_CONTRACT.md; artifacts/NA-03/REPORT.md, artifacts/NA-04/REPORT.md, (if present) artifacts/NA-07/REPORT.md
  - work/states/{callA_d0_E3,callA_d2_E3,callB_d2_E3}.parquet; work/events/*.parquet; work/panel/panel_public.parquet
  - The official notebook (fetch and READ it before writing ours):
    https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb
    and https://huggingface.co/convaiinnovations/laya (README: fine-tuning, calibration, noul caveat, act_probability)
Branch: feat/NA-08-trained-dm.

## Scope

S1. LABELS — train/labels.py from panel_public (≤ 2025-12-31 only; purge per §4.1): H-react = 9-level bin of e5
    with Q1 bin edges (z: ±0.5, ±1, ±2, ±3 → levels 0..8); H-mag = 5-level bin of |z_cc,t| at {0.5, 1, 2, 3};
    H-cont (Call B D2 only, events with |G| ≥ 0.5) = reverse / stall / continue from sign(G)·z(O_{t+1}→C_{t+5}) with
    ±0.5 bands. Splits: train (fit), val-A (early stopping + temperatures), val-B (held-out evaluation).

S2. EXPORT — train/kaggle_export.py → work/kaggle/dataset/: examples as (example_id, event_id, split, call,
    question_id, state_json, question_json (from configs/questions_v1.yaml in Laya's input format), label_index
    [train/val only]) where question_id ∈ {react (Q1 wording), mag (score 5: "How large will the stock's move
    relative to the market and its sector be today?" — add this as an internal training question documented in the
    model card, NOT used for API models), cont (Q6 wording)}; BLOCK DROPOUT: for Call B train examples also emit a
    copy with `reaction_so_far` removed (p = 0.3 sampling at export, seeded) so the model serves Call A too;
    Call A examples include D0 (W0) and D2 (W2, PREREG A3.1) news-only states (same react label e5); labels ONLY
    for train and val-A; val-B = Call A and Call B states with NO label column; test = Call A states (D0 and D2)
    ONLY, NO label column. dataset-metadata.json with "isPrivate": true. Only third_party_ok states. Write a
    sha256 manifest; a schema test asserts the val-B and test files lack any label column.

S3. NOTEBOOK — src/newsaction/train/notebook/newsaction_laya_fin.ipynb adapted from the official one:
    parameters INIT ∈ {"laya","modernbert"} (laya → load convaiinnovations/laya subfolder typed-decisions; modernbert
    → answerdotai/ModernBERT-large encoder + the SAME decision-head architecture freshly initialised), SEED,
    MAX_LEN = 1024, LR_BACKBONE 2e-5, LR_HEAD 1e-4, EPOCHS ≤ 3, early stopping on val-A loss, mixed precision
    (fp16 on T4), DDP or DataParallel over 2 GPUs as the official notebook does, gradient checkpointing if needed.
    Loss: the official recipe's proper-scoring objective (cross-entropy/log-loss is acceptable and strictly
    proper). After training: fit one temperature per (question type, option count) on val-A by minimising NLL;
    report ECE (15 bins) before/after on val-A and val-B. Outputs to /kaggle/working: predictions for val-A,
    val-B, test (probabilities per question per example), run_record.json (dataset version, INIT and its revision
    hash, seed, epochs run, timings, GPU), checkpoint (kept in /kaggle/working only; NEVER push to the Hub; remove any
    push cells).

S4. THROUGHPUT PILOT — 5% of train for 200 steps per INIT → examples/s; project epoch time; plan the runs inside
    the quota (≤ 12 h per session, ~30 GPU-h/week): target Laya-Fin seeds {13, 17, 23} + anchor seeds {13, 17, 23};
    if over quota, reduce in this order: anchor seeds → 1; MAX_LEN 768; epochs 2; document the plan in
    throughput.json and the REPORT.

S5. CONTROLS — (a) shuffled-label run (INIT=laya, seed 13, 1 epoch, labels permuted within split) → val-A mean
    daily IC of N̂ vs e5 not significant (|t| < 2); (b) reproducibility: rerun Laya-Fin seed 13 → val-A IC within
    ±0.003 of the first run (if quota forbids, record a deferral the operator must approve). controls.json.

S6. OPERATOR RUNBOOK (in the REPORT, exact commands): install the kaggle group (`uv sync --group kaggle`), place
    the token (~/.kaggle/kaggle.json, chmod 600), `kaggle datasets create -p work/kaggle/dataset` (private),
    create/upload the notebook as a private kernel with GPU T4×2 and the dataset attached, run order (throughput
    pilot → shuffled-label → Laya-Fin seeds → anchor seeds → repro), and `kaggle kernels output <kernel> -p
    work/kaggle/predictions/<run>` to download.

S7. IMPORT — train/import_preds.py: map example probabilities back to events; compute N̂ (react head, PREREG §7
    midpoints), E|N̂|, magnitude probabilities, J/C/W analogues for the cont head; 3-seed ensemble = mean of
    probabilities; write work/kaggle/predictions/{laya_fin,anchor}_{val_a,val_b,test_callA}.parquet in the common
    prediction schema (event_id, model, call, question, probabilities, derived columns).

S8. MODEL CARDS — train/cards.py → model_card_{laya_fin,anchor}.md: data ranges, INIT revision hashes, heads,
    hyper-parameters, seeds, compute, val-A IC (with bootstrap CI), val-A ECE before/after temperature, controls.
    Do NOT compute any val-B metric here (val-B predictions are produced and stored; NA-11 evaluates them).

## Acceptance criteria

- AC1 — NO VAL-B/TEST LABELS: schema test proves val-B and test files have no label column; the uploaded dataset
  hash equals the local manifest; isPrivate true.
- AC2 — DATE HYGIENE: training examples' sessions ≤ 2025-06-30 after purge; temperatures/early stopping on val-A
  only (run_record + code asserts).
- AC3 — CONTROLS: shuffled-label |t| < 2; reproducibility within ±0.003 (or an operator-approved deferral recorded).
- AC4 — IMPORT: predictions exist for val-A, val-B and test Call A for both models with event_ids matching the
  states; probabilities sum to 1.
- AC5 — CALIBRATION REPORTED: val-A ECE before/after temperatures in both model cards; no val-B metric anywhere in
  NA-08 outputs (grep the cards and REPORT).
- AC6 — NO HUB PUSH: the notebook contains no push/upload-to-hub calls (grep) and run_record says so.

## Constraints

- Only third_party_ok, masked states go to Kaggle. Test labels never leave the machine. No Hub pushes.
- No OpenRouter calls in this chunk. No 2026 Call B states (they are built after the NA-11 freeze; NA-11 runs the
  test Call B inference with these checkpoints).
- If NA-07 later picks an encoding other than E3, retrain once with that encoding (PREREG §9.1) and record it.
- Register artifacts; Conventional Commits; do not merge. Self-audit at the end.
```

### Verification prompt — NA-08

```text
Independent verifier for NA-08 (branch feat/NA-08-trained-dm). READ-ONLY; no Kaggle runs; no API calls; restore
mutations; no commits.

1. GATES: `make verify`, `make manifest`.
2. DATASET: open work/kaggle/dataset/*; confirm val-B and test files have no label column; confirm every state is
   masked and third_party_ok; confirm dataset-metadata.json isPrivate true; recompute the sha256 manifest.
3. LABELS: recompute 30 random training labels from panel_public by hand (bins of e5, |z_cc|, the cont rule).
4. DATES: max training session ≤ 2025-06-30 after purge; temperatures fit on val-A (run_record).
5. NOTEBOOK: read it; confirm INIT switch, heads, temperature fitting on val-A, no Hub push, no test labels read.
6. PREDICTIONS: recompute val-A IC for Laya-Fin and the anchor from imported probabilities and compare with the
   model cards; recompute val-A ECE for one model; confirm no val-B metric was computed (cards, REPORT, logs).
7. CONTROLS: check controls.json against the predictions of the shuffled-label run.
8. MUTATION: add a `label_index` column to the test (and separately the val-B) export in code → the schema test
   must RED each time.
9. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC6 and GAC; report Laya-Fin vs anchor val-A IC and ECE.
```

**New tests to add:** `test_train_labels.py`, `test_train_export_schema.py` (no test labels; private; masked), `test_train_import.py`.

**Risks / notes:**
- **Noisy return labels** (~70–90K examples) may leave the trained models weak. The reaction head gets help from the gap-dominated e5, and the result is reported honestly either way. The anchor is the clean reference even if weak.
- **Kaggle quota constrains the number of seeds.** The plan degrades gracefully: fewer seeds, then a shorter max length.
- **Laya's own training data is undisclosed.** That is why the anchor exists and why the headline-claim rule requires the anchor.

---

## NA-09 — [Build] Baselines (incl. a generative LLM at matched cost)

**Category:** Phase 3 — comparisons. Seven pre-registered baselines (PREREG §10) all write the **common prediction schema**, so NA-11/NA-12 can compare everything on the same events. A top-venue reviewer will expect a generative-LLM baseline at matched cost and a strong embedding baseline (Chen–Kelly–Xiu style).

**Goal:**
- Predictions for val-A, val-B and (inputs-only baselines) test, from: vendor sentiment, bge + ridge, tags-LightGBM, price-only, Laya zero-shot, and the generative LLM on a 2,000-event val-B subsample.
- Every baseline is fit on train only.

**Dependencies:** NA-04 (states), NA-03 (events), NA-02 (embeddings), NA-01 (panel), NA-05 (client, for the LLM and local Laya). **S7 (the LLM run on val-B) needs NA-06 done** (`allow_val_b`); everything else can run earlier. Consumed by NA-11, NA-12. · **Estimated time:** 1–1.5 days · **Branch:** `feat/NA-09-baselines`

**Expected outputs:**
- **New code:** `src/newsaction/baselines/{__init__,schema,sentiment,embed_ridge,tags_gbm,price_only,laya_zeroshot,llm_baseline}.py`.
- **Work files:** `work/baselines/*.parquet`.
- **Artifacts:** `artifacts/NA-09/{REPORT.md,baseline_val_metrics.csv}`.
- **Modified:** `src/newsaction/dm/client.py` (adds `chat_json()` with the same guards); ledgers.

**Current state (verified 2026-10-24):**
- NA-02 provides bge-small (title + snippet) embeddings.
- Vendor sentiment is 5-level, and it is "selection only" for model text. As a baseline *signal* it is allowed (it was produced live, day by day).
- Exploratory (2024-01..2026-07, disclosed): pre-open sentiment IC with the gap is large and with open→close small. NA-02 re-derives this on ≤ 2025 data.
- The generative LLM goes through OpenRouter chat completions with JSON output. Choose a catalog model priced ≤ $0.30/M input; record its id and price.

### Power prompt — NA-09

```text
You are implementing NA-09 for /Users/amir/Research/NewsAction: the pre-registered baselines (PREREG §10) in a common
prediction schema. Spend cap $2.00 (generative LLM only). Fit everything on train; tune on val-A; predict val-A,
val-B and — only for baselines that use no post-decision 2026 input — test.

Read first:
  - CLAUDE.md; docs/PREREG.md §4, §6.10, §7 (derived quantities), §10, §11.1–11.2
  - artifacts/NA-04/REPORT.md, artifacts/NA-05/REPORT.md; work/states/*, work/events/*, work/news/embeddings_ts.parquet,
    work/panel/panel_public.parquet, work/panel/panel_test_inputs.parquet
  - src/newsaction/dm/{client,parse}.py
Branch: feat/NA-09-baselines.

## Scope

S1. SCHEMA — baselines/schema.py: common prediction columns {event_id, model, call, split, N_hat (σ units, the
    news-implied eventual move), P_up, P_down, mag_hat (expected |move|), extra (json)}; validators.

S2. SENTIMENT — mean of vendor sentiment (−2..+2) over the event's articles → N_hat via a monotone map fit on train
    (isotonic of e5 on sentiment), mag_hat from the share of non-neutral and intensity Immediate/Short-Term.

S3. EMBED + RIDGE — mean-pooled bge embeddings per event (+ attention features) → ridge for e5 (N_hat) and for
    |z_cc| (mag_hat); λ chosen on val-A from a log grid (each λ logged as a trial).

S4. TAGS-GBM — LightGBM on vendor tag counts, flags, sentiment, intensity, source classes, novelty, attention, tier,
    sector → e5 and |z_cc|; hyper-parameters on val-A (small grid, logged).

S5. PRICE-ONLY — for D0: momentum (5/20/60), z_vol(t−1), σ regime, tier, sector → e5 and |z_cc| (LightGBM); for D2:
    the same + G (z_cc,t) and z_on,t → y2 (subsequent drift) — D2 test predictions are NOT produced here (they need
    2026 reactions; NA-11 produces them after the freeze using this frozen model).

S6. LAYA ZERO-SHOT — dm/laya_local.py on Call A (all splits incl. test Call A) and Call B D2 (train/val) states; parse
    with dm/parse.py.

S7. GENERATIVE LLM — extend dm/client.py with chat_json(model, messages, json_schema) sharing ALL guards (cache,
    ledger, caps, refusals, data_collection deny, offline). Prompt = the same masked Call A state + Q1 wording;
    output JSON {probabilities over the 9 Q1 levels}; temperature 0; seed if supported. Run on a 2,000-event val-B
    D0 subsample (stratified, seed 2026). The test subsample runs in NA-11 after the freeze (≤ $1 there).
    Report cost per 1,000 decisions next to the decision models'.

S8. VAL METRICS — artifacts/NA-09/baseline_val_metrics.csv: val-A daily IC (N_hat vs z_cc and vs e5), |z_cc| R²,
    by tier; every configuration logged in trials.jsonl. Store val-B predictions but compute NO val-B metric (NA-11
    evaluates val-B). S7 must run after NA-06 has set allow_val_b (the client refuses otherwise).

## Acceptance criteria

- AC1 — FIT RANGES: every fitted baseline stores its fit range (train only) and tuning range (val-A); tests assert.
- AC2 — SCHEMA: all outputs validate; event_ids match the states; no duplicate (event_id, model, call).
- AC3 — NO 2026 REACTIONS: no D2/D1 test prediction exists; ledgers/test_access.jsonl has no NA-09 entries.
- AC4 — BUDGET: LLM spend ≤ $2.00 (actual ≤ $1 expected); ledger reconciles; chat_json obeys every refusal (tests).
- AC5 — LAYA ZERO-SHOT predictions present for all Call A splits and Call B train/val.

## Constraints

- No tuning on val-B or test. Third-party rule applies to the LLM baseline. Register artifacts; Conventional Commits;
  do not merge. Self-audit.
```

### Verification prompt — NA-09

```text
Independent verifier for NA-09 (branch feat/NA-09-baselines). READ-ONLY; offline client; restore mutations; no commits.

1. GATES: `make verify`, `make manifest`.
2. FIT RANGES: open each stored model's metadata; confirm train-only fit and val-A tuning.
3. RECOMPUTE val-A IC for the embedding-ridge and sentiment baselines from their prediction files + panel_public.
4. REFUSALS: call chat_json (offline, mock transport) with a test-period state → must raise before transport.
5. MUTATION: let embed_ridge fit on train+val-A → the fit-range test must RED.
6. Confirm no D2/D1 test predictions; no NA-09 test_access entries; LLM spend ≤ $2.
7. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC5 and GAC with the val-A IC table (and confirm no val-B metric was computed).
```

**New tests to add:** `test_baselines_schema.py`, `test_baselines_fit_ranges.py`, `test_chat_json_refusals.py`.

**Risks / notes:** the generative baseline's JSON probabilities are *verbalised*, not model log-probabilities. Report this as a limitation; its role is a cost-matched comparator.

---

## NA-10 — [Build] 30-min bars from FMP (≤ 3,000 requests): D1 (10:00) inputs, sealed 2026

> **Operator decision (2026-10-27):** the probe showed that FMP serves only 30 calendar days per 30-minute request,
> so the cap was raised to 17,000 (PREREG §15, NA-10 rows; 15,858 used). The 3,000 figures below are the original
> specification.

**Category:** Phase 1b — optional but **recommended** data. 30-min bars make the post-open decision **tradeable**: decide at 10:00 with the gap plus the first half hour, enter at the 10:00 bar close. They also give exact 10:00/15:30 prices and (if served) a pre-market price. Hard cap: 3,000 FMP requests; never 1-minute.

**Goal:**
- A ≤ 5-request capability probe.
- A capped fetch for company representatives plus SPY, 2024-06 → 2026-07, with public bars ≤ 2025-12-31 and **2026 bars sealed**.
- Split-basis fix and reconciliation tests.
- σ_30/σ_rest estimates; D1 reaction inputs and D1 Call B states for train/val.

**Dependencies:** NA-01 (companies, calendar, raw EOD for reconciliation); NA-04 (state builder, extended here for D1). Consumed by NA-11 (2026 D1 reactions after the freeze), NA-12, NA-13. · **Estimated time:** 1 day · **Branch:** `feat/NA-10-bars30`

**Expected outputs:**
- **New code:** `src/newsaction/bars/{__init__,fmp30,probe,fetch,basis,derive}.py`.
- **Work files:**
  - `work/bars30/bars_public.parquet` (≤ 2025-12-31);
  - `work/snapshot/sealed/bars30_2026.parquet`;
  - `work/panel/intraday_public.parquet`;
  - `work/states/callB_d1_E3.parquet` (train/val).
- **Artifacts:** `artifacts/NA-10/{REPORT.md,capability.json}`.
- **Modified:** `src/newsaction/panel/reactions.py` (D1 path, sealed for 2026); `configs/availability.yaml`; `ledgers/fmp_requests.jsonl`.

**Current state (verified 2026-10-24; ATOM `docs/runbooks/fmp_intraday_capability.json`, measured 2026-10-21):**
- **Endpoint** `/stable/historical-chart/{interval}?symbol=&from=&to=`: 30-min is supported back to 2010, and from/to is honoured (a 30-day request returned 247 rows = 19 sessions × 13 bars).
- **Bars:** start-labelled 09:30 … 15:30 in America/New_York; 13 bars on full days.
- **Price levels:** default levels are split-adjusted to today's basis; `nonadjusted=true` returned as-traded levels at 1-min (untested at 30-min). Not dividend-adjusted.
- **Extended hours:** `extended=true` adds 04:00–20:00 at 1-min (untested at 30-min).
- **Auction and volume:** the closing auction is NOT in the last bar (EOD close differs slightly). Regular-hours volume is 80–84% of consolidated.
- **Rate:** about 8–9 requests/second.
- **Limits:** the 1-year 30-min window cap is unknown (to probe). The design review estimated ~21K requests with monthly windows, which is **over the cap**. Larger windows are required, otherwise STOP.

### Power prompt — NA-10

```text
You are implementing NA-10 for /Users/amir/Research/NewsAction: 30-min bars with a HARD cap of 3,000 FMP requests
(ledger-enforced), split-basis handling, and D1 (10:00) inputs. 2026 bars go straight to work/snapshot/sealed/ and
are never read in this chunk.

Read first:
  - CLAUDE.md (E18, B8); docs/PREREG.md §2.5 (D1), §5.4–5.6 (σ, G, targets), §15 Amendment A1.2 (the 10:00 rung
    of the convergence ladder and G^lvl)
  - /Users/amir/GitHub/Atom/docs/runbooks/fmp_intraday_capability.md and .json (measured vendor facts — read-only)
  - artifacts/NA-01/REPORT.md; work/panel/companies.parquet; work/snapshot/prices_raw.parquet; src/newsaction/
    {calendar,lock,ledger,io}.py; src/newsaction/states/build.py
Operator prerequisite: FMP_API_KEY in .env (never print it).
Branch: feat/NA-10-bars30.

## Scope

S1. CLIENT — bars/fmp30.py: httpx with retries; FmpLedger.reserve(1) before EVERY request (refuse at 3,000
    cumulative); log {ts, symbol, from, to, params, status, rows} to ledgers/fmp_requests.jsonl; offline cache of raw
    responses under work/bars30/raw/ (gitignored); key from env only.

S2. PROBE (≤ 5 requests) — bars/probe.py on AAPL: (1) 30min 2025-01-02..2025-12-31 default (rows? = 252×13 → no
    cap); (2) same with extended=true (pre-market bars present?); (3) same with nonadjusted=true around NVDA's split
    window 2024-06-03..2024-06-14 (levels as-traded?); (4) a 2-year window to find any cap. Write
    artifacts/NA-10/capability.json. Compute requests needed = Σ over symbols of ceil(span/window). If > 3,000 →
    STOP and report (do not fetch).

S3. FETCH — bars/fetch.py for company representatives that are members at any session 2024-06-03..2026-07-31 plus
    SPY; window per probe; rows dated ≤ 2025-12-31 → work/bars30/bars_public.parquet; rows ≥ 2026-01-02 →
    work/snapshot/sealed/bars30_2026.parquet (write-only here; register hash).

S4. BASIS — bars/basis.py: if nonadjusted is honoured use as-traded levels; else rescale each session's bars so the
    first bar's open equals ATOM's raw EOD open for that session (factor per session). Never mix bases. Tests on
    NVDA 2024-06-10, AVGO 2024-07-15, WMT 2024-02-26, CMG 2024-06-26.

S5. DERIVE (public) — bars/derive.py → work/panel/intraday_public.parquet: P_10:00 (close of the 09:30 bar), P_15:30
    (close of the 15:00 bar), P_pre (close of the 09:00 bar, only if extended bars exist), with the official open/close
    from EOD; AR(close_prev → 10:00) with the same β (t−1) and leave-one-out sector built from the same bars;
    σ_30 (MAD of first-30-min ARs over 126 sessions ending t−1) and σ_rest (10:00→close); G_D1 per PREREG §5.5 and
    its level version G^lvl (÷ σ_cc); the 10:00 rung of the convergence ladder (CAR^lvl at 10:00); y1 targets for
    public sessions. Half days: 7 bars (09:30..12:30); handle.

S6. REACTIONS + STATES — extend panel/reactions.py with the D1 path (public: from intraday_public; 2026: via
    lock.sealed_path("bars30_2026","reactions") → raises before the freeze); extend states/build.py to produce
    callB_d1_E3 for train/val-A/val-B; register new columns in configs/availability.yaml (kind "d1").

## Acceptance criteria

- AC1 — REQUEST CAP: ledgers/fmp_requests.jsonl count ≤ 3,000; FmpLedger refuses the 3,001st (test).
  MUTATION: remove the cap check → RED.
- AC2 — BARS: 13 bars per full session and 7 per half day for ≥ 99% of member-sessions (exceptions listed);
  first-bar open within 5 bp of the EOD raw open on ≥ 99% of member-sessions; the four split windows pass.
- AC3 — SEALED: no public file contains a session ≥ 2026-01-02; build_reactions(…, "test", "D1") raises before the
  freeze and is logged.
- AC4 — D1 STATES: callB_d1_E3 exists for train/val with p95 tokens ≤ 900; check_inputs passes for D1 and fails if a
  post-10:00 field is injected.
- AC5 — ATOM UNTOUCHED: no ATOM access in this chunk (grep) — reconciliation uses the NA-01 snapshot.
- AC6 — 10:00 RUNG (A1.2): intraday_public carries CAR^lvl at 10:00 and G^lvl for public D1 events; a test
  recomputes both for 10 events from bars, β (t−1) and σ_cc,t (tolerance 1e-9); 2026 values do not exist yet.

## Constraints

- Never 1-minute bars. ≤ 3,000 requests; STOP and ask if the probe shows more are needed.
- No OpenRouter calls. Register artifacts; Conventional Commits; do not merge. Self-audit.
```

### Verification prompt — NA-10

```text
Independent verifier for NA-10 (branch feat/NA-10-bars30). READ-ONLY; no FMP calls; restore mutations; no commits.

1. GATES: `make verify`, `make manifest`.
2. LEDGER: count ledgers/fmp_requests.jsonl rows (≤ 3,000); sum of rows returned vs parquet row counts.
3. RECONCILE: for 20 random member-sessions recompute first-bar open vs EOD raw open (bp) and the bar count.
4. SPLITS: inspect NVDA 2024-06-07/2024-06-10 bars: levels on one basis consistent with EOD.
4b. 10:00 RUNG (A1.2, AC6): recompute CAR^lvl at 10:00 and G^lvl for 5 public events by hand.
5. SEALING: max session in bars_public.parquet and intraday_public.parquet ≤ 2025-12-31; sealed file not opened
   by any src/ module except lock.py (grep).
6. MUTATION: remove the FmpLedger cap check → test RED.
7. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC6 and GAC with request count and reconciliation rates.
```

**New tests to add:** `test_bars_cap.py`, `test_bars_basis.py`, `test_bars_counts.py`, `test_reactions_d1_sealed.py`, `test_states_d1_pit.py`.

**Risks / notes:**
- **Window cap:** if a 1-year 30-min window is capped, the request count may exceed 3,000. That is a STOP, and the operator decides.
- **Pre-market bars at 30-min may be unavailable.** D0+ (a pre-market price variant) is then dropped (already optional).

---

## NA-11 — [Run] Final selection on val-B, analysis spec, **FREEZE**, production, ablations

**Category:** Phase 4 — the one-way door. In order:
1. Write and test the analysis specification on validation data.
2. Make the final pre-registered model selection on val-B.
3. Freeze everything (hash-locked).
4. Only then build 2026 reaction states and spend the production budget on val + test, with canary checks and the pre-registered ablations.

**Goal:**
- `src/newsaction/analysis/spec.py` (tested on val).
- `configs/frozen.yaml` complete.
- `artifacts/NA-11/freeze.json` plus tag `prereg-freeze`.
- Production outputs for the primary instrument and comparators on val-A, val-B and test.
- Laya-Fin/anchor test Call B inference on Kaggle.

**Dependencies:** NA-06, NA-07, NA-08, NA-09, NA-10 (if done). Consumed by NA-12, NA-13. · **Estimated time:** 1.5 days · **Branch:** `feat/NA-11-freeze-production`

**Expected outputs:**
- **New code:**
  - `src/newsaction/analysis/{__init__,spec,inference,shapley,metrics}.py` (spec frozen);
  - `src/newsaction/production/{__init__,select_final,freeze,run,ablations}.py`.
- **Work files:** `work/dm/production/*.parquet`, `work/states/{callB_d2_E*,callB_d1_E*}_test.parquet` (post-freeze).
- **Artifacts:** `artifacts/NA-11/{REPORT.md,final_selection.csv,freeze.json,canary_check.csv,production_summary.csv}`.
- **Tag:** `prereg-freeze`.
- **Modified:** `configs/frozen.yaml`, `docs/PREREG.md` (deviations log only), ledgers.

**Current state (planned):**
- OpenRouter cap for this chunk: $18 (cumulative total ≤ $30).
- Production plan (PREREG §13), using NA-03's projection: Call A on D0 (~27K val + ~27K test), Call B on D2 (~34K + ~35K), Call B on D1 (if NA-10). Plus final-selection runs on val-B for the top-2 API survivors (~13K each), ablations on 12K events, the LLM-baseline test subsample (≤ $1), and canary checks.
- If the projection exceeds the remaining budget, the PREREG §13 STOP rules apply.

### Power prompt — NA-11

```text
You are implementing NA-11 for /Users/amir/Research/NewsAction: analysis spec → final selection → FREEZE → 2026 states
→ production → ablations. The ORDER is mandatory and audited. Spend cap $18 for this chunk; $30 total.

Read first:
  - CLAUDE.md (all of B and C); docs/PREREG.md entirely, INCLUDING §15 Amendments A1–A3 (you implement §1, §8.5,
    §11, A1.3–A1.6, A2.4–A2.6 and A3.2–A3.5 in code and freeze the rest)
  - artifacts/NA-03..NA-10 REPORTs; configs/frozen.yaml; artifacts/NA-06/leaderboard.csv; NA-07 decisions;
    artifacts/NA-08/model_card_*.md; artifacts/NA-09/baseline_val_metrics.csv
  - src/newsaction/{lock,dm/*,states/*,panel/{targets,reactions}.py}
Branch: feat/NA-11-freeze-production.

## Scope

S1. ANALYSIS SPEC (before anything else) — analysis/spec.py implements, as pure functions parameterised by split:
    H1–H4 tests (PREREG §1.1), secondary H2-C convergence ladder (PREREG A1.4–A1.5), the A2.5 analyses (mechanism
    cuts with the model's own labels, horizon validity, width additions), the A3 explanation analyses (ladder,
    explained share, explanation → persistence, reasons, optional market replication), H5–H7 and the ≤ 6 heterogeneity cuts
    (§1.2), metrics (§11.1–11.2),
    regressions with two-way clustering + Driscoll–Kraay (§11.3, analysis/inference.py), stationary block
    bootstrap (§11.4), exact Shapley over {R, N, J} (§11.5, analysis/shapley.py), the robustness list (§11.6), the
    headline-claim rule (§1.3), Holm/BH. TEST IT END-TO-END ON VAL-B DATA (and on synthetic data with known effects)
    — tests must show it recovers planted b > 0, c < 0, a planted Shapley interaction, and a planted convergence
    path (κ_h rising to 1 with a known half-life).

S2. FINAL SELECTION (val-B) — production/select_final.py per PREREG §8.5: ensure val-B Call A outputs exist for the
    top-2 API survivors that passed the screens (run them on ALL val-B D0 events; dry-run first), Laya zero-shot,
    Laya-Fin and the anchor; compute daily IC(N̂, z_cc) on val-B; tie-break rules; write final_selection.csv and
    frozen.yaml selection: {primary_instrument, comparators, ic_table_sha}. Also freeze into frozen.yaml: filter (from
    NA-03), encoding & calls_per_event (NA-07), δ/RG thresholds, confidence gates = val-A 70th percentile per model,
    calibration maps Ñ (isotonic N̂ → e5) and the news-implied value map V (PREREG A1.3: isotonic N̂ → E5^lvl),
    both fit on val-A per model with fit ranges stored, strategy parameters (PREREG §12 and A1.6 S-CONV).

S3. FREEZE — set frozen.yaml frozen_requested: true; run production/freeze.py → lock.freeze() writes
    artifacts/NA-11/freeze.json {hash, files, git_sha, ts}; commit; create annotated tag prereg-freeze. Append to the
    PREREG Deviations log any change made since v0 (each with reason) BEFORE freezing.

S4. 2026 REACTION STATES (after the freeze only) — build callB_d2 (and callB_d1 if NA-10) states for the test split
    via panel/reactions.py through lock.sealed_path(..., "reactions") (logged), in the frozen encoding.

S5. CANARY — run canary_v1 for every production API model; if any probability moved ≥ 0.02 vs the NA-05 baseline,
    STOP (silent model update) and report.

S6. PRODUCTION — production/run.py with the frozen plan: the primary instrument (and the best API comparator if the
    primary is a trained model) on val-A, val-B and test: Call A on D0 events (W0 news) AND on D2 events (W2 news,
    PREREG A3.1; identical states hit the cache), and Call B (D2, and D1 if bars) per calls_per_event. Question
    groups (PREREG A2.1): the PRIMARY API instrument gets core + extended on Call A and core + explain on Call B;
    every other model gets the core battery only; apply the A2.6 cutting order if the projection exceeds the
    remaining cap. Optional A3.5: one market state per session for the primary API instrument (≈ 400 calls). Dry-run first; abort if projection > remaining cap; apply PREREG §13 STOP rules. Re-run the
    canary at the end (report drift).

S7. TRAINED-MODEL TEST CALL B — export the 2026 Call B states (masked, third_party_ok, NO labels) as a new private
    Kaggle dataset version; operator runs inference-only with the frozen Laya-Fin and anchor checkpoints; import
    predictions (train/import_preds.py).

S8. ABLATIONS — on 12,000 stratified val+test events for the primary API instrument: Call B with `news` removed;
    Call B with shuffled news; unmasked Call A (probe-tagged). LLM baseline test subsample (2,000 events, ≤ $1).

S9. SUMMARY — production_summary.csv: coverage (share of eligible events with valid outputs per model/call/split),
    spend per model, latency, invalid-response rate.

## Acceptance criteria

- AC1 — ORDER: freeze.json ts precedes (a) the first cache row with a 2026 state and (b) the first "reactions"
  entry in ledgers/test_access.jsonl; spec.py and targets.py hashes are inside freeze.json; tag prereg-freeze points
  at the freeze commit.
- AC2 — SPEC TESTED: synthetic tests recover planted effects (b > 0, c < 0; a Shapley interaction; a convergence path
  with κ_h rising to 1 and a known half-life); the val-B smoke run passes and includes the A1 convergence ladder;
  frozen.yaml holds the A1.3 V maps (val-A fit ranges) and the A1.6 S-CONV parameters before the freeze.
- AC3 — COVERAGE: ≥ 99% of eligible events have valid outputs for the primary instrument per call/split.
- AC4 — CANARY: pre-production drift < 0.02 for all production models (else STOP recorded).
- AC5 — BUDGET: NA-11 spend ≤ $18 and total ≤ $30; ledger reconciles; dry-run within ±20%.
- AC6 — NO TARGETS: no "targets" entry in ledgers/test_access.jsonl (unblinding is NA-12's).

## Constraints

- Absolutely no 2026 outcome statistics. Reactions only via the lock after the freeze.
- After the freeze, PREREG/configs/spec/targets code may not change (the hash would break unblinding); any needed
  change is a reported deviation decided by the operator.
- Register artifacts; Conventional Commits; do not merge. Self-audit with the order evidence (timestamps).
```

### Verification prompt — NA-11

```text
Independent verifier for NA-11 (branch feat/NA-11-freeze-production). READ-ONLY; offline client; no Kaggle; restore
mutations; no commits. Never call load_targets.

1. GATES: `make verify`, `make manifest`.
2. ORDER EVIDENCE: compare freeze.json ts with the earliest 2026-state cache row and the earliest "reactions" access
   entry; confirm tag prereg-freeze; recompute lock.compute_freeze_hash() == freeze.json hash on the tagged commit.
3. SPEC: run the synthetic-effect tests; read spec.py against PREREG §1, §11 and Amendment A1.3–A1.6 (list any
   mismatch); confirm frozen.yaml has the V maps with val-A fit ranges and the S-CONV parameters.
4. SELECTION: recompute val-B IC for the top candidates from cached/imported predictions; re-apply §8.5 rules.
5. CANARY: recompute drift from canary_check.csv and cached answers.
6. COVERAGE + BUDGET: recompute coverage per model/call/split; reconcile spend; total ≤ $30.
7. MUTATION: edit one character in configs/frozen.yaml → lock.require_unblind() must fail the hash check
   (with NA_UNBLIND=1 set). Restore.
8. GAC1–GAC5 (GAC3 here: only "reactions" accesses, all after the freeze).

Verdict: PASS / FAIL per AC1–AC6 and GAC, with the primary instrument named and the spend total.
```

**New tests to add:** `test_spec_synthetic.py`, `test_shapley.py` (identity and planted interaction), `test_inference.py` (clustered SE on known designs), `test_freeze_order.py`, `test_select_final_rule.py`.

**Risks / notes:**
- **This is the irreversible step.** Run it only when NA-03 to NA-10 have passed verification.
- **If the canary drifts,** the vendor silently updated the model. STOP; the operator decides whether to proceed with the new build (a reported deviation).

---

## NA-12 — [Research] Unblinding and the pre-registered analyses

**Category:** Phase 4 — confirmatory analysis. It unblinds 2026 targets with the frozen code and runs the frozen `analysis/spec.py` **verbatim**: H1–H4 (Holm), H5–H7 and ≤ 6 heterogeneity cuts (BH), robustness, model comparison and calibration, and the clean-anchor confirmation. Every pre-registered test is reported, including nulls.

**Goal:** `artifacts/NA-12/tables/*` and `figure_data/*`, plus a REPORT that states each hypothesis's verdict under the headline-claim rule.

**Dependencies:** NA-11 (freeze, production outputs). Consumed by NA-13, NA-14. · **Estimated time:** 1.5–2 days · **Branch:** `feat/NA-12-analysis`

**Expected outputs:**
- **New code:** `src/newsaction/analysis/{unblind,run_all,tables}.py` (they **call** the frozen `spec.py`; they do not change it).
- **Work files:** `work/analysis/targets_test.parquet` (written only after unblinding).
- **Artifacts:** `artifacts/NA-12/{REPORT.md,tables/*.csv,tables/*.tex,figure_data/*.csv}`.

**Current state (planned):** `artifacts/NA-11/freeze.json` holds the hash of PREREG, configs, `targets.py`, `reactions.py` and `spec.py`. 2026 targets have never been computed (`ledgers/test_access.jsonl` has no `targets` entries).

### Power prompt — NA-12

```text
You are implementing NA-12 for /Users/amir/Research/NewsAction: unblinding and the confirmatory analyses, exactly as
frozen in NA-11. You must not modify docs/PREREG.md (except appending to the Deviations log), configs/*.yaml,
src/newsaction/panel/{targets,reactions}.py or src/newsaction/analysis/spec.py — the unblinding lock checks their hash.

Read first:
  - CLAUDE.md; docs/PREREG.md (all, including §15 Amendments A1–A3; you execute §1, §11, A1.4–A1.5, A2.5,
    A3.2–A3.5 and §12-prep exactly); artifacts/NA-11/{REPORT.md,freeze.json};
    configs/frozen.yaml; src/newsaction/analysis/spec.py
  - work/dm/production/*, work/kaggle/predictions/*, work/baselines/*, work/panel/*
Branch: feat/NA-12-analysis.

## Scope

S1. UNBLIND — analysis/unblind.py: with NA_UNBLIND=1, lock.require_unblind() (hash match) → build_targets(panel,
    "test") via the frozen targets.py → work/analysis/targets_test.parquet. Log the access. If the hash check fails,
    STOP (do not "fix" the hash).

S2. RUN ALL — analysis/run_all.py executes spec.py on the test split for: the primary instrument; the clean anchor;
    Laya-Fin; the best API comparator; every baseline. Produce:
    - H1–H4 results (estimates, CIs, p-values, Holm-adjusted), the headline-claim rule outcome (primary AND anchor);
    - secondary H5–H7 and the ≤ 6 heterogeneity cuts with BH q-values;
    - the over/under regression y = a + b·N̂ + c·G + day×tier FE by decision point (D2 primary; D1 if bars; D0
      tradeable y0), and re-estimated within |G| < 1, 1–2, > 2;
    - CONVERGENCE (PREREG A1.4–A1.5, H2-C) — "does the price converge to the model's value, how fast, how completely?":
      the ladder κ_h over open, 10:00 (if bars), close, t+1, t+2, t+5, t+10, t+20; gap closure λ_h with half-life;
      ψ_{h*}; tracking-error ratios vs naive and price-only; by tier / quantified vs story / |G| bins / model
      (primary + anchor); clean-window and plateau robustness;
    - V-decile and RG-class (Under/Fair/Over) CAR^lvl paths from t−5 to t+20, each with its mean V, plus the day-t
      30-min path (if bars) — figure data for Figure 1 (convergence) and Figure 2 (drift vs |G| by news-strength
      terciles);
    - EXPLANATION (PREREG A3, Kelly–Su–Zhang style) — "how much of the move can the news explain?": the explanation
      ladder (market + sector → + ex-ante news → + ex-post news → + explanation features) as out-of-sample shares of
      stock-specific variance by tier / model event type / event vs non-event days; the explained share; θ
      (explanation → persistence) at D2 and D1; persistence by move_reason; the optional market-level replication
      (A3.5) — Figure 8 data;
    - QUESTION BATTERY v2 (PREREG A2.5): mechanism cuts with the model's own event type and quantified flag next to
      the vendor-tag cuts; horizon validity (H vs realized convergence speed); U_unc and P(no_material_effect) in the
      H4 width test; the reading-validity table from NA-06;
    - Shapley shares {R, N, J} of test R² and IC by tier (Figure 5 data);
    - monthly IC of the best API model vs the anchor across val+test with model release dates (Figure 4 data);
    - calibration (ECE, reliability bins) for all decision models (appendix);
    - the robustness list (§11.6), each reported raw and placebo-adjusted;
    - model comparison table (val-B and test IC, cost per 1,000 decisions, latency).

S3. TABLES — analysis/tables.py writes CSV + LaTeX (booktabs) for every table, with a machine-readable key so
    NA-14 captions can be tested against them.

S4. REPORT — artifacts/NA-12/REPORT.md: one section per hypothesis: pre-registered statement → result → verdict
    (supported / not supported / model-specific); every robustness outcome; deviations (if any) clearly flagged.

## Acceptance criteria

- AC1 — LOCK: the hash in freeze.json equals the current hash at unblinding; exactly one "targets" access sequence
  in ledgers/test_access.jsonl, after the freeze.
- AC2 — VERBATIM: git diff between prereg-freeze and HEAD shows no change to the frozen files except the Deviations
  log append; spec.py functions are called, not re-implemented.
- AC3 — INFERENCE: clustering, Driscoll–Kraay, bootstrap parameters and Holm/BH exactly as PREREG (tests assert
  the parameters passed).
- AC4 — COMPLETENESS: every pre-registered test has a row in the tables (including nulls and failed robustness) —
  including every A1 item: κ_h for each rung, λ_h and the half-life, ψ_{h*}, tracking-error ratios, each by the A1.5
  cuts (tier, quantified vs story, |G| bins, model) and with the clean-window and plateau robustness. Likewise every
  A2.5 and A3.2–A3.4 item (and A3.5 if it was run).
- AC5 — HEADLINE RULE: each primary verdict states the anchor's result next to the primary instrument's.

## Constraints

- No new hypotheses presented as confirmatory; exploratory additions go to a separate "Exploratory" section with
  that label. No changes to frozen files. Register artifacts; Conventional Commits; do not merge. Self-audit.
```

### Verification prompt — NA-12

```text
Independent verifier for NA-12 (branch feat/NA-12-analysis). READ-ONLY (you may run the analysis code); restore
mutations; no commits; no API calls.

1. GATES: `make verify`, `make manifest`.
2. LOCK: `git diff prereg-freeze HEAD -- docs/PREREG.md configs src/newsaction/panel/targets.py
   src/newsaction/panel/reactions.py src/newsaction/analysis/spec.py` → only the Deviations-log append (if any).
   Recompute the freeze hash.
3. RECOMPUTE H2 for the primary instrument independently (statsmodels OLS with day×tier FE and two-way clustered
   SE written by you) and compare b, c, SEs with the table (tolerance 1e-6 on estimates, 1e-3 on SEs).
4. RECOMPUTE one Shapley table (exact 7-subset formula) from the stored fold predictions.
4b. CONVERGENCE (A1): independently recompute κ_h at C_t and C_{t+5} (OLS of CAR^lvl_h on V with day×tier FE,
   two-way clustered SE) and λ for D2 → C_{t+5} (with ψ) for the primary instrument; compare with the tables.
5. HOLM/BH: re-adjust the reported p-values.
6. HEADLINE RULE: confirm each verdict lists the anchor result and follows PREREG §1.3.
7. GAC1–GAC5 (GAC3: a single post-freeze targets access sequence).

Verdict: PASS / FAIL per AC1–AC5 and GAC with the H1–H4 verdicts restated and the convergence answer (κ_h ladder,
half-life, ψ) for the primary instrument and the anchor.
```

**New tests to add:** `test_unblind_lock.py`, `test_run_all_params.py`, `test_tables_keys.py`.

**Risks / notes:**
- **Null results are results.** The paper's value includes the contamination-robust protocol and calibrated decision models even if H2 is weak.
- **About 145 test sessions** limit power for the heterogeneity cuts, which is why there are at most 6 of them.

---

## NA-13 — [Research] Strategies and economic significance

**Category:** Phase 4 — economic evaluation of the frozen signals. It runs tradeable, look-ahead-free portfolios at D0, D1 and D2, with:
- costs, turnover and capacity;
- a deflated Sharpe over the full trial count;
- benchmarks (gap fade, sentiment, random-signal placebo).

**Goal:** `artifacts/NA-13/*`: strategy tables and the cumulative-return figure data (Figure 7), with a DSR cross-checked against ATOM's implementation.

**Dependencies:** NA-12. Consumed by NA-14. · **Estimated time:** 1–1.5 days · **Branch:** `feat/NA-13-strategies`

**Expected outputs:**
- **New code:** `src/newsaction/strategy/{__init__,portfolios,costs,dsr,capacity}.py`.
- **Tests:** `tests/golden/dsr_atom.json` (computed once with ATOM's venv), plus `tests/test_strategy_*.py`.
- **Artifacts:** `artifacts/NA-13/{REPORT.md,strategy_table.csv,strategy_table.tex,fig7_data.csv}`.

**Current state (verified 2026-10-24):**
- ATOM `atom_signals/stats.py:238` has `deflated_sharpe_ratio(returns, *, n_trials, trials_sr_var=None, benchmark_sr=0.0)` (Mertens skew/kurtosis correction).
- ATOM `atom_backtest/costs.py:99` has `LinearCostModel(commission_bps=1, slippage_bps=5)`.
- PREREG §12 fixes the rules.

### Power prompt — NA-13

```text
You are implementing NA-13 for /Users/amir/Research/NewsAction: the pre-registered strategies (PREREG §12) on the
frozen signals, with costs, capacity and a deflated Sharpe that counts every trial in ledgers/trials.jsonl.

Read first:
  - CLAUDE.md; docs/PREREG.md §2.5 (decision/entry times), §5.6 (targets), §12 (strategies), §15 Amendment A1.6
    (S-CONV — the primary strategy); artifacts/NA-12/REPORT.md
  - /Users/amir/GitHub/Atom/packages/atom_signals/src/atom_signals/stats.py:238 (deflated_sharpe_ratio — read-only
    reference) and /Users/amir/GitHub/Atom/packages/atom_backtest/src/atom_backtest/costs.py:99 (LinearCostModel)
  - work/analysis/targets_test.parquet, work/dm/production/*, work/kaggle/predictions/*, work/bars30 (if any)
Branch: feat/NA-13-strategies.

## Scope

S1. PORTFOLIOS — strategy/portfolios.py: S-CONV (PRIMARY, PREREG A1.6: at D1 10:00 and at D2 close → next open,
    rank by the remaining gap U_τ = V − G^lvl_τ; long price-below-value, short price-above-value within tier; exits
    C_t (D1 only), t+1, t+5, t+20); S-D0 (rank Ñ at 09:15; long top 20% / short bottom 20% within tier,
    pooled if < 10 per side; equal weight; β-hedged with SPY; enter official open, exit official close; secondary
    exit C_{t+1}); S-D1 (rank J and RG at 10:00; enter at the 10:00 bar close; exit official close, t+1, t+5);
    S-D2 (rank J and RG after the close; enter next open; exit t+1, t+5, t+20 as calendar-time portfolios);
    confidence-gated variants (val-A 70th percentile from frozen.yaml). Entry is ALWAYS strictly after the decision
    time (assert).
S2. COSTS + CAPACITY — strategy/costs.py: 5/10/20 bp per side on both legs and the hedge; turnover; capacity at
    1% of 20-session ADV (dollar) → max deployable capital per strategy.
S3. DSR — strategy/dsr.py re-implements Bailey–López de Prado DSR with the Mertens correction; golden test against
    numbers produced ONCE by ATOM's function (run `/Users/amir/GitHub/Atom/.venv/bin/python` on fixed synthetic
    returns, save tests/golden/dsr_atom.json). n_trials = count of trials.jsonl rows of kind "strategy" plus the
    model/encoding/filter selection trials (document the count).
S4. BENCHMARKS — gap fade (price-only), vendor-sentiment rank, random-signal placebo (100 seeds → distribution).
S5. OUTPUTS — strategy_table (gross/net Sharpe, ann. return, vol, max DD, turnover, hit rate, DSR, capacity) for val
    (reference) and test; fig7_data.csv (cumulative net returns by tier + benchmarks).

## Acceptance criteria

- AC1 — TIMING: tests assert every entry timestamp > decision timestamp and every input's availability ≤ decision.
  MUTATION: enter S-D2 at the day-t close → RED.
- AC2 — COSTS both legs + hedge; a test on a toy book reproduces the expected net return.
- AC3 — DSR golden matches ATOM within 1e-6; n_trials documented and equal to the ledger count.
- AC4 — PLACEBO: the random-signal distribution is reported; strategy Sharpe percentiles vs placebo given.
- AC5 — No modification of frozen files; register artifacts.
- AC6 — S-CONV (A1.6): reported first, at D2 (and D1 if bars) for every exit horizon, ranked by U_τ = V − G^lvl_τ with
  V from the frozen maps; a test rebuilds one day's D2 ranks from the stored inputs.

## Constraints

- Test-period signals are frozen; no re-tuning. Validation shown as reference only. Conventional Commits; do not merge.
```

### Verification prompt — NA-13

```text
Independent verifier for NA-13 (branch feat/NA-13-strategies). READ-ONLY; restore mutations; no commits.

1. GATES: `make verify`, `make manifest`.
2. RECOMPUTE S-CONV (D2 entry, t+5 exit) and S-D2 (t+5) net Sharpe at 10 bp from the stored daily returns; compare.
3. TIMING: inspect 10 random trades: decision ts, entry ts, inputs' availability.
4. DSR: run strategy/dsr.py on the golden inputs; compare with tests/golden/dsr_atom.json.
5. MUTATION: shift S-D0 entry to the previous close → the timing test must RED.
6. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC6 and GAC with the main net Sharpe numbers (S-CONV first).
```

**New tests to add:** `test_strategy_timing.py`, `test_strategy_costs.py`, `test_strategy_dsr_golden.py`.

**Risks / notes:** short-sale borrow costs are not modelled (S&P 500 names are general collateral). This is stated as a limitation.

---

## NA-14 — [Paper] Charts, tables, replication package

**Category:** Phase 5 — publication outputs. Eight publication-quality figures plus an appendix, LaTeX tables, and a one-command rebuild from cached responses and frozen artifacts with digest checks.

**Goal:**
- `artifacts/NA-14/figures/*.pdf|png` and the data CSV for each.
- `make paper` reproduces every table and figure.
- `docs/REPLICATION.md`.
- An outline mapping figures to paper sections.

**Dependencies:** NA-12, NA-13 (NA-06/NA-03 figure data). · **Estimated time:** 1–1.5 days · **Branch:** `feat/NA-14-paper-figures`

**Expected outputs:**
- **New code:** `src/newsaction/figures/{__init__,style,fig1_hero_car,fig2_drift_vs_move,fig3_tournament,fig4_monthly_ic,fig5_shapley,fig6_filters,fig7_strategies,appendix}.py`.
- **Artifacts:** `artifacts/NA-14/{figures/*,captions.yaml,REPORT.md}`.
- **Docs:** `docs/REPLICATION.md`, `docs/paper_outline.md`.
- **Makefile:** a `paper` target.

### Power prompt — NA-14

```text
You are implementing NA-14 for /Users/amir/Research/NewsAction: the paper's charts, tables and replication package.
BEFORE WRITING ANY CHART CODE, invoke the `dataviz` skill and follow it (palette, typography, accessibility, marks,
light/dark not needed for print — vector PDF + PNG at 300 dpi).

Read first:
  - CLAUDE.md (F22); docs/PREREG.md (§11, §12 and §15 Amendment A1 — Figure 1 is the convergence figure);
    artifacts/NA-12/{REPORT.md,figure_data/*},
    artifacts/NA-13/fig7_data.csv, artifacts/NA-06/fig3_data.csv, artifacts/NA-03/frontier.csv
Branch: feat/NA-14-paper-figures.

## Scope

S1. STYLE — figures/style.py: one style (from the dataviz skill), colour-blind-safe categorical palette, consistent
    fonts/sizes for a two-column paper (single-column width 3.3 in, double 6.9 in), shared helpers for CIs.
S2. FIGURES (each reads ONLY its CSV; writes PDF + PNG; caption text with numbers pulled from the tables):
    1 HERO — CONVERGENCE: (a) realized CAR^lvl paths from the previous close through open, 10:00 (if bars), close,
      t+1, t+2, t+5, t+10, t+20 for deciles of the model's value V, each with its mean V as a dashed target line —
      do prices converge to what the decision model says the news is worth?; (b) κ_h with CIs vs horizon, the
      full-convergence line at 1 and the half-life marked; (c) Under / Fair / Over paths by tier; bootstrap bands;
      decision-point markers (D0 open, D1 10:00, D2 close).
    2 Drift vs |initial move| (bins of |G|) split by news strength (terciles of |N̂|) — shows small-move
      underreaction.
    3 Tournament: IC (± CI) vs cost per 1,000 decisions (log x), MCS membership and contamination flags; Laya-Fin and
      the anchor highlighted.
    4 Monthly IC: best API model vs anchor across val+test, vertical lines at decision-model release dates
      (2026-09-15 onward lies after the sample — annotate) — a contamination cliff would be visible.
    5 Shapley value of information (news / reaction / interaction) by tier and decision point.
    6 Filter efficiency: selection share vs material recall per filter (frontier), chosen filter marked.
    7 Strategy cumulative net returns (10 bp) by tier — S-CONV first, then S-D0 / S-D1 / S-D2 — vs benchmarks, with
      the placebo band.
    8 EXPLAINING THE MOVE (PREREG A3, Kelly–Su–Zhang style): (a) stacked bars of the out-of-sample share of
      stock-specific daily variance explained — market + sector → + ex-ante news → + ex-post news → + explanation —
      by tier; (b) persistence θ by the model's move_reason with CIs; (c, optional) the market-level replication.
    Appendix: reliability diagrams; encoding ablation; masking/identifiability; ablations (news removed, shuffled
    news); robustness forest plot.
S3. TABLES — copy NA-12/NA-13 LaTeX tables into artifacts/NA-14/tables with consistent formatting.
S4. CAPTIONS — captions.yaml with every number in a caption referenced by table key; a test asserts each equals the
    table value.
S5. REPLICATION — `make paper` rebuilds all figures/tables from work/ caches and artifacts (no API calls; offline
    client), compares sha256 of CSVs with a committed digest list; docs/REPLICATION.md (environment, data needs,
    exact commands, expected digests, spend ledger total); docs/paper_outline.md (sections → figures/tables).

## Acceptance criteria

- AC1 — `make paper` runs offline and reproduces every CSV digest.
- AC2 — CAPTIONS match tables (test).
- AC3 — Each figure has its CSV; palette/fonts per the dataviz skill; minimum font size ≥ 7 pt at print width.
- AC4 — No new analysis: every plotted number traces to NA-12/NA-13/NA-06/NA-03 outputs.

## Constraints

- No API calls; no frozen-file changes. Register artifacts; Conventional Commits; do not merge. Self-audit.
```

### Verification prompt — NA-14

```text
Independent verifier for NA-14 (branch feat/NA-14-paper-figures). READ-ONLY; restore; no commits; no API calls.

1. `make verify`; `make paper` → all digests OK.
2. Open each PDF: legible at print size, colour-blind-safe palette, axis labels/units present, CIs drawn. Figure 1
   must show realized paths against each V-decile's dashed target line and the κ_h panel with the line at 1.
3. Pick 10 caption numbers and trace each to its table cell.
4. Confirm each figure script reads only its CSV (grep for other reads).
5. GAC1–GAC5.

Verdict: PASS / FAIL per AC1–AC4 and GAC.
```

---

## NA-15 — [Run, later] Forward test on post-release news

**Category:** Phase 6 — the only uncontaminated test for vendor decision models. Every API model was released by 2026-10-21. This chunk runs the **frozen** pipeline, unchanged, on news published after 2026-10-21, once the operator exports it.

**Goal:** a forward-test REPORT that re-estimates H1–H4 with the frozen spec on the new window, for the primary instrument, the best API comparator and the anchor. It is reported separately from the main test.

**Dependencies:** NA-14 merged; operator exports NewsWitch news for 2026-08-01 → latest into `Data/` (new files); ATOM prices current. · **Estimated time:** 1 day · **Branch:** `feat/NA-15-forward`

### Power prompt — NA-15

```text
You are implementing NA-15 for /Users/amir/Research/NewsAction: the forward test. You may NOT change any frozen
file, threshold, model choice or question. You extend the data window only.

Read first: CLAUDE.md; docs/PREREG.md; artifacts/NA-11/freeze.json; artifacts/NA-12/REPORT.md; docs/REPLICATION.md.
Branch: feat/NA-15-forward.

## Scope

S1. DATA — register the new Data/news_2026b*.parquet (or as delivered) in the manifest; extend the ATOM snapshot
    (re-run scripts/export_atom_snapshot.py with a new end date into work/snapshot_fwd/, sealed for sessions after
    2026-10-21 until S4); extend panels with the frozen code.
S2. WINDOW — forward window = first session after 2026-10-21 → last session with complete t+5 targets. Pre-register
    in docs/decisions/NA-15.md BEFORE computing anything: window, models, tests (H1–H4 as frozen).
S3. RUN — rebuild events/states with the frozen filter/encoding/masking; run the primary instrument, best API
    comparator (same model ids; re-run canary first and report drift) and Laya-Fin/anchor (Kaggle inference) within
    the $2 cap.
S4. UNBLIND the forward targets (a new freeze record for the forward window, created before any forward call) and
    run spec.py unchanged.

## Acceptance criteria

- AC1 — No diff to frozen files (git diff prereg-freeze).
- AC2 — The forward window and plan were committed before the first forward call (timestamps).
- AC3 — Spend ≤ $2; total ≤ $30 (or an operator-approved increase recorded).
- AC4 — REPORT compares test vs forward results per model; contamination interpretation stated.

## Constraints

- Frozen everything; register artifacts; Conventional Commits; do not merge. Self-audit.
```

### Verification prompt — NA-15

```text
Independent verifier for NA-15. READ-ONLY; offline client; restore; no commits.
1. `make verify`. 2. git diff prereg-freeze → no frozen-file changes. 3. Timestamps: plan commit < first forward call.
4. Recompute H2 on the forward window for the primary instrument. 5. Spend ledger. 6. GAC1–GAC5.
Verdict: PASS / FAIL per AC1–AC4 and GAC.
```

---

## Appendix A — Artifact flow (who writes what, who reads it)

| Artifact | Producer | Readers |
|---|---|---|
| `work/market/*.parquet` | NA-00 | NA-04 |
| `work/snapshot/*`, `sealed/*` | NA-01 (NA-10 adds `bars30_2026`) | NA-01..NA-04, `lock` (sealed) |
| `work/panel/panel_public.parquet`, `panel_test_inputs.parquet`, `companies.parquet`, `tiers_monthly.parquet` | NA-01 | NA-02..NA-13 |
| `work/news/articles_clean.parquet`, `embeddings_ts.parquet`, `coverage_member_month.parquet` | NA-02 | NA-03, NA-04, NA-09 |
| `work/events/events_{d0,d2}.parquet`, `labels_public.parquet` | NA-03 | NA-04..NA-12 |
| `work/states/*` | NA-04 (NA-10 adds D1; NA-11 adds test Call B) | NA-05..NA-11 |
| `cache/decisions.sqlite`, `ledgers/spend.jsonl` | NA-05..NA-11, NA-15 | verifiers, NA-14 |
| `work/dm/tournament/*`, `leaderboard.csv` | NA-06 | NA-07, NA-11, NA-14 |
| `work/kaggle/predictions/*` | NA-08 (NA-11 adds test Call B) | NA-11, NA-12 |
| `work/baselines/*` | NA-09 (NA-11 adds test parts) | NA-11, NA-12 |
| `work/bars30/*`, `work/panel/intraday_public.parquet` | NA-10 | NA-11..NA-13 |
| `configs/frozen.yaml`, `artifacts/NA-11/freeze.json`, tag `prereg-freeze` | NA-03, NA-06, NA-07, NA-11 | `lock`, NA-12..NA-15 |
| `work/analysis/targets_test.parquet`, `artifacts/NA-12/*` | NA-12 | NA-13, NA-14 |

## Appendix B — Sources

- **Decision models:**
  - [JevAgentHarness (arXiv 2610.21412)](https://arxiv.org/abs/2610.21412)
  - [Jev on OpenRouter](https://openrouter.ai/docs/guides/community/jev)
  - [Decisions API reference (OpenRouterTeam skills)](https://github.com/OpenRouterTeam/skills/blob/main/skills/openrouter-decisions/references/decisions-api.md)
  - [TypeSafe primitives](https://docs.typesafe.ai/primitives) · [TypeSafe confidence](https://docs.typesafe.ai/confidence)
  - [Decision-model catalog](https://openrouter.ai/models?output_modalities=decisions)
- **Laya:**
  - [Laya model card](https://huggingface.co/convaiinnovations/laya)
  - [Laya fine-tuning notebook](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb)
- **ModernBERT:** [answerdotai/ModernBERT-large](https://huggingface.co/answerdotai/ModernBERT-large)
- **Finance:**
  - [Kelly–Su–Zhang, "Explaining Realized Returns: Roll's R² 40 Years Later"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7544058) ([NBER w35885](https://www.nber.org/papers/w35885))
  - [Team paper, arXiv 2608.14014](https://arxiv.org/pdf/2608.14014)
  - [Chen–Kelly–Xiu, "Expected Returns and Large Language Models"](https://papers.ssrn.com/sol3/Delivery.cfm/4416687.pdf?abstractid=4416687&mirid=1)
  - [Chan (2003)](https://academicnewsletter.sufe.edu.cn/info/357702) · [Savor (2012)](https://repository.upenn.edu/handle/20.500.14332/34495)
- **Style:** [Wegmann et al., A Survey on Representing Linguistic Style](https://annawegmann.github.io/pdf/Style_Survey_preprint.pdf)
- **Vendor facts (internal):** `~/GitHub/Atom/docs/runbooks/fmp_intraday_capability.{md,json}`
