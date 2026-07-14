"""Bulk extraction: run one schema over many documents concurrently.

`bulk_extract` is synchronous and returns the final BulkReport. Callers that
need live progress (the HTTP job endpoint, a CLI progress bar) pass
`on_update`, which receives an immutable snapshot of the report after every
state change (a file starting, finishing, or failing).
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel

from .document import Document, coerce_document
from .engines import get_engine
from .errors import DocstillError
from .pricing import CostBreakdown, ModelPrice, cost_of
from .result import ExtractionResult
from .schema import ExtractionSchema

FileStatus = Literal["queued", "running", "done", "failed"]


class BulkFileEntry(BaseModel):
    filename: str
    status: FileStatus = "queued"
    result: ExtractionResult | None = None
    cost: CostBreakdown | None = None
    needs_review: bool | None = None  # any field flagged; None until done
    error: str | None = None
    duration_s: float | None = None


class BulkReport(BaseModel):
    status: Literal["running", "done"] = "running"
    engine: str
    model: str | None = None
    total: int
    completed: int = 0
    failed: int = 0
    needs_review_files: int = 0
    total_cost_usd: float = 0.0
    entries: list[BulkFileEntry]


BulkItem = "Document | bytes | str | Path | tuple[str, bytes]"


def _guess_name(item) -> str:
    if isinstance(item, tuple):
        return item[0]
    if isinstance(item, Document):
        return item.filename
    if isinstance(item, (str, Path)):
        return Path(item).name
    return "document"


def _coerce_item(item) -> Document:
    if isinstance(item, tuple):
        name, data = item
        return Document.from_bytes(data, filename=name)
    return coerce_document(item)


def bulk_extract(
    documents: "list[Document | bytes | str | Path | tuple[str, bytes]]",
    schema: "ExtractionSchema | dict",
    engine: str = "openai",
    model: str | None = None,
    max_workers: int = 4,
    on_update: "Callable[[BulkReport], None] | None" = None,
    prices: dict[str, ModelPrice] | None = None,
) -> BulkReport:
    """Extract `schema` from every document with one engine, concurrently.

    Per-file failures (unreadable file, API error) become failed entries and
    never abort the batch. Raises only for batch-level problems: an invalid
    schema, an unknown engine, or missing engine credentials.
    """
    if not documents:
        raise DocstillError("no documents given")
    parsed_schema = ExtractionSchema.coerce(schema)
    extractor = get_engine(engine, model=model)  # fail fast on config errors

    entries: list[BulkFileEntry] = []
    docs: list[Document | None] = []
    for item in documents:
        try:
            doc = _coerce_item(item)
            entries.append(BulkFileEntry(filename=doc.filename))
            docs.append(doc)
        except DocstillError as exc:
            entries.append(
                BulkFileEntry(filename=_guess_name(item), status="failed", error=str(exc))
            )
            docs.append(None)

    report = BulkReport(
        engine=engine,
        model=extractor.model,
        total=len(entries),
        failed=sum(1 for e in entries if e.status == "failed"),
        entries=entries,
    )
    lock = threading.Lock()

    def notify() -> None:
        if on_update is not None:
            on_update(report.model_copy(deep=True))

    def run(index: int) -> None:
        doc = docs[index]
        if doc is None:
            return
        entry = entries[index]
        with lock:
            entry.status = "running"
            notify()
        start = time.perf_counter()
        try:
            result = extractor.extract(doc, parsed_schema)
        except DocstillError as exc:
            with lock:
                entry.status = "failed"
                entry.error = str(exc)
                entry.duration_s = round(time.perf_counter() - start, 2)
                report.failed += 1
                notify()
            return
        cost = cost_of(result, prices)
        with lock:
            entry.status = "done"
            entry.result = result
            entry.cost = cost
            entry.needs_review = any(v.needs_review for v in result.values)
            entry.duration_s = round(time.perf_counter() - start, 2)
            report.completed += 1
            report.needs_review_files += 1 if entry.needs_review else 0
            report.total_cost_usd = round(report.total_cost_usd + cost.total_cost, 6)
            notify()

    notify()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(run, range(len(entries))))

    with lock:
        report.status = "done"
        notify()
    return report
