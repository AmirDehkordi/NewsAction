"""Provenance helpers shared by ledgers, the lock and the manifest: git sha and UTC timestamps."""

from __future__ import annotations

import functools
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from newsaction.paths import ROOT

NO_GIT = "nogit"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def git_sha(root: Path = ROOT) -> str:
    """HEAD commit of the repository at ``root`` (``"nogit"`` outside a repository or before a commit)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return NO_GIT
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else NO_GIT


@functools.cache
def git_sha_cached(root: Path = ROOT) -> str:
    """``git_sha`` computed once per process (for high-volume records such as spend lines)."""
    return git_sha(root)
