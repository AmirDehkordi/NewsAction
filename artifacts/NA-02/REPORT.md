# NA-02 REPORT — news timing audit, member mapping, cleaning, re-embedding, PIT novelty

Date: 2026-10-24 · Branch `feat/NA-02-news` (cut from `main` @ `1ef4219`) · Decisions: `docs/decisions/NA-02.md` ·
Tables: `artifacts/NA-02/*.csv`, `timing_audit.md`, `rederived_diagnostics.md`, `summary.json`
(`scripts/na02_report.py`), `leakage_ic.csv` (`python -m newsaction.news.audit`).

**Blinding.** No return of a session ≥ 2026-01-02 was read, joined or summarized. 2026 *articles* (text and
timestamps) were processed and appear only in counts: precision classes, mapping, `parsing_allowed`, coverage.
Every return statistic goes through `newsaction.news.audit`. Its `public_targets` reads `panel_public`, which
ends 2025-12-31, and asserts that range. `join_targets` calls `assert_public` before every merge. Tests and
mutations: §2.1.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 load | done | `src/newsaction/news/load.py`: the S1 columns of `Data/news_2023…2026` with pyarrow; `body` refused; summary → `summary_present`; text streamed for member and market rows only |
| S2 map | done | `news/mapping.py`; curated aliases in `configs/news.yaml`; `artifacts/NA-02/{mapping_stats.json,unmapped_top30.csv,unmapped_top100.csv}` |
| S3 timing | done | `load.add_timing` / `naive_sessions`; `audit.affected_share`, `d0_ticker_day_change`, `leak_signature`; `artifacts/NA-02/timing_audit.md` + `timing_*.csv` |
| S4 clean | done | `news/clean.py`, `configs/patterns.yaml` (`holdings_13f`, `form4`); `artifacts/NA-02/spam_judgments.csv` (3 rounds × 400); `parsing_allowed_*.csv` |
| S5 detect + scrub | done | `news/detect.py`, `configs/patterns.yaml`; planted set `tests/data/detector_planted.csv`; `artifacts/NA-02/detector_eval.csv` |
| S6 embed | done | `news/embed.py`; `work/news/embeddings_ts.parquet` (2,906,710 × 384, float16) |
| S7 dedupe | done | `news/dedupe.py` (greedy, backward-looking anchor groups) |
| S8 novelty | done | `news/novelty.py` (strictly earlier representatives, 7 days) |
| S9 sources | done | `news/sources.py`, `configs/sources.yaml`; `artifacts/NA-02/top_domains.csv` |
| S10 leakage audit | done | `news/audit.py` (`python -m newsaction.news.audit`); `artifacts/NA-02/leakage_ic.csv`; `configs/frozen.yaml` `news:` |
| S11 coverage | done | `news/coverage.py`; `work/news/coverage_member_month.parquet`; `artifacts/NA-02/leavers_news_rate.csv` |
| S12 output | done | `news/build.py`; `work/news/articles_clean.parquet` (+ intermediate `articles_stage1.parquet`); all 46 columns registered in `configs/availability.yaml` (44 new entries) |
| S13 re-derived diagnostics | done | `artifacts/NA-02/rederived_diagnostics.md` + `diag_*.csv` |
| S14 market news (optional, PRD) | done | `work/news/market_articles.parquet` (31,506 cleaned ^GSPC / ^VIX / DX-Y.NYB articles) |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 timestamps | `tests/test_news_timing.py` through `load.add_timing` / `calendar`: (a) 2025-03-10 00:00:00Z → t_avail 23:59:59Z, W0 = W2 = **2025-03-11**; (b) 13:00:00Z → 13:59:59Z, W0 = **None**, W2 = 2025-03-10; (c) 12:30:00Z is *minute* precision under §2.2 (t_avail 12:30:59Z), and a true exact stamp 12:30:17Z: W0 = W2 = 2025-03-10. Mutations "no date_only branch" and "no hour branch" in `timeutil` are **RED**. Affected-share table per year: `timing_audit.md` §4 (date-only 75–89% of articles change session; exact 0%) | PASS |
| AC2 mapping | Fixtures: NYSE:SQ 2024-03-04 and 2025-01-03 and NYSE:XYZ 2025-08-04 → symbol 1602, one company_id. Real data: **all 1,270 NYSE:SQ rows of news_2024 → 1602** (the corpus has no NYSE:XYZ row). BRK.B / BRK-B / brk/b → BRK-B. Collisions: `check_collisions` on the real map passes; `resolve` refuses double matches; **0** on the corpus. Mapped share of member-day volume **99.9992%** (2,906,710 / 2,906,734; definition in §3.2). Mutations "ATOM history dropped" and "aliases ignored" are **RED** | PASS |
| AC3 detector | Planted set: 91 sentences (42 after-the-fact and 12 pre-market positives, 37 hard negatives). Recall **1.00 / 1.00**, 0 / 37 negatives flagged. Judged precision on 200 real flagged sentences: **0.945** (after_fact 140/150 = 0.933, premarket 49/50 = 0.98; ≥ 0.8, no explanation needed). Rows in `detector_eval.csv` | PASS |
| AC4 novelty PIT | `tests/test_news_novelty.py`: synthetic deletion test (τ = 2025-06-15) and **real data**: 20 random companies (seed 2026), dedupe + novelty recomputed with and without articles after τ → identical for every article ≤ τ; the recomputation equals the build. Mutation `<` → `<=` (`side="right"`) is **RED** (a representative sees itself) | PASS |
| AC5 spam | Final judged sample (round 3, fresh): **200 / 200 = 1.00** flagged titles are 13F holdings auto-articles (≥ 0.95). Rounds 1–2: 200/200, 199/200. `spam_judgments.csv` committed | PASS |
| AC6 leakage audit dates | `audit.PUBLIC_END` = end of val-B (2025-12-31) from `configs/splits.yaml`. `assert_public` runs in `public_targets` and `join_targets`; `public_only` drops later sessions before any join. `tests/test_news_audit_dates.py` (a 2026 ticker-day raises; an AST check that `join_targets` asserts first); mutations "no assert" and "public_only keeps all" are **RED**. `configs/frozen.yaml` `news:` written and consistent with `leakage_ic.csv` (test) | PASS |
| AC7 embeddings | 2,906,710 rows = every member article id (unique), so every kept id (1,494,138) has exactly one row. `fixed_size_list<float16>[384]`; L2 norm **0.99944 … 1.00056**. `tests/test_news_embed.py::test_real_embeddings_ac7` | PASS |
| AC8 third party | `parsing_allowed` shares (§3.4); `third_party_ok` column present (= `parsing_allowed is True`; None is not OK); decision request §7 | PASS |
| AC9 no 2026 outcomes | `tests/test_blinding.py` passes (one docstring with a 2026 month was reworded); `ledgers/test_access.jsonl` has the 2 NA-01 `write` entries and **no NA-02 entry** | PASS |
| GAC1 | `make verify` exit 0 (§8) | PASS |
| GAC2 | `git status --porcelain Data/` empty; Data/news inputs fingerprinted in the manifest (`make manifest` OK) | PASS |
| GAC3 | Blinding scan clean; no `sealed` use; access ledger unchanged | PASS |
| GAC4 | No API call. Spend $0 (`ledgers/spend.jsonl` empty). Network used only to download the bge-small weights from the Hugging Face Hub; no article text left the machine | PASS |
| GAC5 | 5 new `work/news/` artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A session-local script applied each mutation, ran the test file and restored the source byte-for-byte.

