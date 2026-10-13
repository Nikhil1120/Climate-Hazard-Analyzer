"""Safe client for the Open-Meteo archive (ERA5) and geocoding APIs.

Safety: fixed hosts, numeric-only query params for the archive call, timeouts,
bounded retries with exponential backoff, response-size sanity checks.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx

from . import config


class UpstreamError(Exception):
    """Raised when the upstream weather API cannot be used."""


def _get(url: str, params: dict[str, Any]) -> dict:
    last: Exception | None = None
    for attempt in range(config.UPSTREAM_RETRIES):
        try:
            with httpx.Client(timeout=config.UPSTREAM_TIMEOUT_S, follow_redirects=False) as c:
                r = c.get(url, params=params)
            if r.status_code == 429 or r.status_code >= 500:
                raise UpstreamError(f"upstream returned {r.status_code}")
            if r.status_code != 200:
                raise UpstreamError(f"upstream rejected request ({r.status_code})")
            if len(r.content) > 20_000_000:
                raise UpstreamError("upstream response unexpectedly large")
            return r.json()
        except (httpx.HTTPError, UpstreamError, ValueError) as e:
            last = e
            if isinstance(e, UpstreamError) and "rejected" in str(e):
                break  # 4xx: retrying will not help
            time.sleep(min(2**attempt, 8))
    raise UpstreamError(f"Open-Meteo unavailable: {last}")


def fetch_daily(lat: float, lon: float, start: date, end: date) -> dict:
    """Return {'dates': [...], 'tmax': [...], 'tmin': [...], 'precip': [...]} (None for gaps)."""
    data = _get(
        config.OPEN_METEO_ARCHIVE_URL,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "UTC",
        },
    )
    d = data.get("daily")
    if not d or "time" not in d:
        raise UpstreamError("upstream response missing daily data")
    n = len(d["time"])
    out = {
        "dates": d["time"],
        "tmax": d.get("temperature_2m_max", [None] * n),
        "tmin": d.get("temperature_2m_min", [None] * n),
        "precip": d.get("precipitation_sum", [None] * n),
    }
    if not all(len(out[k]) == n for k in out):
        raise UpstreamError("upstream arrays have inconsistent lengths")
    return out


def geocode(query: str, count: int = 5) -> list[dict]:
    data = _get(config.OPEN_METEO_GEOCODE_URL, {"name": query, "count": count, "language": "en", "format": "json"})
    res = []
    for r in data.get("results", []) or []:
        res.append(
            {
                "name": r.get("name"),
                "admin1": r.get("admin1"),
                "country": r.get("country"),
                "lat": r.get("latitude"),
                "lon": r.get("longitude"),
                "feature": r.get("feature_code"),
            }
        )
    return res
