"""NA-14: where every plotted number comes from, and the check that it still does (PRD NA-14 AC4).

Each figure CSV is long: one row per plotted value, in ``COLUMNS``. Besides what the figure draws (``panel``,
``series``, ``x`` / ``xv``, ``y`` and its interval ``lo`` / ``hi``), a row names its upstream file
(``source``), the row of that file (``key``, built from the file's ``KEYS``) and the columns it took
(``y_col``, ``x_col``, ``lo_col``, ``hi_col``, ``se_col``). ``trace`` re-reads every named cell and returns
the rows whose value differs, so "no new analysis" is a test, not a promise.

The interval of a row (``ci``) is one of:
- ``table``: the stored bounds (bootstrap CIs, the placebo's 5th and 95th percentile paths and Sharpe ratios);
- ``se``: y ± 1.96 × the stored standard error (``se_col``);
- ``se1``: y ± 1 × the stored standard error (``se_col``; the "±1 SE" bands of an exploratory figure);
- ``t``: y ± 1.96 × |y / t| with the stored t statistic in ``se_col`` (the Newey–West SE behind a t);
- ``wilson``: the Wilson score 95% interval of the stored proportion y with the stored number of trials in
  ``se_col`` (y × n must be a count);
- empty: no interval.

Upstream files are read as CSV only (no JSON, no parquet) from ``artifacts/``; the NA-14 tables that
flatten a results JSON are sources of their own (``artifacts/NA-14/tables``).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from newsaction.figures.style import Z95

CHUNK: Final = "NA-14"
ARTIFACTS: Final = "artifacts/NA-14"
FIGURES: Final = f"{ARTIFACTS}/figures"
TABLES: Final = f"{ARTIFACTS}/tables"

COLUMNS: Final = (
    "panel",
    "series",
    "label",
    "role",
    "x",
    "xv",
    "y",
    "lo",
    "hi",
    "ci",
    "source",
    "key",
    "y_col",
    "x_col",
    "lo_col",
    "hi_col",
    "se_col",
)
CI_KINDS: Final = ("", "table", "se", "se1", "t", "wilson")
ATOL: Final = 1e-12

NA12_FIG: Final = "artifacts/NA-12/figure_data"
NA12_TAB: Final = "artifacts/NA-12/tables"
V_DECILES: Final = f"{NA12_FIG}/fig1_v_decile_paths.csv"
RG_CLASSES: Final = f"{NA12_FIG}/fig1_rg_class_paths.csv"
DRIFT: Final = f"{NA12_FIG}/fig2_drift_vs_g.csv"
MONTHLY: Final = f"{NA12_FIG}/fig4_monthly_ic.csv"
SHAPLEY: Final = f"{NA12_FIG}/fig5_shapley_shares.csv"
LADDER: Final = f"{NA12_FIG}/fig8_explanation_ladder.csv"
RELIABILITY: Final = f"{NA12_FIG}/appendix_reliability.csv"
FIG7: Final = "artifacts/NA-13/fig7_data.csv"
STRATEGY: Final = "artifacts/NA-13/strategy_table.csv"
TOURNAMENT: Final = "artifacts/NA-06/fig3_data.csv"
FRONTIER: Final = "artifacts/NA-03/frontier.csv"
ENCODING: Final = "artifacts/NA-07/encoding_ic.csv"
COMPANY_ID: Final = "artifacts/NA-11/company_id_matched.csv"
PROBES: Final = "artifacts/NA-11/probes_val_a.csv"

KEYS: Final[dict[str, tuple[str, ...]]] = {
    V_DECILES: ("model", "figure", "group", "point"),
    RG_CLASSES: ("model", "figure", "group", "point"),
    DRIFT: ("model", "tercile", "g_bin"),
    MONTHLY: ("model", "split", "month"),
    SHAPLEY: ("model", "tier", "metric", "group"),
    LADDER: ("model", "step"),
    RELIABILITY: ("model", "target", "bin"),
    FIG7: ("rule", "tier", "session"),
    STRATEGY: ("split", "rule"),
    TOURNAMENT: ("model",),
    FRONTIER: ("filter", "target_share"),
    ENCODING: ("split", "model", "encoding"),
    COMPANY_ID: ("model",),
    PROBES: ("model",),
}


def wilson(p: float, n: float) -> tuple[float, float]:
    """The Wilson score 95% interval of a proportion p of n trials; p·n must be a whole number of
    successes."""
    if not n > 0 or abs(p * n - round(p * n)) > 1e-6:
        raise ValueError(f"{p!r} of {n!r} trials is not a count of successes")
    z2 = Z95 * Z95
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return centre - half, centre + half


def _interval(kind: str, y: float, stat: float) -> tuple[float, float]:
    """The interval of kind ``se``, ``se1``, ``t`` or ``wilson`` around y from one stored statistic."""
    if kind == "se":
        return y - Z95 * stat, y + Z95 * stat
    if kind == "se1":
        return y - stat, y + stat
    if kind == "t":
        s = abs(y / stat) if stat else math.nan
        return y - Z95 * s, y + Z95 * s
    if kind == "wilson":
        return wilson(y, stat)
    raise ValueError(f"no interval of kind {kind!r} from one statistic")


def key_columns(path: str) -> tuple[str, ...]:
    """The columns that key a source file's rows ("key" for every NA-12 and NA-14 table)."""
    if path in KEYS:
        return KEYS[path]
    if path.endswith(".csv") and (path.startswith(f"{NA12_TAB}/") or path.startswith(f"{TABLES}/")):
        return ("key",)
    raise KeyError(f"{path} is not a registered figure source")