| Mutation | File | Result |
|---|---|---|
| date_only availability branch removed | timeutil.py | RED |
| hour availability branch removed | timeutil.py | RED |
| novelty `<` → `<=` | news/novelty.py | RED |
| ATOM ticker history dropped (current tickers only) | news/mapping.py | RED |
| curated aliases ignored | news/mapping.py | RED |
| join without `assert_public` | news/audit.py | RED |
| `public_only` keeps every row | news/audit.py | RED |
| dedupe window removed | news/dedupe.py | RED |
| 13F exclusion list ignored | news/clean.py | RED |

## 3. Numbers

### 3.1 Corpus and timing (S1, S3; `timing_audit.md`)

- **Load range.** 4,537,511 articles have t_avail in 2023-07-01 … 2026-07-31.
  - us_equity 4,405,637; non_equity 102,896 (indices, FX, crypto, macro series); other 28,978 (non-US
    exchanges, OTC, futures).
- **Precision classes, whole files.**

  | File | date_only | hour | minute | exact |
  |---|---|---|---|---|
  | news_2023 | 37.8% | 7.8% | 12.8% | 41.5% |
  | news_2024 | 10.9% | 5.0% | 11.5% | 72.6% |
  | news_2025 | 5.0% | 2.3% | 7.9% | 84.9% |
  | news_2026 | 3.0% | 1.8% | 9.0% | 86.3% |

  Member articles have a similar mix. By domain, date-only stamps concentrate in finviz (27%),
  theglobeandmail (12%), aol (12%) and gurufocus (12%).
