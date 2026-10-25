"""Trial logging for NA-03 (CLAUDE.md B10): one ``ledgers/trials.jsonl`` record per evaluated variant.

A record identical to one already in the ledger (same chunk, kind, name, params hash, split, metric and
value) is not appended again. A deterministic rerun therefore does not inflate the trial count that the
deflated Sharpe uses. A rerun that changes a value is a new evaluation and is logged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from newsaction.config import SplitName
from newsaction.events import CHUNK
from newsaction.ledger import TRIALS, TrialLedger, TrialRecord, params_hash
from newsaction.paths import Layout, resolve_layout


def log_trial(
    kind: str,
    name: str,
    params: Mapping[str, Any],
    split: SplitName,
    metric: str,
    value: float | None,
    *,
    layout: Layout | None = None,
) -> bool:
    """Append one trial unless an identical record exists; True when appended."""
    rec = TrialRecord(
        chunk=CHUNK,
        kind=kind,
        name=name,
        params_hash=params_hash(dict(params)),
        split=split,
        metric=metric,
        value=None if value is None else float(value),
    )
    ledger = TrialLedger(resolve_layout(layout).ledgers / TRIALS)
    fields = rec.model_dump()
    for r in ledger.records():
        if all(r.get(k) == v for k, v in fields.items()):
            return False
    ledger.log(rec)
    return True
