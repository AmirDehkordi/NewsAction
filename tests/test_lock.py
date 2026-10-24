"""Blinding lock and freeze protocol (PREREG §4.3–4.4; PRD NA-00 AC5). All on a temporary repo."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from newsaction import io, lock
from newsaction.ledger import TEST_ACCESS, AccessLedger
from newsaction.lock import LockError
from newsaction.paths import Layout


def entries(lay: Layout) -> list[dict[str, object]]:
    return AccessLedger(lay.ledgers / TEST_ACCESS).entries()


def request_freeze(lay: Layout) -> None:
    p = lay.configs / "frozen.yaml"
    text = p.read_text(encoding="utf-8")
    assert "frozen_requested: false" in text
    p.write_text(text.replace("frozen_requested: false", "frozen_requested: true"), encoding="utf-8")


@pytest.fixture
def frozen_layout(tmp_layout: Layout) -> Layout:
    request_freeze(tmp_layout)
    lock.freeze("test freeze", layout=tmp_layout)
    return tmp_layout


@pytest.fixture(autouse=True)
def _no_unblind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NA_UNBLIND", raising=False)


# --- before the freeze -----------------------------------------------------------------------------


@pytest.mark.parametrize("purpose", ["reactions", "targets"])
def test_sealed_path_refused_before_freeze_and_logged(tmp_layout: Layout, purpose: lock.Purpose) -> None:
    assert not lock.is_frozen(tmp_layout)
    with pytest.raises(LockError):
        lock.sealed_path("prices_raw_2026", purpose, layout=tmp_layout)
    (e,) = entries(tmp_layout)
    assert e["allowed"] is False
    assert e["purpose"] == purpose
    assert e["name"] == "prices_raw_2026"
    assert "test_lock.py" in str(e["caller"]) and "test_sealed_path_refused_before_freeze" in str(e["caller"])
    assert isinstance(e["git_sha"], str) and e["git_sha"]
    assert e["ts"]


def test_refusal_even_with_unblind_env(tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NA_UNBLIND", "1")
    for purpose in ("reactions", "targets"):
        with pytest.raises(LockError):
            lock.sealed_path("x", purpose, layout=tmp_layout)  # type: ignore[arg-type]
    assert [e["allowed"] for e in entries(tmp_layout)] == [False, False]


def test_every_attempt_appends_one_entry(tmp_layout: Layout) -> None:
    for _ in range(3):
        with pytest.raises(LockError):
            lock.sealed_path("prices_raw_2026", "targets", layout=tmp_layout)
    assert len(entries(tmp_layout)) == 3


@pytest.mark.parametrize("name", ["../prices", "a/b", "", ".hidden", "x y"])
def test_invalid_names_refused_and_logged(frozen_layout: Layout, name: str) -> None:
    with pytest.raises(LockError, match="invalid sealed name"):
        lock.sealed_path(name, "reactions", layout=frozen_layout)
    assert entries(frozen_layout)[-1]["allowed"] is False


def test_unknown_purpose_refused(frozen_layout: Layout) -> None:
    with pytest.raises(LockError, match="purpose"):
        lock.sealed_path("x", "peek", layout=frozen_layout)  # type: ignore[arg-type]
    assert entries(frozen_layout)[-1]["allowed"] is False


def test_require_guards_before_freeze(tmp_layout: Layout) -> None:
    with pytest.raises(LockError):
        lock.require_frozen(tmp_layout)
    with pytest.raises(LockError):
        lock.require_unblind(tmp_layout)


def test_read_sealed_refused_before_freeze(tmp_layout: Layout) -> None:
    with pytest.raises(LockError):
        lock.read_sealed("prices_raw_2026", "reactions", layout=tmp_layout)


def test_malformed_freeze_record_is_not_frozen(tmp_layout: Layout) -> None:
    p = tmp_layout.root / lock.FREEZE_RECORD
    p.parent.mkdir(parents=True)
    p.write_text('{"hash": "not-a-hash"}', encoding="utf-8")
    assert not lock.is_frozen(tmp_layout)
    with pytest.raises(LockError):
        lock.sealed_path("x", "reactions", layout=tmp_layout)


# --- freeze protocol -------------------------------------------------------------------------------


def test_freeze_requires_frozen_requested(tmp_layout: Layout) -> None:
    with pytest.raises(LockError, match="frozen_requested"):
        lock.freeze("too early", layout=tmp_layout)
    assert not (tmp_layout.root / lock.FREEZE_RECORD).exists()


def test_freeze_writes_record_and_flag(frozen_layout: Layout) -> None:
    rec = json.loads((frozen_layout.root / lock.FREEZE_RECORD).read_text(encoding="utf-8"))
    assert rec["hash"] == lock.compute_freeze_hash(frozen_layout).digest
    assert set(rec) >= {"hash", "files", "git_sha", "ts", "note", "deviations_log"}
    assert "configs/frozen.yaml" in rec["files"]
    assert rec["files"]["src/newsaction/panel/targets.py"] == lock.ABSENT
    assert "frozen: true" in (frozen_layout.configs / "frozen.yaml").read_text(encoding="utf-8")
    assert lock.is_frozen(frozen_layout)


def test_freeze_is_one_way(frozen_layout: Layout) -> None:
    with pytest.raises(LockError, match="already exists"):
        lock.freeze("again", layout=frozen_layout)


def test_reactions_allowed_after_freeze_targets_need_unblind(
    frozen_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = lock.sealed_path("prices_raw_2026", "reactions", layout=frozen_layout)
    assert p == frozen_layout.sealed / "prices_raw_2026.parquet"
    with pytest.raises(LockError, match="NA_UNBLIND"):
        lock.sealed_path("prices_raw_2026", "targets", layout=frozen_layout)
    monkeypatch.setenv("NA_UNBLIND", "1")
    assert lock.sealed_path("prices_raw_2026", "targets", layout=frozen_layout) == p
    assert [(e["purpose"], e["allowed"]) for e in entries(frozen_layout)] == [
        ("reactions", True),
        ("targets", False),
        ("targets", True),
    ]


def test_unblind_fails_after_one_character_edit_of_frozen_yaml(
    frozen_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NA_UNBLIND", "1")
    lock.require_unblind(frozen_layout)
    p = frozen_layout.configs / "frozen.yaml"
    # one appended character: independent of which sections later chunks have filled
    p.write_text(p.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(LockError, match=r"hash mismatch.*configs/frozen.yaml"):
        lock.require_unblind(frozen_layout)
    with pytest.raises(LockError):
        lock.sealed_path("prices_raw_2026", "targets", layout=frozen_layout)


@pytest.mark.parametrize(
    "rel", ["src/newsaction/panel/targets.py", "src/newsaction/analysis/spec.py", "configs/new.yaml"]
)
def test_unblind_fails_when_a_frozen_file_appears(
    frozen_layout: Layout, monkeypatch: pytest.MonkeyPatch, rel: str
) -> None:
    monkeypatch.setenv("NA_UNBLIND", "1")
    p = frozen_layout.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(LockError, match="hash mismatch"):
        lock.require_unblind(frozen_layout)


def test_prereg_protected_part_is_hashed(frozen_layout: Layout, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NA_UNBLIND", "1")
    p = frozen_layout.docs / "PREREG.md"
    p.write_text(p.read_text(encoding="utf-8").replace("Holm-corrected", "Holm corrected"), encoding="utf-8")
    with pytest.raises(LockError, match="PREREG"):
        lock.require_unblind(frozen_layout)


def test_deviations_log_may_be_appended_after_freeze(
    frozen_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NA_UNBLIND", "1")
    p = frozen_layout.docs / "PREREG.md"
    with p.open("a", encoding="utf-8") as fh:
        fh.write("| 2026-12-01 | NA-12 | §11 | example | example | after |\n")
    lock.require_unblind(frozen_layout)


def test_deviations_log_edit_after_freeze_detected(
    frozen_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NA_UNBLIND", "1")
    p = frozen_layout.docs / "PREREG.md"
    text = p.read_text(encoding="utf-8")
    head, log = text.split("## 15. Deviations log", 1)
    p.write_text(head + "## 15. Deviations log" + log.replace("Reason", "Why"), encoding="utf-8")
    with pytest.raises(LockError, match="Deviations log"):
        lock.require_unblind(frozen_layout)


# --- hash ------------------------------------------------------------------------------------------


def test_freeze_hash_is_deterministic_and_marks_absent_files(tmp_layout: Layout) -> None:
    a = lock.compute_freeze_hash(tmp_layout)
    b = lock.compute_freeze_hash(tmp_layout)
    assert a == b
    assert a.files["src/newsaction/analysis/spec.py"] == lock.ABSENT
    assert {"configs/project.yaml", "configs/splits.yaml", "configs/frozen.yaml"} <= set(a.files)
    assert lock.PREREG_PROTECTED_KEY in a.files
    assert a.deviations_log_bytes > 0


def test_freeze_hash_changes_with_any_config(tmp_layout: Layout) -> None:
    before = lock.compute_freeze_hash(tmp_layout).digest
    p = tmp_layout.configs / "splits.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert lock.compute_freeze_hash(tmp_layout).digest != before


def test_real_repo_freeze_files_list() -> None:
    assert lock.FREEZE_FILES == (
        "docs/PREREG.md",
        "configs/*.yaml",
        "src/newsaction/panel/targets.py",
        "src/newsaction/panel/reactions.py",
        "src/newsaction/analysis/spec.py",
    )


# --- sealed read/write routes ----------------------------------------------------------------------


def test_write_sealed_then_read_after_freeze(tmp_layout: Layout) -> None:
    df = pd.DataFrame({"x": [1, 2, 3]})
    entry = lock.write_sealed(df, "demo", producer="test", description="demo", layout=tmp_layout)
    assert entry["rows"] == 3
    assert entries(tmp_layout)[-1]["purpose"] == "write"
    with pytest.raises(io.ManifestError, match="lock"):
        io.read_parquet("snapshot/sealed/demo.parquet", layout=tmp_layout)
    with pytest.raises(LockError):
        lock.read_sealed("demo", "reactions", layout=tmp_layout)
    request_freeze(tmp_layout)
    lock.freeze("t", layout=tmp_layout)
    out = lock.read_sealed("demo", "reactions", layout=tmp_layout)
    pd.testing.assert_frame_equal(out, df)


def test_temp_ledger_context_on_real_repo(tmp_path: Path) -> None:
    """The verifier's form: real repository files, temporary access ledger."""
    from newsaction.paths import ROOT

    lay = Layout(ROOT, ledgers_dir=tmp_path)
    with pytest.raises(LockError):
        lock.sealed_path("prices_raw_2026", "targets", layout=lay)
    (e,) = AccessLedger(tmp_path / TEST_ACCESS).entries()
    assert e["allowed"] is False and e["purpose"] == "targets"
