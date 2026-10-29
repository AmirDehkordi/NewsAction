"""NA-13b (e): the conditioning study's statistics, the validation selection and the one test evaluation.

**Outcomes** (each model's own direction, sign(N̂_D0)): the primary is the tradable move after the open,
sign(N̂)·z_id; the secondary is open → C_{t+1}, sign(N̂)·z_o0_c1; sign(N̂)·z_on is descriptive only (it is not
tradable at the open). Events of the split outside the embargo with N̂ and the outcome.

**Statistics** (``conditions`` gives each condition's level):

- event level: per session, the mean outcome of the inside and of the outside events; the inside mean is the
  mean of the inside daily means with a day-clustered t; the difference is the mean over sessions holding
  both groups of (inside − outside), with a day-clustered t (mean / (SD/√days));
- day level: per session, the mean outcome of all its events; the difference of the inside and outside
  sessions' means, with Welch's t;
- paired (E7's rank average): the mean over sessions of [mean sign(ensemble)·z − mean sign(N̂)·z] on the same
  events, day-clustered t.

p-values are two-sided (Student t with days − 1 degrees of freedom; Welch–Satterthwaite for day level).

**Selection rule** (the operator's, fixed before this chunk ran; validation only; primary outcome): a pair is
SELECTED if its difference is positive with t >= 1.0 in val-A and in val-B and the pooled-validation t >= 2.0
(event level and paired: the val-A and val-B daily differences together; day level: Welch's t on the pooled
sessions). E7's three-model agreement, which has no val-A run, needs val-B alone with t >= 2.5. Conditions
marked [seen on test] are reported and never selected.

**Test** (once): every pair on the primary outcome, Benjamini–Hochberg at q = 0.10 across the whole family
(and, reported beside it, across the family without the [seen on test] conditions, whose small test p-values
would otherwise help the rest).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd
from scipy import stats  # type: ignore[import-untyped, unused-ignore]

from newsaction.analysis import metrics as mx
from newsaction.selective import conditions as cd
from newsaction.selective import data as sd

PRIMARY: Final = "z_id"
OUTCOMES: Final = {"z_id": "primary", "z_o0_c1": "secondary", "z_on": "descriptive"}
VAL: Final = ("val_a", "val_b")
T_EACH: Final = 1.0
T_POOLED: Final = 2.0
T_VAL_B_ONLY: Final = 2.5
BH_Q: Final = 0.10


def clustered(x: pd.Series) -> dict[str, float]:
    """Mean, day-clustered t (mean / (SD/√n)), two-sided p and n of a daily series."""
    v = x.dropna().to_numpy(dtype=float)
    n = len(v)
    mean = float(v.mean()) if n else math.nan
    if n < 2:
        return {"mean": mean, "t": math.nan, "p": math.nan, "n": n}
    sd_ = float(v.std(ddof=1))
    t = mean / (sd_ / math.sqrt(n)) if sd_ > 0 else math.nan
    p = float(2 * stats.t.sf(abs(t), n - 1)) if math.isfinite(t) else math.nan
    return {"mean": mean, "t": t, "p": p, "n": n}


def welch(a: pd.Series, b: pd.Series) -> dict[str, float]:
    """Difference of two groups of daily means with Welch's t, two-sided p and the Welch df."""
    x, y = a.dropna().to_numpy(dtype=float), b.dropna().to_numpy(dtype=float)
    if len(x) < 2 or len(y) < 2:
        diff = float(x.mean() - y.mean()) if len(x) and len(y) else math.nan
        return {"mean": diff, "t": math.nan, "p": math.nan, "df": math.nan}
    r = stats.ttest_ind(x, y, equal_var=False)
    return {
        "mean": float(x.mean() - y.mean()),
        "t": float(r.statistic),
        "p": float(r.pvalue),
        "df": float(r.df),
    }


def frame_for(study: pd.DataFrame, model: str, outcome: str) -> pd.DataFrame:
    """Rows with the model's N̂ and the outcome: ``z`` the outcome and y = sign(N̂)·z."""
    f = study.dropna(subset=[f"n_{model}", outcome]).copy()
    f["z"] = f[outcome].to_numpy(dtype=float)
    f["y"] = np.sign(f[f"n_{model}"].to_numpy(dtype=float)) * f["z"].to_numpy()
    return f


