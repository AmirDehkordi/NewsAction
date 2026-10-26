"""The canary set ``canary_v1`` and the drift check (PRD NA-05 S7; PRD NA-11 S5).

**canary_v1** is 50 fixed requests (``artifacts/NA-05/canary_v1.jsonl``, one JSON object per line):
- 30 train-period masked states from the registered E3 state files: 20 Call A on D0 and 10 Call B on D2, the
  states with the smallest u = sha256("2026:canary:<event_id>") within each size tier (proportional, largest
  remainder);
- 20 synthetic states built with the codebook (``synthetic_state``): 6 Call A with hand-written news of a
  known direction, and the 14 Call B states of the numeracy grid (pilot item 8): one clearly positive news
  item, and the stock's reaction at 7 magnitudes × 2 directions, everything else fixed.

Every line holds the state, the core questions of its call (``configs/questions_v1.yaml``), the sha256 of
both, the state's provenance and, for synthetic states, a label.

**Baseline** (``artifacts/NA-05/canary_baseline.parquet``): one row per (model, canary id, question, option)
with the probability of the pilot's repeat 0 (renormalized and flagged for an answer rounded within one step,
``schemas.RENORM_TOL``), the model build and the request key. ``compare`` asks the canary again under
another ``repeat_idx`` (a new key, so a fresh call) and reports max and mean |Δp| against the baseline.
NA-11 S5 (operator decision, docs/decisions/NA-05.md; ``configs/dm.yaml`` ``canary``): a deterministic model
fails at max |Δp| ≥ 0.02; any other model's mean |Δp| is compared with its own repeat noise (5 repeats, pilot
item 4).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal

import pandas as pd

from newsaction import io
from newsaction.dm import DMError
from newsaction.dm.client import CallResult, CallSpec, DecisionClient, StateInfo
from newsaction.dm.schemas import DecisionRequest, questions_from
from newsaction.paths import Layout, resolve_layout
from newsaction.states.codebook import Codebook, Horizon, Move, load_codebook
from newsaction.states.questions import Battery, canonical_json, load_battery

SEED: Final = 2026
VERSION: Final = "canary_v1"
STATE_FILES: Final = {"A": "states/callA_d0_E3.parquet", "B": "states/callB_d2_E3.parquet"}
N_TRAIN: Final = {"A": 20, "B": 10}
NUMERACY_Z: Final = (0.3, 0.7, 1.5, 2.5, 4.0, 6.0, 9.0)
STATE_COLUMNS: Final = [
    "event_id",
    "session",
    "split",
    "call",
    "encoding",
    "masked",
    "state_json",
    "state_sha256",
    "n_tokens_state",
    "third_party_ok_all",
]

CanaryKind = Literal["train", "synthetic"]


@dataclass(frozen=True)
class CanaryItem:
    canary_id: str
    kind: CanaryKind
    group: str  # train_A, train_B, synthetic_A, numeracy
    call: Literal["A", "B"]
    label: str
    state: dict[str, Any]
    questions: dict[str, Any]
    info: StateInfo
    n_tokens_state: int | None = None
    move_z: float | None = None  # numeracy: the signed reaction in typical daily moves

    @property
    def state_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.state).encode("utf-8")).hexdigest()

    @property
    def questions_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.questions).encode("utf-8")).hexdigest()

    def request(self, model: str) -> DecisionRequest:
        return DecisionRequest(model=model, state=self.state, questions=questions_from(self.questions))

    def spec(self, model: str, *, repeat_idx: int = 0, tag: str = "canary") -> CallSpec:
        return CallSpec(self.request(model), self.info, repeat_idx=repeat_idx, tag=tag)

    def line(self) -> dict[str, Any]:
        return {
            "canary_id": self.canary_id,
            "version": VERSION,
            "kind": self.kind,
            "group": self.group,
            "call": self.call,
            "label": self.label,
            "move_z": self.move_z,
            "n_tokens_state": self.n_tokens_state,
            "info": self.info.model_dump(mode="json"),
            "state": self.state,
            "questions": self.questions,
            "state_sha256": self.state_sha256,
            "questions_sha256": self.questions_sha256,
        }


def _u(event_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{SEED}:canary:{event_id}".encode()).digest()[:8], "big")


def _allocate(sizes: Mapping[str, int], n: int) -> dict[str, int]:
    """Proportional allocation with the largest remainder (ties: stratum order)."""
    total = sum(sizes.values())
    if total < n:
        raise DMError(f"only {total} candidates for {n} canary states")
    raw = {k: n * v / total for k, v in sizes.items()}
    out = {k: math.floor(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: (-(raw[k] - out[k]), list(sizes).index(k)))[: n - sum(out.values())]:
        out[k] += 1
    return out


def sample_train(frame: pd.DataFrame, n: int, exclude: frozenset[str] = frozenset()) -> pd.DataFrame:
    """``n`` train-split states, tier-stratified (the size words of the state), smallest u per tier."""
    df = frame.loc[(frame["split"] == "train") & ~frame["event_id"].isin(exclude)].copy()
    df["tier_word"] = [json.loads(s)["company"]["size"] for s in df["state_json"]]
    df["u"] = [_u(e) for e in df["event_id"]]
    sizes = df.groupby("tier_word").size().sort_index()
    alloc = _allocate({str(k): int(v) for k, v in sizes.items()}, n)
    parts = [g.nsmallest(alloc[str(t)], "u") for t, g in df.groupby("tier_word", sort=True)]
    return pd.concat(parts).sort_values("u").reset_index(drop=True)


def state_info(row: Mapping[Any, Any], file: str) -> StateInfo:
    return StateInfo(
        source="states",
        file=file,
        event_id=str(row["event_id"]),
        session=row["session"],
        split=str(row["split"]),
        call=row["call"],
        masked=bool(row["masked"]),
        third_party_ok_all=bool(row["third_party_ok_all"]),
    )


# --- synthetic states -------------------------------------------------------------------------------

SYNTHETIC_INFO: Final = StateInfo(source="synthetic", masked=True, third_party_ok_all=True)


def _move(cb: Codebook, z: float, horizon: Horizon = "day") -> str:
    return cb.encode_move(Move(z=z, horizon=horizon), "E3")


def _company(cb: Codebook, *, sector: str, earnings: bool) -> dict[str, Any]:
    return {
        "analyst_estimates_past_month": cb.revision_word(0.0),
        "earnings_report": cb.earnings_word(earnings),
        "market_sensitivity": cb.beta_word(1.0),
        "performance_vs_market_and_sector": {
            "past_month": _move(cb, -0.4, "month"),
            "past_three_months": _move(cb, 0.3, "three_months"),
            "past_week": _move(cb, 0.2, "week"),
        },
        "sector": sector,
        "size": cb.tier_word("mid"),
        "volatility_vs_its_past_year": cb.percentile_word(50.0),
    }


def _market(cb: Codebook) -> dict[str, Any]:
    return {
        "dollar_change": _move(cb, -0.1),
        "high_yield_spread_change": _move(cb, 0.2),
        "oil_change": _move(cb, 0.3),
        "scheduled_releases_today": "none scheduled",
        "stock_market_previous_session": _move(cb, 0.2),
        "ten_year_yield_change": _move(cb, -0.2),
        "vix_change": _move(cb, -0.1),
        "vix_level_vs_past_year": cb.percentile_word(50.0),
    }


def synthetic_state(
    cb: Codebook,
    news: Sequence[Mapping[str, str]],
    *,
    sector: str = "Industrials",
    earnings: bool = False,
    reaction_z: float | None = None,
) -> dict[str, Any]:
    """A state in the NA-04 layout with neutral context words; Call B when ``reaction_z`` is given."""
    state: dict[str, Any] = {
        "attention": {
            "articles_vs_usual": cb.attention_word(2.0),
            "distinct_stories": cb.count_word(len(news)),
        },
        "company": _company(cb, sector=sector, earnings=earnings),
        "market": _market(cb),
        "news": [dict(n) for n in news],
    }
    if reaction_z is not None:
        state["reaction_so_far"] = {
            "stock_market_move": _move(cb, 0.1),
            "stock_move_vs_market_and_sector": _move(cb, reaction_z),
            "time": cb.time_label_word("D2"),
            "volume_vs_normal": cb.attention_word(2.0),
        }
    out: dict[str, Any] = json.loads(canonical_json(state))  # key order as stored (sorted)
    return out


def _item(
    headline: str, snippet: str, source: str = "press_wire_primary", timing: str = "before_open"
) -> dict[str, str]:
    cb = load_codebook()
    return {
        "headline": headline,
        "snippet": snippet,
        "source_type": cb.source_type_word(source),
        "timing": cb.timing[timing],
    }


POSITIVE_EARNINGS: Final = (
    "The company reports quarterly results well above expectations and raises its full-year outlook",
    "Revenue rose 14% from a year earlier to $4.6 billion, ahead of the $4.2 billion analysts expected, and "
    "adjusted earnings per share of $1.52 beat the consensus estimate of $1.21. The company raised its "
    "full-year revenue guidance to $18.4 billion from $17.6 billion and announced a $2 billion share "
    "repurchase program.",
)
SYNTHETIC_A: Final = (
    ("positive_earnings", "Industrials", True, [POSITIVE_EARNINGS]),
    (
        "negative_earnings",
        "Consumer Discretionary",
        True,
        [
            (
                "The company misses quarterly estimates and cuts its full-year guidance",
                "Revenue fell 9% from a year earlier to $2.1 billion, short of the $2.4 billion analysts "
                "expected, and adjusted earnings per share of $0.38 missed the consensus of $0.71. The "
                "company lowered its full-year earnings outlook to $1.60–$1.80 per share from $2.70–$2.90, "
                "citing weak demand and higher costs.",
            )
        ],
    ),
    (
        "downgrade",
        "Information Technology",
        False,
        [
            (
                "Major broker downgrades the company to sell, citing slowing orders",
                "Analysts at a large investment bank cut their rating on the company to Sell from Buy and "
                "lowered their earnings estimates for next year by 18%, saying channel checks point to a "
                "sharp slowdown in enterprise orders.",
            )
        ],
    ),
    (
        "approval",
        "Health Care",
        False,
        [
            (
                "Regulator approves the company's lead drug for a large patient population",
                "The drug agency approved the company's once-weekly treatment for adults with moderate to "
                "severe disease, a market analysts size at more than $5 billion a year. Approval came "
                "earlier than expected and without the safety warning investors had feared.",
            )
        ],
    ),
    (
        "investigation",
        "Financials",
        False,
        [
            (
                "Federal prosecutors open an investigation into the company's accounting",
                "The company disclosed in a filing that it received subpoenas from federal prosecutors and "
                "the securities regulator about its revenue recognition, and that its auditor has withdrawn "
                "its opinion on the last two annual reports.",
            )
        ],
    ),
    (
        "conference",
        "Utilities",
        False,
        [
            (
                "The company to present at an industry conference",
                "The company's management will participate in a fireside chat at an investor conference "
                "later this month. A webcast will be available on the company's investor relations website.",
            )
        ],
    ),
)


def synthetic_items(battery: Battery, cb: Codebook) -> list[CanaryItem]:
    out: list[CanaryItem] = []
    qa, qb = battery.request("A", ["core"]), battery.request("B", ["core"])
    for label, sector, earnings, news in SYNTHETIC_A:
        items = [_item(h, s) for h, s in news]
        state = synthetic_state(cb, items, sector=sector, earnings=earnings)
        out.append(CanaryItem("", "synthetic", "synthetic_A", "A", label, state, qa, SYNTHETIC_INFO))
    news_b = [_item(*POSITIVE_EARNINGS)]
    for sign in (1.0, -1.0):
        for z in NUMERACY_Z:
            mz = sign * z
            state = synthetic_state(cb, news_b, sector="Industrials", earnings=True, reaction_z=mz)
            label = f"numeracy {'rise' if sign > 0 else 'fall'} {z:g}"
            out.append(
                CanaryItem("", "synthetic", "numeracy", "B", label, state, qb, SYNTHETIC_INFO, move_z=mz)
            )
    return out


# --- the canary file ---------------------------------------------------------------------------------


def build_canary(layout: Layout | None = None) -> list[CanaryItem]:
    """canary_v1 from the registered state files and the codebook (deterministic)."""
    lay = resolve_layout(layout)
    battery = load_battery(lay.configs / "questions_v1.yaml")
    cb = load_codebook(lay.configs / "codebook_v1.yaml")
    items: list[CanaryItem] = []
    for call in ("A", "B"):
        rel = STATE_FILES[call]
        frame = io.read_parquet(rel, columns=STATE_COLUMNS, layout=lay)
        qs = battery.request(call, ["core"])
        for row in sample_train(frame, N_TRAIN[call]).to_dict("records"):
            items.append(
                CanaryItem(
                    "",
                    "train",
                    f"train_{call}",
                    call,
                    "",
                    json.loads(row["state_json"]),
                    qs,
                    state_info(row, f"work/{rel}"),
                    n_tokens_state=int(row["n_tokens_state"]),
                )
            )
    items += synthetic_items(battery, cb)
    return [replace(it, canary_id=f"C{i:02d}") for i, it in enumerate(items, start=1)]


def write_canary(items: Sequence[CanaryItem], path: Path) -> str:
    text = "".join(canonical_json(it.line()) + "\n" for it in items)
    io.atomic_write_bytes(path, text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_canary(path: Path) -> list[CanaryItem]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        d = json.loads(raw)
        it = CanaryItem(
            canary_id=d["canary_id"],
            kind=d["kind"],
            group=d["group"],
            call=d["call"],
            label=d["label"],
            state=d["state"],
            questions=d["questions"],
            info=StateInfo.model_validate(d["info"]),
            n_tokens_state=d["n_tokens_state"],
            move_z=d["move_z"],
        )
        if it.state_sha256 != d["state_sha256"] or it.questions_sha256 != d["questions_sha256"]:
            raise DMError(f"{path}: {it.canary_id} does not match its sha256")
        out.append(it)
    return out


# --- baseline and drift ------------------------------------------------------------------------------


BASELINE_COLUMNS: Final = [
    "model",
    "model_build",
    "canary_id",
    "question",
    "option",
    "p",
    "renormalized",
    "key",
    "repeat_idx",
]


def probability_rows(items: Sequence[CanaryItem], results: Sequence[CallResult]) -> pd.DataFrame:
    """Valid answers, long (``BASELINE_COLUMNS``); ``renormalized`` marks a rescaled rounded answer."""
    rows: list[dict[str, Any]] = []
    for it, res in zip(items, results, strict=True):
        if res.parsed is None or res.row is None:
            continue
        qs = res.spec.request.questions
        for qid, ans in res.parsed.answers.items():
            if ans.probs is None:
                continue
            for opt, p in zip(qs[qid].options(), ans.probs, strict=True):
                rows.append(
                    {
                        "model": res.spec.request.model,
                        "model_build": res.row.model_build,
                        "canary_id": it.canary_id,
                        "question": qid,
                        "option": opt,
                        "p": float(p),
                        "renormalized": ans.renormalized,
                        "key": res.key,
                        "repeat_idx": res.spec.repeat_idx,
                    }
                )
    return pd.DataFrame(rows, columns=BASELINE_COLUMNS)


def max_abs_delta(baseline: pd.DataFrame, current: pd.DataFrame) -> dict[str, Any]:
    """max |Δp| over the (canary id, question, option) cells both frames hold, and where it happens."""
    on = ["canary_id", "question", "option"]
    m = baseline[[*on, "p"]].merge(current[[*on, "p"]], on=on, suffixes=("_base", "_now"))
    if m.empty:
        return {"cells": 0, "max_abs_dp": None, "mean_abs_dp": None, "at": None}
    d = (m["p_now"] - m["p_base"]).abs()
    i = int(d.to_numpy().argmax())
    return {
        "cells": len(m),
        "max_abs_dp": float(d.max()),
        "mean_abs_dp": float(d.mean()),
        "at": {k: str(m.iloc[i][k]) for k in on},
        "missing_cells": len(baseline) - len(m),
    }


def compare(
    client: DecisionClient,
    model: str,
    items: Sequence[CanaryItem],
    baseline: pd.DataFrame,
    *,
    repeat_idx: int,
) -> dict[str, Any]:
    """Ask the canary again under ``repeat_idx`` (fresh keys) and compare with the model's baseline rows."""
    if repeat_idx == 0:
        raise DMError("repeat 0 is the baseline itself; use another repeat_idx")
    base = baseline.loc[baseline["model"] == model]
    if base.empty:
        raise DMError(f"no canary baseline for {model}")
    results = client.decide([it.spec(model, repeat_idx=repeat_idx, tag="canary_compare") for it in items])
    now = probability_rows(items, results)
    return {"model": model, "repeat_idx": repeat_idx, **max_abs_delta(base, now)}
