# Single-container build: React app is compiled, then served by FastAPI.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir $(grep -viE '^(pytest|mongomock)' requirements.txt)
COPY backend/app ./app
COPY --from=web /web/dist ./frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist DATA_DIR=/app/data PORT=8000
RUN useradd -m app && mkdir -p /app/data && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
