"""Hashed artifact I/O and the manifest (CLAUDE.md D19, F20; PRD GAC2, GAC5).

- Derived files live under ``work/`` and are written with ``write_parquet`` (or registered with
  ``register_file`` when another process wrote them). Each gets a ``work/MANIFEST.json`` entry:
  sha256, bytes, rows, columns, producer, description, git sha, time.
- ``Data/`` is read-only. Readers go through ``read_data_parquet`` / ``read_data_pickle`` /
  ``copy_data_file``, which fingerprint the input (sha256, size, mtime) in ``MANIFEST["inputs"]`` the
  first time it is read and refuse it later if its size or mtime changed.
- ``read_parquet`` re-hashes before reading and refuses the lock-protected directory (those files
  are read only through ``newsaction.lock``).
- ``manifest_check`` (``make manifest``) re-hashes every artifact, checks inputs, flags unregistered
  parquet files and compares each sha256 with ``docs/DATA_CONTRACT.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final

import pandas as pd
import pyarrow.parquet as pq
from filelock import FileLock

from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import git_sha_cached, utc_now_iso

MANIFEST_VERSION: Final = 1
DATA_CONTRACT: Final = "DATA_CONTRACT.md"
# Committed outputs that may be registered: the chunks' artifacts and the manuscript's files (NA-16).
COMMITTED_ROOTS: Final = ("artifacts", "paper", "arxiv")
_CHUNK: Final = 8 * 1024 * 1024
_CONTRACT_HEADING: Final = re.compile(r"^###\s+`([^`]+)`")
_CONTRACT_SHA: Final = re.compile(r"\*\*sha256:\*\*\s*`([0-9a-f]{64})`")


class ManifestError(Exception):
    """An artifact is unregistered, changed, or read through the wrong route."""


class InputChanged(ManifestError):
    """A Data/ input differs from the fingerprint recorded when it was first read."""


# --- primitives -----------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _tmp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temporary file in the same directory, fsync, then rename over ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _empty_manifest() -> dict[str, Any]:
    return {"version": MANIFEST_VERSION, "artifacts": {}, "inputs": {}}


def load_manifest(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if not lay.manifest.exists():
        return _empty_manifest()
    m = json.loads(lay.manifest.read_text(encoding="utf-8"))
    if not isinstance(m, dict) or m.get("version") != MANIFEST_VERSION:
        raise ManifestError(f"{lay.manifest}: unsupported manifest format")
    return m


@contextmanager
def _manifest_txn(lay: Layout) -> Iterator[dict[str, Any]]:
    lay.work.mkdir(parents=True, exist_ok=True)
    with FileLock(f"{lay.manifest}.lock"):
        m = load_manifest(lay)
        yield m
        atomic_write_bytes(lay.manifest, (json.dumps(m, indent=2, sort_keys=True) + "\n").encode())


def _work_path(lay: Layout, relpath: str | PurePosixPath) -> Path:
    rel = PurePosixPath(relpath)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ManifestError(f"relpath must be relative to work/ without '..': {relpath!r}")
    return lay.work.joinpath(*rel.parts)


def _parquet_schema(path: Path) -> tuple[int, list[dict[str, str]]]:
    meta = pq.read_metadata(path)
    schema = meta.schema.to_arrow_schema()
    return int(meta.num_rows), [{"name": f.name, "type": str(f.type)} for f in schema]


def _register(
    lay: Layout, path: Path, *, producer: str, description: str, inspect_parquet: bool = True
) -> dict[str, Any]:
    if not producer or not description:
        raise ManifestError("producer and description are required")
    rows: int | None = None
    columns: list[dict[str, str]] | None = None
    if inspect_parquet and path.suffix == ".parquet":
        rows, columns = _parquet_schema(path)
    entry = {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": rows,
        "columns": columns,
        "producer": producer,
        "description": description,
        "git_sha": git_sha_cached(lay.root),
        "written_at": utc_now_iso(),
    }
    with _manifest_txn(lay) as m:
        m["artifacts"][lay.rel(path)] = entry
    return entry


# --- derived artifacts (work/) --------------------------------------------------------------------


def write_parquet(
    df: pd.DataFrame,
    relpath: str,
    *,
    producer: str,
    description: str,
    layout: Layout | None = None,
) -> dict[str, Any]:
    """Write ``df`` to ``work/<relpath>`` (atomically) and upsert its manifest entry.

    The frame must have a default RangeIndex (reset meaningful indexes into columns first) and
    unique string column names.
    """
    lay = resolve_layout(layout)
    path = _work_path(lay, relpath)
    if path.suffix != ".parquet":
        raise ManifestError(f"write_parquet needs a .parquet path, got {relpath!r}")
    if not (isinstance(df.index, pd.RangeIndex) and df.index.start == 0 and df.index.step == 1):
        raise ManifestError("write_parquet needs a default RangeIndex; reset_index() first")
    names = list(df.columns)
    if not all(isinstance(c, str) for c in names) or len(set(names)) != len(names):
        raise ManifestError("column names must be unique strings")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    try:
        df.to_parquet(tmp, index=False, engine="pyarrow")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return _register(lay, path, producer=producer, description=description)


def register_file(
    relpath: str,
    *,
    producer: str,
    description: str,
    inspect_parquet: bool = True,
    layout: Layout | None = None,
) -> dict[str, Any]:
    """Register a file under work/ that was written by another process (e.g. the ATOM-venv export)."""
    lay = resolve_layout(layout)
    path = _work_path(lay, relpath)
    if not path.is_file():
        raise ManifestError(f"cannot register missing file {path}")
    return _register(lay, path, producer=producer, description=description, inspect_parquet=inspect_parquet)


def register_artifact(
    relpath: str, *, producer: str, description: str, layout: Layout | None = None
) -> dict[str, Any]:
    """Register a committed output under ``artifacts/`` (e.g. a parquet a later chunk reads), or one of the
    manuscript's generated files under ``paper/`` or ``arxiv/`` (NA-16), in the manifest, so ``make manifest``
    re-hashes it and checks its docs/DATA_CONTRACT.md entry like a work/ file."""
    lay = resolve_layout(layout)
    rel = PurePosixPath(relpath)
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 2 or rel.parts[0] not in COMMITTED_ROOTS:
        raise ManifestError(f"relpath must be under artifacts/, paper/ or arxiv/ without '..': {relpath!r}")
    path = lay.root.joinpath(*rel.parts)
    if not path.is_file():
        raise ManifestError(f"cannot register missing file {path}")
    return _register(lay, path, producer=producer, description=description)


def _read_verified(
    path: Path, *, columns: list[str] | None = None, verify: bool = True, layout: Layout | None = None
) -> pd.DataFrame:
    """Read a registered parquet after checking its sha256. Lock-protected paths: newsaction.lock only."""
    lay = resolve_layout(layout)
    entry = load_manifest(lay)["artifacts"].get(lay.rel(path))
    if entry is None:
        raise ManifestError(f"{lay.rel(path)} is not registered in work/MANIFEST.json")
    if verify and sha256_file(path) != entry["sha256"]:
        raise ManifestError(f"{lay.rel(path)}: sha256 differs from the manifest")
    return pd.read_parquet(path, columns=columns)


def read_parquet(
    relpath: str, *, verify: bool = True, columns: list[str] | None = None, layout: Layout | None = None
) -> pd.DataFrame:
    """Read ``work/<relpath>``; with ``verify`` the file is re-hashed against the manifest first."""
    lay = resolve_layout(layout)
    path = _work_path(lay, relpath)
    if lay.is_locked(path):
        raise ManifestError(f"{relpath} is lock-protected; read it through newsaction.lock")
    return _read_verified(path, columns=columns, verify=verify, layout=lay)


# --- raw inputs (Data/, read-only) ----------------------------------------------------------------


def _data_path(lay: Layout, path: str | Path) -> Path:
    p = Path(path)
    full = p if p.is_absolute() else lay.data / p
    if not full.resolve().is_relative_to(lay.data.resolve()):
        raise ManifestError(f"{path} is not inside Data/")
    if not full.is_file():
        raise ManifestError(f"input {full} not found")
    return full


def record_input(path: str | Path, *, layout: Layout | None = None) -> dict[str, Any]:
    """Fingerprint a Data/ file the first time it is read; refuse it if it changed since."""
    lay = resolve_layout(layout)
    full = _data_path(lay, path)
    key = lay.rel(full)
    st = full.stat()
    with _manifest_txn(lay) as m:
        known = m["inputs"].get(key)
        if known is not None:
            if known["size"] != st.st_size or known["mtime_ns"] != st.st_mtime_ns:
                raise InputChanged(f"{key} changed since it was first read ({known['first_read_at']})")
            return dict(known)
        entry = {
            "sha256": sha256_file(full),
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
            "mtime_ns": st.st_mtime_ns,
            "first_read_at": utc_now_iso(),
            "first_read_git_sha": git_sha_cached(lay.root),
        }
        m["inputs"][key] = entry
        return dict(entry)


def read_data_parquet(
    path: str | Path, *, columns: list[str] | None = None, layout: Layout | None = None
) -> pd.DataFrame:
    lay = resolve_layout(layout)
    record_input(path, layout=lay)
    return pd.read_parquet(_data_path(lay, path), columns=columns)


def read_data_pickle(path: str | Path, *, layout: Layout | None = None) -> Any:
    """Load a trusted Data/ pickle (needs pandas >= 3 for the market pickles)."""
    lay = resolve_layout(layout)
    record_input(path, layout=lay)
    return pd.read_pickle(_data_path(lay, path))  # local, trusted team data


def copy_data_file(
    path: str | Path,
    relpath: str,
    *,
    producer: str,
    description: str,
    layout: Layout | None = None,
) -> dict[str, Any]:
    """Byte-for-byte copy of a Data/ file to ``work/<relpath>``, registered as input and artifact."""
    lay = resolve_layout(layout)
    src = _data_path(lay, path)
    expected = record_input(src, layout=lay)["sha256"]
    dest = _work_path(lay, relpath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(dest)
    try:
        shutil.copyfile(src, tmp)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    entry = _register(lay, dest, producer=producer, description=description)
    if entry["sha256"] != expected:
        raise ManifestError(f"copy of {src} does not match its input hash")
    return entry


# --- checks (make manifest) -----------------------------------------------------------------------


@dataclass
class CheckReport:
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def contract_shas(path: Path) -> dict[str, str]:
    """``### `path` `` sections of docs/DATA_CONTRACT.md -> the sha256 written in that section."""
    out: dict[str, str] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            m = _CONTRACT_HEADING.match(line)
            current = m.group(1) if m else None
            continue
        if current is not None and current not in out:
            s = _CONTRACT_SHA.search(line)
            if s:
                out[current] = s.group(1)
    return out


