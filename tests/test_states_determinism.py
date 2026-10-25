"""PRD NA-04 AC1: rebuilding reproduces state_sha256 for every row of a 2,000-row sample.

The rebuild starts from the registered inputs (events, panel, market, snapshot, articles): the context is
recomputed for the sampled keys, every article is masked again by a fresh masker (spaCy in-process), and
the states are rendered again. The stored context rows must also match exactly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from newsaction import io
from newsaction.events import EVENTS_D0, EVENTS_D2, load_events_config, tokens
from newsaction.paths import DEFAULT_LAYOUT, ROOT
from newsaction.states import CONTEXT_COMPANY, load_states_config
from newsaction.states import build as b
from newsaction.states.questions import load_battery

FILES = {  # file -> (sample size, call, window, encoding, masked)
    "states/callA_d0_E3.parquet": (400, "A", "W0", "E3", True),
    "states/callA_d2_E3.parquet": (400, "A", "W2", "E3", True),
    "states/callB_d2_E3.parquet": (400, "B", "W2", "E3", True),
    "states/samples/callA_d0_E0.parquet": (200, "A", "W0", "E0", True),
    "states/samples/callA_d0_E4.parquet": (200, "A", "W0", "E4", True),
    "states/samples/unmasked.parquet": (200, "A", "W0", "E3", False),
    "states/market_E3.parquet": (200, "M", "W2", "E3", True),
}


@pytest.fixture(scope="module")
def sample() -> dict[str, pd.DataFrame]:
    if not all((ROOT / "work" / rel).is_file() for rel in FILES):
        pytest.skip("NA-04 state files are absent (run the build)")
    rng = np.random.default_rng(2026)
    out = {}
    for rel, (n, *_rest) in FILES.items():
        df = io.read_parquet(rel)
        out[rel] = df.iloc[np.sort(rng.choice(len(df), n, replace=False))].reset_index(drop=True)
    assert sum(len(v) for v in out.values()) == 2000
    return out


@pytest.mark.slow
def test_rebuild_reproduces_every_sha(sample: dict[str, pd.DataFrame]) -> None:
    lay, cfg = DEFAULT_LAYOUT, load_states_config()
    d0, d2 = io.read_parquet(EVENTS_D0), io.read_parquet(EVENTS_D2)
    events = {"W0": d0, "W2": d2}
    picked = {
        rel: events[w].loc[events[w]["event_id"].isin(set(s["event_id"]))]
        for rel, s in sample.items()
        for (_, call, w, *_r) in [FILES[rel]]
        if call != "M"
    }
    keys = pd.concat(
        [p[["event_id", "company_id", "session", "symbol_id", "split"]] for p in picked.values()]
    )
    company, market, reaction = b.compute_context(lay, keys.drop_duplicates("event_id"))

    stored = io.read_parquet(CONTEXT_COMPANY).merge(
        company[["session", "symbol_id"]], on=["session", "symbol_id"]
    )
    pd.testing.assert_frame_equal(
        stored.sort_values(["session", "symbol_id"]).reset_index(drop=True),
        company.sort_values(["session", "symbol_id"]).reset_index(drop=True)[list(stored.columns)],
    )

    arts = []
    for p in picked.values():
        for col in ("news_w0", "news_w2"):
            if col in p.columns:
                for cid, items in zip(p["company_id"], p[col], strict=True):
                    arts += [
                        (str(a["id"]), int(cid), b._text(a["title"]), b._text(a["snippet"])) for a in items
                    ]
    art_frame = pd.DataFrame(arts, columns=["id", "company_id", "title", "snippet"]).drop_duplicates()
    msel = b.market_selection(lay, cfg)
    msessions = set(sample["states/market_E3.parquet"]["session"])
    msel = msel.loc[msel["session_w2"].isin(msessions)]
    masked = b.mask_frame(art_frame, msel, lay, n_process=1)
    inp = b.load_inputs(lay, masked_frame=masked)
    inp = b.Inputs(
        company=company, market=market, reaction=reaction, masked=inp.masked, third_party=inp.third_party
    )
    tok = tokens.tokenizer(load_events_config().events)
    bud = b.budgets(tok, b.question_tokens(load_battery(), tok), cfg, inp.cb)

    for rel, s in sample.items():
        _, call, window, enc, is_masked = FILES[rel]
        spec = b.make_spec(rel, call, window, enc, is_masked, cfg)
        if call == "M":
            rebuilt = b.build_market_states(msel, spec, inp, cfg)
        else:
            ev = picked[rel]
            # the news list is fitted on the E3 Call A state of the event's window (states.build.run_states)
            base = b.make_spec("fit", "A", window, "E3", True, cfg)
            _, keep = b.build_event_states(ev, base, inp, cfg, budget=bud[window])
            if (call, enc, is_masked) == ("A", "E3", True):
                rebuilt, _ = b.build_event_states(ev, spec, inp, cfg, budget=bud[window])
            else:
                rebuilt, _ = b.build_event_states(ev, spec, inp, cfg, keep=keep)
        got = s[["event_id", "state_sha256"]].merge(
            rebuilt[["event_id", "state_sha256"]], on="event_id", suffixes=("", "_new")
        )
        assert len(got) == len(s), rel
        diff = got.loc[got["state_sha256"] != got["state_sha256_new"]]
        assert diff.empty, (
            f"{rel}: {len(diff)} of {len(s)} states differ, e.g. {diff['event_id'].head(3).tolist()}"
        )
