import json

import pytest
from fastapi.testclient import TestClient

import server.app as app_module
from docstill.errors import EngineError, EngineNotConfigured
from docstill.result import ExtractionResult, FieldValue
from docstill.schema import ExtractionSchema, FieldSpec

PDF = b"%PDF-1.4 fake"
SCHEMA_JSON = json.dumps({"fields": [{"name": "Lieferant"}]})

FAKE_RESULT = ExtractionResult(
    values=[FieldValue(field="Lieferant", value="X", confidence="high", needs_review=False)],
    engine="claude",
    model="test-model",
    usage={},
)


@pytest.fixture
def client():
    return TestClient(app_module.app)


def test_health(client, monkeypatch):
    monkeypatch.setattr(
        app_module.docstill, "available_engines", lambda: {"claude": True, "openai": False, "azure_openai": False}
    )
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["engines"]["claude"] is True


def test_extract_ok(client, monkeypatch):
    captured = {}

    def fake_extract(doc, schema, engine="claude", **kw):
        captured["engine"] = engine
        captured["fields"] = [f.name for f in ExtractionSchema.coerce(schema).fields]
        return FAKE_RESULT

    monkeypatch.setattr(app_module.docstill, "extract", fake_extract)
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON, "engine": "openai"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["values"][0]["value"] == "X"
    assert captured == {"engine": "openai", "fields": ["Lieferant"]}


def test_extract_invalid_json_schema(client):
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": "{not json"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "SchemaValidationError"


def test_extract_empty_schema_fields(client):
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": json.dumps({"fields": []})},
    )
    assert resp.status_code == 422


def test_extract_unsupported_file(client):
    resp = client.post(
        "/extract",
        files={"file": ("a.txt", b"plain text", "text/plain")},
        data={"schema": SCHEMA_JSON},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "UnsupportedDocumentType"


def test_extract_unknown_engine(client):
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON, "engine": "nope"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "UnknownEngine"


def test_engine_not_configured_maps_503(client, monkeypatch):
    def boom(*a, **kw):
        raise EngineNotConfigured("no key")

    monkeypatch.setattr(app_module.docstill, "extract", boom)
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON},
    )
    assert resp.status_code == 503


def test_engine_error_maps_502(client, monkeypatch):
    def boom(*a, **kw):
        raise EngineError("api down", engine="claude")

    monkeypatch.setattr(app_module.docstill, "extract", boom)
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON},
    )
    assert resp.status_code == 502


def test_compare_ok(client, monkeypatch):
    from docstill.compare import CompareEntry
    from docstill.pricing import cost_of

    captured = {}

    def fake_compare(doc, schema, candidates=None):
        captured["candidates"] = candidates
        return [
            CompareEntry(
                engine="claude", model="claude-opus-4-8", ok=True,
                cost=cost_of(FAKE_RESULT), result=FAKE_RESULT, duration_s=1.0,
            )
        ]

    monkeypatch.setattr(app_module.docstill, "compare_engines", fake_compare)
    resp = client.post(
        "/compare",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON, "candidates": json.dumps([{"engine": "claude"}])},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "prices_as_of" in body
    assert body["entries"][0]["engine"] == "claude"
    assert captured["candidates"] == [{"engine": "claude"}]


def test_compare_bad_candidates_json(client):
    resp = client.post(
        "/compare",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON, "candidates": "{bad"},
    )
    assert resp.status_code == 422


def test_suggest_ok(client, monkeypatch):
    fake_schema = ExtractionSchema(fields=[FieldSpec(name="Lieferant")])
    monkeypatch.setattr(app_module.docstill, "suggest_schema", lambda doc, engine="claude": fake_schema)
    resp = client.post("/schema/suggest", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert resp.status_code == 200
    assert resp.json()["fields"][0]["name"] == "Lieferant"
