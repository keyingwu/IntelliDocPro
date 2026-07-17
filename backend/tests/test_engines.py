from types import SimpleNamespace

import pytest

from intellidocpro.document import Document
from intellidocpro.engines import available_engines, get_engine
from intellidocpro.engines.azure_openai import AzureOpenAIExtractor
from intellidocpro.engines.claude import ClaudeExtractor
from intellidocpro.engines.openai import OpenAIExtractor
from intellidocpro.engines.openai_common import document_part
from intellidocpro.errors import DocumentTooLarge, EngineNotConfigured, UnknownEngine
from intellidocpro.prompts import (
    EXTRACTION_SYSTEM,
    LLMExtractionOut,
    LLMFieldOut,
    LLMRefinedField,
    LLMRefinementOperation,
    LLMRefinementPlan,
    LLMSuggestedField,
    LLMSuggestedSchema,
    REFINE_SYSTEM,
)
from intellidocpro.schema import ExtractionSchema, FieldSpec, FieldType, SchemaChatMessage

PDF_DOC = Document.from_bytes(b"%PDF-1.4 fake", filename="invoice.pdf")
PNG_DOC = Document.from_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, filename="scan.png")

SCHEMA = ExtractionSchema(fields=[FieldSpec(name="Lieferant")])

LLM_OUT = LLMExtractionOut(
    fields=[
        LLMFieldOut(
            field="Lieferant",
            value="Meridian GmbH",
            raw_text="Meridian GmbH",
            currency=None,
            confidence="high",
            source_page=1,
            source_location="Kopf",
        )
    ]
)

SUGGESTED = LLMSuggestedSchema(
    fields=[
        LLMSuggestedField(
            name="Lieferant",
            key="supplier",
            source_label="Lieferant",
            type=FieldType.TEXT,
            description="top",
            enum_values=None,
        ),
        LLMSuggestedField(
            name="Rating",
            key="rating",
            source_label=None,
            type=FieldType.ENUM,
            description=None,
            enum_values=None,
        ),
        LLMSuggestedField(
            name="Lieferant",
            key="supplier_2",
            source_label="Lieferant",
            type=FieldType.TEXT,
            description="dupe",
            enum_values=None,
        ),
    ]
)

REFINEMENT_PLAN = LLMRefinementPlan(
    operations=[
        LLMRefinementOperation(
            action="add",
            target_name=None,
            field=LLMRefinedField(
                name="Zahlungsziel",
                key=None,
                type=FieldType.TEXT,
                description="payment term",
                enum_values=None,
                required=False,
            ),
            update_fields=[],
            evidence_text="Zahlungsziel: 30 Tage",
            evidence_page=1,
            reason="visible in sample",
        )
    ],
    rejections=[],
    message="Zahlungsziel wurde ergänzt.",
)

USAGE = SimpleNamespace(input_tokens=100, output_tokens=20)


class FakeClaudeClient:
    def __init__(self, parsed):
        self.calls = []
        self.messages = SimpleNamespace(parse=self._parse)
        self._parsed = parsed

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self._parsed, usage=USAGE)


class FakeOpenAIClient:
    def __init__(self, parsed):
        self.calls = []
        self.responses = SimpleNamespace(parse=self._parse)
        self._parsed = parsed

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self._parsed, usage=USAGE)


def test_claude_extract_pdf():
    fake = FakeClaudeClient(LLM_OUT)
    engine = ClaudeExtractor(client=fake)
    result = engine.extract(PDF_DOC, SCHEMA)

    assert result.values[0].value == "Meridian GmbH"
    assert result.engine == "claude"
    assert result.usage == {"input_tokens": 100, "output_tokens": 20}

    call = fake.calls[0]
    assert call["system"] == EXTRACTION_SYSTEM
    block = call["messages"][0]["content"][0]
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"


def test_claude_image_uses_image_block():
    fake = FakeClaudeClient(LLM_OUT)
    ClaudeExtractor(client=fake).extract(PNG_DOC, SCHEMA)
    block = fake.calls[0]["messages"][0]["content"][0]
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"


def test_claude_suggest_schema_degrades_bad_enum_and_dedupes():
    fake = FakeClaudeClient(SUGGESTED)
    schema = ClaudeExtractor(client=fake).suggest_schema(PDF_DOC)
    assert [f.name for f in schema.fields] == ["Lieferant", "Rating"]
    assert schema.fields[1].type == FieldType.TEXT  # enum without values degraded


def test_suggest_schema_prefers_verbatim_source_label_over_semantic_name():
    suggested = LLMSuggestedSchema(
        fields=[
            LLMSuggestedField(
                name="Steuerbetrag",
                key="",
                source_label="Gesamt Steuerbetrag",
                type=FieldType.AMOUNT,
                description="Normalized meaning belongs here",
                enum_values=None,
            )
        ]
    )
    fake = FakeClaudeClient(suggested)
    schema = ClaudeExtractor(client=fake).suggest_schema(PDF_DOC)
    assert schema.fields[0].name == "Gesamt Steuerbetrag"


