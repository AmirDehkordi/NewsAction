# NA-04 example states (val-A, masked, E3)

Three Call A (D0) and two Call B (D2) states, drawn with seed 2026 (`newsaction.states.report.examples`), for human review of the masking and the codebook. Each block is the exact `state_json` sent to a decision model, pretty-printed (the stored form is compact). Event ids and token counts are shown outside the state; they are not part of it.

## Call A, D0: `W0:1093:2025-07-03`

4 articles · 657 state tokens · 959 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "busy",
    "distinct_stories": "four"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "moderate fall (≈1.1× a typical month's move)",
      "past_three_months": "moderate fall (≈1.5× a typical three-month move)",
      "past_week": "negligible fall (≈0.3× a typical week's move)"
    },
    "sector": "Energy",
    "size": "a large US company (size rank 101–250)",
    "volatility_vs_its_past_year": "high"
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
      "headline": "Analyst Expectations For the company's Future",
      "snippet": "Providing a diverse range of perspectives from bullish to bearish, 8 analysts have published ratings on the company. The company. in the last three months.",
      "source_type": "news aggregator",
      "timing": "shortly before the open"
    },
    {
      "headline": "Le Congrès américain a person et budgétaire de a person",
      "snippet": "Le projet de loi phare sur la réduction des impôts du président a person a franchi jeudi son ultime étape au Congrès américain, la Chambre des...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "JPMorgan Adjusts Price Target on the company to $97 From $94, Maintains Overweight Rating",
      "snippet": "The company is one of the leading American natural gas distributors. Sales break down by activity as follows: - gathering, processing and distribution of...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Torre norte-americana, Blackrock, Meta",
      "snippet": "Analistas de valores mobiliários de Wall Street revisaram suas classificações e metas de preço para diversas empresas listadas nos EUA, incluindo American...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    }
  ]
}
```

## Call A, D0: `W0:222:2025-07-21`

6 articles · 757 state tokens · 1059 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "busy",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "very aggressive",
    "performance_vs_market_and_sector": {
      "past_month": "large rise (≈2.3× a typical month's move)",
      "past_three_months": "small rise (≈0.6× a typical three-month move)",
      "past_week": "moderate rise (≈1.2× a typical week's move)"
    },
    "sector": "Financials",
    "size": "one of the 100 largest US companies",
    "volatility_vs_its_past_year": "normal"
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
      "headline": "What to Expect From PPL Corporation's Next Quarterly Earnings Report",
      "snippet": "PPL Corporation will release its quarterly earnings next week, and analysts anticipate the bottom line to remain unchanged year-over-year.",
      "source_type": "news aggregator",
      "timing": "shortly before the open"
    },
    {
      "headline": "Rogers Communications RCI the quarter Earnings Preview Upside Potential Amid Strategic Acquisitions and Financing Moves",
      "snippet": "Forward-Looking Analysis Rogers Communications is expected to show a promising the quarter earnings report, driven by a combination of strategic acquisitions...",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "British BC Partners intends to sell a controlling stake in Navex for $2.5 billion",
      "snippet": "British BC Partners intends to sell a controlling stake in Navex for $2.5 billion BC Partners plans to raise from 5-6 billion euros for the flagship fund.",
      "source_type": "other source",
      "timing": "after yesterday's close"
    },
    {
      "headline": "The company Exits TikTok U.S. Investment Group | the company Stock News",
      "snippet": "The company has withdrawn from a group aiming to invest in TikTok's U.S. operations, according to insights from individuals with knowledge of the...",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "A person's Tariff Threat, Inflation Dynamics And Federal Reserve Updates: This Week In Economy",
      "snippet": "The past week was a rollercoaster ride in the world of economics and finance. From President's tariff threats against Russia to the Federal Re.",
      "source_type": "news aggregator",
      "timing": "overnight"
    },
    {
      "headline": "The company’s AI Strategy: Analysis of Dominance in Alternative Asset Management",
      "snippet": "The company AI strategy targets dominance in alternative assets—leveraging scale, infrastructure bets, and proprietary data to shape AI's future.",
      "source_type": "other source",
      "timing": "overnight"
    }
  ]
}
```

## Call A, D0: `W0:1139:2025-09-11`

1 articles · 395 state tokens · 697 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "unusually quiet",
    "distinct_stories": "one"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "small rise (≈0.6× a typical month's move)",
      "past_three_months": "moderate rise (≈1.8× a typical three-month move)",
      "past_week": "small fall (≈0.8× a typical week's move)"
    },
    "sector": "Consumer Staples",
    "size": "one of the 100 largest US companies",
    "volatility_vs_its_past_year": "very high"
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
      "headline": "The company the quarter Earnings Report",
      "snippet": "The company announced their quarter earnings recently. View the company's earnings results at MarketBeat.",
      "source_type": "automated article",
      "timing": "early this morning (before 08:00)"
    }
  ]
}
```

## Call B, D2: `W2:983:2025-07-10`

6 articles · 867 state tokens · 1222 with the core questions

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
      "snippet": "Le président américain a person a publié mercredi des avis finaux de tarifs douaniers visant sept partenaires commerciaux secondaires, alors que son...",
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
      "headline": "The company Price Target Raised to $175.00",
      "snippet": "The company had its price target boosted by investment analysts at Piper Sandler from $157.00 to $175.00 in a report...",
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
      "snippet": "The company had its price objective boosted by Wells Fargo & Company from $182.00 to $205.00 in a report issued on...",
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

## Call B, D2: `W2:297:2025-08-06`

6 articles · 811 state tokens · 1166 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "busy",
    "distinct_stories": "seven"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "large fall (≈2.7× a typical month's move)",
      "past_three_months": "moderate fall (≈1.1× a typical three-month move)",
      "past_week": "large fall (≈2.1× a typical week's move)"
    },
    "sector": "Consumer Staples",
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
      "headline": "",
      "snippet": "The company closed recently, with a 0.36% decline and a trading volume of $530 million, ranking 224th among stocks.",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Hill’s delivers double-digit revenue rise in the quarter",
      "snippet": "Hill's Pet Nutrition reported a 13% increase in revenue in the quarter compared to the same period last year. This accounted for 22.9% of the company's...",
      "source_type": "other source",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "A person Target on the company to $90 From $100, Maintains Buy Rating",
      "snippet": "A person Target on the company to $90 From $100, Maintains Buy Rating. LinkedIn X (ex-Twitter) WhatsApp a person.",
      "source_type": "news aggregator",
      "timing": "during today's trading session"
    },
    {
      "headline": "Allstate, BP, Oracle",
      "snippet": "TradingView India. Wall Street securities analysts revised their ratings and price targets on several U.S.-listed companies, including Allstate, BP,...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Wells Fargo & Company Lowers the company Price Target to $83.00",
      "snippet": "The company had its target price dropped by stock analysts at Wells Fargo & Company from $88.00 to $83.00 in a research...",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "Analysts' Mixed Views on Consumer Goods Stocks: The company and Grocery Outlet Holding.",
      "snippet": "Analysts have conflicting sentiments on the company and Grocery Outlet Holding (GO). Goldman Sachs analyst maintained a Buy rating...",
      "source_type": "automated article",
      "timing": "during today's trading session"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "moderate rise (≈1.0× a typical day's move)",
    "stock_move_vs_market_and_sector": "moderate rise (≈1.6× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "normal"
  }
}
```
