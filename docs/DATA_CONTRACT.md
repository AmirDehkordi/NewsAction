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

## NA-01 — ATOM snapshot (read-only export)

Producer for all snapshot files: `scripts/export_atom_snapshot.py` (NA-01 S1), run once under ATOM's venv
(`/Users/amir/GitHub/Atom/.venv/bin/python scripts/export_atom_snapshot.py --out work/snapshot`) in a single
`REPEATABLE READ, READ ONLY` transaction; registered in the NewsAction environment by `scripts/register_snapshot.py`
(sha256 checked against `MANIFEST_snapshot.json`). Inputs: ATOM Postgres (`atom_postgres`), git `f8015d54`.
Export instant 2026-10-24T17:31:10Z. Session dates are XNYS-local; instants are UTC.

### `work/snapshot/MANIFEST_snapshot.json`
- **Producer:** `scripts/export_atom_snapshot.py` (NA-01 S1)
- **Schema:** JSON: export instant, ATOM / NewsAction git sha, read-only transaction evidence (`SHOW transaction_read_only` = on), `count(*)` of md.price_eod and uni.member before / inside / after the export, blinding bounds, ranges, accessor names, the raw SELECTs, per-file sha256 / rows / columns / date range.
- **Key:** n/a
- **Availability:** n/a (provenance record)
- **sha256:** `97d38ebc9e3b324c2236828a4933045e753e7f3be6197171c96761399bc4112c`

