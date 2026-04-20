from abc import ABC, abstractmethod

from agent_engine.core.vault.model.entry import VaultEntry


class VaultRepository(ABC):

    @abstractmethod
    def save(self, entry: VaultEntry) -> None: ...

    @abstractmethod
    def get(self, entry_id: str) -> VaultEntry | None: ...

    @abstractmethod
    def list(self, limit: int = 100) -> list[VaultEntry]: ...

    @abstractmethod
    def delete(self, entry_id: str) -> bool: ...

    @abstractmethod
    def count(self) -> int: ...
