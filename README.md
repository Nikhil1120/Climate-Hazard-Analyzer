# Climate Hazard Trend Analyzer

A web app that analyses historical weather data and shows how climate hazards (default: **heatwaves**) have changed in a region over time: frequency, duration, intensity, trend statistics, and a plain-language insight that states whether the trend is statistically significant.

- **Frontend:** React 18 + Vite, Chart.js, Leaflet map
- **Backend:** Python, FastAPI, pandas / NumPy / SciPy
- **Database:** MongoDB (document store); a JSON-file store is used automatically when no `MONGODB_URI` is set, so local dev needs no database
- **Data:** [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5 reanalysis, free, no key)

---

## 1. Run it locally

Requirements: Python 3.10+, Node 18+. (Optional: Docker.)

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### Frontend (second terminal)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 (Vite proxies `/api` to port 8000).

### Using MongoDB locally (optional)
```bash
docker run -d -p 27017:27017 --name mongo mongo:7
export MONGODB_URI=mongodb://localhost:27017      # PowerShell: $env:MONGODB_URI="mongodb://localhost:27017"
# restart uvicorn
```
`GET /api/health` reports which storage is active.

### Everything in Docker
```bash
docker compose up --build        # app + MongoDB at http://localhost:8000
```

### Tests
```bash
cd backend && source .venv/bin/activate && pytest -q      # 26 tests
```

---

## 2. Deploy (free tier)

The Dockerfile builds the React app and serves it from FastAPI, so one service = one URL.

1. Push this repo to GitHub.
2. Create a free **MongoDB Atlas M0** cluster, create a DB user, allow network access (0.0.0.0/0 for a demo), copy the connection string.
3. On **Render**: New → Blueprint → select the repo (it reads `render.yaml`). Set the `MONGODB_URI` env var to the Atlas string.
4. Wait for the build; the app URL is your submission URL. First request after idle may take ~30 s (free-tier cold start).

Alternative: Cloud Run / Fly.io work the same way using the Dockerfile.

---

## 3. How it was built (step by step)

1. **Read the brief, fixed scope**: heatwave analysis end to end first; multi-hazard only as a cheap extension (heavy rainfall reuses the same pipeline).
2. **Data source**: chose Open-Meteo (no key, daily `temperature_2m_max/min` and `precipitation_sum` back to 1940, plus a geocoding endpoint for city/state search).
3. **Storage design** (`backend/app/store.py`): two collections: `weather_daily` (one document per grid-cell × year) and `analysis` (computed result cached by parameter hash). A `Store` interface with `MongoStore` and `FileStore` implementations.
4. **Ingest + cache** (`ingest.py`): coordinates are snapped to a 0.25° grid; only years missing from the DB are fetched, in blocks of ≤10 years; finished years are immutable, the in-progress year is refreshed at most daily; a per-cell lock stops duplicate upstream calls under concurrency.
5. **Cleaning** (`ingest.clean`): continuous daily calendar so gaps are explicit; physically implausible values removed; gaps ≤2 days interpolated, longer gaps left missing.
6. **Hazard logic** (`hazards.py`): percentile thresholds and run detection (see §5).
7. **Trends** (`trends.py`): annual aggregates, 5-year rolling mean, OLS, Mann-Kendall + Sen's slope, first-vs-last-decade change, and an insight generator that refuses to overstate.
8. **API** (`main.py`): validated query parameters, rate limiting, caching headers, CSV export, SPA hosting.
9. **Frontend**: Leaflet map (point or two-click lat-lon box) + city search, controls, three Chart.js charts, insight panel, CSV download and print-to-PDF.
10. **Tests** (`backend/tests`): synthetic weather with injected warming, gaps and outliers; mocked upstream; both store backends (MongoDB tested via `mongomock`).

---

## 4. Architecture

```
React (Vite)  ──/api──▶  FastAPI ──▶ rate limit + validation
                            │
                            ▼
                      service.analyze()
        ┌───────────────────┼─────────────────────────┐
  analysis cache hit?   ensure_data()              compute
   (Mongo `analysis`)   fetch missing years         clean → detect → aggregate → trends
        │               from Open-Meteo ─▶ Mongo      │
        └──────────────▶ `weather_daily` ─▶ read ─────┘ ─▶ store result ─▶ JSON
```