def test_suggest_schema_uses_semantic_name_for_symbol_only_source_label():
    suggested = LLMSuggestedSchema(
        fields=[
            LLMSuggestedField(
                name="Steuersatz",
                key="",
                source_label="%",
                type=FieldType.PERCENT,
                description="Prozentsatz aus der Spalte %",
                enum_values=None,
            )
        ]
    )
    fake = FakeClaudeClient(suggested)
    schema = ClaudeExtractor(client=fake).suggest_schema(PDF_DOC)
    assert schema.fields[0].name == "Steuersatz"


def test_suggest_schema_removes_only_trailing_label_colon():
    suggested = LLMSuggestedSchema(
        fields=[
            LLMSuggestedField(
                name="Telefonnummer",
                key="",
                source_label="Tel. Nr.:",
                type=FieldType.TEXT,
                description=None,
                enum_values=None,
            )
        ]
    )
    fake = FakeClaudeClient(suggested)
    schema = ClaudeExtractor(client=fake).suggest_schema(PDF_DOC)
    assert schema.fields[0].name == "Tel. Nr."


def test_claude_refine_sends_document_schema_instruction_and_history():
    fake = FakeClaudeClient(REFINEMENT_PLAN)
    result = ClaudeExtractor(client=fake).refine_schema(
        PDF_DOC,
        SCHEMA,
        "Zahlungsziel ergänzen",
        [SchemaChatMessage(role="assistant", content="Vorherige Antwort")],
    )

    assert result.schema.fields[-1].name == "Zahlungsziel"
    call = fake.calls[0]
    assert call["system"] == REFINE_SYSTEM
    assert call["output_format"] is LLMRefinementPlan
    text = call["messages"][0]["content"][1]["text"]
    assert '"fields"' in text
    assert "Zahlungsziel ergänzen" in text
    assert "Vorherige Antwort" in text


def test_openai_extract_pdf_builds_input_file():
    fake = FakeOpenAIClient(LLM_OUT)
    engine = OpenAIExtractor(client=fake, model="gpt-test")
    result = engine.extract(PDF_DOC, SCHEMA)

    assert result.engine == "openai"
    assert result.model == "gpt-test"
    call = fake.calls[0]
    part = call["input"][0]["content"][0]
    assert part["type"] == "input_file"
    assert part["filename"] == "invoice.pdf"
    assert part["file_data"].startswith("data:application/pdf;base64,")


def test_openai_image_part():
    part = document_part(PNG_DOC)
    assert part["type"] == "input_image"
    assert part["image_url"].startswith("data:image/png;base64,")


def test_openai_refine_uses_shared_structured_output():
    fake = FakeOpenAIClient(REFINEMENT_PLAN)
    result = OpenAIExtractor(client=fake, model="gpt-test").refine_schema(
        PDF_DOC, SCHEMA, "add payment terms", []
    )

    assert result.changed is True
    call = fake.calls[0]
    assert call["instructions"] == REFINE_SYSTEM
    assert call["text_format"] is LLMRefinementPlan
    assert call["input"][0]["content"][0]["type"] == "input_file"


def test_pdf_part_filename_fallback():
    doc = Document.from_bytes(b"%PDF-1.4 fake", filename="weird.bin")
    assert document_part(doc)["filename"] == "document.pdf"


def test_azure_uses_deployment_as_model():
    fake = FakeOpenAIClient(LLM_OUT)
    engine = AzureOpenAIExtractor(client=fake, model="my-deployment")
    result = engine.extract(PDF_DOC, SCHEMA)
    assert result.model == "my-deployment"
    assert fake.calls[0]["model"] == "my-deployment"


def test_azure_refine_uses_deployment_and_shared_output():
    fake = FakeOpenAIClient(REFINEMENT_PLAN)
    engine = AzureOpenAIExtractor(client=fake, model="my-deployment")
    result = engine.refine_schema(PDF_DOC, SCHEMA, "add payment terms", [])
    assert result.schema.fields[-1].name == "Zahlungsziel"
    assert fake.calls[0]["model"] == "my-deployment"
    assert fake.calls[0]["text_format"] is LLMRefinementPlan


def test_size_limit_enforced():
    engine = ClaudeExtractor(client=FakeClaudeClient(LLM_OUT))
    engine.max_bytes = 4
    with pytest.raises(DocumentTooLarge):
        engine.extract(PDF_DOC, SCHEMA)


def test_not_configured_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(EngineNotConfigured):
        ClaudeExtractor()
    with pytest.raises(EngineNotConfigured):
        OpenAIExtractor()
    with pytest.raises(EngineNotConfigured):
        AzureOpenAIExtractor()


def test_get_engine_unknown():
    with pytest.raises(UnknownEngine, match="unknown engine"):
        get_engine("nope")


def test_available_engines_reflects_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    engines = available_engines()
    assert engines == {"claude": True, "openai": False, "azure_openai": False}


def test_default_models(monkeypatch):
    monkeypatch.setenv("INTELLIDOCPRO_OPENAI_MODEL", "gpt-5.6-sol")
    engine = OpenAIExtractor(client=FakeOpenAIClient(LLM_OUT))
    assert engine.model == "gpt-5.6-sol"

    monkeypatch.delenv("INTELLIDOCPRO_OPENAI_MODEL")
    assert OpenAIExtractor(client=FakeOpenAIClient(LLM_OUT)).model == "gpt-5.6-luna"
    assert ClaudeExtractor(client=FakeClaudeClient(LLM_OUT)).model == "claude-opus-4-8"
