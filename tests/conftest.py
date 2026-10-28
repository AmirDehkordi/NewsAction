from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from newsaction.ledger import LEDGER_FILES
from newsaction.paths import ROOT, Layout


def make_layout(root: Path) -> Layout:
    """A throwaway repository: copies of PREREG and configs, empty ledgers, empty work/ and Data/. Its
    ``configs/frozen.yaml`` is back in the pre-freeze protocol state (``frozen_requested`` and ``frozen``
    false, every section as copied), so the lock's tests can freeze it themselves after the real NA-11
    freeze."""
    (root / "docs").mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "PREREG.md", root / "docs" / "PREREG.md")
    shutil.copytree(ROOT / "configs", root / "configs")
    frozen = root / "configs" / "frozen.yaml"
    text = re.sub(
        r"^frozen_requested:.*$", "frozen_requested: false", frozen.read_text(encoding="utf-8"), flags=re.M
    )
    frozen.write_text(re.sub(r"^frozen:.*$", "frozen: false", text, flags=re.M), encoding="utf-8")
    (root / "ledgers").mkdir()
    for name in LEDGER_FILES:
        (root / "ledgers" / name).touch()
    (root / "work").mkdir()
    (root / "Data").mkdir()
    return Layout(root)


@pytest.fixture
def tmp_layout(tmp_path: Path) -> Layout:
    return make_layout(tmp_path / "repo")


# --- NA-01 panel artifacts (integration tests skip when the build has not run) ----------------------

PANEL_FILES = ("panel_public", "panel_test_inputs", "companies", "tiers_monthly", "qc_flags", "mapping")


def _work_parquet(rel: str, columns: list[str] | None = None) -> pd.DataFrame:
    from newsaction import io

    if not (ROOT / "work" / rel).is_file():
        pytest.skip(f"work/{rel} is absent (run the NA-01 export and build)")
    return io.read_parquet(rel, columns=columns)


@pytest.fixture(scope="session")
def panel_public() -> pd.DataFrame:
    return _work_parquet("panel/panel_public.parquet")


@pytest.fixture(scope="session")
def tiers_monthly() -> pd.DataFrame:
    return _work_parquet("panel/tiers_monthly.parquet")


@pytest.fixture(scope="session")
def companies() -> pd.DataFrame:
    return _work_parquet("panel/companies.parquet")


@pytest.fixture(scope="session")
def snapshot() -> Callable[[str], pd.DataFrame]:
    def load(name: str) -> pd.DataFrame:
        return _work_parquet(f"snapshot/{name}.parquet")

    return load
