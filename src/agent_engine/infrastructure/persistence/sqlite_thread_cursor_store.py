import sqlite3
from datetime import UTC, datetime

from agent_engine.application.thread.repository.thread_cursor_store import ThreadCursorStore


class SqliteThreadCursorStore(ThreadCursorStore):

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, resume_key: str) -> int:
        row = self._connection.execute(
            "SELECT cursor FROM thread_cursors WHERE resume_key = ?",
            (resume_key,),
        ).fetchone()
        if row is None:
            return 0
        return int(row["cursor"])

    def put(self, resume_key: str, cursor: int) -> None:
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO thread_cursors (resume_key, cursor, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(resume_key) DO UPDATE SET
                cursor = excluded.cursor,
                updated_at = excluded.updated_at
            """,
            (resume_key, cursor, now),
        )
        self._connection.commit()

    def clear(self, resume_key: str) -> None:
        self._connection.execute(
            "DELETE FROM thread_cursors WHERE resume_key = ?",
            (resume_key,),
        )
        self._connection.commit()
