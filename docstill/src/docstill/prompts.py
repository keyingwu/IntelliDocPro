"""Prompt templates and the LLM-facing output models shared by all engines.

The LLM output models are deliberately string-based (values come back as
strings) so the same strict JSON schema works across Claude, OpenAI and
Azure OpenAI structured outputs. Type normalization happens afterwards in
`docstill.normalize`.
"""

from typing import Literal

from pydantic import BaseModel

from .schema import ExtractionSchema, FieldType, SchemaChatMessage


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
    key: str
    source_label: str | None
    type: FieldType
    description: str | None
    enum_values: list[str] | None


class LLMSuggestedSchema(BaseModel):
    fields: list[LLMSuggestedField]


class LLMRefinedField(BaseModel):
    name: str
    key: str | None
    type: FieldType
    description: str | None
    enum_values: list[str] | None
    required: bool


class LLMRefinementOperation(BaseModel):
    action: Literal["add", "update", "delete"]
    target_name: str | None
    field: LLMRefinedField | None
    update_fields: list[
        Literal["name", "type", "description", "enum_values", "required"]
    ]
    evidence_text: str | None
    evidence_page: int | None
    reason: str


class LLMRefinementRejection(BaseModel):
    request: str
    reason: str


class LLMRefinementPlan(BaseModel):
    operations: list[LLMRefinementOperation]
    rejections: list[LLMRefinementRejection]
    message: str


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
  with `field` set to the exact requested field key (the snake_case
  identifier), never the printed label.
"""


def field_lines(schema: ExtractionSchema) -> str:
    lines = []
    for i, f in enumerate(schema.fields, 1):
        parts = [f'{i}. {f.key} (label: "{f.name}", type: {f.type.value})']
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


_SCHEMA_RULES = """\
- `key` is the field's stable machine identifier: concise English snake_case
  (lowercase letters, digits, underscores; starts with a letter), derived from
  the field's meaning, e.g. `invoice_number`, `equity_yield_percentage`. Keys
  must be unique across the schema and are independent of the document's
  language and of `name`.
- For fields proposed from the document, copy the exact printed field label
  into `name` whenever one exists. Preserve its original wording,
  capitalization, punctuation, abbreviations, and spacing. Do not translate,
  shorten, expand, normalize, or replace it with a semantic business name.
  Put normalized meaning or clarification in `description`, never in `name`.
- Treat a colon printed at the very end of a label (`:` or `：`) as a visual
  separator, not part of the field name. Remove only that trailing separator:
  for example, `Belegdatum:` becomes `Belegdatum`, while the periods in
  `Tel. Nr.:` are preserved and the name becomes `Tel. Nr.`.
- Only when no explicit usable label exists may you create a concise `name` in
  the document's language; explain in `description` that it was inferred from
  the visible location or context. A label containing only a unit or symbol
  such as `%`, `€`, or `$` is not a usable text label: in that case create a
  clear semantic name such as `Steuersatz`, while keeping the symbol's meaning
  in `description`.
- Pick the most specific matching type: text, number, date, amount, percent,
  or enum. Use `enum` only when the document implies a small closed set of
  values, and list those values in `enum_values`; otherwise set it to null.
- `description` is a one-line extraction hint for each field.
- Only propose scalar fields: one value per named field per document.
- A specifically named, uniquely identifiable row or category shown in a table
  may still be a scalar field when it appears once, or has one document-level
  total, and has one value. If the user requests multiple such fixed rows,
  create one separate scalar field for every confirmed printed label.
- Do not create generic line-item schemas, arrays, repeating columns, or a new
  field for every arbitrary or variable row in a line-item/transaction table.
"""

SUGGEST_SYSTEM = f"""\
You are a document analysis engine. You receive one sample document
(PDF or image) and propose an extraction schema for documents of this kind.

Rules:
- Be comprehensive: propose every field a business user could plausibly want
  to extract from documents of this type, not just the most prominent ones.
  Business documents often justify 8 to 20 fields. When unsure whether a
  field is useful, include it; the user can delete fields far more easily
  than discover missing ones.
- For every field, set `source_label` to the visible usable text label, with a
  terminal colon separator removed, or null when no such label exists. Use
  null for symbol-only/unit-only labels such as `%`. When `source_label` is not
  null, `name` must initially equal it exactly. For example, a printed label
  `Gesamt Steuerbetrag` must stay `Gesamt Steuerbetrag`, not `Steuerbetrag`;
  `Gesamtbetrag Rechnung` must not become `Gesamtbetrag`.
{_SCHEMA_RULES}"""

SUGGEST_USER = (
    "Analyze the attached sample document and propose an extraction schema for it."
)

REFINE_SYSTEM = f"""\
You are a document analysis engine planning safe changes to an extraction
schema. You receive one sample document, the complete current schema as JSON,
the conversation history, and the user's latest instruction.

Rules:
- Return only the requested add, update, and delete operations. Deterministic
  application code will produce the complete schema after your response.
- Never emit an operation for an existing field unless the latest instruction
  explicitly asks to change, rename, or delete that field.
- An add operation is allowed only when the sample visibly confirms the field:
  an explicit label, a label and value, or an unambiguous value-bearing region.
  A field that is merely common for this document type is NOT confirmed.
- Every add operation must include a short verbatim `evidence_text` from the
  sample and its 1-based `evidence_page`. If you cannot provide both, reject
  the requested field instead of adding or guessing it.
- For add operations with an explicit usable printed text label, the added
  field's `name` must equal that label verbatim. The evidence should include
  the same label. Symbol-only labels may use a semantic name as described above.
- Update and delete operations target existing fields by their exact current
  name. They do not require document evidence because the user is explicitly
  editing the current schema.
- For update operations, `update_fields` must list only the field properties
  that the latest instruction explicitly asks to change. Values for every
  property not listed there are ignored and preserved from the current schema.
  For add and delete operations, set `update_fields` to an empty list.
- Multiple requests may partially succeed. Emit valid operations for confirmed
  requests and one rejection entry per request that cannot be fulfilled.
- Do not reject a requested field merely because its value is displayed in a
  table. A fixed, explicitly named row with one value is eligible as a scalar
  field. For example, if the sample visibly shows separate single-value rows
  named `Fracht Versandort - Empfangsort`, `Road tax`, and `Fuel Surcharge`, a
  request for those three separate costs should produce three add operations.
- Preserve field order conceptually: additions append; updates keep position.
- For add operations set the new field's `key` (see the key rule below); it
  may be null to have one derived from the name. For update and delete
  operations `key` is ignored: a field's key never changes once created.
- `message` is a brief user-facing summary in the language of the latest user
  instruction. Mention both completed changes and rejected requests.
{_SCHEMA_RULES}"""


def refine_user_prompt(
    schema: ExtractionSchema,
    instruction: str,
    history: "list[SchemaChatMessage] | None" = None,
) -> str:
    import json

    parts = [
        "Complete current schema (authoritative):",
        json.dumps(schema.model_dump(mode="json"), ensure_ascii=False),
    ]
    if history:
        parts.extend(
            [
                "Earlier conversation (context only; the schema above is authoritative):",
                json.dumps(
                    [message.model_dump(mode="json") for message in history],
                    ensure_ascii=False,
                ),
            ]
        )
    else:
        parts.extend(["Earlier conversation:", "[]"])
    parts.extend(["Latest user instruction:", instruction])
    return "\n".join(parts)
