"""NA-13: the pre-registered strategies (PREREG §12, A1.6) on the frozen signals.

- ``market``: the daily returns the books trade on (raw open→close, adjusted close→close, SPY's, β_m, the
  20-session dollar ADV, 10:00→close), public for validation and through ``newsaction.lock`` for the test;
- ``portfolios``: the rules (signals, entry and exit instants, the within-tier / pooled 20% sides) and the
  engine that turns them into calendar-time daily returns;
- ``costs``, ``capacity``, ``dsr``: per-side costs on both legs and the hedge, capacity at 1% of ADV, and
  the Bailey–López de Prado deflated Sharpe with the Mertens correction;
- ``benchmarks``: gap fade (price-only), the vendor-sentiment rank and the random-signal placebo;
- ``run``, ``tables``, ``contract``: the NA-13 run, its tables and its data-contract entries;
- ``ma_cross``: the operator's exploratory moving-average add-on (after the pre-registered strategies).
"""
