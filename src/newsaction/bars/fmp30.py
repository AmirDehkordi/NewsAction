"""The FMP 30-minute bar client: the only path to FMP (PRD NA-10 S1; CLAUDE.md E18; PREREG §13).

- **Endpoint.** ``/stable/historical-chart/30min?symbol=&from=&to=`` (``configs/bars.yaml``; ``to`` is
  inclusive, ATOM IR-04). The interval is fixed by the config schema: 1-minute bars cannot be asked for.
- **Ledger.** Every HTTP attempt is a request. It is reserved in ``ledgers/fmp_requests.jsonl`` *before* it
  is sent (``FmpLedger.reserve``, which raises ``FmpCapExceeded`` for request cap + 1, so nothing is sent),
  and a ``response`` line records its status, rows and bytes when it returns. A retry is reserved again.
- **Cache.** Answers of public windows are stored under ``work/bars30/raw/<key>.json.gz`` (the vendor's text,
  gzip; gitignored). A cache hit sends nothing and logs nothing. A window that reaches the test period is
  never cached there: ``fetch`` writes those answers through ``lock.write_sealed`` only (CLAUDE.md B8).
- **Key.** ``FMP_API_KEY`` from the environment or ``.env``, sent as the ``apikey`` query parameter. It never
  appears in the ledger, the cache, a log line or an error message (httpx exceptions carry the URL, so they
  are reduced to their class name).
- **Retries.** 429, 5xx and transport errors, with exponential backoff (at least ``Retry-After``), up to
  ``vendor.max_attempts`` attempts; any other status raises ``FmpError``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final, Literal

import httpx

from newsaction import io
from newsaction.bars import RAW_DIR, VendorConfig, load_bars_config
from newsaction.config import load_splits
from newsaction.ledger import FmpLedger
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso

FIELDS: Final = ("date", "open", "high", "low", "close", "volume")
RETRY_STATUS: Final = frozenset({429, 500, 502, 503, 504})
CACHE_VERSION: Final = 1


class FmpError(Exception):
    """An FMP request failed, or its answer is not a list of bars. Messages never contain the key or URL."""


Api = Literal["stable", "v3"]


@dataclass(frozen=True)
class BarRequest:
    """One request: a symbol, an inclusive date window and the two switches IR-04 measured at 1 minute.
    ``api`` "v3" is the legacy endpoint with the symbol in the path (probe only)."""

    symbol: str
    start: date
    end: date
    extended: bool = False
    nonadjusted: bool = False
    api: Api = "stable"

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"{self.symbol}: window {self.start} .. {self.end} is empty")
        if not self.symbol or any(c.isspace() for c in self.symbol):
            raise ValueError(f"bad symbol {self.symbol!r}")

    def switches(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.extended:
            out["extended"] = "true"
        if self.nonadjusted:
            out["nonadjusted"] = "true"
        return out

    def params(self) -> dict[str, str]:
        """Request parameters without the key (the symbol included, wherever the endpoint puts it)."""
        return {
            "symbol": self.symbol,
            "from": self.start.isoformat(),
            "to": self.end.isoformat(),
            **self.switches(),
        }

    def query(self) -> dict[str, str]:
        """Query-string parameters without the key (v3 carries the symbol in the path)."""
        q = self.params()
        if self.api == "v3":
            q.pop("symbol")
        return q

    def describe(self, interval: str) -> dict[str, Any]:
        """The canonical request; ``api`` appears only for v3, so /stable keys do not depend on it."""
        out: dict[str, Any] = {"interval": interval, **self.params()}
        if self.api != "stable":
            out["api"] = self.api
        return out

    def key(self, interval: str) -> str:
        """sha256 of the canonical request (interval + parameters): the cache key."""
        blob = json.dumps(self.describe(interval), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class Answer:
    request: BarRequest
    key: str
    status: int
    bars: list[dict[str, Any]]
    n: int | None  # ledger request number of the attempt that succeeded; None for a cache hit
    from_cache: bool
    fetched_at: str


def read_key(env: str, root: Path) -> str:
    """The API key from the environment, else from ``<root>/.env``. Never printed or logged."""
    value = os.environ.get(env, "").strip()
    if value:
        return value
    path = root / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, rest = line.strip().partition("=")
            if sep and name.strip() == env:
                value = rest.split(" #", 1)[0].strip().strip("\"'")
                if value:
                    return value
    raise FmpError(f"{env} is not set (environment or .env)")


def parse_bars(text: str) -> list[dict[str, Any]]:
    """The vendor's JSON list of bars; an object (FMP's error form) or a malformed row raises ``FmpError``."""
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FmpError(f"answer is not JSON ({exc.msg})") from None
    if isinstance(body, dict):
        msg = str(body.get("Error Message") or body.get("error") or sorted(body)[:5])
        raise FmpError(f"vendor error: {msg[:200]}")
    if not isinstance(body, list):
        raise FmpError(f"answer is a {type(body).__name__}, not a list")
    for row in body:
        if not isinstance(row, dict) or not set(FIELDS) <= set(row):
            raise FmpError(f"bar without the fields {FIELDS}: {str(row)[:120]}")
    return body


class FmpClient:
    """Synchronous, rate-limited client. ``transport`` and ``sleep`` are for tests (no network there)."""

    def __init__(
        self,
        *,
        ledger: FmpLedger | None = None,
        cfg: VendorConfig | None = None,
        layout: Layout | None = None,
        transport: httpx.BaseTransport | None = None,
        api_key: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.lay = resolve_layout(layout)
        self.cfg = load_bars_config().vendor if cfg is None else cfg
        self.ledger = FmpLedger(self.lay.ledgers / "fmp_requests.jsonl") if ledger is None else ledger
        self._key = api_key
        self._sleep = sleep
        self._clock = clock
        self._last = -1e18
        self._http = httpx.Client(transport=transport, timeout=self.cfg.timeout_s)
        self.sent = 0  # HTTP attempts made by this client

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FmpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def url(self, req: BarRequest) -> str:
        if req.api == "v3":
            return self.cfg.base_url.rstrip("/") + self.cfg.path_v3.format(symbol=req.symbol)
        return self.cfg.base_url.rstrip("/") + self.cfg.path

    def _api_key(self) -> str:
        if self._key is None:
            self._key = read_key(self.cfg.key_env, self.lay.root)
        return self._key

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "<key>") if self._key else text

    # --- cache --------------------------------------------------------------------------------------

    def cache_path(self, req: BarRequest) -> Path:
        return self.lay.work / RAW_DIR / f"{req.key(self.cfg.interval)}.json.gz"

    def _cacheable(self, req: BarRequest) -> bool:
        return req.end < load_splits().splits["test"].start

    def cached(self, req: BarRequest) -> Answer | None:
        path = self.cache_path(req)
        if not self._cacheable(req) or not path.is_file():
            return None
        rec = json.loads(gzip.decompress(path.read_bytes()))
        if rec.get("version") != CACHE_VERSION or rec.get("request") != req.describe(self.cfg.interval):
            raise FmpError(f"cache entry {path.name} does not match its request")
        return Answer(
            req,
            path.name.split(".")[0],
            int(rec["status"]),
            parse_bars(rec["text"]),
            None,
            True,
            rec["fetched_at"],
        )

    def _store(self, req: BarRequest, status: int, text: str, n: int, fetched_at: str) -> None:
        rec = {
            "version": CACHE_VERSION,
            "request": req.describe(self.cfg.interval),
            "status": status,
            "n": n,
            "fetched_at": fetched_at,
            "text": text,
        }
        io.atomic_write_bytes(self.cache_path(req), gzip.compress(json.dumps(rec).encode("utf-8"), mtime=0))

    # --- requests -----------------------------------------------------------------------------------

    def _throttle(self) -> None:
        wait = self._last + 1.0 / self.cfg.rate_limit_rps - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def _backoff(self, attempt: int, headers: Mapping[str, str] | None) -> None:
        delay = self.cfg.backoff_s * 2 ** (attempt - 1)
        retry_after = (headers or {}).get("retry-after", "")
        if retry_after.strip().isdigit():
            delay = max(delay, float(retry_after))
        self._sleep(delay)

    def get(self, req: BarRequest, *, purpose: str, cache: bool = True) -> Answer:
        """The answer to ``req``: from the cache if allowed and present, else from FMP (ledger first)."""
        if cache:
            hit = self.cached(req)
            if hit is not None:
                return hit
        key = req.key(self.cfg.interval)
        params = {**req.query(), "apikey": self._api_key()}
        meta = {**req.describe(self.cfg.interval), "key": key, "purpose": purpose}
        problem = "no attempt made"
        for attempt in range(1, self.cfg.max_attempts + 1):
            self._throttle()
            n = self.ledger.reserve({**meta, "attempt": attempt})  # before the request is sent
            self.sent += 1
            try:
                resp = self._http.get(self.url(req), params=params)
            except httpx.HTTPError as exc:
                problem = type(exc).__name__
                self.ledger.record_response(n, status=None, rows=None, error=problem)
                if attempt < self.cfg.max_attempts:
                    self._backoff(attempt, None)
                continue
            text = resp.text
            if resp.status_code in RETRY_STATUS:
                problem = f"HTTP {resp.status_code}"
                self.ledger.record_response(n, status=resp.status_code, rows=None, nbytes=len(resp.content))
                if attempt < self.cfg.max_attempts:
                    self._backoff(attempt, resp.headers)
                continue
            try:
                if resp.status_code != 200:
                    raise FmpError(f"HTTP {resp.status_code}: {self._scrub(text)[:200]}")
                bars = parse_bars(text)
            except FmpError as exc:
                msg = self._scrub(str(exc))
                self.ledger.record_response(
                    n, status=resp.status_code, rows=None, nbytes=len(resp.content), error=msg[:200]
                )
                raise FmpError(f"{req.symbol} {req.start}..{req.end}: {msg}") from None
            fetched_at = utc_now_iso()
            self.ledger.record_response(n, status=200, rows=len(bars), nbytes=len(resp.content))
            if cache and self._cacheable(req):
                self._store(req, 200, text, n, fetched_at)
            return Answer(req, key, 200, bars, n, False, fetched_at)
        raise FmpError(
            f"{req.symbol} {req.start}..{req.end}: gave up after {self.cfg.max_attempts} attempts ({problem})"
        )
