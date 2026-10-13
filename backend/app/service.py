"""Orchestration: ingest -> read from DB -> clean -> detect -> aggregate -> trends -> cache result."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from . import config, ingest, openmeteo
from .hazards import HAZARDS
from .store import Store
from .trends import build_insight, mann_kendall, ols, period_change, rolling_mean

HAZARD_LABELS = {"heatwave": "Heatwave", "heavy_rainfall": "Heavy-rainfall"}
MIN_COVERAGE = 0.9  # years with less valid-data coverage are excluded from trend statistics


def params_key(p: dict) -> str:
    blob = json.dumps(p, sort_keys=True)
    return "an_" + hashlib.sha256(blob.encode()).hexdigest()[:32]


def _annual_table(df: pd.DataFrame, events: pd.DataFrame, years: list[int]) -> list[dict]:
    rows = []
    for y in years:
        dy = df[df.index.year == y]
        expected = 366 if pd.Timestamp(year=y, month=1, day=1).is_leap_year else 365
        # a still-running year is only expected up to its last available day
        if len(dy):
            expected = min(expected, (dy.index.max() - pd.Timestamp(year=y, month=1, day=1)).days + 1)
        coverage = float(dy["tmax"].notna().sum() / expected) if expected else 0.0
        ev = events[events["year"] == y]
        rows.append(
            {
                "year": y,
                "event_count": int(len(ev)),
                "hazard_days": int(ev["duration"].sum()) if len(ev) else 0,
                "max_duration": int(ev["duration"].max()) if len(ev) else 0,
                "mean_duration": round(float(ev["duration"].mean()), 2) if len(ev) else 0.0,
                "mean_intensity": round(float(ev["mean_excess"].mean()), 2) if len(ev) else 0.0,
                "peak_value": round(float(ev["peak"].max()), 1) if len(ev) else None,
                "mean_tmax": round(float(dy["tmax"].mean()), 2) if dy["tmax"].notna().any() else None,
                "coverage": round(coverage, 3),
                "complete": bool(len(dy) and coverage >= MIN_COVERAGE and dy.index.max() >= pd.Timestamp(year=y, month=12, day=31)),
            }
        )
    return rows


def analyze(
    store: Store,
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
    hazard: str = "heatwave",
    percentile: float = 95,
    min_days: int = 3,
    method: str = "calendar",
    region_name: str | None = None,
    fetcher: Callable = openmeteo.fetch_daily,
    today: date | None = None,
) -> dict:
    cid = ingest.cell_id(lat, lon)
    key_params = dict(cell=cid, start=start_year, end=end_year, hazard=hazard, p=percentile, d=min_days, m=method)
    key = params_key(key_params)
    cached = store.get_analysis(key)
    if cached and time.time() - cached["created_at"] < config.ANALYSIS_TTL_S:
        res = dict(cached["result"])
        res["meta"] = {**res["meta"], "served_from": "analysis-cache"}
        res["region"]["name"] = region_name or res["region"]["name"]
        return res

    ingest.ensure_data(store, lat, lon, start_year, end_year, fetcher, today)
    raw = ingest.load_frame(store, cid, start_year, end_year)
    if raw.empty:
        raise ValueError("No data available for this location/period")
    df, qc = ingest.clean(raw)
    detect = HAZARDS[hazard]
    hres = detect(df, percentile=percentile, min_days=min_days, method=method)

    years = list(range(start_year, end_year + 1))
    annual = _annual_table(df, hres.events, years)
    ok = [r for r in annual if r["complete"]]
    qc["years_requested"] = len(years)
    qc["years_used_for_trend"] = len(ok)
    qc["years_excluded"] = [r["year"] for r in annual if not r["complete"]]

    label = HAZARD_LABELS[hazard]
    region = {"name": region_name or f"{ingest.snap(lat):.2f}, {ingest.snap(lon):.2f}", "lat": ingest.snap(lat), "lon": ingest.snap(lon)}
    trends: dict = {}
    insight = {"headline": "Not enough complete years to compute a trend.", "significance": "insufficient_data", "caveats": []}
    if len(ok) >= 3:
        ys = [r["year"] for r in ok]
        for metric, mlabel in (("hazard_days", "days per year"), ("event_count", "events per year")):
            vals = [float(r[metric]) for r in ok]
            trends[metric] = {
                "ols": ols(ys, vals),
                "mann_kendall": mann_kendall(vals),
                "change": period_change(ys, vals),
            }
        t = [r["mean_tmax"] for r in ok if r["mean_tmax"] is not None]
        if len(t) == len(ok):
            trends["mean_tmax"] = {"ols": ols(ys, t), "mann_kendall": mann_kendall(t)}
        main = "hazard_days"
        insight = build_insight(
            label, "days per year" if hazard == "heatwave" else "days per year", ys, [float(r[main]) for r in ok],
            trends[main]["mann_kendall"], trends[main]["change"], region["name"],
        )
        # Rolling 5-year mean across ALL requested complete years, aligned to annual rows
    roll = rolling_mean([float(r["hazard_days"]) for r in annual], 5)
    for r, v in zip(annual, roll):
        r["rolling_5y_days"] = v
    if trends.get("hazard_days"):
        o = trends["hazard_days"]["ols"]
        for r in annual:
            r["trend_fit"] = round(max(0.0, o["intercept"] + o["slope"] * r["year"]), 3)

    events_out = [
        {"start": e.start.date().isoformat(), "end": e.end.date().isoformat(), "duration": int(e.duration),
         "mean_excess": round(e.mean_excess, 2), "peak": round(e.peak, 1)}
        for e in hres.events.sort_values(["duration", "mean_excess"], ascending=False).head(15).itertuples()
    ]
    result = {
        "region": region,
        "hazard": {
            "id": hazard,
            "label": label,
            "definition": _definition(hazard, percentile, min_days, method),
            "threshold": hres.threshold_summary,
            "unit": hres.unit,
            "excess_unit": hres.excess_unit,
        },
        "range": {"start_year": start_year, "end_year": end_year},
        "annual": annual,
        "trends": trends,
        "insight": insight,
        "top_events": events_out,
        "quality": qc,
        "meta": {
            "source": "Open-Meteo Historical Weather API (ERA5 reanalysis)",
            "cell": cid,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "served_from": "computed",
            "storage": store.kind(),
        },
    }
    store.put_analysis(key, result)
    return result


def _definition(hazard: str, percentile: float, min_days: int, method: str) -> str:
    if hazard == "heatwave":
        base = "the calendar-day" if method == "calendar" else "the all-days"
        return f"≥{min_days} consecutive days with daily maximum temperature above {base} {percentile:g}th percentile"
    return f"a day with precipitation above the {percentile:g}th percentile of wet days (≥1 mm)"


def to_csv(result: dict) -> str:
    cols = ["year", "event_count", "hazard_days", "max_duration", "mean_duration", "mean_intensity", "peak_value", "mean_tmax", "coverage", "rolling_5y_days", "trend_fit"]
    lines = [",".join(cols)]
    for r in result["annual"]:
        lines.append(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols))
    return "\n".join(lines) + "\n"