### `work/snapshot/members_by_session.parquet`
- **Producer:** export S1.a via `get_universe_members("sp500", as_of=session_open_instant("NYSE", d))`
- **Schema:** `session` date32, `symbol_id` int64, `ticker` string (ATOM's current ticker), `as_of` timestamp[us, UTC]
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 451,196 rows; 897 sessions 2023-01-03 .. 2026-07-31; 503 symbols (500 companies) per session median; 565 distinct ids.
- **Availability:** membership at open(s), kind `static` (index changes are announced in advance). Test-period rows are membership only, no prices.
- **sha256:** `e9d1d58e2a3bc9d132f268ea2fe9086d4a4492d99b9cbb0d2f4cba3fdce71915`

### `work/snapshot/symbols.parquet`
- **Producer:** export S1.b (SELECT on ref.symbol ⋈ ref.exchange)
- **Schema:** `symbol_id` int64, `ticker`, `name`, `cik` (6 of 566 filled), `exchange`, `asset_class` string, `listing_date`, `delisting_date` date32, `is_active` bool
- **Key:** `symbol_id`
- **Rows / coverage:** 566 = 565 members ∪ SPY (21538).
- **Availability:** `static` (current-state master data; `delisting_date` is known only after the fact — do not use it as a predictor).
- **sha256:** `aa7e13e649828acc9c707312707572a25c65985019c744a10337f515ed8a1cbf`

### `work/snapshot/symbol_tickers.parquet`
- **Producer:** export S1.b (SELECT on ref.symbol_ticker)
- **Schema:** `symbol_id` int64, `ticker`, `exchange`, `valid_from` / `valid_to` timestamp[us, UTC], `source`
- **Key:** `(symbol_id, ticker, valid_from)`
- **Rows / coverage:** 11 rows (6 renamed symbols: BNY/BK, FISV/FI, MRSH/MMC, PSKY/PARA, SOLS/SOLSV, SATS); all ranges open from 1990 (no real history).
- **Availability:** `static`
- **sha256:** `86d928eff4000e1fd4283d8216820f6f63e5cadc7d4b899a98590b5f5d41e2f1`

### `work/snapshot/gics.parquet`
- **Producer:** export S1.c (ref.symbol_sector ⋈ ref.sector hierarchy, resolved in Python)
- **Schema:** `symbol_id`, `sector_id` int64, `node_level` int32, `taxonomy`, `level{1..4}_code`, `level{1..4}_name` string, `valid_from`, `valid_to` timestamp[us, UTC], `source`
- **Key:** `(symbol_id, valid_from)`
- **Rows / coverage:** 565 rows (SPY has none). Every node is GICS level 1, so levels 2–4 are null; one open-ended range per symbol from 1970 (current classification, no history).
- **Availability:** `static` (current classification applied to all sessions; NA-01 REPORT).
- **sha256:** `e01dd942d9d4dfc7a68a690bfbabe8c6db0b241c049dd3d9bb6b2e4db4e0a2c9`

### `work/snapshot/prices_raw.parquet`
- **Producer:** export S1.d via `get_prices_eod_by_id(ids ∪ SPY, 2022-01-03, 2026-07-31, as_of=export instant, adjust="raw")`, rows ≤ 2025-12-31
- **Schema:** `symbol_id` int64, `trade_date` date32, `open`, `high`, `low`, `close` double, `volume` int64 (as traded, FMP via ATOM)
- **Key:** `(symbol_id, trade_date)`
- **Rows / coverage:** 555,798 rows; 2022-01-03 .. 2025-12-31; 563 of 565 members + SPY.
- **Availability:** a bar dated d is known at close(d) (`post` for d; usable as t-1 from the next session).
- **sha256:** `cc43eb3c5e84cd5bf4f1da4e6cacba382dd490d47b23fb5ae4c623fb864d698e`

### `work/snapshot/total_return_check.parquet`
- **Producer:** export S1.d, same call with `adjust="total"` (splits incl. ATOM's spin-off pseudo-splits + cash dividends known at the export instant), rows ≤ 2025-12-31
- **Schema:** as `prices_raw` (adjusted OHLC, split-adjusted volume)
- **Key:** `(symbol_id, trade_date)`
- **Rows / coverage:** 555,798 rows; 2022-01-03 .. 2025-12-31.
- **Availability:** as `prices_raw`. Used for the QC comparison and as the AdjClose fallback for the 40 ids without Data/prices (PREREG §15).
- **sha256:** `ecfefda44ae370ccd408800e4c8424a2788c56a5b80970344e425f091a4f850f`

### `work/snapshot/sealed/prices_raw_2026.parquet`
- **Producer:** export S1.d, rows ≥ 2026-01-02 of the raw call. Written by the export; registered by hash only (never opened; one `write` entry in `ledgers/test_access.jsonl`).
- **Schema:** as `prices_raw`
- **Key:** `(symbol_id, trade_date)`
- **Rows / coverage:** 78,131 rows (test period).
- **Availability:** BLINDED. Readable only through `newsaction.lock` (`reactions` after the NA-11 freeze; `targets` after unblinding).
- **sha256:** `58895c0ff76c29828031bf1635313ea405f54bbd301820e71c3d21c35675e98b`

### `work/snapshot/sealed/total_return_check_2026.parquet`
- **Producer:** export S1.d, rows ≥ 2026-01-02 of the total-return call; registered by hash only.
- **Schema:** as `total_return_check`
- **Key:** `(symbol_id, trade_date)`
- **Rows / coverage:** 78,131 rows (test period).
- **Availability:** BLINDED, as above.
- **sha256:** `410248ab8153aa8cc764ae8768b2b5f9ee1a7e10131ae1925ceed57ecfca7250`

### `work/snapshot/corporate_actions.parquet`
- **Producer:** export S1.e (SELECT on md.corporate_action for the exported ids; all dates)
- **Schema:** `action_id`, `symbol_id` int64, `action_type` string, `announce_date`, `ex_date`, `record_date`, `pay_date` date32, `split_ratio`, `cash_amount` double, `acquirer_symbol_id` int64, `exchange_ratio` double, `source` string
- **Key:** `action_id`
- **Rows / coverage:** 20,923 rows; ex-dates 1998-11-12 .. 2026-10-23. No `spinoff` rows: ATOM stores spin-offs as `split` rows with the price ratio (GE 2024-04-02: 1.253); `adjust.is_true_split` separates them. Some spin-offs are missing (HON/Solstice 2025-10, CMCSA/Versant 2025-12).
- **Availability:** an action is known from `announce_date`; NA-01 uses ex-dates only for adjustment factors and share bases. Contains no prices.
- **sha256:** `11d3247da15cb821065fade7288b2d185c2123229470204784cc4c440820202d`

### `work/snapshot/shares_basic.parquet`
- **Producer:** export S1.f (SELECT on fnd.financial_metric, metric `shares_basic`)
- **Schema:** `symbol_id` int64, `period_end` date32, `period_type` string (Q/A), `fiscal_year`, `fiscal_period` int32, `value` double (millions), `known_from` / `known_to` timestamp[us, UTC] (= lower/upper(knowledge_range)), `source`, `ingested_at` timestamp[us, UTC]
- **Key:** `(symbol_id, period_end, period_type, known_from)`
- **Rows / coverage:** 35,539 rows; 547 of 565 members; period ends 1992-12-31 .. 2026-07-05.
- **Availability:** `known_from` is synthetic (period_end + 45 days for Q, + 90 for A); no row is ever superseded. Values are **company-level** (all share classes carry the same count) and **restated to the split basis of the CIQ pull** (`ingested_at` 2026-08-01) — NA-01 `tiers.share_basis` verified 115/115 true splits.
- **sha256:** `0ebece5fe85eb1f961aff52c52ab5e10abbcac9be1d53c36e5f86e96ad3fe56f`

### `work/snapshot/estimates_fy1.parquet`
- **Producer:** export S1.g via `get_estimates(tickers, ["eps_diluted"], ["mean", "count"], annual periods, as_of=end of month M, snapshot_start=first day of M)` for M = 2023-01 .. 2026-07, pivoted per snapshot
- **Schema:** `symbol_id` int64, `ticker` string, `period_end`, `as_of_date` date32, `mean` double, `n` int64 (analysts on the mean snapshot), `count` double (the `count` aggregation when stored that day), `visible_at` timestamp[us, UTC]
- **Key:** `(symbol_id, period_end, as_of_date)`
- **Rows / coverage:** 229,990 rows; snapshots are change-driven (stored when a value changes); 80 annual period ends; no ticker aliased.
- **Availability:** knowledge_range starts at 00:00 UTC of `as_of_date` (no restatements). Use only snapshots with `as_of_date` < session (kind `t_minus_1`); FY1 selection and the 30-day revision are NA-04's.
- **sha256:** `de9fde0faccd1af828c1db77f021e0c2bd5742b65c52d653dbda3cbcbfd263cf`

### `work/snapshot/calendar_atom.parquet`
- **Producer:** export S1.h via `atom_core.calendars.sessions_between / session_open_instant / session_close_instant` ("NYSE")
- **Schema:** `session` date32, `open_utc`, `close_utc` timestamp[us, UTC]
- **Key:** `session`
- **Rows / coverage:** 1,207 sessions 2022-01-03 .. 2026-10-23; equal to `newsaction.calendar` (tests/test_panel_calendar_equality.py).
- **Availability:** `static`
- **sha256:** `c3490a3addc6f7db8e44416226dbd6aa5e043b254bcd62f70861e5ec172f9749`

## NA-01 — daily panel

Producer for all panel files: `newsaction.panel.build` (NA-01 S7), `uv run python -m newsaction.panel.build`; deterministic
(a rebuild reproduces every sha256). Inputs: the public snapshot files above, `Data/prices/prices.parquet` (adjusted close
and volume), `work/market/market_prices.parquet` (SPY close) and `work/market/shares.parquet` (Yahoo share counts, the
independent reference of the share cross-check). Test-period closes from those two files are used only for
t-1 features of test sessions (PREREG §15, NA-00 row 2); the blinded raw prices are not read.

### `work/panel/panel_public.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S7)
- **Schema:** 87 columns. Ids/static: `session` date32, `symbol_id`, `company_id` int64, `ticker`, `sector` (GICS level 1), `split`, `adj_source` (data_prices | atom_total), `price_symbol` string, `member`, `half_day` bool. Tiers (t-1): `tier`, `dv_tier`, `tier_source` string, `rank`, `dv_rank` double, `is_rep` bool. Same-day (post): `raw_open`, `raw_close`, `raw_volume`, `adj_close`, `adj_open`, `adj_factor`, `r_{cc,on,id}`, `r_spy_{cc,on,id}`, `r_sec_{cc,on,id}`, `r_sec_n`, `ar_{cc,on,id}`, `z_{cc,on,id}`, `z_vol`, `qc_rule`, `qc_flag`. Risk (t-1): `beta_m`, `beta_s`, `beta_n`, `sigma_{cc,on,id}`, `logv_med60`, `logv_mad60`, `adv63`, `car_m{5,20,60}`, `z_m{5,20,60}`. Targets (post, purged): `y0`, `ar_o0_c{1,5}`, `z_o0_c{1,5}`, `ar_c0_o1`, `z_c0_o1`, `ar_o1_c{1,5,20}`, `z_o1_c{1,5,20}`, `fwd_lvl_o1_c{1,5,20}`, `y2`, `e5`, `car6_z`, `car_lvl_o0`, `car_lvl_c{0,1,2,5,10,20,60}`, `e5_lvl`, `delist_within_c20`. Reactions (d2_reaction): `g_d2`, `g_d2_lvl`. Formulas: `newsaction.panel.{adjust,risk,targets,reactions}` docstrings.
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 317,729 rows; sessions 2023-07-03 .. 2025-12-31; member rows 315,887 + 1,842 priced rows within 60 sessions after an exit (target horizons of leavers). `raw_volume` is ATOM's raw volume except on the 60 days before the ORLY, NOW and TPL splits that ATOM had already put on the post-split basis; those are restored to the traded basis (`adjust.volume_basis_check`, PREREG §15). It stays on ATOM's price basis, like `raw_close` (HON: both off by 2×, so their product is the traded dollar volume).
- **Availability:** per column in `configs/availability.yaml` (kinds static / t_minus_1 / d2_reaction / post). Every t-1 statistic uses data through close(t-1) (tests/test_panel_pit.py).
- **sha256:** `1d4f6009bd3ab82d18ea624a031c0f68f9efd46e6a18ac265086914ad037cd4f`

### `work/panel/panel_test_inputs.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S7)
- **Schema:** 29 columns, all `static` or `t_minus_1`: `session`, `symbol_id`, `ticker`, `company_id`, `member`, `sector`, `half_day`, `split`, `adj_source`, `price_symbol`, `is_rep`, `tier`, `rank`, `dv_tier`, `dv_rank`, `tier_source`, `beta_m`, `beta_s`, `beta_n`, `sigma_cc`, `logv_med60`, `logv_mad60`, `adv63`, `car_m{5,20,60}`, `z_m{5,20,60}`. No `sigma_on` / `sigma_id` (they need blinded opens; NA-11 rebuilds them through the lock).
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 72,935 rows = test sessions 2026-01-02 .. 2026-07-31 × 503 members. Ids without Data/prices (40) have no test-period closes, so their close-based features become NaN once their windows need test sessions; volume baselines are NaN from a test-period true split onward.
- **Availability:** nothing dated t or later (tests/test_panel_sealing.py checks the kinds against the registry).
- **sha256:** `defac179748234968820440ade3d23d615760317ce7fcef8f6f8797cab5d2f90`

### `work/panel/companies.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S5)
- **Schema:** `symbol_id`, `company_id`, `n_classes` int64, `ticker`, `name`, `cik`, `grouping` (cik | name), `group_key`, `price_symbol`, `status` (mapping), `adj_source`, `sector` string, `first_member_session`, `last_member_session` date32
- **Key:** `symbol_id`
- **Rows / coverage:** 565 symbols → 562 companies (GOOGL/GOOG, FOXA/FOX, NWSA/NWS grouped by issuer name).
- **Availability:** `static`; `first/last_member_session` summarize the membership file and are descriptive only.
- **sha256:** `5271bd2f20c906e649918e8d0ffbbbe64fd25256ec134a72c7aba9e600927a95`

### `work/panel/tiers_monthly.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S5, `newsaction.panel.tiers`)
- **Schema:** `month` string (applied month YYYY-MM), `ranking_session` date32, `company_id`, `rep_symbol_id` int64, `member_at_ranking` bool, `raw_close` double (on the traded level: ATOM raw × `mapping.level_factor`), `close_source` (atom_raw | reconstructed | stale_public), `shares_mn` double (the count used), `shares_source` (ciq | ciq_unchecked | yahoo_ciq_rejected | yahoo_ciq_missing | missing), `ciq_shares_mn` double, `ciq_period_end` date32, `yahoo_shares_mn` double, `yahoo_obs_date` date32, `cap_usd`, `adv63_usd`, `cap_rank_value`, `rank`, `dv_rank` double, `fallback_dv` bool, `tier`, `dv_tier` string, `tier_source` (ranked | joiner_threshold | no_data)
- **Key:** `(month, company_id)`
- **Rows / coverage:** 18,557 rows; 37 months 2023-07 .. 2026-07; exactly 100 Top-100 and 150 Mid ranked companies per month. Shares: CIQ cross-checked against Yahoo (> 1.5× apart or CIQ missing → Yahoo; 325 + 499 company-months), DV fallback 54 company-months. Ranking sessions in the test period use reconstructed raw closes (validated on 2025-H2: 100% tier agreement); for those months `raw_close`, `cap_usd`, `cap_rank_value` and `adv63_usd` are NaN (only ranks and tiers are kept) — PREREG §15.
- **Availability:** `t_minus_1` for every session of `month` (ranking session = last session of the previous month).
- **sha256:** `d660d7b808926ba483032658273b5c0a2a178cf426087cc2f83bdc5a05ec0c7b`

### `work/panel/qc_flags.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S2, `adjust.qc_flags`)
- **Schema:** `session` date32, `symbol_id` int64, `ticker`, `rule` (tr_diff_gt_50bp, abs_r_on_gt_25pct), `reason`, `atom_actions` string, `r_cc`, `r_cc_atom_total`, `diff_bp`, `r_on`, `r_id`, `dlog_f`, `dlog_f_next` double
- **Key:** `(session, symbol_id)`
- **Rows / coverage:** 228 public symbol-days 2022-01-04 .. 2025-12-31 (any symbol, member or not). Values are never altered by a flag.
- **Availability:** `post` (same-day QC).
- **sha256:** `f7d119c29740e7f92ad2cd1494f59bf8b1594a4f4fb2a47b1489f8f3504fbbec`

### `work/panel/mapping.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S2, `newsaction.panel.mapping`)
- **Schema:** `symbol_id`, `n_obs` int64, `atom_ticker`, `price_symbol`, `candidate_source`, `status` (mapped | no_candidate | failed_corr | conflict), `adj_source` string, `corr_pearson`, `corr_spearman`, `level_n`, `level_rho`, `level_iqr`, `level_factor` double (raw price-level check, `adjust.raw_level_check`: HON 2.0, all others 1), `volume_basis_days` int64 (ATOM raw-volume days restored to the traded share basis, `adjust.volume_basis_check`: ORLY, NOW, TPL 20 each, all others 0)
- **Key:** `symbol_id`
- **Rows / coverage:** 565 ids: 525 mapped (Spearman ≥ 0.99 on ≥ 120 non-event days, public period only), 40 without any Data/prices candidate.
- **Availability:** `static`
- **sha256:** `1e96f421e0029e3466917a7e1b7b748a68477f919c692023129f32fca35973fb`

## NA-02 — news: timing, member mapping, cleaning, embeddings, novelty

Producer for all files: `newsaction.news.build` (NA-02), one stage per process:
`uv run python -m newsaction.news.build --stage prepare | embed | articles | coverage`. Inputs: `Data/news_2023…2026.parquet`
(fingerprinted; the `body` column is never read) and the registered NA-01 files `snapshot/{symbols,symbol_tickers,
members_by_session}.parquet` and `panel/companies.parquet`. Configs: `configs/news.yaml` (constants, ticker aliases),
`configs/patterns.yaml` (13F / Form-4 / detector regexes), `configs/sources.yaml` (domain classes). No price or return
is read by the build; the ≤ 2025 audits (`newsaction.news.audit`, `scripts/na02_report.py`) write only to `artifacts/NA-02/`.
Instants are UTC; session dates are XNYS-local.

### `work/news/articles_stage1.parquet`
- **Producer:** `newsaction.news.build --stage prepare` (S1–S5, S9)
- **Inputs:** Data/news (light columns for every row; title, snippet, summary only for member and market rows), NA-01 snapshot + companies
- **Schema:** the vendor columns of PRD S1 except `summary` (`id`, `ticker`, `date` int64 unix s, `domain`, `non_news`, `parsing_allowed` bool with nulls, `sentiment_direction`, `sentiment_intensity`, `tag_type`, `tag_type2`, `tag_{scheduled,forward_looking,primary_source,quantified,rumor}` bool, `tag_source`, `event_id`, `event_age_days` int64) + `ts_pub_utc` timestamp[us, UTC], `precision` string, `t_avail` timestamp[ns, UTC], `session_w0`, `session_w2` date32, `symbol_id`, `company_id` int64, `title`, `snippet` string, `summary_present` bool, `junk_tag`, `is_13f`, `is_form4`, `third_party_ok`, `after_fact`, `premarket_talk` bool, `title_clean`, `snippet_clean`, `source_class_domain`, `source_class` string
- **Key:** `id` unique
- **Rows / coverage:** 2,906,710 member articles (t_avail 2023-07-01 … 2026-07-31; company is an S&P 500 member at `session_w2`); sorted by (t_avail, id). Intermediate of NA-02 (input of the `embed` and `articles` stages); later chunks read `articles_clean`.
- **Availability:** as `articles_clean` (no near-duplicate or novelty columns yet).
- **sha256:** `4be969b2103d963cb174140681f3926ba9c2f5b4b40748ace4b440a7520f4637`

### `work/news/articles_clean.parquet`
- **Producer:** `newsaction.news.build --stage articles` (S12; S7 dedupe, S8 novelty)
- **Inputs:** `work/news/articles_stage1.parquet`, `work/news/embeddings_ts.parquet`
- **Schema:** `id`, `company_id`, `symbol_id` (int64; for share-class aliases PARAA / BF-A / LEN-B the member class's id), `ticker_raw` (vendor `EXCH:SYM`), `ts_pub_utc`, `precision` (date_only | hour | minute | exact, PREREG §2.2), `t_avail` (§2.3), `session_w0` (date32, null if t_avail is after 09:15 ET and up to the close), `session_w2`, `domain`, `source_class` (domain class, press_wire_primary when `tag_primary_source`), `source_class_domain` (domain only), `title`, `snippet` (raw), `title_clean`, `snippet_clean` (scrubbed, PREREG §6.3–6.4: no after-the-fact / price-path or pre-market sentences, no share-price levels), `summary_present`, flags `non_news`, `junk_tag`, `is_13f`, `is_form4`, `after_fact`, `premarket_talk`, `has_clean_text`, `non_english_hint` (bool), `third_party_ok` (`parsing_allowed` True, or None while `configs/frozen.yaml` `news.parsing_allowed_none` is `allow`: operator decision A, PREREG §15; never False), `parsing_allowed` (bool, nullable), vendor fields `sentiment_direction`, `sentiment_intensity`, `tag_type`, `tag_type2`, the five `tag_*` flags, `tag_source`, `event_id`, `event_age_days`; `dup_group` (string: id of the group's representative), `dup_count`, `dup_count_w0`, `dup_count_w2` (double, NaN outside the usable set), `is_representative` (bool), `novelty` (double, NaN outside the usable set), `keep` (bool)
- **Key:** `id` unique; sorted by (t_avail, id)
- **Rows / coverage:** 2,906,710 member articles of 536 companies, t_avail 2023-07-01 … 2026-07-31. Usable (passes the §6.2 filters and has clean text): 1,669,437; `keep` (usable and near-duplicate representative): 1,494,138.
- **Availability:** per column in `configs/availability.yaml`. Article columns are `w0`: a row may enter a D0 state of session s only if `session_w0 == s` and a D2 state only if `session_w2 == s` (`pit.assert_visible(t_avail ≤ decision instant)`). `dup_group`, `is_representative` and `novelty` look only backwards (deleting later articles changes none of them; tests/test_news_novelty.py). `dup_count` includes later duplicates (`post`); `dup_count_w0` / `dup_count_w2` count the representative's own window (`w0` / `w2`). Vendor labels and the flags built from them (`source_class`, `summary_present`, `non_news`, `junk_tag`, `keep`, `third_party_ok`, `parsing_allowed`, sentiment, tags, `event_*`) are `selection_only` (CLAUDE.md A6). Contains 2026 articles (text and timestamps only; never joined to a return before unblinding).
- **sha256:** `22b6c616e3cd69b0f6da7337f6416ae52890abebd6e067ff2d2032a85a8af5ba`

### `work/news/embeddings_ts.parquet`
- **Producer:** `newsaction.news.build --stage embed` (S6, `newsaction.news.embed`; written with pyarrow, no pandas metadata, registered with `io.register_file`)
- **Inputs:** `work/news/articles_stage1.parquet` (`id`, `title_clean`, `snippet_clean`)
- **Schema:** `id` large_string, `text_sha` large_string (first 16 hex of sha256 of the embedded text), `embedding` fixed_size_list<float16>[384]
- **Key:** `id` unique (same order as `articles_stage1`)
- **Rows / coverage:** 2,906,710 = every member article (so every `keep` id has exactly one row). Model `BAAI/bge-small-en-v1.5` @ `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, sentence-transformers 6.2.0 / torch 2.14.1 on MPS, computed in float16, `normalize_embeddings=True`; text = title_clean + ". " + snippet_clean (non-empty parts). L2 norms 0.99944 … 1.00056. 1,289 s (2,255 texts/s).
- **Availability:** `w0` per article (a function of the article's own scrubbed text). Read with `embed.read_embeddings()` (hash-checked).
- **sha256:** `9581be35725beeda88d5f6bfe5c048ff8e227ffcc7c216cf0a1d462b05da067e`

### `work/news/coverage_member_month.parquet`
- **Producer:** `newsaction.news.build --stage coverage` (S11, `newsaction.news.coverage`)
- **Inputs:** `work/news/articles_clean.parquet`, `snapshot/members_by_session.parquet`, `panel/companies.parquet`
- **Schema:** `month` string (YYYY-MM), `company_id` int64, `member_sessions` int64, `n_mapped`, `n_clean` (passes §6.2 before deduplication), `n_keep`, `n_keep_w0` int64, `covered` bool (`n_keep ≥ 1`, PREREG §3.4)
- **Key:** `(month, company_id)`
- **Rows / coverage:** 18,555 member-months, 2023-07 … 2026-07, 556 companies; covered 91.4% (2023-H2 61%, 2024 95%, 2025 99%, 2026 98%). Articles are counted by the month of `session_w2`.
- **Availability:** a month's count is complete at the month's last close; `covered` is a sample-definition flag (uncovered member-months are missing, never "no news").
- **sha256:** `4402ca34f94db2e7d57037e927bc4cb77af77b220a1730d413a58ac08d5ab093`

### `work/news/market_articles.parquet`
- **Producer:** `newsaction.news.build --stage prepare` (S14, PREREG A3.5)
- **Inputs:** Data/news rows with ticker `^GSPC`, `^VIX` or `DX-Y.NYB`
- **Schema:** `id`, `ticker_raw`, `ts_pub_utc`, `precision`, `t_avail`, `session_w0`, `session_w2`, `domain`, `source_class_domain`, `title`, `snippet`, `title_clean`, `snippet_clean`, `summary_present`, `non_news`, `junk_tag`, `is_13f`, `after_fact`, `premarket_talk`, `third_party_ok`
- **Key:** `id` unique; sorted by (t_avail, id)
- **Rows / coverage:** 31,506 cleaned market-index articles (^GSPC 12,179, ^VIX 11,081, DX-Y.NYB 8,246), t_avail 2023-09-01 … 2026-07-31; no company mapping; non_news / junk-tag / 13F rows dropped; `third_party_ok` 100% (89.8% before decision A allowed `parsing_allowed` None).
- **Availability:** as `articles_clean` (article columns `w0`, vendor flags `selection_only`).
- **sha256:** `6eaf66a87d6f66e10acd93e04d7b5a90f96942476c13d6571caef770ca17b2e9`

## NA-03 — material labels, importance filters, events

Producer for all files: `newsaction.events.build` (NA-03), one stage per process:
`uv run python -m newsaction.events.build --stage labels | counts | fit | scores | compare | events | project`.
Configuration: `configs/events.yaml` (PREREG §6.6–6.9, A1.2 constants) and the `filter:` section of
`configs/frozen.yaml` (written by `compare`). Only `labels` reads returns (`panel_public`, sessions ≤ 2025-12-31,
asserted); `learned` and `select` read the labels; the `scores`, `events` and `project` stages read articles,
frozen models, counts and t−1 tiers only. No module in `newsaction.events` imports `panel.targets` or the lock
(tests/test_events_no_test_outcomes.py). Every stage reproduces its sha256 on a rerun.

### `work/events/labels_public.parquet`
- **Producer:** `newsaction.events.build --stage labels` (`events.labels`, S1)
- **Inputs:** `work/panel/panel_public.parquet` (representative member rows), `work/news/coverage_member_month.parquet`
- **Schema:** `session` date32, `company_id`, `symbol_id` int64, `split`, `month`, `tier` string, `embargo`, `purged` bool, `horizon_end` date32 (t+5), `z_on`, `z_cc`, `z_vol`, `ar_cc`, `sigma_cc`, `car6_z` (panel), `car_delayed_z` = (car6_z·σ_cc·√6 − AR_cc,t)/(σ_cc·√5) double, `label_ok` bool, `material_on`, `material_car`, `material_vol`, `material`, `delayed` boolean (NA when not `label_ok`)
- **Key:** `(company_id, session)` unique
- **Rows / coverage:** 186,002 covered member company-days: train 122,734 (120,005 labelled), val-A 31,694 (29,215), val-B 31,574 (29,114); sessions 2024-07-01 … 2025-12-31. Purge: the last 5 sessions of each split (`purged`, label NA); `embargo` marks the first 5 sessions of val-A / val-B.
- **Availability:** `post` (labels look at returns t … t+5; never a model input). Val-B rows exist for later chunks; NA-03 computes no val-B statistic from them.
- **sha256:** `6bb810887292c9cb60da50a104c622733658c2229daea0de0a5a64230c589220`

### `work/events/window_counts.parquet`
- **Producer:** `newsaction.events.build --stage counts` (`events.attention`)
- **Inputs:** `work/news/articles_clean.parquet` (company, sessions, keep, novelty), `work/snapshot/members_by_session.parquet`, `work/panel/companies.parquet`
- **Schema:** `session` date32, `company_id` int64; per window w ∈ {w0, w2}: `n_articles_w` (usable articles incl. near-duplicates), `n_stories_w` (representatives), `n_dup_w` int64, `attention_mean_w` (mean n_articles_w over the company's member sessions among the previous 60; ≥ 20 needed), `attention_ratio_w` = n_articles_w / max(mean, 1/60) double
- **Key:** `(session, company_id)` unique
- **Rows / coverage:** 448,505 member company-sessions 2023-01-03 … 2026-07-31, 562 companies.
- **Availability:** counts `w0` / `w2` of the session; `attention_mean_*` `t_minus_1`. Articles only.
- **sha256:** `10ac21439c009c04270f3623feeda4350029eaa2b9941076af3b6ef6a85c96c7`

### `work/events/models/f5_logreg.model.json`
- **Producer:** `newsaction.events.build --stage fit` (`events.learned`, S3)
- **Inputs:** kept W0 articles of labelled covered member-days in the fit window; `work/news/embeddings_ts.parquet`
- **Schema:** JSON {mean, scale, coef (384 each), intercept}: p = σ(((x − mean)/scale)·coef + intercept) on the bge-small embedding
- **Key:** n/a
- **Rows / coverage:** one model (C = 0.1, the best of 4 grid points on the tune window)
- **Availability:** frozen; fit labels end ≤ 2025-03-31 (see the meta file). Selection score only (`f5` is `selection_only`).
- **sha256:** `2d7a11134e4110bbb30baf2767e4875b91686976ae7704e00a20fa24fb80353c`

### `work/events/models/f5_logreg.meta.json`
- **Producer:** `newsaction.events.build --stage fit`
- **Inputs:** as the model
- **Schema:** JSON {fit_range {start, end, min_session, max_session, max_horizon_end, ticker_days, material_ticker_days}, tune_range {…}, fit_articles, tune_articles, label, tuning_metric, seed, embedding, events_config_sha256, filter, model_file, features, params, grid [{params, tune recall}], sha256 {model file}}
- **Key:** n/a
- **Rows / coverage:** fit 89,253 ticker-days / 359,302 articles (sessions 2024-07-01 … 2025-03-24, horizons ≤ 2025-03-31); tune 28,272 / 172,145 (2025-04-01 … 2025-06-23, horizons ≤ 2025-06-30)
- **Availability:** provenance record
- **sha256:** `69f509f1c7bccef63a2fa2ef36436b6ef177ad7e3463651c886feca17e0e9bc0`

### `work/events/models/f6_lgbm.model.txt`
- **Producer:** `newsaction.events.build --stage fit` (`events.learned`, S3)
- **Inputs:** as F5, plus `work/events/window_counts.parquet` (W0 attention ratio)
- **Schema:** LightGBM 4.7 booster (text, `model_to_string`), binary objective, deterministic, seed 2026
- **Key:** n/a
- **Rows / coverage:** one model (15 leaves, min_child_samples 400, 200 rounds; best of 8 grid points)
- **Availability:** frozen; selection score only (`f6_*` are `selection_only`: vendor features).
- **sha256:** `b9973a7c07439dd7bbfdfd49e27ffb2a349b40a412b4affc5b7dec5a6c3c7db5`

### `work/events/models/f6_lgbm.prep.json`
- **Producer:** `newsaction.events.build --stage fit`
- **Inputs:** fit-window articles
- **Schema:** JSON {features (27, in order), vocab {tag_type, sentiment_intensity, source_class}, sentiment_scale, pca {mean (384), components (16×384)}}
- **Key:** n/a
- **Rows / coverage:** PCA fit on the 359,302 fit-window article embeddings
- **Availability:** frozen with the booster
- **sha256:** `c3e70f5481761de641d4f8e347756f375e1d9447c04e2201f8d687b277d30e87`

### `work/events/models/f6_lgbm.meta.json`
- **Producer:** `newsaction.events.build --stage fit`
- **Inputs:** as the model
- **Schema:** as the F5 meta, with `prep_file`, `categorical`, `pca` and sha256 of both F6 files
- **Key:** n/a
- **Rows / coverage:** as F5
- **Availability:** provenance record
- **sha256:** `d11e9b50781b6f7967fbb0777abe8614b3d06bd6e19977ce557f7029a0d8995f`

### `work/events/article_scores.parquet`
- **Producer:** `newsaction.events.build --stage scores` (`events.scores`, S2)
- **Inputs:** `work/news/articles_clean.parquet` (kept rows), `work/news/embeddings_ts.parquet`, `work/events/window_counts.parquet`, the frozen F5/F6 files
- **Schema:** `id` string, `company_id` int64, `t_avail` timestamp[ns, UTC], `session_w0`, `session_w2` date32, `f0`–`f3` (0/1 rule scores), `f4` (novelty), `f5`, `f6_w0`, `f6_w2` (NaN outside the window) double
- **Key:** `id` unique
- **Rows / coverage:** 1,494,138 kept articles (all periods; 1,035,098 in a W0 window), sessions 2023-07-03 … 2026-07-31
- **Availability:** article scores are known at the article's t_avail; all are `selection_only` except `f4` (novelty, `w0`).
- **sha256:** `c4fe428b5fc34cd320ea42c6c4e6e93810f08dcc0861fc5a04b66b3491f62e37`

### `work/events/ticker_days.parquet`
- **Producer:** `newsaction.events.build --stage scores` (`events.scores`, S2)
- **Inputs:** `work/events/article_scores.parquet`
- **Schema:** `window` (W0 | W2), `company_id` int64, `session` date32, `n_kept`, `f0`–`f6` (max over the window's kept articles), `n_f1`, `n_f2`, `n_f3` (articles passing the rule), `split` string, `tie_u` double (sha256 tie-breaker, seed 2026)
- **Key:** `(window, company_id, session)` unique
- **Rows / coverage:** W0 219,749 and W2 249,252 company-sessions with ≥ 1 kept article, 2023-07-03 … 2026-07-31
- **Availability:** `selection_only` (scores and counts); `tie_u` `static`. No return.
- **sha256:** `96f1cd8b791b47df6dfc2a3f26ff896ac7b2020f25b6f16f722059e37abbbb31`

### `work/events/events_d0.parquet`
- **Producer:** `newsaction.events.build --stage events` (`events.aggregate`, S5; written with pyarrow, registered with `io.register_file`)
- **Inputs:** `work/events/{ticker_days,article_scores,window_counts}.parquet`, `work/news/articles_clean.parquet` (text and descriptive fields of kept articles), `work/panel/tiers_monthly.parquet` (t−1 tier, representative class), `configs/frozen.yaml` `filter:`
- **Schema:** `event_id` ("W0:{company_id}:{session}"), `window`, `decision_point` string, `company_id` int64, `session` date32, `n_list_w0` (1–6), `n_ok_w0`, `n_not_third_party_w0`, `n_dropped_cap_w0`, `news_tokens_w0` (≤ 600, ModernBERT-large @ 45bb4654), `n_non_english_w0` int64, `filter_score_w0` double, `n_articles_w0`, `n_stories_w0`, `n_dup_w0` int64, `attention_mean_w0`, `attention_ratio_w0` double, `month`, `tier` string, `symbol_id` int64, `split` string, `embargo` bool, `clean_1`, `clean_2`, `clean_5`, `clean_10`, `clean_20` boolean (NA when the window runs past 2026-07-31), `news_w0` list<struct{id, rank int32, score double, t_avail timestamp[us, UTC], precision, source_class, source_class_domain string, non_english_hint bool, novelty, dup_count double, title, snippet string, title_truncated, snippet_truncated bool}> (no pandas metadata: `pd.read_parquet` gives arrays of dicts)
- **Key:** `event_id` unique (= `(company_id, session)`)
- **Rows / coverage:** 55,485 events 2024-01-02 … 2026-07-31, 530 companies: robustness 2,894, train 22,936, val-A 9,079, val-B 6,149, test 14,427. 3 selected ticker-days (train) have no third-party-OK article and no event (7,385 before decision A: robustness 2,205, train 5,180).
- **Availability:** `w0` for the news and count columns (registry suffix `_w0`); `filter_score_w0`, `n_ok_w0`, `n_not_third_party_w0` `selection_only`; `clean_*` `post` (look forward; sample flags). No price, return or target is read; test-period rows come from articles only.
- **sha256:** `ee7d43876d89253bb545a143b74363250f3451ad909cc789986f9664de3de6e5`

### `work/events/events_d2.parquet`
- **Producer:** as `events_d0` (window W2)
- **Inputs:** as `events_d0`
- **Schema:** as `events_d0` with the `_w2` suffix (`event_id` "W2:{company_id}:{session}")
- **Key:** `event_id` unique
- **Rows / coverage:** 71,540 events 2024-01-02 … 2026-07-31, 531 companies: robustness 3,940, train 29,485, val-A 11,252, val-B 7,912, test 18,951; 3 selected ticker-days (train) without a third-party-OK article (9,258 before decision A).
- **Availability:** `w2` (D2 decision point); otherwise as `events_d0`.
- **sha256:** `7098949a700855d724bf1d1e732310bc705e67b9dfdc048c7fb1edd23b76035b`

## NA-04 — states: context, masked text, decision-model states

Producer for all files: `newsaction.states.build` (NA-04), one stage per process:
`uv run python -m newsaction.states.build --stage context | mask | states | report`. Configuration:
`configs/{codebook_v1,questions_v1,aliases,macro_calendar,states}.yaml`. No stage reads the sealed directory
or calls the lock; the D2 reaction comes from `panel.reactions.build_reactions(period="public")`, which
refuses test rows. Test-period rows exist only for Call A (t−1 context and articles). Every stage reproduces
its sha256 on a rerun.

### `work/states/context_company.parquet`
- **Producer:** `newsaction.states.build --stage context` (S2; `states.context.company_context`, `eps_revision`, `earnings_flags`)
- **Inputs:** `work/events/events_{d0,d2}.parquet` (keys), `work/panel/panel_public.parquet` and `panel_test_inputs.parquet` (t−1 columns; public `adj_close` shifted one session), `work/snapshot/estimates_fy1.parquet`, `work/market/earnings_dates.parquet`, `work/panel/companies.parquet`, `work/snapshot/symbol_tickers.parquet`
- **Schema:** `session` date32, `symbol_id`, `company_id` int64, `ctx_sigma_cc_pct`, `ctx_z_m{5,20,60}_pct`, `ctx_ret_m{5,20,60}` double, `sector` string, `beta_m`, `sigma_cc`, `z_m{5,20,60}`, `logv_mad60`, `ctx_eps_fy1_now`, `ctx_eps_fy1_before`, `ctx_eps_revision` double, `ctx_earnings_w0`, `ctx_earnings_w2` bool
- **Key:** `(session, symbol_id)` unique (the representative symbol of each D0 / D2 event)
- **Rows / coverage:** 71,540 rows = every D0 ∪ D2 event key, 2024-01-02 … 2026-07-31. `ctx_ret_m*` are NaN for test sessions (E0 states are built for val samples only).
- **Availability:** `t_minus_1` (earnings flags `w0` / `w2`): data through close(prev s) only; percentiles compare with the symbol's previous 252 values (tests/test_states_pit.py planted shocks). Contains test-period t−1 values: never summarized before the freeze.
- **sha256:** `7d30be5ca46d2ed47ab545ef0823e72f6ed6a0b7f068ea883c11827f70e201b4`

### `work/states/context_market.parquet`
- **Producer:** `newsaction.states.build --stage context` (S2; `states.context.market_context`, `states.macro`)
- **Inputs:** `work/market/market_prices.parquet` (SPY, ^VIX, DX-Y.NYB, CL=F), `work/market/fred_daily.parquet` (DGS10, BAMLH0A0HYM2), `work/market/cpi_vintages.parquet`, `configs/macro_calendar.yaml`
- **Schema:** `session` date32; per series n ∈ {stock_market, vix, ten_year_yield, high_yield_spread, dollar, oil}: `mkt_{n}_chg`, `mkt_{n}_z`, `mkt_{n}_pct` double; `mkt_vix_level_pct`, `mkt_stock_market_sigma_same`, `mkt_spy_ret_m{5,20,60}` double; `macro_cpi_today`, `macro_fomc_today` bool
- **Key:** `session` unique
- **Rows / coverage:** 647 sessions 2024-01-02 … 2026-07-31
- **Availability:** `t_minus_1` (the change of prev(s), of t−2 for the HY OAS; σ and percentiles from the 252 changes before it); macro flags `static`. `mkt_stock_market_sigma_same` is SPY's σ through prev(s), used only to score SPY's move of s in Call B. Contains test-period t−1 values: never summarized before the freeze.
- **sha256:** `58665927ba1a128e9a90de750d73996377496433ce96e17362897a032338d740`

### `work/states/reaction_d2.parquet`
- **Producer:** `newsaction.states.build --stage context` (S5; `panel.reactions.build_reactions(period="public", point="D2")`, `states.context.reaction_d2`)
- **Inputs:** `work/panel/panel_public.parquet`, `work/market/market_prices.parquet` (SPY history)
- **Schema:** `session` date32, `symbol_id` int64, `g_d2`, `g_d2_lvl`, `react_r_cc`, `react_r_spy_cc`, `react_z_vol`, `react_g_pct`, `react_spy_z`, `react_spy_pct`, `react_volume_multiple` double
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 48,649 rows = the D2 event keys of train, val-A and val-B (sessions ≤ 2025-12-31; no test row)
- **Availability:** `d2_reaction` (the reaction of s; E4 and σ histories through t−1). Never a Call A input.
- **sha256:** `32e339109435119426657ac7ebbcc7c2aab832971fc6925d7a0fddb0d31c7346`

### `work/states/articles_masked.parquet`
- **Producer:** `newsaction.states.build --stage mask` (S3; `states.mask.Masker`, spaCy `en_core_web_sm` 3.8.0)
- **Inputs:** the news lists of `work/events/events_{d0,d2}.parquet` (title_clean / snippet_clean as capped by NA-03), `work/news/market_articles.parquet` (A3.5 selection), `work/panel/companies.parquet`, `work/snapshot/symbol_tickers.parquet`, `configs/{aliases,news,patterns}.yaml`
- **Schema:** `id` string, `kind` (company | market), `company_id` int64 (−1 for market articles), `title_masked`, `snippet_masked` string, `n_names`, `n_tickers`, `n_dates`, `n_persons` int64 (replacements made; price-talk sentences, quotes and price-level rewrites are not counted)
- **Key:** `id` unique
- **Rows / coverage:** 358,358 rows: 355,191 event articles, 3,167 market articles (the A3.5 selection leaves out excluded articles: explainers, TradingView reposts, revision 3; non-English articles, revision 4). Excluded event articles are still masked here; `news_items` leaves them out of the states. Since revision 4 the price step also drops share-price levels, the direction after the number, moves as nouns and price targets in any notation (the second pass drops any sentence that still holds a cents-precision share price); since revision 5 it drops every sentence with a price move of any security or an index or commodity level, before NER and in the final pass (`Masker.has_market_move`), and masks the fifth verification's date forms. 4,964 event articles and 80 market articles have an empty masked title and snippet
- **Availability:** `w0` per article (a function of the article's own text; `title_masked` / `snippet_masked` registered `w0`). Third-party OK articles only (NA-03 lists); contains 2026 article text, no return.
- **sha256:** `b7919e511d05bf2e77bedd43b5142dab0a9c1da35d03cc50d71c64cb9a510002`

### `work/states/person_surnames.parquet`
- **Producer:** `newsaction.states.build --stage mask` (S3; `states.mask.Masker.corpus_surnames`)
- **Inputs:** the spaCy PERSON entities of every event and market article text
- **Schema:** `surname` string
- **Key:** `surname` unique (sorted)
- **Rows / coverage:** 2,046 surnames: last words of multi-word PERSON names in English texts seen ≥ 3 times, capitalized ASCII, 3+ letters, not an ordinary lower-case word of the event texts, not a word of any company alias, and not tagged inside an organization, product or place name at least half as often
- **Availability:** a lexicon of the article texts (`w0`); the masker masks each surname wherever it appears capitalized (PREREG §6.3 person names, also used alone). The determinism test reuses it instead of re-running NER on the corpus.
- **sha256:** `4db73db8f1eeb4809a7271b4d92138aa427504bf689a79179b663d6cc0a50d4b`

### `work/states/company_cjk_names.parquet`
- **Producer:** `newsaction.states.build --stage mask` (S3; `states.mask.cjk_company_names`)
- **Inputs:** the event articles of `work/events/events_{d0,d2}.parquet` (title_clean / snippet_clean as capped by NA-03), the company tickers (`work/panel/companies.parquet`, `work/snapshot/symbol_tickers.parquet`, `configs/{aliases,news}.yaml`)
- **Schema:** `company_id` int64, `name` string
- **Key:** `(company_id, name)` unique
- **Rows / coverage:** 735 Chinese, Japanese and Korean names of 306 companies: the CJK words right before the company's own ticker in parentheses ("迪爾股份（紐交所：DE）"), leading verbs / function words and corporate suffixes removed (a Korean name seen twice)
- **Availability:** a lexicon of the article texts (`w0`); the masker replaces each name in the company's own texts (PREREG §6.3). The masker and the determinism test derive the same list from the event articles; this file records it.
- **sha256:** `650e9d00d805ec6be59de91d3b6cd4ff3d3723d1161292a9f2c261c69fef54e9`

### State files (schema shared by the ten files below)
- **Producer:** `newsaction.states.build --stage states` (S5; `states.build.build_event_states`, `build_market_states`)
- **Inputs:** the four files above, `work/events/events_{d0,d2}.parquet`, `work/news/articles_clean.parquet` (`id`, `third_party_ok`, `domain`, `t_avail` and the raw `title`, `snippet` for the exclusion rules), `work/news/market_articles.parquet`, `configs/{codebook_v1,questions_v1,macro_calendar,states}.yaml`
- **Excluded articles (revisions 3 and 4):** move explainers (a raw title "Why … today" with a move word or a percent between, e.g. "Why … Stock Is Up Today", "Why Micron Technology Rallied Today"; or StockStory's raw snippet "What Happened? Shares of / A number of …"), TradingView reposts (domain) and non-English articles (`states.build.non_english` on the raw title + snippet) are in no state, in any window or call (`configs/states.yaml` `news_exclusion`, `states.build.excluded_ids`; PREREG §15 NA-04 rows 6 and 8). **Running market stories (revision 6):** live blogs and running market reports (live formats, live entries after the open, a market close on the weekday of the session, running intraday wording, market wraps stamped the morning of the session; `configs/states.yaml` `news_exclusion.running_story`, `states.build.running_story_ids`; PREREG §15 NA-04 row 10) are in no W0 state (`callA_d0_E3` and the D0 samples), because their vendor stamp precedes their text; W2 states keep them (W2 ends at the close). The NA-03 lists are not refilled; an event whose every listed article is one gets no state (`events_all_excluded` in artifacts/NA-04/build_states.json; the running stories are `articles_excluded_running`).
- **Schema (all ten files):** `event_id` string, `company_id` int64 (−1 for market states), `session` date32, `split`, `window` (W0 | W2), `call` (A | B | M), `encoding` (E0–E4) string, `masked` bool, `state_json` string (canonical JSON: sorted keys, compact separators, UTF-8), `state_sha256` string (sha256 of the UTF-8 `state_json`), `n_tokens_state`, `n_tokens_with_questions` int64 (ModernBERT-large @ 45bb4654, no special tokens; + the call's core questions as canonical JSON), `n_articles` int64, `third_party_ok_all` bool
- **Key:** `event_id` unique per file (`M:{session}` for market states)
- **Rows / coverage:** `callA_d0_E3.parquet` 54,332; `callA_d2_E3.parquet` 70,709; `callB_d2_E3.parquet` 48,197; `market_E3.parquet` 621; `samples/callA_d0_E0.parquet` 3,000; `samples/callA_d0_E1.parquet` 3,000; `samples/callA_d0_E2.parquet` 3,000; `samples/callA_d0_E3.parquet` 3,000; `samples/callA_d0_E4.parquet` 3,000; `samples/unmasked.parquet` 1,000
- **Availability:** a state is an input at its decision point: Call A D0 (`window` W0) at 09:15 ET of `session`; Call A D2 and Call B (W2) after close(s); `pit.check_inputs` validated every block (`states.build.validate_spec`). Call B rows exist for train, val-A and val-B only. Test-period rows (Call A only) contain t−1 context words: never summarized before the freeze.

### `work/states/callA_d0_E3.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** Call A on D0 (W0 news), E3, masked: every D0 event with text after masking and at least one article that is not excluded (robustness, train, val-A, val-B, test; 1,020 events have every listed article excluded and 133 have no text after masking (before decision A: 1,061, of which 190 from revision 6's running-story rule, and 133), artifacts/NA-04/build_states.json)
- **Schema / key / availability:** as "State files" above
- **Rows:** 54,332
- **sha256:** `1b16491f2eb3aaeb34e6b472fb49158a4b486c1b6c434cf9d84cd80e4a9e9608`

### `work/states/callA_d2_E3.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** Call A on D2 (W2 news, PREREG A3.1), E3, masked: every D2 event with text after masking and an article that is not excluded (all splits; 714 have every listed article excluded, 117 have no text)
- **Schema / key / availability:** as "State files" above
- **Rows:** 70,709
- **sha256:** `0b6db63ecb195ed834ddb061d525b124dd935197e4e54f08d3940387f127412b`

### `work/states/callB_d2_E3.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** Call B on D2 (W2 news + reaction_so_far), E3, masked: the D2 events of train, val-A and val-B with text (383 have every listed article excluded, 69 have no text); same articles as callA_d2_E3
- **Schema / key / availability:** as "State files" above
- **Rows:** 48,197
- **sha256:** `6625fd984ee8f464cc609d8eb290c604a21ec458446e8c73542339542bffcb26`

### `work/states/market_E3.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** A3.5 (optional) market states: one per session with third-party-OK market-index articles, E3, masked; since revision 5 the index moves and levels are masked out (the states' own target), and a session whose every article lost its text has no state (1 session, `build_states.json` `market_E3.sessions_without_text`)
- **Schema / key / availability:** as "State files" above
- **Rows:** 621
- **sha256:** `3c80930c22dbeef70e1961805b894f248f3f01889f34697cf0447da5c7a05a10`

### `work/states/samples/callA_d0_E0.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** NA-07 encoding sample: 1,500 val-A + 1,500 val-B D0 events (tier × month, seed 2026), Call A, E0, masked
- **Schema / key / availability:** as "State files" above
- **Rows:** 3,000
- **sha256:** `006611486d2840a8cc1a8d8d1903b6c1164c1118531b734e0157acfeae1dfbbf`

### `work/states/samples/callA_d0_E1.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** NA-07 encoding sample: 1,500 val-A + 1,500 val-B D0 events (tier × month, seed 2026), Call A, E1, masked
- **Schema / key / availability:** as "State files" above
- **Rows:** 3,000
- **sha256:** `c9be74d4ceab9f5f671d66409e06dda38a2b81e4fb1ccab3d6fa14b1c9583c25`

### `work/states/samples/callA_d0_E2.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** NA-07 encoding sample: 1,500 val-A + 1,500 val-B D0 events (tier × month, seed 2026), Call A, E2, masked
- **Schema / key / availability:** as "State files" above
- **Rows:** 3,000
- **sha256:** `3e58abe34dabbbcddfd093210bb91e7d3b76eb832b346d30c4f9d42691b6e63e`

### `work/states/samples/callA_d0_E3.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** NA-07 encoding sample: 1,500 val-A + 1,500 val-B D0 events (tier × month, seed 2026), Call A, E3, masked
- **Schema / key / availability:** as "State files" above
- **Rows:** 3,000
- **sha256:** `0d1279ecd2817384ebb8713b6092a7c802812042b8ead0d4e46182ebac1622a0`

### `work/states/samples/callA_d0_E4.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** NA-07 encoding sample: 1,500 val-A + 1,500 val-B D0 events (tier × month, seed 2026), Call A, E4, masked
- **Schema / key / availability:** as "State files" above
- **Rows:** 3,000
- **sha256:** `0d5c8d1de7e8fd0f9ce8e29285dcd0a4ceee9a73e657e344beceba510daf8554`

### `work/states/samples/unmasked.parquet`
- **Producer:** `newsaction.states.build --stage states` (S5)
- **Contents:** NA-06 probe: unmasked twin of 1,000 val-A D0 events (tier × month, seed 2026), Call A, E3; the masked twin is the same event_id in callA_d0_E3
- **Schema / key / availability:** as "State files" above
- **Rows:** 1,000
- **sha256:** `48136755fb0db7ac198881ff02e0219953ed53c056e1f2c1f75918c0ffebb51c`

## NA-05 — decision-model client, cache, catalog, canary, pilot

Producer: `newsaction.dm` (NA-05). `newsaction.dm.client.DecisionClient` is the only path to a decision model
(OpenRouter Decisions API or local Laya; CLAUDE.md C12). The pilot runs one stage per process:
`uv run python -m newsaction.dm.pilot --stage catalog | billing | calibrate | measure | smoke | laya | report`;
every request is cached, so a rerun spends nothing, and `report` rebuilds every number from the cache with an
offline client. The committed files below live under `artifacts/NA-05/` and are registered in
`work/MANIFEST.json` with `io.register_artifact` (so `make manifest` re-hashes them).

### `cache/decisions.sqlite` (gitignored; no fixed hash)
- **Producer:** `newsaction.dm.cache.DecisionCache`, written only by the client (every chunk that calls a decision model)
- **Schema:** table `responses`: `key` TEXT PK, `model`, `state_sha256`, `questions_sha256`, `provider_json`, `params_json`, `repeat_idx` INT, `request_json` (the body as sent, without the key), `response_json` (the raw response text), `model_build`, `provider`, `input_tokens` INT, `output_tokens` INT, `cost` REAL, `cost_source` (`usage` = the response's usage.cost, `computed` = catalog price × tokens, `local`), `latency_ms` REAL, `created_at`, `chunk`, `tag`, `meta_json` (the state's provenance: source, file, event_id, session, split, call, masked, third_party_ok_all, probe), `valid` INT (strict parse), `problems_json`. Table `attempts`: `id`, `key`, `model`, `attempt`, `status` (NULL for a transport error), `error`, `latency_ms`, `headers_json` (rate-limit headers), `concurrency`, `created_at`, `chunk`, `tag`.
- **Key:** `responses.key` = sha256 of the canonical JSON of {model, state, questions (ordered: [[id, [type, instructions, criteria]], …]), provider, params, repeat_idx}; local models add their checkpoint settings (revision, subfolder, max_len, head_max_len, device, fp32) to `params`; the session id is not part of the key
- **Rows / coverage (end of NA-05):** 2,227 responses with `chunk = NA-05` (1,949 API, all HTTP 200, 278 local Laya), 2,014 API attempts (1,949 × 200, 61 × 400, 3 × 429, 1 × 502). Sessions of the sent states: 1,976 train-split states (2024-07-01 … 2025-06-30) and 251 synthetic ones. **NA-06 (2026-10-26):** 65,289 responses with `chunk = NA-06` (63,889 API, all HTTP 200 and valid; 1,400 local Laya), 65,004 API attempts (63,889 × 200, 916 × 429, 198 × 502, 1 × 503; 12 requests to openai/gpt-6-luna-decisions refused for good: "OpenAI refused to answer question justified_move"). Every NA-06 state is a val-A state after the embargo (2025-07-09 … 2025-09-30), masked except the 5,940 `unmasked_twin` probe rows (`artifacts/NA-06/cache_audit.json`). GAC4: NA-06's recorded spend $3.526621699 equals Σ `responses.cost` of its rows (difference −2.7e-14) **NA-07 (2026-10-27):** 32,016 responses with `chunk = NA-07` (all API, HTTP 200 and valid), 33,300 attempts (32,016 × 200, 1,284 × 429 retried; one request needed a second pass). States: 23,256 val-A (S1 18,000, S3 1,260 numeracy probes, S4 3,756 Call A D2), 9,000 val-B (S2), all after the embargo (`artifacts/NA-07/cache_audit.json`). NA-07's recorded spend $1.240485312 equals Σ `responses.cost` of its rows.
- **Availability:** n/a (decision-model outputs). GAC4: Σ `responses.cost` where `chunk = X` equals chunk X's recorded spend in `ledgers/spend.jsonl` (NA-05: $0.103922341, difference 9.7e-17)
- **Note:** gitignored like `work/`; the verifier and later chunks need this file next to the branch (copy it with `work/` when merging). `valid` / `problems_json` are the parser's verdict when the row was written; the client re-parses every hit with the current parser, so since the renormalization rule (2026-10-26) a stored row can say invalid for an answer that now parses as valid and `renormalized`. A row is written once and never edited

### `artifacts/NA-05/catalog.json`
- **Producer:** `newsaction.dm.pilot --stage catalog` (`dm.catalog.snapshot`; GET /api/v1/models?output_modalities=decisions, no spend), fetched 2026-10-26T17:47:58Z
- **Schema:** {`fetched_at`, `url`, `params`, `sha256` (sha256 of the canonical JSON of `models`, recomputable from the file), `raw_sha256` (the same over the raw model list as fetched), `n_models`, `total_count`, `models`: [{`id`, `name`, `canonical_slug`, `created`, `created_iso`, `context_length`, `pricing` (USD per token, strings), `architecture`, `top_provider`, `per_request_limits`}]} sorted by id
- **Key:** `models[].id`
- **Rows / coverage:** 30 models (3 aliases, 4 `:free`); `sha256` 205464ea1b0c36a22420ace1dd7a4a94d8eac2b42daa2a1321bfe7b064a58d4d
- **Availability:** n/a (vendor catalog; prices feed `dm.costmodel`)
- **sha256:** `4a5a565a7fb46e6897ac0d2f72902c5b44257b2cfa5686cf9104f8dbed622630`

### `artifacts/NA-05/canary_v1.jsonl`
- **Producer:** `newsaction.dm.canary.build_canary` / `write_canary` (S7)
- **Inputs:** `work/states/callA_d0_E3.parquet`, `work/states/callB_d2_E3.parquet` (train split), `configs/{questions_v1,codebook_v1}.yaml`
- **Schema:** one canonical-JSON object per line: `canary_id` (C01…C50), `version` (canary_v1), `kind` (train | synthetic), `group` (train_A | train_B | synthetic_A | numeracy), `call` (A | B), `label`, `move_z` (numeracy: the signed reaction in typical daily moves), `n_tokens_state`, `info` (StateInfo provenance), `state`, `questions` (the call's core battery, request shape), `state_sha256`, `questions_sha256`
- **Key:** `canary_id`
- **Rows / coverage:** 50: 20 train Call A D0 + 10 train Call B D2 (smallest u = sha256("2026:canary:<event_id>") per size tier, proportional), 6 synthetic Call A, 14 synthetic Call B (one positive news item × reaction z ∈ ±{0.3, 0.7, 1.5, 2.5, 4, 6, 9}); train sessions 2024-08-13 … 2025-06-23
- **Availability:** train-period states (inputs at their decision points) and synthetic states; masked; third-party OK. `load_canary` refuses a line whose hashes do not match
- **sha256:** `783aa96cd3d2e9595435d7d5c6df0a66a6fba778da292f461998945b923714ad`

### `artifacts/NA-05/canary_baseline.parquet`
- **Producer:** `newsaction.dm.pilot --stage report` (`dm.canary.probability_rows`; registered with `io.register_artifact`)
- **Inputs:** `cache/decisions.sqlite` (the canary calls, repeat 0), `artifacts/NA-05/canary_v1.jsonl`
- **Schema:** `model`, `model_build`, `canary_id`, `question`, `option` string, `p` double (renormalized for an answer whose rounded probabilities summed to 1 within one rounding step), `renormalized` bool (that answer was rescaled; `schemas.RENORM_TOL`), `key` string (the cache key of the call), `repeat_idx` int64 (0)
- **Key:** (`model`, `canary_id`, `question`, `option`)
- **Rows / coverage:** 6,846 rows: the 5 pilot API models and the 2 local Laya checkpoints × 50 canary states × every option (978 per model); 19 rows (Jev 1.14: C19 tone, C31 tone, C49 justified_move) are `renormalized`
- **Availability:** n/a (decision-model outputs; NA-11 S5 compares a fresh canary run with it via `dm.canary.compare`)
- **sha256:** `301443ee829cf1e8ab18398a68a491e5b2972d0e1c642cee504fdda3bca9176b`

### `artifacts/NA-05/pilot.json`
- **Producer:** `newsaction.dm.pilot --stage report` (last run `--offline`, 2026-10-26: recomputed from the cache after the renormalization rule, no network call)
- **Inputs:** `cache/decisions.sqlite`, `artifacts/NA-05/{catalog.json,canary_v1.jsonl,key_usage.json}`, `artifacts/NA-03/call_projection.csv`, `work/states/{callA_d0_E3,callA_d2_E3,callB_d2_E3,market_E3}.parquet` (state sizes only), `configs/dm.yaml`
- **Schema:** {`version`, `chunk`, `generated_at`, `git_sha`, `catalog`, `pilot_models`, `local_models`, `stop_per_question_billing`, `items` (the ten PRD S8 answers, `1_billing_basis` … `10_builds`), `per_model` (each pilot model's measurements), `smoke` (every other catalog model), `laya`, `eligibility`, `costmodel`, `na11_projection`, `na06_stage1_projection`, `spend`, `canary`, `peak_rss_mb`}
- **Key:** n/a (one record)
- **Availability:** n/a (no return of any period is read)
- **sha256:** `535cc14619e6bfa0565c74f024035b30dcf9a7540dcb1428407df300649827d4`

### `artifacts/NA-05/key_usage.json`
- **Producer:** `newsaction.dm.pilot` (`record_key_usage`; GET /api/v1/key, no spend)
- **Schema:** list of {`label`, `ts`, `usage`, `usage_daily`, `limit`, `limit_remaining`, `is_free_tier` (the key's own accounting, USD), `ledger_chunk_usd` (NA-05 spend in `ledgers/spend.jsonl` at that time)}
- **Key:** list order
- **Availability:** n/a. The key's usage lags a call by up to about a minute; at the report its change since the first snapshot equals the ledger's to 1e-16
- **sha256:** `17a255df0311e8662ddf3339ef04bcf6b546d692efe27f13e78884302ef26a1d`

## NA-06 — zero-shot decision-model tournament and contamination probes

Producer: `newsaction.tournament` (NA-06), one stage per process:
`uv run python -m newsaction.tournament.run --stage samples | dryrun1 | stage1 | select | dryrun2 | stage2 | validity | report | handoff`.
Configuration: `configs/tournament.yaml` (PREREG §8.2–8.3, §11.1–11.2, A2.5; checked against PREREG by
`tests/test_tournament_{config,screens}.py`). Every request goes through `dm.client.DecisionClient("NA-06")` and is
cached in `cache/decisions.sqlite` (`chunk = NA-06`), so `report` rebuilds every number below from the cache with an
offline client. All states are val-A D0 / D2 states after the embargo (sessions 2025-07-09 … 2025-09-30); every target
comes from `work/panel/panel_public.parquet` (val-A rows, purged by split). No val-B or test state was sent and no
val-B or test outcome was read.

### `work/dm/tournament/samples.parquet`
- **Producer:** `newsaction.tournament.run --stage samples` (`tournament.sample`, `tournament.probes`, `tournament.edits`)
- **Inputs:** `work/events/events_d0.parquet` (keys, tier, month, embargo), `work/states/{callA_d0_E3,callB_d2_E3}.parquet`, `work/states/samples/unmasked.parquet` (event ids), `work/panel/panel_public.parquet` (val-A member rows: sector, tier, rank), `work/panel/companies.parquet` (names), `configs/tournament.yaml`
- **Schema:** `event_id`, `company_id` int64, `symbol_id` int64, `session` date32, `month`, `tier` string; flags `stage1`, `identification`, `reading_validity`, `shuffled`, `stage2`, `unmasked_twin`, `counterfactual` bool; `b_event_id` (the D2 twin with a Call B state), `shuffle_donor` (probe e's donor event), `company_options` (JSON [[key, company_id, name], …]), `company_true_key`, `company_draw` (sector_tier | sector_rank_fill), `month_options` (JSON [[key, YYYY-MM, label], …]), `month_true_key` string
- **Key:** `event_id` unique
- **Rows / coverage:** 3,061 rows: the 3,000 stage-2 events (stage 1 700, identification 400, reading validity 500, probe sample 1,000 = NA-04's unmasked twins) and 61 counterfactual-only events; val-A sessions 2025-07-09 … 2025-09-30 (embargo excluded)
- **Availability:** design file (no outcome); the probe options use t−1 tier and sector of the session
- **sha256:** `be0ea9112d9f746119da269b90157620c869bedf1ab32e106feda87f5f5934f3`

### `work/dm/tournament/counterfactual.parquet`
- **Producer:** `newsaction.tournament.run --stage samples` (`tournament.edits.select`)
- **Inputs:** `work/states/callA_d0_E3.parquet` (val-A pool states), the stage-2 sample
- **Schema:** `event_id`, `in_stage2` bool, `polarity` int64 (+1 positive original outcome, −1 negative), `families`, `edits_json` (list of {item, field, from, to, family}), `n_edits` int64, `state_sha256` (the original state), `edited_state_json` (canonical JSON), `edited_state_sha256` string
- **Key:** `event_id` unique
- **Rows / coverage:** 200 edited val-A Call A states (139 in stage 2) of the 398 editable among the 8,376 pool states
- **Availability:** the state's own availability (09:15 ET of `session`); a synthetic edit of masked text, never sent outside the probe. Contains masked NewsWitch text (gitignored)
- **sha256:** `818e9874cb56bff781c09d9f99e159892636428d6b321425e9b1c6df1919f56c`

### `work/dm/tournament/stage1.parquet`
- **Producer:** `newsaction.tournament.run --stage report` (offline)
- **Inputs:** `cache/decisions.sqlite`, the samples, `work/states/callA_d0_E3.parquet`
- **Schema:** one row per (model, event): `model`, `event_id`, `session` date32, `symbol_id` int64, `call`, `tag` (the request's stage tag), `probe`, `ok` (a cached answer exists), `valid` (strict parse), `key` (cache key), `paid_chunk`, `paid_tag` (the chunk and tag that paid for the answer), `model_build`, `provider`, `input_tokens`, `cost`, `latency_ms`, the PREREG §7 quantities `n_hat`, `abs_n_hat`, `m`, `surprise`, `tone`, `n_renormalized`, and `p_fall`, `p_flat`, `p_rise` (Q1 collapsed to 3 classes)
- **Key:** (`model`, `event_id`)
- **Rows / coverage:** 14,700 rows: 21 eligible models × 700 stage-1 events
- **Availability:** decision-model outputs at 09:15 ET of `session` (Call A on W0 news, masked, E3)
- **sha256:** `a734ea98dfb250f855d255b79ad9c7c822546266865acfbebd96f6fcd4d5e6b5`

### `work/dm/tournament/stage2.parquet`
- **Producer:** `newsaction.tournament.run --stage report` (offline)
- **Inputs:** as stage 1, plus `work/states/callB_d2_E3.parquet`
- **Schema:** as `stage1.parquet` plus `part` (A | B) and the Call B quantities `j`, `w`, `c`
- **Key:** (`model`, `part`, `event_id`)
- **Rows / coverage:** 36,000 rows: 6 stage-2 models × (3,000 Call A + 3,000 Call B)
- **Availability:** Call A at 09:15 ET; Call B after close(`session`) (D2 reaction)
- **sha256:** `3b6909ed5b543ece72e326a12c2d7f570242499fd534519d7443d3e8eadf0f5b`

### `work/dm/tournament/probes.parquet`
- **Producer:** `newsaction.tournament.run --stage report` (offline)
- **Inputs:** as stage 2, plus `work/states/samples/unmasked.parquet`, `work/dm/tournament/counterfactual.parquet`
- **Schema:** the `stage1.parquet` columns plus `probe` (company | month | counterfactual_edit | counterfactual_orig | unmasked | masked | shuffled | reading_validity), `true_key`, `argmax_key`, `p_true`, `correct` (a, b), `polarity` (c), `donor_event_id` (e), and the extended-battery labels and quantities of probe f (`label_*`, `plabel_*`, `h`, `p_no_material_effect`, `u_unc`, `p_mixed`)
- **Key:** (`model`, `probe`, `event_id`)
- **Rows / coverage:** 25,700 (per stage-2 model: company 400, month 400, counterfactual_edit 200, counterfactual_orig 200, masked 1,000, unmasked 1,000, shuffled 1,000; reading_validity 500 for liquid/d1-ultra) rows
- **Availability:** decision-model outputs on probe states (masked, edited, unmasked, shuffled) of val-A events
- **sha256:** `bee48db10f93344829dc048f19bae7a273b6193c86ba728882159fcc23f5c2e1`

### `artifacts/NA-06/leaderboard.csv`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** every eligible model (21): `model`, `rank1`, `kind`, `price_prompt_usd_per_m`, `billing_basis`; stage 1 `n1`, `ok1`, `valid1`, `q1_valid1`, `invalid_rate1`, `ic1_z_cc` (+ `_t`, `_se`, `_days`), `ic1_e5` (+ …), `cost_per_1000_a`, `latency_p50_ms_1`, `latency_p95_ms_1`, `providers1`, `builds1`; `mcs_pvalue`, `mcs_member`, `stage2`; stage 2 `ic2_a_z_cc`, `ic2_a_e5`, `ic2_j_y2`, `ic2_b_z_cc` (each + `_t`, `_se`, `_days`), `ece2_a_z_cc`, `ece2_a_e5_lvl`, `cost_per_1000_a2`, `cost_per_1000_b2`, `n2_a`, `n2_b`, `invalid_rate2_a`, `invalid_rate2_b`, `failed2_a`, `failed2_b`, `latency_p50_ms`, `latency_p95_ms`; probes `company_id_acc`, `company_id_p_true`, `company_id_n`, `month_id_acc`, `month_id_p_true`, `month_id_n`, `flip_rate`, `flip_n`, `flip_pairs_valid`, `edit_mean_shift`, `ic_masked`, `ic_unmasked`, `unmasked_minus_masked`, `ic_shuffled` (each IC + `_t`, `_se`, `_days`); `screen_company_identification`, `screen_counterfactual_flip`, `screen_masked_vs_unmasked`, `screen_shuffled_news`, `screen_all`, `screens_pass`, `contamination_score` (company-ID accuracy − 0.25)
- **Key:** `model`
- **Rows / coverage:** 21 rows (19 API models + 2 local Laya); stage-2 and probe columns for the 6 stage-2 models
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `a7d1abd833dc6c99a10a1f56f9d02b55fd3d0429d10c948d52ab6a0e6158bf89`

### `artifacts/NA-06/fig3_data.csv`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** `model`, `kind`, `cost_per_1000_decisions` (stage-1 realized USD per 1,000 Call A requests; local 0), `ic` (stage-1 mean daily IC vs z_cc), `ci_low`, `ci_high` (± 1.96 Newey–West se), `mcs_member`, `stage2`, `screen` (pass | fail | not_tested)
- **Key:** `model`
- **Rows / coverage:** 21 rows (Figure 3 data, NA-14)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `df891edfeadd2843c3a4e062774b85b2e0e8eadf5ee3bd683d8be8e984a4e3ef`

### `artifacts/NA-06/probe_details.csv`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** `model`, `probe` (company_identification | month_identification | counterfactual_flip | masked_vs_unmasked | shuffled_news), `value` (accuracy, flip rate, unmasked − masked mean daily IC, shuffled mean daily IC), `t` (Newey–West t where one applies), `n` (answers, pairs or days), `passed` (PREREG §8.3; empty for the report-only month probe)
- **Key:** (`model`, `probe`)
- **Rows / coverage:** 30 rows (6 stage-2 models × 5 probes); `tests/test_tournament_screens.py` recomputes `passed` with the PREREG thresholds
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `9806e9e2b7d558b37af80689ed8f5923e7a803cd73b592644d61c08e9a5c458b`

### `artifacts/NA-06/reading_validity.csv`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** `model` (the decision model), `comparison` (event_type | quantified | scheduled | credibility | event_type_vs_raw_tag), `label` (the model's argmax label, credibility as rumor / not_rumor), `reference` (vendor tag mapped by `configs/tournament.yaml`, the earnings-in-W0 flag, `tag_rumor`; the raw `tag_type` for the last table), `n`
- **Key:** (`comparison`, `label`, `reference`)
- **Rows / coverage:** probe f: liquid/d1-ultra on the 500 reading-validity events (PREREG A2.5, report only)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `455933fa0f38ae38939b6b3e1c2bebc18190049cf15d27c59a06cae87056f718`

### `artifacts/NA-06/stage1_daily_ic.csv`
- **Producer:** `newsaction.tournament.run --stage select`
- **Schema:** `model`, `session`, `ic` (daily Spearman IC of N̂ with z_cc,t), `n` (events with an N̂ that day)
- **Key:** (`model`, `session`)
- **Rows / coverage:** 21 models × 57 sessions; the MCS input (`python -m newsaction.tournament.mcs --seed N` reruns it)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `9e9f920944c6ae5ffb1f094fb95192762fef88de5ec3435b66b654f2700b9152`

### `artifacts/NA-06/mcs.json`
- **Producer:** `newsaction.tournament.run --stage select` (`tournament.mcs`)
- **Schema:** {`stage1`: {models, pvalues, steps (elimination order with step and MCS p-values), included, statistic, alpha, reps, block, seed, n_days}, `robustness_other_statistic`: the same with T_max, `no_daily_ic`, `n_common_days`, `stage2_models`}
- **Key:** n/a
- **Rows / coverage:** one record; T_R, α 0.10, block 5, 10,000 reps, seed 2026, 57 sessions
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `336fa0e5a92fee971f40125685eb9c311fd98fd5a8fe604f906475a57af818ca`

### `artifacts/NA-06/dry_run.json`
- **Producer:** `newsaction.tournament.run --stage dryrun1 | stage1 | dryrun2 | stage2 | validity`
- **Schema:** list of {`label` (stage1 | stage2 | validity), `ts`, `n_requests`, `n_unique`, `n_cached`, `n_send`, `tokens`, `usd`, `by_model` {calls, tokens, usd}, `left_usd`, …}: every projection, recorded before the stage sent anything
- **Key:** list order
- **Rows / coverage:** 5 records (stage1 ×2, stage2 ×2, validity)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `28e3fef7a5cd644a43c16c9553cd05dbb389f20937ed18d89d611f32f435b5ed`

### `artifacts/NA-06/spend.json`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** {`ledger` (NA-06 and total USD, by chunk, cap), `reconcile` (ledger − Σ cache cost), `n_rows`, `actual_by_stage`, `calls_by_stage`, `by_model` {usd, calls, cost_ratio = Σ cost / Σ (catalog price × input tokens), cost_ratio_max}, `projection_vs_actual` per stage and model (the first projection of each stage), `projection_total`, `actual_total`, `actual_over_projected_total`}
- **Key:** n/a
- **Rows / coverage:** one record
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `3dc299e32fe0abf173d7ee78124afbe8a04c74714fb233e39e15cca203b5f0f4`

### `artifacts/NA-06/cache_audit.json`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** {`chunk`, `n_rows`, `by_source`, `by_probe`, `min_session`, `max_session`, `allowed`, `violations`, `n_violations`, `shuffle_donors_in_val_a_after_embargo`, `ok`}
- **Key:** n/a
- **Rows / coverage:** AC1: 65,289 NA-06 cache rows, all val-A states 2025-07-09 … 2025-09-30
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `4308ad6de68ff5755929d9f2b1929fdf28a194b2be24ca92edf711d785be3972`

### `artifacts/NA-06/summary.json`
- **Producer:** `newsaction.tournament.run --stage report`
- **Schema:** {`stage1_survivors`, `stage1_survivors_other_statistic`, `stage2_models`, `stage2_survivors_passing`, `rank_vs_contamination` (Spearman of stage-1 / stage-2 IC with the contamination score; exact permutation p), `reading_validity` (model, n, agreement per comparison), `spend` (as spend.json), `audit_ok`, `leaderboard_sha256`}
- **Key:** n/a
- **Rows / coverage:** one record (deterministic: a rerun of the report reproduces it)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `288620cc7c15a134ce33834979581ee7b41d18775c1c8fb49291816e91a5765a`

### `artifacts/NA-06/counterfactual_edits.jsonl`
- **Producer:** `newsaction.tournament.run --stage samples` (`tournament.edits`)
- **Schema:** one canonical-JSON object per line: `event_id`, `in_stage2`, `polarity`, `families`, `edits` [{item, field, from, to, family}], `state_sha256`, `edited_state_sha256` (no article text; the states are in `work/dm/tournament/counterfactual.parquet`)
- **Key:** `event_id`
- **Rows / coverage:** 200 pairs
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; no val-B or test value)
- **sha256:** `5267d8d750e812c96278e427000aba8921ce35ca46a54bdc515333e7e3b285f2`

## NA-07 — encoding ("numbers as words") and anchoring study

Producer: `newsaction.encoding` (NA-07), one stage per process:
`uv run python -m newsaction.encoding.run --stage samples | dryrun | search | anchoring | select | confirm | numeracy | report`.
Configuration: `configs/encoding.yaml` (PREREG §8.4, §6.11, §11.1, §11.4; PRD NA-07; checked against the PREREG and PRD
text by `tests/test_encoding_config.py`). Every request goes through `dm.client.DecisionClient("NA-07")` and is cached in
`cache/decisions.sqlite` (`chunk = NA-07`); the E3 val-A search states and the Call B D2 twins are NA-06's cached answers.
`report` rebuilds every number below from the cache with an offline client. Models: liquid/d1-ultra, respan/span-02,
nace-ai/drex-v2.0 (screen-failing, PREREG §15 operator row of 2026-10-27): every value is model-specific. S1, S3 and S4
states are val-A after the embargo (2025-07-09 … 2025-09-30); S2 states are val-B after the embargo (2025-10-08 …
2025-12-31). Targets: z_cc,t from `work/panel/panel_public.parquet` (same-session reaction). No test state was sent and
no test outcome was read.

### `work/dm/encoding/samples.parquet`
- **Producer:** `newsaction.encoding.run --stage samples`
- **Inputs:** `work/states/samples/callA_d0_E{0..4}.parquet` (event ids), `work/events/events_d0.parquet` (keys, tier, month, embargo), `work/states/{callA_d2_E3,callB_d2_E3}.parquet` (twin checks), `configs/encoding.yaml`
- **Schema:** `event_id`, `split` (val_a | val_b), `company_id` int64, `symbol_id` int64, `session` date32, `month`, `tier`, `d2_event_id` (the "W2:" twin), `anchoring` bool (val-A twins with both D2 states), `numeracy` bool (the 30 numeracy events, tier × month, seed 2026)
- **Key:** `event_id` unique
- **Rows / coverage:** 3,000 rows: NA-04's 1,500 val-A + 1,500 val-B D0 sample events (embargo excluded); 1,500 anchoring twins; 30 numeracy events
- **Availability:** design file (no outcome)
- **sha256:** `8082520badb2caf967fb4475abd1b3a76fa4af82d201041f3fb0e628b3c7f732`

### `work/dm/encoding/search.parquet`
- **Producer:** `newsaction.encoding.run --stage report` (offline)
- **Inputs:** `cache/decisions.sqlite`, the samples, `work/states/samples/callA_d0_E{0..4}.parquet`
- **Schema:** one row per (model, encoding, event): `model`, `event_id`, `session` date32, `call`, `tag`, `probe`, `ok`, `valid`, `key`, `paid_chunk`, `paid_tag` (NA-06 for the cached E3 answers), `model_build`, `provider`, `input_tokens`, `cost`, `latency_ms`, the PREREG §7 quantities `n_hat`, `abs_n_hat`, `m`, `surprise`, `tone`, `n_renormalized`, `p_fall`, `p_flat`, `p_rise`, `encoding`, `split` (no target column)
- **Key:** (`model`, `encoding`, `event_id`)
- **Rows / coverage:** 22,500 rows: 3 models × 5 encodings × 1,500 val-A events (S1)
- **Availability:** decision-model outputs at 09:15 ET of `session` (Call A on W0 news, masked)
- **sha256:** `6c1d353280661c8a8718237dfc392d63f22781887244e68e9a304b424eee8825`

### `work/dm/encoding/confirm.parquet`
- **Producer:** `newsaction.encoding.run --stage report` (offline)
- **Inputs:** as `search.parquet` (val-B rows of the samples)
- **Schema:** as `search.parquet`
- **Key:** (`model`, `encoding`, `event_id`)
- **Rows / coverage:** 9,000 rows: 3 models × {E1, E3} × 1,500 val-B events (S2, written because the val-A best E1 is not E3)
- **Availability:** decision-model outputs at 09:15 ET of `session` (val-B; NA-07's confirmation and NA-11's selection only, CLAUDE.md B9)
- **sha256:** `a02322e5c82db0aa9ad59d6267ba345958fbe916da61f5a3c8de21d5b83a10d7`

### `work/dm/encoding/numeracy.parquet`
- **Producer:** `newsaction.encoding.run --stage report` (offline)
- **Inputs:** `cache/decisions.sqlite`, `work/states/callB_d2_E3.parquet` (the 30 numeracy states), `configs/codebook_v1.yaml`
- **Schema:** `model`, `event_id` (the D2 state whose non-reaction blocks were used), `session` date32, `encoding`, `direction` (rise | fall), `magnitude_idx` int64 (0–6), `z` (signed synthetic move), `reaction_text` (the synthetic move phrase), `ok`, `key`, `paid_chunk`, `p_wrong_direction`, `p_too_small`, `p_much_too_small`, `p_about_right`, `p_too_large`, `p_much_too_large`, `p_large`, `p_small` (Q5 probabilities)
- **Key:** (`model`, `encoding`, `event_id`, `direction`, `magnitude_idx`)
- **Rows / coverage:** 1,260 rows: 3 models × 30 states × 2 directions × 7 magnitudes, in E3
- **Availability:** outcome-free probe (synthetic `reaction_so_far`; no realized reaction shown or read)
- **sha256:** `c3f76ef1d60bb79bb35e9fcbf70b213fa166351c5c3f63cd821a5edf40f10d1f`

### `work/dm/encoding/anchoring.parquet`
- **Producer:** `newsaction.encoding.run --stage report` (offline)
- **Inputs:** `cache/decisions.sqlite`, `work/states/{callA_d2_E3,callB_d2_E3}.parquet` (the 1,500 val-A twins)
- **Schema:** one row per (model, D2 event): `event_id`, `session` date32, `ok_a`, `valid_a`, `n_hat_a`, `paid_chunk_a`, `cost_a` (Call A on W2 news), `ok_b`, `valid_b`, `n_hat_b`, `paid_chunk_b`, `cost_b`, `j`, `w`, `c` (Call B), `model` (G is not stored)
- **Key:** (`model`, `event_id`)
- **Rows / coverage:** 4,500 rows (3 models × 1,500 events; 9,000 requests)
- **Availability:** Call A at close(`session`) on W2 news; Call B after close(`session`) with the D2 reaction
- **sha256:** `beb50a9d99f0ce4c273fc9b66fe946772025af4782186114c20b677d92a90f19`

### `artifacts/NA-07/encoding_ic.csv`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** `split`, `model` (or `pooled`), `encoding`, `n_events`, `n_answered`, `n_paid_na07`, `ic` (mean daily IC of N̂ vs z_cc,t; for `pooled` the mean over models), `t`, `nw_se` (Newey–West, 5 lags), `boot_se`, `ci_low`, `ci_high` (stationary bootstrap, block 5, 10,000 reps, seed 2026, 95% percentile), `n_days`, `rank` (within model; for `pooled` the mean rank), `best` (the val-A rule's encoding), `chosen` (`frozen.yaml` `encoding.chosen`)
- **Key:** (`split`, `model`, `encoding`)
- **Rows / coverage:** 26 rows: val-A 3 models × 5 encodings, val-B 3 models × {E1, E3}, 5 pooled val-A rows
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; val-B only in the S2 check; no test value)
- **sha256:** `04c2c0d40a8a9c9a14bb658830ea9c81652f6109048d80737fba2d6297806140`

### `artifacts/NA-07/encoding_daily_ic.csv`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** `split`, `model`, `encoding`, `session`, `ic` (daily Spearman of N̂ with z_cc,t), `n` (events with both values)
- **Key:** (`split`, `model`, `encoding`, `session`)
- **Rows / coverage:** the daily series behind `encoding_ic.csv` (59 val-A and 59 val-B sessions)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; val-B only in the S2 check; no test value)
- **sha256:** `2b119288a97c0a9c726571feff0779301ca45fdb39f12b6ef7366eb74d214a20`

### `artifacts/NA-07/encoding_check.csv`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** row `scope = rule`: `needed`, `best`, `default`, `chosen` (the encoding the val-B check keeps), `delta`, `se`, `threshold` (−1·SE), `n_days`, `kept_best`; rows `scope = pooled` and per model: `delta` (mean daily IC(best) − IC(E3) on val-B), `t`, `nw_se`, `boot_se`, `ci_low`, `ci_high`, `n_days`
- **Key:** `scope`
- **Rows / coverage:** 5 rows (rule, pooled, 3 models)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; val-B only in the S2 check; no test value)
- **sha256:** `084c20f939dd972b4f4fdcdf8653c3cd68cbcf937657dc86f0aa48e19883ff06`

### `artifacts/NA-07/numeracy.csv`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** `model`, `encoding`, `role` (gate: the encoding the val-B check kept; reference: E3 beside a non-E3 gate), `n_series`, `n_complete`, `n_monotone`, `share_large_non_decreasing`, `share_small_non_increasing`, `share` (monotone series / series), `target` (0.90), `passes`, `leading` (liquid/d1-ultra)
- **Key:** (`model`, `encoding`)
- **Rows / coverage:** 3 rows (E3 gate rows; no reference run since the kept encoding is E3)
- **Availability:** outcome-free probe
- **sha256:** `86af0d6997a91cc4f58db9c112c922d75fd3cbde135ec37a2511992b34a3cc4d`

### `artifacts/NA-07/numeracy_series.csv`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** `model`, `event_id`, `direction`, `complete`, `large_non_decreasing`, `small_non_increasing`, `monotone` bool, `p_large`, `p_small` (JSON lists over the 7 magnitudes, rounded to 6 decimals), `encoding`
- **Key:** (`model`, `encoding`, `event_id`, `direction`)
- **Rows / coverage:** 180 rows (3 models × 30 states × 2 directions)
- **Availability:** outcome-free probe
- **sha256:** `564bd6e4bd47a87dddf2af56e23bd680b39b2c28a525b3e1159169fe6469d674`

### `artifacts/NA-07/anchoring.csv`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** per model: `model`, `n`, `n_sessions`, `slope` (b in N̂_B = a + b·G + c·N̂_A), `slope_se_hc1`, `slope_se_cluster` (by session), `coef_n_hat_a`, `intercept`, `r2`, `corr` (Pearson N̂_A, N̂_B), `spearman`, `slope_without_control`, `present`; row `all`: the largest slope, the smallest corr, `present` (any model), `calls_per_event`; `slope_min` 0.30, `corr_max` 0.70 on every row
- **Key:** `model`
- **Rows / coverage:** 4 rows (3 models + all)
- **Availability:** n/a (decision-model outputs and their evaluation on val-A; val-B only in the S2 check; no test value)
- **sha256:** `db55a940ebcced410ecb8c7472a744ae2dedb823f061c7f9f0c209b368a98214`

### `artifacts/NA-07/spend.json`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** {`ledger` (NA-07, total, by chunk, cap), `reconcile` (ledger − Σ cache cost), `n_rows`, `actual_by_part`, `calls_by_part`, `by_model` (usd, calls, cost_ratio), `projection_vs_actual` (per part: projected, actual, ratio, within_20pct), `projection_total`, `actual_total`, `actual_over_projected_total`, `within_20pct_total`}
- **Key:** n/a
- **Rows / coverage:** one record; NA-07 $1.240485 of $2.00
- **Availability:** n/a
- **sha256:** `6c748331dbe333c3d371b4e31f4bc2e9d561d7a40ef56a7bbd3b20767b2eb7b1`

### `artifacts/NA-07/cache_audit.json`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** {`chunk`, `n_rows_na07`, `na07_rows_by_part`, `na07_rows_by_part_split`, `used_requests_by_part` (every request the report uses, NA-06-paid included: requests, outside, by split), `allowed` (session ranges), `part_split`, `violations`, `n_violations`, `ok`}
- **Key:** n/a
- **Rows / coverage:** AC3: 32,016 NA-07 cache rows and 41,760 used requests, 0 outside their part's split
- **Availability:** n/a
- **sha256:** `0dfe8bf6cedc2dce32049d681db1825d0acf95d5f9aceb6b25a2889bcc13193a`

### `artifacts/NA-07/dry_run.json`
- **Producer:** `newsaction.encoding.run --stage dryrun | search | anchoring | confirm | numeracy`
- **Schema:** list of {`label` (plan_s1, plan_s4, plan_s2_worst, plan_s3_worst; s1, s4, s2, s3 just before the paid calls), `ts`, `n_requests`, `n_unique`, `n_cached`, `n_send`, `tokens`, `usd`, `by_model`, `left_usd`, `credit_remaining`}
- **Key:** (`label`, `ts`)
- **Rows / coverage:** every projection made (worst case $1.4026; the paid parts $1.3748)
- **Availability:** n/a
- **sha256:** `223217d879f03daa4ed07c1fa4c6dcb7befc1f1a5cbac2a4b6f457cef43f1c8d`

### `artifacts/NA-07/key_usage.json`
- **Producer:** `newsaction.encoding.run` (`record_credit`; GET /api/v1/key and /api/v1/credits, no spend)
- **Schema:** list of {`label`, `ts`, `usage`, `usage_daily`, `limit`, `limit_remaining`, `is_free_tier`, `total_credits`, `total_usage`, `credit_remaining`, `ledger_chunk_usd`}
- **Key:** (`label`, `ts`)
- **Rows / coverage:** 10 snapshots from the dry run to the final reconciliation (credit $11.37 → $10.13)
- **Availability:** n/a
- **sha256:** `f40593d7bd7d84830771eff10ae1f4ad4ceae5aa11b2c331dcd7607f0d21aa2d`

### `artifacts/NA-07/selection.json`
- **Producer:** `newsaction.encoding.run --stage select` (offline)
- **Schema:** {`best`, `choice` (best, reason, tied, mean_rank, mean_ic), `ts`}
- **Key:** n/a
- **Rows / coverage:** one record (the val-A rule's result, written before any val-B call)
- **Availability:** n/a
- **sha256:** `e5d7a63ebb3a5e5a144512e9ccaacac941538a8284de5b998b2f8f47d048a800`

### `artifacts/NA-07/summary.json`
- **Producer:** `newsaction.encoding.run --stage report`
- **Schema:** {`models`, `val_a_best`, `val_b_check`, `val_b_kept`, `chosen`, `by_model`, `numeracy`, `anchoring`, `trials_appended` (this run), `trials_na07` (ledger totals by kind), `spend`, `audit_ok`}
- **Key:** n/a
- **Rows / coverage:** one record
- **Availability:** n/a
- **sha256:** `7586758528db865d23a4dc4a8f0da47458df9960cffd28e3519d78b2e5c5840e`

## NA-10 — 30-minute bars (FMP), D1 (10:00) inputs, sealed 2026

Producer: `newsaction.bars` (`fetch`, `derive`; `uv run python -m newsaction.bars.<module>`) and
`newsaction.states.build --stage d1`. Vendor: FMP `/stable/historical-chart/30min` with `extended=true&nonadjusted=true`
(`configs/bars.yaml`; capability and request count in `artifacts/NA-10/capability.json`), every request in
`ledgers/fmp_requests.jsonl`. Bars are start-labelled New York wall time; every bar is located by its slot after
the session's open (`newsaction.calendar`), never by clock time.

### `work/bars30/raw/` (gitignored cache, not an artifact)
- **Producer:** `bars.fmp30.FmpClient` (public windows only: a window that reaches the test period is never cached here)
- **Schema:** one gzip JSON per request, `<sha256 of interval + parameters>.json.gz`: {`version`, `request` (interval, symbol, from, to, switches), `status`, `n` (ledger request number), `fetched_at`, `text` (the vendor's answer)}; no key
- **Availability:** as the bars below. Re-runs of `fetch --part public` read it and send nothing for a cached window.

### `work/bars30/bars_public.parquet`
- **Producer:** `bars.fetch --part public` (`fetch.frame_of` on the cached answers; aliases and exclusions of `configs/bars.yaml` applied)
- **Inputs:** the cached FMP answers; `work/snapshot/prices_raw.parquet` (first EOD day per symbol, for the plan); `work/panel/panel_public.parquet`, `panel_test_inputs.parquet` (member, is_rep: the symbols)
- **Schema:** `symbol_id` int64, `ticker` (FMP ticker asked, dictionary), `session` date32, `bar_start` timestamp[ns, UTC], `slot` int64 (30-minute steps after the open: 0 = the first regular bar, −1 = the bar that ends at the open, −11 … 20 with extended hours), `regular` bool (0 ≤ slot < 13, or < 7 on a half day), `open`, `high`, `low`, `close`, `volume` double (as served: levels before any basis factor, volume regular-hours venues), `request_key` (dictionary), `switches` (dictionary; one value, `extended=true&nonadjusted=true`)
- **Key:** `(symbol_id, bar_start)`
- **Rows / coverage:** 5,698,440 bars of 544 companies' representative classes + SPY, sessions 2023-01-03 (SPY) / 2024-01-02 … 2025-12-31; 3,302,680 regular, 1,300,777 pre-market
- **Availability:** a bar is known at its end (`bar_start` + 30 minutes); the first regular bar of s at 10:00 ET (D1). Not a model input as such (`intraday_public` holds the D1 inputs).
- **sha256:** `d6a92498f46d556265f335d7d43abb02d93825e38b9f5dfac7a38febce6b3790`

### `work/bars30/session_qc.parquet`
- **Producer:** `bars.derive` (`bars.basis.session_qc`)
- **Inputs:** `bars_public.parquet`, `work/snapshot/prices_raw.parquet`, `work/panel/mapping.parquet` (`level_factor`)
- **Schema:** `symbol_id` int64, `session` date32, `n_regular`, `n_expected` int64, `complete` bool, `first_open`, `bar_high`, `bar_low`, `last_close`, `eod_open`, `eod_high`, `eod_low`, `eod_close`, `level_factor`, `phi_open`, `phi_high`, `phi_low`, `phi_close`, `level_prev`, `open_dev_bp` double, `open_ok` bool, `basis` string (as_traded / rescaled / inconsistent / no_eod), `factor` double, `usable` bool
- **Key:** `(symbol_id, session)`
- **Rows / coverage:** 255,488 symbol-sessions with regular bars (public)
- **Availability:** `factor` / `basis` / `usable` use the symbol's previous 5 sessions and the session's own open (known at 10:00); `complete`, `last_close`, `phi_close` are known at the close. QC table, not a model input.
- **sha256:** `2bb1b1a3c65f1657f3f1d6f63c2a8c4169f980dd2b6c33e6e64c20f91fa01dde`

### `work/panel/intraday_public.parquet`
- **Producer:** `bars.derive` (`derive.compute`; `panel.reactions.build_reactions(..., "public", "D1")`; `panel.targets.build_d1_targets(..., "public")`)
- **Inputs:** `bars_public.parquet`, `session_qc.parquet`, `work/panel/panel_public.parquet` (member, is_rep, sector, raw open / close, r_on, r_spy_on, ar_cc, β, σ), `work/snapshot/prices_raw.parquet` (SPY EOD), `work/snapshot/symbols.parquet`
- **Schema:** `session` date32, `symbol_id`, `company_id` int64, `split` string, `member`, `is_rep`, `half_day`, `bars_complete`, `bars_d1` bool; `sigma_on`, `sigma_cc` (NA-01, t−1); `p_open`, `p_close`, `first_open`, `p10`, `v10`, `p1530`, `p_pre` (ATOM's raw level); `r_c10`, `r_o10`, `r_10c`, `r_spy_c10`, `r_spy_o10`, `r_spy_10c`, `r_sec_c10`, `r_sec_o10`, `r_sec_10c`, `r_sec_n10`, `ar_c10`, `ar_o10`, `ar_10c`; `sigma_30`, `sigma_rest`, `logv10_med60`, `logv10_mad60`, `z_vol10`; `g_d1`, `g_d1_lvl`, `car_lvl_10`, `react_d1_r`, `react_d1_r_spy`, `react_d1_z_vol`; `y1`, `ar_10_c0`, `ar_10_c1`, `z_10_c1`, `ar_10_c5`, `z_10_c5`, `fwd_lvl_10_c0`, `fwd_lvl_10_c1`, `fwd_lvl_10_c5`, `fwd_lvl_10_c20` double; `delist_within_c20_d1` bool (definitions: PREREG §15 NA-10 row 2)
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 252,309 panel rows of the 544 symbols with bars, 2024-01-02 … 2025-12-31 (249,950 with P_10:00); G_D1 from 2024-03-28 (σ_30 needs 60 sessions)
- **Availability:** per column in `configs/availability.yaml`: `d1` (P_10:00, the close(prev) → 10:00 and open → 10:00 returns and AR, G_D1, G^lvl, z_vol10, P_pre), `t_minus_1` (σ_30, σ_rest, the volume baseline), `post` (P_15:30, the close, 10:00 → close pieces, `car_lvl_10`, the D1 targets). No test-period row.
- **sha256:** `2c8b3722ba68ed0d728603d963cbbde028abccf7f718e8f2b42ac193ad3f9f2d`

### `work/panel/intraday_spy_public.parquet`
- **Producer:** `bars.derive` (`derive.spy_returns`)
- **Inputs:** SPY's bars in `bars_public.parquet`, its EOD open / close (`work/snapshot/prices_raw.parquet`), `r_spy_on` (`work/panel/panel_public.parquet`)
- **Schema:** `session` date32, `spy_open`, `spy_close`, `r_spy_on`, `spy_p10`, `r_spy_c10`, `r_spy_o10`, `r_spy_10c` double
- **Key:** `session` unique
- **Rows / coverage:** 628 sessions 2023-07-03 … 2025-12-31 (SPY's D1 history for the states)
- **Availability:** `d1` (open, P_10:00, close(prev) → 10:00), `post` (close, 10:00 → close)
- **sha256:** `fb82dd7b75a01ca8d152c5a1d0c841d08e28c50ebb56e0ce489611b29385207f`

### `work/snapshot/sealed/bars30_2026.parquet`
- **Producer:** `bars.fetch --part test` (`fetch.write_test_part` → `lock.write_sealed`; written once, never read in NA-10; one `write` entry in `ledgers/test_access.jsonl`)
- **Schema:** as `bars_public.parquet`
- **Key:** `(symbol_id, bar_start)`
- **Rows / coverage:** 2,060,207 bars (test period); requests and answer counts in the FMP ledger
- **Availability:** BLINDED. Readable only through `newsaction.lock` (`reactions` after the NA-11 freeze; `targets` after unblinding), by `panel.reactions.build_reactions(..., "test", "D1")` and `panel.targets.build_d1_targets(..., "test")` through `bars.derive.test_intraday_panel`.
- **sha256:** `1d08a2447c07f5fc2f0b84e4a11eb0a00e4bd6edc07adfbd616b9ae9bcd37bdd`

### `work/states/reaction_d1.parquet`
- **Producer:** `newsaction.states.build --stage d1` (`states.build.reaction_frame_d1`, `states.context.reaction_d1`)
- **Inputs:** `work/panel/intraday_public.parquet`, `intraday_spy_public.parquet`, `work/events/events_d0.parquet`
- **Schema:** `session` date32, `symbol_id` int64, `g_d1`, `g_d1_lvl`, `car_lvl_10`, `react_d1_r`, `react_d1_r_spy`, `react_d1_z_vol`, `react_d1_g_pct`, `react_d1_spy_z`, `react_d1_spy_pct`, `react_d1_volume_multiple` double
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 38,164 = the D0 event keys of train, val-A and val-B (no test row)
- **Availability:** `d1` (the reaction by 10:00 of s; σ and E4 histories through t−1); `car_lvl_10` `post` (carried along, not rendered). Never a Call A input.
- **sha256:** `4daa36ad248d2f6a9a2490c3a84d4806b899d79813a9d690159c15001b61e6b3`

### `work/states/callB_d1_E3.parquet`
- **Producer:** `newsaction.states.build --stage d1` (`states.build.run_d1`; NA-04's builder, masking and W0 exclusions)
- **Inputs:** as the NA-04 state files, plus `reaction_d1.parquet`
- **Schema / key:** as "State files" (NA-04); `window` W0, `call` B
- **Rows / coverage:** 37,562 D0 events of train, val-A and val-B with text ; 543 have every listed article excluded, 59 no text after masking; 597 states show 'not available' for the move (no G_D1 that session); 1,055 carry fewer articles than their Call A D0 twin
- **Availability:** an input at D1 (10:00 ET of `session`); `pit.check_inputs` validated every block at D1 (`reaction_so_far` reads `d1` columns only). No test-period row before the freeze.
- **sha256:** `500962d70d8caa53c2daed5de6a37fbb5205bad96c81393e39328de0d3b18ea9`

### `artifacts/NA-10/capability.json`
- **Producer:** `newsaction.bars.probe` (7 requests in all; re-runs read the cache)
- **Schema:** {`endpoint`, `vendor_timezone`, `bar_label`, `requests_sent_this_run`, `probe_requests_total`, `probes` [per probe: request, rows, first / last bar, sessions served, completeness, extended bars, open vs EOD], `facts` (window cap in days with per-probe bounds, extended, nonadjusted, v3), `decision` {api, extended, nonadjusted, basis, window_days}, `projection` {windows, by part, requests needed, cap, headroom, stop, scopes}, `fmp_request_cap`, `ledger_requests_remaining`, `corroboration`}
- **Key:** n/a
- **Rows / coverage:** one record
- **Availability:** n/a (vendor capability; no price statistic)
- **sha256:** `6fad2a68e23dc04225295619a0ef4c60bcdcf6b2bc391c69a08357a160349b4c`

### `artifacts/NA-10/summary.json`
- **Producer:** `scripts/na10_report.py`
- **Schema:** {`ledger` (requests by purpose, rows, empty answers, statuses), `capability`, `bars_public_rows`, `bars_test_rows_from_manifest`, `member_sessions` (complete, half days, usable, open within 5 bp, open deviation quantiles, basis counts, exceptions), `intraday_member_rows`, quantiles of `sigma_30`, `sigma_rest`, `g_d1`, `g_d1_lvl`, `y1`, `corr_g_d1_lvl_vs_g_d2_lvl`, `d1_events_train_val`, `spy_sessions`, `states_d1`, `states_d1_tokens`}
- **Key:** n/a
- **Rows / coverage:** one record (public sessions only; the test-period bars only as row counts from the manifest)
- **Availability:** n/a
- **sha256:** `d6f2591f5a9eae5b94458da365b7618d259eb3b34498269282b64f6fec756a95`

### `artifacts/NA-10/build_states_d1.json`
- **Producer:** `newsaction.states.build --stage d1`
- **Schema:** {`rows`, `articles_excluded`, `articles_excluded_non_english`, `articles_excluded_running`, `events_all_excluded`, `events_without_text`, `states_with_dropped_articles`, `articles_dropped`, `texts_cut`, `cap` (state token budget), `sha256` (of `callB_d1_E3.parquet`), `reaction_missing`}
- **Key:** n/a
- **Rows / coverage:** one record
- **Availability:** n/a
- **sha256:** `cd005ed5547593b10949b558aa9225e90f973d520b2ea312c3c959395580edda`

### `artifacts/NA-10/basis_by_symbol.csv`
- **Producer:** `scripts/na10_report.py`
- **Schema:** `symbol_id`, `ticker`, `sessions`, `as_traded`, `rescaled`, `inconsistent`, `factor_min`, `factor_max`, `first_rescaled`, `last_rescaled` (symbols with at least one rescaled or inconsistent public session)
- **Key:** `symbol_id`
- **Rows / coverage:** public sessions only
- **Availability:** n/a (QC)
- **sha256:** `38215a42d85dfb3e50e2971ef9dff7d7b2f835623dddb3eb20d077ec415bb8fb`

### `artifacts/NA-10/member_session_exceptions.csv`
- **Producer:** `scripts/na10_report.py`
- **Schema:** `ticker`, `session`, `n_regular`, `n_expected`, `basis`, `phi_open`, `phi_close`, `level_prev`: the public member-sessions that are not complete or not usable (AC2's listed exceptions)
- **Key:** `(ticker, session)`
- **Rows / coverage:** public sessions only
- **Availability:** n/a (QC)
- **sha256:** `893e6e8e81925d71472f8ce63c97c0e2abdc7ceaee68d48dd3b001f3954b5f92`

## NA-08 — trained decision models: labels, the private Kaggle dataset, predictions

Producer for all files: `newsaction.train.build` (NA-08), one stage per process:
`uv run python -m newsaction.train.build --stage labels | export | notebook | kernels | plan | import | cards`.
Configuration: `configs/training.yaml` (PREREG §9, PRD NA-08). Only `labels` reads returns (`panel_public`,
sessions ≤ 2025-12-31, asserted). No `newsaction.train` module imports `panel.targets` or the lock, and no
module computes a statistic on val-B or test rows (`train.metrics.require_val_a`). Every stage reproduces its
sha256 on a rerun (labels and export were run twice: 8 of 8 files identical).

### `work/kaggle/labels.parquet`
- **Producer:** `newsaction.train.build --stage labels` (`train.labels`, S1)
- **Inputs:** `work/panel/panel_public.parquet` (session, symbol_id, split, e5, z_cc, g_d2, y2), `work/events/events_{d0,d2}.parquet` (event keys, symbol, split, embargo)
- **Schema:** `company_id` int64, `session` date32, `symbol_id` int64, `split` string (train | val_a | val_b), `embargo` bool (first 5 sessions of val-A / val-B), `in_d0`, `in_d2` bool (the key has a D0 / D2 event), `e5`, `z_cc`, `g_d2`, `y2`, `cont_x` (= sign(G)·y2) double, `react_label` (0–8), `mag_label` (0–4), `cont_label` (0 reverse, 1 stall, 2 continue; only for |G| ≥ 0.5) Int8 nullable, `react_horizon_end` (t+4), `cont_horizon_end` (t+5) date32
- **Key:** `(company_id, session)` unique
- **Rows / coverage:** 48,649 event keys (every D0 key is also a D2 key): train 29,485, val-A 11,252, val-B 7,912. Labelled train: react 29,026, mag 29,456, cont 19,115. Bins: |z| in [0, 0.5) [0.5, 1) [1, 2) [2, 3) [3, ∞) (the codebook's move words), react level = 4 + sign(e5)·bin(|e5|), mag level = bin(|z_cc,t|); cont x ≤ −0.5 reverse, x ≥ 0.5 continue, else stall.
- **Availability:** `post` (labels look at returns t … t+5; never a model input). Purged (PREREG §4.1): every label's horizon ends inside its split (asserted); the last train label horizon is 2025-06-30. Local only: never in the Kaggle dataset except as `label_index` of train and val-A rows. Val-B rows are kept for NA-11; NA-08 computes no statistic on them.
- **sha256:** `a0bc7de7ae70efb7023c6c915bc396a1bdccd5204a8481ada1364d32cda3a3dc`

### Kaggle dataset files (schema shared by the four example files below)
- **Producer:** `newsaction.train.build --stage export` (`train.kaggle_export`, S2); uploaded privately to Kaggle as `amirdehkordi98/newsaction-na08-states` (runbook: artifacts/NA-08/REPORT.md).
- **Inputs:** `work/states/{callA_d0_E3, callA_d2_E3, callB_d2_E3}.parquet` (masked E3 states, all `third_party_ok_all`, checked), `work/kaggle/labels.parquet`, `configs/{training, questions_v1}.yaml`, the ModernBERT-large tokenizer @ 45bb4654 (identical ids to Laya's typed-decisions tokenizer on 4,500 sampled states) and `laya.common.build_head` (head lengths)
- **Example:** one (state variant, question) pair. `state_json` is the NA-04 state byte for byte (`variant` full), or a train copy (PREREG §9.1 block dropout, a sha256 draw per state, seed 2026): `no_reaction` (a Call B state without `reaction_so_far`, p = 0.3, asked react; byte-identical to the event's Call A D2 state) or `no_context` (without attention, company and market, p = 0.1, the source's questions). Questions by source: Call A D0 and D2 react + mag, Call B react + cont. `question_json` is Laya's input format `{type, instructions, criteria}` (react = Q1, cont = Q6 of `configs/questions_v1.yaml`, option order kept; mag = the internal H-mag question of `configs/training.yaml`).
- **Schema:** `example_id` ("{event_id}|{call}|{variant}|{question_id}"), `event_id`, `split`, `call` (A | B), `window` (W0 | W2), `variant`, `question_id` (react | mag | cont), `state_json`, `question_json` string, `n_tokens_state` int64 (ModernBERT-large tokens; NA-04's count for full states, recounted for copies); train and val-A only: `label_index` int8 (val-A nullable: purged or missing); val-A only: `embargo` bool. **The val-B and test files have exactly the columns before `label_index`** (`kaggle_export.EVAL_COLUMNS`, asserted; tests/test_train_export_schema.py).
- **Key:** `example_id` unique per file
- **Availability:** a state is an input at its decision point (NA-04); labels `post`. Val-B and test labels never leave this machine (PREREG §9.3, CLAUDE.md D16). Sequence check (`dataset_info.json` `truncation`): with max length 1,036 (PREREG §15 NA-08 row) and head length 143 (react, Laya's rendering) no state is cut; at 1,024, 5 Call A D0 react examples (4 train, 1 val-A) would exceed the room by ≤ 12 tokens.

### `work/kaggle/dataset/train.parquet`
- **Producer / schema:** as "Kaggle dataset files" above (labelled examples only)
- **Rows:** 174,320 examples of 83,749 distinct states: Call A D0 react 22,267 + mag 22,598; Call A D2 react 28,766 + mag 29,192; Call B react 28,766 + cont 18,946; copies no_reaction 8,680, no_context 15,105. Sessions 2024-07-01 … 2025-06-30; last label horizon 2025-06-30.
- **sha256:** `41af9208ebdd51e206350240564bdb5e06a4c5b18fdcafd555cbd78cb98e6213`

### `work/kaggle/dataset/val_a.parquet`
- **Producer / schema:** as "Kaggle dataset files" above (`label_index` nullable, `embargo`)
- **Rows:** 62,404 examples (every val-A state × its questions; full states only), 29,687 distinct states; 56,323 labelled; embargo rows 3,828.
- **sha256:** `9bf4807754c5d405af29996f40a61054cf07790db1c5972b32902bfb594faf75`

### `work/kaggle/dataset/val_b.parquet`
- **Producer / schema:** as "Kaggle dataset files" above, **no label column**
- **Rows:** 43,382 examples (Call A D0 / D2 and Call B states of val-B × their questions), 20,327 distinct states.
- **sha256:** `744463ce1a75dd7fc41be33a98bf04717392cc266e2f502a700fcd030c61d043`

### `work/kaggle/dataset/test_callA.parquet`
- **Producer / schema:** as "Kaggle dataset files" above, **no label column**; Call A only (no test-period Call B state exists before the NA-11 freeze)
- **Rows:** 65,204 examples (Call A D0 13,977 and D2 18,625 states × react, mag), 29,237 distinct states.
- **Availability:** test-period t−1 context words: never summarized before the freeze.
- **sha256:** `61271b3eb46127598b1cee51f7d04c4b8d7202d412e7e0397964fbf46667cbe6`

### `work/kaggle/dataset/dataset_info.json`
- **Producer:** `--stage export`; uploaded with the dataset
- **Schema:** JSON: `questions` (Laya input format, type, k, option keys, head tokens: react 143, mag 77, cont 64), `questions_by_source`, `max_len` (1,036), `head_max_len` (143), `truncation` (room per question: react 889, mag 955, cont 968; cut example ids: none; `max_len_without_cut` 1,036), `files`, `counts` (examples / labelled / embargo by call, window, variant, question), `dates`, label definitions, export constants, `provenance` (sha256 of the three state files, the labels, `configs/training.yaml`, `configs/questions_v1.yaml`)
- **sha256:** `4011235ee0b9182cf2ef87c267f67119edf14b79657ed6c7713ea6d220c002ae`

### `work/kaggle/dataset/sha256_manifest.json`
- **Producer:** `--stage export`; uploaded with the dataset. The notebook checks every file against it on Kaggle and records the sha256s in each run record; `import_preds` requires them to equal this manifest (AC1).
- **Schema:** JSON `{version, files: {name: {sha256, bytes[, rows, columns]}}}` for the four parquet files and `dataset_info.json`
- **sha256:** `2bafd1de3d40a705ab14c150672b83d0c251b88d7ee0db57db286f5b0e796992`

### `work/kaggle/dataset/dataset-metadata.json`
- **Producer:** `--stage export`; Kaggle's dataset metadata (not uploaded as data)
- **Schema:** JSON `{title, id, licenses: [{name: other}], isPrivate: true}`
- **sha256:** `f3538aea683d833f88d9cc417d02f0c17d3dd8a995b2de6ff874e15b0a607353`

#### Downloaded run outputs (not registered)
- `work/kaggle/predictions/<run>/na08_*`: a run's Kaggle outputs (Arrow IPC predictions, calibration, run record, run config, `na08_outputs.json`) and the kernel log, downloaded with `--file-pattern na08_`; checked against their sha256 (`import_preds.verify_run`) before the import reads them. Not parquet, so `make manifest` does not take them for unregistered artifacts.

### Run files (schema shared by the run files below)
- **Producer:** `newsaction.train.build --stage import` (`train.import_preds`, S7), from the verified download of the run
- **Schema:** `run`, `init` (laya | modernbert) string, `seed` int64, `split` (val_a | val_b | test), `example_id`, `event_id`, `call`, `window`, `question_id` string, `k` int8, `logits` list<double> (the run's raw logits), `probabilities` list<double> (softmax(logits / T) with the run's val-A temperature per head; options in Laya's order)
- **Key:** `(split, example_id)` unique
- **Availability:** model outputs at the state's decision point (the inputs are the NA-04 states). Val-B and test rows are stored, never evaluated in NA-08.

### `work/kaggle/predictions/runs/shuffle-s13.parquet`
- **Producer / schema:** as "Run files" above; the shuffled-label control (Laya init, seed 13, 1 epoch, labels permuted within split and question; val-A only)
- **Rows:** 62,404 (val-A 62,404)
- **sha256:** `6c0f7557e99b4b929fca0ec314354e8f06984209c45a063288b55bc033bbf539`

### `work/kaggle/predictions/runs/laya-s13.parquet`
- **Producer / schema:** as "Run files" above; Laya-Fin, seed 13, 1 epoch
- **Rows:** 170,990 (val-A 62,404 + val-B 43,382 + test 65,204)
- **sha256:** `ae03f6e92df888e6d58bf1cd69478ce616d88766dc60d7222363d03d16bd24c8`

### `work/kaggle/predictions/runs/anchor-s13.parquet`
- **Producer / schema:** as "Run files" above; the anchor (ModernBERT-large, fresh head), seed 13, 1 epoch
- **Rows:** 170,990 (val-A 62,404 + val-B 43,382 + test 65,204)
- **sha256:** `4c844aa5047d062e8f545ac5d12bd1bc61a2896e6b61b858893d88e5c74c59cd`

### Prediction files (schema shared by the six files below)
- **Producer:** `newsaction.train.build --stage import` (`train.import_preds`, S7): per model, the mean of its seed runs' calibrated probabilities (PREREG §9.1). Each model has one seed for now (PREREG §15 NA-08 row 2: seeds 17 and 23 deferred), so its file holds that seed's probabilities; a deferred seed joins on a rerun of the import.
- **Schema (the common prediction schema):** `event_id`, `company_id` int64, `session` date32, `split`, `window` (W0 | W2), `decision_point` (D0 | D2), `call` (A | B), `question` (react | mag | cont), `model` (laya_fin | anchor), `n_seeds` int64, `runs` (comma-separated run names) string, `k` int8, `probabilities` list<double>, derived double (NaN where not applicable): `n_hat`, `e_abs_n` (react; PREREG §7 midpoints), `mag_mean` (midpoints 0.25, 0.75, 1.5, 2.5, 3.5), `p_mag_ge1` (mag), `p_reverse`, `p_stall`, `p_continue`, `c_cont` (= P(continue) − P(reverse)), `j_cont` (J analogue = c_cont), `w_cont` (W analogue = P(reverse)) (cont), `confidence` (max probability)
- **Key:** `(event_id, call, question)` unique
- **Availability:** model outputs at the state's decision point. Val-B and test files are stored, never evaluated in NA-08 (NA-11 evaluates val-B; test after the freeze and unblinding).

### `work/kaggle/predictions/laya_fin_val_a.parquet`
- **Producer / schema:** as "Prediction files" above; laya_fin, val-A: Call A D0 / D2 (react, mag) and Call B (react, cont)
- **Rows:** 62,404
- **sha256:** `f1544b79f3bb7d149990083f5745c27166a42ffca4b4bdc12d331504a4aa9d8a`

### `work/kaggle/predictions/laya_fin_val_b.parquet`
- **Producer / schema:** as "Prediction files" above; laya_fin, val-B: as val-A; stored, not evaluated
- **Rows:** 43,382
- **sha256:** `e57d9ee831932f932426cccb29a1ed94c6f18e2f74d0446d0bf6dd2f83673c7e`

### `work/kaggle/predictions/laya_fin_test_callA.parquet`
- **Producer / schema:** as "Prediction files" above; laya_fin, test: Call A D0 and D2 (react, mag); stored, not evaluated
- **Rows:** 65,204
- **sha256:** `c256836331623f652d7b85299000002ba92f27032fb2536f4cd18d2be86593c1`

### `work/kaggle/predictions/anchor_val_a.parquet`
- **Producer / schema:** as "Prediction files" above; anchor, val-A: Call A D0 / D2 (react, mag) and Call B (react, cont)
- **Rows:** 62,404
- **sha256:** `a26d094e6d7fc18522a02a5a9700d4bcccebeacdd45743e1e199ae44ac717970`

### `work/kaggle/predictions/anchor_val_b.parquet`
- **Producer / schema:** as "Prediction files" above; anchor, val-B: as val-A; stored, not evaluated
- **Rows:** 43,382
- **sha256:** `6cced05c5e499aba76c6256941bfb5ecd6a8829e479178d0f8ef981d9fe6b334`

### `work/kaggle/predictions/anchor_test_callA.parquet`
- **Producer / schema:** as "Prediction files" above; anchor, test: Call A D0 and D2 (react, mag); stored, not evaluated
- **Rows:** 65,204
- **sha256:** `d659d3659c2abe819dc454ef06f3b5db848263b2877d3f96061346549f289376`

## NA-09 — baselines (`newsaction.baselines`)

### `work/baselines/sentiment.parquet`
- **Producer:** `newsaction.baselines.run --stage fit`
- **Inputs:** `work/baselines/state_articles.parquet`, `work/news/articles_clean.parquet`, `work/events/events_d0.parquet`, `work/states/context_company.parquet`, `work/panel/panel_public.parquet` (targets, train / val-A only)
- **Schema:** `event_id`, `model`, `call` (A: D0 event with a Call A state; B: D2 event with a Call B state), `split`, `session` (date), `company_id` (int64), `N_hat` (σ units, e5 scale), `P_up` = P(e5 ≥ +0.5), `P_down` = P(e5 ≤ −0.5), `mag_hat` (expected \|move\|), `y_hat` (price-only D2: predicted y2), `extra` (JSON object); `newsaction.baselines.schema`
- **Key:** (`event_id`, `model`, `call`) unique; `schema.validate` (events match the state files)
- **Rows / coverage:** PREREG §10.1: mean vendor sentiment of the state's articles → isotonic N_hat (train), OLS mag_hat (train), val-A P maps. Every Call A D0 state, test included (54,332) (54,332 rows)
- **Availability:** D0 (`w0` / `t_minus_1` inputs, vendor fields as pre-registered baseline signals, PREREG §10); fit on train, tuned and calibrated on val-A (fit records in `work/baselines/models/`); train and val-A rows are in-sample for the fit or the maps. Test rows use only inputs known before the open (no 2026 price, return or volume)
- **sha256:** `a0350d0fc8bf8a227837fb71f851059236da7f47d43a534a4c21f83679bdc782`

### `work/baselines/embed_ridge.parquet`
- **Producer:** `newsaction.baselines.run --stage fit`
- **Inputs:** the above + `work/news/embeddings_ts.parquet`
- **Schema:** `event_id`, `model`, `call` (A: D0 event with a Call A state; B: D2 event with a Call B state), `split`, `session` (date), `company_id` (int64), `N_hat` (σ units, e5 scale), `P_up` = P(e5 ≥ +0.5), `P_down` = P(e5 ≤ −0.5), `mag_hat` (expected \|move\|), `y_hat` (price-only D2: predicted y2), `extra` (JSON object); `newsaction.baselines.schema`
- **Key:** (`event_id`, `model`, `call`) unique; `schema.validate` (events match the state files)
- **Rows / coverage:** PREREG §10.2: mean bge-small vector of the state's articles + attention → ridge (train; λ on val-A). Every Call A D0 state, test included (54,332) (54,332 rows)
- **Availability:** D0 (`w0` / `t_minus_1` inputs, vendor fields as pre-registered baseline signals, PREREG §10); fit on train, tuned and calibrated on val-A (fit records in `work/baselines/models/`); train and val-A rows are in-sample for the fit or the maps. Test rows use only inputs known before the open (no 2026 price, return or volume)
- **sha256:** `3fc6f18bf565f162ddddf89ac417178f3fa6f662a2e196aa6e511ecbccd521f4`

### `work/baselines/tags_gbm.parquet`
- **Producer:** `newsaction.baselines.run --stage fit`
- **Inputs:** `work/baselines/state_articles.parquet`, `work/news/articles_clean.parquet`, `work/events/events_d0.parquet`, `work/states/context_company.parquet`, `work/panel/panel_public.parquet` (targets, train / val-A only)
- **Schema:** `event_id`, `model`, `call` (A: D0 event with a Call A state; B: D2 event with a Call B state), `split`, `session` (date), `company_id` (int64), `N_hat` (σ units, e5 scale), `P_up` = P(e5 ≥ +0.5), `P_down` = P(e5 ≤ −0.5), `mag_hat` (expected \|move\|), `y_hat` (price-only D2: predicted y2), `extra` (JSON object); `newsaction.baselines.schema`
- **Key:** (`event_id`, `model`, `call`) unique; `schema.validate` (events match the state files)
- **Rows / coverage:** PREREG §10.3: vendor tags, flags, sentiment, intensity, source classes, novelty, attention, tier, sector → LightGBM (train; grid on val-A). Every Call A D0 state, test included (54,332) (54,332 rows)
- **Availability:** D0 (`w0` / `t_minus_1` inputs, vendor fields as pre-registered baseline signals, PREREG §10); fit on train, tuned and calibrated on val-A (fit records in `work/baselines/models/`); train and val-A rows are in-sample for the fit or the maps. Test rows use only inputs known before the open (no 2026 price, return or volume)
- **sha256:** `b3fd8859a8d50b55ad6ff71ab661743b18e61d51ad51c249dee2dff8432a7aba`

### `work/baselines/price_only.parquet`
- **Producer:** `newsaction.baselines.run --stage fit`
- **Inputs:** `work/baselines/state_articles.parquet`, `work/news/articles_clean.parquet`, `work/events/events_d0.parquet`, `work/states/context_company.parquet`, `work/panel/panel_public.parquet` (targets, train / val-A only)
- **Schema:** `event_id`, `model`, `call` (A: D0 event with a Call A state; B: D2 event with a Call B state), `split`, `session` (date), `company_id` (int64), `N_hat` (σ units, e5 scale), `P_up` = P(e5 ≥ +0.5), `P_down` = P(e5 ≤ −0.5), `mag_hat` (expected \|move\|), `y_hat` (price-only D2: predicted y2), `extra` (JSON object); `newsaction.baselines.schema`
- **Key:** (`event_id`, `model`, `call`) unique; `schema.validate` (events match the state files)
- **Rows / coverage:** PREREG §10.4: call A (D0) momentum, z_vol(t−1), σ regime, tier, sector → N_hat / mag_hat; call B (D2) + G, z_on,t, z_vol,t → y_hat (y2). Call A D0 states of robustness, train, val-A, val-B (40,355) and Call B states (48,197); **no test row** (NA-11 predicts test with the saved models after the freeze) (88,552 rows)
- **Availability:** call A: D0 (`t_minus_1`); call B: D2 (`d2_reaction`); fit on train, grid on val-A; no 2026 input
- **sha256:** `b67b72aa41814a24c1a1e92b589f8ce077268bd43701b337f2da2d7a74a3bf95`

### `work/baselines/laya_zeroshot.parquet`
- **Producer:** `newsaction.baselines.run --stage laya_zeroshot_predictions`
- **Inputs:** `work/states/callA_d0_E3.parquet`, `work/states/callB_d2_E3.parquet`, `cache/decisions.sqlite` (chunk NA-09 rows and NA-05 / NA-06 hits)
- **Schema:** `event_id`, `model`, `call` (A: D0 event with a Call A state; B: D2 event with a Call B state), `split`, `session` (date), `company_id` (int64), `N_hat` (σ units, e5 scale), `P_up` = P(e5 ≥ +0.5), `P_down` = P(e5 ≤ −0.5), `mag_hat` (expected \|move\|), `y_hat` (price-only D2: predicted y2), `extra` (JSON object); `newsaction.baselines.schema`
- **Key:** (`event_id`, `model`, `call`) unique; `schema.validate` (events match the state files)
- **Rows / coverage:** PREREG §10.5: local Laya typed-decisions (@55cf4c4e), core battery, from the decision cache: N_hat = N̂, P_up / P_down = Σ p of Q1's rise / fall levels, mag_hat = E\|N̂\|; `extra` M, surprise, tone (A) or J, W, C (B), Q1 probabilities, build, truncation. Call A D0: robustness, train, val-A, val-B; Call B D2: train, val-A, val-B; no test row (NA-11 after the freeze) (88,552 rows)
- **Availability:** the masked states (D0 / D2); zero-shot, nothing fitted
- **sha256:** `7dd7b218b1cf974b0d653ed21947cbc384b31563446059fb9899e407e6ba820c`

### `work/baselines/llm.parquet`
- **Producer:** `newsaction.baselines.run --stage llm_predictions`
- **Inputs:** `work/baselines/llm_sample.parquet`, `cache/decisions.sqlite` (NA-09 chat rows)
- **Schema:** `event_id`, `model`, `call` (A: D0 event with a Call A state; B: D2 event with a Call B state), `split`, `session` (date), `company_id` (int64), `N_hat` (σ units, e5 scale), `P_up` = P(e5 ≥ +0.5), `P_down` = P(e5 ≤ −0.5), `mag_hat` (expected \|move\|), `y_hat` (price-only D2: predicted y2), `extra` (JSON object); `newsaction.baselines.schema`
- **Key:** (`event_id`, `model`, `call`) unique; `schema.validate` (events match the state files)
- **Rows / coverage:** PREREG §10.7: mistralai/mistral-nemo via `DecisionClient.chat_json`: Q1 probabilities (verbalized) → N_hat, P_up, P_down, mag_hat; `extra` the probabilities, renormalized flag, raw sum, build, provider, cost. Valid answers only (invalid ones counted in `artifacts/NA-09/llm_summary.json`). The 2,000 val-B events of `work/baselines/llm_sample.parquet` (valid answers) (1,978 rows)
- **Availability:** D0 (the masked Call A state); val-B only, no metric in NA-09
- **sha256:** `fbaf22a7b97c502b8fd722678d53e074af576ea58995948cda53a18b34025b30`

### `work/baselines/state_articles.parquet`
- **Producer:** `newsaction.baselines.run --stage articles` (`data.rebuild_state_articles`)
- **Inputs:** `work/states/callA_d0_E3.parquet`, `work/events/events_d0.parquet` (`news_w0`), `work/states/articles_masked.parquet`, `work/news/articles_clean.parquet` (NA-04's exclusions)
- **Schema:** `event_id`, `article_id`, `rank` (int64; order in the state's `news` list)
- **Key:** (`event_id`, `rank`)
- **Rows / coverage:** 189,705 rows for the 54,332 Call A D0 states; every state's news items equal its rebuilt articles' masked title and snippet (the first may be cut by words) (189,705 rows)
- **Availability:** `w0` (the state's own articles)
- **sha256:** `008c0230ee0b1346f9be3850b98781249c03384e294e88987cb6049ecfc6fb0c`

### `work/baselines/llm_sample.parquet`
- **Producer:** `newsaction.baselines.run --stage llm_sample` (`llm_baseline.sample`)
- **Inputs:** `work/states/callA_d0_E3.parquet`, `work/events/events_d0.parquet`
- **Schema:** `event_id`, `tier`, `month`, then `dm.canary.STATE_COLUMNS` of the Call A state (`session`, `split`, `call`, `encoding`, `masked`, `state_json`, `state_sha256`, `n_tokens_state`, `third_party_ok_all`)
- **Key:** `event_id`
- **Rows / coverage:** 2,000 val-B D0 events after the embargo (2025-10-08 … 12-31), tier × month, seed 2026 (NA-04's `stratified_sample`) (2,000 rows)
- **Availability:** D0 inputs only (no outcome)
- **sha256:** `f9fb689a2d3cb0c0354196225600818a6737b3a4499b534ab19f2abc4b752fd2`

### `work/baselines/models/sentiment_e5.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/sentiment.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: isotonic thresholds, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** sentiment → e5
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `f4a2a81f772b3bcff3e2657158f59aa97f6a17b13c128602e6fa214b15819e91`

### `work/baselines/models/sentiment_abs_z_cc.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/sentiment.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: OLS coefficients, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** sentiment → abs_z_cc
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `d2b24183918bf386692eada42d62273b6376a9a154f9638b7172f6ee2bf01515`

### `work/baselines/models/embed_ridge_e5.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/embed_ridge.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: ridge coefficients, intercept, λ, standardization, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** embed_ridge → e5
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `cb4b2a1d2924c47ade0ba8f98e35118e73cd39696785d26a2d2d2f43e66e4399`

### `work/baselines/models/embed_ridge_abs_z_cc.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/embed_ridge.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: ridge coefficients, intercept, λ, standardization, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** embed_ridge → abs_z_cc
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `9073a80b69b229143cbbdec5a631f68732b87f70aae3f4b528453ab0e0929f96`

### `work/baselines/models/tags_gbm_e5.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/tags_gbm.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: LightGBM model text, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** tags_gbm → e5
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `688ba83308f3095632456f141ff85137309bd8f0ad4092d9afaf284623023607`

### `work/baselines/models/tags_gbm_abs_z_cc.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/tags_gbm.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: LightGBM model text, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** tags_gbm → abs_z_cc
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `452210b423948e2ebd9299b83e5f78559404b607a6d9b530888068ac52cb0014`

### `work/baselines/models/price_only_e5.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/price_only.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: LightGBM model text, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** price_only → e5
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `cdaad7aeccd67188c16382f25959f6d87e3150601eb7d37d8fc47cd1ce23c435`

### `work/baselines/models/price_only_abs_z_cc.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/price_only.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: LightGBM model text, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** price_only → abs_z_cc
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `01fb5cd61babe24192533c6c620876724dec33c42e8a104024ed10bf173ad45d`

### `work/baselines/models/price_only_y2.json`
- **Producer:** `newsaction.baselines.run --stage fit` (`fitting.save_model`)
- **Inputs:** `work/baselines/price_only.parquet`'s frame
- **Schema:** {`record`: `schema.FitRecord` (model, target, point, features, `fit` / `tune` / `calibration` ranges {split, start, end, n_rows, n_sessions}, `selected`, `grid` with val-A scores, seed, library), `model`: LightGBM model text, `prob_maps`: val-A isotonic P_up / P_down maps or null}
- **Key:** n/a
- **Rows / coverage:** price_only → y2
- **Availability:** fit range inside train, tuning and calibration ranges inside val-A (`check_fit_record`, AC1)
- **sha256:** `ed99ad1280df5a49ff665d4be13bd49557be30745fa7cbc93e74102be72566e2`

### `artifacts/NA-09/llm_catalog.json`
- **Producer:** `newsaction.baselines.run --stage llm_select`
- **Inputs:** GET https://openrouter.ai/api/v1/models (no spend), `artifacts/NA-06/leaderboard.csv`, `work/baselines/llm_sample.parquet` (state sizes)
- **Schema:** {`fetched_at`, `url`, `raw_sha256` (the full catalog response), `n_models`, `rule` (`configs/baselines.yaml` `llm.selection`), `reference_usd_per_1000`, `mean_input_bytes`, `order`, `chosen`, `models` (every candidate passing the rule: id, pricing, cutoff, parameters, projected USD per 1,000)}; the client's chat price snapshot (`configs/dm.yaml` `api.chat_catalog`)
- **Key:** `models[].id`
- **Rows / coverage:** 463 catalog models, 11 candidates; chosen mistralai/mistral-nemo
- **Availability:** n/a (val-A metrics, model choice and spend; no val-B or test value)
- **sha256:** `5dd90aed0bd23461d981b25e14ffdd6cb7aeb44ca41d4175edf64ee56a1dd71d`

### `artifacts/NA-09/llm_dry_run.json`
- **Producer:** `newsaction.baselines.run --stage llm_dry | llm_run`
- **Inputs:** the 2,000 chat requests
- **Schema:** list of {`ts`, `send`, `model`, `n_requests`, `n_send`, `projected_usd`, `projected_tokens`, `budget_left_usd`, and for a run `account_left_usd`, `answered`, `valid`, `spent_usd`, `reconcile`}
- **Key:** list order
- **Rows / coverage:** every projection and the run
- **Availability:** n/a (val-A metrics, model choice and spend; no val-B or test value)
- **sha256:** `c524571880925e1b3c348b9fd98b52e99ddaf1b01207cbb979c89bfb85f7cbf8`

### `artifacts/NA-09/llm_summary.json`
- **Producer:** `newsaction.baselines.run --stage llm_predictions` (`llm_baseline.summary`, offline)
- **Inputs:** `cache/decisions.sqlite` (NA-09 chat rows)
- **Schema:** {`model`, `builds`, `providers`, `n`, `answered`, `valid`, `invalid`, `problems`, `renormalized`, `raw_sum_min` / `max`, mean input / output tokens, `cost_usd`, `cost_per_1000`, latency p50 / p95}
- **Key:** n/a
- **Rows / coverage:** one record
- **Availability:** n/a (val-A metrics, model choice and spend; no val-B or test value)
- **sha256:** `52fda0efdf873d65fffb1862d8d6f92a20b424e9ce602b738d5b08d3ba298292`

### `artifacts/NA-09/key_usage.json`
- **Producer:** `llm_baseline.snapshot_key` (GET /api/v1/key and /api/v1/credits; no spend)
- **Inputs:** OpenRouter
- **Schema:** list of {`label`, `ts`, the key's `usage`, `usage_daily`, `limit`, `limit_remaining`, `is_free_tier`, the account's `total_credits`, `total_usage`, `remaining`, `ledger_chunk_usd`}
- **Key:** list order
- **Rows / coverage:** before / after the S7 probe and run
- **Availability:** n/a (val-A metrics, model choice and spend; no val-B or test value)
- **sha256:** `4e56533e93eeaf2dbfc86851187afa6b79013307f1bbd4b5dad9d0fb07e5b9d1`

### `artifacts/NA-09/baseline_val_metrics.csv`
- **Producer:** `newsaction.baselines.run --stage metrics` (`metrics.val_metrics`)
- **Inputs:** `work/baselines/*.parquet`, `work/panel/panel_public.parquet`, `work/events/events_d{0,2}.parquet`
- **Schema:** `model`, `call`, `signal` (N_hat, mag_hat, y_hat, j, c), `target` (z_cc, e5, abs_z_cc, y2), `metric` (ic: mean daily Spearman IC, ≥ 5 events a day; r2_vs_zero; r2_vs_train_mean), `tier` (all, top100, mid, rest), `value`, `t` (Newey–West, 5 lags), `se`, `n_days`, `n_events`
- **Key:** (`model`, `call`, `signal`, `target`, `metric`, `tier`)
- **Rows / coverage:** val-A outside the embargo only (`metrics.evaluation_rows`); no val-B or test metric
- **Availability:** n/a (val-A metrics, model choice and spend; no val-B or test value)
- **sha256:** `5cb239fa1cd3b3bcfed4afec6b7e5d24d0ff23d45f659d6661c770b1d6396d4f`

### `artifacts/NA-09/summary.json`
- **Producer:** `newsaction.baselines.run --stage report`
- **Inputs:** `work/baselines/*`, `ledgers/spend.jsonl`
- **Schema:** {`predictions`: rows by `call:split` per model, `fit_records`: {fit, tune, calibration, selected} per model and target, `spend`}
- **Key:** n/a
- **Rows / coverage:** one record
- **Availability:** n/a (val-A metrics, model choice and spend; no val-B or test value)
- **sha256:** `fbd0352853166b35025db104ad91404ce44d29abbb2678ad7c6066e707e83ce7`

## NA-11 — final selection, freeze, production (`newsaction.analysis`, `newsaction.production`)

### `work/analysis/state_articles_w2.parquet`
- **Producer:** `newsaction.analysis.frames.write_state_articles_w2`
- **Inputs:** `work/events/events_d2.parquet` (`news_w2`), `work/states/callA_d2_E3.parquet`, `work/states/articles_masked.parquet`, `work/news/articles_clean.parquet` (NA-04 exclusions)
- **Schema:** `event_id`, `article_id`, `rank` (int64, 0 = the state's first news item)
- **Key:** (`event_id`, `rank`) unique
- **Rows / coverage:** every Call A D2 state's articles, rebuilt as NA-09 rebuilt the D0 ones and checked against each state's news block (274,944 rows)
- **Availability:** D2 (`w2`); article ids only
- **sha256:** `4910de4f168d07f0d6fe4c5cfc277de5212235b3adccab064667987725a45e35`

### `work/dm/production/company_id_matched.parquet`
- **Producer:** `newsaction.production.company_id.run`
- **Inputs:** `work/dm/tournament/samples.parquet` (NA-06's 400 identification events), `work/states/callA_d0_E3.parquet`, `work/events/{events_d0,window_counts}.parquet`, `work/panel/{panel_public,companies}.parquet`, `cache/decisions.sqlite` (chunk NA-11)
- **Schema:** `model`, `event_id`, `key`, `ok`, `valid`, `true_key`, `argmax_key`, `p_true`, `cost`, `correct`
- **Key:** (`model`, `event_id`) unique
- **Rows / coverage:** PREREG §15 NA-06 row option (iv): company identification with activity-matched distractors, six stage-2 API models and local Laya zero-shot × 400 val-A events (2,800 rows)
- **Availability:** val-A D0 states (masked); a probe, no target
- **sha256:** `124ef4866f682b690463fd17aedcd082ab569f108171551e32533c66d85953d9`

### `work/states/callB_d2_E3_test.parquet`
- **Producer:** `newsaction.production.states_test` (S4, after the freeze)
- **Inputs:** `work/events/events_d2.parquet`, `work/analysis/state_articles_w2.parquet`, NA-04's inputs; the test reactions from `panel.reactions.build_reactions(..., "test", "D2")` through `newsaction.lock` (purpose reactions, logged)
- **Schema:** NA-04's state schema (`event_id`, `company_id`, `session`, `split`, `window`, `call`, `encoding`, `masked`, `state_json`, `state_sha256`, `n_tokens_state`, `n_tokens_with_questions`, `n_articles`, `third_party_ok_all`)
- **Key:** `event_id` unique
- **Rows / coverage:** Call B on D2 for the 18,625 test D2 events with a Call A D2 state; each equals its Call A D2 twin except `reaction_so_far` (asserted)
- **Availability:** D2 (after close(s)); built only after the freeze (PREREG §4.4 step 5)
- **sha256:** `3d171ae2d835a3410e99d1faac6ec56fb08e48b9ccea1344d4769f8091866054`

### `work/states/callB_d1_E3_test.parquet`
- **Producer:** `newsaction.production.states_test` (S4, after the freeze)
- **Inputs:** `work/events/events_d0.parquet`, NA-04's inputs; the test D1 reactions from `panel.reactions.build_reactions(..., "test", "D1")` and `bars.derive.test_intraday_panel` on the blinded bars and prices, all through `newsaction.lock` (purpose reactions, logged)
- **Schema:** NA-04's state schema
- **Key:** `event_id` unique
- **Rows / coverage:** Call B on D1 (W0 news + the reaction by 10:00) for the test D0 events with text (13,977); NA-10's budget (the longest possible reaction block)
- **Availability:** D1 (10:00 ET); built only after the freeze
- **sha256:** `c0c047b8511fff75b61295bc957e724f7d784132398b7ee744a1b5a52f622f77`

### `work/dm/production/local_laya_typed_decisions_probes.parquet`
- **Producer:** `newsaction.production.laya_local.run("probes")`
- **Inputs:** NA-06's probe builders (`tournament.run`: counterfactual edits, unmasked twins, shuffled news) on `work/states/callA_d0_E3.parquet` and `work/states/samples/*.parquet`; `cache/decisions.sqlite`
- **Schema:** `newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, `tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, `tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `probe`)
- **Key:** (`probe`, `event_id`) unique
- **Rows / coverage:** the operator's disclosed val-A probes for Laya zero-shot: flip_edit 200, flip_orig 200, unmasked 1,000, masked_twin 1,000, shuffled 1,000 (3,400 rows)
- **Availability:** val-A D0; run locally (the unmasked states never leave this machine); probes, not hypotheses
- **sha256:** `9b970744dc75c9249a73b2dddefe23ebfbf175836cbce7ecfb10fce618ab9d06`

### `work/dm/production/local_laya_typed_decisions_test.parquet`
- **Producer:** `newsaction.production.laya_local.run("test")`
- **Inputs:** `work/states/callA_d0_E3.parquet` (test rows, after the freeze); `cache/decisions.sqlite`
- **Schema:** `newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, `tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, `tone`, confidences; plus `q1`, `conf3`, `source`, `split`)
- **Key:** `event_id` unique
- **Rows / coverage:** Laya zero-shot's test Call A at D0, core battery (PREREG §10.5 comparator)
- **Availability:** D0 (09:15 ET); local model, nothing sent to a third party
- **sha256:** `df399845360d9e13078fd85d93ab26f63f9b70bfa6c80019a3a67f1fcc157e0a`

### `work/dm/production/liquid_d1_ultra_api_comparators_market.parquet`
- **Producer:** `newsaction.production.run.run(["api", "comparators", "market"])` (S6)
- **Inputs:** the state files of `configs/production.yaml` `states`; `cache/decisions.sqlite` (chunk NA-11)
- **Schema:** `newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, `tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, `tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `component`; market rows: `n_hat`, `label_market_reason`, `plabel_market_reason`)
- **Key:** (`component`, `event_id`) unique
- **Rows / coverage:** liquid/d1-ultra: the full plan: Call A D0/D2 (core + extended), Call B D2 (core) and D1 (core + explain), the 2024-H1 A0/A2 core, the A3.5 market states
- **Availability:** the readings' window (`source`: a0 = W0, a2 = W2, b2 = D2, b1 = D1, m = market); test rows sent after the freeze
- **sha256:** `d81a9194c6b1be67d09771d5230e58855aad573b361a8385124c49beb0b57aaa`

### `work/dm/production/respan_span_02_api_comparators_market.parquet`
- **Producer:** `newsaction.production.run.run(["api", "comparators", "market"])` (S6)
- **Inputs:** the state files of `configs/production.yaml` `states`; `cache/decisions.sqlite` (chunk NA-11)
- **Schema:** `newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, `tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, `tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `component`; market rows: `n_hat`, `label_market_reason`, `plabel_market_reason`)
- **Key:** (`component`, `event_id`) unique
- **Rows / coverage:** respan/span-02: core Call A D0 on val-B and test (comparator; screen-failing, model-specific)
- **Availability:** the readings' window (`source`: a0 = W0, a2 = W2, b2 = D2, b1 = D1, m = market); test rows sent after the freeze
- **sha256:** `05cbc981c70651ea9226140abbbb31714abe0d0dbe901fca24acc064753f6d48`

### `work/dm/production/nace_ai_drex_v2_0_api_comparators_market.parquet`
- **Producer:** `newsaction.production.run.run(["api", "comparators", "market"])` (S6)
- **Inputs:** the state files of `configs/production.yaml` `states`; `cache/decisions.sqlite` (chunk NA-11)
- **Schema:** `newsaction.production.run.readings` (NA-06's `derived_frame` columns: `key`, `model`, `event_id`, `tag`, `repeat_idx`, `ok`, `valid`, `model_build`, `cost`, `latency_ms`, `n_hat`, `m`, `surprise`, `tone`, confidences; plus `q1`, `conf3`, `source`, `split`, `component`; market rows: `n_hat`, `label_market_reason`, `plabel_market_reason`)
- **Key:** (`component`, `event_id`) unique
- **Rows / coverage:** nace-ai/drex-v2.0: core Call A D0 on val-B and test (comparator; screen-failing, model-specific)
- **Availability:** the readings' window (`source`: a0 = W0, a2 = W2, b2 = D2, b1 = D1, m = market); test rows sent after the freeze
- **sha256:** `853cf27d7c1c7804f17d8fff59cd77f431e5414cc313411cc5b18cb42e2b2469`

### `work/kaggle/dataset_na11/test_callB.parquet`
- **Producer:** `newsaction.production.kaggle_infer.export` (S7)
- **Inputs:** NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` questions (Laya's input format)
- **Schema:** NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, `question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column
- **Key:** `example_id` unique
- **Rows / coverage:** test Call B at D2 (18,625 states) and D1 (13,977), questions react and cont
- **Availability:** masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset `amirdehkordi98/newsaction-na11-infer`
- **sha256:** `4f530b780ccd77b90ef012f111ca2b1aaaf5ac96e5b863f12a77c2f6cb737157`

### `work/kaggle/dataset_na11/val_callB_d1.parquet`
- **Producer:** `newsaction.production.kaggle_infer.export` (S7)
- **Inputs:** NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` questions (Laya's input format)
- **Schema:** NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, `question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column
- **Key:** `example_id` unique
- **Rows / coverage:** val-A and val-B Call B at D1 (14,941 states), react and cont
- **Availability:** masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset `amirdehkordi98/newsaction-na11-infer`
- **sha256:** `cab199f65b70d84431669c55624b57f4ac2474f7f6ddfdb6c01ef83fa914a5f0`

### `work/kaggle/dataset_na11/robustness_callA.parquet`
- **Producer:** `newsaction.production.kaggle_infer.export` (S7)
- **Inputs:** NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` questions (Laya's input format)
- **Schema:** NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, `question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column
- **Key:** `example_id` unique
- **Rows / coverage:** Call A at D0 (2,793) and D2 (3,887) of the robustness split, react and mag
- **Availability:** masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset `amirdehkordi98/newsaction-na11-infer`
- **sha256:** `5d100f1ae17701e58b1ef4200b3e22b026775ddf33c08490c606086cbe1e3656`

### `work/kaggle/dataset_na11/probes.parquet`
- **Producer:** `newsaction.production.kaggle_infer.export` (S7)
- **Inputs:** NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` questions (Laya's input format)
- **Schema:** NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, `question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column
- **Key:** `example_id` unique
- **Rows / coverage:** NA-06's 200 counterfactual edits (flip_edit) and 1,000 shuffled-news states (shuffled), react
- **Availability:** masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset `amirdehkordi98/newsaction-na11-infer`
- **sha256:** `28b853b283ce99fdfe114c9691b8e03ebdcce4c367ef696885743ca5cb67f4a5`

### `work/kaggle/dataset_na11/check_val_a.parquet`
- **Producer:** `newsaction.production.kaggle_infer.export` (S7)
- **Inputs:** NA-04 / NA-11 state files of `configs/production.yaml` `trained.export`; `configs/training.yaml` questions (Laya's input format)
- **Schema:** NA-08's evaluation columns (`example_id`, `event_id`, `split`, `call`, `window`, `variant`, `question_id`, `state_json`, `question_json`, `n_tokens_state`); no label column
- **Key:** `example_id` unique
- **Rows / coverage:** 500 val-A D0 react examples of NA-08's export, re-predicted to check the checkpoint
- **Availability:** masked, third-party-OK states only (CLAUDE.md D15-D16); uploaded as the private Kaggle dataset `amirdehkordi98/newsaction-na11-infer`
- **sha256:** `e14fed28384c312ce4a85ff6c316d497b2d724bce1fcc208cd6880aeb5c9d78a`

### `artifacts/NA-11/final_selection.csv`
- **Producer:** `newsaction.production.select_final`
- **Inputs:** `work/kaggle/predictions/{laya_fin,anchor}_{val_a,val_b}.parquet` (the frozen runs), `work/baselines/laya_zeroshot.parquet`, `work/dm/encoding/confirm.parquet`, `work/panel/panel_public.parquet`
- **Schema:** `model`, `role`, `runs`, `n_events`, `n_days`, `ic`, `nw_t`, `boot_se`, `ci_low`, `ci_high`, `p_one_sided`, `ic_j_y2`, `ic_j_y2_t`, `ic_j_y2_days`, `cost_per_1000`, `selected`, `rank`, `rule`
- **Key:** `model` unique
- **Rows / coverage:** PREREG §8.5 on val-B: three candidates (common events) and three screen-failing comparators (NA-07's val-B sample, information only); its sha256 is `configs/frozen.yaml` `selection.ic_table_sha`
- **Availability:** val-B targets (`allow_val_b: true`); no test row
- **sha256:** `31d0a918b4462ba3779dc78fbf7eee42caf46c75e389c16df2238cefd680f2fd`

### `artifacts/NA-11/company_id_matched.csv`
- **Producer:** `newsaction.production.company_id.run`
- **Inputs:** `work/dm/production/company_id_matched.parquet`, `work/dm/tournament/probes.parquet`
- **Schema:** `model`, `n`, `valid`, `accuracy`, `mean_p_true`, `cost`, `accuracy_na06_design`, `baseline_matched`, `baseline_na06_design`, `screen_threshold`
- **Key:** `model` unique
- **Rows / coverage:** accuracy per model beside NA-06's and the no-reading baselines of both designs
- **Availability:** val-A; a probe
- **sha256:** `1e9e0c22b9a1506872ffa683d0275b847d89d3219aa0f30dc9d8ccb3bd6da7ad`

### `artifacts/NA-11/spec_smoke_val_b.json`
- **Producer:** `newsaction.production.smoke_spec`
- **Inputs:** the val-A / val-B analysis frames (`newsaction.analysis.frames`) of Laya-Fin, the anchor and Laya zero-shot; `configs/frozen.yaml` calibration
- **Schema:** {split, primary, steps: {name: {result, seconds}}, plateau_check, live_format_states_val_b, seconds}
- **Key:** one JSON object
- **Rows / coverage:** PRD NA-11 AC2: the spec end to end on val-B (29 steps; the ridge protocol's splits shifted)
- **Availability:** val-A / val-B targets; no test row
- **sha256:** `110db5b0bda03f7e55903a03eef51694a840172150c6d193ea8a1ef423ceed2c`

### `artifacts/NA-11/canary_baseline_na11.parquet`
- **Producer:** `newsaction.production.canary_check.run`
- **Inputs:** `artifacts/NA-05/canary_v1.jsonl`; `cache/decisions.sqlite` (chunk NA-11)
- **Schema:** `model`, `model_build`, `canary_id`, `question`, `option`, `p`, `renormalized`, `key`, `repeat_idx` (NA-05's `canary_baseline.parquet` format)
- **Key:** (`model`, `canary_id`, `question`, `option`, `repeat_idx`) unique
- **Rows / coverage:** canary baselines of d1-ultra, span-02 and drex-v2.0 (no NA-05 baseline): repeat 0 of all 50 items and repeats 1–4 of the 20 train Call A items
- **Availability:** train and synthetic canary states; no target
- **sha256:** `d091b3d1140984fca3be9d724f786824dd5436d7cc049c090b03cdca1731ae75`

### `artifacts/NA-11/canary_drift_na06.csv`
- **Producer:** `newsaction.production.canary_check.run`
- **Inputs:** `artifacts/NA-11/canary_baseline_na11.parquet`, `work/dm/tournament/stage2.parquet`, `cache/decisions.sqlite` (NA-06 and NA-11 rows)
- **Schema:** `model`, `canary_noise_mean_abs_dp`, `canary_noise_per_repeat`, `drift_mean_abs_dp_vs_na06`, `drift_pairs`, `same_state_noise_mean_abs_dp`, `builds_na06`, `builds_now`, `stop`
- **Key:** `model` unique
- **Rows / coverage:** repeat noise of the new baselines and the drift of 100 NA-06 stage-2 answers per model (operator rule: STOP if the drift exceeds the noise)
- **Availability:** val-A states; no target
- **sha256:** `b6b9f058dd139b310c90f999ff49c291a5eecc6df27ac75ab3df90325b2f2cf4`

### `work/dm/production/ablation_sample.parquet`
- **Producer:** `newsaction.production.ablations.write_sample` (S8)
- **Inputs:** `work/states/{callB_d2_E3,callB_d2_E3_test,callA_d0_E3}.parquet`, `work/events/{events_d0,events_d2}.parquet` (tier, month, embargo)
- **Schema:** `event_id`, `base` (`B_D2` / `A_D0`), `split`, `session`, `company_id`, `tier`, `month`, `donor` (the shuffled-news donor of a `B_D2` event)
- **Key:** `event_id` unique
- **Rows / coverage:** 12,000 events per base outside the embargo, split × tier × month, the smallest u = sha256('2026:ablation:<event_id>') per stratum (24,000 rows)
- **Availability:** keys only
- **sha256:** `4b21ca97cb414c52d76e2ed936e97f7fd32f92e0e2190446fc7d47197269371d`

### `work/states/samples/unmasked_robustness.parquet`
- **Producer:** `newsaction.production.ablations.build_unmasked` (S8)
- **Inputs:** NA-04's builder inputs (`states.build.load_inputs`), `work/baselines/state_articles.parquet` (the articles each masked D0 state kept), `work/dm/production/ablation_sample.parquet`
- **Schema:** NA-04's state columns (`event_id`, …, `masked` false, `state_json`, `state_sha256`, tokens, `third_party_ok_all`)
- **Key:** `event_id` unique
- **Rows / coverage:** the unmasked twins of the 12,000 sampled Call A D0 events; the masked rebuild equals NA-04's state for every one and the 439 NA-04 twins in the sample are unchanged
- **Availability:** D0 (09:15 ET); unmasked: sent only under the registered probe tag `unmasked_robustness` (PREREG §11.6), third-party-OK articles only
- **sha256:** `1092922246b9adafb5a7e2084808c498aadb1d1e882a57db2d3948f3abf33c25`

### `work/dm/production/liquid_d1_ultra_ablations.parquet`
- **Producer:** `newsaction.production.ablations.run` (S8)
- **Inputs:** `work/dm/production/ablation_sample.parquet`, the Call B D2 states, `work/states/samples/unmasked_robustness.parquet`; `cache/decisions.sqlite` (chunk NA-11)
- **Schema:** `newsaction.production.run.readings` plus `ablation` (`b2_no_news`, `b2_shuffled`, `a0_unmasked`) and `donor`
- **Key:** (`ablation`, `event_id`) unique
- **Rows / coverage:** d1-ultra, core battery: 12,000 events per ablation (36,000 rows)
- **Availability:** D2 (Call B) / D0 (Call A); probes, compared with the S6 readings of the same events
- **sha256:** `0a53fae8615a3dc3c980793b673e85c4f8fe03b9ce04cc26031a28bef025b4f0`

### `work/dm/production/llm_sample_test.parquet`
- **Producer:** `newsaction.production.llm_test.write_sample` (S8)
- **Inputs:** `work/states/callA_d0_E3.parquet`, `work/events/events_d0.parquet` (NA-09's `d0_events`)
- **Schema:** `event_id`, `tier`, `month` and the client's state columns
- **Key:** `event_id` unique
- **Rows / coverage:** 2,000 test D0 events outside the embargo, tier × month, seed 2026 (NA-09's val-B rule, PREREG §10.7)
- **Availability:** D0 (09:15 ET), masked
- **sha256:** `ae28772ca585086b1fb5a70fad93d7fc7546e9f75c848b1bc070e0d618ecf7bc`

### `work/dm/production/llm_test.parquet`
- **Producer:** `newsaction.production.llm_test.run` (S8)
- **Inputs:** `work/dm/production/llm_sample_test.parquet`; NA-09's prompt and settings; `cache/decisions.sqlite`
- **Schema:** NA-09's common prediction schema (`baselines.schema`)
- **Key:** `event_id` unique
- **Rows / coverage:** mistralai/mistral-nemo's valid answers on the 2,000 test events (invalid ones counted in `artifacts/NA-11/llm_test.json`)
- **Availability:** D0 (09:15 ET)
- **sha256:** `9930c454e27b2c52b68ec2743eafd498c1828dcd55fa6b0007b5f069b25b26fb`

### `work/dm/production/price_only_test.parquet`
- **Producer:** `newsaction.production.price_only_test.run` (S8)
- **Inputs:** `work/baselines/models/price_only_{e5,abs_z_cc}.json` (NA-09), `work/states/context_company.parquet`, `work/panel/panel_public.parquet`, the 2026 `react_z_vol` of `reactions.build_reactions` (lock)
- **Schema:** NA-09's common prediction schema (`baselines.schema`)
- **Key:** `event_id` unique
- **Rows / coverage:** every test Call A D0 event (13,977); the same code reproduces NA-09's val-A/val-B rows exactly
- **Availability:** D0 (09:15 ET): t−1 context, z_vol of the previous session
- **sha256:** `613d555227462262d39ce7534582efd45c070259ed51732ae65dee61f188a145`

### `artifacts/NA-11/ablation_runs.json`
- **Producer:** `newsaction.production.ablations.run` (S8)
- **Inputs:** `work/dm/production/liquid_d1_ultra_ablations.parquet`
- **Schema:** list of {ablation, requests, ok, valid, cost}
- **Key:** one entry per ablation
- **Rows / coverage:** the S8 ablation batches
- **Availability:** counts and cost only
- **sha256:** `7ce01d0f5ed9a52d3cd1729f6d6333259485b050bfb81a7757db04b0a0e6ae2a`

### `artifacts/NA-11/llm_test.json`
- **Producer:** `newsaction.production.llm_test.run` (S8)
- **Inputs:** `work/dm/production/llm_test.parquet`
- **Schema:** {model, requests, send, projected_usd, cap_usd, budget_left_usd, answered, valid, invalid, spent_usd_this_run, spent_usd (the ledger's total under the batch's tag)}
- **Key:** one object
- **Rows / coverage:** the LLM baseline's test batch
- **Availability:** counts and cost only
- **sha256:** `33f6d8c61dc7ff00961f23698752e318ca157dd4f9a1549976125a7749e72964`

### `artifacts/NA-11/freeze.json`
- **Producer:** `newsaction.production.freeze` (S3) through `lock.freeze`
- **Inputs:** the freeze files (`lock.FREEZE_FILES`): PREREG before its Deviations log, `configs/*.yaml`, `panel/{targets,reactions}.py`, `analysis/{spec,inference,shapley,metrics}.py`
- **Schema:** {version, hash, files, freeze_files, deviations_log {bytes, sha256}, git_sha, ts, note}
- **Key:** one object
- **Rows / coverage:** the PREREG §4.4 freeze record (hash `523e7589…`; the freeze time is its `ts`)
- **Availability:** written once, before any 2026 state was built or sent
- **sha256:** `f5801cd802de0bee776cbe69e0d49c3904e812d7d3b1866ec2bc0903f714663e`

### `artifacts/NA-11/canary_check.csv`
- **Producer:** `newsaction.production.canary_check.compare_now` (S5, end of S6)
- **Inputs:** `artifacts/NA-05/canary_v1.jsonl`, `artifacts/NA-11/canary_baseline_na11.parquet`; `cache/decisions.sqlite`
- **Schema:** model, phase, repeat_idx, cells, mean_abs_dp_train_a, mean_abs_dp_all, max_abs_dp_all, repeat_noise, rule, stop, builds
- **Key:** (model, phase) unique
- **Rows / coverage:** the canary against the NA-11 baselines under the `configs/dm.yaml` rule: S5 (repeat 10) and the end of S6 (repeat 11)
- **Availability:** train-period canary items; no test data
- **sha256:** `eebb9c72756d82da900929a29207934a369b5c259b874d67bbf04d3dbef98062`

### `artifacts/NA-11/canary_drift_check.csv`
- **Producer:** `newsaction.production.canary_check.drift_now` (end of S6)
- **Inputs:** 100 NA-06 stage-2 val-A Call A states per model; `cache/decisions.sqlite`
- **Schema:** model, phase, repeat_idx, drift_mean_abs_dp_vs_na06, drift_pairs, repeat_noise, fires, builds_na06, builds_now
- **Key:** (model, phase) unique
- **Rows / coverage:** the pre-freeze drift check repeated once at the end of S6 (repeat 3)
- **Availability:** val-A states; no test data
- **sha256:** `3987b819818d1b1bceed28a1c2ac93c3699492a8d2565859bfc87cac7f791f16`

### `artifacts/NA-11/canary_end_s6.json`
- **Producer:** the end-of-S6 run of `canary_check.compare_now`, `drift_now` and `judge`
- **Inputs:** `artifacts/NA-11/{canary_check.csv,canary_drift_check.csv,canary_drift_na06.csv}`, the S6 readings' model builds
- **Schema:** {canary, drift, production_builds, verdicts, reconcile}
- **Key:** one object
- **Rows / coverage:** the end-of-S6 verdict per model under the post-freeze §15 rule
- **Availability:** no test data
- **sha256:** `525b71ff40f05018149cef6f41e6e668c2749bae0cfb9be02dbe585ac0bdb33a`

### `artifacts/NA-11/production_runs_api_comparators_market.json`
- **Producer:** `newsaction.production.run.run` (S6)
- **Inputs:** `work/dm/production/*_api_comparators_market.parquet`
- **Schema:** list of {model, component, requests, ok, valid, cost}
- **Key:** one entry per component
- **Rows / coverage:** the S6 batches before the retry pass
- **Availability:** counts and cost only
- **sha256:** `c3a020cc22d4ab4b8efb29faf3e97e98c7cb3ea215299d8311bb4650c7f185fb`

### `artifacts/NA-11/production_retry.json`
- **Producer:** `newsaction.production.run.retry` (S6, operator decision)
- **Inputs:** `work/dm/production/*_api_comparators_market.parquet`
- **Schema:** list of {model, component, retried, ok_now, valid_now, statuses_before} and per model {component: '(not retried)', failed, statuses}
- **Key:** one entry per retried component, one per model for what was left
- **Rows / coverage:** the one retry pass over S6's transient failures (429, 5xx, transport)
- **Availability:** counts only
- **sha256:** `e069281eac36b9903500da695537e895cd43821a0731e226d2f75a7a8d9f9bc8`

### `artifacts/NA-11/production_summary.csv`
- **Producer:** `newsaction.production.summary.run` (S9)
- **Inputs:** every NA-11 reading file, NA-08's instrument files, the state files (eligible events)
- **Schema:** model, source, split, eligible, rows, answered, valid, coverage, invalid_rate, latency_p50_ms, latency_p95_ms, cost_usd
- **Key:** (model, source, split) unique
- **Rows / coverage:** coverage, invalid rate, latency and cost per model, reading and split (AC3)
- **Availability:** counts only; no outcome
- **sha256:** `39d70b860badb73cdf4ebc39345cb47d7af0562489e7d8bdce888479515db531`

### `artifacts/NA-11/production_spend.csv`
- **Producer:** `newsaction.production.summary.spend` (S9)
- **Inputs:** `ledgers/spend.jsonl` (chunk NA-11, spend records)
- **Schema:** model, purpose, requests, usd
- **Key:** (model, purpose) unique
- **Rows / coverage:** NA-11's ledger spend per model and purpose (AC5)
- **Availability:** spend only
- **sha256:** `b268692da089e297836023cb61dc31fbc7404cc5cc5717abe347ffce72b23971`

### `artifacts/NA-11/probes_val_a.csv`
- **Producer:** `newsaction.production.probes.run`
- **Inputs:** `artifacts/NA-06/leaderboard.csv`, `work/dm/production/local_laya_typed_decisions_probes.parquet`, `work/kaggle/predictions/{laya_fin,anchor}_probes.parquet`, NA-08's val-A predictions
- **Schema:** model, kind, flip_rate, flip_pairs, ic_masked(_t), ic_unmasked(_t), unmasked_minus_masked(_t), ic_shuffled(_t), screen thresholds
- **Key:** model unique
- **Rows / coverage:** the operator's disclosed val-A probes beside NA-06's API screens (not hypotheses)
- **Availability:** val-A only
- **sha256:** `787ad832275982dfdc1206872d254c5409b1ea4039985fd1628743f71ed03aa1`

### `artifacts/NA-11/key_usage.json`
- **Producer:** `newsaction.production.record_key_usage`
- **Inputs:** OpenRouter GET /api/v1/key and /api/v1/credits; `ledgers/spend.jsonl`
- **Schema:** list of {label, ts, usage, usage_daily, limit, limit_remaining, is_free_tier, total_credits, total_usage, remaining, ledger_chunk_usd}
- **Key:** one entry per check, in time order
- **Rows / coverage:** the key's usage before and after each NA-11 paid batch (operator preamble item 6)
- **Availability:** account metadata; no data
- **sha256:** `a824467a5b36a1e01549c089c5a53e2deb5863f7db582bf05cdb9398a716435b`

### `work/kaggle/predictions/laya_fin_test_callB.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-laya-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/test_callB.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** laya_fin on test_callB
- **Availability:** the states' decision points; predictions only
- **sha256:** `64cf0dadbf501b37d0a924407db557ee3dc442b39c52bbf0dd5c029286d17a11`

### `work/kaggle/predictions/laya_fin_val_callB_d1.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-laya-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/val_callB_d1.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** laya_fin on val_callB_d1
- **Availability:** the states' decision points; predictions only
- **sha256:** `c724b1557d5c80909a7d5badd0487d34bde1967a04cfcd95f8fa604fb1449cb5`

### `work/kaggle/predictions/laya_fin_robustness_callA.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-laya-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/robustness_callA.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** laya_fin on robustness_callA
- **Availability:** the states' decision points; predictions only
- **sha256:** `029466c9604108bccfa6754b396e7d2079cd94f9dc09686a386170d267a25e1f`

### `work/kaggle/predictions/laya_fin_probes.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-laya-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/probes.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** laya_fin on probes
- **Availability:** the states' decision points; predictions only
- **sha256:** `bc58ea501ca3e5cce2c8fb267cbcd6be6015cef2a23267c9394f14ef9cc3356b`

### `work/kaggle/predictions/anchor_test_callB.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-anchor-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/test_callB.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** anchor on test_callB
- **Availability:** the states' decision points; predictions only
- **sha256:** `e214885469887ce927dfbae722b3ca187562a41384665bf43a50725c5642f8d9`

### `work/kaggle/predictions/anchor_val_callB_d1.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-anchor-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/val_callB_d1.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** anchor on val_callB_d1
- **Availability:** the states' decision points; predictions only
- **sha256:** `9de67c2255c0a7ddb772566b57d3b9991d0268cb32544bba7673493c30a18fb3`

### `work/kaggle/predictions/anchor_robustness_callA.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-anchor-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/robustness_callA.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** anchor on robustness_callA
- **Availability:** the states' decision points; predictions only
- **sha256:** `ebfab81e21d3a1f785e9af0d33035f65a1d1f71892996fd6f526e7c9ef5ad66e`

### `work/kaggle/predictions/anchor_probes.parquet`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the Kaggle kernel `newsaction-na11-infer-anchor-s13` (inference only, the frozen pin) on `work/kaggle/dataset_na11/probes.parquet`; its record and outputs verified
- **Schema:** NA-08's instrument schema plus `variant`
- **Key:** (`event_id`, `call`, `window`, `variant`, `question`) unique
- **Rows / coverage:** anchor on probes
- **Availability:** the states' decision points; predictions only
- **sha256:** `178d34650f9586487f1838ad96b82c7d3e58fbc28204fe5b9946eaabf8370567`

### `artifacts/NA-11/kaggle_import_laya-s13.json`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the kernel `newsaction-na11-infer-laya-s13`'s outputs
- **Schema:** {file: rows} per imported file
- **Key:** one object
- **Rows / coverage:** what the S7 import of laya-s13 wrote
- **Availability:** counts only
- **sha256:** `4ee4979c19c77091eaf4c3003fc069ec2f0acaa9f29eb5ed3759648127bf6e56`

### `artifacts/NA-11/kaggle_import_anchor-s13.json`
- **Producer:** `newsaction.production.kaggle_infer.import_run` (S7)
- **Inputs:** the kernel `newsaction-na11-infer-anchor-s13`'s outputs
- **Schema:** {file: rows} per imported file
- **Key:** one object
- **Rows / coverage:** what the S7 import of anchor-s13 wrote
- **Availability:** counts only
- **sha256:** `d429ed785674a6fba4404946e38a88d633edbeabacda2c121d45ff8ae7087738`

## NA-12 — unblinding and the pre-registered analyses (`newsaction.analysis`)

### `work/analysis/targets_test.parquet`
- **Producer:** `newsaction.analysis.unblind.run` (once, `NA_UNBLIND=1`)
- **Inputs:** `panel.targets.build_targets` and `build_d1_targets` ("test"), `panel.reactions.build_reactions` (D2, D1) and `panel.build.test_returns_panel`, all on the blinded files through `newsaction.lock` (purposes targets and reactions, logged in `ledgers/test_access.jsonl`); `analysis.slot_path`
- **Schema:** ids (`session`, `symbol_id`, `split`, `company_id`, `member`, `is_rep`, `sector`, `half_day`); same-day `r_cc`, `r_spy_cc`, `ar_*`, `sigma_*`, `z_cc`, `z_on`, `z_id`, `z_vol`; `targets.py`'s columns (`y0`, `y2`, `e5`, `e5_lvl`, `car_lvl_*`, `fwd_lvl_*`, `ar_o*`, `z_o*`, …); `g_d2`, `g_d2_lvl`; D1 `y1`, `fwd_lvl_10_*`, `g_d1`, `g_d1_lvl`, `car_lvl_10`; the 30-minute path `car_lvl_b0` … `car_lvl_b11`
- **Key:** (`session`, `symbol_id`) unique
- **Rows / coverage:** every test-period row of the test returns panel (members and the post-exit rows)
- **Availability:** the test period's outcomes, after unblinding (NA-12 S1); the only file 2026 outcomes are read from afterwards
- **sha256:** `c6b7cf4d4c4c76ce19bd1dca752471671e5146d309ba497228ca00c7e805122e`

### `work/analysis/price_only_d2_test.parquet`
- **Producer:** `newsaction.analysis.price_only_d2.run`
- **Inputs:** NA-09's `work/baselines/models/price_only_y2.json`; `work/states/callB_d2_E3_test.parquet`, `work/events/events_d2.parquet`, `work/states/context_company.parquet`, `work/panel/panel_public.parquet`, `work/analysis/targets_test.parquet` (G, z_on, z_vol of t)
- **Schema:** NA-09's common prediction schema (call B, `y_hat`)
- **Key:** `event_id` unique
- **Rows / coverage:** the price-only baseline's D2 test predictions for every test Call B D2 state; the same code first reproduces NA-09's val-A and val-B D2 predictions exactly
- **Availability:** D2 (after close(t)); built from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `b94a93b9bdb646614261e145110b79bfa338f26e915cb1df84bb6f9485886034`

### `work/analysis/h3_predictions.parquet`
- **Producer:** `newsaction.analysis.run_all.shapley`
- **Inputs:** the D2 analysis frames; `spec.ridge_protocol` per coalition (fit val-B, λ val-A)
- **Schema:** `event_id`, `session`, `company_id`, `tier`, `y2`, `pred_<coalition>` (7), `model`
- **Key:** (`model`, `event_id`) unique
- **Rows / coverage:** H3's seven coalition predictions of y2 per test D2 event for Laya-Fin, the anchor and d1-ultra; `spec.shapley_tables` on them reproduces H3's tables (checked)
- **Availability:** test predictions; y2 from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `178119aadf649eb0c7870ed594c4eae1f1fecc99fb23aefb431522c1442318b4`

### `work/analysis/frame_d0_laya_fin.parquet`
- **Producer:** `newsaction.analysis.run_all.write_frames`
- **Inputs:** `analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the frozen V / Ñ maps
- **Schema:** the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) dropped
- **Key:** `event_id` unique
- **Rows / coverage:** the D0 analysis frame of laya_fin on val-A, val-B and test, for the verifier's recomputation (PRD NA-12 verification 3, 4b)
- **Availability:** val rows public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `f290b7c87eececbb33070293f2ac95d7e3a7462676ed6326ed0a0e0b55adbe24`

### `work/analysis/frame_d2_laya_fin.parquet`
- **Producer:** `newsaction.analysis.run_all.write_frames`
- **Inputs:** `analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the frozen V / Ñ maps
- **Schema:** the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) dropped
- **Key:** `event_id` unique
- **Rows / coverage:** the D2 analysis frame of laya_fin on val-A, val-B and test, for the verifier's recomputation (PRD NA-12 verification 3, 4b)
- **Availability:** val rows public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `ad80220b41dced9f67429ea7b7680e2f67e0c26ac273ee092ca597c59f92c11b`

### `work/analysis/frame_d0_anchor.parquet`
- **Producer:** `newsaction.analysis.run_all.write_frames`
- **Inputs:** `analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the frozen V / Ñ maps
- **Schema:** the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) dropped
- **Key:** `event_id` unique
- **Rows / coverage:** the D0 analysis frame of anchor on val-A, val-B and test, for the verifier's recomputation (PRD NA-12 verification 3, 4b)
- **Availability:** val rows public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `2ac22b3a3ad27caff49cefe5947aaf78b06da60419796ced22ad5ef0505ffa2e`

### `work/analysis/frame_d2_anchor.parquet`
- **Producer:** `newsaction.analysis.run_all.write_frames`
- **Inputs:** `analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the frozen V / Ñ maps
- **Schema:** the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) dropped
- **Key:** `event_id` unique
- **Rows / coverage:** the D2 analysis frame of anchor on val-A, val-B and test, for the verifier's recomputation (PRD NA-12 verification 3, 4b)
- **Availability:** val rows public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `5946721294d78ead8603664c3b927fe43e3fad5c851d567574f3b3b8369d0ab9`

### `work/analysis/frame_d0_d1_ultra.parquet`
- **Producer:** `newsaction.analysis.run_all.write_frames`
- **Inputs:** `analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the frozen V / Ñ maps
- **Schema:** the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) dropped
- **Key:** `event_id` unique
- **Rows / coverage:** the D0 analysis frame of d1_ultra on val-A, val-B and test, for the verifier's recomputation (PRD NA-12 verification 3, 4b)
- **Availability:** val rows public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `11cbfbd5896ecfb807c4408eea18bff127af494ee7923557229e67be68cbf5b7`

### `work/analysis/frame_d2_d1_ultra.parquet`
- **Producer:** `newsaction.analysis.run_all.write_frames`
- **Inputs:** `analysis.frames.base` (events, public targets, `targets_test`), the model's readings, the frozen V / Ñ maps
- **Schema:** the spec's analysis-frame columns (`analysis.spec` docstring); list columns (Q1 probabilities) dropped
- **Key:** `event_id` unique
- **Rows / coverage:** the D2 analysis frame of d1_ultra on val-A, val-B and test, for the verifier's recomputation (PRD NA-12 verification 3, 4b)
- **Availability:** val rows public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `977524c65410c63a344c75046aa0dfe1a8f963bca7fcb115020da66a8880b0fd`

### `artifacts/NA-12/unblind.json`
- **Producer:** `newsaction.analysis.unblind.run`
- **Inputs:** the unblinding run
- **Schema:** the freeze hash at unblinding, the run's "targets" ledger entries, the output's sha256, counts
- **Key:** one record
- **Rows / coverage:** the evidence of the one access sequence (AC1); counts only
- **Availability:** after unblinding
- **sha256:** `54cadb6d484b6e24b50e75428d2423a99507518c0c8dfaecc17fbc257a711e11`

### `artifacts/NA-12/unblind_rehearsal.json`
- **Producer:** `newsaction.analysis.unblind.rehearse`
- **Inputs:** `work/panel/panel_public.parquet`, `work/panel/intraday_public.parquet`, the public bars
- **Schema:** the consistency gaps, the largest difference against the public panels, counts
- **Key:** one record
- **Rows / coverage:** the val-B rehearsal of the unblinding's assembly (59 columns reproduced)
- **Availability:** public (val-B); written before unblinding
- **sha256:** `448ecd8c7e3cc3d5e68c2c182e14c892c2921a253d37b8d908df4d7c8402447b`

### `artifacts/NA-12/results/exploratory_d0_signal.json`
- **Producer:** `newsaction.analysis.exploratory.run` (operator request after unblinding)
- **Inputs:** the D0 analysis frames (`run_all.build_ctx`), NA-09's `work/baselines/{sentiment,tags_gbm}.parquet`, covered member-days (`frames.member_days`), `configs/analysis.yaml` (frozen daily IC, Newey–West lags, bootstrap)
- **Schema:** `earnings` and `tier` (`spec.ic_targets` per group; earnings − rest daily difference), `monthly` (month means, F test, implied monthly SE), `company` (per-company Spearman SD and its shuffle null), `market_state` (tercile cut-offs; daily IC by tercile, high − low)
- **Key:** nested by analysis, signal and split
- **Rows / coverage:** exploratory, outside every family (no hypothesis, no claim): where the D0 signal lives for Laya-Fin, d1-ultra, span-02, drex-v2.0, Laya zero-shot and the vendor sentiment and tags-GBM baselines on val-A, val-B and test outside the embargo
- **Availability:** val-A and val-B public; test outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `6e4da0e60ad37ff8871bc9945566895569d056b3be2c1c99c79b52a05312e446`

### `artifacts/NA-12/results/battery.json`
- **Producer:** `newsaction.analysis.run_all.battery`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `battery` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `d260a106afe6b2e4dd2b7b9e9cdf00facbccba41448ceb55bf065acaf5163bae`

### `artifacts/NA-12/results/calibration.json`
- **Producer:** `newsaction.analysis.run_all.calibration`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `calibration` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `18fda0ff63ee4b03a4f3f9adffde5c93fff22f04a6047fad642d246a6c34bce6`

### `artifacts/NA-12/results/comparison.json`
- **Producer:** `newsaction.analysis.run_all.comparison`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `comparison` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `2a2522b79be80575760625d82044e5cb182d39f3528c3b89a1692be615749ab8`

### `artifacts/NA-12/results/convergence.json`
- **Producer:** `newsaction.analysis.run_all.convergence`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `convergence` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `68445fd0e89a7e9683d68e36af58908cd2bf39aeafa008f11d15d8d11ac3e804`

### `artifacts/NA-12/results/explanation.json`
- **Producer:** `newsaction.analysis.run_all.explanation`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `explanation` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `adbc2161148f884d8e83ff286907c80070efbdb0703a49cf508f0d53dfa38a93`

### `artifacts/NA-12/results/exploratory.json`
- **Producer:** `newsaction.analysis.run_all.exploratory`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `exploratory` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `9fe02c991fe35afd469f3e12721d9a330343ecd95899a79d1b2958262c7c1fae`

### `artifacts/NA-12/results/figures.json`
- **Producer:** `newsaction.analysis.run_all.figures`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `figures` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `977ce98ea3f171af8d4884580144eee80178a27bd8f5e0b3630f97b997856fa4`

### `artifacts/NA-12/results/heterogeneity.json`
- **Producer:** `newsaction.analysis.run_all.heterogeneity`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `heterogeneity` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `c88192fb0f1517f0d778581b2368de72918fbdcb60591c61b3856cde1cf5e86d`

### `artifacts/NA-12/results/monthly_ic.json`
- **Producer:** `newsaction.analysis.run_all.monthly_ic`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `monthly_ic` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `f8685e6a9aa619d761654d93b8175c9dd07e8946536c05cd7e1ecb2440efb7e2`

### `artifacts/NA-12/results/primary.json`
- **Producer:** `newsaction.analysis.run_all.primary`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `primary` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `17e2243f698b339c37ac2c9297641b2bb7492cb3bcd974894ff202e8dceb477b`

### `artifacts/NA-12/results/robustness.json`
- **Producer:** `newsaction.analysis.run_all.robustness`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `robustness` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `c4b1af585386d610ac15d8b9be916c17a30212883692b8f24cd546f453fed710`

### `artifacts/NA-12/results/secondary.json`
- **Producer:** `newsaction.analysis.run_all.secondary`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `secondary` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `56a9983862e6b2065f9c5200fddb4bcf8e70dbd74a318f6c858eae3fc751dc35`

### `artifacts/NA-12/results/shapley.json`
- **Producer:** `newsaction.analysis.run_all.shapley`
- **Inputs:** the analysis frames (`analysis.frames`), `configs/analysis.yaml` (frozen)
- **Schema:** the frozen `spec` functions' result dicts (JSON; NaN as null, ±∞ as strings)
- **Key:** nested by model and test
- **Rows / coverage:** S2 section `shapley` on the test split
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `56ada3698d66f00ec4b3db03b4adb95dbd738c3af8bc66303cb4264325b62a8e`

### `artifacts/NA-12/figure_data/appendix_reliability.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `appendix_reliability`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `5ca5ee4708886246446110198f8822cb037dcec94a1e80673f2f2196b2168293`

### `artifacts/NA-12/figure_data/fig1_rg_class_paths.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `fig1_rg_class_paths`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `b221d493486798811dd3bb03db5966bc6caadf62ca534891a7ae53ab9d5f2a97`

### `artifacts/NA-12/figure_data/fig1_v_decile_paths.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `fig1_v_decile_paths`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `50fda57b88044198a82805aa8265e5fee8503e3d9752647dc5b2c7c4d1d9c07b`

### `artifacts/NA-12/figure_data/fig2_drift_vs_g.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `fig2_drift_vs_g`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `77851140502935c1c5892e21bc58643a2f8679f4e02e9589c7348aed6b1e5808`

### `artifacts/NA-12/figure_data/fig4_monthly_ic.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `fig4_monthly_ic`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `b77094efc12a1049d5652db4085effbb7896db53f7d85e8859271f5999cd0ccd`

### `artifacts/NA-12/figure_data/fig5_shapley_shares.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `fig5_shapley_shares`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `5e31b18d8165b9d415946ea8ae22db1f4b101987f69800be2b53a3faa72af6e4`

### `artifacts/NA-12/figure_data/fig8_explanation_ladder.csv`
- **Producer:** `newsaction.analysis.run_all` (`figures`, `monthly_ic`, `calibration`), `analysis.figdata`
- **Inputs:** the analysis frames and the S2 results
- **Schema:** long CSV (the plotted values with their group, point, mean, se, n)
- **Key:** one row per plotted value
- **Rows / coverage:** figure data `fig8_explanation_ladder`
- **Availability:** test (Figure 4: val-A, val-B, test); outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `bc49efc5abe64340a8fff622214873729d0d78facefdd97f968e05de6ba843e7`

### `artifacts/NA-12/tables/index.json`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** keys.json: "table/key/column" → value; index.json: tables, columns, notes
- **Key:** one file
- **Rows / coverage:** table file `index.json`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `f231b1f5de4cf608a6ef9a9a6b41ac412b7cf13fe2d6ffad881288805b1abe76`

### `artifacts/NA-12/tables/keys.json`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** keys.json: "table/key/column" → value; index.json: tables, columns, notes
- **Key:** one file
- **Rows / coverage:** table file `keys.json`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `81ad60cdeaa61b5ff5483cd73308d6390e13806e34a95aff469261f1c32bb576`

### `artifacts/NA-12/tables/t10_explanation_ladder.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t10_explanation_ladder.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `d58de25f8b3bc8d38cd0722904e8afb121cb38be769cdcd268f44e1c80fe51e2`

### `artifacts/NA-12/tables/t10_explanation_ladder.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t10_explanation_ladder.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `4458a376672369506e473818a5eebfe999c82f48f703aef2235f6f361f72119c`

### `artifacts/NA-12/tables/t11_explanation_share_theta.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t11_explanation_share_theta.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `4ad3c9e9feff9fcd6fc0657ee34cb92b6f1c383b27e07577936555506498978e`

### `artifacts/NA-12/tables/t11_explanation_share_theta.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t11_explanation_share_theta.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `1f56af7f88148fdde512c98eefe39ca2086e6e26a2b65f68e85a9d4c0f7e8d3a`

### `artifacts/NA-12/tables/t12_question_battery.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t12_question_battery.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `5b29c92473bae8d038757d10f92c134adbac4618c1baad4a0efe86e29bd48fbc`

### `artifacts/NA-12/tables/t12_question_battery.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t12_question_battery.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `0ce3b335a0a6618f64624a54446bc69ed02ecf4f7c73a46ed7e37658ac01cda3`

### `artifacts/NA-12/tables/t13_shapley.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t13_shapley.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `a4fec4309891b7241386a7ce95059e736c2d4b87e7aa58cf6a5ccb0b43bb2992`

### `artifacts/NA-12/tables/t13_shapley.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t13_shapley.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `2368ba77d18ec69a6a9a9862240935d9c1fc2bc54e41b92c2c546d9f8819f07a`

### `artifacts/NA-12/tables/t14_model_comparison.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t14_model_comparison.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `1f09db3d94b5046e4ab761cd55bd32dccef063534d8ed4d2d0d2935adf63c0dd`

### `artifacts/NA-12/tables/t14_model_comparison.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t14_model_comparison.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `e690edec69b611bad96d7b1f2e61ff20f070c3a9930414983830154f6c5737af`

### `artifacts/NA-12/tables/t15_calibration.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t15_calibration.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `c7fa83ab91049a6a328f397ebff93fe19fa9aa892b81ae08af04cebf55acefdc`

### `artifacts/NA-12/tables/t15_calibration.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t15_calibration.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `b952825eaa27cd1cede66a9d98ed876ea6f46586f49320759f3d0665be03680e`

### `artifacts/NA-12/tables/t16_robustness.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t16_robustness.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `5f2017bd953fc130ea3fb542f57612ab4c2fd6a4d7192612b42c0e0853ca8485`

### `artifacts/NA-12/tables/t16_robustness.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t16_robustness.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `d1f6568d33029ddf32020cc7f93d77b0b2f8d1b1f8bb4ac537bd0b705a5c8da9`

### `artifacts/NA-12/tables/t17_sector_exploratory.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t17_sector_exploratory.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `97dd083818aeb747ad3c16923b867b0ed6d0f0b616d0599ccc181c5b45c73d75`

### `artifacts/NA-12/tables/t17_sector_exploratory.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t17_sector_exploratory.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `9c75875f03220abf7e80c0f2a76707e7b80d0b3b14f1d2b8082a93031531c1ea`

### `artifacts/NA-12/tables/t18_probes_val_a.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t18_probes_val_a.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `114b88a202d89e4916eecbfd12cb19c667f99c181e6d600addef7201484f4fd9`

### `artifacts/NA-12/tables/t18_probes_val_a.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t18_probes_val_a.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `2d3b2da837297e3a19c51c41edc649ae86188ef2490728cb051e9e39ed32b0ff`

### `artifacts/NA-12/tables/t19_monthly_ic.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t19_monthly_ic.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `6ee63d6d4ac06908411d75fddb3170bcdb6855de2b44889db48d9264bb68046f`

### `artifacts/NA-12/tables/t19_monthly_ic.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t19_monthly_ic.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `87098f6d50799dd9834efe1af19273988834a2fbae24756ac1bfda87ac315ee2`

### `artifacts/NA-12/tables/t1_primary.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t1_primary.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `a39e2f671ba9805c9381f28bb2db820fafc8aa83bde9192872f754ff342ae3c2`

### `artifacts/NA-12/tables/t1_primary.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t1_primary.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `2f3bb04d13c789f75a65de05493d643c9bbe01b43c8ee9bc7927d2eb6414a2dd`

### `artifacts/NA-12/tables/t1b_primary_by_model.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t1b_primary_by_model.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `37cf7a2c0739482d26afc019866a3a57054d25a24ec97554eb7792fcc4c6d676`

### `artifacts/NA-12/tables/t1b_primary_by_model.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t1b_primary_by_model.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `925624c1ad4eafffb25b36513d486b3324c8201ba65b7ea64015996ccf9a8179`

### `artifacts/NA-12/tables/t2_h2_over_under.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t2_h2_over_under.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `8bcb2c11f32a8574b4c70dbd21d211c31f5bf4884c731e4c99b6dafe0fe1306a`

### `artifacts/NA-12/tables/t2_h2_over_under.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t2_h2_over_under.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `08e9a6a7a034b159a5eb94f543f956f9e31d2d044d06bc1df23893371050f4ab`

### `artifacts/NA-12/tables/t3_ic.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t3_ic.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `dae94be5f0635c9f7914619bc1bdb4541729ad29d2e6f2555b9a8ec4c544ef41`

### `artifacts/NA-12/tables/t3_ic.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t3_ic.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `cf62889f75006e2f611e425bcd5094738ba69767463c6f3ddb417acfa9d7a2e0`

### `artifacts/NA-12/tables/t4_secondary.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t4_secondary.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `c474f9c40628f2da101a9c92ed41aec9b53012837fed16bc7a15c81f6f5b3067`

### `artifacts/NA-12/tables/t4_secondary.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t4_secondary.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `5d7c684611dd9b95536126a827df107c5326a3f9600bf24d67300d614760763d`

### `artifacts/NA-12/tables/t5_heterogeneity.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t5_heterogeneity.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `126066b207041c66d4e0b83cee5d8fec1bd6165a705e6578243e60c9562ba178`

### `artifacts/NA-12/tables/t5_heterogeneity.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t5_heterogeneity.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `24c54d1a80b9ba88d0e3d84f7d2e2e1caf4865941d20d6f46e0bb007841bdd83`

### `artifacts/NA-12/tables/t6_convergence_ladder.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t6_convergence_ladder.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `e2b1ff300300b610b187c12c5ea019d89e9fd13c69600306979245b296db7901`

### `artifacts/NA-12/tables/t6_convergence_ladder.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t6_convergence_ladder.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `a389df64fe52fe4dede235a94be983e624a19496030b546c2e786e7765e4cf3e`

### `artifacts/NA-12/tables/t7_gap_closure.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t7_gap_closure.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `33062977043288242b154d2ab05d7097f9211457fe7ecb6465b426daa09a8d48`

### `artifacts/NA-12/tables/t7_gap_closure.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t7_gap_closure.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `265ab3c9e39af4c9311c1d9bf864ad05c2f154681362ac2ceaa3b0cf8982e0c2`

### `artifacts/NA-12/tables/t8_tracking_error.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t8_tracking_error.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `43ea9867777802a24d0d7d1ca4331f39c99e210428b1242ceef463bae84ef80b`

### `artifacts/NA-12/tables/t8_tracking_error.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t8_tracking_error.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `eeb92483707d17cc511a7dde8f50bc20d97f6a160e76a4bef976ba2526b1ee3c`

### `artifacts/NA-12/tables/t9_convergence_cuts.csv`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** a `key` column (unique) and the table's columns
- **Key:** `key`
- **Rows / coverage:** table file `t9_convergence_cuts.csv`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `a644adda42c8717329bdefe50f5b302895c6729ad119ddda3811e4dc5fbaa354`

### `artifacts/NA-12/tables/t9_convergence_cuts.tex`
- **Producer:** `newsaction.analysis.tables.write`
- **Inputs:** `artifacts/NA-12/results/*.json`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** table file `t9_convergence_cuts.tex`
- **Availability:** test; outcomes from the test period's outcomes, after unblinding (NA-12 S1)
- **sha256:** `c89ddfc721e737bbb855f4b4070774ea3446d63c6d8eefda1ba7ded414fdfccd`

## NA-13 — strategies and economic significance (`newsaction.strategy`)

### `work/strategy/market_public.parquet`
- **Producer:** `newsaction.strategy.market public`
- **Inputs:** `panel.build.assemble` on the public inputs; `work/panel/intraday_public.parquet`
- **Schema:** `session`, `symbol_id`, `company_id`, `split`, `member`, `is_rep`, `raw_open`, `raw_close`, `adj_close`, `r_cc`, `r_id`, `r_spy_cc`, `r_spy_id`, `beta_m`, `ar_cc`, `adv20`, `ma20`, `ma50`, `ma20_prev`, `ma50_prev`, `p10`, `r_10c`, `r_spy_10c`
- **Key:** (`session`, `symbol_id`) unique
- **Rows / coverage:** val-A and val-B member and post-exit rows; equal to `panel_public` on the shared columns
- **Availability:** returns of session t are known at its close; `beta_m`, `adv20` end at t−1
- **sha256:** `197029706fc8a5233672bf4af41ffce3121e0ea7a51a81d16b4b7cb95a7875f7`

### `work/strategy/market_test.parquet`
- **Producer:** `newsaction.strategy.market test` (once, `NA_UNBLIND=1`)
- **Inputs:** `newsaction.lock` (purpose targets) reads of the blinded prices, total-return check and 30-minute bars (logged in `ledgers/test_access.jsonl`), assembled as `panel.build.test_returns_panel` and `bars.derive.test_intraday_panel` do
- **Schema:** as `market_public`
- **Key:** (`session`, `symbol_id`) unique
- **Rows / coverage:** the test period's member and post-exit rows (73,498, as `targets_test`); its val-B rows equal the public build and its `r_cc`, `r_spy_cc`, `ar_cc` equal `targets_test` (`artifacts/NA-13/market_test.json`)
- **Availability:** test-period returns, after unblinding; `beta_m`, `adv20` end at t−1
- **sha256:** `a8dd253d72cbd0e811ce2be5adaa1e7f18b7c75332d636b8ac625fcdc5765580`

### `work/strategy/ma_cross_books.parquet`
- **Producer:** `newsaction.strategy.ma_cross`
- **Inputs:** `work/panel/panel_public.parquet`, the market panels, the D0 frames
- **Schema:** `period`, `session`, `gross`, `turnover`, `active`, `net_5`, `net_10`, `net_20`
- **Key:** (`period`, `session`) unique
- **Rows / coverage:** the exploratory no-news MA-cross fade (operator item 9), validation and test
- **Availability:** exploratory, after unblinding
- **sha256:** `96cd616b9c8f10c68f7d9e4e191cbbf3a553ffb2861db0277c678ffc06dfdb98`

### `work/strategy/books_val_b.parquet`
- **Producer:** `newsaction.strategy.run` `val_b`
- **Inputs:** `work/analysis/frame_{d0,d2}_{laya_fin,d1_ultra,anchor}.parquet`, `work/baselines/sentiment.parquet`, the market panel, `configs/frozen.yaml` (`strategy`, maps, gates)
- **Schema:** `rule`, `split`, `tier` (all / top100 / mid / rest), `session`, `gross`, `turnover`, `active`, `net_5`, `net_10`, `net_20`
- **Key:** (`rule`, `tier`, `session`) unique
- **Rows / coverage:** every non-empty book's daily series over its window (first entry to last exit)
- **Availability:** val-B (reference; the maps and gates were fit on val-A)
- **sha256:** `720d8a963875db84da03c688ae236ebecd713312d1225a495e656347147abf09`

### `work/strategy/positions_val_b.parquet`
- **Producer:** `newsaction.strategy.run` `val_b`
- **Inputs:** as the books
- **Schema:** `rule`, `event_id`, `session`, `symbol_id`, `tier`, `cohort`, `beta`, `adv20`, `decision_utc`, `entry_utc`, `exit_utc`, the inputs' instants (`news_utc`, `reaction_utc`, `tier_utc`, `risk_utc`, `calibration_utc`), `side`, `weight`, `score`, `group`
- **Key:** (`rule`, `event_id`) unique
- **Rows / coverage:** every position of every book
- **Availability:** val-B (reference; the maps and gates were fit on val-A)
- **sha256:** `3f53b166d8fa0ac7bec94265a5b4a7ce10be120d8b2569baa33785493a7443f1`

### `work/strategy/placebo_val_b.parquet`
- **Producer:** `newsaction.strategy.run` `val_b`
- **Inputs:** the books' universes
- **Schema:** `universe`, `seed`, `sharpe_gross`, `sharpe_net_{5,10,20}`, `ann_return_gross`, `ann_return_net_{5,10,20}`
- **Key:** (`universe`, `seed`) unique
- **Rows / coverage:** 100 random-signal books (seeds 2027–2126) per universe
- **Availability:** val-B (reference; the maps and gates were fit on val-A)
- **sha256:** `3afb87655673961d7f35f7fdc114431d99f45fd7c0d60c627f8ad28ad3e87e83`

### `work/strategy/placebo_paths_val_b.parquet`
- **Producer:** `newsaction.strategy.run` `val_b`
- **Inputs:** the placebo books
- **Schema:** `universe`, `session`, `cum_net_10_q05`, `cum_net_10_q50`, `cum_net_10_q95`
- **Key:** (`universe`, `session`) unique
- **Rows / coverage:** the placebo's percentile paths of the cumulative net return at 10 bp
- **Availability:** val-B (reference; the maps and gates were fit on val-A)
- **sha256:** `cf48913c6661879148a5c49af975531f643cfba64b8e51af79f99865109b7afe`

### `artifacts/NA-13/results/books_val_b.json`
- **Producer:** `newsaction.strategy.run` `val_b`
- **Inputs:** as the books
- **Schema:** per rule: the rule, counts (events, purged, β fallbacks, zero-return days), metrics, capacity, placebo percentiles
- **Key:** one file
- **Rows / coverage:** every pre-registered book and benchmark, empty ones included
- **Availability:** val-B (reference; the maps and gates were fit on val-A)
- **sha256:** `7900a88db8eeff2a31a05df1bac6695b912e6f7e4c06231d4cd49ae86f62c749`

### `work/strategy/books_test.parquet`
- **Producer:** `newsaction.strategy.run` `test`
- **Inputs:** `work/analysis/frame_{d0,d2}_{laya_fin,d1_ultra,anchor}.parquet`, `work/baselines/sentiment.parquet`, the market panel, `configs/frozen.yaml` (`strategy`, maps, gates)
- **Schema:** `rule`, `split`, `tier` (all / top100 / mid / rest), `session`, `gross`, `turnover`, `active`, `net_5`, `net_10`, `net_20`
- **Key:** (`rule`, `tier`, `session`) unique
- **Rows / coverage:** every non-empty book's daily series over its window (first entry to last exit)
- **Availability:** test-period returns from `work/strategy/market_test.parquet` (after unblinding)
- **sha256:** `dab383be66554632cdb1a075782d7f26e7f4e972cf0953d81cbd90b72151f86d`

### `work/strategy/positions_test.parquet`
- **Producer:** `newsaction.strategy.run` `test`
- **Inputs:** as the books
- **Schema:** `rule`, `event_id`, `session`, `symbol_id`, `tier`, `cohort`, `beta`, `adv20`, `decision_utc`, `entry_utc`, `exit_utc`, the inputs' instants (`news_utc`, `reaction_utc`, `tier_utc`, `risk_utc`, `calibration_utc`), `side`, `weight`, `score`, `group`
- **Key:** (`rule`, `event_id`) unique
- **Rows / coverage:** every position of every book
- **Availability:** test-period returns from `work/strategy/market_test.parquet` (after unblinding)
- **sha256:** `203b8668b53955618238a76d602e778018f84776394e7c38d4498c9b67b0e9e6`

### `work/strategy/placebo_test.parquet`
- **Producer:** `newsaction.strategy.run` `test`
- **Inputs:** the books' universes
- **Schema:** `universe`, `seed`, `sharpe_gross`, `sharpe_net_{5,10,20}`, `ann_return_gross`, `ann_return_net_{5,10,20}`
- **Key:** (`universe`, `seed`) unique
- **Rows / coverage:** 100 random-signal books (seeds 2027–2126) per universe
- **Availability:** test-period returns from `work/strategy/market_test.parquet` (after unblinding)
- **sha256:** `2812e846b555c8e25fde3b127bf9df3c08f395741fdaeb3fbcde2bb3871edcdb`

### `work/strategy/placebo_paths_test.parquet`
- **Producer:** `newsaction.strategy.run` `test`
- **Inputs:** the placebo books
- **Schema:** `universe`, `session`, `cum_net_10_q05`, `cum_net_10_q50`, `cum_net_10_q95`
- **Key:** (`universe`, `session`) unique
- **Rows / coverage:** the placebo's percentile paths of the cumulative net return at 10 bp
- **Availability:** test-period returns from `work/strategy/market_test.parquet` (after unblinding)
- **sha256:** `4596074650f39f1d724b01ea5655ecaf7784cf86adc07324b0c72766d1a912d6`

### `artifacts/NA-13/results/books_test.json`
- **Producer:** `newsaction.strategy.run` `test`
- **Inputs:** as the books
- **Schema:** per rule: the rule, counts (events, purged, β fallbacks, zero-return days), metrics, capacity, placebo percentiles
- **Key:** one file
- **Rows / coverage:** every pre-registered book and benchmark, empty ones included
- **Availability:** test-period returns from `work/strategy/market_test.parquet` (after unblinding)
- **sha256:** `8ea70d15fe96c18f75c95b564b2119ff73be752ab6749331eca53912421658ce`

### `artifacts/NA-13/market_test.json`
- **Producer:** `newsaction.strategy.market test`
- **Inputs:** the test build
- **Schema:** output path and sha256, sessions, the lock reads, the consistency gaps
- **Key:** one file
- **Rows / coverage:** the record of the one NA-13 access sequence
- **Availability:** after unblinding
- **sha256:** `b01909a35ba336a3ac2bad258d56a98d4592ec9ca4a0e426342cc198d27492a9`

### `artifacts/NA-13/results/ma_cross.json`
- **Producer:** `newsaction.strategy.ma_cross`
- **Inputs:** as its books
- **Schema:** per period: crosses, the group statistics (mean bp, Newey–West t, days, crosses), the fade book
- **Key:** one file
- **Rows / coverage:** validation (reproduces the operator's numbers) and test
- **Availability:** exploratory, after unblinding
- **sha256:** `974bfab1c04a59606eaeb62c52b61567b264640131baf996187ae6649594cf4f`

### `artifacts/NA-13/strategy_table.csv`
- **Producer:** `newsaction.strategy.tables`
- **Inputs:** the books, the placebo, the trials ledger (n_trials for the DSR)
- **Schema:** `order`, `split`, `family`, `model`, `point`, `signal`, `exit`, `gated`, `role`, `rule`, `universe`, the metrics, `dsr_*_net_{5,10,20}`, `capacity_*`, `note`, `n_trials`
- **Key:** (`split`, `rule`) unique
- **Rows / coverage:** every book on test and val-B, S-CONV first; the exploratory fade last
- **Availability:** test and val-B (reference)
- **sha256:** `82ac46c930fef646d6911062ae053075ea99c2e2001d64396638fce2384b5b8b`

### `artifacts/NA-13/strategy_table.tex`
- **Producer:** `newsaction.strategy.tables`
- **Inputs:** `strategy_table.csv`
- **Schema:** booktabs tabular; title and notes as comments
- **Key:** one file
- **Rows / coverage:** the test books
- **Availability:** test
- **sha256:** `67386daeab07d8e251a8d988f0d9762d9a397a8e85cc034216e2ae2aa7232e80`

### `artifacts/NA-13/fig7_data.csv`
- **Producer:** `newsaction.strategy.tables`
- **Inputs:** the test books, the placebo paths, the exploratory fade
- **Schema:** `rule`, `tier`, `session`, `cum_net_10`, `series` (book / placebo_band), `cum_net_10_q05/_q50/_q95`
- **Key:** (`rule`, `tier`, `session`) unique
- **Rows / coverage:** Figure 7: cumulative net returns at 10 bp by tier, with the benchmarks and the placebo band
- **Availability:** test
- **sha256:** `a7b92b463d4aa0f90dcbed361ad5d87232a3258cefa4bbac0877e1d3be8887f1`

### `artifacts/NA-13/results/strategy_summary.json`
- **Producer:** `newsaction.strategy.tables`
- **Inputs:** the trials ledger, `market_test.json`
- **Schema:** n_trials and its parts, the DSR settings, the lock reads, row counts
- **Key:** one file
- **Rows / coverage:** the DSR's trial count
- **Availability:** after unblinding
- **sha256:** `ddfbb405824fa716cebc4d323cd5f65ac922fbdfb6631b84be0ce7709c3508fc`
