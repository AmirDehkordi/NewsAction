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
