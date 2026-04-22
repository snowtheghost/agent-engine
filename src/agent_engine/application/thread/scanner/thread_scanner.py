from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadScanReport:
    indexed_threads: int
    skipped_unchanged: int
    removed_threads: int
    total_threads: int
    total_chunks: int


class ThreadScanner(ABC):
    @abstractmethod
    def scan(self, force: bool = False) -> ThreadScanReport: ...
