# NA-04 example states (val-A, masked, E3)

Three Call A (D0) and two Call B (D2) states, drawn with seed 2026 (`newsaction.states.report.examples`), for human review of the masking and the codebook. Each block is the exact `state_json` sent to a decision model, pretty-printed (the stored form is compact). Event ids and token counts are shown outside the state; they are not part of it.

## Call A, D0: `W0:1098:2025-07-03`

6 articles · 722 state tokens · 1024 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "normal",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "aggressive",
    "performance_vs_market_and_sector": {
      "past_month": "small rise (≈0.6× a typical month's move)",
      "past_three_months": "negligible rise (≈0.3× a typical three-month move)",
      "past_week": "negligible rise (≈0.0× a typical week's move)"
    },
    "sector": "Information Technology",
    "size": "an S&P 500 company (size rank 251–500)",
    "volatility_vs_its_past_year": "very high"
  },
  "market": {
    "dollar_change": "negligible fall (≈0.0× a typical day's move)",
    "high_yield_spread_change": "small fall (≈0.8× a typical day's move)",
    "oil_change": "moderate rise (≈1.4× a typical day's move)",
    "scheduled_releases_today": "none scheduled",
    "stock_market_previous_session": "small rise (≈0.6× a typical day's move)",
    "ten_year_yield_change": "small rise (≈0.6× a typical day's move)",
    "vix_change": "negligible fall (≈0.1× a typical day's move)",
    "vix_level_vs_past_year": "normal"
  },
  "news": [
    {
      "headline": "",
      "snippet": "Nasdaq's record rally fuels upside in MSFT, V, and MA as easing tariffs and AI momentum lift tech optimism.",
      "source_type": "news aggregator",
      "timing": "shortly before the open"
    },
    {
      "headline": "‘Investors Were Relieved’: CNN Admits Stock Market Having ‘Remarkable’ Turnaround Under a person",
      "snippet": "CNN reporter a person and “CNN News Central” host a person expressed shock recently at the “remarkable” turnaround on Wall Street as stocks...",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Silicon On Insulators Market Thrives On Surging Demand",
      "snippet": "Stay ahead with our updated market reports featuring the latest on tariffs, trade flows, and supply chain transformations. What Will the Silicon On...",
      "source_type": "automated article",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Chip Industry Week in Review",
      "snippet": "U.S. lifts EDA export restrictions to China; collusion risk in the IC supply chain; Onto buys materials analysis biz; Tenstorrent acquires a person;...",
      "source_type": "other source",
      "timing": "overnight"
    },
    {
      "headline": "Ambiq Micro files for U.S. IPO as generative AI fuels chip demand",
      "snippet": "",
      "source_type": "news aggregator",
      "timing": "shortly before the open"
    },
    {
      "headline": "The Role of Semiconductor Filters in Shaping Modern Electronics",
      "snippet": "Explore how advancements in semiconductor filter technology, including AI integration and ultra-pure gas filtration, shape industries like 5G, IoT,...",
      "source_type": "other source",
      "timing": "after yesterday's close"
    }
  ]
}
```

## Call A, D0: `W0:185:2025-07-21`

6 articles · 691 state tokens · 993 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "very heavy",
    "distinct_stories": "six"
  },
  "company": {
    "analyst_estimates_past_month": "cut",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "aggressive",
    "performance_vs_market_and_sector": {
      "past_month": "small rise (≈0.7× a typical month's move)",
      "past_three_months": "moderate fall (≈1.0× a typical three-month move)",
      "past_week": "large fall (≈2.1× a typical week's move)"
    },
    "sector": "Industrials",
    "size": "an S&P 500 company (size rank 251–500)",
    "volatility_vs_its_past_year": "high"
  },
  "market": {
    "dollar_change": "small fall (≈0.5× a typical day's move)",
    "high_yield_spread_change": "moderate fall (≈1.5× a typical day's move)",
    "oil_change": "negligible fall (≈0.1× a typical day's move)",
    "scheduled_releases_today": "none scheduled",
    "stock_market_previous_session": "negligible fall (≈0.0× a typical day's move)",
    "ten_year_yield_change": "small fall (≈0.5× a typical day's move)",
    "vix_change": "negligible fall (≈0.0× a typical day's move)",
    "vix_level_vs_past_year": "normal"
  },
  "news": [
    {
      "headline": "The company the quarter Earnings Report",
      "snippet": "The company announced their quarter earnings recently. View the company's earnings results at MarketBeat.",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "Zelman & Associates Reaffirms Underperform Rating for the company",
      "snippet": "The company's stock had its \"underperform\" rating reiterated by investment analysts at Zelman & Associates in a...",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "Jefferies Reiterates Buy Rating on the company with Price Target",
      "snippet": "Jefferies maintains a Buy rating on the company with a price target, citing positive corporate insider sentiment and a one-year high of...",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    },
    {
      "headline": "North American Morning Briefing: Stocks Rise -2",
      "snippet": "Of about the year bunkers and air-raid shelters operational during the Cold War, only 580 remain, offering space for 480000 people, or half a percent of...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Tremont Co-operative Grain Co.",
      "snippet": "",
      "source_type": "other source",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Insider Buying Surges: Top Executives Invest $170 Million in the company, UNH, and MIDD",
      "snippet": "Insider buying activity has surged at three major companies, with top executives and influential insiders investing over $170 million.",
      "source_type": "automated article",
      "timing": "overnight"
    }
  ]
}
```