- **Sessions that move under the PREREG rule.**
  - date-only: 75% of articles change W0 and W2 in 2025 (84% in 2024);
  - hour: 19% (30% in 2024);
  - minute: 0.4%; exact: 0%.
- **D0 ticker-days.**
  - Naive D0 ticker-days that are not D0 ticker-days under the PREREG rule: 7.8% in 2024, 2.5% in 2025.
  - Ticker-days whose W0 article set changes: 54% in 2024, 41% in 2025.
- **Leak signature, ≤ 2025** (cleaned W0 articles, vendor sentiment).

  | Rule | Cell | IC(z_on) | t | IC(z_id) | t |
  |---|---|---|---|---|---|
  | naive | date-only | 0.035 | 5.9 | 0.0085 | 1.5 |
  | PREREG | date-only | 0.013 | 2.4 | −0.002 | −0.4 |
  | PREREG | pooled | 0.051 | 12.8 | 0.004 | 0.9 |

  The naive rule puts date-only articles published during the day into that morning's W0. That raises
  their open→close IC; the PREREG rule removes it.
  - The signature is weak in this metric (naive t 1.5), because vendor sentiment is a coarse signal.
  - Under the PREREG rule no precision class passes the §6.4 leak test.

### 3.2 Mapping (S2)

- **Resolution.**
  - US-equity articles that resolve to an ATOM symbol: 3,049,144.
  - Member articles: **2,906,710** in 536 companies: 17,581 in 2023-H2, 719,639 in 2024, 1,726,292 in 2025,
    443,198 in 2026-Jan…Jul.
- **Mapped share** = member articles / US-equity articles whose ticker is any identifier of a member company
  (current ATOM ticker, ATOM history, alias; ignoring validity ranges) on a member-day of that company:
  **2,906,710 / 2,906,734 = 99.9992%**.
  - The 24 misses are 2023 NYSE:DOC articles about Physicians Realty Trust, correctly unmapped.
  - The share is near 100% by construction. What it cannot see are members whose news the vendor files under
    unknown tickers, so the top-30 unmapped tickers are the check: all are non-members (GLD, MSTR, RIVN, USO,
    XLB, LCID, XLE, SNOW, SOFI, XLV, NET, X, RKLB, JEF, QGEN, XLF, CELH, MARA, SPOT, CG, LNG, ZS, TOL, GME,
    JHG, ASTS, ROKU, AFRM).
- **Vendor coverage of members.** 20 member companies have **no** article at all: AAP, AMTM, ATVI, CRH, DELL,
  DXC, ERIE, FDXF, FLEX, HONA, LITE, NWL, OGN, PXD, Q, SEDG, SNDK, SOLS, SW, XYZ.
  - Block's only articles are tagged NYSE:SQ, up to 2025-01; Block joined the index 2025-07-22.
- **Renames and classes.**
  - Renames handled by ATOM's history: BK→BNY, MMC→MRSH, FI→FISV, PARA→PSKY (the vendor keeps the old tickers
    through 2026).
  - Renames handled by curated aliases: SQ, PEAK, CHK, FB.
  - Class aliases: PARAA, BF-A, LEN-B.

