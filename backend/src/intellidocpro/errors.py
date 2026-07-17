class IntelliDocProError(Exception):
    """Base class for all intellidocpro errors."""


class UnsupportedDocumentType(IntelliDocProError):
    """The document is not a supported type (PDF, PNG, JPEG)."""


class DocumentTooLarge(IntelliDocProError):
    """The document exceeds the size limit of the selected engine."""


class SchemaValidationError(IntelliDocProError):
    """The extraction schema is invalid."""


class UnknownEngine(IntelliDocProError):
    """No engine is registered under the requested name."""


class EngineNotConfigured(IntelliDocProError):
    """Required credentials/environment variables for the engine are missing."""


class EngineError(IntelliDocProError):
    """The engine's API call failed."""

    def __init__(self, message: str, *, engine: str, request_id: str | None = None):
        super().__init__(message)
        self.engine = engine
        self.request_id = request_id
