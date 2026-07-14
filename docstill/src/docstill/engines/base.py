from abc import ABC, abstractmethod

from ..document import Document
from ..prompts import LLMSuggestedSchema
from ..result import ExtractionResult
from ..schema import ExtractionSchema, FieldSpec, FieldType


class Extractor(ABC):
    """A pluggable extraction engine. Implementations wrap one LLM provider."""

    name: str
    max_bytes: int

    @classmethod
    @abstractmethod
    def is_configured(cls) -> bool:
        """True if the required environment variables are present."""

    @classmethod
    @abstractmethod
    def default_model(cls) -> str:
        """The model used when none is passed (env override included).
        Empty string if there is no meaningful default (e.g. Azure without
        a configured deployment)."""

    @abstractmethod
    def extract(self, doc: Document, schema: ExtractionSchema) -> ExtractionResult: ...

    @abstractmethod
    def suggest_schema(self, doc: Document) -> ExtractionSchema: ...

    def check_document(self, doc: Document) -> None:
        doc.ensure_max_size(self.max_bytes, engine=self.name)


def suggested_to_schema(suggested: LLMSuggestedSchema) -> ExtractionSchema:
    """Convert the LLM's schema proposal into a valid ExtractionSchema.

    An enum field proposed without values cannot validate, so it degrades
    to text rather than failing the whole suggestion.
    """
    fields = []
    seen: set[str] = set()
    for f in suggested.fields:
        name = f.name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ftype, enum_values = f.type, f.enum_values
        if ftype == FieldType.ENUM and not enum_values:
            ftype, enum_values = FieldType.TEXT, None
        fields.append(
            FieldSpec(name=name, type=ftype, description=f.description, enum_values=enum_values)
        )
    return ExtractionSchema(fields=fields)


def usage_dict(usage: object) -> dict:
    """Extract input/output token counts from an SDK usage object, tolerating
    per-provider naming differences."""
    if usage is None:
        return {}
    out = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            out[key] = value
    return out
