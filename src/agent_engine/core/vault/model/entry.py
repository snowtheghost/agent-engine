from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class VaultEntry:
    entry_id: str
    kind: str
    title: str
    body: str
    tags: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class VaultSearchHit:
    entry: VaultEntry
    score: float
    path: Path
