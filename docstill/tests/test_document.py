import pytest

from docstill.document import Document, coerce_document
from docstill.errors import DocumentTooLarge, UnsupportedDocumentType

PDF = b"%PDF-1.4 fake"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 8


def test_detects_pdf():
    doc = Document.from_bytes(PDF, filename="a.pdf")
    assert doc.media_type == "application/pdf"
    assert doc.is_pdf


def test_detects_png_and_jpeg():
    assert Document.from_bytes(PNG).media_type == "image/png"
    assert Document.from_bytes(JPG).media_type == "image/jpeg"


def test_extension_is_ignored_magic_wins():
    doc = Document.from_bytes(PDF, filename="lying-name.png")
    assert doc.media_type == "application/pdf"


def test_unsupported_type_rejected():
    with pytest.raises(UnsupportedDocumentType):
        Document.from_bytes(b"hello world plain text")


def test_empty_rejected():
    with pytest.raises(UnsupportedDocumentType):
        Document.from_bytes(b"")


def test_size_limit():
    doc = Document.from_bytes(PDF)
    doc.ensure_max_size(1024, engine="claude")  # fine
    with pytest.raises(DocumentTooLarge, match="claude"):
        doc.ensure_max_size(4, engine="claude")


def test_from_path(tmp_path):
    p = tmp_path / "sample.pdf"
    p.write_bytes(PDF)
    doc = coerce_document(p)
    assert doc.filename == "sample.pdf"
    assert doc.is_pdf


def test_coerce_bytes_and_passthrough():
    doc = coerce_document(PDF)
    assert doc.is_pdf
    assert coerce_document(doc) is doc


def test_base64_roundtrip():
    import base64

    doc = Document.from_bytes(PDF)
    assert base64.standard_b64decode(doc.base64()) == PDF
