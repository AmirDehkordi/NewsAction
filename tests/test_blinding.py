"""Blinding guards (PRD NA-00 S13, GAC3; CLAUDE.md B8).

(a) No module in src/ other than lock.py contains a test-period date literal or touches the sealed
    directory (the ``SEALED`` constant, ``Layout.sealed``, or a "sealed" string); io's private
    verified reader is used only by the lock. paths.py may define the location, nothing else.
(b) sealed_path refuses both purposes before the freeze and logs each attempt.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from newsaction import lock
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.paths import ROOT, Layout

SRC = ROOT / "src" / "newsaction"
DATE_RES = (
    re.compile(r"2026-0[1-9]|2026-1[0-2]"),  # PRD S13
    re.compile(r"\b2026(0[1-9]|1[0-2])\d{2}\b"),  # compact yyyymmdd
    re.compile(r"2026/(0[1-9]|1[0-2])"),
)
SEALED_IDENTIFIERS = {"SEALED", "sealed"}
LOCK_ONLY_ATTRS = {"_read_verified"}
DATE_CONSTRUCTORS = {"date", "datetime", "Timestamp", "datetime64"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def _callee(node: ast.Call) -> str | None:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def violations(source: str, rel: str) -> list[str]:
    """Blinding violations in one source file (``rel`` is its path under src/newsaction/)."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    sealed_rules = rel not in {"lock.py", "paths.py"}
    out: list[str] = []

    def hit(node: ast.AST, what: str) -> None:
        out.append(f"{rel}:{getattr(node, 'lineno', '?')}: {what}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str | bytes):
            text = node.value.decode("latin-1") if isinstance(node.value, bytes) else node.value
            if any(r.search(text) for r in DATE_RES):
                hit(node, f"test-period date literal {text[:60]!r}")
            if sealed_rules and id(node) not in docstrings and "sealed" in text.lower():
                hit(node, f"sealed path string {text[:60]!r}")
        elif isinstance(node, ast.Call) and _callee(node) in DATE_CONSTRUCTORS and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, int) and first.value >= 2026:
                hit(node, f"test-period date constructor {_callee(node)}({first.value}, ...)")
        if not sealed_rules:
            continue
        if isinstance(node, ast.Name) and node.id in SEALED_IDENTIFIERS:
            hit(node, f"sealed identifier {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in SEALED_IDENTIFIERS:
            hit(node, f"sealed attribute .{node.attr}")
        elif isinstance(node, ast.alias) and node.name in SEALED_IDENTIFIERS:
            hit(node, f"import of {node.name}")
        if rel != "io.py" and isinstance(node, ast.Attribute) and node.attr in LOCK_ONLY_ATTRS:
            hit(node, f"lock-only reader .{node.attr}")
    return out


def test_scanner_catches_planted_violations() -> None:
    planted = '''
"""Docstrings may say sealed, but not 2026-03-02."""
from datetime import date
from newsaction.paths import SEALED
from newsaction import paths, io
a = "2026-01-02"
b = paths.WORK / "snapshot" / "sealed"
c = layout.sealed
d = date(2026, 1, 2)
e = io._read_verified(p)
f = "20260315"
g = f"{x}/2026-07"
'''
    found = violations(planted, "panel/targets.py")
    expected = ["2:", "4:", "6:", "7:", "8:", "9:", "10:", "11:", "12:"]
    for prefix in expected:
        assert any(f"panel/targets.py:{prefix}" in v for v in found), (prefix, found)


def test_scanner_allows_the_sanctioned_routes() -> None:
    ok = '''
"""Reads 2025 data; 2026 outcomes only via the lock, which keeps them sealed."""
from newsaction import lock
p = lock.sealed_path(name, "targets")
df = lock.read_sealed(name, "reactions")
end = "2025-12-31"
seed = 2026
'''
    assert violations(ok, "panel/targets.py") == []


def test_src_has_no_test_period_literals_or_sealed_access() -> None:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel == "lock.py":
            continue
        found += violations(path.read_text(encoding="utf-8"), rel)
    assert found == []


def test_paths_module_only_defines_locations() -> None:
    tree = ast.parse((SRC / "paths.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
    }
    assert imported <= {"__future__", "dataclasses", "pathlib", "typing"}


# --- (b) refusals before the freeze ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_unblind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NA_UNBLIND", raising=False)


def test_sealed_path_refuses_both_purposes_before_freeze_and_logs(tmp_layout: Layout) -> None:
    for purpose in ("reactions", "targets"):
        with pytest.raises(lock.LockError):
            lock.sealed_path("prices_raw_2026", purpose, layout=tmp_layout)  # type: ignore[arg-type]
    logged = AccessLedger(tmp_layout.ledgers / TEST_ACCESS).entries()
    assert [(e["purpose"], e["allowed"]) for e in logged] == [("reactions", False), ("targets", False)]
    assert all(e["caller"] and e["git_sha"] and e["reason"] for e in logged)


def test_real_repo_targets_refused_without_unblind(tmp_path: Path) -> None:
    lay = Layout(ROOT, ledgers_dir=tmp_path)
    with pytest.raises(lock.LockError):
        lock.sealed_path("prices_raw_2026", "targets", layout=lay)
    assert AccessLedger(tmp_path / TEST_ACCESS).entries()[0]["allowed"] is False


def test_real_repo_reactions_refused_until_frozen(tmp_path: Path) -> None:
    if lock.is_frozen():
        pytest.skip("repository is frozen (NA-11 done)")
    with pytest.raises(lock.LockError):
        lock.sealed_path("prices_raw_2026", "reactions", layout=Layout(ROOT, ledgers_dir=tmp_path))


def test_real_access_ledger_has_no_premature_grants() -> None:
    """GAC3: every granted reactions/targets access in ledgers/test_access.jsonl follows the freeze."""
    granted = [
        e for e in AccessLedger().entries() if e["allowed"] and e["purpose"] in {"reactions", "targets"}
    ]
    if not granted:
        return
    record = json.loads((ROOT / lock.FREEZE_RECORD).read_text(encoding="utf-8"))
    assert all(str(e["ts"]) > record["ts"] for e in granted)
