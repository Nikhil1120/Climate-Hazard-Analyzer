import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def synthetic_fetcher(trend_per_year=0.08, seed=1, gaps=True, outliers=True):
    """Fake Open-Meteo: seasonal Tmax + noise + warming trend, with gaps and a bad value."""
    calls = []

    def fetch(lat, lon, start: date, end: date):
        calls.append((start, end))
        rng = np.random.default_rng(seed + start.year)
        days = (end - start).days + 1
        dates = [start + timedelta(days=i) for i in range(days)]
        doy = np.array([d.timetuple().tm_yday for d in dates])
        yrs = np.array([d.year for d in dates])
        # AR(1) noise: real weather is persistent, so multi-day hot spells actually occur
        from scipy.signal import lfilter

        noise = lfilter([1], [1, -0.75], rng.normal(0, 1.5, days))
        tmax = 30 + 8 * np.sin((doy - 100) / 365 * 2 * np.pi) + noise + trend_per_year * (yrs - 1990)
        tmin = tmax - 10
        precip = np.maximum(0, rng.gamma(0.4, 6, days) - 1)
        tmax_l, tmin_l, p_l = tmax.round(1).tolist(), tmin.round(1).tolist(), precip.round(1).tolist()
        if gaps:
            for i in (50, 51, 400, 401, 402, 403, 404):  # 2-day gap (interpolated) + 5-day gap (kept)
                if i < days:
                    tmax_l[i] = None
        if outliers and days > 700:
            tmax_l[700] = 999.0
        return {"dates": [d.isoformat() for d in dates], "tmax": tmax_l, "tmin": tmin_l, "precip": p_l}

    fetch.calls = calls
    return fetch


@pytest.fixture
def fetcher():
    return synthetic_fetcher()