### 3.3 Cleaning, detectors, sources (S4, S5, S9)

- **Flag rates among member articles.**

  | Year | non_news | junk tag | 13F | Form-4 | after-the-fact | pre-market |
  |---|---|---|---|---|---|---|
  | 2024 | 5.0% | 13.9% | 10.5% | 0.6% | 7.2% | 0.3% |
  | 2025 | 1.7% | 14.6% | 28.5% | 0.7% | 7.4% | 0.3% |
  | 2026 | 0.7% | 17.3% | 28.2% | 0.9% | 10.8% | 0.4% |

  Totals: 692,303 13F articles (23.8%) and 19,821 Form-4 articles.
- **13F recall.** Within flagged ∪ insider_ownership it is estimated at **0.99**: precision 1.00 on 692,303
  flagged articles, and 6.5% of the 91,266 unflagged insider_ownership articles judged 13F.
- **Usable articles.** 1,700,170 pass the §6.2 filters. 30,733 of them have no text left after scrubbing.
  The rest, **1,669,437**, are usable.
- **Non-English.** `non_english_hint` marks 6.7% of kept articles (5.4% of all). The detectors and NA-04's
  masking are English-only (§7, item 4).
- **Source class of kept articles.**
  - With the vendor primary-source override (`source_class`): press_wire_primary 30.2%, aggregator 25.5%,
    auto_generated 19.6%, other 17.6%, retail_analysis 5.0%, major_outlet 2.1%.
  - Domain only (`source_class_domain`): aggregator 35.4%, other 27.6%, auto_generated 23.2%, retail 7.1%,
    press wire 4.0%, major 2.6%.
  - The top 100 domains, all listed in `configs/sources.yaml`, cover 79.9% of member articles.

### 3.4 `parsing_allowed` (S4, AC8; member articles with t_avail 2024-07 … 2026-07)

| Scope | Period | Articles | True | None | False |
|---|---|---|---|---|---|
| all member articles | 2024-07..2026-07 | 2,778,253 | 86.0% | 13.0% | 1.0% |
| | 2024-H2 | 608,763 | 37.4% | 59.2% | 3.5% |
| | 2025 | 1,726,292 | 99.6% | 0.0% | 0.4% |
| | 2026 | 443,198 | 99.95% | 0.0% | 0.05% |
| cleaned (pre-dedupe) | 2024-07..2026-07 | 1,591,365 | 84.1% | 15.8% | 0.2% |
| | 2024-H2 | 410,791 | 38.6% | 61.1% | 0.3% |

None occurs only in 2024. Monthly: `parsing_allowed_monthly.csv`.

### 3.5 Embeddings, dedupe, novelty (S6–S8)

- **Embeddings.**
  - 2,906,710 texts in 1,289 s (2,255/s) on MPS. bge-small-en-v1.5 @ `5c38ec7c…267a`, fp16 compute, float16
    storage.
  - Rerunning the build reproduced the sha256. A re-encode of 2,000 texts gives cosine ≥ 0.9992 to the stored
    vectors.
- **Near-duplicates** (cosine ≥ 0.93 within 72 h, greedy anchors).
  - 10.5% of usable articles are duplicates. Group size: median 1, p99 3, max 48.
  - **`keep` = 1,494,138**: 14,872 in 2023-H2, 456,882 in 2024, 818,447 in 2025, 203,937 in 2026.
- **Novelty.**
  - Median 0.206, p10 0.070, p90 0.351; 0.37% equal 1.0 (no representative in the 7 previous days).
  - Against all earlier articles (PREREG §6.5 wording) instead of representatives: mean |Δ| 0.0017, 5.0% of
    articles differ by more than 0.01, Spearman 0.997 (40 companies, 94,037 articles).

### 3.6 Leakage audit (S10; `leakage_ic.csv`)

Kept W0 articles, public sessions 2023-07 … 2025-12-31. Daily Spearman IC of the ticker-day mean vendor
sentiment, Newey–West t (5 lags).

