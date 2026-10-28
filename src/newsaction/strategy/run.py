"""NA-13 run: every pre-registered book, its benchmarks and the random-signal placebo on one split.

    uv run python -m newsaction.strategy.run val_b      # reference (the maps and gates were fit on val-A)
    uv run python -m newsaction.strategy.run test       # needs work/strategy/market_test.parquet
    uv run python -m newsaction.strategy.run trials     # once, after both: the "strategy" rows of the ledger

**Rules** (``rules``, from configs/frozen.yaml ``strategy``; models: Laya-Fin, the primary instrument;
d1-ultra,
the best API comparator, model-specific; the anchor, reported as uninformative):

- S-CONV (A1.6, primary): U = V − G^lvl at D2 (V from Call A on W2 news) and D1 (V from Call A on W0 news,
  G^lvl at 10:00); long the top (price below value). Exits: D2 t+1, t+5, t+20; D1 C_t, t+1, t+5, t+20.
- S-D0: Ñ (Call A on W0); ties on N̂. Exits C_t and C_{t+1}. Gated: Q1 three-class confidence of Call A ≥ the
  model's frozen D0 gate.
- S-D1 and S-D2: J and RG. §7 defines both relative to a direction: J (Q5; a trained model's J is its
  continuation head C) says whether the move so far is too small or too large, so the expected drift is
  sign(G)·J; RG = (N̂ − G)·sign(N̂) for |N̂| ≥ 0.5 (N̂ from Call A, the unanchored reading NA-12 used), so the
  expected drift in the news direction is sign(N̂)·RG = N̂ − G. The books rank those signed values. S-D1 exits
  C_t, t+1, t+5; S-D2 exits t+1, t+5, t+20; S-D2 gated on Call B's confidence ≥ the frozen D2 gate; S-D1 has
  no frozen gate (not run gated).
- Benchmarks: gap fade (price-only: −G^lvl, the S-CONV rank with V = 0) at D1 and D2 for S-CONV's exits; the
  vendor-sentiment rank (NA-09's ``N_hat``; retrospective labels, CLAUDE.md A6: a possibly look-ahead-
  contaminated upper bound) at D0 for S-D0's exits; the placebo: 100 uniform random signals (seeds
  ``SEED`` + 1 … + 100) on each rule's own universe, the same sides, entry, exit, hedge and costs.

**Inputs and their instants** (checked per position by ``portfolios.check_timing``): the latest article of the
state (``latest_et``), the reaction (the 10:00 bar end at D1, close(t) at D2), the tier (close of the prior
month's ranking session), β_m and ADV (close of the session before entry), and the model's frozen maps and
gates
(the close of the last session their val-A fits read).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction import calendar, io
from newsaction.config import load_splits, load_yaml
from newsaction.paths import CONFIGS, Layout, resolve_layout
from newsaction.strategy import costs as cs
from newsaction.strategy import market as mk
from newsaction.strategy import portfolios as pf

CHUNK: Final = "NA-13"
ARTIFACTS: Final = "artifacts/NA-13"
RESULTS: Final = f"{ARTIFACTS}/results"
SPLITS: Final = ("val_b", "test")
MODELS: Final = ("laya_fin", "d1_ultra", "anchor")
CALIBRATION_KEY: Final = {"laya_fin": "laya_fin", "anchor": "anchor", "d1_ultra": "liquid/d1-ultra"}
UNINFORMATIVE: Final = ("anchor",)
TIERS: Final = ("top100", "mid", "rest")
PLACEBO_SEEDS: Final = 100
E5_HORIZON: Final = 4  # e5 and E5^lvl end at C_{t+4} (PREREG §5.6): the maps' last outcome
FRAME: Final = "analysis/frame_{point}_{model}.parquet"
SENTIMENT: Final = "baselines/sentiment.parquet"
TIERS_MONTHLY: Final = "panel/tiers_monthly.parquet"
OUT_DAILY: Final = "strategy/books_{split}.parquet"
OUT_POSITIONS: Final = "strategy/positions_{split}.parquet"
OUT_PLACEBO: Final = "strategy/placebo_{split}.parquet"
ENTRY_TEXT: Final = {"open_t": "open_t", "10:00 bar close": "bar10_t", "open_t+1": "open_t+1"}
D0_COLS: Final = ("a0_n_hat", "a0_n_tilde", "a0_v", "b1_j", "g_d1", "g_d1_lvl")
D2_COLS: Final = ("a2_n_hat", "a2_v", "b2_j", "g_d2", "g_d2_lvl")
BASE_COLS: Final = ("event_id", "session", "symbol_id", "company_id", "tier", "split", "embargo", "latest_et")
AVAILABLE: Final = ("news_utc", "reaction_utc", "tier_utc", "risk_utc", "calibration_utc")
UNIVERSE_COLS: Final = ("event_id", "session", "symbol_id", "company_id", "tier")


class RunError(RuntimeError):
    pass


def frozen_strategy() -> dict[str, Any]:
    block: dict[str, Any] = load_yaml(CONFIGS / "frozen.yaml")["strategy"]
    return block


def frozen_calibration(model: str) -> dict[str, Any]:
    out: dict[str, Any] = load_yaml(CONFIGS / "frozen.yaml")["calibration"][CALIBRATION_KEY[model]]
    return out


# --- rules --------------------------------------------------------------------------------------------------


def rules() -> list[pf.Rule]:
    """Every pre-registered book and benchmark (configs/frozen.yaml ``strategy``), S-CONV first."""
    st = frozen_strategy()
    out: list[pf.Rule] = []
    conv = st["s_conv"]["points"]
    conv_points: tuple[pf.Point, ...] = ("D2", "D1")
    for m in MODELS:
        for point in conv_points:
            out += [pf.Rule("S-CONV", point, "u", e, m) for e in conv[point]["exits"]]
    d0 = [st["s_d0"]["exit"], st["s_d0"]["secondary_exit"]]
    gate_points = set(st["gating"]["points"])
    for m in MODELS:
        out += [pf.Rule("S-D0", "D0", "n_tilde", e, m) for e in d0]
        if "D0" in gate_points:
            out += [pf.Rule("S-D0", "D0", "n_tilde", e, m, gated=True) for e in d0]
    j_rg: tuple[tuple[str, pf.Point, str], ...] = (("S-D1", "D1", "s_d1"), ("S-D2", "D2", "s_d2"))
    for fam, point, key in j_rg:
        for m in MODELS:
            for sig in ("j", "rg"):
                out += [pf.Rule(fam, point, sig, e, m) for e in st[key]["exits"]]
                if point in gate_points:
                    out += [pf.Rule(fam, point, sig, e, m, gated=True) for e in st[key]["exits"]]
    for point in conv_points:
        out += [pf.Rule("gap_fade", point, "gap", e) for e in conv[point]["exits"]]
    out += [pf.Rule("vendor_sentiment", "D0", "sentiment", e) for e in d0]
    return out


def check_entries() -> None:
    """The code's entry per point equals the frozen text (configs/frozen.yaml ``strategy``)."""
    st = frozen_strategy()
    frozen = {
        "D0": st["s_d0"]["entry"],
        "D1": st["s_d1"]["entry"],
        "D2": st["s_d2"]["entry"],
    }
    for point, text in (
        ("D1", st["s_conv"]["points"]["D1"]["entry"]),
        ("D2", st["s_conv"]["points"]["D2"]["entry"]),
    ):
        if text != frozen[point]:
            raise RunError(f"S-CONV's {point} entry {text!r} differs from {frozen[point]!r}")
    for point, text in frozen.items():
        if ENTRY_TEXT.get(text) != pf.ENTRY_OF_POINT[point]:  # type: ignore[index]
            raise RunError(f"{point}: code entry {pf.ENTRY_OF_POINT[point]!r} differs from frozen {text!r}")  # type: ignore[index]