def key_part(v: Any) -> str:
    """One key component as text: integers without a decimal point, other numbers to 10 digits."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, bool | np.bool_):
        return str(bool(v))
    if isinstance(v, int | np.integer):
        return str(int(v))
    if isinstance(v, float | np.floating):
        f = float(v)
        return str(int(f)) if f.is_integer() else format(f, ".10g")
    return str(v)


def row_key(values: Iterable[Any]) -> str:
    return "|".join(key_part(v) for v in values)


class Sources:
    """Read-only, memoised access to the upstream CSVs under a repository root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._frames: dict[str, pd.DataFrame] = {}
        self._index: dict[str, dict[str, int]] = {}

    def frame(self, path: str) -> pd.DataFrame:
        if path not in self._frames:
            self._frames[path] = pd.read_csv(self.root / path)
        return self._frames[path]

    def index(self, path: str) -> dict[str, int]:
        if path not in self._index:
            df = self.frame(path)
            cols = key_columns(path)
            keys = [row_key(vals) for vals in df[list(cols)].itertuples(index=False, name=None)]
            if len(set(keys)) != len(keys):
                raise ValueError(f"{path}: the key columns {cols} do not identify its rows")
            self._index[path] = {k: i for i, k in enumerate(keys)}
        return self._index[path]

    def row(self, path: str, key: str) -> pd.Series:
        idx = self.index(path)
        if key not in idx:
            raise KeyError(f"{path}: no row {key!r}")
        return self.frame(path).iloc[idx[key]]

    def keyed(self, path: str) -> pd.DataFrame:
        """The file with its row key as the first column ``key`` (an NA-12 table keeps its own)."""
        df = self.frame(path)
        if key_columns(path) == ("key",):
            return df.copy()
        out = df.copy()
        out.insert(0, "key", list(self.index(path)))
        return out


def rows(
    df: pd.DataFrame,
    source: str,
    *,
    panel: str,
    series: Any,
    y_col: str,
    x: Any = "",
    xv: Any = math.nan,
    x_col: str = "",
    label: Any = "",
    role: Any = "",
    ci: str = "",
    lo_col: str = "",
    hi_col: str = "",
    se_col: str = "",
) -> pd.DataFrame:
    """Long figure rows from ``df`` (rows of ``source``): ``y`` from ``y_col`` and the interval by ``ci``.

    ``series``, ``x``, ``xv``, ``label`` and ``role`` are constants or column names of ``df`` (a string that
    names a column is read from it; prefix a constant with "=" to force a literal)."""
    if ci not in CI_KINDS:
        raise ValueError(f"unknown interval kind {ci!r}")
    cols = key_columns(source)
    keys = [row_key(vals) for vals in df[list(cols)].itertuples(index=False, name=None)]

    def col(v: Any) -> Any:
        if isinstance(v, str) and v.startswith("="):
            return v[1:]
        if isinstance(v, str) and v in df.columns:
            return df[v].to_numpy()
        return v

    y = df[y_col].to_numpy(dtype=float)
    lo = np.full(len(df), np.nan)
    hi = np.full(len(df), np.nan)
    if ci == "table":
        lo, hi = df[lo_col].to_numpy(dtype=float), df[hi_col].to_numpy(dtype=float)
    elif ci:
        stats = df[se_col].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            pairs = [_interval(ci, float(a), float(b)) for a, b in zip(y, stats, strict=True)]
        lo = np.array([p[0] for p in pairs], dtype=float)
        hi = np.array([p[1] for p in pairs], dtype=float)
    out = pd.DataFrame(
        {
            "panel": panel,
            "series": col(series),
            "label": col(label),
            "role": col(role),
            "x": col(x),
            "xv": df[x_col].to_numpy(dtype=float) if x_col else col(xv),
            "y": y,
            "lo": lo,
            "hi": hi,
            "ci": ci,
            "source": source,
            "key": keys,
            "y_col": y_col,
            "x_col": x_col,
            "lo_col": lo_col,
            "hi_col": hi_col,
            "se_col": se_col,
        }
    )
    return out[list(COLUMNS)]


def _same(a: Any, b: Any) -> bool:
    fa, fb = float(a), float(b)
    if math.isnan(fa) or math.isnan(fb):
        return math.isnan(fa) and math.isnan(fb)
    return abs(fa - fb) <= ATOL or (math.isinf(fa) and fa == fb)


def trace(fig: pd.DataFrame, src: Sources) -> list[str]:
    """The rows of a figure CSV whose plotted values do not equal their source cells (empty if all do)."""
    bad: list[str] = []
    for i, r in enumerate(fig.to_dict("records")):
        where = f"row {i} ({r['source']} {r['key']!r})"
        try:
            rec = src.row(str(r["source"]), str(r["key"]))
        except KeyError as exc:
            bad.append(f"{where}: {exc}")
            continue
        y = float(r["y"])
        if not _same(y, rec[str(r["y_col"])]):
            bad.append(f"{where}: y {y!r} != {r['y_col']} {rec[str(r['y_col'])]!r}")
        if isinstance(r["x_col"], str) and r["x_col"] and not _same(r["xv"], rec[r["x_col"]]):
            bad.append(f"{where}: xv {r['xv']!r} != {r['x_col']} {rec[r['x_col']]!r}")
        kind = r["ci"] if isinstance(r["ci"], str) else ""
        lo, hi = float(r["lo"]), float(r["hi"])
        if kind == "table":
            want = (float(rec[str(r["lo_col"])]), float(rec[str(r["hi_col"])]))
        elif kind:
            try:
                want = _interval(kind, y, float(rec[str(r["se_col"])]))
            except ValueError as exc:
                bad.append(f"{where}: {exc}")
                continue
        else:
            want = (math.nan, math.nan)
        if not (_same(lo, want[0]) and _same(hi, want[1])):
            bad.append(f"{where}: interval ({lo!r}, {hi!r}) != {kind or 'none'} {want!r}")
    return bad
