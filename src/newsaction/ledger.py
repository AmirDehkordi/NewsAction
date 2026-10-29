"""Append-only JSONL ledgers (CLAUDE.md B8, B10, C12, E18): spend, trials, test access, FMP requests.

Every line is one JSON object, written under a file lock, flushed and fsynced. Lines are
hash-chained: ``prev`` is the sha256 of the previous line (``GENESIS`` for the first), so editing,
deleting or reordering earlier lines is detected by ``verify()`` and ``make ledgers``. There is no
API that rewrites a ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

from newsaction.config import BudgetConfig, SplitName, load_project
from newsaction.paths import LEDGERS
from newsaction.provenance import git_sha_cached, utc_now_iso

GENESIS: Final = "0" * 64
_RESERVED_KEYS: Final = frozenset({"ts", "prev"})
_EPS: Final = 1e-9

SPEND: Final = "spend.jsonl"
TRIALS: Final = "trials.jsonl"
TEST_ACCESS: Final = "test_access.jsonl"
FMP_REQUESTS: Final = "fmp_requests.jsonl"
LEDGER_FILES: Final = (SPEND, TRIALS, TEST_ACCESS, FMP_REQUESTS)


class LedgerError(Exception):
    """Ledger protocol violation."""


class LedgerCorrupt(LedgerError):
    """A ledger file is not a valid, intact hash chain of JSON lines."""


class BudgetExceeded(LedgerError):
    """A reservation or a recorded spend would cross the chunk cap or the total cap."""


class FmpCapExceeded(LedgerError):
    """The FMP request cap (PREREG §13) would be crossed."""


def _hash(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def _encode(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False
    ).encode()


class JsonlLedger:
    """One append-only, hash-chained JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = FileLock(f"{path}.lock")
        self._offset = 0
        self._tail = GENESIS
        self._pending: list[dict[str, Any]] = []  # scanned but not yet handed to read_new()

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._append_locked(record)

    def _append_locked(self, record: Mapping[str, Any]) -> dict[str, Any]:
        clash = _RESERVED_KEYS & set(record)
        if clash:
            raise ValueError(f"keys {sorted(clash)} are set by the ledger")
        self._scan_locked()  # brings _tail to the current end of file and validates it
        rec = {**record, "ts": utc_now_iso(), "prev": self._tail}
        line = _encode(rec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as fh:
            fh.write(line + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._scan_locked()
        return rec

    def _read_new_locked(self) -> list[dict[str, Any]]:
        """Records appended since this instance last read, own appends included; caller holds the lock."""
        self._scan_locked()
        out, self._pending = self._pending, []
        return out

    def _scan_locked(self) -> None:
        """Validate and buffer every line after the current offset."""
        if not self.path.exists():
            if self._offset:
                raise LedgerCorrupt(f"{self.path} disappeared")
            return
        with self.path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size < self._offset:
                raise LedgerCorrupt(f"{self.path} shrank from {self._offset} to {size} bytes")
            fh.seek(self._offset)
            data = fh.read(size - self._offset)
        if data and not data.endswith(b"\n"):
            raise LedgerCorrupt(f"{self.path} ends with a partial line")
        for raw in data.split(b"\n")[:-1]:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LedgerCorrupt(f"{self.path}: invalid JSON line: {exc}") from None
            if not isinstance(rec, dict) or rec.get("prev") != self._tail:
                raise LedgerCorrupt(f"{self.path}: hash chain broken at byte {self._offset}")
            self._tail = _hash(raw)
            self._offset += len(raw) + 1
            self._pending.append(rec)

    def read_new(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_new_locked()

    def records(self) -> list[dict[str, Any]]:
        """All records, verifying the whole chain from the first line."""
        return JsonlLedger(self.path).read_new()

    def verify(self) -> int:
        """Number of records; raises LedgerCorrupt if the chain is broken."""
        return len(self.records())


# --- spend ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reservation:
    rid: str
    chunk: str
    est_usd: float


@dataclass(frozen=True)
class SpendTotals:
    total_usd: float  # recorded spend, all chunks
    chunk_usd: float  # recorded spend, this chunk
    held_total_usd: float  # unspent part of open reservations, all chunks
    held_chunk_usd: float
    by_chunk: dict[str, float]
    total_cap_usd: float
    chunk_cap_usd: float


def _usd(x: float) -> float:
    v = float(x)
    if not math.isfinite(v) or v < 0:
        raise ValueError(f"USD amount must be finite and >= 0, got {x!r}")
    return v


class SpendLedger:
    """OpenRouter spend with a hard total cap and per-chunk caps (PREREG §13, CLAUDE.md C12).

    Protocol: ``r = reserve(est)`` before a call (or a batch), ``record(actual, meta, reservation=r)``
    after it. A reservation holds budget until it is closed by a final ``record`` or ``release``;
    holds are written to the ledger, so concurrent processes see each other's reservations.
    """

    def __init__(
        self, chunk_id: str, *, path: Path | None = None, budget: BudgetConfig | None = None
    ) -> None:
        self.chunk_id = chunk_id
        self.budget = load_project().budget if budget is None else budget
        self._ledger = JsonlLedger(LEDGERS / SPEND if path is None else path)
        self._spent: defaultdict[str, float] = defaultdict(float)
        self._open: dict[str, tuple[str, float]] = {}
        self._spent_by_rid: defaultdict[str, float] = defaultdict(float)

    @property
    def path(self) -> Path:
        return self._ledger.path

    def _sync_locked(self) -> None:
        for rec in self._ledger._read_new_locked():
            event, rid = rec.get("event"), rec.get("rid")
            if event == "reserve":
                self._open[str(rid)] = (str(rec["chunk"]), float(rec["usd"]))
            elif event == "spend":
                self._spent[str(rec["chunk"])] += float(rec["usd"])
                if rid is not None:
                    self._spent_by_rid[str(rid)] += float(rec["usd"])
                    if rec.get("close"):
                        self._open.pop(str(rid), None)
            elif event == "release":
                self._open.pop(str(rid), None)
            else:
                raise LedgerCorrupt(f"{self.path}: unknown spend event {event!r}")

    def _totals_locked(self) -> SpendTotals:
        held: defaultdict[str, float] = defaultdict(float)
        for rid, (chunk, est) in self._open.items():
            held[chunk] += max(0.0, est - self._spent_by_rid.get(rid, 0.0))
        return SpendTotals(
            total_usd=sum(self._spent.values()),
            chunk_usd=self._spent.get(self.chunk_id, 0.0),
            held_total_usd=sum(held.values()),
            held_chunk_usd=held.get(self.chunk_id, 0.0),
            by_chunk=dict(self._spent),
            total_cap_usd=self.budget.total_usd,
            chunk_cap_usd=self.budget.chunk_cap(self.chunk_id),
        )

    def totals(self) -> SpendTotals:
        with self._ledger._lock:
            self._sync_locked()
            return self._totals_locked()

    def reserve(self, est_usd: float, *, note: str = "") -> Reservation:
        """Hold ``est_usd``; raise BudgetExceeded if spent + held + est would cross either cap."""
        est = _usd(est_usd)
        with self._ledger._lock:
            self._sync_locked()
            t = self._totals_locked()
            total_after = t.total_usd + t.held_total_usd + est
            chunk_after = t.chunk_usd + t.held_chunk_usd + est
            if total_after > t.total_cap_usd + _EPS:
                raise BudgetExceeded(
                    f"total cap: spent {t.total_usd:.6f} + held {t.held_total_usd:.6f} + est {est:.6f} "
                    f"> ${t.total_cap_usd:.2f}"
                )
            if chunk_after > t.chunk_cap_usd + _EPS:
                raise BudgetExceeded(
                    f"{self.chunk_id} cap: spent {t.chunk_usd:.6f} + held {t.held_chunk_usd:.6f} + "
                    f"est {est:.6f} > ${t.chunk_cap_usd:.2f}"
                )
            rid = uuid.uuid4().hex
            self._ledger._append_locked(
                {"event": "reserve", "chunk": self.chunk_id, "rid": rid, "usd": est, "note": note}
            )
            self._sync_locked()
        return Reservation(rid=rid, chunk=self.chunk_id, est_usd=est)

    def record(
        self,
        actual_usd: float,
        meta: Mapping[str, Any] | None = None,
        *,
        reservation: Reservation | None = None,
        final: bool = True,
    ) -> None:
        """Append an actual spend. The line is always written (money already spent is recorded);
        afterwards a spend without a reservation, or one that leaves a cap exceeded, raises."""
        usd = _usd(actual_usd)
        if reservation is not None and reservation.chunk != self.chunk_id:
            raise LedgerError(f"reservation of {reservation.chunk} used by {self.chunk_id}")
        unreserved = reservation is None and usd > 0
        with self._ledger._lock:
            self._ledger._append_locked(
                {
                    "event": "spend",
                    "chunk": self.chunk_id,
                    "usd": usd,
                    "rid": None if reservation is None else reservation.rid,
                    "close": bool(final and reservation is not None),
                    "unreserved": unreserved,
                    "meta": dict(meta or {}),
                    "git_sha": git_sha_cached(),
                }
            )
            self._sync_locked()
            t = self._totals_locked()
        if unreserved:
            raise LedgerError(f"{self.chunk_id}: spend of ${usd:.6f} recorded without a reservation")
        if t.total_usd > t.total_cap_usd + _EPS or t.chunk_usd > t.chunk_cap_usd + _EPS:
            raise BudgetExceeded(
                f"recorded spend over cap: total {t.total_usd:.6f}/{t.total_cap_usd}, "
                f"{self.chunk_id} {t.chunk_usd:.6f}/{t.chunk_cap_usd}"
            )

    def release(self, reservation: Reservation) -> None:
        """Close a reservation without (further) spend, e.g. after a cache hit or a failed batch."""
        if reservation.chunk != self.chunk_id:
            raise LedgerError(f"reservation of {reservation.chunk} released by {self.chunk_id}")
        with self._ledger._lock:
            self._ledger._append_locked({"event": "release", "chunk": self.chunk_id, "rid": reservation.rid})
            self._sync_locked()

    def reconcile(self, cache_costs: Iterable[float]) -> float:
        """Recorded spend of this chunk minus the sum of ``usage.cost`` in the cache (GAC4: ~0)."""
        return self.totals().chunk_usd - math.fsum(float(c) for c in cache_costs)


# --- trials ---------------------------------------------------------------------------------------


class TrialRecord(BaseModel):
    """One evaluated variant (CLAUDE.md B10); the deflated Sharpe uses the count of these."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    chunk: str = Field(pattern=r"^NA-\d{2}[a-z]?$")  # NA-13b: an operator chunk between two PRD chunks
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    params_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: SplitName | Literal["synthetic"]
    metric: str = Field(min_length=1)
    value: float | None


def params_hash(params: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON of a parameter mapping (for TrialRecord.params_hash)."""
    return _hash(_encode(params))


class TrialLedger:
    def __init__(self, path: Path | None = None) -> None:
        self._ledger = JsonlLedger(LEDGERS / TRIALS if path is None else path)

    def log(self, record: TrialRecord | Mapping[str, Any]) -> dict[str, Any]:
        rec = record if isinstance(record, TrialRecord) else TrialRecord.model_validate(record)
        return self._ledger.append(rec.model_dump())

    def records(self) -> list[dict[str, Any]]:
        return self._ledger.records()

    def count(self, *, kind: str | None = None, chunk: str | None = None) -> int:
        return sum(
            1
            for r in self.records()
            if (kind is None or r["kind"] == kind) and (chunk is None or r["chunk"] == chunk)
        )


# --- test-period access (written by newsaction.lock) ----------------------------------------------


class AccessLedger:
    """``ledgers/test_access.jsonl``: every lock.sealed_path call, allowed or refused (PREREG §4.3)."""

    def __init__(self, path: Path | None = None) -> None:
        self._ledger = JsonlLedger(LEDGERS / TEST_ACCESS if path is None else path)

    @property
    def path(self) -> Path:
        return self._ledger.path

    def log(
        self, *, caller: str, name: str, purpose: str, allowed: bool, reason: str, git_sha: str
    ) -> dict[str, Any]:
        return self._ledger.append(
            {
                "caller": caller,
                "name": name,
                "purpose": purpose,
                "allowed": allowed,
                "reason": reason,
                "git_sha": git_sha,
            }
        )

    def entries(self) -> list[dict[str, Any]]:
        return self._ledger.records()


# --- FMP requests ---------------------------------------------------------------------------------


class FmpLedger:
    """``ledgers/fmp_requests.jsonl``: a ``request`` line for each FMP request, reserved before it is sent,
    and a ``response`` line with its status and row count once it returns (NA-10). Only ``request`` lines
    count toward the cap, so a request that never returned still counts."""

    def __init__(self, path: Path | None = None, cap: int | None = None) -> None:
        self._ledger = JsonlLedger(LEDGERS / FMP_REQUESTS if path is None else path)
        self.cap = load_project().fmp_request_cap if cap is None else cap
        self._count = 0

    @property
    def path(self) -> Path:
        return self._ledger.path

    def _sync_locked(self) -> None:
        for rec in self._ledger._read_new_locked():
            event = rec.get("event")
            if event == "request":
                self._count += 1
            elif event != "response":
                raise LedgerCorrupt(f"{self.path}: unknown FMP event {event!r}")

    def count(self) -> int:
        with self._ledger._lock:
            self._sync_locked()
            return self._count

    def remaining(self) -> int:
        return self.cap - self.count()

    def reserve(self, meta: Mapping[str, Any] | None = None) -> int:
        """Log one request before sending it; raise FmpCapExceeded if it would be number cap + 1."""
        with self._ledger._lock:
            self._sync_locked()
            if self._count + 1 > self.cap:
                raise FmpCapExceeded(f"FMP request cap {self.cap} reached ({self._count} used)")
            self._ledger._append_locked({"event": "request", "n": self._count + 1, "meta": dict(meta or {})})
            self._sync_locked()
            return self._count

    def record_response(
        self,
        n: int,
        *,
        status: int | None,
        rows: int | None,
        nbytes: int | None = None,
        error: str | None = None,
    ) -> None:
        """Log the outcome of request ``n`` (``status`` None: no HTTP answer, e.g. a timeout)."""
        with self._ledger._lock:
            self._ledger._append_locked(
                {"event": "response", "n": n, "status": status, "rows": rows, "bytes": nbytes, "error": error}
            )
            self._sync_locked()

    def records(self) -> list[dict[str, Any]]:
        return self._ledger.records()


# --- CLI ------------------------------------------------------------------------------------------


def check_all(ledgers_dir: Path = LEDGERS) -> dict[str, int]:
    """Verify the chain of every ledger; raises LedgerCorrupt on the first broken one."""
    return {p.name: JsonlLedger(p).verify() for p in sorted(ledgers_dir.glob("*.jsonl"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m newsaction.ledger")
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--dir", type=Path, default=LEDGERS)
    args = parser.parse_args(argv)
    missing = [name for name in LEDGER_FILES if not (args.dir / name).exists()]
    if missing:
        print(f"ledgers: missing {missing} in {args.dir}", file=sys.stderr)
        return 1
    try:
        counts = check_all(args.dir)
    except LedgerCorrupt as exc:
        print(f"ledgers: CORRUPT: {exc}", file=sys.stderr)
        return 1
    print("ledgers: OK " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
