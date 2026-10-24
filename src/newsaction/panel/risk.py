"""Betas, abnormal returns, sigma, z-scores, abnormal volume, momentum (PREREG §5.3-5.4; NA-01 S4).

Every statistic dated t uses data through t-1 only (CLAUDE.md A3). Each is first computed over the
window that ends at row s and then moved down one session with an explicit ``.shift(1)``; the
planted-shock test (tests/test_panel_pit.py) fails if any of those shifts is removed.

- beta_m, beta_s: OLS with intercept of r_cc on [r_SPY, r_sec - r_SPY] over the 252 sessions ending
  t-1, at least 126 complete observations.
- AR_x = r_x - beta_m * r_SPY,x - beta_s * (r_sec,x - r_SPY,x), x in {cc, on, id}.
- sigma_x = 1.4826 * MAD(AR_x) over the 126 sessions ending t-1 (at least 60), floored at that
  day's cross-sectional 10th percentile among index members; on half days sigma_id is scaled by
  sqrt(minutes / 390).
- z_x = AR_x / sigma_x clipped to [-10, 10].
- z_vol = (log V_t - median) / (1.4826 * MAD) of log V over the 60 sessions ending t-1 (at least 40).
- momentum: sum of AR_cc over the 5 / 20 / 60 sessions ending t-1 (complete windows only), and the
  same divided by sigma_cc * sqrt(k).
"""

from __future__ import annotations

import warnings
from typing import Final

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from newsaction.panel.grid import FloatArray

BETA_WINDOW: Final = 252
BETA_MIN: Final = 126
SIGMA_WINDOW: Final = 126
SIGMA_MIN: Final = 60
MAD_SCALE: Final = 1.4826
FLOOR_QUANTILE: Final = 0.10
Z_CLIP: Final = 10.0
VOL_WINDOW: Final = 60
VOL_MIN: Final = 40
ADV_WINDOW: Final = 63
ADV_MIN: Final = 40
MOMENTUM: Final = (5, 20, 60)
FULL_DAY_MINUTES: Final = 390
RETURN_TYPES: Final = ("cc", "on", "id")


