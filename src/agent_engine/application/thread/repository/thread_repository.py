from abc import ABC, abstractmethod

from agent_engine.core.thread.model.thread import Thread, ThreadEntry


class ThreadRepository(ABC):

    @abstractmethod
    def append(self, resume_key: str, entry: ThreadEntry) -> int: ...

    @abstractmethod
    def load(self, resume_key: str) -> Thread | None: ...

    @abstractmethod
    def delete(self, resume_key: str) -> bool: ...

    @abstractmethod
    def list_keys(self) -> list[str]: ...

    @abstractmethod
    def update_cursor(self, resume_key: str, cursor: int) -> None: ...
