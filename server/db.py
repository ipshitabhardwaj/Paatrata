"""SQLite storage. One file (DB_PATH, default data/paatrata.db), no ORM."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(os.environ.get("DB_PATH", "data/paatrata.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_docs (
  id TEXT PRIMARY KEY, title TEXT, mime_type TEXT, sha256 TEXT, url TEXT,
  is_primary_source INTEGER DEFAULT 0, pages_json TEXT, path TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS schemes (
  id TEXT PRIMARY KEY, name TEXT, department TEXT, jurisdiction TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS rule_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scheme_id TEXT REFERENCES schemes(id), version INTEGER,
  status TEXT CHECK (status IN ('draft','approved','superseded','rejected')),
  rules_json TEXT, issues_json TEXT, extractor TEXT, source_doc_id TEXT,
  created_at TEXT, approved_at TEXT, approved_by TEXT
);
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, purpose TEXT, backend TEXT, model TEXT, latency_ms INTEGER,
  cache_hit INTEGER, input_tokens INTEGER, output_tokens INTEGER, attempts INTEGER, error TEXT, created_at TEXT
);
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init(path: Path | None = None) -> None:
    with connect(path) as con:
        con.executescript(SCHEMA)


def row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("rules_json", "issues_json", "pages_json"):
        if k in d and d[k] is not None:
            d[k[:-5]] = json.loads(d.pop(k))
    return d


def log_call(con: sqlite3.Connection, purpose: str, meta: dict[str, Any]) -> None:
    con.execute(
        "INSERT INTO llm_calls(purpose, backend, model, latency_ms, cache_hit, input_tokens, output_tokens, attempts, error, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (purpose, meta.get("backend"), meta.get("model"), meta.get("latency_ms"), int(bool(meta.get("cache_hit"))),
         meta.get("input_tokens"), meta.get("output_tokens"), meta.get("attempts"), meta.get("error"), now()),
    )
