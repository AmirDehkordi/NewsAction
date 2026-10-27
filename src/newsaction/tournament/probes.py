"""Contamination probes and screens of PREREG §8.3 (PRD NA-06 S4).

Probe requests (built in ``run``; each carries a ``StateInfo.probe`` tag from ``configs/tournament.yaml``):
- **a. company identification**: the masked Call A state and one choice, "Which company is this news most
  likely about?", over the true company and 3 other S&P 500 members of the session with the same GICS sector
  and size tier (both are in the state, so a candidate outside them could be ruled out by reading the state,
  not by recognizing the company). ATOM has GICS level 1 only (PREREG §15 NA-01 / NA-04 rows), so the sector
  stands in for the industry. A sector-tier cell with fewer than 3 other members is filled from the same
  sector by nearest size rank. Names: ``panel/companies.parquet`` without the share-class suffix;
- **b. month identification** (report only): the true month and 3 other months of ``first``..``last``;
- **c. counterfactual edits** (``edits``): flip rate = the share of pairs with sign(N̂_edit) ≠ sign(N̂_orig)
  among the pairs with |N̂_orig| >= ``flip_min_abs_n_hat``;
- **d. masked vs unmasked**: the paired difference of daily ICs (unmasked − masked) on NA-04's 1,000 twins;
- **e. shuffled news**: the Call A state with its ``news`` block replaced by that of another event of the
  same 1,000 (a seeded derangement with a different company); mean daily IC and Newey–West t;
- **f. reading validity** (PREREG A2.5, report only): ``validity_tables``.

Options use the neutral keys ``option_keys``; the candidates are shuffled with a seed per event
(sha256("{seed}:{probe}:{event_id}")). Accuracy is the share of answers whose most probable option is the
true one.

**Screens** (``screens``): mechanical, with the thresholds of ``configs/tournament.yaml`` (= PREREG §8.3). A
probe without a value (no valid answer, no pair with |N̂_orig| >= 0.25) fails its screen: passing must be
shown.
"""

from __future__ import annotations

import calendar as pycal
import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from newsaction.dm.schemas import QuestionSpec
from newsaction.tournament import ScreenConfig, TournamentConfig

SCREENS: Final = ("company_identification", "counterfactual_flip", "masked_vs_unmasked", "shuffled_news")
REPORT_ONLY: Final = ("month_identification",)
_CLASS: Final = re.compile(r"\s*\((?:Class|Series)\s+[A-Z]\)\s*$")


