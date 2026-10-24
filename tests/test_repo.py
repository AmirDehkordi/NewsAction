"""Repository invariants (PRD NA-00 AC9): ignore rules, untracked Data/, the prereg-v0 tag."""

from __future__ import annotations

import subprocess

import pytest

from newsaction.lock import _split_prereg
from newsaction.paths import ROOT

pytestmark = pytest.mark.skipif(not (ROOT / ".git").exists(), reason="not a git checkout")


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)


@pytest.mark.parametrize(
    "path",
    ["Data", "work", "cache", "Data/news_2025.parquet", "work/MANIFEST.json", "cache/decisions.sqlite",
     ".env", "kaggle.json", "x.sqlite", ".venv/bin/python", "src/newsaction/__pycache__/x.pyc",
     ".mypy_cache/x", ".ruff_cache/x", "m.ckpt", "m.safetensors", "ledgers/spend.jsonl.lock"],
)  # fmt: skip
def test_gitignore_excludes(path: str) -> None:
    assert git("check-ignore", "-q", "--no-index", path).returncode == 0, path


@pytest.mark.parametrize(
    "path", ["ledgers/spend.jsonl", "ledgers/test_access.jsonl", "artifacts/NA-00/REPORT.md", "uv.lock"]
)
def test_committed_paths_not_ignored(path: str) -> None:
    assert git("check-ignore", "-q", "--no-index", path).returncode == 1, path


def test_data_is_not_tracked() -> None:
    assert git("ls-files", "Data", "work", "cache", ".env").stdout == b""


def test_initial_docs_commit_is_the_root_of_main() -> None:
    root = git("rev-list", "--max-parents=0", "main").stdout.decode().split()
    assert len(root) == 1
    assert git("log", "-1", "--format=%s", root[0]).stdout.decode().strip() == "chore: initial docs"
    files = set(git("show", "--name-only", "--format=", root[0]).stdout.decode().split("\n")) - {""}
    assert files == {"CLAUDE.md", "NewsAction PRD.md", "docs/PREREG.md"}


def test_prereg_v0_tag() -> None:
    assert git("cat-file", "-t", "prereg-v0").stdout.decode().strip() == "tag"  # annotated
    tagged = git("rev-parse", "prereg-v0^{commit}").stdout.decode().strip()
    root = git("rev-list", "--max-parents=0", "main").stdout.decode().strip()
    assert tagged == root
    v0 = git("show", "prereg-v0:docs/PREREG.md").stdout
    assert v0 == git("show", f"{root}:docs/PREREG.md").stdout
    assert b"**Version:** v0" in v0


def test_prereg_changed_only_by_appending_to_the_deviations_log() -> None:
    """CLAUDE.md B11: earlier sections are never edited; the Deviations log only grows."""
    v0_head, v0_log = _split_prereg(git("show", "prereg-v0:docs/PREREG.md").stdout)
    now_head, now_log = _split_prereg((ROOT / "docs" / "PREREG.md").read_bytes())
    assert now_head == v0_head
    assert now_log.startswith(v0_log)
