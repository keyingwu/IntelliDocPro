import os

from openai import OpenAI

from ..errors import EngineNotConfigured
from .openai_common import ResponsesAPIExtractor

DEFAULT_MODEL = "gpt-5.6-luna"


class OpenAIExtractor(ResponsesAPIExtractor):
    name = "openai"

    def __init__(self, model: str | None = None, client: object | None = None):
        self.model = model or os.environ.get("INTELLIDOCPRO_OPENAI_MODEL", DEFAULT_MODEL)
        if client is None:
            if not self.is_configured():
                raise EngineNotConfigured("OPENAI_API_KEY is not set")
            client = OpenAI()
        self.client = client

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    @classmethod
    def default_model(cls) -> str:
        return os.environ.get("INTELLIDOCPRO_OPENAI_MODEL", DEFAULT_MODEL)
