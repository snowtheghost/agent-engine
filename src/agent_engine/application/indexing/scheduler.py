from collections.abc import Callable
from typing import Protocol, runtime_checkable

IndexingJob = Callable[[], None]


@runtime_checkable
class IndexingScheduler(Protocol):
    def schedule(self, job: IndexingJob, *, name: str) -> None: ...
