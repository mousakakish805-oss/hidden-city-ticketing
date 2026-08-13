# Single image serving both the API and the built React app.
#
# One deployable unit instead of two keeps the browser same-origin, which
# matters here: EventSource (the live progress stream) cannot send custom
# headers and is fussy about CORS. It also means no CORS configuration to get
# wrong in production.
#
#   docker build -t hidden-city .
#   docker run -p 8000:8000 --env-file backend/.env hidden-city

# ---------------------------------------------------------------- frontend --
FROM node:22-alpine AS web

WORKDIR /build
# Copy manifests first so dependency layers cache independently of source.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ----------------------------------------------------------------- runtime --
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/scripts ./scripts

# The compiled SPA is served by FastAPI from here.
COPY --from=web /build/dist ./app/static/web

# Fail the build rather than ship an image whose reference data is missing --
# the app cannot rank candidates without it.
RUN python -c "from app.data.airports import all_airports; from app.data.routes import onward_markets; \
assert len(all_airports()) > 5000; assert onward_markets('IST'); print('reference data OK')"

# Run as a non-root user.
RUN useradd --system --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000

# The container reports unhealthy if the API cannot reach its database.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,json,sys; \
r=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)); \
sys.exit(0 if r.get('database_reachable') else 1)"

# Migrations run at start, not at import: create_all cannot alter an existing
# table, so a schema change would otherwise land silently.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips='*'"]
