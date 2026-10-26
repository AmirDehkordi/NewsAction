# NewsAction — Pre-registration

**Version:** v0 (2026-10-24). **Status:** DRAFT, committed in NA-00. Selections made by the protocol below are recorded in `configs/frozen.yaml`. This file, `configs/*.yaml` and the target/reaction code are **frozen and hash-locked in NA-11, before any test-period (2026) model call**. Edits are allowed only through the Deviations log (§15).

**How to read this file.** Every symbol used in code refers to a section here (e.g. "PREREG §5.4"). Exact strings (question wording, codebook thresholds) live in `configs/questions_v1.yaml` and `configs/codebook_v1.yaml`. They are written in NA-04 from §6.11–§7, and the freeze hash covers them.

---

## 0. Purpose

We measure whether decision models can:
- **(a)** read company news available before the open and anticipate the market's reaction;
- **(b)** judge, given the part of the reaction already visible, whether the market over- or under-reacted. This includes important news that produced only small moves.

We also measure **how much predictive value comes from news vs. from the observed price reaction**. All of this is done without look-ahead, on S&P 500 point-in-time members in three size tiers.

## 1. Hypotheses

### 1.1 Primary (Holm-corrected, family α = 0.05; test period)

- **H1 — Priced at the open.** For D0 events, Call A's news-implied move N̂ predicts the overnight gap z_on much more strongly than the subsequent open→close return z_id.
  - Test: the paired difference IC(N̂, z_on) − IC(N̂, z_id) of daily Spearman ICs is > 0, using a stationary block bootstrap over days.
- **H2 — Explained moves persist; unexplained moves reverse (central).** In the pooled regression y = a + b·N̂ + c·G + (day × tier fixed effects) + ε, with **no conditioning on |G|**:
  - **b > 0:** underreaction to news.
  - **c < 0:** overreaction to price.
  - Here y is the subsequent abnormal return (§5.6) and G is the observed reaction at the decision point (§5.5).
  - Primary decision point: D2 (y = z(O_{t+1}→C_{t+5})). D1 is used if 30-min bars exist (y = z(10:00→C_t)).
  - Both coefficients are tested one-sided; standard errors are two-way clustered (date, firm).
- **H3 — Complementarity.** Adding Call B's judgments J to {price-only R, Call A N} raises the out-of-sample IC for the subsequent return.
  - Test: ΔIC = IC(R+N+J) − IC(R+N) > 0 on the test period, block bootstrap.
- **H4 — Width.** The judged materiality, surprise and E|N̂| predict |z_cc| on D0 event days beyond a realized-volatility (HAR) model + earnings-day flag + tier.
  - Test: out-of-sample ΔR² > 0, block bootstrap.

### 1.2 Secondary (Benjamini–Hochberg, q = 0.10)

- **H5 — Firm-level Roll R².** Share of stock-specific daily variance explained ex post by same-day news (D2 Call A on W2 news, price-language scrubbed) vs. predicted ex ante (D0).
- **H6 — Style vs. content.** Conditional on content (tag type, quantified flag, materiality, N̂), a more promotional or sensational tone (Q4) predicts reversal (negative coefficient in the H2 regression augmented with tone × sign(N̂)).
- **H7 — Decision models as instruments.**
  - Trained (Laya-Fin, anchor) vs. zero-shot IC on val-B and test.
  - Calibration (ECE) before and after temperature fitting.
  - Cost per 1,000 decisions.
- **Heterogeneity cuts (≤ 6, BH):**
  - Tier: Top-100, 101–250 and 251–500 (3 cuts).
  - Quantified vs. story news (1 cut).
  - Small moves |G| < 1 (1 cut).
  - Press wires / primary source vs. others (1 cut).

### 1.3 Headline-claim rule

A primary result is reported as a general claim only if it holds with the same sign and p < 0.05 (pooled) **both** for the selected primary instrument (§8.5) **and** for the clean anchor model (§9.2). Otherwise it is reported as model-specific.

## 2. Time conventions

- **2.1 Calendar.** NYSE (XNYS) sessions; regular session 09:30–16:00 America/New_York; half days close 13:00. All instants are stored in UTC; session dates are exchange-local.
- **2.2 Timestamp precision.** For the publication time `date` (unix seconds, UTC):

  | Class | Condition |
  |---|---|
  | `date_only` | seconds mod 86400 = 0 |
  | `hour` | seconds mod 3600 = 0, and not `date_only` |
  | `minute` | seconds mod 60 = 0, and not `hour` |
  | `exact` | otherwise |

- **2.3 Availability time** t_avail:

  | Class | t_avail |
  |---|---|
  | `date_only` | 23:59:59 UTC of that date |
  | `hour` | t + 3599 s |
  | `minute` | t + 59 s |
  | `exact` | t |

- **2.4 Windows for session s** (prev(s) = previous session):
  - **W0(s)** = (close(prev(s)), 09:15 ET of s]: news for **D0**.
  - **W2(s)** = (close(prev(s)), close(s)]: news for **D2**.
- **2.5 Decision points:**

  | Point | Decision time | Information | Tradeable entry |
  |---|---|---|---|
  | **D0** | 09:15 ET | Call A on W0 news; prices through close(prev(s)) | Official open of s (MOO) |
  | **D1** (only with NA-10 bars) | 10:00 ET | Call B on W0 news + reaction from close(prev(s)) to the 10:00 bar close | Price at the 10:00 bar close |
  | **D2** | After close(s) | Call B on W2 news + full-day reaction (close(prev(s)) → close(s)) | Official open of next(s) |

- **2.6 Processing delay.** Ignored, per the operator's instruction: news is usable from t_avail. Robustness (§11.6) moves the W0 cutoff to 08:00 and 09:30.

## 3. Universe, tiers, data

- **3.1 Membership.** ATOM `uni.member`, universe code `sp500`, half-open `valid_range`, evaluated at open(s). Leavers are kept while they are members.
- **3.2 Companies, not tickers.**
  - Dual share classes (same CIK in `ref.symbol`) are one company.
  - The representative class is the one with the higher 63-session dollar volume at the prior month-end.
  - Company market cap is the sum over classes.
- **3.3 Tiers.** Ranked on company market cap at the last session of the prior month: **Top-100** (ranks 1–100), **Mid** (101–250), **Rest** (251+).
  - Market cap = raw close × `shares_basic`, using the latest value with `known_from` ≤ the ranking session.
  - Shares are multiplied by the split ratios with ex_date in (period_end, ranking session].
  - Fallback: names without shares are ranked by dollar volume and flagged.
  - Robustness tiers: 63-session average dollar volume.
- **3.4 Coverage.** A member-month is *covered* if it has ≥ 1 cleaned article (§6.2). Uncovered member-months are **missing**: they are never treated as "no news" and never enter placebo groups.
- **3.5 Sources:**
  - ATOM snapshot (NA-01): raw OHLCV, membership, symbol-ticker history, GICS sectors, corporate actions, `shares_basic`, CIK, calendar.
  - `Data/prices/prices.parquet`: adjusted close.
  - `Data/market/*`: SPY close, VIX, DXY, oil, FRED vintages.
  - `Data/news_*.parquet`.
  - Optional NA-10: FMP 30-min bars.

## 4. Splits, purge, embargo, blinding

| Split | Range | Use |
|---|---|---|
| robustness-only | 2024-01-02 → 2024-06-28 | sparse coverage; many date-only stamps |
| **train** | 2024-07-01 → 2025-06-30 | fitting trained models, learned filters (§6.8) |
| **val-A** | 2025-07-01 → 2025-09-30 | search, calibration maps, temperatures, thresholds |
| **val-B** | 2025-10-01 → 2025-12-31 | confirmation and final selection |
| **test** | 2026-01-02 → 2026-07-31 | used once, after the freeze |

- **4.1 Purge.** An event's target is used within a split only if its whole horizon ends inside that split. Test horizons must end by 2026-07-31.
- **4.2 Embargo.** Events in the first 5 sessions of val-A, val-B and test are excluded from that split's evaluation.
- **4.3 Blinding.** 2026 prices are stored in `work/snapshot/sealed/` and read only through `newsaction.lock`.
  - `build_reactions()` (2026 observed reactions for Call B states) requires the freeze record.
  - `load_targets()` (2026 outcomes) requires the freeze record, a hash match and `NA_UNBLIND=1`.
  - Every read is appended to `ledgers/test_access.jsonl`.
- **4.4 Freeze (NA-11):**
  1. Record all selections in `configs/frozen.yaml`.
  2. Compute sha256 over this file, `configs/*.yaml`, `src/newsaction/panel/targets.py`, `src/newsaction/panel/reactions.py` and `src/newsaction/analysis/spec.py`.
  3. Write `artifacts/NA-11/freeze.json`.
  4. Tag `prereg-freeze`.
  5. Only then build 2026 Call B states and send any 2026 call.

## 5. Prices, returns, targets

- **5.1 Adjusted prices.** f_t = AdjClose_t (`Data/prices`) / RawClose_t (ATOM).
  - Adjusted open AO_t = RawOpen_t · f_t; AC_t = AdjClose_t. This handles splits, dividends and **spin-offs** (ATOM has no spin-offs; golden case GE 2024-04-02).
  - Returns: r_cc = AC_t/AC_{t−1} − 1; r_id = RawClose_t/RawOpen_t − 1; r_on = (1+r_cc)/(1+r_id) − 1.
  - QC flag when |r_cc − ATOM total return| > 50 bp.
- **5.2 Factors.**
  - Market: SPY, built the same way.
  - Sector: the **leave-one-out** equal-weighted mean return of the other same-GICS-sector members (same return type), with at least 5 other members.
- **5.3 Betas.** OLS over the 252 sessions ending t−1 (at least 126 observations) of r_cc on [r_SPY, (r_sec − r_SPY)], giving (β_m, β_s).
- **5.4 Abnormal returns and σ.**
  - AR_x = r_x − β_m·r_SPY,x − β_s·(r_sec,x − r_SPY,x), for x ∈ {cc, on, id, and intraday windows}.
  - σ_x = 1.4826 · MAD(AR_x) over the 126 sessions ending t−1 (at least 60 observations), floored at that day's cross-sectional 10th percentile.
  - Half days: σ_id is scaled by √(minutes/390).
  - z_x = AR_x/σ_x, clipped to [−10, 10].
  - Multi-day: z = ΣAR_cc / (σ_cc·√k).
  - Abnormal volume: z_vol = (log V_t − median over the 60 sessions ending t−1) / (1.4826·MAD).
