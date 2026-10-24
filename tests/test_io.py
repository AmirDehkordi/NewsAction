"""Hashed artifact I/O, input fingerprints and the manifest/contract check (PRD NA-00 S10, GAC2, GAC5)."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from newsaction import io
from newsaction.io import InputChanged, ManifestError
from newsaction.paths import Layout


def frame() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})


def write(lay: Layout, rel: str = "demo/a.parquet") -> dict[str, object]:
    return io.write_parquet(frame(), rel, producer="tests", description="demo", layout=lay)


def contract(lay: Layout) -> None:
    """Write a DATA_CONTRACT.md with one section per manifest artifact."""
    m = io.load_manifest(lay)
    body = "".join(
        f"### `{rel}`\n- **Producer:** tests\n- **sha256:** `{e['sha256']}`\n\n"
        for rel, e in m["artifacts"].items()
    )
    (lay.docs / "DATA_CONTRACT.md").write_text("# Data contract\n\n" + body, encoding="utf-8")


def test_write_registers_and_read_verifies(tmp_layout: Layout) -> None:
    entry = write(tmp_layout)
    path = tmp_layout.work / "demo" / "a.parquet"
    assert entry["sha256"] == io.sha256_file(path)
    assert entry["rows"] == 3
    assert [c["name"] for c in entry["columns"]] == ["a", "b"]  # type: ignore[union-attr]
    assert entry["producer"] == "tests" and entry["git_sha"]
    m = io.load_manifest(tmp_layout)
    assert "work/demo/a.parquet" in m["artifacts"]
    pd.testing.assert_frame_equal(io.read_parquet("demo/a.parquet", layout=tmp_layout), frame())


def test_write_is_deterministic(tmp_layout: Layout) -> None:
    assert write(tmp_layout)["sha256"] == write(tmp_layout)["sha256"]


def test_tampered_artifact_refused(tmp_layout: Layout) -> None:
    write(tmp_layout)
    frame().iloc[:2].to_parquet(tmp_layout.work / "demo" / "a.parquet", index=False)
    with pytest.raises(ManifestError, match="sha256"):
        io.read_parquet("demo/a.parquet", layout=tmp_layout)
    io.read_parquet("demo/a.parquet", verify=False, layout=tmp_layout)  # explicit opt-out still works


def test_unregistered_read_refused(tmp_layout: Layout) -> None:
    (tmp_layout.work / "x.parquet").parent.mkdir(exist_ok=True)
    frame().to_parquet(tmp_layout.work / "x.parquet", index=False)
    with pytest.raises(ManifestError, match="not registered"):
        io.read_parquet("x.parquet", layout=tmp_layout)


@pytest.mark.parametrize("rel", ["../escape.parquet", "/abs.parquet", "demo/a.csv"])
def test_bad_relpaths_refused(tmp_layout: Layout, rel: str) -> None:
    with pytest.raises(ManifestError):
        io.write_parquet(frame(), rel, producer="t", description="d", layout=tmp_layout)


def test_non_default_index_and_bad_columns_refused(tmp_layout: Layout) -> None:
    with pytest.raises(ManifestError, match="RangeIndex"):
        io.write_parquet(
            frame().set_index("a"), "x.parquet", producer="t", description="d", layout=tmp_layout
        )
    with pytest.raises(ManifestError, match="column names"):
        io.write_parquet(
            pd.DataFrame([[1, 2]], columns=["a", "a"]),
            "x.parquet",
            producer="t",
            description="d",
            layout=tmp_layout,
        )
    with pytest.raises(ManifestError, match="producer"):
        io.write_parquet(frame(), "x.parquet", producer="", description="d", layout=tmp_layout)


def test_lock_protected_directory_not_readable_via_io(tmp_layout: Layout) -> None:
    write(tmp_layout, "snapshot/sealed/p.parquet")
    with pytest.raises(ManifestError, match="lock"):
        io.read_parquet("snapshot/sealed/p.parquet", layout=tmp_layout)


def test_register_file_written_elsewhere(tmp_layout: Layout) -> None:
    p = tmp_layout.work / "snapshot" / "ext.parquet"
    p.parent.mkdir(parents=True)
    frame().to_parquet(p, index=False)
    entry = io.register_file(
        "snapshot/ext.parquet", producer="atom-export", description="d", layout=tmp_layout
    )
    assert entry["rows"] == 3 and entry["sha256"] == io.sha256_file(p)
    with pytest.raises(ManifestError, match="missing"):
        io.register_file("snapshot/none.parquet", producer="x", description="d", layout=tmp_layout)


# --- inputs ------------------------------------------------------------------------------------------


def put_input(lay: Layout, rel: str = "market/in.parquet") -> Path:
    p = lay.data / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    frame().to_parquet(p, index=False)
    return p


def test_inputs_fingerprinted_once_and_change_detected(tmp_layout: Layout) -> None:
    p = put_input(tmp_layout)
    df = io.read_data_parquet("market/in.parquet", layout=tmp_layout)
    pd.testing.assert_frame_equal(df, frame())
    rec = io.load_manifest(tmp_layout)["inputs"]["Data/market/in.parquet"]
    assert rec["sha256"] == io.sha256_file(p) and rec["size"] == p.stat().st_size
    assert io.record_input("market/in.parquet", layout=tmp_layout)["first_read_at"] == rec["first_read_at"]
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    with pytest.raises(InputChanged):
        io.read_data_parquet("market/in.parquet", layout=tmp_layout)


def test_inputs_must_be_inside_data(tmp_layout: Layout, tmp_path: Path) -> None:
    outside = tmp_path / "outside.parquet"
    frame().to_parquet(outside, index=False)
    with pytest.raises(ManifestError, match="not inside Data"):
        io.record_input(outside, layout=tmp_layout)
    with pytest.raises(ManifestError, match="not found"):
        io.record_input("market/none.parquet", layout=tmp_layout)


def test_pickle_input(tmp_layout: Layout) -> None:
    p = tmp_layout.data / "market" / "x.pkl"
    p.parent.mkdir(parents=True)
    pd.to_pickle({"A": pd.Series([1.0])}, p)
    obj = io.read_data_pickle("market/x.pkl", layout=tmp_layout)
    assert list(obj) == ["A"]
    assert "Data/market/x.pkl" in io.load_manifest(tmp_layout)["inputs"]


def test_copy_data_file_is_byte_identical(tmp_layout: Layout) -> None:
    src = put_input(tmp_layout)
    entry = io.copy_data_file("market/in.parquet", "market/copy.parquet", producer="t", description="d",
                              layout=tmp_layout)  # fmt: skip
    m = io.load_manifest(tmp_layout)
    assert entry["sha256"] == io.sha256_file(src) == m["inputs"]["Data/market/in.parquet"]["sha256"]
    assert m["artifacts"]["work/market/copy.parquet"]["rows"] == 3


# --- manifest check ----------------------------------------------------------------------------------


def test_manifest_check_ok_and_failures(tmp_layout: Layout) -> None:
    assert io.manifest_check(layout=tmp_layout).ok  # empty repo: nothing to check
    write(tmp_layout)
    put_input(tmp_layout)
    io.read_data_parquet("market/in.parquet", layout=tmp_layout)
    rep = io.manifest_check(layout=tmp_layout)
    assert not rep.ok and any("DATA_CONTRACT" in e for e in rep.errors)
    contract(tmp_layout)
    assert io.manifest_check(layout=tmp_layout).ok
    assert io.manifest_check(deep=True, layout=tmp_layout).ok

    stray = tmp_layout.work / "stray.parquet"
    frame().to_parquet(stray, index=False)
    assert any("unregistered" in e for e in io.manifest_check(layout=tmp_layout).errors)
    stray.unlink()

    frame().iloc[:1].to_parquet(tmp_layout.work / "demo" / "a.parquet", index=False)
    assert any("sha256 mismatch" in e for e in io.manifest_check(layout=tmp_layout).errors)


def test_manifest_check_contract_sha_must_match(tmp_layout: Layout) -> None:
    write(tmp_layout)
    contract(tmp_layout)
    p = tmp_layout.docs / "DATA_CONTRACT.md"
    sha = io.load_manifest(tmp_layout)["artifacts"]["work/demo/a.parquet"]["sha256"]
    p.write_text(p.read_text(encoding="utf-8").replace(sha, "0" * 64), encoding="utf-8")
    errors = io.manifest_check(layout=tmp_layout).errors
    assert errors == ["docs/DATA_CONTRACT.md sha256 for work/demo/a.parquet differs from the manifest"]


def test_manifest_check_detects_changed_input(tmp_layout: Layout) -> None:
    p = put_input(tmp_layout)
    io.read_data_parquet("market/in.parquet", layout=tmp_layout)
    with p.open("ab") as fh:
        fh.write(b"x")
    assert any("input changed" in e for e in io.manifest_check(layout=tmp_layout).errors)
