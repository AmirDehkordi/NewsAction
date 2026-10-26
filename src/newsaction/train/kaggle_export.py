"""The private Kaggle dataset of NA-08 (PRD NA-08 S2) and one kernel directory per planned run (S6).

``work/kaggle/dataset/`` holds four example files, the notebook's metadata and the sha256 manifest:

- ``train.parquet`` and ``val_a.parquet`` carry ``label_index``. Train keeps only labelled examples; val-A
  keeps every state, with a null label where the label is purged or missing, plus ``embargo`` (the first 5
  sessions, which early stopping, the temperatures and every val-A metric leave out, PREREG §4.2).
- ``val_b.parquet`` (Call A and Call B states) and ``test_callA.parquet`` (Call A on D0 and D2 only) have
  **no label column**: their columns are exactly ``EVAL_COLUMNS`` (``assert_no_labels``). Val-B and test
  labels never leave this machine (PREREG §9.3, CLAUDE.md D16).
- ``dataset_info.json``: the questions in Laya's input format, their head lengths in Laya's rendering, the
  sequence-length check, counts and definitions. ``sha256_manifest.json``: sha256, bytes, rows and columns of
  every file above. ``dataset-metadata.json``: Kaggle's metadata (private).

An example is one (state variant, question) pair. Its ``state_json`` is the NA-04 state, byte for byte
(``variant`` ``full``), or a train copy with one block removed (PREREG §9.1 block dropout; a draw
u = sha256("{seed}:{block}:{source}:{event_id}") / 2^256 per state):

- ``no_reaction``: a Call B state with u < 0.3 gets a copy without ``reaction_so_far``, asked the react
  question. The copy is byte-identical to the event's Call A D2 state (NA-04 builds both from the same news),
  so it adds weight, not a new input (REPORT).
- ``no_context``: any train state with u < 0.1 gets a copy without the context blocks (attention, company,
  market), asked the source's questions with the same labels.

Governance (asserted): only masked, third-party-OK states of the configured encoding; no test-period Call B
state; every state plus its question fits ``model.max_len`` except the states counted in
``dataset_info.json`` ``truncation``. Each written file is registered in ``work/MANIFEST.json``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final

import pandas as pd

from newsaction import io
from newsaction.config import load_splits
from newsaction.paths import Layout, resolve_layout
from newsaction.states import QUESTIONS_PATH
from newsaction.states.questions import canonical_json, sha256_file
from newsaction.train import (
    DATASET_DIR,
    EXPORT_FILES,
    KERNELS_DIR,
    LABELS,
    NOTEBOOK,
    PRODUCER,
    QUESTION_IDS,
    REACTION_BLOCK,
    SOURCES,
    TRAINING_CONFIG_PATH,
    VARIANTS,
    QuestionId,
    RunSpec,
    Source,
    TrainingConfig,
    load_training_config,
    option_keys,
    training_questions,
)

STATE_COLUMNS: Final = (
    "event_id",
    "company_id",
    "session",
    "split",
    "window",
    "call",
    "encoding",
    "masked",
    "state_json",
    "n_tokens_state",
    "third_party_ok_all",
)
EVAL_COLUMNS: Final = (
    "example_id",
    "event_id",
    "split",
    "call",
    "window",
    "variant",
    "question_id",
    "state_json",
    "question_json",
    "n_tokens_state",
)
TRAIN_COLUMNS: Final = (*EVAL_COLUMNS, "label_index")
VAL_A_COLUMNS: Final = (*TRAIN_COLUMNS, "embargo")
FILE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "train": TRAIN_COLUMNS,
    "val_a": VAL_A_COLUMNS,
    "val_b": EVAL_COLUMNS,
    "test_callA": EVAL_COLUMNS,
}
LABEL_OF: Final[dict[QuestionId, str]] = {"react": "react_label", "mag": "mag_label", "cont": "cont_label"}
INFO_FILE: Final = "dataset_info.json"
MANIFEST_FILE: Final = "sha256_manifest.json"
METADATA_FILE: Final = "dataset-metadata.json"
SPECIAL_TOKENS: Final = 3  # [CLS] instruction [SEP] options [SEP] -- the closing [SEP] after the state is +1
_FORBIDDEN_EVAL: Final = re.compile(r"label|target|e5|y2|z_|g_d2|ret|outcome|move_size", re.IGNORECASE)

Encode = Callable[[Sequence[str]], list[int]]


class ExportError(ValueError):
    """The dataset would break a governance rule (labels, masking, third-party, test-period Call B)."""


# --- pieces -----------------------------------------------------------------------------------------


def draw(seed: int, block: str, source: str, event_id: str) -> float:
    """A uniform draw in [0, 1) from sha256 (stable across runs, platforms and row orders)."""
    h = hashlib.sha256(f"{seed}:{block}:{source}:{event_id}".encode()).digest()
    return int.from_bytes(h, "big") / 2.0**256


def drop_blocks(state_json: str, blocks: Sequence[str]) -> str:
    """The canonical JSON of a state without ``blocks`` (each must be present)."""
    state = json.loads(state_json)
    missing = [b for b in blocks if b not in state]
    if missing:
        raise ExportError(f"state has no block(s) {missing}")
    for b in blocks:
        del state[b]
    return canonical_json(state)


def assert_no_labels(df: pd.DataFrame, name: str) -> None:
    """A val-B or test file has exactly ``EVAL_COLUMNS`` and nothing that looks like an outcome."""
    cols = tuple(df.columns)
    if cols != EVAL_COLUMNS:
        raise ExportError(f"{name}: columns {cols} are not exactly {EVAL_COLUMNS}")
    bad = [c for c in cols if _FORBIDDEN_EVAL.search(c)]
    if bad:  # pragma: no cover - EVAL_COLUMNS holds no such name (tested)
        raise ExportError(f"{name}: outcome-like columns {bad}")


def check_states(states: pd.DataFrame, source: Source, cfg: TrainingConfig) -> None:
    """Masked, third-party-OK states of the configured encoding and source; no test-period Call B state."""
    call, window = source.split("_")
    problems = []
    if not bool(states["masked"].all()):
        problems.append("an unmasked state")
    if not bool(states["third_party_ok_all"].all()):
        problems.append("a state with a non-third-party-OK article")
    if set(states["encoding"].unique()) != {cfg.encoding}:
        problems.append(f"encodings {sorted(states['encoding'].unique())} != {cfg.encoding}")
    if set(states["call"].unique()) != {call} or set(states["window"].unique()) != {window}:
        problems.append("states of another call or window")
    if call == "B" and bool((states["split"] == "test").any()):
        problems.append("a test-period Call B state (built only after the NA-11 freeze)")
    if not states["event_id"].is_unique:
        problems.append("duplicate event ids")
    if problems:
        raise ExportError(f"{source}: " + "; ".join(problems))


def head_lengths(
    tok: Any, questions: Mapping[QuestionId, dict[str, Any]], head_max_len: int
) -> dict[str, int]:
    """Tokens of each question's head in Laya's rendering, without the 3 special tokens.

    ``laya.common.build_head`` caps the head at ``head_max_len``; a question longer than that would lose
    instruction or option tokens, which is refused here (the operator's decision on NA-04 owner decision 2:
    the head length is the longest trained question).
    """
    from laya.common import build_head
    from laya.train import to_internal

    out: dict[str, int] = {}
    for qid, q in questions.items():
        full, _, _ = build_head(tok, to_internal(qid, q), 10_000)
        capped, markers, stats = build_head(tok, to_internal(qid, q), head_max_len)
        if (
            capped != full
            or stats["options_distinct"] != stats["options"]
            or len(markers) != len(option_keys(q))
        ):
            raise ExportError(f"{qid}: head_max_len {head_max_len} cuts the question ({len(full)} tokens)")
        out[qid] = len(full) - SPECIAL_TOKENS
    return out


def hf_lengths(tok: Any) -> Encode:
    def lengths(texts: Sequence[str]) -> list[int]:
        if not texts:
            return []
        return [len(ids) for ids in tok(list(texts), add_special_tokens=False)["input_ids"]]

    return lengths


# --- examples ---------------------------------------------------------------------------------------


def state_variants(
    states: Mapping[Source, pd.DataFrame], cfg: TrainingConfig, n_tokens: Encode
) -> pd.DataFrame:
    """Every state as ``full``; train states also as their block-dropout copies (PREREG §9.1)."""
    ex = cfg.export
    parts = []
    for source in SOURCES:
        s = states[source]
        keep = [
            "event_id",
            "company_id",
            "session",
            "split",
            "call",
            "window",
            "state_json",
            "n_tokens_state",
        ]
        base = s[keep]
        parts.append(base.assign(source=source, variant="full"))
        train = base[base["split"] == "train"]
        if source.startswith("B") and ex.reaction_dropout > 0:
            pick = [draw(ex.seed, "reaction", source, e) < ex.reaction_dropout for e in train["event_id"]]
            c = train[pick].copy()
            c["state_json"] = [drop_blocks(j, [REACTION_BLOCK]) for j in c["state_json"]]
            parts.append(c.assign(source=source, variant="no_reaction"))
        if ex.context_dropout > 0:
            pick = [draw(ex.seed, "context", source, e) < ex.context_dropout for e in train["event_id"]]
            c = train[pick].copy()
            c["state_json"] = [drop_blocks(j, ex.context_blocks) for j in c["state_json"]]
            parts.append(c.assign(source=source, variant="no_context"))
    out = pd.concat(parts, ignore_index=True)
    copies = out["variant"] != "full"
    out.loc[copies, "n_tokens_state"] = n_tokens(out.loc[copies, "state_json"].tolist())
    out["n_tokens_state"] = out["n_tokens_state"].astype("int64")
    return out


def build_examples(
    variants: pd.DataFrame,
    labels: pd.DataFrame,
    questions: Mapping[QuestionId, dict[str, Any]],
    cfg: TrainingConfig,
) -> pd.DataFrame:
    """One row per (state variant, question); labels attached for train and val-A only."""
    by_source = cfg.questions.by_source
    qjson = {qid: json.dumps(q, ensure_ascii=False, separators=(",", ":")) for qid, q in questions.items()}
    lab = labels[["company_id", "session", "embargo", *LABEL_OF.values()]]
    v = variants.merge(lab, on=["company_id", "session"], how="left", validate="many_to_one")
    rows = []
    for source in SOURCES:
        vs = v[v["source"] == source]
        for qid in by_source[source]:
            qs = vs if qid == "react" else vs[vs["variant"] != "no_reaction"]  # the copy is asked react only
            r = qs.assign(question_id=qid, question_json=qjson[qid])
            r["label_index"] = r[LABEL_OF[qid]].astype("Int8")
            rows.append(r)
    ex = pd.concat(rows, ignore_index=True)
    ex = ex[~((ex["split"] == "train") & ex["label_index"].isna())]
    ex["embargo"] = ex["embargo"].astype("boolean").fillna(False).astype(bool)
    ex["example_id"] = ex["event_id"] + "|" + ex["call"] + "|" + ex["variant"] + "|" + ex["question_id"]
    order: dict[str, dict[str, int]] = {
        "source": {s: i for i, s in enumerate(SOURCES)},
        "variant": {s: i for i, s in enumerate(VARIANTS)},
        "question_id": {s: i for i, s in enumerate(QUESTION_IDS)},
    }
    for col, rank in order.items():
        ex[f"_{col}"] = ex[col].map(rank)
    keys = ["split", "_source", "session", "event_id", "_variant", "_question_id"]
    ex = ex.sort_values(keys, kind="mergesort")
    if not ex["example_id"].is_unique:
        raise ExportError("example ids are not unique")
    return ex.drop(columns=[f"_{c}" for c in order]).reset_index(drop=True)


def split_files(examples: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The four dataset files with their exact columns (no label column in val-B and test)."""
    out: dict[str, pd.DataFrame] = {}
    for name, (split, _labelled) in EXPORT_FILES.items():
        part = examples[examples["split"] == split]
        if name == "test_callA" and bool((part["call"] != "A").any()):
            raise ExportError("the test file may hold Call A states only")
        out[name] = part[list(FILE_COLUMNS[name])].reset_index(drop=True)
    for name in ("val_b", "test_callA"):
        assert_no_labels(out[name], name)
    return out


