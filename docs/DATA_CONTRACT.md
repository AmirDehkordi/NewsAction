# Data contract

Every derived artifact used across chunks is listed here (CLAUDE.md F21: chunks communicate only
through these files). `make manifest` fails when an artifact in `work/MANIFEST.json` has no entry
here, or when the sha256 written here differs from the manifest.

## How to add an entry

One `###` section per file, headed by its repository-relative path in backticks:

```markdown
### `work/<dir>/<name>.parquet`
- **Producer:** chunk + script/module that writes it (via `newsaction.io`)
- **Inputs:** files read (Data/ inputs are fingerprinted in `MANIFEST["inputs"]`)
- **Schema:** column: type, ...
- **Key:** columns that identify a row (or "none" with the reason)
- **Rows / coverage:** count, entities, date range
- **Availability:** when each value becomes known (registry kind in configs/availability.yaml if it can be a model input)
- **sha256:** `<64 hex, equal to work/MANIFEST.json>`
```

Re-running a producer must reproduce the same sha256; if it changes, update the entry in the same
commit.

## NA-00 — market inputs converted from `Data/market`

Producer for all five files: `scripts/convert_pickles.py` (NA-00 S11), run with
`uv run python scripts/convert_pickles.py` in the NewsAction environment (pandas ≥ 3). Rows are not
transformed or dropped; row counts per series/ticker equal the pickles (tests/test_market_pickles.py).

### `work/market/fred_daily.parquet`
- **Producer:** `scripts/convert_pickles.py` (NA-00 S11)
- **Inputs:** `Data/market/fred_daily.pkl` (sha256 `bfb67657832f82f5aee99500aca61d828e7f6f02539e4e27212754c2d691446b`)
- **Schema:** `series_id` large_string, `date` timestamp[us], `value` double
- **Key:** `(series_id, date)` unique
- **Rows / coverage:** 7,522 rows; 4 series (DFF, DGS10, DGS2, BAMLH0A0HYM2); 2019-01-01 .. 2026-07-31; 174 NaN values kept as in the source.
- **Availability:** `date` is the FRED **observation** date, not the publication time. Use only observations dated before the session (t−1, kind `t_minus_1`); publication lags are verified where the field is first used (NA-04).
- **sha256:** `095b134afb9f44ce1f43aeddc87b5a4d928e943a98f31b2b35549accd7715d33`

### `work/market/cpi_vintages.parquet`
- **Producer:** `scripts/convert_pickles.py` (NA-00 S11)
- **Inputs:** `Data/market/fred_releases.pkl` (sha256 `e7be22a7f94085eeda49508c20a37112cfb59bbcc100826504a609f103d6e5d6`)
- **Schema:** `series_id` large_string, `date` timestamp[us], `value` double, `realtime_start` timestamp[us]
- **Key:** `(series_id, date, realtime_start)` unique
- **Rows / coverage:** 775 rows; ALFRED vintages of CPIAUCSL and CPILFESL; `realtime_start` 2019-02-13 .. 2026-07-14; 2 NaN values (NaT in the source).
- **Availability:** A value is known from its `realtime_start` (vintage date). The release time of day is not recorded, so the first chunk to use it decides the intraday rule (NA-04).
- **sha256:** `654646a6557aaba8546325206a7a1f175033eaab97e6cd77bc2a9f188b4907a2`

### `work/market/earnings_dates.parquet`
- **Producer:** `scripts/convert_pickles.py` (NA-00 S11)
- **Inputs:** `Data/market/earnings_dates.pkl` (sha256 `7f60c7b0e3db565d1df9a357a8a5c9812e847939e59d34f66be7641083425b6a`)
- **Schema:** `ticker` large_string, `earnings_ts` timestamp[us]
- **Key:** none: 43 duplicate `(ticker, earnings_ts)` rows kept as in the source
- **Rows / coverage:** 115,766 rows; 2,891 tickers (106 source tickers have no dates); 1998-07-30 .. 2026-11-25.
- **Availability:** `earnings_ts` is **naive**. Times of day (16:00, 07:00, 06:00, 08:00 dominate) suggest America/New_York wall time, but the timezone is not recorded. The calendar was collected retrospectively, so it is not proof that a date was announced in advance. NA-04 decides how to use it for “a scheduled report within W0”.
- **sha256:** `7e717dbdd157df4cb015cb05d8b96e67a0279e8eda4a85671199e78ffd871aa7`

