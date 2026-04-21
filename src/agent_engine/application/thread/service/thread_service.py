from datetime import UTC, datetime

from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.core.thread.model.thread import AttachmentMetadata, Thread, ThreadEntry

AGENT_AUTHOR = "agent"

_QUEUED_HEADER = "[Queued messages while you were working:]\n"


class ThreadService:

    def __init__(self, repository: ThreadRepository) -> None:
        self._repository = repository

    def handle_message(
        self,
        resume_key: str,
        entry: ThreadEntry,
        interrupt: bool = True,
    ) -> str | None:
        self._repository.append(resume_key, entry)
        pending = self.get_pending_prompts(resume_key)
        if pending is None:
            return None
        prompt, _cursor = pending
        return prompt

    def log_reply(self, resume_key: str, content: str) -> None:
        entry = ThreadEntry(
            author=AGENT_AUTHOR,
            content=content,
            attachments=(),
            timestamp=datetime.now(UTC),
        )
        self._repository.append(resume_key, entry)

    def acknowledge(self, resume_key: str, cursor: int) -> None:
        self._repository.update_cursor(resume_key, cursor)

    def get_pending_prompts(self, resume_key: str) -> tuple[str, int] | None:
        thread = self._repository.load(resume_key)
        if thread is None:
            return None
        unread = [
            entry
            for entry in thread.unread_from(thread.read_cursor)
            if entry.author != AGENT_AUTHOR
        ]
        if not unread:
            return None
        new_cursor = len(thread.entries)
        if len(unread) == 1:
            prompt = _entry_to_prompt(unread[0])
        else:
            parts: list[str] = [_QUEUED_HEADER]
            for entry in unread:
                parts.append(_entry_to_prompt(entry))
                parts.append("")
            prompt = "\n".join(parts)
        return (prompt, new_cursor)

    def get_thread(self, resume_key: str) -> Thread | None:
        return self._repository.load(resume_key)

    def list_threads(self, limit: int = 50, offset: int = 0) -> list[str]:
        keys = self._repository.list_keys()
        return keys[offset : offset + limit]


def _entry_to_prompt(entry: ThreadEntry) -> str:
    parts: list[str] = []
    if entry.author:
        parts.append(f"[From: {entry.author}]")
        parts.append("")
    parts.append(entry.content)
    if entry.attachments:
        parts.append("")
        parts.append("[Attachments:]")
        for meta in entry.attachments:
            parts.append(_format_attachment(meta))
            if meta.description:
                parts.append(f"    [Vision: {meta.description}]")
    return "\n".join(parts)


def _format_attachment(meta: AttachmentMetadata) -> str:
    size_kb = meta.size / 1024
    if size_kb >= 1024:
        size_str = f"{size_kb / 1024:.1f} MB"
    else:
        size_str = f"{size_kb:.0f} KB"
    return f"  {meta.filename} ({meta.content_type}, {size_str}): {meta.path}"
