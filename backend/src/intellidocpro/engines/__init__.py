from ..errors import UnknownEngine
from .azure_openai import AzureOpenAIExtractor
from .base import Extractor
from .claude import ClaudeExtractor
from .openai import OpenAIExtractor

ENGINES: dict[str, type[Extractor]] = {
    ClaudeExtractor.name: ClaudeExtractor,
    OpenAIExtractor.name: OpenAIExtractor,
    AzureOpenAIExtractor.name: AzureOpenAIExtractor,
}


def get_engine(name: str, **kwargs) -> Extractor:
    try:
        cls = ENGINES[name]
    except KeyError:
        raise UnknownEngine(
            f"unknown engine '{name}'; available: {', '.join(sorted(ENGINES))}"
        ) from None
    return cls(**kwargs)


def available_engines() -> dict[str, bool]:
    """Engine name -> whether its credentials are configured in the environment."""
    return {name: cls.is_configured() for name, cls in ENGINES.items()}
