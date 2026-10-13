import pytest
from fastapi.testclient import TestClient

from app import config, main, openmeteo, service
from app.ratelimit import RateLimiter
from app.store import FileStore

from .conftest import synthetic_fetcher


@pytest.fixture
def client(tmp_path, monkeypatch):
    main._store = FileStore(tmp_path)
    fetch = synthetic_fetcher()
    monkeypatch.setattr(openmeteo, "fetch_daily", fetch)
    monkeypatch.setattr(service.analyze, "__defaults__", service.analyze.__defaults__)  # no-op, keeps signature
    # analyze() binds fetcher at definition time; patch via a wrapper
    orig = service.analyze

    def wrapped(*a, **k):
        k.setdefault("fetcher", fetch)
        return orig(*a, **k)

    monkeypatch.setattr(service, "analyze", wrapped)
    monkeypatch.setattr(openmeteo, "geocode", lambda q, count=5: [{"name": q, "lat": 17.38, "lon": 78.48}])
    return TestClient(main.app)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_analysis_point_and_box(client):
    r = client.get("/api/analysis", params={"lat": 17.38, "lon": 78.48, "start_year": 2000, "end_year": 2015})
    assert r.status_code == 200 and r.json()["region"]["selection"] == "point"
    assert r.headers["cache-control"].startswith("public")
    r = client.get("/api/analysis", params={"min_lat": 16, "max_lat": 18, "min_lon": 77, "max_lon": 79, "start_year": 2000, "end_year": 2015})
    assert r.status_code == 200 and r.json()["region"]["selection"] == "box"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lon": 0},
        {"lat": 10, "lon": 200},
        {"lat": 10, "lon": 10, "start_year": 2000, "end_year": 2003},  # span too short
        {"lat": 10, "lon": 10, "start_year": 1900, "end_year": 2020},  # before MIN_YEAR
        {"lat": 10, "lon": 10, "hazard": "tornado"},
        {"lat": 10, "lon": 10, "percentile": 10},
        {"lat": 10, "lon": 10, "start_year": 2020, "end_year": 2000},
        {"min_lat": 0, "max_lat": 50, "min_lon": 0, "max_lon": 5},  # box too large
        {"lat": "abc", "lon": 1},
        {},
    ],
)
def test_invalid_inputs_rejected(client, params):
    assert client.get("/api/analysis", params=params).status_code == 422


def test_csv_endpoint(client):
    r = client.get("/api/analysis.csv", params={"lat": 17.38, "lon": 78.48, "start_year": 2000, "end_year": 2015})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("year,")


def test_geocode_validation_and_result(client):
    assert client.get("/api/geocode", params={"q": "a"}).status_code == 422
    assert client.get("/api/geocode", params={"q": "Hyderabad"}).json()["results"][0]["name"] == "Hyderabad"


def test_upstream_failure_is_502_without_leaking_details(client, monkeypatch):
    def boom(*a, **k):
        raise openmeteo.UpstreamError("secret internal detail")

    orig = service.analyze
    monkeypatch.setattr(service, "analyze", lambda *a, **k: (_ for _ in ()).throw(openmeteo.UpstreamError("secret internal detail")))
    r = client.get("/api/analysis", params={"lat": 1, "lon": 1, "start_year": 2000, "end_year": 2015})
    assert r.status_code == 502 and "secret" not in r.text


def test_rate_limiter_blocks_and_sets_retry_after():
    from fastapi import HTTPException

    class Req:
        client = type("c", (), {"host": "1.2.3.4"})()

    rl = RateLimiter(3, 60)
    for _ in range(3):
        rl(Req())
    with pytest.raises(HTTPException) as e:
        rl(Req())
    assert e.value.status_code == 429 and "Retry-After" in e.value.headers
