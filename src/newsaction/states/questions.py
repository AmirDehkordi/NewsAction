"""The frozen question battery (PREREG §7, A2.1–A2.3; PRD NA-04 S4).

``load_battery()`` reads ``configs/questions_v1.yaml``; ``Battery.request(call, groups)`` returns the
decision-model ``questions`` object for a call and any combination of the groups {core, extended,
explain}: ``{key: {"type", "instructions", "criteria"}}``, where ``criteria`` maps option → description for
a ``choice`` and is a list, lowest level first, for a ``score``. ``noul`` is refused (PREREG §7).

The battery's sha256 (of the YAML bytes) is recorded in ``configs/frozen.yaml`` as ``questions_v1_sha256``
(``write_frozen_hashes``, together with the codebook's ``codebook_v1_sha256``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from newsaction.config import load_yaml
from newsaction.paths import CONFIGS
from newsaction.states import CODEBOOK_PATH, QUESTIONS_PATH

Group = Literal["core", "extended", "explain"]
GROUPS: Final[tuple[Group, ...]] = ("core", "extended", "explain")
CALLS: Final = ("A", "B")
TYPES: Final = frozenset({"choice", "score"})
MAX_SCORE_LEVELS: Final = 10  # Jev: a score has at most 10 levels
FROZEN_PATH: Final = CONFIGS / "frozen.yaml"


class QuestionsError(ValueError):
    """The battery file is malformed or asks for something PREREG §7 forbids."""


@dataclass(frozen=True)
class Question:
    key: str
    qid: str
    type: str
    instructions: str
    criteria: tuple[str, ...] | Mapping[str, str]

    def request(self) -> dict[str, Any]:
        crit: Any = list(self.criteria) if isinstance(self.criteria, tuple) else dict(self.criteria)
        return {"type": self.type, "instructions": self.instructions, "criteria": crit}


@dataclass(frozen=True)
class Battery:
    version: int
    questions: Mapping[str, Question]
    groups: Mapping[str, Mapping[str, tuple[str, ...]]]
    sha256: str

    def keys(self, call: str, groups: Iterable[str] = ("core",)) -> list[str]:
        if call not in CALLS:
            raise QuestionsError(f"unknown call {call!r}")
        out: list[str] = []
        for g in groups:
            if g not in GROUPS:
                raise QuestionsError(f"unknown group {g!r}; expected a subset of {GROUPS}")
            out += [k for k in self.groups[g][call] if k not in out]
        return out

    def request(self, call: str, groups: Iterable[str] = ("core",)) -> dict[str, dict[str, Any]]:
        """The ``questions`` object of a decision request for ``call`` and ``groups`` (in battery order)."""
        return {k: self.questions[k].request() for k in self.keys(call, groups)}


def canonical_json(obj: Any) -> str:
    """Sorted keys, compact separators, UTF-8 text (also the state serialization)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _question(key: str, raw: Mapping[str, Any]) -> Question:
    qtype = str(raw["type"])
    if qtype == "noul":
        raise QuestionsError(f"{key}: noul is not allowed (PREREG §7: two-option choice with neutral keys)")
    if qtype not in TYPES:
        raise QuestionsError(f"{key}: unknown type {qtype!r}")
    crit = raw["criteria"]
    if qtype == "score":
        if not isinstance(crit, list) or not 2 <= len(crit) <= MAX_SCORE_LEVELS:
            raise QuestionsError(f"{key}: a score needs 2..{MAX_SCORE_LEVELS} ordered levels")
        criteria: tuple[str, ...] | Mapping[str, str] = tuple(str(c) for c in crit)
    else:
        if not isinstance(crit, dict) or len(crit) < 2:
            raise QuestionsError(f"{key}: a choice needs a mapping of >= 2 options")
        criteria = {str(k): str(v) for k, v in crit.items()}
        if any(k.lower() in {"true", "false", "yes", "no"} for k in criteria):
            raise QuestionsError(f"{key}: choice keys must be neutral, not yes/no or true/false")
    text = str(raw["instructions"]).strip()
    if not text:
        raise QuestionsError(f"{key}: empty instructions")
    return Question(key=key, qid=str(raw["qid"]), type=qtype, instructions=text, criteria=criteria)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_battery(path: Path = QUESTIONS_PATH) -> Battery:
    raw = load_yaml(path)
    qs = {str(k): _question(str(k), v) for k, v in raw["questions"].items()}
    groups: dict[str, dict[str, tuple[str, ...]]] = {}
    for g in GROUPS:
        spec = raw["groups"][g]
        groups[g] = {c: tuple(str(k) for k in spec.get(c) or []) for c in CALLS}
        unknown = [k for c in CALLS for k in groups[g][c] if k not in qs]
        if unknown:
            raise QuestionsError(f"group {g} lists unknown questions {unknown}")
    used = {k for g in groups.values() for ks in g.values() for k in ks}
    if used != set(qs):
        raise QuestionsError(f"questions in no group: {sorted(set(qs) - used)}")
    return Battery(version=int(raw["version"]), questions=qs, groups=groups, sha256=sha256_file(path))


_HASH_LINE: Final = re.compile(r"^(questions_v1_sha256|codebook_v1_sha256):.*\n", re.MULTILINE)


def write_frozen_hashes(
    frozen: Path = FROZEN_PATH, questions: Path = QUESTIONS_PATH, codebook: Path = CODEBOOK_PATH
) -> dict[str, str]:
    """Record the sha256 of the battery and the codebook in ``configs/frozen.yaml`` (idempotent).

    The two keys are written as top-level lines just before ``allow_val_b`` so that the file's comments and
    layout stay as they are.
    """
    hashes = {"questions_v1_sha256": sha256_file(questions), "codebook_v1_sha256": sha256_file(codebook)}
    text = _HASH_LINE.sub("", frozen.read_text(encoding="utf-8"))
    block = "".join(f"{k}: {v}   # NA-04: sha256 of configs/{k[:-7]}.yaml\n" for k, v in hashes.items())
    anchor = re.search(r"^allow_val_b:", text, re.MULTILINE)
    if anchor is None:
        raise QuestionsError(f"{frozen}: no allow_val_b line to anchor the hashes")
    text = text[: anchor.start()].rstrip("\n") + "\n\n" + block + "\n" + text[anchor.start() :]
    frozen.write_text(text, encoding="utf-8")
    return hashes
