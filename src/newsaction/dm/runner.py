"""Registered state files → decision requests → answers (PRD NA-05; for the pilot, NA-06, NA-07 and NA-11).

- ``load_states``: rows of a registered state file (``io.read_parquet``, sha256-checked), optionally filtered
  by split or event id;
- ``state_specs``: one ``CallSpec`` per row, with the call's questions from the frozen battery (any group
  combination) and the row's provenance for the refusal rules;
- ``answers_frame``: one row per (request, question, option) with its probability;
- ``derived_frame``: one row per request with the PREREG §7 / A2.4 quantities (``parse.derive``) and the model
  build, tokens, cost and validity.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any, Final

import pandas as pd

from newsaction import io
from newsaction.dm.canary import STATE_COLUMNS, state_info
from newsaction.dm.client import CallResult, CallSpec
from newsaction.dm.parse import derive
from newsaction.dm.schemas import DecisionRequest, questions_from
from newsaction.paths import Layout
from newsaction.states.questions import Battery, load_battery

ANSWER_COLUMNS: Final = ["key", "model", "event_id", "tag", "repeat_idx", "question", "option", "p"]


def load_states(
    rel: str,
    *,
    splits: Iterable[str] | None = None,
    event_ids: Iterable[str] | None = None,
    layout: Layout | None = None,
) -> pd.DataFrame:
    """Rows of ``work/<rel>`` (a registered state file) with the columns the client needs."""
    df = io.read_parquet(rel, columns=STATE_COLUMNS, layout=layout)
    if splits is not None:
        df = df.loc[df["split"].isin(list(splits))]
    if event_ids is not None:
        df = df.loc[df["event_id"].isin(list(event_ids))]
    return df.reset_index(drop=True)


def state_specs(
    rows: pd.DataFrame,
    rel: str,
    model: str,
    *,
    call: str,
    groups: Sequence[str] = ("core",),
    battery: Battery | None = None,
    repeat_idx: int = 0,
    tag: str = "",
    probe: str | None = None,
) -> list[CallSpec]:
    b = load_battery() if battery is None else battery
    questions = questions_from(b.request(call, groups))
    out = []
    for rec in rows.to_dict("records"):
        info = state_info(rec, f"work/{rel}")
        if probe is not None:
            info = info.model_copy(update={"probe": probe})
        req = DecisionRequest(model=model, state=json.loads(rec["state_json"]), questions=questions)
        if req.state_sha256() != rec["state_sha256"]:
            raise ValueError(f"{rec['event_id']}: state_json does not match its state_sha256")
        out.append(CallSpec(req, info, repeat_idx=repeat_idx, tag=tag))
    return out


def answers_frame(results: Sequence[CallResult]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for r in results:
        if r.parsed is None:
            continue
        qs = r.spec.request.questions
        for qid, ans in r.parsed.answers.items():
            if ans.probs is None:
                continue
            for opt, p in zip(qs[qid].options(), ans.probs, strict=True):
                rows.append(
                    {
                        "key": r.key,
                        "model": r.spec.request.model,
                        "event_id": r.spec.info.event_id,
                        "tag": r.spec.tag,
                        "repeat_idx": r.spec.repeat_idx,
                        "question": qid,
                        "option": opt,
                        "p": float(p),
                    }
                )
    return pd.DataFrame(rows, columns=ANSWER_COLUMNS)


def derived_frame(results: Sequence[CallResult]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for r in results:
        base: dict[str, Any] = {
            "key": r.key,
            "model": r.spec.request.model,
            "event_id": r.spec.info.event_id,
            "tag": r.spec.tag,
            "repeat_idx": r.spec.repeat_idx,
            "n_questions": len(r.spec.request.questions),
            "ok": r.ok,
            "status": r.status,
            "valid": bool(r.parsed is not None and r.parsed.valid),
        }
        if r.row is not None:
            base |= {
                "model_build": r.row.model_build,
                "provider": r.row.provider,
                "input_tokens": r.row.input_tokens,
                "cost": r.row.cost,
                "latency_ms": r.row.latency_ms,
            }
        if r.parsed is not None:
            base |= derive(r.parsed.answers, r.spec.request.questions)
        rows.append(base)
    return pd.DataFrame(rows)