### `work/market/shares.parquet`
- **Producer:** `scripts/convert_pickles.py` (NA-00 S11)
- **Inputs:** `Data/market/shares.pkl` (sha256 `06fba76bc2b7614b6d91f36c244397ef2b1ff13ef4312f46a0897612d70f8e3d`)
- **Schema:** `ticker` large_string, `date` timestamp[ms], `shares` int64
- **Key:** `(ticker, date)` unique
- **Rows / coverage:** 1,496,155 rows; 2,990 tickers (7 source tickers empty); 2019-01-05 .. 2026-08-04.
- **Availability:** Shares outstanding by date, collected retrospectively; as-of semantics unverified. PREREG §3.3 tiers use ATOM `shares_basic`, not this file.
- **sha256:** `2e0a3e88317bd5983abf327eb346eca1d6291e5594903f8d9d8b217243cf982f`

### `work/market/market_prices.parquet`
- **Producer:** `scripts/convert_pickles.py` (NA-00 S11), byte-for-byte copy via `io.copy_data_file`
- **Inputs:** `Data/market/market_prices.parquet` (sha256 `1f5a84f8bc394bac0dbd6ff94985e6fba48254fe1eef06fa029261e075afeb58`, identical to the copy)
- **Schema:** `symbol` large_string, `date` timestamp[ms], `close` double, `volume` int64
- **Key:** `(symbol, date)` unique
- **Rows / coverage:** 32,407 rows; 17 symbols (SPY, ^GSPC, ^NDX, ^VIX, CL=F, DX-Y.NYB, 11 sector ETFs); 2019-01-02 .. 2026-08-04.
- **Availability:** a close dated d is known at close(d), so it is usable from the next session (kind `t_minus_1`). **Contains 2026 rows** like `Data/` itself: never compute or show a statistic of 2026 returns before unblinding (CLAUDE.md B8; PREREG §15 entry of 2026-10-24).
- **sha256:** `1f5a84f8bc394bac0dbd6ff94985e6fba48254fe1eef06fa029261e075afeb58`

## NA-00 — bookkeeping files (no fixed hash)

### `work/MANIFEST.json` (gitignored)
- **Producer:** `newsaction.io` (every `write_parquet` / `register_file` / `copy_data_file` / Data/ read)
- **Schema:** `{"version": 1, "artifacts": {path: {sha256, bytes, rows, columns[{name, type}], producer, description, git_sha, written_at}}, "inputs": {path: {sha256, size, mtime, mtime_ns, first_read_at, first_read_git_sha}}}`
- **Key:** repository-relative path
- **Availability:** n/a. `make manifest` re-hashes every artifact, checks inputs by size + mtime (`make manifest-deep` re-hashes them) and flags unregistered parquet files under `work/`.

### `ledgers/{spend,trials,test_access,fmp_requests}.jsonl` (committed)
- **Producer:** `newsaction.ledger` (`SpendLedger`, `TrialLedger`, `AccessLedger` via `newsaction.lock`, `FmpLedger`)
- **Schema:** one JSON object per line with `ts` (UTC ISO) and `prev` (sha256 of the previous line; `0`×64 for the first). Spend events: `reserve` {chunk, rid, usd, note} / `spend` {chunk, rid, usd, close, unreserved, meta, git_sha} / `release` {chunk, rid}. Trials: {chunk, kind, name, params_hash, split, metric, value}. Test access: {caller, name, purpose ∈ reactions | targets | write, allowed, reason, git_sha}. FMP: {event: request, n, meta}.
- **Key:** line order (append-only, hash-chained; `make ledgers` verifies every chain)
- **Availability:** n/a. Empty at the end of NA-00.