| Cell | Ticker-days | IC(z_on) | t | IC(z_id) | t | LEAKY |
|---|---|---|---|---|---|---|
| all | 170,318 | 0.050 | 12.8 | 0.004 | 0.8 | no |
| summary present | 163,974 | 0.053 | 13.5 | 0.003 | 0.6 | no |
| summary absent | 50,111 | 0.028 | 3.7 | −0.003 | −0.4 | no |
| aggregator | 68,801 | 0.093 | 14.5 | 0.010 | 1.8 | no |
| auto_generated | 65,029 | 0.044 | 6.4 | −0.007 | −1.3 | no |
| major_outlet | 11,559 | 0.068 | 6.0 | 0.014 | 1.2 | no |
| other | 74,352 | 0.020 | 4.2 | 0.004 | 0.8 | no |
| press_wire_primary | 98,844 | 0.044 | 10.1 | 0.004 | 0.9 | no |
| retail_analysis | 25,157 | 0.056 | 6.1 | **0.031** | **3.0** | no (IC(z_id) < IC(z_on); diff t −2.0) |
| date_only | 53,437 | 0.013 | 2.4 | −0.000 | −0.0 | no |
| exact | 139,966 | 0.060 | 15.2 | 0.007 | 1.9 | no |
| hour | 25,046 | 0.028 | 3.6 | 0.008 | 1.0 | no |
| minute | 56,177 | 0.049 | 6.4 | 0.013 | 2.3 | no |
| after_fact = False | 168,155 | 0.046 | 11.8 | 0.001 | 0.2 | no |
| after_fact = True | 26,370 | 0.165 | 14.7 | 0.051 | 5.7 | no |

**`configs/frozen.yaml` `news:`**:
- `summary_variant_allowed: true`
- `excluded_sources: []`
- `leakage_audit_sha: cb82051d…ac19` (the sha256 of `leakage_ic.csv`)
- `parsing_allowed_none: pending_operator`

### 3.7 Coverage and leavers (S11)

- **Coverage.** 18,555 member-months (2023-07 … 2026-07, 556 companies); **91.4% covered**: 2023-H2 61%,
  2024 95%, 2025 99%, 2026 98%. Uncovered member-months are missing, not "no news" (§3.4).
- **Leavers** (61 companies; kept articles per member-day in their last 60 member sessions, against stayers
  with the same tier and sector):
  - median ratio 0.76;
  - 26% of leavers have no kept article in that window. These are mostly 2023 exits from the sparse backfill
    (AAP, ATVI, SEE, SEDG, PXD, …), names the vendor never tracked (AMTM, SOLS), and 5 exits before the
    corpus starts (DISH, FRC, LUMN, SBNY, SIVB).
  - Among leavers with news the ratio ranges from 0.18 (WBA) to 2.45 (ENPH): acquisition targets (JNPR, CZR,
    DFS, EMN) have more news, and companies in decline (WBA, AAL, IPG) less.
  - NA-03's placebo and coverage rules should keep in mind that leaver news is thinner.

### 3.8 Re-derived §14 diagnostics (S13; `rederived_diagnostics.md`, sessions 2024-01-02 … 2025-12-31)

These replace the 2026-10-24 exploratory numbers, which used 2026 data and no availability rule.

- **Overnight share of stock-specific variance** (covered member-days):
  - no news: **21.5%**;
  - intraday-only news: 23.3%;
  - pre-open news: **27.5%**;
  - pre-open earnings news: **54.7%**.

  The exploratory figures were 25% / 38% / 47%. The pre-open figure falls once date-only articles stop being
  counted as pre-open news.
- **W0 vendor sentiment.**
  - Gap: IC **0.054** (t 16.4), 14.8 bp per sentiment unit (t 14.2).
  - Open→close: IC 0.0065 (t 2.3), 1.9 bp (t 3.0).
  - Close-to-close: IC 0.038 (t 12.0).
  - Next day: IC 0.001 (t 0.3). Next 5 days: IC −0.001 (t −0.3).

  The exploratory figures were +6 bp gap and +0.8 bp open→close. In the robustness split (2024-H1, 25%
  date-only stamps) the open→close IC is 0.017 (t 2.8), against 0.003–0.007 elsewhere.
