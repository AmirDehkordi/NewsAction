# NA-00 REPORT — scaffold, time / lock / ledger primitives, PREREG v0

Date: 2026-10-24 · Branch `feat/NA-00-scaffold` (from `main` @ `3d70988` "chore: initial docs") ·
Tag `prereg-v0` → `3d70988` · Decisions: `docs/decisions/NA-00.md`

Environment: Python 3.12.13, uv 0.11.7, pandas 3.1.0, pyarrow 26.0.0, pydantic 2.14.1,
exchange-calendars 4.13.2 (pinned).

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 git + ignore | done | `git init -b main`; root commit `3d70988` "chore: initial docs" (CLAUDE.md, PRD, PREREG); `.gitignore` (Data, work, cache, .env, *.sqlite, .venv/, __pycache__/, .mypy_cache/, .ruff_cache/, kaggle.json, *.ckpt, *.safetensors; ledgers/ and artifacts/ committed) |
| S2 uv project | done | `pyproject.toml` (newsaction, `>=3.12,<3.13`, src layout, all runtime + dev deps; extras `embed`, `laya`, `kaggle` declared, not installed), `uv.lock`; `uv sync` OK |
| S3 Makefile | done | `Makefile`: sync, lint, format, type, test, manifest, manifest-deep, ledgers, verify |
| S4 configs | done | `configs/{project,splits,availability,frozen}.yaml`; `src/newsaction/{config,paths}.py` |
| S5 calendar | done | `src/newsaction/calendar.py` (exchange_calendars XNYS; `FORCED_CLOSURES` keeps 2025-01-09 closed, a no-op on 4.13.2) |
| S6 timeutil | done | `src/newsaction/timeutil.py` (`precision_class`, `availability`; scalar + Series/ndarray, one code path) |
| S7 pit | done | `src/newsaction/pit.py`; `configs/availability.yaml` (7 kinds incl. `d2_reaction`, 17 seed columns) |
| S8 lock | done | `src/newsaction/lock.py` (`FREEZE_FILES`, `compute_freeze_hash`, `freeze`, `is_frozen`, `require_frozen`, `require_unblind`, `sealed_path`, plus `read_sealed` / `write_sealed`) |
| S9 ledgers | done | `src/newsaction/ledger.py` (hash-chained JSONL; `SpendLedger`, `TrialLedger`, `AccessLedger`, `FmpLedger`); `ledgers/*.jsonl` (empty) |
| S10 io | done | `src/newsaction/io.py` (`write_parquet`, `read_parquet`, `register_file`, `record_input`, `read_data_*`, `copy_data_file`, `manifest_check`); `work/MANIFEST.json` |
| S11 pickles | done | `scripts/convert_pickles.py` → `work/market/{fred_daily,cpi_vintages,earnings_dates,shares,market_prices}.parquet` |
| S12 docs | done | `README.md`, `docs/DATA_CONTRACT.md`, `docs/decisions/NA-00.md`, this file, `.env.example` |
| S13 blinding test | done | `tests/test_blinding.py` (AST scan of `src/` + refusals + real-ledger GAC3 check) |
| S14 tag + commit | done | annotated tag `prereg-v0` on `3d70988`; work committed on `feat/NA-00-scaffold`; not merged |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 `make verify` | `make verify` → exit 0: ruff "All checks passed!", "22 files already formatted"; mypy --strict "no issues found in 10 source files"; pytest **219 passed**; "manifest: OK" (5 artifacts, 5 inputs); "ledgers: OK" (4 ledgers, 0 records) | PASS |
| AC2 calendar goldens | `tests/test_calendar.py` (45 tests): W0(2024-03-11) = (2024-03-08 21:00Z, 2024-03-11 13:15Z]; W0(2024-11-04) = 2024-11-01 20:00Z → 2024-11-04 14:15Z; close(2024-11-29) = 18:00Z = W0(2024-12-02).start; W0(2024-01-16).start = 2024-01-12 21:00Z; 2025-01-09 not a session, W0(2025-01-10).start = 2025-01-08 21:00Z; close(2025-07-03) = 17:00Z. Also: the six half days exactly, DST pairs 2024/2025, session counts 252 / 250, equality with exchange_calendars' schedule for 2023–2025, a 300-example property test. Mutations close_utc → const 21:00Z: **RED**; cutoff → fixed 14:15Z: **RED** | PASS |
| AC3 availability | `tests/test_timeutil.py` (20): verifier inputs 1735689600 → 2025-01-01 23:59:59Z, 1735693200 → 01:59:59Z (+3599 s), 1735693260 → 01:01:59Z (+59 s), 1735693261 → unchanged; hypothesis properties per class, `availability ≥ publication`, same UTC date, vectorized = scalar. Mutation "delete date_only branch": classification **RED**, availability **RED** | PASS |
| AC4 PIT registry | `tests/test_pit.py` (38): `check_inputs(["z_id"], "D0")` raises (z_id = post); unknown column raises; full 7-kind × 3-point visibility matrix; `assert_visible` raises on a planted row 1 s after the decision and on NaT. Mutations check_inputs (method) / (module) / assert_visible → no-op: **RED** ×3 | PASS |
| AC5 lock | `tests/test_lock.py` (29), temp layout and temp ledger: before the freeze both purposes raise `LockError` and each attempt appends one `allowed: false` entry (caller `tests/test_lock.py:<test>:<line>`, git_sha). Freeze refused without `frozen_requested`, one-way; reactions allowed after the freeze; targets need `NA_UNBLIND=1`; one-character edit of frozen.yaml → hash mismatch. Mutations is_frozen → True / skip logging / skip hash check: **RED** ×3 | PASS |
| AC6 ledger | `tests/test_ledger.py` (19): `reserve(0.25)` refused by the NA-05 cap 0.20 although the total allows it; the total cap refuses NA-07 after an NA-06 overrun; 4 processes × 150 appends → 600 valid JSON lines, chain intact, per-process order kept. Mutations remove chunk-cap / total-cap / FMP-cap / chain check: **RED** ×4 | PASS |
| AC7 configs = PREREG | `tests/test_configs_match_prereg.py` (11): split dates (§4), contiguity (next_session(end) = next start), embargo 5 (§4.2), max horizon 20 (§5.6), 09:15 / 10:00 (§2.4–2.5), caps 0.2/4/2/2/18/2 + reserve 1.8 = 30 (§13, parsed from the PREREG line), FMP 3000 (§13), seed 2026; each value also asserted in the PREREG text | PASS |
| AC8 pickles | `tests/test_market_pickles.py` (8): per-key counts equal the pickles: fred_daily 7,522 (2,769 + 1,979 + 1,979 + 795), cpi_vintages 775 (389 + 386), earnings_dates 115,766 (2,891 tickers), shares 1,496,155 (2,990 tickers); market_prices sha256 = input sha256. `make manifest` and `make manifest-deep` → OK. Rerun reproduced all 5 sha256 | PASS |
| AC9 git | `git log main` root = "chore: initial docs" (3 files); `git cat-file -t prereg-v0` = tag → `3d70988`; `git show prereg-v0:docs/PREREG.md` = v0 byte-for-byte; the current PREREG differs from v0 only by 2 appended §15 rows (test asserts this); `git check-ignore Data work cache .env` prints all four; `git ls-files Data` = 0 | PASS |
| GAC2 Data unchanged | no writes under Data/; `make manifest-deep` re-hashed the 5 inputs = recorded sha256 | PASS |
| GAC3 blinding | AST scan of `src/` (excl. lock.py) finds 0 test-period literals and 0 sealed-path uses; `ledgers/test_access.jsonl` has 0 entries (tests use temp ledgers) | PASS |
| GAC4 spend | 0 records; $0 | PASS |
| GAC5 contract | `make manifest` checks the 5 artifact sha256 against `docs/DATA_CONTRACT.md` → OK | PASS |

