"""Tests for the top-level docstill.extract / suggest_schema API."""

import pytest

import docstill
from docstill.engines.claude import ClaudeExtractor
from docstill.errors import SchemaValidationError, UnknownEngine
from docstill.schema import ExtractionSchema, FieldSpec

from .test_engines import LLM_OUT, SUGGESTED, FakeClaudeClient

PDF = b"%PDF-1.4 fake"


@pytest.fixture
def fake_claude(monkeypatch):
    fake = FakeClaudeClient(LLM_OUT)
    monkeypatch.setattr(
        ClaudeExtractor, "__init__", lambda self, **kw: setattr(self, "client", fake) or setattr(self, "model", "test-model"),
    )
    return fake


def test_extract_with_bytes_and_dict_schema(fake_claude):
    result = docstill.extract(PDF, {"fields": [{"name": "Lieferant"}]})
    assert result.values[0].field == "Lieferant"
    assert result.values[0].value == "Meridian GmbH"


def test_extract_with_path(tmp_path, fake_claude):
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
    fake = FakeClaudeClient(SUGGESTED)
    monkeypatch.setattr(
        ClaudeExtractor, "__init__", lambda self, **kw: setattr(self, "client", fake) or setattr(self, "model", "test-model"),
    )
    schema = docstill.suggest_schema(PDF)
    assert [f.name for f in schema.fields] == ["Lieferant", "Rating"]
