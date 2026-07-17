"""intellidocpro: schema-driven document field extraction with pluggable LLM engines."""

from pathlib import Path

from .bulk import BulkFileEntry, BulkReport, bulk_extract
from .compare import Candidate, CompareEntry, compare_engines
from .document import Document, coerce_document
from .engines import available_engines, get_engine
from .pricing import PRICES, PRICES_AS_OF, CostBreakdown, ModelPrice, cost_of
from .errors import (
    IntelliDocProError,
    DocumentTooLarge,
    EngineError,
    EngineNotConfigured,
    SchemaValidationError,
    UnknownEngine,
    UnsupportedDocumentType,
)
from .result import ExtractionResult, FieldValue, SourceRef
from .schema import (
    ExtractionSchema,
    FieldSpec,
    FieldType,
    SchemaChatMessage,
    SchemaRefinement,
    coerce_chat_history,
)

__all__ = [
    "BulkFileEntry",
    "BulkReport",
    "bulk_extract",
    "Candidate",
    "CompareEntry",
    "CostBreakdown",
    "Document",
    "ModelPrice",
    "PRICES",
    "PRICES_AS_OF",
    "compare_engines",
    "cost_of",
    "IntelliDocProError",
    "DocumentTooLarge",
    "EngineError",
    "EngineNotConfigured",
    "ExtractionResult",
    "ExtractionSchema",
    "FieldSpec",
    "FieldType",
    "FieldValue",
    "SchemaValidationError",
    "SchemaChatMessage",
    "SchemaRefinement",
    "SourceRef",
    "UnknownEngine",
    "UnsupportedDocumentType",
    "available_engines",
    "extract",
    "refine_schema",
    "suggest_schema",
]

DEFAULT_ENGINE = "openai"


def extract(
    document: "Document | bytes | str | Path",
    schema: "ExtractionSchema | dict",
    engine: str = DEFAULT_ENGINE,
    **engine_kwargs,
) -> ExtractionResult:
    """Extract the schema's fields from a document (PDF/PNG/JPEG).

    `document` may be a Document, raw bytes, or a filesystem path.
    `schema` may be an ExtractionSchema or an equivalent dict.
    `engine` is one of: claude, openai, azure_openai.
    """
    doc = coerce_document(document)
    parsed_schema = ExtractionSchema.coerce(schema)
    return get_engine(engine, **engine_kwargs).extract(doc, parsed_schema)


def suggest_schema(
    document: "Document | bytes | str | Path",
    engine: str = DEFAULT_ENGINE,
    **engine_kwargs,
) -> ExtractionSchema:
    """Propose an extraction schema from a sample document."""
    doc = coerce_document(document)
    return get_engine(engine, **engine_kwargs).suggest_schema(doc)


def refine_schema(
    document: "Document | bytes | str | Path",
    schema: "ExtractionSchema | dict",
    instruction: str,
    history: "list[SchemaChatMessage | dict] | None" = None,
    engine: str = DEFAULT_ENGINE,
    **engine_kwargs,
) -> SchemaRefinement:
    """Refine a schema against a required sample document and user instruction."""

    clean_instruction = instruction.strip()
    if not clean_instruction:
        raise SchemaValidationError("instruction must not be blank")
    doc = coerce_document(document)
    parsed_schema = ExtractionSchema.coerce(schema)
    parsed_history = coerce_chat_history(history)
    return get_engine(engine, **engine_kwargs).refine_schema(
        doc,
        parsed_schema,
        clean_instruction,
        parsed_history,
    )
