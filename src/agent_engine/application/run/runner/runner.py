from typing import Protocol

from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult


class Runner(Protocol):

    @property
    def provider_name(self) -> str: ...

    async def run(
        self,
        prompt: str,
        *,
        run_id: str,
        resume_handle: ResumeHandle | None,
        model: str | None,
    ) -> RunResult: ...

    async def interrupt(self, run_id: str) -> bool: ...

    def is_running(self, run_id: str) -> bool: ...

    def active_run_ids(self) -> set[str]: ...
