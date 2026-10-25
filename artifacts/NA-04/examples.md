# NA-04 example states (val-A, masked, E3)

Three Call A (D0) and two Call B (D2) states, drawn with seed 2026 (`newsaction.states.report.examples`), for human review of the masking and the codebook. Each block is the exact `state_json` sent to a decision model, pretty-printed (the stored form is compact). Event ids and token counts are shown outside the state; they are not part of it.

## Call A, D0: `W0:1093:2025-07-03`

4 articles · 654 state tokens · 956 with the core questions

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
      "snippet": "Le projet de loi phare sur la réduction des impôts du président a person a franchi recently son ultime étape au Congrès américain, la Chambre des...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "JPMorgan Adjusts Price Target on the company raised by about 3%, Maintains Overweight Rating",
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

## Call A, D0: `W0:211:2025-07-21`

6 articles · 743 state tokens · 1045 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "busy",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "little changed",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "negligible fall (≈0.2× a typical month's move)",
      "past_three_months": "negligible fall (≈0.4× a typical three-month move)",
      "past_week": "negligible rise (≈0.2× a typical week's move)"
    },
    "sector": "Health Care",
    "size": "one of the 100 largest US companies",
    "volatility_vs_its_past_year": "very high"
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
      "headline": "Exploring Analyst Estimates for the company the quarter Earnings, Beyond Revenue and EPS",
      "snippet": "The upcoming report from the company is expected to reveal quarterly earnings of $0.72 per share, indicating an increase of 16.1% compared to...",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    },
    {
      "headline": "What To Expect in Markets This Week: Tesla, Google Lead a String of Big Earnings Reports",
      "snippet": "Tesla earnings are scheduled for recently as the EV maker's sales falter; other tech companies set to report this week include Google, Intel, and IBM.",
      "source_type": "investor commentary",
      "timing": "overnight"
    },
    {
      "headline": "The company the company the quarter Earnings Preview Upside Potential on Robust Revenue Growth",
      "snippet": "Forward-Looking Analysis the company is expected to report its quarter earnings recently. Analysts anticipate a strong performance,...",
      "source_type": "automated article",
      "timing": "overnight"
    },
    {
      "headline": "The company Projected to Post Earnings recently",
      "snippet": "The company is anticipated to announce its quarter earnings results before the market opens recently.",
      "source_type": "automated article",
      "timing": "after yesterday's close"
    },
    {
      "headline": "The quarter Earnings Recap: Growth or Caution Ahead?",
      "snippet": "Market Analysis by covering: Chevron Corp, Citigroup Inc, Intel Corporation, Walt Disney Company. Read 's Market Analysis on Investing.com.",
      "source_type": "news aggregator",
      "timing": "shortly before the open"
    },
    {
      "headline": "The company Stock Report: Strong Buy Ratings Signal 13.42% Potential Upside",
      "snippet": "The company stands tall as a leader in the healthcare sector, specifically within the medical devices industry.",
      "source_type": "automated article",
      "timing": "early this morning (before 08:00)"
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

## Call B, D2: `W2:978:2025-07-10`

6 articles · 818 state tokens · 1173 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "very heavy",
    "distinct_stories": "more than ten"
  },
  "company": {
    "analyst_estimates_past_month": "cut",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "large fall (≈2.2× a typical month's move)",
      "past_three_months": "large fall (≈2.2× a typical three-month move)",
      "past_week": "very large fall (≈4.8× a typical week's move)"
    },
    "sector": "Health Care",
    "size": "an S&P 500 company (size rank 251–500)",
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
      "headline": "Cantor Fitzgerald Brokers Lower Earnings Estimates for the company",
      "snippet": "The company - Cantor Fitzgerald decreased their fiscal year EPS estimates for shares of the company in a report issued...",
      "source_type": "automated article",
      "timing": "shortly before the open"
    },
    {
      "headline": "JP Morgan Reduces PT on the company lowered by about 5%, Keeps a Hold Rating",
      "snippet": "The company is one of the 13 Cheap Healthcare Stocks with Huge Upside Potential. Recently, JP Morgan analyst maintained...",
      "source_type": "news aggregator",
      "timing": "during today's trading session"
    },
    {
      "headline": "The company Announces Preliminary Results For the quarter",
      "snippet": "The company is one of the 10 Best Growth Stocks to Buy With Huge Upside Potential. Recently, the company...",
      "source_type": "news aggregator",
      "timing": "shortly before the open"
    },
    {
      "headline": "The company Downgraded by Morgan Stanley | the company Stock News",
      "snippet": "The company has been downgraded by Morgan Stanley analyst, shifting the rating from Overweight to Equal Weight.",
      "source_type": "automated article",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "UnitedHealth names new chief of government programs, Medicaid unit",
      "snippet": "Longtime insurance executive will helm the company's Medicaid division, while an executive is stepping up as CEO of government programs.",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "The company: Morgan Stanley dégrade son opinion à neutre",
      "snippet": "The company est spécialisé dans les prestations de services de soins de santé gérés au sein des programmes de couverture et d'assurance maladie...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "negligible rise (≈0.3× a typical day's move)",
    "stock_move_vs_market_and_sector": "large fall (≈2.5× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "busy"
  }
}
```

## Call B, D2: `W2:285:2025-08-06`

2 articles · 549 state tokens · 904 with the core questions

```json
{
  "attention": {
    "articles_vs_usual": "unusually quiet",
    "distinct_stories": "two"
  },
  "company": {
    "analyst_estimates_past_month": "cut",
    "earnings_report": "no scheduled earnings report falls in this window",
    "market_sensitivity": "market-like",
    "performance_vs_market_and_sector": {
      "past_month": "extreme fall (≈5.7× a typical month's move)",
      "past_three_months": "very large fall (≈3.9× a typical three-month move)",
      "past_week": "moderate fall (≈1.3× a typical week's move)"
    },
    "sector": "Communication Services",
    "size": "a large US company (size rank 101–250)",
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
      "headline": "Disney tops earnings forecasts with streaming gains, raises guidance",
      "snippet": "LOS ANGELES -Walt Disney posted better-than-expected quarterly results and raised its annual profit forecast recently, led by gains in the streaming...",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    },
    {
      "headline": "Zacks Investment Ideas feature highlights: MSCI, the company and Healthpeak Properties",
      "snippet": "MSCI, the company, and DOC CEOs just bought millions in shares, signaling confidence despite recent stock weakness.",
      "source_type": "news aggregator",
      "timing": "early this morning (before 08:00)"
    }
  ],
  "reaction_so_far": {
    "stock_market_move": "moderate rise (≈1.0× a typical day's move)",
    "stock_move_vs_market_and_sector": "small fall (≈0.9× a typical day's move)",
    "time": "by the close",
    "volume_vs_normal": "busy"
  }
}
```
