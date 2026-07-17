from abc import ABC, abstractmethod

from ..document import Document
from ..prompts import LLMSuggestedSchema
from ..result import ExtractionResult
from ..schema import (
    KEY_PATTERN,
    ExtractionSchema,
    FieldSpec,
    FieldType,
    SchemaChatMessage,
    SchemaRefinement,
    field_key_from_name,
)


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

    @abstractmethod
    def refine_schema(
        self,
        doc: Document,
        schema: ExtractionSchema,
        instruction: str,
        history: list[SchemaChatMessage],
    ) -> SchemaRefinement: ...

    def check_document(self, doc: Document) -> None:
        doc.ensure_max_size(self.max_bytes, engine=self.name)


def suggested_to_schema(suggested: LLMSuggestedSchema) -> ExtractionSchema:
    """Convert the LLM's schema proposal into a valid ExtractionSchema.

    An enum field proposed without values cannot validate, so it degrades
    to text rather than failing the whole suggestion.
    """
    fields = []
    seen: set[str] = set()
    seen_keys: set[str] = set()
    for f in suggested.fields:
        source_label = (f.source_label or "").strip().rstrip(":：").rstrip()
        if source_label and not any(character.isalnum() for character in source_label):
            source_label = ""
        name = source_label or f.name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        # Model-proposed key when it is valid and free; otherwise let the
        # schema validator derive one from the name.
        key = (f.key or "").strip().lower()
        if not KEY_PATTERN.match(key) or key in seen_keys:
            key = ""
        if not key:
            derived = field_key_from_name(name)
            key = derived if derived and derived not in seen_keys else ""
        if key:
            seen_keys.add(key)
        ftype, enum_values = f.type, f.enum_values
        if ftype == FieldType.ENUM and not enum_values:
            ftype, enum_values = FieldType.TEXT, None
        fields.append(
            FieldSpec(
                name=name, key=key, type=ftype, description=f.description, enum_values=enum_values
            )
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