Mutation table (a session-local script, not committed. Each mutation was applied to the real
source, `pytest -x` run and the file restored. The suite was green before and after, and `src/`
was byte-identical afterwards):

| Mutation | File | Result |
|---|---|---|
| close_utc → constant 21:00Z | calendar.py | RED |
| 09:15 cutoff → fixed 14:15Z | calendar.py | RED |
| delete date_only branch (classification) | timeutil.py | RED |
| delete date_only branch (availability) | timeutil.py | RED |
| check_inputs (method) → no-op | pit.py | RED |
| check_inputs (module) → no-op | pit.py | RED |
| assert_visible → no-op | pit.py | RED |
| is_frozen → True | lock.py | RED |
| sealed_path skips logging | lock.py | RED |
| require_unblind skips hash check | lock.py | RED |
| remove chunk-cap comparison | ledger.py | RED |
| remove total-cap comparison | ledger.py | RED |
| FMP cap check removed | ledger.py | RED |
| hash chain not checked | ledger.py | RED |
| read_parquet skips re-hash | io.py | RED |
| read_parquet allows sealed dir | io.py | RED |
| input change not detected | io.py | RED |

## 3. Spend

OpenRouter: $0.00 this chunk, $0.00 cumulative (`ledgers/spend.jsonl` empty). FMP requests: 0.
No network calls apart from `uv sync`; no ATOM, OpenRouter, FMP or Kaggle access.

