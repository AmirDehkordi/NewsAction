"""PRD NA-03 AC4: building events reads no outcome; nothing in events/ imports panel.targets or the lock.

- No module in ``src/newsaction/events`` imports ``newsaction.panel.targets``, ``newsaction.panel.reactions``
  or ``newsaction.lock``, or reads the sealed directory.
- Only ``labels`` reads ``panel_public`` (returns, public sessions only), and only ``labels`` /
  ``learned`` / ``select`` read the labels. The modules that build test-period events (``aggregate``,
  ``scores``, ``attention``, ``filters``, ``tokens``, ``clean_window``, ``projection``) reference
  neither.
- ``ledgers/test_access.jsonl`` holds no entry written from NA-03 code.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from newsaction.paths import ROOT

EVENTS = ROOT / "src" / "newsaction" / "events"
FORBIDDEN_MODULES = ("newsaction.panel.targets", "newsaction.panel.reactions", "newsaction.lock")
EVENT_BUILDERS = ("aggregate", "scores", "attention", "filters", "tokens", "clean_window", "projection")
OUTCOME_SOURCES = ("panel_public", "LABELS", "labels_public")


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


def _code_identifiers_and_strings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                doc_ids.add(id(first.value))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.add(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            out.add(node.value)
    return out


def test_scanner_detects_planted_imports(tmp_path: Path) -> None:
    p = tmp_path / "bad.py"
    p.write_text("from newsaction.panel import targets\nfrom newsaction.lock import read_sealed\n")
    found = _imports(p)
    assert "newsaction.panel.targets" in found and "newsaction.lock" in found


@pytest.mark.parametrize("path", sorted(EVENTS.glob("*.py")), ids=lambda p: p.name)
def test_events_import_no_targets_or_lock(path: Path) -> None:
    found = _imports(path)
    bad = [m for m in found if any(m == f or m.startswith(f + ".") for f in FORBIDDEN_MODULES)]
    assert not bad, f"{path.name} imports {bad}"
    assert not any("sealed" in s.lower() for s in _code_identifiers_and_strings(path))


@pytest.mark.parametrize("name", EVENT_BUILDERS)
def test_event_builders_read_no_outcome(name: str) -> None:
    path = EVENTS / f"{name}.py"
    names = _code_identifiers_and_strings(path)
    hits = [s for s in names if any(src in s for src in OUTCOME_SOURCES)]
    assert not hits, f"{name}.py references outcome sources {hits}"
    assert "newsaction.events.labels" not in _imports(path)
    assert "newsaction.events.select" not in _imports(path)


def test_only_labels_reads_the_public_panel() -> None:
    readers = sorted(
        p.stem
        for p in EVENTS.glob("*.py")
        if any("panel_public" in s for s in _code_identifiers_and_strings(p))
    )
    assert readers == ["labels"]


def test_access_ledger_has_no_na03_entry() -> None:
    lines = (ROOT / "ledgers" / "test_access.jsonl").read_text(encoding="utf-8").splitlines()
    for line in lines:
        rec = json.loads(line)
        blob = json.dumps(rec).lower()
        assert "events" not in str(rec.get("caller", "")).lower()
        assert "na-03" not in blob