def check_dates(examples: pd.DataFrame, labels: pd.DataFrame) -> dict[str, str]:
    """Train sessions and label horizons end inside train (PREREG §4.1, §9.3); returns the ranges."""
    train_end = load_splits().splits["train"].end
    tr = examples[examples["split"] == "train"]
    if tr.empty:
        raise ExportError("no train examples")
    if max(tr["session"]) > train_end:
        raise ExportError(f"a train example is dated after {train_end}")
    keys = labels[labels["split"] == "train"]
    horizons: list[date] = []
    for qid, col in LABEL_OF.items():
        asked = tr.loc[tr["question_id"] == qid, ["company_id", "session"]].drop_duplicates()
        used = keys.merge(asked, on=["company_id", "session"])
        hz = {"react": "react_horizon_end", "mag": "session", "cont": "cont_horizon_end"}[qid]
        ends = used.loc[used[col].notna(), hz]
        if len(ends):
            horizons.append(max(ends))
    last = max(horizons)
    if last > train_end:
        raise ExportError(f"a train label's horizon ends {last}, after {train_end}")
    return {
        "train_first_session": str(min(tr["session"])),
        "train_last_session": str(max(tr["session"])),
        "train_last_label_horizon": str(last),
    }


def length_check(examples: pd.DataFrame, heads: Mapping[str, int], max_len: int) -> dict[str, Any]:
    """Examples whose state would be cut: state + head + 3 special + closing [SEP] > max_len."""
    room = {q: max_len - h - SPECIAL_TOKENS - 1 for q, h in heads.items()}
    rooms = examples["question_id"].map(room).astype("int64").to_numpy()
    excess = examples["n_tokens_state"].to_numpy(dtype="int64") - rooms
    over = excess > 0
    cut = examples[over]
    size = cut.groupby(["split", "question_id"]).size()
    lv = size.index
    by = {
        f"{s}/{q}": int(n)
        for s, q, n in zip(lv.get_level_values(0), lv.get_level_values(1), size.to_numpy(), strict=True)
    }
    return {
        "max_len": max_len,
        "room_by_question": room,
        "examples_cut": int(over.sum()),
        "states_cut": int(cut["event_id"].nunique()),
        "cut_by_split_question": by,
        "max_excess_tokens": int(excess.max(initial=0)) if over.any() else 0,
        "cut_example_ids": sorted(cut["example_id"].tolist()),
        "max_len_without_cut": int((excess + max_len).max()),
    }


