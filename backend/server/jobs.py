"""In-memory bulk job store shared by /bulk and /agents/{id}/bulk.
Swap for Redis when running multiple processes."""

import threading

from intellidocpro.bulk import BulkReport

_jobs: dict[str, BulkReport] = {}
_lock = threading.Lock()


def publish(job_id: str, report: BulkReport) -> None:
    with _lock:
        _jobs[job_id] = report


def get(job_id: str) -> BulkReport | None:
    with _lock:
        return _jobs.get(job_id)
