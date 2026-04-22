from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ThreadChunk:
    chunk_id: str
    resume_key: str
    entry_index: int
    author: str
    timestamp: datetime
    content: str


@dataclass(frozen=True)
class ThreadSearchHit:
    chunk: ThreadChunk
    score: float
