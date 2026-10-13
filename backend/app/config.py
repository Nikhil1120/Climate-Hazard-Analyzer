"""Central configuration, read from environment variables with safe defaults."""
import os
from pathlib import Path

MONGODB_URI = os.getenv("MONGODB_URI", "")  # empty -> local file-backed document store
MONGODB_DB = os.getenv("MONGODB_DB", "climate_hazards")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

# Upstream APIs (fixed hosts only; user input never becomes a host or path).
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
UPSTREAM_TIMEOUT_S = float(os.getenv("UPSTREAM_TIMEOUT_S", "30"))
UPSTREAM_RETRIES = int(os.getenv("UPSTREAM_RETRIES", "3"))
ARCHIVE_LAG_DAYS = 6  # ERA5 archive trails real time by a few days

# Caching
GRID_RESOLUTION_DEG = 0.25  # requests are snapped to this grid (~ERA5 native resolution)
ANALYSIS_TTL_S = int(os.getenv("ANALYSIS_TTL_S", str(24 * 3600)))
CURRENT_YEAR_REFRESH_S = 24 * 3600  # re-fetch the in-progress year at most daily

# Rate limiting (requests per minute per client IP)
RATE_LIMIT_GENERAL = int(os.getenv("RATE_LIMIT_GENERAL", "120"))
RATE_LIMIT_ANALYSIS = int(os.getenv("RATE_LIMIT_ANALYSIS", "20"))

# Input limits
MIN_YEAR = 1950
MIN_SPAN_YEARS = 10
MAX_SPAN_YEARS = 75
MAX_BOX_DEG = 10.0

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"))
