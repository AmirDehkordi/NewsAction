"""Repository layout (CLAUDE.md "Repository layout").

Module constants point at the real repository. Guarded functions (``io``, ``lock``) also accept a
``Layout`` so tests and verifiers can run them against a temporary root or a temporary ledger
directory without touching the committed state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
DATA: Final = ROOT / "Data"
WORK: Final = ROOT / "work"
ARTIFACTS: Final = ROOT / "artifacts"
LEDGERS: Final = ROOT / "ledgers"
CACHE: Final = ROOT / "cache"
CONFIGS: Final = ROOT / "configs"
DOCS: Final = ROOT / "docs"
SEALED: Final = WORK / "snapshot" / "sealed"
MANIFEST: Final = WORK / "MANIFEST.json"


@dataclass(frozen=True)
class Layout:
    """All repository locations derived from one root (``ledgers_dir`` may be redirected)."""

    root: Path
    ledgers_dir: Path | None = None

    @property
    def data(self) -> Path:
        return self.root / "Data"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def ledgers(self) -> Path:
        return self.ledgers_dir if self.ledgers_dir is not None else self.root / "ledgers"

    @property
    def manifest(self) -> Path:
        return self.work / "MANIFEST.json"

    @property
    def sealed(self) -> Path:
        return self.work / "snapshot" / "sealed"

    def is_locked(self, path: Path) -> bool:
        """True if ``path`` lies in the lock-protected directory (readable only via ``newsaction.lock``)."""
        return path.resolve().is_relative_to(self.sealed.resolve())

    def rel(self, path: Path) -> str:
        """Repository-relative POSIX path (the key used in manifests and ledgers)."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()


DEFAULT_LAYOUT: Final = Layout(ROOT)


def resolve_layout(layout: Layout | None) -> Layout:
    return DEFAULT_LAYOUT if layout is None else layout