# --- events and their inputs --------------------------------------------------------------------------------


def _utc_minutes(session: pd.Series, minutes: pd.Series) -> pd.Series:
    midnight = pd.to_datetime(session.astype(str)).dt.tz_localize("America/New_York")
    return (midnight + pd.to_timedelta(minutes, unit="min")).dt.tz_convert("UTC")


def _by_session(days: Iterable[date], fn: Any) -> dict[date, pd.Timestamp]:
    return {d: fn(d) for d in sorted(set(days))}


def calibration_utc(model: str) -> pd.Timestamp:
    """The close of the last session the model's frozen maps (e5 at t+4) and gates read."""
    cal = frozen_calibration(model)
    ends = []
    for src in ("a0", "a2"):
        if src in cal:
            end = date.fromisoformat(cal[src]["fit_range"][1])
            ends.append(calendar.close_utc(pf.session_after(end, E5_HORIZON)))
    for g in cal.get("gates", {}).values():
        ends.append(calendar.close_utc(date.fromisoformat(g["fit_range"][1])))
    return max(ends)


def tier_instants(sessions: pd.Series, layout: Layout | None = None) -> pd.Series:
    tm = io.read_parquet(TIERS_MONTHLY, columns=["month", "ranking_session"], layout=layout).drop_duplicates()
    rank = {str(m): pd.to_datetime(r).date() for m, r in zip(tm["month"], tm["ranking_session"], strict=True)}
    months = sessions.map(lambda d: f"{d.year:04d}-{d.month:02d}")
    close = {m: calendar.close_utc(r) for m, r in rank.items()}
    return months.map(close)


