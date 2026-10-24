"""Adjusted prices and returns (PREREG §5.1; PRD NA-01 S2).

- f_t = AdjClose_t / RawClose_t; adjusted open AO_t = RawOpen_t * f_t.
- r_cc = AC_t / AC_{t-1} - 1; r_id = RawClose_t / RawOpen_t - 1; r_on = (1 + r_cc) / (1 + r_id) - 1.
  AdjClose comes from Data/prices (split, dividend and spin-off adjusted). For ATOM ids without a
  validated Data/prices symbol the fallback is ATOM's total-return close (``adj_source`` =
  ``atom_total``; PREREG §15).
- QC: r_cc is compared with ATOM's total-return close-to-close; |diff| > 50 bp and |r_on| > 25%
  are flagged with a reason. Flagged values are never changed.

ATOM stores spin-offs as ``split`` rows with the price ratio (GE 2024-04-02: 1.253). They scale
prices but not share counts, so ``is_true_split`` separates them (PREREG §15).
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from newsaction.panel.grid import empty_like, lag

QC_TR_DIFF: Final = 0.005  # 50 bp (PREREG §5.1)
QC_R_ON: Final = 0.25  # PRD NA-01 AC3
F_JUMP: Final = 0.005  # |delta log f| that counts as an adjustment-factor jump
_MAX_DENOMINATOR: Final = 4


def is_true_split(ratio: float) -> bool:
    """A share split (r or 1/r = p/q with q <= 4, e.g. 2, 3:2, 1:5), not a spin-off price ratio."""
    if not np.isfinite(ratio) or ratio <= 0:
        return False
    for r in (ratio, 1.0 / ratio):
        for q in range(1, _MAX_DENOMINATOR + 1):
            p = r * q
            if round(p) >= 1 and abs(p - round(p)) < 1e-6 * max(1.0, p):
                return True
    return False


def classify_actions(actions: pd.DataFrame) -> pd.DataFrame:
    """Add ``kind``: split / spinoff (split rows) or the action_type; and ``ex_session`` (Timestamp)."""
    out = actions.copy()
    kind = out["action_type"].astype(str).copy()
    is_split = out["action_type"] == "split"
    kind[is_split] = np.where(out.loc[is_split, "split_ratio"].map(is_true_split), "split", "spinoff")
    out["kind"] = kind
    out["ex_session"] = pd.to_datetime(out["ex_date"])
    return out


def returns(ac: pd.DataFrame, ro: pd.DataFrame, rc: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """r_cc, r_id, r_on, f and AO on the grid (r_id / r_on need raw prices, so public sessions only)."""
    f = ac / rc
    r_cc = ac / lag(ac) - 1.0
    r_id = rc / ro - 1.0
    r_on = (1.0 + r_cc) / (1.0 + r_id) - 1.0
    return {"r_cc": r_cc, "r_id": r_id, "r_on": r_on, "f": f, "adj_open": ro * f}


def true_split_factor_after(
    sessions: pd.Index, symbols: list[int], actions: pd.DataFrame, until: pd.Timestamp
) -> pd.DataFrame:
    """S_t = product of true split ratios with t < ex_date <= ``until`` (a fixed share basis)."""
    out = pd.DataFrame(1.0, index=sessions, columns=symbols)
    spl = actions[(actions["kind"] == "split") & (actions["ex_session"] <= until)]
    for rec in spl.to_dict("records"):
        if rec["symbol_id"] in out.columns:
            out.loc[out.index < rec["ex_session"], rec["symbol_id"]] *= float(rec["split_ratio"])
    return out


def split_adjusted_volume(rv: pd.DataFrame, split_after: pd.DataFrame) -> pd.DataFrame:
    """ATOM raw volume on one true-split share basis (spin-offs do not change share volume)."""
    return rv * split_after


def reconstruct_raw_close(
    ac: pd.DataFrame, f_anchor: pd.Series, anchor: pd.Timestamp, actions: pd.DataFrame
) -> pd.DataFrame:
    """Raw close for sessions after ``anchor`` from the adjusted close (rows <= anchor are NaN).

    RC_t = AC_t / f_t with f_t = f_anchor * prod over ATOM events e in (anchor, t] of a_e, where
    a_e = split_ratio for every split row (spin-off ratios included: Data/prices applies them to the
    price factor) and a_e = 1 / (1 - D_e / RC_{e-1}) for a cash dividend (Yahoo's convention).
    Used only where the raw close is blinded (tier ranking sessions of the test months).
    """
    out = empty_like(ac)
    after = np.asarray(ac.index > anchor)
    kinds = ["split", "spinoff", "cash_dividend"]
    ev = actions[(actions["ex_session"] > anchor) & actions["kind"].isin(kinds)]
    sessions = ac.index[after].to_numpy()
    todo: dict[int, dict[int, list[tuple[str, float]]]] = {}
    for rec in ev.to_dict("records"):
        kind = str(rec["kind"])
        amount = float(rec["split_ratio"]) if kind in ("split", "spinoff") else float(rec["cash_amount"])
        pos = int(np.searchsorted(sessions, np.datetime64(rec["ex_session"])))
        todo.setdefault(int(rec["symbol_id"]), {}).setdefault(pos, []).append((kind, amount))
    anchor_row: dict[Any, float] = (
        {c: float(v) for c, v in zip(ac.columns, ac.loc[anchor].to_numpy(dtype="float64"), strict=True)}
        if anchor in ac.index
        else {}
    )
    for sid in ac.columns:
        f = float(f_anchor.get(sid, np.nan))
        if not np.isfinite(f):
            continue
        prev_rc = anchor_row.get(sid, np.nan) / f
        events = todo.get(int(sid), {})
        col = ac.loc[after, sid].to_numpy(dtype="float64")
        res = np.full(len(col), np.nan)
        for i, a in enumerate(col):
            for kind, amount in events.get(i, []):
                if kind in ("split", "spinoff"):
                    f *= amount
                elif np.isfinite(prev_rc) and prev_rc > amount > 0:
                    f /= 1.0 - amount / prev_rc
            if np.isfinite(a):
                res[i] = a / f
                prev_rc = res[i]
        out.loc[after, sid] = res
    return out


LEVEL_MIN_EX_DATES: Final = 4
LEVEL_MIN_JUMP: Final = 5e-4  # dividend factor jumps below this are too noisy (e.g. NVDA's $0.01)
LEVEL_MAX_IQR: Final = 0.05
LEVEL_TOLERANCE: Final = 1.25


def raw_level_check(
    f: pd.DataFrame, rc: pd.DataFrame, actions: pd.DataFrame, public: pd.Index
) -> pd.DataFrame:
    """Per symbol: is ATOM's raw close on the as-traded price level?

    Data/prices applies a cash dividend D with ex-date e as f_{e-1} = f_e * (1 - D / C_{e-1}), where
    C is the as-traded close. So C*_{e-1} = D / (1 - f_{e-1} / f_e) recovers the as-traded level from
    the factor alone, and rho = C* / RC_{e-1} compares it with ATOM's raw close (rho = 1 when ATOM is
    as traded). ``level_factor`` is the median rho for symbols with at least ``LEVEL_MIN_EX_DATES``
    usable ex-dates, an IQR <= ``LEVEL_MAX_IQR`` and a median off by more than ``LEVEL_TOLERANCE``x
    (HON: ATOM's 2023-2025 raw prices are half the traded prices); 1 otherwise.
    """
    div = actions[(actions["kind"] == "cash_dividend") & actions["ex_session"].isin(public)]
    amounts = div.groupby(["symbol_id", "ex_session"], as_index=False).agg(cash_amount=("cash_amount", "sum"))
    f_pub, rc_pub = f.loc[public], rc.loc[public]
    prev_f, prev_rc = f_pub.shift(1), rc_pub.shift(1)
    rows = []
    for key, g in amounts.groupby("symbol_id"):
        sid = int(cast(int, key))
        if sid not in f_pub.columns:
            continue
        ex = pd.DatetimeIndex(g["ex_session"])
        fa = f_pub[sid].reindex(ex).to_numpy(dtype="float64")
        fb = prev_f[sid].reindex(ex).to_numpy(dtype="float64")
        cb = prev_rc[sid].reindex(ex).to_numpy(dtype="float64")
        jump = 1.0 - fb / fa
        rho = (g["cash_amount"].to_numpy(dtype="float64") / jump) / cb
        ok = np.isfinite(rho) & (jump > LEVEL_MIN_JUMP) & (jump < 0.2)
        r = rho[ok]
        med = float(np.median(r)) if len(r) else float("nan")
        iqr = float(np.subtract(*np.quantile(r, [0.75, 0.25]))) if len(r) else float("nan")
        flagged = (
            len(r) >= LEVEL_MIN_EX_DATES
            and iqr <= LEVEL_MAX_IQR
            and abs(np.log(med)) > np.log(LEVEL_TOLERANCE)
        )
        rows.append((sid, len(r), med, iqr, med if flagged else 1.0))
    out = pd.DataFrame(rows, columns=["symbol_id", "level_n", "level_rho", "level_iqr", "level_factor"])
    out = out.set_index("symbol_id").reindex(pd.Index(f.columns, name="symbol_id"))
    return out.fillna({"level_factor": 1.0, "level_n": 0})


def unit_ratio(num: pd.DataFrame, den: pd.DataFrame, window: pd.Index) -> pd.Series:
    """Per-symbol median of num/den over ``window`` (a unit conversion between two vendors' series)."""
    ratio = (num / den).loc[window].replace([np.inf, -np.inf], np.nan)
    return ratio.median(skipna=True)


def qc_flags(
    r: dict[str, pd.DataFrame],
    tc: pd.DataFrame,
    actions: pd.DataFrame,
    mapped: pd.Series,
    public: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Flag public symbol-days with |r_cc - r_cc(ATOM total)| > 50 bp or |r_on| > 25%, with a reason.

    Reasons (first match): split / spinoff / cash_dividend / merger (an ATOM action that day);
    raw_print_suspect (the factor f jumps and reverts the next session: one bad raw close);
    adj_factor_jump_no_atom_action (f jumps with no ATOM action: a spin-off or special dividend
    ATOM lacks); genuine_large_move (|r_on| > 25% with smooth f and ATOM agreeing); other.
    """
    r_cc, r_on, f = (r[k].loc[public] for k in ("r_cc", "r_on", "f"))
    r_tot = (tc / lag(tc) - 1.0).loc[public]
    diff = r_cc - r_tot
    dlogf = pd.DataFrame(np.log((f / lag(f)).to_numpy(dtype="float64")), index=f.index, columns=f.columns)
    rule_tr = (diff.abs() > QC_TR_DIFF) & pd.DataFrame(
        np.broadcast_to(mapped.reindex(r_cc.columns).fillna(False).to_numpy(dtype=bool), r_cc.shape),
        index=r_cc.index,
        columns=r_cc.columns,
    )
    rule_on = r_on.abs() > QC_R_ON
    flagged = rule_tr | rule_on
    if not bool(flagged.to_numpy().any()):
        return pd.DataFrame(columns=_QC_COLUMNS)
    idx = np.argwhere(flagged.to_numpy())
    sess, sym = r_cc.index[idx[:, 0]], r_cc.columns[idx[:, 1]]
    acts = actions.groupby(["symbol_id", "ex_session"])["kind"].agg(lambda s: ",".join(sorted(set(s))))
    out = pd.DataFrame(
        {
            "session": sess,
            "symbol_id": sym.astype("int64"),
            "rule": [
                "+".join(
                    n
                    for n, hit in (
                        ("tr_diff_gt_50bp", rule_tr.iat[i, j]),
                        ("abs_r_on_gt_25pct", rule_on.iat[i, j]),
                    )
                    if hit
                )
                for i, j in idx
            ],
            "r_cc": r_cc.to_numpy()[idx[:, 0], idx[:, 1]],
            "r_cc_atom_total": r_tot.to_numpy()[idx[:, 0], idx[:, 1]],
            "diff_bp": 1e4 * diff.to_numpy()[idx[:, 0], idx[:, 1]],
            "r_on": r_on.to_numpy()[idx[:, 0], idx[:, 1]],
            "r_id": r["r_id"].loc[public].to_numpy()[idx[:, 0], idx[:, 1]],
            "dlog_f": dlogf.to_numpy()[idx[:, 0], idx[:, 1]],
            "dlog_f_next": dlogf.shift(-1).to_numpy()[idx[:, 0], idx[:, 1]],
        }
    )
    keys = list(zip(out["symbol_id"], out["session"], strict=True))
    out["atom_actions"] = [acts.get(k, "") for k in keys]
    out["reason"] = [_reason(rec) for rec in out.to_dict("records")]
    return out[_QC_COLUMNS].sort_values(["session", "symbol_id"]).reset_index(drop=True)


_QC_COLUMNS: Final = [
    "session",
    "symbol_id",
    "rule",
    "reason",
    "atom_actions",
    "r_cc",
    "r_cc_atom_total",
    "diff_bp",
    "r_on",
    "r_id",
    "dlog_f",
    "dlog_f_next",
]


def _reason(rec: dict[Hashable, Any]) -> str:
    acts = str(rec.get("atom_actions", ""))
    for kind in ("split", "spinoff", "merger", "cash_dividend"):
        if kind in acts.split(","):
            return kind
    dlf, nxt = float(rec["dlog_f"]), float(rec["dlog_f_next"])
    if np.isfinite(dlf) and abs(dlf) > F_JUMP:
        if np.isfinite(nxt) and abs(dlf + nxt) < abs(dlf) / 4:
            return "raw_print_suspect"
        return "adj_factor_jump_no_atom_action"
    if "abs_r_on_gt_25pct" in str(rec["rule"]):
        return "genuine_large_move"
    return "other"
