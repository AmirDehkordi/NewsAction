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