def gate_values(model: str) -> dict[str, float]:
    return {p: float(g["value"]) for p, g in frozen_calibration(model).get("gates", {}).items()}


def conf3(model: str, splits: Sequence[str], layout: Layout | None = None) -> pd.DataFrame:
    """Q1's three-class confidence of Call A on W0 (``a0_conf3``) and Call B at D2 (``b2_conf3``)."""
    if model == "d1_ultra":
        d0 = io.read_parquet(
            FRAME.format(point="d0", model=model), columns=["event_id", "a0_conf3"], layout=layout
        )
        d2 = io.read_parquet(
            FRAME.format(point="d2", model=model), columns=["event_id", "b2_conf3"], layout=layout
        )
        return d0.merge(d2, on="event_id", how="outer")
    from newsaction.analysis import frames
    from newsaction.production import select_final

    r = select_final.with_conf3(frames.readings_trained(model, list(splits), layout, s7=True))
    return r[["event_id", "a0_conf3", "b2_conf3"]]


def _signals(df: pd.DataFrame, point: pf.Point, rg_min: float) -> pd.DataFrame:
    if point == "D0":
        df["n_tilde"] = df["a0_n_tilde"]
        df["tiebreak"] = df["a0_n_hat"]
    elif point == "D1":
        df["u"] = df["a0_v"] - df["g_d1_lvl"]
        df["j"] = np.sign(df["g_d1"]) * df["b1_j"]
        df["rg"] = (df["a0_n_hat"] - df["g_d1"]).where(df["a0_n_hat"].abs() >= rg_min)
        df["gap"] = -df["g_d1_lvl"]
    else:
        df["u"] = df["a2_v"] - df["g_d2_lvl"]
        df["j"] = np.sign(df["g_d2"]) * df["b2_j"]
        df["rg"] = (df["a2_n_hat"] - df["g_d2"]).where(df["a2_n_hat"].abs() >= rg_min)
        df["gap"] = -df["g_d2_lvl"]
    return df


def event_frame(model: str, point: pf.Point, split: str, layout: Layout | None = None) -> pd.DataFrame:
    """One model's events of ``split`` at ``point`` outside the embargo, its signals and input instants."""
    lay = resolve_layout(layout)
    name = "d2" if point == "D2" else "d0"
    cols = [*BASE_COLS, *(D2_COLS if point == "D2" else D0_COLS)]
    df = io.read_parquet(FRAME.format(point=name, model=model), columns=cols, layout=lay)
    df = df.loc[(df["split"] == split) & ~df["embargo"].astype(bool)].reset_index(drop=True)
    df["session"] = pd.to_datetime(df["session"]).dt.date
    rg = load_yaml(CONFIGS / "frozen.yaml")["thresholds"]["rg"]["min_abs_n_hat"]
    df = _signals(df, point, float(rg))
    c = conf3(model, [split], lay)
    df = df.merge(c, on="event_id", how="left", validate="one_to_one")
    gates = gate_values(model)
    gate_col = {"D0": "a0_conf3", "D2": "b2_conf3"}.get(point)
    df["gate_pass"] = (df[gate_col] >= gates[point]) if gate_col and point in gates else False
    df["news_utc"] = _utc_minutes(pd.Series(df["session"]), df["latest_et"])
    react = {"D0": None, "D1": calendar.d1_utc, "D2": calendar.close_utc}[point]
    df["reaction_utc"] = df["session"].map(_by_session(df["session"], react)) if react else pd.NaT
    df["tier_utc"] = tier_instants(pd.Series(df["session"]), lay)
    df["calibration_utc"] = calibration_utc(model)
    return df


