"""The tournament samples of val-A D0 events (PRD NA-06 S1; PREREG §8.2–8.3, §4.2).

**Pool.** The val-A D0 events of ``work/events/events_d0.parquet`` that have a Call A E3 state, outside the
embargo: the first ``embargo_sessions`` (5) sessions of val-A, taken from the calendar (PREREG §4.2), which
agrees with NA-03's ``embargo`` flag (asserted).

**Draws.** Every sample is NA-04's ``states.build.stratified_sample`` of the pool with the configured strata
(tier × month) and seed: proportional allocation by largest remainder, then the events with the smallest
u = sha256("{seed}:{event_id}") in each stratum. The order inside a stratum is the same for every size, so a
smaller sample is a subset of a larger one; that is asserted, not assumed:

- identification (400) ⊂ reading validity (500) ⊂ stage 1 (700) ⊂ shuffled (1,000) ⊂ stage 2 (3,000);
- the shuffled-news sample equals NA-04's unmasked twins (``states/samples/unmasked.parquet``), so probes d
  and e run on the same 1,000 events and the masked side of probe d is stage 2's own Call A.

**D2 twins.** The Call B state of "W2:{company_id}:{session}", where it exists (``b_event_id``).

**Counterfactual** (probe c) is chosen in ``edits.select`` from the states themselves.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from typing import Final

import pandas as pd

from newsaction import calendar, io
from newsaction.config import SplitName, load_splits
from newsaction.paths import Layout, resolve_layout
from newsaction.states.build import stratified_sample
from newsaction.tournament import TournamentConfig, TournamentError

EVENTS_D0: Final = "events/events_d0.parquet"
EVENT_COLUMNS: Final = ["event_id", "company_id", "symbol_id", "session", "month", "tier", "split", "embargo"]
SAMPLE_FLAGS: Final = ("stage1", "identification", "reading_validity", "shuffled", "stage2")
SAMPLE_COLUMNS: Final = [
    "event_id",
    "company_id",
    "symbol_id",
    "session",
    "month",
    "tier",
    *SAMPLE_FLAGS,
    "unmasked_twin",
    "b_event_id",
]


def embargo_sessions(split: SplitName) -> list[pd.Timestamp]:
    """The first ``embargo_sessions`` sessions of a split (PREREG §4.2)."""
    cfg = load_splits()
    rng = cfg.splits[split]
    days = calendar.sessions(rng.start, rng.end)[: cfg.embargo_sessions]
    return [pd.Timestamp(d) for d in days]


def event_pool(cfg: TournamentConfig, layout: Layout | None = None) -> pd.DataFrame:
    """Val-A D0 events with a Call A state, embargo excluded, with the state's hash."""
    lay = resolve_layout(layout)
    ev = io.read_parquet(EVENTS_D0, columns=EVENT_COLUMNS, layout=lay)
    ev = ev.loc[ev["split"] == cfg.samples.split]
    states = io.read_parquet(
        cfg.state_files.call_a,
        columns=["event_id", "split", "state_sha256", "third_party_ok_all"],
        layout=lay,
    )
    states = states.loc[states["split"] == cfg.samples.split]
    pool = ev.merge(states[["event_id", "state_sha256", "third_party_ok_all"]], on="event_id", how="inner")
    emb = {d.date() for d in embargo_sessions(cfg.samples.split)}
    flagged = pool["session"].isin(emb)
    if not (flagged == pool["embargo"].astype(bool)).all():
        raise TournamentError(
            "NA-03's embargo flag disagrees with the calendar's first sessions of the split"
        )
    if cfg.samples.exclude_embargo:
        pool = pool.loc[~flagged]
    if not pool["third_party_ok_all"].astype(bool).all():
        raise TournamentError("a val-A Call A state holds an article that is not third-party OK")
    return pool.sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def _ids(frame: pd.DataFrame) -> set[str]:
    return set(frame["event_id"].astype(str))


def draw(
    pool: pd.DataFrame,
    cfg: TournamentConfig,
    *,
    unmasked_ids: Iterable[str],
    call_b_ids: Iterable[str],
) -> pd.DataFrame:
    """The stage-2 events with a membership flag per sample (module docstring); raises if the samples do not
    nest or the shuffled sample is not NA-04's unmasked twin set."""
    s = cfg.samples
    draws = {
        "stage1": s.stage1,
        "identification": s.identification,
        "reading_validity": s.reading_validity,
        "shuffled": s.shuffled,
        "stage2": s.stage2,
    }
    ids = {k: _ids(stratified_sample(pool, n, list(s.strata), cfg.seed)) for k, n in draws.items()}
    order = sorted(draws, key=lambda k: draws[k])
    for small, big in itertools.pairwise(order):
        if not ids[small] <= ids[big]:
            raise TournamentError(f"the {small} sample is not inside the {big} sample")
    twins = set(unmasked_ids)
    if ids["shuffled"] != twins:
        raise TournamentError("the shuffled-news sample differs from NA-04's unmasked twins")
    out = pool.loc[pool["event_id"].isin(ids["stage2"])].copy()
    for k in SAMPLE_FLAGS:
        out[k] = out["event_id"].isin(ids[k])
    out["unmasked_twin"] = out["event_id"].isin(twins)
    b_ids = set(call_b_ids)
    twin_b = out["event_id"].str.replace("W0:", "W2:", n=1, regex=False)
    out["b_event_id"] = twin_b.where(twin_b.isin(b_ids), None)
    return out[SAMPLE_COLUMNS].sort_values(["session", "company_id"], kind="mergesort").reset_index(drop=True)


def build_samples(cfg: TournamentConfig, layout: Layout | None = None) -> pd.DataFrame:
    """``draw`` on the registered inputs (pool, NA-04's unmasked twins, Call B val-A states)."""
    lay = resolve_layout(layout)
    pool = event_pool(cfg, lay)
    twins = io.read_parquet(cfg.state_files.unmasked, columns=["event_id"], layout=lay)
    b = io.read_parquet(cfg.state_files.call_b, columns=["event_id", "split"], layout=lay)
    b = b.loc[b["split"] == cfg.samples.split]
    return draw(pool, cfg, unmasked_ids=twins["event_id"], call_b_ids=b["event_id"])
