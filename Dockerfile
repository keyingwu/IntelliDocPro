# ---- Stage 1: build the webapp ----
FROM node:22-alpine AS webapp
WORKDIR /build
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci
COPY webapp/ ./
RUN npm run build

# ---- Stage 2: Python runtime, serves API + built webapp in one process ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# server/ is not an installed package; uvicorn imports it from this workdir
WORKDIR /app/backend
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/src ./src
RUN uv pip install --system --no-cache ".[server]"
COPY backend/server ./server

# app.py serves /app/webapp/dist as the SPA when it exists
COPY --from=webapp /build/dist /app/webapp/dist

RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app

# SQLite database + uploaded document blobs live under /data
ENV INTELLIDOCPRO_DB=/data/data.db
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
