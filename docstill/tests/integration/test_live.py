"""End-to-end extraction against real APIs. Each test runs only when its
engine's credentials are present in the environment.

Run: pytest tests/integration -v
"""

import os

import pytest

import docstill
from docstill.engines import ENGINES

from .pdf_fixture import minimal_pdf

INVOICE_PDF = minimal_pdf(
    [
        "RECHNUNG",
        "Lieferant: Meridian Supplies GmbH",
        "Rechnungsnummer: RE-2026-04821",
        "Rechnungsdatum: 12.06.2026",
        "Nettobetrag: 8.450,00 EUR",
        "MwSt.-Satz: 19 %",
        "Gesamtbetrag: 10.055,50 EUR",
    ]
)

SCHEMA = {
    "fields": [
        {"name": "Lieferant", "type": "text"},
        {"name": "Rechnungsnummer", "type": "text"},
        {"name": "Rechnungsdatum", "type": "date"},
        {"name": "Nettobetrag", "type": "amount"},
        {"name": "MwSt-Satz", "type": "percent", "description": "VAT rate"},
        {"name": "Gesamtbetrag", "type": "amount"},
    ]
}


def _configured(engine: str) -> bool:
    return ENGINES[engine].is_configured()


@pytest.mark.parametrize("engine", ["claude", "openai", "azure_openai"])
def test_extract_invoice(engine):
    if not _configured(engine):
        pytest.skip(f"{engine} credentials not configured")

    result = docstill.extract(INVOICE_PDF, SCHEMA, engine=engine)

    by_field = {v.field: v for v in result.values}
    assert len(result.values) == len(SCHEMA["fields"])
    assert by_field["Lieferant"].value == "Meridian Supplies GmbH"
    assert by_field["Rechnungsnummer"].value == "RE-2026-04821"
    assert by_field["Rechnungsdatum"].value == "2026-06-12"
    assert by_field["Nettobetrag"].value == 8450.0
    assert by_field["Nettobetrag"].currency == "EUR"
    assert by_field["MwSt-Satz"].value == 19.0
    assert by_field["Gesamtbetrag"].value == 10055.5
    assert result.usage.get("input_tokens", 0) > 0


@pytest.mark.parametrize("engine", ["claude", "openai", "azure_openai"])
def test_suggest_schema(engine):
    if not _configured(engine):
        pytest.skip(f"{engine} credentials not configured")

    schema = docstill.suggest_schema(INVOICE_PDF, engine=engine)
    assert len(schema.fields) >= 3
    names = " ".join(f.name.lower() for f in schema.fields)
    assert "rechnung" in names or "lieferant" in names or "betrag" in names
