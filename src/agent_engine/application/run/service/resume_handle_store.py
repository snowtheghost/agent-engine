from abc import ABC, abstractmethod

from agent_engine.core.run.model.resume_handle import ResumeHandle


class ResumeHandleStore(ABC):

    @abstractmethod
    def get(self, resume_key: str) -> ResumeHandle | None: ...

    @abstractmethod
    def put(self, resume_key: str, handle: ResumeHandle) -> None: ...

    @abstractmethod
    def clear(self, resume_key: str) -> None: ...