## Call A, D0: `W0:1452:2025-09-11`

6 articles · 672 state tokens · 974 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "very heavy",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "moderate fall (≈1.4× a typical month's move)",
      "past_three_months": "moderate fall (≈1.9× a typical three-month move)",
      "past_week": "very large fall (≈3.0× a typical week's move)"
    },
    "sector": "Information Technology",
    "size": "an S&P 500 company (size rank 251–500)",
    "volatility_vs_its_past_year": "not available"
  },
  "market": {
    "dollar_change": "negligible fall (≈0.0× a typical day's move)",
    "high_yield_spread_change": "small rise (≈0.5× a typical day's move)",
    "oil_change": "small rise (≈0.8× a typical day's move)",
    "scheduled_releases_today": "consumer price index release before the open",
    "stock_market_previous_session": "negligible rise (≈0.4× a typical day's move)",
    "ten_year_yield_change": "small fall (≈0.6× a typical day's move)",
    "vix_change": "negligible rise (≈0.3× a typical day's move)",
    "vix_level_vs_past_year": "low"
  },
  "news": [
    {
      "headline": "How major US stock indexes fared recently, recently",
      "snippet": "",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "S&P 500 ends at record as markets await key US consumer price data",
      "snippet": "",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Stock market today: S&P 500, Nasdaq notch fresh records as Oracle soars, with inflation data on deck",
      "snippet": "",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Morning Bid: Another day, another AI record",
      "snippet": "Oracle's skyrocketing share price lifted Asian equities recently, as AI enthusiasm shows no signs of abating. Meanwhile, European markets remain in...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "",
      "snippet": "Oracle's massive backlog for its cloud business stunned Wall Street recently, cementing its spot as a key player in the AI market and lifting hopes that...",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Wall Street futures inch higher in lead-up to inflation data",
      "snippet": "U.S. stock index futures were slightly higher recently as investors refrained from making large bets ahead of crucial inflation numbers that are likely...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    }
  ]
}
```

## Call B, D2: `W2:983:2025-07-10`

6 articles · 850 state tokens · 1205 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "normal",
    "distinct_stories": "six"
  },
  "company": {
    "analyst_estimates_past_month": "raised",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "moderate rise (≈1.2× a typical month's move)",
      "past_three_months": "large rise (≈2.7× a typical three-month move)",
      "past_week": "moderate rise (≈1.0× a typical week's move)"
    },
    "sector": "Energy",
    "size": "a large US company (size rank 101–250)",
    "volatility_vs_its_past_year": "high"
  },
  "market": {
    "dollar_change": "negligible fall (≈0.0× a typical day's move)",
    "high_yield_spread_change": "moderate rise (≈1.0× a typical day's move)",
    "oil_change": "negligible rise (≈0.0× a typical day's move)",
    "scheduled_releases_today": "none scheduled",
    "stock_market_previous_session": "small rise (≈0.7× a typical day's move)",
    "ten_year_yield_change": "moderate fall (≈1.3× a typical day's move)",
    "vix_change": "small fall (≈0.7× a typical day's move)",
    "vix_level_vs_past_year": "low"
  },
  "news": [
    {
      "headline": "A person Annonce de Nouveaux Avis de Tarifs Douaniers alors que l'UE Pousse pour un Accord Commercial avec les États-Unis",
      "snippet": "Le président américain a person a publié recently des avis finaux de tarifs douaniers visant sept partenaires commerciaux secondaires, alors que son...",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Marathon Oil Employees: Is the Russia-Ukraine War a Threat to the Global Economy?",
      "snippet": "Standard deduction. $15,000 single; $30,000 married filing jointly for the year, $15,750 single; $31,500 married filing jointly for the year.",
      "source_type": "other source",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "The company Price Target Raised",
      "snippet": "The company had its price target boosted by investment analysts at Piper Sandler raised by about 11% in a report...",
      "source_type": "automated article",
      "timing": "during today's trading session"
    },
    {
      "headline": "The company: UBS herhaalt koopadvies",
      "snippet": "The company is gespecialiseerd in olieraffinage, transport en distributie. De verkoop kan als volgt per activiteit worden uitgesplitst...",
      "source_type": "news aggregator",
      "timing": "during today's trading session"
    },
    {
      "headline": "Wells Fargo & Company Issues Positive Forecast for the company Stock Price",
      "snippet": "The company had its price objective boosted by Wells Fargo & Company raised by about 13% in a report issued on...",
      "source_type": "automated article",
      "timing": "during today's trading session"
    },
    {
      "headline": "The company Price Target Raised by Wells Fargo | the company Stock News",
      "snippet": "Recently, Wells Fargo analyst announced an update on the company, maintaining an \"Overweight\" rating on the stock...",
      "source_type": "automated article",
      "timing": "during today's trading session"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "negligible rise (≈0.3× a typical day's move)",
    "stock_move_vs_market_and_sector": "moderate rise (≈1.0× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "busy"
  }
}
```

