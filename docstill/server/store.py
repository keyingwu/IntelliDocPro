"""SQLite persistence for the platform layer: assistants, runs, results.

Uses stdlib sqlite3 with WAL. One short-lived connection per operation keeps
things thread-safe (the bulk worker thread writes from outside the request
cycle). DOCSTILL_DB overrides the database location (tests point it at a tmp
file).
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from docstill.bulk import BulkReport

DEFAULT_DB = Path(__file__).parent / "data.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS assistants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  engine TEXT NOT NULL,
  model TEXT,
  schema_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  assistant_id TEXT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
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
  assistant_id TEXT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  status TEXT NOT NULL,
  needs_review INTEGER,
  error TEXT,
  duration_s REAL,
  cost_usd REAL,
  values_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_assistant ON results(assistant_id);
CREATE INDEX IF NOT EXISTS idx_runs_assistant ON runs(assistant_id);
"""

_initialized_paths: set[str] = set()


def db_path() -> Path:
    return Path(os.environ.get("DOCSTILL_DB", DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    path = db_path()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    key = str(path)
    if key not in _initialized_paths:
        conn.executescript(_SCHEMA_SQL)
        _initialized_paths.add(key)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- assistants ----

def _assistant_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["schema"] = json.loads(d.pop("schema_json"))
    return d

_STATS_SELECT = """
  a.*,
  COALESCE(s.doc_count, 0) AS doc_count,
  COALESCE(s.review_count, 0) AS review_count,
  COALESCE(s.failed_count, 0) AS failed_count,
  ROUND(COALESCE(s.total_cost_usd, 0), 6) AS total_cost_usd
FROM assistants a
LEFT JOIN (
  SELECT assistant_id,
         SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS doc_count,
         SUM(CASE WHEN needs_review = 1 THEN 1 ELSE 0 END) AS review_count,
         SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
         SUM(COALESCE(cost_usd, 0)) AS total_cost_usd
  FROM results GROUP BY assistant_id
) s ON s.assistant_id = a.id
"""


def create_assistant(
    name: str, description: str, engine: str, model: str | None, schema: dict
) -> dict:
    now = _now()
    aid = _new_id()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO assistants (id, name, description, engine, model, schema_json,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (aid, name, description, engine, model, json.dumps(schema), now, now),
        )
    return get_assistant(aid)


def list_assistants() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {_STATS_SELECT} ORDER BY a.created_at DESC"
        ).fetchall()
    return [_assistant_row_to_dict(r) for r in rows]


def get_assistant(assistant_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            f"SELECT {_STATS_SELECT} WHERE a.id = ?", (assistant_id,)
        ).fetchone()
    return _assistant_row_to_dict(row) if row else None


def update_assistant(assistant_id: str, **fields) -> dict | None:
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
        return get_assistant(assistant_id)
    sets.append("updated_at = ?")
    params.extend([_now(), assistant_id])
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE assistants SET {', '.join(sets)} WHERE id = ?", params
        )
        if cur.rowcount == 0:
            return None
    return get_assistant(assistant_id)


def delete_assistant(assistant_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM assistants WHERE id = ?", (assistant_id,))
        return cur.rowcount > 0


# ---- runs and results ----

def save_run(assistant_id: str, report: BulkReport) -> str:
    run_id = _new_id()
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, assistant_id, engine, model, total, completed,"
            " failed, total_cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, assistant_id, report.engine, report.model, report.total,
                report.completed, report.failed, report.total_cost_usd, now,
            ),
        )
        for entry in report.entries:
            values_json = (
                json.dumps([v.model_dump() for v in entry.result.values])
                if entry.result is not None
                else None
            )
            conn.execute(
                "INSERT INTO results (id, run_id, assistant_id, filename, status,"
                " needs_review, error, duration_s, cost_usd, values_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _new_id(), run_id, assistant_id, entry.filename, entry.status,
                    None if entry.needs_review is None else int(entry.needs_review),
                    entry.error, entry.duration_s,
                    entry.cost.total_cost if entry.cost else None,
                    values_json, now,
                ),
            )
    return run_id


def list_results(assistant_id: str, filter: str = "all") -> list[dict]:
    where = "assistant_id = ?"
    if filter == "review":
        where += " AND needs_review = 1"
    elif filter == "ready":
        where += " AND status = 'done' AND needs_review = 0"
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM results WHERE {where} ORDER BY created_at DESC, id",
            (assistant_id,),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        raw = d.pop("values_json")
        d["values"] = json.loads(raw) if raw else []
        d["needs_review"] = None if d["needs_review"] is None else bool(d["needs_review"])
        out.append(d)
    return out
