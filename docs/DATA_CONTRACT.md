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
- **Rows / coverage:** 317,729 rows; sessions 2023-07-03 .. 2025-12-31; member rows 315,887 + 1,842 priced rows within 60 sessions after an exit (target horizons of leavers).
- **Availability:** per column in `configs/availability.yaml` (kinds static / t_minus_1 / d2_reaction / post). Every t-1 statistic uses data through close(t-1) (tests/test_panel_pit.py).
- **sha256:** `d8ea1983d90ed193277b1f83266ed2025381c06d4eb2ed310fb24a022d1a274e`

### `work/panel/panel_test_inputs.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S7)
- **Schema:** 29 columns, all `static` or `t_minus_1`: `session`, `symbol_id`, `ticker`, `company_id`, `member`, `sector`, `half_day`, `split`, `adj_source`, `price_symbol`, `is_rep`, `tier`, `rank`, `dv_tier`, `dv_rank`, `tier_source`, `beta_m`, `beta_s`, `beta_n`, `sigma_cc`, `logv_med60`, `logv_mad60`, `adv63`, `car_m{5,20,60}`, `z_m{5,20,60}`. No `sigma_on` / `sigma_id` (they need blinded opens; NA-11 rebuilds them through the lock).
- **Key:** `(session, symbol_id)` unique
- **Rows / coverage:** 72,935 rows = test sessions 2026-01-02 .. 2026-07-31 × 503 members. Ids without Data/prices (40) have no test-period closes, so their close-based features become NaN once their windows need test sessions; volume baselines are NaN from a test-period true split onward.
- **Availability:** nothing dated t or later (tests/test_panel_sealing.py checks the kinds against the registry).
- **sha256:** `af5a1c4881a63acd721e577cdc6be4d4d9ce71ee8246f0a9f308266b5622714e`

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
- **sha256:** `6e586aebf45a4ead85e4f74781b9d5082069cd56dc5581c7c0bd2d7ed69f668d`

### `work/panel/qc_flags.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S2, `adjust.qc_flags`)
- **Schema:** `session` date32, `symbol_id` int64, `ticker`, `rule` (tr_diff_gt_50bp, abs_r_on_gt_25pct), `reason`, `atom_actions` string, `r_cc`, `r_cc_atom_total`, `diff_bp`, `r_on`, `r_id`, `dlog_f`, `dlog_f_next` double
- **Key:** `(session, symbol_id)`
- **Rows / coverage:** 228 public symbol-days 2022-01-04 .. 2025-12-31 (any symbol, member or not). Values are never altered by a flag.
- **Availability:** `post` (same-day QC).
- **sha256:** `f7d119c29740e7f92ad2cd1494f59bf8b1594a4f4fb2a47b1489f8f3504fbbec`

### `work/panel/mapping.parquet`
- **Producer:** `newsaction.panel.build` (NA-01 S2, `newsaction.panel.mapping`)
- **Schema:** `symbol_id`, `n_obs` int64, `atom_ticker`, `price_symbol`, `candidate_source`, `status` (mapped | no_candidate | failed_corr | conflict), `adj_source` string, `corr_pearson`, `corr_spearman`, `level_n`, `level_rho`, `level_iqr`, `level_factor` double (raw price-level check, `adjust.raw_level_check`: HON 2.0, all others 1)
- **Key:** `symbol_id`
- **Rows / coverage:** 565 ids: 525 mapped (Spearman ≥ 0.99 on ≥ 120 non-event days, public period only), 40 without any Data/prices candidate.
- **Availability:** `static`
- **sha256:** `48f86f07362868b48acf6b891d38ad89f65437dc2d68aa0f4a68f32be5e761c2`
