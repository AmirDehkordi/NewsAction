# NA-10 REPORT — 30-minute bars (FMP), D1 (10:00) inputs, sealed 2026

Date: 2026-10-27 · Branch `feat/NA-10-bars30` (worktree `NewsAction-NA10`, cut from `main` @ `7bc114b`) ·
Decisions: `docs/decisions/NA-10.md` · Numbers: `artifacts/NA-10/summary.json` (written by
`scripts/na10_report.py`), `capability.json`, `build_states_d1.json`, `basis_by_symbol.csv`,
`member_session_exceptions.csv`.

**STOP, resolved by the operator.** The probe found that FMP's 30-minute endpoint returns only the last 30
calendar days of any window, so the fetch needed 16,833 requests against 2,995 left under the 3,000 cap
(PRD S2: STOP and report; the fetch refused to start). Asked in session, the operator approved two requests to
check the legacy `/api/v3` endpoint (same cap; one request used) and then raised the cap to 17,000 for the full
design (PREREG §15, NA-10 row 1). The chunk used **15,858** requests.

**Blinding.** No statistic, print or plot of any test-period bar or return appears here or was looked at.
The test-period windows were fetched without a cache, held in memory as numeric arrays, and written once
through `lock.write_sealed`; only request, answer and row counts are reported.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 client | done | `src/newsaction/bars/fmp30.py` (httpx, retries, rate limit; 30-minute only); `ledger.FmpLedger` (a `request` line before every send, refuses cap + 1; a `response` line after); cache `work/bars30/raw/` (public windows only) |
| S2 probe | done (7 requests; STOP fired, resolved) | `src/newsaction/bars/probe.py`; `artifacts/NA-10/capability.json` |
| S3 fetch | done | `src/newsaction/bars/fetch.py`; `work/bars30/bars_public.parquet`; `work/snapshot/sealed/bars30_2026.parquet` (write-only, hash registered) |
| S4 basis | done (per-session rule; S4's "else" branch generalized) | `src/newsaction/bars/basis.py`; `work/bars30/session_qc.parquet`; split tests NVDA / AVGO / WMT / CMG |
| S5 derive | done | `src/newsaction/bars/derive.py`; `work/panel/intraday_public.parquet`, `intraday_spy_public.parquet` |
| S6 reactions + states | done | `panel/reactions.py` (D1 path; test route through `lock.read_sealed("bars30_2026", "reactions")`), `panel/targets.py` (D1 targets), `states/build.py --stage d1`; `work/states/{reaction_d1,callB_d1_E3}.parquet`; 49 columns registered in `configs/availability.yaml` |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 request cap | `ledgers/fmp_requests.jsonl`: **15,858** `request` lines (each answered: 15,858 `response` lines, all HTTP 200, 0 retries) ≤ the cap of **17,000** (PREREG §13 as raised in §15 by the operator). Against the original 3,000 the probe's projection fired the PRD's STOP before any fetch. `tests/test_bars_cap.py` (8): a ledger holding 17,000 requests refuses the 17,001st and writes nothing; the client sends nothing past the cap, reserves before every attempt and again for a retry, never stores the key, never caches a test-period window; the real ledger is within the cap. Mutation "cap check removed" **RED** | PASS (amended cap) |
| AC2 bars | 250,992 public member-sessions (representative class, member, EOD row; 2024-01-02 … 2025-12-31): every regular bar on **99.78%**; half days (2,999) 7 bars on **99.83%**; price basis usable on **99.58%**; 1,177 exceptions listed (`member_session_exceptions.csv`: 412 without bars, 400 of them PSKY's excluded pre-merger history; 630 inconsistent opens; 135 incomplete). First-bar open within 5 bp of the EOD raw open on **72.9%** only (median 0 bp, q75 6.6, q90 27, q99 209 bp): FMP's first 30-minute bar opens at its first trade, not at the official opening auction (§3.4). The four split windows pass (`tests/test_bars_basis.py`: NVDA 2024-06-10, AVGO 2024-07-15, WMT 2024-02-26, CMG 2024-06-26 as traded on both sides, first-bar opens within 1% of ATOM's raw open, 10:00 prices continuous on one basis). `tests/test_bars_counts.py` | counts and splits PASS · **5 bp bound FAIL as written** (strict xfail; owner decision 2) |
| AC3 sealed | No public NA-10 file holds a session ≥ 2026-01-02 (`bars_public`, `session_qc`, `intraday_public`, `intraday_spy_public`, `reaction_d1`, `callB_d1_E3`: max 2025-12-31, from the parquet columns). `build_reactions(…, "test", "D1")` raises `LockError` and logs (`bars30_2026`, `reactions`, allowed false) first; `build_d1_targets(…, "test")` likewise for `targets`; the public D1 routes refuse test rows; after a temporary freeze the route reads `bars30_2026`, `prices_raw_2026`, `total_return_check_2026` through the lock only. The blinded bars are in the manifest and unreadable through `io`. `ledgers/test_access.jsonl`: one new entry, the `write` of `bars30_2026`. `tests/test_reactions_d1_sealed.py` (11). Mutations "D1 test reactions skip the lock", "public D1 targets accept test rows" **RED** | PASS |
| AC4 D1 states | `work/states/callB_d1_E3.parquet`: **37,562** states (train 22,621, val-A 8,906, val-B 6,035), state tokens p50 677, **p95 840** (≤ 900), max 874 (budget 875 + Call B's longest core question + 3 ≤ 1,024). `validate_spec` passes at D1; injecting any of 9 columns known after 10:00 (`p1530`, `r_10c`, `ar_10c`, `p_close`, `bars_complete`, `y1`, `car_lvl_10`, `g_d2`, `z_cc`) into the reaction or company block raises `PITError`, and so does a D0-visible non-reaction column (`beta_m`, `news_w0`, `z_m5`, `attention_ratio_w0`) in the reaction block. `tests/test_states_d1_pit.py` (19). Mutation "reaction block call rule dropped" **RED** | PASS |
| AC5 ATOM untouched | No ATOM access: a grep of every changed and new file under `src/ scripts/ tests/ configs/` for `atom_postgres`, `ATOM_DB_PASSWORD`, `sqlalchemy`, `psycopg`, `GitHub/Atom`, ATOM's venv or docker finds nothing. Only ATOM's runbook files were read (allowed). Reconciliation uses the NA-01 snapshot (`work/snapshot/prices_raw.parquet`) and NA-01's level factors | PASS |
| AC6 10:00 rung | `intraday_public` carries `car_lvl_10` and `g_d1_lvl` (and G_D1, y1) for 249,330 public rows. `tests/test_bars_rung.py` rebuilds both for 10 seeded public D0 events from the raw bars, the session basis factor, the EOD opens, r_on, SPY's bars, every same-sector member peer's bars (leave-one-company-out mean, ≥ 5), the panel's β of row t and σ_cc,t, without `bars.derive`: equal to **1e-9**. Max session 2025-12-31: no 2026 value exists | PASS |
| GAC1 | `make verify` exit 0 (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; nothing written under `Data/` | PASS |
| GAC3 | `tests/test_blinding.py` (8) passes: no test-period literal and no sealed-path use in `src/` outside `lock.py`; the access ledger has no read entry | PASS |
| GAC4 | No OpenRouter call: NA-10 spend $0.00; cumulative $3.6305 (NA-05 $0.1039, NA-06 $3.5266) | PASS |
| GAC5 | 12 NA-10 files in `docs/DATA_CONTRACT.md` with the manifest sha256 (7 under `work/`, 5 under `artifacts/NA-10/`); `make manifest` OK, 89 artifacts | PASS |

### 2.1 Mutations

A session-local script applied each mutation, cleared `__pycache__`, ran the guard's tests, restored the file and
checked its sha256; `src/` holds no residue.

| Mutation | File | Result |
|---|---|---|
| cap check removed from `FmpLedger.reserve` | ledger.py | RED |
| client reserves after sending | bars/fmp30.py | RED |
| test-period windows cached outside the lock | bars/fmp30.py | RED |
| basis level uses the session's own close (no `shift(1)`) | bars/basis.py | RED |
| D1 test reactions read the public bars instead of the lock | panel/reactions.py | RED |
| public D1 targets accept test-period rows | panel/targets.py | RED |
| reaction-block call rule dropped from `validate_spec` | states/build.py | RED (GREEN on the first run: the injected columns were already refused by `check_inputs`; the call-rule test with D0-visible columns was added) |

## 3. Numbers

### 3.1 Probe (S2) and the cap

| Probe | Request | Rows | Served | Bounds on the days one answer covers |
|---|---|---|---|---|
| 1 | AAPL 2025-01-02 … 2025-12-31 | 267 | 21 sessions, 2025-12-02 … 12-31, all 13 bars | [30, 30] (2025-12-01, a session, missing) |
| 2 | same, `extended=true` | 666 | the same 21 sessions, pre-market bar on 21 | [30, 30] |
| 3 | NVDA 2024-06-03 … 06-14, `nonadjusted=true` | 130 | 10 of 10, as traded (first-bar open / ATOM raw open = 1.000 on 06-07 and 06-10) | whole |
| 4 | NVDA 2024-01-02 … 2025-12-31, `nonadjusted=true` | 267 | 21 sessions of December 2025 | [30, 30] |
| 5 | NVDA 2024-01-02 … 2024-12-31, `nonadjusted=true` | 267 | 21 sessions of December 2024 | [30, 32] |
| 6 | AAPL 2025, legacy `/api/v3` (operator-approved) | 267 | December 2025 | [30, 30] |

The cap is a window of calendar days ending at `to`, oldest dropped (as IR-04 found at 1 minute, 3 days);
`extended` adds rows, not days. Projections at 30 days (plain windows, at the STOP): 16,833 for the plan,
14,003 for the PRD's span from 2024-06-03, 7,501 from val-A, 4,000 for the test period alone. The final plan
(session-anchored windows, clipped at the first EOD day) needed 15,826; ticker aliases added 26 (§3.3).
Probes 4–5 went out without `extended` because of a bug in the first run (the pre-market share divided by
expected instead of served sessions, decisions doc); the cap finding does not depend on it, and the
fetch's pre-flight confirmed `extended` + `nonadjusted` together on NVDA's split window (as traded,
pre-market bars on every session).

### 3.2 Requests

| Purpose | Requests | HTTP 200 | Rows | Empty answers |
|---|---|---|---|---|
| probe | 6 | 6 | 1,864 | 0 |
| fetch, public | 12,299 (12,273 plan + 26 alias) | 12,299 | 5,719,814 | 9 |
| fetch, test period | 3,553 | 3,553 | 2,060,207 | 16 |
| **total** | **15,858** | 15,858 | | |

Public: ~34 minutes at 6–7 requests per second (peak RSS 0.4 GB; assembly 2.3 GB). Test period: 616 s, peak
RSS 1.0 GB, 0 failures. Empty answers: CPAY and DAY before their renames (then fetched under FLT and CDAY), JNPR
and PXD after their acquisitions closed, SATS from 2025-09-19 (public) and all of 2026 (FMP serves no SATS bars
from then on: no D1 data for SATS in the test period), FDXF and HONA before their 2026 listings (history
buffer). `bars_public.parquet`: 5,698,440 bars of 544 companies + SPY (3,302,680 regular, 1,300,777 pre-market).
Sealed: 2,060,207 bars (from the manifest).

### 3.3 Price basis (S4)

Session classes on public member-sessions: as traded 247,611, rescaled 2,339, inconsistent 630, no bars 412.
Rescaled runs (constant level factors, `basis_by_symbol.csv`): FDX 0.805 and CTVA 0.150 over the whole public
range, HON 1.061 to 2025-09-30 (the vendor-dated Solstice spin-off NA-01 found), FTV 0.754 to 2025-06-27
(Ralliant), J ≈ 0.990 (Amentum), ILMN, MMM (Solventum), CMCSA from 2025-12-08 (vendor-dated Versant).
Inconsistent sessions are mostly misprinted first bars (April 2025: AJG, AON, AMP, AVY 5–18% off the official
open) and thin high-priced names whose first trade is >1.5% from the auction. Ticker fixes: PEAK for DOC before
2024-03-01 (FMP's DOC was Physicians Realty Trust), FLT for CPAY before 2024-03-25, CDAY for DAY before
2024-02-01; PSKY before 2025-08-07 excluded (another intraday path than Paramount Global's EOD prices; FMP's
PARA is now a different, penny-priced security: 20 requests spent finding out).

### 3.4 Reconciliation with the EOD open (AC2's 5 bp)

|first-bar open − EOD raw open| on public member-sessions: q50 0 bp, q75 6.6, q90 27, q99 209 bp; 72.9% within
5 bp. The vendor's first 30-minute bar starts with its first trade at or after the open; the official open is
the opening auction. P_10:00 and every D1 return use the official EOD open, so the 5 bp gap does not enter them;
the basis decision uses the trailing close ratio confirmed by the open within 1.5% (§15 row 3).

### 3.5 D1 quantities (public)

| | q10 | q50 | q90 |
|---|---|---|---|
| σ_30 (open → 10:00) | 0.39% | 0.56% | 0.91% |
| σ_rest (10:00 → close) | 0.53% | 0.73% | 1.12% |
| σ_on / σ_30 | 0.52 | 0.66 | 0.85 |
| G_D1 | −1.33 | 0.00 | 1.35 |
| G^lvl_D1 = CAR^lvl_10 | −0.94 | 0.00 | 0.95 |
| y1 | −1.38 | 0.00 | 1.39 |

(σ_on² + σ_30²)^½ has median 0.68% against σ_cc 0.97%. Robust SD of G_D1 0.94 and of y1 1.01. Spearman of
G^lvl_D1 with G^lvl_D2: 0.65. The decomposition is exact: (1 + r_c10)(1 + r_10c) = 1 + r_cc to 4e-16 on 249,950
rows, and the sector factor built with NA-01's pool reproduces NA-01's `r_sec_cc` to 7e-17. G_D1 exists on 217,810
of 251,002 member rows; σ_30 needs 60 sessions, so it starts 2024-03-28 (robustness split). D0 events of train /
val-A / val-B with G_D1: 37,561 of 38,164.

### 3.6 D1 states (S6)

37,562 `callB_d1_E3` states of 38,164 B-split D0 events (543 with every listed article excluded, 59 without text
after masking). Excluded article slots 29,311 (non-English 20,115, running market stories 3,984). 2,533 states
drop 2,621 articles to fit the D1 budget; 1,055 carry fewer articles than their Call A D0 twin. 597 states show
"not available" for the move (no G_D1 that session). The reaction block adds a median 84 tokens, e.g.
`{"time": "half an hour after the open", "stock_move_vs_market_and_sector": "small rise (≈0.7× a typical move by
this time of day)", "stock_market_move": "negligible rise (≈0.2× a typical move by this time of day)",
"volume_vs_normal": "busy"}` (a train state). Stage: 248 s, peak RSS 3.4 GB.

## 4. Spend

OpenRouter: $0.00 this chunk, $3.6305 cumulative (`ledgers/spend.jsonl`). FMP: 15,858 requests (6 probe, 12,299
public, 3,553 test period) of the 17,000 cap; 0 failures, 0 retries.

## 5. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| FMP 30-minute bars of session s | P_10:00, P_pre (D1); P_15:30, last close (post) | a bar is known at its end; the first regular bar at 10:00 ET |
| Session basis factor | rescales a session's bars | trailing median of EOD close / last-bar close over the previous 5 sessions (known by close(s−1)), confirmed by the EOD open and first-bar open of s (known at the open); PIT test with a mutation |
| ATOM raw EOD open of s | O_s for the D1 returns, the basis check | known at the open |
| ATOM raw EOD close of s | 10:00 → close pieces, y1 (post); basis of later sessions | known at the close |
| NA-01 r_on,s, β (row s), σ_on, σ_cc (row s) | D1 returns, AR, G_D1, G^lvl | r_on at the open; β and σ through s−1 |
| Sector peers' bars | leave-one-company-out sector of each window | same instants as the stock's; NA-01's pool (membership and representative class known at open(s)) |
| σ_30, σ_rest, first-bar volume baseline | G_D1, y1, the volume multiple | 126 / 60 sessions ending s−1 (`.shift(1)` in `risk`) |
| SPY's D1 history | the D1 market move z and E4 | the 252 sessions before s |
| AR_cc of s+1 … s+20 | D1 targets (post only) | purged at split ends; never a state input |
| W0 news, context | D1 states | as NA-04 (W0 exclusions applied) |

The D1 state reads only `d1` reaction columns (`validate_spec`); `car_lvl_10` (an outcome) and the 10:00 →
close pieces are `post`. No test-period bar was read: the D1 test route raises before the freeze.

## 6. Deviations from PREREG

Four rows appended to §15 (2026-10-27, NA-10), all before the freeze:
1. §13: the FMP cap raised from 3,000 to 17,000 (operator decision), with the plan and the probe's evidence.
2. §2.5, §5.2–5.6, A1.2, A1.5: the D1 quantities (prices, returns, sector, σ_30, σ_rest with the half-day
   scaling, G_D1 clip, G^lvl = CAR^lvl_10, y1 and its secondaries, the forward level pieces, the volume
   multiple).
3. §3.5, §5.1: the bars, the per-session price-basis rule, the ticker aliases and exclusion, AC2's 5 bp bound.
4. §6.9–6.11: the D1 Call B state (W0 exclusions, the codebook unit `d1`, the budget); the codebook hash in
   `configs/frozen.yaml` re-recorded.

PRD-level choices without a PREREG change: bars from 2024-01-02 and members from 2024-01-02 (PRD: 2024-06-03),
SPY from 2023-01-03; session-anchored windows; the test-period part written once with a sealed fallback.

## 7. STOP conditions and owner decisions

- **Fired:** the probe's projection exceeded the FMP cap (16,833 > 2,995). Resolved by the operator in session
  (v3 check, then the cap at 17,000). Not fired: the cap during the fetch (15,858 used), any OpenRouter cap
  (no call).
- **Owner decisions requested:**
  1. Confirm the four §15 rows (the cap row records the decision taken in session).
  2. **AC2's 5 bp bound:** accept 72.9% within 5 bp as a vendor fact (first trade vs opening auction), with
     completeness 99.78% and usable basis 99.58% as the bars' acceptance (strict xfail, as NA-01's AC3(c)).
  3. **CLAUDE.md E18, the Quick facts line and PRD NA-10 AC1** still say 3,000 requests: update them (operator's
     files; not edited here).
  4. **SATS** has no FMP bars from 2025-09-19 on, so none of its test-period events gets a D1 state; PSKY's
     pre-merger sessions are excluded (D1 for PSKY from 2025-08-07).
  5. 20 requests went to FMP's PARA, now another security; the cache keeps them, unused.
  6. When the sealed files are copied to main at merge: `work/snapshot/sealed/bars30_2026.parquet` (sha256
     `1d08a2447c07f5fc2f0b84e4a11eb0a00e4bd6edc07adfbd616b9ae9bcd37bdd`, 2,060,207 rows) is registered in this
     worktree's `work/MANIFEST.json`; `work/bars30/raw/` (12,305 cached public answers) can be copied too, so that
     re-runs send nothing.

## 8. Files

- **Added:** `src/newsaction/bars/{__init__,fmp30,probe,fetch,basis,derive}.py`; `configs/bars.yaml`;
  `scripts/na10_report.py`; `docs/decisions/NA-10.md`; `artifacts/NA-10/{REPORT.md,capability.json,summary.json,
  build_states_d1.json,basis_by_symbol.csv,member_session_exceptions.csv}`.
- **Tests added (54):** `test_bars_cap` 8, `test_bars_basis` 8, `test_bars_counts` 4 (one strict xfail),
  `test_bars_fetch` 3, `test_bars_rung` 1, `test_reactions_d1_sealed` 11, `test_states_d1_pit` 19; updated: `test_ledger` (cap), `test_configs_match_prereg` (cap and its
  §15 row), `test_panel_sealing` (the NA-01 D1 stub replaced by the D1 route), `test_states_pit` (the W0
  reaction block is the D1 block).
- **Changed:** `src/newsaction/ledger.py` (`FmpLedger`: response lines, request-only count),
  `panel/reactions.py` (D1 path), `panel/targets.py` (D1 targets, `blinded_bars_file`), `panel/build.py` (the test
  route's columns), `states/{build,context,codebook}.py` (D1 state); `configs/{availability,codebook_v1,frozen,
  project}.yaml`; `docs/DATA_CONTRACT.md` (NA-10 section, 12 files); `docs/PREREG.md` (§15 rows);
  `ledgers/fmp_requests.jsonl` (15,858 requests), `ledgers/test_access.jsonl` (one `write`).
- **Derived (gitignored):** `work/bars30/{raw/,bars_public.parquet,session_qc.parquet}`,
  `work/panel/{intraday_public,intraday_spy_public}.parquet`, `work/states/{reaction_d1,callB_d1_E3}.parquet`,
  `work/snapshot/sealed/bars30_2026.parquet`.

## 9. `make verify`

Exit 0 (219 s, peak RSS 7.7 GB): ruff "All checks passed!", 162 files formatted; mypy --strict "no issues found
in 78 source files"; pytest **1,485 passed, 2 xfailed** (NA-01's literal AC3(c) bound and NA-10's literal 5 bp
bound); manifest OK (89 artifacts, 10 inputs); ledgers OK (`fmp_requests.jsonl` 31,716 lines = 15,858 requests +
15,858 responses, `test_access.jsonl` 3, `trials.jsonl` 200).
