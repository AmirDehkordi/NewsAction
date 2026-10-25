"""The val-A filter comparison and the pre-registered selection rule (PREREG §6.8; PRD NA-03 S4).

- **Sample.** Covered member company-days of val-A with a valid label (purged at the split end, §4.1),
  without the first 5 sessions (embargo, §4.2). ``assert_val_a`` refuses any other session. Train
  is used only by ``learned``, and val-B is never read here.
- **Candidates at the budget.** F1–F6 each select at most 30% of the sample (``filters.budget_select``).
- **References at the natural rate.** Rows with role ``reference_natural`` hold each rule filter's
  natural rate (F0–F3); F0 is not a candidate.
- **Metrics.**
  - material recall, delayed-reaction recall, precision;
  - abnormal variance ratio Var(z_cc | selected) / Var(z_cc | all);
  - selection rate by tier, and recall of each material component.
- **Rule** (``apply_rule``, mechanical): among candidates whose delayed recall is ≥ F1's, the highest
  material recall wins. Recalls less than 1 pp below the best are ties, and ties go to fewer inputs in
  the order F1 < F2 < … < F6.
- **Frontier.** Selection share vs recall at 10 budget shares per filter (Figure 6).

Every evaluated filter, threshold and frontier point is logged in ``ledgers/trials.jsonl``.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd
import yaml

from newsaction import io
from newsaction.config import load_splits
from newsaction.events import (
    FILTER_IDS,
    LABELS,
    RULE_FILTERS,
    TICKER_DAYS,
    CompareConfig,
    FilterId,
    load_events_config,
)
from newsaction.events.filters import SCORE_COLUMN, Selection, budget_select, eligible, tie_u
from newsaction.events.trials import log_trial
from newsaction.paths import CONFIGS, Layout, resolve_layout

VAL_A: Final = "val_a"
TIERS: Final = ("top100", "mid", "rest")
INPUTS: Final[dict[str, str]] = {
    "F0": "clean articles (§6.2)",
    "F1": "vendor tag, sentiment, event age",
    "F2": "F1 + HARD tag, intensity",
    "F3": "source class",
    "F4": "novelty",
    "F5": "bge embedding (logistic regression)",
    "F6": "vendor tag, flags, sentiment, intensity, source class, novelty, 16 PCs, attention (LightGBM)",
}
_EPS: Final = 1e-12


class CompareError(ValueError):
    """The comparison was given sessions outside val-A, or a malformed comparison table."""


def assert_val_a(sessions: pd.Series | Sequence[date]) -> None:
    """Raise CompareError unless every session lies in val-A (PREREG §6.8: compare on val-A only)."""
    rng = load_splits().splits[VAL_A]
    s = pd.to_datetime(pd.Series(list(sessions))).dt.date
    if len(s) == 0:
        raise CompareError("empty comparison sample")
    if bool(s.isna().any()) or min(s) < rng.start or max(s) > rng.end:
        raise CompareError(
            f"comparison sessions {min(s)}..{max(s)} are not inside val-A {rng.start}..{rng.end}"
        )


def comparison_sample(labels: pd.DataFrame, td_w0: pd.DataFrame) -> pd.DataFrame:
    """Val-A evaluation days (labelled, purged, embargo removed) with their W0 ticker-day scores."""
    lab = labels.loc[
        (labels["split"] == VAL_A) & labels["label_ok"].astype(bool) & ~labels["embargo"].astype(bool)
    ]
    assert_val_a(lab["session"])
    td = td_w0.loc[td_w0["window"] == "W0"].drop(columns=["window", "split"])
    s = lab.merge(td.drop(columns=["tie_u"]), on=["company_id", "session"], how="left")
    s["tie_u"] = tie_u(s["company_id"], s["session"], load_events_config().learned.seed)
    assert_val_a(s["session"])
    return s.reset_index(drop=True)


def _ratio(hit: npt.NDArray[np.bool_], base: npt.NDArray[np.bool_]) -> float:
    return int(hit.sum()) / max(int(base.sum()), 1)


def _cell(df: pd.DataFrame, row: str, col: str) -> float:
    return float(df[col].to_numpy(dtype=np.float64)[df.index.get_loc(row)])


def evaluate(sel: npt.NDArray[np.bool_], sample: pd.DataFrame) -> dict[str, float | int]:
    """Selection metrics on the val-A sample."""
    mat = sample["material"].astype(bool).to_numpy()
    dl = sample["delayed"].astype(bool).to_numpy()
    z = sample["z_cc"].to_numpy(dtype=np.float64)
    n, k = len(sample), int(sel.sum())
    zf = np.isfinite(z)
    out: dict[str, float | int] = {
        "n_eval": n,
        "n_selected": k,
        "selected_share": k / n,
        "n_material": int(mat.sum()),
        "n_delayed": int(dl.sum()),
        "recall_material": _ratio(sel & mat, mat),
        "recall_delayed": _ratio(sel & dl, dl),
        "precision": int((sel & mat).sum()) / k if k else float("nan"),
        "var_ratio": float(np.var(z[sel & zf]) / np.var(z[zf])) if k else float("nan"),
    }
    for comp in ("material_on", "material_car", "material_vol"):
        c = sample[comp].astype(bool).to_numpy()
        out[f"recall_{comp.removeprefix('material_')}"] = _ratio(sel & c, c)
    tier = sample["tier"].astype("string").fillna("none").to_numpy()
    for t in TIERS:
        m = tier == t
        out[f"share_{t}"] = float(sel[m].mean()) if m.any() else float("nan")
    return out


def select_filter(sample: pd.DataFrame, fid: FilterId, k: int | None) -> Selection:
    """``fid``'s selection on ``sample``: at most ``k`` days, or its whole eligible set when k is None."""
    ok = eligible(sample, fid)
    score = sample[SCORE_COLUMN[fid]].to_numpy(dtype=np.float64)
    u = sample["tie_u"].to_numpy(dtype=np.float64)
    return budget_select(score, ok, u, int(ok.sum()) if k is None else k)


