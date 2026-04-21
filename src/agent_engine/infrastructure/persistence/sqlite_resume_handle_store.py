import sqlite3
from datetime import UTC, datetime

from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.core.run.model.resume_handle import ResumeHandle


class SqliteResumeHandleStore(ResumeHandleStore):

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, resume_key: str) -> ResumeHandle | None:
        row = self._connection.execute(
            "SELECT provider, session_id FROM resume_handles WHERE resume_key = ?",
            (resume_key,),
        ).fetchone()
        if row is None:
            return None
        return ResumeHandle(provider=row["provider"], session_id=row["session_id"])

    def put(self, resume_key: str, handle: ResumeHandle) -> None:
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO resume_handles (resume_key, provider, session_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(resume_key) DO UPDATE SET
                provider = excluded.provider,
                session_id = excluded.session_id,
                updated_at = excluded.updated_at
            """,
            (resume_key, handle.provider, handle.session_id, now),
        )
        self._connection.commit()

    def clear(self, resume_key: str) -> None:
        self._connection.execute(
            "DELETE FROM resume_handles WHERE resume_key = ?", (resume_key,)
        )
        self._connection.commit()
