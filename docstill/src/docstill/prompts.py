"""Prompt templates and the LLM-facing output models shared by all engines.

The LLM output models are deliberately string-based (values come back as
strings) so the same strict JSON schema works across Claude, OpenAI and
Azure OpenAI structured outputs. Type normalization happens afterwards in
`docstill.normalize`.
"""

from typing import Literal

from pydantic import BaseModel

from .schema import ExtractionSchema, FieldType


class LLMFieldOut(BaseModel):
    field: str
    value: str | None
    raw_text: str | None
    currency: str | None
    confidence: Literal["high", "medium", "low"]
    source_page: int | None
    source_location: str | None


class LLMExtractionOut(BaseModel):
    fields: list[LLMFieldOut]


class LLMSuggestedField(BaseModel):
    name: str
    type: FieldType
    description: str | None
    enum_values: list[str] | None


class LLMSuggestedSchema(BaseModel):
    fields: list[LLMSuggestedField]


_TYPE_RULES = {
    FieldType.TEXT: "return the text verbatim",
    FieldType.NUMBER: "return the plain number as a string, keep it exactly as printed",
    FieldType.DATE: "normalize to ISO 8601 (YYYY-MM-DD) in `value`; keep the original wording in `raw_text`",
    FieldType.AMOUNT: "return the amount as printed in `value`, and put the ISO 4217 currency code (e.g. EUR, USD) in `currency`",
    FieldType.PERCENT: "return the percentage number as printed, without the % sign",
    FieldType.ENUM: "return exactly one of the allowed values",
}

EXTRACTION_SYSTEM = """\
You are a precise document data extraction engine.
You receive one document (PDF or image) and a list of fields to extract.

Rules:
- Extract each requested field from the document. Never invent values.
- If a field is not present or you cannot read it, set `value` to null.
- `raw_text` is the verbatim text from the document that the value came from.
- `confidence`: "high" if the value is clearly and unambiguously printed,
  "medium" if you had to interpret formatting or context,
  "low" if you are unsure or multiple candidate values exist.
- `source_page` is the 1-based page number where the value was found.
- `source_location` is a short description of where on the page it was found,
  in the language of the document (e.g. "Kopfzeile", "Summenblock", "table row 3").
- Return one entry per requested field, in the same order as requested,
  with `field` set to the exact requested field name.
"""


def field_lines(schema: ExtractionSchema) -> str:
    lines = []
    for i, f in enumerate(schema.fields, 1):
        parts = [f"{i}. {f.name} (type: {f.type.value})"]
        if f.description:
            parts.append(f"hint: {f.description}")
        parts.append(_TYPE_RULES[f.type])
        if f.type == FieldType.ENUM and f.enum_values:
            parts.append("allowed values: " + ", ".join(f.enum_values))
        if f.required:
            parts.append("this field is expected to be present")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def extraction_user_prompt(schema: ExtractionSchema) -> str:
    return (
        "Extract the following fields from the attached document:\n\n"
        + field_lines(schema)
    )


SUGGEST_SYSTEM = """\
You are a document analysis engine. You receive one sample document
(PDF or image) and propose an extraction schema for documents of this kind.

Rules:
- Identify the key fields a business user would want to extract from
  documents of this type (typically 4 to 10 fields).
- Use concise field names in the language of the document.
- Pick the most specific matching type: text, number, date, amount, percent,
  or enum. Use `enum` only when the document implies a small closed set of
  values, and list those values in `enum_values`; otherwise set it to null.
- `description` is a one-line extraction hint for each field.
"""

SUGGEST_USER = (
    "Analyze the attached sample document and propose an extraction schema for it."
)
