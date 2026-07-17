import pytest
from pydantic import ValidationError

from intellidocpro.errors import SchemaValidationError
from intellidocpro.schema import ExtractionSchema, FieldSpec, FieldType


def test_valid_schema():
    schema = ExtractionSchema(
        fields=[
            FieldSpec(name="Rechnungsnummer"),
            FieldSpec(name="Betrag", type=FieldType.AMOUNT),
            FieldSpec(name="Rating", type=FieldType.ENUM, enum_values=["AAA", "AA", "A"]),
        ]
    )
    assert schema.fields[0].type == FieldType.TEXT
    assert schema.fields[1].type == FieldType.AMOUNT


def test_empty_fields_rejected():
    with pytest.raises(ValidationError, match="at least one field"):
        ExtractionSchema(fields=[])


def test_duplicate_names_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        ExtractionSchema(fields=[FieldSpec(name="a"), FieldSpec(name="a")])


def test_blank_name_rejected():
    with pytest.raises(ValidationError):
        FieldSpec(name="   ")


def test_enum_requires_values():
    with pytest.raises(ValidationError, match="enum_values"):
        FieldSpec(name="Rating", type=FieldType.ENUM)


def test_coerce_from_dict():
    schema = ExtractionSchema.coerce(
        {"fields": [{"name": "Lieferant", "type": "text"}]}
    )
    assert isinstance(schema, ExtractionSchema)
    assert schema.fields[0].name == "Lieferant"


def test_coerce_bad_dict_raises_schema_error():
    with pytest.raises(SchemaValidationError):
        ExtractionSchema.coerce({"fields": []})
