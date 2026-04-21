import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS resume_handles (
    resume_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    session_id TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thread_cursors (
    resume_key TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL,
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