def counts(files: Mapping[str, pd.DataFrame]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, df in files.items():
        g = df.groupby(["call", "window", "variant", "question_id"], dropna=False)
        rows: dict[str, Any] = {}
        for (call, window, variant, qid), part in g:
            key = f"{call}_{window}/{variant}/{qid}"
            rows[key] = {"examples": len(part)}
            if "label_index" in part:
                rows[key]["labelled"] = int(part["label_index"].notna().sum())
            if "embargo" in part:
                rows[key]["embargo"] = int(part["embargo"].sum())
        out[name] = {"examples": len(df), "states": int(df["state_json"].nunique()), "by": rows}
    return out


# --- write ------------------------------------------------------------------------------------------


def metadata(cfg: TrainingConfig) -> dict[str, Any]:
    ex = cfg.export
    return {
        "title": ex.dataset_title,
        "id": ex.dataset_id,
        "licenses": [{"name": ex.license}],
        "isPrivate": True,
    }


def _write_json(path: Path, obj: Any) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    io.atomic_write_bytes(path, text.encode())


def manifest_of(dataset_dir: Path, names: Sequence[str]) -> dict[str, Any]:
    import pyarrow.parquet as pq

    files: dict[str, Any] = {}
    for name in names:
        p = dataset_dir / name
        entry: dict[str, Any] = {"sha256": io.sha256_file(p), "bytes": p.stat().st_size}
        if p.suffix == ".parquet":
            meta = pq.read_metadata(p)
            entry["rows"] = int(meta.num_rows)
            entry["columns"] = [f.name for f in meta.schema.to_arrow_schema()]
        files[name] = entry
    return {"version": 1, "files": files}


def load_states(cfg: TrainingConfig, layout: Layout | None = None) -> dict[Source, pd.DataFrame]:
    out: dict[Source, pd.DataFrame] = {}
    for source in SOURCES:
        df = io.read_parquet(cfg.states[source], columns=list(STATE_COLUMNS), layout=layout)
        check_states(df, source, cfg)
        out[source] = df
    return out


def run(
    layout: Layout | None = None,
    *,
    n_tokens: Encode | None = None,
    tok: Any = None,
    cfg: TrainingConfig | None = None,
) -> dict[str, Any]:
    """Build and write work/kaggle/dataset/ (S2); returns ``dataset_info``."""
    from newsaction.events.tokens import tokenizer

    lay = resolve_layout(layout)
    cfg = load_training_config() if cfg is None else cfg
    tok = tokenizer() if tok is None else tok
    n_tokens = hf_lengths(tok) if n_tokens is None else n_tokens
    questions = training_questions(cfg)
    heads = head_lengths(tok, questions, cfg.model.head_max_len)
    longest = max(heads.values())
    if cfg.model.head_max_len != longest:
        raise ExportError(
            f"head_max_len {cfg.model.head_max_len} is not the longest trained question ({longest})"
        )
    splits = {split for split, _ in EXPORT_FILES.values()}
    states = {s: df[df["split"].isin(splits)] for s, df in load_states(cfg, lay).items()}
    labels = io.read_parquet(LABELS, layout=lay)
    examples = build_examples(state_variants(states, cfg, n_tokens), labels, questions, cfg)
    dates = check_dates(examples, labels)
    lengths = length_check(examples, heads, cfg.model.max_len)
    files = split_files(examples)
    out_dir = lay.work / DATASET_DIR
    for name, df in files.items():
        io.write_parquet(
            df,
            f"{DATASET_DIR}/{name}.parquet",
            producer=PRODUCER,
            description=f"NA-08 S2: Kaggle dataset file {name} (masked {cfg.encoding} states x questions"
            + (", label_index" if EXPORT_FILES[name][1] else ", NO label column")
            + "); third-party OK; uploaded privately to Kaggle",
            layout=lay,
        )
    shas = io.load_manifest(lay)["artifacts"]
    info = {
        "version": 1,
        "chunk": "NA-08",
        "encoding": cfg.encoding,
        "questions": {
            qid: {
                "question": questions[qid],
                "type": questions[qid]["type"],
                "k": len(option_keys(questions[qid])),
                "options": option_keys(questions[qid]),
                "head_tokens": heads[qid],
            }
            for qid in QUESTION_IDS
        },
        "questions_by_source": {s: list(q) for s, q in cfg.questions.by_source.items()},
        "max_len": cfg.model.max_len,
        "head_max_len": cfg.model.head_max_len,
        "special_tokens": SPECIAL_TOKENS + 1,
        "truncation": lengths,
        "files": {n: {"split": EXPORT_FILES[n][0], "labels": EXPORT_FILES[n][1]} for n in files},
        "counts": counts(files),
        "dates": dates,
        "labels": {
            "react": "level = 4 + sign(e5)·bin(|e5|), bins [0,0.5) [0.5,1) [1,2) [2,3) [3,inf); Q1 levels",
            "mag": "bin(|z_cc,t|), levels 0..4",
            "cont": "Call B D2, |G| >= 0.5: x = sign(G)·y2; reverse x <= -0.5, continue x >= 0.5, else stall",
            "val_a_embargo": "first 5 val-A sessions: not used for early stopping, temperatures or metrics",
        },
        "export": {
            "seed": cfg.export.seed,
            "reaction_dropout": cfg.export.reaction_dropout,
            "context_dropout": cfg.export.context_dropout,
            "context_blocks": list(cfg.export.context_blocks),
        },
        "provenance": {  # inputs only, so the dataset does not change with a commit or an unrelated config
            "states": {s: shas[f"work/{p}"]["sha256"] for s, p in cfg.states.items()},
            "labels": shas[f"work/{LABELS}"]["sha256"],
            "training_yaml": sha256_file(TRAINING_CONFIG_PATH),
            "questions_yaml": sha256_file(QUESTIONS_PATH),
        },
    }
    _write_json(out_dir / INFO_FILE, info)
    _write_json(out_dir / METADATA_FILE, metadata(cfg))
    names = [f"{n}.parquet" for n in files] + [INFO_FILE]
    _write_json(out_dir / MANIFEST_FILE, manifest_of(out_dir, names))
    for name, desc in (
        (INFO_FILE, "NA-08 S2: dataset_info (questions, head lengths, truncation check, counts, provenance)"),
        (METADATA_FILE, "NA-08 S2: Kaggle dataset-metadata.json (private)"),
        (MANIFEST_FILE, "NA-08 S2: sha256 manifest of the uploaded dataset files"),
    ):
        io.register_file(f"{DATASET_DIR}/{name}", producer=PRODUCER, description=desc, layout=lay)
    return info


# --- kernels (S6) -----------------------------------------------------------------------------------

PARAMS_TAG: Final = "parameters"


def run_parameters(run: RunSpec, cfg: TrainingConfig) -> dict[str, Any]:
    """The notebook parameters of one planned run (written into its parameters cell)."""
    m = cfg.model
    ds_slug = cfg.export.dataset_id.split("/")[1]
    return {
        "RUN_NAME": run.name,
        "MODE": run.mode,
        "INITS": list(run.inits) if run.mode == "pilot" else [run.init],
        "SEED": run.seed if run.seed is not None else m.seeds[0],
        "EPOCHS": run.epochs if run.epochs is not None else m.max_epochs,
        "SHUFFLE_LABELS": run.shuffle_labels,
        "SHUFFLE_SEED": cfg.controls.shuffle_permutation_seed,
        "DATASET_DIR": f"/kaggle/input/{ds_slug}",
        "MAX_LEN": m.max_len,
        "HEAD_MAX_LEN": m.head_max_len,
        "QUESTIONS_BY_SOURCE": {s: list(q) for s, q in cfg.questions.by_source.items()},
        "TRAIN_VARIANTS": list(VARIANTS),
        "LAYA": m.laya.model_dump(mode="json"),
        "ANCHOR": m.anchor.model_dump(mode="json"),
        "HEAD": {"head_layers": m.head_layers, "act_costs": dict(m.act_costs)},
        "HPARAMS": {
            k: getattr(m, k)
            for k in (
                "lr_backbone",
                "lr_head",
                "min_lr",
                "warmup_frac",
                "weight_decay",
                "grad_clip",
                "micro_batch",
                "grad_accum",
                "grad_checkpointing",
                "eval_batch",
                "loss",
                "rl_samples",
                "sigma_start",
                "sigma_end",
                "w_sph",
                "w_rps",
                "amp",
            )
        },
        "TIME_BUDGET_HOURS": m.time_budget_hours,
        "PIP": list(m.pip),
        "PILOT": cfg.kaggle.pilot.model_dump(mode="json"),
        "ECE_BINS": cfg.evaluation.ece_bins,
        "LOCAL": None,  # a local run sets out_dir, dataset_dir, model_dirs, device, limits
    }


def params_cell_source(params: Mapping[str, Any]) -> str:
    import pprint

    lines = ["# Parameters (written by `python -m newsaction.train.build --stage kernels`; one set per run)"]
    for k, v in params.items():
        text = pprint.pformat(v, width=100, sort_dicts=False)
        lines.append(f"{k} = " + text.replace("\n", "\n" + " " * (len(k) + 3)))
    return "\n".join(lines) + "\n"


def notebook_with_params(nb: dict[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    """The notebook with its single ``parameters``-tagged cell replaced by ``params``."""
    cells = [c for c in nb["cells"] if PARAMS_TAG in c.get("metadata", {}).get("tags", [])]
    if len(cells) != 1:
        raise ExportError(f"the notebook needs exactly one '{PARAMS_TAG}' cell, found {len(cells)}")
    out: dict[str, Any] = json.loads(json.dumps(nb))
    for c in out["cells"]:
        if PARAMS_TAG in c.get("metadata", {}).get("tags", []):
            c["source"] = params_cell_source(params).splitlines(keepends=True)
    return out


def kernel_metadata(run: RunSpec, cfg: TrainingConfig) -> dict[str, Any]:
    user = cfg.export.dataset_id.split("/")[0]
    slug = f"{cfg.kaggle.kernel_prefix}-{run.name}"
    return {
        "id": f"{user}/{slug}",
        "title": slug,
        "code_file": NOTEBOOK.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": cfg.kaggle.accelerator,
        "dataset_sources": [cfg.export.dataset_id],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }


def write_kernels(
    layout: Layout | None = None, runs: Sequence[str] | None = None, cfg: TrainingConfig | None = None
) -> dict[str, Any]:
    """work/kaggle/kernels/<run>/{kernel-metadata.json, notebook}: one private GPU kernel per run."""
    lay = resolve_layout(layout)
    cfg = load_training_config() if cfg is None else cfg
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    out: dict[str, Any] = {}
    for spec in cfg.kaggle.runs:
        if runs is not None and spec.name not in runs:
            continue
        d = lay.work / KERNELS_DIR / spec.name
        d.mkdir(parents=True, exist_ok=True)
        meta = kernel_metadata(spec, cfg)
        _write_json(d / "kernel-metadata.json", meta)
        text = json.dumps(notebook_with_params(nb, run_parameters(spec, cfg)), indent=1, ensure_ascii=False)
        io.atomic_write_bytes(d / NOTEBOOK.name, (text + "\n").encode())
        out[spec.name] = {
            "kernel": meta["id"],
            "dir": lay.rel(d),
            "notebook_sha256": io.sha256_file(d / NOTEBOOK.name),
        }
    return out


def verify_download(path: Path, layout: Layout | None = None) -> dict[str, str]:
    """The dataset downloaded back from Kaggle into ``path`` equals the local sha256 manifest (AC1)."""
    lay = resolve_layout(layout)
    manifest = json.loads((lay.work / DATASET_DIR / MANIFEST_FILE).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, entry in manifest["files"].items():
        got = io.sha256_file(path / name)
        if got != entry["sha256"]:
            raise ExportError(f"{name}: the uploaded file differs from the local export ({got})")
        out[name] = got
    return out


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m newsaction.train.kaggle_export")
    ap.add_argument("command", choices=["verify"])
    ap.add_argument("path", type=Path, help="a directory holding the dataset downloaded back from Kaggle")
    args = ap.parse_args(argv)
    for name, sha in verify_download(args.path).items():
        print(f"{name}: {sha} OK")
    print("the uploaded dataset equals the local export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
