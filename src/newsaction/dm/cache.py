"""The decision cache (PRD NA-05 S2): ``cache/decisions.sqlite`` (gitignored).

**Key.** sha256 of the canonical JSON (sorted keys, compact, UTF-8) of
{model, state, questions, provider, params, repeat_idx}, where ``state`` is the state object (or string) as
sent, ``questions`` the ordered list [[id, [type, instructions, criteria]], …] (so the order of questions
and options counts), ``provider`` the provider object, ``params`` the extra body fields of the run (for a
local model, its checkpoint settings) and ``repeat_idx`` the repeat number. Changing any character of any
of them gives another key. The session id is not part of the key: it is observability metadata that never
reaches the provider.

**Tables.**
- ``responses``: one row per key, written once: the request parts and their hashes, the raw response JSON,
  the model build and provider that answered, usage, cost and its source, latency, the time, the chunk that
  paid for it, the state's provenance (``meta``) and the strict-parse verdict. Every HTTP 200 is stored, valid
  or not, so a billed answer is never bought twice.
- ``attempts``: every network attempt (status, latency, rate-limit headers, error), successful or not.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from newsaction.dm.schemas import DecisionRequest
from newsaction.provenance import utc_now_iso
from newsaction.states.questions import canonical_json

SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    state_sha256 TEXT NOT NULL,
    questions_sha256 TEXT NOT NULL,
    provider_json TEXT NOT NULL,
    params_json TEXT NOT NULL,
    repeat_idx INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    model_build TEXT,
    provider TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost REAL NOT NULL,
    cost_source TEXT NOT NULL,
    latency_ms REAL,
    created_at TEXT NOT NULL,
    chunk TEXT NOT NULL,
    tag TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    valid INTEGER NOT NULL,
    problems_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    model TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status INTEGER,
    error TEXT,
    latency_ms REAL,
    headers_json TEXT NOT NULL,
    concurrency INTEGER,
    created_at TEXT NOT NULL,
    chunk TEXT NOT NULL,
    tag TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS responses_chunk ON responses (chunk);
CREATE INDEX IF NOT EXISTS attempts_key ON attempts (key);
"""


class CacheError(Exception):
    """The cache is inconsistent (e.g. a second, different row for a key)."""


def key_payload(
    model: str, request: DecisionRequest, params: Mapping[str, Any], repeat_idx: int
) -> dict[str, Any]:
    return {
        "model": model,
        "state": request.state,
        "questions": request.questions_ordered(),
        "provider": request.provider.model_dump(),
        "params": dict(params),
        "repeat_idx": int(repeat_idx),
    }


def request_key(model: str, request: DecisionRequest, params: Mapping[str, Any], repeat_idx: int) -> str:
    """sha256 of the canonical JSON of the key payload (module docstring)."""
    payload = key_payload(model, request, params, repeat_idx)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedRow:
    key: str
    model: str
    state_sha256: str
    questions_sha256: str
    provider_json: str
    params_json: str
    repeat_idx: int
    request_json: str
    response_json: str
    model_build: str | None
    provider: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost: float
    cost_source: str  # "usage" (the response's usage.cost), "computed" (price × tokens) or "local"
    latency_ms: float | None
    created_at: str
    chunk: str
    tag: str
    meta_json: str
    valid: bool
    problems_json: str

    @property
    def response(self) -> Any:
        return json.loads(self.response_json)

    @property
    def meta(self) -> dict[str, Any]:
        out: dict[str, Any] = json.loads(self.meta_json)
        return out

    @property
    def problems(self) -> list[str]:
        out: list[str] = json.loads(self.problems_json)
        return out


_COLUMNS: Final = tuple(CachedRow.__dataclass_fields__)


class DecisionCache:
    """sqlite store of decision responses and network attempts (module docstring)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, timeout=60.0, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=60000")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> DecisionCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Connection]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self._db
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._db.execute("COMMIT")

    def get(self, key: str) -> CachedRow | None:
        cur = self._db.execute(f"SELECT {', '.join(_COLUMNS)} FROM responses WHERE key = ?", (key,))
        rec = cur.fetchone()
        return None if rec is None else CachedRow(*rec)

    def put(self, row: CachedRow) -> None:
        """Insert a row; a key is written once (a second, different row is an error)."""
        with self._txn() as db:
            cur = db.execute("SELECT response_json FROM responses WHERE key = ?", (row.key,))
            old = cur.fetchone()
            if old is not None:
                if old[0] != row.response_json:
                    raise CacheError(f"key {row.key[:16]} already holds a different response")
                return
            marks = ", ".join("?" for _ in _COLUMNS)
            db.execute(
                f"INSERT INTO responses ({', '.join(_COLUMNS)}) VALUES ({marks})",
                tuple(getattr(row, c) for c in _COLUMNS),
            )

    def log_attempt(
        self,
        *,
        key: str,
        model: str,
        attempt: int,
        status: int | None,
        error: str | None,
        latency_ms: float | None,
        headers: Mapping[str, str],
        concurrency: int | None,
        chunk: str,
        tag: str,
    ) -> None:
        with self._txn() as db:
            db.execute(
                "INSERT INTO attempts (key, model, attempt, status, error, latency_ms, headers_json, "
                "concurrency, created_at, chunk, tag) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    model,
                    attempt,
                    status,
                    error,
                    latency_ms,
                    json.dumps(dict(headers), sort_keys=True),
                    concurrency,
                    utc_now_iso(),
                    chunk,
                    tag,
                ),
            )

    def rows(self, *, chunk: str | None = None, keys: Sequence[str] | None = None) -> list[CachedRow]:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM responses"
        args: list[Any] = []
        if chunk is not None:
            sql += " WHERE chunk = ?"
            args.append(chunk)
        out = [CachedRow(*r) for r in self._db.execute(sql + " ORDER BY created_at, key", args)]
        if keys is not None:
            wanted = set(keys)
            out = [r for r in out if r.key in wanted]
        return out

    def costs(self, chunk: str) -> list[float]:
        """``usage.cost`` (or its computed stand-in) of every response this chunk paid for (GAC4)."""
        return [float(c) for (c,) in self._db.execute("SELECT cost FROM responses WHERE chunk = ?", (chunk,))]

    def frame(self, table: str = "responses") -> pd.DataFrame:
        if table not in {"responses", "attempts"}:
            raise CacheError(f"unknown table {table!r}")
        return pd.read_sql_query(f"SELECT * FROM {table}", self._db)
