class DocstillError(Exception):
    """Base class for all docstill errors."""


class UnsupportedDocumentType(DocstillError):
    """The document is not a supported type (PDF, PNG, JPEG)."""


class DocumentTooLarge(DocstillError):
    """The document exceeds the size limit of the selected engine."""


class SchemaValidationError(DocstillError):
    """The extraction schema is invalid."""


class UnknownEngine(DocstillError):
    """No engine is registered under the requested name."""


class EngineNotConfigured(DocstillError):
    """Required credentials/environment variables for the engine are missing."""


class EngineError(DocstillError):
    """The engine's API call failed."""

    def __init__(self, message: str, *, engine: str, request_id: str | None = None):
        super().__init__(message)
        self.engine = engine
        self.request_id = request_id
