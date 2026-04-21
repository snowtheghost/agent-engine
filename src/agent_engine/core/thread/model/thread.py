from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AttachmentMetadata:
    path: str
    filename: str
    content_type: str
    size: int
    description: str


@dataclass
class ThreadEntry:
    author: str
    content: str
    attachments: tuple[AttachmentMetadata, ...]
    timestamp: datetime


@dataclass
class Thread:
    resume_key: str
    entries: list[ThreadEntry] = field(default_factory=list)
    read_cursor: int = 0

    def append(self, entry: ThreadEntry) -> None:
        self.entries.append(entry)

    def unread_from(self, cursor: int) -> list[ThreadEntry]:
        return self.entries[cursor:]
