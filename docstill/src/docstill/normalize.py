"""Turn raw LLM extraction output into the typed, validated ExtractionResult."""

import re
from datetime import date

from .prompts import LLMExtractionOut, LLMFieldOut
from .result import ExtractionResult, FieldValue, SourceRef
from .schema import ExtractionSchema, FieldSpec, FieldType

_NUMERIC_TYPES = {FieldType.NUMBER, FieldType.AMOUNT, FieldType.PERCENT}


def parse_number(text: str) -> float | None:
    """Parse a human-formatted number, handling German (1.234,56) and
    English (1,234.56) separators. Returns None if unparseable."""
    s = re.sub(r"[^\d.,\-+]", "", text).strip()
    if not s or not re.search(r"\d", s):
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        # the rightmost separator is the decimal separator
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        # single comma with 1-2 trailing digits reads as a decimal separator,
        # anything else (e.g. 25,000,000 or 25,000) as thousands grouping
        parts = s.split(",")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_dot:
        # dots in groups of three (1.234.567) are thousands separators
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _is_iso_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False


def _normalize_one(spec: FieldSpec, out: LLMFieldOut) -> FieldValue:
    value: str | float | None = out.value
    parse_failed = False

    if out.value is not None:
        if spec.type in _NUMERIC_TYPES:
            parsed = parse_number(out.value)
            if parsed is None:
                parse_failed = True
                value = out.value
            else:
                value = parsed
        elif spec.type == FieldType.DATE:
            parse_failed = not _is_iso_date(out.value)
        elif spec.type == FieldType.ENUM:
            parse_failed = spec.enum_values is not None and out.value not in spec.enum_values

    source = None
    if out.source_page is not None or out.source_location is not None:
        source = SourceRef(page=out.source_page, location=out.source_location)

    needs_review = value is None or out.confidence == "low" or parse_failed
    return FieldValue(
        field=spec.key,
        value=value,
        raw_text=out.raw_text,
        currency=out.currency if spec.type == FieldType.AMOUNT else None,
        confidence=out.confidence,
        source=source,
        needs_review=needs_review,
    )


def assemble_result(
    schema: ExtractionSchema,
    llm_out: LLMExtractionOut,
    *,
    engine: str,
    model: str,
    usage: dict,
) -> ExtractionResult:
    """Map LLM output onto the schema: one FieldValue per schema field, in
    schema order. The model is asked to echo the field key, but a match on the
    display name is accepted as fallback. Fields the model did not return come
    back as missing."""
    by_field = {f.field: f for f in llm_out.fields}
    values = []
    for spec in schema.fields:
        out = by_field.get(spec.key) or by_field.get(spec.name)
        if out is None:
            values.append(
                FieldValue(field=spec.key, value=None, confidence="low", needs_review=True)
            )
        else:
            values.append(_normalize_one(spec, out))
    return ExtractionResult(values=values, engine=engine, model=model, usage=usage)