## Call B, D2: `W2:400:2025-08-06`

6 articles · 846 state tokens · 1201 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "busy",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "not available",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "negligible fall (≈0.1× a typical month's move)",
      "past_three_months": "small rise (≈0.5× a typical three-month move)",
      "past_week": "small rise (≈0.5× a typical week's move)"
    },
    "sector": "Utilities",
    "size": "a large US company (size rank 101–250)",
    "volatility_vs_its_past_year": "very high"
  },
  "market": {
    "dollar_change": "no change (≈0.0× a typical day's move)",
    "high_yield_spread_change": "moderate fall (≈1.8× a typical day's move)",
    "oil_change": "small fall (≈0.7× a typical day's move)",
    "scheduled_releases_today": "none scheduled",
    "stock_market_previous_session": "small fall (≈0.7× a typical day's move)",
    "ten_year_yield_change": "no change (≈0.0× a typical day's move)",
    "vix_change": "negligible rise (≈0.2× a typical day's move)",
    "vix_level_vs_past_year": "normal"
  },
  "news": [
    {
      "headline": "The company the quarter Earnings Call Transcript",
      "snippet": "The company the quarter Earnings Call Transcript recently. The company beats earnings expectations. Reported EPS is $0.75,...",
      "source_type": "investor commentary",
      "timing": "shortly before the open"
    },
    {
      "headline": "The company Posts Higher Profit",
      "snippet": "The company has reported $649 million in adjusted net profit for the quarter, up from $567 million for the same three-month period last year...",
      "source_type": "other source",
      "timing": "during today's trading session"
    },
    {
      "headline": "The company's the quarter Earnings Call: Balancing Progress and Challenges",
      "snippet": "The company reported the quarter operating earnings of $0.75 per share, reaffirming its financial guidance for the year. The Coastal Virginia Offshore Wind project...",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "The company's Solar Stadium Push Drives 46.63% Trading Surge to 182nd in Market Activity",
      "snippet": "Recently,. The company traded with a volume of $0.61 billion, a 46.63% increase from the previous day, ranking 182nd in market...",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    },
    {
      "headline": "IBD Rating Upgrades: The company Flashes Improved Technical Strength",
      "snippet": "Recently, the company received a positive adjustment to its Relative Strength (RS) Rating, from 69 to 72. When To Sell Stocks To Lock In Profits And...",
      "source_type": "news aggregator",
      "timing": "overnight"
    },
    {
      "headline": "U.S. MBA 30-Year Mortgage Rate Hits 6.77%: Sector-Specific Market Responses and Strategic Portfolio Adjustments",
      "snippet": "U.S. MBA 30-Year Mortgage Rate fell to 6.77% recently, sparking sector-specific market responses amid inflation and labor challenges.",
      "source_type": "automated article",
      "timing": "early this morning (before 08:00)"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "moderate rise (≈1.0× a typical day's move)",
    "stock_move_vs_market_and_sector": "small rise (≈0.8× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "normal"
  }
}
```
