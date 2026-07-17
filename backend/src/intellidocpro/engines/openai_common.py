"""Shared Responses API logic for the OpenAI and Azure OpenAI engines."""

import openai as openai_sdk

from ..document import Document
from ..errors import EngineError
from ..normalize import assemble_result
from ..prompts import (
    EXTRACTION_SYSTEM,
    REFINE_SYSTEM,
    SUGGEST_SYSTEM,
    SUGGEST_USER,
    LLMExtractionOut,
    LLMRefinementPlan,
    LLMSuggestedSchema,
    extraction_user_prompt,
    refine_user_prompt,
)
from ..refinement import apply_refinement_plan
from ..result import ExtractionResult
from ..schema import ExtractionSchema, SchemaChatMessage, SchemaRefinement
from .base import Extractor, suggested_to_schema, usage_dict


def document_part(doc: Document) -> dict:
    if doc.is_pdf:
        filename = doc.filename if doc.filename.lower().endswith(".pdf") else "document.pdf"
        return {
            "type": "input_file",
            "filename": filename,
            "file_data": f"data:application/pdf;base64,{doc.base64()}",
        }
    return {
        "type": "input_image",
        "image_url": f"data:{doc.media_type};base64,{doc.base64()}",
    }


class ResponsesAPIExtractor(Extractor):
    """Base for engines that speak the OpenAI Responses API."""

    max_bytes = 50 * 1024 * 1024
    model: str
    client: object

    def _parse(self, doc: Document, system: str, user_text: str, text_format: type):
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=system,
                input=[
                    {
                        "role": "user",
                        "content": [
                            document_part(doc),
                            {"type": "input_text", "text": user_text},
                        ],
                    }
                ],
                text_format=text_format,
            )
        except openai_sdk.OpenAIError as exc:
            raise EngineError(
                str(exc), engine=self.name, request_id=getattr(exc, "request_id", None)
            ) from exc
        if response.output_parsed is None:
            raise EngineError("model returned no parseable output", engine=self.name)
        return response.output_parsed, usage_dict(response.usage)

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

    def refine_schema(
        self,
        doc: Document,
        schema: ExtractionSchema,
        instruction: str,
        history: list[SchemaChatMessage],
    ) -> SchemaRefinement:
        self.check_document(doc)
        plan, _ = self._parse(
            doc,
            REFINE_SYSTEM,
            refine_user_prompt(schema, instruction, history),
            LLMRefinementPlan,
        )
        return apply_refinement_plan(schema, plan)
