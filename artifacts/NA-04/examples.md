# NA-04 example states (val-A, masked, E3)

Three Call A (D0) and two Call B (D2) states, drawn with seed 2026 (`newsaction.states.report.examples`), for human review of the masking and the codebook. Each block is the exact `state_json` sent to a decision model, pretty-printed (the stored form is compact). Event ids and token counts are shown outside the state; they are not part of it.

## Call A, D0: `W0:1093:2025-07-03`

2 articles · 481 state tokens · 783 with the core questions

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
      "headline": "JPMorgan Adjusts Price Target on the company raised by about 3%, Maintains Overweight Rating",
      "snippet": "The company is one of the leading American natural gas distributors. Sales break down by activity as follows: - gathering, processing and distribution of...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    }
  ]
}
```

## Call A, D0: `W0:193:2025-07-21`

5 articles · 656 state tokens · 958 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "normal",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "cut sharply",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "moderate rise (≈1.2× a typical month's move)",
      "past_three_months": "negligible rise (≈0.1× a typical three-month move)",
      "past_week": "large rise (≈2.0× a typical week's move)"
    },
    "sector": "Health Care",
    "size": "a large US company (size rank 101–250)",
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
      "headline": "The company to Announce Results for the quarter, full-year recently",
      "snippet": "The company to Announce Results for the quarter, full-year recently. The company (NYS:...",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "The company Trading Volume Plummets 36 Percent to 231st Rank Despite Promising Drug Developments",
      "snippet": "Recently,. The company experienced a significant drop in trading volume, with a total of $504 million in shares traded,...",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    },
    {
      "headline": "The company Stock Opinions on Phase 3 Trial Results",
      "snippet": "Recent discussions on X about the company have centered around the company's latest clinical trial results and strategic moves.",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "The company’s Reblozyl fails Phase 3 in anemia; Sanofi, Blueprint deal closes",
      "snippet": "Plus, news about DiaMedica Therapeutics, Cantargia and a person: The company suffers late-stage miss in anemia: Patients with...",
      "source_type": "other source",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Rep. Sells the company Shares",
      "snippet": "Representative (R-North Carolina) recently sold shares of the company. In a filing disclosed recently,...",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    }
  ]
}
```

## Call A, D0: `W0:1401:2025-09-11`

3 articles · 586 state tokens · 888 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "normal",
    "distinct_stories": "six"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "very aggressive",
    "performance_vs_market_and_sector": {
      "past_month": "small fall (≈0.9× a typical month's move)",
      "past_three_months": "negligible fall (≈0.0× a typical three-month move)",
      "past_week": "moderate fall (≈1.1× a typical week's move)"
    },
    "sector": "Health Care",
    "size": "an S&P 500 company (size rank 251–500)",
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
      "headline": "A person Takes one Step Back and Another Forward in his Attempt to Reshape the Fed",
      "snippet": "Cobb ruled that Fed governors can only be fired for malfeasance or other actions while in office and said the White House also failed to provide a person with a...",
      "source_type": "other source",
      "timing": "after yesterday's close"
    },
    {
      "headline": "U.S. CPI Rose Faster Than Expected 0.4% recently; Core Rate In Line",
      "snippet": "U.S. inflation for recent came in hotter than expected, though likely not enough to derail the Federal Reserve from cutting interest rates next week.",
      "source_type": "other source",
      "timing": "shortly before the open"
    },
    {
      "headline": "Rising US Stock Records Amid Mixed Market Signals: Decoding the S&P 500's Lead and the Divergent Paths of the Dow and Nasdaq",
      "snippet": "S&P 500's record highs reflect macroeconomic resilience and sector diversification, outperforming lagging Dow and Nasdaq.",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    }
  ]
}
```

## Call B, D2: `W2:975:2025-07-10`

4 articles · 691 state tokens · 1046 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "normal",
    "distinct_stories": "four"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "moderate fall (≈1.4× a typical month's move)",
      "past_three_months": "negligible fall (≈0.0× a typical three-month move)",
      "past_week": "large fall (≈2.5× a typical week's move)"
    },
    "sector": "Consumer Staples",
    "size": "a large US company (size rank 101–250)",
    "volatility_vs_its_past_year": "normal"
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
      "headline": "The company the quarter Earnings Report",
      "snippet": "The company announced their quarter earnings recently. View the company's earnings results at MarketBeat.",
      "source_type": "automated article",
      "timing": "during today's trading session"
    },
    {
      "headline": "North American Morning Briefing: Futures Point to -2",
      "snippet": "12:30/US: Recently Unemployment Insurance Weekly Claims Report - Initial Claims 12:30/US: U.S. Weekly Export Sales 13:00/RUS: Weekly International Reserves...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Global stocks mostly up despite new a person tariffs, Nasdaq at record",
      "snippet": "The Nasdaq powered to a fresh record and major European markets closed in the green recently, brushing off US President's growing array of...",
      "source_type": "news aggregator",
      "timing": "after yesterday's close"
    },
    {
      "headline": "Global Sports Nutrition Supplements Market Size is expected to experience a CAGR of 4.2% through the period, according to industry projections.",
      "snippet": "Global Sports Nutrition Supplements Market Size is expected to experience a CAGR of 4.2% through the period, according to industry projections.",
      "source_type": "other source",
      "timing": "after yesterday's close"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "negligible rise (≈0.3× a typical day's move)",
    "stock_move_vs_market_and_sector": "moderate fall (≈1.3× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "normal"
  }
}
```

## Call B, D2: `W2:401:2025-08-06`

3 articles · 615 state tokens · 970 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "normal",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "raised",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "very aggressive",
    "performance_vs_market_and_sector": {
      "past_month": "small rise (≈0.5× a typical month's move)",
      "past_three_months": "negligible fall (≈0.4× a typical three-month move)",
      "past_week": "negligible fall (≈0.1× a typical week's move)"
    },
    "sector": "Industrials",
    "size": "an S&P 500 company (size rank 251–500)",
    "volatility_vs_its_past_year": "normal"
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
      "headline": "London Heathrow Expansion: These 4 New Long-Haul Airlines Set To Launch Flights",
      "snippet": "Air Peace, Alaska Airlines, IndiGo, and Riyadh Air are reportedly coming.",
      "source_type": "major news outlet",
      "timing": "shortly before the open"
    },
    {
      "headline": "The company COVID-19 flexible booking",
      "snippet": "+1 844 376 0587Take advantage of the company COVID-19 flexible booking for peace of mind when planning your trip. +1 844 376 0587the company has.",
      "source_type": "other source",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Behind the scenes with a company meteorologist",
      "snippet": "Every day, a person sits down at his desk in the company's Operations and Customer Center in Atlanta and performs a job that's crucial to the airline's.",
      "source_type": "other source",
      "timing": "early this morning (before 08:00)"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "moderate rise (≈1.0× a typical day's move)",
    "stock_move_vs_market_and_sector": "moderate rise (≈1.0× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "normal"
  }
}
```
