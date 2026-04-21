import json
import re
from datetime import datetime
from pathlib import Path

import structlog

from agent_engine.application.thread.repository.thread_cursor_store import ThreadCursorStore
from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.core.thread.model.thread import AttachmentMetadata, Thread, ThreadEntry

logger = structlog.get_logger(__name__)

_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9_\-]+")
_JSONL_SUFFIX = ".jsonl"


class JsonlThreadRepository(ThreadRepository):

    def __init__(self, data_dir: Path, cursor_store: ThreadCursorStore) -> None:
        self._directory = data_dir / "threads"
        self._cursor_store = cursor_store

    def append(self, resume_key: str, entry: ThreadEntry) -> None:
        path = self._path(resume_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, object] = {
            "author": entry.author,
            "content": entry.content,
            "timestamp": entry.timestamp.isoformat(),
        }
        if entry.attachments:
            record["attachments"] = [
                {
                    "path": attachment.path,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "size": attachment.size,
                    "description": attachment.description,
                }
                for attachment in entry.attachments
            ]
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record) + "\n")

    def load(self, resume_key: str) -> Thread | None:
        path = self._path(resume_key)
        if not path.exists():
            return None
        entries = _read_entries(path)
        cursor = self._cursor_store.get(resume_key)
        return Thread(resume_key=resume_key, entries=entries, read_cursor=cursor)

    def delete(self, resume_key: str) -> bool:
        path = self._path(resume_key)
        if not path.exists():
            self._cursor_store.clear(resume_key)
            return False
        path.unlink()
        self._cursor_store.clear(resume_key)
        return True

    def list_keys(self) -> list[str]:
        if not self._directory.exists():
            return []
        keys: list[tuple[float, str]] = []
        for path in self._directory.iterdir():
            if not path.is_file() or path.suffix != _JSONL_SUFFIX:
                continue
            keys.append((path.stat().st_mtime, path.stem))
        keys.sort(key=lambda item: item[0], reverse=True)
        return [key for _timestamp, key in keys]

    def update_cursor(self, resume_key: str, cursor: int) -> None:
        self._cursor_store.put(resume_key, cursor)

    def _path(self, resume_key: str) -> Path:
        return self._directory / f"{_slugify(resume_key)}{_JSONL_SUFFIX}"


def _slugify(resume_key: str) -> str:
    cleaned = _SLUG_PATTERN.sub("_", resume_key).strip("_")
    return cleaned or "thread"


def _read_entries(path: Path) -> list[ThreadEntry]:
    entries: list[ThreadEntry] = []
    with open(path, "rb") as file:
        for line_number, raw_line in enumerate(file, 1):
            cleaned = raw_line.replace(b"\x00", b"")
            line = cleaned.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "thread_jsonl_corrupt_line_skipped",
                    path=str(path),
                    line_number=line_number,
                )
                continue
            attachments = tuple(
                AttachmentMetadata(
                    path=raw["path"],
                    filename=raw["filename"],
                    content_type=raw["content_type"],
                    size=int(raw["size"]),
                    description=raw.get("description", ""),
                )
                for raw in data.get("attachments", [])
            )
            entries.append(
                ThreadEntry(
                    author=data["author"],
                    content=data["content"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    attachments=attachments,
                )
            )
    return entries
