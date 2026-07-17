import re
import unicodedata
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from .errors import SchemaValidationError


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    AMOUNT = "amount"
    PERCENT = "percent"
    ENUM = "enum"


KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def field_key_from_name(name: str) -> str:
    """Derive a snake_case machine key from a display label. ASCII-folds
    accents; labels with no usable ASCII (e.g. CJK) come back empty and the
    caller must fall back to a placeholder key."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", folded.lower()).strip("_")
    slug = slug[:64].rstrip("_")
    if slug and not slug[0].isalpha():
        slug = ("f_" + slug)[:64].rstrip("_")
    return slug


def _dedupe_key(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    for n in range(2, 1000):
        candidate = f"{base[: 64 - len(str(n)) - 1]}_{n}"
        if candidate not in taken:
            return candidate
    raise ValueError(f"cannot find a unique key for '{base}'")


class FieldSpec(BaseModel):
    name: str
    # Stable machine identifier: extraction round-trips, storage and exports
    # key on it, so renaming the display name never breaks the mapping.
    # Empty is tolerated on input; ExtractionSchema derives it from the name.
    key: str = ""
    type: FieldType = FieldType.TEXT
    description: str | None = None
    enum_values: list[str] | None = None
    required: bool = False

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field name must not be blank")
        return v.strip()

    @field_validator("key")
    @classmethod
    def _key_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if v and not KEY_PATTERN.match(v):
            raise ValueError(
                f"field key '{v}' must be snake_case: start with a letter, "
                "then lowercase letters, digits or underscores (max 64 chars)"
            )
        return v

    @model_validator(mode="after")
    def _enum_needs_values(self) -> "FieldSpec":
        if self.type == FieldType.ENUM and not self.enum_values:
            raise ValueError(f"field '{self.name}': type 'enum' requires enum_values")
        return self


class ExtractionSchema(BaseModel):
    fields: list[FieldSpec]

    @model_validator(mode="after")
    def _fields_valid(self) -> "ExtractionSchema":
        if not self.fields:
            raise ValueError("schema must contain at least one field")
        names = [f.name for f in self.fields]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate field names: {sorted(dupes)}")
        # Fill in missing keys (pre-key schemas, hand-written dicts) and make
        # them unique, so every validated schema is fully keyed.
        taken = {f.key for f in self.fields if f.key}
        explicit = [f.key for f in self.fields if f.key]
        key_dupes = {k for k in explicit if explicit.count(k) > 1}
        if key_dupes:
            raise ValueError(f"duplicate field keys: {sorted(key_dupes)}")
        for f in self.fields:
            if not f.key:
                base = field_key_from_name(f.name) or "field"
                f.key = _dedupe_key(base, taken)
                taken.add(f.key)
        return self

    @classmethod
    def coerce(cls, value: "ExtractionSchema | dict") -> "ExtractionSchema":
        """Accept an ExtractionSchema or a plain dict; raise SchemaValidationError on bad input."""
        if isinstance(value, cls):
            return value
        try:
            return cls.model_validate(value)
        except Exception as exc:
            raise SchemaValidationError(str(exc)) from exc


class SchemaChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message content must not be blank")
        return value.strip()


class RejectedSchemaRequest(BaseModel):
    request: str
    reason: str


class SchemaRefinement(BaseModel):
    """The complete validated schema plus structured UI metadata."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_value: ExtractionSchema = Field(alias="schema")
    message: str
    changed: bool
    applied: list[str]
    rejected: list[RejectedSchemaRequest]

    @property
    def schema(self) -> ExtractionSchema:
        return self.schema_value


_CHAT_HISTORY_ADAPTER = TypeAdapter(list[SchemaChatMessage])


def coerce_chat_history(
    value: "list[SchemaChatMessage | dict] | None",
) -> list[SchemaChatMessage]:
    if value is None:
        return []
    try:
        history = _CHAT_HISTORY_ADAPTER.validate_python(value)
    except Exception as exc:
        raise SchemaValidationError(f"history is invalid: {exc}") from exc
    if len(history) > 20:
        raise SchemaValidationError("history must contain at most 20 messages")
    return history
