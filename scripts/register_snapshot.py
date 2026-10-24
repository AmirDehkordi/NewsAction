"""NA-01 S1: register the ATOM snapshot (written by scripts/export_atom_snapshot.py) in work/MANIFEST.json.

    uv run python scripts/register_snapshot.py

Every file listed in work/snapshot/MANIFEST_snapshot.json must exist with the sha256 recorded at
export time; it is then registered through ``newsaction.io.register_file``. Sealed files are
registered by hash only (no parquet footer is read) and each gets a ``write`` entry in
ledgers/test_access.jsonl, the same audit record ``lock.write_sealed`` leaves. Nothing is read
from them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from newsaction import io
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import git_sha

PRODUCER = "scripts/export_atom_snapshot.py (NA-01 S1, ATOM venv)"
SNAPSHOT = "snapshot"
MANIFEST_NAME = "MANIFEST_snapshot.json"


def load_snapshot_manifest(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    manifest: dict[str, Any] = json.loads((lay.work / SNAPSHOT / MANIFEST_NAME).read_text(encoding="utf-8"))
    return manifest


def register(layout: Layout | None = None) -> list[str]:
    """Verify and register every snapshot file; returns the registered work/-relative paths."""
    lay = resolve_layout(layout)
    manifest = load_snapshot_manifest(lay)
    if not manifest["counts"]["equal"]:
        raise SystemExit(f"refusing to register: ATOM counts changed during the export {manifest['counts']}")
    done: list[str] = []
    for rec in manifest["files"]:
        rel = f"{SNAPSHOT}/{rec['path']}"
        path = lay.work / rel
        sealed = lay.is_locked(path)
        if sealed != bool(rec["sealed"]):
            raise SystemExit(f"{rel}: sealed flag {rec['sealed']} does not match its location")
        if io.sha256_file(path) != rec["sha256"]:
            raise SystemExit(f"{rel}: sha256 differs from {MANIFEST_NAME}")
        io.register_file(
            rel,
            producer=PRODUCER,
            description=f"{rec['description']} [{rec['rows']} rows at export]",
            inspect_parquet=not sealed,
            layout=lay,
        )
        if sealed:
            AccessLedger(lay.ledgers / TEST_ACCESS).log(
                caller=f"{Path(__file__).name}:register",
                name=Path(rec["path"]).stem,
                purpose="write",
                allowed=True,
                reason="written by the NA-01 ATOM export; registered by hash only, not read",
                git_sha=git_sha(lay.root),
            )
        done.append(rel)
    io.register_file(
        f"{SNAPSHOT}/{MANIFEST_NAME}",
        producer=PRODUCER,
        description="export record: read-only transaction, before/after counts, file hashes",
        inspect_parquet=False,
        layout=lay,
    )
    return [*done, f"{SNAPSHOT}/{MANIFEST_NAME}"]


def main() -> int:
    for rel in register():
        print(f"registered work/{rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
