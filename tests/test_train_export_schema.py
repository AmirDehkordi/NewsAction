"""The Kaggle dataset (PRD NA-08 S2, AC1, AC2): no val-B / test labels, private, masked, third-party OK.

The synthetic tests run the export's own code path (``state_variants`` → ``build_examples`` →
``split_files``), so adding a label column to the val-B or test file in the code turns them red. The
integration tests read the built ``work/kaggle/dataset`` (skipped before the export has run).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from newsaction import io
from newsaction.paths import ROOT
from newsaction.states.questions import canonical_json
from newsaction.train import (
    REACTION_BLOCK,
    SOURCES,
    Source,
    load_training_config,
    option_keys,
    training_questions,
)
from newsaction.train.kaggle_export import (
    EVAL_COLUMNS,
    STATE_COLUMNS,
    ExportError,
    assert_no_labels,
    build_examples,
    check_states,
    draw,
    drop_blocks,
    kernel_metadata,
    length_check,
    metadata,
    notebook_with_params,
    params_cell_source,
    run_parameters,
    split_files,
    state_variants,
)

CFG = load_training_config()
DAYS = {
    "train": date(2025, 1, 6),
    "val_a": date(2025, 8, 4),
    "val_b": date(2025, 11, 3),
    "test": date(2026, 2, 2),
}


def _state(call: str, i: int) -> str:
    s: dict[str, Any] = {
        "attention": {"articles_vs_usual": "normal"},
        "company": {"sector": "Energy"},
        "market": {"vix_change": "small rise"},
        "news": [{"headline": f"headline {i}", "snippet": "text"}],
    }
    if call == "B":
        s[REACTION_BLOCK] = {"stock_move_vs_market_and_sector": "small rise"}
    return canonical_json(s)


def synthetic_states(n: int = 60) -> dict[Source, pd.DataFrame]:
    out: dict[Source, pd.DataFrame] = {}
    for source in SOURCES:
        call, window = source.split("_")
        rows = []
        for split, day in DAYS.items():
            if call == "B" and split == "test":
                continue
            for c in range(n):
                rows.append(
                    {
                        "event_id": f"{window}:{c}:{day}",
                        "company_id": c,
                        "session": day,
                        "split": split,
                        "window": window,
                        "call": call,
                        "encoding": "E3",
                        "masked": True,
                        "state_json": _state(call, c),
                        "n_tokens_state": 40,
                        "third_party_ok_all": True,
                    }
                )
        out[source] = pd.DataFrame(rows, columns=list(STATE_COLUMNS))
    return out


def synthetic_labels(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for split, day in DAYS.items():
        if split == "test":
            continue
        for c in range(n):
            rows.append(
                {
                    "company_id": c,
                    "session": day,
                    "split": split,
                    "embargo": c < 3,
                    "react_label": int(rng.integers(9)),
                    "mag_label": int(rng.integers(5)),
                    "cont_label": int(rng.integers(3)) if c % 2 else pd.NA,
                    "react_horizon_end": day,
                    "cont_horizon_end": day,
                }
            )
    df = pd.DataFrame(rows)
    for col in ("react_label", "mag_label", "cont_label"):
        df[col] = df[col].astype("Int8")
    return df


def _lengths(texts: list[str]) -> list[int]:
    return [len(t) // 4 for t in texts]


@pytest.fixture(scope="module")
def files() -> dict[str, pd.DataFrame]:
    variants = state_variants(synthetic_states(), CFG, _lengths)
    ex = build_examples(variants, synthetic_labels(), training_questions(CFG), CFG)
    return split_files(ex)


def test_val_b_and_test_files_have_no_label_column(files: dict[str, pd.DataFrame]) -> None:
    for name in ("val_b", "test_callA"):
        cols = list(files[name].columns)
        assert cols == list(EVAL_COLUMNS), name
        assert not [c for c in cols if "label" in c.lower() or c in {"e5", "z_cc", "y2", "g_d2", "embargo"}]


def test_train_and_val_a_carry_labels(files: dict[str, pd.DataFrame]) -> None:
    assert "label_index" in files["train"] and files["train"]["label_index"].notna().all()
    assert {"label_index", "embargo"} <= set(files["val_a"].columns)
    assert files["val_a"]["label_index"].isna().any()  # the cont rows without a label are kept
    assert files["val_a"]["embargo"].any()


def test_test_file_holds_call_a_only(files: dict[str, pd.DataFrame]) -> None:
    assert set(files["test_callA"]["call"]) == {"A"}
    assert set(files["val_b"]["call"]) == {"A", "B"}
    assert set(files["test_callA"]["window"]) == {"W0", "W2"}


def test_block_dropout_copies(files: dict[str, pd.DataFrame]) -> None:
    for name in ("val_a", "val_b", "test_callA"):
        assert set(files[name]["variant"]) == {"full"}
    tr = files["train"]
    nr = tr[tr["variant"] == "no_reaction"]
    assert len(nr) and set(nr["call"]) == {"B"} and set(nr["question_id"]) == {"react"}
    assert all(REACTION_BLOCK not in json.loads(s) for s in nr["state_json"])
    nc = tr[tr["variant"] == "no_context"]
    assert len(nc)
    assert all(not ({"attention", "company", "market"} & set(json.loads(s))) for s in nc["state_json"])
    full = tr[tr["variant"] == "full"].set_index(["event_id", "call", "question_id"])["label_index"]
    for r in pd.concat([nr, nc]).itertuples():
        assert r.label_index == full[(r.event_id, r.call, r.question_id)]  # a copy keeps the original's label


def test_draw_is_stable_and_uniform() -> None:
    assert draw(2026, "reaction", "B_W2", "W2:1:2025-01-06") == draw(
        2026, "reaction", "B_W2", "W2:1:2025-01-06"
    )
    u = np.array([draw(2026, "context", "A_W0", f"W0:{i}:x") for i in range(20_000)])
    assert abs(u.mean() - 0.5) < 0.01 and abs((u < 0.3).mean() - 0.3) < 0.015


def test_drop_blocks_is_canonical_and_strict() -> None:
    s = _state("B", 1)
    out = drop_blocks(s, [REACTION_BLOCK])
    assert REACTION_BLOCK not in json.loads(out) and out == canonical_json(json.loads(out))
    with pytest.raises(ExportError):
        drop_blocks(_state("A", 1), [REACTION_BLOCK])


def test_assert_no_labels_refuses_any_extra_column(files: dict[str, pd.DataFrame]) -> None:
    for name in ("val_b", "test_callA"):
        with pytest.raises(ExportError):
            assert_no_labels(files[name].assign(label_index=0), name)
        with pytest.raises(ExportError):
            assert_no_labels(files[name][list(EVAL_COLUMNS)[::-1]], name)


def test_check_states_refuses_governance_breaks() -> None:
    st = synthetic_states(4)
    check_states(st["A_W0"], "A_W0", CFG)
    with pytest.raises(ExportError, match="unmasked"):
        check_states(st["A_W0"].assign(masked=False), "A_W0", CFG)
    with pytest.raises(ExportError, match="third-party"):
        check_states(st["A_W0"].assign(third_party_ok_all=False), "A_W0", CFG)
    b_test = st["B_W2"].iloc[:1].assign(split="test")
    with pytest.raises(ExportError, match="test-period Call B"):
        check_states(b_test, "B_W2", CFG)
    with pytest.raises(ExportError, match="encoding"):
        check_states(st["A_W0"].assign(encoding="E1"), "A_W0", CFG)


def test_split_files_refuses_call_b_in_the_test_file(files: dict[str, pd.DataFrame]) -> None:
    variants = state_variants(synthetic_states(), CFG, _lengths)
    ex = build_examples(variants, synthetic_labels(), training_questions(CFG), CFG)
    ex.loc[ex["split"] == "test", "call"] = "B"
    with pytest.raises(ExportError):
        split_files(ex)


def test_question_json_keeps_the_battery_option_order(files: dict[str, pd.DataFrame]) -> None:
    qs = training_questions(CFG)
    for qid, qj in files["val_b"].groupby("question_id")["question_json"].first().items():
        assert json.loads(qj) == qs[str(qid)]
        assert option_keys(json.loads(qj)) == option_keys(qs[str(qid)])


def test_length_check_counts_cut_states() -> None:
    ex = pd.DataFrame(
        {
            "example_id": ["a", "b", "c"],
            "event_id": ["e1", "e2", "e3"],
            "split": "train",
            "question_id": ["react", "react", "mag"],
            "n_tokens_state": [877, 878, 940],
        }
    )
    out = length_check(ex, {"react": 143, "mag": 77, "cont": 64}, 1024)
    assert out["room_by_question"] == {"react": 877, "mag": 943, "cont": 956}
    assert out["cut_example_ids"] == ["b"] and out["max_excess_tokens"] == 1
    assert out["max_len_without_cut"] == 1025


def test_dataset_metadata_is_private() -> None:
    meta = metadata(CFG)
    assert meta["isPrivate"] is True and meta["id"] == CFG.export.dataset_id
    assert len(meta["licenses"]) == 1


def test_kernels_are_private_gpu_t4x2_with_the_dataset_attached() -> None:
    for spec in CFG.kaggle.runs:
        meta = kernel_metadata(spec, CFG)
        assert meta["is_private"] is True and meta["enable_gpu"] is True and meta["enable_internet"] is True
        assert meta["machine_shape"] == "NvidiaTeslaT4" and meta["dataset_sources"] == [CFG.export.dataset_id]
        assert meta["id"].endswith("/" + meta["title"])  # Kaggle derives the slug from the title


def test_parameters_cell_round_trips() -> None:
    nb = json.loads(
        (ROOT / "src" / "newsaction" / "train" / "notebook" / "newsaction_laya_fin.ipynb").read_text()
    )
    for spec in CFG.kaggle.runs:
        params = run_parameters(spec, CFG)
        ns: dict[str, Any] = {}
        exec(params_cell_source(params), ns)
        assert {k: ns[k] for k in params} == params
        out = notebook_with_params(nb, params)
        changed = [i for i, (a, b) in enumerate(zip(nb["cells"], out["cells"], strict=True)) if a != b]
        assert len(changed) <= 1 and all("parameters" in nb["cells"][i]["metadata"]["tags"] for i in changed)


# --- the built dataset (integration) ----------------------------------------------------------------

DS = ROOT / "work" / "kaggle" / "dataset"


@pytest.fixture(scope="module")
def built() -> dict[str, pd.DataFrame]:
    if not (DS / "sha256_manifest.json").is_file():
        pytest.skip("work/kaggle/dataset is absent (run the NA-08 export stage)")
    return {
        n: io.read_parquet(f"kaggle/dataset/{n}.parquet") for n in ("train", "val_a", "val_b", "test_callA")
    }


def test_built_eval_files_have_no_label_column(built: dict[str, pd.DataFrame]) -> None:
    for name in ("val_b", "test_callA"):
        assert pq.read_schema(DS / f"{name}.parquet").names == list(EVAL_COLUMNS)
        assert list(built[name].columns) == list(EVAL_COLUMNS)
    assert json.loads((DS / "dataset-metadata.json").read_text())["isPrivate"] is True


def test_built_manifest_matches_the_files(built: dict[str, pd.DataFrame]) -> None:
    manifest = json.loads((DS / "sha256_manifest.json").read_text())
    assert set(manifest["files"]) == {
        "train.parquet",
        "val_a.parquet",
        "val_b.parquet",
        "test_callA.parquet",
        "dataset_info.json",
    }
    for name, entry in manifest["files"].items():
        assert io.sha256_file(DS / name) == entry["sha256"]


def test_built_states_are_the_na04_states_masked_and_third_party_ok(built: dict[str, pd.DataFrame]) -> None:
    for source in SOURCES:
        src = io.read_parquet(
            CFG.states[source], columns=["event_id", "state_json", "masked", "third_party_ok_all"]
        )
        assert src["masked"].all() and src["third_party_ok_all"].all()
        ref = dict(zip(src["event_id"], src["state_json"], strict=True))
        call, window = source.split("_")
        for name, df in built.items():
            part = df[(df["call"] == call) & (df["window"] == window) & (df["variant"] == "full")]
            assert (part["state_json"] == part["event_id"].map(ref)).all(), (name, source)
    tr = built["train"]
    a2 = io.read_parquet(CFG.states["A_W2"], columns=["event_id", "state_json"])
    ref2 = dict(zip(a2["event_id"], a2["state_json"], strict=True))
    nr = tr[tr["variant"] == "no_reaction"]
    assert (nr["state_json"] == nr["event_id"].map(ref2)).all()  # the copy is the event's Call A D2 state


def test_built_dates_and_labels(built: dict[str, pd.DataFrame]) -> None:
    from newsaction.config import load_splits

    splits = load_splits().splits
    for name, (split, _) in {
        "train": ("train", 0),
        "val_a": ("val_a", 0),
        "val_b": ("val_b", 0),
        "test_callA": ("test", 0),
    }.items():
        sessions = pd.to_datetime(built[name]["event_id"].str.rsplit(":", n=1).str[1]).dt.date
        assert sessions.min() >= splits[split].start and sessions.max() <= splits[split].end
    labels = io.read_parquet("kaggle/labels.parquet")
    col = {"react": "react_label", "mag": "mag_label", "cont": "cont_label"}
    for name in ("train", "val_a"):
        df = built[name].copy()
        df["company_id"] = df["event_id"].str.split(":").str[1].astype("int64")
        df["session"] = pd.to_datetime(df["event_id"].str.rsplit(":", n=1).str[1]).dt.date
        m = df.merge(labels, on=["company_id", "session"], how="left", validate="many_to_one")
        want = pd.Series([r[col[q]] for q, r in zip(m["question_id"], m.to_dict("records"), strict=True)])
        got = m["label_index"]
        assert ((want.isna() & got.isna()) | (want.astype("float") == got.astype("float"))).all(), name
    tr = built["train"]
    assert tr["label_index"].notna().all()


def test_built_head_lengths_are_laya_s_rendering(built: dict[str, pd.DataFrame]) -> None:
    pytest.importorskip("laya")
    from newsaction.events.tokens import tokenizer
    from newsaction.train.kaggle_export import head_lengths

    info = json.loads((DS / "dataset_info.json").read_text())
    try:
        tok = tokenizer()
    except OSError:
        pytest.skip("the ModernBERT-large tokenizer is not in the local cache")
    heads = head_lengths(tok, training_questions(CFG), CFG.model.head_max_len)
    assert {q: v["head_tokens"] for q, v in info["questions"].items()} == heads
    assert CFG.model.head_max_len == max(heads.values()) == 143
    assert info["truncation"]["examples_cut"] == 5 and info["truncation"]["max_len_without_cut"] == 1036
