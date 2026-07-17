"""SQLite persistence for Document Agents, runs, results, and
uploaded documents (metadata in SQLite, bytes as blobs beside the database).

Uses stdlib sqlite3 with WAL. One short-lived connection per operation keeps
things thread-safe (the bulk worker thread writes from outside the request
cycle). INTELLIDOCPRO_DB overrides the database location (tests point it at a tmp
file).
"""

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from intellidocpro.bulk import BulkReport

DEFAULT_DB = Path(__file__).parent / "data.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  engine TEXT NOT NULL,
  model TEXT,
  schema_json TEXT NOT NULL,
  sample_document_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  content_type TEXT,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  engine TEXT NOT NULL,
  model TEXT,
  total INTEGER NOT NULL,
  completed INTEGER NOT NULL,
  failed INTEGER NOT NULL,
  total_cost_usd REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  document_id TEXT,
  filename TEXT NOT NULL,
  status TEXT NOT NULL,
  needs_review INTEGER,
  error TEXT,
  duration_s REAL,
  cost_usd REAL,
  values_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_agent ON results(agent_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON runs(agent_id);
"""

_initialized_paths: set[str] = set()


def db_path() -> Path:
    return Path(os.environ.get("INTELLIDOCPRO_DB", DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    path = db_path()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    key = str(path)
    if key not in _initialized_paths:
        conn.executescript(_SCHEMA_SQL)
        # migrate databases created before document persistence
        for stmt in (
            "ALTER TABLE agents ADD COLUMN sample_document_id TEXT",
            "ALTER TABLE results ADD COLUMN document_id TEXT",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        _initialized_paths.add(key)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- documents ----
# Uploaded files live as blobs next to the database; callers only ever see
# document ids. Lifecycle is owned entirely by this module: deleting an
# agent (or replacing its sample) removes the rows and the blobs.

def _blob_path(document_id: str) -> Path:
    return db_path().parent / "blobs" / document_id[:2] / document_id


def save_document(filename: str, data: bytes, content_type: str | None = None) -> dict:
    doc_id = _new_id()
    path = _blob_path(doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO documents (id, filename, content_type, size_bytes, sha256,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, filename, content_type, len(data),
             hashlib.sha256(data).hexdigest(), now),
        )
    return {
        "id": doc_id, "filename": filename, "content_type": content_type,
        "size_bytes": len(data), "created_at": now,
    }


def get_document(document_id: str) -> tuple[dict, bytes] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
    if row is None:
        return None
    try:
        data = _blob_path(document_id).read_bytes()
    except FileNotFoundError:
        return None
    return dict(row), data


def _delete_documents(conn: sqlite3.Connection, document_ids: list[str]) -> None:
    conn.executemany(
        "DELETE FROM documents WHERE id = ?", [(d,) for d in document_ids]
    )
    for doc_id in document_ids:
        _blob_path(doc_id).unlink(missing_ok=True)


# ---- agents ----

def _agent_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    schema = json.loads(d.pop("schema_json"))
    # Validation derives field keys missing from pre-key schemas, so every
    # schema leaving the store is fully keyed without a DB migration.
    try:
        from intellidocpro import ExtractionSchema

        schema = ExtractionSchema.coerce(schema).model_dump(mode="json")
    except Exception:
        pass
    d["schema"] = schema
    return d

_STATS_SELECT = """
  a.*,
  COALESCE(s.doc_count, 0) AS doc_count,
  COALESCE(s.review_count, 0) AS review_count,
  COALESCE(s.failed_count, 0) AS failed_count,
  ROUND(COALESCE(s.total_cost_usd, 0), 6) AS total_cost_usd
FROM agents a
LEFT JOIN (
  SELECT agent_id,
         SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS doc_count,
         SUM(CASE WHEN needs_review = 1 THEN 1 ELSE 0 END) AS review_count,
         SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
         SUM(COALESCE(cost_usd, 0)) AS total_cost_usd
  FROM results GROUP BY agent_id
) s ON s.agent_id = a.id
"""


def create_agent(
    name: str, description: str, engine: str, model: str | None, schema: dict
) -> dict:
    now = _now()
    aid = _new_id()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, description, engine, model, schema_json,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (aid, name, description, engine, model, json.dumps(schema), now, now),
        )
    return get_agent(aid)


def list_agents() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {_STATS_SELECT} ORDER BY a.created_at DESC"
        ).fetchall()
    return [_agent_row_to_dict(r) for r in rows]


def get_agent(agent_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            f"SELECT {_STATS_SELECT} WHERE a.id = ?", (agent_id,)
        ).fetchone()
    return _agent_row_to_dict(row) if row else None


def update_agent(agent_id: str, **fields) -> dict | None:
    allowed = {"name", "description", "engine", "model"}
    sets, params = [], []
    for key, value in fields.items():
        if key == "schema" and value is not None:
            sets.append("schema_json = ?")
            params.append(json.dumps(value))
        elif key in allowed and value is not None:
            sets.append(f"{key} = ?")
            params.append(value)
    if not sets:
        return get_agent(agent_id)
    sets.append("updated_at = ?")
    params.extend([_now(), agent_id])
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE agents SET {', '.join(sets)} WHERE id = ?", params
        )
        if cur.rowcount == 0:
            return None
    return get_agent(agent_id)


def set_sample_document(agent_id: str, document_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT sample_document_id FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        old = row["sample_document_id"]
        conn.execute(
            "UPDATE agents SET sample_document_id = ?, updated_at = ? WHERE id = ?",
            (document_id, _now(), agent_id),
        )
        if old and old != document_id:
            _delete_documents(conn, [old])
    return get_agent(agent_id)


def delete_agent(agent_id: str) -> bool:
    with _connect() as conn:
        doc_ids = [
            r["document_id"]
            for r in conn.execute(
                "SELECT DISTINCT document_id FROM results"
                " WHERE agent_id = ? AND document_id IS NOT NULL",
                (agent_id,),
            ).fetchall()
        ]
        sample = conn.execute(
            "SELECT sample_document_id FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if sample and sample["sample_document_id"]:
            doc_ids.append(sample["sample_document_id"])
        cur = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        if cur.rowcount == 0:
            return False
        _delete_documents(conn, doc_ids)
        return True


# ---- runs and results ----

def save_run(
    agent_id: str,
    report: BulkReport,
    document_ids: list[str | None] | None = None,
) -> str:
    """document_ids aligns with report.entries by index (bulk_extract preserves
    input order); None entries or a missing list leave results unlinked."""
    run_id = _new_id()
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, agent_id, engine, model, total, completed,"
            " failed, total_cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, agent_id, report.engine, report.model, report.total,
                report.completed, report.failed, report.total_cost_usd, now,
            ),
        )
        for i, entry in enumerate(report.entries):
            values_json = (
                json.dumps([v.model_dump() for v in entry.result.values])
                if entry.result is not None
                else None
            )
            document_id = (
                document_ids[i] if document_ids and i < len(document_ids) else None
            )
            conn.execute(
                "INSERT INTO results (id, run_id, agent_id, document_id, filename,"
                " status, needs_review, error, duration_s, cost_usd, values_json,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _new_id(), run_id, agent_id, document_id, entry.filename,
                    entry.status,
                    None if entry.needs_review is None else int(entry.needs_review),
                    entry.error, entry.duration_s,
                    entry.cost.total_cost if entry.cost else None,
                    values_json, now,
                ),
            )
    return run_id


def list_results(agent_id: str, filter: str = "all") -> list[dict]:
    where = "agent_id = ?"
    if filter == "review":
        where += " AND needs_review = 1"
    elif filter == "ready":
        where += " AND status = 'done' AND needs_review = 0"
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM results WHERE {where} ORDER BY created_at DESC, id",
            (agent_id,),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        raw = d.pop("values_json")
        d["values"] = json.loads(raw) if raw else []
        d["needs_review"] = None if d["needs_review"] is None else bool(d["needs_review"])
        out.append(d)
    return out
