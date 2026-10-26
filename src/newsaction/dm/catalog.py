"""The decision-model catalog snapshot and eligibility (PRD NA-05 S4; PREREG §8.1).

``snapshot(client)`` reads GET /api/v1/models?output_modalities=decisions (no spend) and returns the record
written to ``artifacts/NA-05/catalog.json``: the fetch time, the URL and query, one entry per model (id, name,
canonical slug, created, context length, pricing, architecture, top provider, per-request limits) sorted by
id, ``sha256`` = the sha256 of the canonical JSON of those entries (recomputable from the file; pilot item 10)
and ``raw_sha256`` = the same over the raw model list as fetched.

``eligibility(catalog, outcomes, local)`` gives every catalog id, and each local Laya checkpoint, an
include / exclude decision with a reason:
- an alias (``~…``) is excluded: it moves to new builds (PREREG §8.1);
- a ``:free`` id is excluded: a duplicate of its paid id, or an endpoint without the operator's approval
  (CLAUDE.md C13);
- a model whose pilot or smoke calls failed is excluded with the failure: ``data_collection: deny`` rejected,
  errors, missing or malformed probabilities (more than 10% invalid answers), silent truncation
  (``Outcome.failure``). Rounded probabilities within one rounding step are renormalized by the parser
  (``schemas.RENORM_TOL``) and are not a failure; their share is in the reason;
- every other model is included; the local Laya checkpoints are included (PREREG §8.1).

``write_eligibility`` puts the list into ``configs/frozen.yaml`` as ``eligible_models`` (and adds an empty
``free_model_approvals`` when the file has none), keeping the file's comments.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from newsaction import io
from newsaction.dm import CATALOG_FILE, DMError
from newsaction.dm.client import DecisionClient
from newsaction.provenance import utc_now_iso
from newsaction.states.questions import canonical_json

ENTRY_FIELDS: Final = (
    "id",
    "name",
    "canonical_slug",
    "created",
    "context_length",
    "pricing",
    "architecture",
    "top_provider",
    "per_request_limits",
)
ELIGIBLE_KEY: Final = "eligible_models"
FREE_KEY: Final = "free_model_approvals"


def catalog_sha256(models: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(models, key=lambda m: str(m["id"]))
    return hashlib.sha256(canonical_json(list(ordered)).encode("utf-8")).hexdigest()


def snapshot(client: DecisionClient) -> dict[str, Any]:
    api = client.config.api
    raw = client.get_json(api.models_url, api.catalog_params)
    models = raw.get("data")
    if not isinstance(models, list) or not models:
        raise DMError("the catalog response has no model list")
    entries = []
    for m in sorted(models, key=lambda m: str(m["id"])):
        e = {k: m.get(k) for k in ENTRY_FIELDS}
        e["created_iso"] = datetime.fromtimestamp(int(m["created"]), UTC).date().isoformat()
        entries.append(e)
    return {
        "fetched_at": utc_now_iso(),
        "url": api.models_url,
        "params": dict(api.catalog_params),
        "sha256": catalog_sha256(entries),
        "raw_sha256": catalog_sha256(models),
        "n_models": len(entries),
        "total_count": raw.get("total_count"),
        "models": entries,
    }


def write_snapshot(record: Mapping[str, Any], root: Path) -> Path:
    path = root / CATALOG_FILE
    io.atomic_write_bytes(path, (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return path


def load_snapshot(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((root / CATALOG_FILE).read_text(encoding="utf-8"))
    return out


# --- eligibility ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """What a model's pilot or smoke calls showed (``pilot.model_outcomes``)."""

    calls: int
    ok: int
    data_policy_rejected: bool
    error_share: float
    invalid_share: float  # answers with a structural problem (type, options, legend, broken probabilities)
    missing_probabilities: bool
    silent_truncation: bool | None  # None: not measured or inconclusive
    note: str = ""
    rejection: str | None = None  # the API's own message when it refused every call
    renormalized_share: float = 0.0  # answers whose rounded probabilities the parser renormalized

    def failure(self) -> str | None:
        if self.calls == 0:
            return None
        if self.data_policy_rejected:
            return "rejects provider.data_collection = deny (PREREG §8.1)"
        if self.ok == 0 and self.rejection:
            return f"refuses every request (PREREG §8.1): {self.rejection}"
        if self.ok == 0 or self.error_share > 0.1:
            return f"errors on {self.error_share:.0%} of well-formed calls (PREREG §8.1)"
        if self.missing_probabilities:
            return "answers without probabilities (PREREG §8.1)"
        if self.invalid_share > 0.1:
            return f"malformed answers on {self.invalid_share:.0%} of answers (PREREG §8.1)"
        if self.silent_truncation:
            return "silently truncates a 2K-token state (PREREG §8.1)"
        return None


