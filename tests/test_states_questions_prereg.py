"""PRD NA-04 S4 / AC7: configs/questions_v1.yaml equals PREREG §7 (core) and A2.2–A2.3 (extended, explain).

Every id, type, option key and every string PREREG gives verbatim is parsed from the PREREG table rows and
compared with the battery. Text PREREG leaves to NA-04 must reference state fields in backticks and state no
empirical finding. The sha256 of the file is recorded in configs/frozen.yaml; ``noul`` is refused.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from newsaction.config import load_frozen
from newsaction.paths import ROOT
from newsaction.states import QUESTIONS_PATH
from newsaction.states.questions import QuestionsError, load_battery, sha256_file, write_frozen_hashes

PREREG = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")
BATTERY = load_battery()
QS = BATTERY.questions

IDS = {
    "justified_move": "Q1",
    "materiality": "Q2",
    "surprise": "Q3",
    "tone": "Q4",
    "reaction_adequacy": "Q5",
    "continuation": "Q6",
    "impact_horizon": "Q7",
    "event_type": "Q8",
    "quantified": "Q9",
    "scheduled": "Q10",
    "novelty": "Q11",
    "credibility": "Q12",
    "scope": "Q13",
    "uncertainty": "Q14",
    "mixed_signals": "Q15",
    "explains_move": "Q16",
    "move_reason": "Q17",
}
GROUPS = {
    "core": {
        "A": ["justified_move", "materiality", "surprise", "tone"],
        "B": ["justified_move", "reaction_adequacy", "continuation"],
    },
    "extended": {
        "A": [
            "impact_horizon",
            "event_type",
            "quantified",
            "scheduled",
            "novelty",
            "credibility",
            "scope",
            "uncertainty",
            "mixed_signals",
        ],
        "B": [],
    },
    "explain": {"A": [], "B": ["explains_move", "move_reason"]},
}
EMPIRICAL = re.compile(
    r"\b(?:tends?|tend to|usually|typically|historically|on average|often|more likely|less likely|research|"
    r"studies|evidence|underreact|overreact|drift|momentum|revert)\b",
    re.IGNORECASE,
)


def prereg_row(key: str) -> tuple[str, str]:
    """(type, wording) of the PREREG table row of question ``key``."""
    head = f"| {IDS[key]} `{key}` |"
    lines = [ln.strip() for ln in PREREG.splitlines() if ln.strip().startswith(head)]
    assert len(lines) == 1, head
    cells = [c.strip() for c in lines[0][len(head) :].strip().strip("|").split(" | ")]
    return cells[0], cells[1] if len(cells) > 1 else ""


def options(wording: str) -> list[tuple[str, str | None, str | None]]:
    """(key, parenthetical, quoted description) of each option inside the braces of a wording cell."""
    m = re.search(r"\{(.*)\}", wording)
    assert m, wording
    out: list[tuple[str, str | None, str | None]] = []
    for tok in re.finditer(r'"([^"]*)"|([a-z_]+)(?:\s*\(([^)]*)\))?', m.group(1)):
        if tok.group(2):
            out.append((tok.group(2), tok.group(3), None))
        elif out:
            key, paren, _ = out[-1]
            out[-1] = (key, paren, tok.group(1))
    return out


def quoted(wording: str) -> list[str]:
    return re.findall(r'"([^"]*)"', wording.split("{")[0])


def test_ids_types_and_groups() -> None:
    assert set(QS) == set(IDS)
    for key, q in QS.items():
        assert q.qid == IDS[key]
        ptype, _ = prereg_row(key)  # "score, 9 levels" / "score, 5" / "choice"
        assert q.type == ptype.split(",")[0], key
        if "," in ptype:
            assert len(q.criteria) == int(re.findall(r"\d+", ptype)[0]), key
    assert {g: {c: list(v) for c, v in calls.items()} for g, calls in BATTERY.groups.items()} == GROUPS


def test_loader_combines_groups() -> None:
    assert list(BATTERY.request("A")) == GROUPS["core"]["A"]
    assert list(BATTERY.request("A", ["core", "extended"])) == GROUPS["core"]["A"] + GROUPS["extended"]["A"]
    assert list(BATTERY.request("B", ["core", "explain"])) == GROUPS["core"]["B"] + GROUPS["explain"]["B"]
    assert list(BATTERY.request("B", ["extended"])) == []
    assert (
        list(BATTERY.request("A", ["core", "extended", "explain"]))
        == GROUPS["core"]["A"] + GROUPS["extended"]["A"]
    )
    req = BATTERY.request("B")["reaction_adequacy"]
    assert set(req) == {"type", "instructions", "criteria"} and isinstance(req["criteria"], dict)
    assert isinstance(BATTERY.request("A")["justified_move"]["criteria"], list)
    with pytest.raises(QuestionsError):
        BATTERY.request("A", ["bonus"])


def test_verbatim_instructions() -> None:
    """Questions whose PREREG wording starts with a quoted sentence use it verbatim."""
    verbatim = 0
    for key, q in QS.items():
        _, wording = prereg_row(key)
        if wording.startswith('"'):
            assert q.instructions == quoted(wording)[0], key
            verbatim += 1
    assert verbatim == 8  # Q1, Q3, Q4, Q7, Q8, Q14, Q16, Q17


def test_q1_levels() -> None:
    line = next(
        ln.strip() for ln in PREREG.splitlines() if ln.strip().startswith("Q1's levels, low to high:")
    )
    levels = [s.strip().rstrip(".") for s in line.split(":", 1)[1].split(" · ")]
    crit = list(QS["justified_move"].criteria)
    assert len(crit) == 9 == len(levels)
    assert crit[:5] == levels[:5]  # the falls and the middle, verbatim
    for i in range(5, 9):  # the rises: PREREG's word, with the mirrored range of the matching fall
        word, mirror = levels[i], crit[8 - i]
        assert crit[i] == word + mirror[mirror.index(" (") :].replace("fall", "rise")


def test_option_keys_and_verbatim_descriptions() -> None:
    for key, q in QS.items():
        _, wording = prereg_row(key)
        if q.type != "choice" or key == "move_reason":
            continue
        opts = options(wording)
        assert list(q.criteria) == [k for k, _, _ in opts], key
        for k, paren, desc in opts:
            if desc is not None:
                assert dict(q.criteria)[k] == desc, (key, k)
            if paren is not None:
                assert paren in dict(q.criteria)[k], (key, k)


def test_q17_categories() -> None:
    q8 = [k for k in QS["event_type"].criteria if k != "other"]
    assert len(q8) == 9
    assert list(QS["move_reason"].criteria) == [*q8, "market_or_sector_move", "no_identifiable_news"]
    for k in q8:
        assert dict(QS["move_reason"].criteria)[k] == dict(QS["event_type"].criteria)[k]


def test_score_end_points() -> None:
    for key in ("surprise", "tone", "uncertainty"):
        _, wording = prereg_row(key)
        q = quoted(wording)
        crit = list(QS[key].criteria)
        assert len(crit) == 5
        assert (crit[0], crit[-1]) == (q[1], q[2]), key


def test_call_b_descriptions_follow_prereg() -> None:
    assert all("what the news justifies" in d for d in dict(QS["reaction_adequacy"].criteria).values())
    assert (
        "over the next five trading days, relative to the market and its sector"
        in QS["continuation"].instructions
    )


def test_authored_text_references_state_fields_and_states_no_finding() -> None:
    for key, q in QS.items():
        _, wording = prereg_row(key)
        if not wording.startswith('"'):
            assert re.search(r"`(?:news|reaction_so_far)`", q.instructions), key
        texts = [q.instructions, *(q.criteria.values() if isinstance(q.criteria, dict) else q.criteria)]
        for t in texts:
            assert not EMPIRICAL.search(t), (key, t)
            for field in re.findall(r"`([^`]+)`", t):
                assert field in {"news", "reaction_so_far"}, (key, field)


def test_no_noul_and_neutral_keys() -> None:
    raw = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    assert all(v["type"] != "noul" for v in raw["questions"].values())
    for q in QS.values():
        if q.type == "choice":
            assert not {k.lower() for k in q.criteria} & {"yes", "no", "true", "false"}


def test_loader_refuses_noul(tmp_path: Path) -> None:
    raw = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    raw["questions"]["materiality"] = {"qid": "Q2", "type": "noul", "instructions": "x", "criteria": {}}
    path = tmp_path / "q.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(QuestionsError, match="noul is not allowed"):
        load_battery(path)


def test_sha256_recorded_in_frozen() -> None:
    frozen = load_frozen()
    assert getattr(frozen, "questions_v1_sha256", None) == sha256_file(QUESTIONS_PATH)
    assert getattr(frozen, "codebook_v1_sha256", None) == sha256_file(ROOT / "configs" / "codebook_v1.yaml")


def test_write_frozen_hashes_is_idempotent(tmp_path: Path) -> None:
    frozen = tmp_path / "frozen.yaml"
    frozen.write_text((ROOT / "configs" / "frozen.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    write_frozen_hashes(frozen)
    once = frozen.read_bytes()
    write_frozen_hashes(frozen)
    assert frozen.read_bytes() == once
    assert yaml.safe_load(once)["questions_v1_sha256"] == sha256_file(QUESTIONS_PATH)
