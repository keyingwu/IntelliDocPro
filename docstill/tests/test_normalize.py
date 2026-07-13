import pytest

from docstill.normalize import assemble_result, parse_number
from docstill.prompts import LLMExtractionOut, LLMFieldOut
from docstill.schema import ExtractionSchema, FieldSpec, FieldType


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("25.000.000 EUR", 25_000_000.0),
        ("10.055,50 EUR", 10_055.50),
        ("3,25 %", 3.25),
        ("1,234.56", 1_234.56),
        ("1234.5", 1_234.5),
        ("19", 19.0),
        ("25,000", 25_000.0),
        ("-2,5", -2.5),
        ("12.480", 12_480.0),  # German thousands
        ("n/a", None),
        ("", None),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def _out(field, value, confidence="high", **kw):
    return LLMFieldOut(
        field=field,
        value=value,
        raw_text=kw.get("raw_text", value),
        currency=kw.get("currency"),
        confidence=confidence,
        source_page=kw.get("source_page"),
        source_location=kw.get("source_location"),
    )


SCHEMA = ExtractionSchema(
    fields=[
        FieldSpec(name="Lieferant"),
        FieldSpec(name="Nettobetrag", type=FieldType.AMOUNT),
        FieldSpec(name="MwSt", type=FieldType.PERCENT),
        FieldSpec(name="Datum", type=FieldType.DATE),
        FieldSpec(name="Rating", type=FieldType.ENUM, enum_values=["AAA", "AA", "A"]),
    ]
)


def test_assemble_full_result():
    llm = LLMExtractionOut(
        fields=[
            _out("Lieferant", "Meridian Supplies GmbH", source_page=1, source_location="Kopf"),
            _out("Nettobetrag", "8.450,00", currency="EUR"),
            _out("MwSt", "19"),
            _out("Datum", "2026-06-12"),
            _out("Rating", "AA"),
        ]
    )
    result = assemble_result(SCHEMA, llm, engine="claude", model="m", usage={"input_tokens": 1})

    assert [v.field for v in result.values] == [f.name for f in SCHEMA.fields]
    lieferant, betrag, mwst, datum, rating = result.values

    assert lieferant.value == "Meridian Supplies GmbH"
    assert lieferant.source.page == 1
    assert lieferant.source.location == "Kopf"
    assert not lieferant.needs_review

    assert betrag.value == 8450.0
    assert betrag.currency == "EUR"
    assert mwst.value == 19.0
    assert datum.value == "2026-06-12"
    assert rating.value == "AA"
    assert result.engine == "claude"
    assert result.usage == {"input_tokens": 1}


def test_missing_field_needs_review():
    llm = LLMExtractionOut(fields=[_out("Lieferant", "X")])
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    betrag = result.values[1]
    assert betrag.value is None
    assert betrag.needs_review


def test_null_value_needs_review():
    llm = LLMExtractionOut(
        fields=[_out("Lieferant", None, confidence="medium", raw_text=None)]
    )
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    assert result.values[0].value is None
    assert result.values[0].needs_review


def test_low_confidence_needs_review():
    llm = LLMExtractionOut(fields=[_out("Lieferant", "X", confidence="low")])
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    assert result.values[0].value == "X"
    assert result.values[0].needs_review


def test_bad_date_flagged():
    llm = LLMExtractionOut(fields=[_out("Datum", "12.06.2026")])
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    datum = result.values[3]
    assert datum.value == "12.06.2026"
    assert datum.needs_review


def test_enum_value_outside_allowed_flagged():
    llm = LLMExtractionOut(fields=[_out("Rating", "BBB")])
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    rating = result.values[4]
    assert rating.needs_review


def test_unparseable_number_keeps_raw_and_flags():
    llm = LLMExtractionOut(fields=[_out("MwSt", "neunzehn")])
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    mwst = result.values[2]
    assert mwst.value == "neunzehn"
    assert mwst.needs_review


def test_currency_only_kept_for_amount_fields():
    llm = LLMExtractionOut(fields=[_out("Lieferant", "X", currency="EUR")])
    result = assemble_result(SCHEMA, llm, engine="e", model="m", usage={})
    assert result.values[0].currency is None
