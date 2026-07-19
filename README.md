# IntelliDocPro

Schema-driven document processing platform. Upload a sample document to auto-infer a
field schema, then batch-extract structured data from PDFs/images (value + confidence +
source location + review flag), with switchable LLM engines and per-run cost accounting.

```
backend/    Python package (reusable on its own) + FastAPI service + SQLite storage
webapp/     React + Vite + TS frontend (Document Agent management / 3-step wizard / results table / Excel export)
docs/       Design documents
```

## Quick start

### Docker (recommended)

```bash
# Option A: run the published image (data lives in the intellidocpro-data volume)
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... \
  -v intellidocpro-data:/data ghcr.io/keyingwu/intellidocpro
# open http://localhost:8000

# Option B: build locally with docker compose
cp backend/.env.example backend/.env   # fill in a key for at least one engine, delete unused sections
docker compose up --build
```

Engine keys can also be passed as host environment variables
(`export OPENAI_API_KEY=...` before `docker compose up`); when both are set,
the environment variable wins over `backend/.env`.

### Development from source

```bash
# 1. Backend (Python >= 3.10, using uv)
cd backend
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env    # fill in a key for at least one engine

# 2. Frontend
cd ../webapp && npm install

# 3. Dev mode (two terminals)
cd backend && .venv/bin/python -m uvicorn server.app:app --port 8000
cd webapp && npm run dev          # http://localhost:5173

# Or production mode (single process): after building, FastAPI serves the frontend
cd webapp && npm run build
cd ../backend && .venv/bin/python -m uvicorn server.app:app --port 8000
# open http://localhost:8000
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest                    # unit + service tests, no network needed
.venv/bin/python -m pytest tests/integration  # real API end-to-end, skipped per missing key
```

See [backend/README.md](backend/README.md) for engine and library usage.
