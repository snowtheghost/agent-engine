from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult


class CodexRunner:

    @property
    def provider_name(self) -> str:
        return "codex"

    async def run(
        self,
        prompt: str,
        *,
        run_id: str,
        resume_handle: ResumeHandle | None,
        model: str | None,
    ) -> RunResult:
        raise NotImplementedError(
            "CodexRunner is a stub. Implement when Codex provider support lands."
        )

    async def interrupt(self, run_id: str) -> bool:
        return False

    def is_running(self, run_id: str) -> bool:
        return False

    def active_run_ids(self) -> set[str]:
        return set()
