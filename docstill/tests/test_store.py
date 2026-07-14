from docstill.bulk import BulkFileEntry, BulkReport
from docstill.pricing import CostBreakdown
from docstill.result import ExtractionResult, FieldValue
from server import store

SCHEMA = {"fields": [{"name": "Lieferant", "type": "text", "description": None,
                      "enum_values": None, "required": False}]}


def _make_assistant(**kw):
    defaults = dict(name="Invoices", description="", engine="claude", model=None, schema=SCHEMA)
    defaults.update(kw)
    return store.create_assistant(**defaults)


def _report(needs_review=False, failed=False):
    result = ExtractionResult(
        values=[FieldValue(field="Lieferant", value="X", confidence="high",
                           needs_review=needs_review)],
        engine="claude", model="claude-haiku-4-5", usage={"input_tokens": 100},
    )
    entries = [
        BulkFileEntry(
            filename="a.pdf", status="done", result=result, needs_review=needs_review,
            duration_s=1.2,
            cost=CostBreakdown(engine="claude", model="claude-haiku-4-5", input_tokens=100,
                               output_tokens=10, pricing_known=True, total_cost=0.01),
        )
    ]
    if failed:
        entries.append(BulkFileEntry(filename="bad.txt", status="failed", error="nope"))
    return BulkReport(
        status="done", engine="claude", model="claude-haiku-4-5",
        total=len(entries), completed=1, failed=1 if failed else 0,
        total_cost_usd=0.01, entries=entries,
    )


def test_assistant_crud_roundtrip():
    a = _make_assistant()
    assert a["doc_count"] == 0
    assert a["schema"]["fields"][0]["name"] == "Lieferant"

    fetched = store.get_assistant(a["id"])
    assert fetched["name"] == "Invoices"

    updated = store.update_assistant(a["id"], name="Rechnungen", engine="openai")
    assert updated["name"] == "Rechnungen"
    assert updated["engine"] == "openai"

    assert store.delete_assistant(a["id"])
    assert store.get_assistant(a["id"]) is None
    assert not store.delete_assistant(a["id"])


def test_update_schema():
    a = _make_assistant()
    new_schema = {"fields": [{"name": "Betrag", "type": "amount", "description": None,
                              "enum_values": None, "required": False}]}
    updated = store.update_assistant(a["id"], schema=new_schema)
    assert updated["schema"]["fields"][0]["name"] == "Betrag"


def test_list_with_aggregates():
    a = _make_assistant()
    store.save_run(a["id"], _report(needs_review=True, failed=True))
    store.save_run(a["id"], _report())

    listed = {x["id"]: x for x in store.list_assistants()}[a["id"]]
    assert listed["doc_count"] == 2
    assert listed["review_count"] == 1
    assert listed["failed_count"] == 1
    assert listed["total_cost_usd"] == 0.02


def test_results_filters_and_values():
    a = _make_assistant()
    store.save_run(a["id"], _report(needs_review=True))
    store.save_run(a["id"], _report(needs_review=False, failed=True))

    all_rows = store.list_results(a["id"])
    assert len(all_rows) == 3
    review = store.list_results(a["id"], filter="review")
    assert len(review) == 1
    assert review[0]["values"][0]["value"] == "X"
    ready = store.list_results(a["id"], filter="ready")
    assert len(ready) == 1
    assert ready[0]["needs_review"] is False


def test_delete_cascades():
    a = _make_assistant()
    store.save_run(a["id"], _report())
    store.delete_assistant(a["id"])
    assert store.list_results(a["id"]) == []
