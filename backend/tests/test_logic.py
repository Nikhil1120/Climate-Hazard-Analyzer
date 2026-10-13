from datetime import date

import mongomock
import numpy as np
import pandas as pd

from app import ingest, service
from app.hazards import calendar_threshold, detect_heatwaves, find_runs
from app.store import FileStore, MongoStore
from app.trends import mann_kendall

TODAY = date(2026, 10, 12)


def test_find_runs_min_length():
    m = np.array([0, 1, 1, 0, 1, 1, 1, 1, 0, 1], dtype=bool)
    assert find_runs(m, 3) == [(4, 8)]
    assert find_runs(m, 2) == [(1, 3), (4, 8)]
    assert find_runs(np.array([], dtype=bool), 3) == []


def test_heatwave_detection_exact_run():
    idx = pd.date_range("2000-01-01", "2004-12-31", freq="D")
    tmax = pd.Series(30.0, index=idx)
    tmax[(idx >= "2002-06-10") & (idx <= "2002-06-13")] = 45.0  # 4-day event
    tmax[(idx >= "2003-06-10") & (idx <= "2003-06-11")] = 45.0  # 2-day spike: must NOT count
    df = pd.DataFrame({"tmax": tmax, "tmin": tmax - 10, "precip": 0.0})
    res = detect_heatwaves(df, percentile=95, min_days=3, method="fixed")
    assert len(res.events) == 1
    ev = res.events.iloc[0]
    assert ev.duration == 4 and ev.year == 2002 and ev.peak == 45.0


def test_missing_data_breaks_run():
    idx = pd.date_range("2000-01-01", "2004-12-31", freq="D")
    tmax = pd.Series(30.0, index=idx)
    tmax[(idx >= "2002-06-10") & (idx <= "2002-06-14")] = 45.0
    tmax["2002-06-12"] = np.nan
    df = pd.DataFrame({"tmax": tmax, "tmin": tmax - 10, "precip": 0.0})
    assert len(detect_heatwaves(df, 95, 3, "fixed").events) == 0


def test_calendar_threshold_follows_seasons():
    idx = pd.date_range("1990-01-01", "2019-12-31", freq="D")
    rng = np.random.default_rng(0)
    doy = idx.dayofyear.to_numpy()
    tmax = pd.Series(20 + 15 * np.sin((doy - 100) / 365 * 2 * np.pi) + rng.normal(0, 1, len(idx)), index=idx)
    thr = calendar_threshold(tmax, 95)
    assert thr["2000-07-01"] > thr["2000-01-01"] + 15  # summer threshold far above winter


def test_mann_kendall_detects_trend_and_noise():
    up = mann_kendall(list(range(30)))
    assert up["p"] < 0.001 and up["sen_slope"] == 1.0
    rng = np.random.default_rng(3)
    noise = mann_kendall(rng.normal(0, 1, 30).tolist())
    assert noise["p"] > 0.05
    assert mann_kendall([1, 2, 3])["p"] is None


def test_clean_handles_gaps_and_outliers(fetcher):
    raw = fetcher(0, 0, date(2000, 1, 1), date(2002, 12, 31))
    df = pd.DataFrame({"tmax": raw["tmax"], "tmin": raw["tmin"], "precip": raw["precip"]}, index=pd.to_datetime(raw["dates"]))
    clean, qc = ingest.clean(df)
    assert qc["outliers_removed"] == 1  # the 999 C value
    assert qc["gaps_interpolated"] >= 2  # 2-day gap filled
    assert qc["missing_days_remaining"] >= 5  # 5-day gap kept as missing
    assert clean["tmax"].max() < 60


def _stores(tmp_path):
    return [FileStore(tmp_path / "fs"), MongoStore("", "t", client=mongomock.MongoClient())]


def test_full_pipeline_and_cache(tmp_path, fetcher):
    for store in _stores(tmp_path):
        fetcher.calls.clear()
        res = service.analyze(store, 17.38, 78.48, 1990, 2020, fetcher=fetcher, today=TODAY, region_name="Hyderabad")
        assert res["meta"]["served_from"] == "computed"
        assert len(res["annual"]) == 31
        assert res["trends"]["hazard_days"]["mann_kendall"]["sen_slope"] > 0  # injected warming is detected
        assert res["insight"]["significance"] == "significant"
        n_calls = len(fetcher.calls)
        assert n_calls == 4  # 31 years -> blocks of <=10 years

        # same params -> served from analysis cache, zero upstream calls
        again = service.analyze(store, 17.38, 78.48, 1990, 2020, fetcher=fetcher, today=TODAY)
        assert again["meta"]["served_from"] == "analysis-cache" and len(fetcher.calls) == n_calls

        # different params but same cell/years -> raw data reused from DB, no new upstream calls
        service.analyze(store, 17.40, 78.50, 1990, 2020, percentile=90, fetcher=fetcher, today=TODAY)
        assert len(fetcher.calls) == n_calls  # (17.40,78.50) snaps to same 0.25 cell

        # extending the range fetches only the missing years
        service.analyze(store, 17.38, 78.48, 1985, 2020, fetcher=fetcher, today=TODAY)
        assert len(fetcher.calls) == n_calls + 1


def test_in_progress_year_excluded_from_trend(tmp_path, fetcher):
    store = FileStore(tmp_path)
    res = service.analyze(store, 17.38, 78.48, 2010, 2026, fetcher=fetcher, today=TODAY)
    last = res["annual"][-1]
    assert last["year"] == 2026 and last["complete"] is False
    assert 2026 in res["quality"]["years_excluded"]


def test_csv_export(tmp_path, fetcher):
    res = service.analyze(FileStore(tmp_path), 17.38, 78.48, 1990, 2005, fetcher=fetcher, today=TODAY)
    csv = service.to_csv(res).splitlines()
    assert csv[0].startswith("year,event_count") and len(csv) == 17


def test_heavy_rain_hazard(tmp_path, fetcher):
    res = service.analyze(FileStore(tmp_path), 17.38, 78.48, 1990, 2005, hazard="heavy_rainfall", min_days=1, fetcher=fetcher, today=TODAY)
    assert res["hazard"]["id"] == "heavy_rainfall" and sum(r["event_count"] for r in res["annual"]) > 0
