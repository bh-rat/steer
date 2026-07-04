"""
Per-skill SQLite storage.

Every skill that persists anything between runs ends up inventing a
storage location and a file format. Steer gives each skill a real
database with two scopes:

- ``user``: ``~/.steer/skills/<skill>/store.db``; survives across
  projects (caches, history, preferences).
- ``workspace``: ``<workspace>/.steer/<skill>/store.db``; travels with
  the project being operated on (plans, run records, project state).

Three access levels: a KV map, JSON-document tables, and raw SQL.

Usage:
    from steer.store import Store
    store = Store("my-skill")                       # user scope
    store = Store("my-skill", scope="workspace")    # project scope

    store.put("last_run", {"at": "2026-06-11", "ok": True})
    store.get("last_run")

    store.insert("runs", {"file": "report.pdf", "pages": 12})
    store.find("runs", {"file": "report.pdf"})

    store.query("SELECT COUNT(*) AS n FROM runs")
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .paths import skill_data_dir, workspace_steer_dir

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_identifier(name: str) -> str:
    if not _IDENTIFIER.match(name) or name.startswith("sqlite_"):
        raise ValueError(f"Invalid table name: {name!r}")
    return name


class Store:
    """SQLite-backed storage for one skill."""

    def __init__(self, skill: str, scope: str = "user", workspace: str = ".",
                 path: Optional[Union[str, Path]] = None):
        if not skill and path is None:
            raise ValueError("Store requires a skill name")
        if scope not in ("user", "workspace"):
            raise ValueError(f"Unknown scope: {scope!r} (use 'user' or 'workspace')")
        self.skill = skill
        self.scope = scope
        if path is not None:
            self.path = Path(path).expanduser()
        elif scope == "user":
            self.path = skill_data_dir(skill, create=True) / "store.db"
        else:
            from .paths import checked_skill_name

            base = (workspace_steer_dir(workspace, create=True)
                    / checked_skill_name(skill))
            base.mkdir(parents=True, exist_ok=True)
            self.path = base / "store.db"
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS kv ("
                "  key TEXT PRIMARY KEY,"
                "  value TEXT NOT NULL,"
                "  updated_at TEXT NOT NULL"
                ")"
            )
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- key/value ----------------------------------------------------

    def put(self, key: str, value: Any) -> None:
        """Store a JSON-serializable value under a key."""
        self.conn.execute(
            "INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key, json.dumps(value), _now()),
        )
        self.conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def delete(self, key: str) -> bool:
        cur = self.conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        self.conn.commit()
        return cur.rowcount > 0

    def keys(self) -> List[str]:
        rows = self.conn.execute("SELECT key FROM kv ORDER BY key").fetchall()
        return [r["key"] for r in rows]

    # -- JSON document tables ------------------------------------------

    def _ensure_table(self, table: str) -> str:
        table = _check_identifier(table)
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  data TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        return table

    def insert(self, table: str, doc: Dict[str, Any]) -> int:
        """Insert a JSON document; returns its id."""
        table = self._ensure_table(table)
        cur = self.conn.execute(
            f"INSERT INTO {table} (data, created_at) VALUES (?, ?)",
            (json.dumps(doc), _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def find(self, table: str, where: Optional[Dict[str, Any]] = None,
             limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find documents whose fields equal the given values."""
        table = self._ensure_table(table)
        sql = f"SELECT id, data, created_at FROM {table}"
        params: List[Any] = []
        if where:
            clauses = []
            for field_name, value in where.items():
                clauses.append("json_extract(data, ?) = ?")
                params.append(f"$.{field_name}")
                params.append(value)
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            doc = json.loads(row["data"])
            doc["_id"] = row["id"]
            doc["_created_at"] = row["created_at"]
            results.append(doc)
        return results

    def count(self, table: str, where: Optional[Dict[str, Any]] = None) -> int:
        return len(self.find(table, where))

    # -- raw SQL escape hatch ------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Run arbitrary SQL; returns rows as dicts. Commits on success."""
        cur = self.conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        self.conn.commit()
        return rows

    def tables(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]
