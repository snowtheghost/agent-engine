from abc import ABC, abstractmethod


class VectorIndex(ABC):

    @abstractmethod
    def upsert(self, entry_id: str, text: str) -> None: ...

    @abstractmethod
    def remove(self, entry_id: str) -> None: ...

    @abstractmethod
    def search(self, query: str, limit: int) -> list[tuple[str, float]]: ...

    @abstractmethod
    def close(self) -> None: ...
