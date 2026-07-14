"""Tests for the top-level docstill.extract / suggest_schema API."""

import pytest

import docstill
from docstill.engines.openai import OpenAIExtractor
from docstill.errors import SchemaValidationError, UnknownEngine
from docstill.schema import ExtractionSchema, FieldSpec

from .test_engines import LLM_OUT, REFINEMENT_PLAN, SUGGESTED, FakeOpenAIClient

PDF = b"%PDF-1.4 fake"


@pytest.fixture
def fake_openai(monkeypatch):
    fake = FakeOpenAIClient(LLM_OUT)
    monkeypatch.setattr(
        OpenAIExtractor,
        "__init__",
        lambda self, **kw: setattr(self, "client", fake)
        or setattr(self, "model", "gpt-5.6-luna"),
    )
    return fake


def test_extract_with_bytes_and_dict_schema(fake_openai):
    result = docstill.extract(PDF, {"fields": [{"name": "Lieferant"}]})
    assert result.values[0].field == "Lieferant"
    assert result.values[0].value == "Meridian GmbH"
    assert result.engine == "openai"
    assert result.model == "gpt-5.6-luna"


def test_extract_with_path(tmp_path, fake_openai):
    p = tmp_path / "doc.pdf"
    p.write_bytes(PDF)
    result = docstill.extract(p, ExtractionSchema(fields=[FieldSpec(name="Lieferant")]))
    assert result.values[0].value == "Meridian GmbH"


def test_extract_bad_schema():
    with pytest.raises(SchemaValidationError):
        docstill.extract(PDF, {"fields": []})


def test_extract_unknown_engine():
    with pytest.raises(UnknownEngine):
        docstill.extract(PDF, {"fields": [{"name": "a"}]}, engine="nope")


def test_suggest_schema(monkeypatch):
    fake = FakeOpenAIClient(SUGGESTED)
    monkeypatch.setattr(
        OpenAIExtractor,
        "__init__",
        lambda self, **kw: setattr(self, "client", fake)
        or setattr(self, "model", "gpt-5.6-luna"),
    )
    schema = docstill.suggest_schema(PDF)
    assert [f.name for f in schema.fields] == ["Lieferant", "Rating"]


def test_refine_schema_public_api(monkeypatch):
    fake = FakeOpenAIClient(REFINEMENT_PLAN)
    monkeypatch.setattr(
        OpenAIExtractor,
        "__init__",
        lambda self, **kw: setattr(self, "client", fake)
        or setattr(self, "model", "gpt-5.6-luna"),
    )
    result = docstill.refine_schema(
        PDF,
        {"fields": [{"name": "Lieferant", "required": True}]},
        "Zahlungsziel ergänzen",
        history=[{"role": "user", "content": "Bitte genauer"}],
    )
    assert result.changed is True
    assert result.schema.fields[0].required is True
    assert result.schema.fields[-1].name == "Zahlungsziel"


def test_refine_schema_rejects_blank_instruction():
    with pytest.raises(SchemaValidationError, match="instruction"):
        docstill.refine_schema(PDF, {"fields": [{"name": "A"}]}, "   ")


def test_refine_schema_rejects_invalid_history():
    with pytest.raises(SchemaValidationError, match="history"):
        docstill.refine_schema(
            PDF,
            {"fields": [{"name": "A"}]},
            "add B",
            history=[{"role": "system", "content": "bad"}],
        )
