"""Ingest + cache: make sure the DB holds daily data for every requested year, then read it back.

Cache key = grid cell (coordinates snapped to GRID_RESOLUTION_DEG). Each (cell, year) is one
document. Past years are immutable once stored; the in-progress year is refreshed at most daily.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from . import config
from .store import Store

_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)  # per-cell: avoids duplicate upstream fetches


def snap(v: float) -> float:
    r = config.GRID_RESOLUTION_DEG
    return round(round(v / r) * r, 4)


def cell_id(lat: float, lon: float) -> str:
    return f"{snap(lat):.2f}_{snap(lon):.2f}"


def last_available_date(today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=config.ARCHIVE_LAG_DAYS)


def _needs_fetch(doc: dict | None, year: int, today: date) -> bool:
    if doc is None:
        return True
    if doc.get("complete"):
        return False
    return time.time() - doc.get("fetched_at", 0) > config.CURRENT_YEAR_REFRESH_S


def ensure_data(
    store: Store,
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
    fetcher: Callable[[float, float, date, date], dict],
    today: date | None = None,
) -> str:
    """Fetch+store any missing years (one upstream call per contiguous missing block)."""
    today = today or date.today()
    cid = cell_id(lat, lon)
    clat, clon = snap(lat), snap(lon)
    with _locks[cid]:
        missing = [y for y in range(start_year, end_year + 1) if _needs_fetch(store.get_daily(cid, y), y, today)]
        # group into contiguous blocks, max 10 years per upstream request
        blocks: list[list[int]] = []
        for y in missing:
            if blocks and y == blocks[-1][-1] + 1 and len(blocks[-1]) < 10:
                blocks[-1].append(y)
            else:
                blocks.append([y])
        for b in blocks:
            s = date(b[0], 1, 1)
            e = min(date(b[-1], 12, 31), last_available_date(today))
            if e < s:
                continue
            raw = fetcher(clat, clon, s, e)
            by_year: dict[int, dict] = {y: {"dates": [], "tmax": [], "tmin": [], "precip": []} for y in b}
            for i, d in enumerate(raw["dates"]):
                y = int(d[:4])
                if y in by_year:
                    for k in ("tmax", "tmin", "precip"):
                        by_year[y][k].append(raw[k][i])
                    by_year[y]["dates"].append(d)
            for y, arrs in by_year.items():
                if not arrs["dates"]:
                    continue
                full_year = date(y, 12, 31) <= last_available_date(today)
                store.put_daily({"cell": cid, "year": y, "lat": clat, "lon": clon, **arrs, "fetched_at": time.time(), "complete": full_year})
    return cid


def load_frame(store: Store, cid: str, start_year: int, end_year: int) -> pd.DataFrame:
    """Read stored documents back into a DataFrame indexed by date (NaN for gaps)."""
    frames = []
    for y in range(start_year, end_year + 1):
        doc = store.get_daily(cid, y)
        if not doc:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(doc["dates"]),
                    "tmax": pd.to_numeric(pd.Series(doc["tmax"], dtype="object"), errors="coerce"),
                    "tmin": pd.to_numeric(pd.Series(doc["tmin"], dtype="object"), errors="coerce"),
                    "precip": pd.to_numeric(pd.Series(doc["precip"], dtype="object"), errors="coerce"),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["tmax", "tmin", "precip"], index=pd.DatetimeIndex([], name="date"))
    return pd.concat(frames).drop_duplicates("date").set_index("date").sort_index()


def _fill_short_gaps(s: pd.Series, max_gap: int) -> pd.Series:
    """Linearly interpolate only NaN runs of length <= max_gap (pandas' limit= would partially fill longer gaps)."""
    isna = s.isna()
    if not isna.any():
        return s
    run_id = (isna != isna.shift()).cumsum()
    run_len = isna.groupby(run_id).transform("sum")
    filled = s.interpolate(limit_area="inside")
    return s.where(~(isna & (run_len <= max_gap)), filled)


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Quality control. Returns cleaned frame (full daily index) and a QC report.

    - reindex to a continuous daily calendar so gaps are explicit
    - physically implausible values -> NaN (tmax/tmin outside [-90, 60] C, tmin > tmax, precip < 0 or > 2000 mm)
    - short gaps (<= 2 days) in temperature are linearly interpolated; longer gaps stay NaN
    """
    qc = {"rows_received": int(len(df)), "outliers_removed": 0, "gaps_interpolated": 0, "missing_days_remaining": 0}
    if df.empty:
        return df, qc
    full = pd.date_range(df.index.min(), df.index.max(), freq="D", name="date")
    df = df.reindex(full).copy()
    bad_t = (df["tmax"] < -90) | (df["tmax"] > 60) | (df["tmin"] < -90) | (df["tmin"] > 60) | (df["tmin"] > df["tmax"] + 0.5)
    bad_p = (df["precip"] < 0) | (df["precip"] > 2000)
    qc["outliers_removed"] = int(bad_t.sum() + bad_p.sum())
    df.loc[bad_t, ["tmax", "tmin"]] = np.nan
    df.loc[bad_p, "precip"] = np.nan
    before = int(df["tmax"].isna().sum())
    df["tmax"] = _fill_short_gaps(df["tmax"], 2)
    df["tmin"] = _fill_short_gaps(df["tmin"], 2)
    qc["gaps_interpolated"] = before - int(df["tmax"].isna().sum())
    qc["missing_days_remaining"] = int(df["tmax"].isna().sum())
    return df, qc
