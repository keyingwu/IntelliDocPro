import os

import anthropic

from ..document import Document
from ..errors import EngineError, EngineNotConfigured
from ..normalize import assemble_result
from ..prompts import (
    EXTRACTION_SYSTEM,
    SUGGEST_SYSTEM,
    SUGGEST_USER,
    LLMExtractionOut,
    LLMSuggestedSchema,
    extraction_user_prompt,
)
from ..result import ExtractionResult
from ..schema import ExtractionSchema
from .base import Extractor, suggested_to_schema, usage_dict

DEFAULT_MODEL = "claude-opus-4-8"


class ClaudeExtractor(Extractor):
    name = "claude"
    max_bytes = 32 * 1024 * 1024

    def __init__(self, model: str | None = None, client: object | None = None):
        self.model = model or os.environ.get("DOCSTILL_CLAUDE_MODEL", DEFAULT_MODEL)
        if client is None:
            if not self.is_configured():
                raise EngineNotConfigured("ANTHROPIC_API_KEY is not set")
            client = anthropic.Anthropic()
        self.client = client

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _document_block(self, doc: Document) -> dict:
        source = {"type": "base64", "media_type": doc.media_type, "data": doc.base64()}
        if doc.is_pdf:
            return {"type": "document", "source": source}
        return {"type": "image", "source": source}

    def _parse(self, doc: Document, system: str, user_text: str, output_format: type):
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            self._document_block(doc),
                            {"type": "text", "text": user_text},
                        ],
                    }
                ],
                output_format=output_format,
            )
        except anthropic.APIError as exc:
            raise EngineError(
                str(exc), engine=self.name, request_id=getattr(exc, "request_id", None)
            ) from exc
        if response.parsed_output is None:
            raise EngineError("model returned no parseable output", engine=self.name)
        return response.parsed_output, usage_dict(response.usage)

    def extract(self, doc: Document, schema: ExtractionSchema) -> ExtractionResult:
        self.check_document(doc)
        llm_out, usage = self._parse(
            doc, EXTRACTION_SYSTEM, extraction_user_prompt(schema), LLMExtractionOut
        )
        return assemble_result(schema, llm_out, engine=self.name, model=self.model, usage=usage)

    def suggest_schema(self, doc: Document) -> ExtractionSchema:
        self.check_document(doc)
        suggested, _ = self._parse(doc, SUGGEST_SYSTEM, SUGGEST_USER, LLMSuggestedSchema)
        return suggested_to_schema(suggested)
