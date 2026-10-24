"""ATOM snapshot export (PRD NA-01 S1, AC1).

Unit tests cover the export script's pure helpers (it runs under ATOM's venv, so ATOM is imported
only inside its ``main``). Integration tests read work/snapshot/MANIFEST_snapshot.json and parquet
*metadata*: the sealed files are never opened, and public price files are checked through their
row-group statistics only.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import export_atom_snapshot as ex
from newsaction import io
from newsaction.config import load_splits
from newsaction.paths import ROOT

SNAP = ROOT / "work" / "snapshot"
PRICE_FILES = ("prices_raw", "total_return_check")


def test_split_public_sealed_partitions_by_date() -> None:
    t = pa.table({"d": pa.array([date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 2)], pa.date32())})
    pub, sealed = ex.split_public_sealed(t, "d", date(2025, 12, 31), date(2026, 1, 2))
    assert pub.num_rows == 2 and sealed.num_rows == 1


def test_split_public_sealed_refuses_rows_between_the_splits() -> None:
    t = pa.table({"d": pa.array([date(2026, 1, 1)], pa.date32())})
    with pytest.raises(ValueError, match="between the splits"):
        ex.split_public_sealed(t, "d", date(2025, 12, 31), date(2026, 1, 2))


def test_blinding_bounds_come_from_splits_yaml() -> None:
    public_end, test_start = ex.blinding_bounds(ROOT / "configs" / "splits.yaml")
    splits = load_splits().splits
    assert (public_end, test_start) == (splits["val_b"].end, splits["test"].start)


def test_month_windows_cover_each_month_to_its_last_microsecond() -> None:
    w = ex.month_windows((2024, 12), (2025, 2))
    assert [s for s, _ in w] == [date(2024, 12, 1), date(2025, 1, 1), date(2025, 2, 1)]
    assert w[0][1] == datetime(2024, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)


def test_gics_rows_walk_the_hierarchy() -> None:
    sectors = [
        {"sector_id": 1, "taxonomy": "GICS", "code": "45", "level": 1, "name": "IT", "parent_id": None},
        {"sector_id": 2, "taxonomy": "GICS", "code": "4520", "level": 2, "name": "Hardware", "parent_id": 1},
    ]
    rows = ex.gics_rows(
        [{"symbol_id": 7, "sector_id": 2, "valid_from": None, "valid_to": None, "source": "x"}], sectors
    )
    assert (
        rows[0]["level1_name"] == "IT" and rows[0]["level2_code"] == "4520" and rows[0]["level3_name"] is None
    )


def test_pivot_estimates_one_row_per_snapshot() -> None:
    d = date(2025, 1, 2)
    long = [
        {
            "ticker": "A",
            "period_end_date": d,
            "as_of_date": d,
            "aggregation": "mean",
            "value": 1.5,
            "num_analysts": 9,
        },
        {
            "ticker": "A",
            "period_end_date": d,
            "as_of_date": d,
            "aggregation": "count",
            "value": 9.0,
            "num_analysts": 9,
        },
        {
            "ticker": "A",
            "period_end_date": d,
            "as_of_date": date(2025, 1, 3),
            "aggregation": "count",
            "value": 8.0,
        },
    ]
    out = ex.pivot_estimates(long, {"A": 6}, datetime(2025, 1, 31, tzinfo=UTC))
    assert len(out) == 1  # a count-only snapshot without a mean is dropped
    assert out[0]["symbol_id"] == 6 and out[0]["mean"] == 1.5 and out[0]["n"] == 9 and out[0]["count"] == 9.0


# --- integration (AC1) ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    path = SNAP / ex.MANIFEST_NAME
    if not path.is_file():
        pytest.skip("work/snapshot is absent (run scripts/export_atom_snapshot.py)")
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_ac1_read_only_transaction_and_equal_counts(manifest: dict[str, object]) -> None:
    ro = manifest["read_only"]
    counts = manifest["counts"]
    assert isinstance(ro, dict) and isinstance(counts, dict)
    assert ro["transaction_read_only"] == "on"
    assert "READ ONLY" in ro["statement"]
    assert counts["equal"] is True
    for key in ("before", "in_snapshot_before", "in_snapshot_after", "after"):
        assert counts[key] == counts["before"], key
    assert set(counts["before"]) == {"md.price_eod", "uni.member"}


def test_ac1_test_period_prices_only_under_sealed(manifest: dict[str, object]) -> None:
    test_start = load_splits().splits["test"].start
    files = manifest["files"]
    assert isinstance(files, list)
    by_path = {f["path"]: f for f in files}
    for name in PRICE_FILES:
        assert f"{ex.SEALED_DIR}/{name}_{test_start.year}.parquet" in by_path
        meta = pq.read_metadata(SNAP / f"{name}.parquet")  # statistics only, no data pages
        col = meta.schema.to_arrow_schema().get_field_index("trade_date")
        maxima = [meta.row_group(i).column(col).statistics.max for i in range(meta.num_row_groups)]
        assert max(maxima) < test_start, name
    sealed = [p for p in by_path if p.startswith(f"{ex.SEALED_DIR}/")]
    assert sorted(sealed) == sorted(f"{ex.SEALED_DIR}/{n}_{test_start.year}.parquet" for n in PRICE_FILES)
    assert all(by_path[p]["sealed"] for p in sealed)


def test_ac1_every_snapshot_file_registered_with_its_export_hash(manifest: dict[str, object]) -> None:
    arts = io.load_manifest()["artifacts"]
    files = manifest["files"]
    assert isinstance(files, list)
    for rec in files:
        entry = arts[f"work/snapshot/{rec['path']}"]
        assert entry["sha256"] == rec["sha256"], rec["path"]
        if rec["sealed"]:
            assert entry["rows"] is None and entry["columns"] is None  # registered by hash only
