"""PRD NA-04 S5 / AC4 / AC6 on the built state files.

- Schema, canonical JSON, sha256, fixed top-level keys, third-party rule.
- AC4: E2 context / reaction blocks carry no digit; E3 blocks carry digits only inside "≈k.k×". The three
  PREREG §6.11 tier phrases are fixed labels and are removed before the check (REPORT §AC4).
- AC6: no Call B state of the test period; no NA-04 entry in ledgers/test_access.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache

import pandas as pd
import pytest

from newsaction import io
from newsaction.config import load_splits
from newsaction.paths import ROOT
from newsaction.states.build import OUTPUT_COLUMNS
from newsaction.states.codebook import load_codebook
from newsaction.states.questions import canonical_json

MAIN = ("callA_d0_E3", "callA_d2_E3", "callB_d2_E3", "market_E3")
SAMPLES = ("callA_d0_E0", "callA_d0_E1", "callA_d0_E2", "callA_d0_E3", "callA_d0_E4", "unmasked")
KEYS = {
    "A": {"company", "market", "attention", "news"},
    "B": {"company", "market", "attention", "news", "reaction_so_far"},
    "M": {"market", "news"},
}
TIER_PHRASES = tuple(load_codebook().tier.values())


@cache
def states(rel: str) -> pd.DataFrame:
    if not (ROOT / "work" / rel).is_file():
        pytest.skip(f"work/{rel} is absent (run the NA-04 build)")
    return io.read_parquet(rel)


def all_files() -> list[str]:
    return [f"states/{n}.parquet" for n in MAIN] + [f"states/samples/{n}.parquet" for n in SAMPLES]


@pytest.mark.parametrize("rel", all_files())
def test_schema_json_and_hash(rel: str) -> None:
    df = states(rel)
    assert tuple(df.columns) == OUTPUT_COLUMNS
    assert df["event_id"].is_unique and len(df) > 0
    assert bool(df["third_party_ok_all"].all())
    assert (df["n_articles"] >= 1).all()
    sub = df.sample(min(len(df), 500), random_state=7)
    for js, sha, call, n in zip(
        sub["state_json"], sub["state_sha256"], sub["call"], sub["n_articles"], strict=True
    ):
        assert hashlib.sha256(js.encode("utf-8")).hexdigest() == sha
        obj = json.loads(js)
        assert canonical_json(obj) == js
        assert set(obj) == KEYS[call]
        assert len(obj["news"]) == n
        assert all(set(item) == {"headline", "snippet", "source_type", "timing"} for item in obj["news"])


def test_splits_and_counts() -> None:
    """One state per event, except events whose every article is a move explainer or lost its text in masking
    (build_states.json)."""
    built = json.loads((ROOT / "artifacts" / "NA-04" / "build_states.json").read_text(encoding="utf-8"))
    d0 = io.read_parquet("events/events_d0.parquet", columns=["event_id"])
    d2 = io.read_parquet("events/events_d2.parquet", columns=["event_id", "split"])
    b_ids = set(d2.loc[d2["split"].isin(["train", "val_a", "val_b"]), "event_id"])
    for name, ids in (
        ("callA_d0_E3", set(d0["event_id"])),
        ("callA_d2_E3", set(d2["event_id"])),
        ("callB_d2_E3", b_ids),
    ):
        got = set(states(f"states/{name}.parquet")["event_id"])
        assert got <= ids
        n = built[name]
        assert len(ids - got) == n["events_without_text"] + n["events_all_excluded"], name
        # excluded articles (explainers, TradingView) empty about 1.2% of D0 events (PREREG §15 NA-04 row 6)
        assert n["events_without_text"] <= 20 and n["events_all_excluded"] <= 0.02 * len(ids), name
    a2 = set(states("states/callA_d2_E3.parquet")["event_id"])
    assert set(states("states/callB_d2_E3.parquet")["event_id"]) == a2 & b_ids


def test_call_a_d2_and_call_b_share_the_news() -> None:
    a = states("states/callA_d2_E3.parquet").set_index("event_id")["state_json"]
    b = states("states/callB_d2_E3.parquet").set_index("event_id")["state_json"]
    for eid in b.index[:2000]:
        assert json.loads(a[eid])["news"] == json.loads(b[eid])["news"]


def test_no_test_period_call_b() -> None:
    """AC6."""
    test_start = load_splits().splits["test"].start
    for rel in all_files():
        df = states(rel)
        b = df.loc[df["call"] == "B"]
        assert not (b["split"] == "test").any(), rel
        assert not (b["session"] >= test_start).any(), rel
    r = io.read_parquet("states/reaction_d2.parquet", columns=["session"])
    assert not (r["session"] >= test_start).any()


def test_access_ledger_has_no_na04_entry() -> None:
    lines = (ROOT / "ledgers" / "test_access.jsonl").read_text(encoding="utf-8").splitlines()
    for ln in lines:
        rec = json.loads(ln)
        assert "states" not in str(rec.get("caller", "")) and "NA-04" not in ln, ln


def _blocks(obj: dict[str, object]) -> list[str]:
    out = []
    for key in ("company", "market", "attention", "reaction_so_far"):
        if key in obj:
            text = json.dumps(obj[key], ensure_ascii=False)
            for phrase in TIER_PHRASES:
                text = text.replace(phrase, "")
            out.append(text)
    return out


@pytest.mark.parametrize("rel", ["states/samples/callA_d0_E2.parquet"])
def test_e2_blocks_have_no_digits(rel: str) -> None:
    for js in states(rel)["state_json"]:
        for text in _blocks(json.loads(js)):
            assert not re.search(r"\d", text), text


@pytest.mark.parametrize(
    "rel", ["states/samples/callA_d0_E3.parquet", "states/callB_d2_E3.parquet", "states/market_E3.parquet"]
)
def test_e3_digits_only_in_multiples(rel: str) -> None:
    df = states(rel)
    for js in df["state_json"].head(3000):
        for text in _blocks(json.loads(js)):
            assert not re.search(r"\d", re.sub(r"≈\d+\.\d×", "", text)), text


def test_sample_events_are_shared_across_encodings() -> None:
    ids = [
        set(states(f"states/samples/callA_d0_{e}.parquet")["event_id"])
        for e in ("E0", "E1", "E2", "E3", "E4")
    ]
    assert all(i == ids[0] for i in ids)
    df = states("states/samples/callA_d0_E3.parquet")
    assert df["split"].value_counts().to_dict() == {"val_a": 1500, "val_b": 1500}
    main = states("states/callA_d0_E3.parquet").set_index("event_id")["state_sha256"]
    assert (
        df.set_index("event_id")["state_sha256"] == main.loc[df["event_id"]]
    ).all()  # same states as the main E3
    twin = states("states/samples/unmasked.parquet")
    assert len(twin) == 1000 and set(twin["split"]) == {"val_a"} and not twin["masked"].any()
