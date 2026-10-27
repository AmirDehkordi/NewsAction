"""NA-07 runner guards (PRD NA-07 AC3, CLAUDE.md B9 / C13): val-B is read only for the S2 check, every
state belongs to the split its part may use, the numeracy states change only ``reaction_so_far``, and the
frozen.yaml writer touches only its own section."""

from __future__ import annotations

import json

import pytest
import yaml

from newsaction import io
from newsaction.config import load_frozen
from newsaction.encoding import SAMPLES, EncodingError, load_encoding_config
from newsaction.encoding import run as er
from newsaction.paths import ROOT, Layout


def _ctx(layout: Layout) -> er.Ctx:
    return er.Ctx.load(layout)


def _set_val_b(layout: Layout, value: bool) -> None:
    path = layout.configs / "frozen.yaml"
    text = path.read_text(encoding="utf-8")
    new = "\n".join(
        (f"allow_val_b: {'true' if value else 'false'}" if ln.startswith("allow_val_b:") else ln)
        for ln in text.splitlines()
    )
    path.write_text(new + "\n", encoding="utf-8")


def test_val_b_targets_need_the_gate_and_a_non_default_best(tmp_layout: Layout) -> None:
    ctx = _ctx(tmp_layout)
    _set_val_b(tmp_layout, False)
    with pytest.raises(EncodingError, match="allow_val_b"):
        er.targets(ctx, er.VAL_B)
    _set_val_b(tmp_layout, True)
    with pytest.raises(EncodingError, match="select"):
        er.targets(ctx, er.VAL_B)  # no selection yet
    sel = tmp_layout.root / er.SELECTION_FILE
    sel.parent.mkdir(parents=True)
    sel.write_text(json.dumps({"best": "E3"}), encoding="utf-8")
    with pytest.raises(EncodingError, match="default"):
        er.targets(ctx, er.VAL_B)


def test_parts_and_tags() -> None:
    assert er.part_of(er.tag_search("s1", "E0")) == "s1" and er.part_of(er.tag_search("s2", "E3")) == "s2"
    assert (
        er.part_of(er.tag_numeracy("E1")) == "s3"
        and er.part_of(er.TAG_S4_A) == "s4"
        and er.part_of("s2a") == "other"
    )
    assert er.PART_SPLIT == {"s1": "val_a", "s2": "val_b", "s3": "val_a", "s4": "val_a"}


def test_write_frozen_section_round_trips_and_keeps_the_rest(tmp_layout: Layout) -> None:
    path = tmp_layout.configs / "frozen.yaml"
    before = yaml.safe_load(path.read_text(encoding="utf-8"))
    entry = {
        "present": True,
        "slope": 0.123456789012,
        "corr": 0.5,
        "calls_per_event": 2,
        "by_model": {"a/b": True},
    }
    er.write_frozen_section(tmp_layout, "anchoring", "NA-07 test", entry)
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["anchoring"] == entry
    assert {k: v for k, v in after.items() if k != "anchoring"} == {
        k: v for k, v in before.items() if k != "anchoring"
    }


# --- the registered samples (integration; skipped before the samples stage) -------------------------------


@pytest.fixture(scope="module")
def ctx() -> er.Ctx:
    if not (ROOT / "work" / SAMPLES).is_file():
        pytest.skip("work/dm/encoding/samples.parquet is absent (run --stage samples)")
    return er.Ctx.load()


def test_samples_are_val_a_and_val_b_after_the_embargo(ctx: er.Ctx) -> None:
    s = ctx.samples()
    c = load_encoding_config()
    assert s["split"].value_counts().to_dict() == {"val_a": c.samples.val_a, "val_b": c.samples.val_b}
    assert s.loc[s["split"] == "val_a", "session"].min().isoformat() == "2025-07-09"
    assert s.loc[s["split"] == "val_b", "session"].min().isoformat() == "2025-10-08"
    assert s.loc[s["split"] == "val_b", "session"].max().isoformat() <= "2025-12-31"
    assert s["anchoring"].sum() == c.samples.val_a and not s.loc[s["split"] == "val_b", "anchoring"].any()
    assert s["numeracy"].sum() == c.numeracy.n_news and s.loc[s["numeracy"], "split"].eq("val_a").all()


def test_search_specs_use_the_right_split(ctx: er.Ctx) -> None:
    m = ctx.models()[0]
    for e in ("E0", "E3"):
        a = er.search_specs(ctx, m, e, er.VAL_A)
        assert len(a) == 1500 and {x.info.split for x in a} == {"val_a"}
        assert {x.tag for x in a} == {f"na07_s1_{e}"} and all(x.info.masked for x in a)


def test_numeracy_states_change_only_the_reaction(ctx: er.Ctx) -> None:
    items = er.numeracy_items(ctx, ctx.models()[0], "E3")
    c = load_encoding_config().numeracy
    assert len(items) == c.n_news * 2 * len(c.magnitudes)
    base = ctx.d2_states("B").set_index("event_id")
    for it in items[:: len(c.magnitudes)]:
        orig = json.loads(str(base.loc[it.event_id, "state_json"]))
        st = it.spec.request.state
        assert isinstance(st, dict)
        assert {k: v for k, v in st.items() if k != "reaction_so_far"} == {
            k: v for k, v in orig.items() if k != "reaction_so_far"
        }
        assert it.spec.info.split == "val_a" and it.spec.info.probe == "numeracy" and it.spec.info.call == "B"


def test_anchoring_pairs_share_everything_but_the_reaction(ctx: er.Ctx) -> None:
    a = ctx.d2_states("A").set_index("event_id")
    b = ctx.d2_states("B").set_index("event_id")
    assert set(a.index) == set(b.index) == set(ctx.ids(er.VAL_A, "d2_event_id"))
    for e in list(a.index)[:200]:
        sb = json.loads(str(b.loc[e, "state_json"]))
        sb.pop("reaction_so_far")
        assert json.loads(str(a.loc[e, "state_json"])) == sb


def test_cache_audit_artifact_is_clean() -> None:
    path = ROOT / "artifacts" / "NA-07" / "cache_audit.json"
    if not path.is_file():
        pytest.skip("NA-07 has not written its cache audit yet")
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["ok"] and audit["n_violations"] == 0
    for part, counts in audit["used_requests_by_part"].items():
        want = er.PART_SPLIT[part]
        assert counts["outside"] == 0 and set(counts) - {"requests", "outside"} == {want}
    if load_frozen().encoding and not load_frozen().encoding["val_b_check"]["needed"]:  # type: ignore[index]
        assert "s2" not in audit["used_requests_by_part"]  # no val-B state when the best is E3


def test_work_files_carry_no_targets() -> None:
    for rel in ("dm/encoding/search.parquet", "dm/encoding/anchoring.parquet", "dm/encoding/confirm.parquet"):
        if (ROOT / "work" / rel).is_file():
            cols = io.read_parquet(rel).columns
            assert "z_cc" not in cols and "g" not in cols
