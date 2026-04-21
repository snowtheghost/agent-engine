from abc import ABC, abstractmethod


class ThreadCursorStore(ABC):

    @abstractmethod
    def get(self, resume_key: str) -> int: ...

    @abstractmethod
    def put(self, resume_key: str, cursor: int) -> None: ...

    @abstractmethod
    def clear(self, resume_key: str) -> None: ...