- **After |z_on| > 2.** The same-day reaction reverses for most tags: macro_sector −0.13 (t −5.0),
  product_launch −0.16, analyst_action −0.10, other_corporate −0.28, and gaps without any news −0.18 (t −8.0).
  M&A (+0.15, t 1.9) and guidance (+0.20, t 1.5) continue. Over t+1…t+5 no tag differs from 0 at t > 2.

## 4. Spend

OpenRouter $0.00 this chunk, $0.00 cumulative (`ledgers/spend.jsonl` empty). FMP requests: 0. Kaggle: none.

Network: one download of the bge-small-en-v1.5 weights (~130 MB) from the Hugging Face Hub into
`~/.cache/huggingface`. No article text or derived data left the machine.

## 5. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| Data/news `date` | precision, t_avail (§2.3), W0/W2 | t_avail is the end of the stamp's precision period; date-only → 23:59:59 UTC |
| Data/news title, snippet | flags, scrubbed text, embeddings, dedupe, novelty | known at t_avail; dedupe and novelty use only articles at or before t (novelty: strictly before) |
| Data/news summary | `summary_present` only | `selection_only`; the text is not stored |
| vendor sentiment, tags, flags, `event_*`, `non_news`, `parsing_allowed` | selection flags, audits | `selection_only` (produced retrospectively; CLAUDE.md A6) |
| snapshot symbols, symbol_tickers, companies | mapping | `static`; curated alias validity ranges at t_avail |
| members_by_session | member filter at `session_w2`, coverage, leavers | `static` (index changes are announced in advance) |
| panel_public z_on, z_id, z_cc, ar_*, σ_cc | leak signature, leakage audit, diagnostics | `post`; used only as audit targets on sessions ≤ 2025-12-31 (asserted) |
| tiers_monthly tier | leaver matching | `t_minus_1`; labels only, no price |

`dup_count` (total group size) includes later duplicates and is registered `post`. The PIT versions are
`dup_count_w0` (registered `w0`) and `dup_count_w2` (`w2`).

## 6. Deviations from PREREG

Four rows were appended to the §15 Deviations log (2026-10-24, NA-02), all before the freeze. As with NA-01,
they are **in the working tree, not committed**, for the operator to commit with their docs.

1. **§3.2 / §6.2 mapping.** Curated renames, restrictions and share-class aliases complete ATOM's empty ticker
   history.
2. **§6.2 / §6.5 dedupe and novelty.** Greedy backward-looking groups. Novelty is measured against
   representatives (PRD S8; §6.5 says articles; the difference is measured).
3. **§6.3–6.4 scrubbing.** The detector and price-level rules. Fully scrubbed articles are not kept. The
   language limitation.
4. **§6.4 leakage audit.** The rule operationalized, the cells, and the window, which includes val-B returns
   of a vendor field.

PRD-level choices with no PREREG change are in `docs/decisions/NA-02.md`:
- the mapped-share definition;
- fp16 embedding compute;
- the new `selection_only` registry kind;
- `source_class_domain` next to `source_class`;
- the `non_english_hint` flag;
- the staged build;
- the AC1 (c) fixture being minute precision.

## 7. STOP conditions and owner decisions

No STOP condition fired. Owner decisions needed:

1. **`parsing_allowed == None` (decide before NA-05).** None occurs only in 2024, where it covers 59% of
   member articles and 61% of cleaned ones in 2024-H2: 13.0% / 15.8% of 2024-07…2026-07, 0% from 2025.
   `third_party_ok` currently treats None as **not** allowed. The trade-off:
   - Treating None as not allowed removes 61% of 2024-H2 articles from the Kaggle training states (train
     2024-07 … 2025-06) and from 2024 API calls.
   - Treating None as allowed sends text whose redistribution status the vendor did not record.

   Options:
   - (a) keep None = not allowed;
   - (b) None = allowed;
   - (c) allowed for local models only (Laya local, embeddings), not for OpenRouter or Kaggle.

   The answer goes into `configs/frozen.yaml` `news.parsing_allowed_none` and PREREG §15.
