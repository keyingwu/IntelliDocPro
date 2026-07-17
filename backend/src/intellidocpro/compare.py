"""Run the same document + schema across several engine/model candidates and
report the actual cost of each, so callers can compare price (and quality)
before committing to an engine."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel

from .document import Document, coerce_document
from .engines import available_engines, get_engine
from .errors import IntelliDocProError
from .pricing import CostBreakdown, ModelPrice, cost_of
from .result import ExtractionResult
from .schema import ExtractionSchema


class Candidate(BaseModel):
    engine: str
    model: str | None = None  # None = the engine's default model


class CompareEntry(BaseModel):
    engine: str
    model: str | None
    ok: bool
    cost: CostBreakdown | None = None
    result: ExtractionResult | None = None
    error: str | None = None
    duration_s: float


def default_candidates() -> list[Candidate]:
    """One candidate per engine that has credentials configured."""
    return [Candidate(engine=name) for name, ok in available_engines().items() if ok]


def compare_engines(
    document: "Document | bytes | str | Path",
    schema: "ExtractionSchema | dict",
    candidates: "list[Candidate | dict] | None" = None,
    prices: dict[str, ModelPrice] | None = None,
    max_workers: int = 4,
) -> list[CompareEntry]:
    """Extract with every candidate concurrently. A failing candidate becomes
    an entry with ok=False instead of failing the whole comparison. Entries
    come back in candidate order."""
    doc = coerce_document(document)
    parsed_schema = ExtractionSchema.coerce(schema)
    parsed = [c if isinstance(c, Candidate) else Candidate.model_validate(c) for c in candidates or default_candidates()]
    if not parsed:
        raise IntelliDocProError(
            "no candidates: pass candidates explicitly or configure at least one engine"
        )

    def run(cand: Candidate) -> CompareEntry:
        start = time.perf_counter()
        try:
            engine = get_engine(cand.engine, model=cand.model)
            result = engine.extract(doc, parsed_schema)
            return CompareEntry(
                engine=cand.engine,
                model=result.model,
                ok=True,
                cost=cost_of(result, prices),
                result=result,
                duration_s=round(time.perf_counter() - start, 2),
            )
        except IntelliDocProError as exc:
            return CompareEntry(
                engine=cand.engine,
                model=cand.model,
                ok=False,
                error=str(exc),
                duration_s=round(time.perf_counter() - start, 2),
            )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(run, parsed))