- **5.5 Observed reaction G** (z units, at the decision point):

  | Point | G |
  |---|---|
  | D1 | AR(close(prev) → 10:00) / (σ_on² + σ_30²)^½, where σ_30 is estimated from historical first-30-min abnormal returns (NA-10) |
  | D2 | z_cc,t |

  D0 has no G.
- **5.6 Targets:**
  - **D0:** reaction understanding z_on,t and z_cc,t; tradeable y0 = z_id,t; secondary AR(O_t→C_{t+1}) and AR(O_t→C_{t+5}).
  - **D1:** y1 = AR(10:00→C_t) / σ_rest; secondary → C_{t+1}, → C_{t+5}.
  - **D2:** y2 = AR(O_{t+1}→C_{t+5}) (primary); also → C_{t+1}, → C_{t+20}, and AR(C_t→O_{t+1}).
  - **Eventual reaction:** e5 = AR(C_{t−1}→C_{t+4}) / (σ_cc·√5). Used for calibration maps and trained-model labels.
- **5.7 Placebo.** For each day × tier, the mean target over covered member-days with no selected event in W2 of the same or the previous 5 sessions. "Adjusted" targets subtract it. Raw and adjusted are always both reported.
- **5.8 Delistings.** If trading stops within a horizon, the last price is used and the event is flagged; sensitivity analyses exclude these events.

## 6. News, filters, states

### 6.1 Third-party rule

`parsing_allowed == False` articles are never sent to third parties (OpenRouter, Kaggle). The share with `None` is measured in NA-02, and the operator decides how to treat it before NA-05 (logged in §15).

### 6.2 Cleaning

Drop:
- `non_news == True`;
- `tag_type` ∈ {price_commentary, promotional_content};
- institutional-holdings (13F) auto-articles (title regex);
- articles that cannot be mapped to a member by symbol history.

Form-4 insider auto-articles are counted as metadata (insider activity), not used as text.

Near-duplicates (bge cosine ≥ 0.93 within 72 h, same company) collapse to the earliest t_avail; the duplicate count is kept as an attention feature.

### 6.3 Masking

Replace with neutral tokens:
- the company's names and aliases (ATOM name, legal suffixes stripped, curated aliases), tickers, cashtags and `EXCH:SYM` → "the company";
- person names (NER) → "an executive" / "a person";
- dates, weekdays, years and fiscal-period labels (e.g. "Q3 FY2025") → "the latest quarter" / "recently";
- share-price levels and percent price moves → removed (the price-language scrubber).

Fundamental figures (EPS, revenue, guidance numbers) are **kept**.

The target is < 0.5% residual name/ticker hits per state (scanner).

### 6.4 Text

Primary: **title + snippet** (contemporaneous). Variant S (title + LLM summary) is allowed only if the NA-02 leakage audit passes: for pre-open articles, the field's open→close IC must not reach its gap IC (t > 2). After-the-fact and price-path sentences are scrubbed from every news block. Pre-market price talk is stripped from Call A and kept in Call B's reaction context.

### 6.5 Novelty (point-in-time)

1 − max cosine (bge-small on title + snippet) to the same company's articles with t_avail strictly earlier, within 7 days.

### 6.6 Candidate filters

All candidates are scored at article level; the ticker-day score is the max over articles.

| ID | Rule |
|---|---|
| F0 | clean (§6.2) |
| F1 | material rules: F0 ∩ tag ∈ MATERIAL ∩ sentiment ≠ Neutral ∩ `event_age_days == 0` |
| F2 | hard + timely: F1 ∩ tag ∈ HARD ∩ intensity ∈ {Immediate, Short-Term} |
| F3 | source quality: F0 ∩ source class ∈ {press wire / primary source, major outlet} |
| F4 | novelty: F0 ∩ novelty ≥ threshold |
| F5 | logistic regression on title + snippet bge embeddings |
| F6 | LightGBM on: vendor tag, flags, sentiment, intensity; source class; novelty; 16 embedding PCs; attention ratio |

- MATERIAL = {earnings_results, guidance_outlook, analyst_action, ma_deal, legal_regulatory, financing_dilution, capital_returns, leadership_governance, operations_supply, partnership_customer, product_launch, competition}.
- HARD = {earnings_results, guidance_outlook, analyst_action, ma_deal, legal_regulatory, financing_dilution, capital_returns}.

### 6.7 Material label (ticker-day, W0 of session t)

A ticker-day is material if any of the following holds:
- |z_on,t| ≥ 2;
- |Σ_{j=0..5} AR_cc,t+j| / (σ_cc·√6) ≥ 2;
- z_vol,t ≥ 2.

It is **never** "large same-day move only": the delayed component keeps underreaction cases.

### 6.8 Filter protocol and selection rule

- F5 and F6 are fit on 2024-07-01 → 2025-03-31 (purged) and tuned on 2025-04-01 → 2025-06-30.
- All candidates are compared on **val-A** at a fixed budget: each threshold is set so that selected ticker-days ≤ 30% of covered member-days.
- **Rule:** choose the highest recall of material ticker-days, subject to delayed-reaction recall (|z_on| < 1 and |CAR z over t+1..t+5| ≥ 2) ≥ F1's.
- Ties (< 1 pp) go to fewer inputs, in the order F1 < F2 < F3 < F4 < F5 < F6.
- The chosen filter and threshold go to `configs/frozen.yaml`.

### 6.9 Events

One event per (company, session, window):
- D0 events use W0; D2 events use W2.
- At most 6 articles (highest filter score after deduplication) and ≤ 600 news tokens (ModernBERT tokenizer).
- Order: by score, then by t_avail.

### 6.10 State content

JSON with fixed keys. Encoding is per §6.11. Every value is computed with data through t−1 except `reaction_so_far`.

- `company`:
  - sector and industry (GICS);
  - size (tier words);
  - market sensitivity (β_m words);
  - volatility regime (σ_cc percentile vs. its own 252-session history);
  - recent abnormal performance over the past 5 / 20 / 60 sessions;
  - analyst-estimate trend (FY1 EPS consensus 30-day revision, CIQ, as-of);
  - earnings timing (a scheduled report within W0, from the earnings calendar).
- `market`:
  - previous-session SPY move;
  - VIX level percentile and change;
  - 10-year yield change;
  - high-yield spread change;
  - dollar move;
  - oil move;
  - scheduled macro releases today (CPI from FRED vintages, a fixed FOMC calendar).
- `attention`: articles vs. the 60-session average; number of distinct stories.
- `news`: a list of {headline, snippet, source type, timing words}.
- `reaction_so_far` (**Call B only**):
  - move since the previous close;
  - the market's move over the same period;
  - volume vs. normal for the time of day;
  - the time label ("by 10:00" / "by the close").

### 6.11 Codebook v1

**Move words** (|z|):

| |z| | Word |
|---|---|
| < 0.5 | negligible |
| [0.5, 1) | small |
| [1, 2) | moderate |
| [2, 3) | large |
| [3, 5) | very large |
| ≥ 5 | extreme |

Sign words are relative to "the market and its sector".

**Encodings:**

| ID | Form | Example |
|---|---|---|
| E0 | raw % | "+3.4% (S&P 500 +0.6%)" |
| E1 | σ-numbers | "+2.3σ" |
| E2 | words only | "large rise" |
| E3 | words + multiple | "large rise (≈2.3× a typical day's move)" |
| E4 | percentile words | "larger than 97% of its daily moves in the past year" |

The default before NA-07 is **E3**.

**Other scales:**
- **Percentile words** (level vs. own 252-session history): < 10 very low; 10–30 low; 30–70 normal; 70–90 high; ≥ 90 very high.
- **β words:** < 0.7 defensive; 0.7–1.2 market-like; 1.2–1.6 aggressive; ≥ 1.6 very aggressive.
- **Attention multiple:** < 0.5 unusually quiet; 0.5–1.5 normal; 1.5–3 busy; 3–6 very heavy; ≥ 6 extreme.
- **Tier words:**
  - Top-100: "one of the 100 largest US companies";
  - Mid: "a large US company (size rank 101–250)";
  - Rest: "an S&P 500 company (size rank 251–500)".
- **Timing words:** "after yesterday's close" / "overnight" / "early this morning (before 08:00)" / "shortly before the open".

## 7. Question battery v1 (exact text in `configs/questions_v1.yaml`)

