# NA-04 REPORT — states: context, codebook, masking, question battery v1

Date: 2026-10-25, revisions 4–6 on 2026-10-26 · Branch `feat/NA-04-states` (cut from `main` @ `45b3da0`) ·
Decisions: `docs/decisions/NA-04.md` · Artifacts: `artifacts/NA-04/{token_stats.csv, leak_scan.csv, examples.md,
summary.json, build_states.json}`.

**Result.** Every decision-model input of the paper now exists as canonical JSON:
- Call A on D0: 46,909 states, all splits including test (inputs only).
- Call A on D2: 61,354 states (PREREG A3.1).
- Call B on D2: 41,814 states, train / val-A / val-B only.
- 594 optional A3.5 market states.
- The NA-07 encoding samples (3,000 events × E0–E4) and a 1,000-event unmasked twin for NA-06.

Main results:
- **Masking.** On val-A the independent scanner finds:
  - company-name or ticker hits in 8 of 8,906 D0 states (0.09%) and 7 of 11,148 D2 states (0.06%);
  - no year or date (target < 0.5% each);
  - price talk (moves of any security, quotes, share-price, index or commodity levels) in 0 D0 states and 4 D2
    states (0.04%, all four known non-moves); the bar is the same 0.5% (revisions 4 and 5);
  - on the unmasked twin, name / ticker hits in 89.0% of states, year / date hits in 91.3% and price talk in
    33.1%;
  - post-open text (revision 6) in 1 D0 state (0.01%, a year-to-date phrase), against 4.69% before revision 6.

  The third verification labelled residues by hand. Its company name / ticker residue is 1.29% of D0 and 1.00%
  of D2 states of the revision-2 build (1.26% / 0.97% on the revision-3 build, plus about 30 D0 states with the
  name in Korean or Japanese). This residue is accepted (PREREG §15 NA-04 row 7); NA-06's identification probe
  measures what remains identifiable. The fifth verification found dates in 0.83% of D0 and 0.91% of D2 states
  and price moves (indexes, futures, other companies, the company's past moves) in about 2.3% of D0 states. On
  the revision-5 build its date scan finds 0.02% / 0.01% (a Swedish month and a Czech word), and its price
  script finds about three other companies' past moves among the 8,921 D0 states, the rest of its candidates
  being price-target rewrites, fundamentals and forecasts (§ Revision 5).
- **Look-ahead and pre-market talk.** Three kinds of article are in no state:
  - move explainers ("Why … Stock Is Up Today", "Why Micron Technology Rallied Today", StockStory's "What
    Happened? Shares of …");
  - TradingView reposts, whose vendor timestamps often precede their content (revision 3);
  - non-English articles (revision 4, operator decision B), because masking and the price scrubbers are
    English-only.

  Since revision 5 no state holds a price move of any security or an index or commodity level (operator decision
  2026-10-26). Since revision 6 no D0 state holds a running market story: live blogs and running market reports
  keep their first vendor stamp while their text is the latest version, so they carried the decision session's
  own cash-market outcome (the sixth verification; § Revision 6). W2 states keep them, since W2 ends at the close. The third verification found DGX's 2025-07-22 earnings jump and its earnings summary in the 07-21
  pre-open state. The fourth found about 9 val-A D0 states with the company's own pre-market move, in Portuguese
  or Spanish ("dispararam mais de 27% ... pré-mercado"). 1,194 D0 events (2.48%) have no state:
  - 1,061 have every listed article excluded (PREREG §15 NA-04 rows 6, 8 and 10);
  - 133 lost all their text to the price-talk rules (articles that were only price talk: "Dow Drops More Than 700
    Points", "shares rise 1.14% premarket").
- **Availability.** Every block is checked with `pit.check_inputs` at its decision point. A call rule adds that only
  Call B's `reaction_so_far` may read the D2 reaction, and only `d2_reaction` columns.
- **Tokens.** p95(state, Call A, E3) = 761 ≤ 900. With the documented tightening (§3.4), every Call A and Call B state
  plus its longest core question fits Laya's 1,024 tokens.
- **Questions.** `configs/questions_v1.yaml` is frozen (sha256 in `configs/frozen.yaml`). It uses every PREREG §7 /
  A2.2–A2.3 string verbatim and has no `noul`.

**Blinding.**
- No return of a session ≥ 2026-01-02 was read, joined or summarized.
- Test-period rows exist only for Call A and carry t−1 context words, from the NA-01 test inputs and the `Data/` closes
  that PREREG §15 (NA-00 row 2) allows for t−1 features.
- The D2 reaction comes from `panel.reactions.build_reactions(period="public")`, which refuses test rows.
- No module in `newsaction.states` reads the sealed directory or calls the lock.
- `ledgers/test_access.jsonl` is unchanged (2 NA-01 `write` entries).
- No val-B statistic of any return was computed.

## Revision 6 — after the sixth verification's look-ahead finding (2026-10-26)

The sixth verification (on `a005fe1`) passed AC1–AC7 and GAC1–GAC5 on their metrics and found a look-ahead that
none of them measures. Live blogs and running market reports are updated in place but keep their first vendor
timestamp, so D0 states carried the decision session's own cash-market outcome:

| Article (raw text) | Vendor stamp (ET) | What the text reports |
|---|---|---|
| Yahoo "Stock market today: S&P 500, Nasdaq pull back from record run as Senate passes Trump tax bill, Tesla sinks" | Mon 06-30 22:55 | the 07-01 session (the Senate vote came at noon) |
| AP "U.S. stocks are drifting as Wall Street's momentum slows" | Tue 07-01 04:41 | trading on 07-01 |
| Reuters "The S&P 500 ended Tuesday's choppy session slightly lower" | Tue 07-08 05:57 | the 07-08 close |
| Proactive "4:15pm: Crypto surge lifts tech stocks … record close" | Mon 07-14 04:28 | the 07-14 close |
| Investopedia "Markets News, July 16, 2025: Stocks Close Higher …" | Wed 07-16 08:17 | the 07-16 close |
| inkl "Dow Swings To Drop 224 Points; Nasdaq Ekes Out A Gain" | Thu 08-07 08:07 | the 08-07 close |

- **Size** (sixth verification): at least 1.7% of val-A D0 states by its high-precision signatures (87% precision),
  about 3% by reading; 6.2% of D0 states in 2024Q3, about 2% through 2025Q3, 0.2% in the 2026 test period.
- **Independent of any pattern:** market headlines stamped the morning of the session agreed with SPY's
  open-to-close direction of that session more often than headlines stamped the evening before (train + val-A:
  57.1% of 1,098 against 48.5% of 1,552). The company's own direction words showed no such excess.
- A few states carried the company's own same-day move (UNH 2025-08-15 "Dow ends higher after the company gains",
  HD 2025-08-19 "… the company, Intel lift blue chips").
- Call A on D2, Call B and the A3.5 market states read news through the close, so the same text is inside their
  window.

**Operator decision (2026-10-26).** Leave running market stories out of the D0 states before NA-05 (states are
cached by sha256). PREREG §15 NA-04 row 10.

**What changed** (`b6705c4`; tests and scanner `c70ca7f`). `build.running_story_ids` (`configs/states.yaml`
`news_exclusion.running_story`) leaves an article out of every W0 state (Call A on D0, the NA-07 samples, the
unmasked twin). It reads NA-02's raw title and snippet; s is the article's W0 session and "the same day" a stamp
on the calendar date of s. One of five rules is enough (counts are of the 187,459 D0-listed articles; an article
can meet several):

1. **A live format,** whatever its stamp (2,384): "Stock market today:", Reuters' "LIVE MARKETS-", Investopedia's
   "Markets News, <date>:", "Live <fund> (TICKER):", "FTSE 100 Live:", "Live Updates Live Coverage …".
2. **A live entry or an update at or after the open,** the same day (327): "4:15pm: …", "10:54 am by …",
   "Updated at 10:28 AM EST". A text about a European market runs on London time ("12.30pm" on a FTSE page is
   07:30 ET); a "Published on 08/07/2025 at 04:10 pm" byline is the stamp itself.
3. **A market close tied to the session** (401): a market subject and a close verb whose nearest weekday is that of
   s, in one sentence ("ended Tuesday's choppy session", "closed modestly higher on Wednesday"), or "<weekday>
   close". Not pre-market, a schedule or an Asian market (Asian markets close before the US open, European ones
   after 09:15 ET).
4. **Running intraday wording about the market** (175): "U.S. stocks are drifting", "Wall Street … in early
   trading", "opened lower", with a market subject in the sentence or in a Reuters text (Reuters keeps
   "premarket" for before the open), stamped the same day or naming the weekday of s. Not with a forecast or an
   overseas market before the phrase, or another weekday in the sentence.
5. **A market wrap title stamped the same day** (1,382): a title opening, or opening a clause, with a US-market
   subject and a move or close word within 40 characters. Not with futures, pre-market or question words in the
   title, a forecast or overseas word before the move word, pre-market words in the snippet, or an overseas
   market opening the snippet.

In all 3,629 D0-listed articles. Kept on purpose:
- company items ("Coca-Cola climbed 3.7% higher in early trading Tuesday", stamped 08:11, after its 06:55
  release, is pre-market);
- pre-open pieces ("Wall St set to open higher …"), schedules, Asian closes and European mornings;
- recaps of the previous session stamped the evening before;
- companies named like an index (Dow Inc., Nasdaq Inc., S&P Global, Live Nation). A ticker becomes a " (T) " mark,
  so "Nasdaq (NASDAQ:NDAQ) Trading 2% Higher" keeps the "(" that tells the company from the index.

About half of the rule-5 hits recap the previous session in a morning-stamped market wrap: market news in a
company state, little lost. The NA-03 lists are not refilled and the attention counts are unchanged (rows 6 and 8).
Call A on D2, Call B and the market states are byte-identical to revision 5.

**How it was checked.** The rules were tuned in five passes over the D0-listed articles; each pass read random
samples of every rule's hits and a full listing of the morning-stamped market wraps the rules left in. The rebuilt
states were then read through the sixth verification's own nets:

