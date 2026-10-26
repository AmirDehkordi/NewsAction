"""Local Laya behind the decision-response shape (PRD NA-05 S5, AC5).

The fast tests check the exact-probability rewrite; the slow ones load the pinned typed-decisions checkpoint
from the local Hugging Face cache (never downloaded here) and check AC5 on canary states.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from newsaction.dm import CANARY_FILE, CHUNK, DMError, dm_config
from newsaction.dm.cache import DecisionCache
from newsaction.dm.canary import load_canary
from newsaction.dm.laya_local import LayaLocal, exact_answers, softmax64
from newsaction.dm.schemas import parse_response
from newsaction.paths import ROOT

TYPED = "local/laya-typed-decisions"


def test_softmax64_sums_to_one() -> None:
    p = softmax64(np.array([1.0, 2.0, 3.0], dtype=np.float32), 0.7)
    assert math.fsum(p) == pytest.approx(1.0, abs=1e-15)
    assert p.dtype == np.float64


def test_exact_answers_keep_laya_rounding_and_refuse_drift() -> None:
    exact = {"q": [0.123456, 0.876544]}
    laya = {"q": {"type": "choice", "choice": "b", "probabilities": {"a": 0.1235, "b": 0.8765}}}
    out = exact_answers(laya, exact)
    assert out["q"]["probabilities"] == {"a": 0.123456, "b": 0.876544}
    assert out["q"]["probabilities_rounded"] == {"a": 0.1235, "b": 0.8765}
    with pytest.raises(DMError, match="differ"):
        exact_answers({"q": {"type": "choice", "probabilities": {"a": 0.2, "b": 0.8}}}, exact)
    score = exact_answers(
        {"s": {"type": "score", "score": 0.88, "probabilities": {"0": 0.1235, "1": 0.8765}}},
        {"s": exact["q"]},
    )["s"]
    assert score["score"] == pytest.approx(0.876544) and score["score_rounded"] == 0.88


def test_variants_params_and_build() -> None:
    cfg = dm_config().laya
    for model in ("local/laya-typed-decisions", "local/laya-base"):
        m = LayaLocal(model, cfg)
        assert m.build == f"{model}@{cfg.revision}"
        assert m.params["revision"] == cfg.revision and m.params["max_len"] == 1024
        assert m.device == "unloaded"
    with pytest.raises(DMError):
        LayaLocal("local/unknown", cfg)


def _checkpoint_cached() -> bool:
    cfg = dm_config().laya
    snap = Path.home() / ".cache/huggingface/hub/models--convaiinnovations--laya/snapshots" / cfg.revision
    return (snap / "typed-decisions" / "model.safetensors").exists()


@pytest.mark.slow
@pytest.mark.skipif(
    not _checkpoint_cached(), reason="the pinned Laya checkpoint is not in the local HF cache"
)
@pytest.mark.filterwarnings(
    "ignore::DeprecationWarning",
    "ignore::FutureWarning",
    "ignore::UserWarning",
    # laya clamps the checkpoint's choice:11+ temperature (0.10 -> 0.5) and says so
    "ignore:laya. this checkpoint ships invalid temperatures:RuntimeWarning",
)
def test_live_typed_decisions_on_three_canary_states() -> None:
    items = load_canary(ROOT / CANARY_FILE)
    model = LayaLocal(TYPED, dm_config().laya)
    for it in (items[0], items[20], items[35]):  # train Call A, train Call B, synthetic Call B
        req = it.request(TYPED)
        raw: dict[str, Any] = model.predict(req)
        parsed = parse_response(raw, req.questions)
        assert parsed.valid, parsed.problem_list()
        assert raw["model"] == model.build and raw["provider"] in {"local:mps", "local:cpu"}
        assert raw["usage"]["cost"] == 0.0 and "truncated" in raw["usage"]
        for qid, a in parsed.answers.items():
            assert a.probs is not None and math.fsum(a.probs) == pytest.approx(1.0, abs=1e-9)
            rounded = raw["answers"][qid]["probabilities_rounded"]
            assert [round(v, 4) for v in a.probs] == pytest.approx(list(rounded.values()), abs=1.01e-4)


def test_ac5_twenty_canary_states_from_the_pilot_cache() -> None:
    path = ROOT / dm_config().cache
    if not path.is_file():
        pytest.skip("no decision cache in this checkout")
    items = load_canary(ROOT / CANARY_FILE)[:20]
    cache = DecisionCache(path)
    rows = {r.state_sha256: r for r in cache.rows(chunk=CHUNK) if r.model == TYPED and r.tag == "canary"}
    if not rows:
        pytest.skip("the laya stage has not run")
    for it in items:
        req = it.request(TYPED)
        row = rows[req.state_sha256()]
        parsed = parse_response(row.response, req.questions)
        assert parsed.valid, (it.canary_id, parsed.problem_list())
        assert row.model_build == f"{TYPED}@{dm_config().laya.revision}" and row.cost == 0.0
        for a in parsed.answers.values():
            assert a.probs is not None and abs(math.fsum(a.probs) - 1.0) <= 1e-9
    cache.close()
