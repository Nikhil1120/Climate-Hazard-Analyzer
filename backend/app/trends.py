"""Trend statistics: OLS, Mann-Kendall + Sen's slope, rolling means, and honest plain-language insight."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats


def mann_kendall(y: list[float]) -> dict:
    """Mann-Kendall test (with tie correction) + Sen's slope. Returns p=None if n < 8."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 8:
        return {"tau": None, "z": None, "p": None, "sen_slope": None, "n": n}
    s = 0
    for i in range(n - 1):
        s += np.sign(y[i + 1 :] - y[i]).sum()
    _, counts = np.unique(y, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5) - np.sum(counts * (counts - 1) * (2 * counts + 5))) / 18.0
    if var_s <= 0:
        return {"tau": 0.0, "z": 0.0, "p": 1.0, "sen_slope": 0.0, "n": n}
    z = (s - 1) / math.sqrt(var_s) if s > 0 else (s + 1) / math.sqrt(var_s) if s < 0 else 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    slopes = [(y[j] - y[i]) / (j - i) for i in range(n - 1) for j in range(i + 1, n)]
    return {"tau": float(s / (n * (n - 1) / 2)), "z": float(z), "p": float(p), "sen_slope": float(np.median(slopes)), "n": n}


def ols(x: list[float], y: list[float]) -> dict:
    if len(x) < 3 or len(set(y)) == 1:
        return {"slope": 0.0, "intercept": float(np.mean(y)) if len(y) else 0.0, "r2": 0.0, "p": 1.0}
    r = stats.linregress(x, y)
    return {"slope": float(r.slope), "intercept": float(r.intercept), "r2": float(r.rvalue**2), "p": float(r.pvalue)}


def rolling_mean(values: list[float], window: int = 5) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(round(float(np.mean(values[i + 1 - window : i + 1])), 3))
    return out


def period_change(years: list[int], values: list[float]) -> dict:
    """Compare the mean of the first vs last block (10 years, or a third of the record if shorter)."""
    n = len(values)
    k = min(10, max(3, n // 3))
    first, last = float(np.mean(values[:k])), float(np.mean(values[-k:]))
    pct = None if first == 0 else (last - first) / first * 100
    return {
        "first_label": f"{years[0]}–{years[k - 1]}",
        "last_label": f"{years[-k]}–{years[-1]}",
        "first_mean": round(first, 3),
        "last_mean": round(last, 3),
        "pct_change": None if pct is None else round(pct, 1),
    }


def build_insight(hazard_label: str, metric_label: str, years: list[int], values: list[float], mk: dict, change: dict, region: str) -> dict:
    """Plain-language statement that never overstates: it reports significance and the data caveat."""
    p = mk.get("p")
    ptxt = "p<0.001" if (p is not None and p < 0.001) else (f"p={p:.3f}" if p is not None and p < 0.05 else f"p={p:.2f}" if p is not None else "")
    if p is None:
        return {"headline": f"Not enough complete years to assess a trend in {metric_label}.", "significance": "insufficient_data", "caveats": []}
    sig = p < 0.05
    direction = "increased" if (mk["sen_slope"] or 0) > 0 else "decreased" if (mk["sen_slope"] or 0) < 0 else "not changed"
    if change["pct_change"] is not None:
        mag = f"{abs(change['pct_change']):.0f}% ({change['first_mean']:.1f} → {change['last_mean']:.1f} per year, {change['first_label']} vs {change['last_label']})"
    else:
        mag = f"from {change['first_mean']:.1f} to {change['last_mean']:.1f} per year ({change['first_label']} vs {change['last_label']})"
    if sig and direction != "not changed":
        headline = f"{hazard_label} {metric_label} {direction} by {mag} in {region}. The trend is statistically significant (Mann-Kendall {ptxt})."
        level = "significant"
    elif direction == "not changed":
        headline = f"No change in {hazard_label.lower()} {metric_label} was detected in {region}."
        level = "none"
    else:
        headline = (
            f"{hazard_label} {metric_label} appear to have {direction} by {mag} in {region}, "
            f"but this is not statistically significant (Mann-Kendall {ptxt}); year-to-year variability is large relative to the change."
        )
        level = "not_significant"
    caveats = [
        "Thresholds are percentiles of the selected period, so this measures changes in how often locally extreme days occur within that period.",
        "Data is ERA5 reanalysis sampled at one grid cell (~25 km); it smooths local extremes and can differ from station records.",
    ]
    if len(values) < 20:
        caveats.append("Fewer than 20 years selected: trend estimates are fragile. Extend the range if possible.")
    return {"headline": headline, "significance": level, "caveats": caveats}