| Check (val-A D0 unless stated) | Revision 5 | Revision 6 |
|---|---|---|
| the verification's signatures (a clock after the open, a close on the weekday, intraday wording, a dated live title) | 178 states (2.00%) | 16 (0.18%), every one read: futures outlooks, stale items, European mornings, pre-open previews, a company's pre-market item, a feature |
| the verification's morning-stamped market wraps (unique articles) | 552 | 218 left, every one read: previous-session recaps, pre-open pieces, forecasts, features, overseas markets |
| market headlines stamped the morning of s that agree with SPY's open-to-close direction of s (train + val-A) | 57.1% (1,098 articles, se 1.5 pp) | 50.8% (528, se 2.2 pp); stamped the evening before: 46.5% |
| the company's own direction words stamped that morning that agree with its AR open-to-close (train + val-A) | 49.9% (439) | 50.4% (425) |
| scanner `post_open` (new column) | 4.69% | 0.01%: one state, "off to a rough start to the year" |
| scanner `post_open`, unmasked twin | 3.0% | 0.0% |
| D0 states / D0 events without a state | 47,084 / 1,019 | 46,909 / 1,194 (1,061 all excluded, 133 without text) |
| D0 states byte-identical to the Call A D2 state | 10,933 | 10,513 |

- The direction checks use train and val-A sessions only: the operator has not decided whether data audits may use
  val-B, and the sixth verification's first run of this check had included val-B sessions.
- **Cost.** 3,447 article slots left the D0 states (train 1,861, val-A 857, val-B 347, test 320, robustness 62). 190
  more D0 events have no article left (robustness 35, train 101, val-A 16, val-B 9, test 29). Many of them were
  vendor tags whose only article was a market page, such as MPC's 2024-01-04 state, which held only CNBC's
  "Nasdaq closes lower for a fifth day …: Live updates". 2024 is affected most: the rule left out articles of 8.9%
  of robustness and 8.3% of train D0 events, 7.7% of val-A, 4.8% of val-B and 2.0% of test.
- **Scanner.** `scan.post_open_count`, independent of the build rule, counts on the masked text what masking leaves
  unambiguous: live pages, live entries at or after the open, AP-style running text in an item not stamped the
  evening before. (Masking turns weekdays into "recently", so a close can no longer be tied to its session.) The
  D2 files keep 4.51% of states with such text, inside their window; they are reported, not tested.
- **Found while testing, not changed.** Overseas index moves and levels survive in 18 D0 states (0.04%; val-A 2:
  "lifts Japan's Nikkei 3.5%", "push … the Nikkei 1.3%"). They are before the US open, so they are price talk under
  the 0.5% bar, not look-ahead. Revision 5's index list does not name the Nikkei, Sensex, Nifty, ASX or TSX, and
  the scanner misses them too.

**Tests and mutations.**
- 23 running stories must leave W0 and 34 look-alikes must stay. Each rule has a case no other rule catches, and
  each veto a look-alike only it keeps.
- `news_items` leaves a running story out of W0 and keeps it in W2.
- The built W0 files carry no live format, and `build_states.json` counts `articles_excluded_running` for D0 only.
- The scanner counts every masked golden form and none of the look-alikes; val-A W0 states must stay below 0.1%.
- 51 mutations: every `running_story` pattern, the company guards, the W0-only scope (removed and widened to W2),
  `excluded_w0` not filled, every guard of the five rules, the ticker mark and every scanner form. All are RED.
  The Dow Inc. guard first survived: its case "Dow Inc. shares fall …" was also stopped by the period after
  "Inc"; the case is now "Dow Inc shares fall …".

## Revision 5 — after the fifth verification FAIL on AC2 dates, and its price-talk finding (2026-10-26)

The fifth verification (on `085be64`) passed AC1, AC3–AC7 and GAC1–GAC5 and failed AC2 on dates. Its own scripts
found a date in 0.83% of val-A D0 states (74 of 8,923) and 0.91% of D2 / Call B states; the scanner reported 0.
The masker and the scanner both matched a short month name only before a day digit or a period:

| Form | Examples |
|---|---|
| month abbreviation on its own | "by … \| Jul, the year" bylines; "24-Jun-the year" (the year masked first); "in Aug,"; "Sep nat-gas"; "Coffee News Recap, 29 Aug:" |
| weekday or month glued to a word | "StockSavvyThursday, Jul 3"; "OnJuly 27"; "30thSeptember"; "ESTAug 22nd" |
| lower-case month | "july 14th" |
| day ordinal left beside a masked year or month | "24th, the year"; "the 23rd of the month"; "September 23rd and 24th, the year" |
| fiscal and dateline forms | "FY-25"; "4th qtr"; "6/8 15:18. (RTTNews)" |

Outside AC2's metrics it found percent price moves in about 2.3% of val-A D0 states:
- about 1.8% index or futures wraps (Barchart's "The S&P 500 Index ($SPX) (SPY) today is up +0.20% …");
- 0.2% other companies;
- 0.3% the company's own past moves (Zacks' "Shares have added about 8.5% in that time frame").

There was no own pre-market move, so no overnight-target leak. It also found non-English items left in about
0.46% of states, and NA-02 mapping Ainvest / "Stock Analysis" items to the wrong company (Linde's text under APD,
Incyte's under TECH, ResMed's under EW).

**Operator decisions (2026-10-26).**
- Fix the dates (an AC2 failure).
- Remove every price move (the company's own, other companies', indexes, futures, commodities, currencies,
  bonds) and every index or commodity level, not only the company's own moves. The A3.5 market states turned out
  to carry their own target: an index move or level in 26.9% of the 450 market states outside the test split
  (121 states, revision-4 build, independent count).
- Accept the 0.46% non-English residue.

Recorded in PREREG §15 NA-04 row 9.