2. **Confirm the four NA-02 rows in PREREG §15.**
3. **Val-B use.** The leakage audit and the §14 diagnostics read val-B returns of vendor sentiment, as PRD
   NA-02 and PREREG §14 direct. No decision-model metric was computed, and `allow_val_b` is still false.
   Please confirm this is consistent with the val-B gate.
4. **Non-English articles.** 6.7% of kept articles carry `non_english_hint`. The detectors (and NA-04's
   masking) are English-only, so their price talk is not scrubbed. NA-03/NA-04 should either exclude them from
   states or translate them. The flag exists so either works.
5. **Members without vendor news.** There are 20 (CRH, DELL, ERIE, FLEX, SNDK, SW, Q, AMTM, SOLS, XYZ/Block
   after 2025-01, …). They are uncovered, hence missing, in every month. A re-export from NewsWitch with
   current tickers would fill them.
6. **Summary variant.** The audit allows it (`summary_variant_allowed: true`). PREREG §6.4 keeps title +
   snippet primary, and §11.6 runs the summary variant as robustness only.
7. **`retail_analysis`.** It passes §6.4, but its pre-open sentiment has a significant open→close IC (0.031,
   t 3.0). NA-03 may want to watch it as a filter input.
8. **NewsWitch text in committed artifacts.** The PRD requires `spam_judgments.csv` (1,200 titles) and
   `detector_eval.csv` (400 real sentences) to be committed.
   - The 3 rows from `parsing_allowed == False` articles are redacted (judgments kept).
   - 217 rows come from articles with `parsing_allowed` = null and are kept pending decision 1.
   - Both files carry a `parsing_allowed` column. Do not push this repository to a public remote as is.

## 8. Files

- **Added — code.**
  - `src/newsaction/news/{__init__,load,mapping,detect,clean,sources,embed,dedupe,novelty,coverage,audit,build}.py`
  - `scripts/na02_report.py`
- **Added — configs.** `configs/{news,patterns,sources}.yaml`.
- **Added — docs and artifacts.**
  - `docs/decisions/NA-02.md`
  - `artifacts/NA-02/`:
    - this report;
    - `timing_audit.md` + 6 `timing_*.csv`;
    - `leakage_ic.csv`, `spam_judgments.csv`, `detector_eval.csv`;
    - `rederived_diagnostics.md` + 5 `diag_*.csv`;
    - `top_domains.csv`, `unmapped_top30.csv`, `unmapped_top100.csv`;
    - `parsing_allowed_{shares,monthly}.csv`, `flags_by_year.csv`, `leavers_news_rate.csv`;
    - `mapping_stats.json`, `summary.json`.
- **Changed.**
  - `src/newsaction/pit.py`: `selection_only` kind.
  - `configs/availability.yaml`: kind + 44 news columns.
  - `configs/frozen.yaml`: the `news:` block.
  - `docs/DATA_CONTRACT.md`: the NA-02 section, 5 artifacts.
  - `tests/test_pit.py`: kind list.
  - `tests/test_configs_match_prereg.py`: the news block replaces the null check.
  - `tests/test_lock.py`: the one-character edit no longer assumes `news: null`.
- **Changed, uncommitted.** `docs/PREREG.md` (§15 rows).
- **Tests added (104).**
  - `test_news_timing` 8, `test_news_mapping` 10, `test_news_detect` 16, `test_news_clean` 25,
    `test_news_dedupe` 6, `test_news_novelty` 5;
  - `test_news_audit_dates` 11, `test_news_sources` 4, `test_news_coverage` 2, `test_news_embed` 4,
    `test_news_config` 13;
  - fixture `tests/data/detector_planted.csv`.
- **Derived (gitignored).** `work/news/{articles_stage1,articles_clean,embeddings_ts,coverage_member_month,
  market_articles}.parquet` (3.9 GB); `work/MANIFEST.json`.
- **`make verify`:** exit 0.
  - ruff: "All checks passed!", 69 files formatted.
  - mypy --strict: "no issues found in 32 source files".
  - pytest: **455 passed, 1 xfailed** (NA-01's literal AC3(c) bound).
  - manifest OK (29 artifacts, 10 inputs); ledgers OK (test_access 2, spend 0).
