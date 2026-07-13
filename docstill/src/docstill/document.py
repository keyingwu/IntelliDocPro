import base64
from dataclasses import dataclass
from pathlib import Path

from .errors import DocumentTooLarge, UnsupportedDocumentType

_MAGIC = [
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
]


def _sniff(data: bytes) -> str:
    for magic, media_type in _MAGIC:
        if data.startswith(magic):
            return media_type
    raise UnsupportedDocumentType(
        "unsupported document type; expected PDF, PNG or JPEG (detected by magic bytes)"
    )


@dataclass(frozen=True)
class Document:
    data: bytes
    media_type: str
    filename: str

    @classmethod
    def from_bytes(cls, data: bytes, filename: str = "document") -> "Document":
        if not data:
            raise UnsupportedDocumentType("empty document")
        return cls(data=data, media_type=_sniff(data), filename=filename)

    @classmethod
    def from_path(cls, path: "str | Path") -> "Document":
        p = Path(path)
        return cls.from_bytes(p.read_bytes(), filename=p.name)

    @property
    def is_pdf(self) -> bool:
        return self.media_type == "application/pdf"

    @property
    def size(self) -> int:
        return len(self.data)

    def base64(self) -> str:
        return base64.standard_b64encode(self.data).decode("ascii")

    def ensure_max_size(self, limit: int, engine: str) -> None:
        if self.size > limit:
            raise DocumentTooLarge(
                f"document is {self.size} bytes, exceeds the {limit} byte limit of engine '{engine}'"
            )


def coerce_document(value: "Document | bytes | str | Path") -> Document:
    """Accept a Document, raw bytes, or a filesystem path."""
    if isinstance(value, Document):
        return value
    if isinstance(value, bytes):
        return Document.from_bytes(value)
    return Document.from_path(value)