def sentiment_frame(split: str, layout: Layout | None = None) -> pd.DataFrame:
    """D0 events with NA-09's vendor-sentiment N_hat (retrospective labels: a look-ahead upper bound)."""
    base = event_frame("laya_fin", "D0", split, layout)
    s = io.read_parquet(SENTIMENT, columns=["event_id", "call", "N_hat"], layout=layout)
    s = s.loc[s["call"] == "A", ["event_id", "N_hat"]].rename(columns={"N_hat": "sentiment"})
    keep = [*BASE_COLS, "news_utc", "tier_utc"]
    return base[[c for c in keep if c in base.columns]].merge(
        s, on="event_id", how="left", validate="one_to_one"
    )


def available_for(rule: pf.Rule) -> list[str]:
    out = ["tier_utc", "risk_utc"]
    if rule.family != "gap_fade":
        out.append("news_utc")
    if rule.point in ("D1", "D2"):
        out.append("reaction_utc")
    if rule.model is not None:
        out.append("calibration_utc")
    return out


def rule_events(rule: pf.Rule, frames_: Mapping[tuple[str, str], pd.DataFrame]) -> pd.DataFrame:
    if rule.family == "vendor_sentiment":
        df = frames_[("sentiment", "D0")]
    else:
        df = frames_[(rule.model or "laya_fin", rule.point)]
    keep = df[rule.signal].notna()
    if rule.gated:
        keep &= df["gate_pass"].astype(bool)
    return df.loc[keep].reset_index(drop=True)


# --- one split ----------------------------------------------------------------------------------------------


def market_frame(split: str, layout: Layout | None = None) -> pd.DataFrame:
    rel = mk.TEST_OUT if split == "test" else mk.PUBLIC_OUT
    m = io.read_parquet(rel, layout=layout)
    sp = load_splits().splits[split]  # type: ignore[index]
    m["session"] = pd.to_datetime(m["session"]).dt.date
    return m.loc[[sp.start <= d <= sp.end for d in m["session"]]].reset_index(drop=True)


def universe_key(rule: pf.Rule, events: pd.DataFrame) -> str:
    h = hashlib.sha256("\n".join(sorted(events["event_id"].astype(str))).encode()).hexdigest()[:16]
    return f"{rule.point}|{rule.exit}|{h}"


def percentile(value: float, null: np.ndarray) -> float:
    """Share of the placebo below ``value`` (ties count half), in percent."""
    n = np.asarray(null, dtype=float)
    if len(n) == 0 or not np.isfinite(value):
        return float("nan")
    return float(100.0 * (np.sum(n < value) + 0.5 * np.sum(n == value)) / len(n))


@dataclass
class Placebo:
    gross: np.ndarray
    net: dict[str, np.ndarray]


def placebo(u: pf.Universe, seeds: int) -> Placebo:
    ev = u.events
    cohort = ev["cohort"].to_numpy(dtype=np.int64)
    g = pf.groups(cohort, ev["tier"].to_numpy(dtype=object))
    ids = ev["event_id"].tolist()
    w = np.zeros((seeds, len(ev)))
    for i in range(seeds):
        score = pf.draws(ids, pf.SEED + 1 + i)
        side = pf.sides(cohort, g, score, None, np.zeros(len(ev)))
        w[i] = pf.weights(side, cohort, u.n_cohorts)
    d = pf.evaluate(u, w)
    return Placebo(
        pf.sharpe_rows(d.gross),
        {f"{int(bp)}": pf.sharpe_rows(cs.net(d.gross, d.turnover, bp)) for bp in cs.LEVELS_BP},
    )


