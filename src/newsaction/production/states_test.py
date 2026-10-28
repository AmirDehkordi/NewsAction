"""NA-11 S4: the test period's Call B states, after the freeze only (PREREG §4.4 step 5; PRD NA-11 S4,
AC1).

The observed reactions come from ``panel.reactions.build_reactions(..., "test", point)``, which reads the
sealed prices (and, at D1, the sealed 30-minute bars) through ``newsaction.lock`` with purpose "reactions"
(each read logged in ``ledgers/test_access.jsonl``). Everything else is NA-04's and NA-10's builder,
unchanged:

- **D2** (``callB_d2_E3_test``): the test D2 events with a Call A D2 state, each with exactly the articles of
  its Call A D2 state (``analysis/state_articles_w2.parquet``, NA-04's ``keep``), so a Call B state equals its
  Call A D2 twin except for ``reaction_so_far`` (asserted). The reaction block's history (the stock's earlier
  z_cc for E4, ``logv_mad60`` at t−1, SPY's daily changes) comes from the public panel, ``panel_test_inputs``,
  the 2026 reactions of earlier sessions and ``market_prices``, as NA-04's ``compute_context`` builds it.
- **D1** (``callB_d1_E3_test``): the test D0 events with NA-10's D1 builder and its budget (the longest
  possible reaction block, never the observed one). The first bar's volume baseline and SPY's close → 10:00
  history come from ``bars.derive.test_intraday_panel`` on the sealed bars and prices (read through the lock).

No numeric 2026 reaction is written to disk: only the states, which carry the reaction as codebook words.
"""

from __future__ import annotations

import json
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import io, lock
from newsaction.events import EVENTS_D0, EVENTS_D2, load_events_config
from newsaction.paths import Layout, resolve_layout
from newsaction.production import ProductionError
from newsaction.states import build as sb
from newsaction.states import context as ctx
from newsaction.states import load_states_config
from newsaction.states.questions import load_battery

PRODUCER: Final = "newsaction.production.states_test (NA-11 S4)"
CALL_B_D2_TEST: Final = "states/callB_d2_E3_test.parquet"
CALL_B_D1_TEST: Final = "states/callB_d1_E3_test.parquet"
STATE_ARTICLES_W2: Final = "analysis/state_articles_w2.parquet"
CALL_A_D2: Final = "states/callA_d2_E3.parquet"


def require_frozen(layout: Layout | None = None) -> None:
    if not lock.is_frozen(layout):
        raise ProductionError("S4 runs after the freeze only (artifacts/NA-11/freeze.json is missing)")


def _grid() -> list[Any]:
    cfg = load_states_config()
    first, last = sb.context_span()
    return list(ctx.session_grid(first, last, cfg.context.history_sessions))


def spy_daily_change(lay: Layout) -> np.ndarray:
    """SPY's daily return on the context grid, from ``market_prices`` (NA-04's ``compute_context``)."""
    cfg = load_states_config()
    grid = _grid()
    mp = io.read_parquet("market/market_prices.parquet", layout=lay)
    fred = io.read_parquet("market/fred_daily.parquet", layout=lay)
    levels = ctx.series_levels(mp, fred, grid, cfg)
    return np.asarray(ctx.daily_change(levels["stock_market"], "return", 1.0), dtype="float64")


def reaction_test_d2(keys: pd.DataFrame, lay: Layout) -> pd.DataFrame:
    """``reaction_so_far`` inputs at D2 for the test ``keys`` (session, symbol_id)."""
    from newsaction.panel.reactions import build_reactions

    react = build_reactions(pd.DataFrame(), "test", "D2", layout=lay)  # sealed, through the lock
    react["session"] = pd.to_datetime(react["session"]).dt.date
    pub = io.read_parquet(
        "panel/panel_public.parquet", columns=["session", "symbol_id", "z_cc", "logv_mad60"], layout=lay
    )
    t1 = io.read_parquet(
        "panel/panel_test_inputs.parquet", columns=["session", "symbol_id", "logv_mad60"], layout=lay
    )
    test_hist = (
        react[["session", "symbol_id", "g_d2"]]
        .rename(columns={"g_d2": "z_cc"})
        .merge(t1, on=["session", "symbol_id"], how="left")
    )
    hist = pd.concat([pub, test_hist], ignore_index=True)
    hist["session"] = pd.to_datetime(hist["session"]).dt.date
    k = keys[["session", "symbol_id"]].drop_duplicates()
    react = k.merge(react, on=["session", "symbol_id"], how="left")
    out = ctx.reaction_d2(react, hist, spy_daily_change(lay), _grid(), load_states_config())
    return out.sort_values(["session", "symbol_id"], kind="mergesort").reset_index(drop=True)


