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

    def fake_extract(doc, schema, engine="claude", model=None, **kw):
        captured["engine"] = engine
        captured["model"] = model
        captured["fields"] = [f.name for f in ExtractionSchema.coerce(schema).fields]
        return FAKE_RESULT

    monkeypatch.setattr(app_module.docstill, "extract", fake_extract)
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON, "engine": "openai", "model": "gpt-5.6-luna"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["values"][0]["value"] == "X"
    assert captured == {"engine": "openai", "model": "gpt-5.6-luna", "fields": ["Lieferant"]}


def test_extract_defaults_to_openai(client, monkeypatch):
    captured = {}

    def fake_extract(doc, schema, engine, model=None, **kw):
        captured.update(engine=engine, model=model)
        return FAKE_RESULT

    monkeypatch.setattr(app_module.docstill, "extract", fake_extract)
    resp = client.post(
        "/extract",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={"schema": SCHEMA_JSON},
    )

    assert resp.status_code == 200
    assert captured == {"engine": "openai", "model": None}


def test_models_endpoint(client):
    resp = client.get("/models")
    assert resp.status_code == 200
    body = resp.json()
    engines = body["engines"]
    assert set(engines) == {"claude", "openai", "azure_openai"}
    claude_ids = [m["id"] for m in engines["claude"]["models"]]
    assert "claude-opus-4-8" in claude_ids
    terra = next(m for m in engines["openai"]["models"] if m["id"] == "gpt-5.6-terra")
    assert terra["input_per_mtok"] == 2.5
    assert engines["openai"]["default"] == "gpt-5.6-luna"
    assert engines["azure_openai"]["models"] == []


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


def _wait_for_done(client, job_id, timeout=3.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/bulk/{job_id}").json()
        if body["status"] == "done":
            return body
        time.sleep(0.02)
    raise AssertionError("bulk job did not finish in time")


def test_bulk_job_lifecycle(client, monkeypatch):
    from docstill.bulk import BulkFileEntry, BulkReport

    def fake_bulk_extract(documents, schema, engine="claude", model=None, on_update=None):
        names = [name for name, _ in documents]
        entries = [
            BulkFileEntry(filename=n, status="done", needs_review=False, duration_s=0.1)
            for n in names
        ]
        report = BulkReport(
            status="done", engine=engine, model="m", total=len(names),
            completed=len(names), total_cost_usd=0.01, entries=entries,
        )
        on_update(report)
        return report

    monkeypatch.setattr(app_module.docstill, "bulk_extract", fake_bulk_extract)
    monkeypatch.setattr(app_module.docstill, "get_engine", lambda *a, **k: object())

    resp = client.post(
        "/bulk",
        files=[
            ("files", ("a.pdf", PDF, "application/pdf")),
            ("files", ("b.pdf", PDF, "application/pdf")),
        ],
        data={"schema": SCHEMA_JSON},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["total"] == 2

    final = _wait_for_done(client, body["job_id"])
    assert final["completed"] == 2
    assert [e["filename"] for e in final["entries"]] == ["a.pdf", "b.pdf"]
    assert final["total_cost_usd"] == 0.01


def test_bulk_unknown_job_404(client):
    assert client.get("/bulk/nope").status_code == 404


def test_bulk_engine_not_configured_rejected_upfront(client, monkeypatch):
    def boom(*a, **kw):
        raise EngineNotConfigured("no key")

    monkeypatch.setattr(app_module.docstill, "get_engine", boom)
    resp = client.post(
        "/bulk",
        files=[("files", ("a.pdf", PDF, "application/pdf"))],
        data={"schema": SCHEMA_JSON},
    )
    assert resp.status_code == 503


def test_suggest_ok(client, monkeypatch):
    fake_schema = ExtractionSchema(fields=[FieldSpec(name="Lieferant")])
    monkeypatch.setattr(
        app_module.docstill, "suggest_schema", lambda doc, engine="claude", model=None: fake_schema
    )
    resp = client.post("/schema/suggest", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert resp.status_code == 200
    assert resp.json()["fields"][0]["name"] == "Lieferant"


def test_refine_ok(client, monkeypatch):
    captured = {}

    def fake_refine(doc, schema, instruction, history=None, engine="claude", model=None):
        captured.update(
            instruction=instruction,
            history=history,
            engine=engine,
            model=model,
        )
        return docstill.SchemaRefinement(
            schema=ExtractionSchema(
                fields=[FieldSpec(name="Lieferant"), FieldSpec(name="Zahlungsziel")]
            ),
            message="Added Zahlungsziel.",
            changed=True,
            applied=["Added field: Zahlungsziel"],
            rejected=[],
        )

    import docstill

    monkeypatch.setattr(app_module.docstill, "refine_schema", fake_refine)
    resp = client.post(
        "/schema/refine",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data={
            "schema": SCHEMA_JSON,
            "instruction": "add payment terms",
            "engine": "openai",
            "model": "gpt-test",
            "history": json.dumps([{"role": "user", "content": "Earlier"}]),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["schema"]["fields"][-1]["name"] == "Zahlungsziel"
    assert captured == {
        "instruction": "add payment terms",
        "history": [{"role": "user", "content": "Earlier"}],
        "engine": "openai",
        "model": "gpt-test",
    }


@pytest.mark.parametrize(
    "data",
    [
        {"schema": SCHEMA_JSON, "instruction": "add B"},
        {"schema": SCHEMA_JSON, "instruction": "   ", "engine": "claude"},
        {"schema": "{bad", "instruction": "add B", "engine": "claude"},
        {
            "schema": json.dumps({"fields": []}),
            "instruction": "add B",
            "engine": "claude",
        },
        {
            "schema": SCHEMA_JSON,
            "instruction": "add B",
            "engine": "claude",
            "history": "{bad",
        },
        {
            "schema": SCHEMA_JSON,
            "instruction": "add B",
            "engine": "claude",
            "history": json.dumps([{"role": "system", "content": "bad"}]),
        },
    ],
)
def test_refine_invalid_form_returns_422(client, data):
    resp = client.post(
        "/schema/refine",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        data=data,
    )
    assert resp.status_code == 422


def test_refine_missing_file_returns_422(client):
    resp = client.post(
        "/schema/refine",
        data={"schema": SCHEMA_JSON, "instruction": "add B", "engine": "claude"},
    )
    assert resp.status_code == 422
