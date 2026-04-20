from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanReport:
    indexed: int
    skipped_unchanged: int
    removed: int
    total: int


class VaultScanner(ABC):

    @abstractmethod
    def scan(self, force: bool = False) -> ScanReport: ...
