from abc import ABC, abstractmethod

from agent_engine.core.thread.model.chunk import ThreadChunk


class ThreadIndex(ABC):
    @abstractmethod
    def upsert(self, chunks: list[ThreadChunk]) -> None: ...

    @abstractmethod
    def delete_by_resume_key(self, resume_key: str) -> int: ...

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int,
        resume_key_filter: str | None = None,
    ) -> list[tuple[ThreadChunk, float]]: ...

    @abstractmethod
    def resume_keys(self) -> set[str]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def close(self) -> None: ...