def probe_rng(seed: int, probe: str, event_id: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{probe}:{event_id}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def company_names(companies: pd.DataFrame) -> dict[int, str]:
    """company_id → name without a share-class suffix ("Alphabet Inc. (Class A)" → "Alphabet Inc.")."""
    out: dict[int, str] = {}
    for rec in companies.sort_values(["company_id", "symbol_id"]).to_dict("records"):
        out.setdefault(int(rec["company_id"]), _CLASS.sub("", str(rec["name"])).strip())
    return out


def distractors(
    event: Mapping[Any, Any], members: pd.DataFrame, n: int, rng: np.random.Generator
) -> tuple[list[int], str]:
    """``n`` other members of the event's session: same sector and tier at random, then the same sector by
    nearest size rank. ``members`` holds the session's representative member rows (company_id, sector, tier,
    rank). Returns the company ids and how they were drawn (``sector_tier`` or ``sector_rank_fill``)."""
    own = members.loc[members["company_id"] == event["company_id"]]
    if own.empty:
        raise ValueError(f"{event['event_id']}: the company is not a member of its session")
    me = own.iloc[0]
    others = members.loc[(members["company_id"] != event["company_id"]) & (members["sector"] == me["sector"])]
    same = others.loc[others["tier"] == me["tier"]].sort_values("company_id")
    if len(same) >= n:
        pick = rng.choice(same["company_id"].to_numpy(), size=n, replace=False)
        return [int(c) for c in pick], "sector_tier"
    rest = others.loc[~others["company_id"].isin(same["company_id"])].copy()
    rest["dist"] = (rest["rank"] - me["rank"]).abs()
    fill = rest.sort_values(["dist", "company_id"]).head(n - len(same))
    ids = [int(c) for c in same["company_id"]] + [int(c) for c in fill["company_id"]]
    if len(ids) < n:
        raise ValueError(f"{event['event_id']}: fewer than {n} other members in the sector")
    return ids, "sector_rank_fill"


def months_between(first: str, last: str) -> list[str]:
    y, m = (int(x) for x in first.split("-"))
    y1, m1 = (int(x) for x in last.split("-"))
    out = []
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_label(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{pycal.month_name[m]} {y}"


def options(
    true_value: Any, others: Sequence[Any], keys: Sequence[str], rng: np.random.Generator
) -> tuple[list[tuple[str, Any]], str]:
    """The true value and the others shuffled onto ``keys``; returns [(key, value)] and the true key."""
    values = [true_value, *others]
    if len(values) != len(keys):
        raise ValueError(f"{len(values)} candidates for {len(keys)} option keys")
    order = rng.permutation(len(values))
    pairs = [(keys[i], values[j]) for i, j in enumerate(order)]
    true_key = next(k for k, v in pairs if v == true_value)
    return pairs, true_key


def company_design(
    event: Mapping[Any, Any], members: pd.DataFrame, names: Mapping[int, str], cfg: TournamentConfig
) -> dict[str, Any]:
    keys = cfg.probes.option_keys
    rng = probe_rng(cfg.seed, "company", str(event["event_id"]))
    ids, how = distractors(event, members, len(keys) - 1, rng)
    pairs, true_key = options(int(event["company_id"]), ids, keys, rng)
    return {
        "company_options": [[k, int(c), names[int(c)]] for k, c in pairs],
        "company_true_key": true_key,
        "company_draw": how,
    }


def month_design(event: Mapping[Any, Any], cfg: TournamentConfig) -> dict[str, Any]:
    keys = cfg.probes.option_keys
    mp = cfg.probes.month
    rng = probe_rng(cfg.seed, "month", str(event["event_id"]))
    true = str(event["month"])
    pool = [m for m in months_between(mp.first, mp.last) if m != true]
    if true not in months_between(mp.first, mp.last):
        raise ValueError(f"{event['event_id']}: month {true} is outside {mp.first}..{mp.last}")
    others = [pool[i] for i in sorted(rng.choice(len(pool), size=len(keys) - 1, replace=False))]
    pairs, true_key = options(true, others, keys, rng)
    return {"month_options": [[k, m, month_label(m)] for k, m in pairs], "month_true_key": true_key}


def choice_question(qid: str, instructions: str, pairs: Sequence[Sequence[Any]]) -> dict[str, QuestionSpec]:
    """One choice question ``qid`` with criteria {key: label} from [(key, value, label), …]."""
    return {
        qid: QuestionSpec(type="choice", instructions=instructions, criteria={p[0]: p[-1] for p in pairs})
    }


def derangement(event_ids: Sequence[str], companies: Sequence[int], seed: int) -> dict[str, str]:
    """recipient event → donor event: a seeded permutation in which no event keeps its own news and no donor
    is the recipient's own company (on another day)."""
    n = len(event_ids)
    if n < 3:
        raise ValueError("a derangement needs at least 3 events")
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    comp = np.asarray(companies)
    for _ in range(100 * n):
        bad = np.flatnonzero(comp[perm] == comp)  # includes fixed points
        if len(bad) == 0:
            return {event_ids[i]: event_ids[int(perm[i])] for i in range(n)}
        i = int(bad[0])
        j = int(rng.integers(n))
        perm[i], perm[j] = perm[j], perm[i]
    raise ValueError("no derangement found")


def shuffled_state(recipient: Mapping[str, Any], donor: Mapping[str, Any]) -> dict[str, Any]:
    """The recipient's state with the donor's ``news`` block (everything else unchanged)."""
    out = dict(recipient)
    out["news"] = donor["news"]
    return out


# --- scores ------------------------------------------------------------------------------------------------


def accuracy(probs: Sequence[Mapping[str, float]], true_keys: Sequence[str]) -> tuple[float, float, int]:
    """(share whose most probable option is the true one, mean P(true), n) over valid answers."""
    hits, ptrue = [], []
    for p, k in zip(probs, true_keys, strict=True):
        if not p:
            continue
        best = max(p, key=lambda x: p[x])
        hits.append(float(best == k))
        ptrue.append(float(p.get(k, math.nan)))
    n = len(hits)
    return (float(np.mean(hits)) if n else math.nan, float(np.mean(ptrue)) if n else math.nan, n)


def flip_rate(orig: npt.ArrayLike, edit: npt.ArrayLike, min_abs: float) -> tuple[float, int]:
    """Share of pairs with sign(N̂_edit) ≠ sign(N̂_orig) among pairs with |N̂_orig| >= ``min_abs`` (and both
    answers valid); and the number of such pairs."""
    o = np.asarray(orig, dtype=float)
    e = np.asarray(edit, dtype=float)
    keep = np.isfinite(o) & np.isfinite(e) & (np.abs(o) >= min_abs)
    n = int(keep.sum())
    return (float(np.mean(np.sign(e[keep]) != np.sign(o[keep]))) if n else math.nan, n)


# --- screens -----------------------------------------------------------------------------------------------


def _ok(x: float) -> bool:
    return x is not None and math.isfinite(x)


def screens(
    *,
    company_id_acc: float,
    flip: float,
    unmasked_minus_masked: float,
    unmasked_t: float,
    shuffled_t: float,
    cfg: ScreenConfig,
) -> dict[str, bool]:
    """PREREG §8.3, mechanically: company-ID <= max; flip >= min; unmasked − masked <= max or |paired t| <
    t; |shuffled t| < t. A missing value fails its screen. ``all`` = every screen passes."""
    out = {
        "company_identification": _ok(company_id_acc) and company_id_acc <= cfg.company_id_max,
        "counterfactual_flip": _ok(flip) and flip >= cfg.flip_rate_min,
        "masked_vs_unmasked": (
            _ok(unmasked_minus_masked) and unmasked_minus_masked <= cfg.unmasked_minus_masked_max
        )
        or (_ok(unmasked_t) and abs(unmasked_t) < cfg.unmasked_paired_t),
        "shuffled_news": _ok(shuffled_t) and abs(shuffled_t) < cfg.shuffled_t,
    }
    out["all"] = all(out[s] for s in SCREENS)
    return out


# --- reading validity (PREREG A2.5) ------------------------------------------------------------------------


def validity_tables(
    frame: pd.DataFrame, event_type_map: Mapping[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Confusion tables and agreement rates of the model's labels against the vendor / calendar references.

    ``frame`` has one row per event: ``label_event_type``, ``label_quantified``, ``label_scheduled``,
    ``label_credibility`` (the model's argmax labels) and the references ``tag_type``, ``tag_quantified``,
    ``tag_rumor`` (the main article's vendor tags) and ``earnings_w0`` (a scheduled report in W0). Returns the
    long confusion table (comparison, label, reference, n) and the agreement summary."""
    ref = pd.DataFrame(
        {
            "event_type": frame["tag_type"].map(lambda t: event_type_map.get(str(t), "other")),
            "quantified": frame["tag_quantified"].map(lambda b: "numbers" if bool(b) else "narrative"),
            "scheduled": frame["earnings_w0"].map(lambda b: "scheduled" if bool(b) else "unscheduled"),
            "credibility": frame["tag_rumor"].map(lambda b: "rumor" if bool(b) else "not_rumor"),
        }
    )
    model = pd.DataFrame(
        {
            "event_type": frame["label_event_type"],
            "quantified": frame["label_quantified"],
            "scheduled": frame["label_scheduled"],
            "credibility": frame["label_credibility"].map(
                lambda x: x if pd.isna(x) else ("rumor" if x == "rumor" else "not_rumor")
            ),
        }
    )
    rows, summary = [], []
    for comp in ref.columns:
        both = pd.DataFrame({"label": model[comp], "reference": ref[comp]}).dropna()
        tab = both.groupby(["label", "reference"]).size().rename("n").reset_index()
        tab.insert(0, "comparison", comp)
        rows.append(tab)
        agree = float((both["label"] == both["reference"]).mean()) if len(both) else math.nan
        summary.append({"comparison": comp, "n": len(both), "agreement": agree})
    raw = pd.DataFrame({"label": frame["label_event_type"], "reference": frame["tag_type"]}).dropna()
    raw_tab = raw.groupby(["label", "reference"]).size().rename("n").reset_index()
    raw_tab.insert(0, "comparison", "event_type_vs_raw_tag")
    rows.append(raw_tab)
    return pd.concat(rows, ignore_index=True), pd.DataFrame(summary)
