"""HTTP wrapper around docstill. Run with: uvicorn server.app:app"""

import json
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

import docstill
from docstill.envfile import load_env_file

load_env_file(Path(__file__).parent.parent / ".env")

# in-memory bulk job store; swap for Redis when running multiple processes
_jobs: dict[str, docstill.BulkReport] = {}
_jobs_lock = threading.Lock()
from docstill.errors import (
    DocumentTooLarge,
    EngineError,
    EngineNotConfigured,
    SchemaValidationError,
    UnknownEngine,
    UnsupportedDocumentType,
)

app = FastAPI(title="docstill", version="0.1.0")

_STATUS = {
    UnsupportedDocumentType: 422,
    SchemaValidationError: 422,
    UnknownEngine: 422,
    DocumentTooLarge: 413,
    EngineNotConfigured: 503,
    EngineError: 502,
}


@app.exception_handler(docstill.DocstillError)
async def docstill_error_handler(request, exc: docstill.DocstillError):
    status = next(
        (code for cls, code in _STATUS.items() if isinstance(exc, cls)), 500
    )
    return JSONResponse(
        status_code=status,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


@app.get("/health")
def health():
    return {"status": "ok", "engines": docstill.available_engines()}


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    extraction_schema: str = Form(..., alias="schema"),
    engine: str = Form("claude"),
):
    try:
        schema_dict = json.loads(extraction_schema)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"schema is not valid JSON: {exc}") from exc
    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    result = docstill.extract(doc, schema_dict, engine=engine)
    return result.model_dump()


@app.post("/compare")
async def compare(
    file: UploadFile = File(...),
    extraction_schema: str = Form(..., alias="schema"),
    candidates: str | None = Form(None),
):
    """Run the same extraction across engine/model candidates and report the
    actual cost per candidate. `candidates` is a JSON list like
    [{"engine": "claude"}, {"engine": "openai", "model": "gpt-5.6-luna"}];
    omitted = every configured engine with its default model."""
    try:
        schema_dict = json.loads(extraction_schema)
        candidate_list = json.loads(candidates) if candidates else None
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"invalid JSON in form field: {exc}") from exc
    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    entries = docstill.compare_engines(doc, schema_dict, candidates=candidate_list)
    return {
        "prices_as_of": docstill.PRICES_AS_OF,
        "entries": [e.model_dump() for e in entries],
    }


@app.post("/bulk", status_code=202)
async def bulk_start(
    files: list[UploadFile] = File(...),
    extraction_schema: str = Form(..., alias="schema"),
    engine: str = Form("claude"),
    model: str | None = Form(None),
):
    """Start a bulk extraction job over many files. Returns a job_id
    immediately; poll GET /bulk/{job_id} for per-file progress."""
    try:
        schema_dict = json.loads(extraction_schema)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"schema is not valid JSON: {exc}") from exc
    schema = docstill.ExtractionSchema.coerce(schema_dict)
    docstill.get_engine(engine, model=model)  # surface config errors as 4xx/503 now

    # (filename, bytes) tuples; bulk_extract turns unreadable ones into
    # failed entries and keeps the original filename
    documents = [(f.filename or "document", await f.read()) for f in files]

    job_id = uuid.uuid4().hex[:12]
    initial = docstill.BulkReport(
        engine=engine,
        model=model,
        total=len(documents),
        entries=[
            docstill.BulkFileEntry(filename=name) for name, _ in documents
        ],
    )
    with _jobs_lock:
        _jobs[job_id] = initial

    def publish(snapshot: docstill.BulkReport) -> None:
        with _jobs_lock:
            _jobs[job_id] = snapshot

    def run() -> None:
        docstill.bulk_extract(
            documents, schema, engine=engine, model=model, on_update=publish
        )

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "total": len(documents)}


@app.get("/bulk/{job_id}")
def bulk_status(job_id: str):
    with _jobs_lock:
        report = _jobs.get(job_id)
    if report is None:
        return JSONResponse(status_code=404, content={"error": "JobNotFound", "detail": job_id})
    return report.model_dump()


@app.post("/schema/suggest")
async def suggest(
    file: UploadFile = File(...),
    engine: str = Form("claude"),
):
    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    schema = docstill.suggest_schema(doc, engine=engine)
    return schema.model_dump()
