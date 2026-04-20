import json
import sqlite3
from datetime import datetime

from agent_engine.application.vault.repository.vault_repository import VaultRepository
from agent_engine.core.vault.model.entry import VaultEntry


class SqliteVaultRepository(VaultRepository):

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, entry: VaultEntry) -> None:
        self._connection.execute(
            """
            INSERT INTO vault_entries (entry_id, kind, title, body, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_id) DO UPDATE SET
                kind = excluded.kind,
                title = excluded.title,
                body = excluded.body,
                tags = excluded.tags,
                created_at = excluded.created_at
            """,
            (
                entry.entry_id,
                entry.kind,
                entry.title,
                entry.body,
                json.dumps(list(entry.tags)),
                entry.created_at.isoformat(),
            ),
        )
        self._connection.commit()

    def get(self, entry_id: str) -> VaultEntry | None:
        row = self._connection.execute(
            """
            SELECT entry_id, kind, title, body, tags, created_at
            FROM vault_entries WHERE entry_id = ?
            """,
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return self._hydrate(row)

    def list(self, limit: int = 100) -> list[VaultEntry]:
        rows = self._connection.execute(
            """
            SELECT entry_id, kind, title, body, tags, created_at
            FROM vault_entries
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def delete(self, entry_id: str) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM vault_entries WHERE entry_id = ?", (entry_id,)
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM vault_entries").fetchone()
        return int(row["count"])

    @staticmethod
    def _hydrate(row: sqlite3.Row) -> VaultEntry:
        return VaultEntry(
            entry_id=row["entry_id"],
            kind=row["kind"],
            title=row["title"],
            body=row["body"],
            tags=tuple(json.loads(row["tags"])),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
