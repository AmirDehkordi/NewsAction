"""NA-10: 30-minute bars from FMP and the D1 (10:00) inputs (PREREG §2.5, §5.4–5.6, A1.2; CLAUDE.md E18).

Modules, in pipeline order:
- ``fmp30``: the only path to FMP: a 30-minute-only httpx client; every request is reserved in
  ``ledgers/fmp_requests.jsonl`` before it is sent (``ledger.FmpLedger``, hard cap 3,000);
- ``probe``: the ≤ 5-request capability probe and the request projection
  (``artifacts/NA-10/capability.json``);
- ``fetch``: the request plan and the fetch; public bars to ``work/bars30/bars_public.parquet``, test-period
  bars written once through ``lock.write_sealed`` and never read here;
- ``basis``: price basis of the bars and their reconciliation with the EOD raw open;
- ``derive``: P_10:00, P_15:30, P_pre, intraday abnormal returns, σ_30, σ_rest
  (``work/panel/intraday_public.parquet``); G_D1, G^lvl and the 10:00 rung come from ``panel.reactions``
  and the D1 targets from ``panel.targets`` (hashed at the NA-11 freeze).

Constants: ``configs/bars.yaml``.
"""

from __future__ import annotations

import functools
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS

CHUNK: Final = "NA-10"
PRODUCER: Final = "newsaction.bars (NA-10)"
BARS_DIR: Final = "bars30"
RAW_DIR: Final = f"{BARS_DIR}/raw"  # under work/: gzip JSON answers of public windows (gitignored)
BARS_PUBLIC: Final = f"{BARS_DIR}/bars_public.parquet"
BARS_QC: Final = f"{BARS_DIR}/session_qc.parquet"
INTRADAY_PUBLIC: Final = "panel/intraday_public.parquet"
INTRADAY_SPY_PUBLIC: Final = "panel/intraday_spy_public.parquet"
CAPABILITY: Final = "artifacts/NA-10/capability.json"
BARS_CONFIG_PATH: Final = CONFIGS / "bars.yaml"


def blinded_bars_name() -> str:
    """Name of the test-period bars file as the lock knows it (``panel.targets.blinded_bars_file``)."""
    from newsaction.panel.targets import blinded_bars_file

    return blinded_bars_file()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VendorConfig(_Strict):
    base_url: str = Field(min_length=1)
    path: str = Field(min_length=1)
    path_v3: str = Field(pattern=r"\{symbol\}")
    interval: str = Field(pattern=r"^30min$")  # never 1-minute bars (CLAUDE.md E18)
    bar_minutes: int = Field(ge=30, le=30)
    timezone: str
    key_env: str = Field(min_length=1)
    rate_limit_rps: float = Field(gt=0, le=10)
    timeout_s: float = Field(gt=0)
    max_attempts: int = Field(ge=1, le=6)
    backoff_s: float = Field(ge=0)


class ProbeConfig(_Strict):
    max_requests: int = Field(ge=1, le=5)  # PRD NA-10 S2
    approved_extra: int = Field(ge=0, le=2)  # operator approval 2026-10-27 (configs/bars.yaml)


class AliasConfig(_Strict):
    ticker: str = Field(min_length=1)  # the ATOM ticker of the symbol
    alias: str = Field(min_length=1)  # the FMP ticker that has its bars in [start, end]
    start: date
    end: date


class ExcludeConfig(_Strict):
    ticker: str = Field(min_length=1)  # the ATOM ticker whose bars in [start, end] are not the company's
    start: date
    end: date


class FetchConfig(_Strict):
    membership_start: date
    stock_start: date
    history_sessions: int = Field(gt=0)
    spy_symbol: str = Field(min_length=1)
    spy_start: date
    aliases: tuple[AliasConfig, ...] = ()
    exclude: tuple[ExcludeConfig, ...] = ()


class ReconcileConfig(_Strict):
    open_tolerance_bp: float = Field(gt=0)
    basis_tolerance: float = Field(gt=0, lt=1)
    agree_tolerance: float = Field(gt=0, lt=1)
    trailing_sessions: int = Field(ge=1)


class BarsConfig(_Strict):
    vendor: VendorConfig
    probe: ProbeConfig
    fetch: FetchConfig
    reconcile: ReconcileConfig


@functools.cache
def _load(path: Path, mtime_ns: int) -> BarsConfig:
    return BarsConfig.model_validate(load_yaml(path))


def load_bars_config(path: Path = BARS_CONFIG_PATH) -> BarsConfig:
    return _load(path, path.stat().st_mtime_ns)