def manifest_check(*, deep: bool = False, layout: Layout | None = None) -> CheckReport:
    lay = resolve_layout(layout)
    rep = CheckReport()
    m = load_manifest(lay)
    arts: dict[str, Any] = m["artifacts"]
    on_disk = (
        {lay.rel(p) for p in lay.work.rglob("*.parquet") if not p.name.startswith(".")}
        if lay.work.exists()
        else set()
    )
    if not lay.manifest.exists():
        rep.notes.append("no work/MANIFEST.json")
    for rel in sorted(on_disk - set(arts)):
        rep.errors.append(f"unregistered artifact {rel}")
    for rel, entry in sorted(arts.items()):
        p = lay.root / rel
        if not p.is_file():
            rep.errors.append(f"missing artifact {rel}")
        elif sha256_file(p) != entry["sha256"]:
            rep.errors.append(f"sha256 mismatch {rel}")
    for rel, entry in sorted(m["inputs"].items()):
        p = lay.root / rel
        if not p.is_file():
            rep.errors.append(f"missing input {rel}")
            continue
        st = p.stat()
        if st.st_size != entry["size"] or st.st_mtime_ns != entry["mtime_ns"]:
            rep.errors.append(f"input changed (size/mtime) {rel}")
        elif deep and sha256_file(p) != entry["sha256"]:
            rep.errors.append(f"input sha256 mismatch {rel}")
    contract = lay.docs / DATA_CONTRACT
    if arts:
        shas = contract_shas(contract) if contract.is_file() else {}
        for rel, entry in sorted(arts.items()):
            if rel not in shas:
                rep.errors.append(f"{rel} has no entry with a sha256 in docs/{DATA_CONTRACT}")
            elif shas[rel] != entry["sha256"]:
                rep.errors.append(f"docs/{DATA_CONTRACT} sha256 for {rel} differs from the manifest")
    rep.notes.append(
        f"{len(arts)} artifacts, {len(m['inputs'])} inputs checked ({'sha256' if deep else 'size+mtime'})"
    )
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m newsaction.io")
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--deep", action="store_true", help="also re-hash every Data/ input")
    args = parser.parse_args(argv)
    rep = manifest_check(deep=args.deep)
    for note in rep.notes:
        print(f"manifest: {note}")
    for err in rep.errors:
        print(f"manifest: ERROR {err}", file=sys.stderr)
    print("manifest: OK" if rep.ok else f"manifest: FAILED ({len(rep.errors)} errors)")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