All yes/no questions are **two-option `choice`** with neutral keys (Laya's `noul` can follow its labels). Score lists run lowest to highest.

**Call A:**

| ID | Type | Wording |
|---|---|---|
| Q1 `justified_move` | score, 9 levels | "Once investors fully absorb the news in `news`, how will the company's stock perform relative to the overall market and its sector over the next five trading days?" |
| Q2 `materiality` | choice | {new_information: "the news contains new, price-relevant information about the company", no_new_information: "the news is commentary, repetition or promotion without new price-relevant information"} |
| Q3 `surprise` | score, 5 | "How surprising is this news relative to what investors likely expected?" from "fully expected" to "very surprising" |
| Q4 `tone` | score, 5 | "How promotional or sensational is the tone of this coverage?" from "neutral and factual" to "highly promotional or sensational" |

Q1's levels, low to high: very large fall (> 3 typical daily moves) · large fall (2–3) · moderate fall (1–2) · small fall (0.5–1) · no meaningful move (< 0.5) · small rise · moderate rise · large rise · very large rise.

**Call B** adds `reaction_so_far` and asks Q1 plus:

| ID | Type | Options |
|---|---|---|
| Q5 `reaction_adequacy` | choice | {wrong_direction, much_too_small, too_small, about_right, too_large, much_too_large}, each with a one-line description relative to "what the news justifies" |
| Q6 `continuation` | choice | {reverse, stall, continue}: "over the next five trading days, relative to the market and its sector" |

**Derived quantities:**
- N̂ = Σ p_k m_k, with m = (−3.5, −2.5, −1.5, −0.75, 0, 0.75, 1.5, 2.5, 3.5).
- E|N̂| = Σ p_k |m_k|; materiality M = P(new_information).
- J = P(much_too_small) + P(too_small) − P(too_large) − P(much_too_large); W = P(wrong_direction); C = P(continue) − P(reverse).
- RG = (N̂ − G)·sign(N̂) for |N̂| ≥ 0.5: **Under** if RG > 0.5, **Over** if RG < −0.5, otherwise **Fair**.
- Calibrated Ñ = isotonic map of N̂ → E[e5], fit on val-A per model (fit range stored).

## 8. Decision-model selection

- **8.1 Eligible models.** The decision-model catalog snapshot (NA-05), excluding:
  - aliases (`~…`) and `:free` duplicates;
  - models that fail the pilot (errors, silent truncation, missing probabilities);
  - endpoints that reject `data_collection: deny`.

  Local open-weight Laya is eligible.
- **8.2 Stage 1 (NA-06).**
  - **Sample:** all eligible models × 700 val-A D0 events, stratified by tier × month (seed 2026). Call A, masked, E3.
  - **Primary metric:** mean daily Spearman IC of N̂ vs. z_cc,t.
  - **Survivors:** Model Confidence Set at α = 0.10, using a stationary block bootstrap over days (block 5, 10,000 reps) on daily IC losses.
- **8.3 Stage 2 (NA-06).**
  - **Sample:** ≤ 6 survivors (highest stage-1 IC; ties go to the cheaper model) × 3,000 val-A events; Calls A and B (D2).
  - **Screens** (failing any one excludes the model from headline use):

    | Screen | Pass condition |
    |---|---|
    | Company identification (1 of 4 same-industry candidates; chance 25%) | ≤ 40% |
    | Counterfactual flip rate (200 edited states: beat↔miss, raise↔cut, upgrade↔downgrade) | ≥ 70% |
    | Masked vs. unmasked IC (paired, same events) | unmasked − masked ≤ 0.02, or paired \|t\| < 2 |
    | Shuffled-news mean daily IC | not significantly different from 0 (\|t\| < 2, Newey–West) |

  - Month identification is reported but is not a screen.
- **8.4 Encoding and anchoring (NA-07).**
  - **Encoding:** the encoding with the highest val-A IC, unless it is worse than E3 on val-B by more than 1 SE (then E3).
  - **Anchoring** is present if the slope of Call B's N̂ on G is ≥ 0.30 or corr(N̂_A, N̂_B) < 0.70.
  - If anchoring is present, N̂ always comes from Call A (two calls per event). Otherwise production may use Call B alone.
- **8.5 Final selection (NA-11, val-B).**
  - **Candidates:** stage-2 survivors that pass the screens + Laya zero-shot + Laya-Fin + the anchor.
  - **Primary metric:** daily IC of N̂ vs. z_cc,t on D0 events.
  - **Tie-break** (ΔIC < 0.005): the IC of J vs. y2, then the lower cost per 1,000 decisions.
  - The winner is the **primary instrument**; all others are reported.

## 9. Trained decision models (NA-08, Kaggle 2×T4)

- **9.1 Laya-Fin.**
  - **Init:** `convaiinnovations/laya`, subfolder `typed-decisions` (ModernBERT-large + decision head); revision hash recorded.
  - **Heads:**
    - H-react: 9-level score; label = bin of e5 with Q1's bins.
    - H-mag: 5-level score; label = bin of |z_cc,t| at {0.5, 1, 2, 3}.
    - H-cont (Call B): 3-class; label from sign(G)·y over the next window with ±0.5σ bands.
  - **States:** identical to the API states (masked; E3 unless §8.4 picks otherwise, in which case retrain once).
  - **Block dropout:** reaction block 0.3, context block 0.1.
  - **Training:** AdamW, learning rate 2e-5 (backbone) / 1e-4 (heads), max length 1024, ≤ 3 epochs, early stopping on val-A loss, seeds {13, 17, 23}; the reported model is the 3-seed ensemble.
  - **Calibration:** one temperature per head fit on val-A.
- **9.2 Clean anchor.** `answerdotai/ModernBERT-large` (Dec-2024 checkpoint; revision recorded), with identical heads and recipe. No distillation from any vendor model.
- **9.3 Controls.**
  - A shuffled-label run must give a val-A mean daily IC not significantly different from 0 (|t| < 2, Newey–West).
  - Retraining seed 13 must reproduce the IC within ±0.003.
  - Training labels must end ≤ 2025-06-30 minus the purge.
  - The Kaggle dataset contains labels only for train and val-A. Val-B and test are uploaded as states without labels; their labels stay local.
- **9.4 Test inference.** Call A test predictions may run before the freeze; Call B test predictions run only after the freeze (§4.4).

## 10. Baselines

1. Vendor sentiment, aggregated per event (mean of the 5-level score).
2. bge-small (title + snippet) mean-pooled per event + ridge (fit on train, λ on val-A).
3. Vendor tags/flags in LightGBM (fit on train).
4. Price-only model: G, z_on, momentum, z_vol and tier in LightGBM; for D0, momentum and volume only.
5. Laya zero-shot.
6. Best zero-shot API decision model (§8).
7. A generative LLM at matched cost on a 2,000-event val-B/test subsample (JSON output: probabilities over Q1 levels).

## 11. Evaluation

- **11.1 Primary metrics.**
  - Daily cross-sectional Spearman IC (mean; t from Newey–West with 5 lags on the daily series).
  - Out-of-sample R² vs. a zero forecast.
  - Quintile spreads.
- **11.2 Secondary metrics.**
  - Log-loss and Brier skill vs. climatology (3 classes split at ±0.5σ).
  - ECE (15 bins).
  - AUC for |z| ≥ 1.
- **11.3 Regressions.** Pooled OLS with day × tier fixed effects; standard errors two-way clustered (date, firm); Driscoll–Kraay (5 lags) as robustness.
- **11.4 Bootstrap.** Stationary block bootstrap over days, block 5, 10,000 reps, seed 2026.
- **11.5 Shapley decomposition (H3).**
  - Feature groups:
    - R = {G, z_on, momentum, z_vol, tier};
    - N = {N̂, M, surprise, tone};
    - J = {J, C, W}.
  - Fit the 7 non-empty group combinations with ridge regression.
    - For API models: fit on val-B, λ on val-A.
    - For trained models: fit on train, λ on val-A.
  - Report exact Shapley shares of test out-of-sample R² and IC, by tier.
- **11.6 Robustness:**
  - dollar-volume tiers;
  - excluding date-only and hour-precision articles;
  - excluding half days;
  - σ = 60-day standard deviation;
  - a non-overlapping sample (first event per company per 5 sessions);
  - the summary text variant (if allowed);
  - vendor tags in text;
  - W0 cutoffs at 08:00 and 09:30;
  - unmasked states;
  - raw vs. placebo-adjusted;
  - 2024-H1 (robustness-only);
  - Call B with the news removed;
  - shuffled news.

## 12. Strategies (NA-13; test period, validation shown for reference)

- **S-D0.** Rank D0 events by Ñ; long the top 20% and short the bottom 20% within each tier (pooled if a side has < 10 events); equal weight; β-hedged with SPY. Enter at the official open, exit at the official close; secondary exit at C_{t+1}.
- **S-D1** (with NA-10). Rank by J (and RG). Enter at the 10:00 bar close; exit at the official close, t+1 and t+5.
- **S-D2.** Rank by J (and RG). Enter at the next open; exit at t+1, t+5 and t+20, with calendar-time portfolios for overlapping horizons.
- **Confidence gating.** Trade only events at or above the model's val-A 70th confidence percentile (secondary variant).
- **Costs.** 5 / 10 / 20 bp per side; turnover; capacity at 1% of ADV.
- **Deflated Sharpe.** Computed with N = trials in `ledgers/trials.jsonl`.
- **Benchmarks.** Gap fade, vendor-sentiment rank, random-signal placebo.

## 13. Budget and STOP rules

- **OpenRouter:** $30 total. Per-chunk caps: NA-05 $0.2 · NA-06 $4 · NA-07 $2 · NA-09 $2 · NA-11 $18 · NA-15 $2 · reserve $1.8.
- **STOP conditions:**

  | Condition | Action |
  |---|---|
  | The pilot shows the state is billed per question | Reduce the battery to Q1 (+ Q5 for Call B); re-project; report |
  | The winner is priced above $0.12/M | Production = Call A + one Call B (D2); report |
  | Any projection exceeds the remaining budget | STOP and ask the operator |

- **FMP:** ≤ 3,000 requests, NA-10 only. **Kaggle:** free tier only.

## 14. Disclosure: exploratory analyses run before this pre-registration (2026-10-24)

Before v0 we profiled the corpus and ran diagnostics on S&P 500 point-in-time members from 2024-01 to **2026-07, including the test period**:
- article counts, tags and timing by year;
- overnight vs. intraday share of stock-specific variance (25% no-news / 38% pre-open news / 47% earnings);
- a Roll-style R² of 0.34 (0.37 on quiet days);
- vendor-sentiment ICs (gap +6 bp, t ≈ 17; open→close +0.8 bp, t ≈ 1.7; slight 1–5 day reversal);
- continuation after >2σ gaps by tag, size and sentiment agreement;
- selection rates and lift of rule filters (F0–F3 analogues).

These analyses **did not apply §2.2–2.3** (date-only articles were misassigned). They shaped qualitative choices only:
- focusing on heterogeneity;
- including rule filters F1/F2 as candidates;
- the 09:15 cutoff.

**No constant in this document was tuned on them.** NA-02/NA-03 re-derive them on data ≤ 2025-12 and only those versions are reported. Their 2026 values are not used as evidence.

## 15. Deviations log

| Date | Chunk | Section | Change | Reason | Before/after freeze |
|---|---|---|---|---|---|
| | | | | | |
| 2026-10-24 | NA-00 | §4.4 (2), §15 | The freeze hash covers this file *up to* the heading of §15; §15 itself is checked as append-only: `freeze.json` records the sha256 and byte length of the Deviations log at the freeze, and unblinding requires those bytes to be an unchanged prefix of the current log (`newsaction.lock`). | §4.4 hashes "this file", but deviations must stay appendable after the freeze (§15 heading rule; CLAUDE.md B11; PRD NA-12 permits appending to the log and makes a hash mismatch a STOP). Hashing the whole file would block unblinding after any post-freeze deviation; excluding §15 entirely would let earlier rows be edited. | Before |
| 2026-10-24 | NA-00 | §4.3 | Clarification, no code change: 2026 adjusted closes exist outside `work/snapshot/sealed/` in `Data/prices/prices.parquet`, `Data/market/market_prices.parquet` and its NA-00 copy `work/market/market_prices.parquet` (PRD NA-00 S11). The sealed directory holds ATOM raw OHLC (and later 30-min bars); blinding of close-based 2026 outcomes (z_cc,t, e5, ...) is procedural: `tests/test_blinding.py` (no 2026 date literals or sealed-path use in `src/` outside `lock.py`), `ledgers/test_access.jsonl` and verifier greps. | `Data/` is read-only and these closes are needed for t-1 features of 2026 sessions (§6.10 context; §9.4 allows Call A test predictions before the freeze), so they cannot be sealed by file placement. Operator to confirm. | Before |
| 2026-10-24 | post NA-00, pre NA-01 (operator request) | adds to §0, §1.1 (H2), §1.2, §5.5–5.6, §7, §11, §12 via **Amendment A1** below | v0.1: adds the convergence analysis — news-implied value V, remaining gap U_τ, level-unit CAR ladder from the open to t+20 with clean-window flags, H2-C (κ_h, λ_h, ψ, half-life, tracking error) and the S-CONV strategy. H2's primary test is unchanged. | The operator wants to see whether prices converge to the decision model's valuation of the news over the following horizons, and whether the price–value gap is tradeable. Added before any panel, target or model output exists. | Before |

### Amendment A1 (v0.1, 2026-10-24) — convergence to the news-implied value

A1 is operative from v0.1. It **adds** to the sections it names and never replaces them. Code and the PRD cite it as "PREREG A1.x".

- **A1.1 — Question** (adds to §0 and §1.1 H2).
  - After the news, does the price converge to the decision model's news-implied value?
  - How fast and how completely, from the open to t+20?
  - Is the remaining price–value gap tradeable?
  - H2's primary test (b > 0, c < 0) is unchanged; it is the general form of convergence.
- **A1.2 — Level units** (adds to §5.5–5.6).
  - G^lvl_τ = AR(close(prev) → τ) / σ_cc. At D2 this equals z_cc,t.
  - CAR^lvl_h = ΣAR from close(t−1) to h, divided by σ_cc,t with **no √h scaling**, for h ∈ {O_t, 10:00 (with NA-10 bars), C_t, C_{t+1}, C_{t+2}, C_{t+5}, C_{t+10}, C_{t+20}}. C_{t+60} is exploratory, where data allow.
  - Forward pieces AR(τ→h) for τ ∈ {D1 entry, D2 entry}.
  - E5^lvl = CAR^lvl at C_{t+4}.
  - Each event carries a clean-window flag clean_h: no other D2 event for the company in sessions (t, t+h].
  - Purge (§4.1) applies to every rung.
- **A1.3 — Value and gap** (adds to §7).
  - **News-implied value** V = isotonic map of Call A's N̂ → E[E5^lvl], fit on val-A per model (fit range stored). It is the model's estimate, in typical-daily-move units, of where the abnormal price settles once the news is absorbed.
  - **Remaining gap** U_τ = V − G^lvl_τ. At D0, U = V.
- **A1.4 — H2-C, the convergence ladder** (adds to §1.2; secondary family, Benjamini–Hochberg).
  - **κ_h > 0 and increasing in h.** κ_h is the slope of CAR^lvl_h on V.
  - **λ_h ∈ (0, 1].** λ_h is the fraction of U_τ closed by h, for τ ∈ {D1, D2}; the half-life is reported.
  - **ψ_{h*} = 0.** The price converges to V itself, not to a shrunken V. h* = t+20 is the equilibrium horizon; t+5 is the short equilibrium.
  - **Tracking error** RMSE(CAR^lvl_h − V) is below the naive (0) and price-only benchmarks.
- **A1.5 — Specification** (adds to §11). Pooled OLS with day × tier fixed effects and two-way clustered standard errors (date, firm).
  - **Ladder:** CAR^lvl_h = α_h + κ_h·V + ε. Full convergence by h means κ_h → 1; the share realized by h is κ_h / κ_{h*}.
  - **Gap closure:** AR(τ→h)/σ_cc = a + λ_h·U_τ + ψ_h·V + ε, for h ∈ {C_t (D1 only), C_{t+1}, C_{t+5}, C_{t+20}}.
  - **Half-life:** the first h with λ_h ≥ 0.5, with a block-bootstrap CI (§11.4).
  - **Reported by:** tier; quantified vs. story news; |G| bins; model (primary instrument and the anchor).
  - **Robustness:** clean-window events only; a plateau equilibrium (mean CAR^lvl over t+16..t+20); h* = t+10.
- **A1.6 — S-CONV, the primary strategy for H2** (adds to §12).
  - At D1 (10:00, with bars) and D2 (after the close; entry at the next open), rank events by U_τ.
  - Long the top 20% (price below value) and short the bottom 20% (price above value), within each tier; equal weight; β-hedged.
  - Exits: C_t (D1 only), t+1, t+5 and t+20, with calendar-time portfolios for overlapping horizons.
  - Costs, DSR and benchmarks as in §12. S-D1 and S-D2 (the J/RG versions) remain as variants.

| Date | Chunk | Section | Change | Reason | Before/after freeze |
|---|---|---|---|---|---|
| 2026-10-24 | post NA-00, pre NA-01 (operator request) | adds to §1.2 H5, §7, §8, §11, §13 via **Amendments A2 and A3** below | v0.2: (A2) an extended question battery (impact horizon, event type, numbers vs. story, scheduled, novelty, credibility, scope, uncertainty, mixed signals) plus two explanation questions; (A3) the firm-level explanation analysis inspired by Kelly–Su–Zhang: explanation R² ladder, explained share, explanation → persistence, reasons, and an optional market-level replication. No primary hypothesis changes. | Operator: decision models answer several questions per call, so ask more; and add the "can the news explain the move" analysis from Kelly–Su–Zhang (2026). Added before any panel, target or model output exists. | Before |

### Amendment A2 (v0.2, 2026-10-24) — Question battery v2: more questions per call

A2 is operative from v0.2. It **adds** to §7 (questions), §8 (selection uses the core battery only) and §13 (budget). Decision models answer every question in a request independently (the NA-05 pilot verifies this), so when the state is billed once per request, each extra question costs only its own tokens.

- **A2.1 — Core vs. extended.**
  - The **core** battery (§7 Q1–Q6) is unchanged. It is used everywhere: the tournament, the encoding/anchoring study, the trained models and all comparators.
  - The **extended** battery (A2.2–A2.3) is asked only of the **primary API instrument** in production (NA-11) and on a 500-event validity sample in NA-06 stage 2.
  - All yes/no items are two-option `choice` with neutral keys. The exact wording is frozen in `configs/questions_v1.yaml` (NA-04, groups `core` / `extended` / `explain`).
- **A2.2 — Extended Call A questions** (news only):

  | ID | Type | Question → options |
  |---|---|---|
  | Q7 `impact_horizon` | choice | "When will most of this news' effect on the stock price happen?" → {today, within_days (2–5 sessions), within_weeks, months_or_longer, no_material_effect} |
  | Q8 `event_type` | choice | "Which best describes the main news?" → {earnings_results, guidance_outlook, analyst_action, deal_ma_partnership, legal_regulatory, product_operations, management_governance, capital_returns_financing, sector_or_macro, other} |
  | Q9 `quantified` | choice | {numbers: "states concrete figures about results, guidance or deal terms", narrative: "describes developments without concrete figures"} |
  | Q10 `scheduled` | choice | {scheduled: "a pre-announced event, e.g. an earnings release or investor day", unscheduled: "an unannounced development"} |
  | Q11 `novelty` | choice | {new: "first report of new information", partly_known: "adds detail to something already reported", known: "repeats information investors already had"} |
  | Q12 `credibility` | choice | {confirmed: "official company or regulator statement, or filed data", credible_report: "credible media or analyst report", rumor: "unconfirmed rumor or speculation"} |
  | Q13 `scope` | choice | {company_specific, industry_wide, market_wide} |
  | Q14 `uncertainty` | score, 5 | "How much does this news change the uncertainty about the company's future value?" → "no change" … "very large increase" |
  | Q15 `mixed_signals` | choice | {one_directional: "the news points clearly one way", mixed: "it contains both positive and negative elements"} |

- **A2.3 — Explanation questions** (Call B: news + reaction; used by A3):

  | ID | Type | Question → options |
  |---|---|---|
  | Q16 `explains_move` | choice | "Does the news in `news` explain the stock's move in `reaction_so_far`?" → {fully_explains, partly_explains, unrelated: "the move is not explained by this news", contradicts: "the move goes against what the news implies"} |
  | Q17 `move_reason` | choice | "What is the most likely main reason for the stock's move so far?" → {Q8's nine company categories (all but `other`), market_or_sector_move, no_identifiable_news} |

- **A2.4 — Derived variables.**
  - **Expected impact horizon:** H = Σ p_k·h_k over h = {1, 3, 15, 60} sessions. P(no_material_effect) is excluded and renormalized away, and reported separately.
  - **Model-based labels:** event type, quantified, scheduled, novelty, credibility, scope.
  - **Uncertainty score:** U_unc (Q14).
  - **Mixed flag:** from Q15.
  - **Explanation score:** X = P(fully) + 0.5·P(partly) − P(contradicts).
  - **Reason:** argmax of Q17, with its probabilities.
- **A2.5 — Uses (all secondary/BH or descriptive; no new primary hypothesis).**
  - **Mechanism cuts:** H2/A1 results are re-run using the model's **own** event type and quantified flag. These are contemporaneous labels, so they remove the reliance on retrospective vendor tags. They are reported next to the vendor-tag cuts.
  - **Horizon validity:** the rank correlation between H and realized convergence speed. Speed is measured per event as the share of the t+20 move realized by C_t; a longer H should mean a smaller share.
  - **Width (H4):** U_unc and P(no_material_effect) are added to the H4 feature set.
  - **Reading validity** (NA-06 stage 2, 500 events; reported, never a selection screen):
    - `event_type` vs. the vendor tag;
    - `quantified` vs. `tag_quantified`;
    - `scheduled` vs. the earnings calendar;
    - `credibility = rumor` vs. `tag_rumor`.
- **A2.6 — Budget.**
  - The extended battery adds about 500–650 question tokens per request.
  - If the NA-05 pilot shows the state is billed per question, or the NA-11 projection with the extended battery exceeds the remaining cap, cut in this order:
    1. drop Q10, Q13 and Q15;
    2. use the extended battery on Call A D0 / Call A D2 / Call B D2 only (not on D1);
    3. use a stratified 50% event sample.
  - The core battery is never cut.

### Amendment A3 (v0.2, 2026-10-24) — Explaining realized moves (firm-level "Roll's R² 40 years later")

A3 is operative from v0.2. It **adds** to §1.2 H5 and §11. Kelly–Su–Zhang (2026) explain about 30–40% of **market** returns out of sample with GenAI-extracted newspaper reasons. We ask Roll's (1988) **firm-level** question: how much of a stock's own move can its news explain, and does being explained predict persistence?

- **A3.1 — Inputs.**
  - **D2 news-only reading:** Call A on **W2** news (everything published up to the close, with after-the-fact and price language scrubbed per §6.4). This gives N̂_W2, E|N̂_W2| and the A2 variables.
  - **D2 Call B explanation answers:** Q16 and Q17.
  - **Ex-ante D0 reading:** N̂_W0.
  - **Factor model:** market + leave-one-out sector (§5.2–5.4).
- **A3.2 — Explanation ladder (H5).** For covered member-days, report the **out-of-sample share of stock-specific daily variance** that each step adds:
  1. market + sector (Roll's baseline; exploratory ≈ 0.34 of total variance);
  2. \+ ex-ante news (D0 features);
  3. \+ ex-post news (D2 Call A features; adds news that arrived during the day);
  4. \+ explanation features (X, reason).

  Days without a selected event contribute zero news features and are kept, as in Roll.

  - **Fitting:** ridge, using the §11.5 protocol. API outputs are fit on val-B with λ chosen on val-A; trained models are fit on train with λ on val-A. Everything is evaluated on test.
  - **Cuts:** tier; the model's event type; event vs. non-event days.
  - **Interpretation:** step 3 − step 2 is information that arrived during the day; step 2 ÷ step 3 is the share of the explainable move that was knowable before the open.
- **A3.3 — Explained share.** The share of event-day stock-specific variance (Σ AR²) falling on days the model judges *explained* (X ≥ 0.5) vs. *unexplained*, by tier and by reason.
- **A3.4 — Explanation predicts persistence** (Chan 2003, Savor 2012, now measured with decision models).
  - **Regression:** sign(G)·y = a + θ·X + controls(|G|, N̂, tier, event type) + day × tier FE.
    - At D2: y = AR(O_{t+1}→C_{t+5}).
    - At D1: y = AR(10:00→C_t).
  - **θ > 0** means explained moves persist and unexplained moves reverse.
  - Secondary (BH); standard errors two-way clustered.
  - Persistence is also reported by `move_reason`: Kelly–Su–Zhang's "themes" at the firm level.
- **A3.5 — Market-level replication** (optional, exploratory).
  - One state per session from that session's market-index articles (`^GSPC`, `^VIX`, `DX-Y.NYB` tickers; dates masked).
  - It asks Q1 (phrased for "the S&P 500 relative to its typical daily move") and Q17 with market reasons.
  - Report the out-of-sample R² of SPY's daily return on the readings, on our corpus, as a direct analogue of Kelly–Su–Zhang.
  - About 400 val + test sessions, so about 400 calls.

| Date | Chunk | Section | Change | Reason | Before/after freeze |
|---|---|---|---|---|---|
| 2026-10-24 | NA-01 | §3.2 | Share classes are grouped by CIK where ATOM has one, otherwise by issuer name with the class designation removed ("Alphabet Inc. (Class A)" ~ "(Class C)"). Result: GOOGL/GOOG, FOXA/FOX, NWSA/NWS; 565 symbols → 562 companies. | `ref.symbol.cik` is filled for 6 of 1,615 symbols, so "same CIK" groups nothing. Operator to confirm. | Before |
| 2026-10-24 | NA-01 | §3.2–3.3 | Company cap = raw close of the representative class × that class's `shares_basic` (not a sum over classes). Shares are brought to the ranking session's basis by **dividing** by the true splits with ranking session < ex_date ≤ the CIQ pull date (`ingested_at`), instead of multiplying by splits in (period_end, ranking session]. ATOM's spin-off pseudo-splits (split rows with a price ratio, e.g. GE 1.253) never scale shares. | CIQ `shares_basic` in ATOM is a company-level count (identical for GOOGL and GOOG; FOX carries an implausible value) and is restated to the split basis of the 2026-08-01 pull: 115/115 true splits checked are restated (NA-01 REPORT). The §3.3 formula assumes as-reported shares and would mis-scale every pre-split cap; summing would double-count Alphabet and News Corp. Operator to confirm. | Before |
| 2026-10-24 | NA-01 | §3.3 | For ranking sessions in the test period (tiers of Feb–Jul 2026) the raw close is blinded, so it is reconstructed: RC_t = AdjClose_t / f_t with f carried forward from the last public session through ATOM's split rows and cash dividends (Yahoo's dividend convention). Dollar volume in test sessions comes from Data/prices volume, unit-matched to ATOM over the last 63 public sessions. Ids without Data/prices keep their last public close and ADV (`stale_public`). | Tiers of the test months are t−1 inputs needed before the freeze. Validated on public data (anchor 2025-06-30, months 2025-08 … 2026-01): daily median error 0, p99 0.23%, and 100% tier agreement in every month. No blinded file is read. Operator to confirm. | Before |
| 2026-10-24 | NA-01 | §5.1 | The 40 ATOM ids without a validated Data/prices symbol (CBOE, CRH, DELL, ERIE, BK/BNY, MMC/MRSH, FI/FISV, XYZ, WBA, …) use ATOM's total-return close (splits, spin-off pseudo-splits and cash dividends) as AdjClose (`adj_source = atom_total`). Their test-period closes are blinded, so their close-based t−1 features become NaN once a window needs test sessions. | Data/prices lacks these names (download failures or never requested). Where both exist, ATOM total and Data/prices r_cc differ by > 50 bp on 47 of 524,907 symbol-days. Dropping them would remove ~7% of members. Operator to confirm. | Before |
| 2026-10-24 | NA-01 | §5.2 | The sector pool counts one representative class per member company and leaves the symbol's whole company out. For sessions before the first membership snapshot (2022, used only by betas and sigmas from 2023-07), the pool uses the 2023-01-03 membership. GICS is level 1 only and static (ATOM has no history and no levels 2–4). | Prevents Alphabet's second class from entering Alphabet's own factor. Membership is exported from 2023-01-03 (PRD NA-01 S1.a). The missing GICS industry level affects §6.10 (NA-04 decides). | Before |
| 2026-10-24 | NA-01 | §5.4–5.6, A1.2 | Clarifications fixed in `panel/risk.py` and `panel/targets.py`: (i) z_vol needs ≥ 40 of the 60 sessions; volume is ATOM raw volume on one true-split basis (test sessions: Data/prices volume, unit-matched, NaN from a test-period split onward); (ii) the sigma floor is applied before the half-day scaling of sigma_id; (iii) a z target over one intraday piece plus k close-to-close days divides by sqrt(σ_id² + k·σ_cc²); D0 targets use the sigmas of row t, D2 forward targets those of row t+1 (data through t); multi-day z targets are not clipped; (iv) after a symbol's last traded session AR_cc counts as 0 (last price held, flagged `delist_within_c20`); a gap inside a horizon gives NaN; sessions before the first split form a `warmup` split for purging. | §5.4–5.8 do not specify these details, and the frozen target code must. | Before |
| 2026-10-24 | NA-01 (verification round 1, finding F1) | §3.3 | Shares are cross-checked against an independent count: the Yahoo share count of the same class (`work/market/shares.parquet`; the latest observation 45–400 days before the ranking session, after any split has settled, and within 1.5× of its own trailing-year median). If CIQ is missing or differs by more than 1.5×, the Yahoo count is used and both are recorded (`tiers_monthly.shares_source`). DV-rank fallback only when neither exists (54 company-months, was 553). | ATOM's CIQ `shares_basic` is corrupt or missing for a number of large names: MRSH 1.07M from 2024-Q2, BNY interleaved 48–57M rows, CBRE 43M, CTRA 18.5bn, HES 18M, JNPR 14M, CTLT, SEE, WRK, MRO, CMA, IPG; no rows at all for single-letter and class tickers (V, T, C, F, D, O, A, J, K, L, CB, BRK-B, BF-B). This mis-tiered 102 companies in 404 public company-months (`artifacts/NA-01/tier_changes_vs_first_build.csv`). Residual: Yahoo counts all share classes where CIQ counts Class A only (BX, IBKR, ARES, CVNA, SATS), which matches §3.2's "sum over classes"; known Yahoo errors (DOC before 2024-03, UDR 2023, PSKY 2026) change ranks but no tier. Operator to confirm. | Before |
| 2026-10-24 | NA-01 (verification round 1, finding F2) | §3.3, §5.1 | Raw price-level check: at each cash-dividend ex-date the Data/prices factor jump equals D / traded close, so D / jump recovers the traded price level. A symbol whose ATOM raw close is off from that level consistently (median ratio > 1.25× off, ≥ 4 ex-dates, IQR ≤ 0.05) gets a level factor applied to every price *level* used for caps and dollar volume (returns are ratios and unchanged). Only HON is flagged (ratio 2.000 over 16 ex-dates; 434 names checked, 98% within 0.99–1.01). In test months such symbols carry their last public close with shares on that session's basis. `tiers_monthly` keeps no reconstructed test-period price levels (raw close, cap, ADV are NaN for test months). | ATOM's raw HON closes in 2023–2025 are half the traded price (2025-09-04: $107.58 vs $215.16), together with a 0.5 split row on 2026-06-29 and CIQ shares restated to it, which put HON in Mid (cap ≈ $68bn) instead of Top-100 ($140bn). The verifier's suggested Yahoo-cap check would also flag NVDA, CMG, DD and AMCR around their splits; the dividend-level check flags HON alone. Operator to confirm. | Before |
| 2026-10-24 | NA-01 (verification round 2, finding F3) | §5.4, §3.3 | ATOM raw volume is put on the traded share basis before any use. A day whose ATOM volume × the true split ratios after it, compared with Data/prices volume and centred on the symbol's public median, equals the product of the first j pending splits (±10%) is divided by that product (`adjust.volume_basis_check`). For an id with a raw price-level factor (F2 row), dollar volume uses raw volume ÷ that factor. | ATOM's raw volume for the 20 sessions before the ORLY (2025-06-10, 15:1), NOW (2025-12-18, 5:1) and TPL (2025-12-23, 3:1) splits is already split-adjusted while the raw close is not: z_vol reached +12 on those 60 days and ORLY's ADV was 5× too high. HON's ATOM volume is doubled as its price is halved. Otherwise ATOM and Data/prices volumes agree to 0.4% on 99% of days. Only volume-derived columns change (z_vol, volume baselines, ADV, DV tiers). Fixed at the operator's request. | Before |
| 2026-10-24 | NA-02 | §3.2, §6.2 (mapping "by symbol history") | News tickers (`EXCH:SYM`, US exchanges only; `.`/`/` normalized to `-`) resolve to ATOM symbols through validity ranges at t_avail built from ATOM's current tickers, ATOM `ref.symbol_ticker` and curated aliases in `configs/news.yaml`: renames SQ→Block (to 2025-01-21), PEAK→Healthpeak, CHK→Expand Energy, FB→Meta; NYSE:DOC is Healthpeak only from 2024-03-01 (before, it was Physicians Realty Trust); non-member share classes PARAA, BF-A, LEN-B map to their member company. Membership is by company at `session_w2`. Many-to-one collisions are refused. | ATOM's ticker history has 11 rows, all open from 1990, so it holds none of the renames PRD S2 names. The vendor tags by its own (2024-era) ticker list: old tickers persist after renames (BK, MMC, FI, PARA through 2026) and renamed companies' backfill carries the new ticker (CPAY, EG, DAY in 2023). Operator to confirm. | Before |
| 2026-10-24 | NA-02 | §6.2 (near-duplicates), §6.5 (novelty) | Near-duplicate groups are formed greedily in time order within company: an article joins the most similar *representative* with t_avail in [t−72 h, t] if cosine ≥ 0.93, otherwise it starts a group. Groups never chain beyond 72 h and an article's group depends only on earlier articles. Groups and novelty are computed over cleaned articles whose scrubbed text is non-empty. Novelty compares with the company's earlier **representatives** (PRD S8) where §6.5 says "articles"; on 40 random companies (94,037 articles) the mean absolute difference is 0.0017, 5.0% differ by more than 0.01, Spearman 0.997 (NA-02 REPORT). The total duplicate count includes later duplicates and is registered `post`; `dup_count_w0` / `dup_count_w2` count members in the representative's own window. | §6.2 does not say how groups form; connected components would let a later article merge earlier groups and change past representatives, breaking PIT novelty (PRD AC4). The PRD and §6.5 differ on the comparison set; the representative version is the PIT-consistent pair with the grouping. Operator to confirm. | Before |
| 2026-10-24 | NA-02 | §6.3–6.4 (scrubbing) | The after-the-fact detector flags any sentence about a stock's or the market's price move or level: a stock subject with a move verb, a move with a same-session phrase, closed/opened up or down, "as of hh:mm", "trading higher", gaps, moving-average crosses, new highs/lows, and "<word> jumps 5%" unless a fundamental noun precedes or a comparison period follows. Pre-market talk needs a pre-market phrase **and** price content in the same sentence ("reports before the bell" is kept). Share-price levels are removed; price targets and per-share fundamentals (EPS, dividends, deal prices) are kept. An article whose title and snippet are fully scrubbed has no text and is not kept. | §6.3–6.4 name the categories but not the rules. Planted set: recall 1.00 (54 positives), 0 of 37 hard negatives flagged; judged precision 0.945 on 200 real flagged sentences (`artifacts/NA-02/detector_eval.csv`). The detector is English-only; `non_english_hint` marks 6.7% of kept articles (mostly French, German, Spanish, Italian, Dutch and CJK). | Before |
| 2026-10-24 | NA-02 | §6.4 (leakage audit) | The audit rule is operationalized as: a cell is LEAKY when the daily cross-sectional Spearman IC of the ticker-day mean vendor sentiment of its kept W0 articles with z_id is ≥ its IC with z_on **and** t(IC with z_id) > 2 (Newey–West, 5 lags; days with ≥ 10 ticker-days), on public sessions 2023-07-03 … 2025-12-31 (train, val-A and val-B; robustness-only 2024-H1 included). Cells: summary present/absent, source class, precision class, after-the-fact flag. The summary variant is allowed iff the summary-present cell is not LEAKY; leaky source classes are excluded (`configs/frozen.yaml` news). | §6.4 states the rule in words; PRD S10 fixes the cells and the ≤ 2025-12-31 window. The audit reads val-B returns of a vendor field, not of any decision model (the val-B gate of CLAUDE.md C13 concerns model metrics); flagged for the operator. | Before |
| 2026-10-25 | NA-03 | §6.8 (fixed budget for rule filters) | Each candidate has an eligibility set (F0: ≥ 1 kept W0 article; F1/F2/F3: ≥ 1 article passing the rule; F4–F6: ≥ 1 kept article) and a ticker-day score (rules: constant 1; F4–F6: max article score). At the budget a filter selects min(30%, its eligible share) of the comparison sample, ranked by score and then by a seeded tie-breaker u = sha256("2026:{company_id}:{session}") / 2⁶⁴. A selection is frozen as (threshold, tie_u_max): eligible ∧ (score > threshold ∨ (score = threshold ∧ u ≤ tie_u_max)). F1 (46.1% of val-A days) and F3 (52.0%) are thinned at random to 30%; F2 (25.5%) and the continuous filters are unaffected. Natural-rate rows of F0–F3 are reported as references. | §6.8 sets every threshold so that ≤ 30% of days are selected, but a 0/1 rule has no threshold between "all its days" and "none". Read literally, F1 would select nothing, its delayed recall would be 0, and the underreaction constraint would become vacuous. Random thinning adds no information: a thinned rule keeps its natural precision. Operator to confirm. | Before |
| 2026-10-25 | NA-03 | §6.8 (comparison sample), §4.1–4.2 | The val-A comparison sample is the covered member company-days of val-A with a valid label: purged (the last 5 sessions, whose t+5 horizon leaves val-A) and without the first 5 sessions (§4.2 embargo). That gives 26,738 days, of which 21.1% are material and 7.2% delayed. The 30% budget is a share of this sample. A day with no kept W0 article stays in every recall denominator and can never be selected. | §6.8 says "covered member-days" without fixing how purge and embargo apply to the comparison. Both are §4 rules for any val-A evaluation. Operator to confirm. | Before |
| 2026-10-25 | NA-03 | §6.6 (F5, F6), §6.8 (fit / tune) | F5 and F6 are trained on articles. Each kept W0 article of a labelled covered member-day carries its ticker-day's material label, and the ticker-day score is the max over articles, as §6.6 requires. Each window is purged so that the label's t+5 horizon ends inside it: the fit window holds sessions 2024-07-01 … 2025-03-24 (89,253 days, 359,302 articles) and the tune window 2025-04-01 … 2025-06-23 (28,272 / 172,145). The tuning metric is the ticker-day material recall at the 30% budget, and the best grid point is frozen without a refit on the tune window. F5 is an L2 logistic regression on the standardized bge embedding (C ∈ {0.001, 0.01, 0.1, 1}). F6 is LightGBM (8 grid points) on: `tag_type` (not `tag_type2`), the five tag flags, sentiment (−2…2), intensity, source class, novelty, 16 PCs (PCA fit on the fit-window articles) and the W0 attention ratio. The ratio is usable articles today / max(their mean over the company's member sessions among the previous 60, 1/60), with ≥ 20 member sessions. | §6.6–6.8 name the models, features and windows but not the training unit, the tuning metric, or how purge applies inside train. The member-session mean avoids a spurious attention spike for index joiners, whose pre-membership news is not in the corpus. Operator to confirm. | Before |
| 2026-10-25 | NA-03 | §6.9 (events), A1.2 | D2 events use the frozen filter and threshold on W2 ticker-day scores (the max over W2 kept articles; F6 would use the W2 attention ratio). An article with `third_party_ok` False is left out of the list but counted. A selected ticker-day without any third-party-OK article gets no event (2024-H1 robustness: 2,205 of 2,894 selected D0 days; train: 5,180 of 22,939; 0 from 2025), because §6.1's `parsing_allowed` None policy is still pending and None counts as not OK. The 600-token block is the articles' title and snippet (blank-line separated) of NA-02's scrubbed text, measured before NA-04 masking. clean_h is computed from the D2 events as written and is missing when t+h runs past 2026-07-31. | §6.9 and A1.2 do not cover W2 selection, third-party exclusion or the data end. If the operator allows None articles, `events` is rebuilt (one stage, deterministic). Operator to confirm. | Before |
| 2026-10-25 | NA-04 | §6.10 (company block: industry) | The company block carries the GICS **sector** only; the industry field is left out. | ATOM holds GICS level 1 only, one static range per symbol (NA-01 §15 row on §5.2: "the missing GICS industry level affects §6.10 (NA-04 decides)"); no other point-in-time industry source exists in the registered data. A sub-industry would also identify many companies on its own (e.g. a one-member sub-industry). Operator to confirm. | Before |
| 2026-10-25 | NA-04 | §6.10–§6.11 (codebook scales §6.11 does not spell out) | `configs/codebook_v1.yaml` adds, marked "NA-04": (i) multi-day moves use z_m{k} = ΣAR/(σ_cc·√k) with E3 "≈k.k× a typical week's / month's / three-month move" and E4 "… of its weekly / monthly / three-month moves in the past year" (keys `past_week`, `past_month`, `past_three_months` = 5 / 20 / 60 sessions); (ii) market series (SPY, VIX change, 10-year yield, HY OAS, dollar, oil) are moves in their own units: z = change / (1.4826·MAD of the series' 252 previous changes, ≥ 126); the VIX level uses the percentile words; (iii) FY1 EPS 30-day revision words ("cut sharply" < −5% ≤ "cut" < −1% ≤ "little changed" < +1% ≤ "raised" < +5% ≤ "raised sharply", relative to max(\|earlier consensus\|, $0.10)); (iv) counts as words ("none" … "ten", "more than ten"); (v) volume vs normal on the attention-multiple scale (V_t / median of the previous 60 sessions); (vi) timing word "during today's trading session" for W2 news; (vii) the D1 time label "half an hour after the open" (no digits); (viii) source-type words from the domain class; (ix) "not available" for a value that cannot be computed through t−1. Only moves change with the encoding (E0 raw change with the S&P 500 in parentheses for stock moves; E1 one decimal; E3 multiple truncated to one decimal so it never contradicts its word; E4 "a rise / a fall larger than N% …"); every other scale is words in all encodings. | §6.10 names these fields and §6.11 gives no scale for them. Keeping the non-move scales fixed makes the NA-07 encoding study vary only the move encoding. Operator to confirm. | Before |
| 2026-10-25 | NA-04 | §6.10 (market block, earnings timing: availability) | Publication lags: market_prices closes and the 10-year Treasury yield (DGS10) are used as of the previous session; the ICE BofA high-yield OAS (BAMLH0A0HYM2) is used one session later (its change dated t−2), because it is computed after the US close and reaches FRED with a delay. CPI release dates are the ALFRED vintage dates of CPIAUCSL that add a new reference month (seasonal re-vintages excluded); FOMC statement dates come from the Federal Reserve calendar (URL in `configs/macro_calendar.yaml`). Earnings timestamps (naive) are read as America/New_York wall time; the windows are [close(prev s), 09:15 ET] for D0 and [close(prev s), close(s)) for D2, so a "16:00" report belongs to the next session. | §6.10 lists the series but not their publication times; the NA-00 data contract left the FRED and earnings-calendar availability rules to NA-04. A 16:00 stamp means "after the close", and the right-closed W2 window would otherwise put it in the wrong session. Operator to confirm. | Before |
| 2026-10-25 | NA-04 | §6.3 (masking: replacement tokens and rules), §6.4; amends the NA-02 row on §6.3–6.4 (price targets) | Quarter labels in any case ("Q3 FY2025", "Second Quarter", "SECOND-QUARTER", "3Q25", "3. Quartal") → "the quarter" / "quarterly" (not "the latest quarter"); half-year labels ("first half", "1H25") → "the half-year"; years 1900–2099 → "the year"; fiscal years → "the fiscal year"; dates, day ranges ("July 17-18"), weekdays and months → "recently", also in French, German, Italian, Spanish, Portuguese, Dutch, Polish (operator, 2026-10-25), Chinese, Japanese and Korean ("2025年8月7日（星期四）", "週一", "第二季度"); years also when glued to letters or CJK ("CY2025", "EHA2025", "2025年") and with a period ("2025Q2", "FY2025Q2", "Q2-25"); leading datelines (city, date, wire), ISIN codes and option contracts (expiry, strike, ticker: "250703 305.00C (ADI250703C305000)" → "option") removed. Tickers in every form, including any upper-case exchange code (BOATS:NEE), full-width CJK forms ("（紐交所：DE）", "（HOOD US）"), class / venue suffixes (NEE/PR, MS.N, COIN.US) and possessives (ODFL's); a ticker that is also an English word (COST, MET, ALL, MS) whenever it is written in capitals in a text not mostly in capitals, except a clock time ("4:30 PM") and IT before an IT noun ("IT spending"); ticker quotes and quote lines ("MPC-1.32%", "· IP. -0.58%", "|Price:49.32|Chg%:-0.60", "Price: 152.75, Change: -15.87") removed; Reuters exchange letters (AAPL-Q) and the company's drug codes (ABBV-400) count as its ticker; a name cut at the end of a snippet ("for Warner...") is masked. Chinese, Japanese and Korean company names taken from the corpus (the CJK words right before the company's own ticker in parentheses) → "the company"; names also when written without spaces ("MolsonCoors") or glued to the previous word or number ("Key TakeawaysHumana", "2025Principal"). Person names, including surnames used alone (operator, 2026-10-25): spaCy PERSON entities plus every capitalized occurrence of a corpus surname (last word of a multi-word name seen ≥ 3 times) or of a listed public figure (`configs/aliases.yaml` `person_names`); a name right after a role noun is dropped, otherwise "an executive" / "a person"; an entity made only of ordinary lower-case words ("Balance Sheet") is not a name; Chinese transliterations of Western names ("薩姆·阿爾特曼") → "a person". **Price levels** (operator, 2026-10-25; amends NA-02's rule that kept price targets and deal prices): a price-target change "to $622 from $600" becomes "raised by about 4%", a lone price-target amount is dropped, a per-share deal or offering price becomes "a per-share price"; per-share fundamentals (EPS, dividends) are kept. Sentences with a stock or share price move in percent or a share-price level ("boosts stock to $102.89") are dropped (§6.4) unless a fundamental noun is the subject or the amount is per share. Company names match in any case with spaces / hyphens interchangeable, except one-word common-word names ("Target", "Delta"), which match as written, capitalized or in capitals. | "The latest quarter" asserts that the quarter has been reported, which is false for guidance about the next quarter; "the quarter" is neutral. The NA-04 verification found the first masker left company tickers in 3.4% of val-A D0 states, names in ≥ 1.8%, quarter / half labels in 10.3%, non-English dates in 7.9%, price-move sentences in 2.2% and dollar price targets in 13.4% (they reveal the share-price level), and that its scanner reused the masker's own definitions; the operator chose the three policies marked above. The second verification found the company's own ticker in 2.40% of val-A D0 states (tickers that are English words, written in capitals: "MET earnings per share"), years in 3.0% ("CY2025", "2025年") and CJK dates, day-range remnants and option codes, all invisible to the scanner, which again copied the masker's English-word ticker list. §6.3 does not define the tokens or the NER post-rules. | Before |
| 2026-10-25 | NA-04 | §6.4, §6.10 (Call B context), §7 (question text) | (a) Pre-market price talk is **not** added to Call B's reaction context: `reaction_so_far` is the codebook block only (move since the previous close vs the market and its sector, the S&P 500's move, volume vs normal, the time label). (b) Call A on D2 (A3.1) uses the W2 event list and the W2 attention counts, so it shares a hash with the D0 state only when the list and every word agree. (c) Where §7 / A2.2–A2.3 give only option keys or end points, NA-04 wrote the remaining text (instructions of Q2, Q5, Q6, Q9–Q13, Q15; the middle levels of Q3, Q4, Q14; option descriptions of Q5, Q6, Q7, Q8, Q13, Q16, Q17); Q1's rise levels repeat the fall ranges ("small rise (0.5–1)"). Every string §7 / A2 gives verbatim is used verbatim (tests/test_states_questions_prereg.py). (d) Token budget (PRD S6 tightening): each state keeps the leading articles of its §6.9 list (lowest-ranked dropped first) such that state + the call's longest core question + 3 special tokens ≤ 1,024 ModernBERT tokens; for D2 the budget reserves the longest possible `reaction_so_far`, so Call A on D2 and Call B carry the same news and the cut never depends on the observed reaction. (e) An event none of whose articles keeps any text after masking and the second price-talk scrub gets no state (artifacts/NA-04/REPORT.md §3.1). | (a) The scrubbed sentences hold prices and percent moves; adding them back would put numbers into a state outside the codebook (CLAUDE.md A4). (b) A3.1 says "Call A on W2 news"; the attention block is part of that state. (c) §7 says the exact text lives in `configs/questions_v1.yaml`, written in NA-04 from §7. (d) §6.9's 600-token news cap was measured on the plain text; with JSON, context and the reaction block, 12% of Call B states plus their longest question exceeded Laya's 1,024 tokens (p95 1,062). (e) Such an event has no news to read. Operator to confirm. | Before |
| 2026-10-25 | NA-04 | §2 (availability), §6.4 (after-the-fact text), §6.9 (articles of a state), A3.1, A3.5 | Revision 3: two kinds of article are left out of every state, in any window or call (Call A D0 and D2, Call B, A3.5 market states, the NA-07 samples, the unmasked twin), by `configs/states.yaml` `news_exclusion` on NA-02's raw fields: (i) move explainers, i.e. a title "Why … stock/shares … today" (also "Here's why …") or StockStory's snippet "What Happened? Shares of / A number of …" (7,535 corpus articles); (ii) every TradingView domain (tradingview.com and its language subdomains; 38,135 articles). The NA-03 event lists are not refilled and the attention counts are unchanged. An event whose every listed article is excluded gets no state: 596 of 48,103 D0 events (1.24%), 503 of 62,285 D2 events (0.81%) and 224 Call B events; 8,537 D0 and 11,889 D2 listed articles are left out. The price-move filter also drops a move sentence whose verb is glued to a ticker ("DGXjumped 6.4%"). | Third NA-04 verification. (i) Explainers explain the session's move by construction: of 204 pre-open-stamped explainers about the company itself (2024-01 … 2025-09), 29 describe a move after their stamp (18 the same session, 11 the next). In W0 they are pre-market talk (§6.4) or look-ahead; in W2 they reveal the realized move in news-only states. (ii) TradingView reposts carry batch timestamps: 128 of 511 of their earnings summaries are stamped before the release they report (DGX's results of 2025-07-22 were stamped 07-21 13:01 UTC and sat in the 07-21 pre-open state); other outlets 0–7%, previews included. Operator decision 2026-10-25. | Before |
| 2026-10-25 | NA-04 | §6.3 (residual target < 0.5% per state), PRD NA-04 AC2 | Residual company names / tickers, labelled by hand on every val-A state: 1.29% of D0 and 1.00% of D2 / Call B states of the revision-2 build (1.26% / 0.97% on the revision-3 build). The independent scanner reports 0.10% because it cannot see one-word names that are ordinary words (Align, Carrier, Principal, Constellation, West, Regions, Duke, Wells), glued or inflected names ("Broadcomsaw", "Caterpillara"), lower-case tickers in URL slugs, the company's preferred / venue tickers (HBANM, GMM.U) and Korean / Japanese transliterations (about 30 more D0 states). This residue is accepted; there is no further name masking, and AC2's name/ticker target is met only on the scanner's count. Dates: revision 3 also masks written-out ordinal quarters and halves (FR, ES, IT, PT, DE, NL), "3T25", a bare T1–T4 after a period word, Korean 분기 / 반기, two-digit years after any apostrophe, a lone "Aug.", bare H1 / 2H, glued yyyymmdd, day-first dd/mm and "domingo": the verification's date residue fell from 3.86% to 0.13% of val-A D0 states (3.64% → 0.11% D2), the scanner's is 0.00%. | Masking is imperfect by nature (PRD NA-04 risks): content alone (fundamentals, deals, products) identifies about half of the states (the verification's read: 5 of 10), so 1% more adds little; NA-06's company-identification probe measures identifiability and results are reported by it. Operator decision 2026-10-25. | Before |
| 2026-10-26 | NA-04 | §6.3 (share-price levels and percent price moves removed), §6.4 (pre-market price talk stripped from Call A), §6.9 (articles of a state), A3.1, A3.5; applies the operator's decision B of 2026-10-25 (non-English articles dropped at the events/states step) | Revision 4. (i) **Non-English articles** are left out of every state, with the scope of row 6 (Call A D0 and D2, Call B, A3.5 market states, the NA-07 samples, the unmasked twin) and no refill of the NA-03 lists. The rule is `configs/states.yaml` `news_exclusion.non_english` on NA-02's raw title + snippet. A text is non-English when one of these holds: (a) it has ≥ 2 characters of a non-Latin script; (b) its distinct function words of other languages are ≥ 3 and outnumber its distinct English ones (2 suffice with no English one); (c) it has ≥ 3 distinct words with a non-English letter and ≤ 2 English function words. Words count in lower case or capitalized, so tickers such as DE are not "de"; "Las Vegas" and "Los Angeles" are removed first. It flags 7.7% of event articles (NA-02's `non_english_hint`: 5.0%). It finds 98–100% of the fourth verification's non-English price and date residue (the hint: 51–98%), and 205 sampled flags were all non-English. (ii) **English price talk.** Masking also drops: share-price levels after a verb or a currency amount after a share word in the same sentence, unless the amount is per share, a total or a size, or a fundamental is its subject ("shares closed yesterday at $242.66", "traded as high as $145.16", "AMD Stock Sees Clearer Path to $200"); the direction after the number ("Trading 2.4% Higher", "Moves 22.8% Higher", "closing 1% lower"); moves written as nouns ("1.95% Stock Rise", "closed at a 1.13% decline"). Price-target amounts in any currency notation become a relative change or go ("from GBX 420 to GBX 500" → "raised by about 19%", "at USD 220", "€151.88 / share"), as do "$X/Share" deal prices. A second pass followed a full listing of the cents amounts left in val-A states. Its main rule: after the price-target rewrites, a sentence that still holds a cents-precision amount goes, unless a per-share fundamental word (EPS, earnings, per share, dividend, FFO, consensus, estimate, guidance, …) is in it and no price word or move verb stands just before the amount ("The company traded as high as $155.51", "rallies to $202.34", "Receives $645.36 Consensus Price Target", "a one-year high of $66.44", insider "at a price of $251.12"). Sizes ("$9.05 Billion", "$6.16 bln") are not levels. The pass also covers price-target windows across abbreviation periods ("JPMorgan Chase & Co. from $104.00 to $96.00" → "lowered by about 8%"), quoted prices ("$554.00 (-3.11%)"), options-flow chatter, "an increase of 2.4% during after-hours trading", "Sep-25", "Jun-12-2025" and deal prices "$47.50 in cash a share". (iii) Row 6's explainer title rule also takes a move word between "why" and "today" ("Why Micron Technology Rallied Today", "Why Airline Stocks Are Flying High Today"): the old rule needed the singular "stock" or "shares", so 188 event articles had escaped (corpus explainers 8,760, before 7,535). Events left with no article: D0 871 (1.81% of 48,103; 254 of them only non-English), D2 814, Call B 480; events without text 107 / 66 / 31. States: D0 47,125, D2 61,405, Call B 41,852. | Fourth NA-04 verification (2026-10-26). Price talk survived in 2.52% of val-A D0 and 3.25% of D2 / Call B states by its independent scripts; the scanner reported 0.01% levels and 0.09% moves. About 9 val-A D0 states showed the company's own pre-market or after-hours move, i.e. the D0 overnight target (DAY 2025-08-18 "dispararam mais de 27% ... pré-mercado", against an overnight return of +24.7%). MarketBeat's "Trading N% Higher" survived in 0.54% of D0 states, and only rises, because NA-02 scrubs the "Trading Down N%" form. The masker and the price scrubbers are English-only, and NA-02's language hint missed 36% of the non-English price levels. No look-ahead was found: every timed hit was pre-market before 09:15 ET or about a past session. Operator decision 2026-10-26: fix before any API spend, because states are cached by sha256. After: the verification's scripts find no real hit (0.02% / 0.05% of val-A D0 / D2 states hit, all deal or revenue sizes next to "price target"); the listing of every cents amount left finds about 0.01% of states with a share price (an offering range, "reaching as low as $28.83"); the scanner 0.00% / 0.04%; dates 0.02% of D0 states; the accepted name residue (row 7) is unchanged in kind. The structural pass also drops some product and commodity prices (about 0.7% of event articles lose a sentence). | Before |
| 2026-10-26 | NA-04 | §6.3 (dates; every price move and every index or commodity level removed), §6.4, §6.9, A3.1, A3.5; amends rows 4 and 8 | Revision 5. (i) **Dates.** Masking also takes: month abbreviations standing alone in title case ("Jul, 2025" bylines, "24-Jun-2025", "in Aug,", "Sep nat-gas"; "Jan" and "Mar" only where a date is meant, since they are also names: "Jan Hatzius", "Del Mar"); weekdays and months glued to a word ("StockSavvyThursday", "OnJuly 27", "30thSeptember", "ESTAug 22nd", "AJuly"); lower-case months beside a day, a masked year, after "in" or in a URL slug ("july 14th", "in the june 2025 quarter", "effective-october-2025", "julyinvestordeck"); day ordinals and day numbers left beside a masked year or month ("24th, 2025", "the 23rd of the month", "Recently 25."); "FY-25", "4th qtr" and "6/8 15:18" datelines. (ii) **Every price move and every index or commodity level** (operator decision 2026-10-26, "all moves + index levels"): a sentence goes when it holds a percent or points move of any company, index, future, commodity, currency or bond, an index level ("Dow 46,414", "the 5,000 milestone") or a commodity or crypto level ("Gold Surges to $3,816", "Bitcoin Retakes $112K", "$63.56 a barrel"). A number is a move when a move word stands just before it, it is signed, or a move is named up to three words after it ("a 4.38% recent decline", "Mastercard's 13% 3-Month Rise"), and a market subject, the company or a ticker is its subject (after the last fundamental before it, or anywhere in a sentence without one), or the noun names the share price or a trading period. Fundamentals stay (revenue, margins, EPS, guidance, deliveries, AUM, macro gauges such as CPI or PMI, stakes and short interest, payments, a product's price, forecasts, the row-4 price-target changes). The rule also runs before NER, which would otherwise read "Gold Surges" as a person. (iii) **A3.5.** Index moves were the market states' own target: an index move or level was in 121 of the 450 market states outside the test split (26.9%), 17 of 449 (3.8%) after, those being fundamentals, forecasts and structured notes. A market session whose every article lost its text gets no state (1 session; 594 states). (iv) **Non-English residue accepted** (operator decision 2026-10-26): about 0.46% of val-A states keep a non-English item the row-8 rule misses (one with a Swedish month). Events without text: D0 148 (0.31%), D2 117, Call B 69 (revision 4: 107 / 66 / 31); states: D0 47,084, D2 61,354, Call B 41,814. | Fifth NA-04 verification (2026-10-26): AC2 failed on dates, 0.83% of val-A D0 and 0.91% of D2 states (the scanner reported 0), because the masker and the scanner both matched a short month name only before a day digit or a period. Outside AC2's metrics it found percent price moves in about 2.3% of val-A D0 states: about 1.8% index or futures wraps, 0.2% other companies, 0.3% the company's own past moves ("Shares have added about 8.5% in that time frame"); no own pre-market move. Operator decisions 2026-10-26: remove all moves and index and commodity levels, not only the company's own; accept the non-English residue. After (val-A, the verification's own scripts): dates 0.02% of D0 / 0.01% of D2 states (a Swedish month, a Czech word); price candidates only price-target rewrites, fundamentals, forecasts and about three other companies' past moves among 8,921 D0 states; the scanner 0.00% / 0.04% price talk and 0 dates. On articles before 2026-01-02 about 2.3% of company and 11% of market articles lose a sentence; hand-read samples of the dropped sentences are about 90% price talk (the rest mostly macro data, forecasts and product prices). The NA-02 mis-attribution the verification also found is reported, not changed (REPORT owner decision 9). | Before |
| 2026-10-26 | NA-04 | §2 (availability), §6.4 (after-the-fact text), §6.9 (articles of a state), A3.1, A3.5; amends row 6 | Revision 6. **Running market stories are left out of every W0 state** (Call A on D0, the NA-07 samples, the unmasked twin) by `configs/states.yaml` `news_exclusion.running_story` (`states.build.running_story_ids`) on NA-02's raw title / snippet and `t_avail`, with s the article's W0 session. An article goes when one of these holds: (1) a live format, whatever its stamp ("Stock market today:", Reuters' "LIVE MARKETS-", Investopedia's "Markets News, <date>:", "Live <fund> (TICKER):", "Live Updates Live Coverage"); (2) stamped on the calendar date of s, a live entry or an update at or after the open of s ("4:15pm:", "10:54 am by", "Updated at 10:28 AM EST"; London time for a text about a European market); (3) a market subject and a close verb whose nearest weekday is that of s, in one sentence, or "<weekday> close" (not pre-market, a schedule or an Asian market, which closes before the US open); (4) running intraday wording about the market (a market subject in the sentence, or a Reuters text), stamped on the date of s or naming its weekday, without a forecast or an overseas market before the phrase or another weekday; (5) stamped on the date of s, a title opening (or opening a clause) with a US-market subject and a move or close word, without futures, pre-market, forecast, overseas or question words. Company items ("shares rose 3.7% in early trading" before the open), pre-open pieces, schedules, Asian closes, European mornings, recaps stamped the evening before and companies named like an index (Dow Inc., Nasdaq Inc., S&P Global, Live Nation) stay. W2 states (Call A on D2, Call B, A3.5) keep these articles, since W2 ends at the close. The NA-03 lists are not refilled and the attention counts are unchanged. 3,629 of 187,459 D0-listed articles; 3,447 article slots leave the D0 states; D0 states 47,084 → 46,909; D0 events with every listed article excluded 871 → 1,061, without text 148 → 133. | Sixth NA-04 verification (2026-10-26): live blogs and running market reports keep their first vendor stamp while their title and snippet are the latest version, so D0 states carried the decision session's own cash-market outcome (AP's "U.S. stocks are drifting …" stamped 04:41 ET; Reuters' "The S&P 500 ended Tuesday's choppy session" at 05:57 that Tuesday; Yahoo's and Investing.com's "Stock market today" pages stamped the evening before), in at least 1.7% of val-A D0 states (about 3% by reading; 6.2% in 2024Q3, 0.2% in the 2026 test period), a few with the company's own same-day move (UNH 2025-08-15, HD 2025-08-19). Morning-stamped market headlines agreed with SPY's open-to-close direction of the session 57.1% of the time against 48.5% for evening-stamped ones (train + val-A); 50.8% after the rule. The same mechanism as row 6 (TradingView). Operator decision 2026-10-26: leave them out of the D0 states before NA-05, since states are cached by sha256. After (val-A D0): the verification's signatures 2.00% → 0.18% of states, every remaining hit a correct keep; an independent scanner count of post-open text 4.69% → 0.01% (one false positive). | Before |
| 2026-10-26 | NA-04 | §6.3 (masking residue), PRD NA-04 AC2; adds to row 7 | Residues of the revision-6 build that the independent scanner reads as 0 are accepted and disclosed. The seventh NA-04 verification found them by reading val-A states: person names in about 0.7% of states, the company's own executives in 0.11% ("CEO and CFO <Name>" keeps the second name; a first name survives beside a masked surname); price talk in about 0.37% (Ainvest volume-rank titles carrying the previous session's move, some with the % sign stripped; long-horizon returns; TSX / MIB / S&P levels); dates in about 0.27% ("May" as a month; glued years such as "20254:53 PM"). Also left: overseas index moves in 18 D0 states (0.04%; REPORT owner decision 12). None of these is look-ahead: each is about the past or about pre-open prices. | Seventh NA-04 verification (2026-10-26, independent, on 01860ee): PASS on AC1–AC7 and GAC1–GAC5, nothing blocking. Price talk and dates are under AC2's 0.5% bar; AC2 does not measure person names other than the company's identity. More masking means another mask-stage rebuild and verification, and NA-06's identification probe measures what remains identifiable. Operator decision 2026-10-26: accept and merge. | Before |
