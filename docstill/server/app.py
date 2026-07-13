"""HTTP wrapper around docstill. Run with: uvicorn server.app:app"""

import json

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

import docstill
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


@app.post("/schema/suggest")
async def suggest(
    file: UploadFile = File(...),
    engine: str = Form("claude"),
):
    data = await file.read()
    doc = docstill.Document.from_bytes(data, filename=file.filename or "document")
    schema = docstill.suggest_schema(doc, engine=engine)
    return schema.model_dump()