| Endpoint | Purpose |
|---|---|
| `GET /api/analysis` | Full JSON: annual series, trends, insight, top events, data-quality report |
| `GET /api/analysis.csv` | Annual table as CSV |
| `GET /api/geocode?q=` | City/state search |
| `GET /api/health` | Status + active storage |

Key query params: `lat, lon` **or** `min_lat, max_lat, min_lon, max_lon`; `start_year, end_year` (10–75 years, ≥1950); `hazard` (`heatwave` default | `heavy_rainfall`); `percentile` (80–99.9, default 95); `min_days` (default 3); `method` (`calendar` | `fixed`).

---

## 5. Hazard logic

**Heatwave** = at least `min_days` (default 3) consecutive days with daily maximum temperature above the 95th percentile.

- `method=calendar` (default): the threshold is the 95th percentile of Tmax within ±7 days of each calendar day, across all years in the period. This is the standard climatological approach and avoids labelling every summer day "extreme" simply because it is warmer than winter.
- `method=fixed`: one percentile of all daily values (the literal reading of the brief). Available in the UI; it detects only the hottest season.
- Missing days break a run (conservative: a heatwave is never created by gaps).
- Each event records duration, mean excess over the threshold (intensity) and peak Tmax. Annual metrics: events, hazard days, longest event, mean duration, mean intensity.

**Heavy rainfall**: a day above the 95th percentile of wet days (≥1 mm).

**Trends**: OLS slope, Mann-Kendall test with tie correction, Sen's slope (per decade), 5-year rolling mean. Insight text compares the first and last ~10-year blocks and reports significance (p<0.05). It says "not statistically significant" when that is the case.

**Data-quality rules**: outliers (Tmax/Tmin outside −90..60 °C, Tmin > Tmax, negative or >2000 mm precipitation) removed; years with <90% coverage or still in progress are excluded from trend statistics and flagged in the chart and response.

---

## 6. Assumptions and limitations (please read)

- **Baseline = the selected period.** The percentile threshold comes from the same years being analysed, so results show change in how often locally extreme days occur *within that period*. Using a fixed WMO baseline (e.g. 1991–2020) is a straightforward extension.
- **One grid cell per request.** A lat-lon box is analysed at its centre point, not as an area average. ERA5 (~25 km) smooths local extremes and differs from station records.
- Heatwave events are assigned to the year in which they start.
- The 5-day archive lag means the current year is always partial and is excluded from trends.
- Percentage changes can be large when the starting count is small; the UI shows the underlying counts and the p-value next to them.
- **Rate limiting is in-memory** (per instance). Behind multiple instances it should move to Redis or the gateway.

### Verification status
- Backend logic, caching, validation, both store implementations and the API are covered by automated tests using synthetic data and a mocked Open-Meteo.
- The workspace this was built in could not reach `open-meteo.com`, so **the live upstream call has not been exercised here**. Please run one real analysis locally before submitting (see §1) and check the first result looks sensible for a known hot region.
- Not deployed from the build environment: the deploy URL has to be created by following §2.

---

## 7. What I would improve with more time

- Area-averaged analysis over a grid inside the box; true state/district polygons.
- Fixed reference baseline option and humid-heat / minimum-temperature (warm night) definitions.
- Block-bootstrap significance to account for autocorrelation; Theil-Sen confidence intervals.
- Redis-backed rate limiting and cache; background ingestion queue for large ranges.
- Server-generated PDF report; frontend tests (Vitest / Playwright).
- Code-split the Chart.js / Leaflet bundle.

---

## 8. AI tools used

Built with **Claude (Anthropic)** as a coding assistant: it generated the initial code for the backend, frontend, tests and this README from the case-study brief, and ran the tests. **Edit this section to describe your own review and changes before submitting**, and be ready to explain every module in the interview (start with `hazards.py`, `ingest.py`, `trends.py`, `service.py`).
