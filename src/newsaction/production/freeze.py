"""NA-11 S3: the freeze (PREREG §4.4; PRD NA-11 S3, AC1, AC2).

``check`` lists what must hold before ``lock.freeze``:
- ``configs/frozen.yaml`` holds ``selection`` (with the trained-run pin), ``thresholds``, ``calibration``
  (V maps with their val-A fit ranges, AC2) and ``strategy`` (S-CONV, AC2);
- ``configs/production.yaml`` exists (the frozen production plan of S4–S9);
- no cached response holds a test-period state, and ``ledgers/test_access.jsonl`` has no "reactions" or
  "targets" entry (AC1: the freeze precedes both).

``request`` sets ``frozen_requested: true``; ``run`` checks, then writes ``artifacts/NA-11/freeze.json``
through ``lock.freeze``. The freeze commit and the annotated tag ``prereg-freeze`` on it follow, so the tagged
tree hashes to the recorded hash. ``evidence`` compares the freeze time with the first cached 2026 state and
the first "reactions" access (AC1; the verifier's step 2).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections.abc import Sequence
from datetime import date
from typing import Any, Final

from newsaction import io, lock
from newsaction.config import load_frozen, load_splits
from newsaction.dm import dm_config
from newsaction.ledger import TEST_ACCESS
from newsaction.paths import Layout, resolve_layout
from newsaction.production import ProductionError

SECTIONS: Final = ("selection", "thresholds", "calibration", "strategy")
PLAN: Final = "production.yaml"
_REQUEST: Final = re.compile(r"^frozen_requested:\s*false\b.*$", re.MULTILINE)


def test_state_rows(layout: Layout | None = None) -> list[tuple[str, str]]:
    """(created_at, key) of every cached response whose state is in the test period (split or session)."""
    lay = resolve_layout(layout)
    path = lay.root / dm_config(lay).cache
    if not path.is_file():
        return []
    start = load_splits(lay.configs / "splits.yaml").splits["test"].start
    out = []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for created, key, meta in con.execute("SELECT created_at, key, meta_json FROM responses"):
            info = json.loads(meta).get("info", json.loads(meta))
            split, session = info.get("split"), info.get("session")
            if split == "test" or (session is not None and date.fromisoformat(str(session)[:10]) >= start):
                out.append((str(created), str(key)))
    finally:
        con.close()
    return sorted(out)


def access(
    layout: Layout | None = None, purposes: Sequence[str] = ("reactions", "targets")
) -> list[dict[str, Any]]:
    path = resolve_layout(layout).ledgers / TEST_ACCESS
    rows = (
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        if path.is_file()
        else []
    )
    return [r for r in rows if r.get("purpose") in purposes]


def check(layout: Layout | None = None) -> list[str]:
    """The pre-conditions of the freeze that do not hold (empty: ready)."""
    lay = resolve_layout(layout)
    fz = load_frozen(lay.configs / "frozen.yaml")
    problems = [f"frozen.yaml {s} is empty" for s in SECTIONS if not getattr(fz, s, None) and s != "strategy"]
    if not getattr(fz, "strategy", None) and "strategy" not in (fz.model_extra or {}):
        problems.append("frozen.yaml strategy is empty")
    sel = fz.selection if isinstance(fz.selection, dict) else {}
    if not sel.get("primary_instrument") or not sel.get("trained_runs"):
        problems.append("frozen.yaml selection lacks the primary instrument or the trained-run pin")
    cal = fz.calibration if isinstance(fz.calibration, dict) else {}
    for model, entry in cal.items():
        for src in ("a0", "a2"):
            if src in entry and not (entry[src].get("v") and entry[src].get("fit_range")):
                problems.append(f"calibration {model}.{src} lacks its V map or fit range")
    if not (lay.configs / PLAN).is_file():
        problems.append(f"configs/{PLAN} (the frozen production plan) is missing")
    if test_state_rows(lay):
        problems.append("the cache holds a test-period state before the freeze")
    if access(lay):
        problems.append("ledgers/test_access.jsonl has a reactions or targets entry before the freeze")
    if lock.is_frozen(lay):
        problems.append("already frozen")
    return problems


def request(layout: Layout | None = None) -> None:
    """Set ``frozen_requested: true`` in configs/frozen.yaml (exactly one line changes)."""
    lay = resolve_layout(layout)
    path = lay.configs / "frozen.yaml"
    text = path.read_text(encoding="utf-8")
    new, n = _REQUEST.subn("frozen_requested: true   # NA-11 S3: set before lock.freeze()", text)
    if n != 1:
        raise ProductionError("configs/frozen.yaml must contain exactly one 'frozen_requested: false' line")
    io.atomic_write_bytes(path, new.encode("utf-8"))


def run(note: str, layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    problems = check(lay)
    if problems:
        raise ProductionError("freeze refused: " + "; ".join(problems))
    return lock.freeze(note, layout=lay)


def evidence(layout: Layout | None = None) -> dict[str, Any]:
    """AC1: the freeze time against the first cached 2026 state and the first reactions / targets access."""
    lay = resolve_layout(layout)
    rec = json.loads((lay.root / lock.FREEZE_RECORD).read_text(encoding="utf-8"))
    rows = test_state_rows(lay)
    react = [r for r in access(lay) if r["purpose"] == "reactions"]
    targets = [r for r in access(lay) if r["purpose"] == "targets"]
    first_state = rows[0][0] if rows else None
    first_react = min((r["ts"] for r in react), default=None)
    return {
        "freeze_ts": rec["ts"],
        "freeze_hash": rec["hash"],
        "hash_now": lock.compute_freeze_hash(lay).digest,
        "first_test_state_cache_row": first_state,
        "first_reactions_access": first_react,
        "targets_entries": len(targets),
        "order_ok": all(t is None or t > rec["ts"] for t in (first_state, first_react)) and not targets,
        "spec_and_targets_hashed": all(
            k in rec["files"] for k in ("src/newsaction/analysis/spec.py", "src/newsaction/panel/targets.py")
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "check"
    if cmd == "check":
        problems = check()
        print("ready" if not problems else "\n".join(problems))
        return 0 if not problems else 1
    if cmd == "request":
        request()
        print("frozen_requested: true")
        return 0
    if cmd == "freeze":
        rec = run(" ".join(args[1:]) or "NA-11 S3 freeze (PREREG §4.4)")
        print(json.dumps({k: rec[k] for k in ("hash", "git_sha", "ts")}, indent=1))
        return 0
    if cmd == "evidence":
        print(json.dumps(evidence(), indent=1))
        return 0
    raise SystemExit(f"unknown command {cmd!r} (check | request | freeze | evidence)")


if __name__ == "__main__":
    raise SystemExit(main())
