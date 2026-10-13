"""Hazard definitions and event detection.

Heatwave (default): >= min_days consecutive days with Tmax above the P-th percentile threshold.
  method="calendar": threshold varies by day of year (percentile of Tmax within +/-7 days of that
                     calendar day across the baseline years). Standard in climate science; avoids
                     counting every summer day as "hot" just because it is warmer than winter.
  method="fixed":    a single percentile of all daily Tmax values (the literal reading of the brief).
Heavy rainfall: a single day with precipitation above the P-th percentile of wet days (>= 1 mm).

Baseline = the analysed period. The threshold is therefore relative to the region's own climate over
the selected years, so trends show change in the *frequency of days that were extreme in that period*.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

WINDOW_HALF_WIDTH = 7
WET_DAY_MM = 1.0


def _slot(index: pd.DatetimeIndex) -> np.ndarray:
    """Map dates to 0..364 so leap-year Feb 29 shares a slot with Feb 28."""
    doy = index.dayofyear.to_numpy().copy()
    leap = index.is_leap_year
    doy = np.where(leap & (doy > 59), doy - 1, doy)
    return np.clip(doy - 1, 0, 364)


def calendar_threshold(tmax: pd.Series, percentile: float) -> pd.Series:
    """Per-day-of-year percentile threshold with a +/-7 day window, returned aligned to tmax.index."""
    slots = _slot(tmax.index)
    years = tmax.index.year.to_numpy()
    uy = np.unique(years)
    mat = np.full((len(uy), 365), np.nan)
    yi = np.searchsorted(uy, years)
    mat[yi, slots] = tmax.to_numpy()
    offsets = np.arange(-WINDOW_HALF_WIDTH, WINDOW_HALF_WIDTH + 1)
    thr = np.full(365, np.nan)
    for s in range(365):
        vals = mat[:, (s + offsets) % 365].ravel()
        vals = vals[~np.isnan(vals)]
        if vals.size >= 30:
            thr[s] = np.percentile(vals, percentile)
    return pd.Series(thr[slots], index=tmax.index)


def fixed_threshold(values: pd.Series, percentile: float) -> float:
    v = values.dropna()
    return float(np.percentile(v, percentile)) if len(v) else float("nan")


def find_runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Return (start, end_exclusive) of runs of True with length >= min_len."""
    if mask.size == 0:
        return []
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_len]


@dataclass
class HazardResult:
    events: pd.DataFrame  # start, end, duration, mean_excess, peak, year
    threshold_summary: dict
    unit: str
    excess_unit: str


def detect_heatwaves(df: pd.DataFrame, percentile: float = 95, min_days: int = 3, method: str = "calendar") -> HazardResult:
    tmax = df["tmax"]
    if method == "calendar":
        thr = calendar_threshold(tmax, percentile)
        summary = {"type": "calendar-day", "min_c": round(float(thr.min()), 1), "max_c": round(float(thr.max()), 1)}
    else:
        t = fixed_threshold(tmax, percentile)
        thr = pd.Series(t, index=tmax.index)
        summary = {"type": "fixed", "value_c": round(t, 1)}
    exceed = (tmax > thr).to_numpy()  # NaN compares False -> missing data breaks a run (conservative)
    rows = []
    for s, e in find_runs(exceed, min_days):
        seg = tmax.iloc[s:e] - thr.iloc[s:e]
        rows.append(
            {
                "start": tmax.index[s],
                "end": tmax.index[e - 1],
                "duration": e - s,
                "mean_excess": float(seg.mean()),
                "peak": float(tmax.iloc[s:e].max()),
                "year": int(tmax.index[s].year),
            }
        )
    ev = pd.DataFrame(rows, columns=["start", "end", "duration", "mean_excess", "peak", "year"])
    return HazardResult(ev, summary, "°C", "°C above threshold")


def detect_heavy_rain(df: pd.DataFrame, percentile: float = 95, min_days: int = 1, method: str = "fixed") -> HazardResult:
    p = df["precip"]
    wet = p[p >= WET_DAY_MM]
    t = fixed_threshold(wet, percentile)
    exceed = (p > t).to_numpy() if not np.isnan(t) else np.zeros(len(p), dtype=bool)
    rows = []
    for s, e in find_runs(exceed, 1):
        seg = p.iloc[s:e]
        rows.append(
            {
                "start": p.index[s],
                "end": p.index[e - 1],
                "duration": e - s,
                "mean_excess": float((seg - t).mean()),
                "peak": float(seg.max()),
                "year": int(p.index[s].year),
            }
        )
    ev = pd.DataFrame(rows, columns=["start", "end", "duration", "mean_excess", "peak", "year"])
    return HazardResult(ev, {"type": "wet-day percentile", "value_mm": round(t, 1) if not np.isnan(t) else None}, "mm", "mm above threshold")


HAZARDS = {"heatwave": detect_heatwaves, "heavy_rainfall": detect_heavy_rain}
