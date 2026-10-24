from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from newsaction.ledger import LEDGER_FILES
from newsaction.paths import ROOT, Layout


def make_layout(root: Path) -> Layout:
    """A throwaway repository: copies of PREREG and configs, empty ledgers, empty work/ and Data/."""
    (root / "docs").mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "PREREG.md", root / "docs" / "PREREG.md")
    shutil.copytree(ROOT / "configs", root / "configs")
    (root / "ledgers").mkdir()
    for name in LEDGER_FILES:
        (root / "ledgers" / name).touch()
    (root / "work").mkdir()
    (root / "Data").mkdir()
    return Layout(root)


@pytest.fixture
def tmp_layout(tmp_path: Path) -> Layout:
    return make_layout(tmp_path / "repo")