def reaction_test_d1(keys: pd.DataFrame, lay: Layout) -> pd.DataFrame:
    """``reaction_so_far`` inputs at D1 for the test ``keys`` (session, symbol_id)."""
    from newsaction.bars import derive
    from newsaction.panel import reactions
    from newsaction.panel.targets import blinded_bars_file, blinded_price_files

    react = reactions.build_reactions(pd.DataFrame(), "test", "D1", layout=lay)  # sealed, through the lock
    react["session"] = pd.to_datetime(react["session"]).dt.date
    bars = lock.read_sealed(blinded_bars_file(), "reactions", layout=lay)
    prices, total = (lock.read_sealed(n, "reactions", layout=lay) for n in blinded_price_files())
    intra = derive.test_intraday_panel(bars, prices, total, layout=lay)
    intra["session"] = pd.to_datetime(intra["session"]).dt.date
    g = reactions._d1(intra.dropna(subset=["ar_c10"]))  # the frozen formula, for the stock's D1 history
    hist = intra[["session", "symbol_id", "logv10_mad60"]].merge(
        g[["session", "symbol_id", "g_d1"]], on=["session", "symbol_id"], how="left"
    )
    grid = _grid()
    spy = intra.dropna(subset=["r_spy_c10"]).drop_duplicates("session").set_index("session")["r_spy_c10"]
    spy_change = spy.reindex(grid).to_numpy(dtype="float64")
    k = keys[["session", "symbol_id"]].drop_duplicates()
    react = k.merge(react, on=["session", "symbol_id"], how="left")
    out = ctx.reaction_d1(react, hist, spy_change, grid, load_states_config())
    return out.sort_values(["session", "symbol_id"], kind="mergesort").reset_index(drop=True)


def check_twins(b2: pd.DataFrame, lay: Layout) -> int:
    """Every test Call B D2 state equals its Call A D2 twin except for ``reaction_so_far``."""
    frame = io.read_parquet(CALL_A_D2, columns=["event_id", "split", "state_json"], layout=lay)
    a2 = frame.loc[frame["split"] == "test"].set_index("event_id")["state_json"]
    bad = 0
    for eid, js in zip(b2["event_id"], b2["state_json"], strict=True):
        b = json.loads(js)
        b.pop("reaction_so_far", None)
        if b != json.loads(a2[eid]):
            bad += 1
    if bad:
        raise ProductionError(
            f"{bad} test Call B D2 states differ from their Call A D2 twin beyond the reaction"
        )
    return len(b2)


def run(layout: Layout | None = None) -> dict[str, Any]:
    lay = resolve_layout(layout)
    require_frozen(lay)
    cfg = load_states_config()
    from newsaction.events import tokens

    tok = tokens.tokenizer(load_events_config().events)
    qtok = sb.question_tokens(load_battery(), tok)
    inp = sb.load_inputs(lay)
    stats: dict[str, Any] = {}

    d2 = io.read_parquet(EVENTS_D2, layout=lay)
    a2_ids = set(
        io.read_parquet(CALL_A_D2, columns=["event_id", "split"], layout=lay).query("split == 'test'")[
            "event_id"
        ]
    )
    ev2 = d2.loc[(d2["split"] == "test") & d2["event_id"].isin(a2_ids)]
    sa = io.read_parquet(STATE_ARTICLES_W2, layout=lay)
    sa = sa.loc[sa["event_id"].isin(a2_ids)].sort_values(["event_id", "rank"])
    keep = {str(e): g["article_id"].astype(str).tolist() for e, g in sa.groupby("event_id")}
    inp.reaction = reaction_test_d2(ev2, lay)
    spec = sb.make_spec("callB_d2_E3", "B", "W2", "E3", True, cfg)
    b2, _ = sb.build_event_states(ev2, spec, inp, cfg, keep=keep, allow_test=True)
    stats["callB_d2_E3_test"] = {
        "events": len(ev2),
        "states": len(b2),
        "twins_checked": check_twins(b2, lay),
        "reaction_missing": int(inp.reaction["g_d2"].isna().sum()),
    }
    entry = sb.write_states(
        sb.add_tokens(b2, tok, qtok),
        CALL_B_D2_TEST,
        "NA-11 S4: Call B on D2 for the test period (after the freeze), masked, E3",
        lay,
        PRODUCER,
    )
    stats["callB_d2_E3_test"] |= {"sha256": entry["sha256"]}

    d0 = io.read_parquet(EVENTS_D0, layout=lay)
    ev0 = d0.loc[d0["split"] == "test"]
    inp.reaction_d1 = reaction_test_d1(ev0, lay)
    t = cfg.tokens
    budget = sb.Budget(
        tok, t.total_max - t.special_tokens - qtok["B"]["longest_core"], sb.worst_reaction(tok, inp.cb, "D1")
    )
    spec = sb.make_spec("callB_d1_E3", "B", "W0", "E3", True, cfg)
    b1, _ = sb.build_event_states(ev0, spec, inp, cfg, budget=budget, allow_test=True)
    b1t = sb.add_tokens(b1, tok, qtok)
    entry = sb.write_states(
        b1t,
        CALL_B_D1_TEST,
        "NA-11 S4: Call B on D1 for the test period (after the freeze), masked, E3",
        lay,
        PRODUCER,
    )
    stats["callB_d1_E3_test"] = {
        "events": len(ev0),
        "states": len(b1),
        "sha256": entry["sha256"],
        "reaction_missing": int(inp.reaction_d1["g_d1"].isna().sum()),
        "max_tokens_with_questions": int(b1t["n_tokens_with_questions"].max()),
    }
    return stats


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