def compare(sample: pd.DataFrame, cfg: CompareConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(filter_comparison, frontier) tables; logs every evaluation in the trials ledger."""
    assert_val_a(sample["session"])
    n = len(sample)
    k = math.floor(cfg.budget_share * n)
    rows: list[dict[str, Any]] = []
    for fid in FILTER_IDS:
        ok = eligible(sample, fid)
        roles: list[tuple[str, int | None]] = []
        if fid in RULE_FILTERS:
            roles.append(("reference_natural", None))
        if fid != "F0":
            roles.append(("candidate", k))
        for role, kk in roles:
            sel = select_filter(sample, fid, kk)
            rows.append(
                {
                    "filter": fid,
                    "role": role,
                    "inputs": INPUTS[fid],
                    "eligible_share": float(ok.mean()),
                    "threshold": sel.threshold,
                    "tie_u_max": sel.tie_u_max,
                    **evaluate(sel.mask, sample),
                }
            )
    comp = pd.DataFrame(rows)
    f1_dl = float(
        comp.loc[(comp["filter"] == "F1") & (comp["role"] == "candidate"), "recall_delayed"].iloc[0]
    )
    cand = comp["role"] == "candidate"
    comp["constraint_ok"] = pd.array(
        [bool(d >= f1_dl) if c else pd.NA for d, c in zip(comp["recall_delayed"], cand, strict=True)],
        dtype="boolean",
    )
    frontier_rows = []
    for fid in FILTER_IDS:
        for share in cfg.frontier_shares:
            sel = select_filter(sample, fid, math.floor(share * n))
            m = evaluate(sel.mask, sample)
            frontier_rows.append(
                {
                    "filter": fid,
                    "target_share": share,
                    "selected_share": m["selected_share"],
                    "threshold": sel.threshold,
                    "recall_material": m["recall_material"],
                    "recall_delayed": m["recall_delayed"],
                    "precision": m["precision"],
                }
            )
    return comp, pd.DataFrame(frontier_rows)


def apply_rule(
    df: pd.DataFrame,
    *,
    budget_share: float | None = None,
    tie_pp: float | None = None,
    order: Sequence[str] | None = None,
    constrained: bool = True,
) -> str:
    """PREREG §6.8 applied mechanically to a comparison table (rows with role ``candidate``).

    Highest material recall subject to delayed-reaction recall ≥ F1's; recalls within ``tie_pp`` of the
    best are ties, resolved to the first filter in ``order`` (fewer inputs). ``constrained=False``
    drops the delayed-recall constraint (used only to report whether it binds).
    """
    cfg = load_events_config().compare
    budget = cfg.budget_share if budget_share is None else budget_share
    tie = cfg.tie_pp if tie_pp is None else tie_pp
    order = list(cfg.tie_order if order is None else order)
    c = df.loc[df["role"] == "candidate"].set_index("filter")
    if c.index.has_duplicates or set(order) - set(c.index):
        raise CompareError(f"candidates must be exactly one row each of {order}, got {list(c.index)}")
    over = c.index[c["selected_share"] > budget + _EPS].tolist()
    if over:
        raise CompareError(f"candidates over the {budget:.0%} budget: {over}")
    feasible = c.loc[order]
    if constrained:
        feasible = feasible.loc[feasible["recall_delayed"] >= _cell(c, "F1", "recall_delayed")]
    best = float(feasible["recall_material"].max())
    tied = feasible.index[best - feasible["recall_material"] < tie].tolist()
    return next(f for f in order if f in tied)


def rule_trace(df: pd.DataFrame) -> dict[str, Any]:
    """The rule's choice, the choice without the delayed-recall constraint, and whether it binds."""
    c = df.loc[df["role"] == "candidate"].set_index("filter")
    f1 = _cell(c, "F1", "recall_delayed")
    chosen, free = apply_rule(df), apply_rule(df, constrained=False)
    return {
        "chosen": chosen,
        "unconstrained": free,
        "constraint_binding": chosen != free,
        "f1_recall_delayed": f1,
        "excluded_by_constraint": sorted(c.index[c["recall_delayed"] < f1].tolist()),
    }


# --- frozen.yaml ----------------------------------------------------------------------------------


def yaml_float(x: float) -> str:
    """repr(x) in a form YAML 1.1 reads back as the same float (it needs a '.' before an exponent)."""
    if math.isinf(x):
        return ".inf" if x > 0 else "-.inf"
    r = repr(float(x))
    if "e" in r and "." not in r.split("e")[0]:
        m, e = r.split("e")
        r = f"{m}.0e{e}"
    if float(yaml.safe_load(r)) != x:
        raise ValueError(f"{x!r} does not round-trip through YAML as {r}")
    return r


def filter_block(entry: dict[str, Any]) -> str:
    lines = [
        "filter:              # NA-03: PREREG §6.8 val-A comparison (artifacts/NA-03/filter_comparison.csv)"
    ]
    for key, val in entry.items():
        if isinstance(val, bool):
            v = "true" if val else "false"
        elif isinstance(val, float):
            v = yaml_float(val)
        elif isinstance(val, int):
            v = str(val)
        else:
            v = str(val)
        lines.append(f"  {key}: {v}")
    return "\n".join(lines) + "\n"


def write_frozen_filter(entry: dict[str, Any], path: Path = CONFIGS / "frozen.yaml") -> None:
    """Replace the ``filter:`` section of frozen.yaml (other sections and comments are untouched)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if re.match(r"^filter:", ln))
    end = start + 1
    while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
        end += 1
    new = "".join(lines[:start]) + filter_block(entry) + "".join(lines[end:])
    parsed = yaml.safe_load(new)["filter"]
    if {k: parsed[k] for k in entry} != entry:
        raise ValueError("frozen.yaml filter block does not round-trip")
    path.write_text(new, encoding="utf-8")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_compare(layout: Layout | None = None) -> dict[str, Any]:
    """Comparison, frontier, rule and frozen.yaml ``filter:``; logs every evaluation as a trial."""
    lay = resolve_layout(layout)
    cfg = load_events_config()
    labels = io.read_parquet(LABELS, layout=lay)
    td = io.read_parquet(TICKER_DAYS, layout=lay)
    sample = comparison_sample(labels, td.loc[td["split"] == VAL_A])
    comp, frontier = compare(sample, cfg.compare)
    trace = rule_trace(comp)
    comp["chosen"] = (comp["filter"] == trace["chosen"]) & (comp["role"] == "candidate")
    for r in comp.to_dict("records"):
        params = {
            "filter": r["filter"],
            "role": r["role"],
            "threshold": r["threshold"],
            "tie_u_max": r["tie_u_max"],
        }
        name = f"{r['filter']} {r['role']}"
        log_trial("filter", name, params, VAL_A, "recall_material", r["recall_material"], layout=lay)
    for r in frontier.to_dict("records"):
        params = {"filter": r["filter"], "target_share": r["target_share"], "threshold": r["threshold"]}
        name = f"{r['filter']}@{r['target_share']}"
        log_trial("filter_frontier", name, params, VAL_A, "recall_material", r["recall_material"], layout=lay)
    out_dir = lay.artifacts / "NA-03"
    out_dir.mkdir(parents=True, exist_ok=True)
    comp_bytes = comp.to_csv(index=False, lineterminator="\n").encode()
    io.atomic_write_bytes(out_dir / "filter_comparison.csv", comp_bytes)
    io.atomic_write_bytes(
        out_dir / "frontier.csv", frontier.to_csv(index=False, lineterminator="\n").encode()
    )
    row = comp.loc[comp["chosen"]].iloc[0]
    entry: dict[str, Any] = {
        "id": trace["chosen"],
        "threshold": float(row["threshold"]),
        "tie_u_max": float(row["tie_u_max"]),
        "tie_seed": cfg.learned.seed,
        "budget_share": cfg.compare.budget_share,
        "selected_share_val_a": float(row["selected_share"]),
        "rule_version": cfg.compare.rule_version,
        "constraint_binding": bool(trace["constraint_binding"]),
        "comparison_file": "artifacts/NA-03/filter_comparison.csv",
        "comparison_sha": _sha_bytes(comp_bytes),
    }
    write_frozen_filter(entry, lay.configs / "frozen.yaml")
    return {"trace": trace, "entry": entry, "n_eval": len(sample)}
