# IntelliDocPro Python SDK and backend

Schema-driven document field extraction layer: given a document (PDF/PNG/JPEG) and a
field schema, it returns each field's normalized value, confidence, source location,
and review flag. Extraction engines are pluggable, with Claude, OpenAI, and
Azure OpenAI built in. Documents are passed natively to the models (no homegrown
OCR/text-extraction pipeline, so scanned documents work out of the box).

Design document: `../docs/superpowers/specs/2026-07-13-intellidocpro-backend-design.md`

## Installation

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Usage (Python library)

```python
import intellidocpro

schema = {
    "fields": [
        {"name": "Lieferant", "type": "text"},
        {"name": "Rechnungsdatum", "type": "date"},
        {"name": "Gesamtbetrag", "type": "amount"},
        {"name": "MwSt-Satz", "type": "percent"},
    ]
}

result = intellidocpro.extract("rechnung.pdf", schema)
for v in result.values:
    print(v.field, v.value, v.confidence, v.source, v.needs_review)

# Infer a schema from a sample document
suggested = intellidocpro.suggest_schema("rechnung.pdf", engine="openai")
```

Field types: `text` / `number` / `date` / `amount` / `percent` / `enum` (requires
`enum_values`). Normalization rules: dates become ISO 8601; number/amount/percent
become floats (both German `10.055,50` and English `10,055.50` thousand separators
are handled); amounts carry a `currency`. `needs_review=True` when a value is
missing, confidence is low, or normalization fails.

## Engines and environment variables

| engine | environment variables | default model |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | `claude-opus-4-8` (override with `INTELLIDOCPRO_CLAUDE_MODEL`) |
| `openai` | `OPENAI_API_KEY` | `gpt-5.6-luna` (override with `INTELLIDOCPRO_OPENAI_MODEL`) |
| `azure_openai` | `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT` | the deployment name is the model |

Size limits: Claude 32MB, OpenAI/Azure 50MB; exceeding them raises `DocumentTooLarge`.

When engine/model are not specified, OpenAI `gpt-5.6-luna` is used by default.

## Cost estimation and engine comparison

```python
import intellidocpro

# Actual cost of a single extraction (based on the real token usage returned)
result = intellidocpro.extract("rechnung.pdf", schema, engine="openai")
cost = intellidocpro.cost_of(result)
print(cost.total_cost, cost.input_cost, cost.output_cost)  # USD

# Run the same file against several engine/model candidates concurrently;
# returns cost + result + latency for each candidate
entries = intellidocpro.compare_engines("rechnung.pdf", schema, candidates=[
    {"engine": "claude"},                              # engine default model
    {"engine": "claude", "model": "claude-haiku-4-5"},
    {"engine": "openai", "model": "gpt-5.6-luna"},
])
for e in entries:
    print(e.engine, e.model, e.ok, e.cost.total_cost if e.ok else e.error)
```

The price table lives in `intellidocpro.PRICES` (USD / 1M tokens; last updated date
in `intellidocpro.PRICES_AS_OF`) and can be overridden with a custom `prices`.
Unknown models return `pricing_known=False` instead of raising; Azure deployment
names are matched to the underlying model by longest substring
(e.g. `prod-gpt-5.6-terra-eu`). A failing candidate does not abort the whole
comparison (`ok=False` + `error`).

## Bulk processing

```python
import intellidocpro

report = intellidocpro.bulk_extract(
    ["a.pdf", "b.pdf", ("scan.pdf", pdf_bytes)],   # path / bytes / (filename, bytes)
    schema,
    engine="openai", model="gpt-5.6-luna",
    max_workers=4,
    on_update=lambda snap: print(snap.completed, "/", snap.total),  # called on every state change
)
print(report.completed, report.failed, report.needs_review_files, report.total_cost_usd)
```

A single failing file (corrupt file, API error) only marks that entry; the batch
continues. `on_update` receives an immutable snapshot that can be passed straight
to a UI.

The HTTP version is an async job with polling:

```bash
# Submit; returns a job_id immediately
curl -X POST http://localhost:8000/bulk \
  -F "files=@a.pdf" -F "files=@b.pdf" \
  -F 'schema={"fields":[{"name":"Lieferant"}]}' \
  -F "engine=openai" -F "model=gpt-5.6-luna"
# => 202 {"job_id": "7f6f71155c74", "total": 2}

# The frontend polls progress every second: queued/running/done/failed per file + running cost
curl http://localhost:8000/bulk/7f6f71155c74
```

Job state is kept in process memory; swap in Redis for multi-process deployments
(the interface stays the same).

## HTTP service

```bash
uvicorn server.app:app --port 8000
```

```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@rechnung.pdf" \
  -F 'schema={"fields":[{"name":"Lieferant"},{"name":"Gesamtbetrag","type":"amount"}]}' \
  -F "engine=claude"

curl -X POST http://localhost:8000/schema/suggest -F "file=@rechnung.pdf"
curl http://localhost:8000/health

# Multi-candidate cost comparison (omitting candidates = default model of every configured engine)
curl -X POST http://localhost:8000/compare \
  -F "file=@rechnung.pdf" \
  -F 'schema={"fields":[{"name":"Lieferant"}]}' \
  -F 'candidates=[{"engine":"claude"},{"engine":"openai","model":"gpt-5.6-luna"}]'
```

Error mapping: 422 (invalid document type/schema/engine name), 413 (too large),
503 (engine not configured), 502 (upstream API failure).

## Tests

```bash
pytest                      # unit + service tests, no network needed
pytest tests/integration    # real API end-to-end; engines without a configured key are skipped
```