## 4. Look-ahead self-check

No analysis was run. The only data read:

| Input | Use | Availability note |
|---|---|---|
| `Data/market/{fred_daily,fred_releases,earnings_dates,shares}.pkl` | structure inspection, then verbatim long-format conversion | written to `work/market/`; semantics in DATA_CONTRACT (FRED observation date ≠ publication; CPI known from `realtime_start`; earnings naive) |
| `Data/market/market_prices.parquet` | byte copy; parquet footer (rows, schema) | contains rows to 2026-08-04; no value was printed or summarized |

Printed for documentation: row counts, key-duplicate counts and min/max dates. No price, return
or statistic of any session ≥ 2026-01-02 was computed or shown.

## 5. Deviations from PREREG (both logged in `docs/PREREG.md` §15, before the freeze)

1. **§4.4 (2):** the freeze hash covers PREREG up to the §15 heading; §15 is verified append-only
   (prefix sha256 + byte length recorded in freeze.json). Otherwise any post-freeze deviation,
   which CLAUDE.md B11 and PRD NA-12 allow, would break the unblinding hash.
2. **§4.3 (clarification, no code change):** 2026 adjusted closes exist outside the sealed
   directory (`Data/prices`, `Data/market`, and the S11 copy `work/market/market_prices.parquet`),
   and 2026 t−1 features need them. Blinding of close-based 2026 outcomes is therefore procedural.

PRD-level inconsistencies resolved without touching PREREG (details in `docs/decisions/NA-00.md`):
- S7's kind list lacks `d2_reaction`, which its own D2 rule uses.
- S13 forbids "sealed" in `src/`, but S4 puts `SEALED` in `paths.py`, so paths.py may define it.
  Calls to the lock API (`lock.sealed_path`) must be allowed, since NA-01 is required to make them.
- `frozen` vs `frozen_requested` in frozen.yaml: `freeze()` sets `frozen: true` before hashing.

## 6. STOP conditions and owner decisions

No STOP condition fired (no budget-relevant activity). Owner decisions requested:
1. Confirm deviation 1 (freeze-hash treatment of the Deviations log).
2. Confirm deviation 2 (procedural blinding of 2026 closes), or ask NA-01 to handle the 2026 rows of
   `work/market/market_prices.parquet` differently.
3. **Git identity:** none was configured. The commits and the tag use
   `NewsAction operator <mitchellwaters@hotmail.com>`, set through environment variables only
   (git config untouched). Re-author before merging if you want a different author.

Known limitation (also in the PRD): the lock is procedural. Python code can still open a sealed
file by hand. What stands against that is the access ledger, the src/ scan, the verifier greps and
the freeze hash.

## 7. Files

- **Added:** `.gitignore`, `.env.example`, `pyproject.toml`, `uv.lock`, `Makefile`, `README.md`.
- **Added:** `configs/{project,splits,availability,frozen}.yaml`.
- **Added:** `src/newsaction/{__init__,paths,provenance,config,calendar,timeutil,pit,ledger,lock,io}.py`.
- **Added:** `scripts/convert_pickles.py`, `ledgers/{spend,trials,test_access,fmp_requests}.jsonl`.
- **Added:** `docs/DATA_CONTRACT.md`, `docs/decisions/NA-00.md`, `artifacts/NA-00/REPORT.md`.
- **Changed:** `docs/PREREG.md` (2 rows appended to §15 only).
- **Derived (gitignored):** `work/market/*.parquet` (5), `work/MANIFEST.json`.
- **Tests (219):** `test_calendar` 45, `test_pit` 38, `test_lock` 29, `test_repo` 24,
  `test_timeutil` 20, `test_ledger` 19, `test_io` 17, `test_configs_match_prereg` 11,
  `test_blinding` 8, `test_market_pickles` 8; shared fixture in `tests/conftest.py`.
- **`make verify`:** exit 0 (lint, format, mypy --strict, 219 passed, manifest OK, ledgers OK).
