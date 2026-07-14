import threading

import pytest

import docstill.bulk as bulk_module
from docstill.bulk import bulk_extract
from docstill.errors import DocstillError, EngineError
from docstill.result import ExtractionResult, FieldValue

PDF = b"%PDF-1.4 fake"
SCHEMA = {"fields": [{"name": "Lieferant"}]}


class FakeEngine:
    def __init__(self, fail_on: set[str] | None = None):
        self.model = "fake-model"
        self.fail_on = fail_on or set()
        self.calls = []
        self._lock = threading.Lock()

    def extract(self, doc, schema):
        with self._lock:
            self.calls.append(doc.filename)
        if doc.filename in self.fail_on:
            raise EngineError("api down", engine="fake")
        needs_review = doc.filename.startswith("review-")
        return ExtractionResult(
            values=[FieldValue(field="Lieferant", value="X", confidence="high",
                               needs_review=needs_review)],
            engine="fake", model="claude-haiku-4-5",
            usage={"input_tokens": 1_000_000, "output_tokens": 0},
        )


@pytest.fixture
def fake_engine(monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr(bulk_module, "get_engine", lambda name, model=None: engine)
    return engine


def test_bulk_happy_path(fake_engine):
    report = bulk_extract(
        [("a.pdf", PDF), ("b.pdf", PDF), ("c.pdf", PDF)], SCHEMA, engine="claude"
    )
    assert report.status == "done"
    assert report.total == 3
    assert report.completed == 3
    assert report.failed == 0
    assert [e.filename for e in report.entries] == ["a.pdf", "b.pdf", "c.pdf"]
    assert all(e.status == "done" for e in report.entries)
    # 3 files x 1M input tokens on haiku ($1/MTok)
    assert report.total_cost_usd == pytest.approx(3.0)
    assert report.entries[0].needs_review is False


def test_bulk_unreadable_file_becomes_failed_entry(fake_engine):
    report = bulk_extract([("ok.pdf", PDF), ("bad.txt", b"not a pdf")], SCHEMA)
    ok, bad = report.entries
    assert ok.status == "done"
    assert bad.status == "failed"
    assert bad.filename == "bad.txt"
    assert "unsupported" in bad.error
    assert report.completed == 1
    assert report.failed == 1
    assert fake_engine.calls == ["ok.pdf"]  # bad file never reaches the engine


def test_bulk_engine_failure_does_not_abort_batch(monkeypatch):
    engine = FakeEngine(fail_on={"b.pdf"})
    monkeypatch.setattr(bulk_module, "get_engine", lambda name, model=None: engine)
    report = bulk_extract([("a.pdf", PDF), ("b.pdf", PDF)], SCHEMA)
    assert report.completed == 1
    assert report.failed == 1
    assert report.entries[1].error == "api down"
    assert report.entries[1].duration_s is not None


def test_bulk_needs_review_aggregation(fake_engine):
    report = bulk_extract([("review-a.pdf", PDF), ("b.pdf", PDF)], SCHEMA)
    assert report.needs_review_files == 1
    assert report.entries[0].needs_review is True


def test_bulk_progress_snapshots(fake_engine):
    snapshots = []
    report = bulk_extract(
        [("a.pdf", PDF), ("b.pdf", PDF)], SCHEMA, on_update=snapshots.append
    )
    # first snapshot: everything queued; last: done
    assert snapshots[0].status == "running"
    assert all(e.status == "queued" for e in snapshots[0].entries)
    assert snapshots[-1].status == "done"
    assert snapshots[-1].completed == 2
    # snapshots are copies, not live references
    snapshots[0].entries[0].status = "failed"
    assert report.entries[0].status == "done"
    # monotonic completion counts
    completed_seq = [s.completed for s in snapshots]
    assert completed_seq == sorted(completed_seq)


def test_bulk_empty_documents_rejected(fake_engine):
    with pytest.raises(DocstillError, match="no documents"):
        bulk_extract([], SCHEMA)


def test_bulk_accepts_paths_and_bytes(fake_engine, tmp_path):
    p = tmp_path / "from-path.pdf"
    p.write_bytes(PDF)
    report = bulk_extract([p, PDF], SCHEMA)
    assert report.entries[0].filename == "from-path.pdf"
    assert report.entries[1].filename == "document"
    assert report.completed == 2


def test_bulk_bad_schema_raises_before_any_call(fake_engine):
    with pytest.raises(DocstillError):
        bulk_extract([("a.pdf", PDF)], {"fields": []})
    assert fake_engine.calls == []