def _daily(f: pd.DataFrame, col: str = "y") -> pd.Series:
    return f.groupby("session")[col].mean()


def split_stats(
    f: pd.DataFrame, cond: cd.Condition, inside: pd.Series, c: Mapping[str, Any]
) -> tuple[dict[str, Any], pd.Series | tuple[pd.Series, pd.Series]]:
    """One split's statistics and the pieces pooling needs (daily differences, or the two day groups)."""
    if cond.level == "paired":
        ens = cd.ensemble(f, c)
        g = f.assign(y_in=np.sign(ens.to_numpy()) * f["z"].to_numpy())
        g = g.loc[ens.notna() & (ens != 0)]
        a, b = _daily(g, "y_in"), _daily(g, "y")
        diff = (a - b).dropna()
        ins, out, dd = clustered(a), clustered(b), clustered(diff)
        rec = {"n_in": len(g), "n_out": len(g), "days_in": ins["n"], "days_out": out["n"]}
        return rec | _fields(ins, out, dd), diff
    flag = inside.reindex(f.index)
    if cond.level == "day":
        days = _daily(f)
        day_flag = flag.groupby(f["session"]).first().reindex(days.index).astype(bool)
        a, b = days[day_flag], days[~day_flag]
        ins, out = clustered(a), clustered(b)
        dd = welch(a, b)
        rec = {"n_in": int(f.loc[flag == 1].shape[0]), "n_out": int(f.loc[flag == 0].shape[0]),
               "days_in": ins["n"], "days_out": out["n"], "df": dd["df"]}  # fmt: skip
        return rec | _fields(ins, out, dd), (a, b)
    fin, fout = f.loc[flag == 1], f.loc[flag == 0]
    a, b = _daily(fin), _daily(fout)
    diff = (a - b).dropna()
    ins, out, dd = clustered(a), clustered(b), clustered(diff)
    rec = {"n_in": len(fin), "n_out": len(fout), "days_in": ins["n"], "days_out": out["n"]}
    return rec | _fields(ins, out, dd), diff


def _fields(ins: Mapping[str, float], out: Mapping[str, float], dd: Mapping[str, float]) -> dict[str, Any]:
    return {
        "inside": ins["mean"],
        "inside_t": ins["t"],
        "outside": out["mean"],
        "outside_t": out["t"],
        "diff": dd["mean"],
        "diff_t": dd["t"],
        "diff_p": dd["p"],
        "diff_days": dd.get("n", math.nan),
    }


def pooled(cond: cd.Condition, parts: Sequence[Any]) -> dict[str, float]:
    """The pooled-validation statistic from the val-A and val-B pieces."""
    if not parts:
        return {"mean": math.nan, "t": math.nan, "p": math.nan}
    if cond.level == "day":
        a = pd.concat([p[0] for p in parts], ignore_index=True)
        b = pd.concat([p[1] for p in parts], ignore_index=True)
        return welch(a, b)
    return clustered(pd.concat(list(parts), ignore_index=True))


def evaluate(
    study: pd.DataFrame,
    c: Mapping[str, Any],
    splits: Sequence[str],
    outcomes: Sequence[str] = tuple(OUTCOMES),
    conditions: Sequence[cd.Condition] = cd.CONDITIONS,
) -> pd.DataFrame:
    """Every (model, condition, outcome, split) row on ``splits``, plus a pooled-validation row when both
    validation splits are evaluated."""
    rows: list[dict[str, Any]] = []
    for model, cond in cd.pairs(conditions):
        inside = cd.event_inside(study, model, cond, c)
        for outcome in outcomes:
            f_all = frame_for(study, model, outcome)
            pieces: list[Any] = []
            for split in splits:
                if split not in cond.splits:
                    continue
                rec, piece = split_stats(sd.eval_rows(f_all, split), cond, inside, c)
                if split in VAL:
                    pieces.append(piece)
                rows.append(_row(model, cond, outcome, split) | rec)
            if set(VAL) <= set(splits) and set(VAL) <= set(cond.splits):
                p = pooled(cond, pieces)
                rows.append(
                    _row(model, cond, outcome, "val_pooled")
                    | {"diff": p["mean"], "diff_t": p["t"], "diff_p": p["p"]}
                )
    return pd.DataFrame(rows)


