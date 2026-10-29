"""NA-14 AC1 and operator item 2: ``make paper`` runs offline, reproduces every digest and writes no ledger.

- a full rebuild in a scratch copy of the repository (the NA-03 … NA-13 artifacts, PREREG and the
  ledgers linked, NA-13's stored positions, books and placebo books copied with the manifest) exits 0 with
  every output digest equal, writes the committed bytes, leaves every ``ledgers/*.jsonl`` byte-identical and
  imports neither the decision-model client, nor ``newsaction.lock``, nor ``panel.targets`` /
  ``panel.reactions``;
- a changed input stops the run before anything is rebuilt;
- a build that appends to a ledger fails the run (the guard is not vacuous);
- ``docs/REPLICATION.md`` lists the committed CSV digests and the ledgers' spend.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from newsaction.figures import paper
from newsaction.figures import sources as sc
from newsaction.paths import ROOT, Layout

LINKED = (*(f"artifacts/NA-{n:02d}" for n in range(3, 14)), "ledgers", "configs", "docs/PREREG.md")
NA14_INPUTS = ("inputs", "captions.yaml", "digests.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scratch(tmp: Path) -> Path:
    root = tmp / "repo"
    for rel in LINKED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).symlink_to(ROOT / rel)
    na14 = root / sc.ARTIFACTS
    na14.mkdir(parents=True)
    for name in NA14_INPUTS:
        src = ROOT / sc.ARTIFACTS / name
        if src.is_dir():
            shutil.copytree(src, na14 / name)
        else:
            shutil.copy2(src, na14 / name)
    (root / "work" / "strategy").mkdir(parents=True)
    for name in ("positions_test.parquet", "books_test.parquet", "placebo_test.parquet"):
        shutil.copy2(ROOT / "work" / "strategy" / name, root / "work" / "strategy" / name)
    shutil.copy2(ROOT / "work" / "MANIFEST.json", root / "work" / "MANIFEST.json")
    return root


def _run(root: Path) -> tuple[int, dict[str, object]]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "newsaction.figures.paper", "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=900,
        env=env,
        check=False,
    )
    out = proc.stdout
    report: dict[str, object] = (
        json.loads(out[: out.rindex("}") + 1]) if "}" in out else {"stderr": proc.stderr}
    )
    return proc.returncode, report


def test_make_paper_reproduces_every_digest_offline(tmp_path: Path) -> None:
    ledgers = {p.name: _sha(p) for p in sorted((ROOT / "ledgers").glob("*.jsonl"))}
    root = _scratch(tmp_path)
    code, report = _run(root)
    assert code == 0, report
    assert report["outputs"] == "all equal" and report["figures"] == "all equal"
    assert report["ledgers_unchanged"] is True and report["forbidden_imports"] == []
    committed = json.loads((ROOT / paper.DIGESTS).read_text(encoding="utf-8"))
    for rel, sha in {**committed["outputs"], **committed["figures"]}.items():
        assert _sha(root / rel) == sha == _sha(ROOT / rel), rel
    assert {p.name: _sha(p) for p in sorted((ROOT / "ledgers").glob("*.jsonl"))} == ledgers


def test_a_changed_input_stops_the_run(tmp_path: Path) -> None:
    root = _scratch(tmp_path)
    cap = root / sc.ARTIFACTS / "captions.yaml"
    cap.write_text(cap.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    code, report = _run(root)
    assert code == 1
    assert report["inputs"] == [f"changed {sc.ARTIFACTS}/captions.yaml"]
    assert not (root / sc.TABLES).exists()


def test_a_ledger_write_fails_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    (root / "ledgers").mkdir(parents=True)
    for name in paper.LEDGERS:
        (root / "ledgers" / name).write_text('{"event":"x"}\n', encoding="utf-8")
    (root / sc.ARTIFACTS).mkdir(parents=True)
    monkeypatch.setattr(paper, "inputs", lambda: [f"ledgers/{n}" for n in paper.LEDGERS])

    def build(lay: Layout) -> dict[str, object]:
        with (lay.ledgers / "trials.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"event":"y"}\n')
        return {}

    monkeypatch.setattr(paper, "build", build)
    code, report = paper.run(Layout(root), write_digests=True)
    assert code == 1 and report["ledgers_unchanged"] is False


def test_importing_the_package_loads_no_lock_client_or_outcome_module() -> None:
    mods = ", ".join(
        f"newsaction.figures.{m}"
        for m in (
            "paper",
            "contract",
            "tables",
            "latex",
            "preview",
            "guard",
            "data",
            "render",
            "captions",
            "appendix",
            "fig1_validation_test",
        )
    )
    forbidden = list(paper.FORBIDDEN)
    code = f"import {mods}, sys, json; print(json.dumps([m for m in {forbidden!r} if m in sys.modules]))"
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=300
    )
    assert json.loads(proc.stdout) == []


def test_replication_doc_lists_the_committed_digests_and_spend() -> None:
    doc = (ROOT / "docs" / "REPLICATION.md").read_text(encoding="utf-8")
    listed = dict(re.findall(r"\| `([^`]+\.csv)` \| `([0-9a-f]{64})` \|", doc))
    committed = json.loads((ROOT / paper.DIGESTS).read_text(encoding="utf-8"))["outputs"]
    want = {p.rsplit("/", 1)[1]: s for p, s in committed.items() if p.endswith(".csv")}
    assert listed == want
    spend = pd.read_csv(ROOT / sc.TABLES / "t22_spend.csv").set_index("key")["value"]
    assert f"${spend['openrouter_total']:.2f}" in doc and f"{int(spend['fmp_requests']):,} requests" in doc
    assert f"{spend['kaggle_total_gpu_hours']:.2f} GPU-hours" in doc
