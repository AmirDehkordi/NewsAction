"""NA-11: final selection, freeze, production and ablations (PRD NA-11; PREREG §4.4, §8.5, §13, A2.1, A2.6).

Shared helpers: the chunk id, NA-11 trial records (CLAUDE.md B10) and the key-usage record kept before and
after each paid batch (operator preamble NA-11 item 6, as NA-09 did).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from newsaction import io
from newsaction.config import SplitName
from newsaction.ledger import TRIALS, SpendLedger, TrialLedger, TrialRecord, params_hash
from newsaction.paths import Layout, resolve_layout
from newsaction.provenance import utc_now_iso

CHUNK: Final = "NA-11"
ARTIFACTS: Final = "artifacts/NA-11"
KEY_USAGE: Final = "key_usage.json"


class ProductionError(Exception):
    """A pre-condition of an NA-11 step does not hold (order, inputs, budget)."""


def artifacts_dir(layout: Layout | None = None) -> Path:
    path = resolve_layout(layout).root / ARTIFACTS
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    """Append one NA-11 trial unless an identical record exists; True when appended."""
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


def record_key_usage(label: str, client: Any, layout: Layout | None = None) -> dict[str, Any]:
    """Append the key's usage and the account's credits (two GETs, no spend) to
    artifacts/NA-11/key_usage.json,
    with this chunk's recorded spend. ``client``: a ``dm.client.DecisionClient``."""
    lay = resolve_layout(layout)
    entry = {"label": label, "ts": utc_now_iso(), **client.key_usage(), **client.credits()}
    entry["ledger_chunk_usd"] = SpendLedger(CHUNK, path=lay.ledgers / "spend.jsonl").totals().chunk_usd
    path = artifacts_dir(lay) / KEY_USAGE
    prior = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    prior.append(entry)
    io.atomic_write_bytes(path, (json.dumps(prior, indent=2) + "\n").encode("utf-8"))
    return entry
