import hashlib

from agent_engine.core.thread.model.chunk import ThreadChunk
from agent_engine.core.thread.model.thread import AttachmentMetadata, ThreadEntry

_MIN_CONTENT_LENGTH = 20


def chunk_entry(resume_key: str, entry_index: int, entry: ThreadEntry) -> ThreadChunk | None:
    content = _render_entry(entry)
    if len(content) < _MIN_CONTENT_LENGTH:
        return None
    chunk_id = _chunk_id(resume_key, entry_index, content)
    return ThreadChunk(
        chunk_id=chunk_id,
        resume_key=resume_key,
        entry_index=entry_index,
        author=entry.author,
        timestamp=entry.timestamp,
        content=content,
    )


def chunk_entries(resume_key: str, entries: list[ThreadEntry]) -> list[ThreadChunk]:
    chunks: list[ThreadChunk] = []
    for index, entry in enumerate(entries):
        chunk = chunk_entry(resume_key, index, entry)
        if chunk is not None:
            chunks.append(chunk)
    return chunks


def _render_entry(entry: ThreadEntry) -> str:
    parts: list[str] = [entry.content.strip()]
    for attachment in entry.attachments:
        attachment_text = _render_attachment(attachment)
        if attachment_text:
            parts.append(attachment_text)
    return "\n\n".join(part for part in parts if part)


def _render_attachment(attachment: AttachmentMetadata) -> str:
    lines: list[str] = [f"[Attachment: {attachment.filename} ({attachment.content_type})]"]
    if attachment.description:
        lines.append(attachment.description)
    return "\n".join(lines)


def _chunk_id(resume_key: str, entry_index: int, content: str) -> str:
    digest_input = f"{resume_key}:{entry_index}:{content[:100]}".encode()
    return hashlib.md5(digest_input).hexdigest()
