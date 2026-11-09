"""Idempotent schema migration driven by ``schema.sql`` and the Db2 catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from civiclens.db.connection import Db2Session

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
_CREATE = re.compile(
    r"^\s*CREATE\s+(?P<kind>TABLE|INDEX|UNIQUE\s+INDEX|VIEW)\s+\{schema\}\.(?P<name>[A-Z0-9_]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DdlStatement:
    kind: str  # TABLE | INDEX | VIEW
    name: str
    template: str


def load_statements(path: Path = SCHEMA_FILE) -> list[DdlStatement]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("--")]
    statements: list[DdlStatement] = []
    for chunk in "\n".join(lines).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _CREATE.match(chunk)
        if not match:
            raise ValueError(f"Unsupported statement in schema.sql: {chunk[:80]!r}")
        kind = "INDEX" if "INDEX" in match["kind"].upper() else match["kind"].upper()
        statements.append(DdlStatement(kind=kind, name=match["name"].upper(), template=chunk))
    return statements


_CATALOG_SQL = {
    "SCHEMA": "SELECT 1 FROM SYSCAT.SCHEMATA WHERE SCHEMANAME = ?",
    "TABLE": "SELECT 1 FROM SYSCAT.TABLES WHERE TABSCHEMA = ? AND TABNAME = ?",
    "VIEW": "SELECT 1 FROM SYSCAT.TABLES WHERE TABSCHEMA = ? AND TABNAME = ?",
    "INDEX": "SELECT 1 FROM SYSCAT.INDEXES WHERE INDSCHEMA = ? AND INDNAME = ?",
}


def _exists(db: Db2Session, kind: str, name: str | None = None) -> bool:
    params = (db.schema,) if name is None else (db.schema, name)
    return db.fetch_one(_CATALOG_SQL[kind], params) is not None


def migrate(db: Db2Session) -> dict[str, list[str]]:
    """Create any missing schema objects. Returns created/skipped object names."""
    created: list[str] = []
    skipped: list[str] = []
    if not _exists(db, "SCHEMA"):
        db.execute_raw_ddl(f"CREATE SCHEMA {db.schema}")
        created.append(f"SCHEMA {db.schema}")
    for stmt in load_statements():
        label = f"{stmt.kind} {db.schema}.{stmt.name}"
        if _exists(db, stmt.kind, stmt.name):
            skipped.append(label)
            continue
        db.execute_raw_ddl(db.sql(stmt.template))
        created.append(label)
    return {"created": created, "skipped": skipped}