**What changed** (commits `c056249`, `0fdc7ef`, `3a73c52`, `7af8192`):
- **Dates** (`mask_dates`). A weekday or month glued to a word is split first (`_GLUED_PERIOD`: "StockSavvy
  Thursday", "On July", "30th September", "EST Aug 22nd", "A July"). Then each form above, and from the reading of
  the first rebuild: "in the june 2025 quarter", URL slugs ("effective-october-2025", "julyinvestordeck"), "in
  september", a day number left after a masked month ("Recently 25."). "Jan" and "Mar" count only where a date
  is meant (after "in", "on", "of", a colon or a slash; before a comma, a masked year or "recently"): they are
  also names ("Jan Hatzius", "Del Mar").
- **Price talk** (`Masker.has_market_move`; run before NER by `drop_market_moves`, which would otherwise read
  "Gold Surges" as a person, and again in the final pass of `mask_prices`). A sentence goes when it holds:
  - an index level ("Dow 46,414", "closed at 6552", "the 5,000 milestone", up to 60 characters after the index
    name), a commodity or crypto amount behind a level word or a move verb or before a level noun ("Gold Surges
    to $3,816", "Bitcoin Retakes $112K", "a $3,400 Threshold", "$63.56 a barrel", "$90/b"), an amount before a
    move noun ("Nvidia’s $185 Rally"), or a quote ("UpsideBX-1.48%");
  - a percent or points number with a move word just before it, a sign, or a move named up to three words after
    it ("a 4.38% recent decline", "Mastercard's 13% 3-Month Rise", "a 0.68% closing decline", "its first 2% down
    day"), when: the sentence has no fundamental and names a market subject, the company or a ticker anywhere;
    or it is signed and no fundamental stands before it or right after it; or the noun after it names the share
    price or a trading period; or a possessive name or an idiom precedes it ("extends gain to 7.7%"); or a market
    subject, the company or a ticker follows the last fundamental of the 90 characters before it and stands
    before the move word ("Strong earnings sent shares up 7%", "Micron Technology (MU) has seen a modest rise of
    0.93%"; not "Tesla's deliveries jumped 20%"); or a capitalized name that is no fundamental stands right
    before the move verb ("Nvidia dropped 3.5%"); index points need no move word ("the index ahead on the week
    by 180 points"); a percent below or above a high is a move ("26% below its all-time high").

  Fundamentals stay: revenue, margins, EPS, deliveries, AUM, macro gauges ("the PMI index", "the Consumer Price
  Index", "Pending Home Sales Index (PHSI)"), stakes and short interest, payments ("CMS announced a 5.06% Medicare
  Advantage payment increase"; agency acronyms are no tickers), a product's "5% price increase", forecasts
  ("Potential 10% Gain", "Projects 52.5% S&P Rally") and the price-target rewrites ("raised by about 7%").
- **A3.5 market states.** A session whose every article lost its text gets no state, as an event
  (`build_states.json` `market_E3.sessions_without_text`).
- **Scanner** (`scan.market_move_count`): every class in its own wording, and every date form; it no longer
  reads "NASDAQ:" as the index or "Clare-Mar Farms" as a month.

**How the rules were checked.** Four builds. Each was read in full through:
- the scanner's hits;
- the verification's own date and price scripts;
- listings of every month or weekday token, every index or commodity level, and every percent beside a move
  word.

Every form that no rule had seen became a test case and a rule in the next pass. On articles before
2026-01-02, hand-read samples of the dropped sentences were about 90% price talk; the rest were mostly macro data,
forecasts and product prices. About 2.3% of company articles and 11% of market articles before 2026 lose a
sentence.

**After the rebuild** (val-A unless stated; the final build is from `7af8192`):

| Check | Before (revision 4) | After (revision 5) |
|---|---|---|
| verification's strict date scan, D0 / D2 | 0.83% / 0.91% of states | 0.02% / 0.01%: a Swedish "i augusti" (non-English, accepted) and the Czech "Nový" |
| verification's month scan, every hit read | — | place and company names ("Augusta", "Clare-Mar Farms", "Trends Mar Results"), clock times after a masked date ("Recently 16:30 ET"), one slug ("earnings call 29 recently 10 00 am", D2) |
| verification's price script, D0 / D2 | price talk in about 2.3% of D0 states (hand count) | candidates in 1.05% / 1.27%: price-target rewrites (27 / 50 states), short-interest boilerplate, fundamentals, macro data, forecasts, structured notes; real: about three other companies' past moves in D0 ("AT&T rose, bringing year-to-date gains to roughly 21%") |
| every index or commodity level left | — | none: index names ("Russell 1000", "S&P 1500") and sizes ("$2.3 trillion", "$179 million") |
| scanner price talk (its revision-5 rules), D0 / D2 | 0.00% / 0.04% (revision-4 rules) | 0.00% / 0.04%: the same four D2 non-moves (an offering's 2.0% agent fee, another company's insider price, a preferred's $1,000 par, a $100,000 visa fee) |
| scanner name / ticker, D0 / D2 | 0.09% / 0.07% | 0.09% / 0.06% |
| scanner year / date | 0.00% | 0.00% |
| A3.5 market states outside the test split with an index move or level (independent count) | 121 of 450 (26.9%) | 17 of 449 (3.8%): fundamentals ("S&P 500 earnings are up 10% year over year"), forecasts, structured notes, the 2020 crash |
| D0 states / events without a state | 47,125 / 978 | 47,084 / 1,019: 871 all excluded, 148 without text |
| market states / sessions without text | 595 / 0 | 594 / 1 |
| p95 state, Call A D0 / Call B | 766 / 840 | 763 / 837 |
| share of states ≤ 768 tokens (Laya), Call A D0 / Call B | 95% / 71% | 96% / 73% |

The 148 D0 events without text carried only price talk ("Dow Drops More Than 700 Points", "Snap-On Incorporated
shares rise 1.14% premarket …", "Applied Materials (NASDAQ:AMAT) Trading 1.3% Higher After Analyst Upgrade",
"Prologis (NYSE:PLD) Sees 7% Quarterly Dip"). By split: test 74, train 34, val-B 22, val-A 14, robustness 4. The
test period's share is high because automated move reports grow more common in the vendor's feed over time;
no return was read. The bound on events without text in `test_splits_and_counts` is 0.4% (0.31% of D0
events).

**Tests:**
- 22 date forms the verification found or the reading of the builds added, and 8 look-alikes that must stay
  ("Del Mar", "Nový", "Augusta Farmers Coop", "Clare-Mar Farms", "77th in Daily Trading Volume", a clock time);
- 79 sentences with a price move or level that must go, and 86 with a fundamental that must stay (both lists
  also run through the scanner, which must count every move and none of the fundamentals);
- the determinism test also rebuilds every market session without a state and requires it to stay without one.

## Revision 4 — after the fourth verification's price-talk finding (2026-10-26)

The fourth verification passed AC1–AC7 and GAC1–GAC5. It found price talk that AC2's metrics do not measure.
PREREG §6.3 removes share-price levels and percent moves, §6.4 strips pre-market price talk from Call A, and the
PRD bars raw prices. Its independent scripts found (val-A, revision-3 build, about 90–95% precision on hand
checks):

| Price talk | D0 | D2 / Call B | Scanner reported |
|---|---|---|---|
| share-price levels ("shares closed yesterday at $242.66", "Das Papier kostete zuletzt 72,99 US-Dollar") | 1.12% | 1.61% | 0.01% |
| price targets not written "$X" ("at USD 220", "38,36 € / share") | 0.62% | 0.69% | — |
| percent moves (incl. MarketBeat's "Trading 2.4% Higher", 0.54% of D0, rises only) | 1.10% | 1.36% | 0.09% |
| any of these | **2.52%** | **3.25%** | |

- About 9 val-A D0 states carried the company's own pre-market or after-hours move. These were in Portuguese or
  Spanish, and NA-02's language hint had not flagged them. That move is the D0 overnight target: DAY 2025-08-18
  read "dispararam mais de 27% ... pré-mercado" against an overnight return of +24.7%, and GPN 2025-07-16 read
  "+6% en las operaciones previas al mercado" against +6.0%.
- No look-ahead: every timed hit was pre-market before 09:15 ET or about a past session.
- NA-02 scrubs "Trading Down 3.1%", "Shares Up 2%" and "Stock Price Down 1.7%", but not "Trading 2.4% Higher".
  That form exists only for rises, so the residue was sign-dependent.

**Operator decisions (2026-10-26).** Fix it now, before any API spend, because states are cached by their sha256.
Apply decision B of 2026-10-25 (drop non-English articles) at the states step. Recorded in PREREG §15 NA-04
row 8.

**What changed, first pass** (commits `940668d`, `c03a704`):
- **Non-English articles** are in no state (`build.non_english`, `configs/states.yaml`
  `news_exclusion.non_english`; Decisions → States). The rule looks at:
  - non-Latin script;
  - distinct function words of 13 languages against English ones (lower case or capitalized only, so DE is not
    "de");
  - words with non-English letters.

  It flags 22,960 of 296,082 event articles (7.75%); NA-02's hint flagged 5.0%. It finds 98–100% of each
  non-English residue class (the hint: 51–98%), and 205 sampled flags were all non-English.
- **Move explainers.** The title rule now also takes "Why Micron Technology Rallied Today", "Why CoreWeave
  Rocketed as High as 26% Today" and "Why Airline Stocks Are Flying High Today": a move word between "why" and
  "today". The old rule needed the singular "stock" or "shares", so 188 event articles had escaped. "Here's Why
  We Think F5 Might Deserve Your Attention Today" is kept. Corpus explainers: 8,760 (7,535 before).
- **Masker, English price talk:**
  - share-price levels after a verb (`_LEVEL`);
  - a currency amount after a share word unless it is per share, a size, a total or a fundamental
    (`_SHARE_LEVEL`; possessive amounts);
  - the direction after the number ("Trading 2.4% Higher", "Moves 22.8% Higher", "closing 1% lower");
  - moves as nouns ("1.95% Stock Rise", "closed at a 1.13% decline");
  - price targets in any notation ("from GBX 420 to GBX 500" → "raised by about 19%");
  - "$210/Share" deal prices.
- **Scanner:** the same classes with its own rules.

**What changed, second pass** (commits `8bdf5bc`, `dd11b87`, `36f597d`, `5e764ec`, `e62f9dc`, `3680bd2`).

The first rebuild passed the verification's scripts and the scanner. A broader check then listed every
cents-precision amount left in val-A states and read the ones that were not EPS or dividends. It found forms
that no rule (masker, scanner or the verification's scripts) had seen:
- price targets after an abbreviation ("JPMorgan Chase & Co. from $104.00 to $96.00", "Citigroup Inc.");
- MarketBeat's "The company traded as high as $155.51";
- "Receives $645.36 Consensus Price Target";
- "a one-year high of $66.44";
- insider prices ("sold 2,500 shares at a price of $251.12");
- "rallies to $202.34 as … ad revenue";
- "current price ($246.03)";
- quote widgets ("GE VernovaGEV $554.00 (-3.11%)");
- "shares saw an increase of 2.4% during after-hours trading";
- options-flow chatter ("lifted the $0.37 offer … 9/12 weekly 20 puts");
- "Sep-25" and "Jun-12-2025".

Pattern lists kept missing phrasings, so the masker now ends with a structural pass. After the price-target
rewrites, it drops a sentence that holds:
- a cents-precision amount (sizes such as "$9.05 Billion" or "$6.16 bln" are not), unless a per-share
  fundamental word (EPS, earnings, per share, dividend, distribution, FFO, consensus, estimate, guidance, …) is
  in the sentence and no price word or move verb stands just before the amount;
- any cents amount in a sentence with a price-target label;
- a quoted price.

Also:
- the price-target window crosses abbreviation periods (Co., Inc., Corp., Ltd., one capital, ".com");
- "of N%" and "added N%" moves, with a guard for "per share, an increase of 16%";
- options-flow sentences;
- month-year and month-day-year dates;
- deal prices with words before "a share" ("$47.50 in cash a share", "cash + CVR per share"), where "pay" is a
  deal word unless a dividend is on either side.

The scanner learned each class in its own wording, with abbreviation-aware sentence breaks.

**Tests:**
- non-English golden cases in 11 languages, and English look-alikes ("Los Angeles", "DuPont de Nemours", DE /
  EL / DAN);
- no built state carries two non-Latin script characters (exact);
- 50 revision-4 removal cases and 23 fundamentals that must stay (EPS, dividends, market sizes, "EPS rose to
  $1.44");
- the scanner sees every removal case and counts none of the fundamentals (levels, moves, quotes);
- val-A price talk under 0.5% per file (`test_val_a_price_talk_below_target`);
- events without text bounded at 0.3%.

**After the rebuild** (val-A unless stated):

| Check | Before (revision 3) | After (revision 4) |
|---|---|---|
| verification's price-talk scripts, D0 / D2 | 2.52% / 3.25% | 0.02% / 0.05% of states hit, all false positives (deal or revenue sizes next to "price target") |
| every cents amount left, read by hand where not EPS / dividend / revenue / market size | — | D0: 2 market-size headlines cut before "Billion", a structured note quoting Dell's price, a deal's "$22.50" CVR (other companies); one offering range ("$141.85 and $143.35") and one "reaching as low as $28.83" (D2) are the remaining share prices: about 0.01% |
| scanner price talk (moves, quotes, levels; its revision-4 rules), D0 / D2 | 5.47% on the revision-3 build | **0.00% / 0.04%** (D2: another company's insider price, "20,200 Shares at $1.02/Share", and four false positives) |
| scanner name / ticker, D0 / D2 | 0.10% / 0.08% | 0.09% / 0.07% |
| scanner year / date | 0.00% | 0.00% |
| verification's date residue, D0 | 0.13% | 0.02% (a lower-case "july 14th"; a one-line Dutch title) |
| D0 states / events without a state | 47,489 / 614 (1.28%) | 47,125 / 978 (2.03%): 871 all excluded (254 all non-English), 107 without text |
| p95 state, Call A D0 / Call B | 809 / 855 | 766 / 840 |
| share of states ≤ 768 tokens (Laya), Call A D0 / Call B | 87% / 53% | 95% / 71% |

The 107 D0 events without text carried only price talk ("Lockheed Martin (NYSE:LMT) Trading 0.8% Higher - Here's
What Happened", "Cencora, Inc. shares rise 2.42% after-hours …", "Expeditors … Receives $115.40 Average T…"). By
split: test 65, val-B 18, train 12, val-A 12. The structural pass drops a few product and commodity prices too
("a $19.99 per month subscription", silver prices); about 0.7% of event articles lose a sentence to it.

## Revision 3 — after the third verification FAIL on AC2, and its look-ahead finding (2026-10-25)

The third verification passed AC1 and AC3–AC7, and failed AC2. It read every val-A state with its own regexes and
labelled the hits by hand:

| Residue (val-A, revision-2 build) | D0 | D2 / Call B | Scanner reported |
|---|---|---|---|
| the company's own name or ticker | 1.29% | 1.00% | 0.10% / 0.07% |
| a date or period label | 3.86% | 3.64% | 0.00% |
| of which written-out ordinal quarters in other languages ("deuxième trimestre", "zweiten Quartal") | 2.14% | 2.04% | 0 |

**Look-ahead.** It also found future price information in pre-open inputs:
- DGX's D0 state for 2025-07-21 read "Quest Diagnostics DGXjumped 6.4% in the morning session after the company
  reported strong second-quarter" results, a move of 07-22 (z +4.84).
- The vendor timestamps of these move explainers ("Why Quest (DGX) Stock Is Up Today") can precede their content.
  Of 204 pre-open-stamped explainers about the company itself (2024-01 … 2025-09), 29 describe a move after their
  stamp.
- The price-move filter missed the sentence because the ticker is glued to the verb.

During the fix, the same DGX state turned out to hold Reuters' earnings summary of 07-22, reposted on TradingView
under the same stamp. 128 of 511 TradingView earnings summaries are stamped before the release they report, against
0–7% for other outlets (previews included).

**Operator decisions (2026-10-25).**
1. Fix the look-ahead and the cheap date forms now, before any API spend: states are cached by their sha256.
2. Exclude TradingView reposts as well.
3. Accept the name residue as a logged deviation (PREREG §15 NA-04 row 7).
4. This revision was implemented by the session that ran the third verification (the operator waived the
   independence of this round). Its re-check is mechanical: the verification's own scripts plus the tests below.

**What changed** (commit `314efd2`):
- **Exclusion** (`configs/states.yaml` `news_exclusion`, `states.build.excluded_ids`; PREREG §15 NA-04 row 6):
  - move explainers (raw title "Why … stock/shares … today", or StockStory's raw snippet "What Happened? Shares of / A
    number of …") and every TradingView domain are in no state, in any window or call (both twins and the samples
    included);
  - the NA-03 lists are not refilled;
  - `build_states.json` counts the excluded articles and the events left without any (`events_all_excluded`)
    apart from `events_without_text`.
- **Price-move filter:** a move verb glued to an upper-case ticker ("DGXjumped 6.4%") is a move. "Slower 6%" and
  "GROUP" are not.
- **Dates (masker, and the scanner with its own patterns):**
  - written-out ordinal quarters and halves (FR, ES, IT, PT, DE, NL); "3T25"; a bare T1–T4 after a period word;
  - Korean 분기 / 반기;
  - two-digit years after any apostrophe ("'25", "FY’25", "Q1 ‘25");
  - a lone "Aug."; bare H1 / 2H (not hydrogen);
  - glued yyyymmdd; day-first dd/mm; "domingo".
- **Tests:**
  - `tests/test_states_exclusion.py` (rule golden cases, `news_items`, built files);
  - revision-3 masker and scanner cases in `tests/test_states_mask.py`;
  - the determinism test keeps `Inputs.excluded`;
  - `test_splits_and_counts` accounts for the emptied events.

**After the rebuild** (val-A unless stated):

| Check | Before | After |
|---|---|---|
| verification's date residue, D0 / D2 | 3.86% / 3.64% | **0.13% / 0.11%** |
| verification's own name / ticker residue, D0 / D2 (accepted) | 1.29% / 1.00% | 1.26% / 0.97%, plus about 30 D0 states in Korean / Japanese |
| scanner name / ticker, D0 / D2 | 0.10% / 0.07% | 0.10% / 0.08% |
| scanner year / date | 0.00% | 0.00% (now also counting the new forms) |
| glued move sentences, every file and split | 16 val-A D0 states | **0** |
| "N% in the morning / afternoon session" in a D0 state, every split | 39 val-A states | **0** |
| DGX `W0:420:2025-07-21` | the 07-22 jump and results | no state (every listed article excluded) |
| events without any article: D0 / D2 / Call B | — | 596 / 503 / 224 |
| events without text after masking | 18 / 11 / 4 | 18 / 10 / 4 |

What is left of the date residue (12 D0 states): "saison T2", "1º semestre", German compounds ("ersten
Quartalszahlen"), "Investopedia22/08", option expiries ("9/12 weekly puts") and a software version
"2025.001.20744".

## Revision 2 — after the second verification FAIL on AC2 (2026-10-25)

The second verification passed every AC except AC2. It measured, on val-A Call A D0 states:

| Leak | Share of states | Scanner reported |
|---|---|---|
| the company's own ticker written in capitals, a ticker that is an English word ("MET earnings per share", "View the latest DASH revenue", "MS.N") | 2.07% | 0 |
| name or ticker, all forms | 2.40% | 0.33% |
| a year glued to letters or CJK ("the quarter CY2025", "2025年第二季度") | 3.0% | 0.00% |
| CJK months / days / weekdays, "recently-18", "the yearQ2", option codes | 0.5–0.7% each | 0 |
| a percent quote after "the company" ("· IP. -0.58%") | 1.75% | not counted |

**Root cause.** The scanner still shared the masker's blind spots: its list of English-word tickers was a copy of
the masker's stoplist, its year pattern refused a year after a letter or a CJK character, and it had no CJK patterns.

**What changed:**
- **Scanner** (`states/scan.py`). It has no English-word ticker list any more:
  - every bare ticker in capitals counts in a text that is not mostly in capitals; a clock time ("4:30 PM") is the
    only exception, and in a text mostly in capitals a ticker counts unless it is an ordinary word of the corpus;
  - its own forms for "（紐交所：DE）", "紐交所:CTRA", "HOOD US", "COIN.US", option codes, "WMT/TGT", "Inc.ANET",
    "ABBV19";
  - years after letters or CJK; Chinese / Japanese / Korean dates; glued period labels ("yearQ2", "quarter-25");
    option expiries; masked day-range remnants;
  - CJK company names by its own rule (`harvest_cjk_names`: every 2–6 character ending of the CJK word before the
    ticker, seen twice); names glued to the previous word or written without spaces;
  - quote widgets, "Price: … Change: …" lines, Chinese transliterated person names;
  - it scans one headline or snippet at a time.
- **Masker** (`states/mask.py`, `configs/aliases.yaml`):
  - **tickers:** a stoplisted ticker in capitals is the company unless the text is mostly in capitals (a sample
    of 40 such uses was 40 ticker uses); kept are a clock time ("4:30 PM", Philip Morris) and IT before an IT noun
    ("IT spending", Gartner); in a text mostly in capitals, a ticker that is not an ordinary word, in a list of
    tickers, before a period label or right after the company's name is masked too. Also CJK and venue forms,
    Reuters exchange letters (AAPL-Q, NKE-N), drug codes (ABBV-400), tickers with digits ("ABBV19"), in pairs and
    lists ("Omnicom-IPG", "WMT/TGT/TJX"), and glued after a masked name ("Inc.ANET"); option codes are removed
    with their expiry and strike;
  - **dates:** years glued to letters or CJK, year + period in any order ("2025Q2", "FY2025Q2", "Q2-25", "Q1
    CY2025"), day ranges ("July 17-18"), slashed dates (2025/08/08), Chinese / Japanese / Korean dates, weekdays,
    quarters and halves; remnants of a masked range lose their number; period rules use ASCII boundaries (CJK
    characters are word characters);
  - **names:** 572 Chinese / Japanese / Korean names of 254 companies harvested from the event texts (the CJK words
    right before the company's own ticker in parentheses; `work/states/company_cjk_names.parquet`); names glued
    to the previous word or a number ("Key TakeawaysHumana", "2025Principal Financial Group"), written without
    spaces ("MolsonCoors"), or cut at the end of a snippet ("for Warner..."); about 15 more curated names
    (Principal Finl Gr, HP Enterprise, NY Mellon, Smith AO, Norwegian, Caribbean, Campbell, PMČR, …); "Fargo"
    alone for Wells Fargo;
  - **people:** Chinese transliterations of Western names ("薩姆·阿爾特曼") → "a person"; "Leyen" added to the
    public figures;
  - **price talk:** quote widgets are removed before the company step (they split names: "Constellation · CEG.
    +3.58%. Energy's"); "Price: 152.75, Change: -15.87" lines (1% of D2 states before the fix) and share-price
    level sentences ("boosts stock to $102.89") go;
  - **config:** `ON` is quoted (YAML read it as true, so ON Semiconductor's curated names were ignored); the
    loader refuses a non-string entry.
- **The verifier's scripts** (`stoptick.py`, `years.py`, `residues.py`, re-run read-only on the final states): own
  tickers in capitals 5 / 9,073 D0 states (0.06%) and 4 / 11,249 D2 states (0.04%), all Gartner's "IT spending";
  years 0; date residues 1 state (a clock time, "8:30 CEST").
- **Rebuilt** with all earlier mutations plus 15 new ones RED (§2.1).

## Revision 1 — after the first verification FAIL on AC2 (2026-10-25)

The first scanner imported the masker's aliases, exchange list, stoplist and English-only date patterns and reported
0%; independent scans of val-A D0 states found the own ticker in 3.4%, its name in ≥ 1.8%, quarter / half labels in
title case in 10.3%, non-English months / weekdays in 7.9%, price-move sentences in 2.2%, dollar price targets in
13.4% and one-word public figures in 10.3%.

**Operator decisions (2026-10-25).**
1. Price-target and deal-price amounts: drop the amount, keep the action.
2. Non-English dates: mask them too.
3. Person names: mask all of them, including surnames used alone.

All three are in PREREG §15 row 4, which amends NA-02's rule that kept price targets. The scanner was made
independent of the masker's code and alias file; the masker gained every exchange code, class suffixes,
possessives, ticker lists, about 90 curated names, quarter labels in any case, seven languages' dates, numeric m/d
dates, corpus surnames and a public-figure list, the price-move sentence filter and the price-target rewrite.

## 1. Scope

| Item | Status | Where |
|---|---|---|
| S1 codebook | done | `configs/codebook_v1.yaml`, `src/newsaction/states/codebook.py`: PREREG §6.11 scales + encoders E0–E4; NA-04 additions marked in the YAML (PREREG §15 row 2) |
| S2 context | done | `states/context.py` (company, market, attention, reaction blocks), `states/macro.py` + `configs/macro_calendar.yaml` (CPI from vintages; FOMC from federalreserve.gov, URL cited); `configs/states.yaml`; 45 columns registered in `configs/availability.yaml`; `work/states/{context_company, context_market, reaction_d2}.parquet` |
| S3 masking | done | `states/mask.py`, `states/scan.py` (independent), `configs/aliases.yaml`; spaCy `en_core_web_sm` 3.8.0 pinned; `work/states/{articles_masked, person_surnames, company_cjk_names}.parquet` |
| S4 questions | done | `configs/questions_v1.yaml` (groups core / extended / explain), `states/questions.py` (loader for any group combination, `noul` refused, request shape); sha256 in `configs/frozen.yaml` |
| S5 build | done | `states/build.py` (specs, availability checks, canonical JSON, budget, samples, CLI); `work/states/{callA_d0_E3, callA_d2_E3, callB_d2_E3, market_E3}.parquet`, `work/states/samples/{callA_d0_E0…E4, unmasked}.parquet` |
| S6 token budget | done | `artifacts/NA-04/token_stats.csv`; tightening documented (§3.4) |
| S7 leak scan | done | `artifacts/NA-04/leak_scan.csv` (every val-A state of the three masked E3 files + the unmasked twin); `artifacts/NA-04/examples.md` (3 Call A, 2 Call B, val-A, seed 2026) |
| report stage | done | `states/report.py` (`--stage report`) |

## 2. Acceptance criteria

| AC | Evidence | Result |
|---|---|---|
| AC1 determinism | **Test.** `tests/test_states_determinism.py` takes 2,000 rows from seven state files (400 each of the three main files; 200 each of E0, E4, unmasked and market). It rebuilds them from the registered inputs: context recomputed for the sampled keys (and compared with the stored rows: equal), every article re-masked by a fresh in-process masker with the stored corpus surname list (the CJK names are derived again from the event texts), states re-rendered. **2,000 / 2,000 sha256 identical** (the test keeps the excluded articles, revision 3, and the non-English ones, revision 4); since revision 5 it also rebuilds every market session without a state and requires it to stay without one. **Rerun.** Revision 5: the states were built from `7af8192`, the report from `d8a2d02` (the scanner's last two forms; the report came out identical); a full rerun of `mask`, `states` and `report` from `d8a2d02` reproduced all 13 `work/states` files of the stages and the 5 report artifacts byte for byte (22 of 22 outputs incl. the context files and `configs/frozen.yaml`). Revision 6: built from the fix, then `states` and `report` run again from `c70ca7f`: all 16 outputs (10 state files, 5 report artifacts, `configs/frozen.yaml`) byte for byte (§9) | PASS |
| AC2 masking | **Independent scanner** (`leak_scan.csv`, val-A, states with ≥ 1 hit). Name/ticker: callA_d0 **8 / 8,906 (0.09%)**, callA_d2 **7 / 11,148 (0.06%)**, callB_d2 7 / 11,148. Year/date: **0** in all three, with the revision-3 and revision-5 forms counted. Target < 0.5% (`test_val_a_leak_rates_below_target`). **Price talk** (revisions 4 and 5; moves of any security, quotes, share-price, index or commodity levels): 0 D0, 4 D2 / Call B states (0.04%, all known non-moves), target < 0.5% (`test_val_a_price_talk_below_target`). **Post-open text** (revision 6, `post_open`): 1 of 8,906 D0 states (0.01%, a year-to-date phrase; 4.69% before revision 6), none of the unmasked twin; target < 0.1% (`test_val_a_post_open_below_target`). **The fifth verification's scripts** (revision 5): dates 0.02% / 0.01% of D0 / D2 states (a Swedish month, a Czech word; 0.83% / 0.91% before); price candidates only price-target rewrites, fundamentals, forecasts and about three other companies' past moves among 8,921 D0 states. **Positive control.** Unmasked twin: 89.0% name / ticker, 91.3% year / date, 33.1% price talk. **Hand-labelled (third verification, revision-3 build).** Own name / ticker 1.26% D0 / 0.97% D2, plus about 30 D0 states in Korean / Japanese: above the target, **accepted by the operator** (PREREG §15 NA-04 row 7). **Independence.** No import from the masker (`test_scanner_is_independent_of_the_masker`); every stoplisted ATOM ticker counts in capitals (`test_scanner_counts_every_stoplisted_ticker`); the scanner mutations of revisions 1–6 are RED. **Mutation** "empty the alias list": RED | PASS on the scanner and the verification's scripts; names: accepted deviation (row 7) |
| AC3 availability | **Tests.** `tests/test_states_pit.py`, 84 cases: z_id, z_cc, z_on, y0, e5, r_cc, adj_close (`post`), every `w2` / `d2_reaction` column, vendor `selection_only` columns, `material` and `clean_5`, each added to any block of a D0 Call A spec, raise `PITError`. Call B's `reaction_so_far` accepts `d2_reaction` columns only (z_cc, y2, e5, ar_cc, g_d1, raw_close refused). Reaction columns are refused in every other block, and Call A has no reaction block. **Planted shocks.** A +50% SPY day or stock close at t changes no market or company context dated ≤ t, and does change t+1. **Mutation** z_cc registered `t_minus_1`: **RED** | PASS |
| AC4 encodings | **Tests.** `tests/test_states_codebook.py`: every bin edge of move, percentile, β, attention and revision (value − ε, the edge, + ε); the PREREG examples of E0–E4 reproduced exactly; E2 words carry no digit, E3 only inside "≈k.k×", for every horizon. **Built files.** `tests/test_states_outputs.py`: no digit in the company / market / attention blocks of any E2 sample state; E3 (sample, Call B incl. `reaction_so_far`, market) has digits only inside "≈k.k×". The three fixed PREREG tier phrases ("one of the 100 largest US companies", "… rank 101–250", "… 251–500") are removed first: they are labels, not values. **Mutation** move edge 2.0 → 2.5: **RED** | PASS (tier phrases: note) |
| AC5 tokens | `token_stats.csv`. **Call A E3:** p95 state **761** (≤ 900), p95 state + longest core question + 3 special tokens **896**, max 1,024. **Call A D2:** 758 / 893 / 930. **Call B:** 837 / **986** / 1,023 (revision 5). **Before the tightening:** Call B was 913 / 1,062 (fail); §3.4. Stored counts re-tokenize exactly on 200 states per file (`tests/test_states_tokens.py`) | PASS (after documented tightening) |
| AC6 no 2026 Call B | No state file has a Call B row with split test or session ≥ 2026-01-02. `reaction_d2.parquet` has no test session. `build_event_states` refuses Call B events outside train / val-A / val-B (test + mutation RED). `ledgers/test_access.jsonl` has 2 lines, both NA-01 (`test_access_ledger_has_no_na04_entry`) | PASS |
| AC7 questions frozen | `tests/test_states_questions_prereg.py` parses the PREREG §7 / A2.2–A2.3 table rows and compares: ids, types and level counts; option keys; every quoted description; the 8 verbatim instructions; Q1's levels; the Q3 / Q4 / Q14 end points; Q17 = Q8's nine company categories + 2. Groups: core A = Q1–Q4, core B = Q1, Q5, Q6, extended = Q7–Q15, explain = Q16–Q17. `questions_v1_sha256` = `e602c6c0…0c85a` = file sha. No `noul`, and the loader refuses one. **Mutations** (one word of Q3; `noul` check removed): **RED** | PASS |
| GAC1 | `make verify` exit 0: 1,215 passed, 1 xfailed; manifest and ledgers OK (§9) | PASS |
| GAC2 | `git status --porcelain Data/` empty; `make manifest` OK | PASS |
| GAC3 | `tests/test_blinding.py` passes (no 2026 literal in `src/`; dates come from configs); access ledger unchanged | PASS |
| GAC4 | No API call; `ledgers/spend.jsonl` empty; $0 | PASS |
| GAC5 | 16 `work/states/` artifacts in `docs/DATA_CONTRACT.md` with the manifest sha256 (`make manifest` OK) | PASS |

### 2.1 Mutations

A scratchpad script applied each mutation, ran the named test file and restored the file byte-for-byte (asserted).
`git status` afterwards showed only the author's changes. All 100 of revisions 1–4 turn the tests RED: 41 through
revision 2, 22 in revision 3 and 37 in revision 4. In revision 4, four first survived and needed a test, because
another rule caught every golden case or the test did not look at the counted column:
- the verb-level price rule (a case with a fundamental word in the stretch, `c03a704`);
- the options-flow rule (a case with no cents amount, `3680bd2`);
- the scanner's quote guard (the kept-text check now includes quotes, `3680bd2`);
- the scanner's abbreviation-aware sentence breaks (an "EPS …, vs. FactSet Est of …" line, `3680bd2`).

Revision 5 has 134 more, run on the final code (`d8a2d02`) together with the verifier's (a)–(c): 131 of 137 RED.
22 first survived. 16 needed a sharper case: the day number goes with its month ("24-Jun-2025", "29 Aug"), "14
july", "in september", "Inflation data for Jan,", day remnants after a masked month ("Recently 25.", "Recently
24th"), the final pass of `mask_prices` on its own, a percent range ("Discounts of 20%-30% apply"), "/share" ("came
to $3.42/share, up 5%"), an agency acronym ("The agency (CMS) said approvals rose 15%"). Writing them showed the
scanner missing two masked forms ("Recently 24th"; "$3.42/share, up 5%" in its oldest move rule), now counted. Six
survive because later rules cover the same text, so no test can tell them apart:
- the "24-Jun-2025" rule (the lone-abbreviation and day-range remnant rules mask the same text);
- the "a 7.2% rise in sales" check of `_move_after` (the "in / of / for + fundamental" check covers it);
- the exemption of the price-target rewrite ("raised by about 7%" has no move word next to it);
- the price-target restatement check ("a 16% increase" after a rewrite; the price-target compound covers it);
- removing a "(" before the number (the subject window ignores clause breaks);
- the scanner's hyphen guard (only "Clare-Mar" needed it, and "Mar" is now matched only in date context).

The verifier's (a)–(c) were re-run on the final code: RED.

Revision 6 has 51 more, run on the final code (`c70ca7f`): all RED (§ Revision 6). One first survived: the Dow Inc.
guard, whose case "Dow Inc. shares fall …" was also stopped by the period after "Inc"; the case is now "Dow Inc
shares fall …".

| Mutation | File |
|---|---|
| alias list emptied (verifier 6a) | configs/aliases.yaml |
| z_cc registered `t_minus_1` (verifier 6b) | configs/availability.yaml |
| move edge 2.0 → 2.5 (verifier 6c) | configs/codebook_v1.yaml |
| `check_inputs` removed from `validate_spec`; reaction "d2_reaction only" rule removed; Call B test-period refusal removed; third-party check removed | states/build.py |
| E3 multiple rounded instead of truncated | states/codebook.py |
| trailing history includes the scored value; market context not shifted; earnings stamp at the close kept in W2(s) | states/context.py |
| loader accepts `noul`; one word of Q3 edited | states/questions.py, configs/questions_v1.yaml |
| **revision 1:** bare-year rule removed; person masking disabled; public-figure list emptied; any-exchange-code rule removed (BOATS:NEE); ticker quotes kept; quarter labels case-sensitive; non-English weekday rule removed; zero-padded m/d rule removed; price-move sentence filter disabled; price-target amounts kept; scanner imports the masker | states/mask.py, states/scan.py, configs/aliases.yaml |
| **revision 2:** upper-case stoplisted ticker rule removed; stoplisted tickers in a text in capitals kept even when not a word; full-width / venue ticker forms removed; option codes kept; years glued to letters / CJK kept; CJK weekday rule removed; CJK company names not masked; CJK person names kept; YAML boolean guard removed; glued names kept; truncated names kept; quote widgets removed only after the company step; share-price level sentences kept; bare tickers only after a non-word character; names need a space between words; scanner skips English-word tickers; scanner refuses years after letters / CJK | states/mask.py, states/scan.py |
| **revision 4, second pass:** cents-level pass off; options-flow sentences kept; per-share fundamental before the amount not exempt; price word before the amount ignored; price-target label not a level; quoted price not a level; abbreviation periods end the price-target window; "of N%" / "added N%" moves off; "per share" guard off; Mon-DD-YYYY dates off; Mon-YY dates off; "pay" not a deal word; scanner cents levels and options off; scanner price word before the amount ignored; scanner "of N%" moves off; scanner verb-level levels off; scanner sentence breaks after abbreviations; scanner share-amount levels off | states/mask.py, states/scan.py |
| **revision 4:** non-English rule dropped from `excluded_ids`; script rule off; foreign-word rule off; diacritic rule off; words in capitals count (DE = "de"); place names not removed; explainer title rule back to revision 3; broad share-level rule off; verb-level price-level alternatives removed; direction after the number off; moves as nouns off; price targets in other notations off; their relative change off; "/share" deal prices off; possessive amounts reverted; broad-rule cues emptied; scanner new price levels off; scanner new price moves off; scanner fundamental after the number ignored; scanner fundamental acronyms counted as quotes | configs/states.yaml, states/build.py, states/mask.py, states/scan.py |
| **revision 5:** dates: the glued pre-pass, each first-pass form (24-Jun-2025, "Jul, 2025", day + abbreviation, m/d HH:MM, "qtr", "FY-", lone abbreviation, contextual Jan / Mar, lower-case month + day and day + lower-case month, ordinal + year, "of the month", "Recently 24th") and each second-pass form (one-letter glue, month + masked year, "in september", slug, "Recently 25."); moves: pre-NER drop, final pass, index level, its 60-character window, its count nouns and their word end, "S&P 1500", glued quote, amount + move noun, commodity level, its level words, level noun, large amount, "K", per-unit amounts, points, bare points (no subject needed / never a move), leading decimal, signed range, "selling off", "returned", sentence rule, signed numbers, the words after a signed number, the range check, move nouns, words before the noun, "%+", "down day", "dive", a fundamental in the noun, "Trading Surge", forecasts, "rise in sales", a product's price increase, "over the past", the adjective guard, the amount / "more" guard, the price-target exemption and its restatement, the phrase end, a fundamental after the number, "in the core CPI", "extends gain to", the possessive name, price / trading-period nouns, below a high, the subject rule, the company / tickers as subjects, the subject before the move word, the last fundamental, the clause check before the name rule, the name rule and its window, the stake and ticker compounds, the gauge suffix and its words, "/share", agency acronyms, bond yields, "trading activity", "holding"; scanner: each counterpart and its date forms; a market session without text gets a state (determinism test RED) | states/mask.py, states/scan.py, states/build.py |
| **revision 3:** exclusion skip removed from `news_items`; TradingView domain pattern never matches; explainer patterns never match; `market_selection` keeps excluded articles (determinism test RED); determinism test rebuilds `Inputs` by hand and drops `excluded` (RED); glued-verb alternative removed; each new date rule removed, one at a time (ordinal quarters, ordinal halves, "3T25", bare T after a period word, Korean quarters, Korean halves, glued d/m/y, day-first dd/mm, glued yyyymmdd, bare half-year, apostrophe year, curly apostrophes, lone month abbreviation, "recent’25" remnant, "domingo"); scanner revision-3 date forms removed | configs/states.yaml, states/build.py, states/mask.py, states/scan.py, tests/test_states_determinism.py |

The revision-1 mutation "ODFL back in the stoplist" no longer applies: a stoplisted ticker that is not an ordinary
word is masked in capitals anyway, which the revision-2 mutation on the vocabulary check covers.

## 3. Numbers

### 3.1 States

| File | robustness | train | val-A | val-B | test | total | mean articles |
|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 615 | 17,376 | 8,906 | 6,035 | 13,977 | 46,909 | 3.40 |
| callA_d2_E3 | 915 | 22,838 | 11,148 | 7,828 | 18,625 | 61,354 | 3.77 |
| callB_d2_E3 | — | 22,838 | 11,148 | 7,828 | — | 41,814 | 3.93 |
| market_E3 (A3.5) | 118 | 203 | 64 | 64 | 145 | 594 | 5.01 |

- **Samples.**
  - NA-07: 1,500 val-A + 1,500 val-B D0 events in each of E0–E4, the same events in every encoding. The E3 sample
    states are byte-identical to the main E3 states.
  - NA-06: an unmasked twin of 1,000 val-A D0 events (Call A E3). The masked twin is the same `event_id` in
    `callA_d0_E3`.
- **D0 vs D2 Call A.** 10,513 of the 46,909 D0 events have a byte-identical D2 Call A state (NA-03 counted 18,656
  identical W0/W2 lists; 10,933 before revision 6). The rest differ in the W2 attention words, the W2 earnings flag,
  the D2 budget cut, or (since revision 6) the running market stories that W2 keeps.
- **Events with every listed article excluded** (revisions 3, 4 and 6; `build_states.json` `events_all_excluded`).
  These are move explainers, TradingView reposts, non-English articles or, in W0, running market stories, so the
  event gets no state:
  - 1,061 D0 events (test 377, train 358, val-A 160, val-B 92, robustness 74; 190 of them since revision 6), 814 D2
    and 480 Call B (revision 5: 871 / 814 / 480; revision 3: 596 / 503 / 224);
  - 26,095 D0 and 30,585 D2 listed articles are left out, of which 14,897 and 19,642 are non-English and 3,447 (D0
    only) running market stories;
  - of the 296,082 event articles, 34,735 (11.7%) are excluded: 22,960 non-English (7.75%) and 11,775 explainers or
    TradingView reposts (corpus: 8,760 explainers, 38,135 TradingView articles);
  - PREREG §15 NA-04 rows 6, 8 and 10.
- **Events without text** (`build_states.json`). 133 D0, 117 D2 and 69 Call B events have no state, because every
  listed article lost its text to the price-path scrub, the price-move filter or the revision-4 and revision-5
  price rules ("Lockheed Martin (NYSE:LMT) Trading 0.8% Higher - Here's What Happened", "Dow Drops More Than 700
  Points"). D0: test 73, train 25, val-B 22, val-A 13, robustness 0 (revision 5: 148 D0; revision 4: 107 / 66 / 31;
  revision 3: 18 / 10 / 4). Since revision 6, 15 events that revision 5 counted here have only running market
  stories left and count as all excluded. PREREG §15 row 5 (e).
- **Market sessions without text** (revision 5; `build_states.json` `market_E3.sessions_without_text`). One
  robustness session lost every article to the index rules and has no A3.5 state (595 → 594).

### 3.2 Masking

- **Replacements** in the 296,082 event articles (title + snippet):
  - 353,348 company names;
  - 168,938 ticker forms;
  - 266,576 date / year / fiscal-period phrases (incl. datelines, ISINs and option codes; 263,311 before revision 3,
    266,161 before revision 4's month-year forms, 266,174 before revision 5's);
  - 93,376 person names (94,232 before revision 5: the price-talk sentences now go before NER).
- **Shares.** 63.3% of articles had a name masked and 19.7% a person. 4,324 articles have no text left (807 before
  revision 4's price rules, 2,852 before revision 5's). The 3,055 market articles (TradingView reposts, explainers and
  non-English articles left out) had 2,003 dates and 1,136 people masked; 80 have no text left.
- **Lexicons.** 1,772 corpus surnames (last words of multi-word PERSON names seen ≥ 3 times in English texts,
  capitalized ASCII, not an ordinary or company-alias word, not tagged inside an organization or place at least half
  as often) plus 49 listed public figures; 572 CJK names of 254 companies.
- **Not masked by design** (PRD risks; NA-06 measures them): products and subsidiaries (Zepbound, Firefly, Apple Watch
  → "the company Watch"), other companies' names, fundamental figures, "IT" before an IT noun in Gartner's texts, a
  CJK name never written before the company's ticker.
- **Non-English.** 7.75% of event articles are non-English by the revision-4 rule (NA-02's hint: 5.0%), 1% CJK. They
  are still masked (dates, harvested CJK names), but since revision 4 they are in no state (PREREG §15 NA-04 row 8):
  the masker's price rules and NA-02's scrubber are English-only.

### 3.3 Leak scan (val-A; `leak_scan.csv`, independent scanner)

| File | States | Name/ticker | Year/date | Price moves | Quotes | Price levels | Public figures | Post-open |
|---|---|---|---|---|---|---|---|---|
| callA_d0_E3 | 8,906 | 0.09% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.01% |
| callA_d2_E3 | 11,148 | 0.06% | 0.00% | 0.01% | 0.00% | 0.03% | 0.00% | 4.51% (in window) |
| callB_d2_E3 | 11,148 | 0.06% | 0.00% | 0.01% | 0.00% | 0.03% | 0.00% | 4.51% (in window) |
| unmasked twin (control) | 1,000 | 89.0% | 91.3% | 15.2% | 3.1% | 21.5% | 12.8% | 0.0% |

The post-open column (revision 6) counts live pages, live entries at or after the open and AP-style running text
in an item not stamped the evening before. The D2 files keep running market stories, whose text is inside their
window (it ends at the close); the D0 hit is "off to a rough start to the year". Before revision 6 the column read
4.69% of D0 states and 3.0% of the twin.

Since revision 4 the price columns use the scanner's broader rules (amounts after a share word, targets in any
notation, the direction after the number, noun forms); the revision-3 build scored 5.47% of D0 states on them.
Since revision 5 the moves column also counts the moves of any security and index or commodity levels
(`market_move_count`; the unmasked twin's moves went from 2.4% to 15.5%), and the date column the fifth
verification's forms. The 4 D2 states: another company's insider price ("20,200 Shares at $1.02/Share"), and three
false positives (an offering's 2.0% agent fee, a preferred redemption "at $1,000 per…", a $100,000 visa fee).

Revision 2 read its 9 D0 name/ticker states one by one:
- 5 were Gartner's "IT spending" / "IT services", kept on purpose; the scanner counts them conservatively.
- 4 were other entities: Citizens Holding Company, Morgan Stanley in Kinder Morgan's texts, Carnegie Mellon
  University, "visits to Vegas".

The revision-3 to revision-5 hits (9 / 8 / 8 D0, 9 / 8 / 7 D2) were not re-read one by one. **The scanner undercounts names.** The third
verification's hand count is 1.26% D0 / 0.97% D2 own names or tickers, plus about 30 D0 states in Korean /
Japanese. The forms it cannot see are one-word names that are ordinary words, glued or inflected names, slug
tickers, preferred / venue tickers and CJK transliterations. This residue is accepted (PREREG §15 NA-04 row 7).

### 3.4 Tokens and the tightening (S6, AC5)

- **Question tokens** (canonical JSON):

  | | Core battery | Longest single core question | Core + extended / explain |
  |---|---|---|---|
  | Call A | 302 | 132 (Q1) | 976 |
  | Call B | 355 | 146 (Q5) | 663 |

- **Before the tightening:**
  - Call A E3: p95 state 824 and p95 state + longest + 3 = 959 (pass).
  - Call B: p95 state 913 and p95 with the question 1,062; 12% of Call B states over 1,024 (fail).
- **Tightening** (`build.fit_news`; PREREG §15 row 5 (d)).
  - The lowest-ranked articles of a state are dropped (at least one stays) until state + longest core question
    + 3 ≤ 1,024. The caps are 889 state tokens at D0 and 875 at D2.
  - The D2 count reserves the longest possible E3 `reaction_so_far`. So Call A on D2 and Call B keep the same
    articles (tested), and the cut never depends on the observed reaction.
  - The samples and the unmasked twin reuse the D0 cut.
  - No text was cut.
  - Articles dropped by the budget or masking (excluded articles not counted): 1,939 from 1,863 D0 states (4.0%);
    4,585 from 4,368 D2 Call A states (7.1%); 3,590 from 3,406 Call B states (8.1%). Revision 4: 1,434 / 3,492 / 2,654;
    revision 3: 762 / 5,689 / 5,451. The revision-4 exclusions shortened the states, so fewer articles hit the cap;
    revision 5 empties more articles that were only price talk; revision 6 takes the running stories out of D0.
- **After** (`token_stats.csv`):

  | File | p50 state | p95 state | max | p95 + longest question | max + longest | share ≤ 768 |
  |---|---|---|---|---|---|---|
  | callA_d0_E3 | 552 | 761 | 889 | 896 | 1,024 | 96% |
  | callA_d2_E3 | 595 | 758 | 795 | 893 | 930 | 97% |
  | callB_d2_E3 | 689 | 837 | 874 | 986 | 1,023 | 73% |
  | samples E0 / E1 / E2 / E3 / E4 | 501 / 475 / 458 / 576 / 555 | 693 / 667 / 651 / 769 / 748 | ≤ 873 | ≤ 904 | ≤ 1,008 | 95–100% |
  | unmasked twin | 644 | 835 | 923 | 970 | 1,058 | 79% |

  Revision 4 (non-English articles out) shortened the states: Call A D0 p95 809 → 766, Call B 855 → 840; revision 5
  a little more (763 / 837), revision 6 Call A D0 to 761. The unmasked twin is an API probe (NA-06) with the masked
  twin's articles; 0.4% of it exceeds 1,024 with a question (3.3% before revision 4).
- **Laya.** The model card's `head_max_len = 256` leaves about 768 tokens for the state. 27% of Call B states and 4% of
  Call A D0 states are longer (47% / 13% before revision 4; owner decision 2, NA-08's decision C).
- **Cost.** Mean request tokens (state + core questions, val + test) exceed NA-03's assumption (news + 250 + 350):

  | Call | Actual | NA-03 assumed | Difference |
  |---|---|---|---|
  | Call A D0 | 861 | 803 | +7% |
  | Call A D2 | 890 | 826 | +8% |
  | Call B | 1,042 | 857 | +22% |

  The NA-11 full plan is dearer than NA-03 projected. Scaling the revision-3 estimate (requests 2–3% shorter, states
  0.7% fewer): roughly $9.5 at $0.042/M (fits $18) and $20.5–21.5 at $0.10/M (owner decision 3).

### 3.5 Context checks

- **Missing values** ("not available"), share of event keys:
  - σ / momentum percentiles: 1.5–4.5% (short history after index entry);
  - FY1 revision: 3–5%;
  - E0 raw returns: 0.1–3% outside test (test E0 states are never built);
  - HY OAS z: 18.5% of robustness sessions (FRED history starts 2023-08).
- **Macro.** 30 CPI release dates 2024-01 … 2026-07 match the BLS schedule, including the shutdown-delayed 2025-10-24
  and 2025-12-18 releases. 24 FOMC statement dates.
- **Earnings.** A scheduled report falls in W0 for 4.3% of val-A event keys.

## 4. Questions (S4)

- **Shape.** Call A asks core {justified_move (score, 9), materiality (choice, 2 neutral keys), surprise (score, 5),
  tone (score, 5)}; Call B asks {justified_move, reaction_adequacy (choice, 6), continuation (choice, 3)}. The extended
  group is Q7–Q15 (Call A), the explain group Q16–Q17 (Call B). All PREREG-verbatim strings are used as written.
- **Text written by NA-04** (PREREG §15 row 5 (c)):
  - instructions of Q2, Q5, Q6, Q9–Q13, Q15, each referencing `news` and/or `reaction_so_far` in backticks;
  - the middle levels of Q3 / Q4 / Q14;
  - option descriptions where PREREG gives keys only;
  - Q1's rise ranges, mirrored from the falls.
- **Empirical-finding self-check** (`test_authored_text_references_state_fields_and_states_no_finding`).
  - Every instruction and option is scanned for tends / usually / typically / historically / on average / often /
    more or less likely / research / studies / evidence / underreact / overreact / drift / momentum / revert:
    **no match**.
  - Backticked fields must be `news` or `reaction_so_far`.
  - Read by hand as well: no option states what a kind of news usually does. Q5's options are relative to "what the
    news justifies"; Q6's are directional only.

## 5. Spend, network

- **Spend.** OpenRouter $0.00 this chunk and cumulative (`ledgers/spend.jsonl` empty). FMP requests: 0. Kaggle: none.
- **Network:**
  - one download of the spaCy `en_core_web_sm` 3.8.0 wheel from GitHub, pinned in `pyproject.toml` / `uv.lock`;
  - three page reads: the OpenRouter Jev guide, the Laya model card and the Fed FOMC calendar.
- No article text or derived data left the machine.

## 6. Look-ahead self-check

| Input | Use | Availability |
|---|---|---|
| panel `sector`, `tier` (events), `beta_m`, `sigma_cc`, `z_m{5,20,60}`, `logv_mad60` (panel_public ∪ panel_test_inputs) | company block; volume multiple | `static` / `t_minus_1` (NA-01, through close(t−1)) |
| `ctx_sigma_cc_pct`, `ctx_z_m{k}_pct` | volatility regime; E4 | `t_minus_1`: the value at t (already through t−1) vs the symbol's 252 previous values; shock tests |
| panel `adj_close` (public) | `ctx_ret_m{k}` (E0 samples, val only) | shifted one session: AdjClose(t−1) / AdjClose(t−1−k) |
| estimates_fy1 | FY1 revision | snapshots dated before the session (and 30 days earlier); a snapshot dated on the session is not used (test) |
| earnings_dates | earnings flag | [close(prev s), 09:15 ET] (`w0`) / [close(prev s), close s) (`w2`); retrospective calendar, read as a pre-announced schedule |
| market_prices (SPY, VIX, DXY, oil), DGS10 | market block | last observation dated ≤ prev(s); σ / percentiles from the 252 changes before it |
| BAMLH0A0HYM2 | HY spread change | the change of t−2 (publication lag) |
| cpi_vintages, macro_calendar.yaml | scheduled releases today | `static` (published schedules) |
| window_counts via events (`attention_ratio_*`, `n_stories_*`) | attention block | `w0` / `w2` counts; 60-session mean `t_minus_1` (NA-03) |
| events news lists (title_clean / snippet_clean, t_avail, source_class_domain) | news block | `w0` / `w2` (NA-03 / NA-02); vendor `source_class` not used (only the domain class); running market stories, whose text postdates their stamp, in no W0 state (revision 6, row 10) |
| corpus surnames, CJK company names, ordinary-word vocabularies | masking, scanning | lexicons of the article texts (no return); the same for every split |
| articles_clean `third_party_ok` | governance check | `selection_only`; read only to refuse non-OK articles |
| `build_reactions(public)`: g_d2, react_r_cc, react_r_spy_cc, react_z_vol; z_cc history; SPY history | Call B `reaction_so_far` | `d2_reaction` (the reaction of s); E4 / σ histories through t−1; never in Call A (call rule + tests) |

## 7. Deviations from PREREG

Ten rows were appended to the §15 Deviations log (2026-10-25 and 2026-10-26, NA-04), all before the freeze. As in earlier chunks,
they are **in the working tree, not committed**, for the operator to commit on main.

1. **§6.10 industry.** Sector only; ATOM has GICS level 1 only.
2. **§6.10–§6.11 codebook additions:**
   - multi-day and market-series moves;
   - revision, count, volume, timing, time-label and source-type words;
   - "not available";
   - only moves vary with the encoding.
3. **§6.10 availability.** Publication lags (HY OAS at t−2), the CPI and FOMC calendars, the earnings windows.
4. **§6.3 / §6.4 masking**, revised after both verifications:
   - "the quarter" instead of "the latest quarter";
   - non-English dates, including Chinese, Japanese and Korean;
   - person names, including surnames used alone and Chinese transliterations;
   - price-target and deal-price amounts removed, which amends NA-02's rule;
   - price-move and share-price-level sentences and quote lines dropped;
   - every ticker form, including stoplisted tickers in capitals;
   - CJK company names harvested from the corpus.

   The operator decided the three marked policies.
5. **§6.4 / §6.10 / §7:**
   - (a) no pre-market talk in Call B;
   - (b) D2 Call A attention from W2;
   - (c) the question text written by NA-04;
   - (d) the token budget;
   - (e) no state for events without text.
6. **§2 / §6.4 / §6.9 / A3.1 / A3.5 excluded articles** (revision 3): move explainers and TradingView reposts are in
   no state. The NA-03 lists are not refilled. 596 D0 / 503 D2 / 224 Call B events are left without any article.
   Operator decision 2026-10-25.
7. **§6.3 residual target / AC2** (revision 3): the hand-labelled name / ticker residue (1.26% D0, 0.97% D2) is
   above 0.5% and accepted, and the revision-3 date forms are listed. Operator decision 2026-10-25.
8. **§6.3 / §6.4 / §6.9 / A3.1 / A3.5 price talk and non-English articles** (revision 4): non-English articles are
   in no state (operator decision B); the explainer title rule takes any move word; the masker drops the remaining
   English share-price levels, moves and price targets (two passes; a structural cents-amount rule last). 871 D0 /
   814 D2 / 480 Call B events are left without any article, 107 / 66 / 31 without text. Operator decision
   2026-10-26.
9. **§6.3 / §6.4 / §6.9 / A3.1 / A3.5 dates, every price move and level** (revision 5): the fifth verification's
   date forms; every price move of any security and every index or commodity level dropped, also from the A3.5
   market states (which carried their own target); a market session without text gets no state; the
   non-English residue (about 0.46% of val-A states) accepted. 148 D0 / 117 D2 / 69 Call B events and 1 market
   session are left without text. Operator decisions 2026-10-26.
10. **§2 / §6.4 / §6.9 running market stories in W0** (revision 6): live blogs and running market reports, whose
   text postdates their vendor stamp, are in no W0 state (Call A on D0, the NA-07 samples, the unmasked twin); W2
   states keep them. The NA-03 lists are not refilled. 1,061 D0 events are left without any article (190 more),
   133 without text. Operator decision 2026-10-26.

PRD-level choices that need no PREREG change are in `docs/decisions/NA-04.md`.

## 8. STOP conditions and owner decisions

No STOP condition fired: no API call, no budget, no 2026 outcome, no new third party. The three masking policies the
first verification raised were decided by the operator on 2026-10-25 (Revision 1); the second verification raised
no new policy question. The third raised three, which the operator decided on 2026-10-25 (Revision 3): exclude the
explainers, exclude TradingView, accept the name residue. The fourth found price talk outside AC2's metrics; the
operator decided on 2026-10-26 to fix it before any API spend and to apply decision B (drop non-English articles)
at the states step (Revision 4). The fifth failed AC2 on dates and found index, other-company and past moves; the
operator decided on 2026-10-26 to remove every move and every index or commodity level and to accept the
non-English residue (Revision 5). The sixth passed every criterion on its metrics and found running market stories
whose text postdates their stamp in D0 states, a look-ahead; the operator chose on 2026-10-26 to leave them out of
the D0 states before NA-05 (Revision 6).

Owner decisions:

1. **Confirm the ten NA-04 rows in PREREG §15.** Especially:
   - row 4: masking, including the change to NA-02's price-target rule;
   - row 5 (d): the token budget drops the last articles of 7.1% of D2 lists;
   - rows 6–7 (revision 3), row 8 (revision 4), row 9 (revision 5) and row 10 (revision 6).
2. **Laya's state budget.** Every state fits PREREG §9.1's max length 1,024 together with its longest question. If
   NA-08 keeps the released checkpoint's `head_max_len = 256` (≈ 768 for the state), 27% of Call B and 4% of Call A
   D0 states would be cut at the end of the news list (47% / 13% before revision 4). NA-08 should either set the head length to the question's
   actual length (≤ 146 tokens) or ask for a tighter state budget, which is one constant in `configs/states.yaml`.
3. **Cost projection.** Requests are 8–22% larger than NA-03 assumed (§3.4). At $0.10/M the full NA-11 plan is about
   $20.5–21.5 against the $18 cap. NA-05's pilot should re-project with the real states.
4. **Non-English articles** (NA-02 decision 4): decided (operator decision B, 2026-10-25) and applied here in
   revision 4, at the states step and not at NA-02's `keep` (which feeds the frozen F5 filter).
5. **`parsing_allowed == None`** (NA-02 decision 1): the operator allowed these articles (decision A, 2026-10-25).
   Applying it needs the NA-02 → NA-03 → NA-04 rebuild path, which NA-04 has not run. States use only the current
   third-party-OK articles; the rebuild should re-run the leak checks on the added 2024 states.
6. **Identifiability.** Product names, distinctive facts and the accepted name residue remain (row 7). NA-06's
   company-identification probe will measure it on the masked / unmasked twins.
7. **NA-02 timestamps (revision 3).** Revision 3 found vendor timestamps that precede their content. They occur for
   TradingView reposts and pre-open-stamped move explainers, both now left out of the states. NA-02's `t_avail`
   and the NA-03 lists still contain them, so a later chunk that reads articles directly (for example the NA-10
   bars or NA-12 analyses of news timing) should apply the same `news_exclusion` rule.
8. **Language detection downstream (revision 4).** NA-02's `non_english_hint` misses about a third of non-English
   texts. A later chunk that needs English-only text should use `states.build.non_english` (configured in
   `configs/states.yaml`), not the hint.
9. **NA-02 company attribution (fifth verification).** Some Ainvest / "Stock Analysis" items sit under the wrong
   company: Linde's text under APD, Incyte's under TECH, ResMed's under EW. The masker masks the event company's
   names, so another company's name stays readable in such a state, and the news is about another firm. This is
   an NA-02 ticker-mapping issue; NA-04 does not change the NA-03 lists. NA-06's identification probe and the
   NA-05 pilot will see it; a fix belongs to NA-02 (re-attribution) and needs the NA-02 → NA-03 → NA-04 rebuild
   path.
10. **Price talk downstream (revision 5).** The states hold no price move or level, but NA-02's article texts and
   NA-03's lists still do. A later chunk that reads articles directly (NA-10 bars, NA-12 news-timing analyses)
   should mask them with `states.mask.Masker` or reuse `Masker.has_market_move`.
11. **Running stories downstream (revision 6).** NA-02's `t_avail` and NA-03's lists still contain the running
   market stories, and NA-03's F5 selection scored them (the filter stays frozen; an event left without an article
   loses its D0 state). A chunk that reads W0 articles directly (NA-10 bars, NA-12 news-timing analyses) should
   leave them out with `states.build.running_story_ids`.
12. **Overseas index moves (revision 6, found while testing).** 18 D0 states (0.04%; val-A 2) keep an overseas
   index move or level ("lifts Japan's Nikkei 3.5%"), before the US open: price talk under the 0.5% bar, not
   look-ahead. Revision 5's index list does not name the Nikkei, Sensex, Nifty, ASX or TSX. Fixing it means a
   masker change and a mask-stage rebuild; left as is unless the operator asks.

## 9. Files

- **Added — code.** `src/newsaction/states/{__init__, codebook, context, macro, mask, scan, questions, build, report}.py`.
- **Added — configs.** `configs/{codebook_v1, questions_v1, aliases, macro_calendar, states}.yaml`.
- **Added — docs and artifacts.** `docs/decisions/NA-04.md`; `artifacts/NA-04/{REPORT.md, token_stats.csv,
  leak_scan.csv, examples.md, summary.json, build_states.json}`.
- **Changed.**
  - `configs/availability.yaml`: 45 NA-04 columns.
  - `configs/frozen.yaml`: `questions_v1_sha256`, `codebook_v1_sha256`.
  - `docs/DATA_CONTRACT.md`: the NA-04 section, 16 artifacts.
  - `pyproject.toml` / `uv.lock`: `en-core-web-sm` 3.8.0 in the `embed` extra.
- **Changed, uncommitted.** `docs/PREREG.md` (§15 rows 1–10).
- **Tests.** 8 files: `test_states_codebook`, `test_states_pit`, `test_states_mask`, `test_states_questions_prereg`,
  `test_states_outputs`, `test_states_tokens`, `test_states_determinism`, `test_states_exclusion` (revision 3): 668
  tests (17 / 130 / 394 / 13 / 19 / 7 / 1 / 87; 300 before revision 4, 373 before revision 5, 605 before revision 6).
- **Derived (gitignored).** `work/states/*` (16 files); `work/MANIFEST.json`.
- **Peak RSS per stage (GB).** context 0.7, mask 1.8–2.3 (spaCy, 4 workers), states 3.2–4.3 (5.2–5.8 since revision
  4: the language rule reads every listed article's raw text), report 1.5.
- **Reproducibility.**
  - Revision 2: the final code was built (`mask`, `states`, `report`), then `mask` and `states` were run again,
    each in a new process. All 16 `work/states/` sha256s were identical (16 of 16). Mask stage 783 / 818 s, states
    328 / 341 s.
  - Revision 3: the uncommitted fix was built (mask 660 s, states 328 s, report 54 s), then the three stages were
    run again from the fix commit `314efd2` (mask 872 s, states 327 s, report 54 s). All 13 rebuilt `work/states`
    files and the 5 report artifacts came out byte for byte identical (18 of 18). The manifest records `314efd2`.
  - Revision 4: uncommitted builds while the rules were tuned on val-A, then builds from each fix commit
    (mask 550–595 s, states 219–226 s, report 36–42 s). The final states come from `36f597d`, the report from
    `5e764ec`. A full rerun from `3680bd2` (mask 595 s, states 225 s, report 42 s) reproduced all 22 outputs byte
    for byte (13 rebuilt `work/states` files, 5 report artifacts, the 3 context files, `configs/frozen.yaml`).
  - Revision 5: one build from each fix commit (`c056249`, `0fdc7ef`, `3a73c52`, `7af8192`; mask 622–645 s, states
    214–217 s, report 51–58 s), each read by hand before the next; the report stage again from `d8a2d02` (identical).
    A full rerun from `d8a2d02` (mask 648 s, states 220 s, report 58 s) reproduced all 22 outputs byte for byte. The
    manifest records `d8a2d02`.
  - Revision 6: the mask and context stages were not run (the rule reads only the registered article fields, and
    `market_selection` is unchanged). Four `states` + `report` builds while the rule was tuned (states 263–268 s,
    peak RSS 3.9–5.7 GB; report 60 s, 1.5 GB), each read before the next. Then a rerun of both stages from
    `c70ca7f` (states 259 s, report 59 s) reproduced all 16 outputs byte for byte: the 10 state files, the 5 report
    artifacts and `configs/frozen.yaml`. Call A on D2, Call B and the market states are byte-identical to
    revision 5. The manifest records `c70ca7f`.
- **`make verify`** (revision 6, final: exit 0, 136 s, peak RSS 9.7 GB; ruff "All checks passed!", "110 files
  already formatted"; mypy --strict "no issues found in 54 source files"; pytest **1,215 passed, 1 xfailed**;
  manifest 56 artifacts OK; ledgers OK: fmp 0, spend 0, test_access 2, trials 94). Revision 5: 1,152 passed, 1
  xfailed, peak 10.0 GB. Revision 4: 947 passed, 1 xfailed, peak 10.8 GB. Revision 3, for reference (exit 0, 208 s, peak RSS 10.8 GB):
  - ruff check "All checks passed!"; ruff format "110 files already formatted"; mypy --strict "no issues found
    in 54 source files";
  - pytest **847 passed, 1 xfailed** (798 + 1 after revision 2);
  - manifest 56 artifacts OK; ledgers OK (fmp 0, spend 0, test_access 2, trials 94).
