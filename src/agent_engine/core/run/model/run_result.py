from dataclasses import dataclass

from agent_engine.core.run.model.resume_handle import ResumeHandle


@dataclass(frozen=True)
class RunResult:
    run_id: str
    success: bool
    summary: str
    error: str | None
    duration_ms: int
    cost_usd: float
    turns: int
    resume_handle: ResumeHandle | None
