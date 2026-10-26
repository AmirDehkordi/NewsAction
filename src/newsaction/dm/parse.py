"""Derived quantities from answer probabilities (PREREG §7 and A2.4; PRD NA-05 S6).

Every function takes the probabilities of one valid answer in its question's option order
(``schemas.ParsedAnswer.probs``) together with the option keys, or a mapping option → probability.

PREREG §7:
- N̂ = Σ p_k m_k over Q1's nine levels, m = (−3.5, −2.5, −1.5, −0.75, 0, 0.75, 1.5, 2.5, 3.5);
- E|N̂| = Σ p_k |m_k|;
- M = P(new_information) (Q2);
- J = P(much_too_small) + P(too_small) − P(too_large) − P(much_too_large) and W = P(wrong_direction) (Q5);
- C = P(continue) − P(reverse) (Q6);
- RG = (N̂ − G)·sign(N̂) for |N̂| ≥ 0.5: Under if RG > 0.5, Over if RG < −0.5, else Fair.

PREREG A2.4:
- H = Σ p_k h_k over {today: 1, within_days: 3, within_weeks: 15, months_or_longer: 60} sessions, with
  P(no_material_effect) removed and the rest renormalized; P(no_material_effect) is reported beside it;
- X = P(fully_explains) + 0.5·P(partly_explains) − P(contradicts) (Q16);
- the reason: the argmax of Q17 with its probability; the model-based labels of Q8–Q13 the same way;
- U_unc = the expected level of Q14 (0 = no change … 4 = very large increase); the mixed flag P(mixed) (Q15).

Confidence summaries: the model's reported ``confidence``, the largest probability, and the normalized entropy
confidence 1 − H(p)/log k.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Final, Literal

from newsaction.dm.schemas import ParsedAnswer, QuestionSpec

Q1_MIDPOINTS: Final = (-3.5, -2.5, -1.5, -0.75, 0.0, 0.75, 1.5, 2.5, 3.5)
RG_MIN_ABS_N: Final = 0.5
RG_BAND: Final = 0.5
HORIZON_SESSIONS: Final = {"today": 1.0, "within_days": 3.0, "within_weeks": 15.0, "months_or_longer": 60.0}
NO_EFFECT: Final = "no_material_effect"
LABEL_QUESTIONS: Final = ("event_type", "quantified", "scheduled", "novelty", "credibility", "scope")
RGLabel = Literal["Under", "Over", "Fair"]


class ParseError(ValueError):
    """Probabilities that do not fit the question they are said to answer."""


def _check(p: Sequence[float], n: int, what: str) -> list[float]:
    if len(p) != n:
        raise ParseError(f"{what}: {len(p)} probabilities, expected {n}")
    out = [float(v) for v in p]
    if not all(math.isfinite(v) and v >= 0 for v in out) or abs(math.fsum(out) - 1.0) > 1e-6:
        raise ParseError(f"{what}: not a probability vector")
    return out


def _by_key(p: Mapping[str, float], keys: Sequence[str], what: str) -> dict[str, float]:
    if set(p) != set(keys):
        raise ParseError(f"{what}: options {sorted(p)}, expected {sorted(keys)}")
    _check([p[k] for k in keys], len(keys), what)
    return {k: float(p[k]) for k in keys}


def n_hat(p: Sequence[float]) -> float:
    """PREREG §7 N̂: the probability-weighted move of Q1, in typical daily moves."""
    q = _check(p, len(Q1_MIDPOINTS), "justified_move")
    return math.fsum(pk * mk for pk, mk in zip(q, Q1_MIDPOINTS, strict=True))


def abs_n_hat(p: Sequence[float]) -> float:
    """PREREG §7 E|N̂| = Σ p_k |m_k|."""
    q = _check(p, len(Q1_MIDPOINTS), "justified_move")
    return math.fsum(pk * abs(mk) for pk, mk in zip(q, Q1_MIDPOINTS, strict=True))


def materiality(p: Mapping[str, float]) -> float:
    """PREREG §7 M = P(new_information)."""
    return _by_key(p, ["new_information", "no_new_information"], "materiality")["new_information"]


ADEQUACY_KEYS: Final = (
    "wrong_direction",
    "much_too_small",
    "too_small",
    "about_right",
    "too_large",
    "much_too_large",
)


def adequacy_j(p: Mapping[str, float]) -> float:
    """PREREG §7 J = P(much_too_small) + P(too_small) − P(too_large) − P(much_too_large)."""
    q = _by_key(p, ADEQUACY_KEYS, "reaction_adequacy")
    return q["much_too_small"] + q["too_small"] - q["too_large"] - q["much_too_large"]


def adequacy_w(p: Mapping[str, float]) -> float:
    """PREREG §7 W = P(wrong_direction)."""
    return _by_key(p, ADEQUACY_KEYS, "reaction_adequacy")["wrong_direction"]


def continuation_c(p: Mapping[str, float]) -> float:
    """PREREG §7 C = P(continue) − P(reverse)."""
    q = _by_key(p, ["reverse", "stall", "continue"], "continuation")
    return q["continue"] - q["reverse"]


def rg(n: float, g: float) -> tuple[float | None, RGLabel | None]:
    """PREREG §7 RG = (N̂ − G)·sign(N̂) for |N̂| ≥ 0.5 and its Under / Over / Fair label; else (None, None)."""
    if not (math.isfinite(n) and math.isfinite(g)) or abs(n) < RG_MIN_ABS_N:
        return None, None
    value = (n - g) * math.copysign(1.0, n)
    label: RGLabel = "Under" if value > RG_BAND else "Over" if value < -RG_BAND else "Fair"
    return value, label


def horizon(p: Mapping[str, float]) -> tuple[float | None, float]:
    """PREREG A2.4 H (sessions) without P(no_material_effect), renormalized; and P(no_material_effect)."""
    q = _by_key(p, [*HORIZON_SESSIONS, NO_EFFECT], "impact_horizon")
    rest = math.fsum(q[k] for k in HORIZON_SESSIONS)
    if rest <= 0:
        return None, q[NO_EFFECT]
    return math.fsum(q[k] * h for k, h in HORIZON_SESSIONS.items()) / rest, q[NO_EFFECT]


def explanation_x(p: Mapping[str, float]) -> float:
    """PREREG A2.4 X = P(fully_explains) + 0.5·P(partly_explains) − P(contradicts)."""
    q = _by_key(p, ["fully_explains", "partly_explains", "unrelated", "contradicts"], "explains_move")
    return q["fully_explains"] + 0.5 * q["partly_explains"] - q["contradicts"]


def expected_level(p: Sequence[float]) -> float:
    """The probability-weighted level of a score (0 = lowest)."""
    q = _check(p, len(p), "score")
    return math.fsum(i * v for i, v in enumerate(q))


def argmax_label(p: Mapping[str, float]) -> tuple[str, float]:
    """The most probable option (first in option order on ties) and its probability."""
    if not p:
        raise ParseError("no options")
    best = max(p, key=lambda k: p[k])
    return best, float(p[best])


def entropy_confidence(p: Sequence[float]) -> float:
    """1 − H(p)/log k (1 = one option certain, 0 = uniform)."""
    q = _check(p, len(p), "answer")
    if len(q) < 2:
        return 1.0
    h = -math.fsum(v * math.log(v) for v in q if v > 0)
    return 1.0 - h / math.log(len(q))


def probs_by_option(answer: ParsedAnswer, question: QuestionSpec) -> dict[str, float]:
    if answer.probs is None:
        raise ParseError(f"{answer.qid}: no valid probabilities")
    return dict(zip(question.options(), answer.probs, strict=True))


def derive(
    answers: Mapping[str, ParsedAnswer], questions: Mapping[str, QuestionSpec]
) -> dict[str, float | str]:
    """Every PREREG §7 / A2.4 quantity the valid answers allow (keys absent otherwise), with the confidence
    summaries per question (``conf_<id>``, ``pmax_<id>``, ``entconf_<id>``)."""
    out: dict[str, float | str] = {}
    ok = {qid: a for qid, a in answers.items() if a.valid and a.probs is not None and qid in questions}

    def pm(qid: str) -> dict[str, float]:
        return probs_by_option(ok[qid], questions[qid])

    if "justified_move" in ok:
        p1 = ok["justified_move"].probs or ()
        out["n_hat"] = n_hat(p1)
        out["abs_n_hat"] = abs_n_hat(p1)
    if "materiality" in ok:
        out["m"] = materiality(pm("materiality"))
    if "surprise" in ok:
        out["surprise"] = expected_level(ok["surprise"].probs or ())
    if "tone" in ok:
        out["tone"] = expected_level(ok["tone"].probs or ())
    if "reaction_adequacy" in ok:
        out["j"] = adequacy_j(pm("reaction_adequacy"))
        out["w"] = adequacy_w(pm("reaction_adequacy"))
    if "continuation" in ok:
        out["c"] = continuation_c(pm("continuation"))
    if "impact_horizon" in ok:
        h, none = horizon(pm("impact_horizon"))
        if h is not None:
            out["h"] = h
        out["p_no_material_effect"] = none
    if "uncertainty" in ok:
        out["u_unc"] = expected_level(ok["uncertainty"].probs or ())
    if "mixed_signals" in ok:
        out["p_mixed"] = pm("mixed_signals")["mixed"]
    if "explains_move" in ok:
        out["x"] = explanation_x(pm("explains_move"))
    for qid in (*LABEL_QUESTIONS, "move_reason"):
        if qid in ok:
            label, prob = argmax_label(pm(qid))
            out[f"label_{qid}"] = label
            out[f"plabel_{qid}"] = prob
    for qid, a in ok.items():
        p = list(a.probs or ())
        out[f"pmax_{qid}"] = max(p)
        out[f"entconf_{qid}"] = entropy_confidence(p)
        if a.confidence is not None and math.isfinite(a.confidence):
            out[f"conf_{qid}"] = float(a.confidence)
    return out