def rolling_betas(
    r: pd.DataFrame, r_m: pd.Series, r_s: pd.DataFrame, window: int = BETA_WINDOW, min_obs: int = BETA_MIN
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(beta_m, beta_s, n_obs) of r on [r_m, r_s - r_m]; row t uses rows t-window .. t-1."""
    x1 = pd.DataFrame(np.broadcast_to(r_m.reindex(r.index).to_numpy()[:, None], r.shape), r.index, r.columns)
    x2 = r_s.reindex(index=r.index, columns=r.columns) - x1
    valid = r.notna() & x1.notna() & x2.notna()
    y, a, b = r.where(valid, 0.0), x1.where(valid, 0.0), x2.where(valid, 0.0)
    raw = {
        "n": valid.astype("float64"),
        "a": a,
        "b": b,
        "y": y,
        "aa": a * a,
        "bb": b * b,
        "ab": a * b,
        "ay": a * y,
        "by": b * y,
    }
    m = {k: v.rolling(window, min_periods=1).sum().shift(1) for k, v in raw.items()}  # through t-1
    n = m["n"]
    with np.errstate(invalid="ignore", divide="ignore"):
        caa = m["aa"] - m["a"] * m["a"] / n
        cbb = m["bb"] - m["b"] * m["b"] / n
        cab = m["ab"] - m["a"] * m["b"] / n
        cay = m["ay"] - m["a"] * m["y"] / n
        cby = m["by"] - m["b"] * m["y"] / n
        det = caa * cbb - cab * cab
        ok = (n >= min_obs) & (det > 1e-12 * caa * cbb)
        beta_m = ((cbb * cay - cab * cby) / det).where(ok)
        beta_s = ((caa * cby - cab * cay) / det).where(ok)
    return beta_m, beta_s, n.fillna(0.0)


def abnormal(
    r: pd.DataFrame, r_m: pd.Series, r_s: pd.DataFrame, beta_m: pd.DataFrame, beta_s: pd.DataFrame
) -> pd.DataFrame:
    rm = pd.DataFrame(np.broadcast_to(r_m.reindex(r.index).to_numpy()[:, None], r.shape), r.index, r.columns)
    return r - beta_m * rm - beta_s * (r_s - rm)


def _median_mad_windows(col: FloatArray, window: int, min_obs: int) -> tuple[FloatArray, FloatArray]:
    """Median and MAD of the windows ending at each row (rows with < min_obs values -> NaN)."""
    padded = np.concatenate([np.full(window - 1, np.nan), col])
    w = sliding_window_view(padded, window)
    finite = np.isfinite(w)
    cnt = finite.sum(axis=1)
    med = np.full(len(col), np.nan)
    mad = np.full(len(col), np.nan)
    full = cnt == window
    if full.any():
        wf = w[full]
        mf = np.median(wf, axis=1)
        med[full], mad[full] = mf, np.median(np.abs(wf - mf[:, None]), axis=1)
    part = (cnt >= min_obs) & ~full
    if part.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            wp = w[part]
            mp = np.nanmedian(wp, axis=1)
            med[part], mad[part] = mp, np.nanmedian(np.abs(wp - mp[:, None]), axis=1)
    return med, mad


def rolling_median_mad(frame: pd.DataFrame, window: int, min_obs: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-column median and MAD of the windows ending at row s (NOT lagged; callers shift)."""
    vals = frame.to_numpy(dtype="float64")
    med = np.full(vals.shape, np.nan)
    mad = np.full(vals.shape, np.nan)
    for j in range(vals.shape[1]):
        med[:, j], mad[:, j] = _median_mad_windows(vals[:, j], window, min_obs)
    return (
        pd.DataFrame(med, index=frame.index, columns=frame.columns),
        pd.DataFrame(mad, index=frame.index, columns=frame.columns),
    )


def robust_sigma(ar: pd.DataFrame, window: int = SIGMA_WINDOW, min_obs: int = SIGMA_MIN) -> pd.DataFrame:
    """1.4826 * MAD of AR over the ``window`` sessions ending t-1 (before the floor)."""
    _, mad = rolling_median_mad(ar, window, min_obs)
    return (MAD_SCALE * mad).shift(1)  # through t-1


def floor_sigma(sigma: pd.DataFrame, members: pd.DataFrame, q: float = FLOOR_QUANTILE) -> pd.DataFrame:
    """Floor each day's sigma at the q-quantile of that day's member cross-section."""
    m = members.reindex(index=sigma.index, columns=sigma.columns).fillna(False).astype(bool)
    floor = sigma.where(m).quantile(q, axis=1)
    return sigma.clip(lower=floor, axis=0)


def half_day_scale(sigma_id: pd.DataFrame, minutes: pd.Series) -> pd.DataFrame:
    scale = np.sqrt(minutes.reindex(sigma_id.index).astype("float64") / FULL_DAY_MINUTES)
    return sigma_id.mul(scale, axis=0)


def zscore(ar: pd.DataFrame, sigma: pd.DataFrame) -> pd.DataFrame:
    return (ar / sigma).clip(-Z_CLIP, Z_CLIP)


def _log(frame: pd.DataFrame) -> pd.DataFrame:
    """Natural log of the positive entries (others NaN)."""
    vals = frame.where(frame > 0).to_numpy(dtype="float64")
    return pd.DataFrame(np.log(vals), index=frame.index, columns=frame.columns)


def volume_baseline(
    volume: pd.DataFrame, window: int = VOL_WINDOW, min_obs: int = VOL_MIN
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(median, 1.4826 * MAD) of log volume over the ``window`` sessions ending t-1."""
    med, mad = rolling_median_mad(_log(volume), window, min_obs)
    return med.shift(1), (MAD_SCALE * mad).shift(1)  # through t-1


def z_volume(volume: pd.DataFrame, med: pd.DataFrame, mad: pd.DataFrame) -> pd.DataFrame:
    return (_log(volume) - med) / mad.where(mad > 0)


def momentum(ar_cc: pd.DataFrame, sigma_cc: pd.DataFrame, k: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sum of AR_cc over the k sessions ending t-1, that sum / (sigma_cc,t * sqrt(k)))."""
    car = ar_cc.rolling(k, min_periods=k).sum().shift(1)  # through t-1
    return car, car / (sigma_cc * np.sqrt(k))


def average_dollar_volume(dv: pd.DataFrame, window: int = ADV_WINDOW, min_obs: int = ADV_MIN) -> pd.DataFrame:
    return dv.rolling(window, min_periods=min_obs).mean().shift(1)  # through t-1


def compute_risk(
    r: dict[str, pd.DataFrame],
    r_m: dict[str, pd.Series],
    r_s: dict[str, pd.DataFrame],
    members: pd.DataFrame,
    minutes: pd.Series,
    volume: pd.DataFrame,
    dollar_volume: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """All S4 outputs on the grid; keys are panel column names."""
    out: dict[str, pd.DataFrame] = {}
    beta_m, beta_s, n = rolling_betas(r["cc"], r_m["cc"], r_s["cc"])
    out.update(beta_m=beta_m, beta_s=beta_s, beta_n=n)
    for x in RETURN_TYPES:
        if x not in r:
            continue
        ar = abnormal(r[x], r_m[x], r_s[x], beta_m, beta_s)
        sigma = floor_sigma(robust_sigma(ar), members)
        if x == "id":
            sigma = half_day_scale(sigma, minutes)
        out[f"ar_{x}"], out[f"sigma_{x}"], out[f"z_{x}"] = ar, sigma, zscore(ar, sigma)
    med, mad = volume_baseline(volume)
    out.update(logv_med60=med, logv_mad60=mad, z_vol=z_volume(volume, med, mad))
    for k in MOMENTUM:
        out[f"car_m{k}"], out[f"z_m{k}"] = momentum(out["ar_cc"], out["sigma_cc"], k)
    out["adv63"] = average_dollar_volume(dollar_volume)
    return out
