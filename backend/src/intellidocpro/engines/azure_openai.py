import os

from openai import OpenAI

from ..errors import EngineNotConfigured
from .openai_common import ResponsesAPIExtractor

_REQUIRED_VARS = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")


class AzureOpenAIExtractor(ResponsesAPIExtractor):
    """Azure OpenAI via the v1 API surface: the standard OpenAI client pointed
    at {endpoint}/openai/v1/, with the deployment name as the model."""

    name = "azure_openai"

    def __init__(self, model: str | None = None, client: object | None = None):
        deployment = model or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
        if client is None:
            if not self.is_configured():
                missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
                raise EngineNotConfigured(f"missing environment variables: {', '.join(missing)}")
            endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
            # accept both the bare resource endpoint and one that already
            # includes the /openai/v1 path
            if not endpoint.endswith("/openai/v1"):
                endpoint = f"{endpoint}/openai/v1"
            client = OpenAI(
                base_url=f"{endpoint}/",
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
            )
        if not deployment:
            raise EngineNotConfigured("AZURE_OPENAI_DEPLOYMENT is not set")
        self.model = deployment
        self.client = client

    @classmethod
    def is_configured(cls) -> bool:
        return all(os.environ.get(v) for v in _REQUIRED_VARS)

    @classmethod
    def default_model(cls) -> str:
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
