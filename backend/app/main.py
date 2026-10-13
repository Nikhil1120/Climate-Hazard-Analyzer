"""FastAPI application: JSON API + (optionally) the built React frontend."""
 

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, openmeteo, service
from .ratelimit import RateLimiter
from .store import Store, make_store

log = logging.getLogger("climate")
app = FastAPI(title="Climate Hazard Trend Analyzer", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET"], allow_headers=["*"])

_store: Optional[Store] = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = make_store()
    return _store


general_limit = RateLimiter(config.RATE_LIMIT_GENERAL, 60, "general")
analysis_limit = RateLimiter(config.RATE_LIMIT_ANALYSIS, 60, "analysis")


@app.get("/api/health")
def health(store: Store = Depends(get_store)):
    return {"status": "ok", "storage": store.kind()}


@app.get("/api/geocode", dependencies=[Depends(general_limit)])
def geocode(q: str = Query(..., min_length=2, max_length=80)):
    q = " ".join(q.split())
    try:
        return {"results": openmeteo.geocode(q)}
    except openmeteo.UpstreamError as e:
        raise HTTPException(502, str(e))


def _resolve_region(lat, lon, min_lat, max_lat, min_lon, max_lon):
    """Accept either a point (lat, lon) or a box (min_lat, max_lat, min_lon, max_lon -> centre point)."""
    box = [min_lat, max_lat, min_lon, max_lon]
    if all(v is not None for v in box):
        if min_lat >= max_lat or min_lon >= max_lon:
            raise HTTPException(422, "Box must satisfy min_lat < max_lat and min_lon < max_lon")
        if (max_lat - min_lat) > config.MAX_BOX_DEG or (max_lon - min_lon) > config.MAX_BOX_DEG:
            raise HTTPException(422, f"Box too large (max {config.MAX_BOX_DEG}° per side)")
        return (min_lat + max_lat) / 2, (min_lon + max_lon) / 2, "box"
    if lat is not None and lon is not None:
        return lat, lon, "point"
    raise HTTPException(422, "Provide lat & lon, or min_lat, max_lat, min_lon, max_lon")


def _run(lat, lon, min_lat, max_lat, min_lon, max_lon, start_year, end_year, hazard, percentile, min_days, method, name, store):
    clat, clon, kind = _resolve_region(lat, lon, min_lat, max_lat, min_lon, max_lon)
    if end_year < start_year:
        raise HTTPException(422, "end_year must be >= start_year")
    span = end_year - start_year + 1
    if span < config.MIN_SPAN_YEARS or span > config.MAX_SPAN_YEARS:
        raise HTTPException(422, f"Range must span {config.MIN_SPAN_YEARS}-{config.MAX_SPAN_YEARS} years")
    if end_year > date.today().year:
        raise HTTPException(422, "end_year cannot be in the future")
    name = " ".join(name.split()) if name else None
    try:
        res = service.analyze(store, clat, clon, start_year, end_year, hazard, percentile, min_days, method, name)
    except openmeteo.UpstreamError as e:
        log.warning("upstream failure: %s", e)
        raise HTTPException(502, "Weather data provider is unavailable right now. Please retry shortly.")
    except ValueError as e:
        raise HTTPException(404, str(e))
    res["region"]["selection"] = kind
    return res


@app.get("/api/analysis", dependencies=[Depends(analysis_limit)])
def analysis(
    response: Response,
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    min_lat: Optional[float] = Query(None, ge=-90, le=90),
    max_lat: Optional[float] = Query(None, ge=-90, le=90),
    min_lon: Optional[float] = Query(None, ge=-180, le=180),
    max_lon: Optional[float] = Query(None, ge=-180, le=180),
    start_year: int = Query(1990, ge=config.MIN_YEAR, le=2100),
    end_year: int = Query(2020, ge=config.MIN_YEAR, le=2100),
    hazard: Literal["heatwave", "heavy_rainfall"] = "heatwave",
    percentile: float = Query(95, ge=80, le=99.9),
    min_days: int = Query(3, ge=1, le=14),
    method: Literal["calendar", "fixed"] = "calendar",
    name: Optional[str] = Query(None, max_length=120),
    store: Store = Depends(get_store),
):
    res = _run(lat, lon, min_lat, max_lat, min_lon, max_lon, start_year, end_year, hazard, percentile, min_days, method, name, store)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return res


@app.get("/api/analysis.csv", dependencies=[Depends(analysis_limit)])
def analysis_csv(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    min_lat: Optional[float] = Query(None, ge=-90, le=90),
    max_lat: Optional[float] = Query(None, ge=-90, le=90),
    min_lon: Optional[float] = Query(None, ge=-180, le=180),
    max_lon: Optional[float] = Query(None, ge=-180, le=180),
    start_year: int = Query(1990, ge=config.MIN_YEAR, le=2100),
    end_year: int = Query(2020, ge=config.MIN_YEAR, le=2100),
    hazard: Literal["heatwave", "heavy_rainfall"] = "heatwave",
    percentile: float = Query(95, ge=80, le=99.9),
    min_days: int = Query(3, ge=1, le=14),
    method: Literal["calendar", "fixed"] = "calendar",
    store: Store = Depends(get_store),
):
    res = _run(lat, lon, min_lat, max_lat, min_lon, max_lon, start_year, end_year, hazard, percentile, min_days, method, None, store)
    fname = f"{hazard}_{res['meta']['cell']}_{start_year}-{end_year}.csv"
    return Response(service.to_csv(res), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# Serve the built React app when present (single-container deployment).
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (config.FRONTEND_DIST / path).resolve()
        if path and target.is_file() and config.FRONTEND_DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(config.FRONTEND_DIST / "index.html")
