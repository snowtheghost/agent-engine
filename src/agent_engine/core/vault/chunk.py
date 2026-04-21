from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class VaultChunk:
    chunk_id: str
    file_path: str
    heading: str
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VaultSearchHit:
    chunk: VaultChunk
    score: float
    path: Path
