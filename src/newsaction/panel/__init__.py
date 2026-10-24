"""The daily point-in-time panel (NA-01; PREREG §3, §5, Amendment A1).

Modules, in pipeline order:
- ``grid``: the session x symbol grid and the explicit t-1 lag every rolling statistic uses;
- ``mapping``: ATOM symbol_id -> Data/prices symbol, validated by return correlation;
- ``adjust``: adjusted prices and returns (r_cc, r_on, r_id), split/spin-off classification, QC flags,
  raw-close reconstruction for ranking sessions whose raw prices are blinded;
- ``sector``: point-in-time GICS sector and leave-one-company-out sector returns;
- ``risk``: betas, abnormal returns, robust sigma, z-scores, abnormal volume, momentum (all through t-1);
- ``tiers``: companies (share classes grouped), representative class, market caps, monthly tiers;
- ``targets`` / ``reactions``: outcomes and observed reactions (hashed at the NA-11 freeze; the test
  period is reachable only through ``newsaction.lock``);
- ``build``: the CLI that writes work/panel/*.parquet.
"""

from __future__ import annotations

from datetime import date
from typing import Final

HISTORY_START: Final = date(2022, 1, 3)  # first price session in the snapshot (PRD NA-01 S1.d)
PANEL_START: Final = date(2023, 7, 3)  # first session of panel_public (PRD NA-01 S7)