def run_split(split: str, layout: Layout | None = None, *, seeds: int = PLACEBO_SEEDS) -> dict[str, Any]:
    lay = resolve_layout(layout)
    if split not in SPLITS:
        raise RunError(f"NA-13 runs on {SPLITS}; val-A is in-sample for the maps and gates")
    check_entries()
    t0 = time.time()
    sp = load_splits().splits[split]  # type: ignore[index]
    sessions = calendar.sessions(sp.start, sp.end)
    mkt = market_frame(split, lay)
    frames_: dict[tuple[str, str], pd.DataFrame] = {}
    points: tuple[pf.Point, ...] = ("D0", "D1", "D2")
    for m in MODELS:
        for point in points:
            frames_[(m, point)] = event_frame(m, point, split, lay)
    frames_[("sentiment", "D0")] = sentiment_frame(split, lay)

    universes: dict[str, pf.Universe] = {}
    placebos: dict[str, Placebo] = {}
    daily_rows: list[pd.DataFrame] = []
    pos_rows: list[pd.DataFrame] = []
    books: list[dict[str, Any]] = []
    for rule in rules():
        ev = rule_events(rule, frames_)
        key = universe_key(rule, ev)
        if key not in universes:
            universes[key] = pf.build_universe(ev[list(UNIVERSE_COLS)], mkt, rule.point, rule.exit, sessions)
        u = universes[key]
        if u.counts.get("events", 0) == 0:
            books.append(
                {
                    "rule": rule.key,
                    **asdict(rule),
                    "split": split,
                    "universe": key,
                    **u.counts,
                    "uninformative": rule.model in UNINFORMATIVE,
                    "n_positions": 0,
                    "empty": True,
                }
            )
            continue
        ue = u.events.copy()
        ue["risk_utc"] = ue["entry_idx"].map(
            lambda i: calendar.close_utc(calendar.prev_session(sessions[int(i)]))
        )
        need = available_for(rule)
        for c in need:
            if c != "risk_utc":
                ue[c] = pf.aligned(u, ev, c)
        pf.check_timing(ue, need)
        score = pf.aligned(u, ev, rule.signal).to_numpy(dtype=float)
        tb = pf.aligned(u, ev, "tiebreak").to_numpy(dtype=float) if rule.signal == "n_tilde" else None
        side = pf.select(u, score, tb)
        cohort = ue["cohort"].to_numpy(dtype=np.int64)
        w = pf.weights(side, cohort, u.n_cohorts)
        rec: dict[str, Any] = {"rule": rule.key, **asdict(rule), "split": split, "universe": key, **u.counts}
        rec["uninformative"] = rule.model in UNINFORMATIVE
        rec["n_positions"] = int((side != 0).sum())
        if rec["n_positions"] == 0:
            rec["empty"] = True
            books.append(rec)
            continue
        if key not in placebos:
            placebos[key] = placebo(u, seeds)
        d = pf.evaluate(u, w)
        s = pf.summary(d.gross[0], d.turnover[0], d.active[0])
        capy = pf.capacity_of(u, w)
        rec.update(s)
        rec.update({f"capacity_{k}": v for k, v in asdict(capy).items()})
        pl = placebos[key]
        rec["placebo_pct_gross"] = percentile(s["sharpe_gross"], pl.gross)
        for bp in cs.LEVELS_BP:
            tag = f"{int(bp)}"
            rec[f"placebo_pct_net_{tag}"] = percentile(s[f"sharpe_net_{tag}"], pl.net[tag])
            rec[f"placebo_median_net_{tag}"] = float(np.median(pl.net[tag]))
            rec[f"placebo_p95_net_{tag}"] = float(np.quantile(pl.net[tag], 0.95))
        traded = np.unique(cohort[side != 0])
        rec["n_cohorts_traded"] = len(traded)
        rec["mean_names_per_side"] = float(rec["n_positions"] / 2 / len(traded))
        books.append(rec)
        frame = pd.DataFrame(
            {
                "rule": rule.key,
                "split": split,
                "tier": "all",
                "session": u.sessions,
                "gross": d.gross[0],
                "turnover": d.turnover[0],
                "active": d.active[0],
            }
        )
        parts = [frame]
        tier = ue["tier"].to_numpy(dtype=object)
        for t in TIERS:
            wt = pf.tier_weights(side, cohort, tier, t, u.n_cohorts)
            dt = pf.evaluate(u, wt)
            parts.append(
                pd.DataFrame(
                    {
                        "rule": rule.key,
                        "split": split,
                        "tier": t,
                        "session": u.sessions,
                        "gross": dt.gross[0],
                        "turnover": dt.turnover[0],
                        "active": dt.active[0],
                    }
                )
            )
        daily_rows += parts
        on = side != 0
        p = ue.loc[
            on,
            [
                "event_id",
                "session",
                "symbol_id",
                "tier",
                "cohort",
                "beta",
                "adv20",
                "decision_utc",
                "entry_utc",
                "exit_utc",
                *[c for c in AVAILABLE if c in ue.columns],
            ],
        ].copy()
        p.insert(0, "rule", rule.key)
        p["side"] = side[on].astype(np.int64)
        p["weight"] = w[on]
        p["score"] = score[on]
        pos_rows.append(p)

    daily = pd.concat(daily_rows, ignore_index=True)
    for bp in cs.LEVELS_BP:
        daily[f"net_{int(bp)}"] = cs.net(daily["gross"].to_numpy(), daily["turnover"].to_numpy(), bp)
    positions = pd.concat(pos_rows, ignore_index=True)
    for c in ("decision_utc", "entry_utc", "exit_utc", *AVAILABLE):
        if c in positions.columns:
            positions[c] = pd.to_datetime(positions[c], utc=True)
    pl_rows = []
    for key, pl in placebos.items():
        for i in range(len(pl.gross)):
            pl_rows.append(
                {
                    "universe": key,
                    "seed": pf.SEED + 1 + i,
                    "sharpe_gross": float(pl.gross[i]),
                    **{f"sharpe_net_{k}": float(v[i]) for k, v in pl.net.items()},
                }
            )
    place = pd.DataFrame(pl_rows)
    desc = f"NA-13: {split} strategy books"
    io.write_parquet(
        daily,
        OUT_DAILY.format(split=split),
        producer=CHUNK,
        description=f"{desc}: daily gross return, turnover, active flag and net returns at 5/10/20 bp "
        "per rule and tier (all = the book; top100/mid/rest = its tier sub-books)",
        layout=lay,
    )
    io.write_parquet(
        positions,
        OUT_POSITIONS.format(split=split),
        producer=CHUNK,
        description=f"{desc}: every position with its side, weight, score, beta, ADV, decision, "
        "entry and exit instants and its inputs' instants",
        layout=lay,
    )
    io.write_parquet(
        place,
        OUT_PLACEBO.format(split=split),
        producer=CHUNK,
        description=f"{desc}: the random-signal placebo, net and gross annualized Sharpe per "
        "universe and seed",
        layout=lay,
    )
    out = {
        "split": split,
        "seconds": round(time.time() - t0, 1),
        "n_rules": len(books),
        "n_universes": len(universes),
        "placebo_seeds": seeds,
        "books": books,
    }
    write_json(lay, f"books_{split}.json", out)
    return out


def clean(x: Any) -> Any:
    """JSON-safe: NaN / ±inf → None, numpy scalars → Python, other objects → str."""
    if isinstance(x, Mapping):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [clean(v) for v in x]
    if isinstance(x, bool | np.bool_):
        return bool(x)
    if isinstance(x, int | np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        return float(x) if np.isfinite(x) else None
    if x is None or isinstance(x, str):
        return x
    return str(x)


def write_json(layout: Layout, name: str, obj: Any) -> None:
    path = layout.root / RESULTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), indent=1) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "val_b"
    if cmd in SPLITS:
        out = run_split(cmd)
        print(json.dumps({k: v for k, v in out.items() if k != "books"}, indent=1))
        return 0
    print(f"unknown command {cmd!r}; expected one of {SPLITS}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
