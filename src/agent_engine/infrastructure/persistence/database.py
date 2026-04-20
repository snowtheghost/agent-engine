import sqlite3
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
    entry_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vault_created_at
    ON vault_entries(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_vault_kind
    ON vault_entries(kind);

CREATE TABLE IF NOT EXISTS resume_handles (
    resume_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    session_id TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        str(path),
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection
