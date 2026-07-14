"""HTTP wrapper around docstill. Run with: uvicorn server.app:app"""

import json
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

import docstill
from docstill.envfile import load_env_file

from . import jobs

load_env_file(Path(__file__).parent.parent / ".env")
from docstill.errors import (
    DocumentTooLarge,
    EngineError,
    EngineNotConfigured,
    SchemaValidationError,
    UnknownEngine,
    UnsupportedDocumentType,
)

app = FastAPI(title="docstill", version="0.1.0")

from .platform_routes import router as platform_router  # noqa: E402

app.include_router(platform_router)

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


# Curated per-engine model choices offered in the UI. Azure has none:
# its "model" is whatever deployment name the user created.
_ENGINE_MODELS = {
    "claude": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
    "openai": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
    "azure_openai": [],
}


@app.get("/models")
def models():
    from docstill.engines import ENGINES
    from docstill.pricing import PRICES_AS_OF, lookup_price

    out = {}
    for engine_name, cls in ENGINES.items():
        entries = []
        for model_id in _ENGINE_MODELS.get(engine_name, []):
            price = lookup_price(model_id)
            entries.append(
                {
                    "id": model_id,
                    "input_per_mtok": price.input_per_mtok if price else None,
                    "output_per_mtok": price.output_per_mtok if price else None,
                }
            )
        out[engine_name] = {"default": cls.default_model(), "models": entries}
    return {"prices_as_of": PRICES_AS_OF, "engines": out}


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    extraction_schema: str = Form(..., alias="schema"),
    engine: str = Form("openai"),
    model: str | None = Form(None),
):
    try:
        schema_dict = json.loads(extraction_schema)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"schema is not valid JSON: {exc}") from exc
    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    result = docstill.extract(doc, schema_dict, engine=engine, model=model)
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
    engine: str = Form("openai"),
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
    jobs.publish(
        job_id,
        docstill.BulkReport(
            engine=engine,
            model=model,
            total=len(documents),
            entries=[docstill.BulkFileEntry(filename=name) for name, _ in documents],
        ),
    )

    def run() -> None:
        docstill.bulk_extract(
            documents, schema, engine=engine, model=model,
            on_update=lambda snap: jobs.publish(job_id, snap),
        )

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "total": len(documents)}


@app.get("/bulk/{job_id}")
def bulk_status(job_id: str):
    report = jobs.get(job_id)
    if report is None:
        return JSONResponse(status_code=404, content={"error": "JobNotFound", "detail": job_id})
    return report.model_dump()


@app.post("/schema/suggest")
async def suggest(
    file: UploadFile = File(...),
    engine: str = Form("openai"),
    model: str | None = Form(None),
):
    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    schema = docstill.suggest_schema(doc, engine=engine, model=model)
    return schema.model_dump()


@app.post("/schema/refine")
async def refine_schema(
    file: UploadFile = File(...),
    extraction_schema: str = Form(..., alias="schema"),
    instruction: str = Form(...),
    engine: str = Form(...),
    model: str | None = Form(None),
    history: str | None = Form(None),
):
    if not instruction.strip():
        raise SchemaValidationError("instruction must not be blank")
    try:
        schema_dict = json.loads(extraction_schema)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"schema is not valid JSON: {exc}") from exc
    try:
        history_value = json.loads(history) if history else None
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"history is not valid JSON: {exc}") from exc

    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    result = docstill.refine_schema(
        doc,
        schema_dict,
        instruction,
        history=history_value,
        engine=engine,
        model=model,
    )
    return result.model_dump(mode="json")


# ---- production static hosting of the webapp (single-process deploy) ----
# Must stay at the bottom of this module: the catch-all only wins for paths
# no API route above has claimed.
_WEBAPP_DIST = Path(__file__).parent.parent.parent / "webapp" / "dist"

if _WEBAPP_DIST.is_dir():  # only when the frontend has been built
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = (_WEBAPP_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(_WEBAPP_DIST.resolve())
        ):
            return FileResponse(candidate)
        return FileResponse(_WEBAPP_DIST / "index.html")