def free_base(model_id: str) -> str | None:
    return model_id[: -len(":free")] if model_id.endswith(":free") else None


def eligibility(
    catalog: Mapping[str, Any],
    outcomes: Mapping[str, Outcome],
    local: Sequence[str],
    free_approved: Sequence[str] = (),
) -> list[dict[str, Any]]:
    ids = [str(m["id"]) for m in catalog["models"]]
    rows = []
    for mid in ids:
        base = free_base(mid)
        if mid.startswith("~"):
            rows.append({"id": mid, "include": False, "reason": "alias: moves to new builds (PREREG §8.1)"})
        elif base is not None and mid not in free_approved:
            why = f":free duplicate of {base}" if base in ids else ":free endpoint without operator approval"
            rows.append({"id": mid, "include": False, "reason": f"{why} (PREREG §8.1; CLAUDE.md C13)"})
        elif mid in outcomes and (fail := outcomes[mid].failure()) is not None:
            rows.append({"id": mid, "include": False, "reason": f"failed the NA-05 calls: {fail}"})
        elif mid in outcomes and outcomes[mid].calls > 0:
            o = outcomes[mid]
            note = f"; {o.note}" if o.note else ""
            rows.append(
                {
                    "id": mid,
                    "include": True,
                    "reason": f"passed {o.ok}/{o.calls} NA-05 calls with data_collection deny{note}",
                }
            )
        else:
            rows.append({"id": mid, "include": False, "reason": "not tested in NA-05"})
    for mid in local:
        rows.append({"id": mid, "include": True, "reason": "local open-weight Laya (PREREG §8.1)"})
    return rows


_BLOCK: Final = re.compile(rf"^{ELIGIBLE_KEY}:.*\n(?:[ \t]+.*\n|[ \t]*\n)*", re.MULTILINE)


def _yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def write_eligibility(frozen: Path, rows: Sequence[Mapping[str, Any]], *, catalog_sha: str) -> None:
    """Write ``eligible_models`` into ``configs/frozen.yaml`` before ``allow_val_b``, replacing an old one."""
    lines = [
        f"{ELIGIBLE_KEY}:   # NA-05: every catalog id (snapshot sha256 {catalog_sha[:16]}…) and the local "
        "Laya checkpoints, PREREG §8.1\n"
    ]
    for r in rows:
        lines.append(
            f"  - {{id: {_yaml_str(str(r['id']))}, include: {'true' if r['include'] else 'false'}, "
            f"reason: {_yaml_str(str(r['reason']))}}}\n"
        )
    block = "".join(lines)
    text = frozen.read_text(encoding="utf-8")
    text = _BLOCK.sub("", text)
    if not re.search(rf"^{FREE_KEY}:", text, re.MULTILINE):  # the operator's key: added once, never rewritten
        block = (
            f"{FREE_KEY}: {{}}   # operator approvals of :free endpoints (CLAUDE.md C13): none; "
            'format {model_id: "approved by, date"}\n\n' + block
        )
    anchor = re.search(r"^allow_val_b:", text, re.MULTILINE)
    if anchor is None:
        raise DMError(f"{frozen}: no allow_val_b line to anchor eligible_models")
    text = text[: anchor.start()].rstrip("\n") + "\n\n" + block + "\n" + text[anchor.start() :]
    io.atomic_write_bytes(frozen, text.encode("utf-8"))