def _row(model: str, cond: cd.Condition, outcome: str, split: str) -> dict[str, Any]:
    return {
        "model": model,
        "condition": cond.key,
        "group": cond.group,
        "label": cond.label,
        "level": cond.level,
        "seen_on_test": cond.seen_on_test,
        "vendor": cond.vendor,
        "outcome": outcome,
        "role": OUTCOMES[outcome],
        "split": split,
    }


def select(val: pd.DataFrame, conditions: Sequence[cd.Condition] = cd.CONDITIONS) -> pd.DataFrame:
    """The operator's selection rule on the primary outcome, one row per (model, condition)."""
    v = val.loc[val["outcome"] == PRIMARY]
    keys = zip(v["model"], v["condition"], v["split"], strict=True)
    values = zip(v["diff"].to_numpy(dtype=float), v["diff_t"].to_numpy(dtype=float), strict=True)
    stat = dict(zip(keys, values, strict=True))
    rows = []
    for model, cond in cd.pairs(conditions):
        a, ta = stat.get((model, cond.key, "val_a"), (math.nan, math.nan))
        b, tb = stat.get((model, cond.key, "val_b"), (math.nan, math.nan))
        tp = stat.get((model, cond.key, "val_pooled"), (math.nan, math.nan))[1]
        if cond.seen_on_test:
            ok, rule = False, "seen on test: not eligible"
        elif cond.val_b_only:
            ok, rule = bool(b > 0 and tb >= T_VAL_B_ONLY), f"val-B alone, t >= {T_VAL_B_ONLY}"
        else:
            ok = bool(a > 0 and ta >= T_EACH and b > 0 and tb >= T_EACH and tp >= T_POOLED)
            rule = f"t >= {T_EACH} in val-A and val-B, pooled t >= {T_POOLED}"
        rows.append(
            {"model": model, "condition": cond.key, "group": cond.group, "label": cond.label,
             "level": cond.level, "seen_on_test": cond.seen_on_test, "val_b_only": cond.val_b_only,
             "diff_val_a": a, "t_val_a": ta, "diff_val_b": b, "t_val_b": tb, "t_pooled": tp,
             "selected": ok, "rule": rule}
        )  # fmt: skip
    return pd.DataFrame(rows)


def family_on_test(test: pd.DataFrame, selection: pd.DataFrame) -> pd.DataFrame:
    """The test rows of the primary outcome with the Benjamini–Hochberg q over the whole family and the
    validation selection flag."""
    t = test.loc[(test["outcome"] == PRIMARY) & (test["split"] == "test")].copy()
    keys = [f"{m}|{k}" for m, k in zip(t["model"], t["condition"], strict=True)]
    p = dict(zip(keys, t["diff_p"].astype(float), strict=True))
    q = mx.bh(p)
    t["bh_q"] = [q[k] for k in keys]
    seen = dict(zip(keys, t["seen_on_test"].astype(bool), strict=True))
    q_unseen = mx.bh({k: v for k, v in p.items() if not seen[k]})  # the family without the seen conditions
    t["bh_q_unseen"] = [q_unseen.get(k, math.nan) for k in keys]
    sel = selection.set_index(["model", "condition"])["selected"]
    t["selected"] = [bool(sel.get((m, k), False)) for m, k in zip(t["model"], t["condition"], strict=True)]
    t["same_sign"] = t["diff"] > 0
    t["confirmed"] = t["selected"] & t["same_sign"] & (t["bh_q"] < BH_Q)
    t["confirmed_unseen"] = t["selected"] & t["same_sign"] & (t["bh_q_unseen"] < BH_Q)
    return t.reset_index(drop=True)
