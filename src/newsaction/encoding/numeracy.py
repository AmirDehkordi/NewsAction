"""The numeracy probe (PRD NA-07 S3): does a model read the encoded reaction size monotonically?

It is outcome-free: no realized reaction is shown or read. Each of ``n_news`` real masked val-A Call B states
keeps its company, market, attention and news blocks, and its ``reaction_so_far`` is replaced by a synthetic
block (``synthetic_reaction``) in the encoding under test:
- the stock's move vs the market and its sector at ±|z| for |z| in ``magnitudes`` (NA-05's numeracy grid
  ``dm.canary.NUMERACY_Z``: negligible … extreme);
- the S&P 500's move at ``market_z``, volume at ``volume_multiple`` × normal, and the D2 time label (NA-05's
  canary values), the same in every block.
E0 needs raw changes and E4 percentiles, which a typical-move value does not carry. The synthetic raw change
is z × ``e0_stock_sigma`` (the S&P 500's: ``market_z`` × ``e0_market_sigma``), and the synthetic percentile
is that of |z| under a standard normal, 100·erf(|z|/√2). Both are increasing in |z|, so the probe still asks
only whether the model reads a larger move as larger.

**Score** (``monotone``). A (news, direction) series of answers over the magnitudes, in increasing order, is
monotone iff L = P(too_large) + P(much_too_large) is non-decreasing and S = P(too_small) + P(much_too_small)
is non-increasing, each up to ``tol``. A series with a missing answer is not monotone. A model's share is
its monotone series over all its series (``score``); the target is ``target_share``.

**Gate** (``gate``; PREREG §15, NA-07 row on the numeracy gate). When the encoding kept by the val-B check is
not the default (E3), a model whose share in it is below the target uses the default (PRD S3: "prefer E3 for
that model"), and the chosen encoding is the leading model's (PRD AC1). A run in the default encoding beside
it is a report-only reference.
"""

from __future__ import annotations

import itertools
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

from newsaction.encoding import NumeracyConfig
from newsaction.states import Encoding
from newsaction.states.codebook import Codebook, Move
from newsaction.states.questions import canonical_json

LARGE: Final = ("too_large", "much_too_large")
SMALL: Final = ("too_small", "much_too_small")
DIRECTIONS: Final = ("rise", "fall")
REACTION: Final = "reaction_so_far"


def percentile_of(z: float) -> float:
    """Synthetic E4 percentile: share (%) of a standard normal's |z| below |z|."""
    return 100.0 * math.erf(abs(z) / math.sqrt(2.0))


def synthetic_reaction(cb: Codebook, z: float, encoding: Encoding, cfg: NumeracyConfig) -> dict[str, str]:
    """The ``reaction_so_far`` block of a Call B state (NA-04 layout, ``states.context.reaction_block``) for a
    stock move of ``z`` typical daily moves."""
    mkt_raw = cfg.market_z * cfg.e0_market_sigma
    stock = Move(
        z=z, raw=z * cfg.e0_stock_sigma, benchmark=mkt_raw, pct=percentile_of(z), horizon="day", unit="pct"
    )
    market = Move(z=cfg.market_z, raw=mkt_raw, pct=percentile_of(cfg.market_z), horizon="day", unit="pct")
    return {
        "time": cb.time_label_word("D2"),
        "stock_move_vs_market_and_sector": cb.encode_move(stock, encoding),
        "stock_market_move": cb.encode_move(market, encoding),
        "volume_vs_normal": cb.attention_word(cfg.volume_multiple),
    }


def with_reaction(state: Mapping[str, Any], reaction: Mapping[str, str]) -> dict[str, Any]:
    """A copy of a Call B state with ``reaction_so_far`` replaced (keys in canonical order)."""
    if REACTION not in state:
        raise ValueError("not a Call B state: no reaction_so_far")
    out = {**json.loads(json.dumps(state)), REACTION: dict(reaction)}
    parsed: dict[str, Any] = json.loads(canonical_json(out))
    return parsed


def grid(magnitudes: Sequence[float]) -> list[tuple[str, int, float]]:
    """(direction, magnitude index, signed z) for every block of one news item."""
    return [
        (d, i, (1.0 if d == "rise" else -1.0) * float(m))
        for d in DIRECTIONS
        for i, m in enumerate(magnitudes)
    ]


def monotone(large: Sequence[float], small: Sequence[float], tol: float) -> bool:
    """L non-decreasing and S non-increasing over increasing magnitudes, up to ``tol``."""
    if len(large) != len(small) or len(large) < 2:
        raise ValueError("a series needs the same number (>= 2) of L and S values")
    if any(not math.isfinite(v) for v in (*large, *small)):
        return False
    up = all(b >= a - tol for a, b in itertools.pairwise(large))
    down = all(b <= a + tol for a, b in itertools.pairwise(small))
    return up and down


def series_table(answers: pd.DataFrame, n_magnitudes: int, tol: float) -> pd.DataFrame:
    """One row per (model, event_id, direction): ``answers`` has one row per request with ``model``,
    ``event_id``, ``direction``, ``magnitude_idx``, ``p_large``, ``p_small`` (NaN when not answered)."""
    rows: list[dict[str, Any]] = []
    for (m, e, d), g in answers.groupby(["model", "event_id", "direction"], sort=True):
        g = g.set_index("magnitude_idx").reindex(range(n_magnitudes))
        large = g["p_large"].astype(float).tolist()
        small = g["p_small"].astype(float).tolist()
        complete = all(math.isfinite(v) for v in (*large, *small))
        up = complete and all(b >= a - tol for a, b in itertools.pairwise(large))
        down = complete and all(b <= a + tol for a, b in itertools.pairwise(small))
        rows.append(
            {
                "model": m,
                "event_id": e,
                "direction": d,
                "complete": complete,
                "large_non_decreasing": up,
                "small_non_increasing": down,
                "monotone": monotone(large, small, tol),
                "p_large": json.dumps([round(v, 6) for v in large]),
                "p_small": json.dumps([round(v, 6) for v in small]),
            }
        )
    return pd.DataFrame(rows)


def score(series: pd.DataFrame, target: float) -> pd.DataFrame:
    """Per model: series, complete series, monotone share and the two one-sided shares; ``passes`` iff the
    monotone share >= ``target``."""
    out = (
        series.groupby("model", sort=True)
        .agg(
            n_series=("monotone", "size"),
            n_complete=("complete", "sum"),
            n_monotone=("monotone", "sum"),
            share_large_non_decreasing=("large_non_decreasing", "mean"),
            share_small_non_increasing=("small_non_increasing", "mean"),
        )
        .reset_index()
    )
    out["share"] = out["n_monotone"] / out["n_series"]
    out["target"] = target
    out["passes"] = out["share"] >= target
    return out


def gate(
    kept: str, default: str, shares: Mapping[str, float], leading: str, target: float
) -> tuple[str, dict[str, str]]:
    """(chosen encoding, encoding per model) from the monotone ``shares`` in ``kept`` (module docstring)."""
    if leading not in shares:
        raise ValueError(f"no numeracy share for the leading model {leading}")
    if kept == default:
        return default, {m: default for m in shares}
    by_model = {m: kept if share >= target else default for m, share in shares.items()}
    return by_model[leading], by_model
