from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanReport:
    indexed_files: int
    skipped_unchanged: int
    removed_files: int
    total_files: int
    total_chunks: int


class VaultScanner(ABC):

    @abstractmethod
    def scan(self, force: bool = False) -> ScanReport: ...
