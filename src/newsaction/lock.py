"""Blinding lock for the test period (PREREG §4.3–4.4, CLAUDE.md B8).

2026 prices live in ``work/snapshot/sealed/``. The only sanctioned way to obtain a path in there
is ``sealed_path(name, purpose)``:

- ``"reactions"`` (2026 observed reactions for Call B states) requires the NA-11 freeze record;
- ``"targets"`` (2026 outcomes) requires the freeze record, a freeze-hash match and ``NA_UNBLIND=1``.

Every call, allowed or refused, appends {ts, caller, name, purpose, allowed, reason, git_sha} to
``ledgers/test_access.jsonl``. The lock is procedural: Python cannot stop code from opening a file
by hand. Its strength is this ledger plus tests/test_blinding.py (no 2026 date literals and no use
of the sealed directory anywhere in ``src/`` outside this module) and the verifiers' greps.

Freeze hash. sha256 over FREEZE_FILES, each file hashed by content ("ABSENT" if missing). For
docs/PREREG.md the hash covers everything *before* the "Deviations log" heading; the log itself is
append-only after the freeze (CLAUDE.md B11) and is checked as such: the bytes recorded at the
freeze must remain an unchanged prefix of the current log. (Logged as a deviation in PREREG §15.)
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, get_args

import pandas as pd

from newsaction import io
from newsaction.config import load_frozen
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import git_sha, utc_now_iso

Purpose = Literal["reactions", "targets"]
PURPOSES: Final[frozenset[str]] = frozenset(get_args(Purpose))

FREEZE_FILES: Final[tuple[str, ...]] = (
    "docs/PREREG.md",
    "configs/*.yaml",
    "src/newsaction/panel/targets.py",
    "src/newsaction/panel/reactions.py",
    "src/newsaction/analysis/spec.py",
)
FREEZE_RECORD: Final = "artifacts/NA-11/freeze.json"
PREREG: Final = "docs/PREREG.md"
PREREG_PROTECTED_KEY: Final = "docs/PREREG.md#before-deviations-log"
ABSENT: Final = "ABSENT"
UNBLIND_ENV: Final = "NA_UNBLIND"

_DEVIATIONS_HEADING: Final = re.compile(rb"^##\s+\d+\.\s+Deviations log\s*$", re.MULTILINE)
_NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")
_FROZEN_FLAG: Final = re.compile(r"^frozen:\s*false\b.*$", re.MULTILINE)


class LockError(Exception):
    """Access to sealed test-period data refused, or a freeze-protocol violation."""


@dataclass(frozen=True)
class FreezeHash:
    digest: str
    files: dict[str, str]
    deviations_log_sha256: str
    deviations_log_bytes: int


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_prereg(text: bytes) -> tuple[bytes, bytes]:
    """(protected part, deviations log). Without the heading the whole file is protected."""
    m = _DEVIATIONS_HEADING.search(text)
    return (text, b"") if m is None else (text[: m.start()], text[m.start() :])


def compute_freeze_hash(layout: Layout | None = None) -> FreezeHash:
    lay = resolve_layout(layout)
    files: dict[str, str] = {}
    log = b""
    for pattern in FREEZE_FILES:
        matches = sorted(lay.root.glob(pattern)) if "*" in pattern else [lay.root / pattern]
        if not matches:
            files[pattern] = ABSENT
        for path in matches:
            rel = path.relative_to(lay.root).as_posix()
            if not path.is_file():
                files[rel] = ABSENT
            elif rel == PREREG:
                protected, log = _split_prereg(path.read_bytes())
                files[PREREG_PROTECTED_KEY] = _sha(protected)
            else:
                files[rel] = _sha(path.read_bytes())
    digest = _sha("".join(f"{k}\t{v}\n" for k, v in sorted(files.items())).encode())
    return FreezeHash(digest, files, _sha(log), len(log))


def _record_path(lay: Layout) -> Path:
    return lay.root / FREEZE_RECORD


def _load_record(lay: Layout) -> dict[str, Any] | None:
    try:
        rec = json.loads(_record_path(lay).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ok = (
        isinstance(rec, dict)
        and isinstance(rec.get("hash"), str)
        and re.fullmatch(r"[0-9a-f]{64}", rec["hash"]) is not None
        and isinstance(rec.get("files"), dict)
        and isinstance(rec.get("deviations_log"), dict)
    )
    return rec if ok else None


def freeze(note: str, *, layout: Layout | None = None) -> dict[str, Any]:
    """NA-11 only: set ``frozen: true`` in configs/frozen.yaml, hash FREEZE_FILES, write the record.

    Refuses unless configs/frozen.yaml has ``frozen_requested: true`` and no record exists yet.
    """
    lay = resolve_layout(layout)
    frozen_yaml = lay.configs / "frozen.yaml"
    if not load_frozen(frozen_yaml).frozen_requested:
        raise LockError("freeze refused: configs/frozen.yaml does not have frozen_requested: true")
    if _record_path(lay).exists():
        raise LockError(f"freeze refused: {FREEZE_RECORD} already exists (the freeze is one-way)")
    text = frozen_yaml.read_text(encoding="utf-8")
    new_text, n = _FROZEN_FLAG.subn("frozen: true             # set by lock.freeze()", text)
    if n != 1:
        raise LockError("freeze refused: configs/frozen.yaml must contain exactly one 'frozen: false' line")
    io.atomic_write_bytes(frozen_yaml, new_text.encode("utf-8"))
    h = compute_freeze_hash(lay)
    record = {
        "version": 1,
        "hash": h.digest,
        "files": h.files,
        "deviations_log": {"sha256": h.deviations_log_sha256, "bytes": h.deviations_log_bytes},
        "freeze_files": list(FREEZE_FILES),
        "git_sha": git_sha(lay.root),
        "ts": utc_now_iso(),
        "note": note,
    }
    path = _record_path(lay)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:  # exclusive create: never overwrite a freeze
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return record


def is_frozen(layout: Layout | None = None) -> bool:
    """True iff a well-formed freeze record exists (artifacts/NA-11/freeze.json)."""
    return _load_record(resolve_layout(layout)) is not None


def require_frozen(layout: Layout | None = None) -> None:
    if not is_frozen(layout):
        raise LockError("not frozen: artifacts/NA-11/freeze.json is missing or malformed")


def require_unblind(layout: Layout | None = None) -> None:
    """Frozen AND the current freeze hash equals the recorded one AND NA_UNBLIND=1."""
    lay = resolve_layout(layout)
    require_frozen(lay)
    rec = _load_record(lay)
    if rec is None:  # pragma: no cover - require_frozen already checked
        raise LockError("freeze record unreadable")
    now = compute_freeze_hash(lay)
    if now.digest != rec["hash"]:
        changed = sorted(
            k for k in set(now.files) | set(rec["files"]) if now.files.get(k) != rec["files"].get(k)
        )
        raise LockError(f"freeze hash mismatch: changed since the freeze: {changed}")
    _check_log_prefix(lay, rec)
    if os.environ.get(UNBLIND_ENV) != "1":
        raise LockError(f"unblinding requires {UNBLIND_ENV}=1")


def _check_log_prefix(lay: Layout, rec: dict[str, Any]) -> None:
    prereg = lay.root / PREREG
    _, log = _split_prereg(prereg.read_bytes()) if prereg.is_file() else (b"", b"")
    n = int(rec["deviations_log"]["bytes"])
    if _sha(log[:n]) != rec["deviations_log"]["sha256"]:
        raise LockError("PREREG Deviations log was edited, not appended to, after the freeze")


def _caller() -> str:
    here = Path(__file__).resolve()
    for frame in inspect.stack(context=0)[1:]:
        fname = Path(frame.filename)
        if fname.name and fname.resolve() != here:
            try:
                shown = fname.resolve().relative_to(Path.cwd()).as_posix()
            except ValueError:
                shown = frame.filename
            return f"{shown}:{frame.function}:{frame.lineno}"
    return "unknown"


def sealed_path(name: str, purpose: Purpose, *, layout: Layout | None = None) -> Path:
    """Path of ``work/snapshot/sealed/<name>.parquet`` if ``purpose`` is currently allowed.

    Every call is appended to the access ledger before the decision takes effect.
    """
    lay = resolve_layout(layout)
    allowed, reason = False, ""
    try:
        if purpose not in PURPOSES:
            raise LockError(f"unknown purpose {purpose!r}; expected one of {sorted(PURPOSES)}")
        if not _NAME.fullmatch(name):
            raise LockError(f"invalid sealed name {name!r}")
        if purpose == "reactions":
            require_frozen(lay)
        else:
            require_unblind(lay)
        allowed, reason = True, "ok"
    except LockError as exc:
        reason = str(exc)
        raise
    finally:
        AccessLedger(lay.ledgers / TEST_ACCESS).log(
            caller=_caller(),
            name=name,
            purpose=str(purpose),
            allowed=allowed,
            reason=reason,
            git_sha=git_sha(lay.root),
        )
    return lay.sealed / f"{name}.parquet"


def read_sealed(
    name: str, purpose: Purpose, *, columns: list[str] | None = None, layout: Layout | None = None
) -> pd.DataFrame:
    """Read a sealed parquet through the lock (logged), verifying its manifest hash."""
    path = sealed_path(name, purpose, layout=layout)
    return io._read_verified(path, columns=columns, layout=layout)


def write_sealed(
    df: pd.DataFrame, name: str, *, producer: str, description: str, layout: Layout | None = None
) -> dict[str, Any]:
    """Write test-period data into the sealed directory (allowed before the freeze; never reads).

    Logged in the access ledger with purpose "write".
    """
    lay = resolve_layout(layout)
    if not _NAME.fullmatch(name):
        raise LockError(f"invalid sealed name {name!r}")
    rel = (lay.sealed / f"{name}.parquet").relative_to(lay.work).as_posix()
    AccessLedger(lay.ledgers / TEST_ACCESS).log(
        caller=_caller(), name=name, purpose="write", allowed=True, reason="write", git_sha=git_sha(lay.root)
    )
    return io.write_parquet(df, rel, producer=producer, description=description, layout=lay)
