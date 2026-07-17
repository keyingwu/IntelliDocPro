from typing import Literal

from pydantic import BaseModel

Confidence = Literal["high", "medium", "low"]


class SourceRef(BaseModel):
    page: int | None = None
    location: str | None = None


class FieldValue(BaseModel):
    field: str
    value: str | float | None = None
    raw_text: str | None = None
    currency: str | None = None
    confidence: Confidence = "low"
    source: SourceRef | None = None
    needs_review: bool = True


class ExtractionResult(BaseModel):
    values: list[FieldValue]
    engine: str
    model: str
    usage: dict = {}
