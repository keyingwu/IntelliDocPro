from enum import Enum

from pydantic import BaseModel, field_validator, model_validator

from .errors import SchemaValidationError


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    AMOUNT = "amount"
    PERCENT = "percent"
    ENUM = "enum"


class FieldSpec(BaseModel):
    name: str
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
