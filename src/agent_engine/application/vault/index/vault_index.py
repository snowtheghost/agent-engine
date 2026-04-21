from abc import ABC, abstractmethod

from agent_engine.core.vault.chunk import VaultChunk


class VaultIndex(ABC):

    @abstractmethod
    def upsert(self, chunks: list[VaultChunk]) -> None: ...

    @abstractmethod
    def delete_by_file(self, file_path: str) -> int: ...

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int,
        file_filter: str | None = None,
    ) -> list[tuple[VaultChunk, float]]: ...

    @abstractmethod
    def file_paths(self) -> set[str]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def close(self) -> None: ...
